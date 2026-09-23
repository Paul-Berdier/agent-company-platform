#include "api/ApiClient.h"

#include "api/IdempotencyKey.h"
#include "api/SessionCookieJar.h"

#include <QHostAddress>
#include <QJsonParseError>
#include <QNetworkAccessManager>
#include <QNetworkCookie>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRandomGenerator>
#include <QTimer>
#include <QVariant>

namespace acp {

namespace {

//! En-têtes de réponse conservés. Tout le reste est écarté : un en-tête non listé ne
//! doit jamais atteindre l'interface, et surtout pas Set-Cookie.
const QList<QByteArray> kRetainedHeaders = {
    QByteArrayLiteral("content-type"),
    QByteArrayLiteral("content-length"),
    QByteArrayLiteral("content-range"),
    QByteArrayLiteral("retry-after"),
    QByteArrayLiteral("etag"),
    QByteArrayLiteral("last-event-id"),
};

bool isLoopbackHost(const QString &host)
{
    if (host.compare(QStringLiteral("localhost"), Qt::CaseInsensitive) == 0) {
        return true;
    }
    QHostAddress address(host);
    return !address.isNull() && address.isLoopback();
}

} // namespace

// --- ApiCall -----------------------------------------------------------------

ApiCall::ApiCall(ApiRequest request, QObject *parent)
    : QObject(parent)
    , m_request(std::move(request))
{
}

void ApiCall::abort()
{
    if (m_finished || m_aborted) {
        return;
    }
    m_aborted = true;
    if (m_reply) {
        // La fin de l'appel est produite par le gestionnaire de réponse, qui verra
        // l'annulation ; on ne double pas le signal terminal ici.
        m_reply->abort();
        return;
    }
    m_finished = true;
    emit failed(ApiError(ApiFailure::Cancelled, QStringLiteral("Appel interrompu.")));
    deleteLater();
}

// --- ApiClient : cycle de vie -------------------------------------------------

ApiClient::ApiClient(QObject *parent)
    : QObject(parent)
    , m_manager(new QNetworkAccessManager(this))
    , m_cookieJar(new SessionCookieJar(this))
{
    // QNetworkAccessManager prend la propriété du pot ; le pot reste néanmoins enfant du
    // client, ce que Qt accepte : setCookieJar reparente l'objet sur le gestionnaire.
    m_manager->setCookieJar(m_cookieJar);
    m_manager->setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
    // Les réponses sont détruites explicitement par le client, jamais par le gestionnaire :
    // le flux SSE lit un QNetworkReply sur une longue durée et doit contrôler sa fin.
    m_manager->setAutoDeleteReplies(false);
}

ApiClient::~ApiClient() = default;

// --- Configuration ------------------------------------------------------------

ApiError ApiClient::setBaseUrl(const QUrl &url)
{
    if (url.isEmpty()) {
        m_baseUrl = QUrl();
        clearSessionState();
        emit baseUrlChanged();
        return {};
    }
    if (!url.isValid()) {
        return ApiError::refusal(QStringLiteral("L'adresse du serveur n'est pas une URL valide."));
    }
    const QString scheme = url.scheme().toLower();
    if (scheme != QStringLiteral("https")) {
        if (scheme != QStringLiteral("http")) {
            return ApiError::refusal(
                QStringLiteral("Seul le schéma HTTPS est accepté ; « %1 » a été refusé.")
                    .arg(url.scheme()));
        }
        if (!m_allowInsecureLoopback) {
            return ApiError::refusal(QStringLiteral(
                "HTTP en clair est refusé. Utilisez HTTPS, ou activez explicitement le "
                "bouclage local en clair dans les réglages de connexion."));
        }
        if (!isLoopbackHost(url.host())) {
            return ApiError::refusal(QStringLiteral(
                "HTTP en clair n'est accepté que sur une adresse de bouclage ; « %1 » n'en "
                "est pas une.")
                                         .arg(url.host()));
        }
    }
    if (url.host().isEmpty()) {
        return ApiError::refusal(QStringLiteral("L'adresse du serveur n'indique aucun hôte."));
    }

    QUrl normalized;
    normalized.setScheme(scheme);
    normalized.setHost(url.host());
    if (url.port() != -1) {
        normalized.setPort(url.port());
    }
    // Un préfixe de chemin est conservé (déploiement derrière un sous-chemin), sans sa
    // barre oblique finale, pour que resolve() concatène sans ambiguïté.
    QString path = url.path();
    while (path.endsWith(QLatin1Char('/'))) {
        path.chop(1);
    }
    normalized.setPath(path);

    if (normalized == m_baseUrl) {
        return {};
    }
    m_baseUrl = normalized;
    // Une session n'appartient jamais à deux serveurs : changer d'URL purge tout.
    clearSessionState();
    emit baseUrlChanged();
    return {};
}

void ApiClient::setAllowInsecureLoopback(bool allowed)
{
    m_allowInsecureLoopback = allowed;
}

void ApiClient::setUseSystemProxy(bool enabled)
{
    if (m_useSystemProxy == enabled) {
        return;
    }
    m_useSystemProxy = enabled;
    m_manager->setProxy(enabled ? QNetworkProxy(QNetworkProxy::DefaultProxy)
                                : QNetworkProxy(QNetworkProxy::NoProxy));
}

void ApiClient::setUserAgent(const QByteArray &userAgent)
{
    m_userAgent = userAgent;
}

void ApiClient::setCsrfToken(const QString &token)
{
    if (m_csrfToken == token) {
        return;
    }
    m_csrfToken = token;
    emit csrfTokenChanged();
}

void ApiClient::clearCsrfToken()
{
    setCsrfToken(QString());
}

void ApiClient::clearSessionState()
{
    invalidatePendingCalls();
    m_cookieJar->clearAll();
    clearCsrfToken();
    emit sessionStateCleared();
}

void ApiClient::invalidatePendingCalls()
{
    ++m_sessionGeneration;
    const bool alreadyInvalidating = m_invalidating;
    m_invalidating = true;
    const auto calls = m_inFlight;
    m_pendingRotating.clear();
    m_pendingUnsafe.clear();
    m_rotatingCall = nullptr;
    for (const QPointer<ApiCall> &call : calls) {
        if (call && !call->m_finished) {
            call->abort();
            releaseCall(call);
        }
    }
    m_invalidating = alreadyInvalidating;
}

QUrl ApiClient::resolve(const QString &path, const QUrlQuery &query) const
{
    if (m_baseUrl.isEmpty()) {
        return {};
    }
    QUrl url = m_baseUrl;
    QString fullPath = m_baseUrl.path();
    if (!path.startsWith(QLatin1Char('/'))) {
        fullPath += QLatin1Char('/');
    }
    fullPath += path;
    url.setPath(fullPath);
    if (!query.isEmpty()) {
        url.setQuery(query);
    }
    return url;
}

int ApiClient::inFlightCount() const
{
    int count = 0;
    for (const QPointer<ApiCall> &call : m_inFlight) {
        if (call) {
            ++count;
        }
    }
    return count;
}

// --- Politique de réessai -----------------------------------------------------

int ApiClient::plannedAttempts(const ApiRequest &request)
{
    if (request.isSafeMethod()) {
        return kMaxAttempts;
    }
    // Une mutation n'est rejouable QUE si le serveur peut reconnaître le rejeu.
    // Sans clé d'idempotence, une seule tentative — jamais deux.
    return request.idempotencyKey.isEmpty() ? 1 : kMaxAttempts;
}

bool ApiClient::shouldRetry(const ApiRequest &request, const ApiError &error, int attempt)
{
    if (attempt >= plannedAttempts(request)) {
        return false;
    }
    if (!error.isRetryable()) {
        return false;
    }
    if (request.isSafeMethod()) {
        return true;
    }
    return !request.idempotencyKey.isEmpty();
}

std::chrono::milliseconds ApiClient::retryDelay(const ApiError &error, int attempt)
{
    // Le serveur, quand il le dit, a toujours raison : Retry-After prime.
    if (const std::optional<int> &after = error.retryAfterSeconds(); after && *after >= 0) {
        return std::chrono::milliseconds(*after * 1000);
    }
    // Recul progressif borné, avec gigue : 500 ms, 1 s, 2 s, plafonné à 8 s. La gigue
    // évite qu'une flotte de postes reconnectés en même temps frappe en cadence.
    const int exponent = qBound(0, attempt - 1, 4);
    const qint64 base = qMin<qint64>(500LL << exponent, 8000LL);
    const qint64 jitter = QRandomGenerator::global()->bounded(static_cast<int>(base / 4) + 1);
    return std::chrono::milliseconds(base + jitter);
}

// --- Émission -----------------------------------------------------------------

ApiError ApiClient::validateBeforeSend(const ApiRequest &request) const
{
    if (m_invalidating) {
        return ApiError(ApiFailure::Cancelled, QStringLiteral("La session change ; appel annulé."));
    }
    if (m_baseUrl.isEmpty()) {
        return ApiError::refusal(QStringLiteral(
            "Aucune adresse de serveur n'est configurée. Renseignez-la dans l'écran de "
            "connexion avant toute opération."));
    }
    if (request.path.isEmpty()) {
        return ApiError::refusal(QStringLiteral("Chemin d'API vide."));
    }
    if (request.method.isEmpty()) {
        return ApiError::refusal(QStringLiteral("Verbe HTTP vide."));
    }
    if (!request.idempotencyKey.isEmpty() && !isValidIdempotencyKey(request.idempotencyKey)) {
        return ApiError::refusal(QStringLiteral(
            "Clé d'idempotence invalide : 1 à 200 caractères ASCII visibles sont attendus."));
    }
    if (!request.isSafeMethod() && !request.publicEndpoint && m_csrfToken.isEmpty()) {
        return ApiError::refusal(QStringLiteral(
            "Aucun jeton CSRF n'est détenu : l'écriture est refusée tant que la session "
            "n'est pas établie."));
    }
    return {};
}

ApiCall *ApiClient::send(const ApiRequest &request)
{
    auto *call = new ApiCall(request, this);
    call->m_maxAttempts = plannedAttempts(request);
    call->m_sessionGeneration = m_sessionGeneration;
    call->m_url = resolve(request.path, request.query);

    const ApiError refusal = validateBeforeSend(request);
    if (refusal.isError()) {
        // Refus immédiat, mais toujours asynchrone : l'appelant a le droit de connecter
        // ses signaux après le retour de send().
        QTimer::singleShot(0, call, [this, call, refusal] { finishWithError(call, refusal); });
        return call;
    }

    m_inFlight.append(call);
    emit inFlightCountChanged();

    // Une mutation demandée pendant une rotation du jeton CSRF attend : le serveur a
    // peut-être déjà fait tourner le jeton que nous détenons encore.
    if (!request.isSafeMethod() && m_rotatingCall) {
        m_pendingUnsafe.enqueue(call);
        return call;
    }
    dispatch(call);
    return call;
}

ApiCall *ApiClient::sendCsrfRotating(const ApiRequest &request)
{
    auto *call = new ApiCall(request, this);
    call->m_maxAttempts = plannedAttempts(request);
    call->m_sessionGeneration = m_sessionGeneration;
    call->m_url = resolve(request.path, request.query);

    const ApiError refusal = validateBeforeSend(request);
    if (refusal.isError()) {
        QTimer::singleShot(0, call, [this, call, refusal] { finishWithError(call, refusal); });
        return call;
    }

    m_inFlight.append(call);
    emit inFlightCountChanged();

    if (m_rotatingCall) {
        // Un seul appel rotatif en vol : les suivants attendent leur tour, en ordre.
        m_pendingRotating.enqueue(call);
        return call;
    }
    m_rotatingCall = call;
    dispatch(call);
    return call;
}

void ApiClient::dispatch(ApiCall *call)
{
    call->m_attempt = 0;
    startAttempt(call);
}

void ApiClient::startAttempt(ApiCall *call)
{
    if (!call || call->m_finished) {
        return;
    }
    if (call->m_aborted || call->m_sessionGeneration != m_sessionGeneration) {
        finishWithError(call, ApiError(ApiFailure::Cancelled, QStringLiteral("Appel interrompu.")));
        return;
    }
    ++call->m_attempt;

    const ApiRequest &request = call->m_request;
    const QUrl url = call->m_url;
    if (url.isEmpty()) {
        finishWithError(call,
                        ApiError::refusal(QStringLiteral(
                            "Aucune adresse de serveur n'est configurée.")));
        return;
    }

    QNetworkRequest networkRequest(url);
    // Qt ne doit pas appliquer un Set-Cookie AVANT le contrôle de génération : une
    // réponse de connexion retardée pourrait autrement rétablir une session purgée.
    networkRequest.setAttribute(QNetworkRequest::CookieSaveControlAttribute,
                                QNetworkRequest::Manual);
    networkRequest.setRawHeader(QByteArrayLiteral("Accept"), request.accept);
    if (!m_userAgent.isEmpty()) {
        networkRequest.setRawHeader(QByteArrayLiteral("User-Agent"), m_userAgent);
    }
    if (!request.body.isNull()) {
        networkRequest.setHeader(QNetworkRequest::ContentTypeHeader,
                                 QStringLiteral("application/json"));
    }
    // X-CSRF-Token sur les seules méthodes non sûres et non publiques, exactement comme
    // `require_csrf` l'exige côté serveur.
    if (!request.isSafeMethod() && !request.publicEndpoint && !m_csrfToken.isEmpty()) {
        networkRequest.setRawHeader(QByteArrayLiteral("X-CSRF-Token"), m_csrfToken.toUtf8());
    }
    if (!request.clientAnnouncement.isEmpty()) {
        networkRequest.setRawHeader(QByteArrayLiteral("X-ACP-Client"), request.clientAnnouncement);
    }
    if (!request.idempotencyKey.isEmpty()) {
        networkRequest.setRawHeader(QByteArrayLiteral("Idempotency-Key"),
                                    request.idempotencyKey.toUtf8());
    }
    // Aucune redirection suivie : une redirection inattendue est une anomalie, pas un
    // chemin nominal. Le CLI se comporte déjà ainsi.
    networkRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                                QVariant::fromValue(QNetworkRequest::ManualRedirectPolicy));
    networkRequest.setTransferTimeout(request.timeout);

