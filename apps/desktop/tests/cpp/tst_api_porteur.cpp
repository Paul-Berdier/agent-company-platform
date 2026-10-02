// Transport en porteur contre le faux Hermes de bouclage.
//
// Ce qui est prouvé ici :
//   - `Authorization: Bearer` sur les routes protégées, jamais sur les routes publiques ;
//   - hors session, refus local sans aucun appel réseau ;
//   - 401 de la PORTE : un seul rafraîchissement demandé, puis UNE réémission, mutation
//     comprise ; cinq 401 simultanés ⇒ un seul rafraîchissement ;
//   - 401 du greffon, ou second 401 : aucune réémission, et la session est déclarée refusée ;
//   - jamais d'en-tête `Origin`, jamais de `Cookie` hors de la déconnexion ;
//   - toute écriture en JSON, corps de plus de 64 Kio refusé localement ;
//   - 302 de `/auth/logout` tenu pour un succès de cet appel seul.

#include "api/ApiClient.h"
#include "support/FauxHermes.h"

#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>
#include <QTimer>

#include <algorithm>
#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

struct Resultat
{
    bool termine = false;
    bool reussi = false;
    ApiError erreur;
    ApiResponse reponse;
};

std::shared_ptr<Resultat> suivre(ApiCall *appel)
{
    auto resultat = std::make_shared<Resultat>();
    QObject::connect(appel, &ApiCall::succeeded, appel, [resultat](const ApiResponse &reponse) {
        resultat->termine = true;
        resultat->reussi = true;
        resultat->reponse = reponse;
    });
    QObject::connect(appel, &ApiCall::failed, appel, [resultat](const ApiError &erreur) {
        resultat->termine = true;
        resultat->erreur = erreur;
    });
    return resultat;
}

ApiRequest lecture(const QString &chemin)
{
    ApiRequest requete;
    requete.method = QByteArrayLiteral("GET");
    requete.path = chemin;
    return requete;
}

ApiRequest ecriture(const QString &chemin, const QJsonDocument &corps = {})
{
    ApiRequest requete;
    requete.method = QByteArrayLiteral("POST");
    requete.path = chemin;
    requete.body = corps;
    return requete;
}

void configurer(ApiClient &client, const FauxHermes &serveur)
{
    client.setAllowInsecureLoopback(true);
    QVERIFY(!client.setBaseUrl(serveur.url()).isError());
}

const QString kPause = QStringLiteral("/api/plugins/acp-poste/v1/pause");

} // namespace

class TestApiPorteur : public QObject
{
    Q_OBJECT

private slots:
    void porteurSurLesRoutesProtegeesSeulement();
    void refusLocalSansSession();
    void porte401UnRafraichissementPuisUneReemission();
    void cinq401SimultanesUnSeulRafraichissement();
    void second401TermineEtRefuseLaSession();
    void echecDuRafraichissementEchoueLesAppelsEnAttente();
    void refusDuGreffonSansReemission();
    void ecrituresEnJsonEtPlafond();
    void deconnexionCookieEtRedirectionAttendue();
    void fournisseurInjoignableClasse();
    void proxyDesSocketsSuitLaRegleDuClient();
};

void TestApiPorteur::porteurSurLesRoutesProtegeesSeulement()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    ApiClient client;
    configurer(client, serveur);
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });

    auto moi = suivre(client.send(lecture(QStringLiteral("/api/auth/me"))));
    ApiRequest sante = lecture(QStringLiteral("/api/health"));
    sante.publicEndpoint = true;
    auto vivacite = suivre(client.send(sante));
    QTRY_VERIFY(moi->termine && vivacite->termine);
    QVERIFY2(moi->reussi, qPrintable(moi->erreur.message()));
    QVERIFY(vivacite->reussi);

    const auto protegees = serveur.filtrer("GET", QStringLiteral("/api/auth/me"));
    QCOMPARE(protegees.size(), 1);
    QCOMPARE(protegees.first().entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
    const auto publiques = serveur.filtrer("GET", QStringLiteral("/api/health"));
    QCOMPARE(publiques.size(), 1);
    QVERIFY(!publiques.first().aEntete("authorization"));
    for (const RequeteRecue &requete : std::as_const(serveur.requetes)) {
        QVERIFY2(!requete.aEntete("origin"), "la station n'envoie jamais d'Origin");
        QVERIFY2(!requete.aEntete("cookie"), "aucun cookie hors de la déconnexion");
    }
}

