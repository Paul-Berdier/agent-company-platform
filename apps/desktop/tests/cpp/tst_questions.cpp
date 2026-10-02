// Page Questions contre les formes relevées sur l'image et le faux Hermes :
//  - questions, cartes en triage et cartes bloquées libellées en français ; gestes de triage
//    construits DEPUIS `actions` (jamais une liste fixe), geste non offert refusé sans envoi ;
//  - réponse : corps exact, texte borné, message suivant la RÉPONSE du greffon, question
//    fermée entre-temps dite telle quelle puis relue ;
//  - revues de P6 : affichées seulement si la clé `revues` existe, en lecture seule.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/QuestionsViewModel.h"

#include <QJsonArray>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kQuestion = QStringLiteral("q_b627a3c245ec");
const QString kTableau = QStringLiteral("acp-veille-llm-b43a");
const QString kCarte = QStringLiteral("t_0c1d2e3f");

QJsonObject refus(const QString &code, const QString &message)
{
    return QJsonObject{{QStringLiteral("detail"),
                        QJsonObject{{QStringLiteral("code"), code}, {QStringLiteral("message"), message}}}};
}

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    QuestionsViewModel questions{&client, &greffon, &flux};
    QJsonObject liste = fixture(QStringLiteral("questions.json"));
    ReponseFaux reponse = ReponseFaux::json(200, QJsonObject{{QStringLiteral("question"), kQuestion},
                                                             {QStringLiteral("etat"), QStringLiteral("repondue")},
                                                             {QStringLiteral("carte_debloquee"), true},
                                                             {QStringLiteral("reprise_differee"), false}});
    ReponseFaux reprise = ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte"), kCarte},
                                                             {QStringLiteral("reprise"), true},
                                                             {QStringLiteral("action"), QStringLiteral("prolongation")}});
    QList<QUrl> ouvertes;

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
        questions.setOuvreur([this](const QUrl &url) {
            ouvertes.append(url);
            return true;
        });
        serveur.route("GET", kP + QStringLiteral("/questions"), [this](const RequeteRecue &) { return ReponseFaux::json(200, liste); });
        serveur.route("GET", kP + QStringLiteral("/projets"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projets.json"))); });
        serveur.route("POST", kP + QStringLiteral("/questions/") + kQuestion + QStringLiteral("/reponse"),
                      [this](const RequeteRecue &) { return reponse; });
        serveur.route("POST", kP + QStringLiteral("/triage/") + kTableau + QLatin1Char('/') + kCarte + QStringLiteral("/reprendre"),
                      [this](const RequeteRecue &) { return reprise; });
        serveur.route("POST", kP + QStringLiteral("/triage/") + kTableau + QLatin1Char('/') + kCarte + QStringLiteral("/conclure"),
                      [](const RequeteRecue &) {
                          return ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte"), kCarte}, {QStringLiteral("conclu"), true}});
                      });
    }

    void ouvrirLaPage()
    {
        flux.demarrer();
        questions.setPageVisible(true);
        QTRY_VERIFY(questions.lue());
    }

    int lectures() const { return serveur.compter("GET", kP + QStringLiteral("/questions")); }
};

} // namespace

class TestQuestions : public QObject
{
    Q_OBJECT

private slots:
    void questionLibellee();
    void triageConstruitDepuisLesActions();
    void bloqueesEnLectureSeule();
    void messagesSuiventLaReponse();
    void pageLueEtRevuesSeulementSiPubliees();
    void repondreCorpsExactEtRelecture();
    void reponseRefuseeOuHorsBornes();
    void gestesDeTriage();
    void gesteNonOffertRefuseSansEnvoi();
    void revuesTraiteesDansLeNavigateur();
};

