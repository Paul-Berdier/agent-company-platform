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

// Transport déterministe pour inverser de vraies réponses JSON-RPC sans délai ni processus.
struct CanalManuel
{
    JsonRpcChannel *canal;
    QList<QJsonObject> trames;
    explicit CanalManuel(GatewayClient &passerelle) : canal(passerelle.canal())
    {
        canal->attacher([this](const QByteArray &texte) {
            trames.append(QJsonDocument::fromJson(texte).object());
            return true;
        });
    }
    ~CanalManuel() { canal->detacher(QStringLiteral("Fin du scénario déterministe")); }
    QJsonObject derniere(const QString &methode) const
    {
        for (auto i = trames.crbegin(); i != trames.crend(); ++i)
            if (i->value(QStringLiteral("method")).toString() == methode) return *i;
        return {};
    }
    void repondre(const QJsonObject &requete, const QJsonValue &resultat)
    {
        canal->recevoir(QJsonDocument(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
            {QStringLiteral("id"), requete.value(QStringLiteral("id"))}, {QStringLiteral("result"), resultat}}).toJson(QJsonDocument::Compact));
    }
    void refuser(const QJsonObject &requete)
    {
        canal->recevoir(QJsonDocument(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
            {QStringLiteral("id"), requete.value(QStringLiteral("id"))}, {QStringLiteral("error"), QJsonObject{
                {QStringLiteral("code"), 5007}, {QStringLiteral("message"), QStringLiteral("Refus de test")}}}}).toJson(QJsonDocument::Compact));
    }
};

} // namespace

class TestDiscussion : public QObject
{
    Q_OBJECT

private slots:
    void lignesDeSessionEtDeTranscription();
    void messagesEtIssues();
    void brouillonsIsolesEtOublies();
    void listeEtOuverture();
    void discussionsEnAttenteMarqueesDansLaListe();
    void fluxDUnTourSansContenuBrut();
    void autreSessionIgnoreeEtTypesInconnusComptes();
    void erreurInterruptionEtEchec();
    void envoiRefuseGardeLeMessage();
    void coupureConserveLeTexteSansConfirmerSonRefus();
    void refusRestaureLeBrouillonApresNavigation();
    void refusTardifConserveLesSaisies_data();
    void refusTardifConserveLesSaisies();
    void succesTardifNeRestaurePasLeTexteEnvoye();
    void refusApresOubliNeRessuscitePasLeTexte();
    void nouvelleFermeLaPrecedenteSeulementInactive();
    void titreEtSessionsChanged();
    void approbationDepuisLesChoixOfferts();
    void clarificationsSimpleMultipleEtLot();
    void retraitParHermesEtCoupure();
    void secretToujoursRefuse();
    void rechercheEtChargementBornes();
    void listesInverseesEtOubli();
    void titreEtCopieConfirmeesParHermes();
    void gestesTardifsEtInfosIsolees();
    void choixModeleEtConfirmationDeCout();
    void modelesTardifsEtDonneesIllisibles();
    void consignesPrepareesSansEnvoi();
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

void TestDiscussion::coupureConserveLeTexteSansConfirmerSonRefus()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    CanalManuel manuel(banc.passerelle);
    banc.discussion.setBrouillon(QStringLiteral("Consigne sans accusé"));
    QVERIFY(banc.discussion.envoyer(banc.discussion.brouillon()));
    QVERIFY(banc.discussion.brouillon().isEmpty());
    banc.discussion.setBrouillon(QStringLiteral("Saisie après envoi"));
    const QJsonObject envoi = manuel.derniere(QStringLiteral("prompt.submit"));
    QVERIFY(!envoi.isEmpty());
    const auto tramesAvantCoupure = manuel.trames.size();

