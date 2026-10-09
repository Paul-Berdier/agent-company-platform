// Discussion et demandes de l'agent contre le faux Hermes (passerelle /api/ws réelle, ticket,
// sous-protocoles, trames JSON-RPC) :
//  - liste `session.list {limit: 50}`, ouverture `session.resume` par l'identifiant STOCKÉ,
//    transcription (lignes d'outil sans contenu brut), tour en vol repris ;
//  - envoi `prompt.submit` (message affiché aussitôt « Envoi… », puis état rendu), flux
//    message.start / delta / complete, outils sans arguments ni sortie bruts, ligne d'état,
//    erreur, interruption, issue du tour ; événements d'une autre session ignorés ; types hors
//    du sous-ensemble comptés ;
//  - « Nouvelle discussion » ferme la précédente seulement si aucun tour n'y tourne ;
//  - approval / clarify : choix construits depuis ceux offerts, réponse par le MÊME identifiant
//    (`{choice}`, `{answer}`, sélection multiple en tableau JSON, `{answers}`), choix non
//    offert refusé sans trame, retrait sur `request.cancel`, liste vidée à la coupure ;
//    `secret` toujours refusé en -32601.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "gateway/DemandesAgent.h"
#include "gateway/DiscussionsEnAttente.h"
#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "viewmodels/DiscussionViewModel.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    GatewayClient passerelle{&client};
    EventStreamService flux{&client, &greffon, &passerelle};
    DemandesAgent demandes{&passerelle};
    DiscussionViewModel discussion{&passerelle, &flux};
    bool enCours = false;
    qint64 seq = 0;

    Banc()
    {
        serveur.installerAuthentification();
        serveur.activerPasserelle();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
        flux.setIntervalleFond(std::chrono::hours(1));
        serveur.route("GET", QStringLiteral("/api/plugins/acp-poste/v1/projets"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, QJsonObject{}); });
        passerelle.setRecul(Backoff(std::chrono::milliseconds(20), std::chrono::milliseconds(40), 0));

        serveur.methodes.insert(QStringLiteral("session.list"), [](const QJsonObject &) {
            return QJsonObject{{QStringLiteral("sessions"), QJsonArray{
                QJsonObject{{QStringLiteral("id"), QStringLiteral("s1")}, {QStringLiteral("title"), QStringLiteral("Plan du site")},
                            {QStringLiteral("preview"), QStringLiteral("Faisons le plan")}, {QStringLiteral("started_at"), 1790300000.5},
                            {QStringLiteral("message_count"), 3}, {QStringLiteral("source"), QStringLiteral("tui")}},
                QJsonObject{{QStringLiteral("id"), QStringLiteral("s2")}, {QStringLiteral("title"), QString()},
                            {QStringLiteral("preview"), QString()}, {QStringLiteral("started_at"), 1790200000},
                            {QStringLiteral("message_count"), 0}, {QStringLiteral("source"), QString()}},
                QJsonObject{{QStringLiteral("title"), QStringLiteral("sans identifiant")}}}}};
        });
        serveur.methodes.insert(QStringLiteral("session.resume"), [this](const QJsonObject &params) {
            QJsonObject resultat{
                {QStringLiteral("session_id"), QStringLiteral("rt-") + params.value(QStringLiteral("session_id")).toString()},
                {QStringLiteral("message_count"), 3},
                {QStringLiteral("messages"), QJsonArray{
                    QJsonObject{{QStringLiteral("role"), QStringLiteral("user")}, {QStringLiteral("text"), QStringLiteral("Bonjour")},
                                {QStringLiteral("timestamp"), 1790300001.25}},
                    QJsonObject{{QStringLiteral("role"), QStringLiteral("assistant")},
                                {QStringLiteral("text"), QStringLiteral("Bonjour, que puis-je faire ?")}},
                    QJsonObject{{QStringLiteral("role"), QStringLiteral("tool")}, {QStringLiteral("name"), QStringLiteral("terminal")},
                                {QStringLiteral("text"), QStringLiteral("SORTIE-SECRETE")}}}},
                {QStringLiteral("info"), QJsonObject{{QStringLiteral("title"), QStringLiteral("Plan du site")}}},
                {QStringLiteral("running"), enCours},
            };
            if (enCours) {
                resultat.insert(QStringLiteral("inflight"), QJsonObject{{QStringLiteral("assistant"), QStringLiteral("Réponse partielle")},
                                                                        {QStringLiteral("streaming"), true}});
            }
            return resultat;
        });
        serveur.methodes.insert(QStringLiteral("session.create"), [](const QJsonObject &) {
            return QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-nouvelle")},
                               {QStringLiteral("stored_session_id"), QStringLiteral("s-nouvelle")},
                               {QStringLiteral("message_count"), 0}, {QStringLiteral("messages"), QJsonArray{}},
                               {QStringLiteral("info"), QJsonObject{}}};
        });
        serveur.methodes.insert(QStringLiteral("prompt.submit"),
                                [](const QJsonObject &) { return QJsonObject{{QStringLiteral("status"), QStringLiteral("streaming")}}; });
        serveur.methodes.insert(QStringLiteral("session.interrupt"),
                                [](const QJsonObject &) { return QJsonObject{{QStringLiteral("status"), QStringLiteral("interrupted")}}; });
        serveur.methodes.insert(QStringLiteral("session.close"),
                                [](const QJsonObject &) { return QJsonObject{{QStringLiteral("closed"), true}}; });
    }

    void ouvrirPasserelle()
    {
        QSignalSpy prete(&passerelle, &GatewayClient::prete);
        passerelle.ouvrir();
        if (!prete.wait(10000)) {
            qFatal("passerelle jamais prête");
        }
        flux.demarrer();
    }

    void ouvrirSession(const QString &stockee = QStringLiteral("s1"))
    {
        discussion.ouvrir(stockee);
        if (!QTest::qWaitFor([this] { return !discussion.ouverture() && !discussion.sessionVivante().isEmpty(); }, 5000)) {
            qFatal("session jamais ouverte");
        }
    }

    void evenement(const QString &type, const QJsonObject &payload, const QString &session = QStringLiteral("rt-s1"))
    {
        serveur.envoyer(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                                    {QStringLiteral("method"), QStringLiteral("event")},
                                    {QStringLiteral("params"), QJsonObject{{QStringLiteral("type"), type},
                                                                           {QStringLiteral("session_id"), session},
                                                                           {QStringLiteral("seq"), ++seq},
                                                                           {QStringLiteral("payload"), payload}}}});
    }

    void requete(const QString &id, const QString &methode, const QJsonObject &params)
    {
        serveur.envoyer(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")}, {QStringLiteral("id"), id},
                                    {QStringLiteral("method"), methode}, {QStringLiteral("params"), params}});
    }

    QJsonObject derniereLigne() const
    {
        return discussion.transcription()->itemAt(discussion.transcription()->count() - 1);
    }

    //! Réponse du client à une requête serveur (`{id, result|error}`), ou objet vide.
    QJsonObject reponseA(const QString &id) const
    {
        for (const QJsonObject &trame : serveur.tramesRecues) {
            if (trame.value(QStringLiteral("id")).toString() == id && !trame.contains(QStringLiteral("method"))) {
                return trame;
            }
        }
        return {};
    }

    QString texteDeTranscription() const
    {
        QString texte;
        for (int index = 0; index < discussion.transcription()->count(); ++index) {
            texte += QString::fromUtf8(QJsonDocument(discussion.transcription()->itemAt(index)).toJson()) + QLatin1Char('\n');
        }
        return texte;
    }
};

} // namespace

