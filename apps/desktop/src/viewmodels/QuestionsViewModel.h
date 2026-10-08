// Page Questions de la station (cahier P8 § 7.3 ; file à cinq sections de l'étape P7, cahier P7
// § 3), sur `GET /v1/questions` du greffon, relu toutes les 15 s tant que la page est affichée.
// Mêmes sections, mêmes gestes et mêmes messages que la page web (apps/interface/src/projets/
// Questions.tsx), dans le même ordre :
//
//  0. « À traiter par vous » et « Chez Hermes » : `compteurs` servis par le greffon (questions à
//     vous, décisions, revues, cartes arrêtées), plus les discussions en attente quand elles ont
//     pu être lues ; sinon le total le dit, jamais zéro par défaut.
//  1. Questions ouvertes ou escaladées : texte, contexte, projet, carte, QUI y répond (`chez`,
//     règle unique du greffon), motif d'escalade, date ; « Répondre » →
//     `POST /v1/questions/{q}/reponse {reponse}` (1 à 4 000 caractères). Le message suit la RÉPONSE
//     du greffon (`carte_debloquee`, `reprise_differee`), jamais une supposition ; une question
//     fermée entre-temps (409) est dite, puis relue.
//  2. Décisions (cartes en triage) : gestes construits DEPUIS `actions` rendues par le greffon
//     (« Prolonger », « Relancer la planification », « Reprendre » → `/reprendre` avec une consigne
//     facultative ; « Conclure le projet » → `/conclure`), jamais une liste fixe ; un geste non offert
//     est refusé par la station.
//  3. Revues des fichiers de pilotage (P6) : « Accepter » → `/v1/revues/{t}/{c}/accepter`,
//     « Refuser » avec un motif (1 à 1 000 caractères) → `/refuser` ; affichées seulement si la
//     clé `revues` existe.
//  4. Cartes arrêtées (bloquées ou abandonnées) : « Relancer » → `/v1/cartes/{t}/{c}/relancer`
//     avec une consigne facultative (1 à 4 000 caractères ; jamais pour une carte d'intégration),
//     seulement si le greffon la dit `relancable` ; sinon la raison du refus (`refus_relance`).
//     Message d'après la réponse (`relancee`, `session_neuve`, `branche_neuve`, `statut_apres`).
//  5. Discussions en attente : lues par la passerelle (`session.active_list`, DiscussionsEnAttente),
//     en lecture seule : titre, activité, aperçu, session ; « Ouvrir la discussion » reprend la
//     session dans la page Discussion. Illisibles : « état inconnu », avec le compteur du tableau
//     de bord (`discussions` de la file) s'il le publie.
//  Tableaux illisibles : signalés tels quels.
//
// Une réponse rendue sans effet (carte non relancée, non reprise) est une ALERTE, pas une
// réussite : la page la montre comme telle (alerteGeste).
//
// Brouillons : le texte d'une réponse (« q:<question> »), d'une consigne de triage
// (« t:<tableau>/<carte> »), d'une consigne de relance (« r:<tableau>/<carte> ») ou d'un motif de
// refus (« m:<tableau>/<carte> ») est gardé ici à chaque frappe, pas dans le champ seul : il
// survit aux relectures, à un envoi refusé et à un changement de page ; il n'est effacé qu'après
// la réussite du geste (signal brouillonEfface).

#pragma once

#include "models/JsonListModel.h"
#include "viewmodels/PageViewModel.h"

#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>
#include <QVariantMap>

#include <chrono>
#include <optional>

