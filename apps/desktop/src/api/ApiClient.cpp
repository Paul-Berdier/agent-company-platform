#include "api/ApiClient.h"

#include "api/IdempotencyKey.h"
#include "storage/CredentialVault.h"

#include <QHostAddress>
#include <QJsonParseError>
#include <QNetworkAccessManager>
#include <QNetworkCookie>
#include <QNetworkCookieJar>
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

/*!
    Pot de cookies qui refuse tout : la station ne détient aucun cookie. Les attributs
    de requête désactivent déjà le chargement et l'enregistrement ; ce pot est la seconde
    barrière, pour qu'un oubli ne réintroduise jamais une session par cookie.
*/
class PotSansCookie final : public QNetworkCookieJar
{
public:
    using QNetworkCookieJar::QNetworkCookieJar;

    QList<QNetworkCookie> cookiesForUrl(const QUrl &) const override { return {}; }
    bool setCookiesFromUrl(const QList<QNetworkCookie> &, const QUrl &) override { return false; }
};

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
{
    m_manager->setCookieJar(new PotSansCookie(m_manager));
    m_manager->setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
    // Les réponses sont détruites explicitement par le client, jamais par le gestionnaire.
    m_manager->setAutoDeleteReplies(false);
}

ApiClient::~ApiClient() = default;

// --- Configuration ------------------------------------------------------------

