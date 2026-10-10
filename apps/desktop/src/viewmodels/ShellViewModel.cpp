#include "viewmodels/ShellViewModel.h"

#include "api/ApiClient.h"
#include "auth/SessionHermes.h"
#include "commands/CommandRegistry.h"
#include "navigation/NavigationModel.h"
#include "services/HealthService.h"
#include "storage/SettingsStore.h"

#include <QStringList>
#include <QUrl>

namespace acp {

ShellViewModel::ShellViewModel(ApiClient *client, SessionHermes *session, HealthService *health,
                               NavigationModel *navigation, CommandRegistry *commands,
                               SettingsStore *settings, QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_session(session)
    , m_health(health)
    , m_navigation(navigation)
    , m_commands(commands)
    , m_settings(settings)
{
    connect(m_client, &ApiClient::baseUrlChanged, this, [this] {
        m_navigation->resetHistory();
        setInspectorVisible(false);
        setCommandPaletteOpen(false);
        refreshCommandContext();
        emit shellStateChanged();
    });
    connect(m_health, &HealthService::changed, this, [this] {
        refreshCommandContext();
        emit shellStateChanged();
    });
    connect(m_session, &SessionHermes::etatChange, this, [this] {
        refreshCommandContext();
        emit shellStateChanged();
    });
    connect(m_session, &SessionHermes::sessionPerdue, this, [this](const QString &raison) {
        // Aucune donnée de l'ancienne session ne reste à l'écran.
        m_navigation->resetHistory();
        setInspectorVisible(false);
        notify(raison);
    });
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

    refreshCommandContext();
}

SessionStatus::State ShellViewModel::sessionState() const
{
    return m_session->etat();
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
    // Une session établie reste affichée pendant une rotation ou une coupure : les
    // dernières données reçues restent visibles, datées, et la barre d'état dit pourquoi.
    switch (session) {
    case SessionStatus::Connectee:
    case SessionStatus::Rafraichissement:
    case SessionStatus::FournisseurInjoignable:
    case SessionStatus::HorsLigne:
        return false;
    case SessionStatus::NonConfiguree:
    case SessionStatus::Deconnectee:
    case SessionStatus::AttenteNavigateur:
    case SessionStatus::Echange:
    case SessionStatus::Expiree:
    case SessionStatus::Refusee:
        return true;
    }
    return true;
}

bool ShellViewModel::isConnectionRequired() const
{
    return connectionRequired(m_client->isConfigured(), sessionState());
}

bool ShellViewModel::allowsInsecureLoopback() const
{
    return m_client->allowsInsecureLoopback();
}

bool ShellViewModel::isAuthenticated() const
{
    return sessionState() == SessionStatus::Connectee;
}

QString ShellViewModel::serverUrl() const
{
    return m_client->baseUrl().toString();
}

QString ShellViewModel::serverUrlLabel() const
{
    const QString url = serverUrl();
    return url.isEmpty() ? QStringLiteral("Non configuré") : url;
}

QString ShellViewModel::statusSummary() const
{
    QStringList parts;
    parts << QStringLiteral("Lien : %1").arg(m_health->linkStatusLabel());
    parts << QStringLiteral("Session : %1").arg(m_session->libelleEtat());
    parts << QStringLiteral("Hermes : %1").arg(m_health->hermesVersion());
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

int ShellViewModel::sidebarWidth() const { return m_settings->sidebarWidth(); }

void ShellViewModel::setSidebarWidth(int width)
{
    if (sidebarWidth() == width) return;
    m_settings->setSidebarWidth(width);
    emit panelWidthsChanged();
}

int ShellViewModel::inspectorWidth() const { return m_settings->inspectorWidth(); }

void ShellViewModel::setInspectorWidth(int width)
{
    if (inspectorWidth() == width) return;
    m_settings->setInspectorWidth(width);
    emit panelWidthsChanged();
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

    m_health->probeNow();
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
    context.currentRoute = m_navigation->currentRoute();
    const SessionStatus::State etat = m_session->etat();
    context.extra.insert(QStringLiteral("configured"), m_client->isConfigured());
    context.extra.insert(QStringLiteral("sessionBusy"), m_session->estOccupee());
    context.extra.insert(QStringLiteral("sessionPresent"), !connectionRequired(m_client->isConfigured(), etat));
    context.extra.insert(QStringLiteral("sessionStalled"),
                         etat == SessionStatus::FournisseurInjoignable || etat == SessionStatus::HorsLigne);
    m_commands->setContext(context);
}

} // namespace acp
