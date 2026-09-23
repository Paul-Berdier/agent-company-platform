#include "auth/AuthManager.h"

#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"

#include <QJsonObject>
#include <QJsonValue>

namespace acp {

AuthManager::AuthManager(ApiClient *client, QObject *parent)
    : QObject(parent)
    , m_client(client)
{
    connect(m_client, &ApiClient::unauthorizedObserved, this, &AuthManager::handleUnauthorized);
    connect(m_client, &ApiClient::forbiddenObserved, this, &AuthManager::handleForbidden);
    connect(m_client, &ApiClient::sessionStateCleared, this, [this] {
        ++m_operation;
        m_user = {};
        m_expiresAt = {};
        m_recoveryAttempted = false;
        emit userChanged();
        setState(SessionStatus::Disconnected, QStringLiteral("Session locale effacée."));
    });
}

QString AuthManager::stateLabel() const
{
    switch (m_state) {
    case SessionStatus::Disconnected:
        return QStringLiteral("Déconnecté");
    case SessionStatus::Connecting:
        return QStringLiteral("Connexion en cours");
    case SessionStatus::Connected:
        return QStringLiteral("Connecté");
    case SessionStatus::Expired:
        return QStringLiteral("Session expirée");
    case SessionStatus::Revoked:
        return QStringLiteral("Session révoquée");
    case SessionStatus::Offline:
        return QStringLiteral("Hors ligne");
    }
    return QStringLiteral("Inconnu");
}

void AuthManager::setState(SessionStatus::State state, const QString &reason)
{
    const bool changed = (m_state != state) || (m_lastError != reason);
    const SessionStatus::State previous = m_state;
    m_state = state;
    m_lastError = reason;
    if (changed) {
        emit stateChanged();
    }
    if (state == SessionStatus::Connected && previous != SessionStatus::Connected) {
        emit sessionEstablished();
    }
    // Connecting n'est PAS une perte de session : c'est une reprise en cours. Émettre
    // sessionLost ici ferait fermer les flux à chaque relecture de session.
    if (previous == SessionStatus::Connected && state != SessionStatus::Connected
        && state != SessionStatus::Connecting) {
        emit sessionLost(reason.isEmpty() ? stateLabel() : reason);
    }
}

void AuthManager::refreshBootstrapStatus()
{
    ApiRequest request;
    request.method = QByteArrayLiteral("GET");
    request.path = QStringLiteral("/auth/status");

    ApiCall *call = m_client->send(request);
    const auto generation = m_client->sessionGeneration();
    connect(call, &ApiCall::succeeded, this, [this, generation](const ApiResponse &response) {
        if (generation != m_client->sessionGeneration()) return;
        const QJsonObject payload = response.json.object();
        const QJsonValue required = payload.value(QStringLiteral("bootstrap_required"));
        if (!required.isBool()) {
            // Réponse hors contrat : on ne devine pas, on le dit.
            setState(m_state, QStringLiteral("Réponse inexploitable de /auth/status."));
            return;
        }
        const bool value = required.toBool();
        if (value != m_bootstrapRequired) {
            m_bootstrapRequired = value;
            emit bootstrapRequiredChanged();
        }
    });
    connect(call, &ApiCall::failed, this, [this, generation](const ApiError &error) {
        if (generation != m_client->sessionGeneration()) return;
        // L'état d'amorçage reste INCONNU : on n'affirme surtout pas « pas besoin ».
        setState(m_state, error.message());
    });
}

QJsonObject AuthManager::loginRequestBody(const QString &login, const QString &password)
{
    QJsonObject body;
    body.insert(QStringLiteral("login"), login);
    body.insert(QStringLiteral("password"), password);
    return body;
}

void AuthManager::logIn(const QString &login, const QString &password)
{
    if (isBusy()) return;
    if (login.isEmpty() || password.isEmpty()) {
        setState(SessionStatus::Disconnected,
                 QStringLiteral("Identifiant et mot de passe sont tous deux obligatoires."));
        return;
    }
    forgetLocalSession(SessionStatus::Disconnected, QString());
    const auto operation = ++m_operation;
    const auto generation = m_client->sessionGeneration();
    setState(SessionStatus::Connecting);
    m_recoveryAttempted = false;

    ApiRequest request;
    request.method = QByteArrayLiteral("POST");
    request.path = QStringLiteral("/auth/login");
    request.body = QJsonDocument(loginRequestBody(login, password));
    // /auth/login est classée « publique » par l'audit : elle ouvre la session et
    // n'exige donc aucun jeton CSRF — il n'en existe aucun à ce stade.
    request.publicEndpoint = true;

    ApiCall *call = m_client->send(request);
    connect(call, &ApiCall::succeeded, this, [this, operation, generation](const ApiResponse &response) {
        if (operation != m_operation || generation != m_client->sessionGeneration()) return;
        applySessionPayload(response.json.object());
    });
    connect(call, &ApiCall::failed, this, [this, operation, generation](const ApiError &error) {
        if (operation != m_operation || generation != m_client->sessionGeneration()) return;
        const SessionStatus::State state = error.kind() == ApiFailure::Network
                || error.kind() == ApiFailure::Timeout
            ? SessionStatus::Offline
            : SessionStatus::Disconnected;
        setState(state, error.message());
    });
}

void AuthManager::logOut()
{
    if (m_state != SessionStatus::Connected) {
        forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Déconnecté."));
        return;
    }
    ApiRequest request;
    request.method = QByteArrayLiteral("POST");
    request.path = QStringLiteral("/auth/logout");

    // Les anciennes lectures, connexions et réessais sont abandonnés avant le dernier
    // envoi. Le POST part avec le cookie courant ; ensuite la copie locale disparaît
    // immédiatement, même si le réseau ne répond jamais.
    const auto operation = ++m_operation;
    m_client->invalidatePendingCalls();
    const auto generation = m_client->sessionGeneration();
    ApiCall *call = m_client->send(request);
    m_client->cookieJar()->clearAll();
    m_client->clearCsrfToken();
    m_user = {};
    m_expiresAt = {};
    emit userChanged();
    setState(SessionStatus::Disconnected,
             QStringLiteral("Déconnexion locale effectuée ; confirmation du serveur en cours."));
    connect(call, &ApiCall::succeeded, this, [this, operation, generation](const ApiResponse &) {
        if (operation != m_operation || generation != m_client->sessionGeneration()) return;
        forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Déconnecté."));
    });
    connect(call, &ApiCall::failed, this, [this, operation, generation](const ApiError &error) {
        if (operation != m_operation || generation != m_client->sessionGeneration()) return;
        // Le serveur n'a peut-être pas révoqué la session ; l'état local, lui, est purgé
        // de toute façon. On le dit plutôt que de laisser croire à une déconnexion nette.
        forgetLocalSession(
            SessionStatus::Disconnected,
            QStringLiteral("Déconnexion locale effectuée, mais le serveur n'a pas confirmé la "
                           "révocation (%1). La session peut rester ouverte côté serveur "
                           "jusqu'à son expiration.")
                .arg(error.message()));
    });
}

void AuthManager::resumeSession()
{
    if (isBusy()) return;
    if (!m_client->isConfigured()) {
        setState(SessionStatus::Disconnected,
                 QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }
    if (!m_client->cookieJar()->hasSessionCookie()) {
        // Sans cookie, l'appel serait un 401 certain. On ne fait pas semblant d'essayer.
        setState(SessionStatus::Disconnected,
                 QStringLiteral("Aucune session mémorisée sur ce poste."));
        return;
    }
    const auto operation = ++m_operation;
    const auto generation = m_client->sessionGeneration();
    setState(SessionStatus::Connecting);

    ApiRequest request;
    request.method = QByteArrayLiteral("GET");
    request.path = QStringLiteral("/auth/session");

    // Cet appel FAIT TOURNER le jeton CSRF côté serveur : il passe par le portail de
    // sérialisation, sans exception.
    ApiCall *call = m_client->sendCsrfRotating(request);
    connect(call, &ApiCall::succeeded, this, [this, operation, generation](const ApiResponse &response) {
        if (operation != m_operation || generation != m_client->sessionGeneration()) return;
        applySessionPayload(response.json.object());
    });
    connect(call, &ApiCall::failed, this, [this, operation, generation](const ApiError &error) {
        if (operation != m_operation || generation != m_client->sessionGeneration()) return;
        switch (error.kind()) {
        case ApiFailure::Unauthorized:
            forgetLocalSession(SessionStatus::Expired,
                               QStringLiteral("La session mémorisée n'est plus valide."));
            break;
        case ApiFailure::Forbidden:
            forgetLocalSession(SessionStatus::Revoked,
                               QStringLiteral("La session a été refusée par le serveur."));
            break;
        case ApiFailure::Network:
        case ApiFailure::Timeout:
            // Le serveur est injoignable : la session n'est PAS déclarée morte. On le dit.
            setState(SessionStatus::Offline, error.message());
            break;
        default:
            setState(SessionStatus::Disconnected, error.message());
            break;
        }
    });
}

void AuthManager::applySessionPayload(const QJsonObject &payload)
{
    const QJsonValue csrf = payload.value(QStringLiteral("csrf_token"));
    if (!csrf.isString() || csrf.toString().isEmpty()) {
        // Sans jeton CSRF, aucune écriture ne passera : c'est un échec, pas une réussite
        // partielle.
        forgetLocalSession(
            SessionStatus::Disconnected,
            QStringLiteral("Le serveur n'a pas fourni de jeton CSRF : aucune écriture ne "
                           "serait possible."));
        return;
    }
    m_client->setCsrfToken(csrf.toString());

    const QJsonObject user = payload.value(QStringLiteral("user")).toObject();
    m_user.id = user.value(QStringLiteral("id")).toString();
    m_user.displayName = user.value(QStringLiteral("display_name")).toString();
    if (m_user.displayName.isEmpty()) {
        m_user.displayName = user.value(QStringLiteral("login")).toString();
    }
    // Rôle de plateforme, publié sous « role » par AuthenticatedUser.
    m_user.platformRole = user.value(QStringLiteral("role")).toString();

    const QString expires = payload.value(QStringLiteral("expires_at")).toString();
    m_expiresAt = expires.isEmpty() ? QDateTime()
                                    : QDateTime::fromString(expires, Qt::ISODateWithMs).toUTC();

    emit userChanged();
    setState(SessionStatus::Connected);
}

void AuthManager::forgetLocalSession(SessionStatus::State newState, const QString &reason)
{
    m_client->clearSessionState();
    m_user = AuthenticatedUser{};
    m_expiresAt = QDateTime();
    emit userChanged();
    setState(newState, reason);
}

void AuthManager::handleUnauthorized()
{
    if (m_state == SessionStatus::Disconnected || m_state == SessionStatus::Expired
        || m_state == SessionStatus::Revoked) {
        return;
    }
    // Le serveur ne distingue pas « expirée » de « révoquée » sur un 401 ; on annonce le
    // fait certain — la session n'est plus acceptée — sans inventer sa cause.
    forgetLocalSession(SessionStatus::Expired,
                       QStringLiteral("Le serveur n'accepte plus cette session. "
                                      "Reconnectez-vous pour reprendre."));
}

void AuthManager::handleForbidden()
{
    if (m_state != SessionStatus::Connected) {
        return;
    }
    if (m_recoveryAttempted) {
        // Une seule reprise. Au-delà, le 403 est un vrai refus de droits et doit être
        // présenté comme tel par l'écran concerné, pas transformé en déconnexion.
        return;
    }
    m_recoveryAttempted = true;
    // Un 403 peut venir d'un jeton CSRF périmé autant que d'un droit manquant. La seule
    // façon honnête de trancher est de relire la session — ce qui renouvelle le jeton.
    resumeSession();
}

} // namespace acp