    manuel.canal->detacher(QStringLiteral("Connexion interrompue avant la réponse"));
    QVERIFY(!banc.discussion.gesteEnCours());
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("statut")).toString(), QStringLiteral("Envoi non confirmé"));
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne sans accusé\n\nSaisie après envoi"));
    QVERIFY(banc.discussion.erreurGeste().contains(QStringLiteral("Connexion interrompue avant la réponse")));
    QVERIFY(!banc.discussion.erreurGeste().contains(QStringLiteral("Hermes a refusé")));
    QCOMPARE(manuel.trames.size(), tramesAvantCoupure);

    // Un accusé reçu après la terminaison locale ne prouve pas l'état courant
    // du tour et ne doit ni effacer le brouillon conservé ni provoquer un rejeu.
    manuel.repondre(envoi, QJsonObject{{QStringLiteral("status"), QStringLiteral("accepted")}});
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("statut")).toString(), QStringLiteral("Envoi non confirmé"));
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne sans accusé\n\nSaisie après envoi"));
    QCOMPARE(manuel.trames.size(), tramesAvantCoupure);
}

void TestDiscussion::refusRestaureLeBrouillonApresNavigation()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.discussion.setBrouillon(QStringLiteral("Consigne refusée"));
    banc.serveur.methodes.remove(QStringLiteral("prompt.submit"));
    QVERIFY(banc.discussion.envoyer(banc.discussion.brouillon()));
    QVERIFY(banc.discussion.brouillon().isEmpty());
    QTRY_VERIFY(!banc.discussion.gesteEnCours());
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne refusée"));
    QCOMPARE(banc.derniereLigne().value(QStringLiteral("statut")).toString(), QStringLiteral("Non envoyé"));
    banc.ouvrirSession(QStringLiteral("s2"));
    banc.discussion.setBrouillon(QStringLiteral("Autre discussion"));
    banc.ouvrirSession();
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne refusée"));
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("prompt.submit")).size(), 1);
}

void TestDiscussion::refusTardifConserveLesSaisies_data()
{
    QTest::addColumn<bool>("retourAvantRefus");
    QTest::newRow("refus-pendant-lautre-discussion") << false;
    QTest::newRow("refus-apres-retour-a-la-discussion") << true;
}

void TestDiscussion::refusTardifConserveLesSaisies()
{
    QFETCH(bool, retourAvantRefus);
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    CanalManuel manuel(banc.passerelle);
    banc.discussion.setBrouillon(QStringLiteral("Consigne initiale"));
    QVERIFY(banc.discussion.envoyer(banc.discussion.brouillon()));
    const auto envoi = manuel.derniere(QStringLiteral("prompt.submit"));
    QVERIFY(!envoi.isEmpty());
    QVERIFY(banc.discussion.brouillon().isEmpty());
    banc.discussion.setBrouillon(QStringLiteral("Saisie plus récente"));
    banc.discussion.ouvrir(QStringLiteral("s2"));
    manuel.repondre(manuel.derniere(QStringLiteral("session.resume")), QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s2")}, {QStringLiteral("messages"), QJsonArray{}}});
    banc.discussion.setBrouillon(QStringLiteral("Brouillon indépendant B"));
    banc.discussion.renommer(QStringLiteral("Titre B"));
    const auto renommage = manuel.derniere(QStringLiteral("session.title"));
    QVERIFY(banc.discussion.gesteEnCours());
    if (retourAvantRefus) {
        banc.discussion.ouvrir(QStringLiteral("s1"));
        manuel.repondre(manuel.derniere(QStringLiteral("session.resume")), QJsonObject{
            {QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("messages"), QJsonArray{}}});
        QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Saisie plus récente"));
    }
    QSignalSpy changements(&banc.discussion, &DiscussionViewModel::brouillonChange);
    const auto tramesAvantRefus = manuel.trames.size();
    manuel.refuser(envoi);
    QCOMPARE(manuel.trames.size(), tramesAvantRefus); // aucun renvoi automatique
    QCOMPARE(changements.size(), retourAvantRefus ? 1 : 0);
    if (!retourAvantRefus) {
        QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Brouillon indépendant B"));
        QVERIFY(banc.discussion.gesteEnCours()); // le refus de A ne termine pas le renommage de B
        QVERIFY(banc.discussion.erreurGeste().isEmpty());
        manuel.repondre(renommage, QJsonObject{{QStringLiteral("title"), QStringLiteral("Titre B")}});
        banc.discussion.ouvrir(QStringLiteral("s1"));
        manuel.repondre(manuel.derniere(QStringLiteral("session.resume")), QJsonObject{
            {QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("messages"), QJsonArray{}}});
    }
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne initiale\n\nSaisie plus récente"));
    banc.discussion.ouvrir(QStringLiteral("s2"));
    manuel.repondre(manuel.derniere(QStringLiteral("session.resume")), QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s2")}, {QStringLiteral("messages"), QJsonArray{}}});
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Brouillon indépendant B"));
}

void TestDiscussion::succesTardifNeRestaurePasLeTexteEnvoye()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    CanalManuel manuel(banc.passerelle);
    banc.discussion.setBrouillon(QStringLiteral("Texte accepté"));
    QVERIFY(banc.discussion.envoyer(banc.discussion.brouillon()));
    const auto envoi = manuel.derniere(QStringLiteral("prompt.submit"));
    banc.discussion.setBrouillon(QStringLiteral("Suite non envoyée"));
    banc.discussion.ouvrir(QStringLiteral("s2"));
    manuel.repondre(manuel.derniere(QStringLiteral("session.resume")), QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s2")}, {QStringLiteral("messages"), QJsonArray{}}});
    const auto tramesAvantReponse = manuel.trames.size();
    manuel.repondre(envoi, QJsonObject{{QStringLiteral("status"), QStringLiteral("streaming")}});
    QCOMPARE(manuel.trames.size(), tramesAvantReponse);
    QVERIFY(banc.discussion.brouillon().isEmpty());
    banc.discussion.ouvrir(QStringLiteral("s1"));
    manuel.repondre(manuel.derniere(QStringLiteral("session.resume")), QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("messages"), QJsonArray{}}});
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Suite non envoyée"));
}

