// Page Routage contre les formes RÉELLES de `GET /v1/routage` (fixtures-poste.ts, capturées
// sur l'image) et le faux Hermes :
//  - listes relevées et badges ; « Accepter ce relevé » seulement quand le greffon le permet,
//    identifiant envoyé en nombre ;
//  - classes dans l'ordre de la page web, suggestion appliquée au brouillon ; validation avec
//    EXACTEMENT les relevés lus et les classes non vides ; 422 : refus à leur ligne, rien
//    d'enregistré, brouillon gardé ; 409 : relu et brouillon rebâti ;
//  - brouillon gardé au sondage, rebâti à l'arrivée d'un nouveau relevé ;
//  - interdits en lecture seule, surcharges désactivables, édition dans le navigateur.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/RoutageViewModel.h"

#include <QJsonArray>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");

QJsonObject entree(const QString &voie, const QJsonValue &modele, const QJsonValue &effort, const QJsonValue &palier)
{
    return QJsonObject{{QStringLiteral("voie"), voie}, {QStringLiteral("modele"), modele},
                       {QStringLiteral("effort"), effort}, {QStringLiteral("palier"), palier}};
}

//! Vue `routage.json` où la classe donnée est validée avec les entrées jugées données.
QJsonObject avecClasseValidee(QJsonObject vue, const QString &classe, const QJsonArray &entrees)
{
    QJsonObject classes = vue.value(QStringLiteral("classes")).toObject();
    QJsonObject c = classes.value(classe).toObject();
    c.insert(QStringLiteral("etat"), QStringLiteral("validee"));
    c.insert(QStringLiteral("entrees"), entrees);
    c.insert(QStringLiteral("valide_le"), 1790451700);
    classes.insert(classe, c);
    vue.insert(QStringLiteral("classes"), classes);
    return vue;
}

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    RoutageViewModel routage{&client, &greffon, &flux};
    QJsonObject vue = fixture(QStringLiteral("routage.json"));
    ReponseFaux validation;
    ReponseFaux acceptation;
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
        routage.setOuvreur([this](const QUrl &url) {
            ouvertes.append(url);
            return true;
        });
        serveur.route("GET", kP + QStringLiteral("/routage"), [this](const RequeteRecue &) { return ReponseFaux::json(200, vue); });
        serveur.route("POST", kP + QStringLiteral("/routage"), [this](const RequeteRecue &) { return validation; });
        serveur.route("POST", kP + QStringLiteral("/routage/releve-accepte"), [this](const RequeteRecue &) { return acceptation; });
        serveur.route("POST", kP + QStringLiteral("/routage/surcharges/7/desactiver"), [](const RequeteRecue &) {
            return ReponseFaux::json(200, QJsonObject{{QStringLiteral("id"), 7}, {QStringLiteral("active"), false}});
        });
    }

    void ouvrirLaPage()
    {
        flux.demarrer();
        routage.setPageVisible(true);
        QTRY_VERIFY(routage.lue());
    }

    void relire()
    {
        QSignalSpy lu(&routage, &RoutageViewModel::routageChange);
        routage.actualiser();
        QVERIFY(lu.wait(3000));
    }

    QJsonObject classe(const QString &nom) const
    {
        for (int index = 0; index < routage.classes()->count(); ++index) {
            const QJsonObject item = routage.classes()->itemAt(index);
            if (item.value(QStringLiteral("classe")).toString() == nom) {
                return item;
            }
        }
        return {};
    }
};

} // namespace

class TestRoutage : public QObject
{
    Q_OBJECT

private slots:
    void listesLibellees();
    void accepterSeulementSiPropose();
    void classesDansLOrdreAvecSuggestion();
    void tableVideRefuseeSansEnvoi();
    void suggestionPuisValidationCorpsExact();
    void refusParEntreeRienEnregistre();
    void releveChangeRelitEtRebatit();
    void brouillonGardeAuSondageRebatiAuNouveauReleve();
    void retirerPuisRevenir();
    void surchargesEtPolitiques();
    void modifierDansLeNavigateur();
};

