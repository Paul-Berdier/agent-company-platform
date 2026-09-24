#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include <QNetworkCookie>
#include "auth/AuthManager.h"
#include "models/JsonListModel.h"
#include "viewmodels/ConversationsViewModel.h"

#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPointer>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <QTimer>

#include <functional>
#include <memory>

using namespace acp;

namespace {
const QString kDate = QStringLiteral("2026-09-23T10:00:00+00:00");

QJsonObject summary(const QString &id, const QString &project = QStringLiteral("project-a"))
{
    return {{QStringLiteral("id"), id}, {QStringLiteral("project_id"), project.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(project)},
        {QStringLiteral("title"), QStringLiteral("Une conversation")}, {QStringLiteral("status"), QStringLiteral("active")},
        {QStringLiteral("created_at"), kDate}, {QStringLiteral("updated_at"), kDate}};
}

QJsonObject turn(const QString &key, const QString &status = QStringLiteral("running"))
{
    return {{QStringLiteral("id"), QStringLiteral("turn-a")}, {QStringLiteral("client_request_id"), key}, {QStringLiteral("status"), status},
        {QStringLiteral("user_content"), QStringLiteral("Bonjour <img src='https://example.invalid/x'>")},
        {QStringLiteral("assistant_content"), status == QLatin1String("completed") ? QJsonValue(QStringLiteral("Réponse réelle")) : QJsonValue(QJsonValue::Null)},
        {QStringLiteral("error"), QJsonValue(QJsonValue::Null)}, {QStringLiteral("created_at"), kDate}, {QStringLiteral("updated_at"), kDate}};
}

struct Request {
    QByteArray method;
    QByteArray path;
    QByteArray headers;
    QJsonObject body;
};

struct Response {
    int status = 200;
    QJsonObject body;
    int delayMs = 0;
    QByteArray sessionCookie;
};

// Serveur HTTP local : exerce le vrai ApiClient, ses réessais et les réponses tardives.
class ConversationServer : public QObject
{
public:
    QTcpServer server;
    QList<Request> requests;
    std::function<Response(const Request &)> handler;

