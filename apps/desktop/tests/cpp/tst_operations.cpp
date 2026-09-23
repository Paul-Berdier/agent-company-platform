#include "viewmodels/OperationsViewModel.h"
#include "auth/AuthManager.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <QUrlQuery>
#include <functional>
#include <memory>

using namespace acp;

struct OperationRequest {
    QByteArray method;
    QUrl url;
    QJsonObject body;
    QHash<QByteArray, QByteArray> headers;
};
class OperationsHttp : public QObject
{
public:
    QTcpServer server;
    QList<OperationRequest> requests;
    std::function<bool(QTcpSocket*, const OperationRequest&)> intercept;
    QJsonArray memberships;
    QString role = QStringLiteral("owner");
    bool decided = false, acknowledged = false, enabled = false;
    OperationsHttp()
    {
        if (!server.listen(QHostAddress::LocalHost, 0)) qFatal("Serveur local inaccessible");
        connect(&server, &QTcpServer::newConnection, this, [this] {
            while (server.hasPendingConnections()) {
                auto* socket = server.nextPendingConnection();
                auto data = std::make_shared<QByteArray>();
                auto handled = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, data, handled] {
                    data->append(socket->readAll());
                    const qsizetype end = data->indexOf("\r\n\r\n");
                    if (*handled || end < 0) return;
                    const auto lines = data->left(end).split('\n');
                    const auto first = lines.first().trimmed().split(' ');
                    OperationRequest request;
                    request.method = first.value(0);
                    request.url = QUrl(QStringLiteral("http://localhost") + QString::fromUtf8(first.value(1)));
                    for (qsizetype i = 1; i < lines.size(); ++i) {
                        const qsizetype colon = lines[i].indexOf(':');
                        if (colon > 0) request.headers.insert(lines[i].left(colon).trimmed().toLower(), lines[i].mid(colon + 1).trimmed());
                    }
                    const qint64 length = request.headers.value(QByteArrayLiteral("content-length")).toLongLong();
                    if (data->size() - end - 4 < length) return;
                    request.body = QJsonDocument::fromJson(data->mid(end + 4, length)).object();
                    *handled = true; requests.append(request);
                    if (!intercept || !intercept(socket, request)) respond(socket, request);
                });
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            }
        });
    }
    QUrl origin() const { return QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort())); }
    static void reply(QTcpSocket* socket, const QJsonDocument& body, int status = 200)
    {
        const auto bytes = body.toJson(QJsonDocument::Compact);
        socket->write("HTTP/1.1 " + QByteArray::number(status) + " Result\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                      + QByteArray::number(bytes.size()) + "\r\n\r\n" + bytes);
        socket->disconnectFromHost();
    }
    static QJsonObject policy(const QString& project)
    {
        return {{QStringLiteral("project_id"), project}, {QStringLiteral("timezone"), QStringLiteral("America/Montreal")}, {QStringLiteral("updated_at"), QStringLiteral("2026-09-23T00:00:00Z")},
                {QStringLiteral("daily_budget"), QJsonObject{{QStringLiteral("max_cost"), 12.5}, {QStringLiteral("currency"), QStringLiteral("CAD")}, {QStringLiteral("max_tokens"), QJsonValue::Null}, {QStringLiteral("max_tool_calls"), 99}}},
                {QStringLiteral("provider_budgets"), QJsonArray{QJsonObject{{QStringLiteral("provider"), QStringLiteral("local")}, {QStringLiteral("budget"), QJsonObject{{QStringLiteral("max_cost"), QJsonValue::Null},
                    {QStringLiteral("currency"), QStringLiteral("EUR")}, {QStringLiteral("max_tokens"), 1000}, {QStringLiteral("max_tool_calls"), QJsonValue::Null}}}}}},
                {QStringLiteral("max_concurrent_missions"), 4}, {QStringLiteral("max_retries_per_mission"), 0}, {QStringLiteral("max_spawned_agents_per_run"), 3}};
    }
    static QJsonObject routine(const QString& project)
    {
        return {{QStringLiteral("id"), QStringLiteral("routine-1")}, {QStringLiteral("project_id"), project}, {QStringLiteral("name"), QStringLiteral("Routine")}, {QStringLiteral("enabled"), false},
            {QStringLiteral("schedule"), QJsonObject{{QStringLiteral("kind"), QStringLiteral("interval")}, {QStringLiteral("expression"), QStringLiteral("3600")}, {QStringLiteral("timezone"), QStringLiteral("Europe/Paris")}}}};
    }
    void respond(QTcpSocket* socket, const OperationRequest& request)
    {
        const QString path = request.url.path();
        const QString project = QUrlQuery(request.url).queryItemValue(QStringLiteral("project_id"));
        if (path == QLatin1String("/memberships")) reply(socket, QJsonDocument(memberships));
        else if (path == QLatin1String("/projects")) reply(socket, QJsonDocument(QJsonArray{
            QJsonObject{{QStringLiteral("id"), QStringLiteral("p1")}, {QStringLiteral("workspace_id"), QStringLiteral("w1")}}, QJsonObject{{QStringLiteral("id"), QStringLiteral("p2")}, {QStringLiteral("workspace_id"), QStringLiteral("w2")}}}));
        else if (path == QLatin1String("/approvals")) reply(socket, QJsonDocument(decided ? QJsonArray{} : QJsonArray{
            QJsonObject{{QStringLiteral("id"), QStringLiteral("approval-1")}, {QStringLiteral("project_id"), project}, {QStringLiteral("status"), QStringLiteral("WAITING_APPROVAL")}, {QStringLiteral("action"), QStringLiteral("deploy")}, {QStringLiteral("reason"), QStringLiteral("Valider")}}}));
        else if (path == QLatin1String("/alerts")) reply(socket, QJsonDocument(acknowledged ? QJsonArray{} : QJsonArray{
            QJsonObject{{QStringLiteral("id"), QStringLiteral("alert-1")}, {QStringLiteral("project_id"), project}, {QStringLiteral("acknowledged_at"), QJsonValue::Null}, {QStringLiteral("title"), QStringLiteral("Limite")}}}));
        else if (path == QLatin1String("/automations")) {
            auto row = routine(project); row[QStringLiteral("enabled")] = enabled;
            reply(socket, QJsonDocument(QJsonArray{row}));
        } else if (path.endsWith(QLatin1String("/budget-policy"))) {
            const QString id = path.split(QLatin1Char('/')).value(2);
            auto row = request.method == "PUT" ? request.body : policy(id);
            row[QStringLiteral("project_id")] = id; row[QStringLiteral("updated_at")] = QStringLiteral("2026-09-23T00:00:00Z");
            reply(socket, QJsonDocument(row));
        } else if (path.endsWith(QLatin1String("/budget-usage"))) reply(socket, QJsonDocument(QJsonObject{
            {QStringLiteral("project_id"), path.split(QLatin1Char('/')).value(2)}, {QStringLiteral("accounting_day"), QStringLiteral("2026-09-23")}, {QStringLiteral("timezone"), QStringLiteral("America/Montreal")},
            {QStringLiteral("totals"), QJsonObject{{QStringLiteral("cost"), QJsonValue::Null}, {QStringLiteral("tokens_input"), QJsonValue::Null}, {QStringLiteral("tool_calls"), 0}}}}));
        else if (path.endsWith(QLatin1String("/decision"))) {
            decided = true; reply(socket, QJsonDocument(QJsonObject{{QStringLiteral("id"), QStringLiteral("approval-1")}, {QStringLiteral("project_id"), QStringLiteral("p1")}, {QStringLiteral("status"), request.body.value(QStringLiteral("decision"))}}));
        } else if (path.endsWith(QLatin1String("/acknowledge"))) {
            acknowledged = true; reply(socket, QJsonDocument(QJsonObject{{QStringLiteral("id"), QStringLiteral("alert-1")}, {QStringLiteral("project_id"), QStringLiteral("p1")}, {QStringLiteral("acknowledged_at"), QStringLiteral("2026-09-23T00:00:00Z")}}));
        } else if (path.endsWith(QLatin1String("/automations")) && request.method == "POST") {
            auto row = request.body; row[QStringLiteral("id")] = QStringLiteral("new-routine");
            row[QStringLiteral("project_id")] = path.split(QLatin1Char('/')).value(2); row[QStringLiteral("enabled")] = false;
            reply(socket, QJsonDocument(row), 201);
        } else if (path.endsWith(QLatin1String("/runs"))) reply(socket, QJsonDocument(QJsonArray{QJsonObject{
            {QStringLiteral("id"), QStringLiteral("run-1")}, {QStringLiteral("automation_id"), QStringLiteral("routine-1")}, {QStringLiteral("outcome"), QStringLiteral("launched")}, {QStringLiteral("completion_status"), QJsonValue::Null}}}));
        else if (path.endsWith(QLatin1String("/enable")) || path.endsWith(QLatin1String("/disable"))) {
            enabled = path.endsWith(QLatin1String("/enable")); auto row = routine(QStringLiteral("p1")); row[QStringLiteral("enabled")] = enabled;
            reply(socket, QJsonDocument(row));
        } else reply(socket, QJsonDocument(QJsonObject{{QStringLiteral("detail"), QStringLiteral("Route inattendue")}}), 404);
    }
    QList<OperationRequest> mutations() const
    {
        QList<OperationRequest> result;
        for (const auto& request : requests) if (request.method != "GET") result.append(request);
        return result;
    }
};

