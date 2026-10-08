// Flux d'invalidation du greffon (GET /v1/flux, étape P7) consommé par la station, contre le
// faux Hermes qui le sert comme uvicorn (200 `text/event-stream`, corps en morceaux) :
//  - trames PARTAGÉES avec le greffon et la page web (hermes/tests/outils/fixtures_flux/
//    trames.json), lues à leur place : `etat`, `changement`, `illisible`, battement, `fin`,
//    reprise avec `Last-Event-ID` et première trame vide ;
//  - ouvert seulement sur l'annonce de /v1/meta (chemin et version attendus) et si une page
//    peut lire ; « Inconnu » tant que /v1/meta n'est pas lu ;
//  - chien de garde (aucun octet), reprises, repli en sondage après trois échecs, 401 jamais
//    réessayé aussitôt, 429 jamais avant Retry-After, message du greffon tel quel ;
//  - une page (Sondage) relit sur signal de l'un de SES sujets, regroupé, et se contente en
//    temps réel d'une relecture de sûreté ; le service ouvre et ferme le flux avec la session
//    et la fenêtre, et le sondage léger de l'Accueil le suit.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/FluxInvalidation.h"
#include "events/Sondage.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;
using std::chrono::milliseconds;

namespace {

const QString kFlux = QStringLiteral("/api/plugins/acp-poste/v1/flux");
const QString kAccueil = QStringLiteral("/api/plugins/acp-poste/v1/accueil");
const QString kPoste = QStringLiteral("/api/plugins/acp-poste/v1/poste");

QByteArray trame(const char *nom)
{
    return fixturePartagee(QStringLiteral("fixtures_flux/trames.json"))
        .object()
        .value(QStringLiteral("trames"))
        .toObject()
        .value(QString::fromLatin1(nom))
        .toString()
        .toUtf8();
}

QJsonObject annonce(const QString &chemin = QString::fromLatin1(FluxInvalidation::kChemin), int version = 1)
{
    // Forme de meta.py `bloc_flux`.
    return QJsonObject{{QStringLiteral("chemin"), chemin},
                       {QStringLiteral("version"), version},
                       {QStringLiteral("sujets"), QJsonArray::fromStringList(FluxInvalidation::sujets())},
                       {QStringLiteral("battement_s"), 15},
                       {QStringLiteral("duree_max_s"), 600}};
}

FluxInvalidation::Reglages reglagesRapides()
{
    FluxInvalidation::Reglages r;
    r.chienDeGarde = milliseconds(5000);
    r.fenetreEchecs = milliseconds(10000);
    r.nouvelEssai = milliseconds(3600000);
    r.reprises = {milliseconds(40), milliseconds(40), milliseconds(40)};
    r.relectureSurete = milliseconds(120000);
    r.relectureDiscussions = milliseconds(60000);
    r.regroupement = milliseconds(60);
    return r;
}

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    FluxInvalidation flux{&greffon};

    Banc()
    {
        serveur.installerAuthentification();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        serveur.activerFlux();
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
        flux.setReglages(reglagesRapides());
    }

    int ouvertures() const { return serveur.compter("GET", kFlux); }

    //! Ouvre le flux et attend la connexion côté serveur.
    void ouvrir()
    {
        flux.setAnnonce(QStringLiteral("annonce"), annonce());
        flux.setActif(true);
        QTRY_COMPARE(serveur.clientsFlux(), 1);
        QTRY_VERIFY(flux.connecte());
    }
};

} // namespace

class TestFluxInvalidation : public QObject
{
    Q_OBJECT

private slots:
    void tramesPartageesLuesCommeLeGreffon();
    void ouvertSeulementSurAnnonceEtPageActive();
    void chienDeGardeReprisesEtRepli();
    void refusDuServeur();
    void pageRelitSurSignalDeSesSujets();
    void serviceSuitLaSessionEtLaFenetre();
    void greffonBloqueFermeUnFluxOuvert();
    void sessionNeuveOublieLeRepli();
};

