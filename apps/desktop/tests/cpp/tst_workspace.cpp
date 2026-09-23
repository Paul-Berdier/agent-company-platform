#include "api/ApiClient.h"
#include "auth/AuthManager.h"
#include "viewmodels/WorkspaceViewModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QPointer>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <functional>

using namespace acp;

namespace {
class Server : public QTcpServer {
public:
    std::function<void(QTcpSocket *, const QByteArray &, const QByteArray &)> handler;
    QList<QByteArray> requests;
    Server() {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (auto *socket = nextPendingConnection()) {
                connect(socket, &QTcpSocket::readyRead, this, [this, socket] {
                    auto data = socket->property("request").toByteArray() + socket->readAll();
                    socket->setProperty("request", data);
                    const auto split = data.indexOf("\r\n\r\n");
                    if (split < 0 || socket->property("handled").toBool()) return;
                    qint64 expected = 0;
                    for (const auto &line : data.left(split).split('\n')) {
                        if (line.toLower().startsWith("content-length:"))
                            expected = line.mid(15).trimmed().toLongLong();
                    }
                    const auto body = data.mid(split + 4);
                    if (body.size() < expected) return;
                    socket->setProperty("handled", true);
                    requests.append(data);
                    handler(socket, data.left(split), body);
                });
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            }
        });
        if (!listen(QHostAddress::LocalHost)) qFatal("Serveur local indisponible");
    }
    QUrl url() const { return QUrl(QStringLiteral("http://127.0.0.1:%1").arg(serverPort())); }
    static void reply(QTcpSocket *socket, const QByteArray &json) {
        socket->write(QByteArrayLiteral("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ")
            + QByteArray::number(json.size()) + QByteArrayLiteral("\r\nConnection: close\r\n\r\n") + json);
        socket->disconnectFromHost();
    }
};
void login(AuthManager &auth, const QString &role = QStringLiteral("owner")) {
    auth.applySessionPayload({{QStringLiteral("csrf_token"), QStringLiteral("test-csrf")},
        {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("owner")},
         {QStringLiteral("display_name"), QStringLiteral("Test")},
         {QStringLiteral("role"), role}}},
        {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00Z")}});
}
}

