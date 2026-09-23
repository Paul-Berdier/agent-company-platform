#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"
#include "models/JsonListModel.h"
#include "viewmodels/PlatformViewModel.h"

#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkCookie>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <QTimer>

#include <functional>
#include <memory>

using namespace acp;
namespace {
struct Request {
    QByteArray method;
    QByteArray path;
    QByteArray headers;
    QJsonObject body;
};
struct Response {
    QJsonDocument json;
    int status = 200;
    int delayMs = 0;
    QByteArray sessionCookie;
};
class PlatformServer : public QObject
{
public:
    QTcpServer server;
    QList<Request> requests;
    std::function<Response(const Request &)> handler;
    PlatformServer()
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
                    const auto headers = buffer->left(end);
                    qsizetype size = 0;
                    for (const auto &line : headers.split('\n')) {
                        if (line.toLower().startsWith("content-length:")) {
                            size = line.mid(15).trimmed().toLongLong();
                        }
                    }
                    if (buffer->size() < end + 4 + size) { return; }
                    *answered = true;
                    const auto first = headers.split('\n').first().trimmed().split(' ');
                    Request req{first.value(0), first.value(1), headers,
                        QJsonDocument::fromJson(buffer->mid(end + 4, size)).object()};
                    requests.append(req);
                    const auto reply = handler(req);
                    QTimer::singleShot(reply.delayMs, socket, [socket, reply] {
                        const auto body = reply.json.toJson(QJsonDocument::Compact);
                        const QByteArray cookie = reply.sessionCookie.isEmpty() ? QByteArray()
                            : "Set-Cookie: acp_session=" + reply.sessionCookie + "; Path=/; HttpOnly; SameSite=Strict\r\n";
                        socket->write("HTTP/1.1 " + QByteArray::number(reply.status)
                            + " Result\r\nContent-Type: application/json\r\nConnection: close\r\n" + cookie + "Content-Length: "
                            + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                        socket->disconnectFromHost();
                    });
                });
            }
        });
    }
    bool start() { return server.listen(QHostAddress::LocalHost, 0); }
    QUrl url() const { return QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort())); }
};
void authenticate(AuthManager &auth, const QString &role = QStringLiteral("owner"))
{
    auth.applySessionPayload({{QStringLiteral("authenticated"), true},
        {QStringLiteral("csrf_token"), QStringLiteral("csrf-test")},
        {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00+00:00")},
        {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("alice")},
            {QStringLiteral("display_name"), QStringLiteral("Alice")}, {QStringLiteral("role"), role}}}});
}
JsonListModel *model(QObject *value) { return qobject_cast<JsonListModel *>(value); }
QJsonObject summary(const QString &id)
{
    return {{QStringLiteral("id"), id}, {QStringLiteral("name"), id},
        {QStringLiteral("status"), QStringLiteral("active")}, {QStringLiteral("current_revision_number"), 2}};
}
QJsonObject revision(const QString &id, int number, const QString &tool)
{
    return {{QStringLiteral("id"), id}, {QStringLiteral("number"), number},
        {QStringLiteral("config"), QJsonObject{{QStringLiteral("private"), QStringLiteral("must-never-reach-qml")}}},
        {QStringLiteral("discovery"), QJsonObject{{QStringLiteral("tools"), QJsonArray{QJsonObject{
            {QStringLiteral("name"), tool}, {QStringLiteral("description"), QStringLiteral("<img src='https://example.invalid'>")}}}}}}};
}
QJsonObject binding(bool mcp = true)
{
    return {{QStringLiteral("id"), QStringLiteral("binding-a")},
        {mcp ? QStringLiteral("server_id") : QStringLiteral("skill_id"), mcp ? QStringLiteral("mcp-a") : QStringLiteral("skill-a")},
        {QStringLiteral("project_id"), QStringLiteral("project-a")},
        {QStringLiteral("revision_id"), QStringLiteral("revision-one")},
        {QStringLiteral("revision_number"), 1}, {QStringLiteral("enabled"), true},
        {QStringLiteral("revoked_at"), QJsonValue(QJsonValue::Null)},
        {QStringLiteral("allowed_tools"), QJsonArray{QStringLiteral("old_tool")}}};
}
QJsonObject detail(bool mcp = true, bool linked = false)
{
    auto object = summary(mcp ? QStringLiteral("mcp-a") : QStringLiteral("skill-a"));
    const auto current = revision(QStringLiteral("revision-two"), 2, QStringLiteral("new_tool"));
    object.insert(QStringLiteral("current_revision"), current);
    object.insert(QStringLiteral("revisions"), QJsonArray{revision(QStringLiteral("revision-one"), 1, QStringLiteral("old_tool")), current});
    object.insert(QStringLiteral("bindings"), linked ? QJsonArray{binding(mcp)} : QJsonArray{});
    return object;
}
QJsonObject membership(const QString &scope, const QString &id, const QString &role,
                       const QString &user = QStringLiteral("alice"))
{
    return {{QStringLiteral("user_id"), user}, {QStringLiteral("scope_type"), scope},
        {QStringLiteral("scope_id"), id}, {QStringLiteral("role"), role}};
}
Response projectContext()
{
    return {QJsonDocument(QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("project-a")},
        {QStringLiteral("workspace_id"), QStringLiteral("workspace-a")}}})};
}
Response readResponse(const Request &req)
{
    if (req.path == "/connections/hermes/diagnostic") {
        return {QJsonDocument(QJsonObject{{QStringLiteral("status"), QStringLiteral("unavailable")},
            {QStringLiteral("healthy"), false}, {QStringLiteral("message"), QStringLiteral("Non configuré")}})};
    }
    if (req.path == "/mcp/servers") { return {QJsonDocument(QJsonArray{summary(QStringLiteral("mcp-a"))})}; }
    if (req.path == "/skills") { return {QJsonDocument(QJsonArray{summary(QStringLiteral("skill-a"))})}; }
    if (req.path == "/mcp/servers/mcp-a") { return {QJsonDocument(detail())}; }
    if (req.path == "/skills/skill-a") { return {QJsonDocument(detail(false))}; }
    return {QJsonDocument(QJsonArray{})};
}
} // namespace

