// Entrée `ACPH` du coffre : format, bornes, refus d'une entrée étrangère ou corrompue, et
// aller-retour réel dans le Gestionnaire d'identification Windows (nom de test unique).

#include "storage/JetonsCoffre.h"
#include "support/CoffreMemoire.h"

#ifdef Q_OS_WIN
#include "storage/WindowsCredentialVault.h"
#endif

#include <QRegularExpression>
#include <QTest>
#include <QUuid>

using namespace acp;
using namespace acp::test;

namespace {
const QUrl kServeur(QStringLiteral("https://hermes-acp.test"));
const QString kFournisseur = QStringLiteral("self-hosted");
} // namespace

class TestJetonsCoffre : public QObject
{
    Q_OBJECT

private slots:
    void cleEtServeurCanonique();
    void allerRetourDuFormat();
    void tailleBorneeSansTroncature();
    void entreeDUnAutreServeurRefuseeEtEffacee();
    void entreeDUnAutreFournisseurRefuseeEtEffacee();
    void entreeCorrompueIgnoreeEtEffacee();
    void absenceNEstPasUneAnomalie();
    void allerRetourReelWindows();
};

void TestJetonsCoffre::cleEtServeurCanonique()
{
    QCOMPARE(JetonsCoffre::serveurCanonique(QUrl(QStringLiteral("HTTPS://Hermes-ACP.test/"))),
             QStringLiteral("https://hermes-acp.test"));
    QCOMPARE(JetonsCoffre::serveurCanonique(QUrl(QStringLiteral("https://h.test:8443/sous/chemin//"))),
             QStringLiteral("https://h.test:8443/sous/chemin"));
    static const QRegularExpression forme(QStringLiteral("^hermes\\.rt\\.v1\\.[0-9a-f]{64}$"));
    QVERIFY(forme.match(JetonsCoffre::cleDe(kServeur)).hasMatch());
    QCOMPARE(JetonsCoffre::cleDe(QUrl(QStringLiteral("https://HERMES-ACP.test/"))), JetonsCoffre::cleDe(kServeur));
    QVERIFY(JetonsCoffre::cleDe(QUrl(QStringLiteral("https://autre.test"))) != JetonsCoffre::cleDe(kServeur));
}

void TestJetonsCoffre::allerRetourDuFormat()
{
    CoffreMemoire coffre;
    JetonsCoffre jetons(&coffre);
    QVERIFY(jetons.memoriser(kServeur, kFournisseur, QStringLiteral("proprietaire"),
                             QByteArrayLiteral("authelia_rt_synthetique")).ok);
    const QByteArray brut = coffre.entrees.value(JetonsCoffre::cleDe(kServeur));
    QVERIFY(brut.startsWith("ACPH"));
    QCOMPARE(static_cast<int>(brut.at(4)), 1);
    EntreeJetons entree;
    QVERIFY(JetonsCoffre::decoder(brut, entree));
    QCOMPARE(entree.serveur, QStringLiteral("https://hermes-acp.test"));
    QCOMPARE(entree.fournisseur, kFournisseur);
    QCOMPARE(entree.utilisateur, QStringLiteral("proprietaire"));
    QCOMPARE(entree.jeton, QByteArrayLiteral("authelia_rt_synthetique"));

    EntreeJetons relue;
    QVERIFY(jetons.relire(kServeur, kFournisseur, relue).ok);
    QCOMPARE(relue.jeton, QByteArrayLiteral("authelia_rt_synthetique"));
    QVERIFY(jetons.contient(kServeur));
    QVERIFY(jetons.oublier(kServeur).ok);
    QVERIFY(!jetons.contient(kServeur));
}

void TestJetonsCoffre::tailleBorneeSansTroncature()
{
    CoffreMemoire coffre;
    JetonsCoffre jetons(&coffre);
    // En-tête 5 + 4 × 2 + serveur (23) + fournisseur (11) + utilisateur (1) = 48 octets.
    const qsizetype fixe = 5 + 8 + JetonsCoffre::serveurCanonique(kServeur).size() + kFournisseur.size() + 1;
    QVERIFY(jetons.memoriser(kServeur, kFournisseur, QStringLiteral("u"),
                             QByteArray(JetonsCoffre::kTailleMax - fixe, 'a')).ok);
    QCOMPARE(coffre.entrees.value(JetonsCoffre::cleDe(kServeur)).size(), JetonsCoffre::kTailleMax);
    QVERIFY(jetons.oublier(kServeur).ok);
    const VaultResult refus = jetons.memoriser(kServeur, kFournisseur, QStringLiteral("u"),
                                               QByteArray(JetonsCoffre::kTailleMax - fixe + 1, 'a'));
    QVERIFY(!refus.ok);
    QVERIFY(refus.reason.contains(QStringLiteral("rien n'est tronqué")));
    QVERIFY(coffre.entrees.isEmpty());
    QVERIFY(!jetons.memoriser(kServeur, kFournisseur, QStringLiteral("u"), QByteArray()).ok);
}