    ConversationServer()
    {
        connect(&server, &QTcpServer::newConnection, this, [this] {
            while (QTcpSocket *socket = server.nextPendingConnection()) {
                const auto buffer = std::make_shared<QByteArray>();
                const auto answered = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, buffer, answered] {
                    buffer->append(socket->readAll());
                    if (*answered) {
                        return;
                    }
                    const qsizetype headerEnd = buffer->indexOf("\r\n\r\n");
                    if (headerEnd < 0) {
                        return;
                    }
                    const QByteArray headers = buffer->left(headerEnd);
                    qsizetype length = 0;
                    for (const auto &line : headers.split('\n')) {
                        if (line.toLower().startsWith("content-length:")) {
                            length = line.mid(15).trimmed().toLongLong();
                        }
                    }
                    if (buffer->size() < headerEnd + 4 + length) {
                        return;
                    }
                    *answered = true;
                    const QList<QByteArray> first = headers.split('\n').first().trimmed().split(' ');
                    Request req{first.value(0), first.value(1), headers,
                        QJsonDocument::fromJson(buffer->mid(headerEnd + 4, length)).object()};
                    requests.append(req);
                    const Response reply = handler ? handler(req) : Response{404, {{QStringLiteral("detail"), QStringLiteral("absent")}}, 0};
                    QTimer::singleShot(reply.delayMs, socket, [socket, reply] {
                        const QByteArray body = QJsonDocument(reply.body).toJson(QJsonDocument::Compact);
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

void authenticate(AuthManager &auth)
{
    auth.applySessionPayload({{QStringLiteral("authenticated"), true}, {QStringLiteral("csrf_token"), QStringLiteral("csrf-test")},
        {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00+00:00")},
        {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("user-a")}, {QStringLiteral("display_name"), QStringLiteral("Alice")},
                              {QStringLiteral("role"), QStringLiteral("owner")}}}});
}

JsonListModel *model(QObject *object) { return qobject_cast<JsonListModel *>(object); }
} // namespace

class TestConversations : public QObject
{
    Q_OBJECT
private slots:
    void activationBeforeLoginLoadsAfterIdentityConfirmation();
    void projectAndSessionChangesDiscardOldResponses();
    void invalidDocumentsNeverBecomeEmptySuccess();
    void createSendRetryPollRenameArchiveAndExport();
    void hidingThePageStopsPolling();
    void uncertainSubmissionSurvivesSessionRefresh();
    void approvalWaitCanBeStoppedWithoutInventingTerminalState_data();
    void approvalWaitCanBeStoppedWithoutInventingTerminalState();
    void newChatsNeedNoTitleAndWorkBeforePageActivation();
    void draftsSurviveThreadAndProjectSwitchesButNotIdentityLoss();
    void searchAndArchiveFiltersNeverChangeSelectedDraft();
    void codeFencesStayInertAndBounded();
};

void TestConversations::newChatsNeedNoTitleAndWorkBeforePageActivation()
{
    ConversationServer server; QVERIFY(server.start());
    QJsonArray stored;
    int creations = 0;
    bool titlesOmitted = true;
    server.handler = [&](const Request &req) {
        if (req.path == "/conversations" && req.method == "POST") {
            ++creations;
            titlesOmitted = titlesOmitted && !req.body.contains(QStringLiteral("title"));
            auto row = summary(QString::number(creations), req.body.value(QStringLiteral("project_id")).toString());
            row.insert(QStringLiteral("title"), QStringLiteral("Titre par défaut du serveur"));
            stored.append(row);
            return Response{201, row};
        }
        if (req.path == "/conversations") return Response{200, {{QStringLiteral("items"), stored}}};
        for (const auto &value : stored) {
            auto row = value.toObject();
            if (req.path.endsWith(row.value(QStringLiteral("id")).toString().toUtf8())) {
                row.insert(QStringLiteral("turns"), QJsonArray{});
                return Response{200, row};
            }
        }
        return Response{404, {}};
    };
    ApiClient client; client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client); authenticate(auth);
    ConversationsViewModel vm(&client, &auth);
    bool busyNotified = false;
    connect(&vm, &ConversationsViewModel::changed, &vm, [&] { if (vm.busy()) busyNotified = true; });
    QVERIFY(vm.startConversation(QString()));
    QVERIFY(busyNotified);
    QTRY_VERIFY(!vm.busy() && !vm.loading());
    QCOMPARE(vm.currentId(), QStringLiteral("1"));
    QCOMPARE(vm.currentTitle(), QStringLiteral("Titre par défaut du serveur"));
    QVERIFY(vm.projectId().isEmpty());
    vm.setDraft(QStringLiteral("Général à garder"));
    QVERIFY(vm.startConversation(QStringLiteral("project-a")));
    QTRY_VERIFY(!vm.busy() && !vm.loading());
    QCOMPARE(vm.currentId(), QStringLiteral("2"));
    QCOMPARE(vm.projectId(), QStringLiteral("project-a"));
    QCOMPARE(creations, 2);
    QVERIFY(titlesOmitted);
    vm.setProjectId(QString()); QTRY_VERIFY(!vm.loading());
    vm.setActive(false);
    QVERIFY(vm.openConversation(QStringLiteral("1")));
    QTRY_VERIFY(!vm.loading());
    QCOMPARE(vm.draft(), QStringLiteral("Général à garder"));
    QVERIFY(!vm.openConversation(QStringLiteral("non-visible")));
}

void TestConversations::draftsSurviveThreadAndProjectSwitchesButNotIdentityLoss()
{
    ConversationServer server; QVERIFY(server.start());
    const QJsonArray rows{summary(QStringLiteral("a")), summary(QStringLiteral("b")), summary(QStringLiteral("general"), QString())};
    server.handler = [&](const Request &req) {
        if (req.path == "/conversations") return Response{200, {{QStringLiteral("items"), rows}}};
        for (const auto &value : rows) {
            auto row = value.toObject();
            if (req.path == "/conversations/" + row.value(QStringLiteral("id")).toString().toUtf8()) {
                row.insert(QStringLiteral("turns"), QJsonArray{}); return Response{200, row};
            }
        }
        return Response{404, {}};
    };
    ApiClient client; client.setAllowInsecureLoopback(true); QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client); authenticate(auth);
    ConversationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("project-a")); vm.setActive(true);
    QTRY_VERIFY(!vm.loading()); vm.selectConversation(QStringLiteral("a")); QTRY_VERIFY(!vm.loading());
    vm.setDraft(QStringLiteral("Brouillon A\ncode non envoyé"));
    vm.selectConversation(QStringLiteral("b")); QTRY_VERIFY(!vm.loading()); QVERIFY(vm.draft().isEmpty());
    vm.setDraft(QStringLiteral("Brouillon B"));
    vm.selectConversation(QStringLiteral("a")); QTRY_VERIFY(!vm.loading()); QCOMPARE(vm.draft(), QStringLiteral("Brouillon A\ncode non envoyé"));
    vm.setProjectId(QString()); QTRY_VERIFY(!vm.loading()); vm.selectConversation(QStringLiteral("general")); QTRY_VERIFY(!vm.loading());
    vm.setDraft(QStringLiteral("Brouillon général"));
    vm.setProjectId(QStringLiteral("project-a")); QTRY_VERIFY(!vm.loading()); vm.selectConversation(QStringLiteral("b")); QTRY_VERIFY(!vm.loading());
    QCOMPARE(vm.draft(), QStringLiteral("Brouillon B"));
    auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Fin de session")); authenticate(auth);
    QTRY_VERIFY(!vm.loading()); vm.selectConversation(QStringLiteral("a")); QTRY_VERIFY(!vm.loading()); QVERIFY(vm.draft().isEmpty());
    vm.setDraft(QStringLiteral("À purger avec le serveur"));
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:1"))).isError());
    QVERIFY(vm.draft().isEmpty());
    QVERIFY(!client.setBaseUrl(server.url()).isError()); authenticate(auth);
    QTRY_VERIFY(!vm.loading()); vm.selectConversation(QStringLiteral("a")); QTRY_VERIFY(!vm.loading()); QVERIFY(vm.draft().isEmpty());
}

void TestConversations::searchAndArchiveFiltersNeverChangeSelectedDraft()
{
    ConversationServer server; QVERIFY(server.start());
    auto first = summary(QStringLiteral("a")); first.insert(QStringLiteral("title"), QStringLiteral("Projet Boréal"));
    auto archived = summary(QStringLiteral("b")); archived.insert(QStringLiteral("status"), QStringLiteral("archived"));
    archived.insert(QStringLiteral("title"), QStringLiteral("Souvenir Boréal"));
    server.handler = [&](const Request &req) {
        if (req.path == "/conversations") return Response{200, {{QStringLiteral("items"), QJsonArray{first, archived}}}};
        auto detail = first; detail.insert(QStringLiteral("turns"), QJsonArray{}); return Response{200, detail};
    };
    ApiClient client; client.setAllowInsecureLoopback(true); QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client); authenticate(auth);
    ConversationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("project-a")); vm.setActive(true);
    QTRY_VERIFY(!vm.loading()); QCOMPARE(model(vm.conversations())->count(), 1);
    vm.selectConversation(QStringLiteral("a")); QTRY_VERIFY(!vm.loading()); vm.setDraft(QStringLiteral("À préserver"));
    vm.setSearchText(QStringLiteral(" BORÉAL ")); QCOMPARE(model(vm.conversations())->count(), 1);
    vm.setShowArchived(true); QCOMPARE(model(vm.conversations())->count(), 2);
    vm.setSearchText(QStringLiteral("Souvenir")); QCOMPARE(model(vm.conversations())->count(), 1);
    QCOMPARE(vm.currentId(), QStringLiteral("a")); QCOMPARE(vm.draft(), QStringLiteral("À préserver"));
    vm.setSearchText(QStringLiteral("<img>")); QCOMPARE(model(vm.conversations())->count(), 0);
    QCOMPARE(vm.currentId(), QStringLiteral("a")); QCOMPARE(vm.draft(), QStringLiteral("À préserver"));
}

void TestConversations::codeFencesStayInertAndBounded()
{
    ApiClient client; AuthManager auth(&client); ConversationsViewModel vm(&client, &auth);
    const QString hostile = QStringLiteral("<img src='https://example.invalid/secret'>\n[ouvrir](file:///secret)\n![image](https://example.invalid/image)");
    auto blocks = vm.messageBlocks(hostile);
    QCOMPARE(blocks.size(), 1); QCOMPARE(blocks.at(0).toMap().value(QStringLiteral("kind")).toString(), QStringLiteral("text"));
    QCOMPARE(blocks.at(0).toMap().value(QStringLiteral("text")).toString(), hostile);
    blocks = vm.messageBlocks(QStringLiteral("Explication\n```cpp\n<script>alert(1)</script>\nreturn 0;\n```\nSuite"));
    QCOMPARE(blocks.size(), 3);
    QCOMPARE(blocks.at(1).toMap().value(QStringLiteral("kind")).toString(), QStringLiteral("code"));
    QCOMPARE(blocks.at(1).toMap().value(QStringLiteral("language")).toString(), QStringLiteral("cpp"));
    QCOMPARE(blocks.at(1).toMap().value(QStringLiteral("text")).toString(), QStringLiteral("<script>alert(1)</script>\nreturn 0;"));
    blocks = vm.messageBlocks(QStringLiteral("~~~~python\nprint('```')\n~~~\n~~~~"));
    QCOMPARE(blocks.size(), 1); QCOMPARE(blocks.at(0).toMap().value(QStringLiteral("text")).toString(), QStringLiteral("print('```')\n~~~"));
    blocks = vm.messageBlocks(QStringLiteral("```txt\nBloc non clos"));
    QCOMPARE(blocks.at(0).toMap().value(QStringLiteral("text")).toString(), QStringLiteral("Bloc non clos"));
    blocks = vm.messageBlocks(QStringLiteral("```\nx\n```\n").repeated(500) + QStringLiteral("FIN"));
    QVERIFY(blocks.size() <= 128); QVERIFY(blocks.last().toMap().value(QStringLiteral("text")).toString().endsWith(QStringLiteral("FIN")));
}

void TestConversations::approvalWaitCanBeStoppedWithoutInventingTerminalState_data()
{
    QTest::addColumn<bool>("lostResponse");
    QTest::newRow("confirmation") << false;
    QTest::newRow("reponse-perdue") << true;
}
void TestConversations::approvalWaitCanBeStoppedWithoutInventingTerminalState()
{
    QFETCH(bool, lostResponse);
    ConversationServer server;
    QVERIFY(server.start());
    int stops = 0;
    Request stopRequest;
    server.handler = [&](const Request& req) {
        if (req.path == "/conversations") return Response{200, {{QStringLiteral("items"), QJsonArray{summary(QStringLiteral("a"))}}}};
        if (req.path == "/conversations/a/turns/turn-a/stop") {
            ++stops; stopRequest = req;
            return lostResponse ? Response{503, {{QStringLiteral("detail"), QStringLiteral("Réponse perdue")}}}
                : Response{202, turn(QStringLiteral("key"), QStringLiteral("stopping"))};
        }
        if (req.path == "/conversations/a/turns/turn-a")
            return Response{200, turn(QStringLiteral("key"), stops ? QStringLiteral("interrupted") : QStringLiteral("waiting_for_approval"))};
        auto value = summary(QStringLiteral("a"));
        value.insert(QStringLiteral("turns"), QJsonArray{turn(QStringLiteral("key"), QStringLiteral("waiting_for_approval"))});
        return Response{200, value};
    };
    ApiClient client; client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client); authenticate(auth);
    ConversationsViewModel vm(&client, &auth); vm.setProjectId(QStringLiteral("project-a")); vm.setActive(true);
    QTRY_VERIFY(!vm.loading()); vm.selectConversation(QStringLiteral("a"));
    QTRY_VERIFY(!vm.loading());
    vm.setDraft(QStringLiteral("Prochain message"));
    QVERIFY(!vm.canSend()); QVERIFY(vm.canStopTurn());
    vm.stopTurn(); QTRY_VERIFY(!vm.busy());
    QCOMPARE(stops, 1);
    QCOMPARE(stopRequest.method, QByteArray("POST"));
    QVERIFY(stopRequest.headers.toLower().contains("x-csrf-token: csrf-test"));
    QVERIFY(!stopRequest.headers.toLower().contains("idempotency-key:"));
    QCOMPARE(model(vm.turns())->get(0).value(QStringLiteral("status")).toString(),
        lostResponse ? QStringLiteral("waiting_for_approval") : QStringLiteral("stopping"));
    QVERIFY(vm.polling());
    QTRY_COMPARE_WITH_TIMEOUT(model(vm.turns())->get(0).value(QStringLiteral("status")).toString(), QStringLiteral("interrupted"), 5000);
    QVERIFY(!vm.polling()); QVERIFY(!vm.canStopTurn()); QVERIFY(vm.canSend());
    QCOMPARE(vm.draft(), QStringLiteral("Prochain message"));
    QCOMPARE(stops, 1);
}

