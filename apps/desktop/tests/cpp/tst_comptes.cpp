#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "support/FauxHermes.h"
#include "support/FauxComptes.h"
#include "viewmodels/ComptesViewModel.h"
#include <QTest>
#include <QSignalSpy>
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
    QJsonObject claude;
    QJsonObject reception;
    int statutCode=202;
    int statut=200, delai=0, statutMutation=202;
    Banc() {
        serveur.installerAuthentification(); serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true); if(client.setBaseUrl(serveur.url()).isError()) qFatal("URL de test refusée");
        client.setBearerProvider([]{return QByteArrayLiteral("jeton-a");}); flux.setIntervalleFond(std::chrono::hours(1));
        serveur.route("GET",k,[this](const RequeteRecue &) { auto r=ReponseFaux::json(statut,document.isEmpty()?comptesTest(connexion,claude):document); r.delaiMs=delai; return r; });
        serveur.route("POST",k+QStringLiteral("/codex/connexions"),[this](const RequeteRecue &) {
            if(statutMutation!=202) return ReponseFaux::json(statutMutation,QJsonObject{{QStringLiteral("detail"),QJsonObject{{QStringLiteral("code"),QStringLiteral("temporaire")},{QStringLiteral("message"),QStringLiteral("Réessayez après vérification du serveur.")}}}});
            connexion=connexionTest(); auto r=ReponseFaux::json(202,connexion); r.delaiMs=delai; return r;
        });
        serveur.route("POST",k+QStringLiteral("/claude/connexions"),[this](const RequeteRecue &) {
            claude=connexionClaudeTest(); return ReponseFaux::json(202,claude);
        });
        serveur.route("POST",k+QStringLiteral("/connexions/")+connexionTestId()+QStringLiteral("/code"),[this](const RequeteRecue &req) {
            reception={{QStringLiteral("defi_id"),req.json().value(QStringLiteral("defi_id"))},
                {QStringLiteral("soumission_id"),req.json().value(QStringLiteral("soumission_id"))},{QStringLiteral("etat"),QStringLiteral("en_attente")}};
            auto vue=claude; vue.insert(QStringLiteral("reception_code"),reception);
            return ReponseFaux::json(statutCode,statutCode==202?vue:QJsonObject{{QStringLiteral("detail"),QStringLiteral("Corps sensible qui ne doit pas être affiché")}});
        });
        serveur.route("GET",k+QStringLiteral("/connexions/")+connexionTestId(),[this](const RequeteRecue &) {
            auto vue=claude.isEmpty()?connexion:claude;
            if (!claude.isEmpty() && !reception.isEmpty()) vue.insert(QStringLiteral("reception_code"),reception);
            return ReponseFaux::json(200,vue);
        });
        serveur.route("POST",k+QStringLiteral("/connexions/")+connexionTestId()+QStringLiteral("/annuler"),[this](const RequeteRecue &) { if (!claude.isEmpty()) { claude=connexionClaudeTest(QStringLiteral("annulee")); claude.insert(QStringLiteral("compte_connecte"),true); return ReponseFaux::json(200,claude); }
            connexion=connexionTest(QStringLiteral("annulee")); return ReponseFaux::json(200,connexion); });
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
    void claudeCodeTemporaireEtRecu();
    void claudeRepriseIncertaineSansRejeu();
    void claudeReouvertureEtAnnulationDistinctesDuCompte();
    void claudeLiensCodesEtDefisStricts();
    void uneSeuleProcedureEtAncienProtocoleRefuses();
    void defiPerduEtSuccesSansCompteRefuse();
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
void TestComptes::claudeCodeTemporaireEtRecu() {
    Banc b; b.ouvrir(); QTRY_VERIFY(b.comptes.peutConnecterClaude());
    QUrl ouvert; b.comptes.setOuvreur([&](const QUrl &url) {ouvert=url;return true;});
    b.comptes.connecterClaude(); b.comptes.connecterClaude(); QTRY_VERIFY(b.comptes.peutSaisirCode());
    QCOMPARE(b.serveur.compter("POST",k+QStringLiteral("/claude/connexions")),1);
    QVERIFY(!b.comptes.peutConnecter()); QVERIFY(b.comptes.ouvrirVerification());
    QCOMPARE(ouvert.host(),QStringLiteral("claude.com")); QVERIFY(ouvert.hasQuery());
    QVERIFY(!b.comptes.connexion().contains(QStringLiteral("url")));
    QVERIFY(!QJsonDocument::fromVariant(b.comptes.connexion()).toJson().contains("TEST-ETAT"));
    const QString code=QStringLiteral("TEST-CODE-OPAQUE#avec=ponctuation");
    QSignalSpy purge(&b.comptes,&ComptesViewModel::effacerCodeTemporaire);
    b.comptes.soumettreCode(code); QTRY_VERIFY(!b.comptes.gesteEnCours());
    const auto req=b.serveur.filtrer("POST",k+QStringLiteral("/connexions/")+connexionTestId()+QStringLiteral("/code")); QCOMPARE(req.size(),1);
    QCOMPARE(req.first().json().keys(),QStringList({QStringLiteral("code"),QStringLiteral("defi_id"),QStringLiteral("soumission_id")}));
    QCOMPARE(req.first().json().value(QStringLiteral("code")).toString(),code);
    QVERIFY(!req.first().aEntete("idempotency-key")); QVERIFY(req.first().aEntete("authorization")); QVERIFY(!req.first().aEntete("cookie"));
    QVERIFY(!req.first().requete.hasQueryItem(QStringLiteral("code"))); QVERIFY(purge.size()>0);
    QVERIFY(!b.comptes.peutSaisirCode()); QCOMPARE(b.comptes.connexion().value(QStringLiteral("etat")).toString(),QStringLiteral("code_disponible"));
    QVERIFY(!QJsonDocument::fromVariant(b.comptes.connexion()).toJson().contains(code.toUtf8()));
    QVERIFY(!b.comptes.comptes().at(1).toMap().value(QStringLiteral("modeles")).toList().size());
    QCOMPARE(b.comptes.comptes().at(1).toMap().value(QStringLiteral("aliasDocumentes")).toList().size(),1);
}
void TestComptes::claudeRepriseIncertaineSansRejeu() {
    Banc b; b.claude=connexionClaudeTest(); b.ouvrir(); QTRY_VERIFY(b.comptes.peutSaisirCode());
    b.statutCode=503; b.comptes.soumettreCode(QStringLiteral("CODE-SIMULE"));
    QTRY_COMPARE(b.comptes.connexion().value(QStringLiteral("receptionCodeEtat")).toString(),QStringLiteral("en_attente"));
    QVERIFY(!b.comptes.peutSaisirCode()); QVERIFY(b.comptes.erreurGeste().isEmpty());
    const QString chemin=k+QStringLiteral("/connexions/")+connexionTestId()+QStringLiteral("/code");
    QCOMPARE(b.serveur.compter("POST",chemin),1);
    const auto premier=b.serveur.filtrer("POST",chemin).first().json();
    const auto suivi=b.serveur.filtrer("GET",k+QStringLiteral("/connexions/")+connexionTestId()).last();
    QCOMPARE(suivi.requete.queryItemValue(QStringLiteral("defi_id")),defiTestId());
    QCOMPARE(suivi.requete.queryItemValue(QStringLiteral("soumission_id")),premier.value(QStringLiteral("soumission_id")).toString());
    b.reception.insert(QStringLiteral("etat"),QStringLiteral("perdu")); b.comptes.actualiser();
    QTRY_COMPARE(b.comptes.connexion().value(QStringLiteral("receptionCodeEtat")).toString(),QStringLiteral("perdu")); QVERIFY(!b.comptes.peutSaisirCode());
    b.reception.insert(QStringLiteral("etat"),QStringLiteral("non_recue")); b.comptes.actualiser(); QTRY_VERIFY(b.comptes.peutSaisirCode());
    QCOMPARE(b.serveur.compter("POST",chemin),1); // Aucun envoi pendant les lectures.
    b.statutCode=202; b.comptes.soumettreCode(QStringLiteral("CODE-SIMULE")); QTRY_COMPARE(b.serveur.compter("POST",chemin),2);
    QCOMPARE(b.serveur.filtrer("POST",chemin).last().json(),premier);
    QTRY_VERIFY(!b.comptes.gesteEnCours());
    b.reception.insert(QStringLiteral("etat"),QStringLiteral("non_recue")); b.comptes.actualiser(); QTRY_VERIFY(b.comptes.peutSaisirCode());
}
void TestComptes::claudeReouvertureEtAnnulationDistinctesDuCompte() {
    Banc b; b.claude=connexionClaudeTest();
    b.reception={{QStringLiteral("defi_id"),defiTestId()},{QStringLiteral("soumission_id"),QStringLiteral("a41e9599-bc00-4581-9f46-00e134668c30")},{QStringLiteral("etat"),QStringLiteral("transmis")}};
    b.claude.insert(QStringLiteral("reception_code"),b.reception); b.ouvrir(); QTRY_VERIFY(b.comptes.attente());
    QVERIFY(!b.comptes.peutSaisirCode());
    b.comptes.setPageVisible(false); b.comptes.setPageVisible(true); QTRY_VERIFY(!b.comptes.chargement());
    QCOMPARE(b.serveur.compter("POST",k+QStringLiteral("/claude/connexions")),0);
    b.comptes.annulerConnexion(); QTRY_COMPARE(b.comptes.connexion().value(QStringLiteral("etat")).toString(),QStringLiteral("annulee"));
    QVERIFY(!b.comptes.peutSaisirCode()); QVERIFY(!b.comptes.peutOuvrirVerification());
    b.comptes.actualiser(); QTRY_VERIFY(b.comptes.comptes().at(1).toMap().value(QStringLiteral("compteConnecte")).toBool());
    QCOMPARE(b.comptes.connexion().value(QStringLiteral("libelle")).toString(),QStringLiteral("Connexion annulée"));
}
void TestComptes::claudeLiensCodesEtDefisStricts() {
    const QString moteur=QStringLiteral("claude_code");
    QVERIFY(ComptesViewModel::urlVerificationAdmise(QUrl(QStringLiteral("https://claude.com/cai/oauth/authorize?state=simule")),moteur));
    for (const auto &url:QStringList{QStringLiteral("http://claude.com/cai/oauth/authorize?a=b"),QStringLiteral("https://claude.com.evil.example/cai/oauth/authorize?a=b"),QStringLiteral("https://user@claude.com/cai/oauth/authorize?a=b"),QStringLiteral("https://claude.com:444/cai/oauth/authorize?a=b"),QStringLiteral("https://claude.com/cai/oauth/authorize"),QStringLiteral("https://claude.ai/oauth/authorize?a=b"),QStringLiteral("https://claude.com/cai/oauth/authorize?a=b#fragment"),QStringLiteral("https://claude.com/cai%2Foauth/authorize?a=b")})
        QVERIFY(!ComptesViewModel::urlVerificationAdmise(QUrl(url),moteur));
    QVERIFY(ClientGreffonPoste::codeConnexionValide(QString(2048,QLatin1Char('x'))));
    QVERIFY(!ClientGreffonPoste::codeConnexionValide(QString(1025,QChar(0xe9))));
    for (const auto &code:QStringList{QString(),QStringLiteral("code\n"),QStringLiteral("code\r"),QStringLiteral("code\t"),QString(QChar(0)),QString(QChar(127)),QString(2049,QLatin1Char('x'))})
        QVERIFY(!ClientGreffonPoste::codeConnexionValide(code));
    Banc b; b.claude=connexionClaudeTest(); b.ouvrir(); QTRY_VERIFY(b.comptes.peutSaisirCode());
    b.claude.insert(QStringLiteral("defi_type"),QStringLiteral("codex_device")); b.comptes.actualiser(); QTRY_VERIFY(!b.comptes.erreur().isEmpty());
    QVERIFY(!b.comptes.peutSaisirCode()); QVERIFY(!b.comptes.ouvrirVerification());
}
void TestComptes::uneSeuleProcedureEtAncienProtocoleRefuses() {
    Banc b; b.document=comptesTest(connexionTest(),connexionClaudeTest()); b.ouvrir(); QTRY_VERIFY(!b.comptes.erreur().isEmpty()); QVERIFY(!b.comptes.peutConnecterClaude());
    b.document=comptesTest(); b.document.insert(QStringLiteral("protocole"),QStringLiteral("acp-comptes/1")); b.comptes.actualiser();
    QTRY_VERIFY(b.comptes.erreur().contains(QStringLiteral("Mettez ACP à jour"))); QVERIFY(!b.comptes.peutConnecter());
}
void TestComptes::defiPerduEtSuccesSansCompteRefuse() {
    Banc b; b.claude=connexionClaudeTest();
    for (const auto &cle:QStringList{QStringLiteral("defi_id"),QStringLiteral("defi_type"),QStringLiteral("verification_url")}) b.claude.insert(cle,QJsonValue::Null);
    b.ouvrir(); QTRY_VERIFY(b.comptes.lue()); QVERIFY(b.comptes.attente()); QVERIFY(b.comptes.erreur().isEmpty());
    QVERIFY(!b.comptes.peutSaisirCode()); QVERIFY(!b.comptes.peutOuvrirVerification());
    b.claude=connexionClaudeTest(QStringLiteral("connecte")); b.claude.insert(QStringLiteral("compte_connecte"),false);
    b.comptes.actualiser(); QTRY_VERIFY(!b.comptes.erreur().isEmpty());
    QVERIFY(b.comptes.connexion().value(QStringLiteral("etat"))!=QStringLiteral("connecte"));
}
QTEST_GUILESS_MAIN(TestComptes)
#include "tst_comptes.moc"
