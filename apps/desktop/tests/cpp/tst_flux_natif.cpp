// Connexion native RFC 8252 contre le faux Hermes de bouclage.
//
// Le « navigateur » de ces tests suit la redirection 302 du faux Hermes jusqu'à l'écouteur
// de bouclage de la station, exactement comme le ferait le navigateur système ; le produit,
// lui, appelle QDesktopServices::openUrl.
//
// Exigences du plan prouvées ici : `state` différent ou absent refusé sans échange de code ;
// redirection limitée à 127.0.0.1 (jamais localhost ni ::1) ; page de bouclage sans code ni
// état ; seconde requête refusée ; expiration ; erreurs du serveur et réponses de jetons
// invalides refusées en français.

#include "api/ApiClient.h"
#include "auth/EcouteurBouclage.h"
#include "auth/NativeAuthFlow.h"
#include "support/FauxHermes.h"
#include "support/NavigateurTest.h"

#include <QHostAddress>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkInterface>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRegularExpression>
#include <QSignalSpy>
#include <QTcpSocket>
#include <QTest>
#include <QTimeZone>
#include <QTimer>

#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    NativeAuthFlow flux{&client};
    Navigateur navigateur;
    std::unique_ptr<QSignalSpy> reussites;
    std::unique_ptr<QSignalSpy> echecs;
    JetonsHermes jetons;

    Banc()
    {
        serveur.installerAuthentification();
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        flux.setOuvreurNavigateur(navigateur.ouvreur());
        reussites = std::make_unique<QSignalSpy>(&flux, &NativeAuthFlow::reussi);
        echecs = std::make_unique<QSignalSpy>(&flux, &NativeAuthFlow::echoue);
        QObject::connect(&flux, &NativeAuthFlow::reussi, &flux,
                         [this](const JetonsHermes &recus) { jetons = recus; });
    }

    [[nodiscard]] QString raisonEchec() const
    {
        return echecs->isEmpty() ? QString() : echecs->constFirst().constFirst().toString();
    }
};

} // namespace

class TestFluxNatif : public QObject
{
    Q_OBJECT

private slots:
    void connexionNominale();
    void etatDifferentRefuseSansEchange();
    void etatAbsentRefuseSansEchange();
    void erreurRenduParLeServeur();
    void faviconEtAutresCheminsSansEffet();
    void entetesTropVolumineuxSansEffet();
    void expirationDuDelai();
    void ecouteSurLeBouclageIpv4Seulement();
    void adresseNonLocaleInjoignable();
    void annulationSansSignal();
    void unSeulFluxALaFois();
    void authNonRequiseRefusee();
    void fournisseurAbsentRefuse();
    void codeRefuseParHermes();
    void typeDeJetonRefuse();
    void lectureDesJetons();
};