void TestConversations::activationBeforeLoginLoadsAfterIdentityConfirmation()
{
    ConversationServer server;
    QVERIFY(server.start());
    bool authenticatedRead = false;
    server.handler = [&](const Request &req) {
        if (req.path == "/auth/login" && req.method == "POST") {
            return Response{200, {{QStringLiteral("authenticated"), true},
                {QStringLiteral("csrf_token"), QStringLiteral("csrf-test")},
                {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00Z")},
                {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("user-a")},
                    {QStringLiteral("display_name"), QStringLiteral("Alice")},
                    {QStringLiteral("role"), QStringLiteral("owner")}}}}, 0,
                QByteArrayLiteral("real-login-cookie-0123456789")};
        }
        authenticatedRead = req.headers.toLower().contains("cookie: acp_session=real-login-cookie-0123456789");
        return Response{200, {{QStringLiteral("items"), QJsonArray{summary(QStringLiteral("a"))}}}, 0};
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    ConversationsViewModel vm(&client, &auth);
    vm.setProjectId(QStringLiteral("project-a"));
    vm.setActive(true);
    QVERIFY(server.requests.isEmpty());
    bool pendingIdentityObserved = false;
    connect(&auth, &AuthManager::userChanged, &vm, [&] {
        if (auth.state() == SessionStatus::Connecting && !auth.userId().isEmpty()) {
            pendingIdentityObserved = true;
            QVERIFY(!vm.available());
            QCOMPARE(model(vm.conversations())->count(), 0);
        }
    });
    auth.logIn(QStringLiteral("alice"), QStringLiteral("test-password"));
    QTRY_COMPARE(auth.state(), SessionStatus::Connected);
    QVERIFY(pendingIdentityObserved);
    QVERIFY(client.cookieJar()->hasSessionCookie());
    QTRY_COMPARE(model(vm.conversations())->count(), 1);
    QTRY_VERIFY(!vm.loading());
    QVERIFY(authenticatedRead);
    QVERIFY(vm.available());
}

