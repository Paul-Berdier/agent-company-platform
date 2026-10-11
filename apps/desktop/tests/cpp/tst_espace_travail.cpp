// Espace de travail (chantier « atelier », D166 et D167) :
//  - barre latérale : missions servies par GET /v1/projets regroupées par dépôt (« Sans dépôt »
//    pour une mission sans dépôt), groupes actifs d'abord, missions archivées repliées derrière
//    une ligne qui les compte, recherche sans casse ni accents qui déplie tout, sélection marquée ;
//  - panneau des agents : Hermes en racine, une carte par agent, une relecture rangée sous la
//    carte qu'elle relit (à toute profondeur, cycle servi compris), états d'agent tirés des
//    statuts kanban servis et « Inconnu » pour un statut que la station ne connaît pas ;
//  - volet du bas : vérifications lues dans le journal (`carte_terminee`, détail en texte JSON
//    ou en objet), sorties = résumés servis seulement ;
//  - brouillons en mémoire, oubliés avec la session ; pictogrammes stables d'une exécution à
//    l'autre ;
//  - bout en bout contre le faux Hermes : la barre lit la liste, choisir une mission ouvre son
//    détail et remplit le panneau des agents.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/VeilleKanban.h"
#include "models/JsonListModel.h"
#include "navigation/NavigationModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/EspaceTravailViewModel.h"
#include "viewmodels/ProjetsViewModel.h"

#include <QJsonArray>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kId = QStringLiteral("p_367e23fd51b7");

QJsonObject mission(const QString &id, const QString &titre, const QJsonValue &depot, const QString &etat, double creeLe,
                    int questions = 0)
{
    return QJsonObject{{QStringLiteral("id"), id},
                       {QStringLiteral("titre"), titre},
                       {QStringLiteral("depot"), depot},
                       {QStringLiteral("etat"), etat},
                       {QStringLiteral("cree_le"), creeLe},
                       {QStringLiteral("questions_ouvertes"), questions},
                       {QStringLiteral("compteurs"), QJsonObject{{QStringLiteral("faites"), 1}, {QStringLiteral("total"), 3},
                                                                 {QStringLiteral("bloquees"), 0}}}};
}

QJsonObject carte(const QString &id, const QString &role, const QString &statut, int tour, const QJsonValue &relue = {},
                  const QJsonValue &resume = {})
{
    return QJsonObject{{QStringLiteral("carte"), id},
                       {QStringLiteral("titre"), QStringLiteral("Carte %1").arg(id)},
                       {QStringLiteral("role"), role},
                       {QStringLiteral("statut"), statut},
                       {QStringLiteral("tour"), tour},
                       {QStringLiteral("ref"), role},
                       {QStringLiteral("voie"), QStringLiteral("poste-claude")},
                       {QStringLiteral("modele"), QStringLiteral("factice-claude-1")},
                       {QStringLiteral("effort"), QJsonValue::Null},
                       {QStringLiteral("source_routage"), QStringLiteral("table")},
                       {QStringLiteral("mention"), QJsonValue::Null},
                       {QStringLiteral("modele_servi"), QStringLiteral("Non observé")},
                       {QStringLiteral("relue"), relue.isUndefined() ? QJsonValue(QJsonValue::Null) : relue},
                       {QStringLiteral("resume"), resume.isUndefined() ? QJsonValue(QJsonValue::Null) : resume}};
}

QStringList cles(const QJsonArray &lignes)
{
    QStringList sortie;
    for (const QJsonValue &ligne : lignes) sortie.append(ligne.toObject().value(QStringLiteral("cle")).toString());
    return sortie;
}

QJsonObject ligne(const QJsonArray &lignes, const QString &cle)
{
    for (const QJsonValue &element : lignes) {
        if (element.toObject().value(QStringLiteral("cle")).toString() == cle) return element.toObject();
    }
    return {};
}

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    ProjetsViewModel projets{&client, &greffon, &flux};
    NavigationModel navigation;
    EspaceTravailViewModel espace{&greffon, &flux, &projets, &navigation};
    QJsonObject detail = fixture(QStringLiteral("projet-detail.json"));

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
        serveur.route("GET", kP + QStringLiteral("/projets"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projets.json"))); });
        serveur.route("GET", kP + QStringLiteral("/projets/") + kId,
                      [this](const RequeteRecue &) { return ReponseFaux::json(200, detail); });
        serveur.route("GET", kP + QStringLiteral("/catalogue"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("catalogue-profils.json"))); });
        serveur.route("GET", kP + QStringLiteral("/poste"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("poste-releve.json"))); });
        serveur.route("GET", QStringLiteral("/api/plugins/kanban/board"), [](const RequeteRecue &) {
            return ReponseFaux::json(200, QJsonObject{{QStringLiteral("latest_event_id"), 7}, {QStringLiteral("columns"), QJsonArray{}}});
        });
    }
};

} // namespace

