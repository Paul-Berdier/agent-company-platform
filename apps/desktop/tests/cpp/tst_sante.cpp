// État du lien avec Hermes : /api/health, /api/status, hors ligne et retour.

#include "api/ApiClient.h"
#include "services/HealthService.h"
#include "support/FauxHermes.h"

#include <QHostAddress>
#include <QJsonObject>
#include <QTcpServer>
#include <QTest>

using namespace acp;
using namespace acp::test;

class TestSante : public QObject
{
    Q_OBJECT

private slots:
    void enLigneAvecPasserelle();
    void statutIllisibleResteInconnu();
    void serveurQuiNEstPasHermesEstDegrade();
    void horsLignePuisRetour();
};

void TestSante::enLigneAvecPasserelle()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.route("GET", QStringLiteral("/api/status"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("version"), QStringLiteral("0.21.5")},
                                                  {QStringLiteral("gateway_running"), true},
                                                  {QStringLiteral("gateway_state"), QStringLiteral("running")},
                                                  {QStringLiteral("active_sessions"), 2}});
    });
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(serveur.url()).isError());
    HealthService sante(&client);
    QCOMPARE(sante.linkStatusLabel(), QStringLiteral("Inconnu"));
    QCOMPARE(sante.lastSuccessLabel(), QStringLiteral("Jamais"));
    QCOMPARE(sante.gatewayLabel(), QStringLiteral("Inconnu"));
    sante.probeNow();
    QTRY_COMPARE(sante.linkStatus(), LinkStatus::Online);
    QCOMPARE(sante.hermesVersion(), QStringLiteral("0.21.5"));
    QCOMPARE(sante.authRequired(), std::optional<bool>(true));
    QVERIFY(sante.lastSuccessAt().isValid());
    QTRY_COMPARE(sante.gatewayLabel(), QStringLiteral("En marche (running)"));
    QCOMPARE(sante.activeSessionsLabel(), QStringLiteral("2"));
    // Deux routes publiques : aucune session n'y est présentée.
    for (const RequeteRecue &requete : std::as_const(serveur.requetes)) {
        QVERIFY(!requete.aEntete("authorization"));
    }
}

void TestSante::statutIllisibleResteInconnu()
{
    FauxHermes serveur;
    serveur.installerAuthentification(); // aucune route /api/status : 404
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(serveur.url()).isError());
    HealthService sante(&client);
    sante.probeNow();
    QTRY_COMPARE(sante.linkStatus(), LinkStatus::Online);
    QTRY_COMPARE(serveur.compter("GET", QStringLiteral("/api/status")), 1);
    QTest::qWait(50);
    QCOMPARE(sante.gatewayLabel(), QStringLiteral("Inconnu"));
    QCOMPARE(sante.activeSessionsLabel(), QStringLiteral("Inconnu"));
}

void TestSante::serveurQuiNEstPasHermesEstDegrade()
{
    FauxHermes serveur; // aucune route : /api/health en 404
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(serveur.url()).isError());
    HealthService sante(&client);
    sante.probeNow();
    QTRY_COMPARE(sante.linkStatus(), LinkStatus::Degraded);
    QVERIFY(sante.detail().contains(QStringLiteral("/api/health")));
    QCOMPARE(sante.lastSuccessLabel(), QStringLiteral("Jamais"));

    FauxHermes pasOk;
    pasOk.route("GET", QStringLiteral("/api/health"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("ok"), false}});
    });
    QVERIFY(!client.setBaseUrl(pasOk.url()).isError());
    sante.probeNow();
    QTRY_COMPARE(sante.linkStatus(), LinkStatus::Degraded);
    QCOMPARE(sante.hermesVersion(), QStringLiteral("Inconnu"));
}

void TestSante::horsLignePuisRetour()
{
    // Un port de bouclage libéré : rien n'y écoute.
    quint16 portFerme = 0;
    {
        QTcpServer temporaire;
        QVERIFY(temporaire.listen(QHostAddress(QHostAddress::LocalHost), 0));
        portFerme = temporaire.serverPort();
    }
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:%1").arg(portFerme))).isError());
    HealthService sante(&client);
    sante.probeNow();
    QTRY_COMPARE_WITH_TIMEOUT(sante.linkStatus(), LinkStatus::Offline, 30000);
    QCOMPARE(sante.linkStatusLabel(), QStringLiteral("Hors ligne"));
    // Constat de relecture P8 : le détail montré à l'écran de connexion était le texte anglais
    // de Qt (« Connection refused »).
    QCOMPARE(sante.detail(), QStringLiteral("Serveur injoignable : connexion refusée : aucun service n'écoute à "
                                            "cette adresse (erreur réseau 1)"));
    QCOMPARE(sante.lastSuccessLabel(), QStringLiteral("Jamais"));

    FauxHermes serveur;
    serveur.installerAuthentification();
    QVERIFY(!client.setBaseUrl(serveur.url()).isError());
    QCOMPARE(sante.linkStatus(), LinkStatus::Unknown); // nouveau serveur : rien de supposé
    sante.probeNow();
    QTRY_COMPARE(sante.linkStatus(), LinkStatus::Online);
    QVERIFY(sante.lastSuccessLabel() != QStringLiteral("Jamais"));
}

QTEST_GUILESS_MAIN(TestSante)

#include "tst_sante.moc"
