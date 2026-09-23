#include "viewmodels/OperationsViewModel.h"
#include "api/IdempotencyKey.h"
#include "auth/AuthManager.h"
#include "diagnostics/Redaction.h"
#include <QRegularExpression>
#include <QSet>
#include <cmath>
#include <utility>

namespace acp {
namespace {
QString text(const QJsonObject& object, const char* key) { return object.value(QLatin1String(key)).toString(); }
bool integer(const QJsonValue& value, int lower, int upper)
{
    const double number = value.toDouble(-1);
    return value.isDouble() && std::isfinite(number) && number >= lower && number <= upper
        && std::floor(number) == number;
}
bool validPolicy(const QJsonObject& policy, const QString& project)
{
    return text(policy, "project_id") == project && !text(policy, "timezone").isEmpty()
        && (policy.value(QStringLiteral("daily_budget")).isNull() || policy.value(QStringLiteral("daily_budget")).isObject())
        && policy.value(QStringLiteral("provider_budgets")).isArray()
        && integer(policy.value(QStringLiteral("max_concurrent_missions")), 1, 100)
        && integer(policy.value(QStringLiteral("max_retries_per_mission")), 0, 20)
        && integer(policy.value(QStringLiteral("max_spawned_agents_per_run")), 1, 32);
}
}

OperationsViewModel::OperationsViewModel(ApiClient* client, AuthManager* auth, QObject* parent)
    : QObject(parent), m_client(client), m_auth(auth)
{
    connect(client, &ApiClient::baseUrlChanged, this, [this] { invalidate(); });
    connect(auth, &AuthManager::stateChanged, this, [this] {
        const auto state = m_auth->state();
        if (state == SessionStatus::Disconnected || state == SessionStatus::Expired
            || state == SessionStatus::Revoked) invalidate();
        else emit changed();
    });
    connect(auth, &AuthManager::userChanged, this, [this] { invalidate(); if (ready()) load(); });
    connect(auth, &AuthManager::sessionEstablished, this, &OperationsViewModel::refresh);
}
OperationsViewModel::~OperationsViewModel()
{
    ++m_generation;
    for (const auto& call : std::as_const(m_calls)) if (call) {
        disconnect(call, nullptr, this, nullptr); call->abort();
    }
}
bool OperationsViewModel::ready() const
{
    return !m_projectId.isEmpty() && m_client->isConfigured() && m_auth->state() == SessionStatus::Connected;
}
bool OperationsViewModel::canManage() const { return ready() && m_manage && !busy() && !m_mutating; }
bool OperationsViewModel::canDecide() const { return ready() && m_decide && !busy() && !m_mutating; }
QString OperationsViewModel::segment(const QString& id) { return QString::fromLatin1(QUrl::toPercentEncoding(id)); }
bool OperationsViewModel::contains(const JsonListModel& model, const QString& id)
{
    for (int i = 0; i < model.count(); ++i) if (model.get(i).value(QStringLiteral("id")).toString() == id) return true;
    return false;
}
void OperationsViewModel::fail(const QString& message) { m_error = redactSecrets(message); emit changed(); }
void OperationsViewModel::invalidate(bool clearKeys)
{
    ++m_generation; ++m_selection;
    const auto calls = m_calls;
    m_calls.clear();
    for (const auto& call : calls) if (call) call->abort();
    m_pending = 0; m_mutating = false; m_manage = false; m_decide = false;
    m_approvals.clear(); m_alerts.clear(); m_automations.clear(); m_runs.clear();
    m_policy = {}; m_usage = {}; m_automation = {}; m_memberships = {};
    m_workspaceId.clear(); m_statuses.clear(); m_error.clear(); m_notice.clear();
    if (clearKeys) m_mutationKeys.clear();
    emit contextReset(); emit changed();
}
void OperationsViewModel::setProjectId(const QString& id)
{
    if (id == m_projectId) return;
    m_projectId = id; invalidate(); if (ready()) load();
}
void OperationsViewModel::refresh()
{
    if (m_mutating) return;
    invalidate(false); if (ready()) load();
}
void OperationsViewModel::request(ApiRequest request, const QString& section, Success success)
{
    const quint64 generation = m_generation;
    ++m_pending;
    if (!section.isEmpty()) m_statuses[section] = QStringLiteral("Chargement…");
    ApiCall* call = m_client->send(request);
    m_calls.append(call);
    connect(call, &ApiCall::succeeded, this, [this, call, generation, success](const ApiResponse& response) {
        if (generation != m_generation) return;
        m_calls.removeAll(call); --m_pending;
        success(response); emit changed();
    });
    connect(call, &ApiCall::failed, this, [this, call, generation, section](const ApiError& error) {
        if (generation != m_generation) return;
        m_calls.removeAll(call); --m_pending;
        const QString message = redactSecrets(error.message());
        if (error.httpStatus() == 403 || error.httpStatus() == 401) invalidate();
        if (section == QLatin1String("action")) m_mutating = false;
        if (!section.isEmpty()) m_statuses[section] = message;
        fail(message);
    });
    emit changed();
}
void OperationsViewModel::load()
{
    permissions();
    loadList(QStringLiteral("/approvals"), QStringLiteral("approvals"), &m_approvals);
    loadList(QStringLiteral("/alerts"), QStringLiteral("alerts"), &m_alerts, 200);
    loadList(QStringLiteral("/automations"), QStringLiteral("automations"), &m_automations, 500);
    ApiRequest policy; policy.path = QStringLiteral("/projects/%1/budget-policy").arg(segment(m_projectId));
    request(policy, QStringLiteral("policy"), [this](const ApiResponse& response) {
        const auto body = response.json.object();
        if (!response.json.isObject() || !validPolicy(body, m_projectId)) {
            m_statuses[QStringLiteral("policy")] = QStringLiteral("Politique indisponible : réponse invalide.");
            return;
        }
        m_policy = body; m_statuses[QStringLiteral("policy")] = QStringLiteral("Politique lue sur le serveur.");
    });
    ApiRequest usage; usage.path = QStringLiteral("/projects/%1/budget-usage").arg(segment(m_projectId));
    request(usage, QStringLiteral("usage"), [this](const ApiResponse& response) {
        const auto body = response.json.object();
        if (!response.json.isObject() || text(body, "project_id") != m_projectId
            || !body.value(QStringLiteral("totals")).isObject()) {
            m_statuses[QStringLiteral("usage")] = QStringLiteral("Consommation indisponible : réponse invalide."); return;
        }
        m_usage = body; m_statuses[QStringLiteral("usage")] = QStringLiteral("Consommation du %1 (%2)")
            .arg(text(body, "accounting_day"), text(body, "timezone"));
    });
}
void OperationsViewModel::loadList(const QString& path, const QString& section, JsonListModel* model, int limit)
{
    ApiRequest req; req.path = path;
    req.query.addQueryItem(QStringLiteral("project_id"), m_projectId);
    if (section == QLatin1String("approvals")) req.query.addQueryItem(QStringLiteral("status"), QStringLiteral("WAITING_APPROVAL"));
    if (section == QLatin1String("alerts")) req.query.addQueryItem(QStringLiteral("open"), QStringLiteral("true"));
    if (limit) req.query.addQueryItem(QStringLiteral("limit"), QString::number(limit));
    request(req, section, [this, section, model, limit](const ApiResponse& response) {
        bool valid = response.json.isArray();
        const auto rows = response.json.array();
        QSet<QString> seen;
        for (const auto& value : rows) {
            const auto row = value.toObject(); const QString id = text(row, "id");
            valid = valid && value.isObject() && !id.isEmpty() && !seen.contains(id)
                && text(row, "project_id") == m_projectId;
            if (section == QLatin1String("approvals")) valid = valid && text(row, "status") == QLatin1String("WAITING_APPROVAL");
            if (section == QLatin1String("alerts")) valid = valid && row.value(QStringLiteral("acknowledged_at")).isNull();
            if (section == QLatin1String("automations")) valid = valid && row.value(QStringLiteral("enabled")).isBool();
            seen.insert(id);
        }
        if (!valid || (limit && rows.size() > limit)) {
            m_statuses[section] = QStringLiteral("Liste indisponible : réponse invalide."); return;
        }
        model->setItems(rows);
        m_statuses[section] = rows.isEmpty() ? QStringLiteral("Aucun élément retourné par l’API.")
            : QStringLiteral("%1 élément(s)%2").arg(rows.size()).arg(limit && rows.size() == limit
                ? QStringLiteral(" — limite de lecture atteinte") : QString());
    });
}
void OperationsViewModel::permissions()
{
    m_manage = m_decide = m_auth->platformRole() == QLatin1String("owner");
    if (m_manage) return;
    ApiRequest memberships; memberships.path = QStringLiteral("/memberships");
    memberships.query.addQueryItem(QStringLiteral("user_id"), m_auth->userId());
    request(memberships, {}, [this](const ApiResponse& response) {
        if (response.json.isArray()) m_memberships = response.json.array(); updatePermissions();
    });
    ApiRequest projects; projects.path = QStringLiteral("/projects");
    request(projects, {}, [this](const ApiResponse& response) {
        for (const auto& row : response.json.array())
            if (text(row.toObject(), "id") == m_projectId) m_workspaceId = text(row.toObject(), "workspace_id");
        updatePermissions();
    });
}
void OperationsViewModel::updatePermissions()
{
    m_manage = m_decide = false;
    for (const auto& value : m_memberships) {
        const auto row = value.toObject(); const QString role = text(row, "role");
        const bool scoped = (text(row, "scope_type") == QLatin1String("project") && text(row, "scope_id") == m_projectId)
            || (!m_workspaceId.isEmpty() && text(row, "scope_type") == QLatin1String("workspace") && text(row, "scope_id") == m_workspaceId);
        if (!scoped || text(row, "user_id") != m_auth->userId()) continue;
        if (role == QLatin1String("owner")) m_decide = true;
        if (role == QLatin1String("owner") || role == QLatin1String("operator") || role == QLatin1String("member")) m_manage = true;
    }
}
void OperationsViewModel::mutate(ApiRequest req, Verify verify, const QString& notice)
{
    m_mutating = true; m_error.clear(); m_notice.clear();
    // Seules les routes automations reconnaissent une clé de rejeu.
    QByteArray signature;
    if (req.path.startsWith(QLatin1String("/automations/")) || req.path.endsWith(QLatin1String("/automations"))) {
        signature = req.method + '\n' + req.path.toUtf8() + '\n' + req.body.toJson(QJsonDocument::Compact);
        if (!m_mutationKeys.contains(signature)) m_mutationKeys.insert(signature, makeIdempotencyKey(QStringLiteral("operation")));
        req.idempotencyKey = m_mutationKeys.value(signature);
    }
    request(req, QStringLiteral("action"), [this, verify, notice, signature](const ApiResponse& response) {
        m_mutating = false;
        if (!response.json.isObject() || !verify(response.json.object())) {
            fail(QStringLiteral("Résultat non confirmé par le serveur. Actualisez avant toute nouvelle décision.")); return;
        }
        m_mutationKeys.remove(signature);
        invalidate(false); m_notice = notice; if (ready()) load();
    });
}
void OperationsViewModel::decideApproval(const QString& id, const QString& decision, const QString& comment)
{
    if (!canDecide() || !contains(m_approvals, id)) { fail(QStringLiteral("Décision indisponible : droits owner et demande en attente requis.")); return; }
    if ((decision != QLatin1String("APPROVED") && decision != QLatin1String("REJECTED")) || comment.size() > 2000) {
        fail(QStringLiteral("Décision ou commentaire invalide (2 000 caractères maximum).")); return;
    }
    ApiRequest req; req.method = "POST"; req.path = QStringLiteral("/approvals/%1/decision").arg(segment(id));
    req.body = QJsonDocument(QJsonObject{{QStringLiteral("decision"), decision}, {QStringLiteral("comment"), comment}});
    const QString project = m_projectId;
    mutate(req, [id, project, decision](const QJsonObject& row) {
        return text(row, "id") == id && text(row, "project_id") == project && text(row, "status") == decision;
    }, QStringLiteral("Décision enregistrée par le serveur."));
}
void OperationsViewModel::acknowledgeAlert(const QString& id, const QString& comment)
{
    if (!canManage() || !contains(m_alerts, id)) { fail(QStringLiteral("Acquittement indisponible : droits member requis.")); return; }
    if (comment.size() > 500) { fail(QStringLiteral("Le commentaire d’alerte est limité à 500 caractères.")); return; }
    ApiRequest req; req.method = "POST"; req.path = QStringLiteral("/alerts/%1/acknowledge").arg(segment(id));
    req.body = QJsonDocument(QJsonObject{{QStringLiteral("comment"), comment.trimmed()}});
    const QString project = m_projectId;
    mutate(req, [id, project](const QJsonObject& row) {
        return text(row, "id") == id && text(row, "project_id") == project && !text(row, "acknowledged_at").isEmpty();
    }, QStringLiteral("Alerte acquittée."));
}
void OperationsViewModel::saveBudgetPolicy(int maxConcurrent, int maxRetries, int maxAgents)
{
    if (!canManage() || !validPolicy(m_policy, m_projectId)) { fail(QStringLiteral("Une politique lue et les droits member sont requis.")); return; }
    if (maxConcurrent < 1 || maxConcurrent > 100 || maxRetries < 0 || maxRetries > 20 || maxAgents < 1 || maxAgents > 32) {
        fail(QStringLiteral("Bornes invalides : concurrence 1–100, relances 0–20, agents 1–32.")); return;
    }
    QJsonObject body = m_policy;
    body.remove(QStringLiteral("project_id")); body.remove(QStringLiteral("updated_at"));
    body[QStringLiteral("max_concurrent_missions")] = maxConcurrent;
    body[QStringLiteral("max_retries_per_mission")] = maxRetries;
    body[QStringLiteral("max_spawned_agents_per_run")] = maxAgents;
    ApiRequest req; req.method = "PUT"; req.path = QStringLiteral("/projects/%1/budget-policy").arg(segment(m_projectId));
    req.body = QJsonDocument(body);
    const QString project = m_projectId;
    mutate(req, [project, body](const QJsonObject& row) {
        if (!validPolicy(row, project)) return false;
        for (auto i = body.begin(); i != body.end(); ++i) if (row.value(i.key()) != i.value()) return false;
        return true;
    }, QStringLiteral("Politique enregistrée ; plafonds journaliers et fournisseurs conservés."));
}
void OperationsViewModel::createAutomation(const QVariantMap& form)
{
    if (!canManage()) { fail(QStringLiteral("Création indisponible : droits member requis.")); return; }
    const auto field = [&form](const char* key) { return form.value(QLatin1String(key)).toString().trimmed(); };
    const QString name = field("name"), objective = field("objective"), expected = field("expectedOutcome");
    const QString kind = field("scheduleKind"), timezone = field("timezone");
    QString expression = field("expression");
    QJsonArray criteria;
    for (const QString& line : field("criteria").split(QLatin1Char('\n'))) if (!line.trimmed().isEmpty() && !criteria.contains(line.trimmed())) criteria.append(line.trimmed());
    bool durationOk = false, toolsOk = false;
    const int duration = field("durationSeconds").toInt(&durationOk), tools = field("maxToolCalls").toInt(&toolsOk);
    if (name.isEmpty() || name.size() > 200 || objective.isEmpty() || objective.size() > 10000
        || expected.isEmpty() || expected.size() > 10000 || criteria.isEmpty() || criteria.size() > 100
        || timezone.isEmpty() || timezone.size() > 64 || !durationOk || duration < 1 || duration > 31536000
        || !toolsOk || tools < 0 || (kind != QLatin1String("interval") && kind != QLatin1String("cron"))) {
        fail(QStringLiteral("Complétez le nom, l’objectif, le résultat, les critères, le fuseau et les limites entières.")); return;
    }
    if (kind == QLatin1String("interval")) {
        bool ok = false; const int minutes = expression.toInt(&ok);
        if (!ok || minutes < 1 || minutes > 525600) { fail(QStringLiteral("Intervalle attendu : 1 à 525 600 minutes.")); return; }
        expression = QString::number(minutes * 60);
    } else if (expression.isEmpty() || expression.size() > 200) { fail(QStringLiteral("Expression cron requise (cinq champs).")); return; }
    QJsonObject mission{{QStringLiteral("title"), name}, {QStringLiteral("objective"), objective}, {QStringLiteral("expected_outcome"), expected},
        {QStringLiteral("acceptance_criteria"), criteria}, {QStringLiteral("duration_seconds"), duration}, {QStringLiteral("priority"), 3},
        {QStringLiteral("resources"), QJsonArray{}}, {QStringLiteral("required_capabilities"), QJsonArray{}}, {QStringLiteral("team_id"), QJsonValue::Null},
        {QStringLiteral("agent_instance_id"), QJsonValue::Null},
        {QStringLiteral("autonomy"), QJsonObject{{QStringLiteral("mode"), QStringLiteral("supervised")}, {QStringLiteral("allowed_actions"), QJsonArray{}},
                                {QStringLiteral("forbidden_actions"), QJsonArray{}}, {QStringLiteral("approval_required_actions"), QJsonArray{}}}},
        {QStringLiteral("budget"), QJsonObject{{QStringLiteral("max_cost"), QJsonValue::Null}, {QStringLiteral("currency"), QStringLiteral("EUR")},
                              {QStringLiteral("max_tokens"), QJsonValue::Null}, {QStringLiteral("max_tool_calls"), tools}}}};
    const QJsonObject schedule{{QStringLiteral("kind"), kind}, {QStringLiteral("expression"), expression}, {QStringLiteral("timezone"), timezone}};
    QJsonObject body{{QStringLiteral("name"), name}, {QStringLiteral("description"), QStringLiteral("")}, {QStringLiteral("mission_template"), mission},
                     {QStringLiteral("schedule"), schedule}, {QStringLiteral("catchup_policy"), QStringLiteral("skip")}, {QStringLiteral("max_concurrent_runs"), 1}};
    ApiRequest req; req.method = "POST"; req.path = QStringLiteral("/projects/%1/automations").arg(segment(m_projectId));
    req.body = QJsonDocument(body);
    const QString project = m_projectId;
    mutate(req, [project, name, schedule, mission](const QJsonObject& row) {
        return !text(row, "id").isEmpty() && text(row, "project_id") == project && text(row, "name") == name
            && row.value(QStringLiteral("enabled")).isBool() && !row.value(QStringLiteral("enabled")).toBool()
            && row.value(QStringLiteral("schedule")).toObject() == schedule
            && row.value(QStringLiteral("mission_template")).toObject() == mission;
    }, QStringLiteral("Automation créée en pause. Son activation reste une action explicite."));
}
void OperationsViewModel::selectAutomation(const QString& id)
{
    if (!ready() || m_mutating || !contains(m_automations, id)) return;
    const quint64 selection = ++m_selection;
    m_runs.clear(); m_automation = {};
    for (int i = 0; i < m_automations.count(); ++i) {
        const auto row = m_automations.get(i);
        if (row.value(QStringLiteral("id")).toString() == id) m_automation = QJsonObject::fromVariantMap(row);
    }
    ApiRequest req; req.path = QStringLiteral("/automations/%1/runs").arg(segment(id));
    req.query.addQueryItem(QStringLiteral("limit"), QStringLiteral("20"));
    request(req, QStringLiteral("runs"), [this, selection, id](const ApiResponse& response) {
        if (selection != m_selection) return;
        bool valid = response.json.isArray() && response.json.array().size() <= 20;
        for (const auto& row : response.json.array()) valid = valid && row.isObject()
            && !text(row.toObject(), "id").isEmpty() && text(row.toObject(), "automation_id") == id;
        if (!valid) { m_statuses[QStringLiteral("runs")] = QStringLiteral("Historique indisponible : réponse invalide."); return; }
        m_runs.setItems(response.json.array());
        m_statuses[QStringLiteral("runs")] = m_runs.count() == 0 ? QStringLiteral("Aucune exécution retournée.") : QStringLiteral("20 dernières exécutions au maximum.");
    });
}
void OperationsViewModel::setAutomationEnabled(const QString& id, bool enabled)
{
    if (!canManage() || !contains(m_automations, id)) { fail(QStringLiteral("Activation indisponible : droits member requis.")); return; }
    ApiRequest req; req.method = "POST";
    req.path = QStringLiteral("/automations/%1/%2").arg(segment(id), enabled ? QStringLiteral("enable") : QStringLiteral("disable"));
    const QString project = m_projectId;
    mutate(req, [id, project, enabled](const QJsonObject& row) {
        return text(row, "id") == id && text(row, "project_id") == project
            && row.value(QStringLiteral("enabled")).isBool() && row.value(QStringLiteral("enabled")).toBool() == enabled;
    }, enabled ? QStringLiteral("Automation activée.") : QStringLiteral("Automation mise en pause."));
}
QString OperationsViewModel::describe(const QVariant& value) const
{
    return redactSecrets(QString::fromUtf8(QJsonDocument::fromVariant(value).toJson(QJsonDocument::Indented)));
}
} // namespace acp
