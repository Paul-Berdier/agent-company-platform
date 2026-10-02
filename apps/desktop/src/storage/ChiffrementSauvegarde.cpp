#include "storage/ChiffrementSauvegarde.h"

#include "storage/CredentialVault.h"

#include <QIODevice>
#include <QRandomGenerator>
#include <QtEndian>

#include <algorithm>

#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <dpapi.h>
#endif

namespace acp {

namespace {

constexpr char kMagique[] = "ACPB1";
constexpr char kVersion = 0x01;
constexpr qsizetype kTailleIdentifiant = 16;
//! Un bloc DPAPI d'un morceau de 1 Mio fait un peu plus de 1 Mio : au-delà de 2 Mio, refus.
constexpr quint32 kBlocMaximal = 2 * 1024 * 1024;

#ifdef Q_OS_WIN
class ProtecteurDpapi final : public ProtecteurDonnees
{
public:
    bool disponible() const override { return true; }

    std::optional<QByteArray> proteger(const QByteArray &clair, const QByteArray &entropie) const override
    {
        return appliquer(clair, entropie, true);
    }

    std::optional<QByteArray> deproteger(const QByteArray &bloc, const QByteArray &entropie) const override
    {
        return appliquer(bloc, entropie, false);
    }

private:
    static std::optional<QByteArray> appliquer(const QByteArray &entree, const QByteArray &entropie, bool proteger)
    {
        DATA_BLOB donnees{static_cast<DWORD>(entree.size()),
                          reinterpret_cast<BYTE *>(const_cast<char *>(entree.constData()))};
        DATA_BLOB sel{static_cast<DWORD>(entropie.size()),
                      reinterpret_cast<BYTE *>(const_cast<char *>(entropie.constData()))};
        DATA_BLOB resultat{0, nullptr};
        const BOOL ok = proteger
            ? CryptProtectData(&donnees, nullptr, &sel, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &resultat)
            : CryptUnprotectData(&donnees, nullptr, &sel, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &resultat);
        if (!ok || !resultat.pbData) {
            return std::nullopt;
        }
        QByteArray sortie(reinterpret_cast<const char *>(resultat.pbData), static_cast<qsizetype>(resultat.cbData));
        // Le clair rendu par DPAPI est effacé avant libération.
        SecureZeroMemory(resultat.pbData, resultat.cbData);
        LocalFree(resultat.pbData);
        return sortie;
    }
};
#endif

#ifndef Q_OS_WIN
class ProtecteurIndisponible final : public ProtecteurDonnees
{
public:
    bool disponible() const override { return false; }
    std::optional<QByteArray> proteger(const QByteArray &, const QByteArray &) const override { return std::nullopt; }
    std::optional<QByteArray> deproteger(const QByteArray &, const QByteArray &) const override { return std::nullopt; }
};
#endif

QByteArray enTete(const QByteArray &identifiant)
{
    QByteArray octets(kMagique, 5);
    octets.append(kVersion);
    octets.append(identifiant);
    return octets;
}

} // namespace

std::unique_ptr<ProtecteurDonnees> makeProtecteurUtilisateur()
{
#ifdef Q_OS_WIN
    return std::make_unique<ProtecteurDpapi>();
#else
    return std::make_unique<ProtecteurIndisponible>();
#endif
}

QByteArray entropieMorceau(const QByteArray &identifiant, quint64 rang, bool final)
{
    QByteArray entropie(kMagique, 5);
    entropie.append(identifiant);
    char rangGrosBoutiste[8];
    qToBigEndian(rang, rangGrosBoutiste);
    entropie.append(rangGrosBoutiste, 8);
    entropie.append(final ? '\x01' : '\x00');
    return entropie;
}

// --- Chiffrement ------------------------------------------------------------------------------

ChiffreurSauvegarde::ChiffreurSauvegarde(const ProtecteurDonnees &protecteur, QIODevice *sortie)
    : m_protecteur(protecteur)
    , m_sortie(sortie)
{
}

ChiffreurSauvegarde::~ChiffreurSauvegarde()
{
    CredentialVault::wipe(m_tampon);
}

bool ChiffreurSauvegarde::ecrire(const QByteArray &octets, QString *erreur)
{
    if (!m_sortie || m_sortie->write(octets) != octets.size()) {
        *erreur = QStringLiteral("Écriture du fichier de sauvegarde impossible : %1")
                      .arg(m_sortie ? m_sortie->errorString() : QStringLiteral("aucune sortie"));
        return false;
    }
    m_hachageChiffre.addData(octets);
    m_octetsEcrits += octets.size();
    return true;
}

bool ChiffreurSauvegarde::commencer(QString *erreur)
{
    if (m_commence) {
        return true;
    }
    if (!m_protecteur.disponible()) {
        *erreur = QStringLiteral("Le chiffrement DPAPI n'est disponible que sous Windows : la sauvegarde n'est pas écrite.");
        return false;
    }
    m_identifiant.resize(kTailleIdentifiant);
    QRandomGenerator::system()->fillRange(reinterpret_cast<quint32 *>(m_identifiant.data()),
                                          kTailleIdentifiant / static_cast<qsizetype>(sizeof(quint32)));
    m_commence = true;
    return ecrire(enTete(m_identifiant), erreur);
}

bool ChiffreurSauvegarde::emettre(bool final, QString *erreur)
{
    const qsizetype taille = std::min(m_tampon.size(), kTailleMorceau);
    QByteArray morceau = m_tampon.left(taille);
    const std::optional<QByteArray> bloc = m_protecteur.proteger(morceau, entropieMorceau(m_identifiant, m_rang, final));
    CredentialVault::wipe(morceau);
    if (!bloc) {
        *erreur = QStringLiteral("Chiffrement DPAPI refusé par Windows (morceau %1).").arg(m_rang + 1);
        return false;
    }
    // Le clair consommé est effacé du tampon avant d'être retiré.
    std::fill(m_tampon.begin(), m_tampon.begin() + taille, '\0');
    m_tampon.remove(0, taille);
    QByteArray cadre(1, final ? '\x01' : '\x00');
    char longueur[4];
    qToBigEndian(static_cast<quint32>(bloc->size()), longueur);
    cadre.append(longueur, 4);
    cadre.append(*bloc);
    ++m_rang;
    return ecrire(cadre, erreur);
}

bool ChiffreurSauvegarde::ajouter(QByteArrayView donnees, QString *erreur)
{
    if (!m_commence || m_termine) {
        *erreur = QStringLiteral("Chiffreur de sauvegarde non prêt.");
        return false;
    }
    m_tampon.append(donnees.data(), donnees.size());
    m_hachageClair.addData(donnees);
    m_octetsClairs += donnees.size();
    // Un morceau intermédiaire part seulement s'il reste des octets derrière lui : le dernier
    // morceau, même plein, porte le drapeau final.
    while (m_tampon.size() > kTailleMorceau) {
        if (!emettre(false, erreur)) {
            return false;
        }
    }
    return true;
}

bool ChiffreurSauvegarde::terminer(QString *erreur)
{
    if (!m_commence || m_termine) {
        *erreur = QStringLiteral("Chiffreur de sauvegarde non prêt.");
        return false;
    }
    m_termine = true;
    return emettre(true, erreur);
}

QByteArray ChiffreurSauvegarde::empreinteChiffree() const
{
    return m_hachageChiffre.result().toHex();
}

QByteArray ChiffreurSauvegarde::empreinteClaire() const
{
    return m_hachageClair.result().toHex();
}

// --- Déchiffrement ----------------------------------------------------------------------------

bool dechiffrerSauvegarde(const ProtecteurDonnees &protecteur, QIODevice *entree, QIODevice *sortie, QString *erreur,
                          QByteArray *empreinteClaire)
{
    if (!protecteur.disponible()) {
        *erreur = QStringLiteral("Le déchiffrement DPAPI n'est disponible que sous Windows.");
        return false;
    }
    const QByteArray tete = entree->read(ChiffreurSauvegarde::kTailleEnTete);
    if (tete.size() != ChiffreurSauvegarde::kTailleEnTete || !tete.startsWith(QByteArray(kMagique, 5))) {
        *erreur = QStringLiteral("Ce fichier n'est pas une sauvegarde chiffrée par la station (format ACPB1 attendu).");
        return false;
    }
    if (tete.at(5) != kVersion) {
        *erreur = QStringLiteral("Version de sauvegarde inconnue : %1.").arg(static_cast<int>(static_cast<uchar>(tete.at(5))));
        return false;
    }
    const QByteArray identifiant = tete.mid(6, kTailleIdentifiant);
    QCryptographicHash hachage(QCryptographicHash::Sha256);
    quint64 rang = 0;
    bool fin = false;
    while (!fin) {
        const QByteArray cadre = entree->read(5);
        if (cadre.isEmpty()) {
            *erreur = QStringLiteral("Sauvegarde tronquée : le morceau final manque (%1 morceau(x) lu(s)).").arg(rang);
            return false;
        }
        if (cadre.size() != 5 || (cadre.at(0) != '\x00' && cadre.at(0) != '\x01')) {
            *erreur = QStringLiteral("Sauvegarde altérée : en-tête du morceau %1 illisible.").arg(rang + 1);
            return false;
        }
        const bool final = cadre.at(0) == '\x01';
        const quint32 longueur = qFromBigEndian<quint32>(cadre.constData() + 1);
        if (longueur == 0 || longueur > kBlocMaximal) {
            *erreur = QStringLiteral("Sauvegarde altérée : longueur du morceau %1 invalide.").arg(rang + 1);
            return false;
        }
        const QByteArray bloc = entree->read(longueur);
        if (bloc.size() != static_cast<qsizetype>(longueur)) {
            *erreur = QStringLiteral("Sauvegarde tronquée au morceau %1.").arg(rang + 1);
            return false;
        }
        std::optional<QByteArray> clair = protecteur.deproteger(bloc, entropieMorceau(identifiant, rang, final));
        if (!clair) {
            *erreur = QStringLiteral("Sauvegarde altérée, déplacée ou chiffrée par un autre profil Windows : le morceau %1 "
                                     "ne se déchiffre pas.")
                          .arg(rang + 1);
            return false;
        }
        hachage.addData(*clair);
        const bool ecrit = sortie->write(*clair) == clair->size();
        CredentialVault::wipe(*clair);
        if (!ecrit) {
            *erreur = QStringLiteral("Écriture de l'archive déchiffrée impossible : %1").arg(sortie->errorString());
            return false;
        }
        ++rang;
        fin = final;
    }
    if (!entree->atEnd() && !entree->read(1).isEmpty()) {
        *erreur = QStringLiteral("Sauvegarde altérée : des octets suivent le morceau final.");
        return false;
    }
    if (empreinteClaire) {
        *empreinteClaire = hachage.result().toHex();
    }
    return true;
}

} // namespace acp
