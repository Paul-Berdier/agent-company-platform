// Assemblage de la station : construction des services, enregistrement QML, démarrage.
//
// Un seul objet connaît la composition de l'application. Il est le seul à créer un
// ApiClient, un AuthManager et un coffre ; QML ne les instancie jamais, et aucun module
// ne va les chercher par une variable globale.

#pragma once

#include <QObject>
#include <QString>

#include <memory>

class QQmlApplicationEngine;

namespace acp {

class ApiClient;
class AuthManager;
class CommandRegistry;
class CompatibilityService;
class CredentialVault;
class DiagnosticsViewModel;
class EventStreamService;
class HealthService;
class NavigationModel;
class SettingsStore;
class ShellViewModel;
class SystemAppearance;
class WorkspaceViewModel;
class ConversationsViewModel;
class MissionsViewModel;
class ArtifactsViewModel;
class PlatformViewModel;
class OperationsViewModel;
class SessionPersistence;
class UpdateService;

class Application : public QObject
{
    Q_OBJECT

public:
    explicit Application(QObject *parent = nullptr);
    ~Application() override;

    /*!
        Enregistre les types C++ auprès du moteur QML, sous l'URI « Acp.Runtime ».

        Choix assumé : enregistrement IMPÉRATIF plutôt que macros QML_ELEMENT. La
        bibliothèque de logique reste ainsi indépendante du module QML, ce qui permet aux
        cibles de test de la lier sans embarquer la scène graphique. Le prix est l'absence
        d'informations de type pour qmllint sur ces objets, et il est documenté.
    */
    void registerQmlTypes();

    /*! Expose les singletons de contexte et charge App.qml. Renvoie faux si le chargement
        échoue — auquel cas l'application se termine, elle n'ouvre pas de fenêtre vide. */
    bool load(QQmlApplicationEngine *engine);

    /*! Restaure les préférences, sonde le serveur et tente la reprise de session. */
    void start();

    /*! Ferme proprement : flux fermés, préférences écrites. Un flux laissé ouvert reste
        compté par le serveur jusqu'à 900 secondes. */
    void shutdown();

    [[nodiscard]] static QString version();
    [[nodiscard]] static QString buildInfo();
    [[nodiscard]] static QByteArray userAgent();

private:
    void registerBuiltinCommands();

    SettingsStore *m_settings = nullptr;
    ApiClient *m_client = nullptr;
    AuthManager *m_auth = nullptr;
    HealthService *m_health = nullptr;
    CompatibilityService *m_compatibility = nullptr;
    EventStreamService *m_streams = nullptr;
    NavigationModel *m_navigation = nullptr;
    CommandRegistry *m_commands = nullptr;
    SystemAppearance *m_appearance = nullptr;
    ShellViewModel *m_shell = nullptr;
    DiagnosticsViewModel *m_diagnostics = nullptr;
    WorkspaceViewModel *m_workspace = nullptr;
    ConversationsViewModel *m_conversations = nullptr;
    MissionsViewModel *m_missions = nullptr;
    ArtifactsViewModel *m_artifacts = nullptr;
    PlatformViewModel *m_platform = nullptr;
    OperationsViewModel *m_operations = nullptr;
    SessionPersistence *m_sessionStorage = nullptr;
    UpdateService *m_updates = nullptr;
    std::unique_ptr<CredentialVault> m_vault;
};

} // namespace acp