void TestQuestions::questionLibellee()
{
    const QJsonObject source = fixture(QStringLiteral("questions.json")).value(QStringLiteral("questions")).toArray().at(0).toObject();
    const QJsonObject question = QuestionsViewModel::construireQuestion(source);
    QCOMPARE(question.value(QStringLiteral("id")).toString(), kQuestion);
    QCOMPARE(question.value(QStringLiteral("peutRepondre")).toBool(), true);
    QCOMPARE(question.value(QStringLiteral("texte")).toString(), QStringLiteral("Quelle version de Python viser ?"));
    QCOMPARE(question.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Votre réponse est attendue"));
    QCOMPARE(question.value(QStringLiteral("etatCle")).toString(), QStringLiteral("approvalRequired"));
    QCOMPARE(question.value(QStringLiteral("projet")).toString(), QStringLiteral("p_367e23fd51b7"));
    QCOMPARE(question.value(QStringLiteral("projetTitre")).toString(), QStringLiteral("Outil"));
    QCOMPARE(question.value(QStringLiteral("carte")).toString(), QStringLiteral("Exploration du dépôt « jetable » (t_7aa28f61)"));
    QCOMPARE(question.value(QStringLiteral("contexte")).toString(), QStringLiteral("Le dépôt cible Python 3.11 et 3.12 dans sa CI."));
    QCOMPARE(question.value(QStringLiteral("motif")).toString(), QStringLiteral("politique du projet : le propriétaire répond lui-même"));

    // Identifiant illisible : aucune réponse ne peut partir ; champs absents : « Inconnu » ou rien.
    const QJsonObject illisible = QuestionsViewModel::construireQuestion(QJsonObject{{QStringLiteral("id"), QStringLiteral("../x")}});
    QCOMPARE(illisible.value(QStringLiteral("peutRepondre")).toBool(), false);
    QCOMPARE(illisible.value(QStringLiteral("texte")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(illisible.value(QStringLiteral("etatCle")).toString(), QStringLiteral("unknown"));
    QCOMPARE(illisible.value(QStringLiteral("contexte")).toString(), QString());
}

void TestQuestions::triageConstruitDepuisLesActions()
{
    const QJsonObject source = fixture(QStringLiteral("questions.json")).value(QStringLiteral("triage")).toArray().at(0).toObject();
    const QJsonObject tours = QuestionsViewModel::construireTriage(source);
    QCOMPARE(tours.value(QStringLiteral("libelleReprise")).toString(), QStringLiteral("Prolonger"));
    QCOMPARE(tours.value(QStringLiteral("avecConsigne")).toBool(), true);
    QCOMPARE(tours.value(QStringLiteral("peutConclure")).toBool(), true);
    QVERIFY(tours.value(QStringLiteral("aide")).toString().startsWith(QStringLiteral("« Prolonger » accorde un tour de plus")));
    QCOMPARE(tours.value(QStringLiteral("raison")).toString(), QStringLiteral("3 tours planifiés"));

    QJsonObject sansPlan = source;
    sansPlan.insert(QStringLiteral("genre"), QStringLiteral("sans_plan"));
    sansPlan.insert(QStringLiteral("actions"), QJsonArray{QStringLiteral("relancer"), QStringLiteral("conclure")});
    QCOMPARE(QuestionsViewModel::construireTriage(sansPlan).value(QStringLiteral("libelleReprise")).toString(),
             QStringLiteral("Relancer la planification"));

    // Plafond de corrections : seul « conclure » est offert, aucune reprise proposée.
    QJsonObject corrections = source;
    corrections.insert(QStringLiteral("genre"), QStringLiteral("corrections"));
    corrections.insert(QStringLiteral("actions"), QJsonArray{QStringLiteral("conclure")});
    const QJsonObject c = QuestionsViewModel::construireTriage(corrections);
    QCOMPARE(c.value(QStringLiteral("avecConsigne")).toBool(), false);
    QCOMPARE(c.value(QStringLiteral("peutConclure")).toBool(), true);
    QCOMPARE(c.value(QStringLiteral("aide")).toString(), QStringLiteral("Prolonger le plafond de corrections arrivera à l'étape P6."));

    // Sans liste lisible : le geste historique « Reprendre », et pas de conclusion.
    QJsonObject autre = source;
    autre.remove(QStringLiteral("actions"));
    autre.insert(QStringLiteral("genre"), QJsonValue::Null);
    const QJsonObject a = QuestionsViewModel::construireTriage(autre);
    QCOMPARE(a.value(QStringLiteral("libelleReprise")).toString(), QStringLiteral("Reprendre"));
    QCOMPARE(a.value(QStringLiteral("peutConclure")).toBool(), false);
    QCOMPARE(a.value(QStringLiteral("aide")).toString(), QString());

    // Geste inconnu de la station : dit, jamais transformé en bouton.
    QJsonObject inconnu = source;
    inconnu.insert(QStringLiteral("actions"), QJsonArray{QStringLiteral("teleporter")});
    const QJsonObject i = QuestionsViewModel::construireTriage(inconnu);
    QCOMPARE(i.value(QStringLiteral("avecConsigne")).toBool(), false);
    QCOMPARE(i.value(QStringLiteral("peutConclure")).toBool(), false);
    QCOMPARE(i.value(QStringLiteral("gestesInconnus")).toString(), QStringLiteral("Geste non pris en charge par la station : teleporter."));
}

void TestQuestions::bloqueesEnLectureSeule()
{
    const QJsonObject source = fixture(QStringLiteral("questions.json")).value(QStringLiteral("bloquees")).toArray().at(0).toObject();
    const QJsonObject bloquee = QuestionsViewModel::construireBloquee(source);
    QCOMPARE(bloquee.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Bloquée"));
    QCOMPARE(bloquee.value(QStringLiteral("assigne")).toString(), QStringLiteral("poste-codex"));
    QVERIFY(bloquee.value(QStringLiteral("raison")).toString().startsWith(QStringLiteral("Refusé par ACP")));
    QVERIFY(!bloquee.contains(QStringLiteral("avecConsigne")));
    QJsonObject abandonnee = source;
    abandonnee.insert(QStringLiteral("abandonnee"), true);
    QCOMPARE(QuestionsViewModel::construireBloquee(abandonnee).value(QStringLiteral("etatLibelle")).toString(),
             QStringLiteral("Abandonnée après plusieurs échecs"));
}

void TestQuestions::messagesSuiventLaReponse()
{
    QCOMPARE(QuestionsViewModel::messageReponse(QJsonObject{{QStringLiteral("carte_debloquee"), true}}),
             QStringLiteral("Réponse envoyée : la carte reprend."));
    QCOMPARE(QuestionsViewModel::messageReponse(QJsonObject{{QStringLiteral("carte_debloquee"), true},
                                                            {QStringLiteral("reprise_differee"), true}}),
             QStringLiteral("Réponse enregistrée : la carte reprendra à la reprise du projet."));
    QCOMPARE(QuestionsViewModel::messageReponse(QJsonObject{{QStringLiteral("carte_debloquee"), false}}),
             QStringLiteral("Réponse enregistrée ; la carte n'a pas été relancée (voir le kanban de Hermes)."));
    QCOMPARE(QuestionsViewModel::messageTriage(QJsonObject{{QStringLiteral("reprise"), false}}),
             QStringLiteral("La carte n'a pas été reprise (voir le kanban de Hermes)."));
    QCOMPARE(QuestionsViewModel::messageTriage(QJsonObject{{QStringLiteral("reprise"), true},
                                                           {QStringLiteral("action"), QStringLiteral("relance_planification")}}),
             QStringLiteral("Planification relancée : Hermes planifie avec votre consigne."));
    QCOMPARE(QuestionsViewModel::messageTriage(QJsonObject{{QStringLiteral("reprise"), true},
                                                           {QStringLiteral("action"), QStringLiteral("reprise")}}),
             QStringLiteral("Carte reprise : elle repart dans le graphe du projet."));
}

void TestQuestions::pageLueEtRevuesSeulementSiPubliees()
{
    Banc banc;
    banc.questions.setPageVisible(true);
    QTest::qWait(150);
    QCOMPARE(banc.lectures(), 0); // aucune session : rien ne part
    banc.ouvrirLaPage();
    QCOMPARE(banc.questions.questions()->count(), 1);
    QCOMPARE(banc.questions.triage()->count(), 1);
    QCOMPARE(banc.questions.bloquees()->count(), 1);
    QCOMPARE(banc.questions.revuesPresentes(), false); // base b3faac0 : aucune clé `revues`
    QVERIFY(banc.questions.tableauxIllisibles().isEmpty());
    QVERIFY(banc.questions.lecture().startsWith(QStringLiteral("Lu à ")));

    banc.liste.insert(QStringLiteral("revues"), QJsonArray{QJsonObject{
        {QStringLiteral("projet"), QStringLiteral("p_367e23fd51b7")}, {QStringLiteral("projet_titre"), QStringLiteral("Outil")},
        {QStringLiteral("carte"), QStringLiteral("t_aa")}, {QStringLiteral("titre"), QStringLiteral("Revue de AGENTS.md")},
        {QStringLiteral("chemins"), QJsonArray{QStringLiteral("AGENTS.md"), QStringLiteral(".github/workflows/ci.yml")}},
        {QStringLiteral("resume"), QJsonValue::Null}}});
    banc.liste.insert(QStringLiteral("tableaux_illisibles"), QJsonArray{QStringLiteral("acp-casse-0000")});
    banc.questions.actualiser();
    QTRY_VERIFY(banc.questions.revuesPresentes());
    QCOMPARE(banc.questions.revues()->count(), 1);
    QCOMPARE(banc.questions.revues()->get(0).value(QStringLiteral("chemins")).toString(),
             QStringLiteral("AGENTS.md\n.github/workflows/ci.yml"));
    QCOMPARE(banc.questions.tableauxIllisibles(), QStringList{QStringLiteral("acp-casse-0000")});
}

void TestQuestions::repondreCorpsExactEtRelecture()
{
    Banc banc;
    banc.ouvrirLaPage();
    const int avant = banc.lectures();
    const int fond = banc.serveur.compter("GET", kP + QStringLiteral("/projets"));
    banc.questions.repondre(kQuestion, QStringLiteral("  Python 3.12  "));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("Réponse envoyée : la carte reprend."));
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/questions/") + kQuestion + QStringLiteral("/reponse"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), (QJsonObject{{QStringLiteral("reponse"), QStringLiteral("Python 3.12")}}));
    QVERIFY(envois.first().entete("content-type").startsWith("application/json"));
    QCOMPARE(envois.first().entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
    QVERIFY(!envois.first().aEntete("origin"));
    QTRY_COMPARE(banc.lectures(), avant + 1); // la liste est relue
    QTRY_VERIFY(banc.serveur.compter("GET", kP + QStringLiteral("/projets")) > fond); // et le badge

    // Projet en pause : reprise différée, dite telle que le greffon la rend.
    banc.reponse = ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte_debloquee"), false},
                                                      {QStringLiteral("reprise_differee"), true}});
    banc.questions.repondre(kQuestion, QStringLiteral("Python 3.11"));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("Réponse enregistrée : la carte reprendra à la reprise du projet."));
}

void TestQuestions::reponseRefuseeOuHorsBornes()
{
    Banc banc;
    banc.ouvrirLaPage();
    const QString message = QStringLiteral("Refusé par ACP : la question q_b627a3c245ec est déjà repondue.");
    banc.reponse = ReponseFaux::json(409, refus(QStringLiteral("question_fermee"), message));
    const int avant = banc.lectures();
    banc.questions.repondre(kQuestion, QStringLiteral("trop tard"));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.erreurGeste(), message);
    QCOMPARE(banc.questions.messageGeste(), QString());
    QTRY_COMPARE(banc.lectures(), avant + 1);

    // Vide ou trop long : refus local, rien n'est émis.
    banc.questions.repondre(kQuestion, QStringLiteral("   "));
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("La réponse doit compter de 1 à 4 000 caractères."));
    banc.questions.repondre(kQuestion, QString(4001, QLatin1Char('x')));
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("La réponse doit compter de 1 à 4 000 caractères."));
    // Identifiant illisible : refus de la station, sans envoi.
    banc.questions.repondre(QStringLiteral("../meta"), QStringLiteral("x"));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QVERIFY(banc.questions.erreurGeste().contains(QStringLiteral("illisible")));
    int envois = 0;
    for (const RequeteRecue &requete : std::as_const(banc.serveur.requetes)) {
        envois += requete.methode == "POST" ? 1 : 0;
    }
    QCOMPARE(envois, 1);
}

