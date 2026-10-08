// Accueil de la station contre la fixture PARTAGÉE de l'Accueil agrégé
// (hermes/tests/outils/fixtures_accueil/accueil.json, la même que le greffon et la page web) et le
// faux Hermes :
//  - cartes dans l'ordre de l'Accueil du navigateur, libellées en français, « Inconnu » pour toute
//    valeur absente ou d'un autre type, bloc illisible dit avec sa raison, aucune valeur inventée ;
//  - lecture de `GET /v1/accueil` et des sessions récentes seulement quand la page est affichée ET
//    la session établie, avec les chemins et paramètres exacts ;
//  - un échec garde la dernière valeur, datée, avec l'erreur à côté ;
//  - pause générale et notification de test : corps exacts, refus du greffon rendus tels quels.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "models/JsonListModel.h"
#include "services/CompatibiliteHermes.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/AccueilViewModel.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QSignalSpy>
#include <QTest>
#include <QUrl>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");

QJsonObject accueilPartage()
{
    return fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object();
}

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    AccueilViewModel accueil{&client, &greffon, &flux};
    QJsonObject document = accueilPartage();
    int statutAccueil = 200;
    ReponseFaux reponsePause = ReponseFaux::json(200, QJsonObject{{QStringLiteral("pause_generale"), QJsonObject{}}});
    ReponseFaux reponseTest = ReponseFaux::json(202, QJsonObject{
        {QStringLiteral("notification"), QStringLiteral("test:1790886944")}, {QStringLiteral("etat"), QStringLiteral("en_attente")},
        {QStringLiteral("message"), QStringLiteral("Notification de test mise en file : la passerelle l'envoie à sa prochaine passe.")}});

    Banc()
    {
        serveur.installerAuthentification();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
        flux.setIntervalleFond(std::chrono::hours(1));
        serveur.route("GET", kP + QStringLiteral("/accueil"), [this](const RequeteRecue &) {
            return statutAccueil == 200 ? ReponseFaux::json(200, document)
                                        : ReponseFaux::json(statutAccueil, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Not Found")}});
        });
        serveur.route("GET", kP + QStringLiteral("/projets"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projets.json"))); });
        serveur.route("GET", QStringLiteral("/api/sessions"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("sessions.json"))); });
        serveur.route("POST", kP + QStringLiteral("/pause"), [this](const RequeteRecue &) { return reponsePause; });
        serveur.route("POST", kP + QStringLiteral("/notifications/test"), [this](const RequeteRecue &) { return reponseTest; });
        // Route NATIVE de Hermes (cron/jobs.py) : la liste des tâches, puis la création du bilan.
        serveur.route("GET", QStringLiteral("/api/cron/jobs"), [this](const RequeteRecue &) { return ReponseFaux::json(200, taches); });
        serveur.route("POST", QStringLiteral("/api/cron/jobs"), [this](const RequeteRecue &) { return reponseCreation; });
    }
    QJsonArray taches;
    ReponseFaux reponseCreation = ReponseFaux::json(200, QJsonObject{{QStringLiteral("id"), QStringLiteral("j1")}});
};

QString localDepuisIso(const QString &iso)
{
    QString sansFraction = iso;
    sansFraction.remove(QRegularExpression(QStringLiteral("\\.\\d+")));
    return QDateTime::fromString(sansFraction, Qt::ISODate).toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm"));
}

} // namespace

class TestAccueil : public QObject
{
    Q_OBJECT

private slots:
    void carteATraiterDepuisLaFixturePartagee();
    void carteProjetsEtListe();
    void carteExecutant();
    void carteQuotasParVoie();
    void carteNotifications();
    void cartePause();
    void blocsIllisiblesDitsAvecLeurRaison();
    void sessionsRecentes();
    void litLAccueilEtLesSessionsQuandLaPageEstAffichee();
    void neLitRienSansSessionNiHorsDeLaPage();
    void echecGardeLaDerniereValeur();
    void pauseGeneraleCorpsExactEtRefusTelQuel();
    void notificationDeTestSeulementAvecUnCanal();
    void carteHermesRelueAvecLaPage();
    void carteBilanCommeLaPageWeb();
    void creerLeBilanQuotidienEtOuvrirCron();
};

void TestAccueil::carteATraiterDepuisLaFixturePartagee()
{
    const QVariantMap carte = AccueilViewModel::construireCarteATraiter(accueilPartage());
    QCOMPARE(carte.value(QStringLiteral("lisible")).toBool(), true);
    QCOMPARE(carte.value(QStringLiteral("total")).toString(), QStringLiteral("1"));
    QCOMPARE(carte.value(QStringLiteral("attente")).toBool(), true);
    QCOMPARE(carte.value(QStringLiteral("questions")).toString(), QStringLiteral("1"));
    QCOMPARE(carte.value(QStringLiteral("decisions")).toString(), QStringLiteral("0"));
    QCOMPARE(carte.value(QStringLiteral("revues")).toString(), QStringLiteral("0"));
    QCOMPARE(carte.value(QStringLiteral("arretees")).toString(), QStringLiteral("0"));
    QCOMPARE(carte.value(QStringLiteral("chezHermes")).toString(), QStringLiteral("0"));
    // Les discussions en attente ne sont pas lues par la station : dites inconnues, jamais zéro.
    QCOMPARE(carte.value(QStringLiteral("discussions")).toString(), QStringLiteral("Inconnues"));
    QCOMPARE(carte.value(QStringLiteral("mention")).toString(), QStringLiteral("(discussions en attente : état inconnu, non comptées)"));
    const QVariantList premieres = carte.value(QStringLiteral("premieres")).toList();
    QCOMPARE(premieres.size(), 1);
    const QVariantMap premiere = premieres.first().toMap();
    QCOMPARE(premiere.value(QStringLiteral("genre")).toString(), QStringLiteral("Question :"));
    QCOMPARE(premiere.value(QStringLiteral("titre")).toString(), QStringLiteral("Exploration du dépôt « jetable »"));
    QCOMPARE(premiere.value(QStringLiteral("projet")).toString(), QStringLiteral("Outil jetable"));
}