void TestFluxInvalidation::tramesPartageesLuesCommeLeGreffon()
{
    Banc banc;
    QSignalSpy signaux(&banc.flux, &FluxInvalidation::invalidation);
    banc.ouvrir();
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::Connexion);
    const RequeteRecue ouverture = banc.serveur.ouverturesFlux.constFirst();
    QCOMPARE(ouverture.entete("accept"), QByteArrayLiteral("text/event-stream"));
    QCOMPARE(ouverture.entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
    QVERIFY(!ouverture.aEntete("last-event-id")); // première ouverture : rien à reprendre
    QVERIFY(!ouverture.aEntete("origin"));
    QVERIFY(!ouverture.aEntete("cookie"));

    // Ouverture : `retry`, puis `etat` avec tous les sujets ; coupée n'importe où (au milieu d'une ligne).
    const QByteArray etat = trame("ouverture");
    banc.serveur.envoyerFlux(etat.left(25));
    QTest::qWait(50);
    QCOMPARE(signaux.size(), 0);
    banc.serveur.envoyerFlux(etat.mid(25));
    QTRY_COMPARE(signaux.size(), 1);
    QCOMPARE(signaux.at(0).at(0).toStringList(), FluxInvalidation::sujets());
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::TempsReel);
    QCOMPARE(banc.flux.revision(), QStringLiteral("1727791200.41"));
    QCOMPARE(banc.flux.discussionsSuivies(), std::optional<bool>(true));
    QVERIFY(banc.flux.libelleEtat().startsWith(QStringLiteral("Temps réel : chaque page affichée est relue")));
    QCOMPARE(banc.flux.libelleCourt(), QStringLiteral("Temps réel"));

    // Battement : un commentaire, aucun signal.
    banc.serveur.envoyerFlux(trame("battement"));
    QTest::qWait(50);
    QCOMPARE(signaux.size(), 1);

    // Changement, puis sujets illisibles : les sujets signalés, la révision suit.
    banc.serveur.envoyerFlux(trame("changement"));
    QTRY_COMPARE(signaux.size(), 2);
    QCOMPARE(signaux.at(1).at(0).toStringList(), (QStringList{QStringLiteral("projets"), QStringLiteral("questions")}));
    QCOMPARE(banc.flux.revision(), QStringLiteral("1727791200.42"));
    banc.serveur.envoyerFlux(trame("illisible"));
    QTRY_COMPARE(signaux.size(), 3);
    QCOMPARE(banc.flux.revision(), QStringLiteral("1727791200.43"));
    QCOMPARE(banc.flux.trames(), 3);

    // Trame illisible ou événement inconnu : ignorés, jamais un signal deviné.
    banc.serveur.envoyerFlux(QByteArrayLiteral("event: changement\ndata: {pas du json\n\nevent: autre\ndata: {}\n\n"));
    QTest::qWait(80);
    QCOMPARE(signaux.size(), 3);
    QCOMPARE(banc.flux.tramesIllisibles(), 1);

    // Fin (durée maximale) : réouverture AUSSITÔT, avec la dernière révision en Last-Event-ID.
    banc.serveur.envoyerFlux(trame("fin"));
    banc.serveur.terminerFlux();
    QTRY_COMPARE(banc.ouvertures(), 2);
    QCOMPARE(banc.serveur.ouverturesFlux.at(1).entete("last-event-id"), QByteArrayLiteral("1727791200.43"));
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::TempsReel); // une fin propre n'est pas un échec
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);
    // Reprise sans rien de manqué : trame `etat` sans sujet, aucune relecture.
    banc.serveur.envoyerFlux(trame("reprise"));
    QTRY_COMPARE(banc.flux.revision(), QStringLiteral("1727791200.41"));
    QTest::qWait(50);
    QCOMPARE(signaux.size(), 3);
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::TempsReel);
    QVERIFY(banc.flux.journal().constLast().endsWith(QStringLiteral("etat : aucun sujet")));
}