void TestQuestions::gestesDeTriage()
{
    Banc banc;
    banc.ouvrirLaPage();
    const QString chemin = kP + QStringLiteral("/triage/") + kTableau + QLatin1Char('/') + kCarte;
    banc.questions.agirTriage(kTableau, kCarte, QStringLiteral("reprise"), QStringLiteral("  Un tour de plus, puis synthèse.  "));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("Plafond relevé : Hermes planifie la suite avec votre consigne."));
    QCOMPARE(banc.serveur.filtrer("POST", chemin + QStringLiteral("/reprendre")).first().json(),
             (QJsonObject{{QStringLiteral("consigne"), QStringLiteral("Un tour de plus, puis synthèse.")}}));

    // Sans consigne : corps vide, la consigne n'est pas envoyée.
    banc.reprise = ReponseFaux::json(200, QJsonObject{{QStringLiteral("reprise"), false}});
    banc.questions.agirTriage(kTableau, kCarte, QStringLiteral("reprise"), QStringLiteral("   "));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("La carte n'a pas été reprise (voir le kanban de Hermes)."));
    QCOMPARE(banc.serveur.filtrer("POST", chemin + QStringLiteral("/reprendre")).last().json(), QJsonObject{});

    banc.questions.agirTriage(kTableau, kCarte, QStringLiteral("conclure"), QString());
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("Projet conclu."));
    QCOMPARE(banc.serveur.filtrer("POST", chemin + QStringLiteral("/conclure")).size(), 1);
    QCOMPARE(banc.serveur.filtrer("POST", chemin + QStringLiteral("/conclure")).first().json(), QJsonObject{});
}

