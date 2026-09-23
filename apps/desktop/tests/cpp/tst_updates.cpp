#include "services/UpdateService.h"
#include <QTest>
using acp::UpdateService;
class TestUpdates : public QObject {
    Q_OBJECT
private slots:
    void semanticPrecedence() {
        const QStringList ordered = {QStringLiteral("1.0.0-alpha"), QStringLiteral("1.0.0-alpha.1"),
            QStringLiteral("1.0.0-alpha.beta"), QStringLiteral("1.0.0-beta"), QStringLiteral("1.0.0-beta.2"),
            QStringLiteral("1.0.0-beta.11"), QStringLiteral("1.0.0-rc.1"), QStringLiteral("1.0.0"), QStringLiteral("1.0.1")};
        for (int i = 1; i < ordered.size(); ++i) {
            bool valid = false;
            QVERIFY(UpdateService::compareVersions(ordered.at(i), ordered.at(i - 1), &valid) > 0);
            QVERIFY(valid);
        }
        bool valid = false;
        QVERIFY(UpdateService::compareVersions(QStringLiteral("0.10.0"), QStringLiteral("0.9.9"), &valid) > 0);
        QVERIFY(valid);
        QCOMPARE(UpdateService::compareVersions(QStringLiteral("v1.0.0+build.2"), QStringLiteral("1.0.0+build.1"), &valid), 0);
        QVERIFY(valid);
        for (const auto &value : {QStringLiteral("1.0"), QStringLiteral("01.0.0"), QStringLiteral("1.0.0-01"), QStringLiteral("$(bad)")}) {
            UpdateService::compareVersions(value, QStringLiteral("1.0.0"), &valid);
            QVERIFY(!valid);
        }
    }
    void untrustedReleaseCannotOpenOtherSites() {
        QJsonObject release{{QStringLiteral("draft"), false}, {QStringLiteral("prerelease"), false}, {QStringLiteral("tag_name"), QStringLiteral("v0.10.0")},
            {QStringLiteral("html_url"), QStringLiteral("https://github.com/Paul-Berdier/agent-company-platform/releases/tag/v0.10.0")}};
        QVERIFY(UpdateService::validateRelease(release, false));
        for (const auto &url : {QStringLiteral("https://evil.test/release"), QStringLiteral("file:///tmp/bad.exe"),
             QStringLiteral("http://github.com/Paul-Berdier/agent-company-platform/releases/tag/v0.10.0"),
             QStringLiteral("https://github.com/other/repo/releases/tag/v0.10.0"),
             QStringLiteral("https://user@github.com/Paul-Berdier/agent-company-platform/releases/tag/v0.10.0")}) {
            auto bad = release; bad[QStringLiteral("html_url")] = url;
            QVERIFY(!UpdateService::validateRelease(bad, false));
        }
        auto draft = release; draft[QStringLiteral("draft")] = true;
        QVERIFY(!UpdateService::validateRelease(draft, true));
        release[QStringLiteral("prerelease")] = true;
        QVERIFY(!UpdateService::validateRelease(release, false));
        QVERIFY(UpdateService::validateRelease(release, true));
        release.remove(QStringLiteral("draft"));
        QVERIFY(!UpdateService::validateRelease(release, true));
    }
    void noAutomaticNetworkOrSuccess() {
        UpdateService service(QStringLiteral("0.10.0"));
        QVERIFY(!service.busy()); QVERIFY(!service.updateAvailable());
        QVERIFY(service.latestVersion().isEmpty());
        QVERIFY(service.status().contains(QStringLiteral("Aucune vérification")));
        service.setIncludePrereleases(true);
        QVERIFY(service.includePrereleases()); QVERIFY(!service.busy());
        QVERIFY(!service.updateAvailable());
    }
};
QTEST_GUILESS_MAIN(TestUpdates)
#include "tst_updates.moc"
