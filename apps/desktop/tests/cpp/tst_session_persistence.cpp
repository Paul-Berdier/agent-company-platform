// Secrets exclusivement synthétiques. Les préférences sont isolées dans un répertoire
// temporaire ; le seul accès au coffre réel porte un préfixe de test UUID propre.
#include "services/SessionPersistence.h"
#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"
#include "storage/CredentialVault.h"
#include "storage/SettingsStore.h"
#ifdef Q_OS_WIN
#include "storage/WindowsCredentialVault.h"
#endif

#include <QDataStream>
#include <QFile>
#include <QHostAddress>
#include <QJsonObject>
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
class MemoryVault final : public CredentialVault {
public:
    QHash<QString, QByteArray> entries;
    int loads = 0, stores = 0, removals = 0;
    bool failLoad = false, failStore = false, failRemove = false;
    QString backendName() const override { return QStringLiteral("Coffre de test mémoire"); }
    bool canStore() const override { return true; }
    VaultStatus::State status() const override { return VaultStatus::Available; }
    VaultResult store(const QString &key, const QByteArray &value) override {
        ++stores;
        if (failStore) return VaultResult::failure(QStringLiteral("Écriture du coffre refusée."));
        entries.insert(key, value); return VaultResult::success();
    }
    VaultResult load(const QString &key, QByteArray &value) override {
        ++loads;
        if (failLoad || !entries.contains(key)) return VaultResult::failure(QStringLiteral("Lecture du coffre refusée."));
        value = entries.value(key); return VaultResult::success();
    }
    VaultResult remove(const QString &key) override {
        ++removals;
        if (failRemove) return VaultResult::failure(QStringLiteral("Effacement du coffre refusé."));
        entries.remove(key); return VaultResult::success();
    }
    bool contains(const QString &key) override { return entries.contains(key); }
};
struct Incoming {
    QPointer<QTcpSocket> socket;
    QByteArray headers;
};
class HttpFixture final : public QTcpServer {
public:
    QList<Incoming> received;
    std::function<void(const Incoming &)> handle;
    HttpFixture() {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (hasPendingConnections()) {
                auto *socket = nextPendingConnection();
                auto buffer = std::make_shared<QByteArray>();
                auto done = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, buffer, done] {
                    *buffer += socket->readAll();
                    if (*done) return;
                    const auto end = buffer->indexOf("\r\n\r\n");
                    if (end < 0) return;
                    int length = 0;
                    for (const auto &line : buffer->left(end).split('\n'))
                        if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                    if (buffer->size() < end + 4 + length) return;
                    *done = true;
                    const Incoming request{socket, buffer->left(end)};
                    received.append(request);
                    if (handle) handle(request);
                });
            }
        });
        if (!listen(QHostAddress::LocalHost)) qFatal("Bouclage de test indisponible");
    }
    QUrl url() const { return QUrl(QStringLiteral("http://127.0.0.1:%1").arg(serverPort())); }
    static void reply(const Incoming &request, int code, const QJsonObject &body,
                      const QByteArray &headers = {}) {
        if (!request.socket || request.socket->state() != QAbstractSocket::ConnectedState) return;
        const auto json = QJsonDocument(body).toJson(QJsonDocument::Compact);
        request.socket->write("HTTP/1.1 " + QByteArray::number(code) + " Test\r\nContent-Type: application/json\r\nConnection: close\r\n"
            + headers + "Content-Length: " + QByteArray::number(json.size()) + "\r\n\r\n" + json);
        request.socket->disconnectFromHost();
    }
};
const QUrl kServer(QStringLiteral("https://session-test.invalid/api"));
const QByteArray kCookie(64, 'x');
QJsonObject payload(const QDateTime &expires = QDateTime::currentDateTimeUtc().addSecs(3600)) {
    return {{QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("test-user")},
              {QStringLiteral("role"), QStringLiteral("owner")}}},
            {QStringLiteral("csrf_token"), QStringLiteral("csrf-ne-doit-jamais-etre-memorise")},
            {QStringLiteral("expires_at"), expires.toString(Qt::ISODateWithMs)}};
}
void configure(ApiClient &client, const QUrl &url = kServer) {
    client.setAllowInsecureLoopback(true);
    const auto error = client.setBaseUrl(url);
    if (error.isError()) qFatal("URL locale de test refusée");
}
void establish(ApiClient &client, AuthManager &auth, const QDateTime &expires = QDateTime::currentDateTimeUtc().addSecs(3600)) {
    QNetworkCookie cookie(QByteArrayLiteral("acp_session"), kCookie);
    cookie.setPath(QStringLiteral("/"));
    cookie.setHttpOnly(true);
    cookie.setSecure(client.baseUrl().scheme() == QStringLiteral("https"));
    cookie.setExpirationDate(expires);
    client.cookieJar()->setCookiesFromUrl({cookie}, client.resolve(QStringLiteral("/auth/session")));
    auth.applySessionPayload(payload(expires));
}
}

