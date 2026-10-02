// Analyse des erreurs d'API et politique de réessai sémantique.
//
// Le point le plus important tenu ici : une MUTATION SANS CLÉ D'IDEMPOTENCE n'est JAMAIS
// rejouée. Le protocole l'interdit, et une mission relancée deux fois est un dégât réel.

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "api/IdempotencyKey.h"

#include <QJsonObject>
#include <QMetaEnum>
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
    void readsPluginEnvelope();
    void readsGateEnvelope();
    void readsRoutingRefusals();
    void classifiesUnreachableIdentityProvider();
    void translatesOnlyFixedHermesMessages();
    void networkErrorsAreFrench();
};

void TestApiErrors::readsPluginEnvelope()
{
    // Greffon acp-poste : {"detail": {"code", "message"}}, message déjà en français.
    const QByteArray body = QByteArrayLiteral(
        "{\"detail\":{\"code\":\"question_fermee\",\"message\":\"Cette question est déjà fermée.\"}}");
    const ApiError error = ApiError::fromResponse(409, body);
    QCOMPARE(error.kind(), ApiFailure::Conflict);
    QCOMPARE(error.code(), QStringLiteral("question_fermee"));
    QCOMPARE(error.detail(), QStringLiteral("Cette question est déjà fermée."));
    QVERIFY(!error.isGateRejection());
    QCOMPARE(error.body(), body);
}

void TestApiErrors::readsGateEnvelope()
{
    // Porte de Hermes (middleware.py `_unauth_response`).
    const ApiError error = ApiError::fromResponse(401, QByteArrayLiteral(
        "{\"error\":\"session_expired\",\"detail\":\"Unauthorized\","
        "\"reason\":\"invalid_or_expired_session\",\"login_url\":\"/login\"}"));
    QCOMPARE(error.kind(), ApiFailure::Unauthorized);
    QCOMPARE(error.code(), QStringLiteral("session_expired"));
    QCOMPARE(error.gateReason(), QStringLiteral("invalid_or_expired_session"));
    QVERIFY(error.isGateRejection());
    QCOMPARE(error.detail(), QStringLiteral("non autorisé par la porte de Hermes"));

    // La même forme sans `reason` (refus de /auth/native/refresh) n'est pas la porte.
    const ApiError refresh = ApiError::fromResponse(401, QByteArrayLiteral(
        "{\"error\":\"session_expired\",\"detail\":\"Refresh token expired or invalid; start a new sign-in.\"}"));
    QVERIFY(!refresh.isGateRejection());
    QCOMPARE(refresh.code(), QStringLiteral("session_expired"));
    QCOMPARE(refresh.detail(),
             QStringLiteral("jeton de rafraîchissement expiré ou invalide ; reconnectez-vous"));
}

void TestApiErrors::readsRoutingRefusals()
{
    const ApiError error = ApiError::fromResponse(422, QByteArrayLiteral(
        "{\"detail\":{\"code\":\"table_refusee\",\"message\":\"Table refusée.\","
        "\"refus\":[{\"classe\":\"a\",\"code\":\"aucun_modele\"},{\"classe\":\"b\",\"code\":\"voie_indisponible\"}]}}"));
    QCOMPARE(error.kind(), ApiFailure::Unprocessable);
    QCOMPARE(error.code(), QStringLiteral("table_refusee"));
    QCOMPARE(error.detail(), QStringLiteral("Table refusée."));
    QCOMPARE(error.refusals().size(), 2);
    QCOMPARE(error.refusals().at(1).toObject().value(QStringLiteral("code")).toString(),
             QStringLiteral("voie_indisponible"));
}

void TestApiErrors::classifiesUnreachableIdentityProvider()
{
    const ApiError error = ApiError::fromResponse(503, QByteArrayLiteral(
        "{\"detail\":\"Auth provider 'self-hosted' unreachable\"}"));
    QCOMPARE(error.kind(), ApiFailure::IdentityProviderUnavailable);
    QVERIFY(error.isRetryable());
    QCOMPARE(error.title(), QStringLiteral("Fournisseur d'identité injoignable"));
    QCOMPARE(error.detail(), QStringLiteral("fournisseur d'identité « self-hosted » injoignable"));

    // Un autre 503 reste un service indisponible ordinaire.
    const ApiError other = ApiError::fromResponse(503, QByteArrayLiteral(
        "{\"detail\":\"no auth providers registered\"}"));
    QCOMPARE(other.kind(), ApiFailure::ServiceUnavailable);
    QCOMPARE(other.detail(),
             QStringLiteral("aucun fournisseur de connexion n'est enregistré sur ce serveur"));
}

