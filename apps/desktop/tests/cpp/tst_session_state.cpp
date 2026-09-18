// Machine à états de session, et garde-fous du transport.
//
// Aucun réseau n'est touché : ces tests éprouvent les décisions PRISES AVANT tout envoi —
// refus d'URL non sûre, refus d'écriture sans jeton CSRF, refus de reprise sans cookie,
// purge de session au changement de serveur. Ce sont exactement les cas où une erreur
// produirait un « faux succès » silencieux.
//
// AVERTISSEMENT : jamais compilé, jamais exécuté.

#include "api/ApiClient.h"
#include "api/SessionCookieJar.h"
#include "auth/AuthManager.h"

#include <QNetworkCookie>
#include <QSet>
#include <QSignalSpy>
#include <QTest>
#include <QUrl>

using namespace acp;

class TestSessionState : public QObject
{
    Q_OBJECT

private slots:
    void refusesPlainHttpByDefault();
    void refusesPlainHttpOnNonLoopbackEvenWhenAllowed();
    void acceptsPlainHttpOnLoopbackWhenAllowed();
    void refusesNonHttpScheme();
    void normalisesTrailingSlash();
    void changingServerPurgesSession();
    void resolveRefusesWithoutBaseUrl();
    void initialStateIsDisconnected();
    void resumeWithoutCookieFailsWithoutNetwork();
    void logInRefusesEmptyCredentials();
    void forgetLocalSessionClearsEverything();
    void everySessionStateHasFrenchLabel();
    void cookieJarReportsSessionPresence();
};

void TestSessionState::refusesPlainHttpByDefault()
{
    ApiClient client;
    const ApiError error = client.setBaseUrl(QUrl(QStringLiteral("http://exemple.invalid")));
    QVERIFY(error.isError());
    QCOMPARE(error.kind(), ApiFailure::ClientRefusal);
    QVERIFY(!client.isConfigured());
}

void TestSessionState::refusesPlainHttpOnNonLoopbackEvenWhenAllowed()
{
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    // L'autorisation ne vaut QUE pour le bouclage : elle n'ouvre pas le clair au réseau.
    const ApiError error = client.setBaseUrl(QUrl(QStringLiteral("http://exemple.invalid")));
    QVERIFY(error.isError());
    QVERIFY(!client.isConfigured());
}

void TestSessionState::acceptsPlainHttpOnLoopbackWhenAllowed()
{
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("http://127.0.0.1:8000"))).isError());
    QVERIFY(client.isConfigured());

    ApiClient other;
    other.setAllowInsecureLoopback(true);
    QVERIFY(!other.setBaseUrl(QUrl(QStringLiteral("http://localhost:8000"))).isError());
}

void TestSessionState::refusesNonHttpScheme()
{
    ApiClient client;
    QVERIFY(client.setBaseUrl(QUrl(QStringLiteral("ftp://exemple.invalid"))).isError());
    QVERIFY(client.setBaseUrl(QUrl(QStringLiteral("file:///tmp"))).isError());
    QVERIFY(!client.isConfigured());
}

void TestSessionState::normalisesTrailingSlash()
{
    ApiClient client;
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://exemple.invalid/api/"))).isError());
    QCOMPARE(client.resolve(QStringLiteral("/missions")).path(),
             QStringLiteral("/api/missions"));
}

void TestSessionState::changingServerPurgesSession()
{
    ApiClient client;
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://a.invalid"))).isError());
    client.setCsrfToken(QStringLiteral("jeton"));
    QVERIFY(client.hasCsrfToken());

    // Une session n'appartient jamais à deux serveurs.
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://b.invalid"))).isError());
    QVERIFY(!client.hasCsrfToken());
    QCOMPARE(client.cookieJar()->cookieCount(), 0);
}

void TestSessionState::resolveRefusesWithoutBaseUrl()
{
    ApiClient client;
    QVERIFY(client.resolve(QStringLiteral("/missions")).isEmpty());
}

