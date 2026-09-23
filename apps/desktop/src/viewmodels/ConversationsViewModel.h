#pragma once

#include "api/ApiRequest.h"

#include <QElapsedTimer>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QTimer>
#include <QVariantList>

#include <functional>

namespace acp {

class ApiCall;
class ApiClient;
class ApiError;
class AuthManager;
class JsonListModel;

/*! Conversations distantes : aucun appel Hermes direct, aucune donnée sur disque. */
class ConversationsViewModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString projectId READ projectId WRITE setProjectId NOTIFY projectIdChanged)
    Q_PROPERTY(QObject *conversations READ conversations CONSTANT)
    Q_PROPERTY(QObject *turns READ turns CONSTANT)
    Q_PROPERTY(QString currentId READ currentId NOTIFY changed)
    Q_PROPERTY(QString currentTitle READ currentTitle NOTIFY changed)
    Q_PROPERTY(bool archived READ archived NOTIFY changed)
    Q_PROPERTY(bool loading READ loading NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool available READ available NOTIFY changed)
    Q_PROPERTY(bool canSend READ canSend NOTIFY changed)
    Q_PROPERTY(bool canStopTurn READ canStopTurn NOTIFY changed)
    Q_PROPERTY(bool polling READ polling NOTIFY changed)
    Q_PROPERTY(bool pendingSubmission READ pendingSubmission NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString notice READ notice NOTIFY changed)
    Q_PROPERTY(QString draft READ draft WRITE setDraft NOTIFY changed)
    Q_PROPERTY(QString exportText READ exportText NOTIFY changed)
    Q_PROPERTY(bool active READ active WRITE setActive NOTIFY changed)
    Q_PROPERTY(QString searchText READ searchText WRITE setSearchText NOTIFY changed)
    Q_PROPERTY(bool showArchived READ showArchived WRITE setShowArchived NOTIFY changed)

public:
    ConversationsViewModel(ApiClient *client, AuthManager *auth, QObject *parent = nullptr);
    ~ConversationsViewModel() override;

    [[nodiscard]] QString projectId() const { return m_projectId; }
    void setProjectId(const QString &projectId);
    [[nodiscard]] QObject *conversations() const;
    [[nodiscard]] QObject *turns() const;
    [[nodiscard]] QString currentId() const;
    [[nodiscard]] QString currentTitle() const;
    [[nodiscard]] bool archived() const;
    [[nodiscard]] bool loading() const { return m_loading; }
    [[nodiscard]] bool busy() const { return m_busy; }
    [[nodiscard]] bool available() const;
    [[nodiscard]] bool canSend() const;
    [[nodiscard]] bool canStopTurn() const;
    [[nodiscard]] bool polling() const;
    [[nodiscard]] bool pendingSubmission() const { return !m_pendingKey.isEmpty(); }
    [[nodiscard]] QString error() const { return m_error; }
    [[nodiscard]] QString notice() const { return m_notice; }
    [[nodiscard]] QString draft() const { return m_draft; }
    void setDraft(const QString &draft);
    [[nodiscard]] QString exportText() const { return m_exportText; }
    [[nodiscard]] bool active() const { return m_active; }
    void setActive(bool active);
    [[nodiscard]] QString searchText() const { return m_searchText; }
    void setSearchText(const QString &text);
    [[nodiscard]] bool showArchived() const { return m_showArchived; }
    void setShowArchived(bool show);

    Q_INVOKABLE bool startConversation(const QString &projectId);
    Q_INVOKABLE bool openConversation(const QString &id);
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void selectConversation(const QString &id);
    Q_INVOKABLE void createConversation(const QString &title);
    Q_INVOKABLE void sendMessage();
    Q_INVOKABLE void retryPendingMessage();
    Q_INVOKABLE void stopTurn();
    Q_INVOKABLE void renameConversation(const QString &title);
    Q_INVOKABLE void setArchived(bool archived);
    Q_INVOKABLE void exportConversation();
    // Découpe inerte : texte et clôtures de code uniquement, jamais HTML ni URL active.
    Q_INVOKABLE QVariantList messageBlocks(const QString &text) const;

signals:
    void changed();
    void projectIdChanged();
    void historyAboutToChange();
    void historyChanged();

private:
    using Success = std::function<void(const ApiResponse &)>;
    using Failure = std::function<void(const ApiError &)>;
    void request(const ApiRequest &request, Success success, Failure failure = {});
    void invalidate(bool clearData);
    void updateSession();
    void loadDetail(const QString &id);
    void applySummary(const QJsonObject &summary);
    void applyTurns(const QJsonArray &turns);
    void submitPending();
    void createConversationRequest(const QString &title, bool reloadList);
    void updateConversationList();
    void rememberDraft();
    [[nodiscard]] QString draftKey() const;
    void patchConversation(const QJsonObject &body);
    void schedulePoll();
    void pollTurn();
    void failProtocol(const QString &resource);
    [[nodiscard]] QString activeTurnId() const;
    [[nodiscard]] bool belongsToProject(const QJsonObject &summary) const;
    [[nodiscard]] static bool validSummary(const QJsonObject &summary);
    [[nodiscard]] static bool validTurn(const QJsonObject &turn);
    [[nodiscard]] static bool validTurns(const QJsonArray &turns);

    ApiClient *m_client;
    AuthManager *m_auth;
    JsonListModel *m_conversations;
    JsonListModel *m_turns;
    QList<QPointer<ApiCall>> m_calls;
    QTimer m_pollTimer;
    QElapsedTimer m_pollWindow;
    QJsonArray m_summaries;
    QJsonArray m_turnData;
    QJsonObject m_current;
    QString m_projectId;
    QString m_sessionUser;
    QString m_sessionOrigin;
    QString m_error;
    QString m_notice;
    QString m_draft;
    QString m_pendingKey;
    QString m_pendingContent;
    QString m_exportText;
    QString m_searchText;
    QHash<QString, QString> m_drafts;
    quint64 m_generation = 0;
    bool m_active = false;
    bool m_loading = false;
    bool m_busy = false;
    bool m_pollInFlight = false;
    bool m_detailReady = false;
    bool m_showArchived = false;
};

} // namespace acp
