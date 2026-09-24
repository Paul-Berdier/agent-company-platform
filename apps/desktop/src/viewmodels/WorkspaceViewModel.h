#pragma once
#include "models/JsonListModel.h"
#include <QObject>
#include <QJsonObject>
#include <functional>

namespace acp {
class ApiClient;
class AuthManager;
struct ApiResponse;
struct ApiRequest;

class WorkspaceViewModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(acp::JsonListModel* projects READ projects CONSTANT)
    Q_PROPERTY(acp::JsonListModel* workspaces READ workspaces CONSTANT)
    Q_PROPERTY(acp::JsonListModel* organizations READ organizations CONSTANT)
    Q_PROPERTY(QString projectId READ projectId NOTIFY projectChanged)
    Q_PROPERTY(QString projectName READ projectName NOTIFY projectChanged)
    Q_PROPERTY(QVariantMap project READ project NOTIFY projectChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool canCreateProject READ canCreateProject NOTIFY changed)
    Q_PROPERTY(bool projectCreationPending READ projectCreationPending NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString notice READ notice NOTIFY changed)
public:
    WorkspaceViewModel(ApiClient *client, AuthManager *auth, QObject *parent = nullptr);
    JsonListModel *projects() { return &m_projects; }
    JsonListModel *workspaces() { return &m_workspaces; }
    JsonListModel *organizations() { return &m_organizations; }
    QString projectId() const { return m_project.value(QStringLiteral("id")).toString(); }
    QString projectName() const { return m_project.value(QStringLiteral("name")).toString(); }
    QVariantMap project() const { return m_project; }
    bool busy() const { return m_pending != 0; }
    bool canCreateProject() const;
    bool projectCreationPending() const { return m_projectCreationPending; }
    Q_INVOKABLE void requestProjectCreation();
    Q_INVOKABLE void acknowledgeProjectCreation();
    Q_INVOKABLE bool canCreateInWorkspace(const QString &workspaceId) const;
    QString error() const { return m_error; }
    QString notice() const { return m_notice; }
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void selectProject(const QString &id);
    Q_INVOKABLE void createProject(const QString &workspaceId, const QString &name,
                                   const QString &description);
    Q_INVOKABLE void createOrganization(const QString &name);
    Q_INVOKABLE void createWorkspace(const QString &organizationId, const QString &name);
signals:
    void projectChanged();
    void changed();
private:
    void clear();
    void request(const ApiRequest &request, std::function<void(const ApiResponse &)> success);
    void create(const QString &path, const QJsonObject &body);
    ApiClient *m_client;
    AuthManager *m_auth;
    JsonListModel m_projects;
    JsonListModel m_workspaces;
    JsonListModel m_organizations;
    QVariantMap m_project;
    QJsonArray m_memberships;
    QString m_error;
    QString m_notice;
    QString m_selectAfterRefresh;
    quint64 m_epoch = 0;
    int m_pending = 0;
    bool m_projectCreationPending = false;
};
}
