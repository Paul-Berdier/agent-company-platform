// Garde d'instance unique de la station.
//
// Deux stations ouvertes sur le même poste rejoueraient le même jeton de rafraîchissement :
// Authelia détecte la réutilisation et révoque la session entière (identite.md § 12.1).
// Une seule instance est donc admise, par un verrou de fichier pris sans attente dans
// `%LOCALAPPDATA%\Agent Company Platform\Station de travail\instance.lock`. Un second
// lancement affiche un message français et sort avec le code 3.

#pragma once

#include <QString>

#include <memory>

class QLockFile;

namespace acp {

class GardeInstance
{
public:
    //! Code de sortie d'un second lancement.
    static constexpr int kCodeSecondeInstance = 3;

    explicit GardeInstance(QString cheminVerrou);
    ~GardeInstance();
    GardeInstance(const GardeInstance &) = delete;
    GardeInstance &operator=(const GardeInstance &) = delete;

    /*! Chemin du verrou sous le dossier local de l'application (QStandardPaths). */
    [[nodiscard]] static QString cheminParDefaut();

    /*! Prend le verrou sans attendre. Faux, avec la raison française, s'il est déjà pris. */
    bool acquerir(QString *raison = nullptr);

    [[nodiscard]] bool estAcquise() const;
    [[nodiscard]] const QString &chemin() const { return m_chemin; }

    /*! Message affiché au second lancement. */
    [[nodiscard]] static QString messageSecondeInstance();

private:
    QString m_chemin;
    std::unique_ptr<QLockFile> m_verrou;
};

} // namespace acp
