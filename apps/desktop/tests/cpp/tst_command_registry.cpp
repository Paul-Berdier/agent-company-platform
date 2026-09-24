// Registre de commandes : enregistrement, disponibilité, exécution, filtrage.
//
// La règle éprouvée ici : une commande INDISPONIBLE n'est jamais exécutée, et son refus
// porte une raison française. C'est ce qui permet à l'interface de ne jamais montrer de
// bouton qui fait semblant.

#include "commands/CommandRegistry.h"
#include "navigation/NavigationModel.h"

#include <QSignalSpy>
#include <QTest>

using namespace acp;

namespace {

Command makeCommand(const QString &id, CommandAvailability availability, int *counter)
{
    Command command;
    command.id = id;
    command.title = QStringLiteral("Commande %1").arg(id);
    command.category = QStringLiteral("Test");
    command.keywords = {QStringLiteral("essai")};
    command.availability = [availability](const CommandContext &) { return availability; };
    command.run = [counter](const CommandContext &) {
        if (counter) {
            ++(*counter);
        }
        return CommandResult::accept();
    };
    return command;
}

} // namespace

class TestCommandRegistry : public QObject
{
    Q_OBJECT

private slots:
    void registersAndCounts();
    void refusesDuplicateIdentifier();
    void refusesIncompleteCommand();
    void doesNotExecuteUnavailableCommand();
    void executesAvailableCommand();
    void refusesUnknownCommand();
    void contextChangeReevaluatesAvailability();
    void unavailableCommandsStayVisible();
    void filterMatchesTitleCategoryAndKeywords();
    void unregisterKeepsIndexConsistent();
    void resolvesShortcuts();
    void everyAvailabilityHasFrenchReason();
    void navigationHistoryBranchesAndRefusesUnavailable();
    void navigationHistoryIsBoundedAndResettable();
};

void TestCommandRegistry::registersAndCounts()
{
    CommandRegistry registry;
    QVERIFY(registry.registerCommand(makeCommand(QStringLiteral("a"),
                                                 CommandAvailability::Available, nullptr)));
    QCOMPARE(registry.totalCount(), 1);
    QVERIFY(registry.contains(QStringLiteral("a")));
}

void TestCommandRegistry::refusesDuplicateIdentifier()
{
    CommandRegistry registry;
    QVERIFY(registry.registerCommand(
        makeCommand(QStringLiteral("a"), CommandAvailability::Available, nullptr)));
    // Deux modules qui revendiquent la même commande est un défaut de conception, pas une
    // préférence de dernier arrivé.
    QVERIFY(!registry.registerCommand(
        makeCommand(QStringLiteral("a"), CommandAvailability::Available, nullptr)));
    QCOMPARE(registry.totalCount(), 1);
}

void TestCommandRegistry::refusesIncompleteCommand()
{
    CommandRegistry registry;
    Command withoutRun = makeCommand(QStringLiteral("b"), CommandAvailability::Available, nullptr);
    withoutRun.run = nullptr;
    QVERIFY(!registry.registerCommand(withoutRun));

    Command withoutPredicate =
        makeCommand(QStringLiteral("c"), CommandAvailability::Available, nullptr);
    withoutPredicate.availability = nullptr;
    QVERIFY(!registry.registerCommand(withoutPredicate));

    Command withoutTitle = makeCommand(QStringLiteral("d"), CommandAvailability::Available, nullptr);
    withoutTitle.title.clear();
    QVERIFY(!registry.registerCommand(withoutTitle));

    QCOMPARE(registry.totalCount(), 0);
}

void TestCommandRegistry::doesNotExecuteUnavailableCommand()
{
    CommandRegistry registry;
    int executions = 0;
    registry.registerCommand(
        makeCommand(QStringLiteral("locked"), CommandAvailability::NeedsSession, &executions));

    QSignalSpy spy(&registry, &CommandRegistry::commandExecuted);
    const QString message = registry.execute(QStringLiteral("locked"));

    QCOMPARE(executions, 0);
    QVERIFY(!message.isEmpty());
    QCOMPARE(spy.count(), 1);
    QCOMPARE(spy.at(0).at(1).toBool(), false);
}