class TestSessionPersistence : public QObject {
    Q_OBJECT
private slots:
    void initTestCase();
    void init();
    void optInAndRestoreNeverRestorePrivileges();
    void completeCanonicalUrlScopesTheCredential();
    void corruptOrForeignDocumentIsPurged_data();
    void corruptOrForeignDocumentIsPurged();
    void expiryPurgesLiveAndSavedSessions();
    void logoutUnauthorizedAndRevocationPurge_data();
    void logoutUnauthorizedAndRevocationPurge();
    void disablingAndVaultFailuresAreExplicit();
    void serverChangePurgesOldScopeAndIdentity();
    void offlineResumeKeepsTheSavedSession();
    void loginUsesRealHttpCookieAndRotatesCsrf();
    void oldLoginAndResumeCannotRestoreAfterInvalidation_data();
    void oldLoginAndResumeCannotRestoreAfterInvalidation();
    void retryAndQueuedMutationsCannotMoveToAnotherServer();
    void unauthorizedEmitsOneTerminalDespiteReentrantPurge();
    void repeatedForbiddenHasOneRecoveryAndPreservesTheTerminal();
    void windowsCredentialVaultRoundTripIsIsolated();
private:
    QTemporaryDir m_preferences;
};

void TestSessionPersistence::initTestCase() {
    QVERIFY(m_preferences.isValid());
    QCoreApplication::setOrganizationName(QStringLiteral("ACP-tests-isoles"));
    QCoreApplication::setApplicationName(QUuid::createUuid().toString(QUuid::WithoutBraces));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, m_preferences.path());
}
void TestSessionPersistence::init() { QSettings settings; settings.clear(); settings.sync(); }

void TestSessionPersistence::optInAndRestoreNeverRestorePrivileges() {
    MemoryVault vault;
    SettingsStore settings;
    {
        ApiClient client; configure(client); AuthManager auth(&client);
        SessionPersistence persistence(&client, &auth, &vault, &settings);
        QVERIFY(!persistence.rememberSession());
        QVERIFY(!persistence.restore());
        QCOMPARE(vault.loads, 0);
        establish(client, auth);
        QCOMPARE(vault.stores, 0);
        persistence.setRememberSession(true);
        QVERIFY(vault.stores > 0);
        QVERIFY(vault.entries.value(SessionPersistence::credentialKey(kServer)).contains(kCookie));
        QVERIFY(!vault.entries.value(SessionPersistence::credentialKey(kServer)).contains("csrf-ne-doit"));
        settings.flush();
        QFile file(settings.location()); QVERIFY(file.open(QIODevice::ReadOnly));
        const auto preferences = file.readAll();
        QVERIFY(!preferences.contains(kCookie));
        QVERIFY(!preferences.contains("csrf-ne-doit"));
        QSettings onlyPreferences;
        QCOMPARE(onlyPreferences.allKeys(), QStringList{QStringLiteral("connection/rememberSession")});
    }
    ApiClient client; configure(client); AuthManager auth(&client);
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    QVERIFY(persistence.restore());
    QCOMPARE(auth.state(), SessionStatus::Disconnected);
    QVERIFY(auth.userId().isEmpty());
    QVERIFY(auth.platformRole().isEmpty());
    QVERIFY(!client.hasCsrfToken());
    QCOMPARE(client.inFlightCount(), 0);
    const auto cookies = client.cookieJar()->cookiesForUrl(client.resolve(QStringLiteral("/auth/session")));
    QCOMPARE(cookies.size(), 1);
    QVERIFY(cookies.first().isHttpOnly());
    QVERIFY(cookies.first().isSecure());
    QCOMPARE(cookies.first().sameSitePolicy(), QNetworkCookie::SameSite::Strict);
    QCOMPARE(cookies.first().value(), kCookie);
    QVERIFY(client.cookieJar()->cookiesForUrl(QUrl(QStringLiteral("https://other.invalid"))).isEmpty());
}

