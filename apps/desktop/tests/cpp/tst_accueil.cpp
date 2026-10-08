// Accueil de la station contre les formes relevées sur l'image (tests/fixtures/hermes) et le
// faux Hermes :
//  - cartes libellées en français, « Inconnu » pour toute valeur absente ou d'un autre type,
//    « Non configuré » pour un poste jamais vu, aucune valeur inventée ;
//  - lecture des trois sources (projets, quotas, sessions récentes) seulement quand la page
//    est affichée ET la session établie, avec les chemins et paramètres exacts ;
//  - un échec garde la dernière valeur, datée, avec l'erreur à côté ;
//  - pause générale : corps exact, refus du greffon rendu tel quel.

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

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    AccueilViewModel accueil{&client, &greffon, &flux};
    QJsonObject projets = fixture(QStringLiteral("projets.json"));
    int statutProjets = 200;
    ReponseFaux reponsePause = ReponseFaux::json(200, QJsonObject{{QStringLiteral("pause_generale"), QJsonObject{}}});

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
        serveur.route("GET", kP + QStringLiteral("/projets"), [this](const RequeteRecue &) {
            return statutProjets == 200 ? ReponseFaux::json(200, projets)
                                        : ReponseFaux::json(statutProjets, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Not Found")}});
        });
        serveur.route("GET", kP + QStringLiteral("/quotas"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("quotas.json"))); });
        serveur.route("GET", QStringLiteral("/api/sessions"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("sessions.json"))); });
        serveur.route("POST", kP + QStringLiteral("/pause"), [this](const RequeteRecue &) { return reponsePause; });
    }
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
    void carteProjetsDepuisLaListe();
    void carteProjetsVideOuIllisible();
    void carteQuestions();
    void cartePoste();
    void cartePause();
    void carteQuotas();
    void sessionsRecentes();
    void litLesTroisSourcesQuandLaPageEstAffichee();
    void neLitRienSansSessionNiHorsDeLaPage();
    void echecGardeLaDerniereValeur();
    void pauseGeneraleCorpsExactEtRefusTelQuel();
    void carteHermesRelueAvecLaPage();
};

void TestAccueil::carteProjetsDepuisLaListe()
{
    const QVariantMap carte = AccueilViewModel::construireCarteProjets(fixture(QStringLiteral("projets.json")));
    QCOMPARE(carte.value(QStringLiteral("lisible")).toBool(), true);
    QCOMPARE(carte.value(QStringLiteral("aucunProjet")).toBool(), false);
    QCOMPARE(carte.value(QStringLiteral("total")).toString(), QStringLiteral("2"));
    QCOMPARE(carte.value(QStringLiteral("actifs")).toString(), QStringLiteral("2"));
    QCOMPARE(carte.value(QStringLiteral("enPause")).toString(), QStringLiteral("0"));
    QCOMPARE(carte.value(QStringLiteral("cartesFaites")).toString(), QStringLiteral("2 sur 6"));
    QCOMPARE(carte.value(QStringLiteral("attentePoste")).toString(), QStringLiteral("0"));
    // La première note trouvée, dans l'ordre du serveur (du plus récent au plus ancien).
    QCOMPARE(carte.value(QStringLiteral("derniereNote")).toString(), QStringLiteral("Plan posé : deux recherches."));
    QCOMPARE(carte.value(QStringLiteral("derniereNoteProjet")).toString(), QStringLiteral("Veille LLM"));
}

