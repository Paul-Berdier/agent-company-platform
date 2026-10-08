// Discussions en attente (cinquième section de la file Questions, cahier P7 § 3.5) lues par la
// passerelle de la station (`session.active_list`), comme la page web (jsonrpc/discussions.ts) :
//  - seules les entrées « waiting » avec une clé de session ; entrée illisible écartée, jamais
//    complétée ; réponse illisible, refus de Hermes ou passerelle indisponible : « inconnu » ;
//  - la seule méthode émise est `session.active_list`, avec des paramètres vides ;
//  - le badge, l'Accueil et la file Questions les ajoutent à « À traiter par vous » quand elles
//    sont connues, et le disent quand elles ne le sont pas (jamais zéro par défaut) ; la file en
//    montre la liste (titre, état, activité, aperçu, session).

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/Backoff.h"
#include "events/EventStreamService.h"
#include "gateway/DiscussionsEnAttente.h"
#include "gateway/GatewayClient.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/AccueilViewModel.h"
#include "viewmodels/QuestionsViewModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");

QJsonObject session(const QString &cle, const QString &statut, const QString &titre = QStringLiteral("Plan du site"))
{
    // Forme SessionActiveItem du contrat épinglé (hermes/contrat/gateway-contract.openrpc.json).
    return QJsonObject{{QStringLiteral("id"), QStringLiteral("rt-") + cle},
                       {QStringLiteral("session_key"), cle},
                       {QStringLiteral("status"), statut},
                       {QStringLiteral("title"), titre},
                       {QStringLiteral("preview"), QStringLiteral("Quel nom de domaine ?")},
                       {QStringLiteral("last_active"), 1790451615.5},
                       {QStringLiteral("started_at"), 1790450000.0},
                       {QStringLiteral("message_count"), 4},
                       {QStringLiteral("model"), QStringLiteral("modele")},
                       {QStringLiteral("current"), false}};
}

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    GatewayClient passerelle{&client};
    EventStreamService flux{&client, &greffon, &passerelle};
    QJsonArray actives{session(QStringLiteral("cle-attente"), QStringLiteral("waiting")),
                       session(QStringLiteral("cle-libre"), QStringLiteral("idle"))};

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
        passerelle.setRecul(Backoff(std::chrono::milliseconds(20), std::chrono::milliseconds(40), 0));
        serveur.methodes.insert(QStringLiteral("session.active_list"),
                                [this](const QJsonObject &) { return QJsonObject{{QStringLiteral("sessions"), actives}}; });
        serveur.route("GET", kP + QStringLiteral("/accueil"), [](const RequeteRecue &) {
            return ReponseFaux::json(200, fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object());
        });
        serveur.route("GET", kP + QStringLiteral("/questions"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("questions.json"))); });
    }

    void ouvrirPasserelle()
    {
        passerelle.ouvrir();
        QTRY_COMPARE_WITH_TIMEOUT(passerelle.etat(), GatewayClient::Etat::Pret, 10000);
    }

    [[nodiscard]] int appels() const { return static_cast<int>(serveur.tramesDeMethode(QStringLiteral("session.active_list")).size()); }
};

} // namespace

class TestDiscussionsAttente : public QObject
{
    Q_OBJECT

private slots:
    void entreesEnAttenteSeulement();
    void lectureParLaPasserelle();
    void badgeAccueilEtFileLesComptent();
};

