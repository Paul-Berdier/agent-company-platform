#pragma once
#include <QObject>
#include <QJsonArray>
#include <QPointer>
#include <QVariantMap>
#include "models/JsonListModel.h"
#include "services/ArtifactDownload.h"

namespace acp {
class ApiClient;
class ApiCall;
class AuthManager;

class ArtifactsViewModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString projectId READ projectId WRITE setProjectId NOTIFY changed)
    Q_PROPERTY(JsonListModel *rows READ rows CONSTANT)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool available READ available NOTIFY changed)
    Q_PROPERTY(bool detailBusy READ detailBusy NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString streamKind READ streamKind WRITE setStreamKind NOTIFY changed)
    Q_PROPERTY(QString runId READ runId WRITE setRunId NOTIFY changed)
    Q_PROPERTY(bool canLoadMore READ canLoadMore NOTIFY changed)
    Q_PROPERTY(QVariantMap selected READ selected NOTIFY changed)
    Q_PROPERTY(QString suggestedFileName READ suggestedFileName NOTIFY changed)
    Q_PROPERTY(QUrl suggestedSaveUrl READ suggestedSaveUrl NOTIFY changed)
    Q_PROPERTY(ArtifactDownload *downloader READ downloader CONSTANT)
public:
    ArtifactsViewModel(ApiClient *client, AuthManager *auth, QObject *parent = nullptr);
    ~ArtifactsViewModel() override;
    QString projectId() const { return m_projectId; }
    void setProjectId(const QString &id);
    JsonListModel *rows() const { return m_rows; }
    bool busy() const { return !m_listCall.isNull(); }
    bool available() const { return usable(); }
    bool detailBusy() const { return !m_detailCall.isNull(); }
    QString error() const { return m_error; }
    QString streamKind() const { return m_streamKind; }
    void setStreamKind(const QString &value);
    QString runId() const { return m_runId; }
    void setRunId(const QString &value);
    bool canLoadMore() const { return !m_nextCursor.isEmpty() && m_items.size() < 2000; }
    QVariantMap selected() const { return m_selected; }
    QString suggestedFileName() const;
    QUrl suggestedSaveUrl() const;
    ArtifactDownload *downloader() const { return m_download; }
    Q_INVOKABLE void reload();
    Q_INVOKABLE void nextPage();
    Q_INVOKABLE void selectArtifact(const QString &id);
    Q_INVOKABLE void downloadSelected(const QUrl &destination, const QString &artifactId);
    Q_INVOKABLE void cancelDownload();
signals:
    void changed();
private:
    void invalidate();
    void loadPage(const QString &cursor);
    bool usable() const;
    ApiClient *m_client;
    AuthManager *m_auth;
    JsonListModel *m_rows;
    ArtifactDownload *m_download;
    QPointer<ApiCall> m_listCall;
    QPointer<ApiCall> m_detailCall;
    quint64 m_generation = 0;
    quint64 m_selectionGeneration = 0;
    QString m_projectId;
    QString m_streamKind;
    QString m_runId;
    QString m_nextCursor;
    QString m_error;
    QJsonArray m_items;
    QVariantMap m_selected;
};
} // namespace acp
