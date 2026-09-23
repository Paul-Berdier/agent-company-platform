#include "services/CompatibilityService.h"

#include "api/ApiClient.h"

#include <QJsonObject>
#include <QJsonValue>
#include <QStringList>

namespace acp {

const QStringList &CompatibilityService::candidateEndpoints()
{
    // Ordre de sondage. Le nom définitif appartient au lot qui livrera la route ;
    // sonder évite de figer une supposition dans un binaire installé sur un poste.
    static const QStringList endpoints = {
        QStringLiteral("/meta"),
        QStringLiteral("/capabilities"),
        QStringLiteral("/version"),
    };
    return endpoints;
}

const QStringList &CompatibilityService::supportedEventSchemaVersions()
{
    // EVENT_SCHEMA_VERSION vaut « 1.0 » dans packages/contracts à la date de l'audit.
    static const QStringList versions = {QStringLiteral("1.0")};
    return versions;
}

CompatibilityService::CompatibilityService(ApiClient *client, QString clientVersion,
                                           QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_clientVersion(std::move(clientVersion))
{
}

QString CompatibilityService::stateLabel() const
{
    switch (m_state) {
    case CompatibilityStatus::NotChecked:
        return QStringLiteral("Non vérifié");
    case CompatibilityStatus::Checking:
        return QStringLiteral("Vérification en cours");
    case CompatibilityStatus::Compatible:
        return QStringLiteral("Compatible");
    case CompatibilityStatus::ClientTooOld:
        return QStringLiteral("Client trop ancien");
    case CompatibilityStatus::ServerTooOld:
        return QStringLiteral("Serveur trop ancien");
    case CompatibilityStatus::FeatureUnavailable:
        return QStringLiteral("Compatibilité non vérifiable");
    case CompatibilityStatus::Unreachable:
        return QStringLiteral("Serveur injoignable");
    }
    return QStringLiteral("Inconnu");
}

bool CompatibilityService::isBlocking() const
{
    return m_state == CompatibilityStatus::ClientTooOld
        || m_state == CompatibilityStatus::ServerTooOld;
}

void CompatibilityService::setState(CompatibilityStatus::State state, const QString &explanation)
{
    if (m_state == state && m_explanation == explanation) {
        return;
    }
    m_state = state;
    m_explanation = explanation;
    emit stateChanged();
}

void CompatibilityService::check()
{
    if (!m_client->isConfigured()) {
        setState(CompatibilityStatus::NotChecked,
                 QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }
    m_endpointUsed.clear();
    setState(CompatibilityStatus::Checking, QString());
    probe(0);
}

void CompatibilityService::probe(int candidateIndex)
{
    if (candidateIndex >= candidateEndpoints().size()) {
        setState(CompatibilityStatus::FeatureUnavailable,
                 QStringLiteral(
                     "Ce serveur n'expose aucun point d'entrée de compatibilité (%1). La "
                     "station continue de fonctionner, mais elle ne peut ni garantir que "
                     "son contrat correspond, ni connaître les bornes réelles du serveur : "
                     "les valeurs relevées lors de l'audit sont utilisées par défaut.")
                     .arg(candidateEndpoints().join(QStringLiteral(", "))));
        return;
    }

    const QString path = candidateEndpoints().at(candidateIndex);
    ApiRequest request;
    request.method = QByteArrayLiteral("GET");
    request.path = path;
    // La question « ce point d'entrée doit-il être public ? » est ouverte (audit,
    // question 7). L'appel n'exige donc rien : s'il répond 401, c'est qu'il est
    // authentifié, et la vérification sera refaite après l'ouverture de session.
    request.publicEndpoint = true;
    request.clientAnnouncement = QByteArrayLiteral("desktop/") + m_clientVersion.toUtf8();

    ApiCall *call = m_client->send(request);
    connect(call, &ApiCall::succeeded, this, [this, path](const ApiResponse &response) {
        if (!response.json.isObject()) {
            setState(CompatibilityStatus::FeatureUnavailable,
                     QStringLiteral("%1 a répondu, mais son corps n'est pas un objet JSON.")
                         .arg(path));
            return;
        }
        evaluate(response.json.object(), path);
    });
    connect(call, &ApiCall::failed, this, [this, candidateIndex, path](const ApiError &error) {
        if (error.kind() == ApiFailure::NotFound) {
            probe(candidateIndex + 1);
            return;
        }
        if (error.httpStatus() == 426) {
            // Verdict du serveur, qui connaît sa propre règle d'ordre des versions : il
            // l'emporte sur toute comparaison locale.
            const QString detail = extractProblemDetail(error.body());
            m_endpointUsed = path;
            setState(CompatibilityStatus::ClientTooOld,
                     detail.isEmpty()
                         ? QStringLiteral("Ce serveur refuse la version %1 de la station. "
                                          "Mettez la station à jour avant de poursuivre.")
                               .arg(m_clientVersion)
                         : detail);
            return;
        }
        if (error.kind() == ApiFailure::Unauthorized) {
            setState(CompatibilityStatus::FeatureUnavailable,
                     QStringLiteral("%1 exige une session : la compatibilité ne pourra être "
                                    "vérifiée qu'après connexion.")
                         .arg(path));
            return;
        }
        if (error.kind() == ApiFailure::Network || error.kind() == ApiFailure::Timeout) {
            setState(CompatibilityStatus::Unreachable, error.message());
            return;
        }
        setState(CompatibilityStatus::FeatureUnavailable, error.message());
    });
}

void CompatibilityService::evaluate(const QJsonObject &payload, const QString &endpoint)
{
    m_endpointUsed = endpoint;
    const QJsonObject versions = payload.value(QStringLiteral("versions")).toObject();
    m_serverVersion = versions.value(QStringLiteral("product")).toString();
    m_apiContractVersion = versions.value(QStringLiteral("api_contract")).toString();
    m_eventSchemaVersion = versions.value(QStringLiteral("event_schema")).toString();

    if (m_apiContractVersion.isEmpty()) {
        // La route existe mais ne porte pas le contrat attendu : on le dit précisément,
        // au lieu de conclure à la compatibilité par absence de contradiction.
        setState(CompatibilityStatus::FeatureUnavailable,
                 QStringLiteral("%1 a répondu, mais sans champ « versions.api_contract » : la "
                                "compatibilité ne peut pas être établie.")
                     .arg(endpoint));
        return;
    }

    // --- Contrat d'API ---------------------------------------------------------
    bool majorRead = false;
    const int contractMajor =
        m_apiContractVersion.section(QLatin1Char('.'), 0, 0).toInt(&majorRead);
    if (!majorRead) {
        setState(CompatibilityStatus::FeatureUnavailable,
                 QStringLiteral("%1 annonce un contrat d'API illisible (« %2 ») : la "
                                "compatibilité ne peut pas être établie.")
                     .arg(endpoint, m_apiContractVersion));
        return;
    }
    if (contractMajor > supportedApiContractMajor) {
        setState(CompatibilityStatus::ClientTooOld,
                 QStringLiteral("Le serveur publie le contrat d'API %1 ; cette station ne sait "
                                "lire que la version %2.x. Mettez la station à jour.")
                     .arg(m_apiContractVersion)
                     .arg(supportedApiContractMajor));
        return;
    }
    if (contractMajor < supportedApiContractMajor) {
        setState(CompatibilityStatus::ServerTooOld,
                 QStringLiteral("Le serveur publie le contrat d'API %1 ; cette station exige "
                                "la version %2.x.")
                     .arg(m_apiContractVersion)
                     .arg(supportedApiContractMajor));
        return;
    }

    // --- Bornes annoncées ---------------------------------------------------
    const QJsonObject limits = payload.value(QStringLiteral("limits")).toObject();
    if (!limits.isEmpty()) {
        auto readLimit = [&limits](const char *name, int fallback) {
            const QJsonValue value = limits.value(QLatin1String(name));
            return value.isDouble() ? static_cast<int>(value.toDouble()) : fallback;
        };
        m_limits.maxConnectionsPerUser =
            readLimit("stream_max_connections_per_user", m_limits.maxConnectionsPerUser);
        m_limits.keepAliveSeconds =
            readLimit("stream_keepalive_seconds", m_limits.keepAliveSeconds);
        m_limits.maxStreamSeconds = readLimit("stream_max_seconds", m_limits.maxStreamSeconds);
        m_limits.pollIntervalMilliseconds =
            readLimit("stream_poll_interval_ms", m_limits.pollIntervalMilliseconds);
        // Le rattrapage du journal demande la plus grande page admise par le serveur.
        m_limits.pageLimit = readLimit("event_page_max_limit", m_limits.pageLimit);
        m_limitsAnnounced = true;
    }

    // --- Capacités calculées ------------------------------------------------
    m_capabilities = payload.value(QStringLiteral("capabilities")).toObject();
    m_capabilitiesKnown = !m_capabilities.isEmpty();

    // --- Version cliente minimale -------------------------------------------
    const QJsonObject desktopRequirement = payload.value(QStringLiteral("clients"))
                                               .toObject()
                                               .value(QStringLiteral("desktop"))
                                               .toObject();
    const QString minimumDesktop =
        desktopRequirement.value(QStringLiteral("minimum_version")).toString();
    if (!minimumDesktop.isEmpty() && compareVersions(m_clientVersion, minimumDesktop) < 0) {
        setState(CompatibilityStatus::ClientTooOld,
                 QStringLiteral("Ce serveur exige au minimum la version %1 de la station ; "
                                "celle-ci est en version %2. Mettez la station à jour avant "
                                "de poursuivre.")
                     .arg(minimumDesktop, m_clientVersion));
        return;
    }

    // --- Schéma d'événement --------------------------------------------------
    if (!m_eventSchemaVersion.isEmpty()
        && !supportedEventSchemaVersions().contains(m_eventSchemaVersion)) {
        setState(CompatibilityStatus::ServerTooOld,
                 QStringLiteral("Le serveur transporte un schéma d'événement en version %1 ; "
                                "cette station sait lire %2. Le journal ne serait pas rendu "
                                "fidèlement.")
                     .arg(m_eventSchemaVersion,
                          supportedEventSchemaVersions().join(QStringLiteral(", "))));
        return;
    }

    setState(CompatibilityStatus::Compatible,
             QStringLiteral("Contrat d'API %1, schéma d'événement %2.")
                 .arg(m_apiContractVersion,
                      m_eventSchemaVersion.isEmpty() ? QStringLiteral("inconnu")
                                                     : m_eventSchemaVersion));
}

bool CompatibilityService::capability(const QString &name, bool *known) const
{
    // Chaque capacité est un objet { available, detail } : seul un booléen explicite
    // vaut réponse, toute autre forme reste « Inconnu ».
    const QJsonValue value =
        m_capabilities.value(name).toObject().value(QStringLiteral("available"));
    const bool isKnown = m_capabilitiesKnown && value.isBool();
    if (known) {
        *known = isKnown;
    }
    return isKnown && value.toBool();
}

bool CompatibilityService::capabilityIsKnown(const QString &name) const
{
    return m_capabilitiesKnown
        && m_capabilities.value(name).toObject().value(QStringLiteral("available")).isBool();
}

int CompatibilityService::compareVersions(const QString &left, const QString &right)
{
    const QStringList leftParts = left.split(QLatin1Char('.'));
    const QStringList rightParts = right.split(QLatin1Char('.'));
    const int count = qMax(leftParts.size(), rightParts.size());
    for (int index = 0; index < count; ++index) {
        bool leftOk = false;
        bool rightOk = false;
        const int leftValue =
            index < leftParts.size() ? leftParts.at(index).toInt(&leftOk) : 0;
        const int rightValue =
            index < rightParts.size() ? rightParts.at(index).toInt(&rightOk) : 0;
        // Un segment non numérique (suffixe de pré-publication) vaut zéro : la fonction
        // n'implémente pas SemVer et ne prétend pas ordonner ces suffixes.
        const int leftNumber = leftOk ? leftValue : 0;
        const int rightNumber = rightOk ? rightValue : 0;
        if (leftNumber != rightNumber) {
            return leftNumber < rightNumber ? -1 : 1;
        }
    }
    return 0;
}

} // namespace acp
