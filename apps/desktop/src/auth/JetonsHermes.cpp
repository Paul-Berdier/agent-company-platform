#include "auth/JetonsHermes.h"

#include "storage/CredentialVault.h"

#include <QJsonValue>
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

QString JetonsHermes::lire(const QJsonObject &reponse, const QString &fournisseurAttendu,
                           const QDateTime &maintenant, JetonsHermes &sortie)
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
    if (!expireLe.isValid() || expireLe <= maintenant) {
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
    sortie.expireLe = expireLe;
    sortie.fournisseur = fournisseur.toString();
    sortie.utilisateur = utilisateur.toString();
    return {};
}

} // namespace acp