class TestPlatform : public QObject
{
    Q_OBJECT
private slots:
    void activationBeforeLoginLoadsAfterIdentityConfirmation();
    void inventoryUsesPublicFieldsAndHonestProviderStatus();
    void pinnedToolsBindingsAndActivationUseRealTransport();
    void projectBindingsRequireScopedMembership_data();
    void projectBindingsRequireScopedMembership();
    void permissionsAndServerRefusalsStayClosed();
    void staleProjectSessionAndOriginResponsesAreDiscarded();
    void malformedListIsAnError();
};

void TestPlatform::activationBeforeLoginLoadsAfterIdentityConfirmation()
{
    PlatformServer server;
    QVERIFY(server.start());
    bool authenticatedRead = false;
    server.handler = [&](const Request &req) {
        if (req.path == "/auth/login" && req.method == "POST") {
            return Response{QJsonDocument(QJsonObject{
                {QStringLiteral("authenticated"), true},
                {QStringLiteral("csrf_token"), QStringLiteral("csrf-test")},
                {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00Z")},
                {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("alice")},
                    {QStringLiteral("display_name"), QStringLiteral("Alice")},
                    {QStringLiteral("role"), QStringLiteral("owner")}}}}), 200, 0,
                QByteArrayLiteral("real-login-cookie-0123456789")};
        }
        if (req.path == "/skills") {
            authenticatedRead = req.headers.toLower().contains("cookie: acp_session=real-login-cookie-0123456789");
        }
        return readResponse(req);
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    PlatformViewModel vm(&client, &auth);
    vm.setActive(true);
    QVERIFY(server.requests.isEmpty());
    bool pendingIdentityObserved = false;
    connect(&auth, &AuthManager::userChanged, &vm, [&] {
        if (auth.state() == SessionStatus::Connecting && !auth.userId().isEmpty()) {
            pendingIdentityObserved = true;
            QVERIFY(!vm.available());
            QCOMPARE(model(vm.skills())->count(), 0);
        }
    });
    auth.logIn(QStringLiteral("alice"), QStringLiteral("test-password"));
    QTRY_COMPARE(auth.state(), SessionStatus::Connected);
    QVERIFY(pendingIdentityObserved);
    QVERIFY(client.cookieJar()->hasSessionCookie());
    QTRY_COMPARE(model(vm.skills())->count(), 1);
    QTRY_VERIFY(!vm.loading());
    QVERIFY(authenticatedRead);
    QVERIFY(vm.available());
}

