// Ce que la coquille QML a le droit de voir.
//
// Règle appliquée ici : QML ne parle JAMAIS directement à ApiClient, à AuthManager ni au
// coffre. Il lit ce modèle de vue, qui ne publie que des faits déjà interprétés et
// aucune donnée secrète. C'est ce qui rend vérifiable l'affirmation « aucun secret
// n'atteint QML » : il suffit de lire les propriétés déclarées ci-dessous.

#pragma once

#include <QObject>
#include <QString>

namespace acp {

class ApiClient;
class AuthManager;
class CompatibilityService;
class CommandRegistry;
class EventStreamService;
class HealthService;
class NavigationModel;
class SettingsStore;

class ShellViewModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool firstRun READ isFirstRun NOTIFY shellStateChanged)
    Q_PROPERTY(bool authenticated READ isAuthenticated NOTIFY shellStateChanged)
    Q_PROPERTY(QString serverUrl READ serverUrl NOTIFY shellStateChanged)
    Q_PROPERTY(QString serverUrlLabel READ serverUrlLabel NOTIFY shellStateChanged)
    Q_PROPERTY(QString workspaceLabel READ workspaceLabel NOTIFY shellStateChanged)
    Q_PROPERTY(QString statusSummary READ statusSummary NOTIFY shellStateChanged)
    Q_PROPERTY(QString lastNotice READ lastNotice NOTIFY noticeChanged)
    Q_PROPERTY(bool commandPaletteOpen READ isCommandPaletteOpen WRITE setCommandPaletteOpen NOTIFY
                   commandPaletteOpenChanged)
    Q_PROPERTY(bool inspectorVisible READ isInspectorVisible WRITE setInspectorVisible NOTIFY
                   inspectorVisibleChanged)
    Q_PROPERTY(bool sidebarCollapsed READ isSidebarCollapsed WRITE setSidebarCollapsed NOTIFY
                   sidebarCollapsedChanged)

public:
    ShellViewModel(ApiClient *client, AuthManager *auth, HealthService *health,
                   CompatibilityService *compatibility, EventStreamService *streams,
                   NavigationModel *navigation, CommandRegistry *commands,
                   SettingsStore *settings, QObject *parent = nullptr);

    /*! Vrai tant qu'aucune adresse de serveur n'a jamais été saisie. */
    [[nodiscard]] bool isFirstRun() const;
    [[nodiscard]] bool isAuthenticated() const;
    [[nodiscard]] QString serverUrl() const;

    /*! « Non configuré » quand aucune adresse n'est posée. Jamais une URL inventée. */
    [[nodiscard]] QString serverUrlLabel() const;

    /*! Identité de l'environnement affichée dans la barre supérieure. Elle ne prétend
        pas connaître un nom d'espace de travail tant qu'aucune route ne l'a fourni. */
    [[nodiscard]] QString workspaceLabel() const;

    /*! Résumé d'une ligne pour la barre basse : lien, session, flux. */
    [[nodiscard]] QString statusSummary() const;

    [[nodiscard]] const QString &lastNotice() const { return m_lastNotice; }

    [[nodiscard]] bool isCommandPaletteOpen() const { return m_commandPaletteOpen; }
    void setCommandPaletteOpen(bool open);

    [[nodiscard]] bool isInspectorVisible() const { return m_inspectorVisible; }
    void setInspectorVisible(bool visible);

    [[nodiscard]] bool isSidebarCollapsed() const;
    void setSidebarCollapsed(bool collapsed);

    /*!
        Applique une adresse de serveur saisie par l'opérateur.

        Renvoie une chaîne vide en cas de succès, ou le motif du refus en français. Rien
        n'est mémorisé tant que l'URL n'est pas acceptée.
    */
    Q_INVOKABLE QString applyServerUrl(const QString &url, bool allowInsecureLoopback);

    /*! Affiche un message dans la barre basse. Il n'est jamais inventé : il vient
        toujours d'un fait (refus, erreur serveur, résultat de commande). */
    Q_INVOKABLE void notify(const QString &message);

signals:
    void shellStateChanged();
    void noticeChanged();
    void commandPaletteOpenChanged();
    void inspectorVisibleChanged();
    void sidebarCollapsedChanged();

private:
    void refreshCommandContext();

    ApiClient *m_client = nullptr;
    AuthManager *m_auth = nullptr;
    HealthService *m_health = nullptr;
    CompatibilityService *m_compatibility = nullptr;
    EventStreamService *m_streams = nullptr;
    NavigationModel *m_navigation = nullptr;
    CommandRegistry *m_commands = nullptr;
    SettingsStore *m_settings = nullptr;

    QString m_lastNotice;
    bool m_commandPaletteOpen = false;
    bool m_inspectorVisible = false;
};

} // namespace acp
