// Vérification des publications GitHub, puis mise à jour automatique (D170) contre un faux GitHub
// de bouclage : téléchargement de l'installeur de la publication, refus de toute empreinte, taille
// ou redirection hors contrat, lancement de l'installeur seulement après vérification, installation
// au démarrage suivant sans boucle si elle n'aboutit pas.
#include "services/UpdateService.h"
#include "support/FauxHermes.h"
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
using acp::UpdateService;
using namespace acp::test;
namespace {
const QString kDepot = QStringLiteral("/Paul-Berdier/agent-company-platform");
const QString kInstalleur = QStringLiteral("AgentCompanyPlatform-Setup-1.2.0-x64.exe");
struct Lancement { QString programme; QStringList arguments; };
//! Faux GitHub : publication v1.2.0, installeur servi par une redirection vers un hôte admis.
struct Banc {
    FauxHermes serveur;
    QTemporaryDir dossier;
    QByteArray installeur = QByteArray(300 * 1024, 'x') + QByteArrayLiteral("fin");
    QString empreinte = QString::fromLatin1(QCryptographicHash::hash(installeur, QCryptographicHash::Sha256).toHex());
    QByteArray sommes;
    QString digest;
    qint64 tailleAnnoncee = -1;
    QString urlInstalleur;
    QByteArray redirection;
    QList<Lancement> lancements;
    bool lanceurReussit = true;
    int delaiInstalleurMs = 0;
    Banc() {
        sommes = empreinte.toLatin1() + "  " + kInstalleur.toLatin1() + "\n"
            + QByteArray(64, 'a') + "  AgentCompanyPlatform-Portable-1.2.0-x64.zip\n";
        digest = QStringLiteral("sha256:") + empreinte;
        tailleAnnoncee = installeur.size();
        urlInstalleur = depot() + QStringLiteral("/releases/download/v1.2.0/") + kInstalleur;
        redirection = (base() + QStringLiteral("/objets/installeur")).toUtf8();
        serveur.route("GET", QStringLiteral("/repos") + kDepot + QStringLiteral("/releases/latest"),
                      [this](const RequeteRecue &) { return ReponseFaux::json(200, publication()); });
        serveur.route("GET", QStringLiteral("/repos") + kDepot + QStringLiteral("/releases"), [this](const RequeteRecue &) {
            QJsonObject preversion = publication();
            preversion.insert(QStringLiteral("prerelease"), true);
            return ReponseFaux::json(200, QJsonArray{preversion});
        });
        serveur.route("GET", kDepot + QStringLiteral("/releases/download/v1.2.0/") + kInstalleur,
                      [this](const RequeteRecue &) { return ReponseFaux::redirection(redirection); });
        serveur.route("GET", QStringLiteral("/objets/installeur"), [this](const RequeteRecue &) {
            ReponseFaux reponse; reponse.corps = installeur; reponse.delaiMs = delaiInstalleurMs; return reponse;
        });
        serveur.route("GET", kDepot + QStringLiteral("/releases/download/v1.2.0/SHA256SUMS.txt"),
                      [this](const RequeteRecue &) { ReponseFaux reponse; reponse.corps = sommes; return reponse; });
    }
    QString base() const { return QStringLiteral("http://127.0.0.1:%1").arg(serveur.port()); }
    QString depot() const { return base() + kDepot; }
    QJsonObject publication() const {
        return QJsonObject{{QStringLiteral("draft"), false}, {QStringLiteral("prerelease"), false},
            {QStringLiteral("tag_name"), QStringLiteral("v1.2.0")}, {QStringLiteral("body"), QStringLiteral("Notes.")},
            {QStringLiteral("html_url"), depot() + QStringLiteral("/releases/tag/v1.2.0")},
            {QStringLiteral("assets"), QJsonArray{
                QJsonObject{{QStringLiteral("name"), kInstalleur}, {QStringLiteral("size"), tailleAnnoncee},
                            {QStringLiteral("digest"), digest}, {QStringLiteral("browser_download_url"), urlInstalleur}},
                QJsonObject{{QStringLiteral("name"), QStringLiteral("SHA256SUMS.txt")}, {QStringLiteral("size"), sommes.size()},
                            {QStringLiteral("browser_download_url"), depot() + QStringLiteral("/releases/download/v1.2.0/SHA256SUMS.txt")}}}}};
    }
    UpdateService::Sources sources(bool installation = true) {
        UpdateService::Sources s;
        s.api = QUrl(base() + QStringLiteral("/repos") + kDepot);
        s.depot = depot();
        s.hotes = {QStringLiteral("127.0.0.1")};
        s.httpAutorise = true;
        s.dossier = dossier.path();
        s.installationPermise = installation;
        s.lanceur = [this](const QString &programme, const QStringList &arguments) {
            lancements.append({programme, arguments});
            return lanceurReussit;
        };
        return s;
    }
    int telechargements() const {
        return serveur.compter("GET", kDepot + QStringLiteral("/releases/download/v1.2.0/") + kInstalleur);
    }
};
}
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
    void empreintesDeSha256Sums() {
        const QByteArray h1(64, 'a'), h2(64, 'b');
        QCOMPARE(UpdateService::empreinteDans(h1 + "  a.exe\n" + h2 + "  b.exe\n", QStringLiteral("b.exe")), QString::fromLatin1(h2));
        QCOMPARE(UpdateService::empreinteDans(h1.toUpper() + " *a.exe\r\n", QStringLiteral("a.exe")), QString::fromLatin1(h1));
        // Deux empreintes différentes pour un même nom, ou nom absent : refus.
        QVERIFY(UpdateService::empreinteDans(h1 + "  a.exe\n" + h2 + "  a.exe\n", QStringLiteral("a.exe")).isEmpty());
        QVERIFY(UpdateService::empreinteDans(h1 + "  a.exe.old\n", QStringLiteral("a.exe")).isEmpty());
        QVERIFY(UpdateService::empreinteDans(QByteArray(63, 'a') + "  a.exe\n", QStringLiteral("a.exe")).isEmpty());
    }
    void telechargementVerifiePuisInstallation() {
        Banc banc;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        QSignalSpy pret(&service, &UpdateService::updateReady);
        QSignalSpy quitter(&service, &UpdateService::quitRequested);
        service.check();
        QTRY_VERIFY(service.readyToInstall());
        QCOMPARE(pret.count(), 1);
        QCOMPARE(service.pendingVersion(), QStringLiteral("v1.2.0"));
        QFile fichier(banc.dossier.filePath(kInstalleur));
        QVERIFY(fichier.open(QIODevice::ReadOnly));
        QCOMPARE(fichier.readAll(), banc.installeur);
        // Rien n'est lancé avant le geste ou le démarrage suivant.
        QVERIFY(banc.lancements.isEmpty());
        service.installNow();
        QCOMPARE(banc.lancements.size(), 1);
        QCOMPARE(QDir::cleanPath(banc.lancements.first().programme), QDir::cleanPath(banc.dossier.filePath(kInstalleur)));
        QCOMPARE(banc.lancements.first().arguments, UpdateService::argumentsInstalleur());
        QVERIFY(banc.lancements.first().arguments.contains(QStringLiteral("/SILENT")));
        QVERIFY(banc.lancements.first().arguments.contains(QStringLiteral("/ACPRELANCER=1")));
        QCOMPARE(quitter.count(), 1);
    }
    void empreinteFausseRefusee() {
        Banc banc;
        banc.sommes = QByteArray(64, 'c') + "  " + kInstalleur.toLatin1() + "\n";
        banc.digest.clear();
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.status().contains(QStringLiteral("Empreinte SHA-256")));
        QVERIFY(!service.readyToInstall());
        QVERIFY(!QFile::exists(banc.dossier.filePath(kInstalleur)));
        service.installNow();
        QVERIFY(banc.lancements.isEmpty());
    }
    void empreinteGithubDiscordanteRefuseeAvantTelechargement() {
        Banc banc;
        banc.digest = QStringLiteral("sha256:") + QString(64, QLatin1Char('d'));
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.status().contains(QStringLiteral("diffère de SHA256SUMS.txt")));
        QCOMPARE(banc.telechargements(), 0);
        QVERIFY(!service.readyToInstall());
    }
    void redirectionVersUnHoteNonAdmisRefusee() {
        Banc banc;
        banc.redirection = QStringLiteral("http://localhost:%1/objets/installeur").arg(banc.serveur.port()).toUtf8();
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.status().contains(QStringLiteral("hôte non admis")));
        QVERIFY(!service.readyToInstall());
        QVERIFY(!QFile::exists(banc.dossier.filePath(kInstalleur)));
    }
    void installeurPlusGrosQueAnnonceRefuse() {
        Banc banc;
        banc.tailleAnnoncee = banc.installeur.size() - 10;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.status().contains(QStringLiteral("plus volumineux")));
        QVERIFY(!service.readyToInstall());
        QVERIFY(!QFile::exists(banc.dossier.filePath(kInstalleur)));
    }
    void fichierHorsDeLaPublicationIgnore() {
        Banc banc;
        banc.urlInstalleur = banc.base() + QStringLiteral("/autre/depot/") + kInstalleur;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.updateAvailable());
        QVERIFY(service.status().contains(QStringLiteral("installez-la à la main")));
        QCOMPARE(banc.telechargements(), 0);
    }
    void sansInstallationPossibleRienNestTelecharge() {
        Banc banc;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources(false));
        service.check();
        QTRY_VERIFY(service.updateAvailable());
        QTest::qWait(100);
        QCOMPARE(banc.telechargements(), 0);
        service.downloadAndInstall();
        QVERIFY(service.status().contains(QStringLiteral("seulement sous Windows")));
        QCOMPARE(banc.telechargements(), 0);
        QVERIFY(banc.lancements.isEmpty());
    }
    void sansInstallationAutomatiqueLeGesteTelechargeEtInstalle() {
        Banc banc;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.setAutoInstall(false);
        service.check();
        QTRY_VERIFY(service.updateAvailable());
        QTest::qWait(100);
        QCOMPARE(banc.telechargements(), 0);
        QSignalSpy quitter(&service, &UpdateService::quitRequested);
        service.downloadAndInstall();
        QTRY_COMPARE(quitter.count(), 1);
        QCOMPARE(banc.lancements.size(), 1);
    }
    void installationAuDemarrageSansBoucle() {
        Banc banc;
        {
            UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
            service.check();
            QTRY_VERIFY(service.readyToInstall());
        }
        // Démarrage suivant : l'installeur est lancé avant toute fenêtre.
        {
            UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
            QVERIFY(service.installPendingAtStartup());
            QCOMPARE(banc.lancements.size(), 1);
        }
        // La station n'a pas changé de version : l'installation n'a pas abouti, pas de nouvelle tentative.
        {
            UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
            QVERIFY(!service.installPendingAtStartup());
            QCOMPARE(banc.lancements.size(), 1);
            QVERIFY(service.readyToInstall());
            QVERIFY(service.status().contains(QStringLiteral("n'a pas abouti")));
        }
        // Version installée : l'installeur téléchargé et l'état sont effacés.
        {
            UpdateService service(QStringLiteral("1.2.0"), nullptr, banc.sources());
            QVERIFY(!service.installPendingAtStartup());
            QVERIFY(!service.readyToInstall());
            QVERIFY(!QFile::exists(banc.dossier.filePath(kInstalleur)));
            QVERIFY(!QFile::exists(banc.dossier.filePath(QStringLiteral("attente.json"))));
        }
    }
    void installeurModifieApresTelechargementRefuse() {
        Banc banc;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.readyToInstall());
        QFile fichier(banc.dossier.filePath(kInstalleur));
        QVERIFY(fichier.open(QIODevice::Append));
        fichier.write("ajout");
        fichier.close();
        service.installNow();
        QVERIFY(banc.lancements.isEmpty());
        QVERIFY(!service.readyToInstall());
        QVERIFY(!QFile::exists(banc.dossier.filePath(kInstalleur)));
    }
    void preversionJamaisTelechargeeSansGeste() {
        Banc banc;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.setIncludePrereleases(true);
        service.check();
        QTRY_VERIFY(service.updateAvailable());
        QVERIFY(service.installerAvailable());
        QTest::qWait(100);
        QCOMPARE(banc.telechargements(), 0);
        QVERIFY(!service.readyToInstall());
    }
    void versionRetireeEffaceeALaVerificationSuivante() {
        Banc banc;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.readyToInstall());
        // La publication 1.2.0 est retirée : la dernière publiée redevient 1.0.1.
        banc.serveur.route("GET", QStringLiteral("/repos") + kDepot + QStringLiteral("/releases/latest"), [&banc](const RequeteRecue &) {
            QJsonObject ancienne = banc.publication();
            ancienne.insert(QStringLiteral("tag_name"), QStringLiteral("v1.0.1"));
            ancienne.insert(QStringLiteral("html_url"), banc.depot() + QStringLiteral("/releases/tag/v1.0.1"));
            ancienne.insert(QStringLiteral("assets"), QJsonArray{});
            return ReponseFaux::json(200, ancienne);
        });
        service.check();
        QTRY_VERIFY(service.status().contains(QStringLiteral("n'est plus publiée")));
        QVERIFY(!service.readyToInstall());
        QVERIFY(!QFile::exists(banc.dossier.filePath(kInstalleur)));
        QVERIFY(!service.installPendingAtStartup());
        QVERIFY(banc.lancements.isEmpty());
    }
    void sansInstalleurLeBoutonNeFaitPasSemblant() {
        Banc banc;
        banc.urlInstalleur = banc.base() + QStringLiteral("/autre/") + kInstalleur;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.updateAvailable());
        QVERIFY(!service.installerAvailable());
        service.downloadAndInstall();
        QVERIFY(service.status().contains(QStringLiteral("Aucun installeur vérifiable")));
        QVERIFY(banc.lancements.isEmpty());
    }
    void desactiverPendantLeTelechargementLAnnule() {
        Banc banc;
        banc.delaiInstalleurMs = 1500;
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.check();
        QTRY_VERIFY(service.downloading());
        service.setAutoInstall(false);
        QVERIFY(!service.downloading());
        QVERIFY(service.status().contains(QStringLiteral("téléchargement annulé")));
        QTest::qWait(1700);
        QVERIFY(!service.readyToInstall());
        QVERIFY(!QFile::exists(banc.dossier.filePath(kInstalleur)));
    }
    void echecPrecedentSignaleMemeSansInstallationAutomatique() {
        Banc banc;
        {
            UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
            service.check();
            QTRY_VERIFY(service.readyToInstall());
            service.installNow();
            QCOMPARE(banc.lancements.size(), 1);
        }
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        service.setAutoInstall(false);
        QSignalSpy echec(&service, &UpdateService::installationFailed);
        QVERIFY(!service.installPendingAtStartup());
        QCOMPARE(echec.count(), 1);
        QVERIFY(service.status().contains(QStringLiteral("n'a pas abouti")));
    }
    void etatAltereNeSupprimeQueLInstalleur() {
        Banc banc;
        QFile autre(banc.dossier.filePath(QStringLiteral("garder.txt")));
        QVERIFY(autre.open(QIODevice::WriteOnly)); autre.write("x"); autre.close();
        QFile etat(banc.dossier.filePath(QStringLiteral("attente.json")));
        QVERIFY(etat.open(QIODevice::WriteOnly));
        etat.write(QJsonDocument(QJsonObject{{QStringLiteral("version"), QStringLiteral("v9.0.0")},
            {QStringLiteral("fichier"), QStringLiteral("garder.txt")}, {QStringLiteral("sha256"), QString(64, QLatin1Char('a'))},
            {QStringLiteral("tentatives"), 0}}).toJson());
        etat.close();
        UpdateService service(QStringLiteral("1.0.1"), nullptr, banc.sources());
        QVERIFY(!service.installPendingAtStartup());
        QVERIFY(banc.lancements.isEmpty());
        QVERIFY(QFile::exists(banc.dossier.filePath(QStringLiteral("garder.txt"))));
        QVERIFY(!QFile::exists(banc.dossier.filePath(QStringLiteral("attente.json"))));
    }
};
QTEST_GUILESS_MAIN(TestUpdates)
#include "tst_updates.moc"
