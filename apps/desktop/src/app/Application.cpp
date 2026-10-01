#include "app/Application.h"

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "app/BuildConfig.h"
#include "app/QmlEnums.h"
#include "auth/SessionHermes.h"
#include "commands/CommandRegistry.h"
#include "models/JsonListModel.h"
#include "navigation/NavigationModel.h"
#include "services/HealthService.h"
#include "services/UpdateService.h"
#include "storage/CredentialVault.h"
#include "storage/SettingsStore.h"
#include "system/SystemAppearance.h"
#include "viewmodels/DiagnosticsViewModel.h"
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
    });
    m_diagnostics = new DiagnosticsViewModel(m_client, m_health, m_settings, m_appearance,
                                             m_vault.get(), version(), buildInfo(), this);
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
