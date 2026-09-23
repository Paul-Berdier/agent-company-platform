#include "app/Application.h"
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickWindow>
#include <QTest>

class TestDesktopPages : public QObject
{
    Q_OBJECT
private slots:
    void pagesLoadWithoutBrokenBindings()
    {
        acp::Application application;
        application.registerQmlTypes();
        QQmlApplicationEngine engine;
        QStringList warnings;
        connect(&engine, &QQmlEngine::warnings, this, [&warnings](const QList<QQmlError> &errors) {
            for (const auto &error : errors) warnings.append(error.toString());
        });
        QQuickWindow window;
        window.resize(1280, 850);
        const QStringList pages = {QStringLiteral("ProjectsPage"), QStringLiteral("ConversationsPage"),
            QStringLiteral("MissionsPage"), QStringLiteral("ArtifactsPage"), QStringLiteral("HomePage"),
            QStringLiteral("PlatformPage"), QStringLiteral("ExtensionsPage"), QStringLiteral("OperationsPage"),
            QStringLiteral("SettingsPage"), QStringLiteral("StudioPage")};
        for (const auto &name : pages) {
            warnings.clear();
            QQmlComponent component(&engine);
            component.loadFromModule(QStringLiteral("Acp.Pages"), name);
            QTRY_VERIFY_WITH_TIMEOUT(component.status() != QQmlComponent::Loading, 5000);
            QVERIFY2(component.isReady(), qPrintable(component.errorString()));
            std::unique_ptr<QObject> page(component.create());
            QVERIFY2(page, qPrintable(component.errorString()));
            auto *item = qobject_cast<QQuickItem *>(page.get());
            QVERIFY(item);
            item->setParentItem(window.contentItem());
            item->setSize(QSizeF(1280, 850));
            window.show();
            QTest::qWait(50);
            QVERIFY2(warnings.isEmpty(), qPrintable(name + QStringLiteral(": ") + warnings.join(QLatin1Char('\n'))));
        }
        window.hide();
    }
};
QTEST_MAIN(TestDesktopPages)
#include "tst_desktop_pages.moc"