void TestDiscussion::refusApresOubliNeRessuscitePasLeTexte()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    CanalManuel manuel(banc.passerelle);
    banc.discussion.setBrouillon(QStringLiteral("Ancienne identité"));
    QVERIFY(banc.discussion.envoyer(banc.discussion.brouillon()));
    const auto ancienEnvoi = manuel.derniere(QStringLiteral("prompt.submit"));
    banc.discussion.oublier();
    QVERIFY(banc.discussion.brouillon().isEmpty());
    // Même identifiant stocké après oubli : une réponse de l’ancienne identité
    // ne doit pas repeupler le brouillon de la nouvelle.
    banc.discussion.ouvrir(QStringLiteral("s1"));
    manuel.repondre(manuel.derniere(QStringLiteral("session.resume")), QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("messages"), QJsonArray{}}});
    QVERIFY(banc.discussion.brouillon().isEmpty());
    banc.discussion.setBrouillon(QStringLiteral("Nouvelle identité"));
    QSignalSpy changements(&banc.discussion, &DiscussionViewModel::brouillonChange);
    const auto tramesAvantRefus = manuel.trames.size();
    manuel.refuser(ancienEnvoi);
    QCOMPARE(manuel.trames.size(), tramesAvantRefus);
    QCOMPARE(changements.size(), 0);
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Nouvelle identité"));
    QVERIFY(banc.discussion.erreurGeste().isEmpty());
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

void TestDiscussion::brouillonsIsolesEtOublies()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.discussion.setBrouillon(QStringLiteral("Consigne non envoyée A"));
    banc.ouvrirSession(QStringLiteral("s2"));
    QCOMPARE(banc.discussion.brouillon(), QString());
    banc.discussion.setBrouillon(QStringLiteral("Consigne non envoyée B"));
    banc.ouvrirSession();
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne non envoyée A"));
    banc.discussion.setBrouillon(QString());
    banc.ouvrirSession(QStringLiteral("s2"));
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne non envoyée B"));
    banc.discussion.oublier();
    banc.ouvrirSession(QStringLiteral("s2"));
    QCOMPARE(banc.discussion.brouillon(), QString());
}

