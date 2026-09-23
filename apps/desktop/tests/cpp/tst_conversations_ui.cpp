// Recette du vrai QML de conversation, avec serveur HTTP jetable et aucune donnée utilisateur.
#include "app/Application.h"
#include "api/ApiClient.h"
#include "auth/AuthManager.h"
#include "models/JsonListModel.h"
#include "system/SystemAppearance.h"
#include "viewmodels/ConversationsViewModel.h"
#include <QClipboard>
#include <QDir>
#include <QElapsedTimer>
#include <QGuiApplication>
#include <QHostAddress>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMimeData>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QScopeGuard>
#include <QSettings>
#include <QSGRendererInterface>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>
#include <QTimer>
#include <QWheelEvent>
#include <memory>
#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

using namespace acp;
namespace {
QJsonObject chat(const QString &id, const QJsonValue &project = QJsonValue::Null)
{
    return {{QStringLiteral("id"), id}, {QStringLiteral("project_id"), project},
        {QStringLiteral("title"), QStringLiteral("Chat %1").arg(id.section(QLatin1Char('-'), -1))},
        {QStringLiteral("status"), QStringLiteral("active")},
        {QStringLiteral("created_at"), QStringLiteral("2026-09-23T10:00:00Z")},
        {QStringLiteral("updated_at"), QStringLiteral("2026-09-23T10:00:00Z")}};
}
QJsonObject completedTurn(const QString &id, const QString &content, const QString &answer)
{
    return {{QStringLiteral("id"), id}, {QStringLiteral("client_request_id"), id},
        {QStringLiteral("status"), QStringLiteral("completed")}, {QStringLiteral("user_content"), content},
        {QStringLiteral("assistant_content"), answer}, {QStringLiteral("error"), QJsonValue::Null},
        {QStringLiteral("created_at"), QStringLiteral("2026-09-23T10:00:00Z")},
        {QStringLiteral("updated_at"), QStringLiteral("2026-09-23T10:00:00Z")}};
}
class ChatServer final : public QTcpServer {
public:
    QJsonArray chats;
    QHash<QString, QJsonArray> histories;
    QString answer;
    QString receivedContent;
    int posts = 0;
    int unexpectedImages = 0;
    bool creationWithoutTitle = true;
    ChatServer() {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (auto *socket = nextPendingConnection()) {
                auto buffer = std::make_shared<QByteArray>();
                auto done = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, buffer, done] {
                    *buffer += socket->readAll();
                    const auto split = buffer->indexOf("\r\n\r\n");
                    if (*done || split < 0) return;
                    const auto headers = buffer->left(split);
                    qsizetype length = 0;
                    for (const auto &line : headers.split('\n'))
                        if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toLongLong();
                    if (buffer->size() < split + 4 + length) return;
                    *done = true;
                    const auto first = headers.split('\n').first().split(' ');
                    const auto method = first.value(0), path = first.value(1).split('?').first();
                    const auto input = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    QJsonValue result = QJsonArray{};
                    if (path == "/probe") ++unexpectedImages;
                    if (path == "/conversations" && method == "POST") {
                        creationWithoutTitle = creationWithoutTitle && !input.contains(QStringLiteral("title"));
                        auto row = chat(QStringLiteral("chat-%1").arg(chats.size() + 1), input.value(QStringLiteral("project_id")));
                        chats.append(row); result = row;
                    } else if (path == "/conversations") result = QJsonObject{{QStringLiteral("items"), chats}};
                    else if (path.startsWith("/conversations/")) {
                        const auto pieces = path.split('/');
                        const auto id = QString::fromUtf8(pieces.value(2));
                        if (pieces.size() == 4 && pieces.value(3) == "turns" && method == "POST") {
                            ++posts; receivedContent = input.value(QStringLiteral("content")).toString();
                            auto turn = completedTurn(QStringLiteral("turn-%1").arg(posts), receivedContent, answer);
                            turn.insert(QStringLiteral("client_request_id"), input.value(QStringLiteral("client_request_id")));
                            histories[id].append(turn); result = turn;
                        } else {
                            for (const auto &value : chats) {
                                auto row = value.toObject();
                                if (row.value(QStringLiteral("id")).toString() != id) continue;
                                row.insert(QStringLiteral("turns"), histories.value(id));
                                result = row;
                            }
                        }
                    }
                    const auto body = result.isArray() ? QJsonDocument(result.toArray()).toJson(QJsonDocument::Compact)
                        : QJsonDocument(result.toObject()).toJson(QJsonDocument::Compact);
                    socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                        + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                    socket->disconnectFromHost();
                });
            }
        });
    }
};
QQuickItem *findVisual(QQuickItem *parent, const QString &name)
{
    if (!parent || !parent->isVisible()) return nullptr;
    if (parent->objectName() == name) return parent;
    for (auto *child : parent->childItems())
        if (auto *found = findVisual(child, name)) return found;
    return nullptr;
}
}

