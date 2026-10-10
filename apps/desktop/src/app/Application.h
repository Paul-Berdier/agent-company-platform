// Assemblage de la station : construction des services, enregistrement QML, démarrage.
//
// Un seul objet connaît la composition de l'application. Il est le seul à créer un
// ApiClient, la session et le coffre ; QML ne les instancie jamais, et aucun module ne va
// les chercher par une variable globale.

#pragma once

#include <QObject>
#include <QString>

#include <memory>

class QQmlApplicationEngine;

namespace acp {

class AccueilViewModel;
class ApiClient;
class ClientGreffonPoste;
class CompatibiliteHermes;
class CommandRegistry;
class CredentialVault;
class DemandesAgent;
class DiagnosticsViewModel;
class DiscussionViewModel;
class EventStreamService;
class GatewayClient;
class HealthService;
class NavigationModel;
class PosteViewModel;
class ProjetsViewModel;
class QuestionsViewModel;
class QuotasViewModel;
class RoutageViewModel;
class SauvegardeViewModel;
class SessionHermes;
class SettingsStore;
class ShellViewModel;
class SystemAppearance;
class UpdateService;

class Application : public QObject
{
    Q_OBJECT

public:
    /*!
        `nomCoffre` : préfixe des entrées du coffre Windows. Le produit garde la valeur par
        défaut ; seul l'exécutable du bout en bout local (jamais installé) en passe un autre,
        pour ne jamais toucher l'entrée réelle du poste.
    */
    explicit Application(QObject *parent = nullptr,
                         const QString &nomCoffre = QStringLiteral("AgentCompanyPlatform"));
    ~Application() override;

    /*!
        Enregistre les types C++ auprès du moteur QML, sous l'URI « Acp.Runtime ».

        Choix assumé : enregistrement IMPÉRATIF plutôt que macros QML_ELEMENT. La
        bibliothèque de logique reste ainsi indépendante du module QML, ce qui permet aux
        cibles de test de la lier sans embarquer la scène graphique.
    */
    void registerQmlTypes();

    /*! Expose les singletons de contexte et charge App.qml. Renvoie faux si le chargement
        échoue — auquel cas l'application se termine, elle n'ouvre pas de fenêtre vide. */
    bool load(QQmlApplicationEngine *engine);

    /*! Restaure les préférences, sonde le serveur et reprend la session mémorisée. */
    void start();

    /*! Ferme proprement : sondes arrêtées, préférences écrites. */
    void shutdown();

    [[nodiscard]] static QString version();
    [[nodiscard]] static QString buildInfo();
    [[nodiscard]] static QByteArray userAgent();

private:
    void registerBuiltinCommands();

    SettingsStore *m_settings = nullptr;
    ApiClient *m_client = nullptr;
    std::unique_ptr<CredentialVault> m_vault;
    SessionHermes *m_session = nullptr;
    std::unique_ptr<ClientGreffonPoste> m_greffon;
    CompatibiliteHermes *m_compatibilite = nullptr;
    GatewayClient *m_passerelle = nullptr;
    EventStreamService *m_flux = nullptr;
    HealthService *m_health = nullptr;
    NavigationModel *m_navigation = nullptr;
    CommandRegistry *m_commands = nullptr;
    SystemAppearance *m_appearance = nullptr;
    ShellViewModel *m_shell = nullptr;
    DiagnosticsViewModel *m_diagnostics = nullptr;
    AccueilViewModel *m_accueil = nullptr;
    ProjetsViewModel *m_projets = nullptr;
    QuestionsViewModel *m_questions = nullptr;
    PosteViewModel *m_poste = nullptr;
    QuotasViewModel *m_quotas = nullptr;
    RoutageViewModel *m_routage = nullptr;
    SauvegardeViewModel *m_sauvegarde = nullptr;
    DemandesAgent *m_demandes = nullptr;
    DiscussionViewModel *m_discussion = nullptr;
    UpdateService *m_updates = nullptr;
    bool m_greffonBloque = false; //!< Dernier état du blocage du greffon (verdict de compatibilité).
};

} // namespace acp
