// Parcours des vraies pages QML : souris, clavier, défilement et captures de fenêtre.
// Le transport local est synthétique ; aucune identité, préférence ou API utilisateur.
#include "app/Application.h"
#include "api/ApiClient.h"
#include "auth/AuthManager.h"
#include "models/JsonListModel.h"
#include "commands/CommandRegistry.h"
#include "navigation/NavigationModel.h"
#include "system/SystemAppearance.h"
#include "viewmodels/WorkspaceViewModel.h"
#include "viewmodels/MissionsViewModel.h"
#include "viewmodels/ConversationsViewModel.h"
#include "viewmodels/ShellViewModel.h"
#include "storage/SettingsStore.h"
#include <QDir>
#include <QElapsedTimer>
#include <QGuiApplication>
#include <QHostAddress>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSettings>
#include <QSignalSpy>
#include <QScopeGuard>
#include <QSGRendererInterface>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>
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
class UiServer final : public QTcpServer {
public:
    QJsonArray organizations, workspaces, projects;
    QJsonObject createdMission;
    QJsonArray conversationRows;
    QJsonObject lastConversationRequest;
    int conversationsCreated = 0;
    int unexpectedImages = 0;
    UiServer() {
        const auto summary = [](const QString& id, const QJsonValue& project) {
            return QJsonObject{{QStringLiteral("id"), id}, {QStringLiteral("project_id"), project},
                {QStringLiteral("title"), id}, {QStringLiteral("status"), QStringLiteral("active")},
                {QStringLiteral("created_at"), QStringLiteral("2026-09-23T10:00:00Z")},
                {QStringLiteral("updated_at"), QStringLiteral("2026-09-23T10:00:00Z")}};
        };
        conversationRows = {summary(QStringLiteral("general"), QJsonValue::Null),
            summary(QStringLiteral("project-conversation"), QStringLiteral("project"))};
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (auto* socket = nextPendingConnection()) {
                auto buffer = std::make_shared<QByteArray>();
                auto done = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, buffer, done] {
                    *buffer += socket->readAll();
                    const auto split = buffer->indexOf("\r\n\r\n");
                    if (*done || split < 0) return;
                    const auto headers = buffer->left(split);
                    int length = 0;
                    for (const auto& line : headers.split('\n'))
                        if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                    if (buffer->size() < split + 4 + length) return;
                    *done = true;
                    const auto first = headers.split('\n').first().split(' ');
                    const auto method = first.value(0), path = first.value(1).split('?').first();
                    const auto input = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    QJsonValue result = QJsonArray{};
                    if (path == "/probe") ++unexpectedImages;
                    if (path == "/organizations" || path == "/workspaces" || path == "/projects") {
                        auto* rows = path == "/organizations" ? &organizations : path == "/workspaces" ? &workspaces : &projects;
                        if (method == "POST") {
                            auto row = input;
                            row.insert(QStringLiteral("id"), path == "/organizations" ? QStringLiteral("organization")
                                : path == "/workspaces" ? QStringLiteral("workspace") : QStringLiteral("project"));
                            row.insert(QStringLiteral("status"), QStringLiteral("active"));
                            rows->append(row); result = row;
                        } else result = *rows;
                    } else if (path == "/missions" && method == "POST") {
                        createdMission = input;
                        createdMission.insert(QStringLiteral("id"), QStringLiteral("mission"));
                        createdMission.insert(QStringLiteral("status"), QStringLiteral("queued"));
                        const QJsonObject run{{QStringLiteral("id"), QStringLiteral("run")}, {QStringLiteral("status"), QStringLiteral("queued")},
                            {QStringLiteral("attempt_number"), 1}, {QStringLiteral("evidence"), QJsonArray{}},
                            {QStringLiteral("technical_validation"), QJsonObject{{QStringLiteral("status"), QStringLiteral("pending")}}},
                            {QStringLiteral("user_acceptance"), QJsonObject{{QStringLiteral("status"), QStringLiteral("pending")}}}};
                        createdMission.insert(QStringLiteral("current_run"), run);
                        createdMission.insert(QStringLiteral("runs"), QJsonArray{run}); result = createdMission;
                    } else if (path == "/missions") result = createdMission.isEmpty() ? QJsonArray{} : QJsonArray{createdMission};
                    else if (path == "/missions/mission") result = createdMission;
                    else if (path == "/conversations") {
                        if (method == "POST") {
                            lastConversationRequest = input;
                            auto row = conversationRows.first().toObject();
                            row.insert(QStringLiteral("id"), QStringLiteral("created-%1").arg(++conversationsCreated));
                            row.insert(QStringLiteral("title"), QStringLiteral("Nouvelle conversation"));
                            row.insert(QStringLiteral("project_id"), input.value(QStringLiteral("project_id")));
                            conversationRows.append(row); result = row;
                        } else result = QJsonObject{{QStringLiteral("items"), conversationRows}};
                    } else if (path.startsWith("/conversations/")) {
                        for (const auto& value : conversationRows) {
                            auto row = value.toObject();
                            if (row.value(QStringLiteral("id")).toString().toUtf8() != path.mid(15)) continue;
                            row.insert(QStringLiteral("turns"), QJsonArray{}); result = row; break;
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
}

class TestDesktopInteractions : public QObject {
    Q_OBJECT
    std::unique_ptr<QObject> m_page;
    QQuickWindow* m_window = nullptr;
    QString m_captureDirectory;
    QObject* m_colors = nullptr;
    static QQuickItem* visualItem(QQuickItem* parent, const QString& name) {
        if (!parent) return nullptr;
        if (parent->objectName() == name) return parent;
        for (auto* child : parent->childItems())
            if (auto* result = visualItem(child, name)) return result;
        return nullptr;
    }
    QQuickItem* item(const char* name) const {
        auto* result = m_page ? m_page->findChild<QQuickItem*>(QString::fromLatin1(name)) : nullptr;
        return result ? result : visualItem(m_window ? m_window->contentItem() : nullptr, QString::fromLatin1(name));
    }
    bool reveal(QQuickItem* target) {
        if (!target || !target->isVisible()) return false;
        for (auto* ancestor = target->parentItem(); ancestor; ancestor = ancestor->parentItem()) {
            if (!ancestor->property("contentY").isValid()) continue;
            for (int n = 0; n < 24; ++n) {
                const auto local = ancestor->mapFromItem(target, QPointF(target->width() / 2, target->height() / 2));
                if (local.y() >= 10 && local.y() <= ancestor->height() - 10) break;
                const auto pos = ancestor->mapToScene(QPointF(ancestor->width() / 2, ancestor->height() / 2));
                QWheelEvent event(pos, m_window->mapToGlobal(pos.toPoint()), QPoint(), QPoint(0, local.y() < 10 ? 360 : -360),
                    Qt::NoButton, Qt::NoModifier, Qt::NoScrollPhase, false);
                QCoreApplication::sendEvent(m_window, &event); QTest::qWait(30);
            }
            QElapsedTimer settling; settling.start();
            while (ancestor->property("moving").toBool() && settling.elapsed() < 2000) QTest::qWait(20);
        }
        const auto pos = target->mapToScene(QPointF(target->width() / 2, target->height() / 2));
        return QRectF(0, 0, m_window->width(), m_window->height()).contains(pos);
    }
    bool click(const char* name) {
        auto* target = item(name);
        if (!reveal(target)) return false;
        const auto pos = target->mapToScene(QPointF(target->width() / 2, target->height() / 2)).toPoint();
        QTest::mouseClick(m_window, Qt::LeftButton, Qt::NoModifier, pos); QTest::qWait(35);
        return true;
    }
    bool historyDrawerReady(bool opened) {
        auto* drawer = m_page ? m_page->findChild<QObject*>(QStringLiteral("conversationHistoryDrawer")) : nullptr;
        if (!drawer) return false;
        QElapsedTimer timer; timer.start();
        while (timer.elapsed() < 2000) {
            if (opened ? drawer->property("opened").toBool() : !drawer->property("visible").toBool()) return true;
            QTest::qWait(20);
        }
        return false;
    }
    bool type(const char* name, const QString& value) {
        auto* target = item(name);
        if (!reveal(target)) return false;
        auto* input = target->findChild<QQuickItem*>(QStringLiteral("acpTextFieldInput"));
        if (!input) input = target;
        const auto pos = input->mapToScene(QPointF(input->width() / 2, qMin(input->height() / 2, 15.0))).toPoint();
        QTest::mouseClick(m_window, Qt::LeftButton, Qt::NoModifier, pos);
        QTest::keyClick(m_window, Qt::Key_A, Qt::ControlModifier);
        for (const auto character : value) {
            if (character == QLatin1Char('\n')) QTest::keyClick(m_window, Qt::Key_Return);
            else QTest::keyClick(m_window, character.toLatin1());
        }
        return target->property("text").toString() == value && input->hasActiveFocus();
    }
    bool capture(const QString& name) {
        m_window->setColor(m_colors->property("surfaceCanvas").value<QColor>());
        m_window->requestUpdate(); QTest::qWait(100);
        const QImage shot = m_window->grabWindow();
        if (shot.isNull()) return false;
        return shot.save(QDir(m_captureDirectory).filePath(name + QStringLiteral(".png")));
    }
    bool load(QQmlEngine& engine, const QString& page) {
        m_page.reset();
        QQmlComponent component(&engine);
        component.loadFromModule(QStringLiteral("Acp.Pages"), page);
        if (!component.isReady()) { qWarning().noquote() << component.errorString(); return false; }
        m_page.reset(component.create());
        auto* root = qobject_cast<QQuickItem*>(m_page.get());
        if (!root) return false;
        root->setParentItem(m_window->contentItem()); root->setSize(m_window->size());
        QTest::qWait(60); return true;
    }
private slots:
    void projectsMissionsAndGeneralContextThroughRealControls() {
        QTemporaryDir preferences, temporaryCaptures;
        QVERIFY(preferences.isValid() && temporaryCaptures.isValid());
        QCoreApplication::setOrganizationName(QStringLiteral("ACP interactions jetables"));
        QCoreApplication::setApplicationName(QStringLiteral("QtTest"));
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, preferences.path());
        m_captureDirectory = QString::fromUtf8(qgetenv("ACP_DESKTOP_QA_DIR"));
        if (m_captureDirectory.isEmpty()) m_captureDirectory = temporaryCaptures.path();
        QVERIFY(QDir().mkpath(m_captureDirectory));
        UiServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        Application controller; controller.registerQmlTypes();
        auto* api = controller.findChild<ApiClient*>();
        auto* auth = controller.findChild<AuthManager*>();
        auto* workspace = controller.findChild<WorkspaceViewModel*>();
        auto* missions = controller.findChild<MissionsViewModel*>();
        auto* conversations = controller.findChild<ConversationsViewModel*>();
        auto* appearance = controller.findChild<SystemAppearance*>();
        api->setAllowInsecureLoopback(true);
        QVERIFY(!api->setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort()))).isError());
        auth->applySessionPayload({{QStringLiteral("csrf_token"), QStringLiteral("ui-test-csrf")},
            {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("ui-user")},
                {QStringLiteral("role"), QStringLiteral("owner")}, {QStringLiteral("display_name"), QStringLiteral("Utilisateur jetable")}}}});
        QTRY_VERIFY(!workspace->busy());
        QCOMPARE(workspace->projects()->count(), 0);
        QQmlApplicationEngine engine;
        QStringList warnings;
        connect(&engine, &QQmlEngine::warnings, this, [&warnings](const QList<QQmlError>& values) {
            for (const auto& value : values) warnings.append(value.toString());
        });
        QQmlComponent themeComponent(&engine); themeComponent.loadFromModule(QStringLiteral("Acp.Theme"), QStringLiteral("ThemeBridge"));
        std::unique_ptr<QObject> theme(themeComponent.create()); QVERIFY(theme);
        m_colors = engine.singletonInstance<QObject*>(QStringLiteral("Acp.Design"), QStringLiteral("Colors"));
        QVERIFY(m_colors);
        QQmlComponent windowComponent(&engine);
        windowComponent.setData(QByteArrayLiteral("import QtQuick\nimport QtQuick.Controls.Basic\nimport Acp.Theme\nimport Acp.Design\nApplicationWindow { color: Colors.surfaceCanvas; palette: NativePalette {} }"), QUrl());
        std::unique_ptr<QObject> windowObject(windowComponent.create());
        auto* pageWindow = qobject_cast<QQuickWindow*>(windowObject.get());
        QVERIFY2(pageWindow, qPrintable(windowComponent.errorString()));
        auto& window = *pageWindow; m_window = &window;
        const auto cleanup = qScopeGuard([this] { m_page.reset(); m_window = nullptr; });
        window.resize(1280, 760); window.show(); QVERIFY(QTest::qWaitForWindowExposed(&window));
        appearance->setThemePreference(QStringLiteral("dark"));
        QVERIFY(load(engine, QStringLiteral("ProjectsPage")));
        QVERIFY(capture(QStringLiteral("01-projects-empty-dark-wide")));
        QVERIFY(click("organizationNewButton"));
        QTRY_VERIFY(item("organizationCreateOk"));
        QVERIFY(type("organizationNameField", QStringLiteral("Organisation UI")));
        QVERIFY(capture(QStringLiteral("02-organization-modal-focused")));
        QVERIFY(click("organizationCreateOk"));
        QTRY_COMPARE(workspace->organizations()->count(), 1); QTRY_VERIFY(!workspace->busy());
        QVERIFY(click("workspaceNewButton")); QTRY_VERIFY(item("workspaceCreateOk"));
        QVERIFY(type("workspaceNameField", QStringLiteral("Espace UI")));
        QVERIFY(click("workspaceCreateOk"));
        QTRY_VERIFY2(workspace->error().isEmpty(), qPrintable(workspace->error()));
        QTRY_COMPARE(workspace->workspaces()->count(), 1); QTRY_VERIFY(!workspace->busy());
        QVERIFY(click("projectNewButton")); QTRY_VERIFY(item("projectCreateOk"));
        QVERIFY(type("projectNameField", QStringLiteral("Projet UI")));
        QVERIFY(type("projectDescriptionField", QStringLiteral("Parcours clavier et souris")));
        QVERIFY(click("projectCreateOk"));
        QTRY_COMPARE(workspace->projectId(), QStringLiteral("project"));
        QTRY_VERIFY(!missions->busy());
        QVERIFY(load(engine, QStringLiteral("MissionsPage")));
        QVERIFY(click("missionNewButton"));
        const QString title = QStringLiteral("<img src='http://127.0.0.1:%1/probe'>").arg(server.serverPort());
        QVERIFY(type("missionTitleField", title));
        QVERIFY(type("missionObjectiveField", QStringLiteral("Lire le projet")));
        QVERIFY(type("missionOutcomeField", QStringLiteral("Rapport visible")));
        QVERIFY(type("missionCriteriaField", QStringLiteral("Compte rendu fourni")));
        QVERIFY(click("missionExecutorField"));
        QTest::keyClick(&window, Qt::Key_End); QTest::keyClick(&window, Qt::Key_Return);
        QTRY_COMPARE(item("missionExecutorField")->property("currentIndex").toInt(), 3);
        QCOMPARE(item("missionAutonomyField")->property("currentIndex").toInt(), 0);
        QCOMPARE(item("missionCostLimitedField")->property("checked").toBool(), true);
        QCOMPARE(item("missionCostField")->property("text").toString(), QStringLiteral("5"));
        QVERIFY(click("missionCostLimitedField"));
        QVERIFY(!item("missionCostLimitedField")->property("checked").toBool());
        QCOMPARE(item("missionCostField")->property("text").toString(), QStringLiteral("5"));
        appearance->setThemePreference(QStringLiteral("light"));
        window.resize(820, 760); qobject_cast<QQuickItem*>(m_page.get())->setSize(window.size());
        QVERIFY(reveal(item("missionCreateButton")));
        QVERIFY(capture(QStringLiteral("03-team-form-light-narrow-scrolled")));
        QSignalSpy createdClick(item("missionCreateButton"), SIGNAL(triggered()));
        QVERIFY(click("missionCreateButton"));
        QCOMPARE(createdClick.count(), 1);
        QTRY_VERIFY2(!server.createdMission.isEmpty(), qPrintable(missions->error()));
        QCOMPARE(server.createdMission.value(QStringLiteral("execution")).toObject().value(QStringLiteral("mode")).toString(), QStringLiteral("multi_agent"));
        QVERIFY(server.createdMission.value(QStringLiteral("required_capabilities")).toArray().contains(QStringLiteral("agent_team")));
        QCOMPARE(server.createdMission.value(QStringLiteral("resources")).toArray().size(), 1);
        QVERIFY(server.createdMission.value(QStringLiteral("budget")).toObject().value(QStringLiteral("max_cost")).isNull());
        QTRY_VERIFY(!missions->busy() && !missions->mutating());
        window.resize(1280, 760); qobject_cast<QQuickItem*>(m_page.get())->setSize(window.size());
        appearance->setThemePreference(QStringLiteral("dark"));
        QVERIFY(capture(QStringLiteral("04-mission-created-dark-wide-plain-title")));
        QCOMPARE(server.unexpectedImages, 0);
        QVERIFY(load(engine, QStringLiteral("ConversationsPage")));
        QTRY_VERIFY(!conversations->loading());
        QCOMPARE(conversations->projectId(), QStringLiteral("project"));
        // La vraie racine, sa navigation et ses raccourcis sont testés ensuite.
        m_page.reset(); window.hide();
        QQmlComponent appComponent(&engine);
        appComponent.loadFromModule(QStringLiteral("Acp.Desktop"), QStringLiteral("App"));
        m_page.reset(appComponent.create());
        m_window = qobject_cast<QQuickWindow*>(m_page.get());
        QVERIFY2(m_window, qPrintable(appComponent.errorString()));
        m_window->resize(1280, 800);
        m_window->show(); m_window->requestActivate();
        QVERIFY(QTest::qWaitForWindowExposed(m_window));
        auto* navigation = controller.findChild<NavigationModel*>();
        auto* shell = controller.findChild<ShellViewModel*>();
        auto* commands = controller.findChild<CommandRegistry*>();
        auto* preferencesStore = controller.findChild<SettingsStore*>();
        shell->setSidebarWidth(900);
        QCOMPARE(preferencesStore->sidebarWidth(), 360);
        shell->setSidebarWidth(310);
        QTRY_COMPARE(qRound(item("shell-sidebar")->width()), 310);
        shell->setInspectorWidth(1);
        QCOMPARE(preferencesStore->inspectorWidth(), 320);
        shell->setInspectorWidth(450);
        QVERIFY(capture(QStringLiteral("06-shell-initial")));
        QTRY_VERIFY(item("navigation-missions"));
        QVERIFY(click("navigation-missions"));
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("missions"));
        QTest::keyClick(m_window, Qt::Key_Left, Qt::AltModifier);
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("home"));
        QTest::keyClick(m_window, Qt::Key_Right, Qt::AltModifier);
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("missions"));
        QTRY_VERIFY(!missions->busy());
        QVERIFY(click("shell-inspect"));
        QTRY_VERIFY(shell->isInspectorVisible());
        QTRY_VERIFY(item("shell-inspector")->isVisible());
        QCOMPARE(item("shell-inspector")->property("heading").toString(), QStringLiteral("Mission et tentative"));
        QTRY_COMPARE(qRound(item("shell-inspector")->width()), 450);
        QTest::keyClick(m_window, Qt::Key_Escape);
        QTRY_VERIFY(!shell->isInspectorVisible());
        appearance->setThemePreference(QStringLiteral("dark"));
        QVERIFY(capture(QStringLiteral("06-shell-missions-dark-wide")));
        QTest::keyClick(m_window, Qt::Key_K, Qt::ControlModifier);
        QTRY_VERIFY(shell->isCommandPaletteOpen());
        QTRY_VERIFY(item("commandPaletteSearch"));
        auto* searchInput = item("commandPaletteSearch")->findChild<QQuickItem*>(QStringLiteral("acpTextFieldInput"));
        QVERIFY(searchInput);
        QTRY_VERIFY(searchInput->hasActiveFocus());
        for (const char character : QByteArrayLiteral("Projets")) QTest::keyClick(m_window, character);
        QTRY_COMPARE(commands->filter(), QStringLiteral("Projets"));
        QCOMPARE(item("commandPaletteSearch")->property("text").toString(), QStringLiteral("Projets"));
        QTest::keyClick(m_window, Qt::Key_Tab);
        QTRY_VERIFY(item("commandPaletteResults")->hasActiveFocus());
        int projectsCommandIndex = -1;
        for (int row = 0; row < commands->rowCount(); ++row)
            if (commands->data(commands->index(row), CommandRegistry::IdRole).toString() == QStringLiteral("navigation.projects"))
                projectsCommandIndex = row;
        QVERIFY(projectsCommandIndex >= 0);
        QTest::keyClick(m_window, Qt::Key_Home);
        for (int row = 0; row < projectsCommandIndex; ++row) QTest::keyClick(m_window, Qt::Key_Down);
        QTRY_COMPARE(item("commandPaletteResults")->property("currentIndex").toInt(), projectsCommandIndex);
        QTest::keyClick(m_window, Qt::Key_Tab, Qt::ShiftModifier);
        QTRY_VERIFY(searchInput->hasActiveFocus());
        QVERIFY(capture(QStringLiteral("07-shell-palette-dark-focused")));
        QTest::keyClick(m_window, Qt::Key_Return);
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("projects"));
        QTRY_VERIFY(!shell->isCommandPaletteOpen());
        m_window->resize(960, 700);
        QTRY_COMPARE(qRound(item("shell-sidebar")->width()), 48);
        QCOMPARE(preferencesStore->sidebarWidth(), 310); // Le repli adaptatif n'écrase pas la préférence.
        appearance->setThemePreference(QStringLiteral("light"));
        QVERIFY(capture(QStringLiteral("08-shell-projects-light-narrow")));
        QTest::keyClick(m_window, Qt::Key_K, Qt::ControlModifier);
        QTRY_VERIFY(shell->isCommandPaletteOpen());
        QTRY_VERIFY(searchInput->hasActiveFocus());
        QCOMPARE(item("commandPaletteSearch")->property("text").toString(), QString());
        QTest::keyClick(m_window, Qt::Key_Escape);
        QTRY_VERIFY(!shell->isCommandPaletteOpen());
        QVERIFY(click("navigation-conversations"));
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("conversations"));
        QVERIFY(click("conversationHistoryButton"));
        QVERIFY(historyDrawerReady(true));
        QVERIFY(click("generalConversationsButton"));
        QCOMPARE(navigation->currentRoute(), QStringLiteral("conversations"));
        QTRY_VERIFY(!conversations->loading());
        QCOMPARE(conversations->projectId(), QString());
        QCOMPARE(qobject_cast<JsonListModel*>(conversations->conversations())->get(0).value(QStringLiteral("id")).toString(), QStringLiteral("general"));
        QTest::keyClick(m_window, Qt::Key_Escape);
        QVERIFY(historyDrawerReady(false));
        QCOMPARE(item("shell-context-label")->property("text").toString(), QStringLiteral("Conversation générale"));
        appearance->setThemePreference(QStringLiteral("light"));
        m_window->resize(1280, 800);
        QTRY_COMPARE(qRound(item("shell-sidebar")->width()), 310);
        QVERIFY(capture(QStringLiteral("05-general-conversations-light-wide")));
        QVERIFY(click("conversationHistoryButton"));
        QVERIFY(historyDrawerReady(true));
        QVERIFY(click("projectConversationsButton"));
        QCOMPARE(navigation->currentRoute(), QStringLiteral("conversations"));
        QTRY_VERIFY(!conversations->loading());
        QCOMPARE(conversations->projectId(), QStringLiteral("project"));
        QTest::keyClick(m_window, Qt::Key_Escape);
        QVERIFY(historyDrawerReady(false));
        QVERIFY(click("navigation-home"));
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("home"));
        appearance->setThemePreference(QStringLiteral("dark"));
        QVERIFY(capture(QStringLiteral("09-home-dark-wide")));
        QVERIFY(click("homeNewConversationButton"));
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("conversations"));
        QTRY_COMPARE(server.conversationsCreated, 1);
        QTRY_VERIFY(!conversations->busy() && !conversations->loading());
        QCOMPARE(conversations->projectId(), QString());
        QCOMPARE(conversations->currentId(), QStringLiteral("created-1"));
        QVERIFY(server.lastConversationRequest.value(QStringLiteral("project_id")).isNull());
        QVERIFY(!server.lastConversationRequest.contains(QStringLiteral("title")));
        QVERIFY2(conversations->error().isEmpty(), qPrintable(conversations->error()));
        QVERIFY(capture(QStringLiteral("10-new-general-chat-dark")));
        // Actualiser les métadonnées du projet sélectionné ne sort pas du chat général.
        auto renamedProject = server.projects.first().toObject();
        renamedProject.insert(QStringLiteral("name"), QStringLiteral("Projet UI actualisé"));
        server.projects.replace(0, renamedProject);
        workspace->refresh();
        QTRY_COMPARE(workspace->projectName(), QStringLiteral("Projet UI actualisé"));
        QCOMPARE(conversations->projectId(), QString());
        QVERIFY(click("navigation-home"));
        appearance->setThemePreference(QStringLiteral("light"));
        QVERIFY(capture(QStringLiteral("11-home-light-wide")));
        QVERIFY(click("homeNewProjectButton"));
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("projects"));
        QTRY_VERIFY(item("projectCreateOk") && item("projectCreateOk")->isVisible());
        QVERIFY(!workspace->projectCreationPending());
        // Même un vrai clic dirigé vers la navigation visible sous une modale
        // doit être absorbé, sans exécuter la commande sous-jacente.
        auto *projectDialog = m_page->findChild<QObject*>(QStringLiteral("projectCreateDialog"));
        QVERIFY(projectDialog);
        QTRY_VERIFY(projectDialog->property("opened").toBool());
        QVERIFY(click("navigation-home"));
        QCOMPARE(navigation->currentRoute(), QStringLiteral("projects"));
        QTest::keyClick(m_window, Qt::Key_Escape);
        QTRY_VERIFY(!item("projectCreateOk")->isVisible());
        QVERIFY(click("projectOpenConversationsButton"));
        QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("conversations"));
        QTRY_VERIFY(!conversations->loading());
        QCOMPARE(conversations->projectId(), QStringLiteral("project"));
        QCOMPARE(server.conversationsCreated, 1); // Reprendre le projet ne crée pas un fil.
        QVERIFY2(warnings.isEmpty(), qPrintable(warnings.join(QLatin1Char('\n'))));
        qInfo().noquote() << "Captures UI :" << m_captureDirectory;
        m_page.reset(); window.hide(); m_window = nullptr;
    }
};

int main(int argc, char** argv) {
#ifdef Q_OS_WIN
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
#endif
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    QGuiApplication application(argc, argv);
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    TestDesktopInteractions test;
    return QTest::qExec(&test, argc, argv);
}
#include "tst_desktop_interactions.moc"