class TestConversationsUi : public QObject {
    Q_OBJECT
    QQuickWindow *m_window = nullptr;
    QString m_captures;
    QQuickItem *item(const char *name) const { return findVisual(m_window->contentItem(), QString::fromLatin1(name)); }
    bool reveal(QQuickItem *target) {
        if (!target || !target->isVisible()) return false;
        QTest::qWait(30); // Attend le placement des délégués créés par le dernier tour HTTP.
        for (auto *ancestor = target->parentItem(); ancestor; ancestor = ancestor->parentItem()) {
            if (!ancestor->property("contentY").isValid()) continue;
            for (int step = 0; step < 24; ++step) {
                const auto local = ancestor->mapFromItem(target, QPointF(target->width() / 2, target->height() / 2));
                if (local.y() >= 10 && local.y() <= ancestor->height() - 10) break;
                const auto pos = ancestor->mapToScene(QPointF(ancestor->width() / 2, ancestor->height() / 2));
                QWheelEvent event(pos, m_window->mapToGlobal(pos.toPoint()), QPoint(), QPoint(0, local.y() < 10 ? 360 : -360),
                    Qt::NoButton, Qt::NoModifier, Qt::NoScrollPhase, false);
                QCoreApplication::sendEvent(m_window, &event); QTest::qWait(30);
            }
            QElapsedTimer settling; settling.start();
            while (ancestor->property("moving").toBool() && settling.elapsed() < 2000) QTest::qWait(20);
            const auto local = ancestor->mapFromItem(target, QPointF(target->width() / 2, target->height() / 2));
            if (local.y() < 0 || local.y() > ancestor->height()) return false;
        }
        return true;
    }
    bool click(const char *name) {
        auto *target = item(name);
        if (!reveal(target)) return false;
        const auto pos = target->mapToScene(QPointF(target->width() / 2, target->height() / 2)).toPoint();
        if (!QRect(0, 0, m_window->width(), m_window->height()).contains(pos)) return false;
        QTest::mouseClick(m_window, Qt::LeftButton, Qt::NoModifier, pos);
        QTest::qWait(40);
        return true;
    }
    void writeAscii(const QByteArray &text) {
        for (const char character : text) QTest::keyClick(m_window, character);
    }
    bool capture(const QString &name) {
        m_window->requestUpdate(); QTest::qWait(120);
        const auto image = m_window->grabWindow();
        return !image.isNull() && image.save(QDir(m_captures).filePath(name + QStringLiteral(".png")));
    }
private slots:
    void composeCopyDraftSearchAndScrollThroughRealControls() {
        QTemporaryDir preferences, temporaryCaptures;
        QVERIFY(preferences.isValid() && temporaryCaptures.isValid());
        QCoreApplication::setOrganizationName(QStringLiteral("ACP conversations jetables"));
        QCoreApplication::setApplicationName(QStringLiteral("QtTest"));
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, preferences.path());
        m_captures = QString::fromUtf8(qgetenv("ACP_DESKTOP_QA_DIR"));
        if (m_captures.isEmpty()) m_captures = temporaryCaptures.path();
        QVERIFY(QDir().mkpath(m_captures));
        auto previousClipboard = std::make_unique<QMimeData>();
        if (const auto *data = QGuiApplication::clipboard()->mimeData())
            for (const auto &format : data->formats()) previousClipboard->setData(format, data->data(format));
        const auto restoreClipboard = qScopeGuard([&] { QGuiApplication::clipboard()->setMimeData(previousClipboard.release()); });
        ChatServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        const QString hostile = QStringLiteral("<img src='http://127.0.0.1:%1/probe'>").arg(server.serverPort());
        const QString code = QStringLiteral("print(\"un code inerte\")\nreturn 0");
        server.answer = hostile + QStringLiteral("\nUne réponse en texte.\n```python\n") + code + QStringLiteral("\n```\nFin de réponse.");
        Application controller; controller.registerQmlTypes();
        auto *api = controller.findChild<ApiClient*>();
        auto *auth = controller.findChild<AuthManager*>();
        auto *vm = controller.findChild<ConversationsViewModel*>();
        auto *appearance = controller.findChild<SystemAppearance*>();
        QVERIFY(api && auth && vm && appearance);
        api->setAllowInsecureLoopback(true);
        QVERIFY(!api->setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort()))).isError());
        auth->applySessionPayload({{QStringLiteral("csrf_token"), QStringLiteral("ui-test-csrf")},
            {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("ui-user")},
                {QStringLiteral("role"), QStringLiteral("owner")}, {QStringLiteral("display_name"), QStringLiteral("Session jetable")}}}});
        QQmlApplicationEngine engine;
        QStringList warnings;
        connect(&engine, &QQmlEngine::warnings, this, [&](const QList<QQmlError> &values) {
            for (const auto &value : values) warnings.append(value.toString());
        });
        QQmlComponent themeComponent(&engine); themeComponent.loadFromModule(QStringLiteral("Acp.Theme"), QStringLiteral("ThemeBridge"));
        std::unique_ptr<QObject> theme(themeComponent.create()); QVERIFY(theme);
        QQmlComponent windowComponent(&engine);
        windowComponent.setData(QByteArrayLiteral("import QtQuick\nimport QtQuick.Controls.Basic\nimport Acp.Theme\nimport Acp.Design\nApplicationWindow { color: Colors.surfaceCanvas; palette: NativePalette {} }"), QUrl());
        std::unique_ptr<QObject> windowObject(windowComponent.create());
        m_window = qobject_cast<QQuickWindow*>(windowObject.get());
        QVERIFY2(m_window, qPrintable(windowComponent.errorString()));
        QQmlComponent pageComponent(&engine); pageComponent.loadFromModule(QStringLiteral("Acp.Pages"), QStringLiteral("ConversationsPage"));
        std::unique_ptr<QObject> pageObject(pageComponent.create());
        auto *page = qobject_cast<QQuickItem*>(pageObject.get()); QVERIFY2(page, qPrintable(pageComponent.errorString()));
        auto *drawer = pageObject->findChild<QObject*>(QStringLiteral("conversationHistoryDrawer"));
        QVERIFY(drawer);
        page->setParentItem(m_window->contentItem());
        m_window->resize(1280, 800); page->setSize(m_window->size());
        m_window->show(); m_window->requestActivate();
        QVERIFY(QTest::qWaitForWindowExposed(m_window));
        appearance->setThemePreference(QStringLiteral("dark"));
        QTRY_VERIFY(!vm->loading());
        QVERIFY(click("conversationNewButton"));
        QTRY_VERIFY(!vm->busy() && !vm->loading());
        QCOMPARE(vm->currentId(), QStringLiteral("chat-1")); QVERIFY(server.creationWithoutTitle);
        auto *composerContainer = item("conversationComposerContainer");
        QVERIFY(composerContainer);
        QTRY_VERIFY(composerContainer->width() > 0 && composerContainer->width() <= 680);
        QVERIFY(item("conversationComposer")->width() <= composerContainer->width());
        QVERIFY(click("conversationComposer"));
        QTRY_VERIFY(item("conversationComposer")->hasActiveFocus());
        writeAscii("Bonjour");
        QTest::keyClick(m_window, Qt::Key_Return, Qt::ShiftModifier);
        writeAscii("code");
        QCOMPARE(vm->draft(), QStringLiteral("Bonjour\ncode")); QCOMPARE(server.posts, 0);
        QTest::keyClick(m_window, Qt::Key_Return);
        QTRY_COMPARE(server.posts, 1);
        QTRY_VERIFY(!vm->busy() && !vm->pendingSubmission());
        QCOMPARE(server.receivedContent, QStringLiteral("Bonjour\ncode"));
        QTRY_VERIFY(item("conversationCodeText"));
        QCOMPARE(item("conversationCodeText")->property("text").toString(), code);
        QCOMPARE(item("conversationCodeText")->property("textFormat").toInt(), 0);
        QVERIFY(item("conversationCodeText")->width() <= 680);
        QVERIFY(click("conversationCopyCodeButton"));
        QCOMPARE(QGuiApplication::clipboard()->text(), code);
        QCOMPARE(server.unexpectedImages, 0);
        QVERIFY(capture(QStringLiteral("09-chat-code-dark-wide")));
        QVERIFY(click("conversationComposer")); writeAscii("Brouillon du premier chat");
        QVERIFY(click("conversationNewButton")); QTRY_VERIFY(!vm->busy() && !vm->loading());
        QCOMPARE(vm->currentId(), QStringLiteral("chat-2")); QVERIFY(vm->draft().isEmpty());
        QVERIFY(click("conversationComposer")); writeAscii("Brouillon du second chat");
        QVERIFY(click("conversationHistoryButton"));
        QTRY_VERIFY(drawer->property("opened").toBool());
        QTRY_VERIFY(item("conversationSearchField")->findChild<QQuickItem*>(QStringLiteral("acpTextFieldInput"))->hasActiveFocus());
        QTRY_VERIFY(item("conversation-thread-chat-1"));
        QVERIFY(click("conversation-thread-chat-1"));
        QTRY_VERIFY(!drawer->property("visible").toBool());
        QTRY_VERIFY(!vm->loading());
        QTRY_VERIFY(item("conversationComposer")->hasActiveFocus());
        QCOMPARE(vm->draft(), QStringLiteral("Brouillon du premier chat"));
        QCOMPARE(item("conversationComposer")->property("text").toString(), vm->draft());
        QVERIFY(click("conversationHistoryButton"));
        QTRY_VERIFY(drawer->property("opened").toBool());
        QTRY_VERIFY(item("conversationSearchField"));
        auto *search = item("conversationSearchField")->findChild<QQuickItem*>(QStringLiteral("acpTextFieldInput"));
        QVERIFY(search);
        const auto searchPos = search->mapToScene(QPointF(search->width() / 2, search->height() / 2)).toPoint();
        QTest::mouseClick(m_window, Qt::LeftButton, Qt::NoModifier, searchPos); writeAscii("Chat 2");
        QTRY_COMPARE(qobject_cast<JsonListModel*>(vm->conversations())->count(), 1);
        QCOMPARE(vm->currentId(), QStringLiteral("chat-1"));
        QTest::keyClick(m_window, Qt::Key_A, Qt::ControlModifier); QTest::keyClick(m_window, Qt::Key_Backspace);
        QTest::keyClick(m_window, Qt::Key_Escape);
        QTRY_VERIFY(!drawer->property("visible").toBool());
        appearance->setThemePreference(QStringLiteral("light"));
        m_window->resize(960, 700); page->setSize(m_window->size());
        QTRY_VERIFY(composerContainer->width() > 0 && composerContainer->width() <= 680);
        QVERIFY(item("conversationComposer")->width() <= composerContainer->width());
        QVERIFY(capture(QStringLiteral("10-chat-code-light-narrow")));
        QJsonArray longHistory;
        for (int n = 0; n < 24; ++n)
            longHistory.append(completedTurn(QStringLiteral("long-%1").arg(n), QStringLiteral("Question %1").arg(n),
                QStringLiteral("Une réponse longue pour vérifier la lecture sans déplacement forcé. ").repeated(12)));
        server.histories[QStringLiteral("chat-1")] = longHistory;
        vm->refresh(); QTRY_VERIFY(!vm->loading());
        auto *history = item("conversationHistory"); QVERIFY(history);
        QTRY_VERIFY(history->property("contentHeight").toReal() > history->height() * 3);
        const auto wheelPos = history->mapToScene(QPointF(history->width() / 2, history->height() / 2));
        QWheelEvent wheel(wheelPos, m_window->mapToGlobal(wheelPos.toPoint()), QPoint(), QPoint(0, 1440),
            Qt::NoButton, Qt::NoModifier, Qt::NoScrollPhase, false);
        QCoreApplication::sendEvent(m_window, &wheel);
        QTRY_VERIFY(!history->property("moving").toBool());
        QTest::qWait(100);
        const auto before = history->property("contentY").toReal();
        QVERIFY(!history->property("atYEnd").toBool());
        longHistory.append(completedTurn(QStringLiteral("new-tail"), QStringLiteral("Nouvelle question"), QStringLiteral("Nouvelle réponse arrivée.")));
        server.histories[QStringLiteral("chat-1")] = longHistory;
        vm->refresh(); QTRY_VERIFY(!vm->loading());
        QTRY_COMPARE(qobject_cast<JsonListModel*>(vm->turns())->count(), 25);
        QTest::qWait(150);
        QVERIFY(qAbs(history->property("contentY").toReal() - before) < 64);
        QVERIFY(!history->property("atYEnd").toBool());
        QVERIFY(capture(QStringLiteral("11-chat-history-position-preserved")));
        // Le changement de contexte réinitialise currentId pendant que le Drawer
        // est modal : aucune réponse du VM ne doit rendre Échap inopérant.
        QVERIFY(click("conversationHistoryButton"));
        QTRY_VERIFY(drawer->property("opened").toBool());
        vm->setProjectId(QStringLiteral("project-a"));
        QTRY_VERIFY(!vm->loading());
        QVERIFY(vm->currentId().isEmpty());
        QTRY_VERIFY(search->hasActiveFocus());
        QTest::keyClick(m_window, Qt::Key_Escape);
        QTRY_VERIFY(!drawer->property("visible").toBool());
        QVERIFY(click("conversationHistoryButton"));
        QTRY_VERIFY(drawer->property("opened").toBool());
        QVERIFY(click("generalConversationsButton"));
        QTRY_VERIFY(vm->projectId().isEmpty() && !vm->loading());
        QTest::keyClick(m_window, Qt::Key_Escape);
        QTRY_VERIFY(!drawer->property("visible").toBool());
        QCOMPARE(server.unexpectedImages, 0);
        QVERIFY2(warnings.isEmpty(), qPrintable(warnings.join(QLatin1Char('\n'))));
        qInfo().noquote() << "Captures conversations :" << m_captures;
        pageObject.reset(); m_window->hide(); m_window = nullptr;
    }
};

int main(int argc, char **argv) {
#ifdef Q_OS_WIN
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
#endif
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    QGuiApplication app(argc, argv);
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    TestConversationsUi test;
    return QTest::qExec(&test, argc, argv);
}
#include "tst_conversations_ui.moc"
