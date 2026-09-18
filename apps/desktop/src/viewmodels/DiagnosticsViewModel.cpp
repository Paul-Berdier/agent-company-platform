#include "viewmodels/DiagnosticsViewModel.h"

#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"
#include "diagnostics/Redaction.h"
#include "events/EventStreamService.h"
#include "services/CompatibilityService.h"
#include "services/HealthService.h"
#include "storage/CredentialVault.h"
#include "storage/SettingsStore.h"
#include "system/SystemAppearance.h"

#include <QLibraryInfo>
#include <QStringList>
#include <QSysInfo>

namespace acp {

namespace {

//! Valeur affichée quand rien n'a jamais été mesuré. Jamais un zéro, jamais « OK ».
const QString &unknownValue()
{
    static const QString value = QStringLiteral("Inconnu");
    return value;
}

} // namespace

DiagnosticsViewModel::DiagnosticsViewModel(ApiClient *client, AuthManager *auth,
                                           HealthService *health,
                                           CompatibilityService *compatibility,
                                           EventStreamService *streams, SettingsStore *settings,
                                           SystemAppearance *appearance, CredentialVault *vault,
                                           QString clientVersion, QString buildInfo,
                                           QObject *parent)
    : QAbstractListModel(parent)
    , m_client(client)
    , m_auth(auth)
    , m_health(health)
    , m_compatibility(compatibility)
    , m_streams(streams)
    , m_settings(settings)
    , m_appearance(appearance)
    , m_vault(vault)
    , m_clientVersion(std::move(clientVersion))
    , m_buildInfo(std::move(buildInfo))
{
    connect(m_health, &HealthService::changed, this, &DiagnosticsViewModel::refresh);
    connect(m_auth, &AuthManager::stateChanged, this, &DiagnosticsViewModel::refresh);
    connect(m_compatibility, &CompatibilityService::stateChanged, this,
            &DiagnosticsViewModel::refresh);
    connect(m_streams, &EventStreamService::subscriptionsChanged, this,
            &DiagnosticsViewModel::refresh);
    connect(m_client, &ApiClient::baseUrlChanged, this, &DiagnosticsViewModel::refresh);
    refresh();
}

int DiagnosticsViewModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : static_cast<int>(m_entries.size());
}

QVariant DiagnosticsViewModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_entries.size()) {
        return {};
    }
    const Entry &entry = m_entries.at(index.row());
    switch (role) {
    case SectionRole:
        return entry.section;
    case LabelRole:
        return entry.label;
    case ValueRole:
        return entry.value;
    case KnownRole:
        return entry.known;
    case MonospaceRole:
        return entry.monospace;
    default:
        return {};
    }
}

QHash<int, QByteArray> DiagnosticsViewModel::roleNames() const
{
    return {
        {SectionRole, QByteArrayLiteral("section")},
        {LabelRole, QByteArrayLiteral("label")},
        {ValueRole, QByteArrayLiteral("value")},
        {KnownRole, QByteArrayLiteral("known")},
        {MonospaceRole, QByteArrayLiteral("monospace")},
    };
}

