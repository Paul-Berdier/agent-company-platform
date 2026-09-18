#include "storage/WindowsCredentialVault.h"

#ifdef Q_OS_WIN

// NOMINMAX et WIN32_LEAN_AND_MEAN évitent que les en-têtes Windows ne définissent des
// macros min/max qui casseraient qBound et std::min dans le reste de l'unité.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>
#include <wincred.h>

#include <cstring>

namespace acp {

namespace {

/*!
    Traduit un code d'erreur Windows en message français.

    Seuls les codes réellement documentés pour ces trois fonctions sont nommés ; tout
    autre code est rendu tel quel, en clair. On ne devine jamais une cause : afficher
    « erreur 1168 » est honnête, inventer « le coffre est verrouillé » ne l'est pas.
*/
QString describeCredentialError(DWORD code)
{
    switch (code) {
    case ERROR_NOT_FOUND:
        return QStringLiteral("aucune entrée de ce nom dans le gestionnaire d'identifiants");
    case ERROR_NO_SUCH_LOGON_SESSION:
        return QStringLiteral(
            "la session d'ouverture n'a pas de jeu d'identifiants associé (session réseau)");
    case ERROR_INVALID_PARAMETER:
        return QStringLiteral("paramètre refusé par le gestionnaire d'identifiants");
    case ERROR_INVALID_FLAGS:
        return QStringLiteral("indicateur refusé par le gestionnaire d'identifiants");
    case ERROR_BAD_USERNAME:
        return QStringLiteral("nom d'utilisateur refusé par le gestionnaire d'identifiants");
    default:
        return QStringLiteral("erreur Windows %1").arg(static_cast<quint32>(code));
    }
}

} // namespace

WindowsCredentialVault::WindowsCredentialVault(QString applicationName)
    : m_applicationName(std::move(applicationName))
{
    if (m_applicationName.isEmpty()) {
        m_applicationName = QStringLiteral("AgentCompanyPlatform");
    }
}

QString WindowsCredentialVault::backendName() const
{
    return QStringLiteral("Gestionnaire d'identifiants Windows");
}

QString WindowsCredentialVault::targetNameFor(const QString &key) const
{
    return m_applicationName + QLatin1Char(':') + key;
}

VaultResult WindowsCredentialVault::store(const QString &key, const QByteArray &secret)
{
    if (key.isEmpty()) {
        return VaultResult::failure(QStringLiteral("Clé de secret vide : écriture refusée."));
    }
    if (secret.isEmpty()) {
        return VaultResult::failure(
            QStringLiteral("Secret vide : écriture refusée, car une entrée vide serait "
                           "indiscernable d'un secret perdu."));
    }
    if (secret.size() > kMaxSecretBytes) {
        return VaultResult::failure(
            QStringLiteral("Secret trop volumineux : %1 octets pour un maximum de %2 accepté "
                           "par le gestionnaire d'identifiants Windows.")
                .arg(secret.size())
                .arg(kMaxSecretBytes));
    }

    const QString target = targetNameFor(key);
    // Les tampons doivent survivre à l'appel ; ils sont donc nommés et non temporaires.
    std::wstring targetBuffer = target.toStdWString();
    std::wstring userNameBuffer = m_applicationName.toStdWString();
    QByteArray payload = secret;

    CREDENTIALW credential;
    std::memset(&credential, 0, sizeof(credential));
    credential.Flags = 0;
    credential.Type = CRED_TYPE_GENERIC;
    credential.TargetName = targetBuffer.data();
    credential.Comment = nullptr;
    credential.CredentialBlobSize = static_cast<DWORD>(payload.size());
    credential.CredentialBlob = reinterpret_cast<LPBYTE>(payload.data());
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE;
    credential.AttributeCount = 0;
    credential.Attributes = nullptr;
    credential.TargetAlias = nullptr;
    // Ignoré pour CRED_TYPE_GENERIC, mais renseigné pour que l'entrée reste lisible dans
    // l'interface Windows de gestion des identifiants.
    credential.UserName = userNameBuffer.data();

    const BOOL written = ::CredWriteW(&credential, 0);
    const DWORD lastError = written ? ERROR_SUCCESS : ::GetLastError();
    CredentialVault::wipe(payload);

    if (!written) {
        m_status = VaultStatus::Failed;
        return VaultResult::failure(
            QStringLiteral("Le gestionnaire d'identifiants Windows a refusé l'écriture : %1.")
                .arg(describeCredentialError(lastError)));
    }
    m_status = VaultStatus::Available;
    return VaultResult::success();
}

VaultResult WindowsCredentialVault::load(const QString &key, QByteArray &secret)
{
    if (key.isEmpty()) {
        return VaultResult::failure(QStringLiteral("Clé de secret vide : lecture refusée."));
    }
    const std::wstring target = targetNameFor(key).toStdWString();

    PCREDENTIALW credential = nullptr;
    const BOOL read = ::CredReadW(target.c_str(), CRED_TYPE_GENERIC, 0, &credential);
    if (!read || credential == nullptr) {
        const DWORD lastError = ::GetLastError();
        if (lastError != ERROR_NOT_FOUND) {
            m_status = VaultStatus::Failed;
        }
        return VaultResult::failure(
            QStringLiteral("Lecture impossible : %1.").arg(describeCredentialError(lastError)));
    }

    secret = QByteArray(reinterpret_cast<const char *>(credential->CredentialBlob),
                        static_cast<qsizetype>(credential->CredentialBlobSize));
    // Le tampon rendu par CredReadW appartient au système : il est libéré par CredFree.
    ::CredFree(credential);
    m_status = VaultStatus::Available;
    return VaultResult::success();
}

VaultResult WindowsCredentialVault::remove(const QString &key)
{
    if (key.isEmpty()) {
        return VaultResult::failure(QStringLiteral("Clé de secret vide : suppression refusée."));
    }
    const std::wstring target = targetNameFor(key).toStdWString();
    const BOOL deleted = ::CredDeleteW(target.c_str(), CRED_TYPE_GENERIC, 0);
    if (deleted) {
        return VaultResult::success();
    }
    const DWORD lastError = ::GetLastError();
    if (lastError == ERROR_NOT_FOUND) {
        // L'absence n'est pas un échec : la cible « aucune trace » est atteinte.
        return VaultResult::success();
    }
    m_status = VaultStatus::Failed;
    return VaultResult::failure(
        QStringLiteral("Suppression impossible : %1.").arg(describeCredentialError(lastError)));
}

bool WindowsCredentialVault::contains(const QString &key)
{
    if (key.isEmpty()) {
        return false;
    }
    const std::wstring target = targetNameFor(key).toStdWString();
    PCREDENTIALW credential = nullptr;
    const BOOL read = ::CredReadW(target.c_str(), CRED_TYPE_GENERIC, 0, &credential);
    if (!read || credential == nullptr) {
        return false;
    }
    // Le contenu n'est jamais lu ici : seule la présence compte.
    ::CredFree(credential);
    return true;
}

} // namespace acp

#endif // Q_OS_WIN
