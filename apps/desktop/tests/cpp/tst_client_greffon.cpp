// Client REST du greffon acp-poste : chemins, verbes et corps EXACTS, en porteur, sans
// Origin ; identifiants illisibles et champs inconnus refusés avant tout envoi.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "support/FauxHermes.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTest>

#include <algorithm>
#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste");

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};

    Banc()
    {
        serveur.installerAuthentification();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    }

    //! Attend la fin de l'appel ; rend l'erreur (vide si réussi).
    static ApiError attendre(ApiCall *appel)
    {
        bool fini = false;
        ApiError erreur;
        QObject::connect(appel, &ApiCall::succeeded, appel, [&fini] { fini = true; });
        QObject::connect(appel, &ApiCall::failed, appel, [&](const ApiError &e) {
            erreur = e;
            fini = true;
        });
        if (!QTest::qWaitFor([&fini] { return fini; }, 5000)) {
            return ApiError(ApiFailure::Timeout, QStringLiteral("appel jamais terminé"));
        }
        return erreur;
    }
};

} // namespace

class TestClientGreffon : public QObject
{
    Q_OBJECT

private slots:
    void lecturesSurLesBonsChemins();
    void ecrituresAvecLesCorpsExacts();
    void lancementSeulAvecCleDIdempotence();
    void identifiantsIllisiblesRefusesSansEnvoi();
    void champsInconnusEtRaisonTropLongueRefuses();
};

