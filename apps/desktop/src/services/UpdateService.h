#pragma once
#include <QObject>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QPointer>
#include <QUrl>

class QNetworkReply;
namespace acp {
// Client GitHub séparé : aucun cookie ACP ni identifiant du serveur ne le traverse.
// Vérification à la demande uniquement ; l'installation reste explicite sur GitHub.
class UpdateService : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString currentVersion READ currentVersion CONSTANT)
    Q_PROPERTY(QString latestVersion READ latestVersion NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QString notes READ notes NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool updateAvailable READ updateAvailable NOTIFY changed)
    Q_PROPERTY(bool includePrereleases READ includePrereleases WRITE setIncludePrereleases NOTIFY changed)
public:
    explicit UpdateService(QString version, QObject *parent = nullptr);
    ~UpdateService() override;
    QString currentVersion() const { return m_current; }
    QString latestVersion() const { return m_latest; }
    QString status() const { return m_status; }
    QString notes() const { return m_notes; }
    bool busy() const { return !m_reply.isNull(); }
    bool updateAvailable() const { return m_available; }
    bool includePrereleases() const { return m_prereleases; }
    void setIncludePrereleases(bool enabled);
    Q_INVOKABLE void check();
    Q_INVOKABLE void openRelease();
    // Politique pure, partagée par le transport et les tests de données non fiables.
    static int compareVersions(const QString &left, const QString &right, bool *valid);
    static bool validateRelease(const QJsonObject &release, bool prereleases);
signals:
    void changed();
private:
    void fail(const QString &reason);
    void accept(const QByteArray &body);
    QNetworkAccessManager m_network;
    QPointer<QNetworkReply> m_reply;
    QString m_current, m_latest, m_notes;
    QString m_status = QStringLiteral("Aucune vérification effectuée. GitHub sera contacté à votre demande.");
    QUrl m_releaseUrl;
    bool m_available = false;
    bool m_prereleases = false;
};
}
