// Session Hermes contre le faux Hermes de bouclage et un coffre en mémoire.
//
// Exigence du plan prouvée ici : ROTATION DU JETON DE RAFRAÎCHISSEMENT — le nouveau jeton
// est au coffre AVANT le signal de session renouvelée, l'ancien n'est jamais renvoyé (le
// faux Hermes le refuserait en 503, comme Authelia derrière Hermes) ; cinq 401 simultanés
// ⇒ un seul rafraîchissement ; 401 `session_expired` ⇒ entrée effacée ; 503 ⇒ jeton gardé,
// recul, message après 3 échecs sur 2 minutes ; échec d'écriture du coffre ⇒ session en
// mémoire et message ; démarrage avec jeton mémorisé ⇒ rafraîchissement immédiat ;
// déconnexion ⇒ cookie `hermes_session_rt` envoyé une fois, coffre vidé. Les propriétés
// publiées vers QML ne portent jamais un jeton.

#include "api/ApiClient.h"
#include "auth/NativeAuthFlow.h"
#include "auth/SessionHermes.h"
#include "storage/JetonsCoffre.h"
#include "storage/SettingsStore.h"
#include "support/CoffreMemoire.h"
#include "support/FauxHermes.h"
#include "support/NavigateurTest.h"

#include <QCoreApplication>
#include <QMetaProperty>
#include <QSettings>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>

#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

struct Banc
{
    FauxHermes serveur;
    CoffreMemoire coffre;
    SettingsStore reglages;
    ApiClient client;
    std::unique_ptr<SessionHermes> session;
    Navigateur navigateur;
    QDateTime horloge = QDateTime::currentDateTimeUtc();

    explicit Banc(bool memoriser = true)
    {
        serveur.installerAuthentification();
        client.setAllowInsecureLoopback(true);
        reglages.setConnexionMemorisee(memoriser);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        session = std::make_unique<SessionHermes>(&client, &coffre, &reglages);
        session->flux()->setOuvreurNavigateur(navigateur.ouvreur());
        session->setRecul(Backoff(std::chrono::milliseconds(50), std::chrono::milliseconds(100), 0));
    }

    [[nodiscard]] QString cle() const { return JetonsCoffre::cleDe(serveur.url()); }

    [[nodiscard]] QByteArray jetonAuCoffre() const
    {
        EntreeJetons entree;
        return JetonsCoffre::decoder(coffre.entrees.value(cle()), entree) ? entree.jeton : QByteArray();
    }

    bool connecter()
    {
        QSignalSpy etablie(session.get(), &SessionHermes::sessionEtablie);
        session->seConnecter();
        return etablie.wait(10000) || etablie.count() == 1;
    }

    [[nodiscard]] int refreshAvec(const QByteArray &jeton) const
    {
        int total = 0;
        for (const RequeteRecue &requete : serveur.filtrer("POST", QStringLiteral("/auth/native/refresh"))) {
            if (requete.json().value(QStringLiteral("refresh_token")).toString().toUtf8() == jeton) {
                ++total;
            }
        }
        return total;
    }
};

ApiRequest lecture(const QString &chemin)
{
    ApiRequest requete;
    requete.path = chemin;
    return requete;
}

} // namespace

class TestSessionHermes : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void connexionLitLIdentiteEtMemorise();
    void rotationAuCoffreAvantLeSignal();
    void ancienJetonJamaisRenvoye();
    void cinq401UnSeulRafraichissement();
    void refresh401EffaceLeCoffre();
    void refresh503GardeLeJetonPuisPropose();
    void echecDEcritureDuCoffre();
    void demarrageAvecJetonMemorise();
    void deconnexionRevoqueEtOublie();
    void consentementRetireEffaceLEntree();
    void changementDeServeurPurgeLAncienneEntree();
    void aucunSecretDansLesProprietes();

private:
    QTemporaryDir m_reglages;
};

void TestSessionHermes::initTestCase()
{
    // Préférences isolées : jamais celles du poste.
    QVERIFY(m_reglages.isValid());
    QCoreApplication::setOrganizationName(
        QStringLiteral("ACP Test %1").arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
    QCoreApplication::setApplicationName(QStringLiteral("Session Hermes"));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, m_reglages.path());
}