    const QByteArray payload = request.body.isNull() ? QByteArray() : request.body.toJson(QJsonDocument::Compact);

    QNetworkReply *reply = nullptr;
    if (request.method == QByteArrayLiteral("GET")) {
        reply = m_manager->get(networkRequest);
    } else if (request.method == QByteArrayLiteral("POST")) {
        reply = m_manager->post(networkRequest, payload);
    } else if (request.method == QByteArrayLiteral("PUT")) {
        reply = m_manager->put(networkRequest, payload);
    } else if (request.method == QByteArrayLiteral("DELETE") && payload.isEmpty()) {
        reply = m_manager->deleteResource(networkRequest);
    } else {
        // PATCH, et DELETE avec corps : sendCustomRequest est la voie documentée.
        reply = m_manager->sendCustomRequest(networkRequest, request.method, payload);
    }

    call->m_reply = reply;
    connect(reply, &QNetworkReply::finished, call, [this, call, reply] {
        handleReply(call, reply);
    });
}

void ApiClient::handleReply(ApiCall *call, QNetworkReply *reply)
{
    if (!call) {
        reply->deleteLater();
        return;
    }
    call->m_reply = nullptr;
    if (call->m_finished || call->m_aborted
        || call->m_sessionGeneration != m_sessionGeneration) {
        reply->deleteLater();
        finishWithError(call, ApiError(ApiFailure::Cancelled, QStringLiteral("Appel interrompu.")));
        return;
    }
    const QByteArray body = reply->readAll();
    const QVariant statusAttribute = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute);
    const int httpStatus = statusAttribute.isValid() ? statusAttribute.toInt() : 0;
    const QNetworkReply::NetworkError networkError = reply->error();
    // Lu AVANT toute destruction différée : la chaîne appartient à la réponse.
    const QString networkErrorText = reply->errorString();

    ApiResponse response;
    response.httpStatus = httpStatus;
    response.rawBody = body;
    for (const QByteArray &name : kRetainedHeaders) {
        if (reply->hasRawHeader(name)) {
            response.headers.insert(name, reply->rawHeader(name));
        }
    }
    QList<QNetworkCookie> cookies;
    for (const auto &header : reply->rawHeaderPairs()) {
        if (header.first.compare(QByteArrayLiteral("set-cookie"), Qt::CaseInsensitive) == 0)
            cookies.append(QNetworkCookie::parseCookies(header.second));
    }
    if (!cookies.isEmpty()) m_cookieJar->setCookiesFromUrl(cookies, call->m_url);
    reply->deleteLater();

    if (call->m_aborted || call->m_sessionGeneration != m_sessionGeneration) {
        finishWithError(call,
                        ApiError(ApiFailure::Cancelled, QStringLiteral("Appel interrompu.")));
        return;
    }

    // --- Échec de transport, sans code HTTP ---------------------------------
    if (httpStatus == 0) {
        ApiError error = networkError == QNetworkReply::OperationCanceledError
            ? ApiError(ApiFailure::Timeout,
                       QStringLiteral("Le serveur n'a pas répondu dans le délai imparti."))
            : ApiError(ApiFailure::Network, networkErrorText);
        if (shouldRetry(call->m_request, error, call->m_attempt)) {
            const auto delay = retryDelay(error, call->m_attempt);
            QTimer::singleShot(delay, call, [this, call] { startAttempt(call); });
            return;
        }
        finishWithError(call, error);
        return;
    }

    // --- Redirection : anomalie, jamais suivie ------------------------------
    if (httpStatus >= 300 && httpStatus < 400) {
        finishWithError(call,
                        ApiError(ApiFailure::InvalidResponse,
                                 QStringLiteral("Redirection HTTP inattendue (%1).").arg(httpStatus),
                                 httpStatus));
        return;
    }

    // --- Erreur applicative -------------------------------------------------
    if (httpStatus >= 400) {
        ApiError error = ApiError::fromHttpStatus(httpStatus, extractProblemDetail(body));
        error.setBody(body);
        if (response.headers.contains(QByteArrayLiteral("retry-after"))) {
            bool parsed = false;
            const int seconds = response.header(QByteArrayLiteral("retry-after")).toInt(&parsed);
            if (parsed) {
                error.setRetryAfterSeconds(seconds);
            }
        }
        if (httpStatus == 401) {
            // Le terminal doit précéder la purge réentrante provoquée par le signal.
            // Sinon abort() remplacerait le 401 par Cancelled pour cet appel même.
            call->m_finished = true;
            emit unauthorizedObserved();
            emit call->failed(error);
            releaseCall(call);
            call->deleteLater();
            return;
        } else if (httpStatus == 403) {
            call->m_finished = true;
            emit forbiddenObserved();
            emit call->failed(error);
            releaseCall(call);
            call->deleteLater();
            return;
        }
        if (shouldRetry(call->m_request, error, call->m_attempt)) {
            const auto delay = retryDelay(error, call->m_attempt);
            QTimer::singleShot(delay, call, [this, call] { startAttempt(call); });
            return;
        }
        finishWithError(call, error);
        return;
    }

    // --- Succès -------------------------------------------------------------
    if (!body.isEmpty() && call->m_request.accept.contains(QByteArrayLiteral("application/json"))) {
        QJsonParseError parseError{};
        response.json = QJsonDocument::fromJson(body, &parseError);
        if (parseError.error != QJsonParseError::NoError) {
            // Réponse hors contrat : rien n'est rendu partiellement.
            finishWithError(call,
                            ApiError(ApiFailure::InvalidResponse,
                                     QStringLiteral("Le serveur a renvoyé un corps JSON illisible."),
                                     httpStatus));
            return;
        }
    }
    finishWithResponse(call, response);
}