void TestSessionPersistence::completeCanonicalUrlScopesTheCredential() {
    const auto key = SessionPersistence::credentialKey(QUrl(QStringLiteral("https://EXAMPLE.invalid:443/api/")));
    QCOMPARE(key, SessionPersistence::credentialKey(QUrl(QStringLiteral("https://example.invalid/api"))));
    for (const auto &url : {"http://example.invalid/api", "https://example.invalid:444/api",
                           "https://example.invalid/other", "https://other.invalid/api"})
        QVERIFY(key != SessionPersistence::credentialKey(QUrl(QString::fromLatin1(url))));
}

void TestSessionPersistence::corruptOrForeignDocumentIsPurged_data() {
    QTest::addColumn<int>("variant");
    QTest::newRow("document-corrompu") << 0;
    QTest::newRow("autre-serveur") << 1;
    QTest::newRow("expiration-passee") << 2;
    QTest::newRow("longueur-malveillante") << 3;
}
void TestSessionPersistence::corruptOrForeignDocumentIsPurged() {
    QFETCH(int, variant);
    MemoryVault vault; SettingsStore settings;
    const auto key = SessionPersistence::credentialKey(kServer);
    {
        ApiClient client; configure(client); AuthManager auth(&client);
        SessionPersistence persistence(&client, &auth, &vault, &settings);
        persistence.setRememberSession(true); establish(client, auth);
    }
    auto document = vault.entries.value(key);
    if (variant == 0) document = QByteArrayLiteral("invalide");
    if (variant == 1) document.replace("session-test.invalid", "foreign-test.invalid");
    if (variant == 2) {
        QDataStream stream(&document, QIODevice::ReadWrite);
        QVERIFY(stream.device()->seek(6 + SessionPersistence::canonicalServer(kServer).size()));
        stream << qint64(QDateTime::currentMSecsSinceEpoch() - 1);
    }
    if (variant == 3) { document[4] = char(-1); document[5] = char(-1); }
    vault.entries[key] = document;
    ApiClient client; configure(client); AuthManager auth(&client);
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    QVERIFY(!persistence.restore());
    QVERIFY(!client.cookieJar()->hasSessionCookie());
    QVERIFY(!vault.entries.contains(key));
    QVERIFY(!client.hasCsrfToken());
}

void TestSessionPersistence::expiryPurgesLiveAndSavedSessions() {
    MemoryVault vault; SettingsStore settings; ApiClient client; configure(client); AuthManager auth(&client);
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    persistence.setRememberSession(true);
    establish(client, auth, QDateTime::currentDateTimeUtc().addMSecs(250));
    QVERIFY(!vault.entries.isEmpty());
    QTRY_COMPARE(auth.state(), SessionStatus::Expired);
    QVERIFY(vault.entries.isEmpty());
    QVERIFY(!client.cookieJar()->hasSessionCookie());
    QVERIFY(!client.hasCsrfToken());
}

