#include "storage/CredentialVault.h"

#ifdef Q_OS_WIN
#include "storage/WindowsCredentialVault.h"
#endif

#include <cstring>

namespace acp {

void CredentialVault::wipe(QByteArray &buffer)
{
    if (buffer.isEmpty()) {
        return;
    }
    // detach() garantit que l'on écrase bien CE tampon et non une copie partagée.
    buffer.detach();
    std::memset(buffer.data(), 0, static_cast<size_t>(buffer.size()));
    buffer.clear();
}

RefusingCredentialVault::RefusingCredentialVault(QString reason)
    : m_reason(std::move(reason))
{
}

QString RefusingCredentialVault::backendName() const
{
    return QStringLiteral("Aucun coffre système (stockage refusé)");
}

VaultResult RefusingCredentialVault::store(const QString &key, const QByteArray &secret)
{
    Q_UNUSED(key)
    Q_UNUSED(secret)
    return VaultResult::failure(
        QStringLiteral("Mémorisation refusée : %1. Le secret n'a été écrit nulle part ; il "
                       "devra être saisi de nouveau au prochain lancement.")
            .arg(m_reason));
}

VaultResult RefusingCredentialVault::load(const QString &key, QByteArray &secret)
{
    Q_UNUSED(key)
    Q_UNUSED(secret)
    return VaultResult::failure(
        QStringLiteral("Aucun secret mémorisé : %1.").arg(m_reason));
}

VaultResult RefusingCredentialVault::remove(const QString &key)
{
    Q_UNUSED(key)
    // Rien n'a jamais été écrit : la cible « aucune trace » est donc atteinte.
    return VaultResult::success();
}

bool RefusingCredentialVault::contains(const QString &key)
{
    Q_UNUSED(key)
    return false;
}

std::unique_ptr<CredentialVault> makeCredentialVault(const QString &applicationName)
{
#ifdef Q_OS_WIN
    return std::make_unique<WindowsCredentialVault>(applicationName);
#else
    Q_UNUSED(applicationName)
    return std::make_unique<RefusingCredentialVault>(QStringLiteral(
        "aucune implémentation de coffre n'est écrite pour ce système d'exploitation"));
#endif
}

} // namespace acp