void TestFluxNatif::connexionNominale()
{
    Banc banc;
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.reussites->count(), 1, 10000);
    QVERIFY(banc.echecs->isEmpty());
    QCOMPARE(banc.flux.etape(), NativeAuthFlow::Etape::Inactif);

    // Jetons reçus et contrôlés.
    QVERIFY(banc.serveur.jetonsAccesValides.contains(banc.jetons.acces));
    QCOMPARE(banc.jetons.rafraichissement, banc.serveur.jetonRafraichissementCourant);
    QCOMPARE(banc.jetons.fournisseur, QStringLiteral("self-hosted"));
    QCOMPARE(banc.jetons.utilisateur, QStringLiteral("proprietaire-test"));

    // Demande d'autorisation : S256, fournisseur explicite, bouclage IPv4 exact.
    const QUrlQuery lien(banc.navigateur.lienRecu.query(QUrl::FullyEncoded));
    QCOMPARE(lien.queryItemValue(QStringLiteral("provider")), QStringLiteral("self-hosted"));
    QCOMPARE(lien.queryItemValue(QStringLiteral("code_challenge_method")), QStringLiteral("S256"));
    QCOMPARE(banc.navigateur.lienRecu.path(), QStringLiteral("/auth/native/authorize"));
    static const QRegularExpression forme(QStringLiteral("^http://127\\.0\\.0\\.1:(\\d+)/rappel$"));
    const QRegularExpressionMatch correspondance = forme.match(banc.serveur.dernierRedirectUri);
    QVERIFY2(correspondance.hasMatch(), qPrintable(banc.serveur.dernierRedirectUri));
    QCOMPARE(correspondance.captured(1).toInt(), banc.navigateur.bouclageVisite.port());
    QVERIFY(!banc.serveur.dernierRedirectUri.contains(QStringLiteral("localhost")));
    QVERIFY(!banc.serveur.dernierRedirectUri.contains(QStringLiteral("::1")));
    QCOMPARE(banc.serveur.dernierDefi.size(), 43);
    QCOMPARE(banc.serveur.dernierEtat.size(), 43);

    // Le vérificateur présenté correspond au défi annoncé (le faux Hermes l'a vérifié).
    const auto echanges = banc.serveur.filtrer("POST", QStringLiteral("/auth/native/token"));
    QCOMPARE(echanges.size(), 1);
    const QByteArray verificateur = echanges.first().json().value(QStringLiteral("code_verifier")).toString().toUtf8();
    QCOMPARE(defiS256Reference(verificateur), banc.serveur.dernierDefi);
    QCOMPARE(echanges.first().entete("content-type"), QByteArrayLiteral("application/json"));
    for (const RequeteRecue &requete : std::as_const(banc.serveur.requetes)) {
        QVERIFY(!requete.aEntete("authorization"));
        QVERIFY(!requete.aEntete("origin"));
        QVERIFY(!requete.aEntete("cookie"));
    }

    // Page de bouclage : statique, sans code ni état, en-têtes de protection.
    QTRY_VERIFY(banc.navigateur.termine);
    QCOMPARE(banc.navigateur.statutBouclage, 200);
    const QUrlQuery rappel(banc.navigateur.bouclageVisite.query(QUrl::FullyEncoded));
    const QByteArray code = rappel.queryItemValue(QStringLiteral("code")).toUtf8();
    QVERIFY(!code.isEmpty());
    QVERIFY(!banc.navigateur.pageBouclage.contains(code));
    QVERIFY(!banc.navigateur.pageBouclage.contains(banc.serveur.dernierEtat));
    QVERIFY(QString::fromUtf8(banc.navigateur.pageBouclage).contains(QStringLiteral("Connexion transmise à la station")));
    QCOMPARE(banc.navigateur.entetesBouclage.value("cache-control"), QByteArrayLiteral("no-store"));
    QCOMPARE(banc.navigateur.entetesBouclage.value("content-security-policy"),
             QByteArrayLiteral("default-src 'none'"));
    QCOMPARE(banc.navigateur.entetesBouclage.value("referrer-policy"), QByteArrayLiteral("no-referrer"));

    // Seconde requête refusée : l'écouteur est fermé.
    QVERIFY(banc.flux.redirectUri().isEmpty());
    QNetworkReply *seconde = banc.navigateur.reseau.get(QNetworkRequest(banc.navigateur.bouclageVisite));
    QTRY_VERIFY(seconde->isFinished());
    QCOMPARE(seconde->error(), QNetworkReply::ConnectionRefusedError);
    seconde->deleteLater();
}

void TestFluxNatif::etatDifferentRefuseSansEchange()
{
    Banc banc;
    banc.serveur.etatForce = QByteArrayLiteral("etat-fabrique-par-un-tiers");
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.echecs->count(), 1, 10000);
    QVERIFY(banc.raisonEchec().contains(QStringLiteral("état différent")));
    QCOMPARE(banc.reussites->count(), 0);
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/auth/native/token")), 0);
    QVERIFY(banc.flux.redirectUri().isEmpty());
    QTRY_VERIFY(banc.navigateur.termine);
    QCOMPARE(banc.navigateur.statutBouclage, 400);
    QVERIFY(!banc.navigateur.pageBouclage.contains("etat-fabrique"));
}

void TestFluxNatif::etatAbsentRefuseSansEchange()
{
    Banc banc;
    banc.serveur.omettreEtat = true;
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.echecs->count(), 1, 10000);
    QVERIFY(banc.raisonEchec().contains(QStringLiteral("état différent ou absent")));
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/auth/native/token")), 0);
    QVERIFY(banc.flux.redirectUri().isEmpty());
}

void TestFluxNatif::erreurRenduParLeServeur()
{
    Banc banc;
    banc.navigateur.alterer = [](const QUrl &recu) {
        QUrlQuery requete(recu.query(QUrl::FullyEncoded));
        requete.removeAllQueryItems(QStringLiteral("code"));
        requete.addQueryItem(QStringLiteral("error"), QStringLiteral("access_denied<script>"));
        QUrl altere = recu;
        altere.setQuery(requete);
        return altere;
    };
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.echecs->count(), 1, 10000);
    QVERIFY2(banc.raisonEchec().contains(QStringLiteral("« access_denied")), qPrintable(banc.raisonEchec()));
    QVERIFY(!banc.raisonEchec().contains(QStringLiteral("<script>")));
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/auth/native/token")), 0);
}

void TestFluxNatif::faviconEtAutresCheminsSansEffet()
{
    Banc banc;
    banc.navigateur.cheminsPrealables = {QByteArrayLiteral("/favicon.ico"), QByteArrayLiteral("/autre")};
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.reussites->count(), 1, 10000);
    QCOMPARE(banc.navigateur.statutsPrealables, (QList<int>{404, 404}));
    QVERIFY(banc.echecs->isEmpty());
}