class TestOperations : public QObject
{
    Q_OBJECT
    static void session(ApiClient& client, AuthManager& auth, const OperationsHttp& http, const QString& role = QStringLiteral("owner"))
    {
        client.setAllowInsecureLoopback(true); QVERIFY(!client.setBaseUrl(http.origin()).isError());
        auth.applySessionPayload(QJsonObject{{QStringLiteral("csrf_token"), QStringLiteral("csrf-factice")}, {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00Z")},
            {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("u1")}, {QStringLiteral("role"), role}}}});
    }
    static QVariantMap form(const QString& kind = QStringLiteral("interval"))
    {
        return {{QStringLiteral("name"), QStringLiteral("Routine du matin")}, {QStringLiteral("objective"), QStringLiteral("Vérifier les tests")}, {QStringLiteral("expectedOutcome"), QStringLiteral("Compte rendu")},
            {QStringLiteral("criteria"), QStringLiteral("Résultat documenté\nErreurs recensées")}, {QStringLiteral("scheduleKind"), kind},
            {QStringLiteral("expression"), kind == QLatin1String("interval") ? QStringLiteral("90") : QStringLiteral("0 9 * * 1-5")},
            {QStringLiteral("timezone"), QStringLiteral("Europe/Paris")}, {QStringLiteral("durationSeconds"), 900}, {QStringLiteral("maxToolCalls"), 30}};
    }
