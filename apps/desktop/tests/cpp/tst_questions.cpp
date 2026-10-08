// Page Questions contre les formes relevées sur l'image et le faux Hermes :
//  - questions, cartes en triage et cartes bloquées libellées en français ; gestes de triage
//    construits DEPUIS `actions` (jamais une liste fixe), geste non offert refusé sans envoi ;
//  - réponse : corps exact, texte borné, message suivant la RÉPONSE du greffon, question
//    fermée entre-temps dite telle quelle puis relue ;
//  - revues de P6 : affichées seulement si la clé `revues` existe ; « Accepter » et « Refuser »
//    (motif exigé), refus du greffon dit tel quel ;
//  - étape P7 : « À traiter par vous » d'après `compteurs`, discussions en attente (compteur du
//    tableau de bord), « Relancer » une carte arrêtée seulement si le greffon la dit relançable,
//    consigne jamais envoyée pour une carte d'intégration, message d'après la réponse (alerte si
//    la carte n'est pas repartie), 409 en français rendu tel quel puis liste relue.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/QuestionsViewModel.h"

#include <QJsonArray>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kQuestion = QStringLiteral("q_b627a3c245ec");
const QString kTableau = QStringLiteral("acp-veille-llm-b43a");
const QString kCarte = QStringLiteral("t_0c1d2e3f");
// Carte arrêtée relançable (ARRETEE_RELANCABLE de l'interface web) et revue de pilotage (forme de
// execution.revues_en_cours).
const QString kTableauOutil = QStringLiteral("acp-outil-3dd5");
const QString kArretee = QStringLiteral("t_5e6f7a8b");
const QString kRevue = QStringLiteral("t_aa11bb22");