void TestConversations::projectAndSessionChangesDiscardOldResponses()
{
    ConversationServer server;
    QVERIFY(server.start());
    server.handler = [](const Request &req) {
        if (req.path == "/conversations") {
            return Response{200, {{QStringLiteral("items"), QJsonArray{summary(QStringLiteral("a")), summary(QStringLiteral("b"), QStringLiteral("project-b")), summary(QStringLiteral("general"), QString())}}}, 0};
        }
        QJsonObject detail = summary(QStringLiteral("a"));
        detail.insert(QStringLiteral("turns"), QJsonArray{turn(QStringLiteral("old-key"))});
        return Response{200, detail, 250};
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth);
    ConversationsViewModel vm(&client, &auth);
    vm.setProjectId(QStringLiteral("project-a"));
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    QCOMPARE(model(vm.conversations())->count(), 1);
    QCOMPARE(model(vm.conversations())->get(0).value(QStringLiteral("id")).toString(), QStringLiteral("a"));
    vm.selectConversation(QStringLiteral("a"));
    QTRY_VERIFY(server.requests.size() >= 2);
    vm.setProjectId(QStringLiteral("project-b"));
    QTRY_VERIFY(!vm.loading());
    QTest::qWait(300);
    QVERIFY(vm.currentId().isEmpty());
    QCOMPARE(model(vm.turns())->count(), 0);
    QCOMPARE(model(vm.conversations())->get(0).value(QStringLiteral("id")).toString(), QStringLiteral("b"));
    vm.setProjectId(QStringLiteral(""));
    QTRY_VERIFY(!vm.loading());
    QCOMPARE(model(vm.conversations())->get(0).value(QStringLiteral("id")).toString(), QStringLiteral("general"));
    auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Déconnexion de test"));
    QVERIFY(!vm.available());
    QCOMPARE(model(vm.conversations())->count(), 0);
    QVERIFY(vm.draft().isEmpty());
}

