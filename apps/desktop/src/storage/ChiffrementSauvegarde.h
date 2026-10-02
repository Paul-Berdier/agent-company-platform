// Chiffrement au fil de l'eau d'une sauvegarde de Hermes (cahier P8 § 7.9, décision D8-7).
//
// L'archive de Hermes contient `.env` et `auth.json` (jetons du fournisseur) : elle ne touche
// JAMAIS le disque du PC en clair. Elle est découpée en morceaux de 1 Mio, chacun protégé par
// DPAPI (CryptProtectData, utilisateur Windows courant), et écrite au format ACPB1 :
//
//   en-tête   « ACPB1 » (5 octets) · version 0x01 · identifiant d'export (16 octets aléatoires)
//   morceau   drapeau (0x00 intermédiaire, 0x01 final) · longueur du bloc (4 octets, gros-boutiste)
//             · bloc DPAPI
//
// L'entropie de chaque bloc lie l'identifiant d'export, le RANG du morceau et le drapeau final :
// un morceau déplacé, retiré, rejoué d'une autre sauvegarde ou dont le drapeau est retourné ne
// se déchiffre pas. Le dernier morceau porte toujours le drapeau final (éventuellement vide) :
// un fichier sans lui est tronqué, et des octets après lui sont refusés.
//
// Limite dite : DPAPI lie la sauvegarde au profil Windows qui l'a faite ; elle est perdue avec
// lui. La sauvegarde de volume de Railway reste la sauvegarde principale.

#pragma once

#include <QByteArray>
#include <QByteArrayView>
#include <QCryptographicHash>
#include <QString>

#include <memory>
#include <optional>

class QIODevice;

namespace acp {

/*! Protection de données liée à l'utilisateur courant (DPAPI sous Windows). */
class ProtecteurDonnees
{
public:
    virtual ~ProtecteurDonnees() = default;
    [[nodiscard]] virtual bool disponible() const = 0;
    [[nodiscard]] virtual std::optional<QByteArray> proteger(const QByteArray &clair, const QByteArray &entropie) const = 0;
    [[nodiscard]] virtual std::optional<QByteArray> deproteger(const QByteArray &bloc, const QByteArray &entropie) const = 0;
};

/*! DPAPI de l'utilisateur courant sous Windows ; ailleurs, un protecteur qui refuse tout. */
[[nodiscard]] std::unique_ptr<ProtecteurDonnees> makeProtecteurUtilisateur();

/*! Entropie d'un morceau : identifiant d'export, rang (8 octets gros-boutistes), drapeau final. */
[[nodiscard]] QByteArray entropieMorceau(const QByteArray &identifiant, quint64 rang, bool final);

class ChiffreurSauvegarde
{
public:
    static constexpr qsizetype kTailleMorceau = 1024 * 1024;
    static constexpr qsizetype kTailleEnTete = 22;

    ChiffreurSauvegarde(const ProtecteurDonnees &protecteur, QIODevice *sortie);
    ~ChiffreurSauvegarde();

    /*! Écrit l'en-tête. */
    bool commencer(QString *erreur);
    /*! Ajoute des octets en clair ; un morceau part dès que 1 Mio est réuni. */
    bool ajouter(QByteArrayView donnees, QString *erreur);
    /*! Émet le morceau final (le reste, éventuellement vide). */
    bool terminer(QString *erreur);

    [[nodiscard]] qint64 octetsClairs() const { return m_octetsClairs; }
    [[nodiscard]] qint64 octetsEcrits() const { return m_octetsEcrits; }
    /*! SHA-256 (hexadécimal) du fichier chiffré écrit, après terminer(). */
    [[nodiscard]] QByteArray empreinteChiffree() const;
    /*! SHA-256 (hexadécimal) de l'archive en clair, après terminer(). */
    [[nodiscard]] QByteArray empreinteClaire() const;

private:
    bool ecrire(const QByteArray &octets, QString *erreur);
    bool emettre(bool final, QString *erreur);

    const ProtecteurDonnees &m_protecteur;
    QIODevice *m_sortie = nullptr;
    QByteArray m_identifiant;
    QByteArray m_tampon;
    quint64 m_rang = 0;
    qint64 m_octetsClairs = 0;
    qint64 m_octetsEcrits = 0;
    bool m_commence = false;
    bool m_termine = false;
    QCryptographicHash m_hachageChiffre{QCryptographicHash::Sha256};
    QCryptographicHash m_hachageClair{QCryptographicHash::Sha256};
};

/*!
    Déchiffre un fichier ACPB1 vers `sortie`. Refuse (faux, `erreur` remplie, en français) un
    en-tête inconnu, un bloc altéré, déplacé ou d'une autre sauvegarde, un fichier tronqué ou
    suivi d'octets en trop. `empreinteClaire` reçoit le SHA-256 hexadécimal du clair.
*/
bool dechiffrerSauvegarde(const ProtecteurDonnees &protecteur, QIODevice *entree, QIODevice *sortie, QString *erreur,
                          QByteArray *empreinteClaire = nullptr);

} // namespace acp