class TestDiscussion : public QObject
{
    Q_OBJECT

private slots:
    void lignesDeSessionEtDeTranscription();
    void messagesEtIssues();
    void listeEtOuverture();
    void discussionsEnAttenteMarqueesDansLaListe();
    void fluxDUnTourSansContenuBrut();
    void autreSessionIgnoreeEtTypesInconnusComptes();
    void erreurInterruptionEtEchec();
    void envoiRefuseGardeLeMessage();
    void nouvelleFermeLaPrecedenteSeulementInactive();
    void titreEtSessionsChanged();
    void approbationDepuisLesChoixOfferts();
    void clarificationsSimpleMultipleEtLot();
    void retraitParHermesEtCoupure();
    void secretToujoursRefuse();
};

void TestDiscussion::lignesDeSessionEtDeTranscription()
{
    const QJsonObject sansTitre = DiscussionViewModel::construireSession(
        QJsonObject{{QStringLiteral("id"), QStringLiteral("s2")}, {QStringLiteral("title"), QStringLiteral("  ")}});
    QCOMPARE(sansTitre.value(QStringLiteral("titre")).toString(), QStringLiteral("Sans titre"));
    QCOMPARE(sansTitre.value(QStringLiteral("messages")).toString(), QStringLiteral("Inconnu"));
    QVERIFY(DiscussionViewModel::construireSession(QJsonObject{{QStringLiteral("title"), QStringLiteral("x")}}).isEmpty());

    const QJsonObject outil = DiscussionViewModel::construireMessage(
        QJsonObject{{QStringLiteral("role"), QStringLiteral("tool")}, {QStringLiteral("name"), QStringLiteral("terminal")},
                    {QStringLiteral("text"), QStringLiteral("SORTIE-SECRETE")},
                    {QStringLiteral("args"), QJsonObject{{QStringLiteral("command"), QStringLiteral("cat ARGUMENT-SECRET")}}}},
        0);
    QCOMPARE(outil.value(QStringLiteral("texte")).toString(), QStringLiteral("Outil « terminal »"));
    QCOMPARE(outil.value(QStringLiteral("role")).toString(), QStringLiteral("outil"));
    QVERIFY(!QJsonDocument(outil).toJson().contains("SECRET"));

    const QJsonObject vous = DiscussionViewModel::construireMessage(
        QJsonObject{{QStringLiteral("role"), QStringLiteral("user")}, {QStringLiteral("text"), QStringLiteral("<b>Bonjour</b>")}}, 1);
    QCOMPARE(vous.value(QStringLiteral("auteur")).toString(), QStringLiteral("Vous"));
    QCOMPARE(vous.value(QStringLiteral("texte")).toString(), QStringLiteral("<b>Bonjour</b>")); // texte brut, tel quel
    const QJsonObject autre = DiscussionViewModel::construireMessage(QJsonObject{{QStringLiteral("role"), QStringLiteral("developer")}}, 2);
    QCOMPARE(autre.value(QStringLiteral("auteur")).toString(), QStringLiteral("developer"));
    QCOMPARE(autre.value(QStringLiteral("role")).toString(), QStringLiteral("autre"));
}

