#pragma once

#include "api/ApiRequest.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QPointer>
#include <QSet>
#include <QVariantMap>

#include <functional>

namespace acp {
class ApiCall;
class ApiClient;
class AuthManager;
class JsonListModel;

// Les objets exposés sont une liste blanche de données publiques, jamais les configurations.
class PlatformViewModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString projectId READ projectId WRITE setProjectId NOTIFY changed)
    Q_PROPERTY(bool active READ active WRITE setActive NOTIFY changed)
    Q_PROPERTY(bool available READ available NOTIFY changed)
    Q_PROPERTY(bool isOwner READ isOwner NOTIFY changed)
    Q_PROPERTY(bool canManageProjectBindings READ canManageProjectBindings NOTIFY changed)
    Q_PROPERTY(QString bindingPermissionReason READ bindingPermissionReason NOTIFY changed)
    Q_PROPERTY(bool loading READ loading NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString notice READ notice NOTIFY changed)
    Q_PROPERTY(QString workersNotice READ workersNotice NOTIFY changed)
    Q_PROPERTY(QObject *agents READ agents CONSTANT)
    Q_PROPERTY(QObject *workers READ workers CONSTANT)
    Q_PROPERTY(QObject *providers READ providers CONSTANT)
    Q_PROPERTY(QObject *mcpServers READ mcpServers CONSTANT)
    Q_PROPERTY(QObject *skills READ skills CONSTANT)
    Q_PROPERTY(QObject *mcpTools READ mcpTools CONSTANT)
    Q_PROPERTY(QVariantMap selectedMcp READ selectedMcp NOTIFY changed)
    Q_PROPERTY(QVariantMap selectedSkill READ selectedSkill NOTIFY changed)
public:
    PlatformViewModel(ApiClient *client, AuthManager *auth, QObject *parent = nullptr);
    ~PlatformViewModel() override;
    QString projectId() const { return m_projectId; }
    void setProjectId(const QString &id);
    bool active() const { return m_active; }
    void setActive(bool active);
    bool available() const;
    bool isOwner() const;
    bool canManageProjectBindings() const;
    QString bindingPermissionReason() const;
    bool loading() const { return m_pending > 0; }
    bool busy() const { return m_busy; }
    QString error() const { return m_error; }
    QString notice() const { return m_notice; }
    QString workersNotice() const { return m_workersNotice; }
    QObject *agents() const;
    QObject *workers() const;
    QObject *providers() const;
    QObject *mcpServers() const;
    QObject *skills() const;
    QObject *mcpTools() const;
    QVariantMap selectedMcp() const;
    QVariantMap selectedSkill() const;
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void selectMcp(const QString &id);
    Q_INVOKABLE void selectSkill(const QString &id);
    Q_INVOKABLE void toggleTool(const QString &name, bool selected);
    Q_INVOKABLE void saveMcpBinding();
    Q_INVOKABLE void setMcpBindingEnabled(bool enabled);
    Q_INVOKABLE void removeMcpBinding();
    Q_INVOKABLE void bindSkill();
    Q_INVOKABLE void removeSkillBinding();
    Q_INVOKABLE void setMcpActive(bool active);
    Q_INVOKABLE void setSkillActive(bool active);
signals:
    void changed();
private:
    using Success = std::function<void(const ApiResponse &)>;
    void request(const ApiRequest &request, Success success, bool mutation = false);
    void updateSession();
    void invalidate();
    void loadList(const QString &path, JsonListModel *model, const QList<QByteArray> &fields);
    void loadPermissions();
    void rebuildProviders();
    void rebuildTools();
    void mutate(const QByteArray &method, const QString &path, const QJsonObject &body,
                const QString &expectedId, bool detail, bool mcp);
    bool permit(bool owner = false, bool project = false);
    void refuse(const QString &message);
    QJsonObject binding(const QJsonObject &detail) const;
    QVariantMap selected(const QJsonObject &detail) const;
    ApiClient *m_client;
    AuthManager *m_auth;
    JsonListModel *m_agents;
    JsonListModel *m_workers;
    JsonListModel *m_providers;
    JsonListModel *m_mcpServers;
    JsonListModel *m_skills;
    JsonListModel *m_mcpTools;
    QList<QPointer<ApiCall>> m_calls;
    QJsonArray m_workerData;
    QJsonArray m_memberships;
    QString m_workspaceId;
    QJsonObject m_hermes;
    QJsonObject m_mcp;
    QJsonObject m_skill;
    QSet<QString> m_chosenTools;
    QString m_mcpId;
    QString m_skillId;
    QString m_projectId;
    QString m_sessionUser;
    QString m_sessionRole;
    QString m_sessionOrigin;
    QString m_error;
    QString m_notice;
    QString m_workersNotice;
    quint64 m_generation = 0;
    quint64 m_mcpSelection = 0;
    quint64 m_skillSelection = 0;
    int m_pending = 0;
    bool m_active = false;
    bool m_busy = false;
    bool m_workersKnown = false;
    bool m_membershipsKnown = false;
    bool m_projectKnown = false;
};
} // namespace acp