void TestAccueil::carteProjetsEtListe()
{
    const QJsonObject document = accueilPartage();
    const QVariantMap carte = AccueilViewModel::construireCarteProjets(document);
    QCOMPARE(carte.value(QStringLiteral("lisible")).toBool(), true);
    QCOMPARE(carte.value(QStringLiteral("enCours")).toString(), QStringLiteral("1"));
    QCOMPARE(carte.value(QStringLiteral("enPause")).toString(), QStringLiteral("0"));
    QCOMPARE(carte.value(QStringLiteral("termines7j")).toString(), QStringLiteral("0"));
    QCOMPARE(carte.value(QStringLiteral("aucunOuvert")).toBool(), false);
    const QJsonArray liste = AccueilViewModel::construireProjetsEnCours(document);
    QCOMPARE(liste.size(), 1);
    const QJsonObject projet = liste.first().toObject();
    QCOMPARE(projet.value(QStringLiteral("id")).toString(), QStringLiteral("p_7886b97a0890"));
    QCOMPARE(projet.value(QStringLiteral("titre")).toString(), QStringLiteral("Outil jetable"));
    QCOMPARE(projet.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Exploration du dépôt"));
    QCOMPARE(projet.value(QStringLiteral("avancement")).toString(), QStringLiteral("0 sur 2 cartes faites"));
    QCOMPARE(projet.value(QStringLiteral("note")).toString(), QString());

    // Liste vide : « Aucun projet ouvert » ; une ligne sans identifiant lisible ne désigne rien.
    QJsonObject vide = document;
    QJsonObject projets = vide.value(QStringLiteral("projets")).toObject();
    projets.insert(QStringLiteral("liste"), QJsonArray{});
    vide.insert(QStringLiteral("projets"), projets);
    QCOMPARE(AccueilViewModel::construireCarteProjets(vide).value(QStringLiteral("aucunOuvert")).toBool(), true);
    projets.insert(QStringLiteral("liste"), QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("../x")}}});
    vide.insert(QStringLiteral("projets"), projets);
    QCOMPARE(AccueilViewModel::construireProjetsEnCours(vide).size(), 0);
}

