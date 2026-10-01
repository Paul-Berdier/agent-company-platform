// Garde d'instance unique : second verrou refusé avec le message français, code de sortie 3,
// verrou repris après la fermeture de la première instance.

#include "app/GardeInstance.h"

#include <QTemporaryDir>
#include <QTest>

using namespace acp;

class TestInstanceUnique : public QObject
{
    Q_OBJECT

private slots:
    void secondVerrouRefuse();
    void cheminParDefautSousLeDossierLocal();
};

void TestInstanceUnique::secondVerrouRefuse()
{
    QTemporaryDir dossier;
    QVERIFY(dossier.isValid());
    const QString chemin = dossier.filePath(QStringLiteral("sous/instance.lock"));
    {
        GardeInstance premiere(chemin);
        QString raison;
        QVERIFY2(premiere.acquerir(&raison), qPrintable(raison));
        QVERIFY(premiere.estAcquise());

        GardeInstance seconde(chemin);
        QVERIFY(!seconde.acquerir(&raison));
        QVERIFY(!seconde.estAcquise());
        QCOMPARE(raison, GardeInstance::messageSecondeInstance());
        QVERIFY(raison.contains(QStringLiteral("déjà ouverte")));
        QCOMPARE(GardeInstance::kCodeSecondeInstance, 3);
    }
    // La première instance fermée, le verrou se reprend.
    GardeInstance suivante(chemin);
    QVERIFY(suivante.acquerir());
}

void TestInstanceUnique::cheminParDefautSousLeDossierLocal()
{
    QCoreApplication::setOrganizationName(QStringLiteral("Agent Company Platform"));
    QCoreApplication::setApplicationName(QStringLiteral("Station de travail"));
    const QString chemin = GardeInstance::cheminParDefaut();
    QVERIFY(chemin.endsWith(QStringLiteral("Agent Company Platform/Station de travail/instance.lock")));
    // Le test ne prend PAS ce verrou : il appartient à la station réelle du poste.
    GardeInstance vide{QString()};
    QString raison;
    QVERIFY(!vide.acquerir(&raison));
    QVERIFY(!raison.isEmpty());
}

QTEST_GUILESS_MAIN(TestInstanceUnique)

#include "tst_instance_unique.moc"