void DiagnosticsViewModel::refresh()
{
    QList<Entry> entries;
    const QString station = QStringLiteral("Station");
    const QString connection = QStringLiteral("Connexion");
    const QString session = QStringLiteral("Session");
    const QString streams = QStringLiteral("Flux d'événements");
    const QString storage = QStringLiteral("Stockage local");
    const QString proof = QStringLiteral("Preuve");

    // --- Station ------------------------------------------------------------
    entries.append({station, QStringLiteral("Version de la station"), m_clientVersion, true, true});
    entries.append({station, QStringLiteral("Informations de construction"), m_buildInfo, true, true});
    entries.append({station, QStringLiteral("Version de Qt (exécution)"),
                    QLibraryInfo::version().toString(), true, true});
    entries.append({station, QStringLiteral("Système"), QSysInfo::prettyProductName(), true, false});
    entries.append({station, QStringLiteral("Architecture"), QSysInfo::currentCpuArchitecture(),
                    true, true});
    entries.append({station, QStringLiteral("Thème appliqué"), m_appearance->activeTheme(), true,
                    false});
    entries.append({station, QStringLiteral("Thème système détecté"),
                    m_appearance->systemThemeLabel(),
                    m_appearance->systemThemeLabel() != unknownValue(), false});
    entries.append({station, QStringLiteral("Profil de mouvement"),
                    m_appearance->activeMotionProfile(), true, false});
    entries.append({station, QStringLiteral("Préférence système de mouvement réduit"),
                    QStringLiteral("Non lisible par Qt sur ce système"), false, false});

    // --- Connexion ----------------------------------------------------------
    const QString baseUrl = m_client->baseUrl().toString();
    entries.append({connection, QStringLiteral("Adresse du serveur"),
                    baseUrl.isEmpty() ? QStringLiteral("Non configuré") : baseUrl,
                    !baseUrl.isEmpty(), true});
    entries.append({connection, QStringLiteral("Bouclage en clair autorisé"),
                    m_client->allowsInsecureLoopback() ? QStringLiteral("Oui")
                                                       : QStringLiteral("Non"),
                    true, false});
    entries.append({connection, QStringLiteral("Proxy système"),
                    m_client->usesSystemProxy() ? QStringLiteral("Oui") : QStringLiteral("Non"),
                    true, false});
    entries.append({connection, QStringLiteral("État du lien"), m_health->linkStatusLabel(),
                    m_health->linkStatus() != LinkStatus::Unknown, false});
    entries.append({connection, QStringLiteral("Dernier échange réussi"),
                    m_health->lastSuccessLabel(), m_health->lastSuccessAt().isValid(), true});
    entries.append({connection, QStringLiteral("Détail du lien"),
                    m_health->detail().isEmpty() ? QStringLiteral("Aucun") : m_health->detail(),
                    true, false});
    entries.append({connection, QStringLiteral("Appels en vol"),
                    QString::number(m_client->inFlightCount()), true, true});

    // --- Compatibilité ------------------------------------------------------
    entries.append({connection, QStringLiteral("Compatibilité"), m_compatibility->stateLabel(),
                    m_compatibility->state() != CompatibilityStatus::NotChecked, false});
    entries.append({connection, QStringLiteral("Point d'entrée de compatibilité"),
                    m_compatibility->endpointUsed().isEmpty()
                        ? QStringLiteral("Aucun")
                        : m_compatibility->endpointUsed(),
                    !m_compatibility->endpointUsed().isEmpty(), true});
    entries.append({connection, QStringLiteral("Version du serveur"),
                    m_compatibility->serverVersion().isEmpty() ? unknownValue()
                                                               : m_compatibility->serverVersion(),
                    !m_compatibility->serverVersion().isEmpty(), true});
    entries.append({connection, QStringLiteral("Version de contrat d'API"),
                    m_compatibility->apiContractVersion().isEmpty()
                        ? unknownValue()
                        : m_compatibility->apiContractVersion(),
                    !m_compatibility->apiContractVersion().isEmpty(), true});
    entries.append({connection, QStringLiteral("Schéma d'événement"),
                    m_compatibility->eventSchemaVersion().isEmpty()
                        ? unknownValue()
                        : m_compatibility->eventSchemaVersion(),
                    !m_compatibility->eventSchemaVersion().isEmpty(), true});

    // --- Session ------------------------------------------------------------
    entries.append({session, QStringLiteral("État"), m_auth->stateLabel(), true, false});
    entries.append({session, QStringLiteral("Utilisateur"),
                    m_auth->userDisplayName().isEmpty() ? unknownValue()
                                                        : m_auth->userDisplayName(),
                    !m_auth->userDisplayName().isEmpty(), false});
    entries.append({session, QStringLiteral("Rôle plateforme"),
                    m_auth->platformRole().isEmpty() ? unknownValue() : m_auth->platformRole(),
                    !m_auth->platformRole().isEmpty(), true});
    entries.append({session, QStringLiteral("Expiration"),
                    m_auth->expiresAt().isValid()
                        ? m_auth->expiresAt().toLocalTime().toString(
                              QStringLiteral("dd/MM/yyyy HH:mm:ss"))
                        : unknownValue(),
                    m_auth->expiresAt().isValid(), true});
    entries.append({session, QStringLiteral("Jeton CSRF détenu"),
                    m_client->hasCsrfToken() ? QStringLiteral("Oui") : QStringLiteral("Non"),
                    true, false});
    entries.append({session, QStringLiteral("Cookies détenus"),
                    QString::number(m_client->cookieJar()->cookieCount()), true, true});

    // --- Flux ---------------------------------------------------------------
    const StreamLimits &limits = m_compatibility->streamLimits();
    const bool announced = m_compatibility->limitsAreAnnounced();
    entries.append({streams, QStringLiteral("Abonnements actifs"),
                    QStringLiteral("%1 / %2")
                        .arg(m_streams->activeCount())
                        .arg(m_streams->maxConnections()),
                    true, true});
    entries.append({streams, QStringLiteral("Origine des bornes"),
                    announced ? QStringLiteral("Annoncées par le serveur")
                              : QStringLiteral("Valeurs relevées lors de l'audit, non annoncées"),
                    announced, false});
    entries.append({streams, QStringLiteral("Keep-alive annoncé"),
                    QStringLiteral("%1 s").arg(limits.keepAliveSeconds), announced, true});
    entries.append({streams, QStringLiteral("Durée maximale d'un flux"),
                    QStringLiteral("%1 s").arg(limits.maxStreamSeconds), announced, true});
    entries.append({streams, QStringLiteral("Dernier refus du multiplexeur"),
                    m_streams->lastRefusal().isEmpty() ? QStringLiteral("Aucun")
                                                       : m_streams->lastRefusal(),
                    true, false});

    // --- Stockage -----------------------------------------------------------
    entries.append({storage, QStringLiteral("Coffre de secrets"), m_vault->backendName(), true,
                    false});
    entries.append({storage, QStringLiteral("Le coffre peut stocker"),
                    m_vault->canStore() ? QStringLiteral("Oui")
                                        : QStringLiteral("Non — le stockage est refusé"),
                    true, false});
    entries.append({storage, QStringLiteral("Préférences (aucun secret)"), m_settings->location(),
                    true, true});

    // --- Preuve -------------------------------------------------------------
    // Cette section existe pour que la station ne se présente jamais comme plus éprouvée
    // qu'elle ne l'est. Elle est aussi vraie en production que sur un poste de dévelop-
    // pement, et elle est écrite ici plutôt que promise dans un document.
    entries.append({proof, QStringLiteral("Flux de portée projet"),
                    QStringLiteral("Cette station en est le premier consommateur applicatif ; "
                                   "jamais éprouvé en réel"),
                    false, false});
    entries.append({proof, QStringLiteral("Reprise après coupure réseau réelle"),
                    QStringLiteral("Jamais éprouvée : seuls des minuteurs injectés l'ont été"),
                    false, false});
    entries.append({proof, QStringLiteral("Déploiement hébergé"),
                    QStringLiteral("Aucun déploiement n'a jamais eu lieu"), false, false});

    beginResetModel();
    m_entries = entries;
    endResetModel();
}

QString DiagnosticsViewModel::buildReport() const
{
    QStringList lines;
    QString currentSection;
    for (const Entry &entry : m_entries) {
        if (entry.section != currentSection) {
            currentSection = entry.section;
            lines.append(QString());
            lines.append(QStringLiteral("== %1 ==").arg(currentSection));
        }
        lines.append(QStringLiteral("%1 : %2").arg(entry.label, entry.value));
    }
    // Expurgation intégrale : un rapport de diagnostic est exactement le fichier par
    // lequel un jeton signé finit par fuir.
    return redactSecrets(lines.join(QLatin1Char('\n')).trimmed());
}

} // namespace acp
