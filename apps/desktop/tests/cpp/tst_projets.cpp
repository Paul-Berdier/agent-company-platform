// Page Projets contre les formes relevées sur l'image et le faux Hermes :
//  - lignes et détail libellés en français, « Inconnu » pour toute valeur absente, cartes
//    rangées dans l'ordre du graphe, journal lisible ;
//  - formulaire : mêmes règles que la page web (dépôts et exécutants lus du relevé, efforts
//    interdits exclus, modèle exigé sans défaut), corps EXACT, clé d'idempotence gardée après
//    un refus et renouvelée après un lancement accepté, `deja_lance` dit tel quel ;
//  - détail : veille du kanban ouverte sur le tableau du projet, un changement du tableau
//    déclenche une relecture, la veille s'arrête en quittant le détail ;
//  - gestes : pause, reprise, résumé entier d'une carte, kanban dans le navigateur ; refus du
//    greffon rendus tels quels ;
//  - étape P7 : « Changer qui répond » (projet sur dépôt pas encore fini) et « Clore le projet »
//    (actif ou en pause) : corps exacts, messages d'après la réponse, 409 en français tel quel,
//    geste non offert refusé sans envoi.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/VeilleKanban.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/ProjetsViewModel.h"

#include <QJsonArray>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kId = QStringLiteral("p_367e23fd51b7");

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
    ProjetsViewModel projets{&client, &greffon, &flux};
    QJsonObject poste = fixture(QStringLiteral("poste-releve.json"));
    int statutPoste = 200;
    ReponseFaux reponseLancement = ReponseFaux::json(201, fixture(QStringLiteral("lancement.json")));
    ReponseFaux reponsePause = ReponseFaux::json(200, QJsonObject{{QStringLiteral("cartes_planifiees"), QJsonArray{QStringLiteral("t_7aa28f61")}}});
    QList<QUrl> ouvertes;

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
        flux.setIntervalleFond(std::chrono::hours(1));
        flux.veille()->setRegroupement(std::chrono::milliseconds(20));
        projets.setOuvreur([this](const QUrl &url) {
            ouvertes.append(url);
            return true;
        });
        serveur.route("GET", kP + QStringLiteral("/projets"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projets.json"))); });
        serveur.route("GET", kP + QStringLiteral("/projets/") + kId,
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projet-detail.json"))); });
        serveur.route("GET", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/cartes/t_7aa28f61"), [](const RequeteRecue &) {
            return ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte"),
                QJsonObject{{QStringLiteral("carte"), QStringLiteral("t_7aa28f61")},
                            {QStringLiteral("titre"), QStringLiteral("Exploration du dépôt « jetable »")},
                            {QStringLiteral("role"), QStringLiteral("exploration")},
                            {QStringLiteral("statut"), QStringLiteral("scheduled")},
                            {QStringLiteral("resume"), QStringLiteral("Texte entier du résumé.")},
                            {QStringLiteral("longueur"), 23},
                            {QStringLiteral("tronque"), false}}}});
        });
        serveur.route("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/pause"),
                      [this](const RequeteRecue &) { return reponsePause; });
        serveur.route("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/reprise"), [](const RequeteRecue &) {
            return ReponseFaux::json(200, QJsonObject{{QStringLiteral("cartes_reveillees"), QJsonArray{}}});
        });
        serveur.route("GET", kP + QStringLiteral("/catalogue"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("catalogue-profils.json"))); });
        serveur.route("GET", kP + QStringLiteral("/poste"), [this](const RequeteRecue &) {
            return statutPoste == 200 ? ReponseFaux::json(200, poste)
                                      : ReponseFaux::json(statutPoste, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Not Found")}});
        });
        serveur.route("POST", kP + QStringLiteral("/projets"), [this](const RequeteRecue &) { return reponseLancement; });
        serveur.route("GET", QStringLiteral("/api/plugins/kanban/board"), [](const RequeteRecue &) {
            return ReponseFaux::json(200, QJsonObject{{QStringLiteral("latest_event_id"), 7}, {QStringLiteral("columns"), QJsonArray{}}});
        });
    }

    void ouvrirLaPage()
    {
        flux.demarrer();
        projets.setPageVisible(true);
        QTRY_VERIFY(projets.actif());
    }

    void attendreFormulaire()
    {
        QTRY_VERIFY(projets.formulaire().value(QStringLiteral("pret")).toBool());
    }
};

} // namespace

class TestProjets : public QObject
{
    Q_OBJECT

private slots:
    void lignesDeLaListe();
    void detailLibelle();
    void cartesRangeesDansLOrdreDuGraphe();
    void journalLisible();
    void reglesDuFormulaireCommeLaPageWeb();
    void listeLueSeulementPageAffichee();
    void detailOuvreLaVeilleEtRelitAuChangement();
    void resumeEntierPauseRepriseEtKanban();
    void formulaireSansInventaireOuPosteIllisible();
    void lancementCorpsExactEtCleDIdempotence();
    void lancementRefuseGardeLaCle();
    void modeleExigeRefuseSansEnvoi();
    void messagesQuiRepondEtCloture();
    void quiRepondEtClotureCorpsExacts();
    void quiRepondEtClotureRefusEnFrancais();
};

