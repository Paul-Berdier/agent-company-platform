// Lecture des contrôles de disponibilité rendus par `/ready`.
//
// Le défaut corrigé : la station lisait `status` et `detail` quand le serveur publie
// `ok` et `reason`. L'écran de diagnostics affichait alors cinq noms de contrôle sans
// verdict ni raison. La référence est un corps réellement servi par l'API, capturé dans
// tests/fixtures/ready-document.json et gardé aligné par la suite Python.

#include "services/HealthService.h"

#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTest>

using namespace acp;

class TestReadiness : public QObject
{
    Q_OBJECT

private slots:
    void readsTheChecksServedByTheApi();
    void failedCheckKeepsTheServerReason();
    void checkWithoutVerdictIsUnknownNotHealthy();
    void bodyWithoutChecksYieldsNoRow();

private:
    static QJsonObject servedDocument();
    static const ReadinessModel::Check *find(const QList<ReadinessModel::Check> &checks,
                                             const QString &name);
};

QJsonObject TestReadiness::servedDocument()
{
    QFile file(QStringLiteral(ACP_TEST_FIXTURE_DIR "/ready-document.json"));
    if (!file.open(QIODevice::ReadOnly)) {
        qFatal("Document /ready de référence introuvable : %s", qPrintable(file.fileName()));
    }
    return QJsonDocument::fromJson(file.readAll()).object();
}

const ReadinessModel::Check *TestReadiness::find(const QList<ReadinessModel::Check> &checks,
                                                 const QString &name)
{
    for (const ReadinessModel::Check &check : checks) {
        if (check.name == name) {
            return &check;
        }
    }
    return nullptr;
}

void TestReadiness::readsTheChecksServedByTheApi()
{
    const QList<ReadinessModel::Check> checks = ReadinessModel::parseChecks(servedDocument());
    QCOMPARE(checks.size(), 5);
    const ReadinessModel::Check *database = find(checks, QStringLiteral("database"));
    QVERIFY(database != nullptr);
    QVERIFY(database->healthy);
    QCOMPARE(database->status, QStringLiteral("Sain"));
    QCOMPARE(database->detail, QStringLiteral("base joignable"));
}

void TestReadiness::failedCheckKeepsTheServerReason()
{
    QJsonObject document = servedDocument();
    QJsonObject checks = document.value(QStringLiteral("checks")).toObject();
    QJsonObject database = checks.value(QStringLiteral("database")).toObject();
    database.insert(QStringLiteral("ok"), false);
    database.insert(QStringLiteral("reason"), QStringLiteral("base injoignable"));
    checks.insert(QStringLiteral("database"), database);
    document.insert(QStringLiteral("checks"), checks);

    const QList<ReadinessModel::Check> parsed = ReadinessModel::parseChecks(document);
    const ReadinessModel::Check *check = find(parsed, QStringLiteral("database"));
    QVERIFY(check != nullptr);
    QVERIFY(!check->healthy);
    QCOMPARE(check->status, QStringLiteral("En échec"));
    QCOMPARE(check->detail, QStringLiteral("base injoignable"));
}

void TestReadiness::checkWithoutVerdictIsUnknownNotHealthy()
{
    QJsonObject entry;
    entry.insert(QStringLiteral("reason"), QStringLiteral("sans verdict"));
    QJsonObject checks;
    checks.insert(QStringLiteral("mystere"), entry);
    QJsonObject document;
    document.insert(QStringLiteral("checks"), checks);

    const QList<ReadinessModel::Check> parsed = ReadinessModel::parseChecks(document);
    QCOMPARE(parsed.size(), 1);
    QVERIFY(!parsed.first().healthy);
    QCOMPARE(parsed.first().status, QStringLiteral("Inconnu"));
}

void TestReadiness::bodyWithoutChecksYieldsNoRow()
{
    QJsonObject document;
    document.insert(QStringLiteral("status"), QStringLiteral("ready"));
    // Aucune ligne n'est fabriquée pour remplir l'écran.
    QVERIFY(ReadinessModel::parseChecks(document).isEmpty());
}

QTEST_MAIN(TestReadiness)

#include "tst_readiness.moc"