class TestEspaceTravail : public QObject
{
    Q_OBJECT

private slots:
    void arbreRegroupeParDepot();
    void archivesRepliesEtComptees();
    void rechercheSansCasseNiAccents();
    void groupeReplieGardeSaLigne();
    void relecturesSousLaCarteRelue();
    void carteSansIdentifiantGardeUneCleStable();
    void etatsDAgentTiresDesStatutsServis();
    void verificationsLuesDansLeJournal();
    void sortiesSeulementLesResumesServis();
    void pictogrammeStable();
    void brouillonsEnMemoireOubliesAvecLaSession();
    void boutEnBoutContreLeFauxHermes();
};

void TestEspaceTravail::arbreRegroupeParDepot()
{
    const QJsonArray projets{
        mission(QStringLiteral("p_000000000001"), QStringLiteral("Ancienne"), QStringLiteral("outil"), QStringLiteral("termine"), 100),
        mission(QStringLiteral("p_000000000002"), QStringLiteral("Veille"), QJsonValue::Null, QStringLiteral("actif"), 200, 2),
        mission(QStringLiteral("p_000000000003"), QStringLiteral("Refonte"), QStringLiteral("outil"), QStringLiteral("en_pause"), 300),
        mission(QStringLiteral("p_000000000004"), QStringLiteral("Archivée seule"), QStringLiteral("vieux"), QStringLiteral("abandonne"), 400),
    };
    const QJsonArray lignes = EspaceTravailViewModel::construireArbre(projets, {}, {}, {}, QStringLiteral("p_000000000003"));
    // Le groupe qui a une mission active passe d'abord ; puis les autres du plus récent au plus ancien.
    QCOMPARE(cles(lignes), (QStringList{QStringLiteral("g:"), QStringLiteral("m:p_000000000002"),
                                        QStringLiteral("g:vieux"), QStringLiteral("a:vieux"),
                                        QStringLiteral("g:outil"), QStringLiteral("m:p_000000000003"), QStringLiteral("a:outil")}));
    const QJsonObject sansDepot = ligne(lignes, QStringLiteral("g:"));
    QCOMPARE(sansDepot.value(QStringLiteral("libelle")).toString(), QStringLiteral("Sans dépôt"));
    QCOMPARE(sansDepot.value(QStringLiteral("questions")).toInt(), 2);
    QCOMPARE(sansDepot.value(QStringLiteral("actives")).toInt(), 1);
    const QJsonObject outil = ligne(lignes, QStringLiteral("g:outil"));
    QCOMPARE(outil.value(QStringLiteral("missions")).toInt(), 2);
    QCOMPARE(outil.value(QStringLiteral("actives")).toInt(), 0);
    const QJsonObject refonte = ligne(lignes, QStringLiteral("m:p_000000000003"));
    QVERIFY(refonte.value(QStringLiteral("selectionnee")).toBool());
    QCOMPARE(refonte.value(QStringLiteral("progression")).toString(), QStringLiteral("1/3"));
    QVERIFY(!refonte.value(QStringLiteral("etatLibelle")).toString().isEmpty());
    QVERIFY(!ligne(lignes, QStringLiteral("m:p_000000000002")).value(QStringLiteral("selectionnee")).toBool());
}

void TestEspaceTravail::archivesRepliesEtComptees()
{
    const QJsonArray projets{
        mission(QStringLiteral("p_000000000001"), QStringLiteral("Une"), QStringLiteral("outil"), QStringLiteral("termine"), 100),
        mission(QStringLiteral("p_000000000002"), QStringLiteral("Deux"), QStringLiteral("outil"), QStringLiteral("abandonne"), 200),
        mission(QStringLiteral("p_000000000003"), QStringLiteral("Trois"), QStringLiteral("outil"), QStringLiteral("actif"), 300),
    };
    const QJsonArray repliees = EspaceTravailViewModel::construireArbre(projets, {}, {}, {}, {});
    QCOMPARE(cles(repliees), (QStringList{QStringLiteral("g:outil"), QStringLiteral("m:p_000000000003"), QStringLiteral("a:outil")}));
    QCOMPARE(ligne(repliees, QStringLiteral("a:outil")).value(QStringLiteral("libelle")).toString(),
             QStringLiteral("2 missions archivées"));
    QVERIFY(!ligne(repliees, QStringLiteral("a:outil")).value(QStringLiteral("deplie")).toBool());
    const QJsonArray ouvertes = EspaceTravailViewModel::construireArbre(projets, {}, {}, {QStringLiteral("a:outil")}, {});
    QCOMPARE(cles(ouvertes), (QStringList{QStringLiteral("g:outil"), QStringLiteral("m:p_000000000003"), QStringLiteral("a:outil"),
                                          QStringLiteral("m:p_000000000002"), QStringLiteral("m:p_000000000001")}));
    QVERIFY(ligne(ouvertes, QStringLiteral("m:p_000000000001")).value(QStringLiteral("archivee")).toBool());
}