void TestQuestions::gesteNonOffertRefuseSansEnvoi()
{
    Banc banc;
    QJsonArray triage = banc.liste.value(QStringLiteral("triage")).toArray();
    QJsonObject carte = triage.at(0).toObject();
    carte.insert(QStringLiteral("actions"), QJsonArray{QStringLiteral("prolonger")});
    triage.replace(0, carte);
    banc.liste.insert(QStringLiteral("triage"), triage);
    banc.ouvrirLaPage();

    banc.questions.agirTriage(kTableau, kCarte, QStringLiteral("conclure"), QString());
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("Ce geste n'est pas offert par le greffon pour cette carte."));
    banc.questions.agirTriage(kTableau, kCarte, QStringLiteral("supprimer"), QString());
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("Ce geste n'est pas offert par le greffon pour cette carte."));
    const int avant = banc.lectures();
    banc.questions.agirTriage(kTableau, QStringLiteral("t_disparue"), QStringLiteral("reprise"), QString());
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("Cette carte n'est plus en triage : la liste est relue."));
    QTRY_COMPARE(banc.lectures(), avant + 1);
    for (const RequeteRecue &requete : std::as_const(banc.serveur.requetes)) {
        QVERIFY2(requete.methode != "POST", qPrintable(requete.chemin));
    }
}

void TestQuestions::revuesTraiteesDansLeNavigateur()
{
    Banc banc;
    QVERIFY(banc.questions.traiterDansLeNavigateur());
    QCOMPARE(banc.ouvertes.size(), 1);
    QCOMPARE(banc.ouvertes.first(), QUrl(banc.serveur.url().toString() + QStringLiteral("/projets?vue=questions")));
}

QTEST_MAIN(TestQuestions)
#include "tst_questions.moc"
