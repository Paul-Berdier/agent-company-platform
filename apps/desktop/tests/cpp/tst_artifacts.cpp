#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"
#include "services/ArtifactDownload.h"
#include "viewmodels/ArtifactsViewModel.h"

#include <QCryptographicHash>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkCookie>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>
#include <QUrlQuery>
#include <functional>
#include <memory>

using namespace acp;

class LocalHttp : public QObject
{
public:
    QTcpServer server;
    QList<QByteArray> requests;
    std::function<void(QTcpSocket *, const QByteArray &)> handler;
    LocalHttp()
    {
        if (!server.listen(QHostAddress::LocalHost, 0)) qFatal("Serveur de test local inaccessible");
        connect(&server, &QTcpServer::newConnection, this, [this] {
            while (server.hasPendingConnections()) {
                QTcpSocket *socket = server.nextPendingConnection();
                const auto bytes = std::make_shared<QByteArray>();
                const auto handled = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, bytes, handled] {
                    bytes->append(socket->readAll());
                    if (*handled || !bytes->contains(QByteArrayLiteral("\r\n\r\n"))) return;
                    *handled = true;
                    requests.append(*bytes);
                    if (handler) handler(socket, *bytes);
                });
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            }
        });
    }
    QUrl origin() const { return QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort())); }
    static void reply(QTcpSocket *socket, const QByteArray &body, bool withLength = true,
                      int status = 200, const QByteArray &headers = {})
    {
        QByteArray output = QByteArrayLiteral("HTTP/1.1 ") + QByteArray::number(status)
            + QByteArrayLiteral(" Result\r\nConnection: close\r\nContent-Type: application/json\r\n");
        if (withLength) output += QByteArrayLiteral("Content-Length: ") + QByteArray::number(body.size()) + QByteArrayLiteral("\r\n");
        socket->write(output + headers + QByteArrayLiteral("\r\n") + body);
        socket->disconnectFromHost();
    }
};

class TestArtifacts : public QObject
{
    Q_OBJECT
private:
    static void configure(ApiClient &client, const LocalHttp &http)
    {
        client.setAllowInsecureLoopback(true);
        QVERIFY(!client.setBaseUrl(http.origin()).isError());
    }
    static void authenticate(AuthManager &auth)
    {
        auth.applySessionPayload(QJsonObject{
            {QStringLiteral("csrf_token"), QStringLiteral("jeton-factice")},
            {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("u1")},
                                                {QStringLiteral("role"), QStringLiteral("owner")}}},
            {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00.000Z")}});
    }
    static QByteArray read(const QString &path)
    {
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) return {};
        return file.readAll();
    }
    static void existingFile(const QString &path)
    {
        QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write(QByteArrayLiteral("ancien")), 6);
    }
    static QJsonObject artifact(const QString &id, const QString &project)
    {
        return {{QStringLiteral("id"), id}, {QStringLiteral("project_id"), project},
                {QStringLiteral("original_name"), QStringLiteral("rapport.txt")},
                {QStringLiteral("size_bytes"), 3}, {QStringLiteral("has_content"), true}};
    }
    static QByteArray page(const QJsonArray &items, const QJsonValue &cursor = QJsonValue::Null)
    {
        return QJsonDocument(QJsonObject{{QStringLiteral("items"), items},
                                        {QStringLiteral("next_cursor"), cursor}}).toJson(QJsonDocument::Compact);
    }
