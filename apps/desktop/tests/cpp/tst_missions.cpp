// Le serveur TCP local exerce le transport réel, les générations et les en-têtes.
#include "viewmodels/MissionsViewModel.h"
#include "api/ApiClient.h"
#include "auth/AuthManager.h"
#include "events/EventStreamService.h"

#include <QHostAddress>
#include <QJsonDocument>
#include <QPointer>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <functional>

using namespace acp;

namespace {
struct Incoming {
    QByteArray method, target, headers;
    QJsonObject body;
    QPointer<QTcpSocket> socket;
};
class HttpFixture final : public QTcpServer {
public:
    QList<Incoming> received;
    std::function<void(const Incoming&)> handle;
    HttpFixture() {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (hasPendingConnections()) {
                QTcpSocket* socket = nextPendingConnection();
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                auto buffer = std::make_shared<QByteArray>();
                auto dispatched = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, buffer, dispatched] {
                    *buffer += socket->readAll();
                    if (*dispatched) return;
                    const qsizetype split = buffer->indexOf("\r\n\r\n");
                    if (split < 0) return;
                    const QByteArray headers = buffer->left(split);
                    int length = 0;
                    for (const QByteArray& line : headers.split('\n'))
                        if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                    if (buffer->size() < split + 4 + length) return;
                    *dispatched = true;
                    const auto first = headers.split('\n').first().split(' ');
                    Incoming req{first.value(0), first.value(1), headers,
                                 QJsonDocument::fromJson(buffer->mid(split + 4, length)).object(), socket};
                    received.append(req);
                    if (handle) handle(req); else reply(req, QJsonArray{});
                });
            }
        });
        if (!listen(QHostAddress::LocalHost)) qFatal("Serveur de test local indisponible");
    }
    static void reply(const Incoming& req, const QJsonValue& value, int status = 200) {
        if (!req.socket) return;
        const QByteArray body = value.isArray() ? QJsonDocument(value.toArray()).toJson(QJsonDocument::Compact)
                                               : QJsonDocument(value.toObject()).toJson(QJsonDocument::Compact);
        req.socket->write("HTTP/1.1 " + QByteArray::number(status) + " Test\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                          + QByteArray::number(body.size()) + "\r\n\r\n" + body);
        req.socket->disconnectFromHost();
    }
};
void login(AuthManager& auth, const QString& role = QStringLiteral("owner")) {
    auth.applySessionPayload(QJsonObject{
        {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("user")}, {QStringLiteral("role"), role}}},
        {QStringLiteral("csrf_token"), QStringLiteral("csrf-fixture")}});
}
QJsonObject attempt(const QString& id, const QString& status, const QString& acceptance = QStringLiteral("pending")) {
    return {{QStringLiteral("id"), id}, {QStringLiteral("status"), status}, {QStringLiteral("attempt_number"), 1},
        {QStringLiteral("technical_validation"), QJsonObject{{QStringLiteral("status"), QStringLiteral("passed")}}},
        {QStringLiteral("user_acceptance"), QJsonObject{{QStringLiteral("status"), acceptance}}},
        {QStringLiteral("evidence"), QJsonArray{}}};
}
QJsonObject detail(const QJsonObject& run) {
    return {{QStringLiteral("id"), QStringLiteral("mission")}, {QStringLiteral("project_id"), QStringLiteral("project")},
        {QStringLiteral("current_run"), run}, {QStringLiteral("runs"), QJsonArray{run}}};
}
void configure(ApiClient& api, HttpFixture& server) {
    api.setAllowInsecureLoopback(true);
    const ApiError error = api.setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort())));
    Q_ASSERT(!error.isError());
}
void noStreams(EventStreamService& streams) {
    StreamLimits limits; limits.maxConnectionsPerUser = 0; streams.setLimits(limits);
}
}