void TestSessionHermes::connexionLitLIdentiteEtMemorise()
{
    Banc banc;
    QVERIFY(banc.connecter());
    QCOMPARE(banc.session->etat(), SessionStatus::Connectee);
    QCOMPARE(banc.session->nomAffiche(), QStringLiteral("Propriétaire de test"));
    QCOMPARE(banc.session->identifiant(), QStringLiteral("proprietaire-test"));
    QCOMPARE(banc.session->courriel(), QStringLiteral("proprietaire@exemple.invalid"));
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/api/auth/me")), 1);
    QVERIFY(banc.serveur.jetonsAccesValides.contains(banc.session->jetonAcces()));
    QCOMPARE(banc.jetonAuCoffre(), banc.serveur.jetonRafraichissementCourant);
    QVERIFY(banc.session->avisCoffre().isEmpty());
    const auto moi = banc.serveur.filtrer("GET", QStringLiteral("/api/auth/me"));
    QCOMPARE(moi.first().entete("authorization"), QByteArrayLiteral("Bearer ") + banc.session->jetonAcces());
}

void TestSessionHermes::rotationAuCoffreAvantLeSignal()
{
    Banc banc;
    QVERIFY(banc.connecter());
    const QByteArray ancien = banc.serveur.jetonRafraichissementCourant;
    QByteArray auCoffreAuSignal;
    QByteArray serveurAuSignal;
    connect(banc.session.get(), &SessionHermes::jetonsRenouveles, this, [&] {
        auCoffreAuSignal = banc.jetonAuCoffre();
        serveurAuSignal = banc.serveur.jetonRafraichissementCourant;
    });
    QSignalSpy renouveles(banc.session.get(), &SessionHermes::jetonsRenouveles);
    banc.session->rafraichir();
    QVERIFY(renouveles.wait(5000));
    QVERIFY(serveurAuSignal != ancien);
    QCOMPARE(auCoffreAuSignal, serveurAuSignal);
    QVERIFY(banc.serveur.jetonsRafraichissementTournes.contains(ancien));
    QCOMPARE(banc.session->etat(), SessionStatus::Connectee);
}

void TestSessionHermes::ancienJetonJamaisRenvoye()
{
    Banc banc;
    QVERIFY(banc.connecter());
    const QByteArray premier = banc.serveur.jetonRafraichissementCourant;
    QSignalSpy renouveles(banc.session.get(), &SessionHermes::jetonsRenouveles);
    banc.session->rafraichir();
    QVERIFY(renouveles.wait(5000));
    const QByteArray second = banc.serveur.jetonRafraichissementCourant;
    banc.session->rafraichir();
    QTRY_COMPARE(renouveles.count(), 2);
    QCOMPARE(banc.refreshAvec(premier), 1);
    QCOMPARE(banc.refreshAvec(second), 1);
    // Aucun 503 : le faux Hermes en aurait rendu un pour tout jeton déjà tourné.
    QCOMPARE(banc.session->etat(), SessionStatus::Connectee);
}

void TestSessionHermes::cinq401UnSeulRafraichissement()
{
    Banc banc;
    QVERIFY(banc.connecter());
    banc.serveur.expirerAcces();
    banc.serveur.delaiRefreshMs = 100;
    int reussis = 0;
    for (int index = 0; index < 5; ++index) {
        ApiCall *appel = banc.client.send(lecture(QStringLiteral("/api/auth/me")));
        connect(appel, &ApiCall::succeeded, this, [&reussis] { ++reussis; });
    }
    QTRY_COMPARE_WITH_TIMEOUT(reussis, 5, 10000);
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/auth/native/refresh")), 1);
    QCOMPARE(banc.session->etat(), SessionStatus::Connectee);
}

void TestSessionHermes::refresh401EffaceLeCoffre()
{
    Banc banc;
    QVERIFY(banc.connecter());
    QVERIFY(banc.coffre.entrees.contains(banc.cle()));
    banc.serveur.refreshExpire = true;
    QSignalSpy perdue(banc.session.get(), &SessionHermes::sessionPerdue);
    banc.session->rafraichir();
    QVERIFY(perdue.wait(5000));
    QCOMPARE(banc.session->etat(), SessionStatus::Expiree);
    QVERIFY(banc.session->derniereErreur().contains(QStringLiteral("reconnectez-vous")));
    QVERIFY(!banc.coffre.entrees.contains(banc.cle()));
    QVERIFY(banc.session->jetonAcces().isEmpty());
}

