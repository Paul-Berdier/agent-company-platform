// État du lien avec le serveur : /health et /ready.
//
// Ce que l'audit garantit sur ces deux routes :
//   - `GET /health` : liveness pure, `{"status":"ok","service":"api"}`, PUBLIQUE, et
//     elle NE PORTE AUCUNE VERSION. On ne peut donc rien en déduire sur la compatibilité ;
//   - `GET /ready`  : readiness — base, migrations, stockage livrables, stockage skills,
//     outbox — 200 ou 503, raisons en français, ni chemin ni URL ni secret. C'est la
//     seule source honnête de l'écran des cinq contrôles.
//
// Le hors ligne est l'état du LIEN, pas un état de tâche. Il vit en permanence dans la
// barre basse, avec l'horodatage du dernier échange réussi, et les données déjà reçues
// restent affichées, datées.

#pragma once

#include "app/QmlEnums.h"

#include <QAbstractListModel>
#include <QDateTime>
#include <QList>
#include <QObject>
#include <QString>

class QTimer;

namespace acp {

class ApiClient;

/*! Les contrôles rendus par `/ready`, tels que le serveur les nomme. */
class ReadinessModel : public QAbstractListModel
{
    Q_OBJECT

public:
    enum Roles {
        NameRole = Qt::UserRole + 1,
        StatusRole,   //!< Verdict en français : « Sain », « En échec » ou « Inconnu ».
        DetailRole,   //!< Raison française donnée par le serveur, telle quelle.
        HealthyRole,
    };
    Q_ENUM(Roles)

    struct Check
    {
        QString name;
        QString status;
        QString detail;
        bool healthy = false;
    };

    using QAbstractListModel::QAbstractListModel;

    [[nodiscard]] int rowCount(const QModelIndex &parent = {}) const override;
    [[nodiscard]] QVariant data(const QModelIndex &index, int role) const override;
    [[nodiscard]] QHash<int, QByteArray> roleNames() const override;

    void setChecks(const QList<Check> &checks);
    void clear();

    /*!
        Lit les contrôles d'un corps `/ready`, en 200 comme en 503.

        Forme servie par l'API (`acp_api/readiness.py`) : `checks.<nom>` est un objet
        portant `ok` (booléen) et `reason` (français), plus des champs propres au contrôle.
        Un contrôle sans `ok` booléen reste « Inconnu » et n'est jamais compté sain.
    */
    [[nodiscard]] static QList<Check> parseChecks(const QJsonObject &payload);

private:
    QList<Check> m_checks;
};

class HealthService : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int linkStatus READ linkStatusValue NOTIFY changed)
    Q_PROPERTY(QString linkStatusLabel READ linkStatusLabel NOTIFY changed)
    Q_PROPERTY(QString detail READ detail NOTIFY changed)
    Q_PROPERTY(QDateTime lastSuccessAt READ lastSuccessAt NOTIFY changed)
    Q_PROPERTY(QString lastSuccessLabel READ lastSuccessLabel NOTIFY changed)
    Q_PROPERTY(QObject *readinessChecks READ readinessChecksObject CONSTANT)

public:
    explicit HealthService(ApiClient *client, QObject *parent = nullptr);

    [[nodiscard]] LinkStatus::State linkStatus() const { return m_status; }
    [[nodiscard]] int linkStatusValue() const { return static_cast<int>(m_status); }
    [[nodiscard]] QString linkStatusLabel() const;
    [[nodiscard]] const QString &detail() const { return m_detail; }
    [[nodiscard]] const QDateTime &lastSuccessAt() const { return m_lastSuccessAt; }

    /*! « Jamais » tant qu'aucun échange n'a réussi. Jamais « à l'instant » par défaut. */
    [[nodiscard]] QString lastSuccessLabel() const;

    [[nodiscard]] ReadinessModel *readinessChecks() { return m_readiness; }
    [[nodiscard]] QObject *readinessChecksObject() { return m_readiness; }

    /*! Lance un contrôle immédiat. */
    Q_INVOKABLE void probeNow();

    /*! Démarre ou arrête le contrôle périodique. */
    void setPeriodicProbeEnabled(bool enabled);

signals:
    void changed();

private:
    void setStatus(LinkStatus::State status, const QString &detail);
    void probeReady();

    ApiClient *m_client = nullptr;
    ReadinessModel *m_readiness = nullptr;
    QTimer *m_timer = nullptr;
    LinkStatus::State m_status = LinkStatus::Unknown;
    QString m_detail;
    QDateTime m_lastSuccessAt;
};

} // namespace acp