void TestProjets::lignesDeLaListe()
{
    const QJsonArray projets = fixture(QStringLiteral("projets.json")).value(QStringLiteral("projets")).toArray();
    const QJsonObject outil = ProjetsViewModel::construireLigneProjet(projets.at(0).toObject());
    QCOMPARE(outil.value(QStringLiteral("titre")).toString(), QStringLiteral("Outil"));
    QCOMPARE(outil.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Exploration du dépôt"));
    QCOMPARE(outil.value(QStringLiteral("etatCle")).toString(), QStringLiteral("running"));
    QCOMPARE(outil.value(QStringLiteral("profil")).toString(), QStringLiteral("Base"));
    QCOMPARE(outil.value(QStringLiteral("depot")).toString(), QStringLiteral("jetable"));
    QCOMPARE(outil.value(QStringLiteral("cartes")).toString(), QStringLiteral("0 sur 2"));
    QCOMPARE(outil.value(QStringLiteral("questions")).toString(), QStringLiteral("1"));
    QCOMPARE(outil.value(QStringLiteral("questionsEnAttente")).toBool(), true);
    QCOMPARE(outil.value(QStringLiteral("tour")).toString(), QStringLiteral("Tour 0 sur 3"));
    QCOMPARE(outil.value(QStringLiteral("derniereNote")).toString(), QString());

    const QJsonObject veille = ProjetsViewModel::construireLigneProjet(projets.at(1).toObject());
    QCOMPARE(veille.value(QStringLiteral("depot")).toString(), QStringLiteral("Sans dépôt"));
    QCOMPARE(veille.value(QStringLiteral("profil")).toString(), QStringLiteral("Recherche"));
    QCOMPARE(veille.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("En cours"));
    QCOMPARE(veille.value(QStringLiteral("derniereNote")).toString(), QStringLiteral("Plan posé : deux recherches."));

    // État et profil inconnus de la station : montrés tels quels, jamais traduits au hasard.
    const QJsonObject inconnu = ProjetsViewModel::construireLigneProjet(QJsonObject{
        {QStringLiteral("id"), QStringLiteral("p_x")}, {QStringLiteral("etat"), QStringLiteral("en_hibernation")},
        {QStringLiteral("profil"), QStringLiteral("jeux")}});
    QCOMPARE(inconnu.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("en_hibernation"));
    QCOMPARE(inconnu.value(QStringLiteral("etatConnu")).toBool(), false);
    QCOMPARE(inconnu.value(QStringLiteral("etatCle")).toString(), QStringLiteral("unknown"));
    QCOMPARE(inconnu.value(QStringLiteral("profil")).toString(), QStringLiteral("jeux"));
    QCOMPARE(inconnu.value(QStringLiteral("titre")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(inconnu.value(QStringLiteral("cartes")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(inconnu.value(QStringLiteral("tour")).toString(), QStringLiteral("Inconnu"));
}

void TestProjets::detailLibelle()
{
    const QJsonObject projet = fixture(QStringLiteral("projet-detail.json")).value(QStringLiteral("projet")).toObject();
    const QVariantMap detail = ProjetsViewModel::construireDetail(projet);
    QCOMPARE(detail.value(QStringLiteral("titre")).toString(), QStringLiteral("Outil"));
    QCOMPARE(detail.value(QStringLiteral("objectif")).toString(), QStringLiteral("Écrire outil.py."));
    QCOMPARE(detail.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Exploration du dépôt"));
    // Relecture finale de P7 : « Vous » dans le détail (« Moi » reste le choix du formulaire).
    QCOMPARE(detail.value(QStringLiteral("reponses")).toString(), QStringLiteral("Vous"));
    QCOMPARE(detail.value(QStringLiteral("reponsesCode")).toString(), QStringLiteral("proprietaire"));
    QCOMPARE(detail.value(QStringLiteral("peutChangerReponses")).toBool(), true);
    QCOMPARE(detail.value(QStringLiteral("peutClore")).toBool(), true);
    QCOMPARE(detail.value(QStringLiteral("origine")).toString(), QStringLiteral("Lancé depuis la page Projets"));
    QCOMPARE(detail.value(QStringLiteral("tour")).toString(), QStringLiteral("0 sur 3"));
    QCOMPARE(detail.value(QStringLiteral("cartesCreees")).toString(), QStringLiteral("2 sur 30"));
    QCOMPARE(detail.value(QStringLiteral("corrections")).toString(), QStringLiteral("2"));
    QCOMPARE(detail.value(QStringLiteral("restants")).toString(), QStringLiteral("3 tours, 28 cartes"));
    QCOMPARE(detail.value(QStringLiteral("cartesFaites")).toString(), QStringLiteral("0 sur 2"));
    QCOMPARE(detail.value(QStringLiteral("exploration")).toString(), QStringLiteral("Question ouverte (ACP) : q_b627a3c245ec"));
    QCOMPARE(detail.value(QStringLiteral("resultat")).toString(), QString());
    QCOMPARE(detail.value(QStringLiteral("termineLe")).toString(), QString());
    QCOMPARE(detail.value(QStringLiteral("peutMettreEnPause")).toBool(), true);
    QCOMPARE(detail.value(QStringLiteral("peutReprendre")).toBool(), false);

    // Détail vide : chaque clé existe et vaut « Inconnu » ou rien, jamais « undefined ».
    const QVariantMap vide = ProjetsViewModel::construireDetail({});
    QCOMPARE(vide.value(QStringLiteral("titre")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(vide.value(QStringLiteral("tour")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(vide.value(QStringLiteral("peutMettreEnPause")).toBool(), false);
    QCOMPARE(vide.value(QStringLiteral("peutChangerReponses")).toBool(), false);
    QCOMPARE(vide.value(QStringLiteral("peutClore")).toBool(), false);
    QCOMPARE(vide.keys(), detail.keys());

    // Étape P7 : sans dépôt, « qui répond » est sans objet ; un projet fini ne se règle ni ne se clôt ; un projet en
    // création se règle mais ne se clôt pas (comme le greffon : clore exige actif ou en pause).
    QJsonObject sansDepot = projet;
    sansDepot.insert(QStringLiteral("depot"), QJsonValue::Null);
    const QVariantMap s = ProjetsViewModel::construireDetail(sansDepot);
    QCOMPARE(s.value(QStringLiteral("reponses")).toString(), QStringLiteral("Sans objet (projet sans dépôt)"));
    QCOMPARE(s.value(QStringLiteral("peutChangerReponses")).toBool(), false);
    QCOMPARE(s.value(QStringLiteral("peutClore")).toBool(), true);
    QJsonObject fini = projet;
    fini.insert(QStringLiteral("etat"), QStringLiteral("termine"));
    QCOMPARE(ProjetsViewModel::construireDetail(fini).value(QStringLiteral("peutChangerReponses")).toBool(), false);
    QCOMPARE(ProjetsViewModel::construireDetail(fini).value(QStringLiteral("peutClore")).toBool(), false);
    QJsonObject creation = projet;
    creation.insert(QStringLiteral("etat"), QStringLiteral("creation"));
    creation.insert(QStringLiteral("reponses"), QStringLiteral("hermes_d_abord"));
    const QVariantMap c = ProjetsViewModel::construireDetail(creation);
    QCOMPARE(c.value(QStringLiteral("reponses")).toString(), QStringLiteral("Hermes d'abord"));
    QCOMPARE(c.value(QStringLiteral("reponsesCode")).toString(), QStringLiteral("hermes_d_abord"));
    QCOMPARE(c.value(QStringLiteral("peutChangerReponses")).toBool(), true);
    QCOMPARE(c.value(QStringLiteral("peutClore")).toBool(), false);
    // Identifiant illisible : aucun geste.
    QJsonObject illisible = projet;
    illisible.insert(QStringLiteral("id"), QStringLiteral("p/../x"));
    QCOMPARE(ProjetsViewModel::construireDetail(illisible).value(QStringLiteral("peutClore")).toBool(), false);
}

void TestProjets::cartesRangeesDansLOrdreDuGraphe()
{
    QJsonArray cartes = fixture(QStringLiteral("projet-detail.json")).value(QStringLiteral("projet")).toObject()
                            .value(QStringLiteral("cartes")).toArray();
    // Ordre du serveur inversé : la station range quand même dans l'ordre du graphe.
    QJsonArray inverse;
    for (qsizetype index = cartes.size() - 1; index >= 0; --index) {
        inverse.append(cartes.at(index));
    }
    const QJsonArray lignes = ProjetsViewModel::construireCartes(inverse);
    QCOMPARE(lignes.size(), 2);
    const QJsonObject exploration = lignes.at(0).toObject();
    QCOMPARE(exploration.value(QStringLiteral("groupe")).toString(), QStringLiteral("Exploration du dépôt"));
    QCOMPARE(exploration.value(QStringLiteral("statutLibelle")).toString(), QStringLiteral("Suspendue"));
    QCOMPARE(exploration.value(QStringLiteral("voie")).toString(), QStringLiteral("Poste (Claude)"));
    QCOMPARE(exploration.value(QStringLiteral("palier")).toString(), QStringLiteral("Standard"));
    QCOMPARE(exploration.value(QStringLiteral("mention")).toString(), QStringLiteral("quota inconnu"));
    QCOMPARE(exploration.value(QStringLiteral("modeleServi")).toString(), QStringLiteral("Non observé"));
    const QJsonObject planification = lignes.at(1).toObject();
    QCOMPARE(planification.value(QStringLiteral("groupe")).toString(), QStringLiteral("Planification"));
    QCOMPARE(planification.value(QStringLiteral("effort")).toString(), QStringLiteral("Par défaut"));
    QCOMPARE(planification.value(QStringLiteral("resume")).toString(), QString());
    QCOMPARE(planification.value(QStringLiteral("resumeLongueur")).toString(), QStringLiteral("Inconnu"));
}

void TestProjets::journalLisible()
{
    const QJsonArray journal = fixture(QStringLiteral("projet-detail.json")).value(QStringLiteral("projet")).toObject()
                                   .value(QStringLiteral("journal")).toArray();
    const QJsonArray lignes = ProjetsViewModel::construireJournal(journal);
    QCOMPARE(lignes.size(), 2);
    QCOMPARE(lignes.at(0).toObject().value(QStringLiteral("acteur")).toString(), QStringLiteral("ACP"));
    QCOMPARE(lignes.at(0).toObject().value(QStringLiteral("action")).toString(), QStringLiteral("Question transmise au propriétaire"));
    QCOMPARE(lignes.at(1).toObject().value(QStringLiteral("acteur")).toString(), QStringLiteral("Vous"));
    QCOMPARE(lignes.at(1).toObject().value(QStringLiteral("action")).toString(), QStringLiteral("Lancement"));
    QVERIFY(lignes.at(1).toObject().value(QStringLiteral("detail")).toString().contains(QStringLiteral("tableau_de_bord")));
}

void TestProjets::reglesDuFormulaireCommeLaPageWeb()
{
    const QJsonObject vide = fixture(QStringLiteral("poste-vide.json")).value(QStringLiteral("catalogue")).toObject();
    QVERIFY(!ProjetsViewModel::depotsConnus(vide).has_value());
    QVERIFY(ProjetsViewModel::voiesRelevees(vide).isEmpty());

    const QJsonObject releve = fixture(QStringLiteral("poste-releve.json")).value(QStringLiteral("catalogue")).toObject();
    // Ordre de la politique (voies_par_classe.exploration), pas celui des clés.
    QCOMPARE(ProjetsViewModel::voiesRelevees(releve), (QStringList{QStringLiteral("poste-claude"), QStringLiteral("poste-codex")}));
    QCOMPARE(ProjetsViewModel::depotsConnus(releve).value_or(QStringList()), QStringList{QStringLiteral("jetable")});
    const QStringList interdits = {QStringLiteral("max"), QStringLiteral("ultra"), QStringLiteral("ultracode")};
    const QJsonObject codex = releve.value(QStringLiteral("voies")).toObject().value(QStringLiteral("poste-codex")).toObject();
    QCOMPARE(ProjetsViewModel::effortsAdmis(codex, QString(), interdits),
             (QStringList{QStringLiteral("low"), QStringLiteral("medium"), QStringLiteral("high"), QStringLiteral("xhigh"),
                          QStringLiteral("extreme")}));
    QCOMPARE(ProjetsViewModel::effortsAdmis(codex, QStringLiteral("factice-codex-2"), interdits), QStringList{QStringLiteral("low")});
    // Aucun modèle marqué par défaut : aucun effort (le premier modèle n'est pas un défaut, D73).
    QJsonObject sansDefaut = codex;
    QJsonArray modeles = sansDefaut.value(QStringLiteral("modeles")).toArray();
    QJsonObject premier = modeles.at(0).toObject();
    premier.insert(QStringLiteral("isDefault"), false);
    modeles.replace(0, premier);
    sansDefaut.insert(QStringLiteral("modeles"), modeles);
    QVERIFY(ProjetsViewModel::effortsAdmis(sansDefaut, QString(), interdits).isEmpty());
}

void TestProjets::listeLueSeulementPageAffichee()
{
    Banc banc;
    banc.flux.demarrer();
    QTRY_COMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/projets")), 1); // sondage léger
    QTest::qWait(100);
    QCOMPARE(banc.projets.projets()->count(), 0);
    banc.projets.setPageVisible(true);
    QTRY_COMPARE(banc.projets.projets()->count(), 2);
    QVERIFY(banc.projets.listeLue());
    QCOMPARE(banc.projets.projets()->get(0).value(QStringLiteral("id")).toString(), kId);
    QCOMPARE(banc.projets.pause().value(QStringLiteral("etat")).toInt(), 0);
    QCOMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/projets")), 2);
}

void TestProjets::detailOuvreLaVeilleEtRelitAuChangement()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.projets.ouvrirProjet(kId);
    QCOMPARE(banc.projets.vue(), QStringLiteral("detail"));
    QTRY_VERIFY(banc.projets.detailLu());
    QCOMPARE(banc.projets.detail().value(QStringLiteral("titre")).toString(), QStringLiteral("Outil"));
    QCOMPARE(banc.projets.cartes()->count(), 2);
    QCOMPARE(banc.projets.questionsDuProjet()->count(), 1);
    QCOMPARE(banc.projets.journal()->count(), 2);

    // Veille du kanban sur le tableau du projet, depuis son dernier événement.
    QTRY_COMPARE(banc.flux.veille()->etat(), VeilleKanban::Etat::Prete);
    QCOMPARE(banc.flux.veille()->tableau(), QStringLiteral("acp-outil-3dd5"));
    QCOMPARE(banc.serveur.ouverturesKanban.size(), 1);
    QCOMPARE(banc.serveur.ouverturesKanban.first().requete.queryItemValue(QStringLiteral("since")), QStringLiteral("7"));
    QVERIFY(banc.projets.etatVeille().startsWith(QStringLiteral("Veille du kanban prête")));

    const int avant = banc.serveur.compter("GET", kP + QStringLiteral("/projets/") + kId);
    banc.serveur.envoyerKanban(QJsonObject{{QStringLiteral("events"), QJsonArray{QJsonObject{}}}, {QStringLiteral("cursor"), 8}});
    QTRY_COMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/projets/") + kId), avant + 1);

    // Quitter le détail ferme la veille.
    banc.projets.afficherListe();
    QCOMPARE(banc.flux.veille()->etat(), VeilleKanban::Etat::Arretee);
    QTRY_COMPARE(banc.serveur.clientsKanban(), 0);

    // Identifiant illisible : refusé par la station, rien n'est émis.
    const int requetes = static_cast<int>(banc.serveur.requetes.size());
    banc.projets.ouvrirProjet(QStringLiteral("../meta"));
    QVERIFY(banc.projets.erreurGeste().contains(QStringLiteral("illisible")));
    QCOMPARE(banc.projets.vue(), QStringLiteral("liste"));
    QTest::qWait(100);
    QVERIFY(banc.serveur.requetes.size() <= requetes + 1); // au plus une relecture de la liste
}

void TestProjets::resumeEntierPauseRepriseEtKanban()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.projets.ouvrirProjet(kId);
    QTRY_VERIFY(banc.projets.detailLu());

    banc.projets.lireCarteEnEntier(QStringLiteral("t_7aa28f61"));
    QTRY_COMPARE(banc.projets.carteLue().value(QStringLiteral("chargement")).toBool(), false);
    QCOMPARE(banc.projets.carteLue().value(QStringLiteral("resume")).toString(), QStringLiteral("Texte entier du résumé."));
    QCOMPARE(banc.projets.carteLue().value(QStringLiteral("statut")).toString(), QStringLiteral("Suspendue"));
    banc.projets.fermerCarteLue();
    QVERIFY(banc.projets.carteLue().isEmpty());

    banc.projets.mettreEnPause();
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.messageGeste(), QStringLiteral("Projet mis en pause : 1 carte(s) suspendue(s) jusqu'à la reprise."));
    const auto pauses = banc.serveur.filtrer("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/pause"));
    QCOMPARE(pauses.size(), 1);
    QCOMPARE(pauses.first().json(), QJsonObject{});
    QVERIFY(pauses.first().entete("content-type").startsWith("application/json"));

    const QString message = QStringLiteral("Refusé par ACP : le projet « Outil » est déjà en pause.");
    banc.reponsePause = ReponseFaux::json(409, refus(QStringLiteral("deja_en_pause"), message));
    banc.projets.mettreEnPause();
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.erreurGeste(), message);

    banc.projets.reprendre();
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.messageGeste(), QStringLiteral("Projet repris : 0 carte(s) réveillée(s)."));

    QVERIFY(banc.projets.ouvrirKanban());
    QCOMPARE(banc.ouvertes.size(), 1);
    QCOMPARE(banc.ouvertes.first(), QUrl(banc.serveur.url().toString() + QStringLiteral("/kanban")));
    QVERIFY(banc.projets.messageGeste().contains(QStringLiteral("acp-outil-3dd5")));
    // Constat de relecture P8 : derrière un sous-chemin, le lien gardait la racine du domaine.
    QVERIFY(!banc.client.setBaseUrl(QUrl(banc.serveur.url().toString() + QStringLiteral("/hermes/"))).isError());
    QVERIFY(banc.projets.ouvrirKanban());
    QCOMPARE(banc.ouvertes.last(), QUrl(banc.serveur.url().toString() + QStringLiteral("/hermes/kanban")));
}

void TestProjets::formulaireSansInventaireOuPosteIllisible()
{
    Banc banc;
    banc.poste = fixture(QStringLiteral("poste-vide.json"));
    banc.ouvrirLaPage();
    banc.projets.afficherNouveau();
    banc.attendreFormulaire();
    QVariantMap f = banc.projets.formulaire();
    QCOMPARE(f.value(QStringLiteral("depotsConnus")).toBool(), false);
    QCOMPARE(f.value(QStringLiteral("aideDepot")).toString(),
             QStringLiteral("Aucun dépôt connu : le poste n'a encore publié aucun inventaire (page Poste)."));
    QCOMPARE(f.value(QStringLiteral("avecExploration")).toBool(), false);
    QCOMPARE(f.value(QStringLiteral("reponsesSansObjet")).toBool(), true);
    QCOMPARE(f.value(QStringLiteral("profilDefaut")).toString(), QStringLiteral("base"));
    QCOMPARE(f.value(QStringLiteral("profils")).toList().size(), 4);
    // Un dépôt qui ne vient pas du serveur n'est jamais retenu.
    banc.projets.choisirDepot(QStringLiteral("invente"));
    QCOMPARE(banc.projets.formulaire().value(QStringLiteral("depot")).toString(), QString());

    banc.statutPoste = 404;
    banc.projets.actualiser();
    QTRY_VERIFY(!banc.projets.formulaire().value(QStringLiteral("erreurPoste")).toString().isEmpty());
    banc.attendreFormulaire();
    QCOMPARE(banc.projets.formulaire().value(QStringLiteral("aideDepot")).toString(),
             QStringLiteral("Dépôts inconnus : l'inventaire du poste est illisible (voir l'erreur ci-dessus)."));
}

void TestProjets::lancementCorpsExactEtCleDIdempotence()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.projets.afficherNouveau();
    banc.attendreFormulaire();
    QCOMPARE(banc.projets.formulaire().value(QStringLiteral("releveFactice")).toBool(), true);
    banc.projets.choisirDepot(QStringLiteral("jetable"));
    QVariantMap f = banc.projets.formulaire();
    QCOMPARE(f.value(QStringLiteral("avecExploration")).toBool(), true);
    QCOMPARE(f.value(QStringLiteral("voie")).toString(), QStringLiteral("poste-claude"));
    QCOMPARE(f.value(QStringLiteral("modeleParDefaut")).toBool(), true);
    QCOMPARE(f.value(QStringLiteral("modeleExige")).toBool(), false);
    QCOMPARE(f.value(QStringLiteral("releveDu")).toString(), QStringLiteral("26/09/2026 13:43"));
    QVERIFY(!f.value(QStringLiteral("efforts")).toStringList().contains(QStringLiteral("max")));

    banc.projets.lancer(QStringLiteral("  Outil  "), QStringLiteral("Écrire outil.py."), QStringLiteral("base"),
                        QStringLiteral("proprietaire"), QStringLiteral("high"));
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.erreurGeste(), QString());
    QCOMPARE(banc.projets.messageGeste(), QStringLiteral("Projet lancé : Hermes le planifie."));
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/projets"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(),
             (QJsonObject{{QStringLiteral("titre"), QStringLiteral("Outil")},
                          {QStringLiteral("objectif"), QStringLiteral("Écrire outil.py.")},
                          {QStringLiteral("profil"), QStringLiteral("base")},
                          {QStringLiteral("depot"), QStringLiteral("jetable")},
                          {QStringLiteral("reponses"), QStringLiteral("proprietaire")},
                          {QStringLiteral("exploration"), QJsonObject{{QStringLiteral("voie"), QStringLiteral("poste-claude")},
                                                                      {QStringLiteral("effort"), QStringLiteral("high")}}}}));
    const QByteArray premiereCle = envois.first().entete("idempotency-key");
    QVERIFY(!premiereCle.isEmpty());
    // Le projet lancé s'ouvre.
    QCOMPARE(banc.projets.vue(), QStringLiteral("detail"));
    QCOMPARE(banc.projets.projetOuvert(), QStringLiteral("p_a35a8b99fb0e"));

    // Nouveau formulaire : nouvelle clé ; sans dépôt, aucune exploration et `depot` nul.
    banc.projets.afficherNouveau();
    banc.attendreFormulaire();
    QJsonObject deja = fixture(QStringLiteral("lancement.json"));
    deja.insert(QStringLiteral("deja_lance"), true);
    banc.reponseLancement = ReponseFaux::json(200, deja);
    banc.projets.lancer(QStringLiteral("Veille LLM"), QStringLiteral("Suivre les sorties."), QStringLiteral("recherche"),
                        QStringLiteral("hermes_d_abord"), QString());
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QVERIFY(banc.projets.messageGeste().contains(QStringLiteral("déjà lancé")));
    const auto seconds = banc.serveur.filtrer("POST", kP + QStringLiteral("/projets"));
    QCOMPARE(seconds.size(), 2);
    QVERIFY(seconds.last().entete("idempotency-key") != premiereCle);
    QCOMPARE(seconds.last().json().value(QStringLiteral("depot")), QJsonValue(QJsonValue::Null));
    QVERIFY(!seconds.last().json().contains(QStringLiteral("exploration")));
}

void TestProjets::lancementRefuseGardeLaCle()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.projets.afficherNouveau();
    banc.attendreFormulaire();
    const QJsonObject refusAucunInventaire = fixture(QStringLiteral("refus-aucun-inventaire.json"));
    banc.reponseLancement = ReponseFaux::json(400, refusAucunInventaire);
    banc.projets.lancer(QStringLiteral("Outil"), QStringLiteral("Écrire outil.py."), QStringLiteral("base"),
                        QStringLiteral("hermes_d_abord"), QString());
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.erreurGeste(), refusAucunInventaire.value(QStringLiteral("detail")).toObject()
                                             .value(QStringLiteral("message")).toString());
    QCOMPARE(banc.projets.vue(), QStringLiteral("nouveau"));
    banc.projets.lancer(QStringLiteral("Outil"), QStringLiteral("Écrire outil.py."), QStringLiteral("base"),
                        QStringLiteral("hermes_d_abord"), QString());
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/projets"));
    QCOMPARE(envois.size(), 2);
    // Même formulaire après un refus : même clé, aucun doublon possible côté serveur.
    QCOMPARE(envois.at(0).entete("idempotency-key"), envois.at(1).entete("idempotency-key"));

    // Titre ou objectif vide : refus local, rien n'est émis.
    banc.projets.lancer(QStringLiteral("   "), QStringLiteral("x"), QStringLiteral("base"), QStringLiteral("hermes_d_abord"), QString());
    QCOMPARE(banc.projets.erreurGeste(), QStringLiteral("Le titre et l'objectif sont obligatoires."));
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/projets")).size(), 2);
}