class TestMissions : public QObject {
    Q_OBJECT
private slots:
    void creationRequiresBoundedRealContract();
    void acceptanceAndRetryAreDifferentDecisions();
    void staleProjectAndSessionRepliesCannotRepopulate();
    void mutationUsesOnlyDeclaredIdempotency();
    void projectViewerCannotMutate();
    void staleRunTestsCannotReplaceCurrentResults();
    void ambiguousCommandReusesItsKeyAndBody_data();
    void ambiguousCommandReusesItsKeyAndBody();
    void changingContextCancelsPendingCommandAndRetries();
    void abandoningRequiresExplicitDuplicateRiskAcknowledgement();
};

void TestMissions::creationRequiresBoundedRealContract() {
    QVariantMap form{{QStringLiteral("title"), QStringLiteral("Mission")}, {QStringLiteral("objective"), QStringLiteral("Objectif")},
        {QStringLiteral("expected_outcome"), QStringLiteral("Résultat")}, {QStringLiteral("acceptance_criteria"), QStringLiteral("A\nA\nB")},
        {QStringLiteral("max_cost"), QStringLiteral("1.25")}, {QStringLiteral("duration_seconds"), 900}};
    QString error;
    const auto body = MissionsViewModel::creationBody(QStringLiteral("project"), form, &error);
    QVERIFY(error.isEmpty());
    QCOMPARE(body.value(QStringLiteral("acceptance_criteria")).toArray().size(), 2);
    QCOMPARE(body.value(QStringLiteral("budget")).toObject().value(QStringLiteral("max_cost")).toDouble(), 1.25);
    QCOMPARE(body.value(QStringLiteral("autonomy")).toObject().value(QStringLiteral("mode")).toString(), QStringLiteral("bounded"));
    form.insert(QStringLiteral("max_cost"), QStringLiteral("nan"));
    QVERIFY(MissionsViewModel::creationBody(QStringLiteral("project"), form, &error).isEmpty());
    QVERIFY(!error.isEmpty());
}
void TestMissions::acceptanceAndRetryAreDifferentDecisions() {
    QVERIFY(MissionsViewModel::acceptanceAllowed(attempt(QStringLiteral("r"), QStringLiteral("succeeded"))));
    QVERIFY(!MissionsViewModel::retryAllowed(attempt(QStringLiteral("r"), QStringLiteral("succeeded"))));
    QVERIFY(MissionsViewModel::retryAllowed(attempt(QStringLiteral("r"), QStringLiteral("succeeded"), QStringLiteral("rejected"))));
    QVERIFY(!MissionsViewModel::acceptanceAllowed(attempt(QStringLiteral("r"), QStringLiteral("succeeded"), QStringLiteral("rejected"))));
    QVERIFY(!MissionsViewModel::retryAllowed(attempt(QStringLiteral("r"), QStringLiteral("running"))));
    auto invalid = attempt(QStringLiteral("r"), QStringLiteral("succeeded"));
    invalid.insert(QStringLiteral("technical_validation"), QJsonObject{{QStringLiteral("status"), QStringLiteral("failed")}});
    QVERIFY(!MissionsViewModel::acceptanceAllowed(invalid));
}
void TestMissions::staleProjectAndSessionRepliesCannotRepopulate() {
    HttpFixture server;
    server.handle = [](const Incoming&) {};
    ApiClient api; configure(api, server); AuthManager auth(&api); login(auth);
    EventStreamService streams(&api); noStreams(streams);
    MissionsViewModel vm(&api, &auth, &streams);
    vm.setProjectId(QStringLiteral("old"));
    QTRY_COMPARE(server.received.size(), 1);
    const Incoming old = server.received.first();
    vm.setProjectId(QStringLiteral("new"));
    QTRY_COMPARE(server.received.size(), 2);
    HttpFixture::reply(server.received.last(), QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("new-mission")}, {QStringLiteral("project_id"), QStringLiteral("new")}}});
    QTRY_COMPARE(vm.missions()->count(), 1);
    HttpFixture::reply(old, QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("old-mission")}, {QStringLiteral("project_id"), QStringLiteral("old")}}});
    QTest::qWait(40);
    QCOMPARE(vm.missions()->get(0).value(QStringLiteral("id")).toString(), QStringLiteral("new-mission"));
    vm.refresh(); QTRY_COMPARE(server.received.size(), 3);
    const Incoming pending = server.received.last();
    auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Fin du test"));
    HttpFixture::reply(pending, QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("new-mission")}, {QStringLiteral("project_id"), QStringLiteral("new")}}});
    QTest::qWait(40);
    QCOMPARE(vm.missions()->count(), 0);
    QVERIFY(!vm.canWrite());
}
void TestMissions::mutationUsesOnlyDeclaredIdempotency() {
    HttpFixture server;
    QJsonObject run = attempt(QStringLiteral("run"), QStringLiteral("succeeded"));
    server.handle = [&run](const Incoming& req) {
        if (req.target == "/missions/mission") HttpFixture::reply(req, detail(run));
        else if (req.target.endsWith("/test-run")) HttpFixture::reply(req, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Aucun test")}}, 404);
        else if (req.method == "POST") HttpFixture::reply(req, run);
        else HttpFixture::reply(req, QJsonArray{});
    };
    ApiClient api; configure(api, server); AuthManager auth(&api); login(auth);
    EventStreamService streams(&api); noStreams(streams);
    MissionsViewModel vm(&api, &auth, &streams); vm.setProjectId(QStringLiteral("project")); vm.selectMission(QStringLiteral("mission"));
    QTRY_VERIFY(vm.canAccept());
    vm.decideAcceptance(QStringLiteral("accepted"), QStringLiteral("Vérifié"));
    QTRY_VERIFY(!vm.mutating());
    QList<Incoming> posts;
    for (const auto& req : server.received) if (req.method == "POST") posts.append(req);
    QCOMPARE(posts.size(), 1);
    QCOMPARE(posts.first().target, QByteArray("/missions/mission/runs/run/acceptance"));
    QVERIFY(posts.first().headers.toLower().contains("x-csrf-token: csrf-fixture"));
    QVERIFY(!posts.first().headers.toLower().contains("idempotency-key:"));
    vm.addComment(QStringLiteral("Preuve relue"));
    QTRY_VERIFY(!vm.mutating());
    posts.clear(); for (const auto& req : server.received) if (req.method == "POST") posts.append(req);
    QCOMPARE(posts.size(), 2);
    QVERIFY(posts.last().headers.toLower().contains("idempotency-key:"));
    QCOMPARE(posts.last().body.value(QStringLiteral("run_id")).toString(), QStringLiteral("run"));
}
void TestMissions::projectViewerCannotMutate() {
    HttpFixture server;
    server.handle = [](const Incoming& req) { HttpFixture::reply(req, QJsonArray{}); };
    ApiClient api; configure(api, server); AuthManager auth(&api); login(auth, QStringLiteral("viewer"));
    EventStreamService streams(&api); noStreams(streams);
    MissionsViewModel vm(&api, &auth, &streams); vm.setProjectId(QStringLiteral("project"));
    QTRY_VERIFY(!vm.busy());
    QVERIFY(!vm.canWrite()); vm.stopMission();
    QVERIFY(!vm.error().isEmpty());
    for (const auto& req : server.received) QCOMPARE(req.method, QByteArray("GET"));
}
void TestMissions::staleRunTestsCannotReplaceCurrentResults() {
    HttpFixture server;
    Incoming delayed;
    auto run = attempt(QStringLiteral("run"), QStringLiteral("failed"));
    auto other = attempt(QStringLiteral("other"), QStringLiteral("succeeded"));
    auto mission = detail(other); mission.insert(QStringLiteral("runs"), QJsonArray{run, other});
    server.handle = [&](const Incoming& req) {
        if (req.target == "/missions/mission") HttpFixture::reply(req, mission);
        else if (req.target == "/runs/other/test-run") delayed = req;
        else if (req.target == "/runs/run/test-run") HttpFixture::reply(req, QJsonObject{{QStringLiteral("task_run_id"), QStringLiteral("run")}, {QStringLiteral("cases"), QJsonArray{}}});
        else HttpFixture::reply(req, QJsonArray{});
    };
    ApiClient api; configure(api, server); AuthManager auth(&api); login(auth);
    EventStreamService streams(&api); noStreams(streams);
    MissionsViewModel vm(&api, &auth, &streams); vm.setProjectId(QStringLiteral("project")); vm.selectMission(QStringLiteral("mission"));
    QTRY_VERIFY(delayed.socket);
    vm.selectRun(QStringLiteral("run"));
    QTRY_COMPARE(vm.testReport().value(QStringLiteral("task_run_id")).toString(), QStringLiteral("run"));
    HttpFixture::reply(delayed, QJsonObject{{QStringLiteral("task_run_id"), QStringLiteral("other")}, {QStringLiteral("cases"), QJsonArray{}}});
    QTest::qWait(40);
    QCOMPARE(vm.testReport().value(QStringLiteral("task_run_id")).toString(), QStringLiteral("run"));
    QVERIFY(!vm.canRetry()); // Ancienne tentative : la commande concerne seulement la courante.
}
namespace {
QVariantMap validForm() {
    return {{QStringLiteral("title"), QStringLiteral("Mission")}, {QStringLiteral("objective"), QStringLiteral("Objectif")},
        {QStringLiteral("expected_outcome"), QStringLiteral("Résultat")}, {QStringLiteral("acceptance_criteria"), QStringLiteral("Vérification")},
        {QStringLiteral("max_cost"), QStringLiteral("1.25")}, {QStringLiteral("duration_seconds"), 900}};
}
QByteArray commandKey(const Incoming &request) {
    for (const auto &line : request.headers.split('\n'))
        if (line.toLower().startsWith("idempotency-key:")) return line.mid(16).trimmed();
    return {};
}
}

void TestMissions::ambiguousCommandReusesItsKeyAndBody_data() {
    QTest::addColumn<QString>("action");
    QTest::newRow("creation") << QStringLiteral("create");
    QTest::newRow("arret") << QStringLiteral("stop");
    QTest::newRow("relance") << QStringLiteral("retry");
}
void TestMissions::ambiguousCommandReusesItsKeyAndBody() {
    QFETCH(QString, action);
    HttpFixture server;
    bool returnResponse = false;
    QSet<QByteArray> committed;
    QList<Incoming> posts;
    auto run = attempt(QStringLiteral("run"), action == QLatin1String("retry") ? QStringLiteral("failed") : QStringLiteral("running"));
    server.handle = [&](const Incoming &req) {
        if (req.method == "POST") {
            posts.append(req);
            committed.insert(commandKey(req)); // Le serveur a validé, même si sa réponse est perdue.
            if (returnResponse) {
                if (action == QLatin1String("create")) HttpFixture::reply(req, detail(run), 201);
                else if (action == QLatin1String("stop")) HttpFixture::reply(req, QJsonObject{{QStringLiteral("mission_id"), QStringLiteral("mission")},
                    {QStringLiteral("run"), run}, {QStringLiteral("already_stopped"), true}});
                else HttpFixture::reply(req, run, 201);
            } else req.socket->abort();
        } else if (req.target == "/missions/mission") HttpFixture::reply(req, detail(run));
        else if (req.target.endsWith("/test-run")) HttpFixture::reply(req, QJsonObject{}, 404);
        else HttpFixture::reply(req, QJsonArray{});
    };
    ApiClient api; configure(api, server); AuthManager auth(&api); login(auth);
    EventStreamService streams(&api); noStreams(streams);
    MissionsViewModel vm(&api, &auth, &streams); vm.setProjectId(QStringLiteral("project"));
    QTRY_VERIFY(vm.canWrite());
    if (action != QLatin1String("create")) {
        vm.selectMission(QStringLiteral("mission"));
        QTRY_VERIFY(action == QLatin1String("retry") ? vm.canRetry() : vm.canStop());
    }
    if (action == QLatin1String("create")) vm.createMission(validForm());
    else if (action == QLatin1String("stop")) vm.stopMission();
    else vm.retryMission(QStringLiteral("Motif immuable"));
    QTRY_VERIFY_WITH_TIMEOUT(vm.pendingMutation() && !vm.mutating(), 10000);
    QVERIFY(posts.size() >= 3);
    QVERIFY(vm.canRetryPending());
    QVERIFY(!vm.canWrite()); QVERIFY(!vm.canStop()); QVERIFY(!vm.canRetry());
    const auto original = posts.first();
    QVERIFY(!commandKey(original).isEmpty());
    const auto count = posts.size();
    auto changed = validForm(); changed.insert(QStringLiteral("title"), QStringLiteral("Autre mission"));
    vm.createMission(changed); vm.stopMission(); vm.retryMission(QStringLiteral("Autre motif"));
    QCOMPARE(posts.size(), count);
    // Une rotation de CSRF à identité constante ne doit pas effacer la commande.
    login(auth);
    QVERIFY(vm.pendingMutation());
    returnResponse = true;
    vm.retryPending();
    QTRY_VERIFY(!vm.pendingMutation() && !vm.mutating());
    QVERIFY(posts.size() > count);
    QCOMPARE(committed.size(), 1);
    for (const auto &post : posts) {
        QCOMPARE(commandKey(post), commandKey(original));
        QCOMPARE(post.target, original.target);
        QCOMPARE(post.body, original.body);
    }
}

void TestMissions::changingContextCancelsPendingCommandAndRetries() {
    HttpFixture server;
    int posts = 0;
    Incoming delayed;
    server.handle = [&](const Incoming &req) {
        if (req.method == "POST") { ++posts; delayed = req; }
        else HttpFixture::reply(req, QJsonArray{});
    };
    ApiClient api; configure(api, server); AuthManager auth(&api); login(auth);
    EventStreamService streams(&api); noStreams(streams);
    MissionsViewModel vm(&api, &auth, &streams); vm.setProjectId(QStringLiteral("old"));
    QTRY_VERIFY(vm.canWrite());
    vm.createMission(validForm());
    QTRY_COMPARE(posts, 1);
    QVERIFY(vm.pendingMutation());
    vm.setProjectId(QStringLiteral("new"));
    QVERIFY(!vm.pendingMutation());
    QVERIFY(!vm.mutating());
    vm.retryPending();
    HttpFixture::reply(delayed, detail(attempt(QStringLiteral("run"), QStringLiteral("running"))));
    QTRY_VERIFY(!vm.busy());
    QTest::qWait(700);
    QCOMPARE(posts, 1);
    QVERIFY(vm.selectedMissionId().isEmpty());
}

void TestMissions::abandoningRequiresExplicitDuplicateRiskAcknowledgement() {
    HttpFixture server;
    server.handle = [](const Incoming &req) {
        if (req.method == "POST") req.socket->abort();
        else HttpFixture::reply(req, QJsonArray{});
    };
    ApiClient api; configure(api, server); AuthManager auth(&api); login(auth);
    EventStreamService streams(&api); noStreams(streams);
    MissionsViewModel vm(&api, &auth, &streams); vm.setProjectId(QStringLiteral("project"));
    QTRY_VERIFY(vm.canWrite());
    vm.createMission(validForm());
    QTRY_VERIFY_WITH_TIMEOUT(vm.pendingMutation() && !vm.mutating(), 10000);
    vm.abandonPending(false);
    QVERIFY(vm.pendingMutation());
    QVERIFY(!vm.canWrite());
    vm.abandonPending(true);
    QVERIFY(!vm.pendingMutation());
    QVERIFY(vm.canWrite());
    QVERIFY(vm.notice().contains(QStringLiteral("doublon")));
}

QTEST_MAIN(TestMissions)
#include "tst_missions.moc"
