// Écran de diagnostics : uniquement des valeurs réelles.
//
// Chaque ligne est un FAIT mesuré ou lu, ou bien « Inconnu ». Aucune ligne n'est
// fabriquée pour remplir l'écran, aucune valeur n'est estimée, aucun contrôle n'est
// affiché vert par défaut. Une valeur qui n'a jamais été mesurée dit qu'elle ne l'a
// jamais été.

#pragma once

#include <QAbstractListModel>
#include <QList>
#include <QObject>
#include <QString>

namespace acp {

class ApiClient;
class AuthManager;
class CompatibilityService;
class CredentialVault;
class EventStreamService;
class HealthService;
class SettingsStore;
class SystemAppearance;

class DiagnosticsViewModel : public QAbstractListModel
{
    Q_OBJECT

public:
    enum Roles {
        SectionRole = Qt::UserRole + 1,
        LabelRole,
        ValueRole,
        KnownRole,   //!< Faux quand la valeur n'a jamais pu être mesurée.
        MonospaceRole, //!< Vrai pour les identifiants, chemins, durées, versions.
    };
    Q_ENUM(Roles)

    struct Entry
    {
        QString section;
        QString label;
        QString value;
        bool known = true;
        bool monospace = false;
    };

    DiagnosticsViewModel(ApiClient *client, AuthManager *auth, HealthService *health,
                         CompatibilityService *compatibility, EventStreamService *streams,
                         SettingsStore *settings, SystemAppearance *appearance,
                         CredentialVault *vault, QString clientVersion, QString buildInfo,
                         QObject *parent = nullptr);

    [[nodiscard]] int rowCount(const QModelIndex &parent = {}) const override;
    [[nodiscard]] QVariant data(const QModelIndex &index, int role) const override;
    [[nodiscard]] QHash<int, QByteArray> roleNames() const override;

    /*! Recalcule toutes les lignes depuis les services. */
    Q_INVOKABLE void refresh();

    /*!
        Assemble un rapport texte, expurgé, destiné à être copié dans un ticket.

        Il passe intégralement par acp::redactSecrets() avant d'être rendu : un rapport de
        diagnostic est exactement le fichier par lequel un jeton fuit.
    */
    [[nodiscard]] Q_INVOKABLE QString buildReport() const;

private:
    QList<Entry> m_entries;

    ApiClient *m_client = nullptr;
    AuthManager *m_auth = nullptr;
    HealthService *m_health = nullptr;
    CompatibilityService *m_compatibility = nullptr;
    EventStreamService *m_streams = nullptr;
    SettingsStore *m_settings = nullptr;
    SystemAppearance *m_appearance = nullptr;
    CredentialVault *m_vault = nullptr;
    QString m_clientVersion;
    QString m_buildInfo;
};

} // namespace acp
