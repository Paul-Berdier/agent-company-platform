#include "api/ApiError.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QJsonValue>
#include <QRegularExpression>
#include <QStringList>

namespace acp {

namespace {

//! Longueur maximale conservée d'un détail serveur, pour qu'un corps d'erreur volumineux
//! ne devienne pas un message illisible ni un journal démesuré.
constexpr int kMaxDetailLength = 1000;

QString clamp(QString text)
{
    text = text.simplified();
    if (text.size() > kMaxDetailLength) {
        text.truncate(kMaxDetailLength);
        text.append(QStringLiteral(" […]"));
    }
    return text;
}

QJsonObject objetJson(const QByteArray &body)
{
    if (body.isEmpty()) {
        return {};
    }
    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(body, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        return {};
    }
    return document.object();
}

bool estFournisseurInjoignable(const QString &detailBrut)
{
    // routes.py `/auth/native/refresh` et request_utils.unreachable_response :
    // « Auth provider '<nom>' unreachable ».
    static const QRegularExpression motif(
        QStringLiteral("^Auth provider .* unreachable$"));
    return motif.match(detailBrut.trimmed()).hasMatch();
}

} // namespace

ApiError::ApiError(ApiFailure::Kind kind, QString detail, int httpStatus)
    : m_kind(kind)
    , m_httpStatus(httpStatus)
    , m_detail(clamp(std::move(detail)))
{
}

ApiError ApiError::fromHttpStatus(int httpStatus, const QString &serverDetail)
{
    ApiFailure::Kind kind = ApiFailure::ServerError;
    switch (httpStatus) {
    case 401:
        kind = ApiFailure::Unauthorized;
        break;
    case 403:
        kind = ApiFailure::Forbidden;
        break;
    case 404:
        kind = ApiFailure::NotFound;
        break;
    case 409:
        kind = ApiFailure::Conflict;
        break;
    case 422:
        kind = ApiFailure::Unprocessable;
        break;
    case 429:
        kind = ApiFailure::RateLimited;
        break;
    case 503:
        kind = ApiFailure::ServiceUnavailable;
        break;
    default:
        if (httpStatus >= 500) {
            kind = ApiFailure::ServerError;
        } else if (httpStatus >= 400) {
            // 400, 405, 410, 413, 415… : familles sans traitement particulier côté client.
            // Elles restent des refus de contrat, pas des pannes.
            kind = ApiFailure::Unprocessable;
        } else {
            // Un code hors 4xx/5xx ne devrait jamais atteindre cette fonction ; le dire
            // plutôt que de le classer au hasard.
            kind = ApiFailure::InvalidResponse;
        }
        break;
    }
    return ApiError(kind, serverDetail, httpStatus);
}

ApiError ApiError::fromResponse(int httpStatus, const QByteArray &body)
{
    const QJsonObject objet = objetJson(body);
    ApiError error = fromHttpStatus(httpStatus, extractProblemDetail(body));
    error.m_body = body;

    const QJsonValue detail = objet.value(QStringLiteral("detail"));
    if (detail.isObject()) {
        // Greffon acp-poste : {"detail": {"code", "message", "refus"?}}.
        const QJsonObject contenu = detail.toObject();
        error.m_code = contenu.value(QStringLiteral("code")).toString();
        error.m_refusals = contenu.value(QStringLiteral("refus")).toArray();
    }
    const QJsonValue gateError = objet.value(QStringLiteral("error"));
    if (gateError.isString() && error.m_code.isEmpty()) {
        error.m_code = gateError.toString();
    }
    const QJsonValue reason = objet.value(QStringLiteral("reason"));
    if (httpStatus == 401 && reason.isString() && !reason.toString().isEmpty()) {
        error.m_gateReason = reason.toString();
    }
    if (httpStatus == 503 && detail.isString() && estFournisseurInjoignable(detail.toString())) {
        error.m_kind = ApiFailure::IdentityProviderUnavailable;
    }
    return error;
}

ApiError ApiError::refusal(QString reason)
{
    return ApiError(ApiFailure::ClientRefusal, std::move(reason), 0);
}

QString ApiError::title() const
{
    switch (m_kind) {
    case ApiFailure::None:
        return QStringLiteral("Succès");
    case ApiFailure::ClientRefusal:
        return QStringLiteral("Requête refusée par la station");
    case ApiFailure::Network:
        return QStringLiteral("Serveur injoignable");
    case ApiFailure::Timeout:
        return QStringLiteral("Délai dépassé");
    case ApiFailure::Cancelled:
        return QStringLiteral("Appel annulé");
    case ApiFailure::Unauthorized:
        return QStringLiteral("Session expirée ou révoquée");
    case ApiFailure::Forbidden:
        return QStringLiteral("Accès refusé");
    case ApiFailure::NotFound:
        return QStringLiteral("Introuvable ou hors de votre portée");
    case ApiFailure::Conflict:
        return QStringLiteral("État incompatible avec cette action");
    case ApiFailure::Unprocessable:
        return QStringLiteral("Demande refusée par le contrat de l'API");
    case ApiFailure::RateLimited:
        return QStringLiteral("Trop de demandes simultanées");
    case ApiFailure::ServerError:
        return QStringLiteral("Erreur du serveur");
    case ApiFailure::ServiceUnavailable:
        return QStringLiteral("Service indisponible");
    case ApiFailure::Incompatible:
        return QStringLiteral("Version incompatible");
    case ApiFailure::InvalidResponse:
        return QStringLiteral("Réponse inexploitable");
    case ApiFailure::IdentityProviderUnavailable:
        return QStringLiteral("Fournisseur d'identité injoignable");
    }
    // Aucune valeur d'énumération ne doit manquer ; si l'on arrive ici, le dire.
    return QStringLiteral("Erreur non classée");
}

QString ApiError::message() const
{
    if (m_detail.isEmpty()) {
        return title();
    }
    return QStringLiteral("%1 : %2").arg(title(), m_detail);
}

bool ApiError::isRetryable() const
{
    switch (m_kind) {
    case ApiFailure::Network:
    case ApiFailure::Timeout:
    case ApiFailure::RateLimited:
    case ApiFailure::ServerError:
    case ApiFailure::ServiceUnavailable:
    case ApiFailure::IdentityProviderUnavailable:
        return true;
    case ApiFailure::None:
    case ApiFailure::ClientRefusal:
    case ApiFailure::Cancelled:
    case ApiFailure::Unauthorized:
    case ApiFailure::Forbidden:
    case ApiFailure::NotFound:
    case ApiFailure::Conflict:
    case ApiFailure::Unprocessable:
    case ApiFailure::Incompatible:
    case ApiFailure::InvalidResponse:
        return false;
    }
    return false;
}

QString libelleErreurReseau(QNetworkReply::NetworkError code)
{
    QString libelle;
    switch (code) {
    case QNetworkReply::ConnectionRefusedError:
        libelle = QStringLiteral("connexion refusée : aucun service n'écoute à cette adresse");
        break;
    case QNetworkReply::RemoteHostClosedError:
        libelle = QStringLiteral("le serveur a fermé la connexion");
        break;
    case QNetworkReply::HostNotFoundError:
        libelle = QStringLiteral("hôte introuvable : vérifiez l'adresse du serveur");
        break;
    case QNetworkReply::TimeoutError:
        libelle = QStringLiteral("délai de connexion dépassé");
        break;
    case QNetworkReply::OperationCanceledError:
        libelle = QStringLiteral("opération interrompue avant la réponse");
        break;
    case QNetworkReply::SslHandshakeFailedError:
        libelle = QStringLiteral("connexion sécurisée (TLS) impossible : certificat refusé ou négociation échouée");
        break;
    case QNetworkReply::TemporaryNetworkFailureError:
    case QNetworkReply::NetworkSessionFailedError:
        libelle = QStringLiteral("réseau du poste indisponible");
        break;
    case QNetworkReply::TooManyRedirectsError:
    case QNetworkReply::InsecureRedirectError:
        libelle = QStringLiteral("redirection refusée");
        break;
    case QNetworkReply::ProxyConnectionRefusedError:
    case QNetworkReply::ProxyConnectionClosedError:
    case QNetworkReply::ProxyNotFoundError:
    case QNetworkReply::ProxyTimeoutError:
    case QNetworkReply::ProxyAuthenticationRequiredError:
    case QNetworkReply::UnknownProxyError:
        libelle = QStringLiteral("mandataire (proxy) injoignable ou refusant la connexion");
        break;
    case QNetworkReply::ProtocolUnknownError:
    case QNetworkReply::ProtocolInvalidOperationError:
    case QNetworkReply::ProtocolFailure:
        libelle = QStringLiteral("réponse du serveur illisible (protocole HTTP)");
        break;
    default:
        libelle = QStringLiteral("erreur réseau");
        break;
    }
    return QStringLiteral("%1 (erreur réseau %2)").arg(libelle).arg(static_cast<int>(code));
}

QString libelleErreurSocket(QAbstractSocket::SocketError code)
{
    QString libelle;
    switch (code) {
    case QAbstractSocket::ConnectionRefusedError:
        libelle = QStringLiteral("connexion refusée : aucun service n'écoute à cette adresse");
        break;
    case QAbstractSocket::RemoteHostClosedError:
        libelle = QStringLiteral("le serveur a fermé la connexion");
        break;
    case QAbstractSocket::HostNotFoundError:
        libelle = QStringLiteral("hôte introuvable : vérifiez l'adresse du serveur");
        break;
    case QAbstractSocket::SocketTimeoutError:
    case QAbstractSocket::ProxyConnectionTimeoutError:
        libelle = QStringLiteral("délai de connexion dépassé");
        break;
    case QAbstractSocket::SslHandshakeFailedError:
    case QAbstractSocket::SslInternalError:
    case QAbstractSocket::SslInvalidUserDataError:
        libelle = QStringLiteral("connexion sécurisée (TLS) impossible : certificat refusé ou négociation échouée");
        break;
    case QAbstractSocket::NetworkError:
    case QAbstractSocket::TemporaryError:
        libelle = QStringLiteral("réseau du poste indisponible");
        break;
    case QAbstractSocket::AddressInUseError:
    case QAbstractSocket::SocketAddressNotAvailableError:
        libelle = QStringLiteral("adresse locale indisponible");
        break;
    case QAbstractSocket::SocketAccessError:
        libelle = QStringLiteral("accès réseau refusé par le système");
        break;
    case QAbstractSocket::ProxyAuthenticationRequiredError:
    case QAbstractSocket::ProxyConnectionRefusedError:
    case QAbstractSocket::ProxyConnectionClosedError:
    case QAbstractSocket::ProxyNotFoundError:
    case QAbstractSocket::ProxyProtocolError:
        libelle = QStringLiteral("mandataire (proxy) injoignable ou refusant la connexion");
        break;
    default:
        libelle = QStringLiteral("erreur réseau");
        break;
    }
    return QStringLiteral("%1 (erreur de socket %2)").arg(libelle).arg(static_cast<int>(code));
}

QString traduireMessageHermes(const QString &message)
{
    const QString brut = message.trimmed();
    // Messages fixes de hermes_cli/dashboard_auth (routes.py, middleware.py), Hermes 0.21.5.
    static const QList<QPair<QString, QString>> fixes = {
        {QStringLiteral("Unauthorized"), QStringLiteral("non autorisé par la porte de Hermes")},
        {QStringLiteral("Refresh token expired or invalid; start a new sign-in."),
         QStringLiteral("jeton de rafraîchissement expiré ou invalide ; reconnectez-vous")},
        {QStringLiteral("Invalid or expired authorization code."),
         QStringLiteral("code de connexion invalide ou expiré")},
        {QStringLiteral("refresh_token required"),
         QStringLiteral("jeton de rafraîchissement manquant")},
        {QStringLiteral("no auth providers registered"),
         QStringLiteral("aucun fournisseur de connexion n'est enregistré sur ce serveur")},
        {QStringLiteral("Native login expired or unknown; restart sign-in."),
         QStringLiteral("connexion native expirée ou inconnue ; recommencez")},
        {QStringLiteral("too many pending native authorizations from this address"),
         QStringLiteral("trop de connexions en attente depuis cette adresse ; réessayez dans "
                        "10 minutes")},
        {QStringLiteral("native-flow authorization store at capacity"),
         QStringLiteral("trop de connexions en attente sur ce serveur ; réessayez plus tard")},
        {QStringLiteral("code_challenge_method must be S256"),
         QStringLiteral("méthode PKCE refusée : S256 est exigée")},
        {QStringLiteral("code_challenge required"), QStringLiteral("défi PKCE manquant")},
        {QStringLiteral("redirect_uri required"), QStringLiteral("adresse de retour manquante")},
        // Sauvegarde et fichiers gérés (hermes_cli/web_routers/ops.py, files.py, web_server_files.py).
        {QStringLiteral("Backup not found"), QStringLiteral("archive de sauvegarde introuvable sur le serveur")},
        {QStringLiteral("Invalid backup path"), QStringLiteral("chemin d'archive refusé par Hermes")},
        {QStringLiteral("Backup is outside the dashboard backup directory"),
         QStringLiteral("archive hors du répertoire des sauvegardes de Hermes")},
        {QStringLiteral("Path not found"), QStringLiteral("fichier introuvable sur le volume de Hermes")},
        {QStringLiteral("Path outside managed files root"),
         QStringLiteral("chemin hors de la racine des fichiers gérés par Hermes")},
        {QStringLiteral("Cannot delete the managed files root"),
         QStringLiteral("la racine des fichiers gérés ne peut pas être supprimée")},
        {QStringLiteral("Path must be absolute"), QStringLiteral("chemin absolu exigé")},
        {QStringLiteral("Path cannot contain '..'"), QStringLiteral("chemin contenant « .. » refusé")},
    };
    for (const auto &[anglais, francais] : fixes) {
        if (brut == anglais) {
            return francais;
        }
    }
    // Messages à préfixe fixe suivi d'un détail du système (rendu tel quel, comme donnée).
    static const QList<QPair<QString, QString>> prefixes = {
        {QStringLiteral("Could not delete path: "), QStringLiteral("suppression impossible sur le volume de Hermes : ")},
        {QStringLiteral("Failed to run backup: "), QStringLiteral("lancement de la sauvegarde impossible : ")},
        {QStringLiteral("Could not create backup directory: "),
         QStringLiteral("répertoire des sauvegardes impossible à créer : ")},
    };
    for (const auto &[anglais, francais] : prefixes) {
        if (brut.startsWith(anglais)) {
            return francais + brut.mid(anglais.size());
        }
    }
    static const QRegularExpression injoignable(
        QStringLiteral("^Auth provider '?(.*?)'? unreachable$"));
    const QRegularExpressionMatch correspondance = injoignable.match(brut);
    if (correspondance.hasMatch()) {
        return QStringLiteral("fournisseur d'identité « %1 » injoignable")
            .arg(correspondance.captured(1));
    }
    return message;
}

QString extractProblemDetail(const QByteArray &body)
{
    const QJsonObject objet = objetJson(body);
    if (objet.isEmpty()) {
        return {};
    }
    const QJsonValue detail = objet.value(QStringLiteral("detail"));
    if (detail.isString()) {
        return traduireMessageHermes(detail.toString());
    }
    if (detail.isObject()) {
        // Greffon acp-poste : le message est déjà en français.
        return detail.toObject().value(QStringLiteral("message")).toString();
    }
    if (detail.isArray()) {
        // Forme de validation FastAPI : on assemble les messages en conservant leur
        // emplacement, qui est la seule information réellement actionnable.
        QStringList parts;
        const QJsonArray items = detail.toArray();
        for (const QJsonValue &item : items) {
            if (!item.isObject()) {
                continue;
            }
            const QJsonObject entry = item.toObject();
            const QString text = entry.value(QStringLiteral("msg")).toString();
            if (text.isEmpty()) {
                continue;
            }
            QStringList location;
            const QJsonArray loc = entry.value(QStringLiteral("loc")).toArray();
            for (const QJsonValue &segment : loc) {
                if (segment.isString()) {
                    location.append(segment.toString());
                } else if (segment.isDouble()) {
                    location.append(QString::number(static_cast<int>(segment.toDouble())));
                }
            }
            parts.append(location.isEmpty()
                             ? text
                             : QStringLiteral("%1 (%2)").arg(text, location.join(QLatin1Char('.'))));
        }
        return parts.join(QStringLiteral(" ; "));
    }
    return {};
}

} // namespace acp
