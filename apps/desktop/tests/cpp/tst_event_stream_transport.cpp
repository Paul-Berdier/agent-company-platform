// Le serveur local fournit du vrai HTTP : ces tests exercent les refus, le cookie
// partagé, la fermeture et le recul des connexions SSE, sans serveur externe.
#include "events/EventStreamService.h"
#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"
#include "services/SessionPersistence.h"
#include "storage/CredentialVault.h"
#include "storage/SettingsStore.h"

#include <QElapsedTimer>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkCookie>
#include <QPointer>
#include <QSettings>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>
#include <functional>

using namespace acp;

namespace {
struct Incoming { QPointer<QTcpSocket> socket; QByteArray target, headers; };
class HttpFixture final : public QTcpServer {
public:
    std::function<void(const Incoming &)> stream;
    QList<Incoming> streams;
    HttpFixture() {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (hasPendingConnections()) {
                auto *socket = nextPendingConnection();
                auto bytes = std::make_shared<QByteArray>();
                auto done = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, bytes, done] {
                    *bytes += socket->readAll();
                    if (*done || !bytes->contains("\r\n\r\n")) return;
                    *done = true;
                    Incoming request{socket, bytes->split(' ').value(1), *bytes};
                    if (request.target.startsWith("/streams/")) {
                        streams.append(request);
                        if (stream) stream(request);
                    } else {
                        const auto body = QJsonDocument(QJsonObject{{QStringLiteral("events"), QJsonArray{}},
                            {QStringLiteral("has_more"), false}, {QStringLiteral("next_cursor"), 0}}).toJson(QJsonDocument::Compact);
                        reply(request, 200, "application/json", body);
                    }
                });
            }
        });
        if (!listen(QHostAddress::LocalHost)) qFatal("Bouclage SSE de test indisponible");
    }
    QUrl url() const { return QUrl(QStringLiteral("http://127.0.0.1:%1").arg(serverPort())); }
    static void reply(const Incoming &request, int status, const QByteArray &type,
                      const QByteArray &body, const QByteArray &headers = {}, bool keepOpen = false) {
        if (!request.socket || request.socket->state() != QAbstractSocket::ConnectedState) return;
        QByteArray response = "HTTP/1.1 " + QByteArray::number(status) + " Test\r\n";
        if (!type.isEmpty()) response += "Content-Type: " + type + "\r\n";
        response += headers;
        if (keepOpen) response += "Connection: keep-alive\r\n\r\n";
        else response += "Content-Length: " + QByteArray::number(body.size()) + "\r\nConnection: close\r\n\r\n";
        request.socket->write(response + body);
        if (!keepOpen) request.socket->disconnectFromHost();
    }
};
class MemoryVault final : public CredentialVault {
public:
    QHash<QString, QByteArray> entries;
    QString backendName() const override { return QStringLiteral("Test mémoire"); }
    bool canStore() const override { return true; }
    VaultStatus::State status() const override { return VaultStatus::Available; }
    VaultResult store(const QString &key, const QByteArray &value) override { entries[key] = value; return VaultResult::success(); }
    VaultResult load(const QString &key, QByteArray &value) override {
        if (!entries.contains(key)) return VaultResult::failure(QStringLiteral("Absent"));
        value = entries[key]; return VaultResult::success();
    }
    VaultResult remove(const QString &key) override { entries.remove(key); return VaultResult::success(); }
    bool contains(const QString &key) override { return entries.contains(key); }
};
void configure(ApiClient &client, const QUrl &url) {
    client.setAllowInsecureLoopback(true);
    if (client.setBaseUrl(url).isError()) qFatal("URL SSE de test refusée");
}
void establish(ApiClient &client, AuthManager &auth) {
    const auto expires = QDateTime::currentDateTimeUtc().addSecs(3600);
    QNetworkCookie cookie("acp_session", QByteArray(64, 'a'));
    cookie.setPath(QStringLiteral("/")); cookie.setHttpOnly(true); cookie.setExpirationDate(expires);
    client.cookieJar()->setCookiesFromUrl({cookie}, client.resolve(QStringLiteral("/auth/session")));
    auth.applySessionPayload({{QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("test")}, {QStringLiteral("role"), QStringLiteral("owner")}}},
        {QStringLiteral("csrf_token"), QStringLiteral("synthetique")}, {QStringLiteral("expires_at"), expires.toString(Qt::ISODateWithMs)}});
}
QByteArray changedCookie() { return "Set-Cookie: acp_session=" + QByteArray(64, 'z') + "; Path=/; HttpOnly\r\n"; }
}