ApiError ApiClient::setBaseUrl(const QUrl &url)
{
    if (url.isEmpty()) {
        m_baseUrl = QUrl();
        invalidatePendingCalls();
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
    // Une session n'appartient jamais à deux serveurs : changer d'URL invalide tout.
    invalidatePendingCalls();
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

void ApiClient::setBearerProvider(BearerProvider provider)
{
    m_bearerProvider = std::move(provider);
}

void ApiClient::refreshFinished(bool succeeded)
{
    m_refreshPending = false;
    const QList<QPointer<ApiCall>> waiting = std::exchange(m_awaitingRefresh, {});
    for (const QPointer<ApiCall> &call : waiting) {
        if (!call || call->m_finished) {
            continue;
        }
        if (succeeded) {
            // Réémission UNIQUE, avec le jeton que la session vient de recevoir.
            startAttempt(call);
        } else {
            const ApiError expired(ApiFailure::Unauthorized,
                                   QStringLiteral("la session n'a pas pu être renouvelée ; "
                                                  "reconnectez-vous"),
                                   401);
            finishWithError(call, expired);
        }
    }
}

void ApiClient::invalidatePendingCalls()
{
    ++m_sessionGeneration;
    const bool alreadyInvalidating = m_invalidating;
    m_invalidating = true;
    m_awaitingRefresh.clear();
    m_refreshPending = false;
    const auto calls = m_inFlight;
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
    // Recul progressif borné, avec gigue : 500 ms, 1 s, 2 s, plafonné à 8 s.
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
    if (!request.publicEndpoint && (!m_bearerProvider || m_bearerProvider().isEmpty())) {
        // Hors session, une route protégée part en refus local, sans appel réseau.
        return ApiError::refusal(QStringLiteral("Aucune session : connectez-vous."));
    }
    if (!request.isSafeMethod() && !request.body.isNull()
        && request.body.toJson(QJsonDocument::Compact).size() > kMaxWriteBodyBytes) {
        return ApiError::refusal(QStringLiteral(
            "Corps de plus de 64 Kio : refusé par la station avant l'envoi."));
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
    call->m_attempt = 0;
    startAttempt(call);
    return call;
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
    // Aucun cookie, ni envoyé, ni enregistré.
    networkRequest.setAttribute(QNetworkRequest::CookieLoadControlAttribute,
                                QNetworkRequest::Manual);
    networkRequest.setAttribute(QNetworkRequest::CookieSaveControlAttribute,
                                QNetworkRequest::Manual);
    networkRequest.setRawHeader(QByteArrayLiteral("Accept"), request.accept);
    if (!m_userAgent.isEmpty()) {
        networkRequest.setRawHeader(QByteArrayLiteral("User-Agent"), m_userAgent);
    }
    const bool isWrite = !request.isSafeMethod();
    const bool bodyless = request.method == QByteArrayLiteral("DELETE") && request.body.isNull();
    if (isWrite && !bodyless) {
        // Toute écriture est JSON, même sans champ : la garde du greffon rend 415 sinon.
        networkRequest.setHeader(QNetworkRequest::ContentTypeHeader,
                                 QStringLiteral("application/json"));
    }
    call->m_bearerPresented = false;
    if (!request.publicEndpoint) {
        QByteArray token = m_bearerProvider ? m_bearerProvider() : QByteArray();
        if (token.isEmpty()) {
            finishWithError(call, ApiError::refusal(QStringLiteral("Aucune session : connectez-vous.")));
            return;
        }
        networkRequest.setRawHeader(QByteArrayLiteral("Authorization"),
                                    QByteArrayLiteral("Bearer ") + token);
        CredentialVault::wipe(token);
        call->m_bearerPresented = true;
    }
    if (!request.cookieDeconnexion.isEmpty()) {
        // Seul cookie jamais émis par la station : la révocation par POST /auth/logout.
        networkRequest.setRawHeader(QByteArrayLiteral("Cookie"),
                                    QByteArrayLiteral("hermes_session_rt=")
                                        + request.cookieDeconnexion);
        CredentialVault::wipe(call->m_request.cookieDeconnexion);
    }
    if (!request.idempotencyKey.isEmpty()) {
        networkRequest.setRawHeader(QByteArrayLiteral("Idempotency-Key"),
                                    request.idempotencyKey.toUtf8());
    }
    // Aucune redirection suivie : une redirection inattendue est une anomalie.
    networkRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                                QVariant::fromValue(QNetworkRequest::ManualRedirectPolicy));
    networkRequest.setTransferTimeout(request.timeout);

    QByteArray payload;
    if (!request.body.isNull()) {
        payload = request.body.toJson(QJsonDocument::Compact);
    } else if (isWrite && !bodyless) {
        payload = QByteArrayLiteral("{}");
    }

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
    const QString networkErrorText = reply->errorString();

    ApiResponse response;
    response.httpStatus = httpStatus;
    response.rawBody = body;
    for (const QByteArray &name : kRetainedHeaders) {
        if (reply->hasRawHeader(name)) {
            response.headers.insert(name, reply->rawHeader(name));
        }
    }
    reply->deleteLater();

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

    // --- Redirection : jamais suivie ----------------------------------------
    if (httpStatus >= 300 && httpStatus < 400 && call->m_request.redirectionAttendue) {
        // POST /auth/logout : le 302 vers /login est la réponse nominale de CET appel.
        finishWithResponse(call, response);
        return;
    }
    if (httpStatus >= 300 && httpStatus < 400) {
        finishWithError(call,
                        ApiError(ApiFailure::InvalidResponse,
                                 QStringLiteral("Redirection HTTP inattendue (%1).").arg(httpStatus),
                                 httpStatus));
        return;
    }

    // --- Erreur applicative -------------------------------------------------
    if (httpStatus >= 400) {
        ApiError error = ApiError::fromResponse(httpStatus, body);
        if (response.headers.contains(QByteArrayLiteral("retry-after"))) {
            bool parsed = false;
            const int seconds = response.header(QByteArrayLiteral("retry-after")).toInt(&parsed);
            if (parsed) {
                error.setRetryAfterSeconds(seconds);
            }
        }
        if (httpStatus == 401) {
            handleUnauthorized(call, error);
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

void ApiClient::handleUnauthorized(ApiCall *call, const ApiError &error)
{
    // Un 401 de la porte sur un appel porteur, jamais encore réémis : un rafraîchissement
    // puis UNE réémission. La porte répond avant tout gestionnaire (middleware.py) : même
    // une mutation n'a rien exécuté, la réémettre ne fait pas de double effet.
    if (call->m_bearerPresented && error.isGateRejection() && !call->m_replayedAfterRefresh
        && m_bearerProvider) {
        call->m_replayedAfterRefresh = true;
        m_awaitingRefresh.append(call);
        if (!m_refreshPending) {
            m_refreshPending = true;
            emit refreshRequested();
        }
        return;
    }
    const bool bearer = call->m_bearerPresented;
    finishWithError(call, error);
    if (bearer) {
        emit bearerRejected(error);
    }
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
}

} // namespace acp