QJsonObject revuePilotage()
{
    return QJsonObject{
        {QStringLiteral("projet"), QStringLiteral("p_367e23fd51b7")}, {QStringLiteral("projet_titre"), QStringLiteral("Outil")},
        {QStringLiteral("tableau"), kTableauOutil}, {QStringLiteral("carte"), kRevue},
        {QStringLiteral("titre"), QStringLiteral("Implémentation — e2 : règles des agents")},
        {QStringLiteral("role"), QStringLiteral("implementation")}, {QStringLiteral("voie"), QStringLiteral("poste-claude")},
        {QStringLiteral("chemins"), QJsonArray{QStringLiteral("AGENTS.md"), QStringLiteral(".github/workflows/ci.yml")}},
        {QStringLiteral("diffstat"), QJsonObject{{QStringLiteral("fichiers"), 2}, {QStringLiteral("ajouts"), 14}, {QStringLiteral("retraits"), 3}}},
        {QStringLiteral("branche"), QStringLiteral("acp/outil/e2")}, {QStringLiteral("tete"), QStringLiteral("9f8e7d6c")},
        {QStringLiteral("resume"), QJsonValue::Null},
        {QStringLiteral("diff"), QStringLiteral("Le diff reste sur l'exécutant.")}};
}

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
    ReponseFaux relance = ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte"), kArretee},
                                                             {QStringLiteral("relancee"), true},
                                                             {QStringLiteral("statut_apres"), QStringLiteral("ready")},
                                                             {QStringLiteral("session_neuve"), true},
                                                             {QStringLiteral("branche_neuve"), false}});
    ReponseFaux revue = ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte"), kRevue}, {QStringLiteral("etat"), QStringLiteral("done")}});

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
        serveur.route("POST", kP + QStringLiteral("/cartes/") + kTableauOutil + QLatin1Char('/') + kArretee + QStringLiteral("/relancer"),
                      [this](const RequeteRecue &) { return relance; });
        for (const QString &geste : {QStringLiteral("accepter"), QStringLiteral("refuser")}) {
            serveur.route("POST", kP + QStringLiteral("/revues/") + kTableauOutil + QLatin1Char('/') + kRevue + QLatin1Char('/') + geste,
                          [this](const RequeteRecue &) { return revue; });
        }
    }

    //! Ajoute à la file la carte arrêtée relançable de la page web et une revue de pilotage.
    void ajouterRelancableEtRevue()
    {
        QJsonArray bloquees = liste.value(QStringLiteral("bloquees")).toArray();
        bloquees.append(fixture(QStringLiteral("arretee-relancable.json")));
        liste.insert(QStringLiteral("bloquees"), bloquees);
        liste.insert(QStringLiteral("revues"), QJsonArray{revuePilotage()});
    }

    int envoisPost() const
    {
        int envois = 0;
        for (const RequeteRecue &requete : serveur.requetes) {
            envois += requete.methode == "POST" ? 1 : 0;
        }
        return envois;
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
    void bloqueesRelancablesSelonLeGreffon();
    void revueConstruite();
    void resumeEtDiscussionsDuGreffon();
    void messagesSuiventLaReponse();
    void pageLueEtRevuesSeulementSiPubliees();
    void repondreCorpsExactEtRelecture();
    void reponseRefuseeOuHorsBornes();
    void gestesDeTriage();
    void gesteNonOffertRefuseSansEnvoi();
    void relancerCorpsExactEtMessage();
    void relanceRefuseeParLeGreffonOuLaStation();
    void revuesAccepteesOuRefusees();
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

    // Relecture finale de P7 (constat desktop-4) : règle unique du greffon (`chez`). Une question « ouverte » dont la
    // carte « répondre » n'a jamais été créée attend le propriétaire : jamais « Hermes cherche la réponse ».
    QJsonObject ouverteAVous = source;
    ouverteAVous.insert(QStringLiteral("etat"), QStringLiteral("ouverte"));
    ouverteAVous.insert(QStringLiteral("carte_repondre"), QJsonValue::Null);
    ouverteAVous.insert(QStringLiteral("chez"), QStringLiteral("proprietaire"));
    const QJsonObject aVous = QuestionsViewModel::construireQuestion(ouverteAVous);
    QCOMPARE(aVous.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Votre réponse est attendue"));
    QCOMPARE(aVous.value(QStringLiteral("etatCle")).toString(), QStringLiteral("approvalRequired"));
    QJsonObject ouverteHermes = ouverteAVous;
    ouverteHermes.insert(QStringLiteral("carte_repondre"), QStringLiteral("t_0a0b0c0d"));
    ouverteHermes.insert(QStringLiteral("chez"), QStringLiteral("hermes"));
    QCOMPARE(QuestionsViewModel::construireQuestion(ouverteHermes).value(QStringLiteral("etatLibelle")).toString(),
             QStringLiteral("Hermes cherche la réponse"));
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
    // Relecture finale de P7 (constat desktop-9) : le greffon refuse cette prolongation pour de bon (PROLONGATION_P6).
    QCOMPARE(c.value(QStringLiteral("aide")).toString(),
             QStringLiteral("Le plafond de corrections ne se prolonge pas : la relecture qui l'a atteint est close ; "
                            "concluez le projet depuis cette carte."));

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

void TestQuestions::bloqueesRelancablesSelonLeGreffon()
{
    // Carte étrangère (fixture de la page web) : le greffon la dit non relançable, et pourquoi.
    const QJsonObject source = fixture(QStringLiteral("questions.json")).value(QStringLiteral("bloquees")).toArray().at(0).toObject();
    const QJsonObject bloquee = QuestionsViewModel::construireBloquee(source);
    QCOMPARE(bloquee.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Bloquée"));
    QCOMPARE(bloquee.value(QStringLiteral("assigne")).toString(), QStringLiteral("poste-codex"));
    QVERIFY(bloquee.value(QStringLiteral("raison")).toString().startsWith(QStringLiteral("Refusé par ACP")));
    QCOMPARE(bloquee.value(QStringLiteral("peutRelancer")).toBool(), false);
    QCOMPARE(bloquee.value(QStringLiteral("avecConsigne")).toBool(), false);
    QCOMPARE(bloquee.value(QStringLiteral("refusRelance")).toString(), QStringLiteral("Carte non émise par ACP : ACP ne la relance pas."));
    QJsonObject abandonnee = source;
    abandonnee.insert(QStringLiteral("abandonnee"), true);
    QCOMPARE(QuestionsViewModel::construireBloquee(abandonnee).value(QStringLiteral("etatLibelle")).toString(),
             QStringLiteral("Abandonnée après plusieurs échecs"));
    // Sans `relancable` (greffon antérieur à P7) : jamais relançable par déduction, raison inconnue.
    QJsonObject sansCle = source;
    sansCle.remove(QStringLiteral("relancable"));
    sansCle.remove(QStringLiteral("refus_relance"));
    const QJsonObject inconnue = QuestionsViewModel::construireBloquee(sansCle);
    QCOMPARE(inconnue.value(QStringLiteral("peutRelancer")).toBool(), false);
    QCOMPARE(inconnue.value(QStringLiteral("refusRelance")).toString(), QStringLiteral("Inconnu"));

    // Carte de l'exécutant relançable (ARRETEE_RELANCABLE) : consigne offerte, session neuve annoncée.
    const QJsonObject relancable = QuestionsViewModel::construireBloquee(fixture(QStringLiteral("arretee-relancable.json")));
    QCOMPARE(relancable.value(QStringLiteral("tableau")).toString(), kTableauOutil);
    QCOMPARE(relancable.value(QStringLiteral("carte")).toString(), kArretee);
    QCOMPARE(relancable.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Abandonnée après plusieurs échecs"));
    QCOMPARE(relancable.value(QStringLiteral("peutRelancer")).toBool(), true);
    QCOMPARE(relancable.value(QStringLiteral("avecConsigne")).toBool(), true);
    QCOMPARE(relancable.value(QStringLiteral("refusRelance")).toString(), QString());
    QCOMPARE(relancable.value(QStringLiteral("aide")).toString(), QStringLiteral("L'agent repart d'une session neuve, sur la branche déjà commencée."));
    QCOMPARE(relancable.value(QStringLiteral("aideAlerte")).toBool(), false);

    // Quarantaine (secret détecté, K25) : dite en alerte.
    QJsonObject quarantaine = fixture(QStringLiteral("arretee-relancable.json"));
    quarantaine.insert(QStringLiteral("quarantaine"), true);
    const QJsonObject q = QuestionsViewModel::construireBloquee(quarantaine);
    QVERIFY(q.value(QStringLiteral("aide")).toString().startsWith(QStringLiteral("Bloquée pour un secret détecté.")));
    QCOMPARE(q.value(QStringLiteral("aideAlerte")).toBool(), true);

    // Carte d'intégration : relançable, mais sans consigne (aucun agent).
    QJsonObject integration = fixture(QStringLiteral("arretee-relancable.json"));
    integration.insert(QStringLiteral("integration"), true);
    const QJsonObject i = QuestionsViewModel::construireBloquee(integration);
    QCOMPARE(i.value(QStringLiteral("peutRelancer")).toBool(), true);
    QCOMPARE(i.value(QStringLiteral("integration")).toBool(), true);
    QCOMPARE(i.value(QStringLiteral("avecConsigne")).toBool(), false);
    QVERIFY(i.value(QStringLiteral("aide")).toString().startsWith(QStringLiteral("Carte d'intégration, sans agent")));

    // Relançable mais identifiant illisible : aucun bouton, la raison le dit.
    QJsonObject illisible = fixture(QStringLiteral("arretee-relancable.json"));
    illisible.insert(QStringLiteral("carte"), QStringLiteral("../t"));
    const QJsonObject l = QuestionsViewModel::construireBloquee(illisible);
    QCOMPARE(l.value(QStringLiteral("peutRelancer")).toBool(), false);
    QCOMPARE(l.value(QStringLiteral("refusRelance")).toString(), QStringLiteral("identifiant de carte illisible."));
}

void TestQuestions::revueConstruite()
{
    const QJsonObject revue = QuestionsViewModel::construireRevue(revuePilotage());
    QCOMPARE(revue.value(QStringLiteral("adressable")).toBool(), true);
    QCOMPARE(revue.value(QStringLiteral("chemins")).toString(), QStringLiteral("AGENTS.md\n.github/workflows/ci.yml"));
    QCOMPARE(revue.value(QStringLiteral("modification")).toString(), QStringLiteral("2 fichier(s) · 14 ajout(s) · 3 retrait(s)"));
    QCOMPARE(revue.value(QStringLiteral("branche")).toString(), QStringLiteral("acp/outil/e2"));
    QCOMPARE(revue.value(QStringLiteral("resume")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(revue.value(QStringLiteral("diff")).toString(), QStringLiteral("Le diff reste sur l'exécutant."));
    QJsonObject sansStat = revuePilotage();
    sansStat.insert(QStringLiteral("diffstat"), QJsonValue::Null);
    sansStat.insert(QStringLiteral("tableau"), QStringLiteral("a b"));
    const QJsonObject r = QuestionsViewModel::construireRevue(sansStat);
    QCOMPARE(r.value(QStringLiteral("modification")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(r.value(QStringLiteral("adressable")).toBool(), false);
}

void TestQuestions::resumeEtDiscussionsDuGreffon()
{
    const QJsonObject liste = fixture(QStringLiteral("questions.json"));
    const QVariantMap resume = QuestionsViewModel::construireResume(liste);
    QCOMPARE(resume.value(QStringLiteral("connu")).toBool(), true);
    QCOMPARE(resume.value(QStringLiteral("total")).toString(), QStringLiteral("3"));
    QCOMPARE(resume.value(QStringLiteral("nombre")).toInt(), 3);
    QCOMPARE(resume.value(QStringLiteral("chezHermes")).toString(), QStringLiteral("0"));
    // Les discussions en attente ne sont pas lues par la station : le total le dit, jamais zéro par défaut.
    QCOMPARE(resume.value(QStringLiteral("mention")).toString(), QStringLiteral("(discussions en attente : état inconnu, non comptées)"));
    // Sans compteurs (greffon antérieur à P7) : inconnu.
    const QVariantMap inconnu = QuestionsViewModel::construireResume(QJsonObject{});
    QCOMPARE(inconnu.value(QStringLiteral("connu")).toBool(), false);
    QCOMPARE(inconnu.value(QStringLiteral("total")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(inconnu.value(QStringLiteral("nombre")).toInt(), -1);
    QCOMPARE(inconnu.value(QStringLiteral("chezHermes")).toString(), QStringLiteral("Inconnu"));

    const QVariantMap discussions = QuestionsViewModel::construireDiscussions(liste.value(QStringLiteral("discussions")));
    QCOMPARE(discussions.value(QStringLiteral("etat")).toString(), QStringLiteral("Requêtes ouvertes dans le tableau de bord : 0"));
    QCOMPARE(discussions.value(QStringLiteral("limite")).toString(),
             QStringLiteral("Les questions posées dans la discussion en terminal (/chat) ne sont visibles que dans cette discussion."));
    const QVariantMap nonSuivies = QuestionsViewModel::construireDiscussions(QJsonObject{
        {QStringLiteral("suivies"), false}, {QStringLiteral("requetes_ouvertes"), QJsonValue::Null},
        {QStringLiteral("message"), QStringLiteral("Hermes ne publie pas ce compteur.")}});
    QCOMPARE(nonSuivies.value(QStringLiteral("etat")).toString(), QStringLiteral("Hermes ne publie pas ce compteur."));
    QCOMPARE(QuestionsViewModel::construireDiscussions(QJsonValue()).value(QStringLiteral("etat")).toString(),
             QStringLiteral("Discussions : état inconnu (le tableau de bord n'a pas pu être interrogé)."));
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
    // Relance (messageRelance de la page web), d'après la réponse seulement.
    QCOMPARE(QuestionsViewModel::messageRelance(QJsonObject{{QStringLiteral("relancee"), false}}, false),
             QStringLiteral("La carte n'a pas été relancée."));
    QCOMPARE(QuestionsViewModel::messageRelance(QJsonObject{{QStringLiteral("relancee"), true},
                                                            {QStringLiteral("session_neuve"), true}}, false),
             QStringLiteral("La carte repart : l'agent reprend d'une session neuve, sur la branche déjà commencée."));
    QCOMPARE(QuestionsViewModel::messageRelance(QJsonObject{{QStringLiteral("relancee"), true},
                                                            {QStringLiteral("session_neuve"), false}}, false),
             QStringLiteral("La carte repart."));
    QCOMPARE(QuestionsViewModel::messageRelance(QJsonObject{{QStringLiteral("relancee"), true}}, true),
             QStringLiteral("La carte repart : l'exécutant rejoue la même fusion."));
    QCOMPARE(QuestionsViewModel::messageRelance(QJsonObject{{QStringLiteral("relancee"), true},
                                                            {QStringLiteral("branche_neuve"), true},
                                                            {QStringLiteral("session_neuve"), true}}, false),
             QStringLiteral("La carte repart sur une branche neuve, en session neuve. Le travail en quarantaine n'est pas repris."));
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
    QCOMPARE(banc.questions.revuesPresentes(), true); // forme de l'étape P7 : clé `revues` (vide)
    QCOMPARE(banc.questions.revues()->count(), 0);
    QCOMPARE(banc.questions.resume().value(QStringLiteral("total")).toString(), QStringLiteral("3"));
    QVERIFY(banc.questions.tableauxIllisibles().isEmpty());
    QVERIFY(banc.questions.lecture().startsWith(QStringLiteral("Lu à ")));

    // Greffon antérieur à P6 : aucune clé `revues`, la section n'est pas montrée.
    banc.liste.remove(QStringLiteral("revues"));
    banc.liste.insert(QStringLiteral("tableaux_illisibles"), QJsonArray{QStringLiteral("acp-casse-0000")});
    banc.questions.actualiser();
    QTRY_VERIFY(!banc.questions.revuesPresentes());
    QCOMPARE(banc.questions.tableauxIllisibles(), QStringList{QStringLiteral("acp-casse-0000")});

    banc.liste.insert(QStringLiteral("revues"), QJsonArray{revuePilotage()});
    banc.questions.actualiser();
    QTRY_VERIFY(banc.questions.revuesPresentes());
    QCOMPARE(banc.questions.revues()->count(), 1);
    QCOMPARE(banc.questions.revues()->get(0).value(QStringLiteral("chemins")).toString(),
             QStringLiteral("AGENTS.md\n.github/workflows/ci.yml"));
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
    QCOMPARE(banc.questions.alerteGeste(), true);
    QCOMPARE(banc.serveur.filtrer("POST", chemin + QStringLiteral("/reprendre")).last().json(), QJsonObject{});

    banc.questions.agirTriage(kTableau, kCarte, QStringLiteral("conclure"), QString());
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("Projet conclu."));
    QCOMPARE(banc.questions.alerteGeste(), false);
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

void TestQuestions::relancerCorpsExactEtMessage()
{
    Banc banc;
    banc.ajouterRelancableEtRevue();
    banc.ouvrirLaPage();
    QCOMPARE(banc.questions.bloquees()->count(), 2);
    const QString chemin = kP + QStringLiteral("/cartes/") + kTableauOutil + QLatin1Char('/') + kArretee + QStringLiteral("/relancer");
    const int avant = banc.lectures();
    banc.questions.setBrouillon(QStringLiteral("r:") + kTableauOutil + QLatin1Char('/') + kArretee, QStringLiteral("brouillon"));
    QSignalSpy effaces(&banc.questions, &QuestionsViewModel::brouillonEfface);
    banc.questions.relancer(kTableauOutil, kArretee, QStringLiteral("  Reprends avec Python 3.12.  "));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.erreurGeste(), QString());
    QCOMPARE(banc.questions.messageGeste(),
             QStringLiteral("La carte repart : l'agent reprend d'une session neuve, sur la branche déjà commencée. Statut : Prête."));
    QCOMPARE(banc.questions.alerteGeste(), false);
    const auto envois = banc.serveur.filtrer("POST", chemin);
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), (QJsonObject{{QStringLiteral("consigne"), QStringLiteral("Reprends avec Python 3.12.")}}));
    QCOMPARE(envois.first().entete("content-type"), QByteArrayLiteral("application/json"));
    QVERIFY(!envois.first().aEntete("origin"));
    QCOMPARE(effaces.size(), 1);
    QCOMPARE(effaces.first().first().toString(), QStringLiteral("r:") + kTableauOutil + QLatin1Char('/') + kArretee);
    QTRY_COMPARE(banc.lectures(), avant + 1); // la file est relue

    // Réponse sans effet : alerte, jamais une réussite ; le statut servi est traduit.
    banc.relance = ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte"), kArretee}, {QStringLiteral("relancee"), false},
                                                      {QStringLiteral("statut_apres"), QStringLiteral("blocked")},
                                                      {QStringLiteral("session_neuve"), false}});
    banc.questions.relancer(kTableauOutil, kArretee, QString());
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("La carte n'a pas été relancée. Statut : Bloquée."));
    QCOMPARE(banc.questions.alerteGeste(), true);
    QCOMPARE(banc.serveur.filtrer("POST", chemin).last().json(), QJsonObject{});

    // Carte d'intégration : aucune consigne n'est jamais envoyée, même tapée.
    QJsonArray bloquees = banc.liste.value(QStringLiteral("bloquees")).toArray();
    QJsonObject integration = bloquees.last().toObject();
    integration.insert(QStringLiteral("integration"), true);
    bloquees.replace(bloquees.size() - 1, integration);
    banc.liste.insert(QStringLiteral("bloquees"), bloquees);
    banc.questions.actualiser();
    QTRY_VERIFY(banc.questions.bloquees()->get(1).value(QStringLiteral("integration")).toBool());
    banc.relance = ReponseFaux::json(200, QJsonObject{{QStringLiteral("relancee"), true}, {QStringLiteral("session_neuve"), false},
                                                      {QStringLiteral("statut_apres"), QStringLiteral("ready")}});
    banc.questions.relancer(kTableauOutil, kArretee, QStringLiteral("consigne ignorée"));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.serveur.filtrer("POST", chemin).last().json(), QJsonObject{});
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("La carte repart : l'exécutant rejoue la même fusion. Statut : Prête."));
}

void TestQuestions::relanceRefuseeParLeGreffonOuLaStation()
{
    Banc banc;
    banc.ajouterRelancableEtRevue();
    banc.ouvrirLaPage();
    // 409 du greffon (projet mis en pause entre-temps) : son message français tel quel, puis la file relue.
    const QString message = QStringLiteral("Refusé par ACP : le projet « Outil » est en pause : reprenez-le d'abord.");
    banc.relance = ReponseFaux::json(409, refus(QStringLiteral("projet_en_pause"), message));
    const int avant = banc.lectures();
    banc.questions.relancer(kTableauOutil, kArretee, QStringLiteral("essai"));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.erreurGeste(), message);
    QCOMPARE(banc.questions.messageGeste(), QString());
    QTRY_COMPARE(banc.lectures(), avant + 1);
    const int envois = banc.envoisPost();
    QCOMPARE(envois, 1);

    // Carte que le greffon dit non relançable (fixture : carte étrangère) : refus local, rien n'est émis.
    banc.questions.relancer(QStringLiteral("acp-veille-llm-b43a"), QStringLiteral("t_9a8b7c6d"), QString());
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("Cette carte n'est pas relançable selon la dernière lecture : la liste est relue."));
    // Consigne trop longue : refus local.
    banc.questions.relancer(kTableauOutil, kArretee, QString(4001, QLatin1Char('x')));
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("La consigne compte 4 000 caractères au plus."));
    QCOMPARE(banc.envoisPost(), envois);
}