void TestProjets::modeleExigeRefuseSansEnvoi()
{
    Banc banc;
    // Relevé sans modèle marqué par défaut (cas de Claude, D59) : le modèle est exigé.
    QJsonObject catalogue = banc.poste.value(QStringLiteral("catalogue")).toObject();
    QJsonObject voies = catalogue.value(QStringLiteral("voies")).toObject();
    QJsonObject claude = voies.value(QStringLiteral("poste-claude")).toObject();
    QJsonArray modeles = claude.value(QStringLiteral("modeles")).toArray();
    QJsonObject premier = modeles.at(0).toObject();
    premier.insert(QStringLiteral("isDefault"), false);
    modeles.replace(0, premier);
    claude.insert(QStringLiteral("modeles"), modeles);
    voies.insert(QStringLiteral("poste-claude"), claude);
    catalogue.insert(QStringLiteral("voies"), voies);
    banc.poste.insert(QStringLiteral("catalogue"), catalogue);

    banc.ouvrirLaPage();
    banc.projets.afficherNouveau();
    banc.attendreFormulaire();
    banc.projets.choisirDepot(QStringLiteral("jetable"));
    QCOMPARE(banc.projets.formulaire().value(QStringLiteral("modeleExige")).toBool(), true);
    QCOMPARE(banc.projets.formulaire().value(QStringLiteral("libelleModeleVide")).toString(),
             QStringLiteral("Choisissez un modèle (le relevé n'en désigne aucun par défaut)"));
    banc.projets.lancer(QStringLiteral("Outil"), QStringLiteral("Écrire outil.py."), QStringLiteral("base"),
                        QStringLiteral("proprietaire"), QString());
    QVERIFY(banc.projets.erreurGeste().startsWith(QStringLiteral("Choisissez un modèle")));
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/projets")).size(), 0);

    banc.projets.choisirModele(QStringLiteral("factice-claude-2"));
    QCOMPARE(banc.projets.formulaire().value(QStringLiteral("modeleExige")).toBool(), false);
    QCOMPARE(banc.projets.formulaire().value(QStringLiteral("efforts")).toStringList(), QStringList{QStringLiteral("low")});
    banc.projets.lancer(QStringLiteral("Outil"), QStringLiteral("Écrire outil.py."), QStringLiteral("base"),
                        QStringLiteral("proprietaire"), QStringLiteral("low"));
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    const QJsonObject exploration = banc.serveur.filtrer("POST", kP + QStringLiteral("/projets")).first().json()
                                        .value(QStringLiteral("exploration")).toObject();
    QCOMPARE(exploration, (QJsonObject{{QStringLiteral("voie"), QStringLiteral("poste-claude")},
                                       {QStringLiteral("modele"), QStringLiteral("factice-claude-2")},
                                       {QStringLiteral("effort"), QStringLiteral("low")}}));
}

