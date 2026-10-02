// Mise à jour d'une liste relue (JsonListModel::setItems) : avec une clé, seules les lignes
// changées sont signalées (aucune réinitialisation), dans l'ordre servi ; sans clé, ou avec une
// clé vide ou en double, le modèle est réinitialisé (jamais une ligne rattachée à une autre).
// QAbstractItemModelTester contrôle la cohérence de chaque signal émis.

#include "models/JsonListModel.h"

#include <QAbstractItemModelTester>
#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

using namespace acp;

namespace {

QJsonObject ligne(const QString &id, const QString &texte)
{
    return QJsonObject{{QStringLiteral("id"), id}, {QStringLiteral("texte"), texte}};
}

QStringList identifiants(const JsonListModel &modele)
{
    QStringList resultat;
    for (int rang = 0; rang < modele.count(); ++rang) {
        resultat.append(modele.itemAt(rang).value(QStringLiteral("id")).toString());
    }
    return resultat;
}

} // namespace

class TestModeleListe : public QObject
{
    Q_OBJECT

private slots:
    void relectureIdentiqueNeSignaleRien();
    void ligneModifieeSignaleeSansReinitialisation();
    void insertionsRetraitsEtDeplacements_data();
    void insertionsRetraitsEtDeplacements();
    void cleComposee();
    void sansCleOuCleDouteuseReinitialise();
};

void TestModeleListe::relectureIdentiqueNeSignaleRien()
{
    JsonListModel modele;
    modele.setCle({QStringLiteral("id")});
    QAbstractItemModelTester testeur(&modele, QAbstractItemModelTester::FailureReportingMode::QtTest);
    const QJsonArray liste{ligne(QStringLiteral("q_1"), QStringLiteral("un")),
                           ligne(QStringLiteral("q_2"), QStringLiteral("deux"))};
    modele.setItems(liste);
    QSignalSpy reinitialisations(&modele, &QAbstractItemModel::modelReset);
    QSignalSpy changements(&modele, &QAbstractItemModel::dataChanged);
    QSignalSpy insertions(&modele, &QAbstractItemModel::rowsInserted);
    QSignalSpy retraits(&modele, &QAbstractItemModel::rowsRemoved);
    modele.setItems(liste);
    QCOMPARE(reinitialisations.count(), 0);
    QCOMPARE(changements.count(), 0);
    QCOMPARE(insertions.count(), 0);
    QCOMPARE(retraits.count(), 0);
}

void TestModeleListe::ligneModifieeSignaleeSansReinitialisation()
{
    JsonListModel modele;
    modele.setCle({QStringLiteral("id")});
    QAbstractItemModelTester testeur(&modele, QAbstractItemModelTester::FailureReportingMode::QtTest);
    modele.setItems({ligne(QStringLiteral("q_1"), QStringLiteral("un")), ligne(QStringLiteral("q_2"), QStringLiteral("deux"))});
    QSignalSpy reinitialisations(&modele, &QAbstractItemModel::modelReset);
    QSignalSpy changements(&modele, &QAbstractItemModel::dataChanged);
    modele.setItems({ligne(QStringLiteral("q_1"), QStringLiteral("un")), ligne(QStringLiteral("q_2"), QStringLiteral("deux bis"))});
    QCOMPARE(reinitialisations.count(), 0);
    QCOMPARE(changements.count(), 1);
    QCOMPARE(changements.at(0).at(0).value<QModelIndex>().row(), 1);
    QCOMPARE(modele.itemAt(1).value(QStringLiteral("texte")).toString(), QStringLiteral("deux bis"));
}

void TestModeleListe::insertionsRetraitsEtDeplacements_data()
{
    QTest::addColumn<QStringList>("avant");
    QTest::addColumn<QStringList>("apres");
    const auto l = [](std::initializer_list<const char *> noms) {
        QStringList resultat;
        for (const char *nom : noms) {
            resultat.append(QString::fromLatin1(nom));
        }
        return resultat;
    };
    QTest::newRow("retrait en tete") << l({"a", "b", "c"}) << l({"b", "c"});
    QTest::newRow("retrait au milieu") << l({"a", "b", "c"}) << l({"a", "c"});
    QTest::newRow("ajout en tete") << l({"b", "c"}) << l({"a", "b", "c"});
    QTest::newRow("ajout en fin") << l({"a"}) << l({"a", "b"});
    QTest::newRow("inversion") << l({"a", "b", "c"}) << l({"c", "b", "a"});
    QTest::newRow("rotation") << l({"a", "b", "c", "d"}) << l({"b", "c", "d", "a"});
    QTest::newRow("melange") << l({"a", "b", "c", "d"}) << l({"e", "c", "a", "f"});
    QTest::newRow("videe") << l({"a", "b"}) << QStringList{};
    QTest::newRow("remplie") << QStringList{} << l({"a", "b"});
}