void TestDiscussion::messagesEtIssues()
{
    QCOMPARE(DiscussionViewModel::messageEnvoi(QStringLiteral("streaming")), QStringLiteral("Message envoyé : Hermes répond."));
    QCOMPARE(DiscussionViewModel::messageEnvoi(QStringLiteral("queued")),
             QStringLiteral("Message mis en file : Hermes le traitera après le tour en cours."));
    QCOMPARE(DiscussionViewModel::messageEnvoi(QStringLiteral("steered")),
             QStringLiteral("Message transmis à Hermes pendant le tour en cours."));
    QCOMPARE(DiscussionViewModel::messageEnvoi(QJsonValue()), QStringLiteral("Message envoyé."));
    QCOMPARE(DiscussionViewModel::issueDuTour(QJsonObject{{QStringLiteral("status"), QStringLiteral("complete")}}), QString());
    QCOMPARE(DiscussionViewModel::issueDuTour(QJsonObject{{QStringLiteral("status"), QStringLiteral("interrupted")}}),
             QStringLiteral("Tour interrompu."));
    QCOMPARE(DiscussionViewModel::issueDuTour(QJsonObject{{QStringLiteral("status"), QStringLiteral("error")},
                                                          {QStringLiteral("failure_reason"), QStringLiteral("quota épuisé")}}),
             QStringLiteral("Tour en échec : quota épuisé"));
    QCOMPARE(DiscussionViewModel::issueDuTour(QJsonObject{{QStringLiteral("status"), QStringLiteral("error")}}),
             QStringLiteral("Tour en échec (raison non donnée par Hermes)."));
}

void TestDiscussion::listeEtOuverture()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.discussion.setPageVisible(true);
    QTRY_VERIFY(banc.discussion.sessionsLues());
    QCOMPARE(banc.discussion.sessions()->count(), 2); // la ligne sans identifiant est écartée
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.list")).first().value(QStringLiteral("params")).toObject(),
             (QJsonObject{{QStringLiteral("limit"), 50}}));
    QCOMPARE(banc.discussion.sessions()->itemAt(1).value(QStringLiteral("titre")).toString(), QStringLiteral("Sans titre"));

    banc.ouvrirSession();
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.resume")).first().value(QStringLiteral("params")).toObject(),
             (QJsonObject{{QStringLiteral("session_id"), QStringLiteral("s1")}}));
    QCOMPARE(banc.discussion.sessionOuverte(), QStringLiteral("s1"));
    QCOMPARE(banc.discussion.sessionVivante(), QStringLiteral("rt-s1"));
    QCOMPARE(banc.discussion.titreSession(), QStringLiteral("Plan du site"));
    QCOMPARE(banc.discussion.transcription()->count(), 3);
    QCOMPARE(banc.discussion.transcription()->itemAt(0).value(QStringLiteral("auteur")).toString(), QStringLiteral("Vous"));
    QCOMPARE(banc.discussion.transcription()->itemAt(1).value(QStringLiteral("auteur")).toString(), QStringLiteral("Hermes"));
    QCOMPARE(banc.discussion.transcription()->itemAt(2).value(QStringLiteral("texte")).toString(), QStringLiteral("Outil « terminal »"));
    QVERIFY(!banc.texteDeTranscription().contains(QStringLiteral("SORTIE-SECRETE")));
    QVERIFY(!banc.discussion.tourEnCours());
}

