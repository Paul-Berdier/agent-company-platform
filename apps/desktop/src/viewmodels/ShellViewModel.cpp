#include "viewmodels/ShellViewModel.h"

#include "api/ApiClient.h"
#include "auth/AuthManager.h"
#include "commands/CommandRegistry.h"
#include "events/EventStreamService.h"
#include "navigation/NavigationModel.h"
#include "services/CompatibilityService.h"
#include "services/HealthService.h"
#include "storage/SettingsStore.h"

#include <QStringList>
#include <QUrl>

namespace acp {

ShellViewModel::ShellViewModel(ApiClient *client, AuthManager *auth, HealthService *health,
                              CompatibilityService *compatibility, EventStreamService *streams,
                              NavigationModel *navigation, CommandRegistry *commands,
                              SettingsStore *settings, QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_auth(auth)
    , m_health(health)
    , m_compatibility(compatibility)
    , m_streams(streams)
    , m_navigation(navigation)
    , m_commands(commands)
    , m_settings(settings)
{
    connect(m_client, &ApiClient::baseUrlChanged, this, &ShellViewModel::shellStateChanged);
    connect(m_auth, &AuthManager::stateChanged, this, [this] {
        refreshCommandContext();
        emit shellStateChanged();
    });
    connect(m_auth, &AuthManager::userChanged, this, [this] {
        refreshCommandContext();
        emit shellStateChanged();
    });
    connect(m_auth, &AuthManager::sessionLost, this, [this](const QString &reason) {
        // Une session perdue ferme TOUS les flux : un flux laissé ouvert reste compté par
        // le serveur jusqu'à 900 s, et il répondrait de toute façon 401.
        m_streams->closeAll();
        notify(reason);
    });
    connect(m_health, &HealthService::changed, this, [this] {
        refreshCommandContext();
        emit shellStateChanged();
    });
    connect(m_compatibility, &CompatibilityService::stateChanged, this, [this] {
        m_streams->setLimits(m_compatibility->streamLimits());
        refreshCommandContext();
        emit shellStateChanged();
    });
    connect(m_streams, &EventStreamService::subscriptionsChanged, this,
            &ShellViewModel::shellStateChanged);
    connect(m_streams, &EventStreamService::subscriptionRefused, this, &ShellViewModel::notify);
    connect(m_navigation, &NavigationModel::currentRouteChanged, this, [this] {
        refreshCommandContext();
        emit shellStateChanged();
    });
    connect(m_navigation, &NavigationModel::navigationRefused, this,
            [this](const QString &, const QString &detail) { notify(detail); });
    connect(m_commands, &CommandRegistry::commandExecuted, this,
            [this](const QString &, bool, const QString &message) {
                if (!message.isEmpty()) {
                    notify(message);
                }
            });

    m_inspectorVisible = false;
    refreshCommandContext();
}

bool ShellViewModel::isFirstRun() const
{
    return !m_client->isConfigured();
}

bool ShellViewModel::connectionRequired(bool serverConfigured, SessionStatus::State session)
{
    if (!serverConfigured) {
        return true;
    }
    return session != SessionStatus::Connected && session != SessionStatus::Offline;
}

bool ShellViewModel::isConnectionRequired() const
{
    return connectionRequired(m_client->isConfigured(), m_auth->state());
}

bool ShellViewModel::allowsInsecureLoopback() const
{
    return m_client->allowsInsecureLoopback();
}

bool ShellViewModel::isAuthenticated() const
{
    return m_auth->state() == SessionStatus::Connected;
}

QString ShellViewModel::serverUrl() const
{
    return m_client->baseUrl().toString();
}

QString ShellViewModel::serverUrlLabel() const
{
    const QString url = serverUrl();
    // Aucun domaine n'est décidé par le projet : sans saisie, c'est « Non configuré ».
    return url.isEmpty() ? QStringLiteral("Non configuré") : url;
}

QString ShellViewModel::workspaceLabel() const
{
    if (!m_client->isConfigured()) {
        return QStringLiteral("Non configuré");
    }
    if (!isAuthenticated()) {
        return QStringLiteral("Non connecté");
    }
    // Aucune route consommée par cette fondation ne fournit de nom d'espace de travail :
    // on affiche l'identité de l'opérateur, qui est un fait, et rien d'inventé.
    const QString name = m_auth->userDisplayName();
    return name.isEmpty() ? QStringLiteral("Inconnu") : name;
}

QString ShellViewModel::statusSummary() const
{
    QStringList parts;
    parts << QStringLiteral("Lien : %1").arg(m_health->linkStatusLabel());
    parts << QStringLiteral("Session : %1").arg(m_auth->stateLabel());
    parts << QStringLiteral("Flux : %1/%2")
                 .arg(m_streams->activeCount())
                 .arg(m_streams->maxConnections());
    parts << QStringLiteral("Compatibilité : %1").arg(m_compatibility->stateLabel());
    parts << QStringLiteral("Dernier échange : %1").arg(m_health->lastSuccessLabel());
    return parts.join(QStringLiteral("  ·  "));
}

void ShellViewModel::setCommandPaletteOpen(bool open)
{
    if (m_commandPaletteOpen == open) {
        return;
    }
    m_commandPaletteOpen = open;
    if (open) {
        // Le contexte est réévalué à l'ouverture : une commande disponible il y a dix
        // minutes ne l'est peut-être plus.
        refreshCommandContext();
        m_commands->setFilter(QString());
    }
    emit commandPaletteOpenChanged();
}

void ShellViewModel::setInspectorVisible(bool visible)
{
    if (m_inspectorVisible == visible) {
        return;
    }
    m_inspectorVisible = visible;
    emit inspectorVisibleChanged();
}

bool ShellViewModel::isSidebarCollapsed() const
{
    return m_settings->sidebarCollapsed();
}

void ShellViewModel::setSidebarCollapsed(bool collapsed)
{
    if (m_settings->sidebarCollapsed() == collapsed) {
        return;
    }
    m_settings->setSidebarCollapsed(collapsed);
    emit sidebarCollapsedChanged();
}

QString ShellViewModel::applyServerUrl(const QString &url, bool allowInsecureLoopback)
{
    m_client->setAllowInsecureLoopback(allowInsecureLoopback);
    const ApiError error = m_client->setBaseUrl(QUrl::fromUserInput(url));
    if (error.isError()) {
        notify(error.message());
        return error.message();
    }
    m_settings->setAllowInsecureLoopback(allowInsecureLoopback);
    m_settings->setServerUrl(m_client->baseUrl());
    m_settings->flush();

    // L'ordre compte : on constate d'abord que le serveur répond, ensuite seulement on
    // interroge la compatibilité. Une vérification lancée contre un serveur muet ne dirait
    // rien d'utile.
    m_health->probeNow();
    m_compatibility->check();
    m_auth->refreshBootstrapStatus();
    emit shellStateChanged();
    return {};
}

void ShellViewModel::notify(const QString &message)
{
    if (message.isEmpty() || message == m_lastNotice) {
        return;
    }
    m_lastNotice = message;
    emit noticeChanged();
}

void ShellViewModel::refreshCommandContext()
{
    CommandContext context;
    context.sessionConnected = isAuthenticated();
    context.online = m_health->linkStatus() == LinkStatus::Online
        || m_health->linkStatus() == LinkStatus::Degraded;
    context.platformRole = m_auth->platformRole();
    context.currentRoute = m_navigation->currentRoute();
    m_commands->setContext(context);
}

} // namespace acp
