#include "viewmodels/ArtifactsViewModel.h"
#include "api/ApiClient.h"
#include "auth/AuthManager.h"
#include "diagnostics/Redaction.h"
#include <QJsonObject>
#include <QDir>
#include <QStandardPaths>
#include <QRegularExpression>
#include <QSet>
#include <QUrlQuery>
#include <cmath>

namespace acp {
ArtifactsViewModel::ArtifactsViewModel(ApiClient *client, AuthManager *auth, QObject *parent)
    : QObject(parent), m_client(client), m_auth(auth), m_rows(new JsonListModel(this)),
      m_download(new ArtifactDownload(client, this))
{
    connect(client, &ApiClient::baseUrlChanged, this, &ArtifactsViewModel::invalidate);
    connect(auth, &AuthManager::stateChanged, this, [this] {
        const auto state = m_auth->state();
        if (state == SessionStatus::Disconnected || state == SessionStatus::Expired
            || state == SessionStatus::Revoked)
            invalidate();
        else emit changed();
    });
    connect(auth, &AuthManager::sessionEstablished, this, &ArtifactsViewModel::reload);
    connect(auth, &AuthManager::userChanged, this, [this] {
        invalidate();
        if (usable())
            loadPage({});
    });
}

ArtifactsViewModel::~ArtifactsViewModel()
{
    ++m_generation;
    ++m_selectionGeneration;
    if (m_listCall) {
        disconnect(m_listCall, nullptr, this, nullptr);
        m_listCall->abort();
    }
    if (m_detailCall) {
        disconnect(m_detailCall, nullptr, this, nullptr);
        m_detailCall->abort();
    }
}

bool ArtifactsViewModel::usable() const
{
    return !m_projectId.isEmpty() && m_client->isConfigured()
        && m_auth->state() == SessionStatus::Connected;
}

void ArtifactsViewModel::invalidate()
{
    ++m_generation;
    ++m_selectionGeneration;
    if (m_listCall) m_listCall->abort();
    if (m_detailCall) m_detailCall->abort();
    m_listCall = nullptr;
    m_detailCall = nullptr;
    m_items = {};
    m_rows->clear();
    m_selected.clear();
    m_nextCursor.clear();
    m_error.clear();
    m_download->reset();
    emit changed();
}

void ArtifactsViewModel::setProjectId(const QString &id)
{
    if (id == m_projectId) return;
    m_projectId = id;
    m_runId.clear();
    reload();
}

void ArtifactsViewModel::setStreamKind(const QString &value)
{
    const QString filter = value.trimmed();
    if (filter == m_streamKind) return;
    m_streamKind = filter;
    reload();
}

void ArtifactsViewModel::setRunId(const QString &value)
{
    const QString filter = value.trimmed();
    if (filter == m_runId) return;
    m_runId = filter;
    reload();
}

void ArtifactsViewModel::reload()
{
    invalidate();
    if (usable()) loadPage({});
}

void ArtifactsViewModel::nextPage()
{
    if (usable() && !busy() && canLoadMore()) loadPage(m_nextCursor);
}

void ArtifactsViewModel::loadPage(const QString &cursor)
{
    ApiRequest request;
    request.path = QStringLiteral("/artifacts");
    request.query.addQueryItem(QStringLiteral("project_id"), m_projectId);
    request.query.addQueryItem(QStringLiteral("limit"), QStringLiteral("50"));
    if (!cursor.isEmpty()) request.query.addQueryItem(QStringLiteral("cursor"), cursor);
    if (!m_runId.isEmpty()) request.query.addQueryItem(QStringLiteral("task_run_id"), m_runId);
    if (!m_streamKind.isEmpty()) request.query.addQueryItem(QStringLiteral("stream_kind"), m_streamKind);
    const quint64 generation = m_generation;
    m_error.clear();
    m_listCall = m_client->send(request);
    connect(m_listCall, &ApiCall::succeeded, this, [this, generation, cursor](const ApiResponse &response) {
        if (generation != m_generation) return;
        m_listCall = nullptr;
        const QJsonObject body = response.json.object();
        const QJsonValue items = body.value(QStringLiteral("items"));
        const QJsonValue next = body.value(QStringLiteral("next_cursor"));
        bool valid = response.json.isObject() && items.isArray() && items.toArray().size() <= 50
            && (next.isNull() || next.isString());
        QSet<QString> ids;
        for (const QJsonValue &item : m_items) ids.insert(item.toObject().value(QStringLiteral("id")).toString());
        QJsonArray additions;
        for (const QJsonValue &item : items.toArray()) {
            const QJsonObject row = item.toObject();
            const QString id = row.value(QStringLiteral("id")).toString();
            if (!item.isObject() || id.isEmpty()
                || row.value(QStringLiteral("project_id")).toString() != m_projectId) {
                valid = false;
                break;
            }
            if (!ids.contains(id)) {
                additions.append(item);
                ids.insert(id);
            }
        }
        if (!valid || (!cursor.isEmpty() && next.toString() == cursor)) {
            m_error = QStringLiteral("Page de livrables invalide ; actualisez la liste.");
            m_nextCursor.clear();
        } else {
            for (const QJsonValue &item : additions) m_items.append(item);
            m_rows->setItems(m_items);
            m_nextCursor = next.toString();
            if (m_items.size() >= 2000 && !m_nextCursor.isEmpty())
                m_error = QStringLiteral("2 000 livrables chargés : précisez le filtre avant de poursuivre.");
        }
        emit changed();
    });
    connect(m_listCall, &ApiCall::failed, this, [this, generation](const ApiError &error) {
        if (generation != m_generation) return;
        m_listCall = nullptr;
        m_error = redactSecrets(error.message());
        emit changed();
    });
    emit changed();
}

void ArtifactsViewModel::selectArtifact(const QString &id)
{
    if (!usable()) return;
    static const QRegularExpression identifier(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9_-]{0,199}$"));
    bool present = false;
    for (const QJsonValue &item : m_items)
        present = present || item.toObject().value(QStringLiteral("id")).toString() == id;
    if (!present || !identifier.match(id).hasMatch()) return;
    ++m_selectionGeneration;
    if (m_detailCall) m_detailCall->abort();
    m_detailCall = nullptr;
    m_selected.clear();
    m_error.clear();
    m_download->reset();
    const quint64 generation = m_generation;
    const quint64 selection = m_selectionGeneration;
    ApiRequest request;
    request.path = QStringLiteral("/artifacts/%1").arg(id);
    m_detailCall = m_client->send(request);
    connect(m_detailCall, &ApiCall::succeeded, this, [this, generation, selection, id](const ApiResponse &response) {
        if (generation != m_generation || selection != m_selectionGeneration) return;
        m_detailCall = nullptr;
        const QJsonObject body = response.json.object();
        const QJsonValue size = body.value(QStringLiteral("size_bytes"));
        const double bytes = size.toDouble(-1);
        if (!response.json.isObject() || body.value(QStringLiteral("id")).toString() != id
            || body.value(QStringLiteral("project_id")).toString() != m_projectId
            || !size.isDouble() || !std::isfinite(bytes) || bytes < 0
            || bytes > 9007199254740991.0 || std::floor(bytes) != bytes
            || !body.value(QStringLiteral("has_content")).isBool()) {
            m_error = QStringLiteral("Métadonnées du livrable invalides ; export indisponible.");
        } else {
            m_selected = body.toVariantMap();
        }
        emit changed();
    });
    connect(m_detailCall, &ApiCall::failed, this, [this, generation, selection](const ApiError &error) {
        if (generation != m_generation || selection != m_selectionGeneration) return;
        m_detailCall = nullptr;
        m_error = redactSecrets(error.message());
        emit changed();
    });
    emit changed();
}

QString ArtifactsViewModel::suggestedFileName() const
{
    return ArtifactDownload::safeFileName(m_selected.value(QStringLiteral("original_name")).toString());
}

QUrl ArtifactsViewModel::suggestedSaveUrl() const
{
    QString directory = QStandardPaths::writableLocation(QStandardPaths::DownloadLocation);
    if (directory.isEmpty()) directory = QDir::homePath();
    return QUrl::fromLocalFile(QDir(directory).filePath(suggestedFileName()));
}

void ArtifactsViewModel::downloadSelected(const QUrl &destination, const QString &artifactId)
{
    if (!usable() || artifactId.isEmpty() || artifactId != m_selected.value(QStringLiteral("id")).toString()
        || !m_selected.value(QStringLiteral("has_content")).toBool()) {
        m_error = QStringLiteral("Ce livrable n'est plus disponible dans la session ou le projet courant.");
        emit changed();
        return;
    }
    m_download->start(artifactId, destination,
                      m_selected.value(QStringLiteral("size_bytes")).toLongLong(),
                      m_selected.value(QStringLiteral("checksum")).toString());
}

void ArtifactsViewModel::cancelDownload() { m_download->cancel(); }
} // namespace acp