void TestDiscussion::rechercheEtChargementBornes()
{
    Banc banc;
    banc.serveur.methodes.insert(QStringLiteral("session.list"), [](const QJsonObject &params) {
        QJsonArray sessions;
        for (int i = 0; i < params.value(QStringLiteral("limit")).toInt(); ++i)
            sessions.append(QJsonObject{{QStringLiteral("id"), QStringLiteral("s%1").arg(i)},
                {QStringLiteral("title"), QStringLiteral("Discussion %1").arg(i)},
                {QStringLiteral("preview"), i == 42 ? QStringLiteral("Recette spéciale") : QString()}});
        return QJsonObject{{QStringLiteral("sessions"), sessions}};
    });
    banc.ouvrirPasserelle();
    banc.discussion.actualiserSessions();
    QTRY_COMPARE(banc.discussion.sessionsChargees(), 50);
    const auto lectures = banc.serveur.tramesDeMethode(QStringLiteral("session.list")).size();
    banc.discussion.setRechercheSessions(QStringLiteral("RECETTE"));
    QCOMPARE(banc.discussion.sessions()->count(), 1);
    QCOMPARE(banc.discussion.sessions()->itemAt(0).value(QStringLiteral("id")).toString(), QStringLiteral("s42"));
    QCOMPARE(banc.discussion.sessionsChargees(), 50);
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.list")).size(), lectures);
    for (int limite = 100; limite <= 500; limite += 50) {
        QVERIFY(banc.discussion.peutChargerPlus());
        banc.discussion.chargerPlusSessions();
        QTRY_COMPARE(banc.discussion.sessionsChargees(), limite);
    }
    QVERIFY(!banc.discussion.peutChargerPlus());
    banc.discussion.chargerPlusSessions();
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.list")).last().value(QStringLiteral("params")).toObject()
                 .value(QStringLiteral("limit")).toInt(), 500);
    banc.discussion.setRechercheSessions(QString());
    QCOMPARE(banc.discussion.sessions()->count(), 500);
    banc.serveur.methodes.remove(QStringLiteral("session.list"));
    banc.discussion.actualiserSessions();
    QTRY_VERIFY(!banc.discussion.erreurSessions().isEmpty());
    QCOMPARE(banc.discussion.sessionsChargees(), 500);
    QVERIFY(!banc.discussion.chargementSessions());
}

void TestDiscussion::listesInverseesEtOubli()
{
    Banc banc;
    banc.ouvrirPasserelle();
    CanalManuel manuel(banc.passerelle);
    const auto resultat = [](const QString &id) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{QJsonObject{{QStringLiteral("id"), id}}}}};
    };
    banc.discussion.actualiserSessions();
    const auto ancienne = manuel.derniere(QStringLiteral("session.list"));
    banc.discussion.actualiserSessions();
    const auto recente = manuel.derniere(QStringLiteral("session.list"));
    manuel.repondre(recente, resultat(QStringLiteral("recente")));
    manuel.repondre(ancienne, resultat(QStringLiteral("ancienne")));
    QCOMPARE(banc.discussion.sessions()->itemAt(0).value(QStringLiteral("id")).toString(), QStringLiteral("recente"));
    banc.discussion.actualiserSessions();
    const auto avantOubli = manuel.derniere(QStringLiteral("session.list"));
    banc.discussion.setRechercheSessions(QStringLiteral("ancienne"));
    banc.discussion.oublier();
    manuel.repondre(avantOubli, resultat(QStringLiteral("serveur-oublie")));
    QCOMPARE(banc.discussion.sessions()->count(), 0);
    QVERIFY(!banc.discussion.sessionsLues());
    QVERIFY(!banc.discussion.chargementSessions());
    QVERIFY(banc.discussion.rechercheSessions().isEmpty());
}