class TestEventStreamTransport : public QObject {
    Q_OBJECT
private slots:
    void initTestCase();
    void init();
    void unauthorizedPurgesSessionButForbiddenKeepsIt_data();
    void unauthorizedPurgesSessionButForbiddenKeepsIt();
    void invalidResponsesNeverBecomeLiveOrReconnect_data();
    void invalidResponsesNeverBecomeLiveOrReconnect();
    void streamCookiesAreIgnoredAndResetClosesTheSocket_data();
    void streamCookiesAreIgnoredAndResetClosesTheSocket();
    void networkFailuresUseBackoffAndStopCancelsReconnection();
private:
    QTemporaryDir m_preferences;
};

void TestEventStreamTransport::initTestCase() {
    QVERIFY(m_preferences.isValid());
    QCoreApplication::setOrganizationName(QStringLiteral("ACP-tests-SSE"));
    QCoreApplication::setApplicationName(QUuid::createUuid().toString(QUuid::WithoutBraces));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, m_preferences.path());
}
void TestEventStreamTransport::init() { QSettings preferences; preferences.clear(); preferences.sync(); }

void TestEventStreamTransport::unauthorizedPurgesSessionButForbiddenKeepsIt_data() {
    QTest::addColumn<int>("status"); QTest::newRow("401") << 401; QTest::newRow("403") << 403;
}
void TestEventStreamTransport::unauthorizedPurgesSessionButForbiddenKeepsIt() {
    QFETCH(int, status);
    HttpFixture server;
    server.stream = [status](const Incoming &request) { HttpFixture::reply(request, status, "application/json", "{}", changedCookie()); };
    ApiClient client; configure(client, server.url()); AuthManager auth(&client);
    MemoryVault vault; SettingsStore settings;
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    persistence.setRememberSession(true); establish(client, auth);
    QVERIFY(!vault.entries.isEmpty());
    EventStreamService service(&client);
    QPointer<StreamSubscription> subscription = service.subscribeRun(QStringLiteral("run"));
    QVERIFY(subscription);
    QSignalSpy refused(subscription, &StreamSubscription::refused);
    bool wasLive = false;
    connect(subscription, &StreamSubscription::statusChanged, this, [&] {
        if (subscription && subscription->status() == StreamStatus::Live) wasLive = true;
    });
    QTRY_COMPARE(refused.size(), 1);
    QVERIFY(!wasLive);
    if (status == 401) {
        QTRY_COMPARE(auth.state(), SessionStatus::Expired);
        QVERIFY(vault.entries.isEmpty()); QVERIFY(!client.cookieJar()->hasSessionCookie());
        QVERIFY(!client.hasCsrfToken()); QCOMPARE(service.activeCount(), 0);
    } else {
        QCOMPARE(auth.state(), SessionStatus::Connected);
        QVERIFY(!vault.entries.isEmpty());
        QVERIFY(subscription); QCOMPARE(subscription->status(), StreamStatus::Refused);
        QCOMPARE(client.cookieJar()->cookiesForUrl(client.baseUrl()).first().value(), QByteArray(64, 'a'));
    }
    service.closeAll();
}