void TestCommandRegistry::executesAvailableCommand()
{
    CommandRegistry registry;
    int executions = 0;
    registry.registerCommand(
        makeCommand(QStringLiteral("open"), CommandAvailability::Available, &executions));

    QSignalSpy spy(&registry, &CommandRegistry::commandExecuted);
    registry.execute(QStringLiteral("open"));

    QCOMPARE(executions, 1);
    QCOMPARE(spy.count(), 1);
    QCOMPARE(spy.at(0).at(1).toBool(), true);
}

void TestCommandRegistry::refusesUnknownCommand()
{
    CommandRegistry registry;
    const QString message = registry.execute(QStringLiteral("inexistante"));
    QVERIFY(message.contains(QStringLiteral("inexistante")));
    QCOMPARE(registry.availabilityOf(QStringLiteral("inexistante")),
             int(CommandAvailability::Unavailable));
}

void TestCommandRegistry::contextChangeReevaluatesAvailability()
{
    CommandRegistry registry;
    int executions = 0;
    Command command = makeCommand(QStringLiteral("session"), CommandAvailability::Available,
                                  &executions);
    command.availability = [](const CommandContext &context) {
        return context.sessionConnected ? CommandAvailability::Available
                                        : CommandAvailability::NeedsSession;
    };
    registry.registerCommand(command);

    QCOMPARE(registry.availabilityOf(QStringLiteral("session")),
             int(CommandAvailability::NeedsSession));

    CommandContext connected;
    connected.sessionConnected = true;
    registry.setContext(connected);
    QCOMPARE(registry.availabilityOf(QStringLiteral("session")),
             int(CommandAvailability::Available));

    registry.execute(QStringLiteral("session"));
    QCOMPARE(executions, 1);
}

void TestCommandRegistry::unavailableCommandsStayVisible()
{
    CommandRegistry registry;
    registry.registerCommand(
        makeCommand(QStringLiteral("a"), CommandAvailability::Available, nullptr));
    registry.registerCommand(
        makeCommand(QStringLiteral("b"), CommandAvailability::Offline, nullptr));
    // Masquer une commande indisponible laisserait croire qu'elle n'existe pas.
    QCOMPARE(registry.rowCount(), 2);
}

void TestCommandRegistry::filterMatchesTitleCategoryAndKeywords()
{
    CommandRegistry registry;
    Command command = makeCommand(QStringLiteral("mission.create"),
                                  CommandAvailability::Available, nullptr);
    command.title = QStringLiteral("Créer une mission");
    command.category = QStringLiteral("Missions");
    command.keywords = {QStringLiteral("nouvelle"), QStringLiteral("tâche")};
    registry.registerCommand(command);

    registry.setFilter(QStringLiteral("mission"));
    QCOMPARE(registry.rowCount(), 1);
    registry.setFilter(QStringLiteral("TÂCHE"));
    QCOMPARE(registry.rowCount(), 1);
    registry.setFilter(QStringLiteral("inexistant"));
    QCOMPARE(registry.rowCount(), 0);
    registry.setFilter(QString());
    QCOMPARE(registry.rowCount(), 1);
}

void TestCommandRegistry::unregisterKeepsIndexConsistent()
{
    CommandRegistry registry;
    int executions = 0;
    registry.registerCommand(
        makeCommand(QStringLiteral("a"), CommandAvailability::Available, nullptr));
    registry.registerCommand(
        makeCommand(QStringLiteral("b"), CommandAvailability::Available, nullptr));
    registry.registerCommand(
        makeCommand(QStringLiteral("c"), CommandAvailability::Available, &executions));

    QVERIFY(registry.unregisterCommand(QStringLiteral("a")));
    QCOMPARE(registry.totalCount(), 2);
    QVERIFY(!registry.contains(QStringLiteral("a")));

    // La table d'index doit rester juste : exécuter « c » doit toujours appeler « c ».
    registry.execute(QStringLiteral("c"));
    QCOMPARE(executions, 1);
    QVERIFY(!registry.unregisterCommand(QStringLiteral("a")));
}