void TestRoutage::listesLibellees()
{
    const QJsonObject voies = fixture(QStringLiteral("routage.json")).value(QStringLiteral("voies")).toObject();
    const QJsonObject codex = RoutageViewModel::construireListe(QStringLiteral("poste-codex"), voies.value(QStringLiteral("poste-codex")).toObject());
    QCOMPARE(codex.value(QStringLiteral("titre")).toString(), QStringLiteral("Poste (Codex)"));
    QCOMPARE(codex.value(QStringLiteral("badgeLibelle")).toString(), QStringLiteral("Relevé du compte"));
    QCOMPARE(codex.value(QStringLiteral("badgeCle")).toString(), QStringLiteral("succeeded"));
    QCOMPARE(codex.value(QStringLiteral("versionCli")).toString(), QStringLiteral("0.156.1"));
    QCOMPARE(codex.value(QStringLiteral("peutAccepter")).toBool(), false);
    const QJsonArray modeles = codex.value(QStringLiteral("modeles")).toArray();
    QCOMPARE(modeles.size(), 2);
    QCOMPARE(modeles.at(0).toObject().value(QStringLiteral("id")).toString(), QStringLiteral("factice-codex-1"));
    QCOMPARE(modeles.at(0).toObject().value(QStringLiteral("parDefaut")).toBool(), true);
    QCOMPARE(modeles.at(0).toObject().value(QStringLiteral("efforts")).toString(), QStringLiteral("Efforts : low, medium, high"));
    QCOMPARE(modeles.at(1).toObject().value(QStringLiteral("parDefaut")).toBool(), false);

    const QJsonObject claude = RoutageViewModel::construireListe(QStringLiteral("poste-claude"), voies.value(QStringLiteral("poste-claude")).toObject());
    QCOMPARE(claude.value(QStringLiteral("badgeLibelle")).toString(), QStringLiteral("Alias documentés"));
    QCOMPARE(claude.value(QStringLiteral("modeles")).toArray().at(0).toObject().value(QStringLiteral("resolution")).toString(),
             QStringLiteral("claude-opus-5-5"));

    const QJsonObject vide = RoutageViewModel::construireListe(
        QStringLiteral("poste-codex"),
        fixture(QStringLiteral("routage-vide.json")).value(QStringLiteral("voies")).toObject().value(QStringLiteral("poste-codex")).toObject());
    QCOMPARE(vide.value(QStringLiteral("badgeLibelle")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(vide.value(QStringLiteral("aucunModele")).toString(), QStringLiteral("Aucun relevé : le poste n'a encore rien publié."));
    // Efforts : liste vide documentée, ou absente (inconnue) ; badge inconnu de la station.
    const QJsonObject autre = RoutageViewModel::construireListe(QStringLiteral("poste-codex"), QJsonObject{
        {QStringLiteral("badge"), QStringLiteral("nouveau_badge")},
        {QStringLiteral("modeles"), QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("m1")},
                                                           {QStringLiteral("supportedReasoningEfforts"), QJsonArray{}}},
                                               QJsonObject{{QStringLiteral("id"), QStringLiteral("m2")}}}}});
    QCOMPARE(autre.value(QStringLiteral("badgeLibelle")).toString(), QStringLiteral("nouveau_badge"));
    QCOMPARE(autre.value(QStringLiteral("badgeCle")).toString(), QStringLiteral("unknown"));
    QCOMPARE(autre.value(QStringLiteral("modeles")).toArray().at(0).toObject().value(QStringLiteral("efforts")).toString(),
             QStringLiteral("Aucun effort documenté"));
    QCOMPARE(autre.value(QStringLiteral("modeles")).toArray().at(1).toObject().value(QStringLiteral("efforts")).toString(),
             QStringLiteral("Efforts inconnus"));
}

