// Temps réel de la station contre le faux Hermes (cahier P8 § 6) :
//
//  - Sondage : rien ne part tant que la page n'est pas active ; lecture à l'activation puis
//    périodique ; jamais deux lectures en vol ; la dernière lecture réussie reste datée après
//    un échec, et l'erreur est publiée à côté ;
//  - VeilleKanban : `since` = `latest_event_id` du tableau, ticket en sous-protocole (jamais
//    dans l'URL), connexion ADMISE bien que la route n'ait choisi aucun sous-protocole (ce que
//    le cahier tenait pour supposé), une rafale de lots ⇒ une seule invalidation après
//    regroupement, reprise au dernier curseur après coupure, refus après deux poignées
//    refusées, tableau inconnu refusé, silence après l'arrêt ;
//  - EventStreamService : résumé de `/v1/accueil` (à traiter par vous, poste, pause ; fixture
//    partagée avec le greffon), la page Projets ne met à jour que le poste et la pause, aucun flux
//    SSE ouvert (aucun n'est annoncé à cette base), pages actives = session ET fenêtre,
//    `sessions.changed` relayé, retour du lien signalé.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/Sondage.h"
#include "events/VeilleKanban.h"
#include "gateway/GatewayClient.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

const QString kProjets = QStringLiteral("/api/plugins/acp-poste/v1/projets");
const QString kAccueil = QStringLiteral("/api/plugins/acp-poste/v1/accueil");
const QString kTableau = QStringLiteral("acp-outil-3dd5");

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    qint64 dernierEvenement = 41;
    int statutTableau = 200;
    int statutProjets = 200;
    int delaiProjets = 0;

    Banc()
    {
        serveur.installerAuthentification();
        serveur.activerKanban();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
        serveur.route("GET", QStringLiteral("/api/plugins/kanban/board"), [this](const RequeteRecue &) {
            if (statutTableau != 200) {
                return ReponseFaux::json(statutTableau, QJsonObject{{QStringLiteral("detail"), QStringLiteral("board not found")}});
            }
            return ReponseFaux::json(200, QJsonObject{{QStringLiteral("columns"), QJsonArray{}},
                                                      {QStringLiteral("latest_event_id"), dernierEvenement},
                                                      {QStringLiteral("now"), 1790423039}});
        });
        serveur.route("GET", kProjets, [this](const RequeteRecue &) {
            ReponseFaux reponse = statutProjets == 200
                ? ReponseFaux::json(200, liste())
                : ReponseFaux::json(statutProjets, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Not Found")}});
            reponse.delaiMs = delaiProjets;
            return reponse;
        });
        serveur.route("GET", kAccueil, [](const RequeteRecue &) {
            return ReponseFaux::json(200, fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object());
        });
    }

    static QJsonObject liste()
    {
        // Forme de GET /v1/projets (noyau/projets.lister), réduite à ce que lit le résumé.
        return QJsonObject{
            {QStringLiteral("projets"), QJsonArray{}},
            {QStringLiteral("poste"), QJsonObject{{QStringLiteral("etat"), QStringLiteral("en_ligne")},
                                                  {QStringLiteral("machine"), QStringLiteral("poste-simule")}}},
            {QStringLiteral("pause_generale"), QJsonValue(QJsonValue::Null)},
            {QStringLiteral("questions_ouvertes"), 1},
        };
    }

    static QJsonObject lot(qint64 curseur, int nombre)
    {
        QJsonArray evenements;
        for (int index = 0; index < nombre; ++index) {
            evenements.append(QJsonObject{{QStringLiteral("id"), curseur - index}});
        }
        return QJsonObject{{QStringLiteral("events"), evenements}, {QStringLiteral("cursor"), curseur}};
    }
};

} // namespace

