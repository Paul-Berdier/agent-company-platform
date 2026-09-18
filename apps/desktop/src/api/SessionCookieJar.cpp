#include "api/SessionCookieJar.h"

#include <QNetworkCookie>
#include <QUrl>

namespace acp {

SessionCookieJar::SessionCookieJar(QObject *parent)
    : QNetworkCookieJar(parent)
{
}

bool SessionCookieJar::hasSessionCookie() const
{
    const QList<QNetworkCookie> cookies = allCookies();
    for (const QNetworkCookie &cookie : cookies) {
        if (cookie.name() == QByteArray(kSessionCookieName)) {
            return true;
        }
    }
    return false;
}

void SessionCookieJar::clearAll()
{
    setAllCookies({});
    notifyPresence();
}

int SessionCookieJar::cookieCount() const
{
    return static_cast<int>(allCookies().size());
}

bool SessionCookieJar::setCookiesFromUrl(const QList<QNetworkCookie> &cookies, const QUrl &url)
{
    const bool accepted = QNetworkCookieJar::setCookiesFromUrl(cookies, url);
    notifyPresence();
    return accepted;
}

bool SessionCookieJar::insertCookie(const QNetworkCookie &cookie)
{
    const bool inserted = QNetworkCookieJar::insertCookie(cookie);
    notifyPresence();
    return inserted;
}

bool SessionCookieJar::updateCookie(const QNetworkCookie &cookie)
{
    const bool updated = QNetworkCookieJar::updateCookie(cookie);
    notifyPresence();
    return updated;
}

bool SessionCookieJar::deleteCookie(const QNetworkCookie &cookie)
{
    const bool deleted = QNetworkCookieJar::deleteCookie(cookie);
    notifyPresence();
    return deleted;
}

void SessionCookieJar::notifyPresence()
{
    const bool present = hasSessionCookie();
    if (present != m_lastKnownPresence) {
        m_lastKnownPresence = present;
        emit sessionCookiePresenceChanged(present);
    }
}

} // namespace acp
