// Compatibilité de la station avec le Hermes servi (/v1/meta du greffon acp-poste).
//
// Contrat incompatible ⇒ refus des pages du greffon ; OpenRPC d'une autre version ⇒
// Discussion coupée ; empreinte différente ⇒ avertissement ; Hermes non testé ⇒
// avertissement ; /v1/meta en 404 ⇒ greffon absent ; exécutant de P6 détecté par
// `machine.executant`, jamais supposé.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "app/BuildConfig.h"
#include "services/CompatibiliteHermes.h"
#include "support/FauxHermes.h"

#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

QJsonObject metaDeReference()
{
    QFile fichier(QStringLiteral(ACP_TEST_FIXTURE_DIR "/hermes/meta.json"));
    if (!fichier.open(QIODevice::ReadOnly)) {
        qFatal("Document de référence /v1/meta introuvable");
    }
    return QJsonDocument::fromJson(fichier.readAll()).object();
}

QJsonObject avec(QJsonObject meta, const QString &bloc, const QString &cle, const QJsonValue &valeur)
{
    QJsonObject sous = meta.value(bloc).toObject();
    sous.insert(cle, valeur);
    meta.insert(bloc, sous);
    return meta;
}

} // namespace

class TestCompatibiliteHermes : public QObject
{
    Q_OBJECT

private slots:
    void referenceConforme();
    void contratIncompatibleBloqueLeGreffon();
    void openRpcDUneAutreVersionCoupeLaDiscussion();
    void empreinteDifferenteAvertit();
    void hermesNonTesteAvertit();
    void alertesComptees();
    void executantDetecteSansSupposition();
    void lectureContreLeFauxHermes();
    void greffonAbsentSur404();
};

void TestCompatibiliteHermes::referenceConforme()
{
    const auto evaluation = CompatibiliteHermes::evaluer(metaDeReference());
    QCOMPARE(evaluation.etat, CompatibilityStatus::Compatible);
    QVERIFY(evaluation.greffonDisponible);
    QVERIFY(evaluation.discussionDisponible);
    QVERIFY(evaluation.avertissements.isEmpty());
    QCOMPARE(evaluation.versionHermes, QString::fromLatin1(ACP_HERMES_VERSION));
    QCOMPARE(evaluation.contratRecu, QString::fromLatin1(ACP_CONTRAT_ACP_POSTE));
    QVERIFY(!evaluation.executantPresent);
}

void TestCompatibiliteHermes::contratIncompatibleBloqueLeGreffon()
{
    for (const QString &contrat : {QStringLiteral("acp-poste/2"), QStringLiteral("autre/1"), QString()}) {
        QJsonObject meta = metaDeReference();
        meta.insert(QStringLiteral("contrat"), contrat);
        const auto evaluation = CompatibiliteHermes::evaluer(meta);
        QCOMPARE(evaluation.etat, CompatibilityStatus::Incompatible);
        QVERIFY(!evaluation.greffonDisponible);
        QVERIFY(evaluation.explication.startsWith(QStringLiteral("Contrat du greffon incompatible")));
        QVERIFY(evaluation.explication.contains(QStringLiteral("attendu acp-poste/1")));
    }
    // Une mineure ajoutée reste la même majeure.
    QJsonObject mineure = metaDeReference();
    mineure.insert(QStringLiteral("contrat"), QStringLiteral("acp-poste/1.3"));
    QVERIFY(CompatibiliteHermes::evaluer(mineure).greffonDisponible);
}

void TestCompatibiliteHermes::openRpcDUneAutreVersionCoupeLaDiscussion()
{
    const auto evaluation = CompatibiliteHermes::evaluer(
        avec(metaDeReference(), QStringLiteral("openrpc"), QStringLiteral("info_version"), QStringLiteral("2")));
    QVERIFY(!evaluation.discussionDisponible);
    QVERIFY(evaluation.greffonDisponible);
    QCOMPARE(evaluation.etat, CompatibilityStatus::Avertissement);
    QVERIFY(evaluation.avertissements.join(QLatin1Char(' ')).contains(QStringLiteral("Discussion coupée")));
}

