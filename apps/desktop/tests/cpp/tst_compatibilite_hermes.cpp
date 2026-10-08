// Compatibilité de la station avec le Hermes servi (/v1/meta du greffon acp-poste).
//
// Contrat incompatible ⇒ refus des pages du greffon, APPLIQUÉ : aucune lecture ni écriture du
// greffon ne part plus (seul /v1/meta, pour revérifier) ; OpenRPC d'une autre version ⇒
// Discussion coupée ; empreinte différente ⇒ avertissement ; Hermes non testé ⇒
// avertissement ; /v1/meta en 404 ⇒ greffon absent, bloqué de même ; exécutant de P6 détecté
// par `machine.executant`, jamais supposé.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "app/BuildConfig.h"
#include "events/EventStreamService.h"
#include "services/CompatibiliteHermes.h"
#include "support/FauxHermes.h"
#include "viewmodels/QuestionsViewModel.h"

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

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");

//! Chaque route du greffon, appelée une fois : lectures et écritures du propriétaire.
QList<ApiCall *> toutesLesRoutes(ClientGreffonPoste &greffon)
{
    return {greffon.catalogue(), greffon.projets(), greffon.projet(QStringLiteral("p_367e23fd51b7")),
            greffon.carteDuProjet(QStringLiteral("p_367e23fd51b7"), QStringLiteral("t_7aa28f61")),
            greffon.questions(), greffon.poste(), greffon.routage(), greffon.quotas(),
            greffon.lancerProjet(QJsonObject{{QStringLiteral("titre"), QStringLiteral("Essai")}}, QStringLiteral("cle-1")),
            greffon.mettreProjetEnPause(QStringLiteral("p_367e23fd51b7")), greffon.reprendreProjet(QStringLiteral("p_367e23fd51b7")),
            greffon.repondre(QStringLiteral("q_b627a3c245ec"), QStringLiteral("Python 3.12")),
            greffon.reprendreTriage(QStringLiteral("acp-veille"), QStringLiteral("t_0c1d2e3f"), QString()),
            greffon.conclureTriage(QStringLiteral("acp-veille"), QStringLiteral("t_0c1d2e3f")),
            greffon.pauseGenerale(true, QString()), greffon.enrolerPoste(),
            greffon.confirmerEmpreinte(QStringLiteral("m1"), QStringLiteral("e1")),
            greffon.revoquerPoste(QStringLiteral("m1"), QStringLiteral("essai")), greffon.releverPoste(),
            greffon.validerRoutage(QJsonArray{}, QJsonArray{}), greffon.accepterReleve(1),
            greffon.desactiverSurcharge(QStringLiteral("s1"))};
}

