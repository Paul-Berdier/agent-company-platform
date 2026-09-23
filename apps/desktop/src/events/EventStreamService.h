// Client SSE de la station : abonnements, reprise par curseur, repli par interrogation.
//
// La séquence imposée par l'audit (section 4.4) est implémentée telle quelle :
//
//   1. RATTRAPAGE  — lire le journal durable de la portée jusqu'à `has_more == false`,
//                    en retenant `next_cursor`.
//   2. OUVERTURE   — ouvrir le flux avec `Last-Event-ID` (prioritaire) ou `?after_seq=`.
//   3. CONSOMMATION— traiter `acp.event` ; sur `acp.stream.rotate`, reconnecter au
//                    curseur porté par la trame ; sur `acp.stream.closed`, S'ARRÊTER et
//                    le dire honnêtement — une fermeture de flux n'est PAS un arrêt de
//                    mission.
//   4. COUPURE     — ne JAMAIS rejouer une mutation. La reprise se fait par curseur de
//                    lecture. Ce service n'émet d'ailleurs aucune méthode non sûre : il
//                    ne peut pas relancer une mission, structurellement.
//   5. MULTIPLEXAGE— une connexion par portée réellement affichée, réutilisée par tous
//                    les panneaux. Le serveur ferme au-delà de 4 flux par utilisateur
//                    (429 + Retry-After: 5) ; ce compteur est local au processus serveur
//                    et ne tient que par `numReplicas: 1`.
//
// Ce que le service NE fait pas, volontairement : il n'interprète aucun payload métier.
// Il rend des `StreamEvent` bruts ; leur projection en modèles appartient aux couches
// supérieures.

#pragma once

#include "api/ApiError.h"
#include "app/QmlEnums.h"
#include "events/Backoff.h"
#include "events/SseParser.h"
#include "events/StreamScope.h"

#include <QDateTime>
#include <QHash>
#include <QJsonObject>
#include <QObject>
#include <QPointer>
#include <QString>

#include <memory>

class QNetworkReply;
class QTimer;

namespace acp {

class ApiClient;

/*!
    Bornes de flux annoncées par le serveur.

    Valeurs par défaut = valeurs relevées dans `apps/api/src/acp_api/streams.py` à la date
    de l'audit. Elles sont REMPLACÉES dès que le point d'entrée de compatibilité les
    annonce : le client dimensionne son multiplexeur sur la valeur annoncée, pas sur une
    constante figée dans un binaire installé sur un poste.
*/
struct StreamLimits
{
    int maxConnectionsPerUser = 4;
    int keepAliveSeconds = 15;
    int maxStreamSeconds = 900;
    int pollIntervalMilliseconds = 400;
    int pageLimit = 500;
};

/*! Abonnement vivant à une portée. Créé par le service, jamais par un écran. */
class StreamSubscription : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int status READ statusValue NOTIFY statusChanged)
    Q_PROPERTY(QString statusLabel READ statusLabel NOTIFY statusChanged)
    Q_PROPERTY(QString scopeLabel READ scopeLabelText CONSTANT)
    Q_PROPERTY(qint64 cursor READ cursorValue NOTIFY cursorChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY statusChanged)
    Q_PROPERTY(QDateTime lastEventAt READ lastEventAt NOTIFY cursorChanged)
    Q_PROPERTY(bool journalHasGaps READ journalHasGaps NOTIFY cursorChanged)

public:
    StreamSubscription(StreamScope scope, ApiClient *client, StreamLimits limits,
                       QObject *parent = nullptr);
    ~StreamSubscription() override;

    [[nodiscard]] const StreamScope &scope() const { return m_scope; }
    [[nodiscard]] QString key() const { return scopeKey(m_scope); }
    [[nodiscard]] StreamStatus::State status() const { return m_status; }
    [[nodiscard]] int statusValue() const { return static_cast<int>(m_status); }
    [[nodiscard]] QString statusLabel() const;
    [[nodiscard]] QString scopeLabelText() const { return scopeLabel(m_scope); }
    [[nodiscard]] qint64 cursorValue() const { return scopeCursorValue(m_scope); }
    [[nodiscard]] const QString &lastError() const { return m_lastError; }
    [[nodiscard]] const QDateTime &lastEventAt() const { return m_lastEventAt; }

    /*! Vrai si une page de journal a été rendue avec des événements dépourvus de
        `sequence`. L'audit le signale (limite 9) : une base ancienne montre des trous.
        L'interface les présente, elle ne les masque pas. */
    [[nodiscard]] bool journalHasGaps() const { return m_journalHasGaps; }

    /*! Démarre la séquence complète : rattrapage puis flux. */
    void start();

    /*! Ferme proprement. La fermeture propre est une OBLIGATION : le jeton de connexion
        du serveur n'est libéré que par le `finally` de son générateur, et un flux
        abandonné reste compté jusqu'à 900 s. */
    void stop();

