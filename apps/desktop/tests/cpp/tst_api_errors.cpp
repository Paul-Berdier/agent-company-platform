// Analyse des erreurs d'API et politique de réessai sémantique.
//
// Le point le plus important tenu ici : une MUTATION SANS CLÉ D'IDEMPOTENCE n'est JAMAIS
// rejouée. Le protocole l'interdit, et une mission relancée deux fois est un dégât réel.

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "api/IdempotencyKey.h"

#include <QSet>
#include <QTest>

using namespace acp;

class TestApiErrors : public QObject
{
    Q_OBJECT

private slots:
    void mapsHttpStatusToFamily_data();
    void mapsHttpStatusToFamily();
    void extractsFastApiDetail();
    void extractsValidationDetail();
    void ignoresUnparsableBody();
    void titlesAreFrenchAndDistinct();
    void retryabilityFollowsFamily();
    void plannedAttemptsRefuseReplayOfUnkeyedMutation();
    void shouldRetryNeverReplaysUnkeyedMutation();
    void retryDelayHonoursRetryAfter();
    void idempotencyKeyValidation();
    void generatedKeysAreValid();
    void truncatesOverlongDetail();
};

void TestApiErrors::mapsHttpStatusToFamily_data()
{
    QTest::addColumn<int>("status");
    QTest::addColumn<int>("kind");

    QTest::newRow("401") << 401 << int(ApiFailure::Unauthorized);
    QTest::newRow("403") << 403 << int(ApiFailure::Forbidden);
    QTest::newRow("404") << 404 << int(ApiFailure::NotFound);
    QTest::newRow("409") << 409 << int(ApiFailure::Conflict);
    QTest::newRow("422") << 422 << int(ApiFailure::Unprocessable);
    QTest::newRow("429") << 429 << int(ApiFailure::RateLimited);
    QTest::newRow("500") << 500 << int(ApiFailure::ServerError);
    QTest::newRow("503") << 503 << int(ApiFailure::ServiceUnavailable);
}

void TestApiErrors::mapsHttpStatusToFamily()
{
    QFETCH(int, status);
    QFETCH(int, kind);
    const ApiError error = ApiError::fromHttpStatus(status, QString());
    QCOMPARE(error.kindValue(), kind);
    QCOMPARE(error.httpStatus(), status);
}

void TestApiErrors::extractsFastApiDetail()
{
    const QString detail =
        extractProblemDetail(QByteArrayLiteral("{\"detail\":\"Requête refusée\"}"));
    QCOMPARE(detail, QStringLiteral("Requête refusée"));
}

void TestApiErrors::extractsValidationDetail()
{
    const QByteArray body = QByteArrayLiteral(
        "{\"detail\":[{\"msg\":\"champ obligatoire\",\"loc\":[\"body\",\"title\"]}]}");
    const QString detail = extractProblemDetail(body);
    QVERIFY(detail.contains(QStringLiteral("champ obligatoire")));
    QVERIFY(detail.contains(QStringLiteral("body.title")));
}

void TestApiErrors::ignoresUnparsableBody()
{
    // Un corps illisible ne doit pas se retrouver affiché tel quel dans l'interface.
    QVERIFY(extractProblemDetail(QByteArrayLiteral("<html>500</html>")).isEmpty());
    QVERIFY(extractProblemDetail(QByteArray()).isEmpty());
}

void TestApiErrors::titlesAreFrenchAndDistinct()
{
    QSet<QString> titles;
    const QList<ApiFailure::Kind> kinds = {
        ApiFailure::ClientRefusal, ApiFailure::Network,     ApiFailure::Timeout,
        ApiFailure::Cancelled,     ApiFailure::Unauthorized, ApiFailure::Forbidden,
        ApiFailure::NotFound,      ApiFailure::Conflict,     ApiFailure::Unprocessable,
        ApiFailure::RateLimited,   ApiFailure::ServerError,  ApiFailure::ServiceUnavailable,
        ApiFailure::Incompatible,  ApiFailure::InvalidResponse,
    };
    for (const ApiFailure::Kind kind : kinds) {
        const QString title = ApiError(kind, QString()).title();
        QVERIFY2(!title.isEmpty(), "chaque famille doit porter un titre");
        QVERIFY2(!titles.contains(title), "deux familles ne doivent pas partager un titre");
        titles.insert(title);
    }
}

void TestApiErrors::retryabilityFollowsFamily()
{
    QVERIFY(ApiError(ApiFailure::Network, QString()).isRetryable());
    QVERIFY(ApiError(ApiFailure::Timeout, QString()).isRetryable());
    QVERIFY(ApiError(ApiFailure::RateLimited, QString()).isRetryable());
    QVERIFY(ApiError(ApiFailure::ServiceUnavailable, QString()).isRetryable());

    QVERIFY(!ApiError(ApiFailure::Unauthorized, QString()).isRetryable());
    QVERIFY(!ApiError(ApiFailure::Forbidden, QString()).isRetryable());
    QVERIFY(!ApiError(ApiFailure::Conflict, QString()).isRetryable());
    QVERIFY(!ApiError(ApiFailure::Unprocessable, QString()).isRetryable());
    QVERIFY(!ApiError(ApiFailure::Cancelled, QString()).isRetryable());
}