void TestApiErrors::translatesOnlyFixedHermesMessages()
{
    QCOMPARE(traduireMessageHermes(QStringLiteral("Invalid or expired authorization code.")),
             QStringLiteral("code de connexion invalide ou expiré"));
    // Un message inconnu est rendu tel quel : la station n'invente jamais une cause.
    QCOMPARE(traduireMessageHermes(QStringLiteral("Something unexpected")),
             QStringLiteral("Something unexpected"));
    QCOMPARE(traduireMessageHermes(QStringLiteral("Requête refusée")), QStringLiteral("Requête refusée"));
    // Sauvegarde et fichiers gérés : messages fixes, et préfixes fixes suivis d'un détail rendu tel quel.
    QCOMPARE(traduireMessageHermes(QStringLiteral("Backup not found")),
             QStringLiteral("archive de sauvegarde introuvable sur le serveur"));
    QCOMPARE(traduireMessageHermes(QStringLiteral("Path outside managed files root")),
             QStringLiteral("chemin hors de la racine des fichiers gérés par Hermes"));
    QCOMPARE(traduireMessageHermes(QStringLiteral("Could not delete path: [Errno 13] Permission denied")),
             QStringLiteral("suppression impossible sur le volume de Hermes : [Errno 13] Permission denied"));
    const ApiError introuvable = ApiError::fromResponse(404, QByteArrayLiteral("{\"detail\":\"Backup not found\"}"));
    QCOMPARE(introuvable.detail(), QStringLiteral("archive de sauvegarde introuvable sur le serveur"));
}

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
        ApiFailure::IdentityProviderUnavailable,
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

// Constat de relecture P8 : les erreurs de transport montraient le texte anglais de Qt.
void TestApiErrors::networkErrorsAreFrench()
{
    const QStringList anglais = {QStringLiteral("refused"), QStringLiteral("not found"), QStringLiteral("timed out"),
                                 QStringLiteral("Host "), QStringLiteral("Connection"), QStringLiteral("Unknown"),
                                 QStringLiteral("error")};
    const QMetaEnum reseau = QMetaEnum::fromType<QNetworkReply::NetworkError>();
    for (int index = 0; index < reseau.keyCount(); ++index) {
        const auto code = static_cast<QNetworkReply::NetworkError>(reseau.value(index));
        if (code == QNetworkReply::NoError) {
            continue;
        }
        const QString libelle = libelleErreurReseau(code);
        QVERIFY2(libelle.endsWith(QStringLiteral("(erreur réseau %1)").arg(static_cast<int>(code))), qPrintable(libelle));
        for (const QString &mot : anglais) {
            QVERIFY2(!libelle.contains(mot, Qt::CaseInsensitive), qPrintable(libelle));
        }
    }
    QCOMPARE(libelleErreurReseau(QNetworkReply::HostNotFoundError),
             QStringLiteral("hôte introuvable : vérifiez l'adresse du serveur (erreur réseau 3)"));
    const QMetaEnum socket = QMetaEnum::fromType<QAbstractSocket::SocketError>();
    for (int index = 0; index < socket.keyCount(); ++index) {
        const QString libelle = libelleErreurSocket(static_cast<QAbstractSocket::SocketError>(socket.value(index)));
        for (const QString &mot : anglais) {
            QVERIFY2(!libelle.contains(mot, Qt::CaseInsensitive), qPrintable(libelle));
        }
    }
    QCOMPARE(libelleErreurSocket(QAbstractSocket::ConnectionRefusedError),
             QStringLiteral("connexion refusée : aucun service n'écoute à cette adresse (erreur de socket 0)"));
    // Le transport s'en sert : l'erreur d'un appel vers un port fermé est française.
    const ApiError erreur(ApiFailure::Network, libelleErreurReseau(QNetworkReply::ConnectionRefusedError));
    QVERIFY(erreur.message().startsWith(QStringLiteral("Serveur injoignable : connexion refusée")));
}

QTEST_APPLESS_MAIN(TestApiErrors)

#include "tst_api_errors.moc"