signals:
    void statusChanged();
    void cursorChanged();

    /*! Un événement du journal, tel que le serveur l'a rendu, sans réinterprétation. */
    void journalEvent(const QJsonObject &event);

    /*! Le serveur a fermé le flux de son propre chef. `reason` vaut `unauthorized`
        quand la session ou l'appartenance ont été révoquées. */
    void serverClosed(const QString &reason);

    /*! Un refus définitif : l'abonnement ne sera pas repris tout seul. */
    void refused(const acp::ApiError &error);

private:
    void setStatus(StreamStatus::State status, const QString &detail = {});
    void beginCatchUp();
    void requestJournalPage();
    void openStream();
    void handleStreamBytes();
    void handleStreamFinished();
    void refuseStream(const acp::ApiError &error);
    void handleFrames(const QList<SseEvent> &frames);
    void scheduleReconnect(const QString &reason);
    void enterPolling(const QString &reason);
    void leavePolling();
    void closeReply();
    [[nodiscard]] qint64 parseRotateCursor(const QString &payload) const;

    StreamScope m_scope;
    ApiClient *m_client = nullptr;
    StreamLimits m_limits;

    SseParser m_parser;
    QPointer<QNetworkReply> m_reply;
    QTimer *m_reconnectTimer = nullptr;
    QTimer *m_pollTimer = nullptr;
    QTimer *m_silenceTimer = nullptr;
    Backoff m_backoff;

    StreamStatus::State m_status = StreamStatus::Idle;
    QString m_lastError;
    QDateTime m_lastEventAt;
    bool m_catchUpInProgress = false;
    bool m_journalHasGaps = false;
    bool m_stopped = true;
};

/*!
    Multiplexeur d'abonnements.

    Une seule connexion par portée, quel que soit le nombre de panneaux qui l'affichent.
    Au-delà de la borne annoncée par le serveur, une demande supplémentaire est REFUSÉE
    localement avec un message français, plutôt que d'aller chercher un 429 qui bloquerait
    ensuite l'utilisateur pendant cinq secondes.
*/
class EventStreamService : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int activeCount READ activeCount NOTIFY subscriptionsChanged)
    Q_PROPERTY(int maxConnections READ maxConnections NOTIFY limitsChanged)

public:
    explicit EventStreamService(ApiClient *client, QObject *parent = nullptr);

    /*! Applique les bornes annoncées par le serveur. */
    void setLimits(const StreamLimits &limits);
    [[nodiscard]] const StreamLimits &limits() const { return m_limits; }
    [[nodiscard]] int maxConnections() const { return m_limits.maxConnectionsPerUser; }

    /*! Abonne la portée « tentative ». Renvoie l'abonnement existant s'il y en a un. */
    StreamSubscription *subscribeRun(const QString &runId);

    /*! Abonne la portée « projet ». Le desktop en est le premier consommateur
        applicatif ; l'audit le dit et prévient que cela n'a jamais été éprouvé en réel. */
    StreamSubscription *subscribeProject(const QString &projectId);

    /*! Ferme et oublie un abonnement. */
    Q_INVOKABLE void unsubscribe(const QString &key);

    /*! Ferme TOUS les abonnements. Appelé à la déconnexion, à la révocation et à la
        fermeture de l'application : un flux non refermé reste compté par le serveur. */
    void closeAll();

    [[nodiscard]] int activeCount() const { return static_cast<int>(m_subscriptions.size()); }

    /*! Dernier refus opposé par le multiplexeur lui-même, à afficher tel quel. */
    [[nodiscard]] const QString &lastRefusal() const { return m_lastRefusal; }

signals:
    void subscriptionsChanged();
    void limitsChanged();
    void subscriptionRefused(const QString &message);

private:
    StreamSubscription *acquire(StreamScope scope);

    ApiClient *m_client = nullptr;
    StreamLimits m_limits;
    QHash<QString, StreamSubscription *> m_subscriptions;
    QString m_lastRefusal;
};

} // namespace acp