void TestApiErrors::plannedAttemptsRefuseReplayOfUnkeyedMutation()
{
    ApiRequest read;
    read.method = QByteArrayLiteral("GET");
    read.path = QStringLiteral("/missions");
    QCOMPARE(ApiClient::plannedAttempts(read), ApiClient::kMaxAttempts);

    ApiRequest unkeyedMutation;
    unkeyedMutation.method = QByteArrayLiteral("POST");
    unkeyedMutation.path = QStringLiteral("/missions");
    // UNE seule tentative. Aucune exception.
    QCOMPARE(ApiClient::plannedAttempts(unkeyedMutation), 1);

    ApiRequest keyedMutation = unkeyedMutation;
    keyedMutation.idempotencyKey = QStringLiteral("mission.create.abc");
    QCOMPARE(ApiClient::plannedAttempts(keyedMutation), ApiClient::kMaxAttempts);
}

void TestApiErrors::shouldRetryNeverReplaysUnkeyedMutation()
{
    ApiRequest mutation;
    mutation.method = QByteArrayLiteral("POST");
    mutation.path = QStringLiteral("/missions/x/stop");
    const ApiError networkError(ApiFailure::Network, QStringLiteral("coupure"));

    QVERIFY(!ApiClient::shouldRetry(mutation, networkError, 1));

    mutation.idempotencyKey = QStringLiteral("mission.stop.abc");
    QVERIFY(ApiClient::shouldRetry(mutation, networkError, 1));
    // Au-delà du plafond, plus de réessai même avec une clé.
    QVERIFY(!ApiClient::shouldRetry(mutation, networkError, ApiClient::kMaxAttempts));

    // Une erreur non rejouable ne l'est pas davantage avec une clé.
    const ApiError conflict(ApiFailure::Conflict, QStringLiteral("déjà arrêtée"));
    QVERIFY(!ApiClient::shouldRetry(mutation, conflict, 1));
}

void TestApiErrors::retryDelayHonoursRetryAfter()
{
    ApiError limited(ApiFailure::RateLimited, QStringLiteral("trop de flux"), 429);
    limited.setRetryAfterSeconds(5);
    QCOMPARE(ApiClient::retryDelay(limited, 1).count(), 5000);

    const ApiError plain(ApiFailure::Network, QStringLiteral("coupure"));
    const auto first = ApiClient::retryDelay(plain, 1);
    const auto third = ApiClient::retryDelay(plain, 3);
    QVERIFY(first.count() >= 500);
    QVERIFY(third.count() >= first.count());
    QVERIFY(third.count() <= 10000);
}

void TestApiErrors::idempotencyKeyValidation()
{
    QVERIFY(isValidIdempotencyKey(QStringLiteral("a")));
    QVERIFY(isValidIdempotencyKey(QString(kIdempotencyKeyMaxLength, QLatin1Char('x'))));

    QVERIFY(!isValidIdempotencyKey(QString()));
    QVERIFY(!isValidIdempotencyKey(QString(kIdempotencyKeyMaxLength + 1, QLatin1Char('x'))));
    // Espace, caractère de contrôle et caractère accentué sont hors de la plage 33..126.
    QVERIFY(!isValidIdempotencyKey(QStringLiteral("avec espace")));
    QVERIFY(!isValidIdempotencyKey(QStringLiteral("clé")));
    QVERIFY(!isValidIdempotencyKey(QStringLiteral("saut\nligne")));
}

void TestApiErrors::generatedKeysAreValid()
{
    const QString fromAccentedIntent = makeIdempotencyKey(QStringLiteral("création mission"));
    QVERIFY2(isValidIdempotencyKey(fromAccentedIntent),
             "une intention accentuée doit produire une clé ASCII valide");

    const QString empty = makeIdempotencyKey(QString());
    QVERIFY(isValidIdempotencyKey(empty));
    QVERIFY(empty.startsWith(QStringLiteral("acp.")));

    QVERIFY(makeIdempotencyKey(QStringLiteral("x")) != makeIdempotencyKey(QStringLiteral("x")));
}

void TestApiErrors::truncatesOverlongDetail()
{
    const QString huge(5000, QLatin1Char('a'));
    const ApiError error(ApiFailure::ServerError, huge, 500);
    QVERIFY(error.detail().size() < 1100);
    QVERIFY(error.detail().endsWith(QStringLiteral("[…]")));
}

QTEST_APPLESS_MAIN(TestApiErrors)

#include "tst_api_errors.moc"