void TestRoutage::accepterSeulementSiPropose()
{
    Banc banc;
    banc.vue = fixture(QStringLiteral("routage-secours.json"));
    banc.acceptation = ReponseFaux::json(200, fixture(QStringLiteral("routage.json")));
    banc.ouvrirLaPage();
    QCOMPARE(banc.routage.listes()->itemAt(0).value(QStringLiteral("peutAccepter")).toBool(), true);
    QCOMPARE(banc.routage.listes()->itemAt(1).value(QStringLiteral("peutAccepter")).toBool(), false);

    banc.routage.accepterReleve(QStringLiteral("poste-claude"));
    QCOMPARE(banc.routage.erreurGeste(), QStringLiteral("Le greffon ne propose pas d'accepter ce relevé."));
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/routage/releve-accepte")), 0);

    banc.routage.accepterReleve(QStringLiteral("poste-codex"));
    QTRY_VERIFY(!banc.routage.gesteEnCours());
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/routage/releve-accepte"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), (QJsonObject{{QStringLiteral("releve_id"), 3}}));
    QVERIFY(envois.first().json().value(QStringLiteral("releve_id")).isDouble());
    QCOMPARE(banc.routage.messageGeste(), QStringLiteral("Relevé accepté."));
}

void TestRoutage::classesDansLOrdreAvecSuggestion()
{
    Banc banc;
    banc.ouvrirLaPage();
    QCOMPARE(banc.routage.classes()->count(), 11);
    QStringList ordre;
    for (int index = 0; index < banc.routage.classes()->count(); ++index) {
        ordre.append(banc.routage.classes()->itemAt(index).value(QStringLiteral("classe")).toString());
    }
    QCOMPARE(ordre.mid(0, 3), (QStringList{QStringLiteral("exploration"), QStringLiteral("planification"), QStringLiteral("synthese")}));
    QCOMPARE(ordre.last(), QStringLiteral("relecture"));
    const QJsonObject exploration = banc.classe(QStringLiteral("exploration"));
    QCOMPARE(exploration.value(QStringLiteral("titre")).toString(), QStringLiteral("Exploration du dépôt"));
    QCOMPARE(exploration.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Non validée"));
    QCOMPARE(exploration.value(QStringLiteral("vide")).toBool(), true);
    QCOMPARE(exploration.value(QStringLiteral("voies")).toString(), QStringLiteral("Poste (Claude), Poste (Codex)"));
    QCOMPARE(exploration.value(QStringLiteral("aSuggestion")).toBool(), true);
    QCOMPARE(exploration.value(QStringLiteral("suggestion")).toString(),
             QStringLiteral("Poste (Codex) · factice-codex-1 · effort medium · palier Standard"));
    QCOMPARE(exploration.value(QStringLiteral("suggestionLibelle")).toString(),
             QStringLiteral("Suggestion calculée depuis le relevé du 26/09/2026 21:40."));
    QCOMPARE(exploration.value(QStringLiteral("remarques")).toString(),
             QStringLiteral("Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."));
    QCOMPARE(banc.classe(QStringLiteral("planification")).value(QStringLiteral("suggestion")).toString(),
             QStringLiteral("Hermes · modèle par défaut · palier Standard"));
    QVERIFY(banc.routage.brouillonVide());
    QVERIFY(!banc.routage.brouillonModifie());
}

void TestRoutage::tableVideRefuseeSansEnvoi()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.routage.valider();
    QCOMPARE(banc.routage.erreurGeste(),
             QStringLiteral("La table est vide : appliquez une suggestion, ou modifiez la table dans le navigateur."));
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/routage")), 0);
    banc.routage.appliquerSuggestion(QStringLiteral("classe-inexistante"));
    QCOMPARE(banc.routage.erreurGeste(), QStringLiteral("Classe inconnue : la page est relue."));
}