// Seconde relecture de P8b (constat desktop-11) : la liste des discussions du navigateur (Liste.tsx, P7) marque « En
// attente d'une réponse » chaque discussion dont une demande attend (session.active_list) et dit quand cet état n'a pas
// pu être lu ; celle de la station n'en montrait rien. Même suivi : même marque, même avertissement.
void TestDiscussion::discussionsEnAttenteMarqueesDansLaListe()
{
    Banc banc;
    banc.serveur.methodes.insert(QStringLiteral("session.active_list"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{
            QJsonObject{{QStringLiteral("session_key"), QStringLiteral("s2")}, {QStringLiteral("status"), QStringLiteral("waiting")}},
            QJsonObject{{QStringLiteral("session_key"), QStringLiteral("s1")}, {QStringLiteral("status"), QStringLiteral("working")}}}}};
    });
    banc.ouvrirPasserelle();
    banc.discussion.setPageVisible(true);
    QTRY_COMPARE(banc.discussion.sessions()->count(), 2);
    // La page lit elle-même l'état d'attente avec sa liste, comme la page web (lireDiscussionsEnAttente).
    QTRY_VERIFY(banc.flux.discussions()->connues());
    QTRY_VERIFY(banc.discussion.sessions()->get(1).value(QStringLiteral("enAttente")).toBool()); // s2
    QCOMPARE(banc.discussion.sessions()->get(1).value(QStringLiteral("id")).toString(), QStringLiteral("s2"));
    QCOMPARE(banc.discussion.sessions()->get(0).value(QStringLiteral("enAttente")).toBool(), false); // s1 travaille
    QCOMPARE(banc.discussion.property("attenteInconnue").toString(), QString());

    // Méthode refusée par Hermes : l'état est inconnu ; aucune marque, et l'absence de marque est dite sans valeur.
    banc.serveur.methodes.remove(QStringLiteral("session.active_list"));
    banc.discussion.actualiserSessions();
    QTRY_VERIFY(!banc.flux.discussions()->connues());
    // Le texte même de la page web (T.discussion.attenteInconnue) : français, sans le message brut de Hermes.
    QTRY_COMPARE(banc.discussion.property("attenteInconnue").toString(),
                 QStringLiteral("Discussions en attente : état inconnu (le tableau de bord n'a pas pu être interrogé) ; "
                                "l'absence de la marque « En attente d'une réponse » ne veut rien dire."));
    QCOMPARE(banc.discussion.sessions()->get(1).value(QStringLiteral("enAttente")).toBool(), false);
    QCOMPARE(banc.discussion.sessions()->count(), 2); // la liste, elle, reste
    // Oubli (session perdue) : rien n'est dit tant qu'aucune lecture n'a été tentée.
    banc.flux.discussions()->oublier();
    QVERIFY(!banc.flux.discussions()->tentee());
    QCOMPARE(banc.discussion.property("attenteInconnue").toString(), QString());
}