void TestSessionHermes::refresh503GardeLeJetonPuisPropose()
{
    Banc banc;
    QVERIFY(banc.connecter());
    banc.session->setHorloge([&banc] { return banc.horloge; });
    const QByteArray auCoffre = banc.jetonAuCoffre();
    banc.serveur.refresh503 = 100000;
    banc.session->rafraichir();
    QTRY_COMPARE(banc.session->etat(), SessionStatus::FournisseurInjoignable);
    QVERIFY(banc.session->derniereErreur().contains(QStringLiteral("Le jeton est gardé")));
    // Les nouveaux essais partent seuls (recul) ; l'horloge avance de 3 minutes.
    banc.horloge = banc.horloge.addSecs(180);
    QTRY_VERIFY_WITH_TIMEOUT(banc.serveur.compter("POST", QStringLiteral("/auth/native/refresh")) >= 4, 5000);
    QTRY_VERIFY(banc.session->derniereErreur().contains(QStringLiteral("refuse le rafraîchissement depuis")));
    QVERIFY(banc.session->derniereErreur().contains(QStringLiteral("le jeton mémorisé sera effacé")));
    // Jamais d'effacement automatique sur 503.
    QCOMPARE(banc.jetonAuCoffre(), auCoffre);
    QCOMPARE(banc.refreshAvec(auCoffre), banc.serveur.compter("POST", QStringLiteral("/auth/native/refresh")));
    // Le fournisseur revient : le même jeton tourne enfin.
    banc.serveur.refresh503 = 0;
    QSignalSpy renouveles(banc.session.get(), &SessionHermes::jetonsRenouveles);
    banc.session->reessayer();
    QVERIFY(renouveles.wait(5000));
    QCOMPARE(banc.session->etat(), SessionStatus::Connectee);
    QVERIFY(banc.jetonAuCoffre() != auCoffre);
}

void TestSessionHermes::echecDEcritureDuCoffre()
{
    Banc banc;
    banc.coffre.refuserEcriture = true;
    QVERIFY(banc.connecter());
    QCOMPARE(banc.session->etat(), SessionStatus::Connectee);
    QVERIFY(banc.session->avisCoffre().startsWith(QStringLiteral("Connexion non mémorisée")));
    QVERIFY(banc.coffre.entrees.isEmpty());

    // Une ancienne entrée devenue périmée par la rotation est effacée, jamais gardée.
    banc.coffre.refuserEcriture = false;
    banc.session->setMemoriser(false);
    banc.session->setMemoriser(true);
    QVERIFY(banc.coffre.entrees.contains(banc.cle()));
    banc.coffre.refuserEcriture = true;
    QSignalSpy renouveles(banc.session.get(), &SessionHermes::jetonsRenouveles);
    banc.session->rafraichir();
    QVERIFY(renouveles.wait(5000));
    QVERIFY(!banc.coffre.entrees.contains(banc.cle()));
    QCOMPARE(banc.session->etat(), SessionStatus::Connectee);
}

void TestSessionHermes::demarrageAvecJetonMemorise()
{
    Banc banc;
    // Session précédente : un jeton émis par le serveur et mémorisé.
    const QJsonObject jetons = banc.serveur.emettreJetons();
    JetonsCoffre(&banc.coffre).memoriser(banc.serveur.url(), QStringLiteral("self-hosted"),
                                         QStringLiteral("proprietaire-test"),
                                         jetons.value(QStringLiteral("refresh_token")).toString().toUtf8());
    banc.serveur.jetonsAccesValides.clear();
    QSignalSpy etablie(banc.session.get(), &SessionHermes::sessionEtablie);
    banc.session->restaurer();
    QVERIFY(etablie.wait(5000));
    QCOMPARE(banc.session->etat(), SessionStatus::Connectee);
    QCOMPARE(banc.serveur.compter("POST", QStringLiteral("/auth/native/refresh")), 1);
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/auth/native/authorize")), 0);
    QCOMPARE(banc.jetonAuCoffre(), banc.serveur.jetonRafraichissementCourant);
    QCOMPARE(banc.session->nomAffiche(), QStringLiteral("Propriétaire de test"));

    // Sans consentement, aucun démarrage automatique.
    Banc sansConsentement(false);
    sansConsentement.session->restaurer();
    QCOMPARE(sansConsentement.session->etat(), SessionStatus::Deconnectee);
    QCOMPARE(sansConsentement.coffre.lectures, 0);
}