void TestDiscussion::titreEtCopieConfirmeesParHermes()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.discussion.setBrouillon(QStringLiteral("Brouillon du parent"));
    CanalManuel manuel(banc.passerelle);
    banc.discussion.renommer(QStringLiteral("   "));
    QVERIFY(manuel.derniere(QStringLiteral("session.title")).isEmpty());
    banc.discussion.renommer(QStringLiteral("  Nouveau titre  "));
    const auto titre = manuel.derniere(QStringLiteral("session.title"));
    QCOMPARE(titre.value(QStringLiteral("params")).toObject(), (QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("title"), QStringLiteral("Nouveau titre")}}));
    QCOMPARE(banc.discussion.titreSession(), QStringLiteral("Plan du site"));
    manuel.repondre(titre, QJsonObject{{QStringLiteral("title"), QStringLiteral("Titre normalisé")}, {QStringLiteral("pending"), true}});
    QCOMPARE(banc.discussion.titreSession(), QStringLiteral("Titre normalisé"));
    QVERIFY(banc.discussion.alerteGeste());
    banc.discussion.dupliquer();
    const auto copie = manuel.derniere(QStringLiteral("session.branch_stored"));
    QCOMPARE(copie.value(QStringLiteral("params")).toObject(),
        (QJsonObject{{QStringLiteral("parent_session_id"), QStringLiteral("s1")}}));
    QCOMPARE(banc.discussion.sessionOuverte(), QStringLiteral("s1"));
    manuel.repondre(copie, QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-copie")},
        {QStringLiteral("stored_session_id"), QStringLiteral("copie")}, {QStringLiteral("messages_omitted"), true}});
    const auto reprise = manuel.derniere(QStringLiteral("session.resume"));
    QCOMPARE(reprise.value(QStringLiteral("params")).toObject().value(QStringLiteral("session_id")).toString(), QStringLiteral("copie"));
    QVERIFY(banc.discussion.ouverture());
    manuel.repondre(reprise, QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-copie")},
        {QStringLiteral("info"), QJsonObject{{QStringLiteral("title"), QStringLiteral("Copie")}}},
        {QStringLiteral("messages"), QJsonArray{QJsonObject{{QStringLiteral("role"), QStringLiteral("user")},
            {QStringLiteral("text"), QStringLiteral("Historique copié par le serveur")}}}}});
    QCOMPARE(banc.discussion.transcription()->count(), 1);
    QCOMPARE(banc.discussion.transcription()->itemAt(0).value(QStringLiteral("texte")).toString(), QStringLiteral("Historique copié par le serveur"));
    QCOMPARE(banc.discussion.brouillon(), QString());
    banc.discussion.ouvrir(QStringLiteral("s1"));
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Brouillon du parent"));
}

void TestDiscussion::gestesTardifsEtInfosIsolees()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    banc.evenement(QStringLiteral("session.info"), QJsonObject{
        {QStringLiteral("model"), QStringLiteral("modele-A")}, {QStringLiteral("provider"), QStringLiteral("route-A")},
        {QStringLiteral("profile_name"), QStringLiteral("atelier")}, {QStringLiteral("system_prompt"), QStringLiteral("SECRET")},
        {QStringLiteral("usage"), QJsonObject{{QStringLiteral("context_used"), 1200}, {QStringLiteral("context_max"), 4000},
            {QStringLiteral("context_estimated"), true}, {QStringLiteral("private"), QStringLiteral("SECRET")}}}});
    QTRY_COMPARE(banc.discussion.infosSession().value(QStringLiteral("model")).toString(), QStringLiteral("modele-A"));
    const auto infos = banc.discussion.infosSession();
    QVERIFY(!infos.contains(QStringLiteral("system_prompt")));
    QCOMPARE(infos.value(QStringLiteral("usage")).toMap().value(QStringLiteral("context_used")).toInt(), 1200);
    QVERIFY(!infos.value(QStringLiteral("usage")).toMap().contains(QStringLiteral("private")));
    CanalManuel manuel(banc.passerelle);
    banc.discussion.renommer(QStringLiteral("Ancien renommage"));
    const auto titre = manuel.derniere(QStringLiteral("session.title"));
    banc.discussion.ouvrir(QStringLiteral("s2"));
    QVERIFY(!banc.discussion.gesteEnCours());
    QVERIFY(banc.discussion.infosSession().isEmpty());
    manuel.repondre(manuel.derniere(QStringLiteral("session.resume")), QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s2")}, {QStringLiteral("messages"), QJsonArray{}},
        {QStringLiteral("info"), QJsonObject{{QStringLiteral("title"), QStringLiteral("Session B")}, {QStringLiteral("model"), QStringLiteral("modele-B")}}}});
    manuel.repondre(titre, QJsonObject{{QStringLiteral("title"), QStringLiteral("Ancien renommage")}});
    QCOMPARE(banc.discussion.titreSession(), QStringLiteral("Session B"));
    QVERIFY(banc.discussion.messageGeste().isEmpty());
    banc.discussion.renommer(QStringLiteral("Refus"));
    manuel.refuser(manuel.derniere(QStringLiteral("session.title")));
    QCOMPARE(banc.discussion.titreSession(), QStringLiteral("Session B"));
    QVERIFY(banc.discussion.erreurGeste().contains(QStringLiteral("Refus de test")));
    banc.discussion.oublier();
    QVERIFY(banc.discussion.infosSession().isEmpty());
}

