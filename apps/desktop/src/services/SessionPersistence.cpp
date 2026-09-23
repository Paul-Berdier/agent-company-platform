#include "services/SessionPersistence.h"
#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"
#include "storage/CredentialVault.h"
#include "storage/SettingsStore.h"

#include <QCryptographicHash>
#include <QDataStream>
#include <QIODevice>
#include <QNetworkCookie>
#include <QScopedValueRollback>
#include <QSignalBlocker>
#include <QTimer>
#include <QTimeZone>

namespace acp {
namespace {
constexpr quint32 kMagic = 0x41435031; // ACP1
constexpr qsizetype kMaxDocument = 2560; // Limite du coffre Windows.
bool validCookie(const QByteArray &value)
{
    if (value.size() < 16 || value.size() > 256) return false;
    for (const char c : value)
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
              || (c >= '0' && c <= '9') || c == '-' || c == '_')) return false;
    return true;
}
QByteArray encode(const QByteArray &server, qint64 expiry, const QByteArray &cookie)
{
    QByteArray document;
    QDataStream stream(&document, QIODevice::WriteOnly);
    stream << kMagic << quint16(server.size());
    stream.writeRawData(server.constData(), server.size());
    stream << expiry << quint16(cookie.size());
    stream.writeRawData(cookie.constData(), cookie.size());
    return document;
}
bool decode(const QByteArray &document, QByteArray &server, qint64 &expiry, QByteArray &cookie)
{
    if (document.size() < 16 || document.size() > kMaxDocument) return false;
    QDataStream stream(document);
    quint32 magic = 0;
    quint16 size = 0;
    stream >> magic >> size;
    if (magic != kMagic || size == 0 || size > 2048) return false;
    server.resize(size);
    if (stream.readRawData(server.data(), size) != size) return false;
    stream >> expiry >> size;
    if (size < 16 || size > 256) return false;
    cookie.resize(size);
    if (stream.readRawData(cookie.data(), size) != size) return false;
    return stream.status() == QDataStream::Ok && stream.atEnd() && validCookie(cookie);
}
} // namespace

SessionPersistence::SessionPersistence(ApiClient *client, AuthManager *auth,
                                     CredentialVault *vault, SettingsStore *settings, QObject *parent)
    : QObject(parent), m_client(client), m_auth(auth), m_vault(vault), m_settings(settings),
      m_expiryTimer(new QTimer(this)), m_server(client->baseUrl())
{
    m_expiryTimer->setSingleShot(true);
    connect(m_expiryTimer, &QTimer::timeout, this, &SessionPersistence::checkExpiry);
    connect(m_settings, &SettingsStore::rememberSessionChanged, this, &SessionPersistence::preferenceChanged);
    connect(m_client, &ApiClient::baseUrlChanged, this, &SessionPersistence::serverChanged);
    connect(m_auth, &AuthManager::stateChanged, this, &SessionPersistence::authChanged);
    connect(m_auth, &AuthManager::userChanged, this, &SessionPersistence::authChanged);
    connect(m_client->cookieJar(), &SessionCookieJar::sessionCookiePresenceChanged, this, [this](bool present) {
        // setBaseUrl() change l'URL AVANT de vider les cookies. La purge de l'ancienne
        // entrée appartient alors à serverChanged(), jamais à la nouvelle portée.
        if (m_restoring || m_client->baseUrl() != m_server) return;
        if (!present) {
            m_expiryTimer->stop();
            m_expires = {};
            if (rememberSession()) purge(credentialKey(m_server), QStringLiteral("Session mémorisée effacée."));
        }
    });
    setStatus(rememberSession() ? QStringLiteral("Mémorisation autorisée ; session à vérifier.")
                                : QStringLiteral("Session conservée uniquement pendant cette ouverture."));
}

QByteArray SessionPersistence::canonicalServer(const QUrl &url)
{
    if (!url.isValid() || url.host().isEmpty()) return {};
    QUrl result(url);
    result.setUserInfo(QString());
    result.setQuery(QString());
    result.setFragment(QString());
    result.setScheme(result.scheme().toLower());
    result.setHost(result.host().toLower());
    if ((result.scheme() == QStringLiteral("https") && result.port() == 443)
        || (result.scheme() == QStringLiteral("http") && result.port() == 80)) result.setPort(-1);
    QString path = result.path();
    while (path.endsWith(QLatin1Char('/'))) path.chop(1);
    result.setPath(path);
    return result.toEncoded(QUrl::FullyEncoded);
}