//! Requêtes reçues par le faux Hermes sur le greffon, hors /v1/meta.
int requetesDuGreffon(const FauxHermes &serveur)
{
    int total = 0;
    for (const RequeteRecue &requete : serveur.requetes) {
        if (requete.chemin.startsWith(kP) && requete.chemin != kP + QStringLiteral("/meta")) {
            ++total;
        }
    }
    return total;
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
    void contratIncompatibleRefuse();
    void contratIncompatibleBloqueToutesLesRoutesDuGreffon();
    void greffonAbsentBloqueToutesLesRoutesDuGreffon();
    void openRpcDUneAutreVersionCoupeLaDiscussion();
    void empreinteDifferenteAvertit();
    void hermesNonTesteAvertit();
    void alertesComptees();
    void executantDetecteSansSupposition();
    void fluxDuGreffonDitCeQueLeServeurAnnonce();
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

void TestCompatibiliteHermes::contratIncompatibleRefuse()
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

// Constat de relecture P8 (haute) : le verdict « Incompatible » n'était qu'affiché ; les pages
// lisaient et écrivaient encore vers le greffon. Il est désormais appliqué au client du greffon.
void TestCompatibiliteHermes::contratIncompatibleBloqueToutesLesRoutesDuGreffon()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    QJsonObject meta = metaDeReference();
    meta.insert(QStringLiteral("contrat"), QStringLiteral("acp-poste/2"));
    serveur.route("GET", kP + QStringLiteral("/meta"), [&meta](const RequeteRecue &) { return ReponseFaux::json(200, meta); });
    // Toute autre route du greffon répondrait : seule la station peut empêcher l'envoi.
    serveur.route("GET", kP + QStringLiteral("/questions"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("questions"), QJsonArray{}}});
    });
    serveur.route("POST", kP + QStringLiteral("/questions/q_b627a3c245ec/reponse"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte_debloquee"), true}});
    });
    ApiClient client;
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(serveur.url()).isError());
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    ClientGreffonPoste greffon(&client);
    CompatibiliteHermes compatibilite(&greffon);
    EventStreamService flux(&client, &greffon, nullptr);
    QuestionsViewModel questions(&client, &greffon, &flux);

    compatibilite.verifier();
    QTRY_COMPARE(compatibilite.etat(), CompatibilityStatus::Incompatible);
    QVERIFY(greffon.bloque());

    // 1. Chaque route du greffon, lecture comme écriture : refusée par la station, rien n'est émis.
    int refusees = 0;
    QStringList messages;
    for (ApiCall *appel : toutesLesRoutes(greffon)) {
        connect(appel, &ApiCall::failed, this, [&refusees, &messages](const ApiError &erreur) {
            if (erreur.kind() == ApiFailure::Incompatible) {
                ++refusees;
                messages.append(erreur.message());
            }
        });
    }
    QTRY_COMPARE(refusees, 22);
    QVERIFY(messages.first().contains(QStringLiteral("Contrat du greffon incompatible : acp-poste/2, attendu acp-poste/1.")));
    QVERIFY(messages.first().contains(QStringLiteral("Pages du greffon bloquées par la station.")));

    // 2. La page Questions : ni lecture, ni réponse ; l'explication est affichée.
    flux.demarrer();
    questions.setPageVisible(true);
    QTRY_VERIFY(questions.erreur().contains(QStringLiteral("Contrat du greffon incompatible")));
    questions.repondre(QStringLiteral("q_b627a3c245ec"), QStringLiteral("Python 3.12"));
    QTRY_VERIFY(questions.erreurGeste().contains(QStringLiteral("Pages du greffon bloquées")));
    QVERIFY(questions.messageGeste().isEmpty());
    QTest::qWait(100);
    QCOMPARE(requetesDuGreffon(serveur), 0);

    // 3. Hermes redéployé avec le bon contrat : la revérification lève le blocage.
    meta.insert(QStringLiteral("contrat"), QString::fromLatin1(ACP_CONTRAT_ACP_POSTE));
    compatibilite.verifier();
    QTRY_COMPARE(compatibilite.etat(), CompatibilityStatus::Compatible);
    QVERIFY(!greffon.bloque());
    questions.actualiser();
    QTRY_VERIFY(serveur.compter("GET", kP + QStringLiteral("/questions")) >= 1);

    // 4. Oubli (session perdue, serveur changé) : plus de verdict, plus de blocage.
    meta.insert(QStringLiteral("contrat"), QStringLiteral("acp-poste/2"));
    compatibilite.verifier();
    QTRY_VERIFY(greffon.bloque());
    compatibilite.oublier();
    QVERIFY(!greffon.bloque());
}

