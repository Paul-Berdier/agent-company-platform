#include "app/Application.h"

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "api/ClientGreffonPoste.h"
#include "app/BuildConfig.h"
#include "app/QmlEnums.h"
#include "auth/SessionHermes.h"
#include "commands/CommandRegistry.h"
#include "events/EventStreamService.h"
#include "gateway/DemandesAgent.h"
#include "gateway/GatewayClient.h"
#include "models/JsonListModel.h"
#include "navigation/NavigationModel.h"
#include "services/CompatibiliteHermes.h"
#include "services/HealthService.h"
#include "services/UpdateService.h"
#include "storage/CredentialVault.h"
#include "storage/SettingsStore.h"
#include "system/SystemAppearance.h"
#include "viewmodels/AccueilViewModel.h"
#include "viewmodels/DiagnosticsViewModel.h"
#include "viewmodels/DiscussionViewModel.h"
#include "viewmodels/PosteViewModel.h"
#include "viewmodels/ProjetsViewModel.h"
#include "viewmodels/QuestionsViewModel.h"
#include "viewmodels/QuotasViewModel.h"
#include "viewmodels/RoutageViewModel.h"
#include "viewmodels/ShellViewModel.h"

#include <QCoreApplication>
#include <QMetaType>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>
#include <QtQml>

