// Diagnostics de la station (cahier P8 § 7.8, § 8) :
//  - une valeur jamais mesurée dit « Inconnu » ou « Non configuré », grisée (known = faux) ;
//    aucune ligne n'est « OK » par défaut ; versions de compilation et contrats épinglés lus ;
//  - contrôle RÉEL des préférences : toutes les clés présentes sont énumérées ; une clé hors
//    liste blanche ou une valeur qui ressemble à un jeton est signalée par son NOM, jamais
//    par sa valeur, ni à l'écran ni dans le rapport ;
//  - compteurs de la passerelle (-32601 renvoyés, trames illisibles) relus ;
//  - un secret venu du serveur (alerte de /v1/meta) est expurgé à l'écran comme au rapport.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "app/BuildConfig.h"
#include "auth/SessionHermes.h"
#include "diagnostics/Redaction.h"
#include "events/EventStreamService.h"
#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"
#include "services/CompatibiliteHermes.h"
#include "services/HealthService.h"
#include "storage/SettingsStore.h"
#include "support/CoffreMemoire.h"
#include "support/FauxHermes.h"
#include "system/SystemAppearance.h"
#include "viewmodels/DiagnosticsViewModel.h"

#include <QCoreApplication>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSettings>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>

using namespace acp;
using namespace acp::test;

namespace {

//! JWT synthétique assemblé à l'exécution (le balayage des secrets du dépôt le prendrait sinon
//! pour un vrai jeton).
QString jwtSynthetique()
{
    return QStringLiteral("eyJ") + QStringLiteral("hbGciOiJIUzI1NiJ9.") + QStringLiteral("eyJ")
        + QStringLiteral("zdWIiOiJkaWFnbm9zdGljIn0.") + QStringLiteral("c2lnbmF0dXJlLWRlLXRlc3Q");
}

QJsonObject metaDeReference()
{
    QFile fichier(QStringLiteral(ACP_TEST_FIXTURE_DIR "/hermes/meta.json"));
    if (!fichier.open(QIODevice::ReadOnly)) {
        qFatal("Document de référence /v1/meta introuvable");
    }
    return QJsonDocument::fromJson(fichier.readAll()).object();
}

struct Banc
{
    SettingsStore reglages;
    ApiClient client;
    CoffreMemoire coffre;
    SessionHermes session{&client, &coffre, &reglages};
    ClientGreffonPoste greffon{&client};
    CompatibiliteHermes compatibilite{&greffon};
    GatewayClient passerelle{&client};
    EventStreamService flux{&client, &greffon, &passerelle};
    HealthService sante{&client};
    SystemAppearance apparence{&reglages};
    DiagnosticsViewModel diagnostics{&client,   &session,  &compatibilite, &passerelle,
                                     &sante,    &reglages, &apparence,     &coffre,
                                     QStringLiteral("0.11.0"), QStringLiteral("essai")};

    Banc() { diagnostics.setFlux(&flux); }
    ~Banc() { reglages.clear(); }

    [[nodiscard]] QModelIndex ligne(const QString &libelle) const
    {
        for (int rang = 0; rang < diagnostics.rowCount(); ++rang) {
            const QModelIndex index = diagnostics.index(rang);
            if (index.data(DiagnosticsViewModel::LabelRole).toString() == libelle) {
                return index;
            }
        }
        return {};
    }
    [[nodiscard]] QString valeur(const QString &libelle) const
    {
        const QModelIndex index = ligne(libelle);
        if (!index.isValid()) {
            qFatal("ligne de diagnostic absente : %s", qPrintable(libelle));
        }
        return index.data(DiagnosticsViewModel::ValueRole).toString();
    }
    [[nodiscard]] bool connue(const QString &libelle) const
    {
        return ligne(libelle).data(DiagnosticsViewModel::KnownRole).toBool();
    }
    [[nodiscard]] QStringList valeurs(const QString &libelle) const
    {
        QStringList resultat;
        for (int rang = 0; rang < diagnostics.rowCount(); ++rang) {
            const QModelIndex index = diagnostics.index(rang);
            if (index.data(DiagnosticsViewModel::LabelRole).toString() == libelle) {
                resultat.append(index.data(DiagnosticsViewModel::ValueRole).toString());
            }
        }
        return resultat;
    }
    [[nodiscard]] QStringList toutesLesValeurs() const
    {
        QStringList resultat;
        for (int rang = 0; rang < diagnostics.rowCount(); ++rang) {
            resultat.append(diagnostics.index(rang).data(DiagnosticsViewModel::ValueRole).toString());
        }
        return resultat;
    }
};

} // namespace

