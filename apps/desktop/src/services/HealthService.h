// État du lien avec Hermes : `GET /api/health`.
//
// Route PUBLIQUE de Hermes (hermes_cli/web_routers/status.py) : `{ok, version,
// auth_required}`. Elle ne dit rien de la session ni des greffons : c'est un contrôle de
// vivacité, pas de compatibilité.
//
// Le hors ligne est l'état du LIEN, pas un état de tâche. Il vit en permanence dans la
// barre basse, avec l'horodatage du dernier échange réussi, et les données déjà reçues
// restent affichées, datées.

#pragma once

#include "app/QmlEnums.h"

#include <QDateTime>
#include <QObject>
#include <QString>

#include <optional>

class QTimer;

namespace acp {

class ApiClient;

class HealthService : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int linkStatus READ linkStatusValue NOTIFY changed)
    Q_PROPERTY(QString linkStatusLabel READ linkStatusLabel NOTIFY changed)
    Q_PROPERTY(QString detail READ detail NOTIFY changed)
    Q_PROPERTY(QDateTime lastSuccessAt READ lastSuccessAt NOTIFY changed)
    Q_PROPERTY(QString lastSuccessLabel READ lastSuccessLabel NOTIFY changed)
    Q_PROPERTY(QString hermesVersion READ hermesVersion NOTIFY changed)

public:
    explicit HealthService(ApiClient *client, QObject *parent = nullptr);

    [[nodiscard]] LinkStatus::State linkStatus() const { return m_status; }
    [[nodiscard]] int linkStatusValue() const { return static_cast<int>(m_status); }
    [[nodiscard]] QString linkStatusLabel() const;
    [[nodiscard]] const QString &detail() const { return m_detail; }
    [[nodiscard]] const QDateTime &lastSuccessAt() const { return m_lastSuccessAt; }

    /*! « Jamais » tant qu'aucun échange n'a réussi. Jamais « à l'instant » par défaut. */
    [[nodiscard]] QString lastSuccessLabel() const;

    /*! Version annoncée par `/api/health`, ou « Inconnu ». */
    [[nodiscard]] QString hermesVersion() const;

    /*! `auth_required` lu au dernier contrôle réussi ; absent tant qu'il n'a pas été lu. */
    [[nodiscard]] std::optional<bool> authRequired() const { return m_authRequired; }

    /*! Lance un contrôle immédiat. */
    Q_INVOKABLE void probeNow();

    /*! Démarre ou arrête le contrôle périodique. */
    void setPeriodicProbeEnabled(bool enabled);

signals:
    void changed();

private:
    void setStatus(LinkStatus::State status, const QString &detail);

    ApiClient *m_client = nullptr;
    QTimer *m_timer = nullptr;
    LinkStatus::State m_status = LinkStatus::Unknown;
    QString m_detail;
    QString m_hermesVersion;
    std::optional<bool> m_authRequired;
    QDateTime m_lastSuccessAt;
};

} // namespace acp
