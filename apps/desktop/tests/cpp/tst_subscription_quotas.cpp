// Quotas réels d'abonnement : lecture de GET /subscription-quotas par le propriétaire.
//
// Serveur HTTP local jetable, aucune base, aucun réseau externe. La forme nominale vient
// de fixtures/subscription-quotas.json, que la suite Python compare à la réponse réelle
// de l'API (apps/api/tests/test_subscription_quotas.py).
#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"
#include "models/JsonListModel.h"
#include "viewmodels/SubscriptionQuotasViewModel.h"

#include <QFile>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkCookie>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <QTimeZone>
#include <QTimer>

#include <functional>
#include <memory>

using namespace acp;
namespace {
struct Request {
    QByteArray method;
    QByteArray path;
    QByteArray headers;
};
struct Response {
    QByteArray body;
    int status = 200;
    int delayMs = 0;
};
class QuotaServer : public QObject
{
public:
    QTcpServer server;
    QList<Request> requests;
    std::function<Response(const Request &)> handler;
    QuotaServer()
    {
        connect(&server, &QTcpServer::newConnection, this, [this] {
            while (auto *socket = server.nextPendingConnection()) {
                const auto buffer = std::make_shared<QByteArray>();
                const auto answered = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, buffer, answered] {
                    buffer->append(socket->readAll());
                    const auto end = buffer->indexOf("\r\n\r\n");
                    if (*answered || end < 0) { return; }
                    *answered = true;
                    const auto headers = buffer->left(end);
                    const auto first = headers.split('\n').first().trimmed().split(' ');
                    const Request req{first.value(0), first.value(1), headers};
                    requests.append(req);
                    const auto reply = handler(req);
                    QTimer::singleShot(reply.delayMs, socket, [socket, reply] {
                        socket->write("HTTP/1.1 " + QByteArray::number(reply.status)
                            + " Result\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                            + QByteArray::number(reply.body.size()) + "\r\n\r\n" + reply.body);
                        socket->disconnectFromHost();
                    });
                });
            }
        });
    }
    bool start() { return server.listen(QHostAddress::LocalHost, 0); }
    QUrl url() const { return QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort())); }
    int quotaReads() const
    {
        int count = 0;
        for (const auto &req : requests) { count += req.path == "/subscription-quotas" ? 1 : 0; }
        return count;
    }
};

QByteArray fixture()
{
    QFile file(QStringLiteral(ACP_TEST_FIXTURE_DIR "/subscription-quotas.json"));
    if (!file.open(QIODevice::ReadOnly)) { qFatal("Fixture des quotas illisible"); }
    return file.readAll();
}
QJsonObject fixtureObject() { return QJsonDocument::fromJson(fixture()).object(); }
QByteArray json(const QJsonObject &object) { return QJsonDocument(object).toJson(QJsonDocument::Compact); }

QJsonObject window(const QString &key, const QJsonValue &used, const QJsonValue &minutes,
                   const QJsonValue &resets)
{
    QJsonValue remaining = QJsonValue::Null;
    if (used.isDouble()) { remaining = 100.0 - used.toDouble(); }
    return {{QStringLiteral("key"), key}, {QStringLiteral("used_percent"), used},
        {QStringLiteral("window_minutes"), minutes}, {QStringLiteral("resets_at"), resets},
        {QStringLiteral("remaining_percent"), remaining}};
}
QJsonObject report(const QString &provider, const QString &status, const QString &observed,
                   const QJsonArray &windows = {}, bool stale = false)
{
    const bool codex = provider == QLatin1String("codex");
    return {{QStringLiteral("provider"), provider}, {QStringLiteral("status"), status},
        {QStringLiteral("source"), codex ? QStringLiteral("codex_app_server") : QStringLiteral("claude_code_statusline")},
        {QStringLiteral("plan"), QJsonValue::Null}, {QStringLiteral("limit_id"), QStringLiteral("default")},
        {QStringLiteral("windows"), windows}, {QStringLiteral("credits"), QJsonValue::Null},
        {QStringLiteral("limit_reached"), QJsonValue::Null}, {QStringLiteral("reached_type"), QJsonValue::Null},
        {QStringLiteral("observed_at"), observed},
        {QStringLiteral("detail"), status == QLatin1String("ok") ? QJsonValue(QJsonValue::Null)
                                                                  : QJsonValue(QStringLiteral("Explication du worker."))},
        {QStringLiteral("worker_id"), QStringLiteral("5b1f7a52-3c1e-4d3a-9d1e-0c2f6a7b8c9d")},
        {QStringLiteral("worker_name"), QStringLiteral("poste-principal")},
        {QStringLiteral("received_at"), observed}, {QStringLiteral("stale"), stale}};
}
QJsonObject listing(const QJsonArray &items)
{
    return {{QStringLiteral("items"), items}, {QStringLiteral("stale_after_seconds"), 1800},
        {QStringLiteral("generated_at"), QStringLiteral("2026-09-24T08:00:05Z")}};
}