class TestDiagnostics : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void valeursInconnuesJamaisInventees();
    void controleDesPreferencesSansValeur();
    void compteursDeLaPasserelle();
    void secretDuServeurExpurgeALEcranEtAuRapport();

private:
    QTemporaryDir m_dossier;
};

void TestDiagnostics::initTestCase()
{
    QVERIFY(m_dossier.isValid());
    // Portée de préférences propre au test : le registre réel du poste n'est jamais touché.
    QCoreApplication::setOrganizationName(
        QStringLiteral("ACP Test %1").arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
    QCoreApplication::setApplicationName(QStringLiteral("Diagnostics"));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, m_dossier.path());
}

void TestDiagnostics::valeursInconnuesJamaisInventees()
{
    Banc banc;
    QCOMPARE(banc.valeur(QStringLiteral("Adresse du serveur")), QStringLiteral("Non configuré"));
    QVERIFY(!banc.connue(QStringLiteral("Adresse du serveur")));
    QCOMPARE(banc.valeur(QStringLiteral("Version de Hermes annoncée")), QStringLiteral("Inconnu"));
    QVERIFY(!banc.connue(QStringLiteral("Version de Hermes annoncée")));
    QVERIFY(!banc.connue(QStringLiteral("Verdict")));
    QCOMPARE(banc.valeur(QStringLiteral("Hermes servi")), QStringLiteral("Inconnu"));
    QCOMPARE(banc.valeur(QStringLiteral("Exécutant Railway (P6)")), QStringLiteral("Inconnu"));
    QVERIFY(!banc.connue(QStringLiteral("Alertes de Hermes")));
    QVERIFY(banc.valeur(QStringLiteral("Flux d'événements du greffon")).startsWith(QStringLiteral("Non disponible")));
    QVERIFY(!banc.connue(QStringLiteral("Flux d'événements du greffon")));
    QCOMPARE(banc.valeur(QStringLiteral("Entrée au coffre pour ce serveur")), QStringLiteral("Absente"));

    // Versions et contrats épinglés : lus de la construction, jamais du serveur.
    QCOMPARE(banc.valeur(QStringLiteral("Version de Qt (compilation)")), QString::fromLatin1(QT_VERSION_STR));
    QCOMPARE(banc.valeur(QStringLiteral("Hermes testé par cette station")), QString::fromLatin1(ACP_HERMES_VERSION));
    QCOMPARE(banc.valeur(QStringLiteral("Contrat attendu")), QString::fromLatin1(ACP_CONTRAT_ACP_POSTE));
    QCOMPARE(banc.valeur(QStringLiteral("Empreinte OpenRPC épinglée")), QString::fromLatin1(ACP_OPENRPC_SHA256));

    // Aucune ligne vide, aucun « OK » de complaisance.
    for (const QString &valeur : banc.toutesLesValeurs()) {
        QVERIFY(!valeur.trimmed().isEmpty());
        QVERIFY2(valeur.compare(QStringLiteral("OK"), Qt::CaseInsensitive) != 0, qPrintable(valeur));
    }
}

void TestDiagnostics::controleDesPreferencesSansValeur()
{
    Banc banc;
    banc.reglages.setThemePreference(QStringLiteral("dark"));
    banc.reglages.setServerUrl(QUrl(QStringLiteral("https://hermes-acp.test")));
    banc.reglages.flush();
    banc.diagnostics.refresh();
    QCOMPARE(banc.valeur(QStringLiteral("Clés de préférences présentes")), QStringLiteral("2"));
    QVERIFY2(banc.valeur(QStringLiteral("Contrôle des préférences")).startsWith(QStringLiteral("Conforme")),
             qPrintable(banc.valeur(QStringLiteral("Contrôle des préférences"))));

    // Un autre programme (ou une ancienne version) a écrit une clé étrangère et un jeton.
    const QString jwt = jwtSynthetique();
    const QString valeurEtrangere = QStringLiteral("valeur-etrangere-42");
    {
        QSettings brut;
        brut.setValue(QStringLiteral("session/jetonRafraichissement"), valeurEtrangere);
        brut.setValue(QStringLiteral("connection/serverUrl"), QStringLiteral("https://hermes-acp.test/?ticket=") + jwt);
        brut.sync();
    }
    banc.diagnostics.refresh();
    const QString verdict = banc.valeur(QStringLiteral("Contrôle des préférences"));
    QVERIFY2(verdict.startsWith(QStringLiteral("Écart — ")), qPrintable(verdict));
    QVERIFY2(verdict.contains(QStringLiteral("clé(s) hors liste blanche : session/jetonRafraichissement")),
             qPrintable(verdict));
    QVERIFY2(verdict.contains(QStringLiteral("valeur ressemblant à un jeton sous : connection/serverUrl (valeur "
                                             "jamais affichée)")),
             qPrintable(verdict));
    QCOMPARE(banc.valeur(QStringLiteral("Clés de préférences présentes")), QStringLiteral("3"));

    // Ni l'écran ni le rapport ne portent les valeurs.
    const QString rapport = banc.diagnostics.buildReport();
    QVERIFY(rapport.contains(QStringLiteral("Contrôle des préférences : Écart")));
    for (const QString &texte : banc.toutesLesValeurs() + QStringList{rapport}) {
        QVERIFY(!texte.contains(jwt));
        QVERIFY(!texte.contains(QStringLiteral("c2lnbmF0dXJlLWRlLXRlc3Q")));
        QVERIFY(!texte.contains(valeurEtrangere));
    }
}