void TestFluxInvalidation::ouvertSeulementSurAnnonceEtPageActive()
{
    Banc banc;
    banc.flux.setActif(true);
    QTest::qWait(80);
    QCOMPARE(banc.ouvertures(), 0); // /v1/meta pas encore lu : rien n'est ouvert
    QVERIFY(banc.flux.libelleEtat().startsWith(QStringLiteral("Inconnu : /v1/meta n'a pas encore été lu")));

    banc.flux.setAnnonce(QStringLiteral("absent"), {});
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::Indisponible);
    QVERIFY(banc.flux.libelleEtat().startsWith(
        QStringLiteral("Non utilisé : le greffon acp-poste n'annonce aucun flux d'invalidation")));
    QCOMPARE(banc.flux.libelleCourt(), QStringLiteral("Sondage (aucun flux)"));
    banc.flux.setAnnonce(QStringLiteral("illisible"), QStringLiteral("oui"));
    QVERIFY(banc.flux.libelleEtat().contains(QStringLiteral("annonce du flux illisible")));
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce(QStringLiteral("/ailleurs/flux")));
    QVERIFY(banc.flux.libelleEtat().contains(QStringLiteral("autre chemin (/ailleurs/flux)")));
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce(QString::fromLatin1(FluxInvalidation::kChemin), 2));
    QVERIFY(banc.flux.libelleEtat().contains(QStringLiteral("version du flux non prise en charge (2")));
    QTest::qWait(80);
    QCOMPARE(banc.ouvertures(), 0);

    // Annonce attendue : ouvert ; page inactive (fenêtre réduite, session perdue) : fermé, côté serveur aussi.
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);
    banc.flux.setActif(false);
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::Ferme);
    QVERIFY(!banc.flux.connecte());
    QTRY_COMPARE(banc.serveur.clientsFlux(), 0);
    banc.flux.setActif(true);
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);
    QCOMPARE(banc.ouvertures(), 2);
    // Annonce retirée (serveur changé, verdict relu) : fermé aussitôt.
    banc.flux.setAnnonce(QStringLiteral("absent"), {});
    QTRY_COMPARE(banc.serveur.clientsFlux(), 0);

    // Greffon bloqué par le verdict : refus local, rien n'est émis, et c'est dit.
    banc.greffon.bloquer(QStringLiteral("Contrat du greffon incompatible : acp-poste/2, attendu acp-poste/1"));
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::Indisponible);
    QVERIFY(banc.flux.libelleEtat().startsWith(QStringLiteral("Non utilisé : ")));
    QCOMPARE(banc.ouvertures(), 2);
    banc.greffon.debloquer();
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce()); // verdict suivant
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);

    // Serveur changé : fermé, révision et annonce oubliées ; rien ne s'ouvre avant le verdict du nouveau serveur, et
    // la réouverture ne reprend pas la révision de l'ancien.
    banc.serveur.envoyerFlux(trame("ouverture"));
    QTRY_COMPARE(banc.flux.revision(), QStringLiteral("1727791200.41"));
    banc.flux.oublier();
    QTRY_COMPARE(banc.serveur.clientsFlux(), 0);
    QCOMPARE(banc.flux.revision(), QString());
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::Indisponible);
    QVERIFY(banc.flux.libelleEtat().startsWith(QStringLiteral("Inconnu : /v1/meta n'a pas encore été lu")));
    QTest::qWait(80);
    const int avant = banc.ouvertures();
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    QTRY_COMPARE(banc.ouvertures(), avant + 1);
    QVERIFY(!banc.serveur.ouverturesFlux.constLast().aEntete("last-event-id"));
}