namespace acp {

class ApiClient;
class ClientGreffonPoste;
class Sondage;

class QuestionsViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(JsonListModel *questions READ questions CONSTANT)
    Q_PROPERTY(JsonListModel *triage READ triage CONSTANT)
    Q_PROPERTY(JsonListModel *bloquees READ bloquees CONSTANT)
    Q_PROPERTY(JsonListModel *revues READ revues CONSTANT)
    Q_PROPERTY(bool lue READ lue NOTIFY listeChange)
    Q_PROPERTY(bool revuesPresentes READ revuesPresentes NOTIFY listeChange)
    Q_PROPERTY(QStringList tableauxIllisibles READ tableauxIllisibles NOTIFY listeChange)
    Q_PROPERTY(QVariantMap resume READ resume NOTIFY listeChange)
    Q_PROPERTY(QVariantMap discussions READ discussions NOTIFY listeChange)
    Q_PROPERTY(QString lecture READ lecture NOTIFY lectureChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY lectureChange)

public:
    QuestionsViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                       QObject *parent = nullptr);
    ~QuestionsViewModel() override;

    /*! Intervalle du sondage de la page (15 s ; réglable pour les tests). */
    void setIntervalle(std::chrono::milliseconds intervalle);

    [[nodiscard]] JsonListModel *questions() const { return m_questions; }
    [[nodiscard]] JsonListModel *triage() const { return m_triage; }
    [[nodiscard]] JsonListModel *bloquees() const { return m_bloquees; }
    [[nodiscard]] JsonListModel *revues() const { return m_revues; }
    [[nodiscard]] bool lue() const { return m_lue; }
    [[nodiscard]] bool revuesPresentes() const { return m_revuesPresentes; }
    [[nodiscard]] const QStringList &tableauxIllisibles() const { return m_illisibles; }
    [[nodiscard]] const QVariantMap &resume() const { return m_resume; }
    [[nodiscard]] const QVariantMap &discussions() const { return m_discussions; }
    [[nodiscard]] QString lecture() const;
    [[nodiscard]] QString erreur() const;

    Q_INVOKABLE void actualiser();
    /*! Répond à une question ouverte ou escaladée (1 à 4 000 caractères). */
    Q_INVOKABLE void repondre(const QString &question, const QString &reponse);
    /*!
        Geste sur une carte en triage : « reprise » (prolonger, relancer ou reprendre, selon ce
        que le greffon offre, avec une consigne facultative) ou « conclure ».
    */
    Q_INVOKABLE void agirTriage(const QString &tableau, const QString &carte, const QString &geste,
                                const QString &consigne);
    /*! « Relancer » une carte arrêtée que le greffon dit relançable ; consigne facultative. */
    Q_INVOKABLE void relancer(const QString &tableau, const QString &carte, const QString &consigne);
    /*! « Accepter » une revue des fichiers de pilotage. */
    Q_INVOKABLE void accepterRevue(const QString &tableau, const QString &carte);
    /*! « Refuser » une revue, avec un motif (1 à 1 000 caractères). */
    Q_INVOKABLE void refuserRevue(const QString &tableau, const QString &carte, const QString &motif);

    /*! Brouillon gardé pour sa clé (vide s'il n'y en a pas). */
    Q_INVOKABLE QString brouillon(const QString &cle) const { return m_brouillons.value(cle); }
    /*! Mémorise le texte en cours de frappe ; un texte vide retire le brouillon. */
    Q_INVOKABLE void setBrouillon(const QString &cle, const QString &texte);
    [[nodiscard]] int nombreBrouillons() const { return static_cast<int>(m_brouillons.size()); }

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QJsonObject construireQuestion(const QJsonObject &question);
    [[nodiscard]] static QJsonObject construireTriage(const QJsonObject &carte);
    [[nodiscard]] static QJsonObject construireBloquee(const QJsonObject &carte);
    [[nodiscard]] static QJsonObject construireRevue(const QJsonObject &revue);
    /*!
        « À traiter par vous » : `compteurs` du greffon, plus les `discussions` en attente quand elles
        sont connues (-1 : inconnues, le total le dit).
    */
    [[nodiscard]] static QVariantMap construireResume(const QJsonObject &liste, int discussions = -1);
    /*!
        Section « Discussions en attente » : les `sessions` lues par la passerelle
        (DiscussionsEnAttente::sessionsEnAttente) ; `nullopt` : inconnues, avec le compteur du
        tableau de bord (`serveur`, section `discussions` de la file) ou ce qui en est su.
    */
    [[nodiscard]] static QVariantMap construireDiscussions(const QJsonValue &serveur,
                                                           const std::optional<QJsonArray> &sessions = std::nullopt);
    [[nodiscard]] static QString messageReponse(const QJsonObject &resultat);
    [[nodiscard]] static QString messageTriage(const QJsonObject &resultat);
    /*! Message d'une relance, d'après la réponse du greffon (`integration` : carte sans agent). */
    [[nodiscard]] static QString messageRelance(const QJsonObject &resultat, bool integration);
    /*! Gestes offerts : `actions` lisibles, sinon « reprendre » (comme la page web). */
    [[nodiscard]] static QStringList gestesOfferts(const QJsonObject &carte);

signals:
    void listeChange();
    void lectureChange();
    /*! Le geste a réussi : le champ de ce brouillon se vide. */
    void brouillonEfface(const QString &cle);

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;

private:
    void lire(const QJsonObject &liste);
    void apresGeste();
    void effacerBrouillon(const QString &cle);

    void majDiscussions();

    ClientGreffonPoste *m_greffon = nullptr;
    ApiClient *m_client = nullptr;
    Sondage *m_sondage = nullptr;
    JsonListModel *m_questions = nullptr;
    JsonListModel *m_triage = nullptr;
    JsonListModel *m_bloquees = nullptr;
    JsonListModel *m_revues = nullptr;
    bool m_lue = false;
    bool m_revuesPresentes = false;
    QStringList m_illisibles;
    QVariantMap m_resume;
    QVariantMap m_discussions;
    QJsonObject m_derniereListe;
    QHash<QString, QStringList> m_gestes;   //!< « tableau/carte » → gestes offerts par le greffon.
    QHash<QString, bool> m_relancables;     //!< « tableau/carte » → carte d'intégration ?
    QHash<QString, bool> m_revuesOuvertes;  //!< « tableau/carte » des revues servies.
    QHash<QString, QString> m_brouillons;   //!< clé de brouillon → texte.
};

} // namespace acp
