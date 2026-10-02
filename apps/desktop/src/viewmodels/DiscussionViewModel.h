// Discussion avec Hermes sur la passerelle JSON-RPC `/api/ws` (cahier P8 § 7.4).
//
//  - Liste : `session.list {limit: 50}`, relue à l'affichage de la page et sur
//    `sessions.changed`.
//  - Ouvrir : `session.resume {session_id: <identifiant stocké>}` → identifiant VIVANT, puis
//    transcription (`role`, `text`, `timestamp`), `running`, `inflight` ; « Nouvelle
//    discussion » : `session.create {}`. La session vivante est suivie par la passerelle
//    (rejeu par `seq` après une coupure, relecture si Hermes a redémarré).
//  - Envoyer : `prompt.submit {session_id, text}` ; le message apparaît tout de suite avec
//    « Envoi… », puis l'état rendu par Hermes (`streaming`, `queued`, `steered`,
//    `redirected`), ou « Non envoyé » et l'erreur. « Arrêter » : `session.interrupt`.
//  - Flux : `message.start` ouvre une réponse, `message.delta.text` s'y ajoute,
//    `message.complete` la fige (texte final, issue, avertissement) ; `tool.start` et
//    `tool.complete` : une ligne « Outil » avec son nom et son résumé, JAMAIS ses arguments
//    bruts ; `status.update` : ligne d'état éphémère ; `error` : bandeau ; `notice` : avis.
//    Les autres événements sont comptés et ignorés : aucun rendu deviné.
//  - Quitter une session qui ne tourne pas la ferme (`session.close`) ; une session dont un
//    tour est en cours n'est jamais fermée par la station.
//  - Pas de choix de modèle ni de profil : la session prend le défaut du profil de Hermes.
//
// Les demandes de l'agent (`approval`, `clarify`) sont tenues par DemandesAgent.

#pragma once

#include "models/JsonListModel.h"
#include "viewmodels/PageViewModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>

namespace acp {

class GatewayClient;
struct ErreurRpc;

class DiscussionViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(JsonListModel *sessions READ sessions CONSTANT)
    Q_PROPERTY(bool sessionsLues READ sessionsLues NOTIFY sessionsChange)
    Q_PROPERTY(QString erreurSessions READ erreurSessions NOTIFY sessionsChange)
    Q_PROPERTY(QString sessionOuverte READ sessionOuverte NOTIFY sessionChange)
    Q_PROPERTY(QString sessionVivante READ sessionVivante NOTIFY sessionChange)
    Q_PROPERTY(QString titreSession READ titreSession NOTIFY sessionChange)
    Q_PROPERTY(bool ouverture READ ouverture NOTIFY sessionChange)
    Q_PROPERTY(JsonListModel *transcription READ transcription CONSTANT)
    Q_PROPERTY(bool tourEnCours READ tourEnCours NOTIFY tourChange)
    Q_PROPERTY(QString ligneEtat READ ligneEtat NOTIFY tourChange)
    Q_PROPERTY(QString erreurSession READ erreurSession NOTIFY tourChange)
    Q_PROPERTY(QString avis READ avis NOTIFY tourChange)
    Q_PROPERTY(int evenementsIgnores READ evenementsIgnores NOTIFY tourChange)
    Q_PROPERTY(bool passerellePrete READ passerellePrete NOTIFY passerelleChange)
    Q_PROPERTY(QString etatPasserelle READ etatPasserelle NOTIFY passerelleChange)

public:
    DiscussionViewModel(GatewayClient *passerelle, EventStreamService *flux, QObject *parent = nullptr);
    ~DiscussionViewModel() override;

    [[nodiscard]] JsonListModel *sessions() const { return m_sessions; }
    [[nodiscard]] bool sessionsLues() const { return m_sessionsLues; }
    [[nodiscard]] const QString &erreurSessions() const { return m_erreurSessions; }
    [[nodiscard]] const QString &sessionOuverte() const { return m_stockee; }
    [[nodiscard]] const QString &sessionVivante() const { return m_vivante; }
    [[nodiscard]] const QString &titreSession() const { return m_titre; }
    [[nodiscard]] bool ouverture() const { return m_ouverture; }
    [[nodiscard]] JsonListModel *transcription() const { return m_transcription; }
    [[nodiscard]] bool tourEnCours() const { return m_tourEnCours; }
    [[nodiscard]] const QString &ligneEtat() const { return m_ligneEtat; }
    [[nodiscard]] const QString &erreurSession() const { return m_erreurSession; }
    [[nodiscard]] const QString &avis() const { return m_avis; }
    [[nodiscard]] int evenementsIgnores() const { return m_ignores; }
    [[nodiscard]] bool passerellePrete() const;
    [[nodiscard]] QString etatPasserelle() const;

    Q_INVOKABLE void actualiserSessions();
    /*! Ouvre une session par son identifiant STOCKÉ (liste, accueil). */
    Q_INVOKABLE void ouvrir(const QString &identifiantStocke);
    Q_INVOKABLE void nouvelle();
    /*! Vrai si le message est parti vers Hermes (la zone de saisie peut alors être vidée). */
    Q_INVOKABLE bool envoyer(const QString &texte);
    Q_INVOKABLE void arreter();
    /*! Quitte la session affichée (fermée si aucun tour n'y tourne). */
    Q_INVOKABLE void quitter();

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QJsonObject construireSession(const QJsonObject &ligne);
    [[nodiscard]] static QJsonObject construireMessage(const QJsonObject &message, int rang);
    [[nodiscard]] static QString messageEnvoi(const QJsonValue &statut);
    [[nodiscard]] static QString issueDuTour(const QJsonObject &fin);

signals:
    void sessionsChange();
    void sessionChange();
    void tourChange();
    void passerelleChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;

private:
    void surEvenement(const QString &type, const QString &sessionId, qint64 seq, const QJsonValue &payload);
    void adopter(const QJsonObject &resultat, const QString &stockee);
    void laisserSession();
    int dernierEnCours(const QString &role) const;
    int ligneDeCle(const QString &cle) const;
    void ajouter(QJsonObject ligne);
    void echecRpc(const QString &methode, const ErreurRpc &erreur);
    void majTour(bool enCours);

    GatewayClient *m_passerelle = nullptr;
    JsonListModel *m_sessions = nullptr;
    JsonListModel *m_transcription = nullptr;
    bool m_sessionsLues = false;
    QString m_erreurSessions;
    QString m_stockee;
    QString m_vivante;
    QString m_titre;
    bool m_ouverture = false;
    bool m_tourEnCours = false;
    QString m_ligneEtat;
    QString m_erreurSession;
    QString m_avis;
    int m_ignores = 0;
    int m_compteur = 0;
    quint64 m_generation = 0;
    bool m_dejaPrete = false;
};

} // namespace acp