void TestPlatform::inventoryUsesPublicFieldsAndHonestProviderStatus()
{
    PlatformServer server;
    QVERIFY(server.start());
    server.handler = [](const Request &req) {
        if (req.path == "/workers" || req.path == "/agents") {
            auto row = summary(QStringLiteral("worker-a"));
            row.insert(QStringLiteral("status"), QStringLiteral("offline"));
            row.insert(QStringLiteral("capabilities"), QJsonArray{QStringLiteral("codex_cli")});
            row.insert(QStringLiteral("config"), QJsonObject{{QStringLiteral("secret"), QStringLiteral("do-not-expose")}});
            row.insert(QStringLiteral("metadata"), row.value(QStringLiteral("config")));
            return Response{QJsonDocument(QJsonArray{row})};
        }
        return readResponse(req);
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth);
    PlatformViewModel vm(&client, &auth);
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    QCOMPARE(model(vm.agents())->count(), 1);
    QVERIFY(!model(vm.agents())->get(0).contains(QStringLiteral("config")));
    QVERIFY(!model(vm.workers())->get(0).contains(QStringLiteral("metadata")));
    QCOMPARE(model(vm.providers())->count(), 3);
    QVERIFY(model(vm.providers())->get(0).value(QStringLiteral("state")).toString().contains(QStringLiteral("Indisponible")));
    const auto codex = model(vm.providers())->get(1).value(QStringLiteral("state")).toString();
    QVERIFY(codex.contains(QStringLiteral("offline")));
    QVERIFY(codex.contains(QStringLiteral("inconnue")));
    QVERIFY(model(vm.providers())->get(2).value(QStringLiteral("state")).toString().contains(QStringLiteral("Aucun worker")));
}

