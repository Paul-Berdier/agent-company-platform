// Coffre en mémoire pour les tests : jamais le Gestionnaire d'identification réel, sauf
// dans le test d'aller-retour Windows dédié, sous un nom d'application de test.

#pragma once

#include "storage/CredentialVault.h"

#include <QHash>

namespace acp::test {

class CoffreMemoire final : public CredentialVault
{
public:
    QHash<QString, QByteArray> entrees;
    int lectures = 0;
    int ecritures = 0;
    int effacements = 0;
    bool refuserEcriture = false;
    bool refuserEffacement = false;
    //! Appelé à chaque écriture réussie, avant le retour (ordre des opérations).
    std::function<void(const QString &, const QByteArray &)> surEcriture;

    QString backendName() const override { return QStringLiteral("Coffre de test en mémoire"); }
    bool canStore() const override { return true; }
    VaultStatus::State status() const override { return VaultStatus::Available; }

    VaultResult store(const QString &cle, const QByteArray &secret) override
    {
        ++ecritures;
        if (refuserEcriture) {
            return VaultResult::failure(QStringLiteral("écriture refusée par le coffre de test"));
        }
        entrees.insert(cle, secret);
        if (surEcriture) {
            surEcriture(cle, secret);
        }
        return VaultResult::success();
    }

    VaultResult load(const QString &cle, QByteArray &secret) override
    {
        ++lectures;
        if (!entrees.contains(cle)) {
            return VaultResult::failure(QStringLiteral("aucune entrée de ce nom"));
        }
        secret = entrees.value(cle);
        return VaultResult::success();
    }

    VaultResult remove(const QString &cle) override
    {
        ++effacements;
        if (refuserEffacement) {
            return VaultResult::failure(QStringLiteral("effacement refusé par le coffre de test"));
        }
        entrees.remove(cle);
        return VaultResult::success();
    }

    bool contains(const QString &cle) override { return entrees.contains(cle); }
};

} // namespace acp::test