void TestFluxInvalidation::chienDeGardeReprisesEtRepli()
{
    Banc banc;
    FluxInvalidation::Reglages r = reglagesRapides();
    r.chienDeGarde = milliseconds(250);
    r.nouvelEssai = milliseconds(1200);
    banc.flux.setReglages(r);
    banc.ouvrir();
    // Connexion muette : jamais « temps réel » ; trois échecs (chien de garde) en 2 min : repli en sondage.
    QTRY_COMPARE_WITH_TIMEOUT(banc.ouvertures(), 2, 3000);
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::Connexion);
    QTRY_COMPARE_WITH_TIMEOUT(banc.ouvertures(), 3, 3000);
    QTRY_COMPARE_WITH_TIMEOUT(banc.flux.mode(), FluxInvalidation::Mode::Sondage, 3000);
    QVERIFY2(banc.flux.libelleEtat().startsWith(
                 QStringLiteral("Temps réel indisponible (aucun octet reçu du flux depuis 0.25 s) : les pages sont relues "
                                "par sondage ; nouvel essai à ")),
             qPrintable(banc.flux.libelleEtat()));
    QCOMPARE(banc.flux.libelleCourt(), QStringLiteral("Sondage (temps réel indisponible)"));
    QVERIFY(banc.flux.prochainEssai().isValid());
    // Pendant le repli, le retour du lien ne le court-circuite pas.
    banc.flux.relancer();
    QTest::qWait(400);
    QCOMPARE(banc.ouvertures(), 3);
    // Nouvel essai à l'échéance : une trame `etat` rend le temps réel.
    QTRY_COMPARE_WITH_TIMEOUT(banc.ouvertures(), 4, 3000);
    banc.serveur.envoyerFlux(trame("ouverture"));
    QTRY_COMPARE(banc.flux.mode(), FluxInvalidation::Mode::TempsReel);
    QCOMPARE(banc.flux.raison(), QString());

    // Coupure isolée en temps réel : reprise rapide, le temps réel reste (la trame `etat` dira ce qui a changé).
    banc.serveur.couperFlux();
    QTRY_COMPARE_WITH_TIMEOUT(banc.ouvertures(), 5, 3000);
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::TempsReel);
    QCOMPARE(banc.serveur.ouverturesFlux.constLast().entete("last-event-id"), QByteArrayLiteral("1727791200.41"));
}