void TestEspaceTravail::rechercheSansCasseNiAccents()
{
    const QJsonArray projets{
        mission(QStringLiteral("p_000000000001"), QStringLiteral("Préparer la démo"), QStringLiteral("outil"), QStringLiteral("termine"), 100),
        mission(QStringLiteral("p_000000000002"), QStringLiteral("Veille"), QStringLiteral("outil"), QStringLiteral("actif"), 200),
        mission(QStringLiteral("p_000000000003"), QStringLiteral("Autre"), QJsonValue::Null, QStringLiteral("actif"), 300),
    };
    // « preparer » trouve « Préparer », même archivée et groupe replié : une recherche déplie tout.
    const QJsonArray trouve = EspaceTravailViewModel::construireArbre(projets, QStringLiteral("  PREPARER "),
                                                                      {QStringLiteral("g:outil")}, {}, {});
    QCOMPARE(cles(trouve), (QStringList{QStringLiteral("g:outil"), QStringLiteral("a:outil"), QStringLiteral("m:p_000000000001")}));
    // Le nom du dépôt compte aussi, « Sans dépôt » compris.
    QCOMPARE(cles(EspaceTravailViewModel::construireArbre(projets, QStringLiteral("sans depot"), {}, {}, {})),
             (QStringList{QStringLiteral("g:"), QStringLiteral("m:p_000000000003")}));
    QVERIFY(EspaceTravailViewModel::construireArbre(projets, QStringLiteral("introuvable"), {}, {}, {}).isEmpty());
}

void TestEspaceTravail::groupeReplieGardeSaLigne()
{
    const QJsonArray projets{
        mission(QStringLiteral("p_000000000001"), QStringLiteral("Une"), QStringLiteral("outil"), QStringLiteral("actif"), 100),
    };
    const QJsonArray lignes = EspaceTravailViewModel::construireArbre(projets, {}, {QStringLiteral("g:outil")}, {}, {});
    QCOMPARE(cles(lignes), QStringList{QStringLiteral("g:outil")});
    QVERIFY(!lignes.first().toObject().value(QStringLiteral("deplie")).toBool());
    QCOMPARE(lignes.first().toObject().value(QStringLiteral("missions")).toInt(), 1);
}

