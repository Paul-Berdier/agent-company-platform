// Coffre de secrets du poste.
//
// Ce que ce fichier INTERDIT, et pourquoi :
//
//   - QSettings : écrit en clair dans la base de registre ou dans un fichier .ini ;
//   - un fichier JSON, YAML ou .env : clair, sauvegardé, synchronisé, indexé ;
//   - une propriété QML : lisible par la scène et par tout composant chargé ;
//   - une base non chiffrée : clair, et copiée par toute sauvegarde du poste ;
//   - un journal ou un rapport de plantage : c'est la fuite la plus fréquente ;
//   - Git : évident, et irrattrapable.
//
// Aucune de ces voies n'est empruntée, y compris en repli. Le repli (FallbackVault)
// REFUSE de stocker : il échoue proprement, en français, avec la raison. Un secret non
// mémorisé oblige à ressaisir un mot de passe ; un secret écrit en clair oblige à
// changer de mot de passe, et à ne pas savoir qui l'a lu.
//
// L'implémentation Windows s'appuie sur le gestionnaire d'identifiants du système, via
// CredWriteW / CredReadW / CredDeleteW (wincred.h, Advapi32.lib). Sources consultées le
// 18 septembre 2026, citées dans docs/native-desktop-architecture.md.

#pragma once

#include "app/QmlEnums.h"

#include <QByteArray>
#include <QString>

#include <memory>
#include <optional>

namespace acp {

/*! Résultat d'une opération de coffre. Jamais un booléen nu : la raison compte. */
struct VaultResult
{
    bool ok = false;
    QString reason; //!< Message français, destiné à l'interface. Sans valeur de secret.

    static VaultResult success() { return VaultResult{true, {}}; }
    static VaultResult failure(QString reason) { return VaultResult{false, std::move(reason)}; }
};

/*!
    Abstraction de stockage de secrets.

    Le secret voyage en QByteArray et non en QString : il est effacé explicitement après
    usage, et il ne rejoint pas le pool de chaînes partagées de Qt. Aucune méthode ne
    renvoie le secret par valeur de retour dans un chemin d'erreur : on ne veut pas d'un
    secret qui traîne dans un objet d'erreur ou dans une trace.
*/
class CredentialVault
{
public:
    virtual ~CredentialVault() = default;

    /*! Nom court, français, de l'implémentation, pour l'écran de diagnostics. */
    [[nodiscard]] virtual QString backendName() const = 0;

    /*! Vrai si ce coffre peut réellement stocker. Faux pour le repli. */
    [[nodiscard]] virtual bool canStore() const = 0;

    [[nodiscard]] virtual VaultStatus::State status() const = 0;

    /*! Stocke ou remplace un secret. */
    virtual VaultResult store(const QString &key, const QByteArray &secret) = 0;

    /*! Lit un secret. `secret` n'est écrit qu'en cas de succès. */
    virtual VaultResult load(const QString &key, QByteArray &secret) = 0;

    /*! Supprime un secret. L'absence n'est pas un échec : la cible est atteinte. */
    virtual VaultResult remove(const QString &key) = 0;

    /*! Vrai si une entrée existe. N'implique aucune lecture du contenu. */
    [[nodiscard]] virtual bool contains(const QString &key) = 0;

    /*!
        Écrase le contenu d'un tampon avant de le libérer.

        Ce n'est pas une garantie cryptographique — le système d'exploitation a pu
        recopier la page, et Qt a pu réallouer le tampon — mais c'est la précaution
        minimale, et son absence serait une négligence.
    */
    static void wipe(QByteArray &buffer);
};

/*!
    Repli universel : il REFUSE de stocker.

    Chaque opération d'écriture échoue avec une raison explicite. Aucune écriture nulle
    part, aucun repli silencieux vers un fichier. C'est le comportement voulu : la station
    demandera un mot de passe à chaque lancement plutôt que de le déposer en clair.
*/
class RefusingCredentialVault final : public CredentialVault
{
public:
    explicit RefusingCredentialVault(QString reason);

    [[nodiscard]] QString backendName() const override;
    [[nodiscard]] bool canStore() const override { return false; }
    [[nodiscard]] VaultStatus::State status() const override { return VaultStatus::Refusing; }

    VaultResult store(const QString &key, const QByteArray &secret) override;
    VaultResult load(const QString &key, QByteArray &secret) override;
    VaultResult remove(const QString &key) override;
    [[nodiscard]] bool contains(const QString &key) override;

private:
    QString m_reason;
};

/*!
    Fabrique le coffre adapté au système.

    Sur Windows : le gestionnaire d'identifiants. Ailleurs : le repli qui refuse, faute
    d'implémentation écrite et vérifiée. Aucun coffre « maison » n'est improvisé : un
    chiffrement inventé ici serait pire que l'absence de stockage.
*/
[[nodiscard]] std::unique_ptr<CredentialVault> makeCredentialVault(const QString &applicationName);

} // namespace acp