void TestAccueil::carteExecutant()
{
    const QVariantMap carte = AccueilViewModel::construireCarteExecutant(accueilPartage());
    QCOMPARE(carte.value(QStringLiteral("lisible")).toBool(), true);
    QCOMPARE(carte.value(QStringLiteral("etat")).toString(), QStringLiteral("En ligne"));
    QCOMPARE(carte.value(QStringLiteral("cle")).toString(), QStringLiteral("succeeded"));
    QCOMPARE(carte.value(QStringLiteral("machine")).toString(), QStringLiteral("Exécutant Railway"));
    QCOMPARE(carte.value(QStringLiteral("plateforme")).toString(), QStringLiteral("linux"));
    QCOMPARE(carte.value(QStringLiteral("derniereVue")).toString(),
             QDateTime::fromSecsSinceEpoch(1790886944).toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm")));
    QCOMPARE(carte.value(QStringLiteral("carteEnCours")).toString(),
             QStringLiteral("Exploration du dépôt « jetable » (projet « Outil jetable ») · Suspendue"));
    QCOMPARE(carte.value(QStringLiteral("cartesEnAttente")).toString(), QStringLiteral("0"));
    QVERIFY(carte.value(QStringLiteral("voiesFermees")).toString().startsWith(QStringLiteral("Poste (Codex) : isolement de l'exécutant")));

    // Aucune voie fermée : « Aucune » ; forme inattendue : « Inconnu » ; aucune carte en main.
    QJsonObject document = accueilPartage();
    QJsonObject executant = document.value(QStringLiteral("executant")).toObject();
    executant.insert(QStringLiteral("voies_fermees"), QJsonObject{});
    executant.insert(QStringLiteral("carte_en_cours"), QJsonValue::Null);
    document.insert(QStringLiteral("executant"), executant);
    const QVariantMap libre = AccueilViewModel::construireCarteExecutant(document);
    QCOMPARE(libre.value(QStringLiteral("voiesFermees")).toString(), QStringLiteral("Aucune"));
    QCOMPARE(libre.value(QStringLiteral("carteEnCours")).toString(), QStringLiteral("Aucune carte en cours"));
    executant.insert(QStringLiteral("voies_fermees"), QJsonArray{QStringLiteral("poste-codex")});
    executant.remove(QStringLiteral("nom"));
    document.insert(QStringLiteral("executant"), executant);
    const QVariantMap etrange = AccueilViewModel::construireCarteExecutant(document);
    QCOMPARE(etrange.value(QStringLiteral("voiesFermees")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(etrange.value(QStringLiteral("machine")).toString(), QStringLiteral("Inconnu"));
}

void TestAccueil::carteQuotasParVoie()
{
    const QVariantMap carte = AccueilViewModel::construireCarteQuotas(accueilPartage());
    QCOMPARE(carte.value(QStringLiteral("lisible")).toBool(), true);
    const QVariantList voies = carte.value(QStringLiteral("voies")).toList();
    QCOMPARE(voies.size(), 2);
    const QVariantMap codex = voies.at(0).toMap();
    QCOMPARE(codex.value(QStringLiteral("nom")).toString(), QStringLiteral("Poste (Codex)"));
    QCOMPARE(codex.value(QStringLiteral("etat")).toString(), QStringLiteral("Relevé"));
    QCOMPARE(codex.value(QStringLiteral("utilise")).toString(), QStringLiteral("41 %"));
    QCOMPARE(codex.value(QStringLiteral("source")).toString(),
             QStringLiteral("Compteurs de votre compte ChatGPT, lus par Codex (app-server) sur la machine qui exécute"));
    QVERIFY(codex.value(QStringLiteral("remise")).toString() != QStringLiteral("Inconnu"));
    const QVariantMap claude = voies.at(1).toMap();
    QCOMPARE(claude.value(QStringLiteral("nom")).toString(), QStringLiteral("Poste (Claude)"));
    QCOMPARE(claude.value(QStringLiteral("utilise")).toString(), QStringLiteral("Inconnu")); // aucun résumé : jamais estimé
    QCOMPARE(claude.value(QStringLiteral("remise")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(carte.value(QStringLiteral("hermes")).toString(), QStringLiteral("Même enveloppe que Codex (déclaré dans poste.toml)"));
}

void TestAccueil::carteNotifications()
{
    const QVariantMap ntfy = AccueilViewModel::construireCarteNotifications(accueilPartage());
    QCOMPARE(ntfy.value(QStringLiteral("canal")).toString(), QStringLiteral("ntfy"));
    QCOMPARE(ntfy.value(QStringLiteral("etat")).toString(), QStringLiteral("Configurées"));
    QCOMPARE(ntfy.value(QStringLiteral("configure")).toBool(), true);
    QCOMPARE(ntfy.value(QStringLiteral("note")).toString(), QString());
    // Passerelle muette : état inconnu, jamais « non configurées » ; le message du greffon est rendu tel quel.
    QJsonObject document = accueilPartage();
    document.insert(QStringLiteral("notifications"), QJsonObject{
        {QStringLiteral("canal"), QJsonValue::Null}, {QStringLiteral("configure"), false}, {QStringLiteral("connu"), false},
        {QStringLiteral("message"), QStringLiteral("État du canal inconnu : la passerelle ne l'a pas encore publié.")}});
    const QVariantMap inconnu = AccueilViewModel::construireCarteNotifications(document);
    QCOMPARE(inconnu.value(QStringLiteral("canal")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(inconnu.value(QStringLiteral("etat")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(inconnu.value(QStringLiteral("configure")).toBool(), false);
    QCOMPARE(inconnu.value(QStringLiteral("note")).toString(), QStringLiteral("État du canal inconnu : la passerelle ne l'a pas encore publié."));
    document.insert(QStringLiteral("notifications"), QJsonObject{
        {QStringLiteral("canal"), QStringLiteral("aucune")}, {QStringLiteral("configure"), false}, {QStringLiteral("connu"), true}});
    const QVariantMap aucun = AccueilViewModel::construireCarteNotifications(document);
    QCOMPARE(aucun.value(QStringLiteral("canal")).toString(), QStringLiteral("Aucun"));
    QCOMPARE(aucun.value(QStringLiteral("etat")).toString(), QStringLiteral("Non configurées"));
}

void TestAccueil::cartePause()
{
    // Fixture partagée : pause levée (`null`).
    const QVariantMap levee = AccueilViewModel::construireCartePause(accueilPartage());
    QCOMPARE(levee.value(QStringLiteral("etat")).toInt(), 0);
    QCOMPARE(levee.value(QStringLiteral("pausePossible")).toBool(), true);
    QCOMPARE(levee.value(QStringLiteral("reprisePossible")).toBool(), false);

    const QJsonObject pause = fixture(QStringLiteral("pause-generale.json"));
    const QVariantMap engagee = AccueilViewModel::construireCartePause(QJsonObject{{QStringLiteral("pause_generale"), pause}});
    QCOMPARE(engagee.value(QStringLiteral("etat")).toInt(), 1);
    QCOMPARE(engagee.value(QStringLiteral("raison")).toString(), QStringLiteral("ACP : pause du propriétaire"));
    QCOMPARE(engagee.value(QStringLiteral("depuis")).toString(), localDepuisIso(pause.value(QStringLiteral("engaged_at")).toString()));
    QCOMPARE(engagee.value(QStringLiteral("reprisePossible")).toBool(), true);
    QCOMPARE(engagee.value(QStringLiteral("pausePossible")).toBool(), false);

    // Engagée par la veille des crochets shell : aucun bouton « Reprendre » qui échouerait.
    const QVariantMap crochets = AccueilViewModel::construireCartePause(QJsonObject{
        {QStringLiteral("pause_generale"),
         QJsonObject{{QStringLiteral("reason"), QStringLiteral("ACP : crochets shell détectés en cours de route")}}}});
    QCOMPARE(crochets.value(QStringLiteral("crochets")).toBool(), true);
    QCOMPARE(crochets.value(QStringLiteral("reprisePossible")).toBool(), false);

    const QVariantMap inconnue = AccueilViewModel::construireCartePause({});
    QCOMPARE(inconnue.value(QStringLiteral("etat")).toInt(), -1);
    QCOMPARE(inconnue.value(QStringLiteral("libelle")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(inconnue.value(QStringLiteral("pausePossible")).toBool(), false);
}

void TestAccueil::blocsIllisiblesDitsAvecLeurRaison()
{
    // accueil.construire : un bloc illisible vaut `null` et sa raison est rangée dans `illisibles`.
    QJsonObject document = accueilPartage();
    QJsonObject illisibles;
    for (const QString &bloc : {QStringLiteral("a_traiter"), QStringLiteral("projets"), QStringLiteral("executant"),
                                QStringLiteral("quotas"), QStringLiteral("notifications"), QStringLiteral("pause_generale")}) {
        document.insert(bloc, QJsonValue::Null);
        illisibles.insert(bloc, QStringLiteral("bloc illisible (OperationalError)"));
    }
    document.insert(QStringLiteral("illisibles"), illisibles);
    const QVariantMap aTraiter = AccueilViewModel::construireCarteATraiter(document);
    QCOMPARE(aTraiter.value(QStringLiteral("lisible")).toBool(), false);
    QCOMPARE(aTraiter.value(QStringLiteral("raison")).toString(), QStringLiteral("bloc illisible (OperationalError)"));
    QCOMPARE(aTraiter.value(QStringLiteral("total")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(AccueilViewModel::construireCarteProjets(document).value(QStringLiteral("enCours")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(AccueilViewModel::construireCarteExecutant(document).value(QStringLiteral("etat")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(AccueilViewModel::construireCarteQuotas(document).value(QStringLiteral("lisible")).toBool(), false);
    QCOMPARE(AccueilViewModel::construireCarteNotifications(document).value(QStringLiteral("configure")).toBool(), false);
    // Pause illisible : `null` n'est PAS « levée » — aucun geste offert, la raison est dite.
    const QVariantMap pause = AccueilViewModel::construireCartePause(document);
    QCOMPARE(pause.value(QStringLiteral("etat")).toInt(), -1);
    QCOMPARE(pause.value(QStringLiteral("pausePossible")).toBool(), false);
    QCOMPARE(pause.value(QStringLiteral("raisonIllisible")).toString(), QStringLiteral("bloc illisible (OperationalError)"));
}

void TestAccueil::sessionsRecentes()
{
    QJsonObject page = fixture(QStringLiteral("sessions.json"));
    QJsonArray sessions = page.value(QStringLiteral("sessions")).toArray();
    sessions.append(QJsonObject{{QStringLiteral("title"), QStringLiteral("sans identifiant")}});
    page.insert(QStringLiteral("sessions"), sessions);
    const QJsonArray lignes = AccueilViewModel::construireSessions(page);
    QCOMPARE(lignes.size(), 2); // une ligne sans identifiant ne désigne rien
    QCOMPARE(lignes.at(0).toObject().value(QStringLiteral("titre")).toString(), QStringLiteral("Plan du site vitrine"));
    QCOMPARE(lignes.at(0).toObject().value(QStringLiteral("messages")).toString(), QStringLiteral("12"));
    QCOMPARE(lignes.at(1).toObject().value(QStringLiteral("titre")).toString(), QStringLiteral("Sans titre"));
    QCOMPARE(lignes.at(1).toObject().value(QStringLiteral("actifA")).toString(),
             QDateTime::fromSecsSinceEpoch(1790200500).toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm")));
}

void TestAccueil::litLAccueilEtLesSessionsQuandLaPageEstAffichee()
{
    Banc banc;
    banc.flux.demarrer();
    QTRY_COMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/accueil")), 1); // sondage léger (barre d'état)
    banc.accueil.setPageVisible(true);
    QTRY_VERIFY(banc.accueil.actif());
    QTRY_COMPARE(banc.accueil.sessions()->count(), 2);
    QTRY_VERIFY(banc.accueil.lue());
    QCOMPARE(banc.accueil.carteATraiter().value(QStringLiteral("total")).toString(), QStringLiteral("1"));
    QCOMPARE(banc.accueil.projetsEnCours()->count(), 1);
    QCOMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/accueil")), 2); // sondage léger + page
    QCOMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/quotas")), 0); // plus de lecture séparée
    QCOMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/projets")), 0);
    // La barre d'état suit la lecture de la page.
    QCOMPARE(banc.flux.aTraiter(), 1);
    const auto sessions = banc.serveur.filtrer("GET", QStringLiteral("/api/sessions"));
    QCOMPARE(sessions.size(), 1);
    QCOMPARE(sessions.first().requete.queryItemValue(QStringLiteral("limit")), QStringLiteral("5"));
    QCOMPARE(sessions.first().requete.queryItemValue(QStringLiteral("offset")), QStringLiteral("0"));
    QCOMPARE(sessions.first().requete.queryItemValue(QStringLiteral("order")), QStringLiteral("recent"));
    for (const RequeteRecue &requete : std::as_const(banc.serveur.requetes)) {
        QCOMPARE(requete.entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
        QVERIFY(!requete.aEntete("origin"));
    }
    QVERIFY(banc.accueil.lectureAccueil().startsWith(QStringLiteral("Lu à ")));
    QCOMPARE(banc.accueil.erreurAccueil(), QString());

    // Page quittée : plus aucune lecture de la page.
    banc.accueil.setPageVisible(false);
    QTRY_VERIFY(!banc.accueil.actif());
    const int avant = banc.serveur.compter("GET", kP + QStringLiteral("/accueil"));
    banc.flux.signalerLien(false);
    banc.flux.signalerLien(true); // retour du lien : la page cachée ne relit pas
    QTest::qWait(200);
    QCOMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/accueil")), avant + 1); // seul le sondage léger relit
}

void TestAccueil::neLitRienSansSessionNiHorsDeLaPage()
{
    Banc banc;
    banc.accueil.setPageVisible(true);
    QTest::qWait(200);
    QVERIFY(!banc.accueil.actif());
    QVERIFY(banc.serveur.requetes.isEmpty()); // aucune session : rien ne part
    QCOMPARE(banc.accueil.lue(), false);
    QCOMPARE(banc.accueil.carteATraiter().value(QStringLiteral("total")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(banc.accueil.lectureAccueil(), QStringLiteral("Jamais lu"));

    banc.flux.demarrer();
    QTRY_VERIFY(banc.accueil.actif());
    banc.flux.setFenetreActive(false); // fenêtre réduite
    QTRY_VERIFY(!banc.accueil.actif());
}

void TestAccueil::echecGardeLaDerniereValeur()
{
    Banc banc;
    banc.flux.demarrer();
    banc.accueil.setPageVisible(true);
    QTRY_COMPARE(banc.accueil.carteATraiter().value(QStringLiteral("total")).toString(), QStringLiteral("1"));
    const QString luA = banc.accueil.lectureAccueil();

    banc.statutAccueil = 404;
    banc.accueil.actualiser();
    QTRY_VERIFY(!banc.accueil.erreurAccueil().isEmpty());
    QCOMPARE(banc.accueil.carteATraiter().value(QStringLiteral("total")).toString(), QStringLiteral("1"));
    QCOMPARE(banc.accueil.carteExecutant().value(QStringLiteral("etat")).toString(), QStringLiteral("En ligne"));
    QCOMPARE(banc.accueil.lectureAccueil(), luA);
}

void TestAccueil::pauseGeneraleCorpsExactEtRefusTelQuel()
{
    Banc banc;
    banc.flux.demarrer();
    banc.accueil.setPageVisible(true);
    QTRY_VERIFY(banc.accueil.actif());

    banc.accueil.basculerPause(true, QStringLiteral("maintenance du poste"));
    QTRY_VERIFY(!banc.accueil.gesteEnCours());
    QVERIFY(banc.accueil.messageGeste().startsWith(QStringLiteral("Pause générale engagée")));
    QCOMPARE(banc.accueil.erreurGeste(), QString());
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/pause"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), (QJsonObject{{QStringLiteral("generale"), true},
                                                 {QStringLiteral("raison"), QStringLiteral("maintenance du poste")}}));
    QVERIFY(envois.first().entete("content-type").startsWith("application/json"));
    QVERIFY(!envois.first().aEntete("origin"));

    // Reprise refusée par le greffon (crochets shell) : son message, tel quel.
    const QString refus = QStringLiteral("Reprise refusée : crochets shell encore présents (hooks dans config.yaml).");
    banc.reponsePause = ReponseFaux::json(409, QJsonObject{{QStringLiteral("detail"),
                                                            QJsonObject{{QStringLiteral("code"), QStringLiteral("crochets")},
                                                                        {QStringLiteral("message"), refus}}}});
    banc.accueil.basculerPause(false, QString());
    QTRY_VERIFY(!banc.accueil.gesteEnCours());
    QCOMPARE(banc.accueil.erreurGeste(), refus);
    QCOMPARE(banc.accueil.messageGeste(), QString());
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/pause")).last().json(),
             (QJsonObject{{QStringLiteral("generale"), false}}));

    // Raison trop longue : refusée par la station, rien n'est émis.
    banc.accueil.basculerPause(true, QString(201, QLatin1Char('x')));
    QTRY_VERIFY(!banc.accueil.gesteEnCours());
    QVERIFY(banc.accueil.erreurGeste().contains(QStringLiteral("200 caractères")));
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/pause")).size(), 2);
}

void TestAccueil::notificationDeTestSeulementAvecUnCanal()
{
    Banc banc;
    banc.flux.demarrer();
    banc.accueil.setPageVisible(true);
    QTRY_VERIFY(banc.accueil.lue());
    QCOMPARE(banc.accueil.carteNotifications().value(QStringLiteral("configure")).toBool(), true);
    banc.accueil.envoyerNotificationDeTest();
    QTRY_VERIFY(!banc.accueil.gesteEnCours());
    QCOMPARE(banc.accueil.messageGeste(), QStringLiteral("Notification de test mise en file : la passerelle l'envoie à sa prochaine passe."));
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/notifications/test"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), QJsonObject{});
    QCOMPARE(envois.first().entete("content-type"), QByteArrayLiteral("application/json"));

    // 409 du greffon (canal retiré entre-temps) : son message tel quel.
    const QString message = QStringLiteral("Notifications non configurées : posez les variables du canal dans Railway.");
    banc.reponseTest = ReponseFaux::json(409, QJsonObject{{QStringLiteral("detail"), QJsonObject{
        {QStringLiteral("code"), QStringLiteral("notifications")}, {QStringLiteral("message"), message}}}});
    banc.accueil.envoyerNotificationDeTest();
    QTRY_VERIFY(!banc.accueil.gesteEnCours());
    QCOMPARE(banc.accueil.erreurGeste(), message);

    // Canal lu non configuré : rien n'est envoyé.
    banc.document.insert(QStringLiteral("notifications"), QJsonObject{
        {QStringLiteral("canal"), QStringLiteral("aucune")}, {QStringLiteral("configure"), false}, {QStringLiteral("connu"), true}});
    banc.accueil.actualiser();
    QTRY_VERIFY(!banc.accueil.carteNotifications().value(QStringLiteral("configure")).toBool());
    banc.accueil.envoyerNotificationDeTest();
    QCOMPARE(banc.accueil.erreurGeste(), QStringLiteral("Aucun canal de notifications configuré : rien n'est envoyé."));
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/notifications/test")).size(), 2);
}

// Constat de relecture P8 : la carte « Hermes » (version, verdict, alertes) n'était relue ni
// par le sondage de la page ni par « Actualiser », alors que la page l'annonçait relue.
void TestAccueil::carteHermesRelueAvecLaPage()
{
    Banc banc;
    CompatibiliteHermes compatibilite(&banc.greffon);
    banc.accueil.setCompatibilite(&compatibilite);
    QJsonObject meta = fixture(QStringLiteral("meta.json"));
    int statutMeta = 200;
    banc.serveur.route("GET", kP + QStringLiteral("/meta"), [&meta, &statutMeta](const RequeteRecue &) {
        return statutMeta == 200 ? ReponseFaux::json(200, meta)
                                 : ReponseFaux::json(statutMeta, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Indisponible")}});
    });
    const auto avecVersion = [&meta](const QString &version, const QJsonArray &alertes) {
        QJsonObject hermes = meta.value(QStringLiteral("hermes")).toObject();
        hermes.insert(QStringLiteral("version"), version);
        meta.insert(QStringLiteral("hermes"), hermes);
        meta.insert(QStringLiteral("alertes"), alertes);
    };
    QCOMPARE(compatibilite.lecture(), QStringLiteral("Jamais lu"));
    banc.flux.demarrer();
    banc.accueil.setPageVisible(true);
    QTRY_COMPARE(compatibilite.etat(), CompatibilityStatus::Compatible);
    QVERIFY(compatibilite.lecture().startsWith(QStringLiteral("Lu à ")));

    // Hermes redéployé : « Actualiser » relit /v1/meta.
    avecVersion(QStringLiteral("0.22.0"), QJsonArray{QStringLiteral("Hermes redéployé en 0.22.0")});
    banc.accueil.actualiser();
    QTRY_COMPARE(compatibilite.versionHermes(), QStringLiteral("0.22.0"));
    QCOMPARE(compatibilite.alertes().size(), 1);
    QCOMPARE(compatibilite.etat(), CompatibilityStatus::Avertissement);

    // Puis le sondage de la page, sans geste.
    banc.accueil.setIntervalle(std::chrono::milliseconds(100));
    avecVersion(QStringLiteral("0.22.1"), QJsonArray{});
    QTRY_COMPARE(compatibilite.versionHermes(), QStringLiteral("0.22.1"));

    // Lecture en échec : le dernier verdict reste, daté, l'erreur à côté.
    statutMeta = 403;
    QTRY_VERIFY(!compatibilite.erreurLecture().isEmpty());
    QCOMPARE(compatibilite.versionHermes(), QStringLiteral("0.22.1"));
    QVERIFY(compatibilite.lecture().startsWith(QStringLiteral("Lu à ")));
    // 404 : greffon absent, verdict rendu (et appliqué au client du greffon).
    statutMeta = 404;
    QTRY_COMPARE(compatibilite.etat(), CompatibilityStatus::GreffonAbsent);
    QVERIFY(banc.greffon.bloque());
    banc.accueil.setPageVisible(false);
}

QJsonObject tache(const QJsonObject &champs)
{
    // Forme d'une tâche de Hermes (cron/jobs.py) : seuls les champs lus par la carte, plus les champs du bilan.
    QJsonObject t{{QStringLiteral("id"), QStringLiteral("j1")}, {QStringLiteral("name"), QStringLiteral("Bilan ACP")},
                  {QStringLiteral("script"), QStringLiteral("acp-bilan.py")}, {QStringLiteral("no_agent"), true},
                  {QStringLiteral("enabled"), true}, {QStringLiteral("state"), QStringLiteral("scheduled")},
                  {QStringLiteral("next_run_at"), QStringLiteral("2026-10-09T06:00:00+00:00")},
                  {QStringLiteral("last_run_at"), QJsonValue::Null}, {QStringLiteral("last_status"), QJsonValue::Null}};
    for (auto it = champs.begin(); it != champs.end(); ++it) {
        t.insert(it.key(), it.value());
    }
    return t;
}

void TestAccueil::carteBilanCommeLaPageWeb()
{
    // Tâche du bilan : sans agent, 8 h, livrée en local (accueil-api.ts, TACHE_BILAN).
    QCOMPARE(AccueilViewModel::tacheBilan(),
             (QJsonObject{{QStringLiteral("name"), QStringLiteral("Bilan ACP")}, {QStringLiteral("schedule"), QStringLiteral("0 8 * * *")},
                          {QStringLiteral("prompt"), QString()}, {QStringLiteral("no_agent"), true},
                          {QStringLiteral("script"), QStringLiteral("acp-bilan.py")}, {QStringLiteral("deliver"), QStringLiteral("local")}}));
    // Seules les tâches du script de l'image, SANS agent ; liste nue ou `{jobs}` ; autre forme : illisible.
    const QJsonArray melange{tache({}), tache({{QStringLiteral("no_agent"), false}}),
                             tache({{QStringLiteral("script"), QStringLiteral("autre.py")}})};
    QCOMPARE(AccueilViewModel::tachesDuBilan(melange)->size(), 1);
    QCOMPARE(AccueilViewModel::tachesDuBilan(QJsonObject{{QStringLiteral("jobs"), melange}})->size(), 1);
    QVERIFY(!AccueilViewModel::tachesDuBilan(QJsonObject{{QStringLiteral("taches"), melange}}).has_value());

    QJsonObject accueil = accueilPartage();
    // Rien de lu : ni état ni geste ; lecture en échec : dit, jamais « Non créé ».
    QVariantMap carte = AccueilViewModel::construireCarteBilan(std::nullopt, accueil, QString());
    QCOMPARE(carte.value(QStringLiteral("lu")).toBool(), false);
    QCOMPARE(carte.value(QStringLiteral("peutCreer")).toBool(), false);
    QCOMPARE(carte.value(QStringLiteral("illisible")).toString(), QString());
    carte = AccueilViewModel::construireCarteBilan(std::nullopt, accueil, QStringLiteral("Hermes injoignable"));
    QCOMPARE(carte.value(QStringLiteral("illisible")).toString(),
             QStringLiteral("État du bilan inconnu : la liste des tâches cron de Hermes ne répond pas."));
    QCOMPARE(carte.value(QStringLiteral("peutCreer")).toBool(), false);

    carte = AccueilViewModel::construireCarteBilan(QJsonArray{}, accueil, QString());
    QCOMPARE(carte.value(QStringLiteral("etat")).toString(), QStringLiteral("Non créé"));
    QCOMPARE(carte.value(QStringLiteral("peutCreer")).toBool(), true);
    QVERIFY(carte.value(QStringLiteral("explication")).toString().startsWith(QStringLiteral("Une notification par jour, à 8 h")));

    carte = AccueilViewModel::construireCarteBilan(QJsonArray{tache({})}, accueil, QString());
    QCOMPARE(carte.value(QStringLiteral("etat")).toString(), QStringLiteral("Actif"));
    QCOMPARE(carte.value(QStringLiteral("cle")).toString(), QStringLiteral("succeeded"));
    QCOMPARE(carte.value(QStringLiteral("prochaine")).toString(), localDepuisIso(QStringLiteral("2026-10-09T06:00:00+00:00")));
    QCOMPARE(carte.value(QStringLiteral("derniere")).toString(), QStringLiteral("Jamais"));
    QCOMPARE(carte.value(QStringLiteral("alerte")).toString(), QString());
    QCOMPARE(carte.value(QStringLiteral("peutCreer")).toBool(), false);

    // Exécutée sans issue publiée : jamais un échec supposé (relecture finale de P7, produit-2).
    carte = AccueilViewModel::construireCarteBilan(
        QJsonArray{tache({{QStringLiteral("last_run_at"), QStringLiteral("2026-10-08T06:00:01+00:00")}})}, accueil, QString());
    QCOMPARE(carte.value(QStringLiteral("alerte")).toString(), QString());
    QCOMPARE(carte.value(QStringLiteral("derniere")).toString(), localDepuisIso(QStringLiteral("2026-10-08T06:00:01+00:00")));
    // Issue publiée autre que « ok » : alerte, avec l'issue et le message de Hermes.
    carte = AccueilViewModel::construireCarteBilan(
        QJsonArray{tache({{QStringLiteral("last_run_at"), QStringLiteral("2026-10-08T06:00:01+00:00")},
                          {QStringLiteral("last_status"), QStringLiteral("error")},
                          {QStringLiteral("last_error"), QStringLiteral("script exited with status 1")}})},
        accueil, QString());
    QVERIFY(carte.value(QStringLiteral("alerte")).toString().startsWith(QStringLiteral("Dernière exécution en échec")));
    QCOMPARE(carte.value(QStringLiteral("statut")).toString(), QStringLiteral("error"));
    QCOMPARE(carte.value(QStringLiteral("message")).toString(), QStringLiteral("script exited with status 1"));
    // En pause : ni prochaine exécution ni alerte ; en erreur : alerte de la tâche.
    carte = AccueilViewModel::construireCarteBilan(QJsonArray{tache({{QStringLiteral("enabled"), false}})}, accueil, QString());
    QCOMPARE(carte.value(QStringLiteral("etat")).toString(), QStringLiteral("En pause"));
    QCOMPARE(carte.value(QStringLiteral("prochaine")).toString(), QString());
    carte = AccueilViewModel::construireCarteBilan(QJsonArray{tache({{QStringLiteral("state"), QStringLiteral("error")}})}, accueil, QString());
    QCOMPARE(carte.value(QStringLiteral("etat")).toString(), QStringLiteral("En erreur"));
    QVERIFY(carte.value(QStringLiteral("alerte")).toString().startsWith(QStringLiteral("Hermes a mis la tâche en erreur")));
    // Deux tâches : dit.
    carte = AccueilViewModel::construireCarteBilan(QJsonArray{tache({}), tache({})}, accueil, QString());
    QCOMPARE(carte.value(QStringLiteral("plusieurs")).toString(),
             QStringLiteral("Plusieurs tâches du bilan existent : gardez-en une depuis la page Cron."));
    // Canal non configuré (bloc `notifications` de /v1/accueil) : le bilan ne partira pas, et c'est dit.
    QJsonObject sansCanal = accueil;
    sansCanal.insert(QStringLiteral("notifications"), QJsonObject{{QStringLiteral("connu"), true}, {QStringLiteral("configure"), false}});
    QCOMPARE(AccueilViewModel::construireCarteBilan(QJsonArray{tache({})}, sansCanal, QString()).value(QStringLiteral("sansCanal")).toString(),
             QStringLiteral("Le bilan ne partira pas : notifications non configurées."));
    QJsonObject inconnu = accueil;
    inconnu.insert(QStringLiteral("notifications"), QJsonObject{{QStringLiteral("connu"), false}});
    QCOMPARE(AccueilViewModel::construireCarteBilan(QJsonArray{tache({})}, inconnu, QString()).value(QStringLiteral("sansCanal")).toString(),
             QString());
}

void TestAccueil::creerLeBilanQuotidienEtOuvrirCron()
{
    Banc banc;
    QList<QUrl> ouvertes;
    banc.accueil.setOuvreur([&ouvertes](const QUrl &url) {
        ouvertes.append(url);
        return true;
    });
    banc.flux.demarrer();
    banc.accueil.setPageVisible(true);
    QTRY_VERIFY(banc.accueil.carteBilan().value(QStringLiteral("lu")).toBool());
    QCOMPARE(banc.accueil.carteBilan().value(QStringLiteral("etat")).toString(), QStringLiteral("Non créé"));
    QCOMPARE(banc.serveur.filtrer("GET", QStringLiteral("/api/cron/jobs")).first().entete("authorization"),
             QByteArrayLiteral("Bearer jeton-a"));

    // Création : corps EXACT, message, relecture (la tâche existe alors : plus de bouton).
    banc.taches = QJsonArray{tache({})};
    banc.accueil.creerBilanQuotidien();
    QTRY_VERIFY(!banc.accueil.gesteEnCours());
    QCOMPARE(banc.accueil.messageGeste(), QStringLiteral("Bilan quotidien créé."));
    const auto envois = banc.serveur.filtrer("POST", QStringLiteral("/api/cron/jobs"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), AccueilViewModel::tacheBilan());
    QTRY_COMPARE(banc.accueil.carteBilan().value(QStringLiteral("etat")).toString(), QStringLiteral("Actif"));
    // Le bilan existe : jamais un doublon, rien n'est émis.
    banc.accueil.creerBilanQuotidien();
    QCOMPARE(banc.accueil.erreurGeste(), QStringLiteral("Le bilan quotidien existe déjà : rien n'est créé."));
    QCOMPARE(banc.serveur.filtrer("POST", QStringLiteral("/api/cron/jobs")).size(), 1);

    // Refus de la route native (anglais) : dit en français, détail à la suite.
    banc.taches = QJsonArray{};
    banc.accueil.actualiser();
    QTRY_COMPARE(banc.accueil.carteBilan().value(QStringLiteral("etat")).toString(), QStringLiteral("Non créé"));
    banc.reponseCreation = ReponseFaux::json(400, QJsonObject{{QStringLiteral("detail"), QStringLiteral("script does not exist")}});
    banc.accueil.creerBilanQuotidien();
    QTRY_VERIFY(!banc.accueil.gesteEnCours());
    QVERIFY2(banc.accueil.erreurGeste().startsWith(QStringLiteral("Le bilan n'a pas été créé : Hermes a refusé la tâche (")),
             qPrintable(banc.accueil.erreurGeste()));

    // Page Cron de Hermes : dans le navigateur, sous le préfixe du serveur.
    QVERIFY(banc.accueil.ouvrirCron());
    QCOMPARE(ouvertes.size(), 1);
    QCOMPARE(ouvertes.first(), banc.client.resolve(QStringLiteral("/cron")));
    QCOMPARE(banc.accueil.messageGeste(), QStringLiteral("Page Cron de Hermes ouverte dans le navigateur."));
}

QTEST_MAIN(TestAccueil)
#include "tst_accueil.moc"