void TestDiscussion::fluxDUnTourSansContenuBrut()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    QVERIFY(banc.discussion.envoyer(QStringLiteral("Fais le plan")));
    // Le message apparaît aussitôt, avec son état réel d'envoi.
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("auteur")).toString(), QStringLiteral("Vous"));
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("statut")).toString(), QStringLiteral("Envoi…"));
    QTRY_VERIFY(!banc.discussion.gesteEnCours());
    QCOMPARE(banc.discussion.messageGeste(), QStringLiteral("Message envoyé : Hermes répond."));
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("statut")).toString(), QString());
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("prompt.submit")).first().value(QStringLiteral("params")).toObject(),
             (QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("text"), QStringLiteral("Fais le plan")}}));

    const int avant = banc.discussion.transcription()->count();
    banc.evenement(QStringLiteral("message.start"), {});
    QTRY_VERIFY(banc.discussion.tourEnCours());
    banc.evenement(QStringLiteral("status.update"), QJsonObject{{QStringLiteral("kind"), QStringLiteral("status")},
                                                                {QStringLiteral("text"), QStringLiteral("Réflexion…")}});
    banc.evenement(QStringLiteral("message.delta"), QJsonObject{{QStringLiteral("text"), QStringLiteral("Voici ")}});
    banc.evenement(QStringLiteral("tool.start"), QJsonObject{{QStringLiteral("tool_id"), QStringLiteral("t1")},
                                                             {QStringLiteral("name"), QStringLiteral("terminal")},
                                                             {QStringLiteral("args"), QJsonObject{{QStringLiteral("command"), QStringLiteral("cat ARGUMENT-SECRET")}}},
                                                             {QStringLiteral("args_text"), QStringLiteral("ARGUMENT-SECRET")}});
    banc.evenement(QStringLiteral("message.delta"), QJsonObject{{QStringLiteral("text"), QStringLiteral("le plan.")}});
    QTRY_COMPARE(banc.discussion.ligneEtat(), QStringLiteral("Réflexion…"));
    QTRY_COMPARE(banc.discussion.transcription()->count(), avant + 2);
    QJsonObject reponse = banc.discussion.transcription()->itemAt(avant);
    QTRY_COMPARE(banc.discussion.transcription()->itemAt(avant).value(QStringLiteral("texte")).toString(), QStringLiteral("Voici le plan."));
    QCOMPARE(banc.discussion.transcription()->itemAt(avant).value(QStringLiteral("enCours")).toBool(), true);
    QCOMPARE(banc.discussion.transcription()->itemAt(avant + 1).value(QStringLiteral("texte")).toString(),
             QStringLiteral("Outil « terminal » en cours…"));

    banc.evenement(QStringLiteral("tool.complete"), QJsonObject{{QStringLiteral("tool_id"), QStringLiteral("t1")},
                                                                {QStringLiteral("name"), QStringLiteral("terminal")},
                                                                {QStringLiteral("summary"), QStringLiteral("2 fichiers lus")},
                                                                {QStringLiteral("duration_s"), 1.5},
                                                                {QStringLiteral("result"), QStringLiteral("RESULTAT-SECRET")},
                                                                {QStringLiteral("result_text"), QStringLiteral("RESULTAT-SECRET")}});
    banc.evenement(QStringLiteral("message.complete"), QJsonObject{{QStringLiteral("text"), QStringLiteral("Voici le plan final.")},
                                                                   {QStringLiteral("status"), QStringLiteral("complete")},
                                                                   {QStringLiteral("warning"), QStringLiteral("Contexte presque plein")}});
    QTRY_VERIFY(!banc.discussion.tourEnCours());
    reponse = banc.discussion.transcription()->itemAt(avant);
    QCOMPARE(reponse.value(QStringLiteral("texte")).toString(), QStringLiteral("Voici le plan final."));
    QCOMPARE(reponse.value(QStringLiteral("enCours")).toBool(), false);
    QCOMPARE(reponse.value(QStringLiteral("statut")).toString(), QString());
    QCOMPARE(reponse.value(QStringLiteral("avertissement")).toString(), QStringLiteral("Contexte presque plein"));
    QCOMPARE(banc.discussion.transcription()->itemAt(avant + 1).value(QStringLiteral("texte")).toString(),
             QStringLiteral("Outil « terminal » : 2 fichiers lus (1,5 s)"));
    QCOMPARE(banc.discussion.ligneEtat(), QString()); // la ligne d'état est éphémère
    QCOMPARE(banc.discussion.transcription()->count(), avant + 2);
    QVERIFY2(!banc.texteDeTranscription().contains(QStringLiteral("SECRET")), "ni arguments ni sortie bruts d'un outil");
}

void TestDiscussion::autreSessionIgnoreeEtTypesInconnusComptes()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    const int avant = banc.discussion.transcription()->count();
    banc.evenement(QStringLiteral("message.start"), {}, QStringLiteral("rt-autre"));
    banc.evenement(QStringLiteral("message.delta"), QJsonObject{{QStringLiteral("text"), QStringLiteral("intrus")}}, QStringLiteral("rt-autre"));
    banc.evenement(QStringLiteral("reasoning.delta"), QJsonObject{{QStringLiteral("text"), QStringLiteral("pensée")}});
    banc.evenement(QStringLiteral("session.info"), QJsonObject{{QStringLiteral("model"), QStringLiteral("x")}});
    QTRY_COMPARE(banc.discussion.evenementsIgnores(), 1);
    QCOMPARE(banc.discussion.transcription()->count(), avant);
    QVERIFY(!banc.discussion.tourEnCours());
    QVERIFY(!banc.texteDeTranscription().contains(QStringLiteral("intrus")));
}

