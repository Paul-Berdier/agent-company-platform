#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "support/FauxHermes.h"
#include "support/FauxComptes.h"
#include "viewmodels/ComptesViewModel.h"
#include <QTest>
using namespace acp;
using namespace acp::test;
namespace {
const QString k=QStringLiteral("/api/plugins/acp-poste/v1/comptes");
struct Banc {
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client,&greffon,nullptr};
    ComptesViewModel comptes{&greffon,&flux};
    QJsonObject connexion;
    QJsonObject document;
    int statut=200, delai=0, statutMutation=202;
    Banc() {
        serveur.installerAuthentification(); serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true); if(client.setBaseUrl(serveur.url()).isError()) qFatal("URL de test refusée");
        client.setBearerProvider([]{return QByteArrayLiteral("jeton-a");}); flux.setIntervalleFond(std::chrono::hours(1));
        serveur.route("GET",k,[this](const RequeteRecue &) { auto r=ReponseFaux::json(statut,document.isEmpty()?comptesTest(connexion):document); r.delaiMs=delai; return r; });
        serveur.route("POST",k+QStringLiteral("/codex/connexions"),[this](const RequeteRecue &) {
            if(statutMutation!=202) return ReponseFaux::json(statutMutation,QJsonObject{{QStringLiteral("detail"),QJsonObject{{QStringLiteral("code"),QStringLiteral("temporaire")},{QStringLiteral("message"),QStringLiteral("Réessayez après vérification du serveur.")}}}});
            connexion=connexionTest(); auto r=ReponseFaux::json(202,connexion); r.delaiMs=delai; return r;
        });
        serveur.route("GET",k+QStringLiteral("/connexions/")+connexionTestId(),[this](const RequeteRecue &) {return ReponseFaux::json(200,connexion);});
        serveur.route("POST",k+QStringLiteral("/connexions/")+connexionTestId()+QStringLiteral("/annuler"),[this](const RequeteRecue &) { connexion=connexionTest(QStringLiteral("annulee")); return ReponseFaux::json(200,connexion); });
    }
    void ouvrir() {flux.demarrer(); comptes.setPageVisible(true);}
};
}
class TestComptes : public QObject {
    Q_OBJECT
private slots:
    void etatsDistinguentCompteEtInference();
    void connexionCorpsExactEtNavigateurOfficiel();
    void reouvertureSuitSansAnnulerNiRelancer();
    void annulationExpliciteEtDefiEfface();
    void erreurConserveCleEtOubliIgnoreReponseTardive();
    void schemaEtAncienServeurRefuses();
    void liensEtIdentifiantsStricts();
    void observationPerimeeNeConfirmePasLesModeles();
};
void TestComptes::etatsDistinguentCompteEtInference() {
    Banc b; b.ouvrir(); QTRY_VERIFY(b.comptes.lue()); QCOMPARE(b.comptes.comptes().size(),3); QVERIFY(b.comptes.peutConnecter());
    QVERIFY(!b.comptes.comptes().first().toMap().value(QStringLiteral("inferenceVerifiee")).toBool());
    b.connexion=connexionTest(QStringLiteral("connecte")); b.comptes.actualiser();
    QTRY_COMPARE(b.comptes.comptes().first().toMap().value(QStringLiteral("libelle")).toString(),QStringLiteral("Compte connecté"));
    QVERIFY(!b.comptes.comptes().first().toMap().value(QStringLiteral("inferenceVerifiee")).toBool());
    QVERIFY(b.comptes.comptes().first().toMap().value(QStringLiteral("modeles")).toList().isEmpty());
    QVERIFY(b.comptes.connexion().value(QStringLiteral("code")).toString().isEmpty());
}
void TestComptes::connexionCorpsExactEtNavigateurOfficiel() {
    Banc b; b.ouvrir(); QTRY_VERIFY(b.comptes.peutConnecter());
    QUrl ouvert; b.comptes.setOuvreur([&ouvert](const QUrl &url) {ouvert=url;return true;});
    b.comptes.connecterCodex(); b.comptes.connecterCodex(); QTRY_VERIFY(b.comptes.attente());
    const auto requetes=b.serveur.filtrer("POST",k+QStringLiteral("/codex/connexions")); QCOMPARE(requetes.size(),1);
    QCOMPARE(requetes.first().json().keys(),QStringList{QStringLiteral("idempotency_key")});
    QVERIFY(ComptesViewModel::identifiantConnexionValide(requetes.first().json().value(QStringLiteral("idempotency_key")).toString()));
    QVERIFY(requetes.first().aEntete("authorization")); QVERIFY(!requetes.first().aEntete("cookie"));
    QVERIFY(b.comptes.ouvrirVerification()); QCOMPARE(ouvert,QUrl(QStringLiteral("https://auth.openai.com/codex/device")));
}
void TestComptes::reouvertureSuitSansAnnulerNiRelancer() {
    Banc b; b.connexion=connexionTest(); b.ouvrir(); QTRY_VERIFY(b.comptes.attente());
    b.comptes.setPageVisible(false); QTRY_VERIFY(!b.comptes.actif());
    QCOMPARE(b.serveur.compter("POST",k+QStringLiteral("/connexions/")+connexionTestId()+QStringLiteral("/annuler")),0);
    b.connexion=connexionTest(QStringLiteral("connecte")); b.comptes.setPageVisible(true);
    QTRY_COMPARE(b.comptes.connexion().value(QStringLiteral("etat")).toString(),QStringLiteral("connecte"));
    QCOMPARE(b.serveur.compter("POST",k+QStringLiteral("/codex/connexions")),0);
}
void TestComptes::annulationExpliciteEtDefiEfface() {
    Banc b; b.connexion=connexionTest(); b.ouvrir(); QTRY_VERIFY(b.comptes.attente());
    b.comptes.annulerConnexion(); QTRY_COMPARE(b.comptes.connexion().value(QStringLiteral("etat")).toString(),QStringLiteral("annulee"));
    QVERIFY(b.comptes.connexion().value(QStringLiteral("url")).toString().isEmpty());
    QVERIFY(b.comptes.connexion().value(QStringLiteral("code")).toString().isEmpty());
    const auto req=b.serveur.filtrer("POST",k+QStringLiteral("/connexions/")+connexionTestId()+QStringLiteral("/annuler"));
    QCOMPARE(req.size(),1); QVERIFY(req.first().json().isEmpty());
}
void TestComptes::erreurConserveCleEtOubliIgnoreReponseTardive() {
    Banc b; b.ouvrir(); QTRY_VERIFY(b.comptes.peutConnecter()); b.statutMutation=409;
    b.comptes.connecterCodex(); QTRY_VERIFY(!b.comptes.erreurGeste().isEmpty());
    const auto premiere=b.serveur.filtrer("POST",k+QStringLiteral("/codex/connexions")).first().corps;
    b.statutMutation=202; b.delai=150; b.comptes.connecterCodex();
    QTRY_COMPARE(b.serveur.compter("POST",k+QStringLiteral("/codex/connexions")),2);
    QCOMPARE(b.serveur.filtrer("POST",k+QStringLiteral("/codex/connexions")).last().corps,premiere);
    b.comptes.oublier(); QTest::qWait(220); QVERIFY(!b.comptes.lue()); QVERIFY(b.comptes.connexion().isEmpty()); QVERIFY(!b.comptes.gesteEnCours());
}
void TestComptes::schemaEtAncienServeurRefuses() {
    Banc b; b.document={{QStringLiteral("protocole"),QStringLiteral("autre/1")}}; b.ouvrir(); QTRY_VERIFY(!b.comptes.erreur().isEmpty()); QVERIFY(!b.comptes.peutConnecter());
    b.statut=404; b.comptes.actualiser(); QTRY_VERIFY(b.comptes.erreur().contains(QStringLiteral("Mettez Hermes à jour")));
}
void TestComptes::liensEtIdentifiantsStricts() {
    QVERIFY(ComptesViewModel::urlVerificationAdmise(QUrl(QStringLiteral("https://auth.openai.com/codex/device"))));
    for(const auto &texte:QStringList{QStringLiteral("https://auth.openai.com.evil.example/codex/device"),QStringLiteral("http://auth.openai.com/codex/device"),QStringLiteral("https://user@auth.openai.com/codex/device"),QStringLiteral("https://auth.openai.com/autre"),QStringLiteral("https://auth.openai.com/codex/device?token=secret"),QStringLiteral("https://auth.openai.com/codex/device#secret")})
        QVERIFY(!ComptesViewModel::urlVerificationAdmise(QUrl(texte)));
    QVERIFY(!ComptesViewModel::identifiantConnexionValide(QStringLiteral("../codex")));
}
void TestComptes::observationPerimeeNeConfirmePasLesModeles() {
    Banc b;b.document=comptesTest();auto comptes=b.document.value(QStringLiteral("comptes")).toArray();auto c=comptes.first().toObject();
    c.insert(QStringLiteral("etat"),QStringLiteral("inconnu"));c.insert(QStringLiteral("compte_connecte"),QJsonValue::Null);
    c.insert(QStringLiteral("modeles"),QJsonArray{QJsonObject{{QStringLiteral("id"),QStringLiteral("modele-du-compte")}}});
    c.insert(QStringLiteral("observation"),QJsonObject{{QStringLiteral("etat"),QStringLiteral("perime")},{QStringLiteral("origine_modeles"),QStringLiteral("compte")}});
    comptes[0]=c;b.document.insert(QStringLiteral("comptes"),comptes);b.ouvrir();QTRY_VERIFY(b.comptes.lue());
    QVERIFY(b.comptes.comptes().first().toMap().value(QStringLiteral("modeles")).toList().isEmpty());
    QCOMPARE(b.comptes.comptes().first().toMap().value(QStringLiteral("libelle")).toString(),QStringLiteral("État du compte inconnu"));
    c.insert(QStringLiteral("compte_connecte"),true);
    c.insert(QStringLiteral("observation"),QJsonObject{{QStringLiteral("etat"),QStringLiteral("a_jour")},{QStringLiteral("origine_modeles"),QStringLiteral("compte")}});
    comptes[0]=c;b.document.insert(QStringLiteral("comptes"),comptes);b.comptes.actualiser();
    QTRY_COMPARE(b.comptes.comptes().first().toMap().value(QStringLiteral("modeles")).toList().size(),1);
}
QTEST_GUILESS_MAIN(TestComptes)
#include "tst_comptes.moc"
