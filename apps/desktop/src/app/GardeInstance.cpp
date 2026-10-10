#include "app/GardeInstance.h"

#include <QDir>
#include <QFileInfo>
#include <QLockFile>
#include <QStandardPaths>

namespace acp {

GardeInstance::GardeInstance(QString cheminVerrou)
    : m_chemin(std::move(cheminVerrou))
{
}

GardeInstance::~GardeInstance()
{
    if (m_verrou) {
        m_verrou->unlock();
    }
}

QString GardeInstance::cheminParDefaut()
{
    const QString dossier = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    return dossier.isEmpty() ? QString() : QDir(dossier).filePath(QStringLiteral("instance.lock"));
}

QString GardeInstance::messageSecondeInstance()
{
    return QStringLiteral("La station de travail est déjà ouverte sur ce poste. Une seule "
                          "instance est admise : deux stations rejoueraient le même jeton de "
                          "connexion, et le fournisseur d'identité révoquerait la session.");
}

bool GardeInstance::acquerir(QString *raison)
{
    if (m_chemin.isEmpty()) {
        if (raison) {
            *raison = QStringLiteral("Aucun dossier local n'est disponible pour le verrou "
                                     "d'instance : démarrage refusé.");
        }
        return false;
    }
    if (m_verrou && m_verrou->isLocked()) {
        return true;
    }
    if (!QDir().mkpath(QFileInfo(m_chemin).absolutePath())) {
        if (raison) {
            *raison = QStringLiteral("Dossier du verrou d'instance impossible à créer : %1")
                          .arg(QFileInfo(m_chemin).absolutePath());
        }
        return false;
    }
    m_verrou = std::make_unique<QLockFile>(m_chemin);
    // Un verrou laissé par un processus mort est repris par QLockFile (PID et hôte vérifiés) ;
    // un verrou vivant n'est jamais forcé, quel que soit son âge.
    m_verrou->setStaleLockTime(0);
    if (m_verrou->tryLock(0)) {
        return true;
    }
    if (raison) {
        *raison = m_verrou->error() == QLockFile::LockFailedError
            ? messageSecondeInstance()
            : QStringLiteral("Verrou d'instance illisible (%1) : démarrage refusé.").arg(m_chemin);
    }
    m_verrou.reset();
    return false;
}

bool GardeInstance::estAcquise() const
{
    return m_verrou && m_verrou->isLocked();
}

} // namespace acp