void TestDiscussion::erreurInterruptionEtEchec()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.evenement(QStringLiteral("error"), QJsonObject{{QStringLiteral("message"), QStringLiteral("Model switch failed")}});
    QTRY_COMPARE(banc.discussion.erreurSession(), QStringLiteral("Model switch failed"));
    banc.evenement(QStringLiteral("notice"), QJsonObject{{QStringLiteral("message"), QStringLiteral("Capacités rafraîchies")}});
    QTRY_COMPARE(banc.discussion.avis(), QStringLiteral("Capacités rafraîchies"));

    banc.evenement(QStringLiteral("message.start"), {});
    QTRY_VERIFY(banc.discussion.tourEnCours());
    banc.discussion.arreter();
    QTRY_COMPARE(banc.discussion.messageGeste(), QStringLiteral("Arrêt demandé à Hermes."));
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.interrupt")).first().value(QStringLiteral("params")).toObject(),
             (QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}}));
    banc.evenement(QStringLiteral("message.complete"), QJsonObject{{QStringLiteral("text"), QString()},
                                                                   {QStringLiteral("status"), QStringLiteral("interrupted")}});
    QTRY_VERIFY(!banc.discussion.tourEnCours());
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("statut")).toString(), QStringLiteral("Tour interrompu."));

    banc.evenement(QStringLiteral("message.complete"), QJsonObject{{QStringLiteral("status"), QStringLiteral("error")},
                                                                   {QStringLiteral("error"), QStringLiteral("quota épuisé")}});
    QTRY_COMPARE(banc.derniereLigne().value(QStringLiteral("statut")).toString(), QStringLiteral("Tour en échec : quota épuisé"));
}

void TestDiscussion::envoiRefuseGardeLeMessage()
{
    Banc banc;
    // Aucune session ouverte : refus local, le texte reste dans la zone de saisie.
    QVERIFY(!banc.discussion.envoyer(QStringLiteral("Bonjour")));
    QCOMPARE(banc.discussion.erreurGeste(), QStringLiteral("Ouvrez ou créez une discussion avant d'écrire."));

    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    QVERIFY(!banc.discussion.envoyer(QStringLiteral("   ")));
    banc.serveur.methodes.remove(QStringLiteral("prompt.submit")); // Hermes répond -32601
    QVERIFY(banc.discussion.envoyer(QStringLiteral("Bonjour")));
    QTRY_VERIFY(!banc.discussion.gesteEnCours());
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("statut")).toString(), QStringLiteral("Non envoyé"));
    QVERIFY(banc.discussion.erreurGeste().startsWith(QStringLiteral("Hermes a refusé « prompt.submit »")));
    QVERIFY(banc.discussion.erreurGeste().contains(QStringLiteral("-32601")));
}

void TestDiscussion::nouvelleFermeLaPrecedenteSeulementInactive()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.discussion.setPageVisible(true);
    banc.ouvrirSession();
    const int listes = static_cast<int>(banc.serveur.tramesDeMethode(QStringLiteral("session.list")).size());
    banc.discussion.nouvelle();
    QTRY_COMPARE(banc.discussion.sessionVivante(), QStringLiteral("rt-nouvelle"));
    QCOMPARE(banc.discussion.sessionOuverte(), QStringLiteral("s-nouvelle"));
    QCOMPARE(banc.discussion.transcription()->count(), 0);
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.create")).first().value(QStringLiteral("params")).toObject(), QJsonObject{});
    QTRY_COMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.close")).size(), 1);
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.close")).first().value(QStringLiteral("params")).toObject(),
             (QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}}));
    QTRY_VERIFY(banc.serveur.tramesDeMethode(QStringLiteral("session.list")).size() > listes);

    // Session dont un tour tourne : reprise du tour en vol, et jamais fermée par la station.
    banc.enCours = true;
    banc.ouvrirSession(QStringLiteral("s2"));
    QVERIFY(banc.discussion.tourEnCours());
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("texte")).toString(), QStringLiteral("Réponse partielle"));
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("enCours")).toBool(), true);
    QTRY_COMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.close")).size(), 2); // rt-nouvelle, inactive
    banc.discussion.quitter();
    QTest::qWait(150);
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.close")).size(), 2);
    QCOMPARE(banc.discussion.sessionVivante(), QString());
}

void TestDiscussion::titreEtSessionsChanged()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.discussion.setPageVisible(true);
    banc.ouvrirSession();
    banc.evenement(QStringLiteral("session.title"), QJsonObject{{QStringLiteral("session_id"), QStringLiteral("s1")},
                                                                {QStringLiteral("title"), QStringLiteral("Nouveau titre")}});
    QTRY_COMPARE(banc.discussion.titreSession(), QStringLiteral("Nouveau titre"));
    const int listes = static_cast<int>(banc.serveur.tramesDeMethode(QStringLiteral("session.list")).size());
    banc.serveur.envoyer(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")}, {QStringLiteral("method"), QStringLiteral("event")},
                                     {QStringLiteral("params"), QJsonObject{{QStringLiteral("type"), QStringLiteral("sessions.changed")},
                                                                            {QStringLiteral("payload"), QJsonObject{}}}}});
    QTRY_COMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.list")).size(), listes + 1);
}

