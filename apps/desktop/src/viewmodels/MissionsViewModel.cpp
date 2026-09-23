#include "viewmodels/MissionsViewModel.h"

#include "api/ApiClient.h"
#include "api/IdempotencyKey.h"
#include "auth/AuthManager.h"
#include "diagnostics/Redaction.h"
#include "events/EventStreamService.h"

#include <QJsonDocument>
#include <QRegularExpression>
#include <QUrl>
#include <cmath>

namespace acp {
namespace {
QString text(const QJsonObject& object, const char* name)
{
    return object.value(QLatin1String(name)).toString();
}
QJsonArray lines(const QString& input)
{
    QJsonArray result;
    QSet<QString> seen;
    for (const QString& raw : input.split(QLatin1Char('\n'))) {
        const QString line = raw.trimmed();
        if (!line.isEmpty() && !seen.contains(line)) {
            result.append(line);
            seen.insert(line);
        }
    }
    return result;
}
}

MissionsViewModel::MissionsViewModel(ApiClient* client, AuthManager* auth,
                                   EventStreamService* streams, QObject* parent)
    : QObject(parent), m_client(client), m_auth(auth), m_streams(streams)
{
    m_refreshTimer.setSingleShot(true);
    m_refreshTimer.setInterval(700);
    connect(&m_refreshTimer, &QTimer::timeout, this, &MissionsViewModel::refreshDetail);
    connect(client, &ApiClient::baseUrlChanged, this, [this] { reset(); });
    connect(auth, &AuthManager::stateChanged, this, &MissionsViewModel::syncSession);
    connect(auth, &AuthManager::userChanged, this, &MissionsViewModel::syncSession);
    m_sessionUser = auth->userId();
}

MissionsViewModel::~MissionsViewModel()
{
    ++m_generation;
    const auto calls = m_calls;
    m_calls.clear();
    for (const auto &call : calls) if (call) call->abort();
    closeStream();
}

void MissionsViewModel::syncSession()
{
    // Une rotation CSRF et une coupure réseau ne changent pas l'identité. La commande
    // incertaine reste disponible pour un rejeu explicite après la reconnexion.
    const QString user = m_auth->userId();
    if (user != m_sessionUser || user.isEmpty()
        || m_auth->state() == SessionStatus::Expired || m_auth->state() == SessionStatus::Revoked) {
        reset();
        m_sessionUser = user;
    }
    if (ready()) refresh();
    else closeStream();
    emit changed();
}

bool MissionsViewModel::ready() const
{
    return m_client->isConfigured() && m_auth->state() == SessionStatus::Connected
        && !m_projectId.isEmpty();
}
bool MissionsViewModel::canWrite() const { return ready() && m_writeAllowed && !m_mutating && !pendingMutation(); }
bool MissionsViewModel::canRetryPending() const
{
    return ready() && m_writeAllowed && !m_mutating && m_pendingMutation
        && !m_pendingMutation->idempotencyKey.isEmpty();
}
bool MissionsViewModel::isCurrentRun() const
{
    return !selectedRunId().isEmpty()
        && selectedRunId() == text(m_mission.value(QStringLiteral("current_run")).toObject(), "id");
}
bool MissionsViewModel::canStop() const
{
    const QString status = text(m_run, "status");
    return canWrite() && isCurrentRun() && (status == QLatin1String("queued")
        || status == QLatin1String("preparing") || status == QLatin1String("running")
        || status == QLatin1String("waiting_approval"));
}
bool MissionsViewModel::retryAllowed(const QJsonObject& run)
{
    const QString status = text(run, "status");
    return status == QLatin1String("blocked") || status == QLatin1String("failed")
        || status == QLatin1String("cancelled") || status == QLatin1String("interrupted")
        || (status == QLatin1String("succeeded")
            && text(run.value(QStringLiteral("user_acceptance")).toObject(), "status")
                == QLatin1String("rejected"));
}
bool MissionsViewModel::acceptanceAllowed(const QJsonObject& run)
{
    const QString acceptance = text(run.value(QStringLiteral("user_acceptance")).toObject(), "status");
    return text(run, "status") == QLatin1String("succeeded")
        && text(run.value(QStringLiteral("technical_validation")).toObject(), "status")
            == QLatin1String("passed")
        && (acceptance.isEmpty() || acceptance == QLatin1String("pending"));
}
bool MissionsViewModel::canRetry() const { return canWrite() && isCurrentRun() && retryAllowed(m_run); }
bool MissionsViewModel::canAccept() const { return canWrite() && acceptanceAllowed(m_run); }
QString MissionsViewModel::streamStatus() const
{
    if (m_subscription) return m_subscription->statusLabel()
        + (m_subscription->journalHasGaps() ? QStringLiteral(" — journal incomplet") : QString{});
    return m_streamError.isEmpty() ? QStringLiteral("Aucune tentative suivie") : m_streamError;
}
QString MissionsViewModel::segment(const QString& value)
{
    return QString::fromLatin1(QUrl::toPercentEncoding(value));
}
void MissionsViewModel::fail(const QString& message)
{
    m_error = redactSecrets(message);
    emit changed();
}
void MissionsViewModel::closeStream()
{
    m_refreshTimer.stop();
    if (m_subscription) {
        const QString key = m_subscription->key();
        disconnect(m_subscription, nullptr, this, nullptr);
        m_subscription = nullptr;
        m_streams->unsubscribe(key);
    }
}
void MissionsViewModel::clearSelection()
{
    ++m_selection;
    ++m_detailRequest;
    closeStream();
    m_missionId.clear(); m_mission = {}; m_run = {}; m_testReport = {};
    m_runs.clear(); m_comments.clear(); m_events.clear(); m_evidence.clear(); m_testCases.clear();
    m_eventRows = {}; m_eventIds.clear(); m_testsStatus.clear(); m_streamError.clear();
}
void MissionsViewModel::reset()
{
    ++m_generation;
    const auto calls = m_calls;
    m_calls.clear();
    for (const auto &call : calls) if (call) call->abort();
    clearPendingMutation();
    clearSelection();
    m_missions.clear(); m_memberships = {}; m_workspaceId.clear();
    m_pending = 0; m_mutating = false; m_writeAllowed = false;
    m_error.clear(); m_notice.clear();
    emit contextReset();
    emit changed();
}
void MissionsViewModel::setProjectId(const QString& id)
{
    if (id == m_projectId) return;
    reset(); m_projectId = id; emit changed(); refresh();
}
void MissionsViewModel::request(ApiRequest req, Success success, Failure failure)
{
    const quint64 generation = m_generation;
    ++m_pending; emit changed();
    ApiCall* call = m_client->send(req);
    m_calls.append(call);
    connect(call, &ApiCall::succeeded, this,
        [this, generation, call, success](const ApiResponse& response) {
            m_calls.removeAll(call);
            if (generation != m_generation) return;
            --m_pending; success(response); emit changed();
        });
    connect(call, &ApiCall::failed, this,
        [this, generation, call, failure](const ApiError& error) {
            m_calls.removeAll(call);
            if (generation != m_generation) return;
            --m_pending;
            if (failure) failure(error); else fail(error.message());
            emit changed();
        });
}
void MissionsViewModel::refresh()
{
    if (!ready()) return;
    m_error.clear();
    loadPermissions();
    const quint64 serial = ++m_listRequest;
    ApiRequest req; req.path = QStringLiteral("/missions");
    req.query.addQueryItem(QStringLiteral("project_id"), m_projectId);
    req.query.addQueryItem(QStringLiteral("limit"), QStringLiteral("500"));
    request(req, [this, serial](const ApiResponse& response) {
        if (serial != m_listRequest) return;
        if (!response.json.isArray()) { fail(QStringLiteral("Liste de missions inexploitable.")); return; }
        QJsonArray items;
        for (const QJsonValue& value : response.json.array()) {
            const auto row = value.toObject();
            if (text(row, "project_id") != m_projectId || text(row, "id").isEmpty()) {
                fail(QStringLiteral("Une mission reçue ne correspond pas au projet sélectionné.")); return;
            }
            items.append(row);
        }
        m_missions.setItems(items);
    });
    if (!m_missionId.isEmpty()) refreshDetail();
}
void MissionsViewModel::loadPermissions()
{
    m_writeAllowed = m_auth->platformRole() == QLatin1String("owner");
    if (m_writeAllowed) { emit changed(); return; }
    ApiRequest req; req.path = QStringLiteral("/memberships");
    req.query.addQueryItem(QStringLiteral("user_id"), m_auth->userId());
    request(req, [this](const ApiResponse& response) {
        m_memberships = response.json.array(); updatePermissions();
    });
    ApiRequest projects; projects.path = QStringLiteral("/projects");
    request(projects, [this](const ApiResponse& response) {
        for (const auto& value : response.json.array())
            if (text(value.toObject(), "id") == m_projectId)
                m_workspaceId = text(value.toObject(), "workspace_id");
        updatePermissions();
    });
}
void MissionsViewModel::updatePermissions()
{
    m_writeAllowed = false;
    for (const auto& value : m_memberships) {
        const QJsonObject row = value.toObject();
        const QString role = text(row, "role");
        const bool scope = (text(row, "scope_type") == QLatin1String("project")
                            && text(row, "scope_id") == m_projectId)
            || (!m_workspaceId.isEmpty() && text(row, "scope_type") == QLatin1String("workspace")
                && text(row, "scope_id") == m_workspaceId);
        if (scope && text(row, "user_id") == m_auth->userId()
            && (role == QLatin1String("member") || role == QLatin1String("operator")
                || role == QLatin1String("owner"))) m_writeAllowed = true;
    }
    emit changed();
}
void MissionsViewModel::selectMission(const QString& id)
{
    if (!ready() || id.isEmpty()) return;
    if (pendingMutation()) {
        fail(QStringLiteral("Résolvez ou abandonnez explicitement la commande en attente avant de changer de mission."));
        return;
    }
    clearSelection(); m_error.clear(); m_notice.clear(); m_missionId = id;
    emit changed(); refreshDetail(); loadComments();
}
void MissionsViewModel::refreshDetail()
{
    if (!ready() || m_missionId.isEmpty()) return;
    const quint64 selection = m_selection, serial = ++m_detailRequest;
    ApiRequest req; req.path = QStringLiteral("/missions/") + segment(m_missionId);
    request(req, [this, selection, serial](const ApiResponse& response) {
        if (selection != m_selection || serial != m_detailRequest) return;
        const QJsonObject obj = response.json.object();
        if (text(obj, "id") != m_missionId || text(obj, "project_id") != m_projectId
            || !obj.value(QStringLiteral("runs")).isArray()) {
            fail(QStringLiteral("Détail de mission inexploitable ou hors du projet.")); return;
        }
        applyDetail(obj);
    }, [this, selection, serial](const ApiError& error) {
        if (selection == m_selection && serial == m_detailRequest) fail(error.message());
    });
}
void MissionsViewModel::applyDetail(const QJsonObject& object)
{
    const QString previous = selectedRunId();
    m_mission = object;
    m_runs.setItems(object.value(QStringLiteral("runs")).toArray());
    QString selected = text(object.value(QStringLiteral("current_run")).toObject(), "id");
    for (const auto& value : object.value(QStringLiteral("runs")).toArray())
        if (text(value.toObject(), "id") == previous) selected = previous;
    selectRun(selected);
    emit changed();
}
void MissionsViewModel::selectRun(const QString& id)
{
    QJsonObject selected;
    for (const auto& value : m_mission.value(QStringLiteral("runs")).toArray())
        if (text(value.toObject(), "id") == id) selected = value.toObject();
    if (selected.isEmpty()) return;
    const bool different = id != selectedRunId();
    if (different) {
        closeStream(); m_eventRows = {}; m_eventIds.clear(); m_events.clear();
        m_testReport = {}; m_testCases.clear();
    }
    m_run = selected;
    m_evidence.setItems(selected.value(QStringLiteral("evidence")).toArray());
    loadTests();
    if (different) {
        m_subscription = m_streams->subscribeRun(id);
        if (!m_subscription) m_streamError = m_streams->lastRefusal();
        else {
            connect(m_subscription, &StreamSubscription::statusChanged, this, &MissionsViewModel::changed);
            connect(m_subscription, &StreamSubscription::cursorChanged, this, &MissionsViewModel::changed);
            connect(m_subscription, &StreamSubscription::journalEvent, this, [this, id](const QJsonObject& event) {
                if (id != selectedRunId()) return;
                const QString eventId = text(event, "id");
                if (!eventId.isEmpty() && m_eventIds.contains(eventId)) return;
                if (!eventId.isEmpty()) m_eventIds.insert(eventId);
                m_eventRows.append(event);
                if (m_eventRows.size() > 1000) {
                    m_eventIds.remove(text(m_eventRows.first().toObject(), "id")); m_eventRows.removeFirst();
                }
                m_events.setItems(m_eventRows);
                if (!m_refreshTimer.isActive()) m_refreshTimer.start();
            });
            connect(m_subscription, &StreamSubscription::serverClosed, this, [this](const QString& reason) {
                if (reason == QLatin1String("unauthorized")) {
                    clearSelection(); m_writeAllowed = false;
                    fail(QStringLiteral("Accès au journal révoqué."));
                }
            });
            connect(m_subscription, &StreamSubscription::refused, this, [this](const ApiError& error) {
                if (error.httpStatus() == 401 || error.httpStatus() == 403) {
                    clearSelection(); m_writeAllowed = false;
                }
                fail(error.message());
            });
        }
    }
    emit changed();
}
void MissionsViewModel::loadComments()
{
    const quint64 selection = m_selection, serial = ++m_commentsRequest;
    ApiRequest req; req.path = QStringLiteral("/missions/") + segment(m_missionId) + QStringLiteral("/comments");
    request(req, [this, selection, serial](const ApiResponse& response) {
        if (selection != m_selection || serial != m_commentsRequest) return;
        if (!response.json.isArray()) { fail(QStringLiteral("Commentaires inexploitables.")); return; }
        m_comments.setItems(response.json.array());
    }, [this, selection, serial](const ApiError& error) {
        if (selection == m_selection && serial == m_commentsRequest) fail(error.message());
    });
}
void MissionsViewModel::loadTests()
{
    const QString id = selectedRunId();
    const quint64 selection = m_selection, serial = ++m_testsRequest;
    m_testsStatus = QStringLiteral("Lecture des résultats de tests…");
    ApiRequest req; req.path = QStringLiteral("/runs/") + segment(id) + QStringLiteral("/test-run");
    request(req, [this, id, selection, serial](const ApiResponse& response) {
        if (selection != m_selection || id != selectedRunId() || serial != m_testsRequest) return;
        const auto obj = response.json.object();
        if (text(obj, "task_run_id") != id || !obj.value(QStringLiteral("cases")).isArray()) {
            m_testsStatus = QStringLiteral("Résultats de tests inexploitables."); return;
        }
        m_testReport = obj; m_testCases.setItems(obj.value(QStringLiteral("cases")).toArray());
        m_testsStatus = QStringLiteral("État des tests : ") + text(obj, "status");
    }, [this, id, selection, serial](const ApiError& error) {
        if (selection != m_selection || id != selectedRunId() || serial != m_testsRequest) return;
        m_testReport = {}; m_testCases.clear();
        m_testsStatus = error.httpStatus() == 404 ? QStringLiteral("Aucune exécution de tests pour cette tentative.") : error.message();
    });
}
void MissionsViewModel::mutate(ApiRequest req, const QString& successText, bool creation)
{
    if (!canWrite()) { fail(QStringLiteral("Écriture indisponible : droits du projet requis ou commande en cours ou non résolue.")); return; }
    m_pendingMutation = req;
    m_pendingCreation = creation;
    m_pendingUncertain = false;
    m_pendingSuccess = successText;
    m_pendingAction = creation ? QStringLiteral("Création de mission")
        : req.path.endsWith(QLatin1String("/stop")) ? QStringLiteral("Demande d'arrêt")
        : req.path.endsWith(QLatin1String("/retry")) ? QStringLiteral("Relance de mission")
        : req.path.endsWith(QLatin1String("/comments")) ? QStringLiteral("Ajout de commentaire")
        : QStringLiteral("Décision d'acceptation");
    sendPending();
}

void MissionsViewModel::clearPendingMutation()
{
    m_pendingMutation.reset();
    m_pendingAction.clear();
    m_pendingSuccess.clear();
    m_pendingCreation = false;
    m_pendingUncertain = false;
}

void MissionsViewModel::retryPending()
{
    if (!canRetryPending()) {
        fail(QStringLiteral("Le rejeu exige une session valide, les droits du projet et une commande idempotente en attente."));
        return;
    }
    sendPending();
}

void MissionsViewModel::abandonPending(bool duplicateRiskAcknowledged)
{
    if (!pendingMutation() || m_mutating) return;
    if (!duplicateRiskAcknowledged) {
        fail(QStringLiteral("Confirmez le risque de doublon : abandonner le suivi n'annule aucune opération sur le serveur."));
        return;
    }
    clearPendingMutation();
    m_error.clear();
    m_notice = QStringLiteral("Suivi abandonné. La commande a pu réussir ; vérifiez le serveur avant une nouvelle action pour éviter un doublon.");
    emit changed();
}

void MissionsViewModel::sendPending()
{
    if (!m_pendingMutation) return;
    const ApiRequest req = *m_pendingMutation;
    const QString successText = m_pendingSuccess;
    const bool creation = m_pendingCreation;
    const quint64 selection = m_selection;
    m_mutating = true; m_error.clear(); m_notice.clear(); emit changed();
    request(req, [this, selection, successText, creation](const ApiResponse& response) {
        m_mutating = false;
        if (selection != m_selection) return;
        const QString id = text(response.json.object(), "id");
        if (!response.json.isObject() || (creation && id.isEmpty())) {
            m_pendingUncertain = true;
            fail(QStringLiteral("Réponse de commande inexploitable. Le résultat reste incertain ; conservez la même commande pour réessayer."));
            return;
        }
        clearPendingMutation();
        m_notice = successText;
        if (creation) {
            selectMission(id);
            m_notice = successText;
        } else { refreshDetail(); loadComments(); }
        refresh();
    }, [this, selection](const ApiError& error) {
        m_mutating = false;
        if (selection != m_selection) return;
        const bool ambiguous = error.isRetryable() || error.kind() == ApiFailure::InvalidResponse
            || error.kind() == ApiFailure::Cancelled;
        if (ambiguous || m_pendingUncertain) {
            m_pendingUncertain = true;
            m_notice = QStringLiteral("Résultat incertain. La commande et sa clé sont conservées en mémoire ; aucune nouvelle action ne sera envoyée avant résolution ou abandon explicite.");
        } else clearPendingMutation();
        fail(error.message());
    });
}
QJsonObject MissionsViewModel::creationBody(const QString& projectId, const QVariantMap& form, QString* error)
{
    auto reject = [error](const QString& message) { if (error) *error = message; return QJsonObject{}; };
    if (error) error->clear();
    QJsonObject body;
    if (projectId.isEmpty()) return reject(QStringLiteral("Sélectionnez un projet."));
    body.insert(QStringLiteral("project_id"), projectId);
    for (const QString& key : {QStringLiteral("title"), QStringLiteral("objective"), QStringLiteral("expected_outcome")}) {
        const QString value = form.value(key).toString().trimmed();
        const int maximum = key == QLatin1String("title") ? 300 : 10000;
        if (value.isEmpty() || value.size() > maximum || value.contains(QChar(u'\0')))
            return reject(QStringLiteral("Titre, objectif et résultat attendu sont obligatoires et doivent respecter leurs limites."));
        body.insert(key, value);
    }
    const auto criteria = lines(form.value(QStringLiteral("acceptance_criteria")).toString());
    if (criteria.isEmpty() || criteria.size() > 100) return reject(QStringLiteral("Indiquez entre 1 et 100 critères, un par ligne."));
    bool validCost = false, validDuration = false;
    const double cost = form.value(QStringLiteral("max_cost")).toString().toDouble(&validCost);
    const int duration = form.value(QStringLiteral("duration_seconds")).toInt(&validDuration);
    if (!validCost || !std::isfinite(cost) || cost < 0 || cost > 999999999999.0)
        return reject(QStringLiteral("Le plafond de coût doit être un nombre entre 0 et 999999999999 (point décimal)."));
    if (!validDuration || duration < 1 || duration > 31536000)
        return reject(QStringLiteral("La durée doit être comprise entre 1 et 31536000 secondes."));
    const QString mode = form.value(QStringLiteral("autonomy"), QStringLiteral("bounded")).toString();
    if (mode != QLatin1String("supervised") && mode != QLatin1String("bounded") && mode != QLatin1String("autonomous"))
        return reject(QStringLiteral("Mode d'autonomie inconnu."));
    const auto capabilities = lines(form.value(QStringLiteral("required_capabilities")).toString());
    if (capabilities.size() > 100) return reject(QStringLiteral("Au plus 100 capacités sont admises."));
    body.insert(QStringLiteral("acceptance_criteria"), criteria);
    body.insert(QStringLiteral("autonomy"), QJsonObject{{QStringLiteral("mode"), mode}});
    body.insert(QStringLiteral("budget"), QJsonObject{{QStringLiteral("max_cost"), cost}, {QStringLiteral("currency"), QStringLiteral("EUR")}});
    body.insert(QStringLiteral("duration_seconds"), duration);
    body.insert(QStringLiteral("required_capabilities"), capabilities);
    body.insert(QStringLiteral("resources"), QJsonArray{});
    return body;
}
void MissionsViewModel::createMission(const QVariantMap& form)
{
    QString error;
    const auto body = creationBody(m_projectId, form, &error);
    if (!error.isEmpty()) { fail(error); return; }
    ApiRequest req; req.method = QByteArrayLiteral("POST"); req.path = QStringLiteral("/missions");
    req.body = QJsonDocument(body); req.idempotencyKey = makeIdempotencyKey(QStringLiteral("mission-create"));
    mutate(req, QStringLiteral("Mission créée par le serveur."), true);
}
void MissionsViewModel::stopMission()
{
    if (!canStop()) { fail(QStringLiteral("Cette tentative ne peut pas être arrêtée.")); return; }
    ApiRequest req; req.method = QByteArrayLiteral("POST");
    req.path = QStringLiteral("/missions/") + segment(m_missionId) + QStringLiteral("/stop");
    req.idempotencyKey = makeIdempotencyKey(QStringLiteral("mission-stop"));
    mutate(req, QStringLiteral("Demande d'arrêt enregistrée ; l'état réel reste suivi."));
}
void MissionsViewModel::retryMission(const QString& reason)
{
    if (!canRetry() || reason.trimmed().isEmpty()) { fail(QStringLiteral("Relance indisponible ou motif manquant.")); return; }
    ApiRequest req; req.method = QByteArrayLiteral("POST");
    req.path = QStringLiteral("/missions/") + segment(m_missionId) + QStringLiteral("/retry");
    req.body = QJsonDocument(QJsonObject{{QStringLiteral("reason"), reason.trimmed()}});
    req.idempotencyKey = makeIdempotencyKey(QStringLiteral("mission-retry"));
    mutate(req, QStringLiteral("Nouvelle tentative demandée. Sélectionnez-la dans la liste des tentatives."));
}
void MissionsViewModel::decideAcceptance(const QString& decision, const QString& comment)
{
    if (!canAccept() || (decision != QLatin1String("accepted") && decision != QLatin1String("rejected"))) {
        fail(QStringLiteral("Seule une réussite technique en attente d'acceptation peut être décidée.")); return;
    }
    ApiRequest req; req.method = QByteArrayLiteral("POST");
    req.path = QStringLiteral("/missions/") + segment(m_missionId) + QStringLiteral("/runs/")
        + segment(selectedRunId()) + QStringLiteral("/acceptance");
    req.body = QJsonDocument(QJsonObject{{QStringLiteral("decision"), decision}, {QStringLiteral("comment"), comment}});
    // Aucune clé artificielle : cette route ne déclare pas ce contrat de rejeu.
    mutate(req, QStringLiteral("Décision d'acceptation enregistrée."));
}
void MissionsViewModel::addComment(const QString& body)
{
    if (selectedRunId().isEmpty() || body.trimmed().isEmpty()) { fail(QStringLiteral("Sélectionnez une tentative et saisissez un commentaire.")); return; }
    ApiRequest req; req.method = QByteArrayLiteral("POST");
    req.path = QStringLiteral("/missions/") + segment(m_missionId) + QStringLiteral("/comments");
    req.body = QJsonDocument(QJsonObject{{QStringLiteral("body"), body.trimmed()}, {QStringLiteral("run_id"), selectedRunId()}});
    req.idempotencyKey = makeIdempotencyKey(QStringLiteral("mission-comment"));
    mutate(req, QStringLiteral("Commentaire enregistré."));
}
QString MissionsViewModel::displayJson(const QVariant& value) const
{
    return redactSecrets(QString::fromUtf8(QJsonDocument::fromVariant(value).toJson(QJsonDocument::Indented)));
}
} // namespace acp
