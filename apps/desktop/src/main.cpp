// Point d'entrée de la station de travail.
//
// Rien de métier ici : construire, enregistrer, charger, démarrer, et échouer FERMÉ si
// la scène ne se charge pas. Une fenêtre vide serait un faux succès.

#include "app/Application.h"
#include "app/BuildConfig.h"
#include "diagnostics/Redaction.h"

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QTextStream>
#include <QtGlobal>

#include <cstdio>

namespace {

/*!
    Filtre de journalisation : tout message sortant passe par l'expurgation.

    C'est la dernière barrière avant qu'un jeton n'atterrisse dans un fichier de
    diagnostic du poste. Elle ne remplace pas la discipline du code — aucun secret n'est
    passé à qDebug — elle la double.
*/
void redactingMessageHandler(QtMsgType type, const QMessageLogContext &context,
                             const QString &message)
{
    Q_UNUSED(context)
    const QString safe = acp::redactSecrets(message);
    QString level = QStringLiteral("INFO");
    switch (type) {
    case QtDebugMsg:
        level = QStringLiteral("DEBUG");
        break;
    case QtInfoMsg:
        level = QStringLiteral("INFO");
        break;
    case QtWarningMsg:
        level = QStringLiteral("AVERTISSEMENT");
        break;
    case QtCriticalMsg:
        level = QStringLiteral("CRITIQUE");
        break;
    case QtFatalMsg:
        level = QStringLiteral("FATAL");
        break;
    }
    QTextStream stream(stderr);
    stream << level << QStringLiteral(" : ") << safe << Qt::endl;
}

} // namespace

int main(int argc, char *argv[])
{
    qInstallMessageHandler(redactingMessageHandler);

    QGuiApplication application(argc, argv);
    QGuiApplication::setOrganizationName(QStringLiteral("Agent Company Platform"));
    // Domaine employé uniquement comme espace de nommage de QSettings : il n'est pas une
    // adresse de serveur, et aucune adresse n'est codée en dur dans ce programme.
    QGuiApplication::setOrganizationDomain(QStringLiteral("agent-company-platform.local"));
    QGuiApplication::setApplicationName(QStringLiteral("Station de travail"));
    QGuiApplication::setApplicationVersion(QString::fromLatin1(ACP_DESKTOP_VERSION));

    // Style Qt Quick Controls : « Basic » est le seul style entièrement personnalisable
    // par les jetons du produit. Les styles natifs imposent leurs propres couleurs et
    // rendraient les jetons partiellement inopérants.
    QQuickStyle::setStyle(QStringLiteral("Basic"));

    acp::Application controller;
    controller.registerQmlTypes();

    QQmlApplicationEngine engine;
    if (!controller.load(&engine)) {
        // Échec fermé : on ne laisse pas une fenêtre vide faire croire que tout va bien.
        QTextStream(stderr)
            << QStringLiteral("La scène QML n'a pas pu être chargée : la station s'arrête.")
            << Qt::endl;
        return 1;
    }

    QObject::connect(&application, &QGuiApplication::aboutToQuit, &controller,
                     [&controller] { controller.shutdown(); });

    controller.start();
    return QGuiApplication::exec();
}
