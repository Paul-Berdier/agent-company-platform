// Chaque écran livré et la coquille se chargent hors écran sans liaison cassée.
//
// Les singletons QML sont enregistrés une fois par processus : un seul cas de test crée
// l'application et charge tous les composants, pages puis coquille.

#include "app/Application.h"

#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickWindow>
#include <QTest>

#include <memory>

class TestDesktopPages : public QObject
{
    Q_OBJECT
private slots:
    void componentsLoadWithoutBrokenBindings()
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
        const QList<QPair<QString, QString>> components = {
            {QStringLiteral("Acp.Pages"), QStringLiteral("HomePage")},
            {QStringLiteral("Acp.Pages"), QStringLiteral("FirstRunPage")},
            {QStringLiteral("Acp.Pages"), QStringLiteral("DiagnosticsPage")},
            {QStringLiteral("Acp.Pages"), QStringLiteral("SettingsPage")},
            {QStringLiteral("Acp.Station"), QStringLiteral("ShellRoot")},
        };
        for (const auto &[module, name] : components) {
            warnings.clear();
            QQmlComponent component(&engine);
            component.loadFromModule(module, name);
            QTRY_VERIFY_WITH_TIMEOUT(component.status() != QQmlComponent::Loading, 5000);
            QVERIFY2(component.isReady(), qPrintable(component.errorString()));
            std::unique_ptr<QObject> object(component.create());
            QVERIFY2(object, qPrintable(component.errorString()));
            auto *item = qobject_cast<QQuickItem *>(object.get());
            QVERIFY(item);
            item->setParentItem(window.contentItem());
            item->setSize(QSizeF(1280, 850));
            window.show();
            QTest::qWait(50);
            QVERIFY2(warnings.isEmpty(),
                     qPrintable(name + QStringLiteral(": ") + warnings.join(QLatin1Char('\n'))));
        }
        window.hide();

        // La racine elle-même : fenêtre, écran de connexion (aucune session) et palette.
        warnings.clear();
        QVERIFY(application.load(&engine));
        QTest::qWait(100);
        QVERIFY2(warnings.isEmpty(), qPrintable(QStringLiteral("App : ") + warnings.join(QLatin1Char('\n'))));
        auto *racine = qobject_cast<QQuickWindow *>(engine.rootObjects().constLast());
        QVERIFY(racine);
        QVERIFY(racine->findChild<QObject *>(QStringLiteral("connexion-se-connecter")));
        racine->close();
    }
};
QTEST_MAIN(TestDesktopPages)
#include "tst_desktop_pages.moc"