void TestProjets::messagesQuiRepondEtCloture()
{
    QCOMPARE(ProjetsViewModel::messageReglageReponses(QJsonObject{{QStringLiteral("questions_ouvertes_inchangees"), 2}}),
             QStringLiteral("Réglage enregistré pour les questions suivantes. Questions ouvertes qui gardent leur traitement : 2"));
    QCOMPARE(ProjetsViewModel::messageReglageReponses(QJsonObject{}),
             QStringLiteral("Réglage enregistré pour les questions suivantes. Questions ouvertes qui gardent leur traitement : Inconnu"));
    QCOMPARE(ProjetsViewModel::messageCloture(QJsonObject{
                 {QStringLiteral("etat"), QStringLiteral("termine")}, {QStringLiteral("cartes_archivees"), QJsonArray{}},
                 {QStringLiteral("cartes_non_archivees"), QJsonArray{}}, {QStringLiteral("questions_annulees"), 0},
                 {QStringLiteral("branches_rapportees"), QJsonArray{}}}),
             QStringLiteral("Projet clos : terminé. Cartes archivées : 0 · Questions annulées : 0."));
    QCOMPARE(ProjetsViewModel::messageCloture(QJsonObject{
                 {QStringLiteral("etat"), QStringLiteral("abandonne")},
                 {QStringLiteral("cartes_archivees"), QJsonArray{QStringLiteral("t_1"), QStringLiteral("t_2")}},
                 {QStringLiteral("cartes_non_archivees"), QJsonArray{QStringLiteral("t_3")}},
                 {QStringLiteral("questions_annulees"), 1},
                 {QStringLiteral("branches_rapportees"), QJsonArray{QStringLiteral("acp/outil/e1")}}}),
             QStringLiteral("Projet clos : abandonné (la synthèse du tour en cours n'était pas faite). Cartes archivées : 2 · "
                            "Questions annulées : 1. Cartes que Hermes n'a pas archivées : t_3. Branches restées sur "
                            "l'exécutant (purgées après 7 jours) : acp/outil/e1."));
}