void TestPlatform::pinnedToolsBindingsAndActivationUseRealTransport()
{
    PlatformServer server;
    QVERIFY(server.start());
    QJsonObject mcp = detail(true, true);
    QJsonObject skill = detail(false);
    QList<Request> mutations;
    server.handler = [&](const Request &req) {
        if (req.method != "GET") {
            mutations.append(req);
            if (req.path == "/mcp/bindings/binding-a") { return Response{QJsonDocument(binding())}; }
            if (req.path == "/skills/skill-a/bindings") {
                skill.insert(QStringLiteral("bindings"), QJsonArray{binding(false)});
                return Response{QJsonDocument(binding(false)), 201};
            }
            if (req.path == "/skills/bindings/binding-a") {
                skill.insert(QStringLiteral("bindings"), QJsonArray{});
                return Response{QJsonDocument(binding(false))};
            }
            if (req.path == "/mcp/servers/mcp-a/disable") {
                mcp.insert(QStringLiteral("status"), QStringLiteral("disabled"));
                return Response{QJsonDocument(mcp)};
            }
        }
        if (req.path == "/mcp/servers/mcp-a") { return Response{QJsonDocument(mcp)}; }
        if (req.path == "/skills/skill-a") { return Response{QJsonDocument(skill)}; }
        return readResponse(req);
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth);
    PlatformViewModel vm(&client, &auth);
    vm.setProjectId(QStringLiteral("project-a"));
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    vm.selectMcp(QStringLiteral("mcp-a"));
    vm.selectSkill(QStringLiteral("skill-a"));
    QTRY_VERIFY(!vm.loading());
    QCOMPARE(model(vm.mcpTools())->count(), 1);
    QCOMPARE(model(vm.mcpTools())->get(0).value(QStringLiteral("name")).toString(), QStringLiteral("old_tool"));
    QVERIFY(!vm.selectedMcp().contains(QStringLiteral("current_revision")));
    QVERIFY(!vm.selectedMcp().value(QStringLiteral("versions")).toList().first().toMap().contains(QStringLiteral("config")));
    vm.toggleTool(QStringLiteral("new_tool"), true);
    vm.saveMcpBinding();
    QTRY_VERIFY(!vm.loading() && !vm.busy());
    QCOMPARE(mutations.size(), 1);
    QCOMPARE(mutations.last().method, QByteArray("PATCH"));
    QCOMPARE(mutations.last().body.value(QStringLiteral("allowed_tools")).toArray(), QJsonArray{QStringLiteral("old_tool")});
    QVERIFY(mutations.last().headers.toLower().contains("x-csrf-token: csrf-test"));
    QVERIFY(!mutations.last().headers.toLower().contains("idempotency-key:"));
    vm.setMcpBindingEnabled(false);
    QTRY_VERIFY(!vm.loading() && !vm.busy());
    QCOMPARE(mutations.last().body.value(QStringLiteral("enabled")).toBool(), false);
    vm.bindSkill();
    QTRY_VERIFY(!vm.loading() && !vm.busy());
    QCOMPARE(mutations.last().body.value(QStringLiteral("project_id")).toString(), QStringLiteral("project-a"));
    QVERIFY(vm.selectedSkill().value(QStringLiteral("binding")).toMap().contains(QStringLiteral("id")));
    vm.removeSkillBinding();
    QTRY_VERIFY(!vm.loading() && !vm.busy());
    QCOMPARE(mutations.last().method, QByteArray("DELETE"));
    vm.setMcpActive(false);
    QTRY_VERIFY(!vm.loading() && !vm.busy());
    QCOMPARE(vm.selectedMcp().value(QStringLiteral("status")).toString(), QStringLiteral("disabled"));
    QVERIFY(vm.error().isEmpty());
}