void TestFluxNatif::entetesTropVolumineuxSansEffet()
{
    Banc banc;
    banc.navigateur.visiterBouclage = false;
    banc.flux.demarrer();
    QTRY_COMPARE(banc.flux.etape(), NativeAuthFlow::Etape::AttenteNavigateur);
    QTcpSocket socket;
    socket.connectToHost(QHostAddress(QHostAddress::LocalHost), banc.flux.redirectUri().port());
    QVERIFY(socket.waitForConnected(5000));
    socket.write("GET /rappel?state=x HTTP/1.1\r\nX-Remplissage: " + QByteArray(9000, 'a') + "\r\n\r\n");
    QTRY_VERIFY(socket.bytesAvailable() > 0 || socket.state() != QAbstractSocket::ConnectedState);
    QVERIFY(socket.readAll().startsWith("HTTP/1.1 431"));
    // Aucun effet sur le flux : toujours en attente, écouteur ouvert.
    QCOMPARE(banc.flux.etape(), NativeAuthFlow::Etape::AttenteNavigateur);
    QVERIFY(!banc.flux.redirectUri().isEmpty());
    QVERIFY(banc.echecs->isEmpty());
    banc.flux.annuler();
}

void TestFluxNatif::expirationDuDelai()
{
    Banc banc;
    banc.navigateur.visiterBouclage = false;
    banc.flux.setDelaiAttente(std::chrono::milliseconds(300));
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.echecs->count(), 1, 10000);
    QVERIFY(banc.raisonEchec().contains(QStringLiteral("a expiré")));
    QVERIFY(banc.flux.redirectUri().isEmpty());
    QCOMPARE(banc.flux.etape(), NativeAuthFlow::Etape::Inactif);
}

void TestFluxNatif::ecouteSurLeBouclageIpv4Seulement()
{
    EcouteurBouclage ecouteur;
    QString raison;
    QVERIFY(!ecouteur.ouvrir(QByteArray(), &raison));
    QVERIFY(raison.contains(QStringLiteral("vide")));
    QVERIFY(ecouteur.ouvrir(QByteArrayLiteral("etat-de-test"), &raison));
    QCOMPARE(ecouteur.adresse(), QHostAddress(QHostAddress::LocalHost));
    QVERIFY(ecouteur.port() > 0);
    QCOMPARE(ecouteur.redirectUri().toString(),
             QStringLiteral("http://127.0.0.1:%1/rappel").arg(ecouteur.port()));
    // Aucune écoute IPv6 : ::1 sur le même port est refusé.
    QTcpSocket ipv6;
    ipv6.connectToHost(QHostAddress(QHostAddress::LocalHostIPv6), ecouteur.port());
    QVERIFY(!ipv6.waitForConnected(2000));
    ecouteur.fermer();
    QVERIFY(!ecouteur.estOuvert());
    QVERIFY(ecouteur.redirectUri().isEmpty());
}

void TestFluxNatif::adresseNonLocaleInjoignable()
{
    QHostAddress externe;
    const QList<QHostAddress> adresses = QNetworkInterface::allAddresses();
    for (const QHostAddress &adresse : adresses) {
        if (adresse.protocol() == QAbstractSocket::IPv4Protocol && !adresse.isLoopback()) {
            externe = adresse;
            break;
        }
    }
    if (externe.isNull()) {
        QSKIP("Aucune adresse IPv4 hors bouclage sur ce poste : l'écoute limitée à 127.0.0.1 ne "
              "peut pas être éprouvée depuis une autre interface ici.");
    }
    EcouteurBouclage ecouteur;
    QVERIFY(ecouteur.ouvrir(QByteArrayLiteral("etat-de-test")));
    QTcpSocket socket;
    socket.connectToHost(externe, ecouteur.port());
    QVERIFY2(!socket.waitForConnected(2000),
             qPrintable(QStringLiteral("l'écouteur répond sur %1").arg(externe.toString())));
}

void TestFluxNatif::annulationSansSignal()
{
    Banc banc;
    banc.navigateur.visiterBouclage = false;
    banc.flux.demarrer();
    QTRY_COMPARE(banc.flux.etape(), NativeAuthFlow::Etape::AttenteNavigateur);
    QVERIFY(!banc.flux.lienAutorisation().isEmpty());
    QVERIFY(banc.flux.navigateurOuvert());
    banc.flux.annuler();
    QCOMPARE(banc.flux.etape(), NativeAuthFlow::Etape::Inactif);
    QVERIFY(banc.flux.redirectUri().isEmpty());
    QVERIFY(banc.flux.lienAutorisation().isEmpty());
    QTest::qWait(50);
    QVERIFY(banc.echecs->isEmpty());
    QVERIFY(banc.reussites->isEmpty());
}

