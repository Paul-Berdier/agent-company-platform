#include "api/ApiClient.h"
#include "auth/AuthManager.h"
#include "events/EventStreamService.h"
#include "models/JsonListModel.h"
#include "viewmodels/ArtifactsViewModel.h"
#include "viewmodels/ConversationsViewModel.h"
#include "viewmodels/MissionsViewModel.h"
#include "viewmodels/OperationsViewModel.h"
#include "viewmodels/WorkspaceViewModel.h"
#include <QCryptographicHash>
#include <QFile>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>

using namespace acp;

class TestApiJourney : public QObject
{
    Q_OBJECT
    static QString environment(const char* name) { return QString::fromUtf8(qgetenv(name)); }
    static QString idNamed(JsonListModel* rows, const QString& name)
    {
        for (int i = 0; i < rows->count(); ++i) {
            const auto row = rows->get(i);
            if (row.value(QStringLiteral("name")).toString() == name) return row.value(QStringLiteral("id")).toString();
        }
        return {};
    }
private slots:
    void realApiJourney()
    {
        const QString configured = environment("ACP_DESKTOP_TEST_API_URL");
        if (configured.isEmpty()) QSKIP("Parcours réel optionnel : lancer scripts/verify-desktop-journey.py.");
        // L'activation seule d'une URL ne suffit pas : le lanceur doit confirmer
        // le décor jetable. Aucune origine distante ni compte existant par défaut.
        QCOMPARE(environment("ACP_DESKTOP_TEST_DISPOSABLE"), QStringLiteral("1"));
        const QUrl origin(configured);
        QCOMPARE(origin.scheme(), QStringLiteral("http"));
        QCOMPARE(origin.host(), QStringLiteral("127.0.0.1"));
        QVERIFY(origin.port() > 0);
        const QString login = environment("ACP_DESKTOP_TEST_LOGIN");
        const QString password = environment("ACP_DESKTOP_TEST_PASSWORD");
        const QString fixtureProject = environment("ACP_DESKTOP_TEST_PROJECT_ID");
        const QString artifactId = environment("ACP_DESKTOP_TEST_ARTIFACT_ID");
        QVERIFY(!login.isEmpty() && !password.isEmpty() && !fixtureProject.isEmpty() && !artifactId.isEmpty());

        ApiClient client;
        client.setAllowInsecureLoopback(true);
        QVERIFY(!client.setBaseUrl(origin).isError());
        AuthManager auth(&client);
        auth.logIn(login, password);
        QTRY_VERIFY_WITH_TIMEOUT(auth.state() == SessionStatus::Connected, 10000);
        QVERIFY(client.hasCsrfToken());
        qInfo("journey: real cookie login and CSRF established");

        WorkspaceViewModel workspace(&client, &auth);
        workspace.refresh();
        QTRY_VERIFY_WITH_TIMEOUT(!workspace.busy(), 10000);
        QVERIFY2(workspace.error().isEmpty(), qPrintable(workspace.error()));
        QVERIFY(workspace.projects()->count() >= 1);
        const QString suffix = QUuid::createUuid().toString(QUuid::WithoutBraces);
        const QString organizationName = QStringLiteral("Organisation Qt %1").arg(suffix);
        workspace.createOrganization(organizationName);
        QTRY_VERIFY_WITH_TIMEOUT(!workspace.busy(), 10000);
        const QString organizationId = idNamed(workspace.organizations(), organizationName);
        QVERIFY2(!organizationId.isEmpty(), qPrintable(workspace.error()));
        const QString workspaceName = QStringLiteral("Espace Qt %1").arg(suffix);
        workspace.createWorkspace(organizationId, workspaceName);
        QTRY_VERIFY_WITH_TIMEOUT(!workspace.busy(), 10000);
        const QString workspaceId = idNamed(workspace.workspaces(), workspaceName);
        QVERIFY2(!workspaceId.isEmpty(), qPrintable(workspace.error()));
        workspace.createProject(workspaceId, QStringLiteral("Projet Qt %1").arg(suffix), QStringLiteral("Projet synthétique jetable"));
        QTRY_VERIFY_WITH_TIMEOUT(!workspace.busy(), 10000);
        const QString projectId = workspace.projectId();
        QVERIFY2(!projectId.isEmpty() && projectId != fixtureProject, qPrintable(workspace.error()));
        QCOMPARE(workspace.project().value(QStringLiteral("workspace_id")).toString(), workspaceId);
        qInfo("journey: organizations, workspaces and projects created and listed through native viewmodel");

        ConversationsViewModel conversations(&client, &auth);
        QVERIFY(conversations.startConversation(QString()));
        QTRY_VERIFY_WITH_TIMEOUT(!conversations.currentId().isEmpty() && !conversations.loading() && !conversations.busy(), 10000);
        QVERIFY2(conversations.error().isEmpty(), qPrintable(conversations.error()));
        QVERIFY(!conversations.currentTitle().trimmed().isEmpty());
        QVERIFY(conversations.projectId().isEmpty());
        const QString generalConversationId = conversations.currentId();
        QVERIFY(conversations.startConversation(projectId));
        QTRY_VERIFY_WITH_TIMEOUT(!conversations.currentId().isEmpty() && !conversations.loading() && !conversations.busy(), 10000);
        QVERIFY2(conversations.error().isEmpty(), qPrintable(conversations.error()));
        QVERIFY(!conversations.currentTitle().trimmed().isEmpty());
        QVERIFY(conversations.currentId() != generalConversationId);
        QCOMPARE(conversations.projectId(), projectId);
        qInfo("Parcours : chat général et chat de projet créés sans titre imposé, avant ouverture de la page.");
        conversations.setDraft(QStringLiteral("Message synthétique : aucun fournisseur ne doit être appelé."));
        QVERIFY(conversations.canSend());
        conversations.sendMessage();
        auto* turns = qobject_cast<JsonListModel*>(conversations.turns());
        QVERIFY(turns);
        QTRY_VERIFY_WITH_TIMEOUT(!conversations.busy() && turns->count() == 1, 15000);
        const auto turn = turns->get(0);
        QCOMPARE(turn.value(QStringLiteral("status")).toString(), QStringLiteral("submitting"));
        QVERIFY(turn.value(QStringLiteral("assistant_content")).isNull()
                || turn.value(QStringLiteral("assistant_content")).toString().isEmpty());
        QVERIFY(turn.value(QStringLiteral("error")).toString().contains(QStringLiteral("indisponible")));
        QVERIFY(!conversations.notice().isEmpty());
        conversations.setActive(false);
        qInfo("journey: provider unavailable is explicit; user message persisted without fabricated assistant output");

        EventStreamService streams(&client);
        MissionsViewModel missions(&client, &auth, &streams);
        missions.setProjectId(projectId);
        QTRY_VERIFY_WITH_TIMEOUT(!missions.busy(), 10000);
        QVERIFY(missions.canWrite());
        missions.createMission(QVariantMap{
            {QStringLiteral("title"), QStringLiteral("Mission créée depuis Qt")},
            {QStringLiteral("objective"), QStringLiteral("Vérifier le contrat réel")},
            {QStringLiteral("expected_outcome"), QStringLiteral("Une tentative visible")},
            {QStringLiteral("acceptance_criteria"), QStringLiteral("État serveur conservé\nAucune exécution inventée")},
            {QStringLiteral("autonomy"), QStringLiteral("supervised")},
            {QStringLiteral("max_cost"), QStringLiteral("0")},
            {QStringLiteral("duration_seconds"), 60}});
        QTRY_VERIFY_WITH_TIMEOUT(!missions.mutating() && !missions.busy() && missions.missions()->count() == 1, 15000);
        QVERIFY2(missions.error().isEmpty(), qPrintable(missions.error()));
        if (missions.selectedMissionId().isEmpty()) missions.selectMission(missions.missions()->get(0).value(QStringLiteral("id")).toString());
        QTRY_VERIFY_WITH_TIMEOUT(!missions.busy() && !missions.selectedRunId().isEmpty(), 10000);
        QCOMPARE(missions.mission().value(QStringLiteral("project_id")).toString(), projectId);
        QCOMPARE(missions.run().value(QStringLiteral("status")).toString(), QStringLiteral("queued"));
        QVERIFY(missions.testReport().isEmpty());
        qInfo("journey: mission created, listed and detailed with real queued attempt");

        OperationsViewModel operations(&client, &auth);
        operations.setProjectId(projectId);
        QTRY_VERIFY_WITH_TIMEOUT(!operations.busy(), 10000);
        QVERIFY2(operations.error().isEmpty(), qPrintable(operations.error()));
        QVERIFY(operations.budgetUsage().value(QStringLiteral("totals")).toMap().value(QStringLiteral("cost")).isNull());
        operations.saveBudgetPolicy(2, 1, 3);
        QTRY_VERIFY_WITH_TIMEOUT(!operations.busy(), 10000);
        QVERIFY2(operations.error().isEmpty(), qPrintable(operations.error()));
        QCOMPARE(operations.budgetPolicy().value(QStringLiteral("max_concurrent_missions")).toInt(), 2);
        operations.createAutomation(QVariantMap{
            {QStringLiteral("name"), QStringLiteral("Routine du parcours Qt")},
            {QStringLiteral("objective"), QStringLiteral("Vérifier le contrat")},
            {QStringLiteral("expectedOutcome"), QStringLiteral("Compte rendu")},
            {QStringLiteral("criteria"), QStringLiteral("Résultat vérifiable")},
            {QStringLiteral("scheduleKind"), QStringLiteral("interval")},
            {QStringLiteral("expression"), QStringLiteral("60")},
            {QStringLiteral("timezone"), QStringLiteral("Europe/Paris")},
            {QStringLiteral("durationSeconds"), 60}, {QStringLiteral("maxToolCalls"), 0}});
        QTRY_VERIFY_WITH_TIMEOUT(!operations.busy(), 10000);
        QVERIFY2(operations.error().isEmpty(), qPrintable(operations.error()));
        QCOMPARE(operations.automations()->count(), 1);
        QVERIFY(!operations.automations()->get(0).value(QStringLiteral("enabled")).toBool());
        qInfo("journey: real budget replacement and paused automation creation confirmed");

        ArtifactsViewModel artifacts(&client, &auth);
        artifacts.setProjectId(fixtureProject);
        QTRY_VERIFY_WITH_TIMEOUT(!artifacts.busy(), 10000);
        QVERIFY2(artifacts.error().isEmpty(), qPrintable(artifacts.error()));
        QCOMPARE(artifacts.rows()->count(), 1);
        artifacts.selectArtifact(artifactId);
        QTRY_VERIFY_WITH_TIMEOUT(!artifacts.detailBusy(), 10000);
        QCOMPARE(artifacts.selected().value(QStringLiteral("id")).toString(), artifactId);
        QTemporaryDir exportDirectory;
        QVERIFY(exportDirectory.isValid());
        const auto target = QUrl::fromLocalFile(exportDirectory.filePath(QStringLiteral("actual-download.txt")));
        QSignalSpy saved(artifacts.downloader(), &ArtifactDownload::succeeded);
        artifacts.downloadSelected(target, artifactId);
        QTRY_VERIFY_WITH_TIMEOUT(!artifacts.downloader()->busy(), 10000);
        QVERIFY2(artifacts.downloader()->error().isEmpty(), qPrintable(artifacts.downloader()->error()));
        QCOMPARE(saved.count(), 1);
        QFile downloaded(target.toLocalFile());
        QVERIFY(downloaded.open(QIODevice::ReadOnly));
        const QByteArray bytes = downloaded.readAll();
        QCOMPARE(bytes.size(), environment("ACP_DESKTOP_TEST_ARTIFACT_BYTES").toLongLong());
        QCOMPARE(QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex()),
                 environment("ACP_DESKTOP_TEST_ARTIFACT_SHA256"));
        qInfo("journey: real authenticated artifact endpoint exported exact bytes and SHA-256");

        streams.closeAll();
        auth.logOut();
        QTRY_VERIFY_WITH_TIMEOUT(auth.state() == SessionStatus::Disconnected, 10000);
        QCOMPARE(workspace.projects()->count(), 0); QCOMPARE(artifacts.rows()->count(), 0);
        QVERIFY(operations.budgetPolicy().isEmpty());
        qInfo("journey: logout cleared native project data");
    }
};
QTEST_GUILESS_MAIN(TestApiJourney)
#include "tst_api_journey.moc"