void TestDiscussion::choixModeleEtConfirmationDeCout()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    CanalManuel manuel(banc.passerelle);
    banc.discussion.actualiserModeles();
    const auto inventaire = manuel.derniere(QStringLiteral("model.options"));
    QCOMPARE(inventaire.value(QStringLiteral("params")).toObject(), (QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("include_unconfigured"), false}}));
    manuel.repondre(inventaire, QJsonObject{{QStringLiteral("providers"), QJsonArray{
        QJsonObject{{QStringLiteral("slug"), QStringLiteral("route")}, {QStringLiteral("name"), QStringLiteral("Route réelle")},
            {QStringLiteral("models"), QJsonArray{QStringLiteral("modele"), QStringLiteral("indisponible"), QStringLiteral("x --global")}},
            {QStringLiteral("unavailable_models"), QJsonArray{QStringLiteral("indisponible")}}},
        QJsonObject{{QStringLiteral("slug"), QStringLiteral("sans-auth")}, {QStringLiteral("authenticated"), false},
            {QStringLiteral("models"), QJsonArray{QStringLiteral("modele-prive")}}}}}});
    QVERIFY(banc.discussion.modelesCharges());
    QCOMPARE(banc.discussion.modelesSession()->count(), 2);
    banc.discussion.choisirModele(QStringLiteral("route"), QStringLiteral("invente"));
    banc.discussion.choisirModele(QStringLiteral("route"), QStringLiteral("x --global"));
    QVERIFY(manuel.derniere(QStringLiteral("config.set")).isEmpty());
    banc.discussion.choisirModele(QStringLiteral("route"), QStringLiteral("modele"));
    const auto choix = manuel.derniere(QStringLiteral("config.set"));
    QCOMPARE(choix.value(QStringLiteral("params")).toObject(), (QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("key"), QStringLiteral("model")},
        {QStringLiteral("value"), QStringLiteral("modele --provider route --session")}, {QStringLiteral("confirm_expensive_model"), false}}));
    manuel.repondre(choix, QJsonObject{{QStringLiteral("key"), QStringLiteral("model")}, {QStringLiteral("value"), QStringLiteral("modele")},
        {QStringLiteral("confirm_required"), true}, {QStringLiteral("confirm_message"), QStringLiteral("Coût élevé : confirmer ?")}});
    QCOMPARE(banc.discussion.confirmationModele(), QStringLiteral("Coût élevé : confirmer ?"));
    QVERIFY(banc.discussion.alerteGeste());
    QVERIFY(!banc.discussion.infosSession().contains(QStringLiteral("model")));
    const auto nombre = manuel.trames.size();
    banc.discussion.confirmerModele();
    QCOMPARE(manuel.trames.size(), nombre + 1);
    const auto confirme = manuel.derniere(QStringLiteral("config.set"));
    QVERIFY(confirme.value(QStringLiteral("params")).toObject().value(QStringLiteral("confirm_expensive_model")).toBool());
    manuel.repondre(confirme, QJsonObject{{QStringLiteral("key"), QStringLiteral("model")}, {QStringLiteral("value"), QStringLiteral("modele")},
        {QStringLiteral("deferred"), true}});
    QVERIFY(banc.discussion.confirmationModele().isEmpty());
    QVERIFY(banc.discussion.messageGeste().contains(QStringLiteral("prochain tour")));
    QVERIFY(!banc.discussion.infosSession().contains(QStringLiteral("model")));
    banc.discussion.confirmerModele();
    QCOMPARE(manuel.trames.size(), nombre + 1); // pas de seconde confirmation implicite
}

