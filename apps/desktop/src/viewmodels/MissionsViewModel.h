#pragma once

#include "api/ApiRequest.h"
#include "models/JsonListModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QObject>
#include <QPointer>
#include <QSet>
#include <QTimer>
#include <QVariantMap>
#include <functional>
#include <optional>

namespace acp {
class ApiClient;
class ApiCall;
class ApiError;
class AuthManager;
class EventStreamService;
class StreamSubscription;

// Toutes les données viennent de l'API. Les générations empêchent une réponse
// d'un ancien projet, serveur ou utilisateur de repeupler l'écran courant.
class MissionsViewModel final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString projectId READ projectId WRITE setProjectId NOTIFY changed)
    Q_PROPERTY(acp::JsonListModel* missions READ missions CONSTANT)
    Q_PROPERTY(acp::JsonListModel* runs READ runs CONSTANT)
    Q_PROPERTY(acp::JsonListModel* comments READ comments CONSTANT)
    Q_PROPERTY(acp::JsonListModel* events READ events CONSTANT)
    Q_PROPERTY(acp::JsonListModel* evidence READ evidence CONSTANT)
    Q_PROPERTY(acp::JsonListModel* testCases READ testCases CONSTANT)
    Q_PROPERTY(QVariantMap mission READ mission NOTIFY changed)
    Q_PROPERTY(QVariantMap run READ run NOTIFY changed)
    Q_PROPERTY(QVariantMap testReport READ testReport NOTIFY changed)
    Q_PROPERTY(QString selectedMissionId READ selectedMissionId NOTIFY changed)
    Q_PROPERTY(QString selectedRunId READ selectedRunId NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString notice READ notice NOTIFY changed)
    Q_PROPERTY(QString testsStatus READ testsStatus NOTIFY changed)
    Q_PROPERTY(QString streamStatus READ streamStatus NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool mutating READ mutating NOTIFY changed)
    Q_PROPERTY(bool canWrite READ canWrite NOTIFY changed)
    Q_PROPERTY(bool canStop READ canStop NOTIFY changed)
    Q_PROPERTY(bool canRetry READ canRetry NOTIFY changed)
    Q_PROPERTY(bool canAccept READ canAccept NOTIFY changed)
    Q_PROPERTY(bool pendingMutation READ pendingMutation NOTIFY changed)
    Q_PROPERTY(bool canRetryPending READ canRetryPending NOTIFY changed)
    Q_PROPERTY(QString pendingAction READ pendingAction NOTIFY changed)
public:
    MissionsViewModel(ApiClient*, AuthManager*, EventStreamService*, QObject* parent = nullptr);
    ~MissionsViewModel() override;
    QString projectId() const { return m_projectId; }
    void setProjectId(const QString& id);
    JsonListModel* missions() { return &m_missions; }
    JsonListModel* runs() { return &m_runs; }
    JsonListModel* comments() { return &m_comments; }
    JsonListModel* events() { return &m_events; }
    JsonListModel* evidence() { return &m_evidence; }
    JsonListModel* testCases() { return &m_testCases; }
    QVariantMap mission() const { return m_mission.toVariantMap(); }
    QVariantMap run() const { return m_run.toVariantMap(); }
    QVariantMap testReport() const { return m_testReport.toVariantMap(); }
    QString selectedMissionId() const { return m_missionId; }
    QString selectedRunId() const { return m_run.value(QStringLiteral("id")).toString(); }
    QString error() const { return m_error; }
    QString notice() const { return m_notice; }
    QString testsStatus() const { return m_testsStatus; }
    QString streamStatus() const;
    bool busy() const { return m_pending > 0; }
    bool mutating() const { return m_mutating; }
    bool canWrite() const;
    bool canStop() const;
    bool canRetry() const;
    bool canAccept() const;
    bool pendingMutation() const { return m_pendingMutation.has_value(); }
    bool canRetryPending() const;
    QString pendingAction() const { return m_pendingAction; }

    Q_INVOKABLE void refresh();
    Q_INVOKABLE void selectMission(const QString& id);
    Q_INVOKABLE void selectRun(const QString& id);
    Q_INVOKABLE void refreshDetail();
    Q_INVOKABLE void createMission(const QVariantMap& form);
    Q_INVOKABLE void stopMission();
    Q_INVOKABLE void retryMission(const QString& reason);
    Q_INVOKABLE void decideAcceptance(const QString& decision, const QString& comment);
    Q_INVOKABLE void addComment(const QString& body);
    Q_INVOKABLE void retryPending();
    Q_INVOKABLE void abandonPending(bool duplicateRiskAcknowledged);
    Q_INVOKABLE QString displayJson(const QVariant& value) const;

    static bool retryAllowed(const QJsonObject& run);
    static bool acceptanceAllowed(const QJsonObject& run);
    static QJsonObject creationBody(const QString& projectId, const QVariantMap& form,
                                    QString* error);
signals:
    void changed();
    void contextReset();
private:
    using Success = std::function<void(const ApiResponse&)>;
    using Failure = std::function<void(const ApiError&)>;
    void request(ApiRequest request, Success success, Failure failure = {});
    void reset();
    void clearSelection();
    void closeStream();
    void applyDetail(const QJsonObject& object);
    void loadComments();
    void loadTests();
    void loadPermissions();
    void updatePermissions();
    void mutate(ApiRequest request, const QString& successText, bool creation = false);
    void sendPending();
    void clearPendingMutation();
    void syncSession();
    bool ready() const;
    bool isCurrentRun() const;
    void fail(const QString& message);
    static QString segment(const QString& value);

    ApiClient* m_client;
    AuthManager* m_auth;
    EventStreamService* m_streams;
    JsonListModel m_missions, m_runs, m_comments, m_events, m_evidence, m_testCases;
    QString m_projectId, m_missionId, m_error, m_notice, m_testsStatus, m_streamError;
    QString m_workspaceId;
    QString m_sessionUser;
    QList<QPointer<ApiCall>> m_calls;
    std::optional<ApiRequest> m_pendingMutation;
    QString m_pendingAction, m_pendingSuccess;
    bool m_pendingCreation = false, m_pendingUncertain = false;
    QJsonArray m_memberships, m_eventRows;
    QJsonObject m_mission, m_run, m_testReport;
    QSet<QString> m_eventIds;
    QPointer<StreamSubscription> m_subscription;
    QTimer m_refreshTimer;
    quint64 m_generation = 0, m_selection = 0, m_detailRequest = 0, m_listRequest = 0;
    quint64 m_testsRequest = 0, m_commentsRequest = 0;
    int m_pending = 0;
    bool m_mutating = false, m_writeAllowed = false;
};
} // namespace acp