void TestPlatform::permissionsAndServerRefusalsStayClosed()
{
    PlatformServer server;
    QVERIFY(server.start());
    int mutations = 0;
    server.handler = [&](const Request &req) {
        if (req.path.startsWith("/memberships?")) {
            // Un droit lu précédemment peut être révoqué côté serveur entre-temps.
            return Response{QJsonDocument(QJsonArray{membership(QStringLiteral("project"),
                QStringLiteral("project-a"), QStringLiteral("member"))})};
        }
        if (req.path == "/projects") { return projectContext(); }
        if (req.path == "/auth/session") {
            return Response{QJsonDocument(QJsonObject{
                {QStringLiteral("authenticated"), true},
                {QStringLiteral("csrf_token"), QStringLiteral("refreshed-csrf")},
                {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00+00:00")},
                {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("alice")},
                    {QStringLiteral("display_name"), QStringLiteral("Alice")},
                    {QStringLiteral("role"), QStringLiteral("viewer")}}}})};
        }
        if (req.method != "GET") {
            ++mutations;
            return Response{QJsonDocument(QJsonObject{{QStringLiteral("detail"), QStringLiteral("Rôle membre requis")}}), 403};
        }
        return readResponse(req);
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth, QStringLiteral("viewer"));
    // Une session réelle possède un cookie : le 403 relit alors /auth/session.
    // Sans lui, la fixture simulait à tort une identité connectée sans session.
    QNetworkCookie cookie(QByteArrayLiteral("acp_session"), QByteArrayLiteral("session-test-0123456789"));
    cookie.setHttpOnly(true);
    cookie.setPath(QStringLiteral("/"));
    QVERIFY(client.cookieJar()->setCookiesFromUrl({cookie}, server.url()));
    PlatformViewModel vm(&client, &auth);
    vm.setProjectId(QStringLiteral("project-a"));
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    QVERIFY(vm.canManageProjectBindings());
    QVERIFY(!vm.workersNotice().isEmpty());
    for (const auto &req : server.requests) { QVERIFY(req.path != "/workers"); }
    vm.selectSkill(QStringLiteral("skill-a"));
    QTRY_VERIFY(!vm.loading());
    vm.setSkillActive(true);
    QCOMPARE(mutations, 0);
    QVERIFY(vm.error().contains(QStringLiteral("propriétaire")));
    bool resumed = false;
    connect(&auth, &AuthManager::stateChanged, &vm, [&] {
        if (auth.state() == SessionStatus::Connecting) {
            resumed = true;
            QVERIFY(!vm.available());
        }
    });
    vm.bindSkill();
    QTRY_VERIFY(!vm.loading() && !vm.busy());
    QCOMPARE(mutations, 1);
    QTRY_COMPARE(auth.state(), SessionStatus::Connected);
    QVERIFY(resumed);
    QVERIFY(vm.error().contains(QStringLiteral("Rôle membre requis")));
    QVERIFY(vm.notice().isEmpty());
    QCOMPARE(vm.selectedSkill().value(QStringLiteral("id")).toString(), QStringLiteral("skill-a"));
    QVERIFY(vm.selectedSkill().value(QStringLiteral("binding")).toMap().isEmpty());
}

void TestPlatform::projectBindingsRequireScopedMembership_data()
{
    QTest::addColumn<QString>("scope");
    QTest::addColumn<QString>("scopeId");
    QTest::addColumn<QString>("role");
    QTest::addColumn<QString>("user");
    QTest::addColumn<bool>("allowed");
    QTest::newRow("project-viewer") << QStringLiteral("project") << QStringLiteral("project-a")
        << QStringLiteral("viewer") << QStringLiteral("alice") << false;
    QTest::newRow("workspace-viewer") << QStringLiteral("workspace") << QStringLiteral("workspace-a")
        << QStringLiteral("viewer") << QStringLiteral("alice") << false;
    QTest::newRow("project-member") << QStringLiteral("project") << QStringLiteral("project-a")
        << QStringLiteral("member") << QStringLiteral("alice") << true;
    QTest::newRow("inherited-workspace-member") << QStringLiteral("workspace") << QStringLiteral("workspace-a")
        << QStringLiteral("member") << QStringLiteral("alice") << true;
    QTest::newRow("inherited-workspace-operator") << QStringLiteral("workspace") << QStringLiteral("workspace-a")
        << QStringLiteral("operator") << QStringLiteral("alice") << true;
    QTest::newRow("inherited-workspace-owner") << QStringLiteral("workspace") << QStringLiteral("workspace-a")
        << QStringLiteral("owner") << QStringLiteral("alice") << true;
    QTest::newRow("other-project") << QStringLiteral("project") << QStringLiteral("project-b")
        << QStringLiteral("owner") << QStringLiteral("alice") << false;
    QTest::newRow("other-workspace") << QStringLiteral("workspace") << QStringLiteral("workspace-b")
        << QStringLiteral("owner") << QStringLiteral("alice") << false;
    QTest::newRow("other-user") << QStringLiteral("project") << QStringLiteral("project-a")
        << QStringLiteral("owner") << QStringLiteral("bob") << false;
}