void TestSessionPersistence::logoutUnauthorizedAndRevocationPurge_data() {
    QTest::addColumn<int>("mode");
    QTest::newRow("logout") << 0;
    QTest::newRow("401") << 1;
    QTest::newRow("revocation") << 2;
}
void TestSessionPersistence::logoutUnauthorizedAndRevocationPurge() {
    QFETCH(int, mode);
    HttpFixture server;
    MemoryVault vault; SettingsStore settings; ApiClient client; configure(client, server.url()); AuthManager auth(&client);
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    persistence.setRememberSession(true); establish(client, auth);
    QVERIFY(!vault.entries.isEmpty());
    if (mode == 0) auth.logOut();
    if (mode == 1) emit client.unauthorizedObserved();
    if (mode == 2) auth.forgetLocalSession(SessionStatus::Revoked, QStringLiteral("Révoquée."));
    QVERIFY(vault.entries.isEmpty());
    QVERIFY(!client.hasCsrfToken());
    QVERIFY(auth.userId().isEmpty());
    QVERIFY(!client.cookieJar()->hasSessionCookie());
    if (mode == 0) {
        QTRY_COMPARE(server.received.size(), 1);
        QVERIFY(server.received.first().headers.toLower().contains("cookie: acp_session="));
        QVERIFY(server.received.first().headers.toLower().contains("x-csrf-token:"));
        HttpFixture::reply(server.received.first(), 200, {});
        QTRY_COMPARE(client.inFlightCount(), 0);
    }
}

void TestSessionPersistence::disablingAndVaultFailuresAreExplicit() {
    MemoryVault vault; SettingsStore settings; ApiClient client; configure(client); AuthManager auth(&client);
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    establish(client, auth);
    vault.failStore = true;
    persistence.setRememberSession(true);
    QVERIFY(!persistence.error().isEmpty());
    QVERIFY(vault.entries.isEmpty());
    vault.failStore = false;
    persistence.setRememberSession(false);
    persistence.setRememberSession(true);
    QVERIFY(!vault.entries.isEmpty());
    persistence.setRememberSession(false);
    QVERIFY(vault.entries.isEmpty());
    QCOMPARE(auth.state(), SessionStatus::Connected); // Désactiver n'est pas déconnecter.
    persistence.setRememberSession(true);
    vault.failRemove = true;
    auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Déconnecté."));
    QVERIFY(!persistence.error().isEmpty());
    QVERIFY(!persistence.rememberSession()); // Même après redémarrage, aucune reprise de l'entrée non effacée.
    QVERIFY(!settings.rememberSession());
    QVERIFY(!persistence.restore());
    vault.failRemove = false;
    persistence.setRememberSession(true);
    vault.failLoad = true;
    QVERIFY(!persistence.restore());
    QVERIFY(!persistence.error().isEmpty());
    QVERIFY(!client.cookieJar()->hasSessionCookie());
}

void TestSessionPersistence::serverChangePurgesOldScopeAndIdentity() {
    MemoryVault vault; SettingsStore settings; ApiClient client; configure(client); AuthManager auth(&client);
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    persistence.setRememberSession(true); establish(client, auth);
    QVERIFY(!vault.entries.isEmpty());
    configure(client, QUrl(QStringLiteral("https://session-test.invalid/other")));
    QVERIFY(vault.entries.isEmpty());
    QVERIFY(auth.userId().isEmpty());
    QCOMPARE(auth.state(), SessionStatus::Disconnected);
    QVERIFY(!client.cookieJar()->hasSessionCookie());
    QVERIFY(!persistence.restore());
}

void TestSessionPersistence::offlineResumeKeepsTheSavedSession() {
    HttpFixture server;
    server.handle = [](const Incoming &request) { request.socket->abort(); };
    MemoryVault vault; SettingsStore settings; ApiClient client; configure(client, server.url()); AuthManager auth(&client);
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    persistence.setRememberSession(true); establish(client, auth);
    const int removals = vault.removals;
    auth.resumeSession();
    QTRY_COMPARE_WITH_TIMEOUT(auth.state(), SessionStatus::Offline, 10000);
    QVERIFY(!vault.entries.isEmpty());
    QVERIFY(client.cookieJar()->hasSessionCookie());
    QCOMPARE(vault.removals, removals);
}