namespace acp {

namespace {

constexpr char kQmlUri[] = "Acp.Runtime";

} // namespace

QString Application::version()
{
    // Valeur injectée par CMake depuis le fichier VERSION de la racine du dépôt : elle
    // n'est jamais saisie une seconde fois à la main.
    return QString::fromLatin1(ACP_DESKTOP_VERSION);
}

QString Application::buildInfo()
{
    return QStringLiteral("Qt %1 (compilation), %2")
        .arg(QString::fromLatin1(ACP_DESKTOP_QT_VERSION),
             QString::fromLatin1(ACP_DESKTOP_BUILD_TYPE));
}

QByteArray Application::userAgent()
{
    return QByteArrayLiteral("acp-desktop/") + ACP_DESKTOP_VERSION;
}

Application::Application(QObject *parent)
    : QObject(parent)
    , m_settings(new SettingsStore(this))
    , m_client(new ApiClient(this))
    , m_vault(makeCredentialVault(QStringLiteral("AgentCompanyPlatform")))
    , m_session(new SessionHermes(m_client, m_vault.get(), m_settings, this))
    , m_greffon(std::make_unique<ClientGreffonPoste>(m_client))
    , m_compatibilite(new CompatibiliteHermes(m_greffon.get(), this))
    , m_passerelle(new GatewayClient(m_client, this))
    , m_flux(new EventStreamService(m_client, m_greffon.get(), m_passerelle, this))
    , m_health(new HealthService(m_client, this))
    , m_navigation(new NavigationModel(this))
    , m_commands(new CommandRegistry(this))
    , m_appearance(new SystemAppearance(m_settings, this))
{
    m_client->setUserAgent(userAgent());

    m_shell = new ShellViewModel(m_client, m_session, m_health, m_navigation, m_commands,
                                 m_settings, this);
    // Retour du lien : une session gardée pendant une coupure retente sa rotation.
    connect(m_health, &HealthService::changed, this, [this] {
        if (m_health->linkStatus() == LinkStatus::Online
            && m_session->etat() == SessionStatus::HorsLigne) {
            m_session->reessayer();
        }
        // Retour du lien : les pages visibles relisent tout de suite (cahier P8 § 6.1).
        if (m_health->linkStatus() == LinkStatus::Online) {
            m_flux->signalerLien(true);
        } else if (m_health->linkStatus() == LinkStatus::Offline) {
            m_flux->signalerLien(false);
        }
    });
    m_diagnostics = new DiagnosticsViewModel(m_client, m_session, m_compatibilite, m_passerelle, m_health,
                                             m_settings, m_appearance, m_vault.get(), version(),
                                             buildInfo(), this);
    m_diagnostics->setFlux(m_flux);
    // Pages de pilotage : elles lisent seulement quand elles sont affichées et la session établie.
    m_accueil = new AccueilViewModel(m_client, m_greffon.get(), m_flux, this);
    m_projets = new ProjetsViewModel(m_client, m_greffon.get(), m_flux, this);
    m_questions = new QuestionsViewModel(m_client, m_greffon.get(), m_flux, this);
    m_poste = new PosteViewModel(m_greffon.get(), m_compatibilite, m_flux, this);
    m_quotas = new QuotasViewModel(m_greffon.get(), m_flux, this);
    m_routage = new RoutageViewModel(m_client, m_greffon.get(), m_flux, this);
    // Demandes de l'agent (approval, clarify) et discussion : sur la passerelle JSON-RPC.
    m_demandes = new DemandesAgent(m_passerelle, this);
    m_discussion = new DiscussionViewModel(m_passerelle, m_flux, this);
    // La compatibilité se lit en session (/v1/meta est derrière la porte de Hermes).
    connect(m_session, &SessionHermes::sessionEtablie, m_compatibilite, &CompatibiliteHermes::verifier);
    connect(m_session, &SessionHermes::sessionPerdue, m_compatibilite, &CompatibiliteHermes::oublier);
    // Passerelle JSON-RPC : ouverte dès la session établie (sessions.changed, demandes de
    // l'agent), fermée à sa perte ; coupée si le contrat JSON-RPC servi n'est pas celui de la
    // station.
    connect(m_session, &SessionHermes::sessionEtablie, m_passerelle, &GatewayClient::ouvrir);
    connect(m_session, &SessionHermes::sessionPerdue, m_passerelle, &GatewayClient::fermer);
    // Temps réel : sondage léger, veille du kanban et pages actives suivent la session.
    connect(m_session, &SessionHermes::sessionEtablie, m_flux, &EventStreamService::demarrer);
    connect(m_session, &SessionHermes::sessionPerdue, m_flux, &EventStreamService::arreter);
    // Session perdue (déconnexion, jeton refusé) : la discussion affichée est oubliée. Connexion
    // faite APRÈS celle de la passerelle (ordre d'appel des slots) : la passerelle est déjà
    // fermée, aucune fermeture n'est émise vers Hermes.
    connect(m_session, &SessionHermes::sessionPerdue, m_discussion, &DiscussionViewModel::quitter);
    connect(m_compatibilite, &CompatibiliteHermes::change, this, [this] {
        const CompatibilityStatus::State etat = m_compatibilite->etat();
        const bool verdictRendu = etat != CompatibilityStatus::NonVerifiee
            && etat != CompatibilityStatus::Verification && etat != CompatibilityStatus::Injoignable;
        if (verdictRendu && !m_compatibilite->discussionDisponible()) {
            m_passerelle->fermer();
        }
    });
    m_updates = new UpdateService(version(), this);
    registerBuiltinCommands();
    connect(m_navigation, &NavigationModel::historyChanged, this,
            [this] { m_commands->setContext(m_commands->context()); });
}

Application::~Application()
{
    shutdown();
    // Les vues dépendent du transport créé avant elles. QObject détruit normalement ses
    // enfants dans l'ordre de création : les vues doivent ici partir en premier, pendant
    // que leurs services et le coffre sont encore disponibles.
    while (!children().isEmpty()) delete children().last();
}

void Application::registerQmlTypes()
{
    qRegisterMetaType<acp::ApiError>("acp::ApiError");
    qmlRegisterUncreatableType<JsonListModel>(kQmlUri, 1, 0, "JsonListModel",
        QStringLiteral("Le modèle est fourni par la station."));

    // Énumérations : types non instanciables, exposés pour que QML puisse comparer des
    // états sans recopier des chaînes magiques.
    qmlRegisterUncreatableType<LinkStatus>(kQmlUri, 1, 0, "LinkStatus",
                                           QStringLiteral("LinkStatus n'expose que des "
                                                          "énumérations."));
    qmlRegisterUncreatableType<SessionStatus>(kQmlUri, 1, 0, "SessionStatus",
                                              QStringLiteral("SessionStatus n'expose que des "
                                                             "énumérations."));
    qmlRegisterUncreatableType<CompatibilityStatus>(kQmlUri, 1, 0, "CompatibilityStatus",
                                                    QStringLiteral("CompatibilityStatus n'expose "
                                                                   "que des énumérations."));
    qmlRegisterUncreatableType<ApiFailure>(kQmlUri, 1, 0, "ApiFailure",
                                           QStringLiteral("ApiFailure n'expose que des "
                                                          "énumérations."));
    qmlRegisterUncreatableType<VaultStatus>(kQmlUri, 1, 0, "VaultStatus",
                                            QStringLiteral("VaultStatus n'expose que des "
                                                           "énumérations."));
    // Les modèles sont exposés par instance ; leur type doit être connu pour que QML
    // puisse en déclarer une propriété.
    qmlRegisterUncreatableType<NavigationModel>(kQmlUri, 1, 0, "NavigationModel",
                                                QStringLiteral("NavigationModel est fourni par "
                                                               "l'application."));
    qmlRegisterUncreatableType<CommandRegistry>(kQmlUri, 1, 0, "CommandRegistry",
                                                QStringLiteral("CommandRegistry est fourni par "
                                                               "l'application."));

    // Singletons d'instance : QML lit, il ne construit pas. Aucun de ces objets n'expose
    // de secret — voir les propriétés déclarées dans chaque en-tête.
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Shell", m_shell);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Session", m_session);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Health", m_health);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Compatibility", m_compatibilite);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Gateway", m_passerelle);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Streams", m_flux);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Accueil", m_accueil);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Projets", m_projets);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Questions", m_questions);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Poste", m_poste);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Quotas", m_quotas);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Routage", m_routage);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Demandes", m_demandes);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Discussion", m_discussion);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Navigation", m_navigation);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Commands", m_commands);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Appearance", m_appearance);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Diagnostics", m_diagnostics);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Updates", m_updates);
}