void TestConversations::invalidDocumentsNeverBecomeEmptySuccess()
{
    ConversationServer server;
    QVERIFY(server.start());
    server.handler = [](const Request &) { return Response{200, {{QStringLiteral("items"), QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("bad")}}}}}, 0}; };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth);
    ConversationsViewModel vm(&client, &auth);
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    QVERIFY(vm.error().contains(QStringLiteral("invalide")));
    QCOMPARE(model(vm.conversations())->count(), 0);
}

void TestConversations::createSendRetryPollRenameArchiveAndExport()
{
    ConversationServer server;
    QVERIFY(server.start());
    QJsonObject stored = summary(QStringLiteral("conversation-a"));
    QJsonObject storedTurn;
    QList<QJsonObject> attempts;
    bool csrfSeen = false;
    bool stableHeaderSeen = false;
    server.handler = [&](const Request &req) {
        if (req.path == "/conversations" && req.method == "GET") {
            return Response{200, {{QStringLiteral("items"), QJsonArray{}}}, 0};
        }
        if (req.path == "/conversations" && req.method == "POST") {
            stored.insert(QStringLiteral("title"), req.body.value(QStringLiteral("title")));
            stored.insert(QStringLiteral("project_id"), req.body.value(QStringLiteral("project_id")));
            return Response{201, stored, 0};
        }
        if (req.method == "PATCH") {
            for (auto it = req.body.begin(); it != req.body.end(); ++it) {
                stored.insert(it.key(), it.value());
            }
            return Response{200, stored, 0};
        }
        if (req.path.endsWith("/turns") && req.method == "POST") {
            attempts.append(req.body);
            csrfSeen = req.headers.toLower().contains("x-csrf-token: csrf-test");
            stableHeaderSeen = req.headers.contains(req.body.value(QStringLiteral("client_request_id")).toString().toUtf8());
            storedTurn = turn(req.body.value(QStringLiteral("client_request_id")).toString());
            // Réponse perdue après persistance simulée : le rejeu doit garder son identité.
            if (attempts.size() == 1) {
                return Response{503, {{QStringLiteral("detail"), QStringLiteral("Indisponibilité temporaire")}}, 0};
            }
            return Response{202, storedTurn, 0};
        }
        if (req.path.endsWith("/turns/turn-a")) {
            storedTurn = turn(storedTurn.value(QStringLiteral("client_request_id")).toString(), QStringLiteral("completed"));
            return Response{200, storedTurn, 0};
        }
        if (req.path.endsWith("/export")) {
            auto result = stored;
            result.insert(QStringLiteral("turns"), QJsonArray{storedTurn});
            return Response{200, result, 0};
        }
        return Response{404, {{QStringLiteral("detail"), QStringLiteral("absent")}}, 0};
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth);
    ConversationsViewModel vm(&client, &auth);
    vm.setProjectId(QStringLiteral("project-a"));
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    vm.createConversation(QStringLiteral("Discussion native"));
    QTRY_VERIFY(!vm.busy());
    QCOMPARE(vm.currentTitle(), QStringLiteral("Discussion native"));
    vm.setDraft(QStringLiteral("Bonjour <img src='https://example.invalid/x'>"));
    QVERIFY(vm.canSend());
    vm.sendMessage();
    QVERIFY(vm.pendingSubmission());
    vm.setDraft(QStringLiteral("Ne doit pas remplacer un envoi incertain"));
    QTRY_VERIFY_WITH_TIMEOUT(!vm.busy(), 5000);
    QCOMPARE(attempts.size(), 2);
    QCOMPARE(attempts.at(0), attempts.at(1));
    QVERIFY(csrfSeen);
    QVERIFY(stableHeaderSeen);
    QCOMPARE(model(vm.turns())->count(), 1);
    QVERIFY(!vm.pendingSubmission());
    QVERIFY(vm.draft().isEmpty());
    QTRY_COMPARE_WITH_TIMEOUT(model(vm.turns())->get(0).value(QStringLiteral("status")).toString(), QStringLiteral("completed"), 5000);
    QCOMPARE(model(vm.turns())->get(0).value(QStringLiteral("assistant_content")).toString(), QStringLiteral("Réponse réelle"));
    QVERIFY(!vm.polling());
    vm.renameConversation(QStringLiteral("Renommée"));
    QTRY_VERIFY(!vm.busy());
    QCOMPARE(vm.currentTitle(), QStringLiteral("Renommée"));
    vm.setArchived(true);
    QTRY_VERIFY(!vm.busy());
    QVERIFY(vm.archived());
    vm.setDraft(QStringLiteral("Interdit tant qu'archivée"));
    QVERIFY(!vm.canSend());
    vm.exportConversation();
    QTRY_VERIFY(!vm.busy());
    const QJsonObject exported = QJsonDocument::fromJson(vm.exportText().toUtf8()).object();
    QCOMPARE(exported.value(QStringLiteral("title")).toString(), QStringLiteral("Renommée"));
    QCOMPARE(exported.value(QStringLiteral("turns")).toArray().size(), 1);
    vm.setArchived(false);
    QTRY_VERIFY(!vm.busy());
    QVERIFY(vm.canSend());
}