void TestFluxInvalidation::refusDuServeur()
{
    Banc banc;
    // 429 du greffon : son message français, et jamais de nouvel essai avant Retry-After.
    ReponseFaux trop = ReponseFaux::json(429, QJsonObject{{QStringLiteral("detail"), QJsonObject{
        {QStringLiteral("code"), QStringLiteral("trop_de_flux")},
        {QStringLiteral("message"), QStringLiteral("Trop de flux ouverts : fermez un onglet du tableau de bord.")}}}});
    trop.entetes.append({QByteArrayLiteral("Retry-After"), QByteArrayLiteral("1")});
    banc.serveur.refusFlux.append(trop);
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    banc.flux.setActif(true);
    QTRY_COMPARE(banc.ouvertures(), 1);
    QTRY_COMPARE(banc.flux.raison(), QStringLiteral("Trop de flux ouverts : fermez un onglet du tableau de bord."));
    QTest::qWait(500);
    QCOMPARE(banc.ouvertures(), 1); // reprise de 40 ms ignorée : Retry-After prime
    QTRY_COMPARE_WITH_TIMEOUT(banc.ouvertures(), 2, 3000);
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);

    // 404 sans message du greffon : statut dit.
    banc.serveur.refusFlux.append(ReponseFaux::json(404, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Not Found")}}));
    banc.serveur.couperFlux();
    QTRY_COMPARE(banc.flux.raison(), QStringLiteral("refusé par le serveur (HTTP 404)"));

    // 401 : jamais réessayé aussitôt (décision P8b-1), repli en sondage dit.
    Banc refuse;
    refuse.serveur.jetonsAccesValides.clear();
    refuse.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    refuse.flux.setActif(true);
    QTRY_COMPARE(refuse.flux.mode(), FluxInvalidation::Mode::Sondage);
    QCOMPARE(refuse.flux.raison(), QStringLiteral("session refusée par le flux (401)"));
    QTest::qWait(400);
    QCOMPARE(refuse.ouvertures(), 1);

    // Réponse 200 qui n'est pas un flux d'événements : échec, jamais lue comme des trames.
    Banc autre;
    autre.serveur.refusFlux.append(ReponseFaux::json(200, QJsonObject{{QStringLiteral("sujets"), QJsonArray{}}}));
    QSignalSpy signaux(&autre.flux, &FluxInvalidation::invalidation);
    autre.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    autre.flux.setActif(true);
    QTRY_COMPARE(autre.flux.raison(), QStringLiteral("la réponse n'est pas un flux d'événements"));
    QCOMPARE(signaux.size(), 0);
    QVERIFY(autre.flux.mode() != FluxInvalidation::Mode::TempsReel);
}

void TestFluxInvalidation::pageRelitSurSignalDeSesSujets()
{
    Banc banc;
    int lectures = 0;
    banc.serveur.route("GET", kPoste, [&lectures](const RequeteRecue &) {
        ++lectures;
        return ReponseFaux::json(200, QJsonObject{});
    });
    Sondage page([&banc] { return banc.greffon.poste(); }, milliseconds(15000));
    page.suivre(&banc.flux, {QStringLiteral("poste"), QStringLiteral("quotas")});
    QCOMPARE(page.intervalleEffectif(), milliseconds(15000)); // hors temps réel : le sondage habituel
    page.setActif(true);
    QTRY_COMPARE(lectures, 1);

    banc.ouvrir();
    banc.serveur.envoyerFlux(trame("ouverture")); // tous les sujets : une relecture
    QTRY_COMPARE(lectures, 2);
    QCOMPARE(page.relecturesSurSignal(), 1);
    // Temps réel : relecture de sûreté seulement.
    QCOMPARE(page.intervalleEffectif(), milliseconds(120000));
    // Sujets que la page ne suit pas : rien.
    banc.serveur.envoyerFlux(trame("changement"));
    QTest::qWait(200);
    QCOMPARE(lectures, 2);
    // Une rafale de deux trames pour ses sujets : UNE lecture.
    banc.serveur.envoyerFlux(QByteArrayLiteral("id: 1727791200.44\nevent: changement\ndata: {\"sujets\":[\"quotas\"]}\n\n"
                                               "id: 1727791200.45\nevent: changement\ndata: {\"sujets\":[\"poste\"]}\n\n"));
    QTRY_COMPARE(lectures, 3);
    QTest::qWait(200);
    QCOMPARE(lectures, 3);
    // Page inactive (cachée) : aucun appel sur signal.
    page.setActif(false);
    banc.serveur.envoyerFlux(QByteArrayLiteral("id: 1727791200.46\nevent: changement\ndata: {\"sujets\":[\"poste\"]}\n\n"));
    QTest::qWait(200);
    QCOMPARE(lectures, 3);

    // Discussions non publiées par le greffon : la page qui les suit se relit toutes les minutes.
    Sondage discussions([&banc] { return banc.greffon.poste(); }, milliseconds(15000));
    discussions.suivre(&banc.flux, {QStringLiteral("discussions")});
    QCOMPARE(discussions.intervalleEffectif(), milliseconds(120000)); // `discussions_suivies: true`
    banc.serveur.envoyerFlux(QByteArrayLiteral(
        "id: 1727791200.47\nevent: etat\ndata: {\"revision\":\"1727791200.47\",\"sujets\":[],\"discussions_suivies\":false}\n\n"));
    QTRY_COMPARE(discussions.intervalleEffectif(), milliseconds(60000));
    QCOMPARE(page.intervalleEffectif(), milliseconds(120000));
    QVERIFY(banc.flux.libelleEtat().contains(QStringLiteral("Discussions en attente non publiées par le serveur")));

    // Temps réel perdu (repli) : le sondage habituel revient.
    banc.flux.setAnnonce(QStringLiteral("absent"), {});
    QCOMPARE(page.intervalleEffectif(), milliseconds(15000));
}

void TestFluxInvalidation::serviceSuitLaSessionEtLaFenetre()
{
    Banc banc;
    banc.serveur.route("GET", kAccueil, [](const RequeteRecue &) {
        return ReponseFaux::json(200, fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object());
    });
    EventStreamService service(&banc.client, &banc.greffon, nullptr);
    service.invalidation()->setReglages(reglagesRapides()); // sondage léger : 60 s, jamais atteint ici
    service.setAnnonceFlux(QStringLiteral("annonce"), annonce());
    QTest::qWait(80);
    QCOMPARE(banc.ouvertures(), 0); // aucune session : rien
    QCOMPARE(service.libelleTempsReel(), QString());

    service.demarrer();
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);
    QTRY_COMPARE(banc.serveur.compter("GET", kAccueil), 1); // lecture d'ouverture du sondage léger
    QCOMPARE(service.libelleTempsReel(), QStringLiteral("Temps réel : connexion…"));
    banc.serveur.envoyerFlux(trame("ouverture"));
    QTRY_VERIFY(service.tempsReel());
    QCOMPARE(service.libelleTempsReel(), QStringLiteral("Temps réel"));
    // Le badge et la barre d'état suivent le flux : relecture de /v1/accueil au signal.
    QTRY_COMPARE(banc.serveur.compter("GET", kAccueil), 2);
    banc.serveur.envoyerFlux(trame("changement"));
    QTRY_COMPARE(banc.serveur.compter("GET", kAccueil), 3);
    QVERIFY(service.etatSondage().startsWith(QStringLiteral("Toutes les 120 s")));

    // Fenêtre réduite : flux fermé ; rouverte : rouvert.
    service.setFenetreActive(false);
    QTRY_COMPARE(banc.serveur.clientsFlux(), 0);
    service.setFenetreActive(true);
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);
    // Session perdue : fermé, plus rien dit.
    service.arreter();
    QTRY_COMPARE(banc.serveur.clientsFlux(), 0);
    QCOMPARE(service.libelleTempsReel(), QString());
    QVERIFY(service.etatFlux().startsWith(QStringLiteral("Fermé")));
}