void TestProjets::quiRepondEtClotureCorpsExacts()
{
    Banc banc;
    banc.serveur.route("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/reponses"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("avant"), QStringLiteral("proprietaire")},
                                                  {QStringLiteral("apres"), QStringLiteral("hermes_d_abord")},
                                                  {QStringLiteral("questions_ouvertes_inchangees"), 1}});
    });
    banc.serveur.route("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/clore"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("clos"), true}, {QStringLiteral("etat"), QStringLiteral("abandonne")},
                                                  {QStringLiteral("cartes_archivees"), QJsonArray{QStringLiteral("t_7aa28f61")}},
                                                  {QStringLiteral("cartes_non_archivees"), QJsonArray{}},
                                                  {QStringLiteral("questions_annulees"), 1},
                                                  {QStringLiteral("branches_rapportees"), QJsonArray{}}});
    });
    banc.flux.demarrer();
    banc.projets.setPageVisible(true);
    banc.projets.ouvrirProjet(kId);
    QTRY_VERIFY(banc.projets.detailLu());
    QSignalSpy reglage(&banc.projets, &ProjetsViewModel::reglageReponsesEnregistre);
    QSignalSpy cloture(&banc.projets, &ProjetsViewModel::clotureFaite);
    const int lecturesDetail = banc.serveur.compter("GET", kP + QStringLiteral("/projets/") + kId);

    banc.projets.changerReponses(QStringLiteral("hermes_d_abord"));
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.erreurGeste(), QString());
    QCOMPARE(banc.projets.messageGeste(),
             QStringLiteral("Réglage enregistré pour les questions suivantes. Questions ouvertes qui gardent leur traitement : 1"));
    const auto reglages = banc.serveur.filtrer("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/reponses"));
    QCOMPARE(reglages.size(), 1);
    QCOMPARE(reglages.first().json(), (QJsonObject{{QStringLiteral("reponses"), QStringLiteral("hermes_d_abord")}}));
    QCOMPARE(reglages.first().entete("content-type"), QByteArrayLiteral("application/json"));
    QVERIFY(!reglages.first().aEntete("origin"));
    QCOMPARE(reglage.size(), 1);
    QTRY_VERIFY(banc.serveur.compter("GET", kP + QStringLiteral("/projets/") + kId) > lecturesDetail); // détail relu

    const int lecturesListe = banc.serveur.compter("GET", kP + QStringLiteral("/projets"));
    banc.projets.clore();
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.messageGeste(),
             QStringLiteral("Projet clos : abandonné (la synthèse du tour en cours n'était pas faite). Cartes archivées : 1 · "
                            "Questions annulées : 1."));
    const auto clotures = banc.serveur.filtrer("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/clore"));
    QCOMPARE(clotures.size(), 1);
    QCOMPARE(clotures.first().json(), (QJsonObject{{QStringLiteral("confirmation"), true}}));
    QCOMPARE(cloture.size(), 1);
    QTRY_VERIFY(banc.serveur.compter("GET", kP + QStringLiteral("/projets")) > lecturesListe); // liste relue
}