void TestEventStreamTransport::invalidResponsesNeverBecomeLiveOrReconnect_data() {
    QTest::addColumn<int>("status"); QTest::addColumn<QByteArray>("type");
    QTest::newRow("redirection") << 302 << QByteArray("text/event-stream");
    QTest::newRow("html") << 200 << QByteArray("text/html");
    QTest::newRow("sans-type") << 200 << QByteArray();
    QTest::newRow("201") << 201 << QByteArray("text/event-stream");
}
void TestEventStreamTransport::invalidResponsesNeverBecomeLiveOrReconnect() {
    QFETCH(int, status); QFETCH(QByteArray, type);
    HttpFixture server;
    server.stream = [status, type](const Incoming &request) {
        HttpFixture::reply(request, status, type, "event: acp.event\nid: 1\ndata: {\"id\":\"faux\"}\n\n",
                           changedCookie() + "Location: https://other.invalid/\r\n");
    };
    ApiClient client; configure(client, server.url()); AuthManager auth(&client); establish(client, auth);
    EventStreamService service(&client);
    auto *subscription = service.subscribeRun(QStringLiteral("run"));
    QSignalSpy events(subscription, &StreamSubscription::journalEvent);
    bool wasLive = false;
    connect(subscription, &StreamSubscription::statusChanged, this, [&] {
        if (subscription->status() == StreamStatus::Live) wasLive = true;
    });
    QTRY_COMPARE(subscription->status(), StreamStatus::Refused);
    QTest::qWait(1300);
    QCOMPARE(server.streams.size(), 1); QVERIFY(!wasLive); QCOMPARE(events.size(), 0);
    QCOMPARE(client.cookieJar()->cookiesForUrl(client.baseUrl()).first().value(), QByteArray(64, 'a'));
    service.closeAll();
}

void TestEventStreamTransport::streamCookiesAreIgnoredAndResetClosesTheSocket_data() {
    QTest::addColumn<bool>("serverChange"); QTest::newRow("logout") << false; QTest::newRow("server-change") << true;
}
void TestEventStreamTransport::streamCookiesAreIgnoredAndResetClosesTheSocket() {
    QFETCH(bool, serverChange);
    HttpFixture server, other;
    server.stream = [](const Incoming &request) {
        HttpFixture::reply(request, 200, "text/event-stream; charset=utf-8", ": ping\n\n", changedCookie(), true);
    };
    ApiClient client; configure(client, server.url()); AuthManager auth(&client); establish(client, auth);
    EventStreamService service(&client);
    auto *subscription = service.subscribeRun(QStringLiteral("run"));
    QTRY_COMPARE(subscription->status(), StreamStatus::Live);
    QCOMPARE(client.cookieJar()->cookiesForUrl(client.baseUrl()).first().value(), QByteArray(64, 'a'));
    const auto socket = server.streams.first().socket;
    if (serverChange) configure(client, other.url());
    else auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Déconnecté."));
    QCOMPARE(service.activeCount(), 0);
    // Le serveur peut encore essayer d'émettre avant d'apprendre la fermeture.
    if (socket && socket->state() == QAbstractSocket::ConnectedState) socket->write("event: acp.event\ndata: {}\n\n");
    QTRY_VERIFY(!socket || socket->state() == QAbstractSocket::UnconnectedState);
    QVERIFY(!client.cookieJar()->hasSessionCookie()); QVERIFY(!client.hasCsrfToken());
    QCOMPARE(other.streams.size(), 0);
}

void TestEventStreamTransport::networkFailuresUseBackoffAndStopCancelsReconnection() {
    HttpFixture server;
    QElapsedTimer elapsed; elapsed.start(); QList<qint64> times;
    server.stream = [&](const Incoming &request) {
        times.append(elapsed.elapsed());
        HttpFixture::reply(request, 503, "application/json", "{}");
    };
    ApiClient client; configure(client, server.url());
    EventStreamService service(&client);
    auto *subscription = service.subscribeRun(QStringLiteral("run"));
    bool wasLive = false;
    connect(subscription, &StreamSubscription::statusChanged, this, [&] {
        if (subscription->status() == StreamStatus::Live) wasLive = true;
    });
    QTRY_VERIFY_WITH_TIMEOUT(times.size() >= 3, 6500);
    QVERIFY(times.at(1) - times.at(0) >= 900);
    QVERIFY(times.at(2) - times.at(1) >= 1800);
    QVERIFY(!wasLive);
    service.closeAll();
    const auto count = times.size();
    QTest::qWait(5500); // Dépasse le troisième recul (4 s + gigue maximale de 1 s).
    QCOMPARE(times.size(), count); QCOMPARE(service.activeCount(), 0);
}

QTEST_GUILESS_MAIN(TestEventStreamTransport)
#include "tst_event_stream_transport.moc"
