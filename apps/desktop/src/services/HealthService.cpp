#include "services/HealthService.h"

#include "api/ApiClient.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QTimer>

namespace acp {

// --- ReadinessModel -----------------------------------------------------------

QList<ReadinessModel::Check> ReadinessModel::parseChecks(const QJsonObject &payload)
{
    QList<Check> checks;
    const QJsonObject entries = payload.value(QStringLiteral("checks")).toObject();
    for (auto iterator = entries.constBegin(); iterator != entries.constEnd(); ++iterator) {
        const QJsonObject entry = iterator.value().toObject();
        const QJsonValue ok = entry.value(QStringLiteral("ok"));
        Check check;
        check.name = iterator.key();
        check.healthy = ok.isBool() && ok.toBool();
        check.status = !ok.isBool()
            ? QStringLiteral("Inconnu")
            : (ok.toBool() ? QStringLiteral("Sain") : QStringLiteral("En échec"));
        // La raison est celle du serveur, en français, affichée telle quelle.
        check.detail = entry.value(QStringLiteral("reason")).toString();
        checks.append(check);
    }
    return checks;
}

int ReadinessModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : static_cast<int>(m_checks.size());
}

QVariant ReadinessModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_checks.size()) {
        return {};
    }
    const Check &check = m_checks.at(index.row());
    switch (role) {
    case NameRole:
        return check.name;
    case StatusRole:
        return check.status;
    case DetailRole:
        return check.detail;
    case HealthyRole:
        return check.healthy;
    default:
        return {};
    }
}

QHash<int, QByteArray> ReadinessModel::roleNames() const
{
    return {
        {NameRole, QByteArrayLiteral("name")},
        {StatusRole, QByteArrayLiteral("status")},
        {DetailRole, QByteArrayLiteral("detail")},
        {HealthyRole, QByteArrayLiteral("healthy")},
    };
}

void ReadinessModel::setChecks(const QList<Check> &checks)
{
    beginResetModel();
    m_checks = checks;
    endResetModel();
}

void ReadinessModel::clear()
{
    beginResetModel();
    m_checks.clear();
    endResetModel();
}

// --- HealthService ------------------------------------------------------------

HealthService::HealthService(ApiClient *client, QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_readiness(new ReadinessModel(this))
    , m_timer(new QTimer(this))
{
    // Un contrôle par minute suffit : la barre d'état n'est pas un moniteur, et l'état
    // réel du lien est surtout révélé par le trafic applicatif lui-même.
    m_timer->setInterval(60000);
    connect(m_timer, &QTimer::timeout, this, &HealthService::probeNow);
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
        m_readiness->clear();
        setStatus(LinkStatus::Unknown,
                  QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }
    setStatus(LinkStatus::Probing, QString());

    ApiRequest request;
    request.method = QByteArrayLiteral("GET");
    request.path = QStringLiteral("/health");
    request.publicEndpoint = true;
    // Un contrôle de vivacité doit répondre vite ou pas du tout.
    request.timeout = std::chrono::milliseconds(8000);

    ApiCall *call = m_client->send(request);
    connect(call, &ApiCall::succeeded, this, [this](const ApiResponse &response) {
        const QString status = response.json.object().value(QStringLiteral("status")).toString();
        if (status != QLatin1String("ok")) {
            setStatus(LinkStatus::Degraded,
                      QStringLiteral("/health a répondu « %1 ».")
                          .arg(status.isEmpty() ? QStringLiteral("sans statut") : status));
            return;
        }
        m_lastSuccessAt = QDateTime::currentDateTimeUtc();
        // /health ne porte aucune version et ne dit rien des dépendances : il faut /ready.
        probeReady();
    });
    connect(call, &ApiCall::failed, this, [this](const ApiError &error) {
        m_readiness->clear();
        setStatus(LinkStatus::Offline, error.message());
    });
}

void HealthService::probeReady()
{
    ApiRequest request;
    request.method = QByteArrayLiteral("GET");
    request.path = QStringLiteral("/ready");
    request.publicEndpoint = true;
    request.timeout = std::chrono::milliseconds(15000);

    ApiCall *call = m_client->send(request);

    auto applyPayload = [this](const QJsonObject &payload, bool ready) {
        const QList<ReadinessModel::Check> checks = ReadinessModel::parseChecks(payload);
        m_readiness->setChecks(checks);
        if (checks.isEmpty()) {
            // /ready a répondu sans détailler : on ne fabrique pas cinq lignes vertes.
            setStatus(ready ? LinkStatus::Online : LinkStatus::Degraded,
                      QStringLiteral("/ready n'a détaillé aucun contrôle."));
            return;
        }
        setStatus(ready ? LinkStatus::Online : LinkStatus::Degraded, QString());
    };

    connect(call, &ApiCall::succeeded, this, [this, applyPayload](const ApiResponse &response) {
        m_lastSuccessAt = QDateTime::currentDateTimeUtc();
        applyPayload(response.json.object(), true);
    });
    connect(call, &ApiCall::failed, this, [this, applyPayload](const ApiError &error) {
        if (error.kind() == ApiFailure::ServiceUnavailable) {
            // 503 attendu et documenté : le service répond, mais un contrôle a échoué.
            // C'est « Dégradé », pas « Hors ligne ». Le corps du 503 détaille les
            // contrôles : il est lu, parce que c'est la seule source honnête de l'écran.
            const QJsonDocument document = QJsonDocument::fromJson(error.body());
            if (document.isObject()) {
                applyPayload(document.object(), false);
            } else {
                m_readiness->clear();
            }
            setStatus(LinkStatus::Degraded, error.message());
            return;
        }
        m_readiness->clear();
        setStatus(LinkStatus::Offline, error.message());
    });
}

} // namespace acp