void TestDiscussionsAttente::entreesEnAttenteSeulement()
{
    QJsonObject sansTitre = session(QStringLiteral("cle-2"), QStringLiteral("waiting"), QStringLiteral("   "));
    sansTitre.insert(QStringLiteral("preview"), QString(300, QLatin1Char('a')));
    sansTitre.insert(QStringLiteral("last_active"), QStringLiteral("hier"));
    QJsonObject sansCle = session(QString(), QStringLiteral("waiting"));
    const std::optional<QJsonArray> sessions = DiscussionsEnAttente::sessionsEnAttente(QJsonObject{{QStringLiteral("sessions"), QJsonArray{
        session(QStringLiteral("cle-1"), QStringLiteral("waiting")), session(QStringLiteral("cle-3"), QStringLiteral("working")),
        sansTitre, sansCle, QStringLiteral("illisible")}}});
    QVERIFY(sessions.has_value());
    QCOMPARE(sessions->size(), 2);
    const QJsonObject premiere = sessions->at(0).toObject();
    QCOMPARE(premiere.value(QStringLiteral("cle")).toString(), QStringLiteral("cle-1"));
    QCOMPARE(premiere.value(QStringLiteral("titre")).toString(), QStringLiteral("Plan du site"));
    QCOMPARE(premiere.value(QStringLiteral("apercu")).toString(), QStringLiteral("Quel nom de domaine ?"));
    QCOMPARE(premiere.value(QStringLiteral("derniereActivite")).toDouble(), 1790451615.5);
    const QJsonObject seconde = sessions->at(1).toObject();
    QVERIFY(seconde.value(QStringLiteral("titre")).isNull()); // titre vide : jamais inventé
    QCOMPARE(seconde.value(QStringLiteral("apercu")).toString().size(), 160);
    QVERIFY(seconde.value(QStringLiteral("derniereActivite")).isNull());
    // Réponse sans tableau `sessions` : illisible, jamais « aucune ».
    QVERIFY(!DiscussionsEnAttente::sessionsEnAttente(QJsonObject{}).has_value());
    QVERIFY(!DiscussionsEnAttente::sessionsEnAttente(QJsonObject{{QStringLiteral("sessions"), 3}}).has_value());

    // Section de la file : liste lue, ou état inconnu avec le compteur du tableau de bord.
    const QVariantMap section = QuestionsViewModel::construireDiscussions(
        QJsonObject{{QStringLiteral("limite"), QStringLiteral("Limite du greffon.")}}, sessions);
    QCOMPARE(section.value(QStringLiteral("connues")).toBool(), true);
    QCOMPARE(section.value(QStringLiteral("etat")).toString(), QString());
    const QVariantList liste = section.value(QStringLiteral("sessions")).toList();
    QCOMPARE(liste.size(), 2);
    QCOMPARE(liste.at(0).toMap().value(QStringLiteral("etat")).toString(), QStringLiteral("En attente d'une réponse"));
    QCOMPARE(liste.at(1).toMap().value(QStringLiteral("titre")).toString(), QStringLiteral("Sans titre"));
    QCOMPARE(liste.at(1).toMap().value(QStringLiteral("activite")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(section.value(QStringLiteral("limite")).toString(), QStringLiteral("Limite du greffon."));
    QCOMPARE(QuestionsViewModel::construireDiscussions({}, QJsonArray{}).value(QStringLiteral("etat")).toString(),
             QStringLiteral("Aucune discussion en attente."));
    const QVariantMap inconnues = QuestionsViewModel::construireDiscussions(QJsonObject{
        {QStringLiteral("suivies"), true}, {QStringLiteral("requetes_ouvertes"), 2}});
    QCOMPARE(inconnues.value(QStringLiteral("connues")).toBool(), false);
    QCOMPARE(inconnues.value(QStringLiteral("etat")).toString(), QStringLiteral("Requêtes ouvertes dans le tableau de bord : 2"));
}

void TestDiscussionsAttente::lectureParLaPasserelle()
{
    Banc banc;
    DiscussionsEnAttente *lecture = banc.flux.discussions();
    // Passerelle fermée : inconnu, rien d'émis.
    lecture->lire();
    QCOMPARE(lecture->connues(), false);
    QCOMPARE(lecture->nombre(), -1);
    QVERIFY(lecture->raison().startsWith(QStringLiteral("passerelle de Hermes indisponible")));

    banc.ouvrirPasserelle();
    QSignalSpy change(lecture, &DiscussionsEnAttente::change);
    lecture->lire();
    lecture->lire(); // pendant la lecture en vol : une seule relecture, servie à la fin
    QTRY_COMPARE(lecture->connues(), true);
    QCOMPARE(lecture->nombre(), 1);
    QCOMPARE(lecture->sessions().at(0).toObject().value(QStringLiteral("cle")).toString(), QStringLiteral("cle-attente"));
    QTRY_COMPARE(banc.appels(), 2);
    QTest::qWait(100);
    QCOMPARE(banc.appels(), 2);
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.active_list")).constFirst().value(QStringLiteral("params")).toObject(),
             QJsonObject{});
    // Aucune autre méthode que celles du canal (capacités, rejeu) et session.active_list : aucune session rattachée.
    QVERIFY(banc.serveur.tramesDeMethode(QStringLiteral("session.resume")).isEmpty());
    QVERIFY(banc.serveur.tramesDeMethode(QStringLiteral("session.activate")).isEmpty());

    // Refus de Hermes (méthode inconnue) : inconnu, avec le message et le code, jamais zéro.
    banc.serveur.methodes.remove(QStringLiteral("session.active_list"));
    lecture->lire();
    QTRY_COMPARE(lecture->connues(), false);
    QCOMPARE(lecture->raison(), QStringLiteral("Hermes a refusé « session.active_list » : method not found (code -32601)"));
    // Réponse illisible.
    banc.serveur.methodes.insert(QStringLiteral("session.active_list"),
                                 [](const QJsonObject &) { return QJsonObject{{QStringLiteral("liste"), QJsonArray{}}}; });
    lecture->lire();
    QTRY_COMPARE(lecture->raison(), QStringLiteral("réponse illisible de « session.active_list »"));
    QCOMPARE(lecture->nombre(), -1);
    // Oubli (session perdue) : inconnu.
    banc.serveur.methodes.insert(QStringLiteral("session.active_list"),
                                 [](const QJsonObject &) { return QJsonObject{{QStringLiteral("sessions"), QJsonArray{}}}; });
    lecture->lire();
    QTRY_COMPARE(lecture->nombre(), 0);
    lecture->oublier();
    QCOMPARE(lecture->nombre(), -1);
}

void TestDiscussionsAttente::badgeAccueilEtFileLesComptent()
{
    Banc banc;
    AccueilViewModel accueil{&banc.client, &banc.greffon, &banc.flux};
    QuestionsViewModel questions{&banc.client, &banc.greffon, &banc.flux};

    // Badge : sondage léger lu, passerelle pas encore prête → le libellé dit que les discussions ne sont pas comptées.
    banc.flux.demarrer();
    QTRY_COMPARE(banc.flux.aTraiter(), 1); // a_traiter.total de la fixture partagée
    QCOMPARE(banc.flux.libelleATraiter(), QStringLiteral("À traiter par vous : 1 (discussions non comptées)"));
    // Passerelle prête : les discussions se lisent et le badge les compte.
    banc.ouvrirPasserelle();
    QTRY_COMPARE(banc.flux.aTraiter(), 2);
    QCOMPARE(banc.flux.libelleATraiter(), QStringLiteral("À traiter par vous : 2"));

    // Accueil : total, nombre et mention.
    accueil.setPageVisible(true);
    QTRY_VERIFY(accueil.lue());
    QTRY_COMPARE(accueil.carteATraiter().value(QStringLiteral("discussions")).toString(), QStringLiteral("1"));
    QCOMPARE(accueil.carteATraiter().value(QStringLiteral("total")).toString(), QStringLiteral("2"));
    QCOMPARE(accueil.carteATraiter().value(QStringLiteral("mention")).toString(), QString());
    QCOMPARE(accueil.carteATraiter().value(QStringLiteral("rien")).toBool(), false);

    // File Questions : total compté, liste montrée.
    questions.setPageVisible(true);
    QTRY_VERIFY(questions.lue());
    QTRY_COMPARE(questions.discussions().value(QStringLiteral("connues")).toBool(), true);
    const QJsonObject compteurs = fixture(QStringLiteral("questions.json")).value(QStringLiteral("compteurs")).toObject();
    QCOMPARE(questions.resume().value(QStringLiteral("nombre")).toInt(), compteurs.value(QStringLiteral("a_traiter")).toInt() + 1);
    QCOMPARE(questions.resume().value(QStringLiteral("mention")).toString(), QString());
    QCOMPARE(questions.discussions().value(QStringLiteral("sessions")).toList().at(0).toMap().value(QStringLiteral("cle")).toString(),
             QStringLiteral("cle-attente"));

    // Plus rien en attente : « Rien n'attend votre décision » seulement quand le greffon ne compte rien non plus.
    banc.actives = QJsonArray{};
    banc.flux.discussions()->lire();
    QTRY_COMPARE(banc.flux.aTraiter(), 1);
    QCOMPARE(questions.discussions().value(QStringLiteral("etat")).toString(), QStringLiteral("Aucune discussion en attente."));
    QJsonObject vide = fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object();
    QJsonObject aTraiter = vide.value(QStringLiteral("a_traiter")).toObject();
    aTraiter.insert(QStringLiteral("total"), 0);
    aTraiter.insert(QStringLiteral("premieres"), QJsonArray{});
    vide.insert(QStringLiteral("a_traiter"), aTraiter);
    QCOMPARE(AccueilViewModel::construireCarteATraiter(vide, 0).value(QStringLiteral("rien")).toBool(), true);
    QCOMPARE(AccueilViewModel::construireCarteATraiter(vide).value(QStringLiteral("rien")).toBool(), false); // inconnues

    // Session perdue : inconnu partout.
    banc.flux.arreter();
    QCOMPARE(banc.flux.discussions()->nombre(), -1);
    QCOMPARE(banc.flux.aTraiter(), -1);
}

QTEST_MAIN(TestDiscussionsAttente)

#include "tst_discussions_attente.moc"
