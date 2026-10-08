// Temps réel de la station : ce qui existe vraiment (cahier P8 § 6 ; étape P7 pour le flux).
//
// | Source                                   | Rôle dans la station                                   |
// |------------------------------------------|--------------------------------------------------------|
// | passerelle `/api/ws` (GatewayClient)     | Discussion ; `sessions.changed` relit les sessions     |
// | kanban `/api/plugins/kanban/events`      | signal d'invalidation du projet affiché (VeilleKanban) |
// | flux SSE du greffon `GET /v1/flux`       | signal d'invalidation par sujet (FluxInvalidation) :   |
// |                                          | ouvert seulement s'il est annoncé par /v1/meta         |
// | routes REST du greffon                   | vérité de toutes les pages, relues sur signal du flux  |
// |                                          | et par sondage (Sondage, repli et relecture de sûreté) |
//
// Ce service :
//  - porte le sondage LÉGER de `GET /v1/accueil` (60 s, session établie ; Accueil agrégé de
//    l'étape P7) qui alimente la barre d'état et le badge de la file Questions, même hors des
//    pages : le badge compte « À traiter par vous » (compteurs du greffon : questions à vous,
//    décisions, revues, cartes arrêtées ; plus les discussions en attente lues par la passerelle,
//    DiscussionsEnAttente, et le libellé dit quand elles n'ont pas pu l'être). L'Accueil qui vient
//    de lire `/v1/accueil` le lui signale
//    (noterAccueil) ; la page Projets, qui lit `/v1/projets`, met à jour le poste et la pause
//    seulement (noterProjets), jamais le compteur, qui n'a qu'une source ;
//  - dit aux pages si elles peuvent sonder (`pagesActives` : session établie ET fenêtre non
//    réduite) et quand relire (`lienRetabli`, `sessionsChangees`, `tableauChange`) ;
//  - ouvre le flux d'invalidation quand une page peut lire et que /v1/meta l'annonce
//    (setAnnonceFlux) ; le sondage léger le suit pour tous les sujets ;
//  - publie l'état de chaque source, sans secret, pour les diagnostics.

#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>

#include <chrono>

namespace acp {

class ApiClient;
class ClientGreffonPoste;
class DiscussionsEnAttente;
class FluxInvalidation;
class GatewayClient;
class Sondage;
class VeilleKanban;

class EventStreamService : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool fenetreActive READ fenetreActive WRITE setFenetreActive NOTIFY fenetreActiveChange)
    Q_PROPERTY(bool pagesActives READ pagesActives NOTIFY pagesActivesChange)
    // Résumé du sondage léger (barre d'état, badge de navigation).
    Q_PROPERTY(int aTraiter READ aTraiter NOTIFY resumeChange)
    Q_PROPERTY(QString libelleATraiter READ libelleATraiter NOTIFY resumeChange)
    Q_PROPERTY(QString libellePoste READ libellePoste NOTIFY resumeChange)
    Q_PROPERTY(QString clePoste READ clePoste NOTIFY resumeChange)
    Q_PROPERTY(int pauseGenerale READ pauseGenerale NOTIFY resumeChange)
    Q_PROPERTY(QString libelleResume READ libelleResume NOTIFY resumeChange)
    // Sources (diagnostics).
    Q_PROPERTY(QString etatPasserelle READ etatPasserelle NOTIFY sourcesChange)
    Q_PROPERTY(QString etatVeille READ etatVeille NOTIFY sourcesChange)
    Q_PROPERTY(QString etatSondage READ etatSondage NOTIFY sourcesChange)
    // Flux d'invalidation du greffon (barre d'état, diagnostics).
    Q_PROPERTY(bool tempsReel READ tempsReel NOTIFY sourcesChange)
    Q_PROPERTY(QString libelleTempsReel READ libelleTempsReel NOTIFY sourcesChange)
    Q_PROPERTY(QString etatFlux READ etatFlux NOTIFY sourcesChange)