void TestEspaceTravail::relecturesSousLaCarteRelue()
{
    // Forme servie par le greffon : `relue` porte la CLÉ de la demande relue (noyau/graphe.py, _cle), les
    // cartes arrivent dans l'ordre de leur création (tour, cree_le, rowid).
    const auto cle = [](const QString &suffixe) { return QStringLiteral("acp:%1:t1:e1:%2").arg(kId, suffixe); };
    const auto etape = [](QJsonObject carte, const QString &ref) {
        carte.insert(QStringLiteral("ref"), ref);
        return carte;
    };
    const QJsonObject projet{
        {QStringLiteral("id"), kId},
        {QStringLiteral("etat"), QStringLiteral("actif")},
        {QStringLiteral("cartes"), QJsonArray{
             carte(QStringLiteral("t_plan"), QStringLiteral("planification"), QStringLiteral("done"), 0),
             etape(carte(QStringLiteral("t_impl"), QStringLiteral("implementation"), QStringLiteral("running"), 1), QStringLiteral("e1")),
             etape(carte(QStringLiteral("t_rel1"), QStringLiteral("relecture"), QStringLiteral("review"), 1, cle(QStringLiteral("implementation"))), QStringLiteral("e1")),
             etape(carte(QStringLiteral("t_corr1"), QStringLiteral("correction"), QStringLiteral("todo"), 1, cle(QStringLiteral("relecture"))), QStringLiteral("e1")),
             etape(carte(QStringLiteral("t_rel2"), QStringLiteral("relecture"), QStringLiteral("todo"), 1, cle(QStringLiteral("correction1"))), QStringLiteral("e1")),
             // Clé d'une autre mission, puis étape relue absente : à plat sous Hermes.
             etape(carte(QStringLiteral("t_autre"), QStringLiteral("relecture"), QStringLiteral("todo"), 1,
                         QStringLiteral("acp:p_autremission:t1:e1:implementation")), QStringLiteral("e2")),
             carte(QStringLiteral("t_cycle_a"), QStringLiteral("relecture"), QStringLiteral("todo"), 2, QStringLiteral("t_cycle_b")),
             carte(QStringLiteral("t_cycle_b"), QStringLiteral("relecture"), QStringLiteral("todo"), 2, QStringLiteral("t_cycle_a")),
             etape(carte(QStringLiteral("t_orpheline"), QStringLiteral("relecture"), QStringLiteral("todo"), 2,
                         QStringLiteral("acp:%1:t2:e9:implementation").arg(kId)), QStringLiteral("e9")),
         }},
    };
    const QJsonArray lignes = EspaceTravailViewModel::construireAgents(projet);
    QCOMPARE(cles(lignes), (QStringList{QStringLiteral("hermes"), QStringLiteral("t_plan"), QStringLiteral("t_impl"),
                                        QStringLiteral("t_rel1"), QStringLiteral("t_corr1"), QStringLiteral("t_rel2"),
                                        QStringLiteral("t_autre"), QStringLiteral("t_orpheline"),
                                        QStringLiteral("t_cycle_a"), QStringLiteral("t_cycle_b")}));
    QCOMPARE(ligne(lignes, QStringLiteral("hermes")).value(QStringLiteral("niveau")).toInt(), 0);
    QCOMPARE(ligne(lignes, QStringLiteral("t_impl")).value(QStringLiteral("parent")).toString(), QStringLiteral("hermes"));
    // Relecture sous l'implémentation, correction sous la relecture, seconde relecture sous la correction.
    QCOMPARE(ligne(lignes, QStringLiteral("t_rel1")).value(QStringLiteral("niveau")).toInt(), 2);
    QCOMPARE(ligne(lignes, QStringLiteral("t_rel1")).value(QStringLiteral("parent")).toString(), QStringLiteral("t_impl"));
    QCOMPARE(ligne(lignes, QStringLiteral("t_corr1")).value(QStringLiteral("niveau")).toInt(), 3);
    QCOMPARE(ligne(lignes, QStringLiteral("t_corr1")).value(QStringLiteral("parent")).toString(), QStringLiteral("t_rel1"));
    QCOMPARE(ligne(lignes, QStringLiteral("t_rel2")).value(QStringLiteral("niveau")).toInt(), 4);
    QCOMPARE(ligne(lignes, QStringLiteral("t_rel2")).value(QStringLiteral("parent")).toString(), QStringLiteral("t_corr1"));
    QCOMPARE(ligne(lignes, QStringLiteral("t_autre")).value(QStringLiteral("niveau")).toInt(), 1);
    QCOMPARE(ligne(lignes, QStringLiteral("t_orpheline")).value(QStringLiteral("niveau")).toInt(), 1);
    // Cycle (forme directe) : chaque carte reste visible une seule fois.
    QCOMPARE(ligne(lignes, QStringLiteral("t_cycle_a")).value(QStringLiteral("niveau")).toInt(), 1);
    QCOMPARE(ligne(lignes, QStringLiteral("t_cycle_b")).value(QStringLiteral("parent")).toString(), QStringLiteral("t_cycle_a"));
    const QJsonObject impl = ligne(lignes, QStringLiteral("t_impl"));
    QCOMPARE(impl.value(QStringLiteral("portrait")).toString(), QStringLiteral("developpeur"));
    QCOMPARE(impl.value(QStringLiteral("sprite")).toString(), QStringLiteral("travail"));
    QCOMPARE(impl.value(QStringLiteral("sourceRoutage")).toString(), QStringLiteral("Auto : table de routage"));
    QCOMPARE(impl.value(QStringLiteral("effort")).toString(), QStringLiteral("Par défaut"));
    QCOMPARE(impl.value(QStringLiteral("modeleServi")).toString(), QStringLiteral("Non observé"));
    QCOMPARE(ligne(lignes, QStringLiteral("t_rel1")).value(QStringLiteral("portrait")).toString(), QStringLiteral("relecteur"));

    // Deux implémentations servies pour la même étape (forme inattendue) : aucune relation devinée.
    QJsonArray doubles = projet.value(QStringLiteral("cartes")).toArray();
    doubles.insert(2, etape(carte(QStringLiteral("t_impl_bis"), QStringLiteral("implementation"), QStringLiteral("todo"), 1),
                            QStringLiteral("e1")));
    QJsonObject ambigu = projet;
    ambigu.insert(QStringLiteral("cartes"), doubles);
    QCOMPARE(ligne(EspaceTravailViewModel::construireAgents(ambigu), QStringLiteral("t_rel1")).value(QStringLiteral("niveau")).toInt(), 1);
    // Mission non lue : aucun agent, pas même Hermes.
    QVERIFY(EspaceTravailViewModel::construireAgents({}).isEmpty());
}

void TestEspaceTravail::carteSansIdentifiantGardeUneCleStable()
{
    QJsonObject aCreer = carte(QString(), QStringLiteral("correction"), QStringLiteral("a_creer"), 2);
    aCreer.insert(QStringLiteral("ref"), QStringLiteral("correction-1"));
    const QJsonObject projet{{QStringLiteral("id"), kId}, {QStringLiteral("etat"), QStringLiteral("actif")},
                             {QStringLiteral("cartes"), QJsonArray{aCreer}}};
    const QJsonArray premiere = EspaceTravailViewModel::construireAgents(projet);
    QCOMPARE(cles(premiere), (QStringList{QStringLiteral("hermes"), QStringLiteral("ref:correction-1:2:0")}));
    QCOMPARE(cles(EspaceTravailViewModel::construireAgents(projet)), cles(premiere));
    QCOMPARE(ligne(premiere, QStringLiteral("ref:correction-1:2:0")).value(QStringLiteral("etat")).toString(), QStringLiteral("en_file"));
}