void TestCompatibiliteHermes::greffonAbsentBloqueToutesLesRoutesDuGreffon()
{
    FauxHermes serveur; // aucune route du greffon : /v1/meta rend 404
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
    QVERIFY(greffon.bloque());
    int refusees = 0;
    for (ApiCall *appel : toutesLesRoutes(greffon)) {
        connect(appel, &ApiCall::failed, this, [&refusees](const ApiError &erreur) {
            refusees += erreur.kind() == ApiFailure::Incompatible
                && erreur.detail().contains(QStringLiteral("Greffon acp-poste absent")) ? 1 : 0;
        });
    }
    QTRY_COMPARE(refusees, 22);
    QTest::qWait(50);
    QCOMPARE(requetesDuGreffon(serveur), 0);
    // /v1/meta reste lisible : c'est par elle que le blocage se lève.
    const int lectures = serveur.compter("GET", kP + QStringLiteral("/meta"));
    compatibilite.verifier();
    QTRY_VERIFY(serveur.compter("GET", kP + QStringLiteral("/meta")) > lectures);
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
    // Clé absente (Hermes sans l'étape P6) : « absent ».
    const auto sansP6 = CompatibiliteHermes::evaluer(metaDeReference());
    QVERIFY(!sansP6.executantPresent);
    QCOMPARE(sansP6.etatExecutant, QStringLiteral("absent"));
    // Objet : exécutant annoncé.
    const auto evaluation = CompatibiliteHermes::evaluer(
        avec(metaDeReference(), QStringLiteral("machine"), QStringLiteral("executant"),
             QJsonObject{{QStringLiteral("plateforme"), QStringLiteral("railway")}}));
    QVERIFY(evaluation.executantPresent);
    QCOMPARE(evaluation.etatExecutant, QStringLiteral("annonce"));
    // Constat de relecture P8 : `null` (P6 en place, aucun exécutant connu, meta.py
    // `_resume_executant`) n'est PAS une clé absente.
    const auto aucun = CompatibiliteHermes::evaluer(
        avec(metaDeReference(), QStringLiteral("machine"), QStringLiteral("executant"), QJsonValue::Null));
    QVERIFY(!aucun.executantPresent);
    QCOMPARE(aucun.etatExecutant, QStringLiteral("aucun"));
    // Base du greffon illisible : la clé manque, l'état est inconnu, pas « non déployé ».
    const auto illisible = CompatibiliteHermes::evaluer(
        avec(metaDeReference(), QStringLiteral("machine"), QStringLiteral("base"), QStringLiteral("illisible")));
    QCOMPARE(illisible.etatExecutant, QStringLiteral("illisible"));
    // Rien de lu : inconnu.
    QCOMPARE(CompatibiliteHermes::Evaluation{}.etatExecutant, QStringLiteral("inconnu"));
}

void TestCompatibiliteHermes::fluxDuGreffonDitCeQueLeServeurAnnonce()
{
    // Relecture finale de P7 (constat desktop-1) : le diagnostic disait « n'annonce aucun flux (prévu à l'étape P7) »
    // même devant un greffon de P7 qui l'annonce (clé `flux` de /v1/meta, meta.py `bloc_flux`).
    const auto sansFlux = CompatibiliteHermes::evaluer(metaDeReference());
    QCOMPARE(sansFlux.etatFlux, QStringLiteral("absent"));
    QJsonObject meta = metaDeReference();
    meta.insert(QStringLiteral("flux"), QJsonObject{
        {QStringLiteral("chemin"), QStringLiteral("/api/plugins/acp-poste/v1/flux")}, {QStringLiteral("version"), 1},
        {QStringLiteral("sujets"), QJsonArray{QStringLiteral("projets"), QStringLiteral("questions")}},
        {QStringLiteral("battement_s"), 15}, {QStringLiteral("duree_max_s"), 600}});
    QCOMPARE(CompatibiliteHermes::evaluer(meta).etatFlux, QStringLiteral("annonce"));
    meta.insert(QStringLiteral("flux"), QStringLiteral("oui"));
    QCOMPARE(CompatibiliteHermes::evaluer(meta).etatFlux, QStringLiteral("illisible"));
    QCOMPARE(CompatibiliteHermes::Evaluation{}.etatFlux, QStringLiteral("inconnu"));
    // Ce que le diagnostic en dit : jamais « n'annonce aucun flux » devant une annonce, ni une étape à venir.
    QVERIFY(EventStreamService::etatFluxGreffon(QStringLiteral("annonce"))
                .startsWith(QStringLiteral("Annoncé par le serveur ; non utilisé par cette station")));
    QVERIFY(EventStreamService::etatFluxGreffon(QStringLiteral("absent"))
                .startsWith(QStringLiteral("Non disponible sur ce serveur")));
    QVERIFY(EventStreamService::etatFluxGreffon(QStringLiteral("inconnu")).startsWith(QStringLiteral("Inconnu")));
    for (const QString &etat : {QStringLiteral("annonce"), QStringLiteral("absent"), QStringLiteral("illisible"),
                                QStringLiteral("inconnu")}) {
        QVERIFY(!EventStreamService::etatFluxGreffon(etat).contains(QStringLiteral("étape P7")));
    }
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