class TestTempsReel : public QObject
{
    Q_OBJECT

private slots:
    void sondageInactifNeLitRien();
    void sondageGardeLaDerniereLectureSurEchec();
    void sondageNeChevaucheJamais();
    void veilleOuvreDepuisLeDernierEvenement();
    void veilleUneRafaleUneRelecture();
    void veilleRepriseAuDernierCurseur();
    void veillePoigneeRefuseeDeuxFoisRefusee();
    void veilleTableauInconnuRefuse();
    void veilleArreteeSeTait();
    void serviceResumeSansFluxSse();
    void servicePagesActivesEtLien();
    void serviceRelaieSessionsChanged();
};

void TestTempsReel::sondageInactifNeLitRien()
{
    Banc banc;
    Sondage sondage([&banc] { return banc.greffon.projets(); }, std::chrono::milliseconds(40));
    QTest::qWait(150);
    QCOMPARE(banc.serveur.compter("GET", kProjets), 0);

    sondage.setActif(true);
    QTRY_VERIFY_WITH_TIMEOUT(banc.serveur.compter("GET", kProjets) >= 3, 3000);
    sondage.setActif(false);
    QTRY_VERIFY(!sondage.enCours());
    const int arret = banc.serveur.compter("GET", kProjets);
    QTest::qWait(200);
    QCOMPARE(banc.serveur.compter("GET", kProjets), arret);
    QCOMPARE(sondage.derniereErreur(), QString());
    QVERIFY(sondage.libelleLuA().startsWith(QStringLiteral("Lu à ")));
}

void TestTempsReel::sondageGardeLaDerniereLectureSurEchec()
{
    Banc banc;
    Sondage sondage([&banc] { return banc.greffon.projets(); }, std::chrono::hours(1));
    QSignalSpy lus(&sondage, &Sondage::lu);
    QSignalSpy echecs(&sondage, &Sondage::echec);
    QCOMPARE(sondage.libelleLuA(), QStringLiteral("Jamais lu"));
    sondage.setActif(true);
    QTRY_COMPARE(lus.count(), 1);
    const QDateTime premiere = sondage.luA();
    QVERIFY(premiere.isValid());

    banc.statutProjets = 404;
    sondage.lireMaintenant();
    QTRY_COMPARE(echecs.count(), 1);
    QCOMPARE(lus.count(), 1);
    QCOMPARE(sondage.luA(), premiere); // l'heure de la dernière lecture réussie reste
    QVERIFY(!sondage.derniereErreur().isEmpty());

    banc.statutProjets = 200;
    sondage.lireMaintenant();
    QTRY_COMPARE(lus.count(), 2);
    QCOMPARE(sondage.derniereErreur(), QString());
    QVERIFY(sondage.luA() >= premiere);
}

void TestTempsReel::sondageNeChevaucheJamais()
{
    Banc banc;
    banc.delaiProjets = 250;
    Sondage sondage([&banc] { return banc.greffon.projets(); }, std::chrono::hours(1));
    QSignalSpy lus(&sondage, &Sondage::lu);
    sondage.setActif(true);
    QTRY_COMPARE(banc.serveur.compter("GET", kProjets), 1);
    QVERIFY(sondage.enCours());
    // Trois demandes pendant la lecture en vol : UNE relecture, servie à sa fin.
    sondage.lireMaintenant();
    sondage.lireMaintenant();
    sondage.lireMaintenant();
    QCOMPARE(banc.serveur.compter("GET", kProjets), 1);
    QTRY_COMPARE(lus.count(), 2);
    QTest::qWait(400);
    QCOMPARE(banc.serveur.compter("GET", kProjets), 2);
    QCOMPARE(lus.count(), 2);
}

