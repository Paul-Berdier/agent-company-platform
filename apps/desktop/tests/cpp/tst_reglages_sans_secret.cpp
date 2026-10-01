// Registre des préférences (QSettings) SANS jeton, après un parcours complet.
//
// Parcours contre le faux Hermes : adresse saisie par la coquille, consentement de
// mémorisation, connexion par le navigateur, identité, rotation du jeton, retrait puis
// reprise du consentement, déconnexion. Ensuite, TOUTES les clés de la portée de test sont
// énumérées : une clé hors liste blanche, ou une valeur qui contient un secret émis ou reçu
// pendant le parcours (jetons, code, vérificateur, état), ou une forme de jeton (`eyJ…`,
// `authelia_`, « Bearer »), fait échouer le test. Le coffre est en mémoire : le Gestionnaire
// d'identification réel n'est jamais touché ici.

#include "api/ApiClient.h"
#include "auth/NativeAuthFlow.h"
#include "auth/SessionHermes.h"
#include "commands/CommandRegistry.h"
#include "navigation/NavigationModel.h"
#include "services/HealthService.h"
#include "storage/SettingsStore.h"
#include "support/CoffreMemoire.h"
#include "support/FauxHermes.h"
#include "support/NavigateurTest.h"
#include "viewmodels/ShellViewModel.h"

#include <QCoreApplication>
#include <QFile>
#include <QRegularExpression>
#include <QSettings>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>

using namespace acp;
using namespace acp::test;

class TestReglagesSansSecret : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void aucunJetonDansLesPreferences();

private:
    QTemporaryDir m_dossier;
};

void TestReglagesSansSecret::initTestCase()
{
    QVERIFY(m_dossier.isValid());
    QCoreApplication::setOrganizationName(
        QStringLiteral("ACP Test %1").arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
    QCoreApplication::setApplicationName(QStringLiteral("Reglages sans secret"));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, m_dossier.path());
}

void TestReglagesSansSecret::aucunJetonDansLesPreferences()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    CoffreMemoire coffre;
    QStringList fichiersReglages;
    {
        SettingsStore reglages;
        ApiClient client;
        SessionHermes session(&client, &coffre, &reglages);
        Navigateur navigateur;
        session.flux()->setOuvreurNavigateur(navigateur.ouvreur());
        HealthService sante(&client);
        NavigationModel navigation;
        CommandRegistry commandes;
        ShellViewModel coquille(&client, &session, &sante, &navigation, &commandes, &reglages);

        // Adresse saisie comme dans l'écran de connexion.
        QCOMPARE(coquille.applyServerUrl(serveur.url().toString(), true), QString());
        session.setMemoriser(true);
        QSignalSpy etablie(&session, &SessionHermes::sessionEtablie);
        session.seConnecter();
        QVERIFY(etablie.wait(10000));
        QSignalSpy renouveles(&session, &SessionHermes::jetonsRenouveles);
        session.rafraichir();
        QVERIFY(renouveles.wait(5000));
        session.setMemoriser(false);
        session.setMemoriser(true);
        session.seDeconnecter();
        QTRY_COMPARE(serveur.compter("POST", QStringLiteral("/auth/logout")), 1);
        reglages.flush();
        fichiersReglages.append(reglages.location());
    }

    // Tous les secrets vus pendant le parcours, d'un côté comme de l'autre du fil.
    QList<QByteArray> secrets = {serveur.dernierEtat, serveur.dernierDefi};
    for (const RequeteRecue &requete : std::as_const(serveur.requetes)) {
        const QJsonObject corps = requete.json();
        for (const QString &champ : {QStringLiteral("code"), QStringLiteral("code_verifier"),
                                     QStringLiteral("refresh_token")}) {
            secrets.append(corps.value(champ).toString().toUtf8());
        }
        const QByteArray autorisation = requete.entete("authorization");
        if (autorisation.startsWith("Bearer ")) {
            secrets.append(autorisation.mid(7));
        }
    }
    for (const QByteArray &jeton : std::as_const(serveur.jetonsRafraichissementTournes)) {
        secrets.append(jeton);
    }
    secrets.removeAll(QByteArray());
    QVERIFY2(secrets.size() >= 6, "le parcours doit avoir produit des secrets à rechercher");

    QSettings portee;
    QVERIFY(!portee.allKeys().isEmpty());
    QVERIFY(portee.allKeys().contains(QStringLiteral("connection/serverUrl")));
    static const QRegularExpression formeDeJeton(
        QStringLiteral("eyJ[A-Za-z0-9_-]{4,}|authelia_|Bearer\\s|hermes_session_|ticket"),
        QRegularExpression::CaseInsensitiveOption);
    for (const QString &cle : portee.allKeys()) {
        QVERIFY2(SettingsStore::allowedKeys().contains(cle), qPrintable(QStringLiteral("clé hors liste : ") + cle));
        const QString valeur = portee.value(cle).toString();
        QVERIFY2(!formeDeJeton.match(valeur).hasMatch(), qPrintable(cle));
        for (const QByteArray &secret : std::as_const(secrets)) {
            QVERIFY2(!valeur.contains(QString::fromUtf8(secret)), qPrintable(cle));
        }
    }
    // Le fichier brut lui-même, au cas où une clé échapperait à QSettings::allKeys().
    for (const QString &chemin : std::as_const(fichiersReglages)) {
        QFile fichier(chemin);
        QVERIFY2(fichier.open(QIODevice::ReadOnly), qPrintable(chemin));
        const QByteArray contenu = fichier.readAll();
        for (const QByteArray &secret : std::as_const(secrets)) {
            QVERIFY(!contenu.contains(secret));
        }
    }
    // Le coffre de test a bien été vidé par la déconnexion.
    QVERIFY(coffre.entrees.isEmpty());
}

QTEST_GUILESS_MAIN(TestReglagesSansSecret)

#include "tst_reglages_sans_secret.moc"