void TestSessionHermes::deconnexionRevoqueEtOublie()
{
    Banc banc;
    QVERIFY(banc.connecter());
    const QByteArray jeton = banc.serveur.jetonRafraichissementCourant;
    QSignalSpy perdue(banc.session.get(), &SessionHermes::sessionPerdue);
    banc.session->seDeconnecter();
    QCOMPARE(perdue.count(), 1);
    QCOMPARE(banc.session->etat(), SessionStatus::Deconnectee);
    QVERIFY(banc.coffre.entrees.isEmpty());
    QVERIFY(banc.session->jetonAcces().isEmpty());
    QTRY_COMPARE(banc.serveur.compter("POST", QStringLiteral("/auth/logout")), 1);
    QCOMPARE(banc.serveur.jetonsRevoques, QList<QByteArray>{jeton});
    QTRY_VERIFY(banc.session->bilanDeconnexion().contains(QStringLiteral("302")));
    // Le cookie n'a voyagé que sur la déconnexion.
    for (const RequeteRecue &requete : std::as_const(banc.serveur.requetes)) {
        QCOMPARE(requete.aEntete("cookie"), requete.chemin == QStringLiteral("/auth/logout"));
    }
    // Hors session, une route protégée part en refus local.
    bool refuse = false;
    ApiCall *appel = banc.client.send(lecture(QStringLiteral("/api/auth/me")));
    connect(appel, &ApiCall::failed, this, [&refuse](const ApiError &erreur) {
        refuse = erreur.kind() == ApiFailure::ClientRefusal;
    });
    QTRY_VERIFY(refuse);
}

void TestSessionHermes::consentementRetireEffaceLEntree()
{
    Banc banc(false);
    QVERIFY(banc.connecter());
    QVERIFY(banc.coffre.entrees.isEmpty());
    QCOMPARE(banc.coffre.ecritures, 0);
    banc.session->setMemoriser(true);
    QCOMPARE(banc.jetonAuCoffre(), banc.serveur.jetonRafraichissementCourant);
    banc.session->setMemoriser(false);
    QVERIFY(banc.coffre.entrees.isEmpty());
    QVERIFY(!banc.reglages.connexionMemorisee());
}

void TestSessionHermes::changementDeServeurPurgeLAncienneEntree()
{
    Banc banc;
    QVERIFY(banc.connecter());
    QVERIFY(banc.coffre.entrees.contains(banc.cle()));
    QSignalSpy perdue(banc.session.get(), &SessionHermes::sessionPerdue);
    QVERIFY(!banc.client.setBaseUrl(QUrl(QStringLiteral("https://autre-hermes.test"))).isError());
    QCOMPARE(perdue.count(), 1);
    QCOMPARE(banc.session->etat(), SessionStatus::Deconnectee);
    QVERIFY(banc.coffre.entrees.isEmpty());
    QVERIFY(banc.session->jetonAcces().isEmpty());
}

void TestSessionHermes::aucunSecretDansLesProprietes()
{
    Banc banc;
    banc.navigateur.visiterBouclage = false;
    banc.session->seConnecter();
    QTRY_COMPARE(banc.session->etat(), SessionStatus::AttenteNavigateur);
    QTRY_VERIFY(!banc.serveur.dernierEtat.isEmpty());
    const QList<QByteArray> secretsAttente = {banc.serveur.dernierEtat, banc.serveur.dernierDefi};
    const auto verifier = [&banc](const QList<QByteArray> &secrets) {
        const QMetaObject *meta = banc.session->metaObject();
        for (int index = meta->propertyOffset(); index < meta->propertyCount(); ++index) {
            const QString valeur = meta->property(index).read(banc.session.get()).toString();
            for (const QByteArray &secret : secrets) {
                if (!secret.isEmpty() && valeur.contains(QString::fromUtf8(secret))) {
                    return false;
                }
            }
        }
        return true;
    };
    QVERIFY(verifier(secretsAttente));
    banc.session->annulerConnexion();

    Banc connecte;
    QVERIFY(connecte.connecter());
    const QMetaObject *meta = connecte.session->metaObject();
    for (int index = meta->propertyOffset(); index < meta->propertyCount(); ++index) {
        const QString valeur = meta->property(index).read(connecte.session.get()).toString();
        QVERIFY2(!valeur.contains(QString::fromUtf8(connecte.session->jetonAcces())), meta->property(index).name());
        QVERIFY2(!valeur.contains(QString::fromUtf8(connecte.serveur.jetonRafraichissementCourant)),
                 meta->property(index).name());
    }
}

QTEST_GUILESS_MAIN(TestSessionHermes)

#include "tst_session_hermes.moc"