void TestCompatibiliteHermes::empreinteDifferenteAvertit()
{
    QJsonObject meta = avec(metaDeReference(), QStringLiteral("openrpc"), QStringLiteral("identique"), false);
    meta = avec(meta, QStringLiteral("openrpc"), QStringLiteral("empreinte_installee"), QString(64, QLatin1Char('0')));
    const auto evaluation = CompatibiliteHermes::evaluer(meta);
    QCOMPARE(evaluation.etat, CompatibilityStatus::Avertissement);
    QVERIFY(evaluation.discussionDisponible);
    QVERIFY(evaluation.explication.contains(QStringLiteral("diffère")));
}

void TestCompatibiliteHermes::hermesNonTesteAvertit()
{
    const auto evaluation = CompatibiliteHermes::evaluer(
        avec(metaDeReference(), QStringLiteral("hermes"), QStringLiteral("version"), QStringLiteral("0.22.0")));
    QCOMPARE(evaluation.etat, CompatibilityStatus::Avertissement);
    QVERIFY(evaluation.explication.contains(
        QStringLiteral("Hermes 0.22.0 n'est pas la version testée (%1)").arg(QString::fromLatin1(ACP_HERMES_VERSION))));
    const auto inconnue = CompatibiliteHermes::evaluer(
        avec(metaDeReference(), QStringLiteral("hermes"), QStringLiteral("version"), QJsonValue::Null));
    QVERIFY(inconnue.avertissements.contains(QStringLiteral("Version de Hermes inconnue.")));
}

void TestCompatibiliteHermes::alertesComptees()
{
    QJsonObject meta = metaDeReference();
    meta.insert(QStringLiteral("alertes"), QJsonArray{QStringLiteral("SOUL.md a été modifié."),
                                                      QStringLiteral("Greffons utilisateur présents.")});
    const auto evaluation = CompatibiliteHermes::evaluer(meta);
    QCOMPARE(evaluation.etat, CompatibilityStatus::Avertissement);
    QCOMPARE(evaluation.alertes.size(), 2);
    QVERIFY(evaluation.explication.startsWith(QStringLiteral("2 alerte(s)")));
}

void TestCompatibiliteHermes::executantDetecteSansSupposition()
{
    QVERIFY(!CompatibiliteHermes::evaluer(metaDeReference()).executantPresent);
    const auto evaluation = CompatibiliteHermes::evaluer(
        avec(metaDeReference(), QStringLiteral("machine"), QStringLiteral("executant"),
             QJsonObject{{QStringLiteral("plateforme"), QStringLiteral("railway")}}));
    QVERIFY(evaluation.executantPresent);
    QVERIFY(!CompatibiliteHermes::evaluer(avec(metaDeReference(), QStringLiteral("machine"),
                                                QStringLiteral("executant"), QJsonValue::Null))
                 .executantPresent);
}

void TestCompatibiliteHermes::lectureContreLeFauxHermes()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    serveur.route("GET", QStringLiteral("/api/plugins/acp-poste/v1/meta"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, metaDeReference());
    });
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(serveur.url()).isError());
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    ClientGreffonPoste greffon(&client);
    CompatibiliteHermes compatibilite(&greffon);
    QCOMPARE(compatibilite.etat(), CompatibilityStatus::NonVerifiee);
    QCOMPARE(compatibilite.versionHermes(), QStringLiteral("Inconnu"));
    compatibilite.verifier();
    QCOMPARE(compatibilite.etat(), CompatibilityStatus::Verification);
    QTRY_COMPARE(compatibilite.etat(), CompatibilityStatus::Compatible);
    QCOMPARE(compatibilite.libelle(), QStringLiteral("Compatible"));
    QCOMPARE(serveur.filtrer("GET", QStringLiteral("/api/plugins/acp-poste/v1/meta")).first().entete("authorization"),
             QByteArrayLiteral("Bearer jeton-a"));
    compatibilite.oublier();
    QCOMPARE(compatibilite.etat(), CompatibilityStatus::NonVerifiee);
}

void TestCompatibiliteHermes::greffonAbsentSur404()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(serveur.url()).isError());
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    ClientGreffonPoste greffon(&client);
    CompatibiliteHermes compatibilite(&greffon);
    compatibilite.verifier();
    QTRY_COMPARE(compatibilite.etat(), CompatibilityStatus::GreffonAbsent);
    QVERIFY(!compatibilite.greffonDisponible());
    QVERIFY(compatibilite.discussionDisponible());
    QVERIFY(compatibilite.explication().contains(QStringLiteral("Greffon acp-poste absent")));
}

QTEST_GUILESS_MAIN(TestCompatibiliteHermes)

#include "tst_compatibilite_hermes.moc"
