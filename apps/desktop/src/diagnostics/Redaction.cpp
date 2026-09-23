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

    // Paramètre de requête `token=` : c'est le jeton signé de téléchargement d'un
    // livrable, le seul secret que l'API fasse voyager dans une URL.
    static const QRegularExpression urlToken(
        QStringLiteral("([?&](?:token|signature|sig)=)[^&\\s\"']+"),
        QRegularExpression::CaseInsensitiveOption);
    result.replace(urlToken, QStringLiteral("\\1") + placeholder());

    // En-têtes porteurs de secret, sous la forme « Nom: valeur ».
    static const QRegularExpression headers(
        QStringLiteral("((?:X-CSRF-Token|X-ACP-Bootstrap-Token|X-Worker-Registration-Token|"
                       "Authorization|Cookie|Set-Cookie)\\s*:\\s*)[^\\r\\n]+"),
        QRegularExpression::CaseInsensitiveOption);
    result.replace(headers, QStringLiteral("\\1") + placeholder());

    // Cookie de session, où qu'il apparaisse.
    static const QRegularExpression sessionCookie(
        QStringLiteral("(acp_session\\s*=\\s*)[^;,\\s\"']+"),
        QRegularExpression::CaseInsensitiveOption);
    result.replace(sessionCookie, QStringLiteral("\\1") + placeholder());

    // Champs JSON sensibles.
    static const QRegularExpression jsonSecret(
        QStringLiteral("(\"(?:password|secret|csrf_token|token|bootstrap_token)\"\\s*:\\s*)"
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
