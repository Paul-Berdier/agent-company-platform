// Harnais des tests Qt Quick Test de la coquille.
//
// QUICK_TEST_MAIN_WITH_SETUP permet d'exécuter du C++ avant les tests QML : ici, poser le
// style Qt Quick Controls employé par le produit, faute de quoi les composants seraient
// éprouvés sur un style différent de celui de la station.
// https://doc.qt.io/qt-6/qtquicktest-index.html — consulté le 18 septembre 2026.
//
// Le harnais balaie récursivement QUICK_TEST_SOURCE_DIR à la recherche des fichiers
// « tst_*.qml ».

#include <QQmlEngine>
#include <QQuickStyle>
#include <QtQuickTest>

class Setup : public QObject
{
    Q_OBJECT

public slots:
    void applicationAvailable()
    {
        // Même style que la station : « Basic » est le seul entièrement pilotable par les
        // jetons du produit.
        QQuickStyle::setStyle(QStringLiteral("Basic"));
    }

    void qmlEngineAvailable(QQmlEngine *engine)
    {
        Q_UNUSED(engine)
        // Aucun singleton C++ n'est injecté : ces tests portent sur les composants de
        // présentation, qui ne doivent dépendre d'aucun service. Un composant qui
        // exigerait ici un service serait précisément le couplage à éviter.
    }
};

QUICK_TEST_MAIN_WITH_SETUP(acp_shell, Setup)

#include "tst_qml_shell.moc"