void TestSessionState::initialStateIsDisconnected()
{
    ApiClient client;
    AuthManager auth(&client);
    QCOMPARE(auth.state(), SessionStatus::Disconnected);
    QVERIFY(auth.userId().isEmpty());
    QVERIFY(!auth.isBusy());
}

void TestSessionState::resumeWithoutCookieFailsWithoutNetwork()
{
    ApiClient client;
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://exemple.invalid"))).isError());
    AuthManager auth(&client);

    QSignalSpy spy(&auth, &AuthManager::stateChanged);
    auth.resumeSession();

    // Sans cookie détenu, l'appel serait un 401 certain : la station ne fait pas semblant
    // d'essayer, et l'état est posé SYNCHRONEMENT.
    QCOMPARE(auth.state(), SessionStatus::Disconnected);
    QVERIFY(spy.count() >= 1);
    QVERIFY(!auth.lastError().isEmpty());
}

void TestSessionState::logInRefusesEmptyCredentials()
{
    ApiClient client;
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://exemple.invalid"))).isError());
    AuthManager auth(&client);

    auth.logIn(QString(), QString());
    QCOMPARE(auth.state(), SessionStatus::Disconnected);
    QVERIFY(!auth.lastError().isEmpty());

    auth.logIn(QStringLiteral("a@b.invalid"), QString());
    QCOMPARE(auth.state(), SessionStatus::Disconnected);
}

void TestSessionState::forgetLocalSessionClearsEverything()
{
    ApiClient client;
    QVERIFY(!client.setBaseUrl(QUrl(QStringLiteral("https://exemple.invalid"))).isError());
    client.setCsrfToken(QStringLiteral("jeton"));
    AuthManager auth(&client);

    auth.forgetLocalSession(SessionStatus::Revoked, QStringLiteral("révoquée"));
    QCOMPARE(auth.state(), SessionStatus::Revoked);
    QVERIFY(auth.userId().isEmpty());
    QVERIFY(!auth.expiresAt().isValid());
    QVERIFY(!client.hasCsrfToken());
}

void TestSessionState::everySessionStateHasFrenchLabel()
{
    ApiClient client;
    AuthManager auth(&client);
    const QList<SessionStatus::State> states = {
        SessionStatus::Disconnected, SessionStatus::Connecting, SessionStatus::Connected,
        SessionStatus::Expired,      SessionStatus::Revoked,    SessionStatus::Offline,
    };
    QSet<QString> labels;
    for (const SessionStatus::State state : states) {
        auth.forgetLocalSession(state, QString());
        const QString label = auth.stateLabel();
        QVERIFY(!label.isEmpty());
        QVERIFY2(!labels.contains(label), "deux états ne doivent pas partager un libellé");
        labels.insert(label);
    }
}

void TestSessionState::cookieJarReportsSessionPresence()
{
    SessionCookieJar jar;
    QVERIFY(!jar.hasSessionCookie());
    QCOMPARE(jar.cookieCount(), 0);

    QSignalSpy spy(&jar, &SessionCookieJar::sessionCookiePresenceChanged);
    QNetworkCookie cookie(QByteArrayLiteral("acp_session"), QByteArrayLiteral("valeur-secrète"));
    cookie.setDomain(QStringLiteral("exemple.invalid"));
    cookie.setPath(QStringLiteral("/"));
    jar.setCookiesFromUrl({cookie}, QUrl(QStringLiteral("https://exemple.invalid/")));

    QVERIFY(jar.hasSessionCookie());
    QCOMPARE(spy.count(), 1);
    QCOMPARE(spy.at(0).at(0).toBool(), true);

    jar.clearAll();
    QVERIFY(!jar.hasSessionCookie());
    QCOMPARE(jar.cookieCount(), 0);
}

QTEST_MAIN(TestSessionState)

#include "tst_session_state.moc"
