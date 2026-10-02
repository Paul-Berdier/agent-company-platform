// Page Sauvegarde de la station (cahier P8 § 7.9, décision D8-7) : exporter une sauvegarde de
// Hermes, chiffrée sur ce PC, sans que l'archive en clair touche jamais son disque.
//
//  1. `POST /api/ops/backup {}` → Hermes lance `hermes backup` et dit où il écrit l'archive ;
//  2. `GET /api/actions/backup/status` toutes les 2 s jusqu'à la fin ; code de sortie non nul :
//     échec affiché avec les dernières lignes du journal, expurgées ;
//  3. `GET /api/ops/backup/download?archive=<chemin>` lu en flux (TelechargementFlux, plafond
//     4 Gio) et chiffré au fil de l'eau (ACPB1, DPAPI) vers le fichier choisi (QSaveFile : un
//     échec ou une annulation ne laisse aucun fichier) ;
//  4. `DELETE /api/files {path}` : l'archive en clair quitte le volume de Hermes ; si Hermes le
//     refuse, la page le DIT avec le chemin, car l'archive contient `.env` et `auth.json` ;
//  5. résultat : fichier, taille, SHA-256 du fichier chiffré, durée.
//
// « Déchiffrer une sauvegarde » (restauration de l'étape P9) écrit l'archive en clair à
// l'endroit choisi, après l'avertissement de la page.

#pragma once

#include "viewmodels/PageViewModel.h"

#include <QElapsedTimer>
#include <QJsonValue>
#include <QPointer>
#include <QString>
#include <QVariantMap>

#include <chrono>
#include <memory>

class QSaveFile;
class QTimer;

namespace acp {

class ApiCall;
class ApiClient;
class ChiffreurSauvegarde;
class ProtecteurDonnees;
class TelechargementFlux;

class SauvegardeViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(int phase READ phaseValeur NOTIFY etatChange)
    Q_PROPERTY(QString etape READ etape NOTIFY etatChange)
    Q_PROPERTY(QString etapeCle READ etapeCle NOTIFY etatChange)
    Q_PROPERTY(bool enCours READ enCours NOTIFY etatChange)
    Q_PROPERTY(bool interruptible READ interruptible NOTIFY etatChange)
    Q_PROPERTY(QString progression READ progression NOTIFY progressionChange)
    Q_PROPERTY(QString journal READ journal NOTIFY etatChange)
    Q_PROPERTY(QVariantMap resultat READ resultat NOTIFY etatChange)
    Q_PROPERTY(bool chiffrementDisponible READ chiffrementDisponible CONSTANT)

public:
    enum class Phase { Repos, Lancement, Archivage, Telechargement, Suppression, Termine, Echec };

    static constexpr std::chrono::milliseconds kIntervalleSuivi{2000};
    static constexpr std::chrono::minutes kDureeMaximale{30};

    SauvegardeViewModel(ApiClient *client, EventStreamService *flux, std::unique_ptr<ProtecteurDonnees> protecteur,
                        QObject *parent = nullptr);
    ~SauvegardeViewModel() override;

    void setIntervalleSuivi(std::chrono::milliseconds intervalle) { m_intervalle = intervalle; }
    void setPlafond(qint64 octets);

    [[nodiscard]] Phase phase() const { return m_phase; }
    [[nodiscard]] int phaseValeur() const { return static_cast<int>(m_phase); }
    [[nodiscard]] QString etape() const;
    [[nodiscard]] QString etapeCle() const;
    [[nodiscard]] bool enCours() const;
    /*! Lancement, archivage ou téléchargement : l'export peut encore être annulé. */
    [[nodiscard]] bool interruptible() const;
    [[nodiscard]] const QString &progression() const { return m_progression; }
    [[nodiscard]] const QString &journal() const { return m_journal; }
    [[nodiscard]] const QVariantMap &resultat() const { return m_resultat; }
    [[nodiscard]] bool chiffrementDisponible() const;
    /*! SHA-256 (hexadécimal) de l'archive en clair du dernier export réussi (bout en bout). */
    [[nodiscard]] const QByteArray &empreinteArchive() const { return m_empreinteArchive; }

    /*! Fichier proposé : Documents\hermes-sauvegarde-AAAAMMJJ-HHMMSS.acpb. */
    Q_INVOKABLE QString proposerDestination() const;
    /*! Lance l'export vers `destination` (chemin local ou URL file:). */
    Q_INVOKABLE void exporter(const QString &destination);
    Q_INVOKABLE void annuler();
    /*! Déchiffre `source` (ACPB1) vers `destination` (archive zip en clair). */
    Q_INVOKABLE void dechiffrer(const QString &source, const QString &destination);
    /*! Revient à l'état de repos (nouvel export possible). */
    Q_INVOKABLE void reinitialiser();
    /*! Chemin local d'une URL file: rendue par un dialogue de fichier (pour QML). */
    Q_INVOKABLE QString versCheminLocal(const QString &saisie) const { return cheminLocal(saisie); }

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QString cheminLocal(const QString &saisie);
    [[nodiscard]] static QString formaterTaille(qint64 octets);
    [[nodiscard]] static QString formaterDuree(qint64 millisecondes);
    /*! Dernières lignes (20 au plus) du journal de l'action, expurgées. */
    [[nodiscard]] static QString journalExpurge(const QJsonValue &lignes);

signals:
    void etatChange();
    void progressionChange();

protected:
    void surActivite(bool) override {}

private:
    void passer(Phase phase);
    void suivre();
    void programmerSuivi();
    void telecharger();
    void apresTelechargement();
    void supprimerArchive();
    void conclure();
    void echouer(const QString &message);
    void nettoyer();

    ApiClient *m_client = nullptr;
    std::unique_ptr<ProtecteurDonnees> m_protecteur;
    TelechargementFlux *m_flux = nullptr;
    QTimer *m_minuterie = nullptr;
    QPointer<ApiCall> m_appel;
    std::unique_ptr<QSaveFile> m_fichier;
    std::unique_ptr<ChiffreurSauvegarde> m_chiffreur;
    std::chrono::milliseconds m_intervalle = kIntervalleSuivi;
    Phase m_phase = Phase::Repos;
    QElapsedTimer m_chrono;
    QString m_destination;
    QString m_archive;
    QString m_progression;
    QString m_journal;
    QVariantMap m_resultat;
    QByteArray m_empreinteArchive;
    int m_echecsSuivi = 0;
};

} // namespace acp
