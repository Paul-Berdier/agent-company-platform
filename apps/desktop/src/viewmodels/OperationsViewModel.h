#pragma once

#include "api/ApiClient.h"
#include "models/JsonListModel.h"
#include <QJsonObject>
#include <QObject>
#include <QPointer>
#include <QVariantMap>
#include <functional>

namespace acp {
class AuthManager;

class OperationsViewModel final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString projectId READ projectId WRITE setProjectId NOTIFY changed)
    Q_PROPERTY(acp::JsonListModel* approvals READ approvals CONSTANT)
    Q_PROPERTY(acp::JsonListModel* alerts READ alerts CONSTANT)
    Q_PROPERTY(acp::JsonListModel* automations READ automations CONSTANT)
    Q_PROPERTY(acp::JsonListModel* automationRuns READ automationRuns CONSTANT)
    Q_PROPERTY(QVariantMap budgetPolicy READ budgetPolicy NOTIFY changed)
    Q_PROPERTY(QVariantMap budgetUsage READ budgetUsage NOTIFY changed)
    Q_PROPERTY(QVariantMap selectedAutomation READ selectedAutomation NOTIFY changed)
    Q_PROPERTY(QVariantMap statuses READ statuses NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString notice READ notice NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool mutating READ mutating NOTIFY changed)
    Q_PROPERTY(bool canManage READ canManage NOTIFY changed)
    Q_PROPERTY(bool canDecide READ canDecide NOTIFY changed)
public:
    OperationsViewModel(ApiClient*, AuthManager*, QObject* parent = nullptr);
    ~OperationsViewModel() override;
    QString projectId() const { return m_projectId; }
    void setProjectId(const QString& id);
    JsonListModel* approvals() { return &m_approvals; }
    JsonListModel* alerts() { return &m_alerts; }
    JsonListModel* automations() { return &m_automations; }
    JsonListModel* automationRuns() { return &m_runs; }
    QVariantMap budgetPolicy() const { return m_policy.toVariantMap(); }
    QVariantMap budgetUsage() const { return m_usage.toVariantMap(); }
    QVariantMap selectedAutomation() const { return m_automation.toVariantMap(); }
    QVariantMap statuses() const { return m_statuses; }
    QString error() const { return m_error; }
    QString notice() const { return m_notice; }
    bool busy() const { return m_pending > 0; }
    bool mutating() const { return m_mutating; }
    bool canManage() const;
    bool canDecide() const;
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void decideApproval(const QString& id, const QString& decision, const QString& comment);
    Q_INVOKABLE void acknowledgeAlert(const QString& id, const QString& comment);
    Q_INVOKABLE void saveBudgetPolicy(int maxConcurrent, int maxRetries, int maxAgents);
    Q_INVOKABLE void createAutomation(const QVariantMap& form);
    Q_INVOKABLE void selectAutomation(const QString& id);
    Q_INVOKABLE void setAutomationEnabled(const QString& id, bool enabled);
    Q_INVOKABLE QString describe(const QVariant& value) const;
signals:
    void changed();
    void contextReset();
private:
    using Success = std::function<void(const ApiResponse&)>;
    using Verify = std::function<bool(const QJsonObject&)>;
    void request(ApiRequest, const QString& section, Success);
    void mutate(ApiRequest, Verify, const QString& notice);
    void invalidate(bool clearKeys = true);
    void load();
    void permissions();
    void updatePermissions();
    void loadList(const QString& path, const QString& section, JsonListModel*, int limit = 0);
    bool ready() const;
    void fail(const QString& message);
    static QString segment(const QString& id);
    static bool contains(const JsonListModel&, const QString& id);
    ApiClient* m_client;
    AuthManager* m_auth;
    JsonListModel m_approvals, m_alerts, m_automations, m_runs;
    QJsonObject m_policy, m_usage, m_automation;
    QJsonArray m_memberships;
    QList<QPointer<ApiCall>> m_calls;
    QVariantMap m_statuses;
    QString m_projectId, m_workspaceId, m_error, m_notice;
    QHash<QByteArray, QString> m_mutationKeys;
    quint64 m_generation = 0, m_selection = 0;
    int m_pending = 0;
    bool m_mutating = false, m_manage = false, m_decide = false;
};
} // namespace acp
