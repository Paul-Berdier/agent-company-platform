// Entrée du coffre Windows qui mémorise le jeton de rafraîchissement de Hermes.
//
// Seul secret durable de la station, écrit SEULEMENT si le propriétaire a coché
// « Mémoriser la connexion sur ce poste ». Nom de l'entrée :
// `AgentCompanyPlatform:hermes.rt.v1.<sha256 hexadécimal du serveur canonique>` (le préfixe
// est posé par le coffre). Format binaire `ACPH`, version 1 :
//
//   « ACPH » | version (1 octet) | 4 champs [longueur sur 2 octets gros-boutiste][octets] :
//   serveur canonique, fournisseur, user_id, jeton de rafraîchissement.
//
// Le tout est borné à 2 560 octets (limite du Gestionnaire d'identification Windows pour
// une entrée générique) : au-delà, refus explicite, jamais de troncature. À la relecture,
// le serveur doit être identique à l'adresse configurée et le fournisseur valoir
// `self-hosted` ; une entrée corrompue ou étrangère est ignorée ET effacée.

#pragma once

#include "storage/CredentialVault.h"

#include <QByteArray>
#include <QString>
#include <QUrl>

namespace acp {

struct EntreeJetons
{
    QString serveur;
    QString fournisseur;
    QString utilisateur;
    QByteArray jeton;

    void effacer();
};

class JetonsCoffre
{
public:
    static constexpr char kMagique[] = "ACPH";
    static constexpr quint8 kVersion = 1;
    static constexpr qsizetype kTailleMax = 2560;

    explicit JetonsCoffre(CredentialVault *coffre);

    /*! `schéma://hôte[:port][préfixe]` en minuscules, sans barre oblique finale. */
    [[nodiscard]] static QString serveurCanonique(const QUrl &serveur);

    /*! `hermes.rt.v1.<sha256 hexadécimal du serveur canonique>`. */
    [[nodiscard]] static QString cleDe(const QUrl &serveur);

    /*! Encode une entrée ; tableau vide et raison si elle dépasse 2 560 octets. */
    [[nodiscard]] static QByteArray encoder(const EntreeJetons &entree, QString *raison = nullptr);

    /*! Décode une entrée ; faux et raison si le format est invalide. */
    [[nodiscard]] static bool decoder(const QByteArray &brut, EntreeJetons &sortie,
                                      QString *raison = nullptr);

    /*! Écrit (remplace) l'entrée du serveur, en un seul appel au coffre. */
    VaultResult memoriser(const QUrl &serveur, const QString &fournisseur,
                          const QString &utilisateur, const QByteArray &jeton);

    /*!
        Relit l'entrée du serveur. Une entrée illisible, d'un autre serveur ou d'un autre
        fournisseur est effacée, et l'échec le dit. `introuvable` vaut vrai si aucune
        entrée n'existe (ce n'est alors pas une anomalie).
    */
    VaultResult relire(const QUrl &serveur, const QString &fournisseurAttendu,
                       EntreeJetons &sortie, bool *introuvable = nullptr);

    /*! Efface l'entrée du serveur. L'absence n'est pas un échec. */
    VaultResult oublier(const QUrl &serveur);

    /*! Vrai si une entrée existe, sans la lire. */
    [[nodiscard]] bool contient(const QUrl &serveur) const;

    [[nodiscard]] CredentialVault *coffre() const { return m_coffre; }

private:
    CredentialVault *m_coffre = nullptr;
};

} // namespace acp