void TestAccueil::carteProjetsVideOuIllisible()
{
    const QVariantMap vide = AccueilViewModel::construireCarteProjets(fixture(QStringLiteral("projets-vide.json")));
    QCOMPARE(vide.value(QStringLiteral("aucunProjet")).toBool(), true);
    QCOMPARE(vide.value(QStringLiteral("actifs")).toString(), QStringLiteral("0"));
    QCOMPARE(vide.value(QStringLiteral("cartesFaites")).toString(), QStringLiteral("0 sur 0"));
    QCOMPARE(vide.value(QStringLiteral("derniereNote")).toString(), QString());

    // Liste absente : rien n'est compté, tout est « Inconnu ».
    const QVariantMap illisible = AccueilViewModel::construireCarteProjets({});
    QCOMPARE(illisible.value(QStringLiteral("lisible")).toBool(), false);
    for (const char *cle : {"total", "actifs", "enPause", "cartesFaites", "attentePoste"}) {
        QCOMPARE(illisible.value(QString::fromLatin1(cle)).toString(), QStringLiteral("Inconnu"));
    }

    // Tableau illisible côté greffon (compteurs à null, noyau/projets.lister) : jamais inventés.
    QJsonObject liste = fixture(QStringLiteral("projets.json"));
    QJsonArray projets = liste.value(QStringLiteral("projets")).toArray();
    QJsonObject premier = projets.at(0).toObject();
    premier.insert(QStringLiteral("compteurs"), QJsonObject{{QStringLiteral("faites"), QJsonValue::Null},
                                                            {QStringLiteral("total"), 2},
                                                            {QStringLiteral("en_attente_du_poste"), QJsonValue::Null}});
    projets.replace(0, premier);
    liste.insert(QStringLiteral("projets"), projets);
    const QVariantMap partiel = AccueilViewModel::construireCarteProjets(liste);
    QCOMPARE(partiel.value(QStringLiteral("cartesFaites")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(partiel.value(QStringLiteral("attentePoste")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(partiel.value(QStringLiteral("total")).toString(), QStringLiteral("2"));
}

void TestAccueil::carteQuestions()
{
    const QVariantMap une = AccueilViewModel::construireCarteQuestions(fixture(QStringLiteral("projets.json")));
    QCOMPARE(une.value(QStringLiteral("nombre")).toString(), QStringLiteral("1"));
    QCOMPARE(une.value(QStringLiteral("attente")).toBool(), true);
    QVERIFY(une.value(QStringLiteral("libelle")).toString().startsWith(QStringLiteral("1 question")));
    const QVariantMap aucune = AccueilViewModel::construireCarteQuestions(fixture(QStringLiteral("projets-vide.json")));
    QCOMPARE(aucune.value(QStringLiteral("libelle")).toString(), QStringLiteral("Aucune question en attente."));
    const QVariantMap inconnue = AccueilViewModel::construireCarteQuestions(
        QJsonObject{{QStringLiteral("questions_ouvertes"), QStringLiteral("beaucoup")}});
    QCOMPARE(inconnue.value(QStringLiteral("nombre")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(inconnue.value(QStringLiteral("connu")).toBool(), false);
}

void TestAccueil::cartePoste()
{
    const QVariantMap enLigne = AccueilViewModel::construireCartePoste(fixture(QStringLiteral("projets.json")));
    QCOMPARE(enLigne.value(QStringLiteral("etat")).toString(), QStringLiteral("En ligne"));
    QCOMPARE(enLigne.value(QStringLiteral("cle")).toString(), QStringLiteral("succeeded"));
    QCOMPARE(enLigne.value(QStringLiteral("machine")).toString(), QStringLiteral("poste-simule"));
    QCOMPARE(enLigne.value(QStringLiteral("vuA")).toString(), QStringLiteral("26/09/2026 13:43"));
    QCOMPARE(enLigne.value(QStringLiteral("cartesEnAttente")).toString(), QStringLiteral("0"));

    const QVariantMap jamais = AccueilViewModel::construireCartePoste(fixture(QStringLiteral("projets-vide.json")));
    QCOMPARE(jamais.value(QStringLiteral("etat")).toString(), QStringLiteral("Non configuré"));
    QCOMPARE(jamais.value(QStringLiteral("cle")).toString(), QStringLiteral("notConfigured"));
    QCOMPARE(jamais.value(QStringLiteral("machine")).toString(), QStringLiteral("Aucune"));
    QCOMPARE(jamais.value(QStringLiteral("vuA")).toString(), QStringLiteral("Jamais"));
    QVERIFY(jamais.value(QStringLiteral("message")).toString().contains(QStringLiteral("jamais été vu")));

    // État inconnu de la station : montré tel quel, pastille « Inconnu », jamais traduit au hasard.
    const QVariantMap inconnu = AccueilViewModel::construireCartePoste(
        QJsonObject{{QStringLiteral("poste"), QJsonObject{{QStringLiteral("etat"), QStringLiteral("en_orbite")}}}});
    QCOMPARE(inconnu.value(QStringLiteral("etat")).toString(), QStringLiteral("en_orbite"));
    QCOMPARE(inconnu.value(QStringLiteral("cle")).toString(), QStringLiteral("unknown"));
    QCOMPARE(inconnu.value(QStringLiteral("connu")).toBool(), false);
    QCOMPARE(inconnu.value(QStringLiteral("machine")).toString(), QStringLiteral("Inconnu"));

    // Relecture finale de P7 (constats produit-10 et desktop-5) : titre d'après l'hôte publié par la machine
    // (`poste.poste.hote`), jamais « Poste Windows » pour l'exécutant Railway.
    QCOMPARE(enLigne.value(QStringLiteral("titre")).toString(), QStringLiteral("Exécutant"));  // poste simulé
    for (const auto &[hote, titre] : {std::pair{QStringLiteral("railway"), QStringLiteral("Exécutant Railway")},
                                      std::pair{QStringLiteral("pc"), QStringLiteral("Poste Windows")}}) {
        const QVariantMap carte = AccueilViewModel::construireCartePoste(QJsonObject{{QStringLiteral("poste"), QJsonObject{
            {QStringLiteral("etat"), QStringLiteral("en_ligne")},
            {QStringLiteral("poste"), QJsonObject{{QStringLiteral("hote"), hote}}}}}});
        QCOMPARE(carte.value(QStringLiteral("titre")).toString(), titre);
    }

    const QVariantMap absent = AccueilViewModel::construireCartePoste({});
    QCOMPARE(absent.value(QStringLiteral("etat")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(absent.value(QStringLiteral("vuA")).toString(), QStringLiteral("Inconnu"));
}

void TestAccueil::cartePause()
{
    const QVariantMap levee = AccueilViewModel::construireCartePause(fixture(QStringLiteral("projets.json")));
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

void TestAccueil::carteQuotas()
{
    const QVariantMap releve = AccueilViewModel::construireCarteQuotas(fixture(QStringLiteral("quotas.json")));
    QCOMPARE(releve.value(QStringLiteral("connu")).toBool(), true);
    QCOMPARE(releve.value(QStringLiteral("libelle")).toString(), QStringLiteral("Poste (Codex) : 41\u00A0% utilisés"));
    QCOMPARE(releve.value(QStringLiteral("cle")).toString(), QStringLiteral("succeeded")); // 41 < seuil 90
    QCOMPARE(releve.value(QStringLiteral("etat")).toString(), QStringLiteral("Sous le seuil d'alerte"));
    QVERIFY(releve.value(QStringLiteral("remise")).toString().startsWith(QStringLiteral("Remise à zéro : ")));
    QCOMPARE(releve.value(QStringLiteral("detail")).toString(), QStringLiteral("Seuil d'alerte : 90\u00A0%"));

    const QVariantMap vides = AccueilViewModel::construireCarteQuotas(fixture(QStringLiteral("quotas-vides.json")));
    QCOMPARE(vides.value(QStringLiteral("connu")).toBool(), false);
    QCOMPARE(vides.value(QStringLiteral("libelle")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(vides.value(QStringLiteral("detail")).toString(), QStringLiteral("Aucune voie n'a de relevé de quota."));

    QJsonObject depasse = fixture(QStringLiteral("quotas.json"));
    QJsonObject claude = depasse.value(QStringLiteral("poste-claude")).toObject();
    claude.insert(QStringLiteral("resume"), QJsonObject{{QStringLiteral("pourcentage_utilise"), 93.5}});
    depasse.insert(QStringLiteral("poste-claude"), claude);
    const QVariantMap alerte = AccueilViewModel::construireCarteQuotas(depasse);
    QCOMPARE(alerte.value(QStringLiteral("libelle")).toString(), QStringLiteral("Poste (Claude) : 93,5\u00A0% utilisés"));
    QCOMPARE(alerte.value(QStringLiteral("cle")).toString(), QStringLiteral("degraded"));
    QCOMPARE(alerte.value(QStringLiteral("etat")).toString(), QStringLiteral("Seuil d'alerte atteint"));
    QCOMPARE(vides.value(QStringLiteral("etat")).toString(), QStringLiteral("Inconnu"));
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

void TestAccueil::litLesTroisSourcesQuandLaPageEstAffichee()
{
    Banc banc;
    banc.flux.demarrer();
    QTRY_COMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/projets")), 1); // sondage léger
    banc.accueil.setPageVisible(true);
    QTRY_VERIFY(banc.accueil.actif());
    QTRY_COMPARE(banc.accueil.sessions()->count(), 2);
    QTRY_COMPARE(banc.accueil.carteProjets().value(QStringLiteral("actifs")).toString(), QStringLiteral("2"));
    QTRY_COMPARE(banc.accueil.carteQuotas().value(QStringLiteral("connu")).toBool(), true);
    QCOMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/projets")), 2);
    QCOMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/quotas")), 1);
    const auto sessions = banc.serveur.filtrer("GET", QStringLiteral("/api/sessions"));
    QCOMPARE(sessions.size(), 1);
    QCOMPARE(sessions.first().requete.queryItemValue(QStringLiteral("limit")), QStringLiteral("5"));
    QCOMPARE(sessions.first().requete.queryItemValue(QStringLiteral("offset")), QStringLiteral("0"));
    QCOMPARE(sessions.first().requete.queryItemValue(QStringLiteral("order")), QStringLiteral("recent"));
    for (const RequeteRecue &requete : std::as_const(banc.serveur.requetes)) {
        QCOMPARE(requete.entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
        QVERIFY(!requete.aEntete("origin"));
    }
    QVERIFY(banc.accueil.lectureProjets().startsWith(QStringLiteral("Lu à ")));
    QCOMPARE(banc.accueil.erreurProjets(), QString());
    // Le badge de la barre d'état suit la lecture de la page.
    QCOMPARE(banc.flux.questionsOuvertes(), 1);

    // Page quittée : plus aucune lecture.
    banc.accueil.setPageVisible(false);
    QTRY_VERIFY(!banc.accueil.actif());
    const int avant = static_cast<int>(banc.serveur.requetes.size());
    banc.flux.signalerLien(false);
    banc.flux.signalerLien(true); // retour du lien : la page cachée ne relit pas
    QTest::qWait(200);
    QCOMPARE(static_cast<int>(banc.serveur.requetes.size()), avant + 1); // seul le sondage léger relit
}

void TestAccueil::neLitRienSansSessionNiHorsDeLaPage()
{
    Banc banc;
    banc.accueil.setPageVisible(true);
    QTest::qWait(200);
    QVERIFY(!banc.accueil.actif());
    QVERIFY(banc.serveur.requetes.isEmpty()); // aucune session : rien ne part
    QCOMPARE(banc.accueil.carteProjets().value(QStringLiteral("total")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(banc.accueil.lectureProjets(), QStringLiteral("Jamais lu"));

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
    QTRY_COMPARE(banc.accueil.carteProjets().value(QStringLiteral("actifs")).toString(), QStringLiteral("2"));
    const QString luA = banc.accueil.lectureProjets();

    banc.statutProjets = 404;
    banc.accueil.actualiser();
    QTRY_VERIFY(!banc.accueil.erreurProjets().isEmpty());
    QCOMPARE(banc.accueil.carteProjets().value(QStringLiteral("actifs")).toString(), QStringLiteral("2"));
    QCOMPARE(banc.accueil.cartePoste().value(QStringLiteral("etat")).toString(), QStringLiteral("En ligne"));
    QCOMPARE(banc.accueil.lectureProjets(), luA);
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

QTEST_MAIN(TestAccueil)
#include "tst_accueil.moc"