void TestClientGreffon::lecturesSurLesBonsChemins()
{
    Banc banc;
    Banc::attendre(banc.greffon.meta());
    Banc::attendre(banc.greffon.catalogue());
    Banc::attendre(banc.greffon.projets());
    Banc::attendre(banc.greffon.projet(QStringLiteral("prj_42")));
    Banc::attendre(banc.greffon.carteDuProjet(QStringLiteral("prj_42"), QStringLiteral("t_9f2c")));
    Banc::attendre(banc.greffon.questions());
    Banc::attendre(banc.greffon.poste());
    Banc::attendre(banc.greffon.routage());
    Banc::attendre(banc.greffon.quotas());
    const QStringList attendus = {
        kP + QStringLiteral("/v1/meta"), kP + QStringLiteral("/v1/catalogue"), kP + QStringLiteral("/v1/projets"),
        kP + QStringLiteral("/v1/projets/prj_42"), kP + QStringLiteral("/v1/projets/prj_42/cartes/t_9f2c"),
        kP + QStringLiteral("/v1/questions"), kP + QStringLiteral("/v1/poste"),
        kP + QStringLiteral("/v1/routage"), kP + QStringLiteral("/v1/quotas"),
    };
    QCOMPARE(banc.serveur.requetes.size(), attendus.size());
    for (qsizetype index = 0; index < attendus.size(); ++index) {
        const RequeteRecue &requete = banc.serveur.requetes.at(index);
        QCOMPARE(requete.methode, QByteArrayLiteral("GET"));
        QCOMPARE(requete.chemin, attendus.at(index));
        QCOMPARE(requete.entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
        QVERIFY(!requete.aEntete("origin"));
        QVERIFY(!requete.aEntete("idempotency-key"));
    }
}

void TestClientGreffon::ecrituresAvecLesCorpsExacts()
{
    Banc banc;
    // Le suivi est branché dès la création : un appel terminé se détruit tout seul.
    const auto suivre = [](ApiCall *appel) {
        auto fini = std::make_shared<bool>(false);
        QObject::connect(appel, &ApiCall::succeeded, appel, [fini] { *fini = true; });
        QObject::connect(appel, &ApiCall::failed, appel, [fini] { *fini = true; });
        return fini;
    };
    struct Cas
    {
        std::shared_ptr<bool> fini;
        QString chemin;
        QJsonObject corps;
    };
    const QList<Cas> cas = {
        {suivre(banc.greffon.mettreProjetEnPause(QStringLiteral("prj_42"))), kP + QStringLiteral("/v1/projets/prj_42/pause"), {}},
        {suivre(banc.greffon.reprendreProjet(QStringLiteral("prj_42"))), kP + QStringLiteral("/v1/projets/prj_42/reprise"), {}},
        {suivre(banc.greffon.repondre(QStringLiteral("q_7"), QStringLiteral("Oui, avec la base PostgreSQL."))),
         kP + QStringLiteral("/v1/questions/q_7/reponse"),
         QJsonObject{{QStringLiteral("reponse"), QStringLiteral("Oui, avec la base PostgreSQL.")}}},
        {suivre(banc.greffon.reprendreTriage(QStringLiteral("acp-prj-42"), QStringLiteral("t_1"), QStringLiteral("Essaie encore"))),
         kP + QStringLiteral("/v1/triage/acp-prj-42/t_1/reprendre"),
         QJsonObject{{QStringLiteral("consigne"), QStringLiteral("Essaie encore")}}},
        {suivre(banc.greffon.reprendreTriage(QStringLiteral("acp-prj-42"), QStringLiteral("t_2"), QString())),
         kP + QStringLiteral("/v1/triage/acp-prj-42/t_2/reprendre"), {}},
        {suivre(banc.greffon.conclureTriage(QStringLiteral("acp-prj-42"), QStringLiteral("t_3"))),
         kP + QStringLiteral("/v1/triage/acp-prj-42/t_3/conclure"), {}},
        {suivre(banc.greffon.pauseGenerale(true, QStringLiteral("maintenance"))), kP + QStringLiteral("/v1/pause"),
         QJsonObject{{QStringLiteral("generale"), true}, {QStringLiteral("raison"), QStringLiteral("maintenance")}}},
        {suivre(banc.greffon.pauseGenerale(false, QString())), kP + QStringLiteral("/v1/pause"),
         QJsonObject{{QStringLiteral("generale"), false}}},
        {suivre(banc.greffon.enrolerPoste()), kP + QStringLiteral("/v1/poste/enrolement"), {}},
        {suivre(banc.greffon.confirmerEmpreinte(QStringLiteral("m-1"), QStringLiteral("AB:CD"))),
         kP + QStringLiteral("/v1/poste/confirmation"),
         QJsonObject{{QStringLiteral("machine_id"), QStringLiteral("m-1")}, {QStringLiteral("empreinte"), QStringLiteral("AB:CD")}}},
        {suivre(banc.greffon.revoquerPoste(QStringLiteral("m-1"), QStringLiteral("poste perdu"))),
         kP + QStringLiteral("/v1/poste/revocation"),
         QJsonObject{{QStringLiteral("machine_id"), QStringLiteral("m-1")}, {QStringLiteral("motif"), QStringLiteral("poste perdu")}}},
        {suivre(banc.greffon.releverPoste()), kP + QStringLiteral("/v1/poste/releve"), {}},
        {suivre(banc.greffon.validerRoutage(QJsonArray{QStringLiteral("r1")}, QJsonObject{{QStringLiteral("codage"), QJsonArray{}}})),
         kP + QStringLiteral("/v1/routage"),
         QJsonObject{{QStringLiteral("releves"), QJsonArray{QStringLiteral("r1")}},
                     {QStringLiteral("classes"), QJsonObject{{QStringLiteral("codage"), QJsonArray{}}}}}},
        {suivre(banc.greffon.accepterReleve(QStringLiteral("r1"))), kP + QStringLiteral("/v1/routage/releve-accepte"),
         QJsonObject{{QStringLiteral("releve_id"), QStringLiteral("r1")}}},
        {suivre(banc.greffon.desactiverSurcharge(QStringLiteral("s_5"))),
         kP + QStringLiteral("/v1/routage/surcharges/s_5/desactiver"), {}},
    };
    QTRY_VERIFY_WITH_TIMEOUT(std::all_of(cas.cbegin(), cas.cend(), [](const Cas &un) { return *un.fini; }), 10000);
    // Les appels partent en parallèle : chaque cas doit trouver SA requête, une seule fois.
    QList<RequeteRecue> recues = banc.serveur.requetes;
    QCOMPARE(recues.size(), cas.size());
    for (const Cas &un : cas) {
        const auto trouve = std::find_if(recues.begin(), recues.end(), [&un](const RequeteRecue &r) {
            return r.chemin == un.chemin && r.json() == un.corps;
        });
        QVERIFY2(trouve != recues.end(), qPrintable(un.chemin));
        QCOMPARE(trouve->methode, QByteArrayLiteral("POST"));
        QCOMPARE(trouve->entete("content-type"), QByteArrayLiteral("application/json"));
        QVERIFY(!trouve->corps.isEmpty());
        QVERIFY(!trouve->aEntete("origin"));
        QVERIFY(!trouve->aEntete("idempotency-key"));
        QCOMPARE(trouve->entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
        recues.erase(trouve);
    }
}

void TestClientGreffon::lancementSeulAvecCleDIdempotence()
{
    Banc banc;
    const QJsonObject formulaire{{QStringLiteral("titre"), QStringLiteral("Site vitrine")},
                                 {QStringLiteral("objectif"), QStringLiteral("Une page d'accueil")},
                                 {QStringLiteral("profil"), QStringLiteral("codage")},
                                 {QStringLiteral("depot"), QStringLiteral("depot-1")},
                                 {QStringLiteral("reponses"), QJsonObject{}}};
    Banc::attendre(banc.greffon.lancerProjet(formulaire, QStringLiteral("projet.lancer.abc123")));
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/v1/projets"));
    QVERIFY(envois.size() >= 1);
    QCOMPARE(envois.first().entete("idempotency-key"), QByteArrayLiteral("projet.lancer.abc123"));
    QCOMPARE(envois.first().json(), formulaire);
    // Sans clé : refus local.
    const ApiError sansCle = Banc::attendre(banc.greffon.lancerProjet(formulaire, QString()));
    QCOMPARE(sansCle.kind(), ApiFailure::ClientRefusal);
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/v1/projets")).size(), envois.size());
}

void TestClientGreffon::identifiantsIllisiblesRefusesSansEnvoi()
{
    Banc banc;
    for (const QString &mauvais : {QStringLiteral("../meta"), QStringLiteral("a/b"), QStringLiteral(""),
                                   QStringLiteral("avec espace"), QStringLiteral("q?x=1"), QStringLiteral("é")}) {
        const ApiError erreur = Banc::attendre(banc.greffon.repondre(mauvais, QStringLiteral("r")));
        QCOMPARE(erreur.kind(), ApiFailure::ClientRefusal);
        QVERIFY(erreur.detail().contains(QStringLiteral("question")));
        QVERIFY(!ClientGreffonPoste::identifiantValide(mauvais));
    }
    QCOMPARE(Banc::attendre(banc.greffon.projet(QStringLiteral("x/../y"))).kind(), ApiFailure::ClientRefusal);
    QCOMPARE(Banc::attendre(banc.greffon.conclureTriage(QStringLiteral("t"), QStringLiteral("c#1"))).kind(),
             ApiFailure::ClientRefusal);
    QVERIFY(banc.serveur.requetes.isEmpty());
    QVERIFY(ClientGreffonPoste::identifiantValide(QStringLiteral("t_9f2c-a.b:c")));
}

void TestClientGreffon::champsInconnusEtRaisonTropLongueRefuses()
{
    Banc banc;
    const ApiError inconnu = Banc::attendre(banc.greffon.lancerProjet(
        QJsonObject{{QStringLiteral("titre"), QStringLiteral("x")}, {QStringLiteral("modele"), QStringLiteral("gpt")}},
        QStringLiteral("cle")));
    QCOMPARE(inconnu.kind(), ApiFailure::ClientRefusal);
    QVERIFY(inconnu.detail().contains(QStringLiteral("modele")));
    const ApiError raison = Banc::attendre(banc.greffon.pauseGenerale(true, QString(201, QLatin1Char('x'))));
    QCOMPARE(raison.kind(), ApiFailure::ClientRefusal);
    QVERIFY(banc.serveur.requetes.isEmpty());
}

QTEST_GUILESS_MAIN(TestClientGreffon)

#include "tst_client_greffon.moc"
