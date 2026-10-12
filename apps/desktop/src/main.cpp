// Point d'entrée de la station de travail.
//
// Rien de métier ici : construire, enregistrer, charger, démarrer, et échouer FERMÉ si
// la scène ne se charge pas. Une fenêtre vide serait un faux succès.

#include "app/Application.h"
#include "app/BuildConfig.h"
#include "app/GardeInstance.h"
#include "diagnostics/Redaction.h"

#include <QGuiApplication>
#include <QIcon>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QTextStream>
#include <QtGlobal>

#include <cstdio>
#include <string>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

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

#ifdef Q_OS_WIN
    // Installeur en cours (SetupMutex de AgentCompanyPlatform.iss) : la station ne démarre pas pendant
    // qu'il remplace ses fichiers. Seule la relance par l'installeur lui-même (--apres-mise-a-jour) passe.
    if (!QCoreApplication::arguments().contains(QStringLiteral("--apres-mise-a-jour"))) {
        if (HANDLE installeur = ::OpenMutexW(SYNCHRONIZE, FALSE, L"AcpStationInstallation")) {
            ::CloseHandle(installeur);
            ::MessageBoxW(nullptr, L"Une mise à jour de la station est en cours d'installation : elle se relancera "
                                   L"d'elle-même.", L"Station de travail", MB_OK | MB_ICONINFORMATION);
            return acp::GardeInstance::kCodeSecondeInstance;
        }
    }
#endif

    // Une seule station par poste : deux instances rejoueraient le même jeton de
    // rafraîchissement, et Authelia révoquerait la session (identite.md § 12.1).
    acp::GardeInstance garde(acp::GardeInstance::cheminParDefaut());
    QString refusInstance;
    if (!garde.acquerir(&refusInstance)) {
        QTextStream(stderr) << refusInstance << Qt::endl;
#ifdef Q_OS_WIN
        const std::wstring texte = refusInstance.toStdWString();
        ::MessageBoxW(nullptr, texte.c_str(), L"Station de travail", MB_OK | MB_ICONINFORMATION);
#endif
        return acp::GardeInstance::kCodeSecondeInstance;
    }

    // Style Qt Quick Controls : « Basic » est le seul style entièrement personnalisable
    // par les jetons du produit. Les styles natifs imposent leurs propres couleurs et
    // rendraient les jetons partiellement inopérants.
    QQuickStyle::setStyle(QStringLiteral("Basic"));

    // Icône de fenêtre et de barre des tâches (D165) : l'emblème, dessiné pour chaque taille
    // (Acp.Pixel, ressources engendrées par scripts/generer_assets_pixel.py). L'exécutable
    // porte la même icône par sa ressource Windows (AgentCompanyPlatform.rc).
    QIcon embleme;
    for (const int taille : {16, 20, 24, 32, 40, 48, 64, 128, 256}) {
        embleme.addFile(QStringLiteral(":/qt/qml/Acp/Pixel/assets/embleme-%1.png").arg(taille), QSize(taille, taille));
    }
    QGuiApplication::setWindowIcon(embleme);

    acp::Application controller;
    // Mise à jour téléchargée et vérifiée lors d'une session précédente : installée avant toute fenêtre,
    // l'installeur relance la station (D170).
    if (controller.installPendingUpdateAtStartup()) {
        return 0;
    }
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
