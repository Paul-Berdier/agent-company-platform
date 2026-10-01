// PKCE (RFC 7636) et état de la connexion native.
//
// Vecteur de référence : RFC 7636, annexe B. La transformation S256 doit être exactement
// celle de Hermes (native_flow._s256), faute de quoi chaque échange de code échouerait.

#include "auth/PairePkce.h"

#include <QSet>
#include <QTest>

using namespace acp;

class TestPkce : public QObject
{
    Q_OBJECT

private slots:
    void vecteurDeLaRfc7636();
    void paireGenereeConforme();
    void tiragesTousDistincts();
    void alphabetEtLongueursDuVerificateur();
    void comparaisonATempsConstant();
    void effacementComplet();
};

void TestPkce::vecteurDeLaRfc7636()
{
    QCOMPARE(PairePkce::defiS256(QByteArrayLiteral("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")),
             QByteArrayLiteral("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"));
}

void TestPkce::paireGenereeConforme()
{
    const PairePkce paire = PairePkce::generer();
    QCOMPARE(paire.verificateur().size(), 86);
    QVERIFY(PairePkce::verificateurValide(paire.verificateur()));
    QCOMPARE(paire.defi(), PairePkce::defiS256(paire.verificateur()));
    QCOMPARE(paire.defi().size(), 43);
    QCOMPARE(paire.etat().size(), 43);
    for (const QByteArray &valeur : {paire.verificateur(), paire.defi(), paire.etat()}) {
        QVERIFY2(!valeur.contains('=') && !valeur.contains('+') && !valeur.contains('/'),
                 "base64url sans remplissage attendu");
    }
    QVERIFY(paire.etat() != paire.verificateur().left(43));
}

void TestPkce::tiragesTousDistincts()
{
    QSet<QByteArray> verificateurs;
    QSet<QByteArray> etats;
    for (int index = 0; index < 1000; ++index) {
        const PairePkce paire = PairePkce::generer();
        verificateurs.insert(paire.verificateur());
        etats.insert(paire.etat());
    }
    QCOMPARE(verificateurs.size(), 1000);
    QCOMPARE(etats.size(), 1000);
}

void TestPkce::alphabetEtLongueursDuVerificateur()
{
    QVERIFY(!PairePkce::verificateurValide(QByteArray(42, 'a')));
    QVERIFY(PairePkce::verificateurValide(QByteArray(43, 'a')));
    QVERIFY(PairePkce::verificateurValide(QByteArray(128, 'a')));
    QVERIFY(!PairePkce::verificateurValide(QByteArray(129, 'a')));
    QVERIFY(PairePkce::verificateurValide(QByteArrayLiteral("abc-._~ABC0123456789abcdefghijklmnopqrstuvwxyz")));
    QVERIFY(!PairePkce::verificateurValide(QByteArray(42, 'a') + '+'));
    QVERIFY(!PairePkce::verificateurValide(QByteArray(42, 'a') + ' '));
    QVERIFY(!PairePkce::verificateurValide(QByteArray(42, 'a') + "\xc3\xa9"));
}

void TestPkce::comparaisonATempsConstant()
{
    QVERIFY(egalATempsConstant(QByteArrayLiteral("etat-attendu"), QByteArrayLiteral("etat-attendu")));
    QVERIFY(!egalATempsConstant(QByteArrayLiteral("etat-attendu"), QByteArrayLiteral("etat-attendX")));
    QVERIFY(!egalATempsConstant(QByteArrayLiteral("etat-attendu"), QByteArrayLiteral("etat")));
    QVERIFY(!egalATempsConstant(QByteArrayLiteral("etat-attendu"), QByteArray()));
    // Un état attendu vide ne valide jamais rien, pas même un état reçu vide.
    QVERIFY(!egalATempsConstant(QByteArray(), QByteArray()));
}

void TestPkce::effacementComplet()
{
    PairePkce paire = PairePkce::generer();
    QVERIFY(!paire.estVide());
    paire.effacer();
    QVERIFY(paire.estVide());
    QVERIFY(paire.verificateur().isEmpty() && paire.defi().isEmpty() && paire.etat().isEmpty());
    PairePkce source = PairePkce::generer();
    const QByteArray etat = source.etat();
    PairePkce cible = std::move(source);
    QCOMPARE(cible.etat(), etat);
}

QTEST_APPLESS_MAIN(TestPkce)

#include "tst_pkce.moc"