void TestRoutage::suggestionPuisValidationCorpsExact()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.routage.appliquerSuggestion(QStringLiteral("exploration"));
    QVERIFY(banc.routage.brouillonModifie());
    QVERIFY(!banc.routage.brouillonVide());
    const QJsonObject exploration = banc.classe(QStringLiteral("exploration"));
    QCOMPARE(exploration.value(QStringLiteral("modifiee")).toBool(), true);
    const QJsonObject ligne = exploration.value(QStringLiteral("entrees")).toArray().at(0).toObject();
    QCOMPARE(ligne.value(QStringLiteral("verdict")).toString(), QStringLiteral("À valider"));
    QCOMPARE(ligne.value(QStringLiteral("texte")).toString(), QStringLiteral("Poste (Codex) · factice-codex-1 · effort medium · palier Standard"));

    const QJsonObject jugee = QJsonObject{{QStringLiteral("voie"), QStringLiteral("poste-codex")},
                                          {QStringLiteral("modele"), QStringLiteral("factice-codex-1")},
                                          {QStringLiteral("effort"), QStringLiteral("medium")},
                                          {QStringLiteral("palier"), QStringLiteral("default")},
                                          {QStringLiteral("admise"), true}, {QStringLiteral("code"), QJsonValue::Null},
                                          {QStringLiteral("message"), QJsonValue::Null}};
    const QJsonObject apres = avecClasseValidee(fixture(QStringLiteral("routage.json")), QStringLiteral("exploration"), QJsonArray{jugee});
    banc.validation = ReponseFaux::json(200, apres);
    banc.vue = apres;
    banc.routage.valider();
    QTRY_VERIFY(!banc.routage.gesteEnCours());
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/routage"));
    QCOMPARE(envois.size(), 1);
    const QJsonObject attendu{
        {QStringLiteral("releves"), QJsonObject{{QStringLiteral("poste-codex"), 1}, {QStringLiteral("poste-claude"), 2}}},
        {QStringLiteral("classes"), QJsonObject{{QStringLiteral("exploration"), QJsonArray{
            entree(QStringLiteral("poste-codex"), QStringLiteral("factice-codex-1"), QStringLiteral("medium"), QStringLiteral("default"))}}}},
    };
    QCOMPARE(envois.first().json(), attendu);
    QCOMPARE(banc.routage.messageGeste(), QStringLiteral("Table validée."));
    QVERIFY(!banc.routage.brouillonModifie());
    const QJsonObject validee = banc.classe(QStringLiteral("exploration"));
    QCOMPARE(validee.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Validée"));
    QCOMPARE(validee.value(QStringLiteral("entrees")).toArray().at(0).toObject().value(QStringLiteral("verdict")).toString(),
             QStringLiteral("Admise"));
    QVERIFY(validee.value(QStringLiteral("valideLe")).toString().startsWith(QStringLiteral("26/09/2026")));
}

void TestRoutage::refusParEntreeRienEnregistre()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.routage.appliquerSuggestion(QStringLiteral("implementation"));
    banc.validation = ReponseFaux::json(422, fixture(QStringLiteral("refus-table.json")));
    banc.routage.valider();
    QTRY_VERIFY(!banc.routage.gesteEnCours());
    QCOMPARE(banc.routage.erreurGeste(),
             QStringLiteral("Table de routage refusée : 1 entrée(s) refusée(s) ; rien n'a été enregistré."));
    const QString message = QStringLiteral(
        "Refusé par ACP : le modèle « inexistant » ne figure pas dans le relevé de la voie poste-codex (relevé du 26/09/2026 21:40).");
    const QJsonObject ligne = banc.classe(QStringLiteral("implementation")).value(QStringLiteral("entrees")).toArray().at(0).toObject();
    QCOMPARE(ligne.value(QStringLiteral("verdict")).toString(), QStringLiteral("Refusée"));
    QCOMPARE(ligne.value(QStringLiteral("message")).toString(), message);
    QCOMPARE(banc.routage.refusTable(), QStringList{QStringLiteral("Implémentation, entrée 1 : ") + message});
    // Rien n'est enregistré : le brouillon reste, la page n'est pas relue sur ce refus.
    QVERIFY(banc.routage.brouillonModifie());
    // Retirer l'entrée refusée efface les refus de sa classe (les rangs ont bougé).
    banc.routage.retirerEntree(QStringLiteral("implementation"), 0);
    QCOMPARE(banc.classe(QStringLiteral("implementation")).value(QStringLiteral("entrees")).toArray().size(), 0);
}

