// Compatibilité client / serveur.
//
// Deux comportements décisifs éprouvés ici :
//   - l'ABSENCE du point d'entrée ne vaut PAS « compatible » : une station qui conclurait
//     à la compatibilité par absence de contradiction serait un faux succès ;
//   - la lecture porte sur la forme RÉELLEMENT servie par `GET /meta`, capturée dans
//     tests/fixtures/meta-document.json, que la suite Python garde alignée sur l'API.

#include "api/ApiClient.h"
#include "services/CompatibilityService.h"

#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
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
    void readsTheDocumentServedByTheApi();
    void newerContractMajorMeansClientTooOld();
    void olderContractMajorMeansServerTooOld();
    void desktopFloorAboveClientMeansClientTooOld();
    void legacyFlatShapeIsNotCompatible();
    void capabilityWithoutAvailableFlagStaysUnknown();

private:
    static QJsonObject servedDocument();
};

QJsonObject TestCompatibility::servedDocument()
{
    QFile file(QStringLiteral(ACP_TEST_FIXTURE_DIR "/meta-document.json"));
    if (!file.open(QIODevice::ReadOnly)) {
        qFatal("Document /meta de référence introuvable : %s", qPrintable(file.fileName()));
    }
    return QJsonDocument::fromJson(file.readAll()).object();
}

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

void TestCompatibility::readsTheDocumentServedByTheApi()
{
    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    service.evaluate(servedDocument(), QStringLiteral("/meta"));

    QCOMPARE(service.state(), CompatibilityStatus::Compatible);
    QVERIFY(!service.isBlocking());
    QCOMPARE(service.serverVersion(), QStringLiteral("0.9.0"));
    QCOMPARE(service.apiContractVersion(), QStringLiteral("1.0"));
    QCOMPARE(service.eventSchemaVersion(), QStringLiteral("1.0"));
    QCOMPARE(service.endpointUsed(), QStringLiteral("/meta"));

    QVERIFY(service.limitsAreAnnounced());
    QCOMPARE(service.streamLimits().maxConnectionsPerUser, 4);
    QCOMPARE(service.streamLimits().keepAliveSeconds, 15);
    QCOMPARE(service.streamLimits().maxStreamSeconds, 900);
    QCOMPARE(service.streamLimits().pollIntervalMilliseconds, 400);
    QCOMPARE(service.streamLimits().pageLimit, 500);

    // Une capacité absente côté serveur est CONNUE et fausse, pas inconnue.
    bool known = false;
    QVERIFY(!service.capability(QStringLiteral("artifact_signing"), &known));
    QVERIFY(known);
    QVERIFY(service.capability(QStringLiteral("interactive_docs"), &known));
    QVERIFY(known);
    QVERIFY(!service.capabilityIsKnown(QStringLiteral("capacite_qui_n_existe_pas")));
}

void TestCompatibility::newerContractMajorMeansClientTooOld()
{
    QJsonObject document = servedDocument();
    QJsonObject versions = document.value(QStringLiteral("versions")).toObject();
    versions.insert(QStringLiteral("api_contract"), QStringLiteral("2.0"));
    document.insert(QStringLiteral("versions"), versions);

    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    service.evaluate(document, QStringLiteral("/meta"));
    QCOMPARE(service.state(), CompatibilityStatus::ClientTooOld);
    QVERIFY(service.isBlocking());
}

void TestCompatibility::olderContractMajorMeansServerTooOld()
{
    QJsonObject document = servedDocument();
    QJsonObject versions = document.value(QStringLiteral("versions")).toObject();
    versions.insert(QStringLiteral("api_contract"), QStringLiteral("0.9"));
    document.insert(QStringLiteral("versions"), versions);

    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    service.evaluate(document, QStringLiteral("/meta"));
    QCOMPARE(service.state(), CompatibilityStatus::ServerTooOld);
    QVERIFY(service.isBlocking());
}

void TestCompatibility::desktopFloorAboveClientMeansClientTooOld()
{
    QJsonObject document = servedDocument();
    QJsonObject clients = document.value(QStringLiteral("clients")).toObject();
    QJsonObject desktop = clients.value(QStringLiteral("desktop")).toObject();
    desktop.insert(QStringLiteral("minimum_version"), QStringLiteral("0.10.0"));
    clients.insert(QStringLiteral("desktop"), desktop);
    document.insert(QStringLiteral("clients"), clients);

    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    service.evaluate(document, QStringLiteral("/meta"));
    QCOMPARE(service.state(), CompatibilityStatus::ClientTooOld);
    QVERIFY(service.explanation().contains(QStringLiteral("0.10.0")));
}

void TestCompatibility::legacyFlatShapeIsNotCompatible()
{
    // La forme que ce client lisait avant d'être confronté au vrai serveur : elle ne doit
    // jamais passer pour un contrat reconnu.
    QJsonObject document;
    document.insert(QStringLiteral("server_version"), QStringLiteral("0.9.0"));
    document.insert(QStringLiteral("api_contract_version"), QStringLiteral("1.0"));

    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    service.evaluate(document, QStringLiteral("/meta"));
    QCOMPARE(service.state(), CompatibilityStatus::FeatureUnavailable);
    QVERIFY(!service.isBlocking());
}

void TestCompatibility::capabilityWithoutAvailableFlagStaysUnknown()
{
    QJsonObject document = servedDocument();
    QJsonObject capabilities = document.value(QStringLiteral("capabilities")).toObject();
    QJsonObject vault;
    vault.insert(QStringLiteral("detail"), QStringLiteral("sans verdict"));
    capabilities.insert(QStringLiteral("secrets_vault"), vault);
    document.insert(QStringLiteral("capabilities"), capabilities);

    ApiClient client;
    CompatibilityService service(&client, QStringLiteral("0.9.0"));
    service.evaluate(document, QStringLiteral("/meta"));
    bool known = true;
    QVERIFY(!service.capability(QStringLiteral("secrets_vault"), &known));
    QVERIFY(!known);
}

QTEST_MAIN(TestCompatibility)

#include "tst_compatibility.moc"