void TestApiPorteur::refusLocalSansSession()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    ApiClient client;
    configurer(client, serveur);
    // Sans fournisseur, puis avec un fournisseur qui ne rend rien : refus local les deux fois.
    auto sansFournisseur = suivre(client.send(lecture(QStringLiteral("/api/auth/me"))));
    client.setBearerProvider([] { return QByteArray(); });
    auto sansJeton = suivre(client.send(lecture(QStringLiteral("/api/auth/me"))));
    QTRY_VERIFY(sansFournisseur->termine && sansJeton->termine);
    QCOMPARE(sansFournisseur->erreur.kind(), ApiFailure::ClientRefusal);
    QCOMPARE(sansJeton->erreur.kind(), ApiFailure::ClientRefusal);
    QCOMPARE(sansJeton->erreur.detail(), QStringLiteral("Aucune session : connectez-vous."));
    QVERIFY(serveur.requetes.isEmpty());
}

void TestApiPorteur::porte401UnRafraichissementPuisUneReemission()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    int pauses = 0;
    serveur.route("POST", kPause, [&pauses](const RequeteRecue &) {
        ++pauses;
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("pause_generale"), true}});
    });
    ApiClient client;
    configurer(client, serveur);
    QByteArray jeton = QByteArrayLiteral("jeton-perime");
    client.setBearerProvider([&jeton] { return jeton; });
    QSignalSpy rafraichissements(&client, &ApiClient::refreshRequested);
    connect(&client, &ApiClient::refreshRequested, this, [&] {
        QTimer::singleShot(0, &client, [&] {
            jeton = QByteArrayLiteral("jeton-neuf");
            serveur.jetonsAccesValides.insert(jeton);
            client.refreshFinished(true);
        });
    });

    auto pause = suivre(client.send(ecriture(kPause, QJsonDocument(QJsonObject{
        {QStringLiteral("generale"), true}, {QStringLiteral("raison"), QStringLiteral("essai")}}))));
    QTRY_VERIFY(pause->termine);
    QVERIFY2(pause->reussi, qPrintable(pause->erreur.message()));
    QCOMPARE(rafraichissements.count(), 1);
    QCOMPARE(pauses, 1); // Le gestionnaire n'a tourné qu'une fois : aucun double effet.
    const auto envois = serveur.filtrer("POST", kPause);
    QCOMPARE(envois.size(), 2);
    QCOMPARE(envois.at(0).entete("authorization"), QByteArrayLiteral("Bearer jeton-perime"));
    QCOMPARE(envois.at(1).entete("authorization"), QByteArrayLiteral("Bearer jeton-neuf"));
    QCOMPARE(envois.at(0).corps, envois.at(1).corps);
}

void TestApiPorteur::cinq401SimultanesUnSeulRafraichissement()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    ApiClient client;
    configurer(client, serveur);
    QByteArray jeton = QByteArrayLiteral("jeton-perime");
    client.setBearerProvider([&jeton] { return jeton; });
    QSignalSpy rafraichissements(&client, &ApiClient::refreshRequested);
    bool libere = false;
    connect(&client, &ApiClient::refreshRequested, this, [&] {
        // La session répond plus tard : les cinq refus arrivent pendant le vol.
        QTimer::singleShot(150, &client, [&] {
            jeton = QByteArrayLiteral("jeton-neuf");
            serveur.jetonsAccesValides.insert(jeton);
            libere = true;
            client.refreshFinished(true);
        });
    });

    QList<std::shared_ptr<Resultat>> resultats;
    for (int index = 0; index < 5; ++index) {
        resultats.append(suivre(client.send(lecture(QStringLiteral("/api/auth/me")))));
    }
    QTRY_VERIFY(libere);
    QTRY_VERIFY(std::all_of(resultats.cbegin(), resultats.cend(),
                            [](const auto &resultat) { return resultat->termine; }));
    for (const auto &resultat : std::as_const(resultats)) {
        QVERIFY2(resultat->reussi, qPrintable(resultat->erreur.message()));
    }
    QCOMPARE(rafraichissements.count(), 1);
    QCOMPARE(serveur.compter("GET", QStringLiteral("/api/auth/me")), 10);
}