void TestProjets::quiRepondEtClotureRefusEnFrancais()
{
    Banc banc;
    const QString finiMessage = QStringLiteral("Refusé par ACP : le projet « Outil » est déjà terminé.");
    const QString sansObjet = QStringLiteral("Refusé par ACP : sans objet pour un projet sans dépôt.");
    banc.serveur.route("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/clore"), [&finiMessage](const RequeteRecue &) {
        return ReponseFaux::json(409, refus(QStringLiteral("projet_fini"), finiMessage));
    });
    banc.serveur.route("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/reponses"), [&sansObjet](const RequeteRecue &) {
        return ReponseFaux::json(409, refus(QStringLiteral("reponses_sans_objet"), sansObjet));
    });
    QJsonObject detail = fixture(QStringLiteral("projet-detail.json"));
    banc.serveur.route("GET", kP + QStringLiteral("/projets/") + kId,
                       [&detail](const RequeteRecue &) { return ReponseFaux::json(200, detail); });
    banc.flux.demarrer();
    banc.projets.setPageVisible(true);
    banc.projets.ouvrirProjet(kId);
    QTRY_VERIFY(banc.projets.detailLu());
    QSignalSpy cloture(&banc.projets, &ProjetsViewModel::clotureFaite);

    // 409 du greffon (l'émetteur a terminé le projet au même instant) : message tel quel, rien d'annoncé, détail relu.
    const int lectures = banc.serveur.compter("GET", kP + QStringLiteral("/projets/") + kId);
    banc.projets.clore();
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.erreurGeste(), finiMessage);
    QCOMPARE(banc.projets.messageGeste(), QString());
    QCOMPARE(cloture.size(), 0);
    QTRY_VERIFY(banc.serveur.compter("GET", kP + QStringLiteral("/projets/") + kId) > lectures);
    banc.projets.changerReponses(QStringLiteral("proprietaire"));
    QTRY_VERIFY(!banc.projets.gesteEnCours());
    QCOMPARE(banc.projets.erreurGeste(), sansObjet);

    // Projet relu terminé : ni réglage ni clôture ne partent.
    QJsonObject projet = detail.value(QStringLiteral("projet")).toObject();
    projet.insert(QStringLiteral("etat"), QStringLiteral("termine"));
    detail.insert(QStringLiteral("projet"), projet);
    banc.projets.actualiser();
    QTRY_VERIFY(!banc.projets.detail().value(QStringLiteral("peutClore")).toBool());
    const int envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/clore")).size()
        + banc.serveur.filtrer("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/reponses")).size();
    banc.projets.clore();
    QCOMPARE(banc.projets.erreurGeste(), QStringLiteral("Seul un projet actif ou en pause se clôt."));
    banc.projets.changerReponses(QStringLiteral("proprietaire"));
    QCOMPARE(banc.projets.erreurGeste(), QStringLiteral("« Qui répond » ne se change que pour un projet sur dépôt, pas encore fini."));
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/clore")).size()
                 + banc.serveur.filtrer("POST", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/reponses")).size(),
             envois);
}

QTEST_MAIN(TestProjets)
#include "tst_projets.moc"
