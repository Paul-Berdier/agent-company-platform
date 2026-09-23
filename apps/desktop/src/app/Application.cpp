#include "app/Application.h"

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "app/BuildConfig.h"
#include "app/QmlEnums.h"
#include "auth/AuthManager.h"
#include "commands/CommandRegistry.h"
#include "events/EventStreamService.h"
#include "navigation/NavigationModel.h"
#include "services/CompatibilityService.h"
#include "services/HealthService.h"
#include "storage/CredentialVault.h"
#include "storage/SettingsStore.h"
#include "system/SystemAppearance.h"
#include "viewmodels/DiagnosticsViewModel.h"
#include "viewmodels/ShellViewModel.h"
#include "viewmodels/WorkspaceViewModel.h"
#include "viewmodels/ConversationsViewModel.h"
#include "viewmodels/MissionsViewModel.h"
#include "viewmodels/ArtifactsViewModel.h"
#include "services/ArtifactDownload.h"
#include "viewmodels/PlatformViewModel.h"
#include "viewmodels/OperationsViewModel.h"
#include "services/SessionPersistence.h"
#include "services/UpdateService.h"

#include <QCoreApplication>
#include <QLibraryInfo>
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
    , m_auth(new AuthManager(m_client, this))
    , m_health(new HealthService(m_client, this))
    , m_compatibility(new CompatibilityService(m_client, version(), this))
    , m_streams(new EventStreamService(m_client, this))
    , m_navigation(new NavigationModel(this))
    , m_commands(new CommandRegistry(this))
    , m_appearance(new SystemAppearance(m_settings, this))
    , m_vault(makeCredentialVault(QStringLiteral("AgentCompanyPlatform")))
{
    m_client->setUserAgent(userAgent());

    m_shell = new ShellViewModel(m_client, m_auth, m_health, m_compatibility, m_streams,
                                 m_navigation, m_commands, m_settings, this);
    m_diagnostics =
        new DiagnosticsViewModel(m_client, m_auth, m_health, m_compatibility, m_streams,
                                 m_settings, m_appearance, m_vault.get(), version(), buildInfo(),
                                 this);

    m_workspace = new WorkspaceViewModel(m_client, m_auth, this);
    m_conversations = new ConversationsViewModel(m_client, m_auth, this);
    m_missions = new MissionsViewModel(m_client, m_auth, m_streams, this);
    m_artifacts = new ArtifactsViewModel(m_client, m_auth, this);
    m_platform = new PlatformViewModel(m_client, m_auth, this);
    m_operations = new OperationsViewModel(m_client, m_auth, this);
    m_sessionStorage = new SessionPersistence(m_client, m_auth, m_vault.get(), m_settings, this);
    m_updates = new UpdateService(version(), this);
    connect(m_workspace, &WorkspaceViewModel::projectChanged, this, [this] {
        const auto id = m_workspace->projectId();
        m_conversations->setProjectId(id);
        m_missions->setProjectId(id);
        m_artifacts->setProjectId(id);
        m_platform->setProjectId(id);
        m_operations->setProjectId(id);
    });
    registerBuiltinCommands();
}

Application::~Application()
{
    shutdown();
    // Les vues dépendent du transport et des flux créés avant elles. QObject détruit
    // normalement ses enfants dans l'ordre de création : les vues doivent ici partir
    // en premier, pendant que leurs services et le coffre sont encore disponibles.
    while (!children().isEmpty()) delete children().last();
}

void Application::registerQmlTypes()
{
    qRegisterMetaType<acp::ApiError>("acp::ApiError");
    qmlRegisterUncreatableType<JsonListModel>(kQmlUri, 1, 0, "JsonListModel",
        QStringLiteral("Le modèle est fourni par la station."));
    qmlRegisterUncreatableType<ArtifactDownload>(kQmlUri, 1, 0, "ArtifactDownload",
        QStringLiteral("Le téléchargement est fourni par la station."));

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
    qmlRegisterUncreatableType<StreamStatus>(kQmlUri, 1, 0, "StreamStatus",
                                             QStringLiteral("StreamStatus n'expose que des "
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
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Session", m_auth);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Health", m_health);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Compatibility", m_compatibility);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Navigation", m_navigation);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Commands", m_commands);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Appearance", m_appearance);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Diagnostics", m_diagnostics);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Workspace", m_workspace);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Conversations", m_conversations);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Missions", m_missions);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Artifacts", m_artifacts);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Platform", m_platform);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "Operations", m_operations);
    qmlRegisterSingletonInstance(kQmlUri, 1, 0, "SessionStorage", m_sessionStorage);
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
        m_compatibility->check();
        m_auth->refreshBootstrapStatus();
        // La reprise de session s'appuie sur le cookie ; sans cookie détenu elle échoue
        // immédiatement, sans appel réseau.
        m_sessionStorage->restore();
        m_auth->resumeSession();
    }
}