class TestWorkspace : public QObject {
    Q_OBJECT
private slots:
    void projectCreationIntentNeverSurvivesSessionOrOrigin_data() {
        QTest::addColumn<bool>("changeOrigin");
        QTest::newRow("logout") << false;
        QTest::newRow("origin") << true;
    }
    void projectCreationIntentNeverSurvivesSessionOrOrigin() {
        QFETCH(bool, changeOrigin);
        ApiClient client;
        QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://first.example.test"))).isError());
        AuthManager auth(&client);
        login(auth);
        WorkspaceViewModel vm(&client, &auth);
        vm.workspaces()->setItems({QJsonObject{{QStringLiteral("id"), QStringLiteral("w1")}}});
        vm.requestProjectCreation();
        QVERIFY(vm.projectCreationPending());
        QVERIFY(!vm.busy()); // Une intention d'ouvrir le formulaire ne crée aucune ressource.
        vm.acknowledgeProjectCreation();
        QVERIFY(!vm.projectCreationPending());
        vm.requestProjectCreation();
        if (changeOrigin)
            QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://other.example.test"))).isError());
        else auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Fin"));
        QVERIFY(!vm.projectCreationPending());
        vm.requestProjectCreation();
        QVERIFY(!vm.projectCreationPending());
    }
    void creationRequiresMembershipInWorkspace_data() {
        QTest::addColumn<QString>("scope");
        QTest::addColumn<QString>("role");
        QTest::addColumn<bool>("allowed");
        QTest::newRow("workspace-viewer") << QStringLiteral("workspace") << QStringLiteral("viewer") << false;
        QTest::newRow("workspace-member") << QStringLiteral("workspace") << QStringLiteral("member") << true;
        QTest::newRow("workspace-operator") << QStringLiteral("workspace") << QStringLiteral("operator") << true;
        QTest::newRow("workspace-owner") << QStringLiteral("workspace") << QStringLiteral("owner") << true;
        QTest::newRow("project-member") << QStringLiteral("project") << QStringLiteral("member") << false;
        QTest::newRow("project-owner") << QStringLiteral("project") << QStringLiteral("owner") << false;
    }
    void creationRequiresMembershipInWorkspace() {
        QFETCH(QString, scope);
        QFETCH(QString, role);
        QFETCH(bool, allowed);
        Server server;
        int created = 0;
        bool readMemberships = false;
        server.handler = [&](QTcpSocket *socket, const QByteArray &headers, const QByteArray &) {
            if (headers.startsWith("GET /memberships?user_id=owner ")) {
                readMemberships = true;
                Server::reply(socket, QJsonDocument(QJsonArray{QJsonObject{
                    {QStringLiteral("user_id"), QStringLiteral("owner")},
                    {QStringLiteral("scope_type"), scope}, {QStringLiteral("scope_id"), QStringLiteral("w1")},
                    {QStringLiteral("role"), role}}}).toJson(QJsonDocument::Compact));
            } else if (headers.startsWith("GET /workspaces ")) {
                Server::reply(socket, QByteArrayLiteral("[{\"id\":\"w1\",\"name\":\"Espace visible\"}]"));
            } else if (headers.startsWith("POST /projects ")) {
                ++created; Server::reply(socket, QByteArrayLiteral("{\"id\":\"new\"}"));
            } else Server::reply(socket, QByteArrayLiteral("[]"));
        };
        ApiClient client;
        client.setAllowInsecureLoopback(true);
        QVERIFY(!client.setBaseUrl(server.url()).isError());
        AuthManager auth(&client);
        login(auth, QStringLiteral("member"));
        WorkspaceViewModel vm(&client, &auth);
        vm.refresh();
        QTRY_VERIFY(readMemberships && !vm.busy());
        QCOMPARE(vm.workspaces()->count(), 1);
        QCOMPARE(vm.canCreateInWorkspace(QStringLiteral("w1")), allowed);
        QCOMPARE(vm.canCreateProject(), allowed);
        QVERIFY(!vm.canCreateInWorkspace(QStringLiteral("other")));
        vm.createProject(QStringLiteral("w1"), QStringLiteral("Projet"), {});
        if (allowed) QTRY_COMPARE(created, 1);
        else {
            QVERIFY(!vm.error().isEmpty());
            QTest::qWait(30);
            QCOMPARE(created, 0);
        }
        QTRY_VERIFY(!vm.busy());
        const qsizetype count = server.requests.size();
        vm.createWorkspace(QStringLiteral("organization"), QStringLiteral("Espace"));
        vm.createOrganization(QStringLiteral("Organisation"));
        QTest::qWait(30);
        QCOMPARE(server.requests.size(), count);
        QVERIFY(!vm.error().isEmpty());
        auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Fin"));
        QVERIFY(!vm.canCreateInWorkspace(QStringLiteral("w1")));
        QVERIFY(!vm.canCreateProject());
    }
    void requiresSession() {
        ApiClient client;
        AuthManager auth(&client);
        WorkspaceViewModel vm(&client, &auth);
        vm.refresh();
        QVERIFY(!vm.error().isEmpty());
        QCOMPARE(vm.projects()->count(), 0);
        QVERIFY(!vm.busy());
    }
    void lateProjectResponseCannotRestoreLoggedOutData() {
        Server server;
        QPointer<QTcpSocket> delayed;
        server.handler = [&delayed](QTcpSocket *socket, const QByteArray &headers, const QByteArray &) {
            if (headers.startsWith("GET /projects ")) delayed = socket;
            else Server::reply(socket, QByteArrayLiteral("[]"));
        };
        ApiClient client;
        client.setAllowInsecureLoopback(true);
        QVERIFY(!client.setBaseUrl(server.url()).isError());
        AuthManager auth(&client);
        login(auth);
        WorkspaceViewModel vm(&client, &auth);
        vm.refresh();
        QTRY_VERIFY(delayed);
        auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Fin de session"));
        Server::reply(delayed, QByteArrayLiteral("[{\"id\":\"old\",\"name\":\"Confidentiel\"}]"));
        QTest::qWait(100);
        QCOMPARE(vm.projects()->count(), 0);
        QVERIFY(vm.projectId().isEmpty());
        QVERIFY(!vm.busy());
    }
    void createsAndSelectsOnlyServerConfirmedProject() {
        Server server;
        bool created = false;
        QByteArray mutation;
        server.handler = [&](QTcpSocket *socket, const QByteArray &headers, const QByteArray &body) {
            if (headers.startsWith("POST /projects ")) {
                mutation = headers;
                const auto object = QJsonDocument::fromJson(body).object();
                QCOMPARE(object.value(QStringLiteral("workspace_id")).toString(), QStringLiteral("w1"));
                QCOMPARE(object.value(QStringLiteral("name")).toString(), QStringLiteral("Mon projet"));
                created = true;
                Server::reply(socket, QByteArrayLiteral("{\"id\":\"p1\"}"));
            } else if (headers.startsWith("GET /projects ")) {
                Server::reply(socket, created ? QByteArrayLiteral("[{\"id\":\"p1\",\"name\":\"Mon projet\",\"workspace_id\":\"w1\"}]") : QByteArrayLiteral("[]"));
            } else Server::reply(socket, QByteArrayLiteral("[]"));
        };
        ApiClient client;
        client.setAllowInsecureLoopback(true);
        QVERIFY(!client.setBaseUrl(server.url()).isError());
        AuthManager auth(&client);
        login(auth);
        WorkspaceViewModel vm(&client, &auth);
        vm.createProject(QStringLiteral("w1"), QStringLiteral("  Mon projet  "), QString());
        QTRY_COMPARE(vm.projectId(), QStringLiteral("p1"));
        QTRY_VERIFY(!vm.busy());
        QVERIFY(mutation.toLower().contains("x-csrf-token: test-csrf"));
        QVERIFY(!mutation.toLower().contains("idempotency-key:"));
        QCOMPARE(vm.projects()->count(), 1);
        QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://different.example.test"))).isError());
        QCOMPARE(vm.projects()->count(), 0);
        QVERIFY(vm.projectId().isEmpty());
    }
    void selectionMustBelongToVisibleProjects() {
        ApiClient client;
        AuthManager auth(&client);
        WorkspaceViewModel vm(&client, &auth);
        vm.projects()->setItems({QJsonObject{{QStringLiteral("id"), QStringLiteral("allowed")},
                                            {QStringLiteral("name"), QStringLiteral("Projet")}}});
        vm.selectProject(QStringLiteral("allowed"));
        QCOMPARE(vm.projectId(), QStringLiteral("allowed"));
        vm.selectProject(QStringLiteral("forbidden"));
        QVERIFY(vm.projectId().isEmpty());
    }
};
QTEST_GUILESS_MAIN(TestWorkspace)
#include "tst_workspace.moc"