QString SessionPersistence::credentialKey(const QUrl &url)
{
    const auto server = canonicalServer(url);
    return server.isEmpty() ? QString() : QStringLiteral("session.v1.")
        + QString::fromLatin1(QCryptographicHash::hash(server, QCryptographicHash::Sha256).toHex());
}

bool SessionPersistence::rememberSession() const { return m_settings->rememberSession(); }

void SessionPersistence::setRememberSession(bool remember)
{
    m_settings->setRememberSession(remember);
    m_settings->flush();
}

void SessionPersistence::preferenceChanged()
{
    emit rememberSessionChanged();
    if (!rememberSession()) {
        purge(credentialKey(m_server), QStringLiteral("Mémorisation désactivée ; copie du coffre effacée."));
    } else if (!m_vault->canStore()) {
        setStatus(QStringLiteral("Session non mémorisée."), QStringLiteral("Le coffre système est indisponible. Aucun stockage de remplacement n'est utilisé."));
    } else if (m_auth->state() == SessionStatus::Connected) saveVerifiedSession();
    else setStatus(QStringLiteral("La prochaine session validée sera mémorisée dans le coffre système."));
}

void SessionPersistence::setStatus(const QString &status, const QString &error)
{
    if (m_status == status && m_error == error) return;
    m_status = status;
    m_error = error;
    emit statusChanged();
}

bool SessionPersistence::purge(const QString &key, const QString &message)
{
    if (!key.isEmpty()) {
        const auto result = m_vault->remove(key);
        if (!result.ok) {
            // Un effacement refusé ne doit surtout pas rétablir cette session au
            // prochain lancement. Le consentement non secret est désactivé durablement.
            const bool wasEnabled = rememberSession();
            {
                const QSignalBlocker blocked(m_settings);
                m_settings->setRememberSession(false);
                m_settings->flush();
            }
            if (wasEnabled) emit rememberSessionChanged();
            setStatus(QStringLiteral("L'effacement de la session mémorisée a échoué."), result.reason);
            return false;
        }
    }
    setStatus(message);
    return true;
}

void SessionPersistence::serverChanged()
{
    const auto previous = m_server;
    m_server = m_client->baseUrl();
    m_expiryTimer->stop();
    m_expires = {};
    // Une seule portée mémorisée : changer de serveur supprime l'ancienne copie,
    // même quand seul le port ou le préfixe de chemin change.
    if (!previous.isEmpty() && previous != m_server)
        purge(credentialKey(previous), QStringLiteral("Serveur changé ; ancienne session mémorisée effacée."));
}

bool SessionPersistence::restore()
{
    if (!rememberSession() || !m_client->isConfigured()) return false;
    if (m_auth->state() != SessionStatus::Disconnected || m_client->cookieJar()->hasSessionCookie()) return false;
    m_server = m_client->baseUrl();
    const auto key = credentialKey(m_server);
    QByteArray document;
    const auto result = m_vault->load(key, document);
    if (!result.ok) {
        CredentialVault::wipe(document);
        setStatus(QStringLiteral("Session non restaurée."), result.reason);
        return false;
    }
    QByteArray server, value;
    qint64 expiry = 0;
    const bool valid = decode(document, server, expiry, value)
        && server == canonicalServer(m_server)
        && expiry > QDateTime::currentMSecsSinceEpoch()
        && QDateTime::fromMSecsSinceEpoch(expiry, QTimeZone::UTC).isValid();
    CredentialVault::wipe(document);
    if (!valid) {
        CredentialVault::wipe(value);
        purge(key, QStringLiteral("Session mémorisée expirée ou invalide ; connexion requise."));
        return false;
    }
    const QDateTime expires = QDateTime::fromMSecsSinceEpoch(expiry, QTimeZone::UTC);
    QNetworkCookie cookie(QByteArrayLiteral("acp_session"), value);
    cookie.setHttpOnly(true);
    cookie.setSecure(m_server.scheme() == QStringLiteral("https"));
    cookie.setSameSitePolicy(QNetworkCookie::SameSite::Strict);
    cookie.setExpirationDate(expires);
    cookie.setPath(QStringLiteral("/"));
    QScopedValueRollback restoring(m_restoring, true);
    const bool accepted = m_client->cookieJar()->setCookiesFromUrl({cookie}, m_client->resolve(QStringLiteral("/auth/session")));
    CredentialVault::wipe(value);
    if (!accepted) {
        purge(key, QStringLiteral("Le cookie mémorisé a été refusé ; connexion requise."));
        return false;
    }
    armExpiry(expires);
    setStatus(QStringLiteral("Session retrouvée dans le coffre ; validation du serveur requise."));
    return true;
}

