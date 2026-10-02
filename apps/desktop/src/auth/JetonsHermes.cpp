#include "auth/JetonsHermes.h"

#include "storage/CredentialVault.h"

#include <QJsonValue>
#include <QLocale>
#include <QTimeZone>

namespace acp {

void JetonsHermes::effacer()
{
    CredentialVault::wipe(acces);
    CredentialVault::wipe(rafraichissement);
    expireLe = QDateTime();
    fournisseur.clear();
    utilisateur.clear();
}

QDateTime JetonsHermes::dateHttp(const QByteArray &valeur)
{
    // « Sun, 06 Nov 1994 08:49:37 GMT » : noms anglais fixes, d'où la locale C.
    QDateTime date = QLocale::c().toDateTime(QString::fromLatin1(valeur.trimmed()),
                                             QStringLiteral("ddd, dd MMM yyyy HH:mm:ss 'GMT'"));
    if (!date.isValid()) {
        return {};
    }
    date.setTimeZone(QTimeZone::utc());
    return date;
}

QString JetonsHermes::lire(const QJsonObject &reponse, const QString &fournisseurAttendu,
                           const QDateTime &maintenant, JetonsHermes &sortie, const QDateTime &dateServeur)
{
    const QJsonValue type = reponse.value(QStringLiteral("token_type"));
    if (!type.isString() || type.toString().compare(QStringLiteral("Bearer"), Qt::CaseInsensitive) != 0) {
        return QStringLiteral("Réponse de jetons refusée : type de jeton inattendu.");
    }
    const QJsonValue fournisseur = reponse.value(QStringLiteral("provider"));
    if (!fournisseur.isString() || fournisseur.toString() != fournisseurAttendu) {
        return QStringLiteral("Réponse de jetons refusée : fournisseur « %1 » au lieu de « %2 ».")
            .arg(fournisseur.toString().left(64), fournisseurAttendu);
    }
    const QJsonValue acces = reponse.value(QStringLiteral("access_token"));
    if (!acces.isString() || acces.toString().isEmpty()) {
        return QStringLiteral("Réponse de jetons refusée : jeton d'accès absent.");
    }
    const QJsonValue expiration = reponse.value(QStringLiteral("expires_at"));
    if (!expiration.isDouble()) {
        return QStringLiteral("Réponse de jetons refusée : échéance absente.");
    }
    const QDateTime expireLe =
        QDateTime::fromSecsSinceEpoch(static_cast<qint64>(expiration.toDouble()), QTimeZone::utc());
    const QDateTime reference = dateServeur.isValid() ? dateServeur : maintenant;
    if (!expireLe.isValid() || expireLe <= reference) {
        return QStringLiteral("Réponse de jetons refusée : jeton déjà expiré.");
    }
    const QJsonValue utilisateur = reponse.value(QStringLiteral("user_id"));
    if (!utilisateur.isString() || utilisateur.toString().isEmpty()) {
        return QStringLiteral("Réponse de jetons refusée : identité absente.");
    }
    const QJsonValue rafraichissement = reponse.value(QStringLiteral("refresh_token"));
    if (!rafraichissement.isUndefined() && !rafraichissement.isNull() && !rafraichissement.isString()) {
        return QStringLiteral("Réponse de jetons refusée : jeton de rafraîchissement illisible.");
    }

    sortie.effacer();
    sortie.acces = acces.toString().toUtf8();
    sortie.rafraichissement = rafraichissement.toString().toUtf8();
    // Échéance ramenée à l'horloge du poste : même durée restante que pour Hermes.
    sortie.expireLe = dateServeur.isValid() ? maintenant.addSecs(dateServeur.secsTo(expireLe)) : expireLe;
    sortie.fournisseur = fournisseur.toString();
    sortie.utilisateur = utilisateur.toString();
    return {};
}

} // namespace acp