void TestRoutage::releveChangeRelitEtRebatit()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.routage.appliquerSuggestion(QStringLiteral("exploration"));
    QVERIFY(banc.routage.brouillonModifie());
    banc.validation = ReponseFaux::json(409, QJsonObject{{QStringLiteral("detail"), QJsonObject{
        {QStringLiteral("code"), QStringLiteral("releve_change")},
        {QStringLiteral("message"), QStringLiteral("Refusé par ACP : un relevé a changé depuis l'ouverture de la page.")}}}});
    QSignalSpy lu(&banc.routage, &RoutageViewModel::routageChange);
    banc.routage.valider();
    QTRY_VERIFY(!banc.routage.gesteEnCours());
    QCOMPARE(banc.routage.erreurGeste(), QStringLiteral("Refusé par ACP : un relevé a changé depuis l'ouverture de la page."));
    QTRY_VERIFY(!banc.routage.brouillonModifie()); // relu, brouillon rebâti depuis la table
    QVERIFY(lu.count() >= 1);
}

void TestRoutage::brouillonGardeAuSondageRebatiAuNouveauReleve()
{
    Banc banc;
    banc.ouvrirLaPage();
    banc.routage.appliquerSuggestion(QStringLiteral("exploration"));
    banc.relire();
    QVERIFY(banc.routage.brouillonModifie()); // même relevé : le brouillon reste
    banc.vue.insert(QStringLiteral("releves"), QJsonObject{{QStringLiteral("poste-codex"), 5}, {QStringLiteral("poste-claude"), 2}});
    banc.relire();
    QVERIFY(!banc.routage.brouillonModifie()); // nouveau relevé : rebâti

    // La validation envoie les relevés du brouillon, ceux de la DERNIÈRE reconstruction.
    banc.routage.appliquerSuggestion(QStringLiteral("planification"));
    banc.validation = ReponseFaux::json(200, banc.vue);
    banc.routage.valider();
    QTRY_VERIFY(!banc.routage.gesteEnCours());
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/routage")).last().json().value(QStringLiteral("releves")).toObject()
                 .value(QStringLiteral("poste-codex")).toInt(),
             5);
}

void TestRoutage::retirerPuisRevenir()
{
    Banc banc;
    const QJsonObject jugee{{QStringLiteral("voie"), QStringLiteral("poste-codex")}, {QStringLiteral("modele"), QStringLiteral("factice-codex-2")},
                            {QStringLiteral("effort"), QStringLiteral("low")}, {QStringLiteral("palier"), QStringLiteral("default")},
                            {QStringLiteral("admise"), false}, {QStringLiteral("code"), QStringLiteral("effort_interdit")},
                            {QStringLiteral("message"), QStringLiteral("Refusé par ACP : effort interdit.")}};
    QJsonObject seconde = jugee;
    seconde.insert(QStringLiteral("admise"), true);
    seconde.insert(QStringLiteral("message"), QJsonValue::Null);
    banc.vue = avecClasseValidee(banc.vue, QStringLiteral("implementation"), QJsonArray{jugee, seconde});
    banc.ouvrirLaPage();
    QJsonArray lignes = banc.classe(QStringLiteral("implementation")).value(QStringLiteral("entrees")).toArray();
    QCOMPARE(lignes.size(), 2);
    QCOMPARE(lignes.at(0).toObject().value(QStringLiteral("verdict")).toString(), QStringLiteral("Refusée"));
    QCOMPARE(lignes.at(0).toObject().value(QStringLiteral("message")).toString(), QStringLiteral("Refusé par ACP : effort interdit."));
    QCOMPARE(lignes.at(1).toObject().value(QStringLiteral("verdict")).toString(), QStringLiteral("Admise"));
    QVERIFY(!banc.routage.brouillonVide());

    banc.routage.retirerEntree(QStringLiteral("implementation"), 0);
    banc.routage.retirerEntree(QStringLiteral("implementation"), 9); // hors bornes : sans effet
    lignes = banc.classe(QStringLiteral("implementation")).value(QStringLiteral("entrees")).toArray();
    QCOMPARE(lignes.size(), 1);
    QCOMPARE(lignes.at(0).toObject().value(QStringLiteral("verdict")).toString(), QStringLiteral("À valider"));
    QVERIFY(banc.routage.brouillonModifie());
    banc.routage.revenir();
    QCOMPARE(banc.classe(QStringLiteral("implementation")).value(QStringLiteral("entrees")).toArray().size(), 2);
    QVERIFY(!banc.routage.brouillonModifie());
}

