// Coffre Windows : gestionnaire d'identifiants du système.
//
// API employée, vérifiée le 18 septembre 2026 sur la documentation Microsoft :
//
//   - CredWriteW(PCREDENTIALW, DWORD)  — en-tête wincred.h, bibliothèque Advapi32.lib,
//     renvoie BOOL, l'échec se lit par GetLastError().
//     https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew
//   - CredReadW(LPCWSTR, DWORD, DWORD, PCREDENTIALW*) — le tampon rendu est libéré par
//     CredFree().
//     https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credreadw
//   - CredDeleteW(LPCWSTR, DWORD, DWORD).
//     https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-creddeletew
//   - Structure CREDENTIALW : champs Flags, Type, TargetName, Comment, LastWritten,
//     CredentialBlobSize, CredentialBlob, Persist, AttributeCount, Attributes,
//     TargetAlias, UserName.
//     https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw
//
// Contraintes reprises de cette documentation :
//   - Type = CRED_TYPE_GENERIC (valeur 1) : « stocké de façon sûre, sans autre
//     caractéristique » ; c'est exactement l'usage voulu ;
//   - Persist = CRED_PERSIST_LOCAL_MACHINE (valeur 2) : l'identifiant survit à la
//     fermeture de session, reste visible des seules sessions du MÊME utilisateur sur
//     CETTE machine, et n'est pas itinérant. CRED_PERSIST_ENTERPRISE (3) est écarté :
//     un secret de station n'a pas à suivre l'utilisateur d'un poste à l'autre ;
//   - CredentialBlobSize ne peut dépasser CRED_MAX_CREDENTIAL_BLOB_SIZE, soit 5 × 512 =
//     2560 octets. Un dépassement est refusé AVANT l'appel, avec un message explicite ;
//   - TargetName pour un CRED_TYPE_GENERIC est limité à
//     CRED_MAX_GENERIC_TARGET_NAME_LENGTH (32767) caractères et « devrait être préfixé
//     par le nom de l'entreprise » ; le préfixe retenu est le nom de l'application ;
//   - CredentialBlob « ne comprend pas de caractère nul final » : la taille est donc
//     donnée explicitement et les octets sont copiés tels quels, sans hypothèse
//     d'encodage.
//
// État de la preuve : compilé avec MSVC 14.44 et lié à Advapi32. AUCUN test ne l'exerce
// contre le Gestionnaire d'identifiants réel, et la station ne lui confie aujourd'hui
// aucun secret (la session n'est pas persistée) : son comportement à l'exécution n'est
// pas prouvé.

#pragma once

#include "storage/CredentialVault.h"

#include <QString>

namespace acp {

class WindowsCredentialVault final : public CredentialVault
{
public:
    explicit WindowsCredentialVault(QString applicationName);

    [[nodiscard]] QString backendName() const override;
    [[nodiscard]] bool canStore() const override { return true; }
    [[nodiscard]] VaultStatus::State status() const override { return m_status; }

    VaultResult store(const QString &key, const QByteArray &secret) override;
    VaultResult load(const QString &key, QByteArray &secret) override;
    VaultResult remove(const QString &key) override;
    [[nodiscard]] bool contains(const QString &key) override;

    //! Taille maximale d'un secret, imposée par CRED_MAX_CREDENTIAL_BLOB_SIZE.
    static constexpr int kMaxSecretBytes = 5 * 512;

    /*! Nom d'entrée complet : « <application>:<clé> ». Exposé pour les tests. */
    [[nodiscard]] QString targetNameFor(const QString &key) const;

private:
    QString m_applicationName;
    VaultStatus::State m_status = VaultStatus::Available;
};

} // namespace acp
