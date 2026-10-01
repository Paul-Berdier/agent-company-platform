#include "viewmodels/DiagnosticsViewModel.h"

#include "api/ApiClient.h"
#include "app/BuildConfig.h"
#include "diagnostics/Redaction.h"
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

DiagnosticsViewModel::DiagnosticsViewModel(ApiClient *client, HealthService *health,
                                           SettingsStore *settings,
                                           SystemAppearance *appearance, CredentialVault *vault,
                                           QString clientVersion, QString buildInfo,
                                           QObject *parent)
    : QAbstractListModel(parent)
    , m_client(client)
    , m_health(health)
    , m_settings(settings)
    , m_appearance(appearance)
    , m_vault(vault)
    , m_clientVersion(std::move(clientVersion))
    , m_buildInfo(std::move(buildInfo))
{
    connect(m_health, &HealthService::changed, this, &DiagnosticsViewModel::refresh);
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
    const QString storage = QStringLiteral("Stockage local");

    // --- Station ------------------------------------------------------------
    entries.append({station, QStringLiteral("Version de la station"), m_clientVersion, true, true});
    entries.append({station, QStringLiteral("Informations de construction"), m_buildInfo, true, true});
    entries.append({station, QStringLiteral("Hermes testé par cette station"),
                    QString::fromLatin1(ACP_HERMES_VERSION), true, true});
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
    entries.append({connection, QStringLiteral("Version de Hermes annoncée"),
                    m_health->hermesVersion(), m_health->hermesVersion() != unknownValue(), true});
    entries.append({connection, QStringLiteral("Appels en vol"),
                    QString::number(m_client->inFlightCount()), true, true});

    // --- Stockage -----------------------------------------------------------
    entries.append({storage, QStringLiteral("Coffre de secrets"), m_vault->backendName(), true,
                    false});
    entries.append({storage, QStringLiteral("Le coffre peut stocker"),
                    m_vault->canStore() ? QStringLiteral("Oui")
                                        : QStringLiteral("Non — le stockage est refusé"),
                    true, false});
    entries.append({storage, QStringLiteral("Préférences (aucun secret)"), m_settings->location(),
                    true, true});

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
