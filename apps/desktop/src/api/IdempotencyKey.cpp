#include "api/IdempotencyKey.h"

#include <QRegularExpression>
#include <QUuid>

namespace acp {

bool isValidIdempotencyKey(const QString &key)
{
    if (key.isEmpty() || key.size() > kIdempotencyKeyMaxLength) {
        return false;
    }
    for (const QChar character : key) {
        const char16_t code = character.unicode();
        if (code < 33 || code > 126) {
            return false;
        }
    }
    return true;
}

QString makeIdempotencyKey(const QString &intent)
{
    // On ne garde de l'intention que ce qui est sûr dans un en-tête HTTP : lettres,
    // chiffres, tiret et point. Une intention vide ou illisible donne un préfixe neutre
    // plutôt qu'une clé invalide.
    static const QRegularExpression unsafe(QStringLiteral("[^A-Za-z0-9.-]"));
    QString prefix = intent;
    prefix.replace(unsafe, QStringLiteral("-"));
    prefix = prefix.left(32);
    while (prefix.endsWith(QLatin1Char('-'))) {
        prefix.chop(1);
    }
    if (prefix.isEmpty()) {
        prefix = QStringLiteral("acp");
    }

    const QString unique = QUuid::createUuid().toString(QUuid::WithoutBraces).remove(QLatin1Char('-'));
    QString key = prefix + QLatin1Char('.') + unique;
    if (key.size() > kIdempotencyKeyMaxLength) {
        key.truncate(kIdempotencyKeyMaxLength);
    }
    return key;
}

} // namespace acp