void Application::shutdown()
{
    // Ordre voulu : fermer les flux AVANT de perdre la session, pour que le serveur
    // libère ses jetons de connexion tout de suite plutôt qu'au bout de 900 secondes.
    m_streams->closeAll();
    m_health->setPeriodicProbeEnabled(false);
    m_settings->flush();
}

void Application::registerBuiltinCommands()
{
    const auto alwaysAvailable = [](const CommandContext &) {
        return CommandAvailability::Available;
    };
    const auto needsSession = [](const CommandContext &context) {
        return context.sessionConnected ? CommandAvailability::Available
                                        : CommandAvailability::NeedsSession;
    };

    const QList<QPair<QString, QString>> workspaceRoutes = {
        {QStringLiteral("projects"), QStringLiteral("Projets")},
        {QStringLiteral("conversations"), QStringLiteral("Conversations")},
        {QStringLiteral("missions"), QStringLiteral("Missions et runs")},
        {QStringLiteral("library"), QStringLiteral("Livrables")},
        {QStringLiteral("studio"), QStringLiteral("Studio en direct")},
        {QStringLiteral("platform"), QStringLiteral("Agents et workers")},
        {QStringLiteral("extensions"), QStringLiteral("Extensions MCP et skills")},
        {QStringLiteral("approvals"), QStringLiteral("Opérations")},
    };
    for (const auto &route : workspaceRoutes) {
        m_commands->registerCommand(Command{
            QStringLiteral("navigation.") + route.first, route.second,
            QStringLiteral("Navigation"), {route.second}, QString(), needsSession,
            [this, destination = route.first](const CommandContext &) {
                m_navigation->setCurrentRoute(destination);
                return CommandResult::accept();
            }});
    }

    m_commands->registerCommand(Command{
        QStringLiteral("navigation.settings"), QStringLiteral("Réglages et mises à jour"),
        QStringLiteral("Navigation"), {}, QString(), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("settings"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("session.resume"), QStringLiteral("Reprendre la session"),
        QStringLiteral("Session"), {}, QString(),
        [this](const CommandContext &) {
            return m_client->isConfigured() && !m_auth->isBusy()
                ? CommandAvailability::Available : CommandAvailability::NotConfigured;
        }, [this](const CommandContext &) {
            m_auth->resumeSession();
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
        {QStringLiteral("santé"), QStringLiteral("état"), QStringLiteral("readiness")},
        QStringLiteral("Ctrl+2"), alwaysAvailable,
        [this](const CommandContext &) {
            m_navigation->setCurrentRoute(QStringLiteral("diagnostics"));
            return CommandResult::accept();
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("connection.probe"), QStringLiteral("Vérifier l'état du serveur"),
        QStringLiteral("Connexion"),
        {QStringLiteral("health"), QStringLiteral("ready"), QStringLiteral("ping")},
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
        QStringLiteral("connection.compatibility"),
        QStringLiteral("Revérifier la compatibilité du serveur"), QStringLiteral("Connexion"),
        {QStringLiteral("version"), QStringLiteral("contrat")}, QString(),
        [this](const CommandContext &) {
            return m_client->isConfigured() ? CommandAvailability::Available
                                            : CommandAvailability::NotConfigured;
        },
        [this](const CommandContext &) {
            m_compatibility->check();
            return CommandResult::accept(QStringLiteral("Vérification de compatibilité lancée."));
        }});

    m_commands->registerCommand(Command{
        QStringLiteral("session.logout"), QStringLiteral("Se déconnecter"),
        QStringLiteral("Session"), {QStringLiteral("quitter"), QStringLiteral("session")},
        QString(), alwaysAvailable,
        [this](const CommandContext &) {
            m_streams->closeAll();
            m_auth->logOut();
            return CommandResult::accept();
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
        [this](const CommandContext &) {
            // Le rapport est expurgé par DiagnosticsViewModel::buildReport() ; la copie
            // effective est faite par QML, qui seul dispose du presse-papiers.
            return CommandResult::accept(
                QStringLiteral("Rapport de diagnostic préparé (valeurs sensibles expurgées)."));
        }});
}

} // namespace acp