void TestTempsReel::veilleOuvreDepuisLeDernierEvenement()
{
    Banc banc;
    VeilleKanban veille(&banc.client);
    veille.surveiller(kTableau);
    QTRY_COMPARE(veille.etat(), VeilleKanban::Etat::Prete);
    QCOMPARE(veille.tableau(), kTableau);
    QCOMPARE(veille.curseur(), 41);

    const auto tableaux = banc.serveur.filtrer("GET", QStringLiteral("/api/plugins/kanban/board"));
    QCOMPARE(tableaux.size(), 1);
    QCOMPARE(tableaux.first().requete.queryItemValue(QStringLiteral("board")), kTableau);
    QCOMPARE(tableaux.first().entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/api/auth/ws-ticket")), 1);

    QCOMPARE(banc.serveur.ouverturesKanban.size(), 1);
    const RequeteRecue ouverture = banc.serveur.ouverturesKanban.first();
    QCOMPARE(ouverture.chemin, QStringLiteral("/api/plugins/kanban/events"));
    QCOMPARE(ouverture.requete.queryItemValue(QStringLiteral("since")), QStringLiteral("41"));
    QCOMPARE(ouverture.requete.queryItemValue(QStringLiteral("board")), kTableau);
    QVERIFY2(!ouverture.requete.hasQueryItem(QStringLiteral("ticket")), "le ticket ne voyage jamais dans l'URL");
    QVERIFY(!ouverture.aEntete("origin"));
    QVERIFY(!ouverture.aEntete("authorization"));
    const QByteArray protocoles = ouverture.entete("sec-websocket-protocol");
    QVERIFY(protocoles.contains("hermes-gateway-v1"));
    QVERIFY(protocoles.contains("hermes-gateway-ticket.ticket-faux-"));
    QVERIFY(banc.serveur.ticketsEmis.isEmpty()); // consommé à l'ouverture
    QCOMPARE(banc.serveur.clientsKanban(), 1);
}

void TestTempsReel::veilleUneRafaleUneRelecture()
{
    Banc banc;
    VeilleKanban veille(&banc.client);
    veille.setRegroupement(std::chrono::milliseconds(120));
    QSignalSpy changements(&veille, &VeilleKanban::changement);
    veille.surveiller(kTableau);
    QTRY_COMPARE(veille.etat(), VeilleKanban::Etat::Prete);

    banc.serveur.envoyerKanban(Banc::lot(42, 1));
    banc.serveur.envoyerKanban(Banc::lot(44, 2));
    banc.serveur.envoyerKanban(Banc::lot(45, 1));
    QTRY_COMPARE(changements.count(), 1);
    QCOMPARE(changements.first().first().toString(), kTableau);
    QTest::qWait(300);
    QCOMPARE(changements.count(), 1); // une rafale, une relecture
    QCOMPARE(veille.curseur(), 45);

    // Lot vide, ou curseur qui ne progresse pas : rien n'a bougé.
    banc.serveur.envoyerKanban(Banc::lot(45, 0));
    banc.serveur.envoyerKanban(Banc::lot(44, 1));
    QTest::qWait(300);
    QCOMPARE(changements.count(), 1);

    banc.serveur.envoyerKanban(Banc::lot(46, 1));
    QTRY_COMPARE(changements.count(), 2);
}

void TestTempsReel::veilleRepriseAuDernierCurseur()
{
    Banc banc;
    VeilleKanban veille(&banc.client);
    veille.setRegroupement(std::chrono::milliseconds(10));
    veille.setRecul(Backoff(std::chrono::milliseconds(20), std::chrono::milliseconds(40), 0));
    veille.surveiller(kTableau);
    QTRY_COMPARE(veille.etat(), VeilleKanban::Etat::Prete);
    banc.serveur.envoyerKanban(Banc::lot(50, 1));
    QTRY_COMPARE(veille.curseur(), 50);

    banc.serveur.couperKanban();
    QTRY_COMPARE(banc.serveur.ouverturesKanban.size(), 2);
    QTRY_COMPARE(veille.etat(), VeilleKanban::Etat::Prete);
    QCOMPARE(banc.serveur.ouverturesKanban.at(1).requete.queryItemValue(QStringLiteral("since")), QStringLiteral("50"));
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/api/auth/ws-ticket")), 2); // un ticket par ouverture
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/api/plugins/kanban/board")), 1);
    QVERIFY(veille.reconnexions() >= 1);
}

void TestTempsReel::veillePoigneeRefuseeDeuxFoisRefusee()
{
    Banc banc;
    banc.serveur.refuserKanban = true;
    VeilleKanban veille(&banc.client);
    veille.surveiller(kTableau);
    QTRY_COMPARE(veille.etat(), VeilleKanban::Etat::Refusee);
    QCOMPARE(banc.serveur.ouverturesKanban.size(), 2);
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/api/auth/ws-ticket")), 2);
    QVERIFY(veille.raison().contains(QStringLiteral("refusée")));
    QTest::qWait(200);
    QCOMPARE(banc.serveur.ouverturesKanban.size(), 2); // aucun nouvel essai automatique
}

void TestTempsReel::veilleTableauInconnuRefuse()
{
    Banc banc;
    banc.statutTableau = 404;
    VeilleKanban veille(&banc.client);
    veille.surveiller(QStringLiteral("acp-inconnu-0000"));
    QTRY_COMPARE(veille.etat(), VeilleKanban::Etat::Refusee);
    QVERIFY(veille.raison().contains(QStringLiteral("introuvable")));
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/api/auth/ws-ticket")), 0);
    QVERIFY(banc.serveur.ouverturesKanban.isEmpty());

    // Identifiant illisible : refus local, rien n'est émis.
    veille.surveiller(QStringLiteral("../etc"));
    QCOMPARE(veille.etat(), VeilleKanban::Etat::Refusee);
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/api/plugins/kanban/board")), 1);
}

void TestTempsReel::veilleArreteeSeTait()
{
    Banc banc;
    VeilleKanban veille(&banc.client);
    veille.setRegroupement(std::chrono::milliseconds(10));
    QSignalSpy changements(&veille, &VeilleKanban::changement);
    veille.surveiller(kTableau);
    QTRY_COMPARE(banc.serveur.clientsKanban(), 1);
    veille.arreter();
    QCOMPARE(veille.etat(), VeilleKanban::Etat::Arretee);
    QTRY_COMPARE(banc.serveur.clientsKanban(), 0);
    banc.serveur.envoyerKanban(Banc::lot(60, 1));
    QTest::qWait(200);
    QCOMPARE(changements.count(), 0);
    QCOMPARE(banc.serveur.ouverturesKanban.size(), 1);
}

void TestTempsReel::serviceResumeSansFluxSse()
{
    Banc banc;
    EventStreamService flux(&banc.client, &banc.greffon, nullptr);
    flux.setIntervalleFond(std::chrono::milliseconds(60));
    QCOMPARE(flux.aTraiter(), -1);
    QCOMPARE(flux.libelleATraiter(), QStringLiteral("À traiter par vous : Inconnu"));
    QCOMPARE(flux.libellePoste(), QStringLiteral("Inconnu"));
    QCOMPARE(flux.pauseGenerale(), EventStreamService::kInconnu);
    QTest::qWait(150);
    QCOMPARE(banc.serveur.compter("GET", kAccueil), 0); // aucune session : rien ne part

    flux.demarrer();
    QTRY_COMPARE(flux.aTraiter(), 1); // a_traiter.total de la fixture partagée
    QCOMPARE(flux.libellePoste(), QStringLiteral("En ligne"));
    QCOMPARE(flux.clePoste(), QStringLiteral("succeeded"));
    QCOMPARE(flux.pauseGenerale(), 0);
    // Jamais « rien à traiter » : les discussions en attente ne sont pas comptées, et le libellé le dit.
    QCOMPARE(flux.libelleATraiter(), QStringLiteral("À traiter par vous : 1 (discussions non comptées)"));
    QTRY_VERIFY(banc.serveur.compter("GET", kAccueil) >= 2);

    // Aucun flux SSE n'est annoncé à cette base : rien d'autre n'est ouvert, et l'état le dit.
    for (const RequeteRecue &requete : std::as_const(banc.serveur.requetes)) {
        QCOMPARE(requete.chemin, kAccueil);
        QVERIFY(requete.entete("accept") != QByteArrayLiteral("text/event-stream"));
    }
    // /v1/meta non lu par ce banc : le flux n'est pas ouvert, et l'état le dit (« Inconnu », jamais deviné).
    QVERIFY(flux.etatFlux().startsWith(QStringLiteral("Inconnu : /v1/meta n'a pas encore été lu")));

    // La page Projets (GET /v1/projets) met à jour le poste et la pause, jamais le compteur (une seule source).
    QJsonObject pause = Banc::liste();
    pause.insert(QStringLiteral("pause_generale"), QJsonObject{{QStringLiteral("reason"), QStringLiteral("ACP : pause du propriétaire")}});
    pause.insert(QStringLiteral("questions_ouvertes"), 3);
    flux.noterProjets(pause);
    QCOMPARE(flux.pauseGenerale(), 1);
    QCOMPARE(flux.aTraiter(), 1);
    QVERIFY(flux.libelleResume().contains(QStringLiteral("Pause générale engagée")));

    // L'Accueil (GET /v1/accueil) met tout à jour sans attendre ; un bloc de pause illisible n'est pas « levée ».
    QJsonObject accueil = fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object();
    QJsonObject aTraiter = accueil.value(QStringLiteral("a_traiter")).toObject();
    aTraiter.insert(QStringLiteral("total"), 4);
    accueil.insert(QStringLiteral("a_traiter"), aTraiter);
    accueil.insert(QStringLiteral("illisibles"), QJsonObject{{QStringLiteral("pause_generale"), QStringLiteral("bloc illisible")}});
    flux.noterAccueil(accueil);
    QCOMPARE(flux.aTraiter(), 4);
    QCOMPARE(flux.pauseGenerale(), EventStreamService::kInconnu);
    accueil.insert(QStringLiteral("a_traiter"), QJsonValue::Null);
    flux.noterAccueil(accueil);
    QCOMPARE(flux.aTraiter(), -1);

    flux.arreter();
    QCOMPARE(flux.aTraiter(), -1);
    QCOMPARE(flux.pauseGenerale(), EventStreamService::kInconnu);
    QTRY_VERIFY(!flux.sondageFond()->enCours());
    const int arret = banc.serveur.compter("GET", kAccueil);
    QTest::qWait(200);
    QCOMPARE(banc.serveur.compter("GET", kAccueil), arret);
}

void TestTempsReel::servicePagesActivesEtLien()
{
    Banc banc;
    EventStreamService flux(&banc.client, &banc.greffon, nullptr);
    flux.setIntervalleFond(std::chrono::hours(1));
    QSignalSpy actives(&flux, &EventStreamService::pagesActivesChange);
    QSignalSpy retour(&flux, &EventStreamService::lienRetabli);
    QVERIFY(!flux.pagesActives());
    flux.demarrer();
    QVERIFY(flux.pagesActives());
    flux.setFenetreActive(false); // fenêtre réduite : les pages cessent de sonder
    QVERIFY(!flux.pagesActives());
    flux.setFenetreActive(true);
    QVERIFY(flux.pagesActives());
    QCOMPARE(actives.count(), 3);

    flux.signalerLien(true);
    QCOMPARE(retour.count(), 0); // premier relevé : pas un retour
    flux.signalerLien(false);
    flux.signalerLien(true);
    QCOMPARE(retour.count(), 1);
}

void TestTempsReel::serviceRelaieSessionsChanged()
{
    Banc banc;
    banc.serveur.activerPasserelle();
    GatewayClient passerelle(&banc.client);
    EventStreamService flux(&banc.client, &banc.greffon, &passerelle);
    QSignalSpy sessions(&flux, &EventStreamService::sessionsChangees);
    QSignalSpy prete(&passerelle, &GatewayClient::prete);
    passerelle.ouvrir();
    QVERIFY(prete.wait(10000));
    QVERIFY(flux.etatPasserelle().startsWith(passerelle.libelleEtat()));
    banc.serveur.envoyer(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                                     {QStringLiteral("method"), QStringLiteral("event")},
                                     {QStringLiteral("params"),
                                      QJsonObject{{QStringLiteral("type"), QStringLiteral("sessions.changed")},
                                                  {QStringLiteral("payload"), QJsonObject{}}}}});
    QTRY_COMPARE(sessions.count(), 1);
    passerelle.fermer();
}

QTEST_MAIN(TestTempsReel)
#include "tst_temps_reel.moc"