void authenticate(AuthManager &auth, const QString &role = QStringLiteral("owner"))
{
    auth.applySessionPayload({{QStringLiteral("authenticated"), true},
        {QStringLiteral("csrf_token"), QStringLiteral("csrf-test")},
        {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00+00:00")},
        {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("alice")},
            {QStringLiteral("display_name"), QStringLiteral("Alice")}, {QStringLiteral("role"), role}}}});
}
JsonListModel *rows(SubscriptionQuotasViewModel &vm) { return qobject_cast<JsonListModel *>(vm.reports()); }
QVariantMap windowAt(const QVariantMap &row, int index) { return row.value(QStringLiteral("windows")).toList().value(index).toMap(); }
QString nbsp(const char *text) { return QString::fromUtf8(text).replace(QLatin1Char('_'), QChar(0x00A0)); }

// Horloge figée à 08:03 UTC, affichage à UTC+2 : les heures locales se vérifient sans
// dépendre du fuseau du poste qui exécute la suite.
struct Harness {
    QuotaServer server;
    ApiClient client;
    std::unique_ptr<AuthManager> auth;
    std::unique_ptr<SubscriptionQuotasViewModel> vm;
    explicit Harness(const QString &role = QStringLiteral("owner"))
    {
        if (!server.start()) { qFatal("Serveur local inaccessible"); }
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(server.url()).isError()) { qFatal("Adresse refusée"); }
        auth = std::make_unique<AuthManager>(&client);
        authenticate(*auth, role);
        vm = std::make_unique<SubscriptionQuotasViewModel>(&client, auth.get());
        vm->setClockForTesting([] { return QDateTime(QDate(2026, 9, 24), QTime(8, 3), QTimeZone::UTC); });
        vm->setTimeZoneForTesting(QTimeZone::fromSecondsAheadOfUtc(7200));
    }
};
} // namespace

class TestSubscriptionQuotas : public QObject
{
    Q_OBJECT
private slots:
    void twoProvidersFromTheReferenceFixture();
    void emptyListIsAnHonestEmptyState();
    void forbiddenIsReservedToTheOwner();
    void nonOwnerSessionNeverRequestsQuotas();
    void malformedPayloadIsRefused_data();
    void malformedPayloadIsRefused();
    void staleReadingIsFlaggedAndOlderCountersAreMarked();
    void nullValuesStayUnknown();
    void limitReachedRaisesAnAlert();
    void fractionalTimestampsAndNumbersAreRead();
    void offlineServerIsReportedAsOffline();
    void missingRouteMeansUnsupportedServer();
    void automaticRefreshOnlyWhileVisible();
    void staleSessionResponsesAreDiscarded();
    void probeStatesAreNamedInFrench_data();
    void probeStatesAreNamedInFrench();
    void futureTimestampIsNotCalledRecent();
    void periodicRefreshKeepsTheCurrentExplanation();
};