bool Application::load(QQmlApplicationEngine *engine)
{
    if (!engine) {
        return false;
    }
    bool failed = false;
    QObject::connect(
        engine, &QQmlApplicationEngine::objectCreationFailed, engine,
        [&failed](const QUrl &) { failed = true; }, Qt::DirectConnection);

    engine->loadFromModule(QStringLiteral("Acp.Desktop"), QStringLiteral("App"));
    return !failed && !engine->rootObjects().isEmpty();
}

void Application::start()
{
    // Restauration : aucune valeur par défaut n'est inventée. Sans URL mémorisée, la
    // station ouvre son écran de première ouverture.
    m_client->setAllowInsecureLoopback(m_settings->allowInsecureLoopback());
    const QUrl storedUrl = m_settings->serverUrl();
    if (!storedUrl.isEmpty()) {
        const ApiError error = m_client->setBaseUrl(storedUrl);
        if (error.isError()) {
            m_shell->notify(QStringLiteral("L'adresse mémorisée a été refusée : %1")
                                .arg(error.message()));
        }
    }

    if (m_client->isConfigured()) {
        m_health->probeNow();
        m_health->setPeriodicProbeEnabled(true);
        // Jeton mémorisé pour ce serveur (et consentement donné) : rafraîchissement immédiat.
        m_session->restaurer();
    }
}

void Application::shutdown()
{
    m_flux->arreter();
    m_passerelle->fermer();
    m_health->setPeriodicProbeEnabled(false);
    m_settings->flush();
}

