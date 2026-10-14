#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "support/FauxCoffre.h"
#include "viewmodels/ObsidianViewModel.h"
#include <QTest>
#include <QUuid>
using namespace acp;
using namespace acp::test;
namespace {
struct Banc {
    FauxHermes serveur;
    FauxCoffre disque;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client,&greffon,nullptr};
    ObsidianViewModel vue{&greffon,&flux};
    Banc() {
        serveur.installerAuthentification(); serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        disque.installer(serveur); client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) qFatal("URL du faux Hermes refusée");
        client.setBearerProvider([]{return QByteArrayLiteral("jeton-a");}); flux.setIntervalleFond(std::chrono::hours(1));
    }
    void ouvrir() { flux.demarrer(); vue.setPageVisible(true); }
};
}
class TestObsidian : public QObject
{
    Q_OBJECT
private slots:
    void cheminsEtEmpreintesBornes();
    void etatReelEtSessionRequise();
    void ancienServeurExpliqueLaMiseAJour();
    void refusCertainEtErreurIncertaine();
    void listeRechercheEtLiensDuCoffre();
    void brouillonsConservesEntreNotesEtPages();
    void sauvegardeCasEtConflitSansPerte();
    void editionPendantSauvegardeResteBrouillon();
    void aucuneReussiteAvantLeBridgeEtPasDePostRejoue();
    void archiveConfirmeeConserveUneFrappeTardive();
    void renommageProtegeLesBrouillonsLocaux();
    void reponseIncoherenteEtOubliEnVol();
    void notes128KioEtCorpsSuperieur64Kio();
    void codeEphemereEtEmpreinteConfirmee();
};
void TestObsidian::cheminsEtEmpreintesBornes()
{
    QVERIFY(ObsidianViewModel::cheminValide(QStringLiteral("Projets/Note été.md")));
    for (const QString &p:{QStringLiteral("../secret.md"),QStringLiteral("/secret.md"),QStringLiteral("C:/secret.md"),
        QStringLiteral("Notes\\secret.md"),QStringLiteral(".obsidian/note.md"),QStringLiteral("A//B.md"),
        QStringLiteral("CON.md"),QStringLiteral("A/aux.txt.md"),QStringLiteral("note.md:secret"),QStringLiteral("note.txt")})
        QVERIFY2(!ObsidianViewModel::cheminValide(p),qPrintable(p));
    QVERIFY(ObsidianViewModel::empreinteValide(QString(64,QLatin1Char('a'))));
    QVERIFY(!ObsidianViewModel::empreinteValide(QString(63,QLatin1Char('a'))));
    QVERIFY(!ObsidianViewModel::empreinteValide(QString(64,QLatin1Char('g'))));
}
void TestObsidian::etatReelEtSessionRequise()
{
    Banc b; b.vue.setPageVisible(true); b.vue.actualiser(); QTest::qWait(80);
    QVERIFY(b.serveur.requetes.isEmpty()); QCOMPARE(b.vue.etat(),QStringLiteral("inconnu"));
    b.disque.etat=QStringLiteral("hors_ligne"); b.flux.demarrer(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("hors_ligne"));
    b.vue.lister(); QCOMPARE(b.disque.demandes.size(),0);
    b.disque.etat=QStringLiteral("pret"); b.vue.actualiser(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    QVERIFY(b.vue.lecture().startsWith(QStringLiteral("État lu à ")));
    const auto r=b.serveur.filtrer("GET",b.disque.prefixe).first();
    QCOMPARE(r.entete("authorization"),QByteArrayLiteral("Bearer jeton-a")); QVERIFY(!r.aEntete("origin")); QVERIFY(!r.aEntete("cookie"));
}
void TestObsidian::ancienServeurExpliqueLaMiseAJour()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.serveur.route("GET",b.disque.prefixe,[](const RequeteRecue &){
        return ReponseFaux::json(404,QJsonObject{{QStringLiteral("detail"),QStringLiteral("Not Found")}});
    });
    b.vue.actualiser(); QTRY_VERIFY(b.vue.erreur().contains(QStringLiteral("1.2.0")));
    QCOMPARE(b.vue.etat(),QStringLiteral("inconnu"));
    QVERIFY(!b.vue.etatLibelle().contains(QStringLiteral("hors ligne"),Qt::CaseInsensitive));
    b.vue.lister(); QCOMPARE(b.disque.demandes.size(),0);
    b.disque.installer(b.serveur); b.vue.actualiser(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.serveur.route("POST",b.disque.prefixe+QStringLiteral("/operations"),[](const RequeteRecue &){
        return ReponseFaux::json(404,QJsonObject{{QStringLiteral("detail"),QStringLiteral("Opération introuvable")}});
    });
    b.vue.lister(); QTRY_VERIFY(b.vue.erreur().contains(QStringLiteral("introuvable")));
    QVERIFY(!b.vue.erreur().contains(QStringLiteral("1.2.0"))); // Seulement le 404 de lecture du statut.
    b.vue.fermerSuivi(true);
}
void TestObsidian::refusCertainEtErreurIncertaine()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.vue.nouvelleNote(QStringLiteral("Refusee.md")); b.vue.setBrouillon(QStringLiteral("À conserver"));
    int statut=400;
    b.serveur.route("POST",b.disque.prefixe+QStringLiteral("/operations"),[&](const RequeteRecue &){
        return ReponseFaux::json(statut,QJsonObject{{QStringLiteral("detail"),QJsonObject{
            {QStringLiteral("code"),QStringLiteral("requete_refusee")},{QStringLiteral("message"),QStringLiteral("Refus explicite de la demande")}}}});
    });
    for (const int code : {400,403,413,415,422}) {
        statut=code; b.vue.sauvegarder(); QTRY_VERIFY(!b.vue.occupe());
        QVERIFY(b.vue.operation().contains(QStringLiteral("avant acceptation")));
        QCOMPARE(b.vue.erreur(),QStringLiteral("Refus explicite de la demande"));
        QCOMPARE(b.vue.brouillon(),QStringLiteral("À conserver")); QVERIFY(b.vue.nouvelle());
    }
    for (const int code : {409,500}) {
        statut=code; b.vue.sauvegarder();
        QTRY_VERIFY(b.vue.operation().contains(QStringLiteral("suivi conservé")));
        QVERIFY(b.vue.occupe()); QVERIFY(b.vue.nouvelle()); QCOMPARE(b.vue.brouillon(),QStringLiteral("À conserver"));
        b.vue.fermerSuivi(true); QVERIFY(!b.vue.occupe());
        b.vue.nouvelleNote(QStringLiteral("Refusee%1.md").arg(code)); b.vue.setBrouillon(QStringLiteral("À conserver"));
    }
    QCOMPARE(b.serveur.compter("POST",b.disque.prefixe+QStringLiteral("/operations")),7);
    QCOMPARE(b.disque.demandes.size(),0); // Aucun refus n'a simulé une acceptation du bridge.
}
void TestObsidian::listeRechercheEtLiensDuCoffre()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.vue.lister(); QTRY_COMPARE(b.vue.notes()->count(),2);
    b.vue.setRecherche(QStringLiteral("distante")); b.vue.chercher(); QTRY_COMPARE(b.vue.notes()->count(),1);
    QCOMPARE(b.vue.notes()->itemAt(0).value(QStringLiteral("chemin")).toString(),QStringLiteral("Projet.md"));
    b.vue.ouvrirNote(QStringLiteral("Projet.md")); QTRY_VERIFY(!b.vue.occupe());
    b.vue.lireBacklinks(); QTRY_COMPARE(b.vue.backlinks()->count(),1);
    b.vue.lireGraphe(); QTRY_VERIFY(!b.vue.graphe().isEmpty());
    QCOMPARE(b.vue.graphe().value(QStringLiteral("liens")).toList().size(),1);
    QCOMPARE(b.disque.demandes.last().value(QStringLiteral("action")).toString(),QStringLiteral("graphe"));
    for (const auto &d:b.disque.demandes) { QVERIFY(!QUuid(d.value(QStringLiteral("id_operation")).toString()).isNull()); QCOMPARE(d.value(QStringLiteral("coffre_id")).toString(),b.disque.id); }
}
void TestObsidian::brouillonsConservesEntreNotesEtPages()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.vue.ouvrirNote(QStringLiteral("Accueil.md")); QTRY_VERIFY(!b.vue.occupe()); b.vue.setBrouillon(QStringLiteral("Mon texte local"));
    b.vue.ouvrirNote(QStringLiteral("Projet.md")); QTRY_VERIFY(!b.vue.occupe());
    b.vue.ouvrirNote(QStringLiteral("Accueil.md")); QCOMPARE(b.vue.brouillon(),QStringLiteral("Mon texte local"));
    b.vue.setPageVisible(false); QTRY_VERIFY(!b.vue.actif());
    b.vue.setPageVisible(true); QTRY_VERIFY(b.vue.actif()); QTRY_VERIFY(!b.vue.occupe());
    QCOMPARE(b.vue.brouillon(),QStringLiteral("Mon texte local")); QVERIFY(b.vue.modifie());
}
void TestObsidian::sauvegardeCasEtConflitSansPerte()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    const QString ancien=b.disque.fichiers.value(QStringLiteral("Accueil.md"));
    b.vue.ouvrirNote(QStringLiteral("Accueil.md")); QTRY_VERIFY(!b.vue.occupe());
    b.vue.setBrouillon(QStringLiteral("Version locale")); b.disque.fichiers[QStringLiteral("Accueil.md")]=QStringLiteral("Version Obsidian plus récente");
    b.vue.sauvegarder(); QTRY_VERIFY(!b.vue.occupe()); QVERIFY(b.vue.conflit()); QCOMPARE(b.vue.brouillon(),QStringLiteral("Version locale"));
    const auto p=b.disque.demandes.last().value(QStringLiteral("parametres")).toObject();
    QCOMPARE(p.value(QStringLiteral("empreinte_attendue")).toString(),coffreEmpreinte(ancien));
    b.vue.relire(); QTRY_VERIFY(!b.vue.occupe()); QCOMPARE(b.vue.versionServeur(),QStringLiteral("Version Obsidian plus récente"));
    QCOMPARE(b.vue.brouillon(),QStringLiteral("Version locale"));
    b.vue.garderBrouillonSurVersionServeur(false); QVERIFY(b.vue.conflit());
    b.vue.garderBrouillonSurVersionServeur(true); QVERIFY(!b.vue.conflit()); QVERIFY(b.vue.modifie());
    b.vue.sauvegarder(); QTRY_VERIFY(!b.vue.occupe()); QCOMPARE(b.disque.fichiers.value(QStringLiteral("Accueil.md")),QStringLiteral("Version locale")); QVERIFY(!b.vue.modifie());
}
void TestObsidian::editionPendantSauvegardeResteBrouillon()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.vue.ouvrirNote(QStringLiteral("Accueil.md")); QTRY_VERIFY(!b.vue.occupe());
    b.vue.setBrouillon(QStringLiteral("Texte envoyé")); b.disque.attendre=true; b.vue.sauvegarder();
    QTRY_COMPARE(b.disque.demandes.size(),2); b.vue.setBrouillon(QStringLiteral("Frappe après envoi"));
    b.disque.terminer(b.disque.demandes.last().value(QStringLiteral("id_operation")).toString());
    QTRY_VERIFY_WITH_TIMEOUT(!b.vue.occupe(),5000);
    QCOMPARE(b.disque.fichiers.value(QStringLiteral("Accueil.md")),QStringLiteral("Texte envoyé"));
    QCOMPARE(b.vue.brouillon(),QStringLiteral("Frappe après envoi")); QVERIFY(b.vue.modifie());
}
void TestObsidian::aucuneReussiteAvantLeBridgeEtPasDePostRejoue()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.disque.attendre=true; b.vue.nouvelleNote(QStringLiteral("Neuve.md")); b.vue.setBrouillon(QStringLiteral("En attente")); b.vue.sauvegarder();
    QTRY_COMPARE(b.disque.demandes.size(),1); QVERIFY(b.vue.occupe()); QVERIFY(b.vue.nouvelle()); QVERIFY(!b.disque.fichiers.contains(QStringLiteral("Neuve.md")));
    b.vue.setPageVisible(false); QTRY_VERIFY(!b.vue.actif());
    b.disque.terminer(b.disque.demandes.last().value(QStringLiteral("id_operation")).toString());
    QTest::qWait(120); QVERIFY(b.vue.nouvelle());
    b.vue.setPageVisible(true); QTRY_VERIFY(!b.vue.occupe()); QVERIFY(!b.vue.nouvelle());
    QCOMPARE(b.serveur.compter("POST",b.disque.prefixe+QStringLiteral("/operations")),1);
}
void TestObsidian::archiveConfirmeeConserveUneFrappeTardive()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.vue.ouvrirNote(QStringLiteral("Accueil.md")); QTRY_VERIFY(!b.vue.occupe());
    b.vue.archiver(false); QCOMPARE(b.disque.demandes.size(),1);
    b.disque.attendre=true; b.vue.archiver(true); QTRY_COMPARE(b.disque.demandes.size(),2);
    b.vue.setBrouillon(QStringLiteral("À garder malgré archive"));
    b.disque.terminer(b.disque.demandes.last().value(QStringLiteral("id_operation")).toString());
    QTRY_VERIFY_WITH_TIMEOUT(!b.vue.occupe(),5000);
    QVERIFY(!b.disque.fichiers.contains(QStringLiteral("Accueil.md"))); QCOMPARE(b.vue.brouillon(),QStringLiteral("À garder malgré archive")); QVERIFY(b.vue.nouvelle());
}
void TestObsidian::renommageProtegeLesBrouillonsLocaux()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.vue.nouvelleNote(QStringLiteral("Destination.md")); b.vue.setBrouillon(QStringLiteral("Brouillon destination"));
    b.vue.ouvrirNote(QStringLiteral("Accueil.md")); QTRY_VERIFY(!b.vue.occupe());
    b.vue.renommer(QStringLiteral("Destination.md"),true); QCOMPARE(b.disque.demandes.size(),1);
    b.vue.renommer(QStringLiteral("Renommee.md"),false); QCOMPARE(b.disque.demandes.size(),1);
    b.vue.renommer(QStringLiteral("Renommee.md"),true); QTRY_VERIFY(!b.vue.occupe()); QCOMPARE(b.vue.chemin(),QStringLiteral("Renommee.md"));
    QVERIFY(b.disque.fichiers.contains(QStringLiteral("Renommee.md"))); QVERIFY(!b.disque.fichiers.contains(QStringLiteral("Accueil.md")));
    b.vue.ouvrirNote(QStringLiteral("Destination.md")); QCOMPARE(b.vue.brouillon(),QStringLiteral("Brouillon destination"));
}
void TestObsidian::reponseIncoherenteEtOubliEnVol()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.disque.attendre=true; b.vue.nouvelleNote(QStringLiteral("Neuve.md")); b.vue.setBrouillon(QStringLiteral("Brouillon sûr")); b.vue.sauvegarder();
    QTRY_COMPARE(b.disque.demandes.size(),1); const auto id=b.disque.demandes.last().value(QStringLiteral("id_operation")).toString();
    auto &op=b.disque.operations[id]; op.insert(QStringLiteral("coffre_id"),QStringLiteral("autre"));
    QTRY_VERIFY_WITH_TIMEOUT(b.vue.erreur().contains(QStringLiteral("incohérente")),5000);
    QVERIFY(b.vue.nouvelle()); QCOMPARE(b.vue.brouillon(),QStringLiteral("Brouillon sûr"));
    b.vue.fermerSuivi(true); QVERIFY(!b.vue.occupe()); QVERIFY(b.vue.conflit());
    b.flux.arreter(); b.vue.oublier(); QVERIFY(!b.vue.noteOuverte()); QVERIFY(b.vue.brouillon().isEmpty());
    b.disque.attendre=false; b.disque.delai=250; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.vue.ouvrirNote(QStringLiteral("Accueil.md")); QTRY_VERIFY(b.vue.occupe());
    b.flux.arreter(); b.vue.oublier(); QTest::qWait(400);
    QVERIFY(!b.vue.noteOuverte()); QVERIFY(b.vue.notes()->count()==0);
}
void TestObsidian::notes128KioEtCorpsSuperieur64Kio()
{
    Banc b; b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    b.vue.nouvelleNote(QStringLiteral("Grande.md")); b.vue.setBrouillon(QString(70000,QChar(0x00e9))); b.vue.sauvegarder();
    QCOMPARE(b.disque.demandes.size(),0); QVERIFY(b.vue.erreur().contains(QStringLiteral("128 Kio")));
    b.vue.setBrouillon(QString(70000,QLatin1Char('a'))); b.vue.sauvegarder(); QTRY_VERIFY(!b.vue.occupe());
    QCOMPARE(b.disque.fichiers.value(QStringLiteral("Grande.md")).size(),70000);
}
void TestObsidian::codeEphemereEtEmpreinteConfirmee()
{
    Banc b; b.disque.etat=QStringLiteral("non_configure"); b.ouvrir(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("non_configure"));
    QString copie; b.vue.setPressePapier([&](const QString &s){copie=s;return true;});
    b.vue.creerCode(); QTRY_VERIFY(!b.vue.codeEnrolement().isEmpty()); QVERIFY(b.vue.copierCode()); QCOMPARE(copie,QStringLiteral("acpce_")+QString(43,QLatin1Char('x')));
    QTRY_VERIFY_WITH_TIMEOUT(b.vue.codeEnrolement().isEmpty(),4000); QVERIFY(!b.vue.copierCode());
    b.disque.etat=QStringLiteral("a_confirmer"); b.vue.actualiser(); QTRY_COMPARE(b.vue.etat(),QStringLiteral("a_confirmer"));
    b.vue.confirmerEmpreinte(QStringLiteral("AUTRE")); QCOMPARE(b.serveur.compter("POST",b.disque.prefixe+QStringLiteral("/confirmer")),0);
    b.vue.confirmerEmpreinte(QStringLiteral("ABCD-1234")); QTRY_COMPARE(b.vue.etat(),QStringLiteral("pret"));
    const auto corps=b.serveur.filtrer("POST",b.disque.prefixe+QStringLiteral("/confirmer")).first().json();
    QCOMPARE(corps.value(QStringLiteral("coffre_id")).toString(),b.disque.id);
    b.vue.revoquer(false); QCOMPARE(b.serveur.compter("POST",b.disque.prefixe+QStringLiteral("/revoquer")),0);
    b.vue.revoquer(true); QTRY_COMPARE(b.vue.etat(),QStringLiteral("revoque"));
}
QTEST_MAIN(TestObsidian)
#include "tst_obsidian.moc"