public:
    //! Valeur de `pauseGenerale` quand l'état n'a pas encore été lu.
    static constexpr int kInconnu = -1;
    static constexpr std::chrono::milliseconds kIntervalleFond{60000};

    EventStreamService(ApiClient *client, ClientGreffonPoste *greffon, GatewayClient *passerelle,
                       QObject *parent = nullptr);
    ~EventStreamService() override;

    [[nodiscard]] VeilleKanban *veille() const { return m_veille; }
    [[nodiscard]] Sondage *sondageFond() const { return m_fond; }
    [[nodiscard]] FluxInvalidation *invalidation() const { return m_invalidation; }
    /*! Discussions en attente (`session.active_list`), partagées par le badge, l'Accueil et la file Questions. */
    [[nodiscard]] DiscussionsEnAttente *discussions() const { return m_discussions; }
    /*! Annonce du flux lue dans /v1/meta (CompatibiliteHermes::etatFlux et annonceFlux). */
    void setAnnonceFlux(const QString &etat, const QJsonObject &annonce);
    void setIntervalleFond(std::chrono::milliseconds intervalle);

    // --- Cycle de vie (Application) -------------------------------------------------
    /*! Session établie : sondage léger actif, pages autorisées à sonder. */
    void demarrer();
    /*! Session perdue : tout s'arrête, le résumé redevient « Inconnu ». */
    void arreter();
    /*! État du lien ; un retour en ligne émet `lienRetabli`. */
    void signalerLien(bool enLigne);

    [[nodiscard]] bool fenetreActive() const { return m_fenetreActive; }
    void setFenetreActive(bool active);
    [[nodiscard]] bool sessionOuverte() const { return m_sessionOuverte; }
    [[nodiscard]] bool pagesActives() const { return m_sessionOuverte && m_fenetreActive; }

    /*! L'Accueil vient de lire `GET /v1/accueil` : le résumé suit sans attendre. */
    void noterAccueil(const QJsonObject &accueil);
    /*! La page Projets vient de lire `GET /v1/projets` : poste et pause suivent (jamais le compteur). */
    void noterProjets(const QJsonObject &liste);
    /*! Le résumé redevient « Inconnu » (session perdue, serveur changé, greffon bloqué). */
    void oublierResume();

    // --- Résumé ----------------------------------------------------------------------
    /*! « À traiter par vous » (discussions en attente comprises quand elles sont connues), ou -1 si inconnu. */
    [[nodiscard]] int aTraiter() const;
    [[nodiscard]] QString libelleATraiter() const;
    [[nodiscard]] const QString &libellePoste() const { return m_libellePoste; }
    [[nodiscard]] const QString &clePoste() const { return m_clePoste; }
    /*! 1 engagée, 0 levée, -1 inconnue. */
    [[nodiscard]] int pauseGenerale() const { return m_pauseGenerale; }
    [[nodiscard]] QString libelleResume() const;

    // --- Sources -----------------------------------------------------------------------
    [[nodiscard]] QString etatPasserelle() const;
    [[nodiscard]] QString etatVeille() const;
    [[nodiscard]] QString etatSondage() const;
    /*! État du flux d'invalidation (FluxInvalidation::libelleEtat). */
    [[nodiscard]] QString etatFlux() const;
    [[nodiscard]] bool tempsReel() const;
    /*! Libellé court de la barre d'état (« Temps réel », « Sondage (aucun flux) »…), vide hors session. */
    [[nodiscard]] QString libelleTempsReel() const;

signals:
    void fenetreActiveChange();
    void pagesActivesChange();
    void resumeChange();
    void sourcesChange();
    /*! Le lien vient de revenir : les pages visibles relisent tout de suite. */
    void lienRetabli();
    /*! `sessions.changed` de la passerelle : relire les listes de sessions. */
    void sessionsChangees();
    /*! Le kanban du tableau surveillé a bougé (après regroupement). */
    void tableauChange(const QString &tableau);

private:
    void lireResume(const QJsonObject &accueil);
    void lirePosteEtPause(const QJsonValue &etatPoste, const QJsonValue &pause, bool pauseIllisible);

    ClientGreffonPoste *m_greffon = nullptr;
    GatewayClient *m_passerelle = nullptr;
    VeilleKanban *m_veille = nullptr;
    FluxInvalidation *m_invalidation = nullptr;
    DiscussionsEnAttente *m_discussions = nullptr;
    Sondage *m_fond = nullptr;
    bool m_fenetreActive = true;
    bool m_sessionOuverte = false;
    bool m_lienEnLigne = false;
    bool m_lienConnu = false;
    int m_aTraiterGreffon = -1;
    QString m_libellePoste;
    QString m_clePoste;
    int m_pauseGenerale = kInconnu;
};

} // namespace acp
