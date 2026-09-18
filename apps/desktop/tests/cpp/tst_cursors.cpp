// Les deux espaces de curseurs, et la portée qui les embarque.
//
// Le défaut que ces tests empêchent est le plus coûteux du protocole : deux entiers
// indiscernables dans le même champ SSE `id:`. Un client qui les mélange saute ou rejoue
// des événements SANS AUCUNE ERREUR VISIBLE.
//
// L'essentiel de la garantie est tenu par le compilateur (voir les static_assert de
// api/Cursors.h) ; ces tests couvrent ce qui reste vérifiable à l'exécution : les chemins
// construits et l'avancement du curseur.
//
// AVERTISSEMENT : jamais compilé, jamais exécuté.

#include "api/Cursors.h"
#include "events/StreamScope.h"

#include <QTest>

using namespace acp;

class TestCursors : public QObject
{
    Q_OBJECT

private slots:
    void cursorsAreExplicitlyConstructed();
    void runScopeBuildsRunPaths();
    void projectScopeBuildsProjectPaths();
    void scopeKeysNeverCollideBetweenScopes();
    void cursorAdvancesOnlyForward();
    void advancingKeepsScopeType();
};

void TestCursors::cursorsAreExplicitlyConstructed()
{
    const RunCursor run{42};
    const ProjectCursor project{42};
    QCOMPARE(run.value(), qint64(42));
    QCOMPARE(project.value(), qint64(42));
    QVERIFY(RunCursor{}.isBeginning());
    QVERIFY(ProjectCursor{}.isBeginning());
    QVERIFY(!run.isBeginning());
    // Les deux valent 42 mais ne sont PAS comparables entre elles : le compilateur refuse
    // `run == project`, ce qui est précisément le but.
}

void TestCursors::runScopeBuildsRunPaths()
{
    StreamScope scope = RunScope{QStringLiteral("run-1"), RunCursor{10}};
    QCOMPARE(scopeStreamPath(scope), QStringLiteral("/streams/runs/run-1"));
    QCOMPARE(scopeJournalPath(scope), QStringLiteral("/runs/run-1/events"));
    QCOMPARE(scopeCursorValue(scope), qint64(10));
    QVERIFY(scopeLabel(scope).contains(QStringLiteral("tentative")));
}

void TestCursors::projectScopeBuildsProjectPaths()
{
    StreamScope scope = ProjectScope{QStringLiteral("proj-1"), ProjectCursor{77}};
    QCOMPARE(scopeStreamPath(scope), QStringLiteral("/streams/projects/proj-1"));
    QCOMPARE(scopeJournalPath(scope), QStringLiteral("/projects/proj-1/events"));
    QCOMPARE(scopeCursorValue(scope), qint64(77));
    QVERIFY(scopeLabel(scope).contains(QStringLiteral("projet")));
}

void TestCursors::scopeKeysNeverCollideBetweenScopes()
{
    // Un identifiant de tentative et un identifiant de projet peuvent être identiques :
    // la clé d'abonnement doit malgré tout les distinguer.
    const StreamScope run = RunScope{QStringLiteral("même-id"), RunCursor{}};
    const StreamScope project = ProjectScope{QStringLiteral("même-id"), ProjectCursor{}};
    QVERIFY(scopeKey(run) != scopeKey(project));
    QCOMPARE(scopeKey(run), QStringLiteral("run:même-id"));
    QCOMPARE(scopeKey(project), QStringLiteral("project:même-id"));
}

void TestCursors::cursorAdvancesOnlyForward()
{
    StreamScope scope = RunScope{QStringLiteral("run-1"), RunCursor{10}};
    advanceScopeCursor(scope, 15);
    QCOMPARE(scopeCursorValue(scope), qint64(15));
    // Un curseur ne recule jamais : une trame plus ancienne ne doit pas provoquer de
    // rejeu du journal.
    advanceScopeCursor(scope, 12);
    QCOMPARE(scopeCursorValue(scope), qint64(15));
}

void TestCursors::advancingKeepsScopeType()
{
    StreamScope scope = ProjectScope{QStringLiteral("proj-1"), ProjectCursor{1}};
    advanceScopeCursor(scope, 9);
    QVERIFY(std::holds_alternative<ProjectScope>(scope));
    QVERIFY(!std::holds_alternative<RunScope>(scope));
    QCOMPARE(std::get<ProjectScope>(scope).cursor.value(), qint64(9));
}

QTEST_APPLESS_MAIN(TestCursors)

#include "tst_cursors.moc"