void TestConversations::hidingThePageStopsPolling()
{
    ConversationServer server;
    QVERIFY(server.start());
    int polls = 0;
    server.handler = [&](const Request &req) {
        if (req.path == "/conversations") {
            return Response{200, {{QStringLiteral("items"), QJsonArray{summary(QStringLiteral("a"))}}}, 0};
        }
        if (req.path.contains("/turns/")) {
            ++polls;
            return Response{200, turn(QStringLiteral("pending")), 0};
        }
        auto detail = summary(QStringLiteral("a"));
        detail.insert(QStringLiteral("turns"), QJsonArray{turn(QStringLiteral("pending"))});
        return Response{200, detail, 0};
    };
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    AuthManager auth(&client);
    authenticate(auth);
    ConversationsViewModel vm(&client, &auth);
    vm.setProjectId(QStringLiteral("project-a"));
    vm.setActive(true);
    QTRY_VERIFY(!vm.loading());
    vm.selectConversation(QStringLiteral("a"));
    QTRY_VERIFY(!vm.loading());
    QVERIFY(vm.polling());
    vm.setActive(false);
    QVERIFY(!vm.polling());
    QTest::qWait(2200);
    QCOMPARE(polls, 0);
    QVERIFY(!vm.canSend());
    // Une nouvelle origine ne doit conserver aucun historique de l'ancienne session.
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:1"))).isError());
    QCOMPARE(model(vm.turns())->count(), 0);
    QVERIFY(vm.currentId().isEmpty());
    QVERIFY(!vm.available());
}

