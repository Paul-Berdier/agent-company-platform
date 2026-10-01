#include "diagnostics/Redaction.h"

#include <QRegularExpression>

namespace acp {

namespace {

const QString &placeholder()
{
    static const QString value = QString::fromUtf8(kRedactionPlaceholder);
    return value;
}

} // namespace

QString redactSecrets(const QString &text)
{
    if (text.isEmpty()) {
        return text;
    }
    QString result = text;

    // Paramètres de requête porteurs de secret : jeton signé, code de connexion native,
    // état anti-falsification, ticket de WebSocket, vérificateur PKCE.
    static const QRegularExpression urlSecret(
        QStringLiteral("([?&](?:token|signature|sig|code|state|ticket|code_verifier)=)[^&\\s\"'#]+"),
        QRegularExpression::CaseInsensitiveOption);
    result.replace(urlSecret, QStringLiteral("\\1") + placeholder());

    // En-têtes porteurs de secret, sous la forme « Nom: valeur ».
    static const QRegularExpression headers(
        QStringLiteral("((?:X-CSRF-Token|X-ACP-Bootstrap-Token|X-Worker-Registration-Token|"
                       "Authorization|Cookie|Set-Cookie|Sec-WebSocket-Protocol)\\s*:\\s*)[^\\r\\n]+"),
        QRegularExpression::CaseInsensitiveOption);
    result.replace(headers, QStringLiteral("\\1") + placeholder());

    // Jeton porteur où qu'il apparaisse.
    static const QRegularExpression bearer(
        QStringLiteral("(Bearer\\s+)[A-Za-z0-9._~+/=-]+"), QRegularExpression::CaseInsensitiveOption);
    result.replace(bearer, QStringLiteral("\\1") + placeholder());

    // Cookies de session (ACP historique et Hermes, préfixes __Host- et __Secure- compris).
    static const QRegularExpression sessionCookie(
        QStringLiteral("((?:acp_session|hermes_session_(?:rt|at))\\s*=\\s*)[^;,\\s\"']+"),
        QRegularExpression::CaseInsensitiveOption);
    result.replace(sessionCookie, QStringLiteral("\\1") + placeholder());

    // Ticket de la passerelle passé en sous-protocole WebSocket.
    static const QRegularExpression ticketProtocol(
        QStringLiteral("(hermes-gateway-ticket\\.)[A-Za-z0-9._~-]+"));
    result.replace(ticketProtocol, QStringLiteral("\\1") + placeholder());

    // Jetons JWT (ID token d'Authelia) et jetons opaques d'Authelia, où qu'ils apparaissent.
    static const QRegularExpression jwt(
        QStringLiteral("eyJ[A-Za-z0-9_-]{4,}\\.[A-Za-z0-9_-]{4,}\\.[A-Za-z0-9_-]*"));
    result.replace(jwt, placeholder());
    static const QRegularExpression authelia(QStringLiteral("authelia_[a-z]{2}_[A-Za-z0-9._~-]+"));
    result.replace(authelia, placeholder());

    // Champs JSON sensibles.
    static const QRegularExpression jsonSecret(
        QStringLiteral("(\"(?:password|secret|csrf_token|token|bootstrap_token|access_token|"
                       "refresh_token|id_token|ticket|code|code_verifier|state)\"\\s*:\\s*)"
                       "\"[^\"]*\""),
        QRegularExpression::CaseInsensitiveOption);
    result.replace(jsonSecret, QStringLiteral("\\1\"") + placeholder() + QStringLiteral("\""));

    return result;
}

QString redactUrl(const QString &url)
{
    return redactSecrets(url);
}

} // namespace acp