// Relecture de P8b (constat desktop-1) : un flux DÉJÀ OUVERT restait ouvert, « Temps réel », quand un verdict de
// /v1/meta bloquait ensuite le greffon (contrat d'une autre majeure) sans changer l'annonce du flux. Échec fermé :
// le verdict qui bloque le greffon ferme aussi son flux, et aucune reprise ne le rouvre tant qu'il dure.
void TestFluxInvalidation::greffonBloqueFermeUnFluxOuvert()
{
    Banc banc;
    banc.ouvrir();
    banc.serveur.envoyerFlux(trame("ouverture"));
    QTRY_COMPARE(banc.flux.mode(), FluxInvalidation::Mode::TempsReel);
    const QString blocage = QStringLiteral("Contrat du greffon incompatible : acp-poste/2, attendu acp-poste/1. Pages du "
                                           "greffon bloquées par la station.");
    banc.greffon.bloquer(blocage);
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce()); // verdict republié : annonce inchangée
    QVERIFY(!banc.flux.connecte());
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::Indisponible);
    QVERIFY(!banc.flux.tempsReel());
    QCOMPARE(banc.flux.raison(), blocage);
    QVERIFY2(banc.flux.libelleEtat().startsWith(QStringLiteral("Non utilisé : Contrat du greffon incompatible")),
             qPrintable(banc.flux.libelleEtat()));
    QTRY_COMPARE(banc.serveur.clientsFlux(), 0);
    const int ouvertures = banc.ouvertures();
    banc.flux.relancer(); // retour du lien : rien ne part vers un greffon bloqué
    QTest::qWait(300);    // une reprise (40 ms ici) l'aurait rouvert
    QCOMPARE(banc.ouvertures(), ouvertures);
    QCOMPARE(banc.flux.mode(), FluxInvalidation::Mode::Indisponible);

    // Verdict suivant, compatible : rouvert, avec la révision déjà lue (même serveur).
    banc.greffon.debloquer();
    banc.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);
    QCOMPARE(banc.serveur.ouverturesFlux.constLast().entete("last-event-id"), QByteArrayLiteral("1727791200.41"));
}