void Application::registerBuiltinCommands()
{
    const auto alwaysAvailable = [](const CommandContext &) {
        return CommandAvailability::Available;
    };

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.back"), QStringLiteral("Revenir à l'écran précédent"),
        QStringLiteral("Navigation"), {}, QStringLiteral("Alt+Left"),
        [this](const CommandContext &) { return m_navigation->canGoBack()
            ? CommandAvailability::Available : CommandAvailability::NeedsSelection; },
        [this](const CommandContext &) { m_navigation->goBack(); return CommandResult::accept(); }});
    m_commands->registerCommand(Command{
        QStringLiteral("navigation.forward"), QStringLiteral("Revenir à l'écran suivant"),
        QStringLiteral("Navigation"), {}, QStringLiteral("Alt+Right"),
        [this](const CommandContext &) { return m_navigation->canGoForward()
            ? CommandAvailability::Available : CommandAvailability::NeedsSelection; },
        [this](const CommandContext &) { m_navigation->goForward(); return CommandResult::accept(); }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.settings"), QStringLiteral("Réglages et mises à jour"),
        QStringLiteral("Navigation"), {}, QString(), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("settings"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("palette.open"), QStringLiteral("Ouvrir la palette de commandes"),
        QStringLiteral("Général"), {QStringLiteral("commandes"), QStringLiteral("recherche")},
        QStringLiteral("Ctrl+K"), alwaysAvailable,
        [this](const CommandContext &) {
            m_shell->setCommandPaletteOpen(true);
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.home"), QStringLiteral("Aller à l'accueil"),
        QStringLiteral("Navigation"), {QStringLiteral("accueil")}, QStringLiteral("Ctrl+1"),
        alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("home"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.projects"), QStringLiteral("Aller aux projets"),
        QStringLiteral("Navigation"), {QStringLiteral("projets"), QStringLiteral("kanban")},
        QStringLiteral("Ctrl+3"), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("projects"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.questions"), QStringLiteral("Répondre aux questions des projets"),
        QStringLiteral("Navigation"), {QStringLiteral("questions"), QStringLiteral("triage"), QStringLiteral("décision")},
        QStringLiteral("Ctrl+4"), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("questions"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.station"), QStringLiteral("Voir l'état du poste Windows"),
        QStringLiteral("Navigation"), {QStringLiteral("poste"), QStringLiteral("enrôlement"), QStringLiteral("inventaire")},
        QStringLiteral("Ctrl+6"), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("station"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.quotas"), QStringLiteral("Voir les quotas relevés"),
        QStringLiteral("Navigation"), {QStringLiteral("quotas"), QStringLiteral("abonnement"), QStringLiteral("limite")},
        QStringLiteral("Ctrl+7"), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("quotas"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.routing"), QStringLiteral("Voir la table de routage"),
        QStringLiteral("Navigation"), {QStringLiteral("routage"), QStringLiteral("modèle"), QStringLiteral("exécutant")},
        QStringLiteral("Ctrl+8"), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("routing"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.chat"), QStringLiteral("Discuter avec Hermes"),
        QStringLiteral("Navigation"), {QStringLiteral("discussion"), QStringLiteral("chat"), QStringLiteral("hermes")},
        QStringLiteral("Ctrl+5"), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("chat"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("chat.new"), QStringLiteral("Nouvelle discussion avec Hermes"),
        QStringLiteral("Discussion"), {QStringLiteral("nouvelle"), QStringLiteral("session")}, QString(),
        [this](const CommandContext &context) {
            if (!context.sessionConnected) {
                return CommandAvailability::NeedsSession;
            }
            return m_discussion->passerellePrete() ? CommandAvailability::Available : CommandAvailability::Offline;
        },
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("chat"));
            m_discussion->nouvelle();
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("projects.new"), QStringLiteral("Lancer un nouveau projet"),
        QStringLiteral("Projets"), {QStringLiteral("nouveau"), QStringLiteral("lancer")}, QString(),
        [](const CommandContext &context) {
            return context.sessionConnected ? CommandAvailability::Available : CommandAvailability::NeedsSession;
        },
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("projects"));
            m_projets->afficherNouveau();
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.diagnostics"), QStringLiteral("Ouvrir les diagnostics"),
        QStringLiteral("Navigation"),
        {QStringLiteral("santé"), QStringLiteral("état"), QStringLiteral("version")},
        QStringLiteral("Ctrl+2"), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("diagnostics"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("connection.probe"), QStringLiteral("Vérifier l'état du serveur"),
        QStringLiteral("Connexion"),
        {QStringLiteral("santé"), QStringLiteral("health"), QStringLiteral("ping")},
        QStringLiteral("Ctrl+R"),
        [this](const CommandContext &) {
            return m_client->isConfigured() ? CommandAvailability::Available
                                            : CommandAvailability::NotConfigured;
        },
        [this](const CommandContext &) {
            m_health->probeNow();
            return CommandResult::accept(QStringLiteral("Vérification du serveur lancée."));
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("session.signIn"), QStringLiteral("Se connecter avec le navigateur"),
        QStringLiteral("Session"), {QStringLiteral("connexion"), QStringLiteral("navigateur")}, QString(),
        [](const CommandContext &context) {
            if (!context.extra.value(QStringLiteral("configured")).toBool()) {
                return CommandAvailability::NotConfigured;
            }
            if (context.sessionConnected || context.extra.value(QStringLiteral("sessionBusy")).toBool()) {
                return CommandAvailability::Unavailable;
            }
            return context.online ? CommandAvailability::Available : CommandAvailability::Offline;
        },
        [this](const CommandContext &) {
            m_session->seConnecter();
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("session.logout"), QStringLiteral("Se déconnecter"),
        QStringLiteral("Session"), {QStringLiteral("quitter"), QStringLiteral("session")}, QString(),
        [](const CommandContext &context) {
            return context.extra.value(QStringLiteral("sessionPresent")).toBool()
                ? CommandAvailability::Available
                : CommandAvailability::NeedsSession;
        },
        [this](const CommandContext &) {
            m_session->seDeconnecter();
            return CommandResult::accept(QStringLiteral("Session fermée sur ce poste."));
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("session.retry"), QStringLiteral("Retenter le renouvellement de la session"),
        QStringLiteral("Session"), {QStringLiteral("rafraîchir"), QStringLiteral("jeton")}, QString(),
        [](const CommandContext &context) {
            return context.extra.value(QStringLiteral("sessionStalled")).toBool()
                ? CommandAvailability::Available
                : CommandAvailability::Unavailable;
        },
        [this](const CommandContext &) {
            m_session->reessayer();
            return CommandResult::accept(QStringLiteral("Nouvel essai de renouvellement lancé."));
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("connection.compatibility"),
        QStringLiteral("Revérifier la compatibilité de Hermes"), QStringLiteral("Connexion"),
        {QStringLiteral("version"), QStringLiteral("contrat"), QStringLiteral("greffon")}, QString(),
        [](const CommandContext &context) {
            return context.sessionConnected ? CommandAvailability::Available
                                            : CommandAvailability::NeedsSession;
        },
        [this](const CommandContext &) {
            m_compatibilite->verifier();
            return CommandResult::accept(QStringLiteral("Vérification de compatibilité lancée."));
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("appearance.toggleTheme"), QStringLiteral("Basculer le thème"),
        QStringLiteral("Apparence"), {QStringLiteral("sombre"), QStringLiteral("clair")},
        QString(), alwaysAvailable,
        [this](const CommandContext &) {
            const QString next = m_appearance->activeTheme() == QLatin1String("dark")
                ? QStringLiteral("light")
                : QStringLiteral("dark");
            m_appearance->setThemePreference(next);
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("appearance.toggleMotion"),
        QStringLiteral("Basculer le profil de mouvement réduit"), QStringLiteral("Apparence"),
        {QStringLiteral("animation"), QStringLiteral("accessibilité")}, QString(),
        alwaysAvailable,
        [this](const CommandContext &) {
            const QString next = m_appearance->activeMotionProfile() == QLatin1String("reduced")
                ? QStringLiteral("standard")
                : QStringLiteral("reduced");
            m_appearance->setMotionPreference(next);
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("diagnostics.copyReport"),
        QStringLiteral("Copier le rapport de diagnostic"), QStringLiteral("Diagnostics"),
        {QStringLiteral("support"), QStringLiteral("ticket")}, QString(), alwaysAvailable,
        [](const CommandContext &) {
            // Le rapport est expurgé par DiagnosticsViewModel::buildReport() ; la copie
            // effective est faite par QML, qui seul dispose du presse-papiers.
            return CommandResult::accept(
                QStringLiteral("Rapport de diagnostic préparé (valeurs sensibles expurgées)."));
        }});
}

} // namespace acp