void TestDiscussion::modelesTardifsEtDonneesIllisibles()
{
    Banc banc;
    banc.ouvrirPasserelle();
    banc.ouvrirSession();
    CanalManuel manuel(banc.passerelle);
    banc.discussion.actualiserModeles();
    const auto ancien = manuel.derniere(QStringLiteral("model.options"));
    banc.discussion.actualiserModeles();
    manuel.repondre(manuel.derniere(QStringLiteral("model.options")), QJsonObject{{QStringLiteral("providers"), QJsonArray{}}});
    manuel.repondre(ancien, QJsonObject{{QStringLiteral("providers"), QJsonArray{QJsonObject{
        {QStringLiteral("slug"), QStringLiteral("ancien")}, {QStringLiteral("models"), QJsonArray{QStringLiteral("ancien")}}}}}});
    QVERIFY(banc.discussion.modelesCharges());
    QCOMPARE(banc.discussion.modelesSession()->count(), 0);
    banc.discussion.actualiserModeles();
    manuel.repondre(manuel.derniere(QStringLiteral("model.options")), QJsonObject{});
    QVERIFY(!banc.discussion.erreurModeles().isEmpty());
    banc.discussion.actualiserModeles();
    const auto avantOubli = manuel.derniere(QStringLiteral("model.options"));
    banc.discussion.oublier();
    manuel.refuser(avantOubli);
    QVERIFY(banc.discussion.erreurModeles().isEmpty());
    QVERIFY(!banc.discussion.modelesCharges());
    QVERIFY(!banc.discussion.chargementModeles());
}

void TestDiscussion::consignesPrepareesSansEnvoi()
{
    Banc banc;
    banc.discussion.preparerConsigne(QStringLiteral("Consigne hors ligne"));
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne hors ligne"));
    QVERIFY(banc.discussion.alerteGeste());
    QVERIFY(banc.serveur.tramesDeMethode(QStringLiteral("session.create")).isEmpty());
    banc.ouvrirPasserelle();
    banc.discussion.nouvelle();
    QTRY_COMPARE(banc.discussion.sessionVivante(), QStringLiteral("rt-nouvelle"));
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne hors ligne"));
    banc.discussion.preparerConsigne(QStringLiteral("Complément"));
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("Consigne hors ligne\n\nComplément"));
    QVERIFY(banc.serveur.tramesDeMethode(QStringLiteral("prompt.submit")).isEmpty());
    banc.discussion.oublier();
    QVERIFY(banc.discussion.brouillon().isEmpty());
    CanalManuel manuel(banc.passerelle);
    banc.discussion.preparerConsigne(QStringLiteral("À conserver malgré la reprise annulée"));
    const auto creation = manuel.derniere(QStringLiteral("session.create"));
    QVERIFY(!creation.isEmpty());
    banc.discussion.quitter();
    manuel.repondre(creation, QJsonObject{{QStringLiteral("session_id"), QStringLiteral("ancien-runtime")},
        {QStringLiteral("stored_session_id"), QStringLiteral("ancien-stocke")}, {QStringLiteral("messages"), QJsonArray{}}});
    QVERIFY(banc.discussion.sessionVivante().isEmpty());
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("À conserver malgré la reprise annulée"));
    banc.discussion.nouvelle();
    manuel.repondre(manuel.derniere(QStringLiteral("session.create")), QJsonObject{
        {QStringLiteral("session_id"), QStringLiteral("nouveau-runtime")}, {QStringLiteral("stored_session_id"), QStringLiteral("nouveau-stocke")},
        {QStringLiteral("messages"), QJsonArray{}}});
    QCOMPARE(banc.discussion.brouillon(), QStringLiteral("À conserver malgré la reprise annulée"));
    QVERIFY(manuel.derniere(QStringLiteral("prompt.submit")).isEmpty());
}

QTEST_MAIN(TestDiscussion)
#include "tst_discussion.moc"