void TestSessionPersistence::loginUsesRealHttpCookieAndRotatesCsrf() {
    HttpFixture server;
    server.handle = [](const Incoming &request) {
        HttpFixture::reply(request, 200, payload(), "Set-Cookie: acp_session=" + kCookie + "; Path=/; HttpOnly; SameSite=Strict\r\n");
    };
    MemoryVault vault; SettingsStore settings; ApiClient client; configure(client, server.url()); AuthManager auth(&client);
    SessionPersistence persistence(&client, &auth, &vault, &settings);
    persistence.setRememberSession(true);
    auth.logIn(QStringLiteral("fixture"), QStringLiteral("mot-de-passe-synthetique"));
    QTRY_COMPARE(auth.state(), SessionStatus::Connected);
    QVERIFY(client.hasCsrfToken());
    QVERIFY(client.cookieJar()->hasSessionCookie());
    QVERIFY(!vault.entries.isEmpty());
    QVERIFY(!vault.entries.cbegin().value().contains("mot-de-passe-synthetique"));
    auth.resumeSession();
    QTRY_COMPARE(server.received.size(), 2);
    QTRY_COMPARE(auth.state(), SessionStatus::Connected);
    QVERIFY(server.received.last().headers.toLower().contains("cookie: acp_session="));
}

void TestSessionPersistence::oldLoginAndResumeCannotRestoreAfterInvalidation_data() {
    QTest::addColumn<bool>("resume"); QTest::addColumn<bool>("changeServer");
    QTest::newRow("login-changement-serveur") << false << true;
    QTest::newRow("login-deconnexion") << false << false;
    QTest::newRow("resume-changement-serveur") << true << true;
    QTest::newRow("resume-deconnexion") << true << false;
}
void TestSessionPersistence::oldLoginAndResumeCannotRestoreAfterInvalidation() {
    QFETCH(bool, resume); QFETCH(bool, changeServer);
    HttpFixture oldServer, newServer;
    ApiClient client; configure(client, oldServer.url()); AuthManager auth(&client);
    if (resume) { establish(client, auth); auth.resumeSession(); }
    else auth.logIn(QStringLiteral("fixture"), QStringLiteral("synthetique"));
    QTRY_COMPARE(oldServer.received.size(), 1);
    if (changeServer) configure(client, newServer.url()); else auth.logOut();
    HttpFixture::reply(oldServer.received.first(), 200, payload(), "Set-Cookie: acp_session=" + kCookie + "; Path=/\r\n");
    QTRY_COMPARE(client.inFlightCount(), 0);
    QCoreApplication::processEvents();
    QCOMPARE(auth.state(), SessionStatus::Disconnected);
    QVERIFY(auth.userId().isEmpty());
    QVERIFY(!client.hasCsrfToken());
    QVERIFY(!client.cookieJar()->hasSessionCookie());
    QCOMPARE(newServer.received.size(), 0);
}

void TestSessionPersistence::retryAndQueuedMutationsCannotMoveToAnotherServer() {
    HttpFixture oldServer, newServer;
    oldServer.handle = [](const Incoming &request) { HttpFixture::reply(request, 503, {}, "Retry-After: 1\r\n"); };
    ApiClient client; configure(client, oldServer.url());
    ApiRequest request; request.path = QStringLiteral("/auth/session");
    auto *reading = client.sendCsrfRotating(request);
    QSignalSpy readFailure(reading, &ApiCall::failed);
    client.setCsrfToken(QStringLiteral("synthetique"));
    ApiRequest mutation; mutation.method = "POST"; mutation.path = QStringLiteral("/missions");
    auto *writing = client.send(mutation);
    QSignalSpy writeFailure(writing, &ApiCall::failed);
    QTRY_COMPARE(oldServer.received.size(), 1);
    // Laisser le 503 programmer son réessai, puis changer de destination pendant le recul.
    QTest::qWait(100);
    QCOMPARE(readFailure.size(), 0);
    configure(client, newServer.url());
    QTRY_COMPARE(readFailure.size(), 1);
    QTRY_COMPARE(writeFailure.size(), 1);
    QTest::qWait(1100);
    QCOMPARE(oldServer.received.size(), 1);
    QCOMPARE(newServer.received.size(), 0);
    QCOMPARE(client.inFlightCount(), 0);
}

