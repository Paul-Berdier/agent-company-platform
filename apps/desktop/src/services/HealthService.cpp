#include "services/HealthService.h"

#include "api/ApiClient.h"

#include <QJsonObject>
#include <QJsonValue>
#include <QTimer>

namespace acp {

HealthService::HealthService(ApiClient *client, QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_timer(new QTimer(this))
{
    // Un contrôle toutes les 30 secondes : la barre d'état n'est pas un moniteur, et l'état
    // réel du lien est surtout révélé par le trafic applicatif lui-même.
    m_timer->setInterval(30000);
    connect(m_timer, &QTimer::timeout, this, &HealthService::probeNow);
    connect(m_client, &ApiClient::baseUrlChanged, this, [this] {
        m_hermesVersion.clear();
        m_authRequired.reset();
        m_lastSuccessAt = QDateTime();
        setStatus(LinkStatus::Unknown, QString());
        emit changed();
    });
}

QString HealthService::linkStatusLabel() const
{
    switch (m_status) {
    case LinkStatus::Unknown:
        return QStringLiteral("Inconnu");
    case LinkStatus::Probing:
        return QStringLiteral("Vérification");
    case LinkStatus::Online:
        return QStringLiteral("En ligne");
    case LinkStatus::Degraded:
        return QStringLiteral("Dégradé");
    case LinkStatus::Offline:
        return QStringLiteral("Hors ligne");
    }
    return QStringLiteral("Inconnu");
}

QString HealthService::lastSuccessLabel() const
{
    if (!m_lastSuccessAt.isValid()) {
        // Aucun échange réussi : on le dit. Pas de « à l'instant » par optimisme.
        return QStringLiteral("Jamais");
    }
    return m_lastSuccessAt.toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm:ss"));
}

QString HealthService::hermesVersion() const
{
    return m_hermesVersion.isEmpty() ? QStringLiteral("Inconnu") : m_hermesVersion;
}

void HealthService::setStatus(LinkStatus::State status, const QString &detail)
{
    if (m_status == status && m_detail == detail) {
        return;
    }
    m_status = status;
    m_detail = detail;
    emit changed();
}

void HealthService::setPeriodicProbeEnabled(bool enabled)
{
    if (enabled) {
        if (!m_timer->isActive()) {
            m_timer->start();
        }
    } else {
        m_timer->stop();
    }
}

void HealthService::probeNow()
{
    if (!m_client->isConfigured()) {
        setStatus(LinkStatus::Unknown,
                  QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }
    setStatus(LinkStatus::Probing, QString());

    ApiRequest request;
    request.method = QByteArrayLiteral("GET");
    request.path = QStringLiteral("/api/health");
    request.publicEndpoint = true;
    // Un contrôle de vivacité doit répondre vite ou pas du tout.
    request.timeout = std::chrono::milliseconds(8000);

    ApiCall *call = m_client->send(request);
    connect(call, &ApiCall::succeeded, this, [this](const ApiResponse &response) {
        const QJsonObject payload = response.json.object();
        const QJsonValue ok = payload.value(QStringLiteral("ok"));
        const QJsonValue version = payload.value(QStringLiteral("version"));
        const QJsonValue authRequired = payload.value(QStringLiteral("auth_required"));
        m_hermesVersion = version.isString() ? version.toString() : QString();
        if (authRequired.isBool()) {
            m_authRequired = authRequired.toBool();
        } else {
            m_authRequired.reset();
        }
        if (!ok.isBool() || !ok.toBool()) {
            setStatus(LinkStatus::Degraded,
                      QStringLiteral("/api/health n'a pas répondu « ok »."));
            emit changed();
            return;
        }
        m_lastSuccessAt = QDateTime::currentDateTimeUtc();
        setStatus(LinkStatus::Online, QString());
        emit changed();
    });
    connect(call, &ApiCall::failed, this, [this](const ApiError &error) {
        if (error.httpStatus() > 0) {
            // Le serveur répond, mais pas comme Hermes l'attend : le lien existe.
            setStatus(LinkStatus::Degraded,
                      QStringLiteral("Le serveur répond, mais /api/health a échoué : %1")
                          .arg(error.message()));
            return;
        }
        setStatus(LinkStatus::Offline, error.message());
    });
}

} // namespace acp
