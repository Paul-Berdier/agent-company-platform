#pragma once

#include <QObject>
#include <QPointer>
#include <QUrl>
#include <memory>

class QCryptographicHash;
class QNetworkReply;
class QSaveFile;
class QTimer;

namespace acp {
class ApiClient;

// Export atomique en flux ; le contenu n'est jamais chargé entièrement en mémoire.
class ArtifactDownload : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(qint64 received READ received NOTIFY changed)
    Q_PROPERTY(qint64 total READ total NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QUrl savedFile READ savedFile NOTIFY changed)
public:
    explicit ArtifactDownload(ApiClient *client, QObject *parent = nullptr);
    ~ArtifactDownload() override;
    bool busy() const { return !m_reply.isNull(); }
    qint64 received() const { return m_received; }
    qint64 total() const { return m_expected; }
    QString error() const { return m_error; }
    QUrl savedFile() const { return m_savedFile; }
    static constexpr qint64 MaximumBytes = 512LL * 1024 * 1024;
    static QString safeFileName(const QString &name);
    void start(const QString &artifactId, const QUrl &destination,
               qint64 expectedBytes, const QString &checksum);
    Q_INVOKABLE void cancel();
    void reset();
signals:
    void changed();
    void succeeded(const QUrl &destination);
    void failed(const QString &reason);
private:
    void consume();
    void finish();
    void fail(const QString &reason);
    void releaseReply();
    ApiClient *m_client;
    QPointer<QNetworkReply> m_reply;
    std::unique_ptr<QSaveFile> m_file;
    std::unique_ptr<QCryptographicHash> m_hash;
    QTimer *m_deadline;
    qint64 m_received = 0;
    qint64 m_expected = 0;
    QString m_checksum;
    QString m_error;
    QUrl m_destination;
    QUrl m_savedFile;
};
} // namespace acp