void TestConversations::uncertainSubmissionSurvivesSessionRefresh()
{
    ConversationServer server;
    QVERIFY(server.start());
    QList<QJsonObject> attempts;
    bool acceptTurn = false;
    server.handler = [&](const Request &req) {
        if (req.path == "/auth/session") return Response{200,
            {{QStringLiteral("csrf_token"), QStringLiteral("new-csrf")}, {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00Z")},
             {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("user-a")}, {QStringLiteral("role"), QStringLiteral("owner")}, {QStringLiteral("display_name"), QStringLiteral("Alice")}}}}, 300};
        if (req.method == "POST" && req.path.endsWith("/turns")) {
            attempts.append(req.body);
            if (!acceptTurn) return Response{503, {{QStringLiteral("detail"), QStringLiteral("Résultat incertain")}}, 0};
            auto result = turn(req.body.value(QStringLiteral("client_request_id")).toString());
            result[QStringLiteral("user_content")] = req.body.value(QStringLiteral("content"));
            return Response{202, result, 0};
        }
        if (req.path == "/conversations") return Response{200, {{QStringLiteral("items"), QJsonArray{summary(QStringLiteral("a"))}}}, 0};
        auto detail = summary(QStringLiteral("a")); detail[QStringLiteral("turns")] = QJsonArray{};
        return Response{200, detail, 0};
    };
    ApiClient client; client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(server.url()).isError());
    QVERIFY(client.cookieJar()->setCookiesFromUrl({QNetworkCookie("acp_session", "synthetic-cookie")}, server.url()));
    AuthManager auth(&client); authenticate(auth);
    ConversationsViewModel vm(&client, &auth);
    vm.setProjectId(QStringLiteral("project-a")); vm.setActive(true);
    QTRY_VERIFY(!vm.loading()); vm.selectConversation(QStringLiteral("a")); QTRY_VERIFY(!vm.loading());
    vm.setDraft(QStringLiteral("Message à conserver")); vm.sendMessage();
    QTRY_VERIFY_WITH_TIMEOUT(!vm.busy(), 7000);
    QVERIFY(vm.pendingSubmission()); QVERIFY(attempts.size() >= 1);
    QVERIFY(!vm.startConversation(QString()));
    QVERIFY(!vm.openConversation(QStringLiteral("a")));
    vm.setProjectId(QString());
    QCOMPARE(vm.projectId(), QStringLiteral("project-a"));
    QCOMPARE(vm.draft(), QStringLiteral("Message à conserver"));
    auth.resumeSession();
    QCOMPARE(auth.state(), SessionStatus::Connecting);
    QVERIFY(vm.pendingSubmission()); QCOMPARE(vm.draft(), QStringLiteral("Message à conserver"));
    QTRY_COMPARE(auth.state(), SessionStatus::Connected);
    QVERIFY(vm.pendingSubmission());
    bool acknowledgmentWhileRefreshing = false;
    connect(&vm, &ConversationsViewModel::changed, &vm, [&] {
        if (auth.state() == SessionStatus::Connecting && !vm.busy() && !vm.pendingSubmission())
            acknowledgmentWhileRefreshing = true;
    });
    acceptTurn = true; vm.retryPendingMessage();
    auth.resumeSession();
    QCOMPARE(auth.state(), SessionStatus::Connecting);
    QTRY_VERIFY(!vm.busy()); QVERIFY(!vm.pendingSubmission());
    QVERIFY(acknowledgmentWhileRefreshing);
    QTRY_COMPARE(auth.state(), SessionStatus::Connected);
    QVERIFY(vm.polling());
    for (const auto &attempt : attempts) QCOMPARE(attempt, attempts.first());
}

QTEST_GUILESS_MAIN(TestConversations)
#include "tst_conversations.moc"