void TestEspaceTravail::etatsDAgentTiresDesStatutsServis()
{
    const QList<std::pair<QString, QString>> attendus = {
        {QStringLiteral("todo"), QStringLiteral("en_file")},        {QStringLiteral("ready"), QStringLiteral("en_file")},
        {QStringLiteral("a_creer"), QStringLiteral("en_file")},     {QStringLiteral("scheduled"), QStringLiteral("suspendue")},
        {QStringLiteral("running"), QStringLiteral("execute")},     {QStringLiteral("review"), QStringLiteral("attend_decision")},
        {QStringLiteral("triage"), QStringLiteral("attend_decision")}, {QStringLiteral("blocked"), QStringLiteral("bloquee")},
        {QStringLiteral("done"), QStringLiteral("terminee")},       {QStringLiteral("archived"), QStringLiteral("arretee")},
    };
    for (const auto &[statut, etat] : attendus) {
        const QJsonObject lu = EspaceTravailViewModel::etatAgent(statut);
        QCOMPARE(lu.value(QStringLiteral("etat")).toString(), etat);
        QVERIFY2(!lu.value(QStringLiteral("etatLibelle")).toString().isEmpty(), qPrintable(statut));
    }
    // Seul « running » anime le portrait au travail : rien n'est mimé sans exécution observée.
    QCOMPARE(EspaceTravailViewModel::etatAgent(QStringLiteral("running")).value(QStringLiteral("sprite")).toString(),
             QStringLiteral("travail"));
    QCOMPARE(EspaceTravailViewModel::etatAgent(QStringLiteral("todo")).value(QStringLiteral("sprite")).toString(),
             QStringLiteral("repos"));
    const QJsonObject inconnu = EspaceTravailViewModel::etatAgent(QStringLiteral("statut_futur"));
    QCOMPARE(inconnu.value(QStringLiteral("etat")).toString(), QStringLiteral("inconnu"));
    QCOMPARE(inconnu.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Inconnu (statut_futur)"));
    QCOMPARE(inconnu.value(QStringLiteral("statusKey")).toString(), QStringLiteral("unknown"));
    QCOMPARE(EspaceTravailViewModel::etatAgent(QString()).value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(EspaceTravailViewModel::portraitDuRole(QStringLiteral("role_futur")), QStringLiteral("inconnu"));
    // Posé par le lancement comme par le plan de Hermes : le libellé n'attribue le choix à personne.
    QCOMPARE(EspaceTravailViewModel::libelleSourceRoutage(QStringLiteral("choix_explicite")),
             QStringLiteral("Choix explicite (plan ou lancement), sans repli"));
    // « scheduled » : question, pause ou quota ; le libellé ne choisit pas la cause.
    QCOMPARE(EspaceTravailViewModel::etatAgent(QStringLiteral("scheduled")).value(QStringLiteral("etatLibelle")).toString(),
             QStringLiteral("Suspendue (question, pause ou quota)"));
    QCOMPARE(EspaceTravailViewModel::libelleSourceRoutage(QString()), QStringLiteral("Inconnu"));
}

void TestEspaceTravail::verificationsLuesDansLeJournal()
{
    const auto terminee = [](const QString &cible, const QJsonValue &detail) {
        return QJsonObject{{QStringLiteral("quand"), 1790423039}, {QStringLiteral("acteur"), QStringLiteral("acp-poste")},
                           {QStringLiteral("action"), QStringLiteral("carte_terminee")}, {QStringLiteral("cible"), cible},
                           {QStringLiteral("detail"), detail}};
    };
    const QJsonObject projet{
        {QStringLiteral("cartes"), QJsonArray{carte(QStringLiteral("t_impl"), QStringLiteral("implementation"), QStringLiteral("done"), 1)}},
        {QStringLiteral("journal"), QJsonArray{
             // Forme servie : le détail est un texte JSON.
             terminee(QStringLiteral("t_impl"), QStringLiteral("{\"verification\": \"reussie\", \"role\": \"implementation\"}")),
             terminee(QStringLiteral("t_impl"), QJsonObject{{QStringLiteral("verification"), QStringLiteral("echouee")}}),
             terminee(QStringLiteral("t_autre"), QJsonObject{{QStringLiteral("verification"), QStringLiteral("non_executee")}}),
             terminee(QStringLiteral("t_impl"), QJsonObject{{QStringLiteral("verification"), QJsonValue::Null}}),
             terminee(QStringLiteral("t_impl"), QStringLiteral("pas du JSON")),
             QJsonObject{{QStringLiteral("action"), QStringLiteral("lancement")}, {QStringLiteral("cible"), QStringLiteral("x")}},
         }},
    };
    const QJsonArray essais = EspaceTravailViewModel::construireEssais(projet);
    QCOMPARE(essais.size(), 5);
    QStringList libelles;
    QStringList etats;
    for (const QJsonValue &essai : essais) {
        libelles.append(essai.toObject().value(QStringLiteral("libelle")).toString());
        etats.append(essai.toObject().value(QStringLiteral("statusKey")).toString());
    }
    QCOMPARE(libelles, (QStringList{QStringLiteral("Vérification réussie"), QStringLiteral("Vérification échouée"),
                                    QStringLiteral("Vérification non exécutée"), QStringLiteral("Vérification non rapportée"),
                                    QStringLiteral("Vérification non rapportée")}));
    QCOMPARE(etats, (QStringList{QStringLiteral("succeeded"), QStringLiteral("failed"), QStringLiteral("notConfigured"),
                                 QStringLiteral("unknown"), QStringLiteral("unknown")}));
    QCOMPARE(essais.at(0).toObject().value(QStringLiteral("titre")).toString(), QStringLiteral("Carte t_impl"));
    // Carte absente de la mission : son identifiant, pas un titre inventé.
    QCOMPARE(essais.at(2).toObject().value(QStringLiteral("titre")).toString(), QStringLiteral("t_autre"));
    // Clés uniques même pour plusieurs vérifications d'une même carte.
    const QStringList clesEssais = cles(essais);
    QCOMPARE(QSet<QString>(clesEssais.cbegin(), clesEssais.cend()).size(), 5);
}

void TestEspaceTravail::sortiesSeulementLesResumesServis()
{
    QJsonObject longue = carte(QStringLiteral("t_b"), QStringLiteral("implementation"), QStringLiteral("done"), 1, {},
                               QStringLiteral("Résumé tronqué"));
    longue.insert(QStringLiteral("resume_tronque"), true);
    longue.insert(QStringLiteral("resume_longueur"), 4096);
    const QJsonObject projet{{QStringLiteral("cartes"), QJsonArray{
        carte(QStringLiteral("t_a"), QStringLiteral("exploration"), QStringLiteral("done"), 0, {}, QStringLiteral("Résumé A")),
        carte(QStringLiteral("t_vide"), QStringLiteral("planification"), QStringLiteral("todo"), 0),
        longue,
    }}};
    const QJsonArray sorties = EspaceTravailViewModel::construireSorties(projet);
    QCOMPARE(cles(sorties), (QStringList{QStringLiteral("t_a"), QStringLiteral("t_b")}));
    QVERIFY(sorties.at(1).toObject().value(QStringLiteral("tronque")).toBool());
    QCOMPARE(sorties.at(1).toObject().value(QStringLiteral("resume")).toString(), QStringLiteral("Résumé tronqué"));
}

void TestEspaceTravail::pictogrammeStable()
{
    // FNV-1a : la même clé donne le même pictogramme d'une exécution à l'autre (qHash est salé).
    const QVariantMap premier = EspaceTravailViewModel::pictogramme(QStringLiteral("g:jetable"));
    QCOMPARE(EspaceTravailViewModel::pictogramme(QStringLiteral("g:jetable")), premier);
    const QStringList motifs = {QStringLiteral("fusee"), QStringLiteral("cristal"), QStringLiteral("feuille"), QStringLiteral("livre"),
                                QStringLiteral("eclair"), QStringLiteral("planete"), QStringLiteral("engrenage")};
    const QStringList teintes = {QStringLiteral("lavande"), QStringLiteral("menthe"), QStringLiteral("ambre"), QStringLiteral("rose"),
                                 QStringLiteral("ciel")};
    QSet<QString> vus;
    for (int rang = 0; rang < 200; ++rang) {
        const QVariantMap picto = EspaceTravailViewModel::pictogramme(QStringLiteral("p_%1").arg(rang, 12, 10, QLatin1Char('0')));
        QVERIFY(motifs.contains(picto.value(QStringLiteral("motif")).toString()));
        QVERIFY(teintes.contains(picto.value(QStringLiteral("teinte")).toString()));
        vus.insert(picto.value(QStringLiteral("motif")).toString() + picto.value(QStringLiteral("teinte")).toString());
    }
    // Les 35 combinaisons servent : la répartition n'écrase pas tout sur un seul dessin.
    QVERIFY2(vus.size() >= 30, qPrintable(QString::number(vus.size())));
    // Valeurs fixées (FNV-1a calculé à part) : changer l'empreinte changerait l'aspect des projets existants.
    QCOMPARE(premier.value(QStringLiteral("motif")).toString(), QStringLiteral("livre"));
    QCOMPARE(premier.value(QStringLiteral("teinte")).toString(), QStringLiteral("lavande"));
    QCOMPARE(EspaceTravailViewModel::pictogramme(QStringLiteral("g:")).value(QStringLiteral("motif")).toString(),
             QStringLiteral("cristal"));
    QCOMPARE(EspaceTravailViewModel::pictogramme(QStringLiteral("g:")).value(QStringLiteral("teinte")).toString(),
             QStringLiteral("rose"));
}

void TestEspaceTravail::brouillonsEnMemoireOubliesAvecLaSession()
{
    Banc banc;
    QSignalSpy change(&banc.espace, &EspaceTravailViewModel::brouillonChange);
    banc.espace.noterBrouillon(QStringLiteral("nouvelle-mission:objectif"), QStringLiteral("Écrire les tests"));
    banc.espace.noterBrouillon(QStringLiteral("nouvelle-mission:objectif"), QStringLiteral("Écrire les tests"));
    QCOMPARE(change.count(), 1);
    QCOMPARE(banc.espace.brouillon(QStringLiteral("nouvelle-mission:objectif")), QStringLiteral("Écrire les tests"));
    QCOMPARE(banc.espace.brouillon(QStringLiteral("mission-suivante:jetable")), QString());
    // Contexte vide : refusé sans effet.
    banc.espace.noterBrouillon(QString(), QStringLiteral("x"));
    QCOMPARE(change.count(), 1);
    // Texte vidé : le brouillon disparaît.
    banc.espace.noterBrouillon(QStringLiteral("mission-suivante:jetable"), QStringLiteral("a"));
    banc.espace.noterBrouillon(QStringLiteral("mission-suivante:jetable"), QString());
    QCOMPARE(banc.espace.brouillon(QStringLiteral("mission-suivante:jetable")), QString());
    // Oubli des données du greffon (verdict bloquant) : les brouillons de la Discussion restent.
    banc.espace.noterBrouillon(QStringLiteral("discussion:rt-s1"), QStringLiteral("Message en cours"));
    banc.espace.oublierDonneesGreffon();
    QCOMPARE(banc.espace.brouillon(QStringLiteral("discussion:rt-s1")), QStringLiteral("Message en cours"));
    QCOMPARE(banc.espace.brouillon(QStringLiteral("nouvelle-mission:objectif")), QString());
    banc.espace.noterBrouillon(QStringLiteral("nouvelle-mission:objectif"), QStringLiteral("Écrire les tests"));
    // Oubli de la session (déconnexion) : plus rien, même pas la recherche.
    banc.espace.setRecherche(QStringLiteral("outil"));
    banc.espace.oublier();
    QCOMPARE(banc.espace.brouillon(QStringLiteral("nouvelle-mission:objectif")), QString());
    QCOMPARE(banc.espace.brouillon(QStringLiteral("discussion:rt-s1")), QString());
    QCOMPARE(banc.espace.recherche(), QString());
    QVERIFY(!banc.espace.listeLue());
}

void TestEspaceTravail::boutEnBoutContreLeFauxHermes()
{
    Banc banc;
    banc.flux.demarrer();
    // Rien n'est lu tant que la barre n'est pas affichée.
    QTest::qWait(50);
    QVERIFY(!banc.espace.listeLue());
    banc.espace.setPageVisible(true);
    QTRY_VERIFY(banc.espace.listeLue());
    QCOMPARE(banc.espace.nombreMissions(), 2);
    QCOMPARE(banc.espace.nombreProjets(), 2);
    QStringList lues;
    for (int rang = 0; rang < banc.espace.arbre()->count(); ++rang) {
        lues.append(banc.espace.arbre()->itemAt(rang).value(QStringLiteral("cle")).toString());
    }
    // Deux groupes actifs : « jetable » (le plus récent) puis « Sans dépôt ».
    QCOMPARE(lues, (QStringList{QStringLiteral("g:jetable"), QStringLiteral("m:") + kId, QStringLiteral("g:"),
                                QStringLiteral("m:p_a35a8b99fb0e")}));
    QCOMPARE(banc.espace.arbre()->itemAt(0).value(QStringLiteral("questions")).toInt(), 1);

    // Replier puis déplier un groupe : relu par clé, sans relecture serveur.
    const int requetes = banc.serveur.requetes.size();
    banc.espace.basculer(QStringLiteral("g:jetable"));
    QCOMPARE(banc.espace.arbre()->count(), 3);
    banc.espace.basculer(QStringLiteral("g:jetable"));
    QCOMPARE(banc.espace.arbre()->count(), 4);
    banc.espace.basculer(QStringLiteral("clé inconnue"));
    QCOMPARE(banc.espace.arbre()->count(), 4);
    QCOMPARE(banc.serveur.requetes.size(), requetes);

    // Choisir une mission : route « projects », détail lu, panneau des agents rempli.
    banc.projets.setPageVisible(true);
    QSignalSpy selection(&banc.espace, &EspaceTravailViewModel::selectionChange);
    banc.espace.selectionnerMission(kId);
    QCOMPARE(banc.navigation.currentRoute(), QStringLiteral("projects"));
    QCOMPARE(banc.espace.missionSelectionnee(), kId);
    QVERIFY(selection.count() >= 1);
    QTRY_VERIFY(banc.projets.detailLu());
    QTRY_COMPARE(banc.espace.mission().value(QStringLiteral("id")).toString(), kId);
    QCOMPARE(banc.espace.mission().value(QStringLiteral("depot")).toString(), QStringLiteral("jetable"));
    QStringList agents;
    for (int rang = 0; rang < banc.espace.agents()->count(); ++rang) {
        agents.append(banc.espace.agents()->itemAt(rang).value(QStringLiteral("cle")).toString());
    }
    QCOMPARE(agents, (QStringList{QStringLiteral("hermes"), QStringLiteral("t_7aa28f61"), QStringLiteral("t_342c81eb")}));
    QCOMPARE(banc.espace.mission().value(QStringLiteral("agents")).toInt(), 3);
    // Exploration « scheduled » : suspendue, portrait en attente ; aucune vérification servie.
    QCOMPARE(banc.espace.agents()->itemAt(1).value(QStringLiteral("etat")).toString(), QStringLiteral("suspendue"));
    QCOMPARE(banc.espace.essais()->count(), 0);
    QCOMPARE(banc.espace.sorties()->count(), 1);
    // La ligne de la mission est marquée choisie dans la barre.
    QTRY_VERIFY(banc.espace.arbre()->itemAt(1).value(QStringLiteral("selectionnee")).toBool());

    QVERIFY(!banc.espace.essaisPartiels());

    // Choisir un agent, puis une relecture du détail où il n'est plus servi : la sélection est effacée.
    banc.espace.setAgentSelectionne(QStringLiteral("t_7aa28f61"));
    QCOMPARE(banc.espace.agent().value(QStringLiteral("role")).toString(), QStringLiteral("exploration"));
    QJsonObject relu = banc.detail;
    QJsonObject projetRelu = relu.contains(QStringLiteral("projet")) ? relu.value(QStringLiteral("projet")).toObject() : relu;
    QJsonArray restantes;
    for (const QJsonValue &c : projetRelu.value(QStringLiteral("cartes")).toArray()) {
        if (c.toObject().value(QStringLiteral("carte")).toString() != QLatin1String("t_7aa28f61")) restantes.append(c);
    }
    projetRelu.insert(QStringLiteral("cartes"), restantes);
    // Journal à sa borne (100 lignes servies) : la liste des vérifications se dit partielle.
    QJsonArray journal;
    for (int i = 0; i < EspaceTravailViewModel::kBorneJournal; ++i) {
        journal.append(QJsonObject{{QStringLiteral("quand"), 1790423039 - i}, {QStringLiteral("acteur"), QStringLiteral("acp-poste")},
                                   {QStringLiteral("action"), QStringLiteral("note")}, {QStringLiteral("cible"), kId},
                                   {QStringLiteral("detail"), QStringLiteral("ligne")}});
    }
    projetRelu.insert(QStringLiteral("journal"), journal);
    if (relu.contains(QStringLiteral("projet"))) relu.insert(QStringLiteral("projet"), projetRelu); else relu = projetRelu;
    banc.detail = relu;
    banc.projets.actualiser();
    QTRY_COMPARE(banc.espace.agentSelectionne(), QString());
    QVERIFY(banc.espace.agent().isEmpty());
    QTRY_VERIFY(banc.espace.essaisPartiels());
    QCOMPARE(banc.espace.agents()->count(), 2);

    // Identifiant invalide : refusé sans geste ni navigation.
    banc.navigation.setCurrentRoute(QStringLiteral("home"));
    banc.espace.selectionnerMission(QStringLiteral("../etc"));
    QCOMPARE(banc.navigation.currentRoute(), QStringLiteral("home"));
    QCOMPARE(banc.espace.missionSelectionnee(), kId);

    // Nouvelle mission sur un dépôt : formulaire ouvert, rien n'est envoyé.
    const int avant = banc.serveur.requetes.size();
    banc.espace.nouvelleMission(QStringLiteral("jetable"));
    QCOMPARE(banc.navigation.currentRoute(), QStringLiteral("projects"));
    QCOMPARE(banc.projets.vue(), QStringLiteral("nouveau"));
    // Le dépôt demandé survit à la lecture asynchrone de l'inventaire (première ouverture du formulaire).
    QTRY_VERIFY(banc.projets.formulaire().value(QStringLiteral("pret")).toBool());
    QCOMPARE(banc.projets.formulaire().value(QStringLiteral("depot")).toString(), QStringLiteral("jetable"));
    for (int rang = avant; rang < banc.serveur.requetes.size(); ++rang) {
        QVERIFY2(banc.serveur.requetes.at(rang).methode != "POST", "aucun geste envoyé par la barre");
    }
}

QTEST_MAIN(TestEspaceTravail)
#include "tst_espace_travail.moc"
