#include "storage/JetonsCoffre.h"

#include <QCryptographicHash>

namespace acp {

namespace {

void ajouterChamp(QByteArray &sortie, const QByteArray &champ)
{
    const auto longueur = static_cast<quint16>(champ.size());
    sortie.append(static_cast<char>((longueur >> 8) & 0xFF));
    sortie.append(static_cast<char>(longueur & 0xFF));
    sortie.append(champ);
}

bool lireChamp(const QByteArray &brut, qsizetype &position, QByteArray &champ)
{
    if (position + 2 > brut.size()) {
        return false;
    }
    const auto haut = static_cast<quint8>(brut.at(position));
    const auto bas = static_cast<quint8>(brut.at(position + 1));
    const qsizetype longueur = (static_cast<qsizetype>(haut) << 8) | bas;
    position += 2;
    if (position + longueur > brut.size()) {
        return false;
    }
    champ = brut.mid(position, longueur);
    position += longueur;
    return true;
}

} // namespace

void EntreeJetons::effacer()
{
    serveur.clear();
    fournisseur.clear();
    utilisateur.clear();
    CredentialVault::wipe(jeton);
}

JetonsCoffre::JetonsCoffre(CredentialVault *coffre)
    : m_coffre(coffre)
{
}

QString JetonsCoffre::serveurCanonique(const QUrl &serveur)
{
    if (serveur.isEmpty() || serveur.host().isEmpty()) {
        return {};
    }
    QString canon = serveur.scheme().toLower() + QStringLiteral("://") + serveur.host().toLower();
    if (serveur.port() != -1) {
        canon += QLatin1Char(':') + QString::number(serveur.port());
    }
    QString chemin = serveur.path();
    while (chemin.endsWith(QLatin1Char('/'))) {
        chemin.chop(1);
    }
    return canon + chemin;
}

QString JetonsCoffre::cleDe(const QUrl &serveur)
{
    const QByteArray empreinte =
        QCryptographicHash::hash(serveurCanonique(serveur).toUtf8(), QCryptographicHash::Sha256);
    return QStringLiteral("hermes.rt.v1.") + QString::fromLatin1(empreinte.toHex());
}

QByteArray JetonsCoffre::encoder(const EntreeJetons &entree, QString *raison)
{
    QByteArray sortie;
    sortie.append(kMagique, 4);
    sortie.append(static_cast<char>(kVersion));
    const QByteArray champs[] = {entree.serveur.toUtf8(), entree.fournisseur.toUtf8(),
                                 entree.utilisateur.toUtf8(), entree.jeton};
    qsizetype total = sortie.size();
    for (const QByteArray &champ : champs) {
        total += 2 + champ.size();
    }
    if (total > kTailleMax || entree.jeton.isEmpty()) {
        if (raison) {
            *raison = entree.jeton.isEmpty()
                ? QStringLiteral("jeton de rafraîchissement vide : rien n'est mémorisé")
                : QStringLiteral("entrée de %1 octets pour un maximum de %2 : rien n'est mémorisé, "
                                 "et rien n'est tronqué")
                      .arg(total)
                      .arg(kTailleMax);
        }
        return {};
    }
    for (const QByteArray &champ : champs) {
        ajouterChamp(sortie, champ);
    }
    return sortie;
}

bool JetonsCoffre::decoder(const QByteArray &brut, EntreeJetons &sortie, QString *raison)
{
    const auto refuser = [raison](const QString &motif) {
        if (raison) {
            *raison = motif;
        }
        return false;
    };
    if (brut.size() > kTailleMax || brut.size() < 5 || !brut.startsWith(kMagique)) {
        return refuser(QStringLiteral("entrée du coffre illisible (format inconnu)"));
    }
    if (static_cast<quint8>(brut.at(4)) != kVersion) {
        return refuser(QStringLiteral("entrée du coffre d'une version inconnue"));
    }
    qsizetype position = 5;
    QByteArray champs[4];
    for (QByteArray &champ : champs) {
        if (!lireChamp(brut, position, champ)) {
            return refuser(QStringLiteral("entrée du coffre tronquée"));
        }
    }
    if (position != brut.size() || champs[3].isEmpty()) {
        return refuser(QStringLiteral("entrée du coffre incohérente"));
    }
    sortie.effacer();
    sortie.serveur = QString::fromUtf8(champs[0]);
    sortie.fournisseur = QString::fromUtf8(champs[1]);
    sortie.utilisateur = QString::fromUtf8(champs[2]);
    sortie.jeton = champs[3];
    CredentialVault::wipe(champs[3]);
    return true;
}

VaultResult JetonsCoffre::memoriser(const QUrl &serveur, const QString &fournisseur,
                                    const QString &utilisateur, const QByteArray &jeton)
{
    if (!m_coffre) {
        return VaultResult::failure(QStringLiteral("aucun coffre n'est disponible"));
    }
    EntreeJetons entree{serveurCanonique(serveur), fournisseur, utilisateur,
                        QByteArray(jeton.constData(), jeton.size())};
    QString raison;
    QByteArray brut = encoder(entree, &raison);
    entree.effacer();
    if (brut.isEmpty()) {
        return VaultResult::failure(raison);
    }
    const VaultResult resultat = m_coffre->store(cleDe(serveur), brut);
    CredentialVault::wipe(brut);
    return resultat;
}

VaultResult JetonsCoffre::relire(const QUrl &serveur, const QString &fournisseurAttendu,
                                 EntreeJetons &sortie, bool *introuvable)
{
    if (introuvable) {
        *introuvable = false;
    }
    if (!m_coffre) {
        return VaultResult::failure(QStringLiteral("aucun coffre n'est disponible"));
    }
    const QString cle = cleDe(serveur);
    if (!m_coffre->contains(cle)) {
        if (introuvable) {
            *introuvable = true;
        }
        return VaultResult::failure(QStringLiteral("aucune connexion mémorisée pour ce serveur"));
    }
    QByteArray brut;
    const VaultResult lecture = m_coffre->load(cle, brut);
    if (!lecture.ok) {
        return lecture;
    }
    QString raison;
    EntreeJetons entree;
    const bool lisible = decoder(brut, entree, &raison);
    CredentialVault::wipe(brut);
    if (lisible && entree.serveur != serveurCanonique(serveur)) {
        raison = QStringLiteral("entrée du coffre d'un autre serveur");
    } else if (lisible && entree.fournisseur != fournisseurAttendu) {
        raison = QStringLiteral("entrée du coffre d'un autre fournisseur");
    }
    if (!lisible || !raison.isEmpty()) {
        entree.effacer();
        const VaultResult effacement = m_coffre->remove(cle);
        return VaultResult::failure(
            QStringLiteral("%1 : elle a été %2").arg(
                raison, effacement.ok ? QStringLiteral("effacée")
                                      : QStringLiteral("gardée (effacement refusé : %1)")
                                            .arg(effacement.reason)));
    }
    sortie.effacer();
    sortie = entree;
    entree.effacer();
    return VaultResult::success();
}

VaultResult JetonsCoffre::oublier(const QUrl &serveur)
{
    if (!m_coffre) {
        return VaultResult::success();
    }
    return m_coffre->remove(cleDe(serveur));
}

bool JetonsCoffre::contient(const QUrl &serveur) const
{
    return m_coffre && m_coffre->contains(cleDe(serveur));
}

} // namespace acp
