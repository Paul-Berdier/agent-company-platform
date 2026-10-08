// Temps réel de la station : ce qui existe vraiment à `refonte/hermes` b3faac0, et seulement
// cela (cahier P8 § 6).
//
// | Source                                   | Rôle dans la station                                   |
// |------------------------------------------|--------------------------------------------------------|
// | passerelle `/api/ws` (GatewayClient)     | Discussion ; `sessions.changed` relit les sessions     |
// | kanban `/api/plugins/kanban/events`      | signal d'invalidation du projet affiché (VeilleKanban) |
// | routes REST du greffon                   | vérité de toutes les pages, par sondage (Sondage)      |
// | flux SSE du greffon                      | N'EXISTE PAS : rien n'est ouvert ni supposé            |
//
// Ce service :
//  - porte le sondage LÉGER de `GET /v1/projets` (60 s, session établie) qui alimente la barre
//    d'état et le badge des questions, même hors des pages ; une page qui vient de lire
//    `/v1/projets` le lui signale (noterProjets) pour que le badge suive sans attendre ;
//  - dit aux pages si elles peuvent sonder (`pagesActives` : session établie ET fenêtre non
//    réduite) et quand relire (`lienRetabli`, `sessionsChangees`, `tableauChange`) ;
//  - publie l'état de chaque source, sans secret, pour les diagnostics.
//
// Flux SSE du greffon : il « viendra en P7 » (sondage.ts de l'interface web) ; tant que son
// contrat n'est pas fusionné dans `refonte/hermes`, la station n'ouvre rien et l'écrit :
// « Non disponible sur ce serveur ».

#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>

#include <chrono>

namespace acp {

class ApiClient;
class ClientGreffonPoste;
class GatewayClient;
class Sondage;
class VeilleKanban;

class EventStreamService : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool fenetreActive READ fenetreActive WRITE setFenetreActive NOTIFY fenetreActiveChange)
    Q_PROPERTY(bool pagesActives READ pagesActives NOTIFY pagesActivesChange)
    // Résumé du sondage léger (barre d'état, badge de navigation).
    Q_PROPERTY(int questionsOuvertes READ questionsOuvertes NOTIFY resumeChange)
    Q_PROPERTY(QString libelleQuestions READ libelleQuestions NOTIFY resumeChange)
    Q_PROPERTY(QString libellePoste READ libellePoste NOTIFY resumeChange)
    Q_PROPERTY(QString clePoste READ clePoste NOTIFY resumeChange)
    Q_PROPERTY(int pauseGenerale READ pauseGenerale NOTIFY resumeChange)
    Q_PROPERTY(QString libelleResume READ libelleResume NOTIFY resumeChange)
    // Sources (diagnostics).
    Q_PROPERTY(QString etatPasserelle READ etatPasserelle NOTIFY sourcesChange)
    Q_PROPERTY(QString etatVeille READ etatVeille NOTIFY sourcesChange)
    Q_PROPERTY(QString etatSondage READ etatSondage NOTIFY sourcesChange)

public:
    //! Valeur de `pauseGenerale` quand l'état n'a pas encore été lu.
    static constexpr int kInconnu = -1;
    static constexpr std::chrono::milliseconds kIntervalleFond{60000};

    EventStreamService(ApiClient *client, ClientGreffonPoste *greffon, GatewayClient *passerelle,
                       QObject *parent = nullptr);
    ~EventStreamService() override;

    [[nodiscard]] VeilleKanban *veille() const { return m_veille; }
    [[nodiscard]] Sondage *sondageFond() const { return m_fond; }
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

    /*! Une page vient de lire `GET /v1/projets` : le résumé suit sans attendre. */
    void noterProjets(const QJsonObject &liste);
    /*! Le résumé redevient « Inconnu » (session perdue, serveur changé, greffon bloqué). */
    void oublierResume();

    // --- Résumé ----------------------------------------------------------------------
    /*! Nombre de questions ouvertes, ou -1 si inconnu. */
    [[nodiscard]] int questionsOuvertes() const { return m_questionsOuvertes; }
    [[nodiscard]] QString libelleQuestions() const;
    [[nodiscard]] const QString &libellePoste() const { return m_libellePoste; }
    [[nodiscard]] const QString &clePoste() const { return m_clePoste; }
    /*! 1 engagée, 0 levée, -1 inconnue. */
    [[nodiscard]] int pauseGenerale() const { return m_pauseGenerale; }
    [[nodiscard]] QString libelleResume() const;

    // --- Sources -----------------------------------------------------------------------
    [[nodiscard]] QString etatPasserelle() const;
    [[nodiscard]] QString etatVeille() const;
    [[nodiscard]] QString etatSondage() const;
    /*!
        Ce que la station dit du flux d'invalidation du greffon, d'après `etatFlux` de l'évaluation de
        /v1/meta (« annonce », « absent », « illisible », « inconnu ») : elle ne l'ouvre pas et relit ses
        pages par sondage (relecture finale de P7 : jamais « n'annonce aucun flux » devant une annonce).
    */
    [[nodiscard]] static QString etatFluxGreffon(const QString &etatFlux);

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
    void lireResume(const QJsonObject &liste);

    ClientGreffonPoste *m_greffon = nullptr;
    GatewayClient *m_passerelle = nullptr;
    VeilleKanban *m_veille = nullptr;
    Sondage *m_fond = nullptr;
    bool m_fenetreActive = true;
    bool m_sessionOuverte = false;
    bool m_lienEnLigne = false;
    bool m_lienConnu = false;
    int m_questionsOuvertes = -1;
    QString m_libellePoste;
    QString m_clePoste;
    int m_pauseGenerale = kInconnu;
};

} // namespace acp
