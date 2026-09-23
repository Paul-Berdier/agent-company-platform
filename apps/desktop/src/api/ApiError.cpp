#include "api/ApiError.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QJsonValue>
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

QString extractProblemDetail(const QByteArray &body)
{
    if (body.isEmpty()) {
        return {};
    }
    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(body, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        return {};
    }
    const QJsonValue detail = document.object().value(QStringLiteral("detail"));
    if (detail.isString()) {
        return detail.toString();
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
