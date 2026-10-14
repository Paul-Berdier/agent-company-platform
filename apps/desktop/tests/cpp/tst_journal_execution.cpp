#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "support/FauxHermes.h"
#include "viewmodels/JournalExecutionViewModel.h"
#include <QTest>
#include <QSignalSpy>
using namespace acp;
using namespace acp::test;
namespace {
const QString route=QStringLiteral("/api/plugins/acp-poste/v1/projets/projet-test/evenements");
QJsonObject evenementSimule(int n) { return {{QStringLiteral("id"),QStringLiteral("event-%1").arg(n)},
    {QStringLiteral("curseur"),n},{QStringLiteral("projet_id"),QStringLiteral("projet-test")},
    {QStringLiteral("run_id"),42},{QStringLiteral("genre"),QStringLiteral("message")},{QStringLiteral("texte"),QStringLiteral("Événement simulé %1").arg(n)}}; }
QJsonObject page(QJsonArray ev,int curseur,bool encore=false) {return {{QStringLiteral("projet_id"),QStringLiteral("projet-test")},{QStringLiteral("evenements"),ev},{QStringLiteral("prochain_curseur"),curseur},{QStringLiteral("encore"),encore}};}
struct Banc {
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client,&greffon,nullptr};
    JournalExecutionViewModel journal{&greffon,&flux};
    QJsonObject document=page({},0);
    int statut=200,delai=0;
    Banc() {
        serveur.installerAuthentification(); serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true); if(client.setBaseUrl(serveur.url()).isError()) qFatal("URL de test refusée");
        client.setBearerProvider([] {return QByteArrayLiteral("jeton-a");}); flux.setIntervalleFond(std::chrono::hours(1));
        journal.setIntervalleTest(60000);
        serveur.route("GET",route,[this](const RequeteRecue &) {auto r=ReponseFaux::json(statut,document);r.delaiMs=delai;return r;});
    }
    void ouvrir() {flux.demarrer();journal.choisirProjet(QStringLiteral("projet-test"));journal.setPageVisible(true);}
};
}
class TestJournalExecution:public QObject {
    Q_OBJECT
private slots:
    void reprendAuCurseurSansMutation();
    void paginationEtDeduplication();
    void erreurEtSchemaConserventCurseur();
    void changementEtOubliIgnorentReponseTardive();
    void bornesEtBlocageSansRequete();
};
void TestJournalExecution::reprendAuCurseurSansMutation() {
    Banc b;b.document=page({evenementSimule(1)},1);b.ouvrir();QTRY_COMPARE(b.journal.curseur(),1);
    b.journal.setPageVisible(false); const auto avant=b.serveur.compter("GET",route);
    b.document=page({evenementSimule(2)},2); QTest::qWait(60);QCOMPARE(b.serveur.compter("GET",route),avant);
    b.journal.setPageVisible(true); QTRY_COMPARE(b.journal.curseur(),2);QCOMPARE(b.journal.evenements()->count(),2);
    QCOMPARE(b.journal.evenements()->itemAt(0).value(QStringLiteral("run_id")).toString(),QStringLiteral("42"));
    const auto req=b.serveur.filtrer("GET",route);
    QCOMPARE(req.first().requete.queryItemValue(QStringLiteral("apres")),QStringLiteral("0"));
    QCOMPARE(req.last().requete.queryItemValue(QStringLiteral("apres")),QStringLiteral("1"));
    QCOMPARE(req.last().requete.queryItemValue(QStringLiteral("limite")),QStringLiteral("100"));
    QVERIFY(req.last().aEntete("authorization")); QVERIFY(!req.last().aEntete("cookie"));
    for(const auto &r:b.serveur.requetes) QVERIFY(r.methode!=QByteArrayLiteral("POST"));
}
void TestJournalExecution::paginationEtDeduplication() {
    Banc b;
    b.serveur.route("GET",route,[](const RequeteRecue &r){
        const auto apres=r.requete.queryItemValue(QStringLiteral("apres")).toInt();
        return ReponseFaux::json(200,apres==0?page({evenementSimule(1)},1,true):page({evenementSimule(1),evenementSimule(2),evenementSimule(2)},2));
    });
    b.ouvrir();QTRY_COMPARE(b.journal.curseur(),2);QCOMPARE(b.journal.evenements()->count(),2);
    QCOMPARE(b.serveur.compter("GET",route),2);
    b.journal.actualiser();QTRY_VERIFY(!b.journal.chargement());QCOMPARE(b.journal.evenements()->count(),2);
}
void TestJournalExecution::erreurEtSchemaConserventCurseur() {
    Banc b;b.document=page({evenementSimule(1)},1);b.ouvrir();QTRY_COMPARE(b.journal.curseur(),1);
    b.document=page({evenementSimule(2)},1,true);b.journal.actualiser();QTRY_VERIFY(!b.journal.erreur().isEmpty());
    QCOMPARE(b.journal.curseur(),1);QCOMPARE(b.journal.evenements()->count(),1);
    b.statut=404;b.journal.actualiser();QTRY_VERIFY(b.journal.erreur().contains(QStringLiteral("pas disponible")));
    QCOMPARE(b.journal.curseur(),1);
    b.statut=200;b.document=page({},2);b.document.insert(QStringLiteral("projet_id"),QStringLiteral("autre"));
    b.journal.actualiser();QTRY_VERIFY(!b.journal.chargement());QCOMPARE(b.journal.curseur(),1);
    auto etranger=evenementSimule(2);etranger.insert(QStringLiteral("projet_id"),QStringLiteral("autre"));
    b.statut=200;b.document=page({etranger},2);b.journal.actualiser();QTRY_VERIFY(!b.journal.chargement());
    QCOMPARE(b.journal.curseur(),1);QCOMPARE(b.journal.evenements()->count(),1);
}
void TestJournalExecution::changementEtOubliIgnorentReponseTardive() {
    Banc b;b.delai=150;b.document=page({evenementSimule(1)},1);b.ouvrir();QTRY_COMPARE(b.serveur.compter("GET",route),1);
    b.journal.choisirProjet(QStringLiteral("autre-projet"));QTest::qWait(220);
    QCOMPARE(b.journal.evenements()->count(),0);QCOMPARE(b.journal.curseur(),0);
    b.journal.choisirProjet(QStringLiteral("projet-test"));QTRY_COMPARE(b.serveur.compter("GET",route),2);
    b.journal.oublier();QTest::qWait(220);QVERIFY(b.journal.projet().isEmpty());QCOMPARE(b.journal.evenements()->count(),0);
}
void TestJournalExecution::bornesEtBlocageSansRequete() {
    Banc b;
    auto *a=b.greffon.evenementsProjet(QStringLiteral("../autre"),0);QSignalSpy refuse(a,&ApiCall::failed);QTRY_COMPARE(refuse.count(),1);
    auto *c=b.greffon.evenementsProjet(QStringLiteral("projet-test"),-1);QSignalSpy borne(c,&ApiCall::failed);QTRY_COMPARE(borne.count(),1);
    b.greffon.bloquer(QStringLiteral("Greffon incompatible"));b.ouvrir();QTRY_VERIFY(!b.journal.erreur().isEmpty());
    QCOMPARE(b.serveur.compter("GET",route),0);
}
QTEST_GUILESS_MAIN(TestJournalExecution)
#include "tst_journal_execution.moc"
