// Expurgation des secrets dans tout ce qui sort par écrit.
//
// L'audit est explicite : « rien ne protège les journaux, les rapports de plantage et les
// fichiers de diagnostic du poste client ». Ces tests décrivent ce que le filtre attrape,
// et disent aussi ce qu'il n'attrape PAS — un filtre dont on surestime la portée est
// pire qu'un filtre absent.
//
// AVERTISSEMENT : jamais compilé, jamais exécuté.

#include "diagnostics/Redaction.h"

#include <QTest>

using namespace acp;

class TestRedaction : public QObject
{
    Q_OBJECT

private slots:
    void redactsSignedDownloadToken();
    void keepsRestOfUrlIntact();
    void redactsSensitiveHeaders();
    void redactsSessionCookie();
    void redactsJsonSecrets();
    void leavesOrdinaryTextAlone();
    void doesNotClaimToFindArbitrarySecrets();
};

void TestRedaction::redactsSignedDownloadToken()
{
    const QString redacted = redactUrl(QStringLiteral(
        "https://exemple.invalid/artifacts/42/content?token=abcdef123456&range=0-10"));
    QVERIFY(!redacted.contains(QStringLiteral("abcdef123456")));
    QVERIFY(redacted.contains(QString::fromUtf8(kRedactionPlaceholder)));
}

void TestRedaction::keepsRestOfUrlIntact()
{
    // Un journal expurgé doit rester utile : le chemin et les autres paramètres sont
    // conservés, seule la valeur du jeton disparaît.
    const QString redacted = redactUrl(QStringLiteral(
        "https://exemple.invalid/artifacts/42/content?token=secret&range=0-10"));
    QVERIFY(redacted.contains(QStringLiteral("/artifacts/42/content")));
    QVERIFY(redacted.contains(QStringLiteral("range=0-10")));
}

void TestRedaction::redactsSensitiveHeaders()
{
    const QString redacted = redactSecrets(QStringLiteral(
        "X-CSRF-Token: abc123\nAuthorization: Bearer xyz\nAccept: application/json"));
    QVERIFY(!redacted.contains(QStringLiteral("abc123")));
    QVERIFY(!redacted.contains(QStringLiteral("xyz")));
    // L'en-tête inoffensif reste lisible.
    QVERIFY(redacted.contains(QStringLiteral("application/json")));
}

void TestRedaction::redactsSessionCookie()
{
    const QString redacted =
        redactSecrets(QStringLiteral("Cookie: acp_session=valeur-secrète; Path=/"));
    QVERIFY(!redacted.contains(QStringLiteral("valeur-secrète")));
}

void TestRedaction::redactsJsonSecrets()
{
    const QString redacted = redactSecrets(QStringLiteral(
        "{\"email\":\"a@b.invalid\",\"password\":\"motdepasse\",\"csrf_token\":\"jeton\"}"));
    QVERIFY(!redacted.contains(QStringLiteral("motdepasse")));
    QVERIFY(!redacted.contains(QStringLiteral("jeton")));
    // L'identifiant n'est pas un secret et reste affiché : il sert au diagnostic.
    QVERIFY(redacted.contains(QStringLiteral("a@b.invalid")));
}

void TestRedaction::leavesOrdinaryTextAlone()
{
    const QString message = QStringLiteral("Le serveur a répondu 503 : base indisponible.");
    QCOMPARE(redactSecrets(message), message);
    QCOMPARE(redactSecrets(QString()), QString());
}

void TestRedaction::doesNotClaimToFindArbitrarySecrets()
{
    // Limite ASSUMÉE et inscrite : le filtre reconnaît des FORMES connues, pas un secret
    // quelconque dans un texte quelconque. La vraie garantie est qu'aucun secret n'est
    // passé à la journalisation ; ce filtre est une défense en profondeur.
    const QString opaque = QStringLiteral("valeur=8f3c1a9e7b2d4f60");
    QCOMPARE(redactSecrets(opaque), opaque);
}

QTEST_APPLESS_MAIN(TestRedaction)

#include "tst_redaction.moc"
