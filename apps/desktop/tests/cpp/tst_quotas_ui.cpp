// Recette du vrai QML de l'écran « Quotas », avec serveur HTTP jetable et données de test
// identifiées (fixture de référence) : aucune donnée d'un compte réel.
#include "app/Application.h"
#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"
#include "commands/CommandRegistry.h"
#include "models/JsonListModel.h"
#include "navigation/NavigationModel.h"
#include "system/SystemAppearance.h"
#include "viewmodels/SubscriptionQuotasViewModel.h"

#include <QAccessible>
#include <QDir>
#include <QFile>
#include <QGuiApplication>
#include <QHostAddress>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkCookie>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QSettings>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>
#include <QTimeZone>

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
QByteArray fixture()
{
    QFile file(QStringLiteral(ACP_TEST_FIXTURE_DIR "/subscription-quotas.json"));
    if (!file.open(QIODevice::ReadOnly)) { qFatal("Fixture des quotas illisible"); }
    return file.readAll();
}
class QuotaUiServer final : public QTcpServer {
public:
    int reads = 0;
    int status = 200;
    QByteArray body = fixture();
    const QByteArray session = QJsonDocument(QJsonObject{{QStringLiteral("authenticated"), true},
        {QStringLiteral("csrf_token"), QStringLiteral("ui-test-csrf-2")},
        {QStringLiteral("expires_at"), QStringLiteral("2099-01-01T00:00:00+00:00")},
        {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("ui-owner")},
            {QStringLiteral("role"), QStringLiteral("owner")}, {QStringLiteral("display_name"), QStringLiteral("Propriétaire jetable")}}}})
        .toJson(QJsonDocument::Compact);
    QuotaUiServer() {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (auto *socket = nextPendingConnection()) {
                auto buffer = std::make_shared<QByteArray>();
                auto done = std::make_shared<bool>(false);
                connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, buffer, done] {
                    *buffer += socket->readAll();
                    if (*done || buffer->indexOf("\r\n\r\n") < 0) return;
                    *done = true;
                    const auto path = buffer->split('\n').first().split(' ').value(1);
                    QByteArray payload = "[]";
                    int code = 200;
                    if (path == "/subscription-quotas") { ++reads; payload = body; code = status; }
                    // Un 403 fait relire la session une fois : même propriétaire, même rôle.
                    if (path == "/auth/session") payload = session;
                    socket->write("HTTP/1.1 " + QByteArray::number(code) + " Result\r\nContent-Type: application/json\r\n"
                        "Connection: close\r\nContent-Length: " + QByteArray::number(payload.size()) + "\r\n\r\n" + payload);
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
QString accessibleName(QObject *object)
{
    QAccessibleInterface *interface = object ? QAccessible::queryAccessibleInterface(object) : nullptr;
    return interface ? interface->text(QAccessible::Name) : QString();
}
}

class TestQuotasUi : public QObject {
    Q_OBJECT
    QQuickWindow *m_window = nullptr;
    QString m_captures;
    QQuickItem *item(const QString &name) const { return findVisual(m_window->contentItem(), name); }
    bool click(const QString &name) {
        auto *target = item(name);
        if (!target) return false;
        const auto pos = target->mapToScene(QPointF(target->width() / 2, target->height() / 2)).toPoint();
        if (!QRect(0, 0, m_window->width(), m_window->height()).contains(pos)) return false;
        QTest::mouseClick(m_window, Qt::LeftButton, Qt::NoModifier, pos);
        QTest::qWait(40);
        return true;
    }
    bool capture(const QString &name) {
        m_window->requestUpdate(); QTest::qWait(120);
        const auto image = m_window->grabWindow();
        return !image.isNull() && image.save(QDir(m_captures).filePath(name + QStringLiteral(".png")));
    }
private slots:
    void ownerSeesRealQuotasThroughTheRealPage() {
        QTemporaryDir preferences, temporaryCaptures;
        QVERIFY(preferences.isValid() && temporaryCaptures.isValid());
        QCoreApplication::setOrganizationName(QStringLiteral("ACP quotas jetables"));
        QCoreApplication::setApplicationName(QStringLiteral("QtTest"));
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, preferences.path());
        m_captures = QString::fromUtf8(qgetenv("ACP_DESKTOP_QA_DIR"));
        if (m_captures.isEmpty()) m_captures = temporaryCaptures.path();
        QVERIFY(QDir().mkpath(m_captures));
        QuotaUiServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        Application controller; controller.registerQmlTypes();
        auto *api = controller.findChild<ApiClient*>();
        auto *auth = controller.findChild<AuthManager*>();
        auto *vm = controller.findChild<SubscriptionQuotasViewModel*>();
        auto *appearance = controller.findChild<SystemAppearance*>();
        auto *navigation = controller.findChild<NavigationModel*>();
        auto *commands = controller.findChild<CommandRegistry*>();
        QVERIFY(api && auth && vm && appearance && navigation && commands);
        vm->setClockForTesting([] { return QDateTime(QDate(2026, 9, 24), QTime(8, 3), QTimeZone::UTC); });
        vm->setTimeZoneForTesting(QTimeZone::fromSecondsAheadOfUtc(7200));
        api->setAllowInsecureLoopback(true);
        QVERIFY(!api->setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort()))).isError());
        QNetworkCookie cookie(QByteArrayLiteral("acp_session"), QByteArrayLiteral("session-ui-0123456789"));
        cookie.setHttpOnly(true);
        cookie.setPath(QStringLiteral("/"));
        QVERIFY(api->cookieJar()->setCookiesFromUrl({cookie}, api->baseUrl()));
        auth->applySessionPayload({{QStringLiteral("csrf_token"), QStringLiteral("ui-test-csrf")},
            {QStringLiteral("user"), QJsonObject{{QStringLiteral("id"), QStringLiteral("ui-owner")},
                {QStringLiteral("role"), QStringLiteral("owner")}, {QStringLiteral("display_name"), QStringLiteral("Propriétaire jetable")}}}});
        // La destination existe, est prête et s'atteint par sa commande.
        QVERIFY(navigation->isNavigable(QStringLiteral("quotas")));
        commands->execute(QStringLiteral("navigation.quotas"));
        QCOMPARE(navigation->currentRoute(), QStringLiteral("quotas"));
        QCOMPARE(navigation->currentTitle(), QStringLiteral("Quotas"));
        QCOMPARE(server.reads, 0); // Rien n'est lu tant que l'écran n'est pas affiché.

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
        QQmlComponent pageComponent(&engine); pageComponent.loadFromModule(QStringLiteral("Acp.Pages"), QStringLiteral("QuotasPage"));
        std::unique_ptr<QObject> pageObject(pageComponent.create());
        auto *page = qobject_cast<QQuickItem*>(pageObject.get()); QVERIFY2(page, qPrintable(pageComponent.errorString()));
        page->setParentItem(m_window->contentItem());
        m_window->resize(1280, 820); page->setSize(QSizeF(1280, 820));
        m_window->show(); m_window->requestActivate();
        QVERIFY(QTest::qWaitForWindowExposed(m_window));
        appearance->setThemePreference(QStringLiteral("dark"));
        QTRY_VERIFY(vm->active());
        QTRY_COMPARE(vm->state(), QStringLiteral("ready"));
        QCOMPARE(server.reads, 1);

        // Mention visible et lisible par un lecteur d'écran.
        auto *notice = item(QStringLiteral("quotasPersonalUseNotice"));
        QVERIFY(notice);
        QVERIFY2(accessibleName(notice).startsWith(QStringLiteral("Abonnements personnels du propriétaire — usage personnel uniquement")),
                 qPrintable(accessibleName(notice)));
        auto *noticeTitle = item(QStringLiteral("quotasPersonalUseTitle"));
        QVERIFY(noticeTitle);
        QCOMPARE(noticeTitle->property("text").toString(), QStringLiteral("Abonnements personnels du propriétaire — usage personnel uniquement"));

        // Une carte par relevé, nommée pour l'accessibilité par le résumé du ViewModel.
        auto *rows = qobject_cast<JsonListModel*>(vm->reports());
        QCOMPARE(rows->count(), 3);
        for (int index = 0; index < rows->count(); ++index) {
            const auto name = QStringLiteral("quotaCard-%1").arg(index);
            QTRY_VERIFY2(item(name), qPrintable(name));
            QCOMPARE(accessibleName(item(name)), rows->get(index).value(QStringLiteral("accessibleName")).toString());
        }
        QCOMPARE(item(QStringLiteral("quotaProvider-0"))->property("text").toString(), QStringLiteral("Codex (compte ChatGPT)"));
        QCOMPARE(item(QStringLiteral("quotaProvider-2"))->property("text").toString(), QStringLiteral("Claude Code"));
        QVERIFY(item(QStringLiteral("quotaState-1")));
        QCOMPARE(item(QStringLiteral("quotaState-1"))->property("label").toString(), QStringLiteral("Non connecté"));
        QVERIFY(!item(QStringLiteral("quotaStale-0")));
        QVERIFY(!item(QStringLiteral("quotaLimitReached-0")));
        // Une lecture en échec n'est pas un compteur : son identifiant réservé ne s'affiche pas.
        QVERIFY(item(QStringLiteral("quotaMeta-1")));
        QCOMPARE(item(QStringLiteral("quotaMeta-1"))->property("text").toString(),
                 QStringLiteral("Offre : Inconnu · Source : relevé officiel app-server · Compteur : aucun (lecture en échec)"));
        QVERIFY(item(QStringLiteral("quotaMeta-2")));
        QCOMPARE(item(QStringLiteral("quotaMeta-2"))->property("text").toString(),
                 QStringLiteral("Offre : Inconnu · Source : ligne d'état Claude Code · Compteur : unique"));

        // Jauge dessinée : 58 % restant sur la fenêtre de 5 h Codex.
        auto *gauge = item(QStringLiteral("quotaGauge-0-0"));
        QVERIFY(gauge);
        QCOMPARE(gauge->property("remainingPercent").toDouble(), 58.0);
        auto *fill = gauge->findChild<QQuickItem*>(QStringLiteral("quotaGaugeFill"));
        auto *track = gauge->findChild<QQuickItem*>(QStringLiteral("quotaGaugeTrack"));
        QVERIFY(fill && track && fill->isVisible());
        QVERIFY(qAbs(fill->width() - track->width() * 0.58) < 1.0);
        QVERIFY(accessibleName(gauge).contains(QStringLiteral("dans 3 h 57")));
        // Semaine Claude Code : reste inconnu, aucune barre dessinée.
        auto *unknown = item(QStringLiteral("quotaGauge-2-1"));
        QVERIFY(unknown);
        QVERIFY(!unknown->findChild<QQuickItem*>(QStringLiteral("quotaGaugeFill"))->isVisible());
        QVERIFY(accessibleName(unknown).contains(QStringLiteral("reste Inconnu")));
        QVERIFY(capture(QStringLiteral("12-quotas-dark-wide")));

        // Fenêtre réduite : l'écran n'est plus visible, la lecture périodique s'arrête ;
        // il relit à la restauration plutôt que d'afficher des valeurs d'avant.
        // La plateforme peut faire osciller l'état de la fenêtre pendant la réduction : ces
        // allers-retours transitoires ne déclenchent aucune lecture.
        m_window->showMinimized();
        QTRY_VERIFY(!vm->active());
        QTest::qWait(400);
        QVERIFY(!vm->active());
        const int readsWhileMinimized = server.reads;
        QCOMPARE(readsWhileMinimized, 1);
        m_window->showNormal();
        QTRY_VERIFY(vm->active());
        QTRY_COMPARE(vm->state(), QStringLiteral("ready"));
        QCOMPARE(server.reads, readsWhileMinimized + 1);
        QTRY_VERIFY(item(QStringLiteral("quotaCard-0")));

        // Actualisation manuelle : un vrai appel de plus, rien d'autre.
        const int readsBeforeRefresh = server.reads;
        QVERIFY(click(QStringLiteral("quotasRefreshButton")));
        QTRY_COMPARE(server.reads, readsBeforeRefresh + 1);
        QTRY_COMPARE(vm->state(), QStringLiteral("ready"));
        QTest::qWait(150);
        QCOMPARE(server.reads, readsBeforeRefresh + 1);

        // Limite atteinte : l'alerte nomme la cause en français, sans répéter son libellé ni
        // afficher l'identifiant anglais de la source ; l'offre « unknown » reste « Inconnu ».
        {
            QJsonObject reached = QJsonDocument::fromJson(fixture()).object();
            QJsonArray items = reached.value(QStringLiteral("items")).toArray();
            QJsonObject codex = items.at(1).toObject();
            QCOMPARE(codex.value(QStringLiteral("limit_id")).toString(), QStringLiteral("codex"));
            codex.insert(QStringLiteral("limit_reached"), true);
            codex.insert(QStringLiteral("reached_type"), QStringLiteral("workspace_owner_credits_depleted"));
            codex.insert(QStringLiteral("plan"), QStringLiteral("unknown"));
            items.replace(1, codex);
            reached.insert(QStringLiteral("items"), items);
            server.body = QJsonDocument(reached).toJson(QJsonDocument::Compact);
        }
        QVERIFY(click(QStringLiteral("quotasRefreshButton")));
        QTRY_VERIFY(item(QStringLiteral("quotaLimitReached-0")));
        QTRY_COMPARE(accessibleName(item(QStringLiteral("quotaLimitReached-0"))),
                     QStringLiteral("Limite atteinte : crédits du propriétaire de l'espace de travail épuisés"));
        QVERIFY(item(QStringLiteral("quotaMeta-0")));
        QCOMPARE(item(QStringLiteral("quotaMeta-0"))->property("text").toString(),
                 QStringLiteral("Offre : Inconnu · Source : relevé officiel app-server · Compteur : codex"));
        QVERIFY(capture(QStringLiteral("12b-quotas-limit-reached")));
        server.body = fixture();

        appearance->setThemePreference(QStringLiteral("light"));
        // Taille posée explicitement : une vraie fenêtre applique resize() de façon différée.
        m_window->resize(960, 700); page->setSize(QSizeF(960, 700));
        QTRY_VERIFY(item(QStringLiteral("quotaCard-0")) && item(QStringLiteral("quotaCard-0"))->width() <= 960);
        QVERIFY(capture(QStringLiteral("13-quotas-light-narrow")));

        // Refus du serveur : l'écran le dit, sans valeur résiduelle.
        server.status = 403;
        server.body = QByteArrayLiteral("{\"detail\":\"Quotas d'abonnement réservés au propriétaire de la plateforme : l'usage d'un abonnement est personnel à son titulaire.\"}");
        QVERIFY(click(QStringLiteral("quotasRefreshButton")));
        QTRY_COMPARE(vm->state(), QStringLiteral("forbidden"));
        QTRY_COMPARE(auth->state(), SessionStatus::Connected);
        QCOMPARE(vm->state(), QStringLiteral("forbidden"));
        QTRY_VERIFY(item(QStringLiteral("quotasEmptyState")));
        QCOMPARE(item(QStringLiteral("quotasEmptyState"))->property("title").toString(),
                 QStringLiteral("Réservé au propriétaire de la plateforme"));
        QVERIFY(!item(QStringLiteral("quotaCard-0")));
        QVERIFY(item(QStringLiteral("quotasPersonalUseNotice")));
        QVERIFY(capture(QStringLiteral("14-quotas-owner-only")));

        pageObject.reset();
        QVERIFY(!vm->active());

        // Coquille réelle : l'entrée « Quotas » de la navigation ouvre l'écran par la zone
        // de travail, et le quitter arrête la lecture.
        server.status = 200;
        server.body = fixture();
        navigation->setCurrentRoute(QStringLiteral("home"));
        QQmlComponent shellComponent(&engine);
        shellComponent.setData(QByteArrayLiteral("import QtQuick\nimport Acp.Station\nItem {\n"
            "    SideNavigation { id: side; width: 240; height: parent.height }\n"
            "    WorkArea { anchors.left: side.right; anchors.right: parent.right; height: parent.height }\n}"), QUrl());
        std::unique_ptr<QObject> shellObject(shellComponent.create());
        auto *shell = qobject_cast<QQuickItem*>(shellObject.get());
        QVERIFY2(shell, qPrintable(shellComponent.errorString()));
        shell->setParentItem(m_window->contentItem());
        shell->setSize(QSizeF(960, 700));
        QTRY_VERIFY(item(QStringLiteral("navigation-quotas")));
        QCOMPARE(accessibleName(item(QStringLiteral("navigation-quotas"))), QStringLiteral("Quotas"));
        const int readsBefore = server.reads;
        QVERIFY(click(QStringLiteral("navigation-quotas")));
        QCOMPARE(navigation->currentRoute(), QStringLiteral("quotas"));
        QTRY_VERIFY(item(QStringLiteral("quotasRefreshButton")));
        QVERIFY(vm->active());
        QTRY_COMPARE(vm->state(), QStringLiteral("ready"));
        QCOMPARE(server.reads, readsBefore + 1);
        navigation->setCurrentRoute(QStringLiteral("home"));
        QTRY_VERIFY(!vm->active());
        shellObject.reset();

        QVERIFY2(warnings.isEmpty(), qPrintable(warnings.join(QLatin1Char('\n'))));
        qInfo().noquote() << "Captures quotas :" << m_captures;
        m_window->hide(); m_window = nullptr;
    }
};

int main(int argc, char **argv) {
#ifdef Q_OS_WIN
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
#endif
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    QGuiApplication app(argc, argv);
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    TestQuotasUi test;
    return QTest::qExec(&test, argc, argv);
}
#include "tst_quotas_ui.moc"
