#include "viewmodels/ConversationsViewModel.h"

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "api/IdempotencyKey.h"
#include "auth/AuthManager.h"
#include "models/JsonListModel.h"

#include <QDateTime>
#include <QSet>
#include <QUrl>

namespace acp {
namespace {
constexpr int kPollIntervalMs = 2000;
constexpr qint64 kPollWindowMs = 5 * 60 * 1000;

QString segment(const QString &value)
{
    return QString::fromLatin1(QUrl::toPercentEncoding(value));
}

bool textField(const QJsonObject &object, const char *key, bool nullable = false)
{
    const auto value = object.value(QLatin1String(key));
    return value.isString() || (nullable && value.isNull());
}

bool timestamp(const QJsonObject &object, const char *key)
{
    return textField(object, key)
        && QDateTime::fromString(object.value(QLatin1String(key)).toString(), Qt::ISODateWithMs)
               .isValid();
}
} // namespace

ConversationsViewModel::ConversationsViewModel(ApiClient *client, AuthManager *auth,
                                             QObject *parent)
    : QObject(parent), m_client(client), m_auth(auth),
      m_conversations(new JsonListModel(this)), m_turns(new JsonListModel(this))
{
    m_pollTimer.setSingleShot(true);
    connect(&m_pollTimer, &QTimer::timeout, this, &ConversationsViewModel::pollTurn);
    connect(m_auth, &AuthManager::stateChanged, this, &ConversationsViewModel::updateSession);
    connect(m_auth, &AuthManager::userChanged, this, &ConversationsViewModel::updateSession);
    connect(m_client, &ApiClient::baseUrlChanged, this, [this] {
        m_sessionOrigin.clear();
        invalidate(true);
    });
    updateSession();
}

ConversationsViewModel::~ConversationsViewModel()
{
    invalidate(false);
}

QObject *ConversationsViewModel::conversations() const { return m_conversations; }
QObject *ConversationsViewModel::turns() const { return m_turns; }
QString ConversationsViewModel::currentId() const { return m_current.value(QStringLiteral("id")).toString(); }
QString ConversationsViewModel::currentTitle() const { return m_current.value(QStringLiteral("title")).toString(); }
bool ConversationsViewModel::archived() const
{
    return m_current.value(QStringLiteral("status")).toString() == QLatin1String("archived");
}

bool ConversationsViewModel::available() const
{
    return m_auth->state() == SessionStatus::Connected && !m_sessionUser.isEmpty()
        && m_sessionOrigin == m_client->baseUrl().toString();
}

bool ConversationsViewModel::canSend() const
{
    return m_active && available() && !currentId().isEmpty() && !archived()
        && m_detailReady && !m_loading && !m_busy && !pendingSubmission() && activeTurnId().isEmpty()
        && !m_draft.trimmed().isEmpty() && m_draft.size() <= 100000;
}

bool ConversationsViewModel::polling() const
{
    return m_pollTimer.isActive() || m_pollInFlight;
}

void ConversationsViewModel::setDraft(const QString &draft)
{
    // Un envoi incertain conserve exactement son texte et sa clé, jusqu'à rapprochement.
    if (pendingSubmission() || m_draft == draft) {
        return;
    }
    m_draft = draft;
    emit changed();
}

void ConversationsViewModel::invalidate(bool clearData)
{
    ++m_generation;
    m_pollTimer.stop();
    m_pollWindow.invalidate();
    m_pollInFlight = false;
    m_loading = false;
    m_busy = false;
    const auto calls = m_calls;
    m_calls.clear();
    for (const auto &call : calls) {
        if (call) {
            call->abort();
        }
    }
    if (clearData) {
        m_detailReady = false;
        m_summaries = {};
        m_turnData = {};
        m_current = {};
        m_conversations->clear();
        m_turns->clear();
        m_draft.clear();
        m_pendingContent.clear();
        m_pendingKey.clear();
        m_exportText.clear();
        m_error.clear();
        m_notice.clear();
    }
    emit changed();
}

void ConversationsViewModel::updateSession()
{
    const auto state = m_auth->state();
    const bool knownIdentity = !m_sessionUser.isEmpty() && m_auth->userId() == m_sessionUser
        && m_sessionOrigin == m_client->baseUrl().toString();
    const bool retained = state == SessionStatus::Connected
        || ((state == SessionStatus::Connecting || state == SessionStatus::Offline) && knownIdentity);
    const QString user = retained ? m_auth->userId() : QString();
    const QString origin = user.isEmpty() ? QString() : m_client->baseUrl().toString();
    if (user == m_sessionUser && origin == m_sessionOrigin) {
        // La relecture de session ne détruit pas la clé d'un envoi incertain.
        // Les boutons réseau restent suspendus jusqu'à la confirmation du serveur.
        if (state != SessionStatus::Connected) m_pollTimer.stop();
        else schedulePoll();
        emit changed();
        return;
    }
    invalidate(true);
    m_sessionUser = user;
    m_sessionOrigin = origin;
    emit changed();
    if (m_active && available()) {
        refresh();
    }
}

void ConversationsViewModel::setProjectId(const QString &projectId)
{
    if (projectId == m_projectId) {
        return;
    }
    invalidate(true);
    m_projectId = projectId;
    emit projectIdChanged();
    if (m_active && available()) {
        refresh();
    }
}

void ConversationsViewModel::setActive(bool active)
{
    if (m_active == active) {
        return;
    }
    m_active = active;
    if (active) {
        refresh();
    } else {
        invalidate(false);
    }
    emit changed();
}

void ConversationsViewModel::request(const ApiRequest &requestValue, Success success, Failure failure)
{
    const quint64 generation = m_generation;
    ApiCall *call = m_client->send(requestValue);
    m_calls.append(call);
    connect(call, &ApiCall::succeeded, this,
            [this, generation, call, success](const ApiResponse &response) {
        m_calls.removeAll(call);
        if (generation == m_generation && m_active && !m_sessionUser.isEmpty()
            && m_auth->userId() == m_sessionUser
            && m_sessionOrigin == m_client->baseUrl().toString()) {
            success(response);
        }
    });
    connect(call, &ApiCall::failed, this,
            [this, generation, call, failure](const ApiError &error) {
        m_calls.removeAll(call);
        if (generation != m_generation || !m_active || m_sessionUser.isEmpty()
            || m_auth->userId() != m_sessionUser
            || m_sessionOrigin != m_client->baseUrl().toString()) {
            return;
        }
        m_error = error.message();
        if (failure) {
            failure(error);
        }
        emit changed();
    });
}

bool ConversationsViewModel::validSummary(const QJsonObject &summary)
{
    const QString status = summary.value(QStringLiteral("status")).toString();
    return textField(summary, "id") && !summary.value(QStringLiteral("id")).toString().isEmpty()
        && textField(summary, "project_id", true) && textField(summary, "title")
        && !summary.value(QStringLiteral("title")).toString().trimmed().isEmpty()
        && (status == QLatin1String("active") || status == QLatin1String("archived"))
        && timestamp(summary, "created_at") && timestamp(summary, "updated_at");
}

bool ConversationsViewModel::validTurn(const QJsonObject &turn)
{
    static const QSet<QString> states{QStringLiteral("submitting"), QStringLiteral("running"),
        QStringLiteral("completed"), QStringLiteral("failed"), QStringLiteral("interrupted")};
    return textField(turn, "id") && !turn.value(QStringLiteral("id")).toString().isEmpty()
        && textField(turn, "client_request_id") && !turn.value(QStringLiteral("client_request_id")).toString().isEmpty()
        && textField(turn, "user_content")
        && textField(turn, "assistant_content", true) && textField(turn, "error", true)
        && states.contains(turn.value(QStringLiteral("status")).toString())
        && timestamp(turn, "created_at") && timestamp(turn, "updated_at")
        && (turn.value(QStringLiteral("status")).toString() != QLatin1String("completed")
            || !turn.value(QStringLiteral("assistant_content")).toString().trimmed().isEmpty());
}

bool ConversationsViewModel::validTurns(const QJsonArray &turnsValue)
{
    QSet<QString> ids;
    for (const auto &value : turnsValue) {
        const QJsonObject turn = value.toObject();
        const QString id = turn.value(QStringLiteral("id")).toString();
        if (!validTurn(turn) || ids.contains(id)) {
            return false;
        }
        ids.insert(id);
    }
    return true;
}

bool ConversationsViewModel::belongsToProject(const QJsonObject &summary) const
{
    return m_projectId.isEmpty() ? summary.value(QStringLiteral("project_id")).isNull()
                                 : summary.value(QStringLiteral("project_id")).toString() == m_projectId;
}

void ConversationsViewModel::failProtocol(const QString &resource)
{
    m_loading = false;
    m_busy = false;
    m_error = QStringLiteral("Réponse %1 invalide : les données ne sont pas affichées.").arg(resource);
    emit changed();
}

void ConversationsViewModel::refresh()
{
    if (!m_active || !available() || m_busy) {
        return;
    }
    invalidate(false);
    m_error.clear();
    m_notice.clear();
    m_loading = true;
    emit changed();
    ApiRequest req;
    req.path = QStringLiteral("/conversations");
    request(req, [this](const ApiResponse &response) {
        const QJsonValue items = response.json.object().value(QStringLiteral("items"));
        if (!response.json.isObject() || !items.isArray()) {
            failProtocol(QStringLiteral("de liste des conversations"));
            return;
        }
        QJsonArray visible;
        QSet<QString> ids;
        for (const auto &value : items.toArray()) {
            const QJsonObject item = value.toObject();
            const QString id = item.value(QStringLiteral("id")).toString();
            if (!validSummary(item) || ids.contains(id)) {
                failProtocol(QStringLiteral("de liste des conversations"));
                return;
            }
            ids.insert(id);
            if (belongsToProject(item)) {
                visible.append(item);
            }
        }
        m_summaries = visible;
        m_conversations->setItems(visible);
        const QString selected = currentId();
        bool found = false;
        for (const auto &value : visible) {
            if (value.toObject().value(QStringLiteral("id")).toString() == selected) {
                found = true;
            }
        }
        if (found) {
            loadDetail(selected);
        } else {
            m_detailReady = false;
            m_current = {};
            m_turnData = {};
            m_turns->clear();
            m_draft.clear();
            m_pendingKey.clear();
            m_pendingContent.clear();
            m_exportText.clear();
            m_loading = false;
        }
        emit changed();
    }, [this](const ApiError &) { m_loading = false; });
}

void ConversationsViewModel::selectConversation(const QString &id)
{
    if (!m_active || !available() || m_busy || id == currentId()) {
        return;
    }
    if (pendingSubmission()) {
        m_error = QStringLiteral("Rapprochez d'abord le message dont l'envoi reste incertain.");
        emit changed();
        return;
    }
    for (const auto &value : m_summaries) {
        if (value.toObject().value(QStringLiteral("id")).toString() == id) {
            invalidate(false);
            m_current = value.toObject();
            m_turnData = {};
            m_turns->clear();
            m_draft.clear();
            m_exportText.clear();
            m_error.clear();
            m_notice.clear();
            loadDetail(id);
            return;
        }
    }
}

void ConversationsViewModel::loadDetail(const QString &id)
{
    m_detailReady = false;
    m_loading = true;
    emit changed();
    ApiRequest req;
    req.path = QStringLiteral("/conversations/%1").arg(segment(id));
    request(req, [this, id](const ApiResponse &response) {
        const QJsonObject detail = response.json.object();
        const QJsonValue turnsValue = detail.value(QStringLiteral("turns"));
        if (!validSummary(detail) || detail.value(QStringLiteral("id")).toString() != id
            || !belongsToProject(detail) || !turnsValue.isArray() || !validTurns(turnsValue.toArray())) {
            failProtocol(QStringLiteral("de conversation"));
            return;
        }
        applySummary(detail);
        applyTurns(turnsValue.toArray());
        m_detailReady = true;
        m_loading = false;
        m_pollWindow.start();
        schedulePoll();
        emit changed();
    }, [this](const ApiError &) { m_loading = false; });
}

void ConversationsViewModel::applySummary(const QJsonObject &summary)
{
    m_current = summary;
    m_current.remove(QStringLiteral("turns"));
    bool found = false;
    for (qsizetype i = 0; i < m_summaries.size(); ++i) {
        if (m_summaries.at(i).toObject().value(QStringLiteral("id")) == summary.value(QStringLiteral("id"))) {
            m_summaries.replace(i, m_current);
            found = true;
            break;
        }
    }
    if (!found) {
        m_summaries.prepend(m_current);
    }
    m_conversations->setItems(m_summaries);
}

void ConversationsViewModel::applyTurns(const QJsonArray &turnsValue)
{
    m_turnData = turnsValue;
    m_turns->setItems(m_turnData);
    for (const auto &value : m_turnData) {
        const auto turn = value.toObject();
        if (!m_pendingKey.isEmpty() && turn.value(QStringLiteral("client_request_id")).toString() == m_pendingKey
            && turn.value(QStringLiteral("user_content")).toString() == m_pendingContent) {
            m_pendingKey.clear();
            m_pendingContent.clear();
            m_draft.clear();
        }
    }
}

void ConversationsViewModel::createConversation(const QString &title)
{
    if (!m_active || !available() || m_busy || m_loading || pendingSubmission()) {
        return;
    }
    if (title.trimmed().isEmpty() || title.size() > 200 || title.contains(QChar::Null)) {
        m_error = QStringLiteral("Saisissez un titre de 1 à 200 caractères, sans caractère NUL.");
        emit changed();
        return;
    }
    invalidate(false);
    m_busy = true;
    m_error.clear();
    ApiRequest req;
    req.method = QByteArrayLiteral("POST");
    req.path = QStringLiteral("/conversations");
    req.body = QJsonDocument(QJsonObject{{QStringLiteral("title"), title.trimmed()},
        {QStringLiteral("project_id"), m_projectId.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(m_projectId)}});
    // La création n'a pas de contrat d'idempotence : aucun rejeu automatique.
    request(req, [this](const ApiResponse &response) {
        const auto summary = response.json.object();
        if (!validSummary(summary) || !belongsToProject(summary)) {
            failProtocol(QStringLiteral("de création de conversation"));
            return;
        }
        m_busy = false;
        m_draft.clear();
        m_exportText.clear();
        applySummary(summary);
        applyTurns({});
        m_detailReady = true;
        m_notice = QStringLiteral("Conversation créée.");
        emit changed();
    }, [this](const ApiError &error) {
        m_busy = false;
        if (error.isRetryable()) {
            m_notice = QStringLiteral("La création a pu aboutir. Actualisez la liste avant de réessayer.");
        }
    });
}

void ConversationsViewModel::sendMessage()
{
    if (!canSend()) {
        return;
    }
    if (m_draft.contains(QChar::Null)) {
        m_error = QStringLiteral("Le message ne peut pas contenir de caractère NUL.");
        emit changed();
        return;
    }
    m_pendingKey = makeIdempotencyKey(QStringLiteral("conversation-turn"));
    m_pendingContent = m_draft.trimmed();
    submitPending();
}

void ConversationsViewModel::retryPendingMessage()
{
    if (m_active && available() && pendingSubmission() && !m_busy && !m_loading && !archived()) {
        submitPending();
    }
}

void ConversationsViewModel::submitPending()
{
    m_busy = true;
    m_error.clear();
    m_notice.clear();
    m_pollTimer.stop();
    emit changed();
    ApiRequest req;
    req.method = QByteArrayLiteral("POST");
    req.path = QStringLiteral("/conversations/%1/turns").arg(segment(currentId()));
    req.idempotencyKey = m_pendingKey;
    req.body = QJsonDocument(QJsonObject{{QStringLiteral("client_request_id"), m_pendingKey},
                                       {QStringLiteral("content"), m_pendingContent}});
    req.timeout = std::chrono::milliseconds(60000);
    request(req, [this](const ApiResponse &response) {
        const auto turn = response.json.object();
        m_busy = false;
        if (!validTurn(turn) || turn.value(QStringLiteral("client_request_id")).toString() != m_pendingKey
            || turn.value(QStringLiteral("user_content")).toString() != m_pendingContent) {
            failProtocol(QStringLiteral("d'envoi de message"));
            return;
        }
        QJsonArray updated = m_turnData;
        bool found = false;
        for (qsizetype i = 0; i < updated.size(); ++i) {
            if (updated.at(i).toObject().value(QStringLiteral("id")) == turn.value(QStringLiteral("id"))) {
                updated.replace(i, turn);
                found = true;
                break;
            }
        }
        if (!found) {
            updated.append(turn);
        }
        applyTurns(updated);
        m_notice = QStringLiteral("Message enregistré par le serveur.");
        m_pollWindow.start();
        schedulePoll();
        emit changed();
    }, [this](const ApiError &error) {
        m_busy = false;
        if (error.httpStatus() == 422 || error.httpStatus() == 403 || error.httpStatus() == 404) {
            m_pendingKey.clear();
            m_pendingContent.clear();
        } else {
            m_notice = QStringLiteral("Envoi incertain : le texte est conservé. Réessayez avec la même clé ou actualisez.");
        }
    });
}

void ConversationsViewModel::renameConversation(const QString &title)
{
    if (title.trimmed().isEmpty() || title.size() > 200 || title.contains(QChar::Null)) {
        m_error = QStringLiteral("Saisissez un titre de 1 à 200 caractères, sans caractère NUL.");
        emit changed();
        return;
    }
    patchConversation({{QStringLiteral("title"), title.trimmed()}});
}

void ConversationsViewModel::setArchived(bool archivedValue)
{
    patchConversation({{QStringLiteral("status"), archivedValue ? QStringLiteral("archived") : QStringLiteral("active")}});
}

void ConversationsViewModel::patchConversation(const QJsonObject &body)
{
    if (!m_active || !available() || currentId().isEmpty() || m_busy || m_loading || pendingSubmission()) {
        return;
    }
    m_busy = true;
    m_error.clear();
    emit changed();
    const QString id = currentId();
    ApiRequest req;
    req.method = QByteArrayLiteral("PATCH");
    req.path = QStringLiteral("/conversations/%1").arg(segment(id));
    req.body = QJsonDocument(body);
    request(req, [this, id](const ApiResponse &response) {
        const auto summary = response.json.object();
        if (!validSummary(summary) || summary.value(QStringLiteral("id")).toString() != id
            || !belongsToProject(summary)) {
            failProtocol(QStringLiteral("de modification de conversation"));
            return;
        }
        m_busy = false;
        applySummary(summary);
        m_notice = QStringLiteral("Conversation mise à jour.");
        emit changed();
    }, [this](const ApiError &) { m_busy = false; });
}

QString ConversationsViewModel::activeTurnId() const
{
    for (const auto &value : m_turnData) {
        const auto turn = value.toObject();
        const QString state = turn.value(QStringLiteral("status")).toString();
        if (state == QLatin1String("submitting") || state == QLatin1String("running")) {
            return turn.value(QStringLiteral("id")).toString();
        }
    }
    return {};
}

void ConversationsViewModel::schedulePoll()
{
    if (!m_active || !available() || activeTurnId().isEmpty() || m_pollInFlight) {
        return;
    }
    if (!m_pollWindow.isValid() || m_pollWindow.elapsed() >= kPollWindowMs) {
        m_notice = QStringLiteral("Le suivi automatique est en pause après cinq minutes. Actualisez pour reprendre.");
        return;
    }
    m_pollTimer.start(kPollIntervalMs);
}

void ConversationsViewModel::pollTurn()
{
    const QString id = activeTurnId();
    if (!m_active || !available() || id.isEmpty() || m_pollInFlight) {
        return;
    }
    if (m_pollWindow.elapsed() >= kPollWindowMs) {
        schedulePoll();
        emit changed();
        return;
    }
    m_pollInFlight = true;
    emit changed();
    ApiRequest req;
    req.path = QStringLiteral("/conversations/%1/turns/%2").arg(segment(currentId()), segment(id));
    req.timeout = std::chrono::milliseconds(60000);
    request(req, [this, id](const ApiResponse &response) {
        m_pollInFlight = false;
        const auto turn = response.json.object();
        if (!validTurn(turn) || turn.value(QStringLiteral("id")).toString() != id) {
            failProtocol(QStringLiteral("de suivi de message"));
            return;
        }
        QJsonArray updated = m_turnData;
        for (qsizetype i = 0; i < updated.size(); ++i) {
            if (updated.at(i).toObject().value(QStringLiteral("id")).toString() == id) {
                updated.replace(i, turn);
                break;
            }
        }
        m_error.clear();
        applyTurns(updated);
        schedulePoll();
        emit changed();
    }, [this](const ApiError &error) {
        m_pollInFlight = false;
        if (error.isRetryable()) {
            schedulePoll();
        }
    });
}

void ConversationsViewModel::exportConversation()
{
    if (!m_active || !available() || currentId().isEmpty() || m_busy || m_loading) {
        return;
    }
    m_busy = true;
    m_error.clear();
    m_exportText.clear();
    emit changed();
    const QString id = currentId();
    ApiRequest req;
    req.path = QStringLiteral("/conversations/%1/export").arg(segment(id));
    request(req, [this, id](const ApiResponse &response) {
        const auto detail = response.json.object();
        if (!validSummary(detail) || detail.value(QStringLiteral("id")).toString() != id
            || !belongsToProject(detail) || !detail.value(QStringLiteral("turns")).isArray()
            || !validTurns(detail.value(QStringLiteral("turns")).toArray())) {
            failProtocol(QStringLiteral("d'export"));
            return;
        }
        m_busy = false;
        m_exportText = QString::fromUtf8(response.json.toJson(QJsonDocument::Indented));
        m_notice = QStringLiteral("Export JSON prêt à lire ou copier.");
        emit changed();
    }, [this](const ApiError &) { m_busy = false; });
}

} // namespace acp