void TestSessionPersistence::unauthorizedEmitsOneTerminalDespiteReentrantPurge() {
    HttpFixture server;
    server.handle = [](const Incoming &request) { HttpFixture::reply(request, 401, {}); };
    ApiClient client; configure(client, server.url()); AuthManager auth(&client); establish(client, auth);
    ApiRequest request; request.path = QStringLiteral("/projects");
    auto *call = client.send(request);
    int failures = 0; ApiFailure::Kind kind = ApiFailure::None;
    connect(call, &ApiCall::failed, this, [&](const ApiError &error) { ++failures; kind = error.kind(); });
    QTRY_COMPARE(failures, 1);
    QCOMPARE(kind, ApiFailure::Unauthorized);
    QCOMPARE(auth.state(), SessionStatus::Expired);
    QCOMPARE(client.inFlightCount(), 0);
}

void TestSessionPersistence::windowsCredentialVaultRoundTripIsIsolated() {
#ifdef Q_OS_WIN
    WindowsCredentialVault vault(QStringLiteral("ACP.Test.Session.") + QUuid::createUuid().toString(QUuid::WithoutBraces));
    const QString key = QStringLiteral("roundtrip");
    struct Cleanup { CredentialVault &vault; QString key; ~Cleanup() { vault.remove(key); } } cleanup{vault, key};
    QByteArray secret = QByteArrayLiteral("cookie-synthetique-aucune-identite-utilisateur");
    const auto written = vault.store(key, secret);
    if (!written.ok) QSKIP(qPrintable(written.reason));
    QByteArray loaded;
    QVERIFY(vault.load(key, loaded).ok);
    QCOMPARE(loaded, secret);
    CredentialVault::wipe(loaded); CredentialVault::wipe(secret);
    QVERIFY(vault.remove(key).ok);
    QVERIFY(!vault.contains(key));
#else
    QSKIP("Coffre Windows réel non disponible sur cette plateforme.");
#endif
}

void TestSessionPersistence::repeatedForbiddenHasOneRecoveryAndPreservesTheTerminal() {
    HttpFixture server;
    int resumed = 0;
    server.handle = [&resumed](const Incoming &request) {
        if (request.headers.startsWith("GET /auth/session ")) {
            ++resumed;
            HttpFixture::reply(request, 200, payload());
        } else HttpFixture::reply(request, 403, {});
    };
    ApiClient client; configure(client, server.url()); AuthManager auth(&client); establish(client, auth);
    ApiRequest request; request.path = QStringLiteral("/restricted");
    for (int attempt = 0; attempt < 2; ++attempt) {
        QPointer<ApiCall> call = client.send(request);
        int failures = 0;
        ApiFailure::Kind kind = ApiFailure::None;
        connect(call, &ApiCall::failed, this, [&](const ApiError &error) { ++failures; kind = error.kind(); });
        // Une VM peut annuler ses lectures pendant le signal de changement d'état.
        const auto connection = connect(&client, &ApiClient::forbiddenObserved, this, [call] { if (call) call->abort(); });
        QTRY_COMPARE(failures, 1);
        QCOMPARE(kind, ApiFailure::Forbidden);
        QTRY_COMPARE(client.inFlightCount(), 0);
        QCOMPARE(auth.state(), SessionStatus::Connected);
        QCOMPARE(resumed, 1);
        disconnect(connection);
    }
}

QTEST_GUILESS_MAIN(TestSessionPersistence)
#include "tst_session_persistence.moc"