void TestFluxNatif::unSeulFluxALaFois()
{
    Banc banc;
    banc.navigateur.visiterBouclage = false;
    banc.flux.demarrer();
    banc.flux.demarrer();
    QTRY_COMPARE(banc.flux.etape(), NativeAuthFlow::Etape::AttenteNavigateur);
    banc.flux.demarrer();
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/api/health")), 1);
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/auth/native/authorize")) <= 1, true);
    banc.flux.annuler();
}

void TestFluxNatif::authNonRequiseRefusee()
{
    Banc banc;
    banc.serveur.authRequise = false;
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.echecs->count(), 1, 10000);
    QVERIFY(banc.raisonEchec().contains(QStringLiteral("n'exige aucune connexion")));
    QVERIFY(banc.navigateur.lienRecu.isEmpty());
}

void TestFluxNatif::fournisseurAbsentRefuse()
{
    Banc banc;
    banc.serveur.fournisseur = QStringLiteral("autre-fournisseur");
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.echecs->count(), 1, 10000);
    QVERIFY(banc.raisonEchec().contains(QStringLiteral("self-hosted")));
    QVERIFY(banc.navigateur.lienRecu.isEmpty());
}

void TestFluxNatif::codeRefuseParHermes()
{
    Banc banc;
    banc.serveur.route("POST", QStringLiteral("/auth/native/token"), [](const RequeteRecue &) {
        return ReponseFaux::json(400, QJsonObject{{QStringLiteral("detail"),
                                                   QStringLiteral("Invalid or expired authorization code.")}});
    });
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.echecs->count(), 1, 10000);
    QCOMPARE(banc.raisonEchec(),
             QStringLiteral("Code de connexion refusé ou expiré ; recommencez depuis la station."));
}

void TestFluxNatif::typeDeJetonRefuse()
{
    Banc banc;
    banc.serveur.typeJetonFaux = true;
    banc.flux.demarrer();
    QTRY_COMPARE_WITH_TIMEOUT(banc.echecs->count(), 1, 10000);
    QVERIFY(banc.raisonEchec().contains(QStringLiteral("type de jeton inattendu")));
    QCOMPARE(banc.reussites->count(), 0);
}

void TestFluxNatif::lectureDesJetons()
{
    const QDateTime maintenant = QDateTime::currentDateTimeUtc();
    const QJsonObject valide{
        {QStringLiteral("access_token"), QStringLiteral("a")},
        {QStringLiteral("refresh_token"), QStringLiteral("r")},
        {QStringLiteral("token_type"), QStringLiteral("Bearer")},
        {QStringLiteral("expires_at"), maintenant.toSecsSinceEpoch() + 3600},
        {QStringLiteral("provider"), QStringLiteral("self-hosted")},
        {QStringLiteral("user_id"), QStringLiteral("u")},
    };
    JetonsHermes jetons;
    QVERIFY(JetonsHermes::lire(valide, QStringLiteral("self-hosted"), maintenant, jetons).isEmpty());
    QCOMPARE(jetons.acces, QByteArrayLiteral("a"));
    QCOMPARE(jetons.expireLe.toSecsSinceEpoch(), maintenant.toSecsSinceEpoch() + 3600);

    QJsonObject autre = valide;
    autre.insert(QStringLiteral("provider"), QStringLiteral("nous-portal"));
    QVERIFY(JetonsHermes::lire(autre, QStringLiteral("self-hosted"), maintenant, jetons).contains(QStringLiteral("fournisseur")));
    QJsonObject expire = valide;
    expire.insert(QStringLiteral("expires_at"), maintenant.toSecsSinceEpoch() - 1);
    QVERIFY(JetonsHermes::lire(expire, QStringLiteral("self-hosted"), maintenant, jetons).contains(QStringLiteral("expiré")));
    QJsonObject sansAcces = valide;
    sansAcces.insert(QStringLiteral("access_token"), QString());
    QVERIFY(!JetonsHermes::lire(sansAcces, QStringLiteral("self-hosted"), maintenant, jetons).isEmpty());
    QJsonObject sansRafraichissement = valide;
    sansRafraichissement.insert(QStringLiteral("refresh_token"), QString());
    QVERIFY(JetonsHermes::lire(sansRafraichissement, QStringLiteral("self-hosted"), maintenant, jetons).isEmpty());
    QVERIFY(jetons.rafraichissement.isEmpty());
    jetons.effacer();
    QVERIFY(jetons.estVide());
}

QTEST_GUILESS_MAIN(TestFluxNatif)

#include "tst_flux_natif.moc"