void TestModeleListe::insertionsRetraitsEtDeplacements()
{
    QFETCH(QStringList, avant);
    QFETCH(QStringList, apres);
    JsonListModel modele;
    modele.setCle({QStringLiteral("id")});
    QAbstractItemModelTester testeur(&modele, QAbstractItemModelTester::FailureReportingMode::QtTest);
    QJsonArray premiere;
    for (const QString &id : std::as_const(avant)) {
        premiere.append(ligne(id, QStringLiteral("v1-") + id));
    }
    modele.setItems(premiere);
    // Index persistant d'une ligne conservée : il doit la suivre (un délégué la suit de même).
    QPersistentModelIndex suivi;
    QString idSuivi;
    for (int rang = 0; rang < avant.size(); ++rang) {
        if (apres.contains(avant.at(rang))) {
            suivi = modele.index(rang);
            idSuivi = avant.at(rang);
            break;
        }
    }
    QSignalSpy reinitialisations(&modele, &QAbstractItemModel::modelReset);
    QSignalSpy compte(&modele, &JsonListModel::countChanged);
    QJsonArray seconde;
    for (const QString &id : std::as_const(apres)) {
        seconde.append(ligne(id, QStringLiteral("v2-") + id));
    }
    modele.setItems(seconde);
    QCOMPARE(reinitialisations.count(), 0);
    QCOMPARE(identifiants(modele), apres);
    for (int rang = 0; rang < apres.size(); ++rang) {
        QCOMPARE(modele.itemAt(rang).value(QStringLiteral("texte")).toString(), QStringLiteral("v2-") + apres.at(rang));
    }
    QCOMPARE(compte.count(), avant.size() == apres.size() ? 0 : 1);
    if (!idSuivi.isEmpty()) {
        QVERIFY(suivi.isValid());
        QCOMPARE(suivi.data(JsonListModel::IdRole).toString(), idSuivi);
    }
}

void TestModeleListe::cleComposee()
{
    JsonListModel modele;
    modele.setCle({QStringLiteral("tableau"), QStringLiteral("carte")});
    QAbstractItemModelTester testeur(&modele, QAbstractItemModelTester::FailureReportingMode::QtTest);
    const auto carte = [](const QString &tableau, const QString &id) {
        return QJsonObject{{QStringLiteral("tableau"), tableau}, {QStringLiteral("carte"), id}};
    };
    // Même carte sur deux tableaux : deux lignes distinctes.
    modele.setItems({carte(QStringLiteral("t1"), QStringLiteral("c1")), carte(QStringLiteral("t2"), QStringLiteral("c1"))});
    QSignalSpy reinitialisations(&modele, &QAbstractItemModel::modelReset);
    QSignalSpy retraits(&modele, &QAbstractItemModel::rowsRemoved);
    modele.setItems({carte(QStringLiteral("t2"), QStringLiteral("c1"))});
    QCOMPARE(reinitialisations.count(), 0);
    QCOMPARE(retraits.count(), 1);
    QCOMPARE(modele.itemAt(0).value(QStringLiteral("tableau")).toString(), QStringLiteral("t2"));
}

void TestModeleListe::sansCleOuCleDouteuseReinitialise()
{
    // Sans clé : réinitialisation, comme avant.
    JsonListModel libre;
    libre.setItems({ligne(QStringLiteral("a"), QStringLiteral("1"))});
    QSignalSpy reinitialisationsLibres(&libre, &QAbstractItemModel::modelReset);
    libre.setItems({ligne(QStringLiteral("a"), QStringLiteral("2"))});
    QCOMPARE(reinitialisationsLibres.count(), 1);

    JsonListModel modele;
    modele.setCle({QStringLiteral("id")});
    QAbstractItemModelTester testeur(&modele, QAbstractItemModelTester::FailureReportingMode::QtTest);
    modele.setItems({ligne(QStringLiteral("a"), QStringLiteral("1")), ligne(QStringLiteral("b"), QStringLiteral("2"))});
    QSignalSpy reinitialisations(&modele, &QAbstractItemModel::modelReset);
    // Clé en double : aucune ligne ne doit hériter du délégué d'une autre.
    modele.setItems({ligne(QStringLiteral("a"), QStringLiteral("1")), ligne(QStringLiteral("a"), QStringLiteral("3"))});
    QCOMPARE(reinitialisations.count(), 1);
    QCOMPARE(modele.count(), 2);
    // Clé absente.
    modele.setItems({QJsonObject{{QStringLiteral("texte"), QStringLiteral("sans identifiant")}}});
    QCOMPARE(reinitialisations.count(), 2);
    QCOMPARE(modele.count(), 1);
}

QTEST_GUILESS_MAIN(TestModeleListe)
#include "tst_modele_liste.moc"