void ApiClient::finishWithError(ApiCall *call, const ApiError &error)
{
    if (!call || call->m_finished) {
        return;
    }
    call->m_finished = true;
    emit call->failed(error);
    releaseCall(call);
    call->deleteLater();
}

void ApiClient::finishWithResponse(ApiCall *call, const ApiResponse &response)
{
    if (!call || call->m_finished) {
        return;
    }
    if (call->m_sessionGeneration != m_sessionGeneration) {
        finishWithError(call, ApiError(ApiFailure::Cancelled, QStringLiteral("La session a changé.")));
        return;
    }
    call->m_finished = true;
    emit call->succeeded(response);
    releaseCall(call);
    call->deleteLater();
}

void ApiClient::releaseCall(ApiCall *call)
{
    m_inFlight.removeIf([call](const QPointer<ApiCall> &entry) {
        return entry.isNull() || entry.data() == call;
    });
    emit inFlightCountChanged();

    if (m_rotatingCall == call) {
        m_rotatingCall = nullptr;
        drainPending();
    }
}

void ApiClient::drainPending()
{
    if (m_invalidating) return;
    // Priorité au prochain appel rotatif : il renouvelle le jeton dont les mutations
    // retenues ont besoin.
    while (!m_pendingRotating.isEmpty()) {
        const QPointer<ApiCall> next = m_pendingRotating.dequeue();
        if (!next || next->m_finished || next->m_aborted) {
            continue;
        }
        m_rotatingCall = next;
        dispatch(next);
        return;
    }
    while (!m_pendingUnsafe.isEmpty()) {
        const QPointer<ApiCall> next = m_pendingUnsafe.dequeue();
        if (!next || next->m_finished || next->m_aborted) {
            continue;
        }
        dispatch(next);
    }
}

} // namespace acp
