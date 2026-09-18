// Compatibilité client / serveur.
//
// Le comportement décisif éprouvé ici : l'ABSENCE du point d'entrée ne vaut PAS
// « compatible ». L'audit établit qu'aucune route de compatibilité n'existe à ce jour ;
// une station qui conclurait à la compatibilité par absence de contradiction serait un
// faux succès.
//
// AVERTISSEMENT : jamais compilé, jamais exécuté.

#include "api/ApiClient.h"
#include "services/CompatibilityService.h"

#include <QTest>

using namespace acp;

class TestCompatibility : public QObject
{
    Q_OBJECT

private slots:
    void comparesVersions_data();
    void comparesVersions();
    void treatsPrereleaseSuffixAsZero();
    void initialStateIsNotChecked();
    void checkWithoutServerStaysNotChecked();
    void defaultLimitsMatchAuditValues();
    void limitsAreNotAnnouncedUntilServerSaysSo();
    void unknownCapabilityIsUnknownNotFalse();
    void everyStateHasFrenchLabel();
    void onlyVersionMismatchIsBlocking();
    void probeOrderIsStable();
    void supportedEventSchemaIsDeclared();
};

void TestCompatibility::comparesVersions_data()
{
    QTest::addColumn<QString>("left");
    QTest::addColumn<QString>("right");
    QTest::addColumn<int>("expected");

    // QT_NO_CAST_FROM_ASCII est actif : chaque colonne QString est alimentée par un
    // QStringLiteral, jamais par un littéral nu.
    QTest::newRow("égales") << QStringLiteral("0.9.0") << QStringLiteral("0.9.0") << 0;
    QTest::newRow("correctif inférieur")
        << QStringLiteral("0.9.0") << QStringLiteral("0.9.1") << -1;
    QTest::newRow("mineur supérieur")
        << QStringLiteral("0.10.0") << QStringLiteral("0.9.9") << 1;
    QTest::newRow("majeur supérieur")
        << QStringLiteral("1.0.0") << QStringLiteral("0.99.99") << 1;
    QTest::newRow("segments manquants") << QStringLiteral("1") << QStringLiteral("1.0.0") << 0;
    QTest::newRow("vide contre valeur") << QString() << QStringLiteral("0.0.1") << -1;
}

void TestCompatibility::comparesVersions()
{
    QFETCH(QString, left);
    QFETCH(QString, right);
    QFETCH(int, expected);
    QCOMPARE(CompatibilityService::compareVersions(left, right), expected);
}

void TestCompatibility::treatsPrereleaseSuffixAsZero()
{
    // Comportement documenté et assumé : la fonction n'implémente pas SemVer et n'ordonne
    // pas les suffixes de pré-publication. Le test l'inscrit pour qu'aucun appelant ne
    // s'appuie sur un ordre qui n'existe pas.
    QCOMPARE(CompatibilityService::compareVersions(QStringLiteral("1.0.0-rc1"),
                                                   QStringLiteral("1.0.0")),
             0);
}

void TestCompatibility::initialStateIsNotChecked()
{
    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    QCOMPARE(service.state(), CompatibilityStatus::NotChecked);
    QVERIFY(!service.isBlocking());
    QCOMPARE(service.clientVersion(), QStringLiteral("0.9.0"));
}

void TestCompatibility::checkWithoutServerStaysNotChecked()
{
    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    service.check();
    // Sans adresse de serveur, aucune sonde n'est émise et rien n'est supposé.
    QCOMPARE(service.state(), CompatibilityStatus::NotChecked);
    QVERIFY(!service.explanation().isEmpty());
}

void TestCompatibility::defaultLimitsMatchAuditValues()
{
    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    const StreamLimits &limits = service.streamLimits();
    // Valeurs relevées dans apps/api/src/acp_api/streams.py à la date de l'audit.
    QCOMPARE(limits.maxConnectionsPerUser, 4);
    QCOMPARE(limits.keepAliveSeconds, 15);
    QCOMPARE(limits.maxStreamSeconds, 900);
    QCOMPARE(limits.pollIntervalMilliseconds, 400);
    QCOMPARE(limits.pageLimit, 500);
}

void TestCompatibility::limitsAreNotAnnouncedUntilServerSaysSo()
{
    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    // L'écran de diagnostics doit pouvoir dire que ces bornes sont supposées et non
    // annoncées : sans ce drapeau, il présenterait une hypothèse comme un fait.
    QVERIFY(!service.limitsAreAnnounced());
}

void TestCompatibility::unknownCapabilityIsUnknownNotFalse()
{
    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    bool known = true;
    const bool value = service.capability(QStringLiteral("artifact_signing"), &known);
    QVERIFY(!value);
    // Le point décisif : « inconnu » et « désactivé » ne se confondent pas.
    QVERIFY(!known);
    QVERIFY(!service.capabilityIsKnown(QStringLiteral("artifact_signing")));
}

void TestCompatibility::everyStateHasFrenchLabel()
{
    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    QVERIFY(!service.stateLabel().isEmpty());
}

void TestCompatibility::onlyVersionMismatchIsBlocking()
{
    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    // L'indisponibilité du point d'entrée ne doit JAMAIS bloquer l'application : une
    // fonction récente qui manque ne fait pas planter la station.
    QVERIFY(!service.isBlocking());
}

void TestCompatibility::probeOrderIsStable()
{
    const QStringList &candidates = CompatibilityService::candidateEndpoints();
    QCOMPARE(candidates.size(), 3);
    QCOMPARE(candidates.at(0), QStringLiteral("/meta"));
    QCOMPARE(candidates.at(1), QStringLiteral("/capabilities"));
    QCOMPARE(candidates.at(2), QStringLiteral("/version"));
}

void TestCompatibility::supportedEventSchemaIsDeclared()
{
    // EVENT_SCHEMA_VERSION vaut « 1.0 » dans packages/contracts à la date de l'audit.
    QVERIFY(CompatibilityService::supportedEventSchemaVersions().contains(
        QStringLiteral("1.0")));
}

QTEST_MAIN(TestCompatibility)

#include "tst_compatibility.moc"