void TestSubscriptionQuotas::twoProvidersFromTheReferenceFixture()
{
    Harness h;
    h.server.handler = [](const Request &) { return Response{fixture()}; };
    QCOMPARE(h.vm->state(), QStringLiteral("idle"));
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    QVERIFY(!h.vm->loading());
    QCOMPARE(h.server.quotaReads(), 1);
    const auto &req = h.server.requests.first();
    QCOMPARE(req.method, QByteArray("GET"));
    QVERIFY(req.headers.toLower().contains("accept: application/json"));
    QVERIFY(!req.headers.toLower().contains("x-csrf-token"));
    QCOMPARE(h.vm->stateLabel(), QStringLiteral("Relevés reçus"));
    QCOMPARE(h.vm->servedLabel(), QStringLiteral("Liste servie par l'API à 10:00:05"));
    QCOMPARE(h.vm->staleAfterLabel(), QStringLiteral("Un relevé devient « Périmé » après 30 min."));

    // Codex d'abord, puis Claude Code ; dans un même poste, compteurs par identifiant.
    QCOMPARE(rows(*h.vm)->count(), 3);
    const auto codex = rows(*h.vm)->get(0);
    QCOMPARE(codex.value(QStringLiteral("providerLabel")).toString(), QStringLiteral("Codex (compte ChatGPT)"));
    QCOMPARE(codex.value(QStringLiteral("plan")).toString(), QStringLiteral("prolite"));
    QCOMPARE(codex.value(QStringLiteral("statusLabel")).toString(), QStringLiteral("Connecté"));
    QCOMPARE(codex.value(QStringLiteral("statusKey")).toString(), QStringLiteral("succeeded"));
    QCOMPARE(codex.value(QStringLiteral("sourceLabel")).toString(), QStringLiteral("relevé officiel app-server"));
    QCOMPARE(codex.value(QStringLiteral("limitId")).toString(), QStringLiteral("codex"));
    QCOMPARE(codex.value(QStringLiteral("workerName")).toString(), QStringLiteral("poste-principal"));
    QCOMPARE(codex.value(QStringLiteral("freshness")).toString(), QStringLiteral("relevé il y a 3 min"));
    QCOMPARE(codex.value(QStringLiteral("stale")).toBool(), false);
    QCOMPARE(codex.value(QStringLiteral("current")).toBool(), true);
    QCOMPARE(codex.value(QStringLiteral("creditsLabel")).toString(), QStringLiteral("Aucun crédit"));
    QCOMPARE(codex.value(QStringLiteral("limitReached")).toBool(), false);
    QCOMPARE(codex.value(QStringLiteral("limitReachedLabel")).toString(), QStringLiteral("Non atteinte"));
    const auto primary = windowAt(codex, 0);
    QCOMPARE(primary.value(QStringLiteral("label")).toString(), QStringLiteral("Fenêtre 5 h"));
    QCOMPARE(primary.value(QStringLiteral("usedText")).toString(), nbsp("42_%"));
    QCOMPARE(primary.value(QStringLiteral("remainingText")).toString(), nbsp("58_%"));
    QCOMPARE(primary.value(QStringLiteral("remainingPercent")).toDouble(), 58.0);
    QCOMPARE(primary.value(QStringLiteral("resetText")).toString(), QStringLiteral("aujourd'hui à 14:00"));
    QCOMPARE(primary.value(QStringLiteral("countdownText")).toString(), QStringLiteral("dans 3 h 57"));
    QCOMPARE(primary.value(QStringLiteral("level")).toString(), QStringLiteral("normal"));
    const auto weekly = windowAt(codex, 1);
    QCOMPARE(weekly.value(QStringLiteral("label")).toString(), QStringLiteral("Semaine"));
    QCOMPARE(weekly.value(QStringLiteral("usedText")).toString(), nbsp("7_%"));
    QCOMPARE(weekly.value(QStringLiteral("remainingText")).toString(), nbsp("93_%"));
    QCOMPARE(weekly.value(QStringLiteral("resetText")).toString(), QStringLiteral("le 29/09 à 02:00"));
    QCOMPARE(weekly.value(QStringLiteral("countdownText")).toString(), QStringLiteral("dans 4 j 15 h"));
    const QString summary = codex.value(QStringLiteral("accessibleName")).toString();
    QVERIFY2(summary.contains(QStringLiteral("Codex (compte ChatGPT)")) && summary.contains(QStringLiteral("Fenêtre 5 h"))
             && summary.contains(nbsp("58_% restant")), qPrintable(summary));

    const auto signedOut = rows(*h.vm)->get(1);
    QCOMPARE(signedOut.value(QStringLiteral("statusLabel")).toString(), QStringLiteral("Non connecté"));
    QCOMPARE(signedOut.value(QStringLiteral("statusKey")).toString(), QStringLiteral("notConfigured"));
    QVERIFY(signedOut.value(QStringLiteral("detail")).toString().contains(QStringLiteral("codex login")));
    QCOMPARE(signedOut.value(QStringLiteral("windows")).toList().size(), 0);
    QCOMPARE(signedOut.value(QStringLiteral("plan")).toString(), QStringLiteral("Inconnu"));

    const auto claude = rows(*h.vm)->get(2);
    QCOMPARE(claude.value(QStringLiteral("providerLabel")).toString(), QStringLiteral("Claude Code"));
    QCOMPARE(claude.value(QStringLiteral("sourceLabel")).toString(), QStringLiteral("ligne d'état Claude Code"));
    QCOMPARE(claude.value(QStringLiteral("plan")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(claude.value(QStringLiteral("creditsLabel")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(claude.value(QStringLiteral("limitReachedLabel")).toString(), QStringLiteral("Inconnu"));
    const auto fiveHours = windowAt(claude, 0);
    QCOMPARE(fiveHours.value(QStringLiteral("usedText")).toString(), nbsp("12,5_%"));
    QCOMPARE(fiveHours.value(QStringLiteral("remainingText")).toString(), nbsp("87,5_%"));
    QCOMPARE(fiveHours.value(QStringLiteral("resetText")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(fiveHours.value(QStringLiteral("countdownText")).toString(), QString());
    const auto sevenDays = windowAt(claude, 1);
    QCOMPARE(sevenDays.value(QStringLiteral("label")).toString(), QStringLiteral("Semaine"));
    QCOMPARE(sevenDays.value(QStringLiteral("usedText")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(sevenDays.value(QStringLiteral("remainingText")).toString(), QStringLiteral("Inconnu"));
    QVERIFY(sevenDays.value(QStringLiteral("remainingPercent")).isNull());
    QCOMPARE(sevenDays.value(QStringLiteral("level")).toString(), QStringLiteral("unknown"));
    QVERIFY(h.vm->message().isEmpty());
}

void TestSubscriptionQuotas::emptyListIsAnHonestEmptyState()
{
    Harness h;
    h.server.handler = [](const Request &) { return Response{json(listing({}))}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("empty"));
    QCOMPARE(h.vm->stateLabel(), QStringLiteral("Aucun relevé"));
    QVERIFY(h.vm->message().contains(QStringLiteral("ACP_WORKER_SUBSCRIPTION_QUOTAS=1")));
    QCOMPARE(rows(*h.vm)->count(), 0);
}

void TestSubscriptionQuotas::forbiddenIsReservedToTheOwner()
{
    Harness h;
    // Session réelle : le 403 déclenche une seule relecture de /auth/session.
    QNetworkCookie cookie(QByteArrayLiteral("acp_session"), QByteArrayLiteral("session-test-0123456789"));
    cookie.setHttpOnly(true);
    cookie.setPath(QStringLiteral("/"));
    QVERIFY(h.client.cookieJar()->setCookiesFromUrl({cookie}, h.server.url()));
    h.vm->setRefreshIntervalForTesting(std::chrono::milliseconds(50));
    h.server.handler = [](const Request &req) {
        if (req.path == "/auth/session") {
            return Response{json({{QStringLiteral("authenticated"), true},
                {QStringLiteral("csrf_token"), QStringLiteral("refreshed")},
                {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00+00:00")},
                {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("alice")},
                    {QStringLiteral("display_name"), QStringLiteral("Alice")}, {QStringLiteral("role"), QStringLiteral("owner")}}}})};
        }
        return Response{json({{QStringLiteral("detail"), QStringLiteral("Quotas d'abonnement réservés au propriétaire de la plateforme : l'usage d'un abonnement est personnel à son titulaire.")}}), 403};
    };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("forbidden"));
    QCOMPARE(h.vm->stateLabel(), QStringLiteral("Réservé au propriétaire de la plateforme"));
    QVERIFY(h.vm->message().contains(QStringLiteral("personnel à son titulaire")));
    QCOMPARE(rows(*h.vm)->count(), 0);
    QTRY_COMPARE(h.auth->state(), SessionStatus::Connected);
    QTest::qWait(300);
    // Un refus de droits n'est pas relu en boucle.
    QCOMPARE(h.server.quotaReads(), 1);
    QCOMPARE(h.vm->state(), QStringLiteral("forbidden"));
}

void TestSubscriptionQuotas::nonOwnerSessionNeverRequestsQuotas()
{
    Harness h(QStringLiteral("operator"));
    h.server.handler = [](const Request &) { return Response{fixture()}; };
    h.vm->setActive(true);
    QCOMPARE(h.vm->state(), QStringLiteral("forbidden"));
    QCOMPARE(h.vm->stateLabel(), QStringLiteral("Réservé au propriétaire de la plateforme"));
    h.vm->refresh();
    QTest::qWait(100);
    QCOMPARE(h.server.quotaReads(), 0);
    QVERIFY(!h.vm->canRefresh());
}

void TestSubscriptionQuotas::malformedPayloadIsRefused_data()
{
    QTest::addColumn<QByteArray>("body");
    QTest::addColumn<QString>("reason");
    const auto base = fixtureObject();
    const auto withItem = [&base](const std::function<void(QJsonObject &)> &change) {
        auto document = base;
        auto items = document.value(QStringLiteral("items")).toArray();
        auto item = items.at(1).toObject();
        change(item);
        items.replace(1, item);
        document.insert(QStringLiteral("items"), items);
        return json(document);
    };
    const auto withWindow = [&withItem](const std::function<void(QJsonObject &)> &change) {
        return withItem([&change](QJsonObject &item) {
            auto windows = item.value(QStringLiteral("windows")).toArray();
            auto first = windows.at(0).toObject();
            change(first);
            windows.replace(0, first);
            item.insert(QStringLiteral("windows"), windows);
        });
    };
    auto extra = base;
    extra.insert(QStringLiteral("unexpected"), true);
    QTest::newRow("unknown-top-level-field") << json(extra) << QStringLiteral("champ inattendu « unexpected »");
    auto missing = base;
    missing.remove(QStringLiteral("stale_after_seconds"));
    QTest::newRow("missing-top-level-field") << json(missing) << QStringLiteral("champ absent « stale_after_seconds »");
    QTest::newRow("not-an-object") << QByteArray("[]") << QStringLiteral("objet JSON attendu");
    QTest::newRow("unknown-item-field") << withItem([](QJsonObject &item) { item.insert(QStringLiteral("email"), QStringLiteral("x@y")); })
                                        << QStringLiteral("champ inattendu « email »");
    QTest::newRow("missing-item-field") << withItem([](QJsonObject &item) { item.remove(QStringLiteral("stale")); })
                                        << QStringLiteral("champ absent « stale »");
    QTest::newRow("stale-as-number") << withItem([](QJsonObject &item) { item.insert(QStringLiteral("stale"), 0); })
                                     << QStringLiteral("« stale »");
    QTest::newRow("unknown-provider") << withItem([](QJsonObject &item) { item.insert(QStringLiteral("provider"), QStringLiteral("gemini")); })
                                      << QStringLiteral("« provider »");
    QTest::newRow("unknown-status") << withItem([](QJsonObject &item) { item.insert(QStringLiteral("status"), QStringLiteral("maybe")); })
                                    << QStringLiteral("« status »");
    QTest::newRow("source-mismatch") << withItem([](QJsonObject &item) { item.insert(QStringLiteral("source"), QStringLiteral("claude_code_statusline")); })
                                     << QStringLiteral("« source »");
    QTest::newRow("measure-on-failure") << withItem([](QJsonObject &item) {
        item.insert(QStringLiteral("status"), QStringLiteral("unavailable"));
        item.insert(QStringLiteral("detail"), QStringLiteral("Délai dépassé."));
    }) << QStringLiteral("aucune mesure");
    QTest::newRow("timestamp-without-zone") << withItem([](QJsonObject &item) { item.insert(QStringLiteral("observed_at"), QStringLiteral("2026-09-24T08:00:00")); })
                                            << QStringLiteral("« observed_at »");
    QTest::newRow("used-as-text") << withWindow([](QJsonObject &w) { w.insert(QStringLiteral("used_percent"), QStringLiteral("42")); })
                                  << QStringLiteral("« used_percent »");
    QTest::newRow("used-as-boolean") << withWindow([](QJsonObject &w) { w.insert(QStringLiteral("used_percent"), true); })
                                     << QStringLiteral("« used_percent »");
    QTest::newRow("used-above-100") << withWindow([](QJsonObject &w) { w.insert(QStringLiteral("used_percent"), 101); w.insert(QStringLiteral("remaining_percent"), -1); })
                                    << QStringLiteral("« used_percent »");
    QTest::newRow("remaining-invented") << withWindow([](QJsonObject &w) { w.insert(QStringLiteral("remaining_percent"), 60); })
                                        << QStringLiteral("« remaining_percent »");
    QTest::newRow("fractional-minutes") << withWindow([](QJsonObject &w) { w.insert(QStringLiteral("window_minutes"), 300.5); })
                                        << QStringLiteral("« window_minutes »");
    QTest::newRow("unknown-window-field") << withWindow([](QJsonObject &w) { w.insert(QStringLiteral("limit_name"), QStringLiteral("x")); })
                                          << QStringLiteral("champ inattendu « limit_name »");
    QTest::newRow("credits-as-text") << withItem([](QJsonObject &item) { item.insert(QStringLiteral("credits"), QStringLiteral("0")); })
                                     << QStringLiteral("« credits »");
    QTest::newRow("reached-type-without-limit") << withItem([](QJsonObject &item) { item.insert(QStringLiteral("reached_type"), QStringLiteral("primary")); })
                                                << QStringLiteral("« reached_type »");
    QTest::newRow("duplicate-counter") << withItem([&base](QJsonObject &item) { item = base.value(QStringLiteral("items")).toArray().at(2).toObject(); })
                                       << QStringLiteral("en double");
}

void TestSubscriptionQuotas::malformedPayloadIsRefused()
{
    QFETCH(QByteArray, body);
    QFETCH(QString, reason);
    Harness h;
    bool broken = false;
    h.server.handler = [&broken, body](const Request &) { return Response{broken ? body : fixture()}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    QCOMPARE(rows(*h.vm)->count(), 3);
    broken = true;
    h.vm->refresh();
    QTRY_COMPARE(h.vm->state(), QStringLiteral("error"));
    // Échec fermé : les valeurs précédentes ne restent pas affichées comme actuelles.
    QCOMPARE(rows(*h.vm)->count(), 0);
    QVERIFY2(h.vm->message().startsWith(QStringLiteral("Réponse des quotas refusée")), qPrintable(h.vm->message()));
    QVERIFY2(h.vm->message().contains(reason), qPrintable(h.vm->message()));
}

void TestSubscriptionQuotas::staleReadingIsFlaggedAndOlderCountersAreMarked()
{
    Harness h;
    auto older = report(QStringLiteral("codex"), QStringLiteral("ok"), QStringLiteral("2026-09-24T05:59:00Z"),
        {window(QStringLiteral("primary"), 90, 300, QStringLiteral("2026-09-24T06:30:00Z"))}, true);
    older.insert(QStringLiteral("limit_id"), QStringLiteral("codex"));
    older.insert(QStringLiteral("plan"), QStringLiteral("prolite"));
    const auto latest = report(QStringLiteral("codex"), QStringLiteral("unavailable"), QStringLiteral("2026-09-24T08:02:00Z"));
    h.server.handler = [&](const Request &) { return Response{json(listing({older, latest}))}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    QCOMPARE(rows(*h.vm)->count(), 2);
    const auto current = rows(*h.vm)->get(0);
    QCOMPARE(current.value(QStringLiteral("statusLabel")).toString(), QStringLiteral("Indisponible"));
    QCOMPARE(current.value(QStringLiteral("statusKey")).toString(), QStringLiteral("failed"));
    QCOMPARE(current.value(QStringLiteral("current")).toBool(), true);
    QCOMPARE(current.value(QStringLiteral("freshness")).toString(), QStringLiteral("relevé il y a 1 min"));
    const auto previous = rows(*h.vm)->get(1);
    QCOMPARE(previous.value(QStringLiteral("stale")).toBool(), true);
    QCOMPARE(previous.value(QStringLiteral("staleLabel")).toString(), QStringLiteral("Périmé"));
    QCOMPARE(previous.value(QStringLiteral("current")).toBool(), false);
    QVERIFY2(previous.value(QStringLiteral("supersededNote")).toString().contains(QStringLiteral("« Indisponible »")),
             qPrintable(previous.value(QStringLiteral("supersededNote")).toString()));
    QCOMPARE(previous.value(QStringLiteral("freshness")).toString(), QStringLiteral("relevé il y a 2 h 04"));
    const auto gauge = windowAt(previous, 0);
    QCOMPARE(gauge.value(QStringLiteral("level")).toString(), QStringLiteral("critical"));
    QCOMPARE(gauge.value(QStringLiteral("resetText")).toString(), QStringLiteral("aujourd'hui à 08:30"));
    QCOMPARE(gauge.value(QStringLiteral("countdownText")).toString(), QStringLiteral("déjà passée"));
    QVERIFY(previous.value(QStringLiteral("accessibleName")).toString().contains(QStringLiteral("Périmé")));
}

void TestSubscriptionQuotas::nullValuesStayUnknown()
{
    Harness h;
    auto row = report(QStringLiteral("codex"), QStringLiteral("ok"), QStringLiteral("2026-09-24T08:02:59Z"),
        {window(QStringLiteral("primary"), QJsonValue::Null, QJsonValue::Null, QJsonValue::Null),
         window(QStringLiteral("secondary"), 20, 1440, QJsonValue::Null)});
    h.server.handler = [&](const Request &) { return Response{json(listing({row}))}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    const auto item = rows(*h.vm)->get(0);
    QCOMPARE(item.value(QStringLiteral("plan")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(item.value(QStringLiteral("creditsLabel")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(item.value(QStringLiteral("limitReachedLabel")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(item.value(QStringLiteral("freshness")).toString(), QStringLiteral("relevé à l'instant"));
    QVERIFY(item.value(QStringLiteral("accessibleName")).toString().contains(QStringLiteral("Fenêtre « primary » (durée inconnue) : reste Inconnu")));
    const auto unknown = windowAt(item, 0);
    QCOMPARE(unknown.value(QStringLiteral("label")).toString(), QStringLiteral("Fenêtre « primary » (durée inconnue)"));
    QCOMPARE(unknown.value(QStringLiteral("usedText")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(unknown.value(QStringLiteral("remainingText")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(unknown.value(QStringLiteral("resetText")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(unknown.value(QStringLiteral("level")).toString(), QStringLiteral("unknown"));
    const auto daily = windowAt(item, 1);
    QCOMPARE(daily.value(QStringLiteral("label")).toString(), QStringLiteral("Fenêtre de 1440 min"));
    QCOMPARE(daily.value(QStringLiteral("remainingText")).toString(), nbsp("80_%"));
    QVERIFY(item.value(QStringLiteral("accessibleName")).toString().contains(QStringLiteral("Inconnu")));
}

void TestSubscriptionQuotas::limitReachedRaisesAnAlert()
{
    Harness h;
    auto row = report(QStringLiteral("codex"), QStringLiteral("ok"), QStringLiteral("2026-09-24T08:00:00Z"),
        {window(QStringLiteral("primary"), 100, 300, QStringLiteral("2026-09-24T09:00:00Z"))});
    row.insert(QStringLiteral("limit_reached"), true);
    row.insert(QStringLiteral("reached_type"), QStringLiteral("rate_limit_reached"));
    row.insert(QStringLiteral("credits"), QJsonObject{{QStringLiteral("has_credits"), true},
        {QStringLiteral("unlimited"), false}, {QStringLiteral("balance"), QStringLiteral("12.50")}});
    h.server.handler = [&](const Request &) { return Response{json(listing({row}))}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    const auto item = rows(*h.vm)->get(0);
    QCOMPARE(item.value(QStringLiteral("limitReached")).toBool(), true);
    QCOMPARE(item.value(QStringLiteral("limitReachedLabel")).toString(), QStringLiteral("Limite atteinte (rate_limit_reached)"));
    QCOMPARE(item.value(QStringLiteral("creditsLabel")).toString(), QStringLiteral("Solde : 12.50"));
    QCOMPARE(windowAt(item, 0).value(QStringLiteral("remainingText")).toString(), nbsp("0_%"));
    QCOMPARE(windowAt(item, 0).value(QStringLiteral("level")).toString(), QStringLiteral("critical"));
    QCOMPARE(windowAt(item, 0).value(QStringLiteral("countdownText")).toString(), QStringLiteral("dans 57 min"));
    QVERIFY(item.value(QStringLiteral("accessibleName")).toString().contains(QStringLiteral("Limite atteinte")));
}

void TestSubscriptionQuotas::fractionalTimestampsAndNumbersAreRead()
{
    Harness h;
    auto row = report(QStringLiteral("claude_code"), QStringLiteral("ok"), QStringLiteral("2026-09-24T07:02:59.123456Z"),
        {window(QStringLiteral("five_hour"), 33.3333, 300, QStringLiteral("2026-09-24T10:15:30.5+00:00"))});
    auto windows = row.value(QStringLiteral("windows")).toArray();
    auto first = windows.at(0).toObject();
    first.insert(QStringLiteral("remaining_percent"), 66.6667);
    windows.replace(0, first);
    row.insert(QStringLiteral("windows"), windows);
    row.insert(QStringLiteral("received_at"), QStringLiteral("2026-09-24T07:03:01.999999+00:00"));
    h.server.handler = [&](const Request &) { return Response{json(listing({row}))}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    const auto item = rows(*h.vm)->get(0);
    QCOMPARE(item.value(QStringLiteral("freshness")).toString(), QStringLiteral("relevé il y a 1 h"));
    const auto gauge = windowAt(item, 0);
    QCOMPARE(gauge.value(QStringLiteral("usedText")).toString(), nbsp("33,3333_%"));
    QCOMPARE(gauge.value(QStringLiteral("remainingText")).toString(), nbsp("66,6667_%"));
    QCOMPARE(gauge.value(QStringLiteral("resetText")).toString(), QStringLiteral("aujourd'hui à 12:15"));
    QCOMPARE(gauge.value(QStringLiteral("countdownText")).toString(), QStringLiteral("dans 2 h 12"));
}

void TestSubscriptionQuotas::offlineServerIsReportedAsOffline()
{
    Harness h;
    h.server.handler = [](const Request &) { return Response{fixture()}; };
    h.server.server.close();
    h.vm->setActive(true);
    QTRY_COMPARE_WITH_TIMEOUT(h.vm->state(), QStringLiteral("offline"), 15000);
    QCOMPARE(h.vm->stateLabel(), QStringLiteral("Hors ligne"));
    QCOMPARE(rows(*h.vm)->count(), 0);
    QVERIFY(!h.vm->message().isEmpty());
}

void TestSubscriptionQuotas::missingRouteMeansUnsupportedServer()
{
    Harness h;
    h.server.handler = [](const Request &) { return Response{json({{QStringLiteral("detail"), QStringLiteral("Not Found")}}), 404}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("unsupported"));
    QCOMPARE(h.vm->stateLabel(), QStringLiteral("Non disponible sur ce serveur"));
    QCOMPARE(rows(*h.vm)->count(), 0);
}

void TestSubscriptionQuotas::automaticRefreshOnlyWhileVisible()
{
    Harness h;
    h.vm->setRefreshIntervalForTesting(std::chrono::milliseconds(60));
    QCOMPARE(h.vm->refreshIntervalSeconds(), 60);
    h.server.handler = [](const Request &) { return Response{fixture()}; };
    QTest::qWait(150);
    QCOMPARE(h.server.quotaReads(), 0);
    h.vm->setActive(true);
    QTRY_VERIFY(h.server.quotaReads() >= 3);
    h.vm->setActive(false);
    QCOMPARE(rows(*h.vm)->count(), 0);
    QTest::qWait(100);
    const int reads = h.server.quotaReads();
    QTest::qWait(300);
    QCOMPARE(h.server.quotaReads(), reads);
}

void TestSubscriptionQuotas::staleSessionResponsesAreDiscarded()
{
    Harness h;
    h.server.handler = [](const Request &) { return Response{fixture(), 200, 250}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.server.quotaReads(), 1);
    QVERIFY(h.vm->loading());
    h.auth->forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Test"));
    QCOMPARE(h.vm->state(), QStringLiteral("signedOut"));
    QTest::qWait(400);
    QCOMPARE(rows(*h.vm)->count(), 0);
    QCOMPARE(h.vm->state(), QStringLiteral("signedOut"));
    QVERIFY(!h.vm->loading());
    // Une nouvelle identité recharge sans rien reprendre de la précédente.
    authenticate(*h.auth);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    QCOMPARE(rows(*h.vm)->count(), 3);
}

void TestSubscriptionQuotas::probeStatesAreNamedInFrench_data()
{
    QTest::addColumn<QString>("status");
    QTest::addColumn<QString>("label");
    QTest::addColumn<QString>("chip");
    QTest::newRow("ok") << QStringLiteral("ok") << QStringLiteral("Connecté") << QStringLiteral("succeeded");
    QTest::newRow("not-signed-in") << QStringLiteral("not_signed_in") << QStringLiteral("Non connecté") << QStringLiteral("notConfigured");
    QTest::newRow("cli-missing") << QStringLiteral("cli_missing") << QStringLiteral("CLI absente") << QStringLiteral("notConfigured");
    QTest::newRow("cli-too-old") << QStringLiteral("cli_too_old") << QStringLiteral("CLI trop ancienne") << QStringLiteral("blocked");
    QTest::newRow("unavailable") << QStringLiteral("unavailable") << QStringLiteral("Indisponible") << QStringLiteral("failed");
}

void TestSubscriptionQuotas::probeStatesAreNamedInFrench()
{
    QFETCH(QString, status);
    QFETCH(QString, label);
    QFETCH(QString, chip);
    Harness h;
    const auto row = report(QStringLiteral("codex"), status, QStringLiteral("2026-09-24T08:00:00Z"));
    h.server.handler = [&](const Request &) { return Response{json(listing({row}))}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    const auto item = rows(*h.vm)->get(0);
    QCOMPARE(item.value(QStringLiteral("statusLabel")).toString(), label);
    QCOMPARE(item.value(QStringLiteral("statusKey")).toString(), chip);
    QCOMPARE(item.value(QStringLiteral("detail")).toString(),
             status == QLatin1String("ok") ? QString() : QStringLiteral("Explication du worker."));
}

void TestSubscriptionQuotas::futureTimestampIsNotCalledRecent()
{
    Harness h;
    // L'API tolère cinq minutes d'avance d'horloge : l'écran ne l'appelle pas « à l'instant ».
    const auto row = report(QStringLiteral("claude_code"), QStringLiteral("ok"), QStringLiteral("2026-09-24T08:07:00Z"),
        {window(QStringLiteral("five_hour"), 10, 300, QJsonValue::Null)});
    h.server.handler = [&](const Request &) { return Response{json(listing({row}))}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("ready"));
    QCOMPARE(rows(*h.vm)->get(0).value(QStringLiteral("freshness")).toString(),
             QStringLiteral("relevé daté de 4 min dans le futur (horloge du worker en avance)"));
}

void TestSubscriptionQuotas::periodicRefreshKeepsTheCurrentExplanation()
{
    Harness h;
    int delay = 0;
    h.server.handler = [&delay](const Request &) { return Response{json(listing({})), 200, delay}; };
    h.vm->setActive(true);
    QTRY_COMPARE(h.vm->state(), QStringLiteral("empty"));
    const QString explanation = h.vm->message();
    delay = 300;
    h.vm->refresh();
    QVERIFY(h.vm->loading());
    // Pas de clignotement « Chargement… » à chaque relecture : l'explication reste lisible.
    QCOMPARE(h.vm->state(), QStringLiteral("empty"));
    QCOMPARE(h.vm->message(), explanation);
    QTRY_VERIFY(!h.vm->loading());
    QCOMPARE(h.vm->state(), QStringLiteral("empty"));
}

QTEST_GUILESS_MAIN(TestSubscriptionQuotas)
#include "tst_subscription_quotas.moc"