// Relecture de P8b (constat desktop-2) : le repli en sondage (401, ou trois échecs) survivait à la perte de session ; une
// session neuve et valide restait jusqu'à 5 min sans temps réel, et l'état disait « Temps réel indisponible () ».
void TestFluxInvalidation::sessionNeuveOublieLeRepli()
{
    Banc banc;
    banc.serveur.route("GET", kAccueil, [](const RequeteRecue &) {
        return ReponseFaux::json(200, fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object());
    });
    banc.serveur.jetonsAccesValides.clear(); // jeton refusé : 401
    EventStreamService service(&banc.client, &banc.greffon, nullptr);
    service.invalidation()->setReglages(reglagesRapides()); // nouvel essai du repli : dans 1 h
    service.setAnnonceFlux(QStringLiteral("annonce"), annonce());
    service.demarrer();
    QTRY_COMPARE(service.invalidation()->mode(), FluxInvalidation::Mode::Sondage);
    QCOMPARE(service.invalidation()->raison(), QStringLiteral("session refusée par le flux (401)"));
    const int ouvertures = banc.ouvertures();
    QCOMPARE(ouvertures, 1);

    // Session perdue, dans l'ordre d'Application : verdict oublié (annonce « inconnu »), puis temps réel arrêté.
    service.setAnnonceFlux(QStringLiteral("inconnu"), {});
    service.arreter();
    // Session neuve, jeton accepté : le flux s'ouvre AUSSITÔT, sans attendre l'échéance de l'ancien repli.
    banc.serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    service.demarrer();
    service.setAnnonceFlux(QStringLiteral("annonce"), annonce());
    QTRY_COMPARE(banc.ouvertures(), ouvertures + 1);
    QTRY_COMPARE(banc.serveur.clientsFlux(), 1);
    QCOMPARE(service.invalidation()->mode(), FluxInvalidation::Mode::Connexion);
    QVERIFY2(!service.etatFlux().contains(QStringLiteral("()")), qPrintable(service.etatFlux()));
    banc.serveur.envoyerFlux(trame("ouverture"));
    QTRY_VERIFY(service.tempsReel());

    // Même session, repli en cours, annonce retirée puis rendue : le repli reste (son heure), sa raison est dite.
    Banc autre;
    autre.serveur.jetonsAccesValides.clear();
    autre.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    autre.flux.setActif(true);
    QTRY_COMPARE(autre.flux.mode(), FluxInvalidation::Mode::Sondage);
    autre.flux.setAnnonce(QStringLiteral("absent"), {});
    autre.flux.setAnnonce(QStringLiteral("annonce"), annonce());
    QCOMPARE(autre.flux.mode(), FluxInvalidation::Mode::Sondage);
    QVERIFY2(autre.flux.libelleEtat().startsWith(
                 QStringLiteral("Temps réel indisponible (session refusée par le flux (401)) : les pages sont relues par "
                                "sondage ; nouvel essai à ")),
             qPrintable(autre.flux.libelleEtat()));
    QTest::qWait(100);
    QCOMPARE(autre.ouvertures(), 1);
}

QTEST_GUILESS_MAIN(TestFluxInvalidation)

#include "tst_flux_invalidation.moc"