void TestDiscussion::approbationDepuisLesChoixOfferts()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.requete(QStringLiteral("srq-1"), QStringLiteral("approval"),
                 QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("request_id"), QStringLiteral("r1")},
                             {QStringLiteral("command"), QStringLiteral("rm -rf /tmp/essai")},
                             {QStringLiteral("description"), QStringLiteral("Suppression récursive")},
                             {QStringLiteral("tool_name"), QStringLiteral("terminal")},
                             {QStringLiteral("choices"), QJsonArray{QStringLiteral("once"), QStringLiteral("session"),
                                                                    QStringLiteral("deny"), QStringLiteral("forever")}}});
    QTRY_COMPARE(banc.demandes.nombre(), 1);
    const QJsonObject demande = banc.demandes.demandes()->itemAt(0);
    QCOMPARE(demande.value(QStringLiteral("sessionId")).toString(), QStringLiteral("rt-s1"));
    QCOMPARE(demande.value(QStringLiteral("commande")).toString(), QStringLiteral("rm -rf /tmp/essai"));
    QCOMPARE(demande.value(QStringLiteral("outil")).toString(), QStringLiteral("terminal"));
    const QJsonArray choix = demande.value(QStringLiteral("choix")).toArray();
    QCOMPARE(choix.size(), 3); // « forever » n'est pas un choix connu : aucun bouton
    QCOMPARE(choix.at(0).toObject().value(QStringLiteral("libelle")).toString(), QStringLiteral("Autoriser une fois"));
    QCOMPARE(choix.at(2).toObject().value(QStringLiteral("libelle")).toString(), QStringLiteral("Refuser"));

    // Choix non offert : refusé par la station, aucune trame.
    QVERIFY(!banc.demandes.approuver(QStringLiteral("srq-1"), QStringLiteral("always")));
    QCOMPARE(banc.demandes.erreur(), QStringLiteral("Ce choix n'est pas offert par Hermes pour cette demande."));
    QTest::qWait(100);
    QVERIFY(banc.reponseA(QStringLiteral("srq-1")).isEmpty());
    QCOMPARE(banc.demandes.nombre(), 1);

    QVERIFY(banc.demandes.approuver(QStringLiteral("srq-1"), QStringLiteral("once")));
    QTRY_VERIFY(!banc.reponseA(QStringLiteral("srq-1")).isEmpty());
    QCOMPARE(banc.reponseA(QStringLiteral("srq-1")).value(QStringLiteral("result")).toObject(),
             (QJsonObject{{QStringLiteral("choice"), QStringLiteral("once")}}));
    QCOMPARE(banc.demandes.nombre(), 0);
    QCOMPARE(banc.demandes.message(), QStringLiteral("Décision transmise à Hermes : autoriser une fois."));
    // Une seconde réponse est refusée : la demande n'est plus ouverte.
    QVERIFY(!banc.demandes.approuver(QStringLiteral("srq-1"), QStringLiteral("once")));
}