void TestDiagnostics::compteursDeLaPasserelle()
{
    Banc banc;
    QCOMPARE(banc.valeur(QStringLiteral("Requêtes de l'agent refusées (-32601)")), QStringLiteral("0"));
    QCOMPARE(banc.valeur(QStringLiteral("Trames illisibles ignorées")), QStringLiteral("0"));
    QList<QByteArray> emises;
    banc.passerelle.canal()->attacher([&emises](const QByteArray &trame) {
        emises.append(trame);
        return true;
    });
    banc.passerelle.canal()->recevoir(
        QByteArrayLiteral("{\"jsonrpc\":\"2.0\",\"id\":\"r-7\",\"method\":\"secret\",\"params\":{}}"));
    banc.passerelle.canal()->recevoir(QByteArrayLiteral("pas du json"));
    banc.diagnostics.refresh();
    QCOMPARE(banc.valeur(QStringLiteral("Requêtes de l'agent refusées (-32601)")), QStringLiteral("1"));
    QCOMPARE(banc.valeur(QStringLiteral("Trames illisibles ignorées")), QStringLiteral("1"));
    // Le refus est bien parti, au même identifiant, avec le code exact.
    QCOMPARE(emises.size(), 1);
    const QJsonObject refus = QJsonDocument::fromJson(emises.constFirst()).object();
    QCOMPARE(refus.value(QStringLiteral("id")).toString(), QStringLiteral("r-7"));
    QCOMPARE(refus.value(QStringLiteral("error")).toObject().value(QStringLiteral("code")).toInt(), -32601);
    banc.passerelle.canal()->detacher(QStringLiteral("fin du test"));
}

void TestDiagnostics::secretDuServeurExpurgeALEcranEtAuRapport()
{
    const QString jwt = jwtSynthetique();
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    QJsonObject meta = metaDeReference();
    meta.insert(QStringLiteral("alertes"),
                QJsonArray{QStringLiteral("Jeton vu dans un journal : Authorization: Bearer %1").arg(jwt),
                           QStringLiteral("Sauvegarde du volume ancienne de 9 jours")});
    serveur.route("GET", QStringLiteral("/api/plugins/acp-poste/v1/meta"),
                  [&meta](const RequeteRecue &) { return ReponseFaux::json(200, meta); });

    Banc banc;
    banc.client.setAllowInsecureLoopback(true);
    QVERIFY(!banc.client.setBaseUrl(serveur.url()).isError());
    banc.client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    banc.compatibilite.verifier();
    QTRY_VERIFY(banc.compatibilite.etat() != CompatibilityStatus::Verification);
    QCOMPARE(banc.valeur(QStringLiteral("Alertes de Hermes")), QStringLiteral("2"));
    const QStringList alertes = banc.valeurs(QStringLiteral("Alerte"));
    QCOMPARE(alertes.size(), 2);
    QVERIFY(alertes.contains(QStringLiteral("Sauvegarde du volume ancienne de 9 jours")));
    QVERIFY(alertes.constFirst().contains(QString::fromUtf8(kRedactionPlaceholder)));
    const QString rapport = banc.diagnostics.buildReport();
    for (const QString &texte : banc.toutesLesValeurs() + QStringList{rapport}) {
        QVERIFY(!texte.contains(jwt));
        QVERIFY(!texte.contains(QStringLiteral("c2lnbmF0dXJlLWRlLXRlc3Q")));
        QVERIFY(!texte.contains(QStringLiteral("jeton-a")));
    }
    QVERIFY(rapport.contains(QStringLiteral("Sauvegarde du volume ancienne de 9 jours")));
}

QTEST_MAIN(TestDiagnostics)
#include "tst_diagnostics.moc"