void TestPlatform::projectBindingsRequireScopedMembership()
{
    QFETCH(QString, scope);
    QFETCH(QString, scopeId);
    QFETCH(QString, role);
    QFETCH(QString, user);
    QFETCH(bool, allowed);
    PlatformServer server;
    QVERIFY(server.start());
    int mutations = 0;
    server.handler = [&](const Request &req) {
        if (req.path.startsWith("/memberships?")) {
            return Response{QJsonDocument(QJsonArray{membership(scope, scopeId, role, user)})};
        }
        if (req.path == "/projects") { return projectContext(); }
        if (req.method != "GET") {
            ++mutations;
            return Response{QJsonDocument(binding(false)), 201};
        }
        if (req.path == "/mcp/servers/mcp-a") { return Response{QJsonDocument(detail(true, true))}; }
        return readResponse(req);
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth, QStringLiteral("viewer"));
    PlatformViewModel vm(&client, &auth);
    vm.setProjectId(QStringLiteral("project-a"));
    vm.setActive(true);
    QVERIFY(!vm.canManageProjectBindings());
    QTRY_VERIFY(!vm.loading());
    QCOMPARE(vm.canManageProjectBindings(), allowed);
    QCOMPARE(vm.bindingPermissionReason().isEmpty(), allowed);
    vm.selectSkill(QStringLiteral("skill-a"));
    vm.selectMcp(QStringLiteral("mcp-a"));
    QTRY_VERIFY(!vm.loading());
    if (!allowed) {
        vm.toggleTool(QStringLiteral("old_tool"), false);
        QCOMPARE(model(vm.mcpTools())->get(0).value(QStringLiteral("selected")).toBool(), true);
        vm.saveMcpBinding();
        vm.setMcpBindingEnabled(false);
        vm.removeMcpBinding();
        vm.removeSkillBinding();
    }
    vm.bindSkill();
    QTRY_VERIFY(!vm.loading() && !vm.busy());
    QCOMPARE(mutations, allowed ? 1 : 0);
    if (!allowed) { QVERIFY(vm.error().contains(QStringLiteral("Rôle membre"))); }
    else { QVERIFY(vm.error().isEmpty()); }
    vm.setProjectId(QStringLiteral("project-b"));
    QVERIFY(!vm.canManageProjectBindings());
    auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Test"));
    QVERIFY(!vm.canManageProjectBindings());
}

void TestPlatform::staleProjectSessionAndOriginResponsesAreDiscarded()
{
    PlatformServer server;
    QVERIFY(server.start());
    server.handler = [](const Request &req) {
        auto reply = readResponse(req);
        if (req.path == "/mcp/servers/mcp-a") { reply.delayMs = 200; }
        return reply;
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth);
    PlatformViewModel vm(&client, &auth);
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    vm.selectMcp(QStringLiteral("mcp-a"));
    QTRY_VERIFY(server.requests.last().path == "/mcp/servers/mcp-a");
    vm.setProjectId(QStringLiteral("project-b"));
    QTRY_VERIFY(!vm.loading());
    QTest::qWait(250);
    QVERIFY(vm.selectedMcp().isEmpty());
    QCOMPARE(model(vm.mcpTools())->count(), 0);
    auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Test"));
    QCOMPARE(model(vm.agents())->count(), 0);
    QCOMPARE(model(vm.providers())->count(), 0);
    authenticate(auth);
    QTRY_VERIFY(!vm.loading());
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:1"))).isError());
    QVERIFY(!vm.available());
    QCOMPARE(model(vm.skills())->count(), 0);
    const auto count = server.requests.size();
    vm.bindSkill();
    QCOMPARE(server.requests.size(), count);
    QVERIFY(!vm.error().isEmpty());
}

void TestPlatform::malformedListIsAnError()
{
    PlatformServer server;
    QVERIFY(server.start());
    server.handler = [](const Request &req) {
        return req.path == "/skills" ? Response{QJsonDocument(QJsonObject{})} : readResponse(req);
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth);
    PlatformViewModel vm(&client, &auth);
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    QVERIFY(vm.error().contains(QStringLiteral("invalide")));
    QCOMPARE(model(vm.skills())->count(), 0);
}

QTEST_GUILESS_MAIN(TestPlatform)
#include "tst_platform.moc"