void TestCommandRegistry::resolvesShortcuts()
{
    CommandRegistry registry;
    Command command =
        makeCommand(QStringLiteral("palette.open"), CommandAvailability::Available, nullptr);
    command.shortcut = QStringLiteral("Ctrl+K");
    registry.registerCommand(command);

    QCOMPARE(registry.commandForShortcut(QStringLiteral("Ctrl+K")),
             QStringLiteral("palette.open"));
    QCOMPARE(registry.commandForShortcut(QStringLiteral("ctrl+k")),
             QStringLiteral("palette.open"));
    QVERIFY(registry.commandForShortcut(QStringLiteral("Ctrl+P")).isEmpty());
    QVERIFY(registry.commandForShortcut(QString()).isEmpty());
}

void TestCommandRegistry::everyAvailabilityHasFrenchReason()
{
    const QList<CommandAvailability> states = {
        CommandAvailability::NeedsSession,   CommandAvailability::NeedsRole,
        CommandAvailability::NeedsSelection, CommandAvailability::Offline,
        CommandAvailability::NotConfigured,  CommandAvailability::Unavailable,
    };
    for (const CommandAvailability state : states) {
        QVERIFY2(!describeAvailability(state).isEmpty(),
                 "toute indisponibilité doit pouvoir s'expliquer à l'opérateur");
    }
    // Disponible = aucune raison à afficher.
    QVERIFY(describeAvailability(CommandAvailability::Available).isEmpty());
}

void TestCommandRegistry::navigationHistoryBranchesAndRefusesUnavailable()
{
    NavigationModel navigation;
    QVERIFY(!navigation.canGoBack());
    QVERIFY(!navigation.canGoForward());
    navigation.goBack();
    QCOMPARE(navigation.currentRoute(), QStringLiteral("home"));
    navigation.setCurrentRoute(QStringLiteral("projects"));
    navigation.setCurrentRoute(QStringLiteral("conversations"));
    navigation.goBack();
    QCOMPARE(navigation.currentRoute(), QStringLiteral("projects"));
    QVERIFY(navigation.canGoForward());
    QSignalSpy refused(&navigation, &NavigationModel::navigationRefused);
    navigation.setCurrentRoute(QStringLiteral("office"));
    navigation.setCurrentRoute(QStringLiteral("unknown"));
    QCOMPARE(refused.count(), 2);
    // Les quotas d'abonnement sont une destination livrée, hors contexte de projet.
    QVERIFY(navigation.isNavigable(QStringLiteral("quotas")));
    QVERIFY(navigation.detailFor(QStringLiteral("quotas")).isEmpty());
    QVERIFY(navigation.canGoForward());
    navigation.goForward();
    QCOMPARE(navigation.currentRoute(), QStringLiteral("conversations"));
    navigation.goBack();
    navigation.setCurrentRoute(QStringLiteral("missions"));
    QVERIFY(!navigation.canGoForward());
    navigation.setCurrentRoute(QStringLiteral("missions")); // Pas de doublon adjacent.
    navigation.goBack();
    QCOMPARE(navigation.currentRoute(), QStringLiteral("projects"));
}

void TestCommandRegistry::navigationHistoryIsBoundedAndResettable()
{
    NavigationModel navigation;
    for (int i = 0; i < 80; ++i)
        navigation.setCurrentRoute(i % 2 ? QStringLiteral("projects") : QStringLiteral("conversations"));
    int backwards = 0;
    while (navigation.canGoBack()) { navigation.goBack(); ++backwards; }
    QCOMPARE(backwards, 31);
    QVERIFY(navigation.canGoForward());
    navigation.resetHistory();
    QCOMPARE(navigation.currentRoute(), QStringLiteral("home"));
    QVERIFY(!navigation.canGoBack());
    QVERIFY(!navigation.canGoForward());
    navigation.goForward();
    QCOMPARE(navigation.currentRoute(), QStringLiteral("home"));
}

QTEST_APPLESS_MAIN(TestCommandRegistry)

#include "tst_command_registry.moc"