void TestJetonsCoffre::entreeDUnAutreServeurRefuseeEtEffacee()
{
    CoffreMemoire coffre;
    JetonsCoffre jetons(&coffre);
    // Entrée posée sous la clé de kServeur mais portant un autre serveur.
    const QByteArray etrangere = JetonsCoffre::encoder(
        EntreeJetons{QStringLiteral("https://autre.test"), kFournisseur, QStringLiteral("u"),
                     QByteArrayLiteral("jeton-etranger")});
    coffre.entrees.insert(JetonsCoffre::cleDe(kServeur), etrangere);
    EntreeJetons entree;
    const VaultResult lecture = jetons.relire(kServeur, kFournisseur, entree);
    QVERIFY(!lecture.ok);
    QVERIFY(lecture.reason.contains(QStringLiteral("autre serveur")));
    QVERIFY(entree.jeton.isEmpty());
    QVERIFY(coffre.entrees.isEmpty());
}

void TestJetonsCoffre::entreeDUnAutreFournisseurRefuseeEtEffacee()
{
    CoffreMemoire coffre;
    JetonsCoffre jetons(&coffre);
    QVERIFY(jetons.memoriser(kServeur, QStringLiteral("nous-portal"), QStringLiteral("u"),
                             QByteArrayLiteral("jeton")).ok);
    EntreeJetons entree;
    const VaultResult lecture = jetons.relire(kServeur, kFournisseur, entree);
    QVERIFY(!lecture.ok);
    QVERIFY(lecture.reason.contains(QStringLiteral("autre fournisseur")));
    QVERIFY(coffre.entrees.isEmpty());
}

void TestJetonsCoffre::entreeCorrompueIgnoreeEtEffacee()
{
    const QList<QByteArray> corrompues = {
        QByteArrayLiteral("pas du tout ACPH"),
        QByteArrayLiteral("ACPH\x02\x00\x00"),
        QByteArray("ACPH\x01\x00\x30", 7),
        QByteArray("ACPH\x01\x00\x01h\x00\x01s\x00\x01u\x00\x00", 16),
    };
    for (const QByteArray &brut : corrompues) {
        CoffreMemoire coffre;
        JetonsCoffre jetons(&coffre);
        coffre.entrees.insert(JetonsCoffre::cleDe(kServeur), brut);
        EntreeJetons entree;
        bool introuvable = true;
        const VaultResult lecture = jetons.relire(kServeur, kFournisseur, entree, &introuvable);
        QVERIFY2(!lecture.ok, brut.constData());
        QVERIFY(!introuvable);
        QVERIFY(lecture.reason.contains(QStringLiteral("effacée")));
        QVERIFY(coffre.entrees.isEmpty());
    }
}

void TestJetonsCoffre::absenceNEstPasUneAnomalie()
{
    CoffreMemoire coffre;
    JetonsCoffre jetons(&coffre);
    EntreeJetons entree;
    bool introuvable = false;
    QVERIFY(!jetons.relire(kServeur, kFournisseur, entree, &introuvable).ok);
    QVERIFY(introuvable);
    QCOMPARE(coffre.effacements, 0);
    QVERIFY(jetons.oublier(kServeur).ok);
}

void TestJetonsCoffre::allerRetourReelWindows()
{
#ifdef Q_OS_WIN
    // Nom d'application unique : l'entrée réelle du produit n'est jamais touchée.
    const QString application = QStringLiteral("AcpDesktopTest-%1")
                                    .arg(QUuid::createUuid().toString(QUuid::WithoutBraces));
    WindowsCredentialVault coffre(application);
    JetonsCoffre jetons(&coffre);
    QVERIFY(!jetons.contient(kServeur));
    const VaultResult ecriture = jetons.memoriser(kServeur, kFournisseur, QStringLiteral("proprietaire"),
                                                  QByteArrayLiteral("jeton-synthetique-de-test"));
    QVERIFY2(ecriture.ok, qPrintable(ecriture.reason));
    QVERIFY(jetons.contient(kServeur));
    EntreeJetons entree;
    const VaultResult lecture = jetons.relire(kServeur, kFournisseur, entree);
    QVERIFY2(lecture.ok, qPrintable(lecture.reason));
    QCOMPARE(entree.jeton, QByteArrayLiteral("jeton-synthetique-de-test"));
    QVERIFY(jetons.oublier(kServeur).ok);
    QVERIFY(!jetons.contient(kServeur));
#else
    QSKIP("Aller-retour réel réservé à Windows : hors Windows, le coffre refuse de stocker.");
#endif
}

QTEST_APPLESS_MAIN(TestJetonsCoffre)

#include "tst_jetons_coffre.moc"
