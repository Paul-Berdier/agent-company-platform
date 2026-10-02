// Page Projets de la station (cahier P8 § 7.2) : liste, détail, nouveau projet.
//
// Liste : `GET /v1/projets` (15 s tant que la page est affichée). Détail : `GET /v1/projets/{id}`,
// relu toutes les 15 s, ou toutes les 60 s quand la veille du kanban est prête — chaque
// changement du tableau déclenche alors une relecture (EventStreamService, VeilleKanban).
// Résumé d'une carte en entier : `GET /v1/projets/{id}/cartes/{carte}`.
//
// Nouveau projet : mêmes champs, mêmes listes et mêmes contrôles que la page web
// (apps/interface/src/projets/NouveauProjet.tsx), lus des mêmes routes (`/v1/catalogue`,
// `/v1/poste`) ; aucun profil, dépôt, exécutant, modèle ou effort qui ne vienne du serveur.
// Une clé d'idempotence par formulaire : un double envoi rend `deja_lance`, dit tel quel ;
// elle n'est renouvelée qu'après un lancement accepté.
//
// Toutes les valeurs exposées sont déjà libellées en français ; une valeur absente ou d'un
// autre type vaut « Inconnu ». Les gestes rendent le message du serveur tel quel.

#pragma once

#include "viewmodels/PageViewModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QUrl>
#include <QVariantMap>

#include <chrono>
#include <functional>
#include <optional>

namespace acp {

class ApiClient;
class ClientGreffonPoste;
class JsonListModel;
class Sondage;

class ProjetsViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(QString vue READ vue NOTIFY vueChange)
    // Liste
    Q_PROPERTY(JsonListModel *projets READ projets CONSTANT)
    Q_PROPERTY(bool listeLue READ listeLue NOTIFY listeChange)
    Q_PROPERTY(QVariantMap pause READ pause NOTIFY listeChange)
    Q_PROPERTY(QString lectureListe READ lectureListe NOTIFY lectureChange)
    Q_PROPERTY(QString erreurListe READ erreurListe NOTIFY lectureChange)
    // Détail
    Q_PROPERTY(QString projetOuvert READ projetOuvert NOTIFY vueChange)
    Q_PROPERTY(bool detailLu READ detailLu NOTIFY detailChange)
    Q_PROPERTY(QVariantMap detail READ detail NOTIFY detailChange)
    Q_PROPERTY(JsonListModel *cartes READ cartes CONSTANT)
    Q_PROPERTY(JsonListModel *questionsDuProjet READ questionsDuProjet CONSTANT)
    Q_PROPERTY(JsonListModel *tours READ tours CONSTANT)
    Q_PROPERTY(JsonListModel *journal READ journal CONSTANT)
    Q_PROPERTY(QVariantMap carteLue READ carteLue NOTIFY carteLueChange)
    Q_PROPERTY(QString lectureDetail READ lectureDetail NOTIFY lectureChange)
    Q_PROPERTY(QString erreurDetail READ erreurDetail NOTIFY lectureChange)
    Q_PROPERTY(QString etatVeille READ etatVeille NOTIFY veilleChange)
    // Nouveau projet
    Q_PROPERTY(QVariantMap formulaire READ formulaire NOTIFY formulaireChange)

public:
    static constexpr std::chrono::milliseconds kIntervalleDetailVeille{60000};

    ProjetsViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                     QObject *parent = nullptr);
    ~ProjetsViewModel() override;

    //! Ouvre une URL dans le navigateur du système (injectable pour les tests).
    using Ouvreur = std::function<bool(const QUrl &)>;
    void setOuvreur(Ouvreur ouvreur) { m_ouvreur = std::move(ouvreur); }
    void setIntervalles(std::chrono::milliseconds page, std::chrono::milliseconds detailVeille);

    [[nodiscard]] const QString &vue() const { return m_vue; }
    [[nodiscard]] JsonListModel *projets() const { return m_projets; }
    [[nodiscard]] bool listeLue() const { return m_listeLue; }
    [[nodiscard]] const QVariantMap &pause() const { return m_pause; }
    [[nodiscard]] QString lectureListe() const;
    [[nodiscard]] QString erreurListe() const;

    [[nodiscard]] const QString &projetOuvert() const { return m_projetOuvert; }
    [[nodiscard]] bool detailLu() const { return m_detailLu; }
    [[nodiscard]] const QVariantMap &detail() const { return m_detail; }
    [[nodiscard]] JsonListModel *cartes() const { return m_cartes; }
    [[nodiscard]] JsonListModel *questionsDuProjet() const { return m_questionsDuProjet; }
    [[nodiscard]] JsonListModel *tours() const { return m_tours; }
    [[nodiscard]] JsonListModel *journal() const { return m_journal; }
    [[nodiscard]] const QVariantMap &carteLue() const { return m_carteLue; }
    [[nodiscard]] QString lectureDetail() const;
    [[nodiscard]] QString erreurDetail() const;
    [[nodiscard]] QString etatVeille() const;

    [[nodiscard]] const QVariantMap &formulaire() const { return m_formulaire; }

    // --- Navigation interne ----------------------------------------------------------
    Q_INVOKABLE void afficherListe();
    Q_INVOKABLE void ouvrirProjet(const QString &identifiant);
    Q_INVOKABLE void afficherNouveau();
    Q_INVOKABLE void actualiser();

    // --- Gestes du détail ----------------------------------------------------------------
    Q_INVOKABLE void lireCarteEnEntier(const QString &carte);
    Q_INVOKABLE void fermerCarteLue();
    Q_INVOKABLE void mettreEnPause();
    Q_INVOKABLE void reprendre();
    /*! Ouvre le kanban de Hermes (`/kanban`) dans le navigateur du système. */
    Q_INVOKABLE bool ouvrirKanban();

    // --- Formulaire « Nouveau projet » -----------------------------------------------------
    Q_INVOKABLE void choisirDepot(const QString &depot);
    Q_INVOKABLE void choisirVoie(const QString &voie);
    Q_INVOKABLE void choisirModele(const QString &modele);
    Q_INVOKABLE void lancer(const QString &titre, const QString &objectif, const QString &profil,
                            const QString &reponses, const QString &effort);
    [[nodiscard]] const QString &cleIdempotence() const { return m_cle; }

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QJsonObject construireLigneProjet(const QJsonObject &projet);
    [[nodiscard]] static QVariantMap construireDetail(const QJsonObject &projet);
    [[nodiscard]] static QJsonArray construireCartes(const QJsonArray &cartes);
    [[nodiscard]] static QJsonArray construireJournal(const QJsonArray &journal);
    [[nodiscard]] static QStringList voiesRelevees(const QJsonObject &cataloguePoste);
    /*! Dépôts autorisés lus dans les relevés ; nul si le poste n'a publié AUCUN relevé. */
    [[nodiscard]] static std::optional<QStringList> depotsConnus(const QJsonObject &cataloguePoste);
    [[nodiscard]] static QStringList effortsAdmis(const QJsonObject &voie, const QString &modele,
                                                  const QStringList &interdits);

signals:
    void vueChange();
    void listeChange();
    void detailChange();
    void carteLueChange();
    void lectureChange();
    void veilleChange();
    void formulaireChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;

private:
    void changerVue(const QString &vue);
    void majSondages();
    void majVeille();
    void lireListe(const QJsonObject &liste);
    void lireDetail(const QJsonObject &reponse);
    void viderDetail();
    void lireFormulaire();
    void majFormulaire();
    void apresGesteProjet(const QString &message);

    ApiClient *m_client = nullptr;
    ClientGreffonPoste *m_greffon = nullptr;
    Sondage *m_liste = nullptr;
    Sondage *m_detailSondage = nullptr;
    JsonListModel *m_projets = nullptr;
    JsonListModel *m_cartes = nullptr;
    JsonListModel *m_questionsDuProjet = nullptr;
    JsonListModel *m_tours = nullptr;
    JsonListModel *m_journal = nullptr;
    Ouvreur m_ouvreur;
    std::chrono::milliseconds m_intervallePage{15000};
    std::chrono::milliseconds m_intervalleVeille{kIntervalleDetailVeille};

    QString m_vue = QStringLiteral("liste");
    bool m_listeLue = false;
    QVariantMap m_pause;
    QString m_projetOuvert;
    QString m_tableauOuvert;
    QString m_etatProjet;
    bool m_detailLu = false;
    QVariantMap m_detail;
    QVariantMap m_carteLue;
    quint64 m_generationDetail = 0;

    // Formulaire
    QString m_cle;
    QJsonObject m_catalogue;
    QJsonObject m_poste;
    bool m_catalogueLu = false;
    bool m_posteLu = false;
    QString m_erreurCatalogue;
    QString m_erreurPoste;
    QString m_depot;
    QString m_voie;
    QString m_modele;
    QVariantMap m_formulaire;
};

} // namespace acp
