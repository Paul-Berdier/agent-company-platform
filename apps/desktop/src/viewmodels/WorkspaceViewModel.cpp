#include "viewmodels/WorkspaceViewModel.h"
#include "api/ApiClient.h"
#include "auth/AuthManager.h"

namespace acp {
WorkspaceViewModel::WorkspaceViewModel(ApiClient *client, AuthManager *auth, QObject *parent)
    : QObject(parent), m_client(client), m_auth(auth)
{
    connect(client, &ApiClient::baseUrlChanged, this, &WorkspaceViewModel::clear);
    connect(client, &ApiClient::sessionStateCleared, this, &WorkspaceViewModel::clear);
    connect(auth, &AuthManager::sessionLost, this, [this] {
        if (m_auth->state() != SessionStatus::Offline) clear();
    });
    connect(auth, &AuthManager::sessionEstablished, this, &WorkspaceViewModel::refresh);
    connect(auth, &AuthManager::stateChanged, this, &WorkspaceViewModel::changed);
}
void WorkspaceViewModel::clear()
{
    ++m_epoch;
    m_pending = 0;
    m_projects.clear();
    m_workspaces.clear();
    m_organizations.clear();
    m_project.clear();
    m_memberships = {};
    m_selectAfterRefresh.clear();
    m_projectCreationPending = false;
    m_error.clear();
    m_notice.clear();
    emit projectChanged();
    emit changed();
}
void WorkspaceViewModel::request(const ApiRequest &request,
                               std::function<void(const ApiResponse &)> success)
{
    if (m_auth->state() != SessionStatus::Connected) {
        m_error = QStringLiteral("Connectez-vous pour consulter les projets.");
        emit changed();
        return;
    }
    const auto epoch = m_epoch;
    ++m_pending;
    emit changed();
    auto *call = m_client->send(request);
    connect(call, &ApiCall::succeeded, this, [this, epoch, success](const ApiResponse &response) {
        if (epoch != m_epoch) return;
        --m_pending;
        success(response);
        emit changed();
    });
    connect(call, &ApiCall::failed, this, [this, epoch](const ApiError &error) {
        if (epoch != m_epoch) return;
        --m_pending;
        m_error = error.message();
        emit changed();
    });
}
void WorkspaceViewModel::refresh()
{
    if (busy()) return;
    m_error.clear();
    m_memberships = {};
    if (m_auth->platformRole() != QLatin1String("owner")) {
        ApiRequest memberships;
        memberships.path = QStringLiteral("/memberships");
        memberships.query.addQueryItem(QStringLiteral("user_id"), m_auth->userId());
        request(memberships, [this](const ApiResponse &response) {
            if (response.json.isArray()) m_memberships = response.json.array();
            else m_error = QStringLiteral("Droits de création indisponibles : réponse invalide.");
        });
    }
    const auto list = [this](const QString &path, JsonListModel *model) {
        ApiRequest query;
        query.path = path;
        request(query, [this, model, path](const ApiResponse &response) {
            if (!response.json.isArray()) {
                m_error = QStringLiteral("Le serveur n'a pas renvoyé une liste pour %1.").arg(path);
                return;
            }
            model->setItems(response.json.array());
            if (model == &m_projects) {
                const QString chosen = m_selectAfterRefresh.isEmpty() ? projectId() : m_selectAfterRefresh;
                m_selectAfterRefresh.clear();
                selectProject(chosen);
            }
        });
    };
    list(QStringLiteral("/projects"), &m_projects);
    list(QStringLiteral("/workspaces"), &m_workspaces);
    list(QStringLiteral("/organizations"), &m_organizations);
}
bool WorkspaceViewModel::canCreateInWorkspace(const QString &workspaceId) const
{
    if (workspaceId.isEmpty() || busy() || m_auth->state() != SessionStatus::Connected) return false;
    if (m_auth->platformRole() == QLatin1String("owner")) return true;
    for (const auto &value : m_memberships) {
        const auto row = value.toObject();
        const QString role = row.value(QStringLiteral("role")).toString();
        if (row.value(QStringLiteral("user_id")).toString() == m_auth->userId()
            && row.value(QStringLiteral("scope_type")).toString() == QLatin1String("workspace")
            && row.value(QStringLiteral("scope_id")).toString() == workspaceId
            && (role == QLatin1String("member") || role == QLatin1String("operator") || role == QLatin1String("owner"))) return true;
    }
    return false;
}
bool WorkspaceViewModel::canCreateProject() const
{
    for (int i = 0; i < m_workspaces.count(); ++i)
        if (canCreateInWorkspace(m_workspaces.get(i).value(QStringLiteral("id")).toString())) return true;
    return false;
}
void WorkspaceViewModel::requestProjectCreation()
{
    if (!canCreateProject()) return;
    m_projectCreationPending = true;
    emit changed();
}
void WorkspaceViewModel::acknowledgeProjectCreation()
{
    if (!m_projectCreationPending) return;
    m_projectCreationPending = false;
    emit changed();
}
void WorkspaceViewModel::selectProject(const QString &id)
{
    QVariantMap selected;
    for (int i = 0; i < m_projects.count(); ++i) {
        const auto row = m_projects.get(i);
        if (row.value(QStringLiteral("id")).toString() == id) {
            selected = row;
            break;
        }
    }
    if (selected == m_project) return;
    m_project = selected;
    emit projectChanged();
}
void WorkspaceViewModel::create(const QString &path, const QJsonObject &body)
{
    if (busy()) return;
    m_error.clear();
    m_notice.clear();
    if (body.value(QStringLiteral("name")).toString().trimmed().isEmpty()) {
        m_error = QStringLiteral("Le nom est obligatoire.");
        emit changed();
        return;
    }
    ApiRequest mutation;
    mutation.method = QByteArrayLiteral("POST");
    mutation.path = path;
    mutation.body = QJsonDocument(body);
    // Ces routes CRUD n'offrent pas d'idempotence : aucun rejeu automatique du POST.
    request(mutation, [this, path](const ApiResponse &response) {
        const auto id = response.json.object().value(QStringLiteral("id")).toString();
        if (id.isEmpty()) {
            m_error = QStringLiteral("La création n'a pas renvoyé d'identifiant ; actualisez avant de réessayer.");
            return;
        }
        if (path == QStringLiteral("/projects")) m_selectAfterRefresh = id;
        m_notice = QStringLiteral("Création confirmée par le serveur.");
        refresh();
    });
}
void WorkspaceViewModel::createProject(const QString &workspaceId, const QString &name,
                                      const QString &description)
{
    if (workspaceId.isEmpty()) {
        m_error = QStringLiteral("Choisissez un espace de travail.");
        emit changed();
        return;
    }
    if (!canCreateInWorkspace(workspaceId)) {
        m_error = QStringLiteral("Création indisponible : le rôle membre minimum est requis dans cet espace de travail.");
        emit changed();
        return;
    }
    create(QStringLiteral("/projects"), {{QStringLiteral("workspace_id"), workspaceId},
           {QStringLiteral("name"), name.trimmed()}, {QStringLiteral("description"), description}});
}
void WorkspaceViewModel::createOrganization(const QString &name)
{
    if (m_auth->platformRole() != QLatin1String("owner")) {
        m_error = QStringLiteral("Création réservée au propriétaire de la plateforme."); emit changed(); return;
    }
    create(QStringLiteral("/organizations"), {{QStringLiteral("name"), name.trimmed()}});
}
void WorkspaceViewModel::createWorkspace(const QString &organizationId, const QString &name)
{
    if (m_auth->platformRole() != QLatin1String("owner")) {
        m_error = QStringLiteral("Création réservée au propriétaire de la plateforme."); emit changed(); return;
    }
    if (organizationId.isEmpty()) {
        m_error = QStringLiteral("Choisissez une organisation.");
        emit changed();
        return;
    }
    create(QStringLiteral("/workspaces"), {{QStringLiteral("organization_id"), organizationId},
           {QStringLiteral("name"), name.trimmed()}});
}
}