void TestQuestions::revuesAccepteesOuRefusees()
{
    Banc banc;
    banc.ajouterRelancableEtRevue();
    banc.ouvrirLaPage();
    QCOMPARE(banc.questions.revues()->count(), 1);
    const QString base = kP + QStringLiteral("/revues/") + kTableauOutil + QLatin1Char('/') + kRevue;

    banc.questions.accepterRevue(kTableauOutil, kRevue);
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("Revue acceptée : la carte est terminée."));
    QCOMPARE(banc.serveur.filtrer("POST", base + QStringLiteral("/accepter")).first().json(), QJsonObject{});

    // Refus : motif exigé et borné, rien n'est émis sans lui.
    banc.questions.refuserRevue(kTableauOutil, kRevue, QStringLiteral("   "));
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("Le motif du refus doit compter de 1 à 1 000 caractères."));
    banc.questions.refuserRevue(kTableauOutil, kRevue, QString(1001, QLatin1Char('m')));
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("Le motif du refus doit compter de 1 à 1 000 caractères."));
    QCOMPARE(banc.serveur.filtrer("POST", base + QStringLiteral("/refuser")).size(), 0);
    banc.questions.refuserRevue(kTableauOutil, kRevue, QStringLiteral("  Ne touche pas à la CI.  "));
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.messageGeste(), QStringLiteral("Revue refusée : la carte revient à l'exécutant avec votre motif."));
    QCOMPARE(banc.serveur.filtrer("POST", base + QStringLiteral("/refuser")).first().json(),
             (QJsonObject{{QStringLiteral("motif"), QStringLiteral("Ne touche pas à la CI.")}}));

    // 409 `revue_changee` du greffon : dit tel quel.
    const QString message = QStringLiteral("Refusé par ACP : la carte t_aa11bb22 n'est plus en revue (statut : done).");
    banc.revue = ReponseFaux::json(409, refus(QStringLiteral("revue_changee"), message));
    banc.questions.accepterRevue(kTableauOutil, kRevue);
    QTRY_VERIFY(!banc.questions.gesteEnCours());
    QCOMPARE(banc.questions.erreurGeste(), message);

    // Revue absente de la dernière lecture : refus local, sans envoi.
    const int envois = banc.envoisPost();
    banc.questions.accepterRevue(kTableauOutil, QStringLiteral("t_inconnue"));
    QCOMPARE(banc.questions.erreurGeste(), QStringLiteral("Cette revue n'est plus en attente selon la dernière lecture : la liste est relue."));
    QCOMPARE(banc.envoisPost(), envois);
}

QTEST_MAIN(TestQuestions)
#include "tst_questions.moc"