void TestApiPorteur::second401TermineEtRefuseLaSession()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    ApiClient client;
    configurer(client, serveur);
    client.setBearerProvider([] { return QByteArrayLiteral("jamais-valide"); });
    QSignalSpy rafraichissements(&client, &ApiClient::refreshRequested);
    QSignalSpy refus(&client, &ApiClient::bearerRejected);
    connect(&client, &ApiClient::refreshRequested, this,
            [&] { QTimer::singleShot(0, &client, [&] { client.refreshFinished(true); }); });

    auto moi = suivre(client.send(lecture(QStringLiteral("/api/auth/me"))));
    QTRY_VERIFY(moi->termine);
    QVERIFY(!moi->reussi);
    QCOMPARE(moi->erreur.kind(), ApiFailure::Unauthorized);
    QCOMPARE(moi->erreur.code(), QStringLiteral("session_expired"));
    QCOMPARE(rafraichissements.count(), 1);
    QCOMPARE(refus.count(), 1);
    QCOMPARE(serveur.compter("GET", QStringLiteral("/api/auth/me")), 2);
}

void TestApiPorteur::echecDuRafraichissementEchoueLesAppelsEnAttente()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    ApiClient client;
    configurer(client, serveur);
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-perime"); });
    connect(&client, &ApiClient::refreshRequested, this,
            [&] { QTimer::singleShot(0, &client, [&] { client.refreshFinished(false); }); });
    auto pause = suivre(client.send(ecriture(kPause)));
    QTRY_VERIFY(pause->termine);
    QCOMPARE(pause->erreur.kind(), ApiFailure::Unauthorized);
    QCOMPARE(serveur.compter("POST", kPause), 1);
}

void TestApiPorteur::refusDuGreffonSansReemission()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    serveur.route("POST", kPause, [](const RequeteRecue &) {
        return ReponseFaux::json(401, QJsonObject{{QStringLiteral("detail"), QJsonObject{
            {QStringLiteral("code"), QStringLiteral("session")},
            {QStringLiteral("message"), QStringLiteral("Session du tableau de bord requise.")}}}});
    });
    ApiClient client;
    configurer(client, serveur);
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    QSignalSpy rafraichissements(&client, &ApiClient::refreshRequested);
    QSignalSpy refus(&client, &ApiClient::bearerRejected);
    auto pause = suivre(client.send(ecriture(kPause)));
    QTRY_VERIFY(pause->termine);
    QCOMPARE(pause->erreur.kind(), ApiFailure::Unauthorized);
    QCOMPARE(pause->erreur.code(), QStringLiteral("session"));
    QCOMPARE(pause->erreur.detail(), QStringLiteral("Session du tableau de bord requise."));
    QVERIFY(!pause->erreur.isGateRejection());
    QCOMPARE(rafraichissements.count(), 0);
    QCOMPARE(refus.count(), 1);
    QCOMPARE(serveur.compter("POST", kPause), 1);
}