private slots:
    void loadsScopedRoutesAndPreservesUnknownConsumption()
    {
        OperationsHttp http; ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1"));
        QTRY_VERIFY_WITH_TIMEOUT(!vm.busy(), 5000);
        QCOMPARE(vm.approvals()->count(), 1); QCOMPARE(vm.alerts()->count(), 1); QCOMPARE(vm.automations()->count(), 1);
        QVERIFY(vm.budgetUsage().value(QStringLiteral("totals")).toMap().value(QStringLiteral("cost")).isNull());
        QCOMPARE(vm.budgetUsage().value(QStringLiteral("totals")).toMap().value(QStringLiteral("tool_calls")).toInt(), 0);
        QVERIFY(vm.canManage()); QVERIFY(vm.canDecide());
        QCOMPARE(http.requests.size(), 5);
        for (const auto& request : http.requests) if (!request.url.path().startsWith(QLatin1String("/projects/")))
            QCOMPARE(QUrlQuery(request.url).queryItemValue(QStringLiteral("project_id")), QStringLiteral("p1"));
    }
    void budgetReplacementPreservesUneditedLimitsWithoutRetryKey()
    {
        OperationsHttp http; ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(!vm.busy());
        vm.saveBudgetPolicy(9, 2, 7); QTRY_VERIFY(!vm.busy());
        const auto requests = http.mutations(); QCOMPARE(requests.size(), 1);
        const auto request = requests.first(); QCOMPARE(request.method, QByteArray("PUT"));
        QCOMPARE(request.url.path(), QStringLiteral("/projects/p1/budget-policy"));
        QVERIFY(!request.headers.contains(QByteArrayLiteral("idempotency-key"))); QCOMPARE(request.headers.value(QByteArrayLiteral("x-csrf-token")), QByteArray("csrf-factice"));
        QCOMPARE(request.body.value(QStringLiteral("daily_budget")), OperationsHttp::policy(QStringLiteral("p1")).value(QStringLiteral("daily_budget")));
        QCOMPARE(request.body.value(QStringLiteral("provider_budgets")), OperationsHttp::policy(QStringLiteral("p1")).value(QStringLiteral("provider_budgets")));
        QCOMPARE(request.body.value(QStringLiteral("timezone")).toString(), QStringLiteral("America/Montreal"));
        QCOMPARE(request.body.value(QStringLiteral("max_retries_per_mission")).toInt(), 2);
        QVERIFY(!request.body.contains(QStringLiteral("project_id"))); QVERIFY(!request.body.contains(QStringLiteral("updated_at")));
        QVERIFY(!vm.notice().isEmpty());
    }
    void realDecisionAndAcknowledgementCarryComments()
    {
        OperationsHttp http; ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(!vm.busy());
        vm.decideApproval(QStringLiteral("approval-1"), QStringLiteral("REJECTED"), QStringLiteral("Preuve insuffisante"));
        QTRY_VERIFY(!vm.busy()); QCOMPARE(vm.approvals()->count(), 0);
        vm.acknowledgeAlert(QStringLiteral("alert-1"), QStringLiteral("  Pris en compte  "));
        QTRY_VERIFY(!vm.busy()); QCOMPARE(vm.alerts()->count(), 0);
        const auto requests = http.mutations(); QCOMPARE(requests.size(), 2);
        QCOMPARE(requests[0].url.path(), QStringLiteral("/approvals/approval-1/decision"));
        QCOMPARE(requests[0].body.value(QStringLiteral("decision")).toString(), QStringLiteral("REJECTED"));
        QCOMPARE(requests[0].body.value(QStringLiteral("comment")).toString(), QStringLiteral("Preuve insuffisante"));
        QCOMPARE(requests[1].url.path(), QStringLiteral("/alerts/alert-1/acknowledge"));
        QCOMPARE(requests[1].body.value(QStringLiteral("comment")).toString(), QStringLiteral("Pris en compte"));
        QVERIFY(!requests[0].headers.contains(QByteArrayLiteral("idempotency-key"))); QVERIFY(!requests[1].headers.contains(QByteArrayLiteral("idempotency-key")));
    }
    void createsPausedAutomationWithRealSchedule_data()
    {
        QTest::addColumn<QString>("kind"); QTest::addColumn<QString>("expression");
        QTest::newRow("interval") << QStringLiteral("interval") << QStringLiteral("5400");
        QTest::newRow("cron") << QStringLiteral("cron") << QStringLiteral("0 9 * * 1-5");
    }
    void createsPausedAutomationWithRealSchedule()
    {
        QFETCH(QString, kind); QFETCH(QString, expression);
        OperationsHttp http; ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(!vm.busy());
        vm.createAutomation(form(kind)); QTRY_VERIFY(!vm.busy());
        const auto mutations = http.mutations(); QCOMPARE(mutations.size(), 1); const auto req = mutations.first();
        QCOMPARE(req.url.path(), QStringLiteral("/projects/p1/automations")); QVERIFY(!req.headers.value(QByteArrayLiteral("idempotency-key")).isEmpty());
        QCOMPARE(req.body.value(QStringLiteral("schedule")).toObject().value(QStringLiteral("expression")).toString(), expression);
        QVERIFY(!req.body.contains(QStringLiteral("enabled")));
        const auto mission = req.body.value(QStringLiteral("mission_template")).toObject();
        QCOMPARE(mission.value(QStringLiteral("autonomy")).toObject().value(QStringLiteral("mode")).toString(), QStringLiteral("supervised"));
        QCOMPARE(mission.value(QStringLiteral("budget")).toObject().value(QStringLiteral("max_tool_calls")).toInt(), 30);
        QVERIFY(mission.value(QStringLiteral("budget")).toObject().value(QStringLiteral("max_cost")).isNull());
        QCOMPARE(mission.value(QStringLiteral("acceptance_criteria")).toArray().size(), 2); QVERIFY(!vm.notice().isEmpty());
    }
    void activationPauseAndHistoryUseSupportedRoutes()
    {
        OperationsHttp http; ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(!vm.busy());
        vm.selectAutomation(QStringLiteral("routine-1")); QTRY_VERIFY(!vm.busy()); QCOMPARE(vm.automationRuns()->count(), 1);
        vm.setAutomationEnabled(QStringLiteral("routine-1"), true); QTRY_VERIFY(!vm.busy());
        QVERIFY(vm.automations()->get(0).value(QStringLiteral("enabled")).toBool());
        vm.setAutomationEnabled(QStringLiteral("routine-1"), false); QTRY_VERIFY(!vm.busy());
        QVERIFY(!vm.automations()->get(0).value(QStringLiteral("enabled")).toBool());
        const auto mutations = http.mutations(); QCOMPARE(mutations.size(), 2);
        QCOMPARE(mutations[0].url.path(), QStringLiteral("/automations/routine-1/enable"));
        QCOMPARE(mutations[1].url.path(), QStringLiteral("/automations/routine-1/disable"));
        QVERIFY(!mutations[0].headers.value(QByteArrayLiteral("idempotency-key")).isEmpty());
        QVERIFY(mutations[0].headers.value(QByteArrayLiteral("idempotency-key")) != mutations[1].headers.value(QByteArrayLiteral("idempotency-key")));
    }
    void decisionFailureIsNotRetriedOrReportedAsSuccess()
    {
        OperationsHttp http;
        http.intercept = [](QTcpSocket* socket, const OperationRequest& req) {
            if (!req.url.path().endsWith(QLatin1String("/decision"))) return false;
            OperationsHttp::reply(socket, QJsonDocument(QJsonObject{{QStringLiteral("detail"), QStringLiteral("Écriture incertaine")}}), 500); return true;
        };
        ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(!vm.busy());
        vm.decideApproval(QStringLiteral("approval-1"), QStringLiteral("APPROVED"), {}); QTRY_VERIFY(!vm.busy());
        QCOMPARE(http.mutations().size(), 1); QVERIFY(vm.notice().isEmpty()); QVERIFY(!vm.error().isEmpty()); QVERIFY(!vm.mutating());
    }
    void unconfirmedResponseNeverDisplaysSuccess()
    {
        OperationsHttp http;
        http.intercept = [](QTcpSocket* socket, const OperationRequest& req) {
            if (!req.url.path().endsWith(QLatin1String("/decision"))) return false;
            OperationsHttp::reply(socket, QJsonDocument(QJsonObject{{QStringLiteral("id"), QStringLiteral("other")}, {QStringLiteral("project_id"), QStringLiteral("p1")}, {QStringLiteral("status"), QStringLiteral("APPROVED")}})); return true;
        };
        ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(!vm.busy());
        vm.decideApproval(QStringLiteral("approval-1"), QStringLiteral("APPROVED"), {}); QTRY_VERIFY(!vm.busy());
        QVERIFY(vm.notice().isEmpty()); QVERIFY(vm.error().contains(QStringLiteral("non confirmé")));
    }
    void projectAndWorkspaceMembershipsDeterminePermissions()
    {
        OperationsHttp http;
        http.memberships = {QJsonObject{{QStringLiteral("user_id"), QStringLiteral("u1")}, {QStringLiteral("scope_type"), QStringLiteral("project")}, {QStringLiteral("scope_id"), QStringLiteral("p1")}, {QStringLiteral("role"), QStringLiteral("viewer")}},
                            QJsonObject{{QStringLiteral("user_id"), QStringLiteral("other")}, {QStringLiteral("scope_type"), QStringLiteral("project")}, {QStringLiteral("scope_id"), QStringLiteral("p1")}, {QStringLiteral("role"), QStringLiteral("owner")}}};
        ApiClient client; AuthManager auth(&client); session(client, auth, http, QStringLiteral("member"));
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(!vm.busy());
        QVERIFY(!vm.canManage()); QVERIFY(!vm.canDecide()); vm.saveBudgetPolicy(1, 1, 1); QVERIFY(http.mutations().isEmpty());
        http.memberships.append(QJsonObject{{QStringLiteral("user_id"), QStringLiteral("u1")}, {QStringLiteral("scope_type"), QStringLiteral("workspace")}, {QStringLiteral("scope_id"), QStringLiteral("w1")}, {QStringLiteral("role"), QStringLiteral("owner")}});
        vm.refresh(); QTRY_VERIFY(!vm.busy()); QVERIFY(vm.canManage()); QVERIFY(vm.canDecide());
    }
    void projectSwitchAndLogoutDiscardStaleData()
    {
        OperationsHttp http; QPointer<QTcpSocket> held;
        http.intercept = [&held](QTcpSocket* socket, const OperationRequest& req) {
            if (req.url.path() != QLatin1String("/approvals") || QUrlQuery(req.url).queryItemValue(QStringLiteral("project_id")) != QLatin1String("p1")) return false;
            held = socket; return true;
        };
        ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(held);
        vm.setProjectId(QStringLiteral("p2")); QTRY_VERIFY(!vm.busy());
        QCOMPARE(vm.approvals()->get(0).value(QStringLiteral("project_id")).toString(), QStringLiteral("p2"));
        QCOMPARE(vm.budgetPolicy().value(QStringLiteral("project_id")).toString(), QStringLiteral("p2"));
        auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("fin"));
        QCOMPARE(vm.approvals()->count(), 0); QVERIFY(vm.budgetPolicy().isEmpty()); QVERIFY(!vm.canManage());
    }
    void revokedAccessClearsLoadedProjectAndMutationState()
    {
        OperationsHttp http;
        http.intercept = [](QTcpSocket* socket, const OperationRequest& req) {
            if (req.method != "PUT") return false;
            OperationsHttp::reply(socket, QJsonDocument(QJsonObject{{QStringLiteral("detail"), QStringLiteral("Session révoquée")}}), 401); return true;
        };
        ApiClient client; AuthManager auth(&client); session(client, auth, http);
        OperationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("p1")); QTRY_VERIFY(!vm.busy());
        vm.saveBudgetPolicy(2, 0, 3); QTRY_VERIFY(auth.state() != SessionStatus::Connected);
        QVERIFY(vm.budgetPolicy().isEmpty()); QCOMPARE(vm.alerts()->count(), 0); QVERIFY(!vm.mutating()); QVERIFY(!vm.canManage());
    }
};
QTEST_GUILESS_MAIN(TestOperations)
#include "tst_operations.moc"
