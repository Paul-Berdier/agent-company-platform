// Client REST du greffon acp-poste : chemins, verbes et corps EXACTS, en porteur, sans
// Origin ; identifiants illisibles et champs inconnus refusés avant tout envoi. Routes de P6 et
// P7 (revues, relance, qui répond, clôture, accueil agrégé, flux d'invalidation) comprises.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "support/FauxHermes.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
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
    void quiRepondSeulementAvecUneValeurDuGreffon();
    void fluxOuvertEnPorteurAvecLaRevision();
    void greffonBloqueRefuseLesRoutesDeP7();
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
    Banc::attendre(banc.greffon.accueil());
    const QStringList attendus = {
        kP + QStringLiteral("/v1/meta"), kP + QStringLiteral("/v1/catalogue"), kP + QStringLiteral("/v1/projets"),
        kP + QStringLiteral("/v1/projets/prj_42"), kP + QStringLiteral("/v1/projets/prj_42/cartes/t_9f2c"),
        kP + QStringLiteral("/v1/questions"), kP + QStringLiteral("/v1/poste"),
        kP + QStringLiteral("/v1/routage"), kP + QStringLiteral("/v1/quotas"), kP + QStringLiteral("/v1/accueil"),
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
        {suivre(banc.greffon.accepterReleve(3)), kP + QStringLiteral("/v1/routage/releve-accepte"),
         QJsonObject{{QStringLiteral("releve_id"), 3}}},
        {suivre(banc.greffon.desactiverSurcharge(QStringLiteral("s_5"))),
         kP + QStringLiteral("/v1/routage/surcharges/s_5/desactiver"), {}},
        // Étape P7 (dashboard/plugin_api.py) : relance, qui répond, clôture.
        {suivre(banc.greffon.relancerCarte(QStringLiteral("acp-prj-42"), QStringLiteral("t_4"), QStringLiteral("Reprends le test"))),
         kP + QStringLiteral("/v1/cartes/acp-prj-42/t_4/relancer"),
         QJsonObject{{QStringLiteral("consigne"), QStringLiteral("Reprends le test")}}},
        {suivre(banc.greffon.relancerCarte(QStringLiteral("acp-prj-42"), QStringLiteral("t_5"), QStringLiteral("  "))),
         kP + QStringLiteral("/v1/cartes/acp-prj-42/t_5/relancer"), {}},
        {suivre(banc.greffon.changerReponses(QStringLiteral("prj_43"), QStringLiteral("proprietaire"))),
         kP + QStringLiteral("/v1/projets/prj_43/reponses"),
         QJsonObject{{QStringLiteral("reponses"), QStringLiteral("proprietaire")}}},
        {suivre(banc.greffon.changerReponses(QStringLiteral("prj_44"), QStringLiteral("hermes_d_abord"))),
         kP + QStringLiteral("/v1/projets/prj_44/reponses"),
         QJsonObject{{QStringLiteral("reponses"), QStringLiteral("hermes_d_abord")}}},
        {suivre(banc.greffon.clore(QStringLiteral("prj_45"))), kP + QStringLiteral("/v1/projets/prj_45/clore"),
         QJsonObject{{QStringLiteral("confirmation"), true}}},
        {suivre(banc.greffon.notificationDeTest()), kP + QStringLiteral("/v1/notifications/test"), {}},
        // Étape P6 : revues des fichiers de pilotage.
        {suivre(banc.greffon.accepterRevue(QStringLiteral("acp-prj-42"), QStringLiteral("t_6"))),
         kP + QStringLiteral("/v1/revues/acp-prj-42/t_6/accepter"), {}},
        {suivre(banc.greffon.refuserRevue(QStringLiteral("acp-prj-42"), QStringLiteral("t_7"), QStringLiteral("Retire la règle"))),
         kP + QStringLiteral("/v1/revues/acp-prj-42/t_7/refuser"),
         QJsonObject{{QStringLiteral("motif"), QStringLiteral("Retire la règle")}}},
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
    // Routes de P6 et P7 : même contrôle de chaque segment de chemin.
    QCOMPARE(Banc::attendre(banc.greffon.relancerCarte(QStringLiteral("../t"), QStringLiteral("c"), QString())).kind(),
             ApiFailure::ClientRefusal);
    QCOMPARE(Banc::attendre(banc.greffon.relancerCarte(QStringLiteral("t"), QStringLiteral("c/1"), QString())).kind(),
             ApiFailure::ClientRefusal);
    QCOMPARE(Banc::attendre(banc.greffon.accepterRevue(QStringLiteral("t"), QStringLiteral("c?x"))).kind(),
             ApiFailure::ClientRefusal);
    QCOMPARE(Banc::attendre(banc.greffon.refuserRevue(QStringLiteral("t t"), QStringLiteral("c"), QStringLiteral("m"))).kind(),
             ApiFailure::ClientRefusal);
    QCOMPARE(Banc::attendre(banc.greffon.clore(QStringLiteral("p/../q"))).kind(), ApiFailure::ClientRefusal);
    QCOMPARE(Banc::attendre(banc.greffon.changerReponses(QStringLiteral("p q"), QStringLiteral("proprietaire"))).kind(),
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

void TestClientGreffon::quiRepondSeulementAvecUneValeurDuGreffon()
{
    Banc banc;
    for (const QString &valeur : {QStringLiteral("moi"), QStringLiteral("hermes"), QString(), QStringLiteral("Proprietaire")}) {
        const ApiError erreur = Banc::attendre(banc.greffon.changerReponses(QStringLiteral("prj_42"), valeur));
        QCOMPARE(erreur.kind(), ApiFailure::ClientRefusal);
        QVERIFY(erreur.detail().contains(QStringLiteral("Qui répond")));
    }
    QVERIFY(banc.serveur.requetes.isEmpty());
}

void TestClientGreffon::fluxOuvertEnPorteurAvecLaRevision()
{
    Banc banc;
    // Révision du greffon (« <époque>.<numéro> ») renvoyée telle quelle ; toute autre valeur n'est jamais envoyée.
    const QList<QPair<QString, QByteArray>> cas = {
        {QStringLiteral("1727791200.41"), QByteArrayLiteral("1727791200.41")},
        {QString(), QByteArray()},
        {QStringLiteral("1727791200.41\r\nX-Injecte: oui"), QByteArray()},
        {QStringLiteral("abc"), QByteArray()},
    };
    for (const auto &[dernier, attendu] : cas) {
        ApiError refus;
        std::unique_ptr<QNetworkReply> reponse(banc.greffon.ouvrirFlux(dernier, &refus));
        QVERIFY(reponse);
        QTRY_VERIFY(reponse->isFinished());
        const RequeteRecue requete = banc.serveur.requetes.constLast();
        QCOMPARE(requete.methode, QByteArrayLiteral("GET"));
        QCOMPARE(requete.chemin, kP + QStringLiteral("/v1/flux"));
        QCOMPARE(requete.entete("accept"), QByteArrayLiteral("text/event-stream"));
        QCOMPARE(requete.entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
        QCOMPARE(requete.entete("last-event-id"), attendu);
        QVERIFY(!requete.aEntete("x-injecte"));
        QVERIFY(!requete.aEntete("origin"));
        QVERIFY(!requete.aEntete("cookie"));
    }
    QCOMPARE(banc.serveur.compter("GET", kP + QStringLiteral("/v1/flux")), cas.size());
}

void TestClientGreffon::greffonBloqueRefuseLesRoutesDeP7()
{
    Banc banc;
    banc.greffon.bloquer(QStringLiteral("Contrat du greffon incompatible : acp-poste/2, attendu acp-poste/1"));
    QCOMPARE(Banc::attendre(banc.greffon.accueil()).kind(), ApiFailure::Incompatible);
    QCOMPARE(Banc::attendre(banc.greffon.relancerCarte(QStringLiteral("t"), QStringLiteral("c"), QString())).kind(),
             ApiFailure::Incompatible);
    QCOMPARE(Banc::attendre(banc.greffon.clore(QStringLiteral("p"))).kind(), ApiFailure::Incompatible);
    QCOMPARE(Banc::attendre(banc.greffon.changerReponses(QStringLiteral("p"), QStringLiteral("proprietaire"))).kind(),
             ApiFailure::Incompatible);
    QCOMPARE(Banc::attendre(banc.greffon.accepterRevue(QStringLiteral("t"), QStringLiteral("c"))).kind(),
             ApiFailure::Incompatible);
    QCOMPARE(Banc::attendre(banc.greffon.refuserRevue(QStringLiteral("t"), QStringLiteral("c"), QStringLiteral("m"))).kind(),
             ApiFailure::Incompatible);
    ApiError refus;
    QVERIFY(banc.greffon.ouvrirFlux(QString(), &refus) == nullptr);
    QCOMPARE(refus.kind(), ApiFailure::Incompatible);
    QVERIFY(refus.detail().contains(QStringLiteral("acp-poste/2")));
    QVERIFY(banc.serveur.requetes.isEmpty());
}

QTEST_GUILESS_MAIN(TestClientGreffon)

#include "tst_client_greffon.moc"