void TestApiPorteur::ecrituresEnJsonEtPlafond()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    serveur.route("POST", kPause, [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{});
    });
    ApiClient client;
    configurer(client, serveur);
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });

    auto sansCorps = suivre(client.send(ecriture(kPause)));
    QTRY_VERIFY(sansCorps->termine);
    QVERIFY(sansCorps->reussi);
    const RequeteRecue envoi = serveur.filtrer("POST", kPause).constFirst();
    QCOMPARE(envoi.entete("content-type"), QByteArrayLiteral("application/json"));
    QCOMPARE(envoi.corps, QByteArrayLiteral("{}"));

    const QString enorme(70 * 1024, QLatin1Char('x'));
    auto tropGros = suivre(client.send(ecriture(kPause, QJsonDocument(QJsonObject{
        {QStringLiteral("raison"), enorme}}))));
    QTRY_VERIFY(tropGros->termine);
    QCOMPARE(tropGros->erreur.kind(), ApiFailure::ClientRefusal);
    QCOMPARE(serveur.compter("POST", kPause), 1); // Rien n'est parti.
}

void TestApiPorteur::deconnexionCookieEtRedirectionAttendue()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.route("GET", QStringLiteral("/api/redirige"), [](const RequeteRecue &) {
        return ReponseFaux::redirection(QByteArrayLiteral("/ailleurs"));
    });
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    ApiClient client;
    configurer(client, serveur);
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });

    ApiRequest deconnexion = ecriture(QStringLiteral("/auth/logout"));
    deconnexion.publicEndpoint = true;
    deconnexion.redirectionAttendue = true;
    deconnexion.cookieDeconnexion = QByteArrayLiteral("rt-a-revoquer");
    auto fin = suivre(client.send(deconnexion));
    auto anomalie = suivre(client.send(lecture(QStringLiteral("/api/redirige"))));
    QTRY_VERIFY(fin->termine && anomalie->termine);
    QVERIFY2(fin->reussi, qPrintable(fin->erreur.message()));
    QCOMPARE(fin->reponse.httpStatus, 302);
    QCOMPARE(serveur.jetonsRevoques, QList<QByteArray>{QByteArrayLiteral("rt-a-revoquer")});
    const RequeteRecue envoi = serveur.filtrer("POST", QStringLiteral("/auth/logout")).constFirst();
    QCOMPARE(envoi.entete("cookie"), QByteArrayLiteral("hermes_session_rt=rt-a-revoquer"));
    QVERIFY(!envoi.aEntete("authorization"));
    QCOMPARE(anomalie->erreur.kind(), ApiFailure::InvalidResponse);
    QVERIFY(!serveur.filtrer("GET", QStringLiteral("/api/redirige")).constFirst().aEntete("cookie"));
}

void TestApiPorteur::fournisseurInjoignableClasse()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    serveur.route("POST", kPause, [](const RequeteRecue &) {
        return ReponseFaux::json(503, QJsonObject{{QStringLiteral("detail"),
                                                   QStringLiteral("Auth provider 'self-hosted' unreachable")}});
    });
    ApiClient client;
    configurer(client, serveur);
    client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    auto pause = suivre(client.send(ecriture(kPause)));
    QTRY_VERIFY(pause->termine);
    QCOMPARE(pause->erreur.kind(), ApiFailure::IdentityProviderUnavailable);
    QCOMPARE(pause->erreur.detail(), QStringLiteral("fournisseur d'identité « self-hosted » injoignable"));
    // Mutation sans clé d'idempotence : une seule tentative, jamais rejouée.
    QCOMPARE(serveur.compter("POST", kPause), 1);
}

void TestApiPorteur::proxyDesSocketsSuitLaRegleDuClient()
{
    // Les WebSockets (passerelle, veille du kanban) prennent la MÊME règle que le REST : aucun
    // proxy implicite par défaut, le proxy du système seulement s'il est demandé.
    ApiClient client;
    QCOMPARE(client.proxyDesSockets().type(), QNetworkProxy::NoProxy);
    client.setUseSystemProxy(true);
    QCOMPARE(client.proxyDesSockets().type(), QNetworkProxy::DefaultProxy);
    client.setUseSystemProxy(false);
    QCOMPARE(client.proxyDesSockets().type(), QNetworkProxy::NoProxy);
}

QTEST_GUILESS_MAIN(TestApiPorteur)

#include "tst_api_porteur.moc"
