// Le coffre ne conserve que le cookie et sa portée. L'identité, les droits et le CSRF
// sont toujours relus sur /auth/session après restauration, jamais restaurés localement.
#pragma once

#include <QDateTime>
#include <QObject>
#include <QUrl>

class QTimer;

namespace acp {
class ApiClient;
class AuthManager;
class CredentialVault;
class SettingsStore;

class SessionPersistence final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool rememberSession READ rememberSession WRITE setRememberSession NOTIFY rememberSessionChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString error READ error NOTIFY statusChanged)
public:
    SessionPersistence(ApiClient *client, AuthManager *auth, CredentialVault *vault,
                       SettingsStore *settings, QObject *parent = nullptr);
    [[nodiscard]] bool rememberSession() const;
    void setRememberSession(bool remember);
    [[nodiscard]] QString status() const { return m_status; }
    [[nodiscard]] QString error() const { return m_error; }
    /*! Appeler après setBaseUrl(), avant AuthManager::resumeSession(). Aucun réseau,
        aucun droit local, aucun secret en propriété QML. */
    bool restore();
    [[nodiscard]] static QByteArray canonicalServer(const QUrl &url);
    [[nodiscard]] static QString credentialKey(const QUrl &url);
signals:
    void rememberSessionChanged();
    void statusChanged();
private:
    void preferenceChanged();
    void serverChanged();
    void authChanged();
    void saveVerifiedSession();
    bool purge(const QString &key, const QString &message);
    void setStatus(const QString &status, const QString &error = {});
    void armExpiry(const QDateTime &expires);
    void checkExpiry();

    ApiClient *m_client;
    AuthManager *m_auth;
    CredentialVault *m_vault;
    SettingsStore *m_settings;
    QTimer *m_expiryTimer;
    QUrl m_server;
    QDateTime m_expires;
    QString m_status;
    QString m_error;
    bool m_restoring = false;
};
} // namespace acp
