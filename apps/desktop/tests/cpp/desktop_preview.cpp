// Harnais de recette manuelle : construit uniquement avec les tests, jamais empaqueté.
// Le lanceur Python fournit une API jetable et un compte synthétique via l'environnement.
#include "app/Application.h"
#include "api/ApiClient.h"
#include "auth/AuthManager.h"
#include "storage/SettingsStore.h"
#include "viewmodels/WorkspaceViewModel.h"
#include "navigation/NavigationModel.h"
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QSettings>
#include <QTemporaryDir>
#include <QTimer>

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    if (qgetenv("ACP_DESKTOP_TEST_DISPOSABLE") != "1") return 2;
    const QUrl url(QString::fromUtf8(qgetenv("ACP_DESKTOP_TEST_API_URL")));
    if (url.scheme() != QStringLiteral("http") || url.host() != QStringLiteral("127.0.0.1")) return 2;
    QTemporaryDir preferences;
    if (!preferences.isValid()) return 2;
    QCoreApplication::setOrganizationName(QStringLiteral("ACP QA jetable"));
    QCoreApplication::setApplicationName(QStringLiteral("Recette native"));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, preferences.path());
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    acp::Application controller;
    controller.registerQmlTypes();
    auto *settings = controller.findChild<acp::SettingsStore *>();
    settings->setAllowInsecureLoopback(true);
    settings->setServerUrl(url);
    auto *auth = controller.findChild<acp::AuthManager *>();
    auto *workspace = controller.findChild<acp::WorkspaceViewModel *>();
    bool selected = false;
    QObject::connect(workspace, &acp::WorkspaceViewModel::changed, &controller, [&] {
        if (selected || workspace->busy() || workspace->projects()->count() == 0) return;
        selected = true;
        workspace->selectProject(QString::fromUtf8(qgetenv("ACP_DESKTOP_TEST_PROJECT_ID")));
        controller.findChild<acp::NavigationModel *>()->setCurrentRoute(QStringLiteral("projects"));
    });
    QQmlApplicationEngine engine;
    if (!controller.load(&engine)) return 3;
    controller.start();
    QTimer::singleShot(500, auth, [auth] {
        auth->logIn(QString::fromUtf8(qgetenv("ACP_DESKTOP_TEST_LOGIN")),
                    QString::fromUtf8(qgetenv("ACP_DESKTOP_TEST_PASSWORD")));
    });
    return app.exec();
}