void SessionPersistence::authChanged()
{
    if (m_restoring || m_client->baseUrl() != m_server) return;
    switch (m_auth->state()) {
    case SessionStatus::Connected:
        if (m_auth->userId().isEmpty()) return;
        if (m_auth->expiresAt().isValid()) armExpiry(m_auth->expiresAt());
        if (rememberSession()) saveVerifiedSession();
        break;
    case SessionStatus::Expired:
    case SessionStatus::Revoked:
        m_expiryTimer->stop();
        m_expires = {};
        if (rememberSession()) purge(credentialKey(m_server), QStringLiteral("Session mémorisée effacée après invalidation."));
        break;
    case SessionStatus::Offline:
        if (rememberSession() && m_error.isEmpty())
            setStatus(QStringLiteral("Serveur injoignable ; la session mémorisée reste à vérifier."));
        break;
    default: break;
    }
}

void SessionPersistence::saveVerifiedSession()
{
    if (!m_vault->canStore()) {
        setStatus(QStringLiteral("Session non mémorisée."), QStringLiteral("Le coffre système est indisponible. Aucun stockage de remplacement n'est utilisé."));
        return;
    }
    QDateTime expires = m_auth->expiresAt();
    const auto cookies = m_client->cookieJar()->cookiesForUrl(m_client->resolve(QStringLiteral("/auth/session")));
    for (const auto &cookie : cookies) {
        if (cookie.name() != QByteArrayLiteral("acp_session")) continue;
        QByteArray value = cookie.value();
        if (!expires.isValid() || !validCookie(value)) {
            CredentialVault::wipe(value);
            setStatus(QStringLiteral("Session non mémorisée."), QStringLiteral("Le serveur n'a pas fourni un cookie et une expiration exploitables."));
            return;
        }
        if (!cookie.isSessionCookie() && cookie.expirationDate() < expires) expires = cookie.expirationDate();
        if (expires <= QDateTime::currentDateTimeUtc()) {
            CredentialVault::wipe(value);
            armExpiry(expires);
            return;
        }
        const auto server = canonicalServer(m_server);
        if (server.size() > 2048) {
            CredentialVault::wipe(value);
            setStatus(QStringLiteral("Session non mémorisée."), QStringLiteral("L'adresse du serveur dépasse la capacité du coffre."));
            return;
        }
        auto document = encode(server, expires.toMSecsSinceEpoch(), value);
        CredentialVault::wipe(value);
        const auto result = m_vault->store(credentialKey(m_server), document);
        CredentialVault::wipe(document);
        armExpiry(expires);
        if (result.ok) setStatus(QStringLiteral("Session mémorisée dans le coffre système jusqu'à son expiration."));
        else setStatus(QStringLiteral("Session non mémorisée."), result.reason);
        return;
    }
    setStatus(QStringLiteral("Session non mémorisée."), QStringLiteral("Aucun cookie de session utilisable n'a été reçu du serveur."));
}

void SessionPersistence::armExpiry(const QDateTime &expires)
{
    m_expires = expires;
    // Réévaluer chaque minute prend aussi en compte une correction de l'horloge système.
    m_expiryTimer->start(int(qBound(qint64(1), QDateTime::currentDateTimeUtc().msecsTo(expires), qint64(60000))));
}

void SessionPersistence::checkExpiry()
{
    if (!m_expires.isValid()) return;
    if (m_expires > QDateTime::currentDateTimeUtc()) { armExpiry(m_expires); return; }
    m_expires = {};
    m_auth->forgetLocalSession(SessionStatus::Expired, QStringLiteral("La session a atteint son expiration."));
}
} // namespace acp