private slots:
    void streamedExportUsesSessionAndVerifiesContent()
    {
        LocalHttp http;
        const QByteArray content(180000, 'x');
        http.handler = [&content](QTcpSocket *socket, const QByteArray &) { LocalHttp::reply(socket, content); };
        ApiClient client;
        configure(client, http);
        QNetworkCookie cookie(QByteArrayLiteral("acp_session"), QByteArrayLiteral("session-factice"));
        cookie.setPath(QStringLiteral("/"));
        QVERIFY(client.cookieJar()->setCookiesFromUrl({cookie}, http.origin()));
        QTemporaryDir directory;
        const QString target = directory.filePath(QStringLiteral("export.bin"));
        ArtifactDownload download(&client);
        QSignalSpy success(&download, &ArtifactDownload::succeeded);
        download.start(QStringLiteral("artifact-1"), QUrl::fromLocalFile(target), content.size(),
                       QString::fromLatin1(QCryptographicHash::hash(content, QCryptographicHash::Sha256).toHex()));
        QTRY_COMPARE_WITH_TIMEOUT(success.count(), 1, 5000);
        QCOMPARE(read(target), content);
        QCOMPARE(download.received(), content.size());
        QVERIFY(download.error().isEmpty());
        // Les noms d'en-têtes HTTP sont insensibles à la casse.
        QByteArray sessionHeader;
        for (const QByteArray &line : http.requests.first().split('\n')) {
            const qsizetype separator = line.indexOf(':');
            if (separator > 0 && line.left(separator).trimmed().compare(
                    QByteArrayLiteral("cookie"), Qt::CaseInsensitive) == 0) {
                sessionHeader = line.mid(separator + 1).trimmed();
                break;
            }
        }
        QCOMPARE(sessionHeader, QByteArrayLiteral("acp_session=session-factice"));
    }

    void overrunWithoutContentLengthPreservesExistingFile()
    {
        LocalHttp http;
        http.handler = [](QTcpSocket *socket, const QByteArray &) { LocalHttp::reply(socket, QByteArrayLiteral("abcdef"), false); };
        ApiClient client;
        configure(client, http);
        QTemporaryDir directory;
        const QString target = directory.filePath(QStringLiteral("export.bin"));
        existingFile(target);
        ArtifactDownload download(&client);
        QSignalSpy failed(&download, &ArtifactDownload::failed);
        QSignalSpy success(&download, &ArtifactDownload::succeeded);
        download.start(QStringLiteral("artifact-1"), QUrl::fromLocalFile(target), 3, {});
        QTRY_COMPARE_WITH_TIMEOUT(failed.count(), 1, 5000);
        QCOMPARE(success.count(), 0);
        QCOMPARE(read(target), QByteArrayLiteral("ancien"));
        QVERIFY(download.error().contains(QStringLiteral("dépasse")));
    }

    void mismatchedHeaderAndChecksumAreRefused_data()
    {
        QTest::addColumn<qint64>("expected");
        QTest::addColumn<QString>("checksum");
        QTest::newRow("taille") << qint64(6) << QString();
        QTest::newRow("empreinte") << qint64(3) << QString(64, QLatin1Char('0'));
    }
    void mismatchedHeaderAndChecksumAreRefused()
    {
        QFETCH(qint64, expected);
        QFETCH(QString, checksum);
        LocalHttp http;
        http.handler = [](QTcpSocket *socket, const QByteArray &) { LocalHttp::reply(socket, QByteArrayLiteral("abc")); };
        ApiClient client;
        configure(client, http);
        QTemporaryDir directory;
        const QString target = directory.filePath(QStringLiteral("export.bin"));
        existingFile(target);
        ArtifactDownload download(&client);
        QSignalSpy failed(&download, &ArtifactDownload::failed);
        download.start(QStringLiteral("artifact-1"), QUrl::fromLocalFile(target), expected, checksum);
        QTRY_COMPARE_WITH_TIMEOUT(failed.count(), 1, 5000);
        QCOMPARE(read(target), QByteArrayLiteral("ancien"));
        QVERIFY(download.savedFile().isEmpty());
    }

    void redirectNeverSendsCredentialsToAnotherOrigin()
    {
        LocalHttp http, external;
        external.handler = [](QTcpSocket *socket, const QByteArray &) { LocalHttp::reply(socket, QByteArrayLiteral("secret")); };
        http.handler = [&external](QTcpSocket *socket, const QByteArray &) {
            LocalHttp::reply(socket, {}, true, 302,
                             QByteArrayLiteral("Location: ") + external.origin().toEncoded() + QByteArrayLiteral("/leak\r\n"));
        };
        ApiClient client;
        configure(client, http);
        QNetworkCookie cookie(QByteArrayLiteral("acp_session"), QByteArrayLiteral("session-factice"));
        cookie.setPath(QStringLiteral("/"));
        QVERIFY(client.cookieJar()->setCookiesFromUrl({cookie}, http.origin()));
        QTemporaryDir directory;
        ArtifactDownload download(&client);
        QSignalSpy failed(&download, &ArtifactDownload::failed);
        download.start(QStringLiteral("artifact-1"), QUrl::fromLocalFile(directory.filePath(QStringLiteral("x"))), 6, {});
        QTRY_COMPARE_WITH_TIMEOUT(failed.count(), 1, 5000);
        QTest::qWait(50);
        QCOMPARE(external.requests.size(), 0);
        QVERIFY(download.savedFile().isEmpty());
    }

    void cancellationDiscardsPartialData()
    {
        LocalHttp http;
        http.handler = [](QTcpSocket *socket, const QByteArray &) {
            socket->write(QByteArrayLiteral("HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nabc"));
            socket->flush();
        };
        ApiClient client;
        configure(client, http);
        QTemporaryDir directory;
        const QString target = directory.filePath(QStringLiteral("x"));
        existingFile(target);
        ArtifactDownload download(&client);
        QSignalSpy success(&download, &ArtifactDownload::succeeded);
        download.start(QStringLiteral("artifact-1"), QUrl::fromLocalFile(target), 6, {});
        QTRY_COMPARE_WITH_TIMEOUT(download.received(), 3, 5000);
        download.cancel();
        QVERIFY(!download.busy());
        QCOMPARE(read(target), QByteArrayLiteral("ancien"));
        QCOMPARE(success.count(), 0);
    }

    void oversizedMetadataNeverStartsTheNetwork()
    {
        LocalHttp http;
        ApiClient client;
        configure(client, http);
        QTemporaryDir directory;
        ArtifactDownload download(&client);
        download.start(QStringLiteral("artifact-1"), QUrl::fromLocalFile(directory.filePath(QStringLiteral("x"))),
                       ArtifactDownload::MaximumBytes + 1, {});
        QVERIFY(!download.busy());
        QVERIFY(download.error().contains(QStringLiteral("512")));
        QCOMPARE(http.requests.size(), 0);
    }

    void projectFilterPaginationAndMetadataUseRealRoutes()
    {
        LocalHttp http;
        http.handler = [](QTcpSocket *socket, const QByteArray &request) {
            const QUrl url = QUrl::fromEncoded(request.split(' ').at(1));
            if (url.path() == QStringLiteral("/artifacts/a2")) {
                LocalHttp::reply(socket, QJsonDocument(artifact(QStringLiteral("a2"), QStringLiteral("p1"))).toJson());
            } else if (QUrlQuery(url).hasQueryItem(QStringLiteral("cursor"))) {
                LocalHttp::reply(socket, page({artifact(QStringLiteral("a2"), QStringLiteral("p1"))}));
            } else {
                LocalHttp::reply(socket, page({artifact(QStringLiteral("a1"), QStringLiteral("p1"))}, QStringLiteral("opaque+/=")));
            }
        };
        ApiClient client;
        configure(client, http);
        AuthManager auth(&client);
        authenticate(auth);
        ArtifactsViewModel model(&client, &auth);
        model.setRunId(QStringLiteral("run-1"));
        model.setStreamKind(QStringLiteral("stdout"));
        model.setProjectId(QStringLiteral("p1"));
        // Un changement de projet vide le filtre run ; on le pose sur ce projet.
        model.setRunId(QStringLiteral("run-1"));
        QTRY_COMPARE_WITH_TIMEOUT(model.rows()->count(), 1, 5000);
        QVERIFY(model.canLoadMore());
        model.nextPage();
        QTRY_COMPARE_WITH_TIMEOUT(model.rows()->count(), 2, 5000);
        QVERIFY(!model.canLoadMore());
        const QUrl url = QUrl::fromEncoded(http.requests.last().split(' ').at(1));
        const QUrlQuery query(url);
        QCOMPARE(query.queryItemValue(QStringLiteral("project_id")), QStringLiteral("p1"));
        QCOMPARE(query.queryItemValue(QStringLiteral("task_run_id")), QStringLiteral("run-1"));
        QCOMPARE(query.queryItemValue(QStringLiteral("stream_kind")), QStringLiteral("stdout"));
        QCOMPARE(query.queryItemValue(QStringLiteral("cursor")), QStringLiteral("opaque+/="));
        model.selectArtifact(QStringLiteral("a2"));
        QTRY_COMPARE_WITH_TIMEOUT(model.selected().value(QStringLiteral("id")).toString(), QStringLiteral("a2"), 5000);
        QCOMPARE(model.suggestedFileName(), QStringLiteral("rapport.txt"));
    }

    void projectAndSessionChangesDiscardStaleResponses()
    {
        LocalHttp http;
        QPointer<QTcpSocket> first;
        http.handler = [&first](QTcpSocket *socket, const QByteArray &request) {
            const QUrl url = QUrl::fromEncoded(request.split(' ').at(1));
            if (QUrlQuery(url).queryItemValue(QStringLiteral("project_id")) == QStringLiteral("p1"))
                first = socket;
            else
                LocalHttp::reply(socket, page({artifact(QStringLiteral("a2"), QStringLiteral("p2"))}));
        };
        ApiClient client;
        configure(client, http);
        AuthManager auth(&client);
        authenticate(auth);
        ArtifactsViewModel model(&client, &auth);
        model.setProjectId(QStringLiteral("p1"));
        QTRY_VERIFY_WITH_TIMEOUT(!first.isNull(), 5000);
        model.setProjectId(QStringLiteral("p2"));
        QTRY_COMPARE_WITH_TIMEOUT(model.rows()->count(), 1, 5000);
        QCOMPARE(model.rows()->get(0).value(QStringLiteral("id")).toString(), QStringLiteral("a2"));
        if (first && first->state() == QAbstractSocket::ConnectedState)
            LocalHttp::reply(first, page({artifact(QStringLiteral("a1"), QStringLiteral("p1"))}));
        auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Fin de session"));
        QCOMPARE(model.rows()->count(), 0);
        QVERIFY(model.selected().isEmpty());
        QVERIFY(!model.busy());
    }

    void originChangeAbortsStreamingAndPreservesDestination()
    {
        LocalHttp http, other;
        http.handler = [](QTcpSocket *socket, const QByteArray &) {
            socket->write(QByteArrayLiteral("HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nabc"));
            socket->flush();
        };
        ApiClient client;
        configure(client, http);
        QTemporaryDir directory;
        const QString target = directory.filePath(QStringLiteral("x"));
        existingFile(target);
        ArtifactDownload download(&client);
        QSignalSpy success(&download, &ArtifactDownload::succeeded);
        download.start(QStringLiteral("a1"), QUrl::fromLocalFile(target), 6, {});
        QTRY_COMPARE_WITH_TIMEOUT(download.received(), 3, 5000);
        QVERIFY(!client.setBaseUrl(other.origin()).isError());
        QVERIFY(!download.busy());
        QCOMPARE(read(target), QByteArrayLiteral("ancien"));
        QCOMPARE(success.count(), 0);
        QCOMPARE(other.requests.size(), 0);
    }

    void logoutAbortsSelectedDownloadAndClearsMetadata()
    {
        LocalHttp http;
        http.handler = [](QTcpSocket *socket, const QByteArray &request) {
            const QUrl url = QUrl::fromEncoded(request.split(' ').at(1));
            if (url.path().endsWith(QStringLiteral("/content"))) {
                socket->write(QByteArrayLiteral("HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\na"));
                socket->flush();
            } else if (url.path() == QStringLiteral("/artifacts/a1")) {
                LocalHttp::reply(socket, QJsonDocument(artifact(QStringLiteral("a1"), QStringLiteral("p1"))).toJson());
            } else {
                LocalHttp::reply(socket, page({artifact(QStringLiteral("a1"), QStringLiteral("p1"))}));
            }
        };
        ApiClient client;
        configure(client, http);
        AuthManager auth(&client);
        authenticate(auth);
        ArtifactsViewModel model(&client, &auth);
        model.setProjectId(QStringLiteral("p1"));
        QTRY_COMPARE_WITH_TIMEOUT(model.rows()->count(), 1, 5000);
        model.selectArtifact(QStringLiteral("a1"));
        QTRY_VERIFY_WITH_TIMEOUT(!model.selected().isEmpty(), 5000);
        QTemporaryDir directory;
        const QString target = directory.filePath(QStringLiteral("x"));
        existingFile(target);
        model.downloadSelected(QUrl::fromLocalFile(target), QStringLiteral("a1"));
        QTRY_COMPARE_WITH_TIMEOUT(model.downloader()->received(), 1, 5000);
        auth.forgetLocalSession(SessionStatus::Disconnected, QStringLiteral("Fin de session"));
        QVERIFY(!model.downloader()->busy());
        QVERIFY(model.selected().isEmpty());
        QCOMPARE(model.rows()->count(), 0);
        QCOMPARE(read(target), QByteArrayLiteral("ancien"));
        QVERIFY(model.downloader()->savedFile().isEmpty());
    }

    void filenameNeverEscapesTheChosenFolder()
    {
        QCOMPARE(ArtifactDownload::safeFileName(QStringLiteral("../../rapport.txt")), QStringLiteral("rapport.txt"));
        QCOMPARE(ArtifactDownload::safeFileName(QStringLiteral("C:\\secret\\CON.txt")), QStringLiteral("_CON.txt"));
        QCOMPARE(ArtifactDownload::safeFileName(QStringLiteral("../")), QStringLiteral("livrable.bin"));
        QVERIFY(!ArtifactDownload::safeFileName(QStringLiteral("bad:name?.txt")).contains(QLatin1Char(':')));
    }
};

QTEST_GUILESS_MAIN(TestArtifacts)
#include "tst_artifacts.moc"
