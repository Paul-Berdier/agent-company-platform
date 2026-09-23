#include "events/EventStreamService.h"

#include "api/ApiClient.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrlQuery>
#include <QVariant>

namespace acp {

namespace {

//! Marge ajoutée au keep-alive avant de considérer le flux muet. Le serveur émet
//! « : ping » toutes les 15 s ; au-delà de deux intervalles plus une marge, le lien est
//! mort même si la socket n'a rien signalé.
constexpr int kSilenceMarginSeconds = 10;

bool hasEventStreamType(QNetworkReply *reply)
{
    return reply->rawHeader(QByteArrayLiteral("Content-Type")).split(';').first().trimmed().toLower()
        == QByteArrayLiteral("text/event-stream");
}

} // namespace

// --- StreamSubscription -------------------------------------------------------

StreamSubscription::StreamSubscription(StreamScope scope, ApiClient *client, StreamLimits limits,
                                       QObject *parent)
    : QObject(parent)
    , m_scope(std::move(scope))
    , m_client(client)
    , m_limits(limits)
    , m_reconnectTimer(new QTimer(this))
    , m_pollTimer(new QTimer(this))
    , m_silenceTimer(new QTimer(this))
{
    m_reconnectTimer->setSingleShot(true);
    connect(m_reconnectTimer, &QTimer::timeout, this, [this] {
        if (!m_stopped) {
            openStream();
        }
    });

    // Interrogation périodique : repli quand le flux ne tient pas. L'intervalle est
    // volontairement bien plus lent que le pas serveur (400 ms) : l'interrogation est un
    // filet de sécurité, pas un substitut permanent.
    m_pollTimer->setInterval(5000);
    connect(m_pollTimer, &QTimer::timeout, this, [this] {
        if (!m_stopped && !m_catchUpInProgress) {
            requestJournalPage();
        }
    });

    m_silenceTimer->setSingleShot(true);
    connect(m_silenceTimer, &QTimer::timeout, this, [this] {
        // Aucun octet, pas même un keep-alive : le lien est mort sans l'avoir dit.
        scheduleReconnect(QStringLiteral("Aucun signe de vie du flux."));
    });
}

StreamSubscription::~StreamSubscription()
{
    closeReply();
}

QString StreamSubscription::statusLabel() const
{
    switch (m_status) {
    case StreamStatus::Idle:
        return QStringLiteral("Inactif");
    case StreamStatus::Connecting:
        return QStringLiteral("Connexion");
    case StreamStatus::Live:
        return QStringLiteral("En direct");
    case StreamStatus::Reconnecting:
        return QStringLiteral("Reconnexion");
    case StreamStatus::Polling:
        return QStringLiteral("Interrogation périodique");
    case StreamStatus::Offline:
        return QStringLiteral("Hors ligne");
    case StreamStatus::Refused:
        return QStringLiteral("Refusé");
    }
    return QStringLiteral("Inconnu");
}

void StreamSubscription::setStatus(StreamStatus::State status, const QString &detail)
{
    if (m_status == status && m_lastError == detail) {
        return;
    }
    m_status = status;
    m_lastError = detail;
    emit statusChanged();
}

void StreamSubscription::start()
{
    if (!m_stopped) {
        return;
    }
    m_stopped = false;
    m_backoff.reset();
    beginCatchUp();
}

void StreamSubscription::stop()
{
    if (m_stopped) {
        return;
    }
    m_stopped = true;
    m_reconnectTimer->stop();
    m_silenceTimer->stop();
    leavePolling();
    closeReply();
    setStatus(StreamStatus::Idle);
}

void StreamSubscription::closeReply()
{
    if (!m_reply) {
        return;
    }
    QNetworkReply *reply = m_reply.data();
    m_reply = nullptr;
    // La fermeture propre est ce qui rend son jeton au serveur. On coupe les signaux
    // avant d'abandonner, pour ne pas retomber dans handleStreamFinished().
    reply->disconnect(this);
    reply->abort();
    reply->deleteLater();
}

// --- Étape 1 : rattrapage sur le journal durable ------------------------------

void StreamSubscription::beginCatchUp()
{
    m_catchUpInProgress = true;
    setStatus(StreamStatus::Connecting);
    requestJournalPage();
}

void StreamSubscription::requestJournalPage()
{
    if (!m_client) {
        return;
    }
    ApiRequest request;
    request.method = QByteArrayLiteral("GET");
    request.path = scopeJournalPath(m_scope);
    QUrlQuery query;
    // Le curseur est EXCLUSIF côté serveur : after_seq=N rend les événements > N.
    query.addQueryItem(QStringLiteral("after_seq"), QString::number(scopeCursorValue(m_scope)));
    query.addQueryItem(QStringLiteral("limit"), QString::number(m_limits.pageLimit));
    request.query = query;

    ApiCall *call = m_client->send(request);
    connect(call, &ApiCall::succeeded, this, [this](const ApiResponse &response) {
        const QJsonObject page = response.json.object();
        if (!page.contains(QStringLiteral("events"))) {
            // Réponse hors contrat : rien n'est rendu partiellement.
            m_catchUpInProgress = false;
            setStatus(StreamStatus::Offline,
                      QStringLiteral("Le journal a renvoyé une page hors contrat."));
            return;
        }
        const QJsonArray events = page.value(QStringLiteral("events")).toArray();
        for (const QJsonValue &item : events) {
            if (!item.isObject()) {
                continue;
            }
            const QJsonObject event = item.toObject();
            if (!event.contains(QStringLiteral("sequence"))
                || event.value(QStringLiteral("sequence")).isNull()) {
                // Ligne antérieure au Lot E : elle n'a pas de numérotation et sort donc
                // des portées. On le SIGNALE au lieu de faire comme si de rien n'était.
                m_journalHasGaps = true;
            }
            emit journalEvent(event);
        }

        const QJsonValue nextCursor = page.value(QStringLiteral("next_cursor"));
        if (nextCursor.isDouble()) {
            advanceScopeCursor(m_scope, static_cast<qint64>(nextCursor.toDouble()));
            m_lastEventAt = QDateTime::currentDateTimeUtc();
            emit cursorChanged();
        }

        const bool hasMore = page.value(QStringLiteral("has_more")).toBool(false);
        if (hasMore) {
            // Encore des pages : on continue le rattrapage avant d'ouvrir le flux.
            requestJournalPage();
            return;
        }
        m_catchUpInProgress = false;
        if (m_stopped) {
            return;
        }
        if (m_status == StreamStatus::Polling) {
            // En mode interrogation, une page complète suffit ; on retente le direct.
            openStream();
            return;
        }
        openStream();
    });
    connect(call, &ApiCall::failed, this, [this](const ApiError &error) {
        m_catchUpInProgress = false;
        if (m_stopped) {
            return;
        }
        if (error.kind() == ApiFailure::Forbidden || error.kind() == ApiFailure::Unauthorized) {
            setStatus(StreamStatus::Refused, error.message());
            emit refused(error);
            return;
        }
        if (error.kind() == ApiFailure::NotFound) {
            setStatus(StreamStatus::Refused, error.message());
            emit refused(error);
            return;
        }
        scheduleReconnect(error.message());
    });
}

// --- Étape 2 : ouverture du flux ---------------------------------------------

void StreamSubscription::openStream()
{
    if (m_stopped || !m_client) {
        return;
    }
    closeReply();

    QUrlQuery query;
    // `Last-Event-ID` est prioritaire côté serveur ; `after_seq` reste envoyé pour le cas
    // où l'en-tête serait absorbé par une passerelle. Les deux portent le MÊME curseur,
    // celui de CETTE portée : voir StreamScope, où c'est structurellement garanti.
    query.addQueryItem(QStringLiteral("after_seq"), QString::number(scopeCursorValue(m_scope)));

    const QUrl url = m_client->resolve(scopeStreamPath(m_scope), query);
    if (url.isEmpty()) {
        setStatus(StreamStatus::Offline,
                  QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }

    QNetworkRequest request(url);
    // Le flux ne renouvelle pas la session. Une réponse tardive ne doit pas rétablir
    // un cookie après la déconnexion ou un changement de serveur.
    request.setAttribute(QNetworkRequest::CookieSaveControlAttribute, QNetworkRequest::Manual);
    request.setRawHeader(QByteArrayLiteral("Accept"), QByteArrayLiteral("text/event-stream"));
    request.setRawHeader(QByteArrayLiteral("Cache-Control"), QByteArrayLiteral("no-cache"));
    if (!m_parser.lastEventId().isEmpty()) {
        request.setRawHeader(QByteArrayLiteral("Last-Event-ID"), m_parser.lastEventId().toUtf8());
    }
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                         QVariant::fromValue(QNetworkRequest::ManualRedirectPolicy));
    // Aucun délai de transfert : un flux SSE est long par nature, et le serveur le fait
    // tourner lui-même au bout de 900 s avec une trame `acp.stream.rotate`. Le silence
    // est surveillé par m_silenceTimer, qui est le bon instrument ici.
    request.setTransferTimeout(std::chrono::milliseconds::zero());

    m_parser.resetFrameBuffers();
    setStatus(StreamStatus::Connecting);

    QNetworkReply *reply = m_client->networkAccessManager()->get(request);
    m_reply = reply;
    connect(reply, &QNetworkReply::readyRead, this, &StreamSubscription::handleStreamBytes);
    connect(reply, &QNetworkReply::finished, this, &StreamSubscription::handleStreamFinished);

    m_silenceTimer->start((m_limits.keepAliveSeconds * 2 + kSilenceMarginSeconds) * 1000);
}

// --- Étape 3 : consommation ---------------------------------------------------

void StreamSubscription::handleStreamBytes()
{
    if (!m_reply) {
        return;
    }
    // Tout octet reçu — y compris un simple keep-alive — prouve que le lien est vivant.
    m_silenceTimer->start((m_limits.keepAliveSeconds * 2 + kSilenceMarginSeconds) * 1000);

    const QVariant statusAttribute = m_reply->attribute(QNetworkRequest::HttpStatusCodeAttribute);
    const int httpStatus = statusAttribute.isValid() ? statusAttribute.toInt() : 0;
    if (httpStatus == 401 || httpStatus == 403) {
        refuseStream(ApiError::fromHttpStatus(httpStatus, extractProblemDetail(m_reply->read(4096))));
        return;
    }
    if (httpStatus >= 400) {
        // Le corps d'erreur sera traité à la fin de la réponse ; on ne l'analyse pas
        // comme du SSE.
        return;
    }
    if (httpStatus != 200 || !hasEventStreamType(m_reply)) {
        refuseStream(ApiError(ApiFailure::InvalidResponse,
                              QStringLiteral("Le serveur n'a pas renvoyé un flux SSE HTTP 200 de type text/event-stream."),
                              httpStatus));
        return;
    }

    if (m_status != StreamStatus::Live) {
        setStatus(StreamStatus::Live);
        leavePolling();
        // Le recul n'est remis à zéro qu'après un signe de vie RÉEL, jamais sur la seule
        // ouverture de socket : sinon une boucle « ouvre, ferme » resterait à 1 s.
        m_backoff.reset();
    }
    handleFrames(m_parser.consume(m_reply->readAll()));
}

void StreamSubscription::handleFrames(const QList<SseEvent> &frames)
{
    for (const SseEvent &frame : frames) {
        if (frame.isClosed()) {
            QString reason = QStringLiteral("inconnue");
            QJsonParseError parseError{};
            const QJsonDocument document =
                QJsonDocument::fromJson(frame.data.toUtf8(), &parseError);
            if (parseError.error == QJsonParseError::NoError && document.isObject()) {
                reason = document.object().value(QStringLiteral("reason")).toString(reason);
            }
            // Une fermeture serveur n'est PAS une erreur réseau, et surtout pas un arrêt
            // de mission. On s'arrête et on le dit.
            m_stopped = true;
            m_silenceTimer->stop();
            leavePolling();
            closeReply();
            setStatus(StreamStatus::Refused,
                      reason == QLatin1String("unauthorized")
                          ? QStringLiteral("Session ou appartenance révoquée par le serveur.")
                          : QStringLiteral("Le serveur a fermé le flux (%1).").arg(reason));
            emit serverClosed(reason);
            return;
        }

        if (frame.isRotate()) {
            // Durée maximale atteinte. Le curseur porté par la trame fait autorité : il
            // est repris tel quel, dans l'espace de curseur de CETTE portée.
            const qint64 rotateCursor = parseRotateCursor(frame.data);
            if (rotateCursor > 0) {
                advanceScopeCursor(m_scope, rotateCursor);
                emit cursorChanged();
            }
            closeReply();
            m_silenceTimer->stop();
            setStatus(StreamStatus::Reconnecting,
                      QStringLiteral("Rotation du flux après la durée maximale."));
            // Reconnexion immédiate mais pas instantanée : la rotation est un chemin
            // nominal, et une flotte de postes ne doit pas repartir en rafale.
            m_reconnectTimer->start(std::chrono::milliseconds(250));
            return;
        }

        if (!frame.isJournalEvent()) {
            // Trame nommée inconnue : ignorée sans erreur, pour que le serveur puisse en
            // ajouter sans casser ce client.
            continue;
        }

        QJsonParseError parseError{};
        const QJsonDocument document = QJsonDocument::fromJson(frame.data.toUtf8(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
            // Une trame illisible est signalée, jamais rendue à moitié.
            setStatus(StreamStatus::Live,
                      QStringLiteral("Une trame d'événement était illisible et a été écartée."));
            continue;
        }
        const QJsonObject event = document.object();
        bool converted = false;
        const qint64 cursor = frame.lastEventId.toLongLong(&converted);
        if (converted) {
            advanceScopeCursor(m_scope, cursor);
        }
        m_lastEventAt = QDateTime::currentDateTimeUtc();
        emit journalEvent(event);
        emit cursorChanged();
    }
}

qint64 StreamSubscription::parseRotateCursor(const QString &payload) const
{
    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(payload.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        return 0;
    }
    const QJsonValue cursor = document.object().value(QStringLiteral("cursor"));
    return cursor.isDouble() ? static_cast<qint64>(cursor.toDouble()) : 0;
}

// --- Étape 4 : coupure --------------------------------------------------------

void StreamSubscription::handleStreamFinished()
{
    if (!m_reply) {
        return;
    }
    QNetworkReply *reply = m_reply.data();
    m_reply = nullptr;
    m_silenceTimer->stop();

    const QVariant statusAttribute = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute);
    const int httpStatus = statusAttribute.isValid() ? statusAttribute.toInt() : 0;
    const QByteArray tail = reply->readAll();
    const QString transportError = reply->errorString();
    const bool validStream = httpStatus == 200 && hasEventStreamType(reply);
    reply->deleteLater();

    if (m_stopped) {
        return;
    }

    if (httpStatus == 401 || httpStatus == 403) {
        refuseStream(ApiError::fromHttpStatus(httpStatus, extractProblemDetail(tail)));
        return;
    }
    if (httpStatus > 0 && httpStatus < 400 && !validStream) {
        refuseStream(ApiError(ApiFailure::InvalidResponse,
                              QStringLiteral("Le serveur n'a pas renvoyé un flux SSE HTTP 200 de type text/event-stream."),
                              httpStatus));
        return;
    }

    if (!tail.isEmpty() && validStream) {
        handleFrames(m_parser.consume(tail));
        if (m_stopped) {
            return;
        }
    }
    // Un bloc tronqué en fin de flux est abandonné, jamais complété.
    const QList<SseEvent> trailing = m_parser.finish();
    if (!trailing.isEmpty()) {
        handleFrames(trailing);
        if (m_stopped) {
            return;
        }
    }

    if (httpStatus == 429) {
        // Borne de flux simultanés atteinte. Le serveur donne Retry-After: 5, et le jeton
        // d'un flux mal refermé n'est rendu qu'au bout de 900 s : insister ne sert à rien.
        enterPolling(QStringLiteral(
            "Trop de flux simultanés pour cet utilisateur ; passage en interrogation "
            "périodique. Fermez un panneau en direct pour revenir au temps réel."));
        return;
    }
    if (httpStatus >= 400) {
        const ApiError error = ApiError::fromHttpStatus(httpStatus, extractProblemDetail(tail));
        scheduleReconnect(error.message());
        return;
    }
    scheduleReconnect(transportError.isEmpty() ? QStringLiteral("Le flux s'est interrompu.")
                                               : transportError);
}

void StreamSubscription::refuseStream(const ApiError &error)
{
    m_stopped = true;
    m_reconnectTimer->stop();
    m_silenceTimer->stop();
    leavePolling();
    closeReply();
    setStatus(StreamStatus::Refused, error.message());
    const QPointer<ApiClient> client = m_client;
    emit refused(error);
    // Un 403 peut désigner seulement une appartenance manquante. Un 401, en revanche,
    // invalide la session globale et donc sa copie éventuelle dans le coffre système.
    if (error.httpStatus() == 401 && client) emit client->unauthorizedObserved();
}

void StreamSubscription::scheduleReconnect(const QString &reason)
{
    if (m_stopped) {
        return;
    }
    closeReply();
    const std::chrono::milliseconds delay = m_backoff.nextDelay();
    // Au-delà de quelques échecs consécutifs, on cesse de prétendre au direct et on
    // bascule en interrogation : l'opérateur doit voir « Interrogation périodique » et
    // non un « Reconnexion » perpétuel qui ressemble à un travail en cours.
    if (m_backoff.consecutiveFailures() >= 4) {
        enterPolling(reason);
        return;
    }
    setStatus(StreamStatus::Reconnecting, reason);
    m_reconnectTimer->start(delay);
}

void StreamSubscription::enterPolling(const QString &reason)
{
    setStatus(StreamStatus::Polling, reason);
    if (!m_pollTimer->isActive()) {
        m_pollTimer->start();
    }
    // Une tentative de retour au direct est programmée sur le recul courant : le repli
    // est un état temporaire annoncé comme tel, pas une résignation.
    m_reconnectTimer->start(m_backoff.nextDelay());
}

void StreamSubscription::leavePolling()
{
    if (m_pollTimer->isActive()) {
        m_pollTimer->stop();
    }
}

// --- EventStreamService -------------------------------------------------------

EventStreamService::EventStreamService(ApiClient *client, QObject *parent)
    : QObject(parent)
    , m_client(client)
{
    connect(client, &ApiClient::baseUrlChanged, this, &EventStreamService::closeAll);
    connect(client, &ApiClient::sessionStateCleared, this, &EventStreamService::closeAll);
}

void EventStreamService::setLimits(const StreamLimits &limits)
{
    m_limits = limits;
    emit limitsChanged();
}

StreamSubscription *EventStreamService::subscribeRun(const QString &runId)
{
    return acquire(RunScope{runId, RunCursor{}});
}

StreamSubscription *EventStreamService::subscribeProject(const QString &projectId)
{
    return acquire(ProjectScope{projectId, ProjectCursor{}});
}

StreamSubscription *EventStreamService::acquire(StreamScope scope)
{
    const QString key = scopeKey(scope);
    if (StreamSubscription *existing = m_subscriptions.value(key, nullptr)) {
        // Une connexion par portée, réutilisée par tous les panneaux. Jamais une par
        // fenêtre, jamais une par onglet.
        return existing;
    }
    if (m_subscriptions.size() >= m_limits.maxConnectionsPerUser) {
        m_lastRefusal = QStringLiteral(
                            "Limite de %1 flux simultanés atteinte pour cet utilisateur. "
                            "Fermez un panneau en direct avant d'en ouvrir un autre.")
                            .arg(m_limits.maxConnectionsPerUser);
        emit subscriptionRefused(m_lastRefusal);
        return nullptr;
    }

    auto *subscription = new StreamSubscription(std::move(scope), m_client, m_limits, this);
    m_subscriptions.insert(key, subscription);
    emit subscriptionsChanged();
    subscription->start();
    return subscription;
}

void EventStreamService::unsubscribe(const QString &key)
{
    StreamSubscription *subscription = m_subscriptions.take(key);
    if (!subscription) {
        return;
    }
    subscription->stop();
    subscription->deleteLater();
    emit subscriptionsChanged();
}

void EventStreamService::closeAll()
{
    const QList<QString> keys = m_subscriptions.keys();
    for (const QString &key : keys) {
        unsubscribe(key);
    }
}

} // namespace acp
