#include "viewmodels/DiagnosticsViewModel.h"

#include "api/ApiClient.h"
#include "app/BuildConfig.h"
#include "auth/SessionHermes.h"
#include "diagnostics/Redaction.h"
#include "events/EventStreamService.h"
#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"
#include "services/CompatibiliteHermes.h"
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

DiagnosticsViewModel::DiagnosticsViewModel(ApiClient *client, SessionHermes *session,
                                           CompatibiliteHermes *compatibilite,
                                           GatewayClient *passerelle,
                                           HealthService *health,
                                           SettingsStore *settings,
                                           SystemAppearance *appearance, CredentialVault *vault,
                                           QString clientVersion, QString buildInfo,
                                           QObject *parent)
    : QAbstractListModel(parent)
    , m_client(client)
    , m_session(session)
    , m_compatibilite(compatibilite)
    , m_passerelle(passerelle)
    , m_health(health)
    , m_settings(settings)
    , m_appearance(appearance)
    , m_vault(vault)
    , m_clientVersion(std::move(clientVersion))
    , m_buildInfo(std::move(buildInfo))
{
    connect(m_health, &HealthService::changed, this, &DiagnosticsViewModel::refresh);
    connect(m_client, &ApiClient::baseUrlChanged, this, &DiagnosticsViewModel::refresh);
    connect(m_session, &SessionHermes::etatChange, this, &DiagnosticsViewModel::refresh);
    connect(m_session, &SessionHermes::identiteChange, this, &DiagnosticsViewModel::refresh);
    connect(m_session, &SessionHermes::avisCoffreChange, this, &DiagnosticsViewModel::refresh);
    connect(m_session, &SessionHermes::memoriserChange, this, &DiagnosticsViewModel::refresh);
    connect(m_compatibilite, &CompatibiliteHermes::change, this, &DiagnosticsViewModel::refresh);
    connect(m_passerelle, &GatewayClient::etatChange, this, &DiagnosticsViewModel::refresh);
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
    const QString session = QStringLiteral("Session");
    const QString compatibility = QStringLiteral("Compatibilité");
    const QString gateway = QStringLiteral("Passerelle JSON-RPC");

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
    entries.append({connection, QStringLiteral("Passerelle de Hermes"), m_health->gatewayLabel(),
                    m_health->gatewayLabel() != unknownValue(), false});
    entries.append({connection, QStringLiteral("Sessions actives sur Hermes"),
                    m_health->activeSessionsLabel(), m_health->activeSessionsLabel() != unknownValue(),
                    true});
    entries.append({connection, QStringLiteral("Appels en vol"),
                    QString::number(m_client->inFlightCount()), true, true});

    // --- Session ------------------------------------------------------------
    // Aucune valeur de jeton n'apparaît ici, seulement des faits sur la session.
    entries.append({session, QStringLiteral("État"), m_session->libelleEtat(), true, false});
    entries.append({session, QStringLiteral("Dernière erreur"),
                    m_session->derniereErreur().isEmpty() ? QStringLiteral("Aucune")
                                                          : m_session->derniereErreur(),
                    true, false});
    entries.append({session, QStringLiteral("Identité"), m_session->identifiant(),
                    m_session->identifiant() != unknownValue(), true});
    entries.append({session, QStringLiteral("Nom affiché"), m_session->nomAffiche(),
                    m_session->nomAffiche() != unknownValue(), false});
    entries.append({session, QStringLiteral("Fournisseur d'identité"), m_session->fournisseur(),
                    m_session->fournisseur() != unknownValue(), true});
    entries.append({session, QStringLiteral("Échéance du jeton d'accès"), m_session->expiration(),
                    m_session->expiration() != unknownValue(), true});
    entries.append({session, QStringLiteral("Connexion mémorisée sur ce poste"),
                    m_session->memoriser() ? QStringLiteral("Oui (consentement donné)")
                                           : QStringLiteral("Non"),
                    true, false});
    entries.append({session, QStringLiteral("Entrée au coffre pour ce serveur"),
                    m_session->entreeAuCoffre() ? QStringLiteral("Présente (valeur jamais affichée)")
                                                : QStringLiteral("Absente"),
                    true, false});
    entries.append({session, QStringLiteral("Avis du coffre"),
                    m_session->avisCoffre().isEmpty() ? QStringLiteral("Aucun") : m_session->avisCoffre(),
                    true, false});
    entries.append({session, QStringLiteral("Dernière déconnexion"),
                    m_session->bilanDeconnexion().isEmpty() ? QStringLiteral("Aucune")
                                                            : m_session->bilanDeconnexion(),
                    true, false});

    // --- Compatibilité ------------------------------------------------------
    entries.append({compatibility, QStringLiteral("Verdict"), m_compatibilite->libelle(),
                    m_compatibilite->etat() != CompatibilityStatus::NonVerifiee, false});
    entries.append({compatibility, QStringLiteral("Explication"),
                    m_compatibilite->explication().isEmpty() ? QStringLiteral("Aucune")
                                                             : m_compatibilite->explication(),
                    true, false});
    entries.append({compatibility, QStringLiteral("Hermes servi"), m_compatibilite->versionHermes(),
                    m_compatibilite->versionHermes() != unknownValue(), true});
    entries.append({compatibility, QStringLiteral("Contrat du greffon"), m_compatibilite->contratRecu(),
                    m_compatibilite->contratRecu() != unknownValue(), true});
    entries.append({compatibility, QStringLiteral("Contrat attendu"),
                    QString::fromLatin1(ACP_CONTRAT_ACP_POSTE), true, true});
    entries.append({compatibility, QStringLiteral("Version du greffon"), m_compatibilite->versionGreffon(),
                    m_compatibilite->versionGreffon() != unknownValue(), true});
    entries.append({compatibility, QStringLiteral("Empreinte OpenRPC servie"),
                    m_compatibilite->empreinteOpenRpc(),
                    m_compatibilite->empreinteOpenRpc() != unknownValue(), true});
    entries.append({compatibility, QStringLiteral("Empreinte OpenRPC épinglée"),
                    QString::fromLatin1(ACP_OPENRPC_SHA256), true, true});
    entries.append({compatibility, QStringLiteral("Exécutant Railway (P6)"),
                    m_compatibilite->etat() == CompatibilityStatus::NonVerifiee
                        ? unknownValue()
                        : (m_compatibilite->executantPresent() ? QStringLiteral("Annoncé par Hermes")
                                                               : QStringLiteral("Non disponible sur ce serveur")),
                    m_compatibilite->etat() != CompatibilityStatus::NonVerifiee, false});
    const QStringList alertes = m_compatibilite->alertes();
    entries.append({compatibility, QStringLiteral("Alertes de Hermes"),
                    QString::number(alertes.size()),
                    m_compatibilite->etat() != CompatibilityStatus::NonVerifiee, true});
    for (const QString &alerte : alertes) {
        entries.append({compatibility, QStringLiteral("Alerte"), alerte, true, false});
    }

    // --- Passerelle ---------------------------------------------------------
    entries.append({gateway, QStringLiteral("État"), m_passerelle->libelleEtat(), true, false});
    entries.append({gateway, QStringLiteral("Raison"),
                    m_passerelle->raison().isEmpty() ? QStringLiteral("Aucune") : m_passerelle->raison(),
                    true, false});
    entries.append({gateway, QStringLiteral("Sous-protocole retenu"),
                    m_passerelle->sousProtocoleRetenu().isEmpty() ? unknownValue()
                                                                  : m_passerelle->sousProtocoleRetenu(),
                    !m_passerelle->sousProtocoleRetenu().isEmpty(), true});
    entries.append({gateway, QStringLiteral("Époque de rejeu"),
                    m_passerelle->epoque().isEmpty() ? unknownValue() : m_passerelle->epoque(),
                    !m_passerelle->epoque().isEmpty(), true});
    entries.append({gateway, QStringLiteral("Dernier signe de vie"), m_passerelle->dernierSigneDeVie(),
                    m_passerelle->dernierSigneDeVie() != QStringLiteral("Jamais"), true});
    entries.append({gateway, QStringLiteral("Reconnexions"), QString::number(m_passerelle->reconnexions()),
                    true, true});
    entries.append({gateway, QStringLiteral("Requêtes de l'agent refusées (-32601)"),
                    QString::number(m_passerelle->canal()->methodesRefusees()), true, true});
    entries.append({gateway, QStringLiteral("Trames illisibles ignorées"),
                    QString::number(m_passerelle->canal()->tramesIllisibles()), true, true});

    // --- Temps réel --------------------------------------------------------
    if (m_flux) {
        const QString temps = QStringLiteral("Temps réel");
        entries.append({temps, QStringLiteral("Passerelle JSON-RPC"), m_flux->etatPasserelle(), true, false});
        entries.append({temps, QStringLiteral("Veille du kanban"), m_flux->etatVeille(), true, false});
        entries.append({temps, QStringLiteral("Sondage de /v1/projets"), m_flux->etatSondage(), true, false});
        entries.append({temps, QStringLiteral("Flux d'événements du greffon"), EventStreamService::etatFluxGreffon(),
                        false, false});
    }

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

void DiagnosticsViewModel::setFlux(EventStreamService *flux)
{
    m_flux = flux;
    if (m_flux) {
        connect(m_flux, &EventStreamService::sourcesChange, this, &DiagnosticsViewModel::refresh);
    }
    refresh();
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