void TestRoutage::surchargesEtPolitiques()
{
    Banc banc;
    banc.vue.insert(QStringLiteral("surcharges"), QJsonArray{QJsonObject{
        {QStringLiteral("id"), 7}, {QStringLiteral("classe"), QStringLiteral("implementation")},
        {QStringLiteral("voie"), QStringLiteral("poste-claude")}, {QStringLiteral("modele"), QStringLiteral("opus")},
        {QStringLiteral("effort"), QStringLiteral("high")}, {QStringLiteral("palier"), QJsonValue::Null},
        {QStringLiteral("motif"), QStringLiteral("Essai d'Opus")}, {QStringLiteral("cree_le"), 1790451700}}});
    banc.ouvrirLaPage();
    QCOMPARE(banc.routage.surcharges()->count(), 1);
    const QJsonObject surcharge = banc.routage.surcharges()->itemAt(0);
    QCOMPARE(surcharge.value(QStringLiteral("id")).toString(), QStringLiteral("7"));
    QCOMPARE(surcharge.value(QStringLiteral("classe")).toString(), QStringLiteral("Implémentation"));
    QCOMPARE(surcharge.value(QStringLiteral("entree")).toString(), QStringLiteral("Poste (Claude) · opus · effort high"));
    QCOMPARE(surcharge.value(QStringLiteral("motif")).toString(), QStringLiteral("Essai d'Opus"));
    banc.routage.desactiverSurcharge(QStringLiteral("7"));
    QTRY_VERIFY(!banc.routage.gesteEnCours());
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/routage/surcharges/7/desactiver")).first().json(), QJsonObject{});
    QCOMPARE(banc.routage.messageGeste(), QStringLiteral("Surcharge désactivée."));

    const QVariantMap hermes = banc.routage.politiqueHermes();
    QCOMPARE(hermes.value(QStringLiteral("effortsInterdits")).toString(), QStringLiteral("max, ultra, ultracode"));
    QCOMPARE(hermes.value(QStringLiteral("paliersAdmis")).toString(), QStringLiteral("default"));
    const QVariantMap poste = banc.routage.politiquePoste();
    QCOMPARE(poste.value(QStringLiteral("presente")).toBool(), true);
    QCOMPARE(poste.value(QStringLiteral("executants")).toString(), QStringLiteral("codex, claude"));
    QCOMPARE(poste.value(QStringLiteral("modelesCodex")).toString(), QStringLiteral("Tous ceux du relevé"));
    QCOMPARE(poste.value(QStringLiteral("aliasClaude")).toString(), QStringLiteral("opus, opus[1m], sonnet, haiku"));
    QCOMPARE(poste.value(QStringLiteral("reseau")).toString(), QStringLiteral("Non"));
    QCOMPARE(RoutageViewModel::construirePolitiquePoste(QJsonObject{{QStringLiteral("politique_poste"), QJsonValue::Null}})
                 .value(QStringLiteral("presente")).toBool(),
             false);
    QCOMPARE(RoutageViewModel::construirePolitiqueHermes({}).value(QStringLiteral("effortsInterdits")).toString(),
             QStringLiteral("Inconnu"));
}

void TestRoutage::modifierDansLeNavigateur()
{
    Banc banc;
    QVERIFY(banc.routage.modifierDansLeNavigateur());
    QCOMPARE(banc.ouvertes.size(), 1);
    QCOMPARE(banc.ouvertes.first().path(), QStringLiteral("/poste"));
    QCOMPARE(banc.ouvertes.first().query(), QStringLiteral("vue=routage"));
    QCOMPARE(banc.ouvertes.first().host(), QStringLiteral("127.0.0.1"));
}

QTEST_MAIN(TestRoutage)
#include "tst_routage.moc"