void TestDiscussion::clarificationsSimpleMultipleEtLot()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.requete(QStringLiteral("srq-2"), QStringLiteral("clarify"),
                 QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("question"), QStringLiteral("Quel nom ?")},
                             {QStringLiteral("choices"), QJsonArray{QStringLiteral("a"), QStringLiteral("b")}}});
    banc.requete(QStringLiteral("srq-3"), QStringLiteral("clarify"),
                 QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("question"), QStringLiteral("Quelles cibles ?")},
                             {QStringLiteral("choices"), QJsonArray{QStringLiteral("staging"), QStringLiteral("prod"), QStringLiteral("dev")}},
                             {QStringLiteral("multi_select"), true}});
    banc.requete(QStringLiteral("srq-4"), QStringLiteral("clarify"),
                 QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")},
                             {QStringLiteral("questions"), QJsonArray{
                                 QJsonObject{{QStringLiteral("qid"), QStringLiteral("q1")}, {QStringLiteral("question"), QStringLiteral("Langue ?")}},
                                 QJsonObject{{QStringLiteral("qid"), QStringLiteral("q2")}, {QStringLiteral("question"), QStringLiteral("Licence ?")},
                                             {QStringLiteral("choices"), QJsonArray{QStringLiteral("MIT")}}}}},
                             {QStringLiteral("answers"), QJsonObject{{QStringLiteral("q1"), QStringLiteral("français")}}}});
    QTRY_COMPARE(banc.demandes.nombre(), 3);
    const QJsonObject lot = banc.demandes.demandes()->itemAt(2);
    QCOMPARE(lot.value(QStringLiteral("estLot")).toBool(), true);
    QCOMPARE(lot.value(QStringLiteral("lot")).toArray().at(0).toObject().value(QStringLiteral("verrouillee")).toString(), QStringLiteral("français"));

    QVERIFY(banc.demandes.clarifier(QStringLiteral("srq-2"), QStringLiteral("  b ")));
    QTRY_COMPARE(banc.reponseA(QStringLiteral("srq-2")).value(QStringLiteral("result")).toObject(),
                 (QJsonObject{{QStringLiteral("answer"), QStringLiteral("b")}}));

    QVERIFY(!banc.demandes.clarifierSelection(QStringLiteral("srq-3"), {QStringLiteral("staging"), QStringLiteral("qa")}));
    QVERIFY(!banc.demandes.clarifierSelection(QStringLiteral("srq-3"), {}));
    QVERIFY(banc.demandes.clarifierSelection(QStringLiteral("srq-3"), {QStringLiteral("staging"), QStringLiteral("prod")}));
    QTRY_COMPARE(banc.reponseA(QStringLiteral("srq-3")).value(QStringLiteral("result")).toObject(),
                 (QJsonObject{{QStringLiteral("answer"), QStringLiteral("[\"staging\",\"prod\"]")}}));

    QVERIFY(!banc.demandes.clarifierLot(QStringLiteral("srq-4"), QVariantMap{{QStringLiteral("q1"), QStringLiteral("français")}}));
    QCOMPARE(banc.demandes.erreur(), QStringLiteral("Chaque question du lot attend une réponse (vide pour la passer)."));
    QVERIFY(banc.demandes.clarifierLot(QStringLiteral("srq-4"), QVariantMap{{QStringLiteral("q1"), QStringLiteral("français")},
                                                                            {QStringLiteral("q2"), QString()}}));
    QTRY_COMPARE(banc.reponseA(QStringLiteral("srq-4")).value(QStringLiteral("result")).toObject(),
                 (QJsonObject{{QStringLiteral("answers"), QJsonObject{{QStringLiteral("q1"), QStringLiteral("français")},
                                                                      {QStringLiteral("q2"), QString()}}}}));
    QCOMPARE(banc.demandes.nombre(), 0);
}

void TestDiscussion::retraitParHermesEtCoupure()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.requete(QStringLiteral("srq-5"), QStringLiteral("clarify"),
                 QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("question"), QStringLiteral("Encore là ?")}});
    QTRY_COMPARE(banc.demandes.nombre(), 1);
    banc.evenement(QStringLiteral("request.cancel"), QJsonObject{{QStringLiteral("id"), QStringLiteral("srq-5")},
                                                                 {QStringLiteral("method"), QStringLiteral("clarify")},
                                                                 {QStringLiteral("reason"), QStringLiteral("timeout")}});
    QTRY_COMPARE(banc.demandes.nombre(), 0);
    QCOMPARE(banc.demandes.message(), QStringLiteral("Demande retirée par Hermes (timeout)."));

    // Coupure : les demandes ouvertes appartenaient à la connexion perdue ; la liste est vidée.
    banc.requete(QStringLiteral("srq-6"), QStringLiteral("clarify"),
                 QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("question"), QStringLiteral("Et là ?")}});
    QTRY_COMPARE(banc.demandes.nombre(), 1);
    banc.serveur.couperClient();
    QTRY_COMPARE(banc.demandes.nombre(), 0);
    QVERIFY(!banc.demandes.clarifier(QStringLiteral("srq-6"), QStringLiteral("oui")));
}

void TestDiscussion::secretToujoursRefuse()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.requete(QStringLiteral("srq-7"), QStringLiteral("secret"),
                 QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("env_var"), QStringLiteral("OPENAI_API_KEY")},
                             {QStringLiteral("prompt"), QStringLiteral("Clé ?")}});
    QTRY_VERIFY(!banc.reponseA(QStringLiteral("srq-7")).isEmpty());
    QCOMPARE(banc.reponseA(QStringLiteral("srq-7")).value(QStringLiteral("error")).toObject().value(QStringLiteral("code")).toInt(),
             JsonRpcChannel::kMethodeIntrouvable);
    QCOMPARE(banc.demandes.nombre(), 0);
}

QTEST_MAIN(TestDiscussion)
#include "tst_discussion.moc"
