#include "viewmodels/PlatformViewModel.h"

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "auth/AuthManager.h"
#include "models/JsonListModel.h"

#include <QUrl>

namespace acp {
namespace {
QString part(const QString &id) { return QString::fromLatin1(QUrl::toPercentEncoding(id)); }
QString field(const QJsonObject &object, const char *key)
{
    return object.value(QLatin1String(key)).toString();
}
QJsonObject publicFields(const QJsonObject &object, const QList<QByteArray> &fields)
{
    QJsonObject result;
    for (const auto &key : fields) {
        const QString name = QString::fromLatin1(key);
        if (object.contains(name)) {
            result.insert(name, object.value(name));
        }
    }
    return result;
}
const QList<QByteArray> extensionFields{"id", "name", "display_name", "description", "status",
    "current_revision_number", "kind", "category", "transport", "discovery_current", "requires_approval"};

bool validDetail(const QJsonObject &object, const QString &id)
{
    return field(object, "id") == id && !id.isEmpty()
        && object.value(QStringLiteral("name")).isString()
        && object.value(QStringLiteral("status")).isString()
        && object.value(QStringLiteral("revisions")).isArray()
        && object.value(QStringLiteral("bindings")).isArray()
        && (object.value(QStringLiteral("current_revision")).isObject()
            || object.value(QStringLiteral("current_revision")).isNull());
}
} // namespace

PlatformViewModel::PlatformViewModel(ApiClient *client, AuthManager *auth, QObject *parent)
    : QObject(parent), m_client(client), m_auth(auth), m_agents(new JsonListModel(this)),
      m_workers(new JsonListModel(this)), m_providers(new JsonListModel(this)),
      m_mcpServers(new JsonListModel(this)), m_skills(new JsonListModel(this)),
      m_mcpTools(new JsonListModel(this))
{
    connect(m_auth, &AuthManager::stateChanged, this, &PlatformViewModel::updateSession);
    connect(m_auth, &AuthManager::userChanged, this, &PlatformViewModel::updateSession);
    connect(m_client, &ApiClient::baseUrlChanged, this, [this] {
        m_sessionOrigin.clear();
        invalidate();
    });
    updateSession();
}
PlatformViewModel::~PlatformViewModel() { invalidate(); }
QObject *PlatformViewModel::agents() const { return m_agents; }
QObject *PlatformViewModel::workers() const { return m_workers; }
QObject *PlatformViewModel::providers() const { return m_providers; }
QObject *PlatformViewModel::mcpServers() const { return m_mcpServers; }
QObject *PlatformViewModel::skills() const { return m_skills; }
QObject *PlatformViewModel::mcpTools() const { return m_mcpTools; }
QVariantMap PlatformViewModel::selectedMcp() const { return selected(m_mcp); }
QVariantMap PlatformViewModel::selectedSkill() const { return selected(m_skill); }

bool PlatformViewModel::available() const
{
    return m_auth->state() == SessionStatus::Connected && !m_sessionUser.isEmpty()
        && m_sessionOrigin == m_client->baseUrl().toString();
}
bool PlatformViewModel::isOwner() const
{
    return available() && m_auth->platformRole() == QLatin1String("owner");
}
bool PlatformViewModel::canManageProjectBindings() const
{
    if (!available() || m_projectId.isEmpty()) { return false; }
    if (isOwner()) { return true; }
    if (!m_membershipsKnown || !m_projectKnown) { return false; }
    for (const auto &value : m_memberships) {
        const auto membership = value.toObject();
        const QString role = field(membership, "role");
        const QString scope = field(membership, "scope_type");
        const QString id = field(membership, "scope_id");
        if (field(membership, "user_id") == m_sessionUser
            && (role == QLatin1String("member") || role == QLatin1String("operator") || role == QLatin1String("owner"))
            && ((scope == QLatin1String("project") && id == m_projectId)
                || (scope == QLatin1String("workspace") && id == m_workspaceId))) { return true; }
    }
    return false;
}
QString PlatformViewModel::bindingPermissionReason() const
{
    if (!available()) { return QStringLiteral("Connectez-vous pour gérer les liaisons du projet."); }
    if (m_projectId.isEmpty()) { return QStringLiteral("Sélectionnez un projet pour gérer ses extensions."); }
    if (canManageProjectBindings()) { return {}; }
    if (!m_membershipsKnown || !m_projectKnown) {
        return QStringLiteral("Droits du projet non confirmés ; attendez le chargement ou actualisez.");
    }
    return QStringLiteral("Rôle membre, opérateur ou propriétaire requis sur ce projet ou son espace de travail.");
}
void PlatformViewModel::invalidate()
{
    ++m_generation;
    ++m_mcpSelection;
    ++m_skillSelection;
    m_pending = 0;
    m_busy = false;
    const auto calls = m_calls;
    m_calls.clear();
    for (const auto &call : calls) {
        if (call) { call->abort(); }
    }
    for (auto *model : {m_agents, m_workers, m_providers, m_mcpServers, m_skills, m_mcpTools}) {
        model->clear();
    }
    m_workerData = {};
    m_workersKnown = false;
    m_memberships = {};
    m_membershipsKnown = false;
    m_projectKnown = false;
    m_workspaceId.clear();
    m_hermes = {};
    m_mcp = {};
    m_skill = {};
    m_mcpId.clear();
    m_skillId.clear();
    m_chosenTools.clear();
    m_error.clear();
    m_notice.clear();
    m_workersNotice.clear();
    emit changed();
}
void PlatformViewModel::updateSession()
{
    const auto state = m_auth->state();
    const bool knownIdentity = !m_sessionUser.isEmpty() && m_auth->userId() == m_sessionUser
        && m_auth->platformRole() == m_sessionRole
        && m_sessionOrigin == m_client->baseUrl().toString();
    if ((state == SessionStatus::Connecting || state == SessionStatus::Offline) && knownIdentity) {
        // Conserver seulement une identité déjà confirmée ; userChanged arrive
        // avant Connected pendant une première connexion.
        emit changed();
        return;
    }
    const bool connected = state == SessionStatus::Connected;
    const QString user = connected ? m_auth->userId() : QString();
    const QString role = connected ? m_auth->platformRole() : QString();
    const QString origin = connected ? m_client->baseUrl().toString() : QString();
    if (m_sessionUser == user && m_sessionRole == role && m_sessionOrigin == origin) { emit changed(); return; }
    invalidate();
    m_sessionUser = user;
    m_sessionRole = role;
    m_sessionOrigin = origin;
    emit changed();
    if (m_active && available()) { refresh(); }
}
void PlatformViewModel::setProjectId(const QString &id)
{
    if (m_projectId == id) { return; }
    invalidate();
    m_projectId = id;
    emit changed();
    if (m_active && available()) { refresh(); }
}
void PlatformViewModel::setActive(bool activeValue)
{
    if (m_active == activeValue) { return; }
    m_active = activeValue;
    if (m_active) { refresh(); } else { invalidate(); }
    emit changed();
}
void PlatformViewModel::refuse(const QString &message)
{
    m_error = message;
    emit changed();
}
bool PlatformViewModel::permit(bool owner, bool project)
{
    if (!m_active || !available()) {
        refuse(QStringLiteral("Connectez-vous à cette API pour continuer."));
        return false;
    }
    if (m_busy || loading()) {
        refuse(QStringLiteral("Attendez la fin de l'opération en cours."));
        return false;
    }
    if (owner && !isOwner()) {
        refuse(QStringLiteral("Cette opération est réservée au propriétaire de la plateforme."));
        return false;
    }
    if (project && !canManageProjectBindings()) {
        refuse(bindingPermissionReason());
        return false;
    }
    return true;
}
void PlatformViewModel::request(const ApiRequest &requestValue, Success success, bool mutation)
{
    const quint64 generation = m_generation;
    ++m_pending;
    ApiCall *call = m_client->send(requestValue);
    m_calls.append(call);
    connect(call, &ApiCall::succeeded, this,
            [this, generation, call, success, mutation](const ApiResponse &response) {
        m_calls.removeAll(call);
        // Connecting suspend les nouvelles actions, sans invalider les réponses
        // du même utilisateur. Sinon un 403 perd son refus et laisse busy figé.
        if (generation != m_generation || !m_active || m_sessionUser.isEmpty()
            || m_auth->userId() != m_sessionUser || m_auth->platformRole() != m_sessionRole
            || m_sessionOrigin != m_client->baseUrl().toString()) { return; }
        --m_pending;
        if (mutation) { m_busy = false; }
        success(response);
        emit changed();
    });
    connect(call, &ApiCall::failed, this,
            [this, generation, call, mutation, path = requestValue.path](const ApiError &error) {
        m_calls.removeAll(call);
        if (generation != m_generation || !m_active || m_sessionUser.isEmpty()
            || m_auth->userId() != m_sessionUser || m_auth->platformRole() != m_sessionRole
            || m_sessionOrigin != m_client->baseUrl().toString()) { return; }
        --m_pending;
        if (mutation) { m_busy = false; }
        if (path == QLatin1String("/workers")) {
            m_workersNotice = error.message();
            m_workersKnown = false;
            rebuildProviders();
        } else {
            m_error = error.message();
            if (mutation && error.isRetryable()) {
                m_error += QStringLiteral(" Résultat incertain : actualisez avant de recommencer.");
            }
        }
        emit changed();
    });
    emit changed();
}
void PlatformViewModel::loadList(const QString &path, JsonListModel *model,
                                 const QList<QByteArray> &fields)
{
    ApiRequest req;
    req.path = path;
    request(req, [this, model, fields, path](const ApiResponse &response) {
        if (!response.json.isArray()) {
            refuse(QStringLiteral("Réponse de liste invalide : %1.").arg(path));
            return;
        }
        QJsonArray rows;
        QSet<QString> ids;
        for (const auto &value : response.json.array()) {
            const auto object = value.toObject();
            const QString id = field(object, "id");
            if (id.isEmpty() || ids.contains(id) || !object.value(QStringLiteral("name")).isString()
                || !object.value(QStringLiteral("status")).isString()) {
                refuse(QStringLiteral("Réponse de liste invalide : %1.").arg(path));
                return;
            }
            ids.insert(id);
            rows.append(publicFields(object, fields));
        }
        model->setItems(rows);
        if (model == m_workers) {
            m_workerData = rows;
            m_workersKnown = true;
            rebuildProviders();
        }
    });
}
void PlatformViewModel::refresh()
{
    if (!m_active || !available() || m_busy || loading()) { return; }
    const QString mcpId = m_mcpId;
    const QString skillId = m_skillId;
    invalidate();
    loadPermissions();
    rebuildProviders();
    loadList(QStringLiteral("/agents"), m_agents,
             {"id", "name", "status", "workspace_id", "team_id", "role_id", "module", "capabilities"});
    if (isOwner() || m_auth->platformRole() == QLatin1String("operator")) {
        loadList(QStringLiteral("/workers"), m_workers,
                 {"id", "name", "status", "capabilities", "max_concurrency", "active_runs",
                  "simulation", "project_id", "global_access", "last_seen_at", "lease_expires_at"});
    } else {
        m_workersNotice = QStringLiteral("La consultation des workers est réservée aux propriétaires et opérateurs.");
    }
    loadList(QStringLiteral("/mcp/servers"), m_mcpServers, extensionFields);
    loadList(QStringLiteral("/skills"), m_skills, extensionFields);
    ApiRequest req;
    req.path = QStringLiteral("/connections/hermes/diagnostic");
    request(req, [this](const ApiResponse &response) {
        const auto object = response.json.object();
        const QString status = field(object, "status");
        if ((status != QLatin1String("connected") && status != QLatin1String("degraded")
             && status != QLatin1String("unavailable"))
            || !object.value(QStringLiteral("healthy")).isBool()
            || !object.value(QStringLiteral("message")).isString()) {
            refuse(QStringLiteral("Diagnostic Hermes invalide : disponibilité inconnue."));
            return;
        }
        m_hermes = publicFields(object, {"status", "healthy", "message", "checked_at"});
        rebuildProviders();
    });
    if (!mcpId.isEmpty()) { selectMcp(mcpId); }
    if (!skillId.isEmpty()) { selectSkill(skillId); }
}
void PlatformViewModel::loadPermissions()
{
    if (isOwner() || m_projectId.isEmpty()) { return; }
    ApiRequest memberships;
    memberships.path = QStringLiteral("/memberships");
    memberships.query.addQueryItem(QStringLiteral("user_id"), m_sessionUser);
    request(memberships, [this](const ApiResponse &response) {
        if (!response.json.isArray()) {
            refuse(QStringLiteral("Appartenances illisibles : modification des liaisons refusée."));
            return;
        }
        for (const auto &value : response.json.array()) {
            const auto row = value.toObject();
            if (!row.value(QStringLiteral("user_id")).isString()
                || !row.value(QStringLiteral("scope_type")).isString()
                || !row.value(QStringLiteral("scope_id")).isString()
                || !row.value(QStringLiteral("role")).isString()) {
                refuse(QStringLiteral("Appartenance invalide : modification des liaisons refusée."));
                return;
            }
        }
        m_memberships = response.json.array();
        m_membershipsKnown = true;
    });
    ApiRequest projects;
    projects.path = QStringLiteral("/projects");
    request(projects, [this](const ApiResponse &response) {
        if (!response.json.isArray()) {
            refuse(QStringLiteral("Contexte du projet illisible : modification des liaisons refusée."));
            return;
        }
        for (const auto &value : response.json.array()) {
            const auto row = value.toObject();
            if (field(row, "id") == m_projectId && !field(row, "workspace_id").isEmpty()) {
                m_workspaceId = field(row, "workspace_id");
                m_projectKnown = true;
                return;
            }
        }
        refuse(QStringLiteral("Le projet n'est plus accessible ; modification des liaisons refusée."));
    });
}
void PlatformViewModel::rebuildProviders()
{
    QString hermes = QStringLiteral("Inconnu — diagnostic non reçu.");
    if (!m_hermes.isEmpty()) {
        const QString status = field(m_hermes, "status");
        hermes = status == QLatin1String("connected") ? QStringLiteral("Connecté")
            : status == QLatin1String("degraded") ? QStringLiteral("Dégradé") : QStringLiteral("Indisponible");
        hermes += QStringLiteral(" — ") + field(m_hermes, "message");
    }
    QJsonArray rows{QJsonObject{{QStringLiteral("id"), QStringLiteral("hermes")},
        {QStringLiteral("name"), QStringLiteral("Hermes")}, {QStringLiteral("state"), hermes},
        {QStringLiteral("checked_at"), m_hermes.value(QStringLiteral("checked_at"))}}};
    for (const auto &capability : {QStringLiteral("codex_cli"), QStringLiteral("claude_code")}) {
        QStringList reporters;
        for (const auto &value : m_workerData) {
            const auto worker = value.toObject();
            if (worker.value(QStringLiteral("capabilities")).toArray().contains(capability)) {
                reporters.append(field(worker, "name") + QStringLiteral(" (")
                                 + field(worker, "status") + QStringLiteral(")"));
            }
        }
        const QString state = !m_workersKnown ? QStringLiteral("Inconnu — workers non consultables.")
            : reporters.isEmpty() ? QStringLiteral("Aucun worker n'annonce cette capacité. Santé du fournisseur inconnue.")
            : QStringLiteral("Capacité annoncée : %1. Santé du fournisseur inconnue.").arg(reporters.join(QStringLiteral(", ")));
        rows.append(QJsonObject{{QStringLiteral("id"), capability},
            {QStringLiteral("name"), capability == QLatin1String("codex_cli") ? QStringLiteral("Codex") : QStringLiteral("Claude Code")},
            {QStringLiteral("state"), state}});
    }
    m_providers->setItems(rows);
}
QJsonObject PlatformViewModel::binding(const QJsonObject &detail) const
{
    if (m_projectId.isEmpty()) { return {}; }
    for (const auto &value : detail.value(QStringLiteral("bindings")).toArray()) {
        const auto row = value.toObject();
        if (field(row, "project_id") == m_projectId
            && (row.value(QStringLiteral("revoked_at")).isNull()
                || row.value(QStringLiteral("revoked_at")).isUndefined())) {
            return publicFields(row, {"id", "project_id", "revision_id", "revision_number", "allowed_tools", "enabled"});
        }
    }
    return {};
}
QVariantMap PlatformViewModel::selected(const QJsonObject &detail) const
{
    if (detail.isEmpty()) { return {}; }
    QJsonObject result = publicFields(detail, extensionFields);
    result.insert(QStringLiteral("binding"), binding(detail));
    QJsonArray versions;
    for (const auto &value : detail.value(QStringLiteral("revisions")).toArray()) {
        const auto revision = value.toObject();
        versions.append(publicFields(revision, {"number", "approved", "requires_approval", "discovery_current"}));
    }
    result.insert(QStringLiteral("versions"), versions);
    return result.toVariantMap();
}
void PlatformViewModel::selectMcp(const QString &id)
{
    if (!m_active || !available() || m_busy || id.isEmpty()) { return; }
    const quint64 selection = ++m_mcpSelection;
    m_mcp = {};
    m_mcpId = id;
    m_chosenTools.clear();
    m_mcpTools->clear();
    ApiRequest req;
    req.path = QStringLiteral("/mcp/servers/%1").arg(part(id));
    request(req, [this, id, selection](const ApiResponse &response) {
        if (selection != m_mcpSelection) { return; }
        if (!validDetail(response.json.object(), id)) {
            refuse(QStringLiteral("Détail du serveur MCP invalide."));
            return;
        }
        m_mcp = response.json.object();
        for (const auto &tool : binding(m_mcp).value(QStringLiteral("allowed_tools")).toArray()) {
            if (tool.isString()) { m_chosenTools.insert(tool.toString()); }
        }
        rebuildTools();
    });
}
void PlatformViewModel::selectSkill(const QString &id)
{
    if (!m_active || !available() || m_busy || id.isEmpty()) { return; }
    const quint64 selection = ++m_skillSelection;
    m_skill = {};
    m_skillId = id;
    ApiRequest req;
    req.path = QStringLiteral("/skills/%1").arg(part(id));
    request(req, [this, id, selection](const ApiResponse &response) {
        if (selection != m_skillSelection) { return; }
        if (!validDetail(response.json.object(), id)) {
            refuse(QStringLiteral("Détail de la compétence invalide."));
            return;
        }
        m_skill = response.json.object();
    });
}
void PlatformViewModel::rebuildTools()
{
    QJsonObject revision = m_mcp.value(QStringLiteral("current_revision")).toObject();
    const auto linked = binding(m_mcp);
    if (!linked.isEmpty()) {
        revision = {};
        for (const auto &value : m_mcp.value(QStringLiteral("revisions")).toArray()) {
            if (field(value.toObject(), "id") == field(linked, "revision_id")) {
                revision = value.toObject();
                break;
            }
        }
    }
    QJsonArray rows;
    for (const auto &value : revision.value(QStringLiteral("discovery")).toObject()
                                      .value(QStringLiteral("tools")).toArray()) {
        const auto tool = value.toObject();
        const QString name = field(tool, "name");
        if (!name.isEmpty()) {
            auto row = publicFields(tool, {"name", "description"});
            row.insert(QStringLiteral("selected"), m_chosenTools.contains(name));
            rows.append(row);
        }
    }
    m_mcpTools->setItems(rows);
    emit changed();
}
void PlatformViewModel::toggleTool(const QString &name, bool selectedValue)
{
    if (m_busy || loading() || !canManageProjectBindings()) { return; }
    for (int i = 0; i < m_mcpTools->count(); ++i) {
        if (m_mcpTools->get(i).value(QStringLiteral("name")).toString() == name) {
            if (selectedValue) { m_chosenTools.insert(name); } else { m_chosenTools.remove(name); }
            rebuildTools();
            return;
        }
    }
}
void PlatformViewModel::mutate(const QByteArray &method, const QString &path,
                               const QJsonObject &body, const QString &expectedId, bool detail, bool mcp)
{
    m_error.clear();
    m_notice.clear();
    m_busy = true;
    ApiRequest req;
    req.method = method;
    req.path = path;
    req.body = QJsonDocument(body);
    // Pas de réessai automatique : ces routes ne promettent pas d'idempotence.
    request(req, [this, expectedId, detail, mcp](const ApiResponse &response) {
        const auto object = response.json.object();
        const bool valid = detail ? validDetail(object, expectedId)
            : !field(object, "id").isEmpty() && field(object, "project_id") == m_projectId
                && field(object, mcp ? "server_id" : "skill_id") == expectedId;
        if (!valid) {
            refuse(QStringLiteral("Réponse de modification invalide. Actualisez pour vérifier l'état serveur."));
            return;
        }
        refresh();
        m_notice = QStringLiteral("Modification confirmée par le serveur.");
    }, true);
}
void PlatformViewModel::saveMcpBinding()
{
    if (!permit(false, true) || m_mcp.isEmpty()) { return; }
    if (m_chosenTools.isEmpty()) {
        refuse(QStringLiteral("Sélectionnez au moins un outil autorisé."));
        return;
    }
    const auto linked = binding(m_mcp);
    QStringList tools = m_chosenTools.values();
    tools.sort();
    QJsonObject body{{QStringLiteral("allowed_tools"), QJsonArray::fromStringList(tools)}};
    if (linked.isEmpty()) {
        body.insert(QStringLiteral("project_id"), m_projectId);
        mutate("POST", QStringLiteral("/mcp/servers/%1/bindings").arg(part(m_mcpId)), body, m_mcpId, false, true);
    } else {
        mutate("PATCH", QStringLiteral("/mcp/bindings/%1").arg(part(field(linked, "id"))), body, m_mcpId, false, true);
    }
}
void PlatformViewModel::setMcpBindingEnabled(bool enabled)
{
    if (!permit(false, true)) { return; }
    const auto linked = binding(m_mcp);
    if (linked.isEmpty()) { refuse(QStringLiteral("Ce serveur n'est pas lié au projet.")); return; }
    mutate("PATCH", QStringLiteral("/mcp/bindings/%1").arg(part(field(linked, "id"))),
           {{QStringLiteral("enabled"), enabled}}, m_mcpId, false, true);
}
void PlatformViewModel::removeMcpBinding()
{
    if (!permit(false, true)) { return; }
    const auto linked = binding(m_mcp);
    if (linked.isEmpty()) { return; }
    mutate("DELETE", QStringLiteral("/mcp/bindings/%1").arg(part(field(linked, "id"))), {}, m_mcpId, false, true);
}
void PlatformViewModel::bindSkill()
{
    if (!permit(false, true) || m_skill.isEmpty()) { return; }
    mutate("POST", QStringLiteral("/skills/%1/bindings").arg(part(m_skillId)),
           {{QStringLiteral("project_id"), m_projectId}}, m_skillId, false, false);
}
void PlatformViewModel::removeSkillBinding()
{
    if (!permit(false, true)) { return; }
    const auto linked = binding(m_skill);
    if (linked.isEmpty()) { return; }
    mutate("DELETE", QStringLiteral("/skills/bindings/%1").arg(part(field(linked, "id"))), {}, m_skillId, false, false);
}
void PlatformViewModel::setMcpActive(bool activeValue)
{
    if (!permit(true) || m_mcp.isEmpty()) { return; }
    mutate("POST", QStringLiteral("/mcp/servers/%1/%2").arg(part(m_mcpId),
        activeValue ? QStringLiteral("activate") : QStringLiteral("disable")), {}, m_mcpId, true, true);
}
void PlatformViewModel::setSkillActive(bool activeValue)
{
    if (!permit(true) || m_skill.isEmpty()) { return; }
    mutate("POST", QStringLiteral("/skills/%1/%2").arg(part(m_skillId),
        activeValue ? QStringLiteral("activate") : QStringLiteral("disable")), {}, m_skillId, true, false);
}
} // namespace acp
