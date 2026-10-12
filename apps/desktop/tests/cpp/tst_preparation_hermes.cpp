// Contrat réel Hermes 0.21.5 : JSON-RPC de préparation et routes OAuth propriétaires.
// Uniquement FauxHermes sur 127.0.0.1 ; aucun compte, navigateur ni fournisseur réel.
#include "api/ApiClient.h"
#include "gateway/GatewayClient.h"
#include "support/FauxHermes.h"
#include "viewmodels/PreparationHermesViewModel.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {
const QString kId = QStringLiteral("abcdefghijklmnopqrstuv"); // token_urlsafe(16) : 22 caractères
const QString kStart = QStringLiteral("/api/providers/oauth/openai-codex/start");
const QString kPoll = QStringLiteral("/api/providers/oauth/openai-codex/poll/") + kId;
const QString kCancel = QStringLiteral("/api/providers/oauth/sessions/") + kId;

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    GatewayClient passerelle{&client};
    PreparationHermesViewModel preparation{&client, &passerelle};
    bool configure = false;
    bool disponible = false;
    bool annulationOk = true;
    int delaiStart = 0;
    int delaiPoll = 0;
    int demandesStatut = 0;
    int demandesResolution = 0;
    QString statut = QStringLiteral("pending");
    QString idReponse = kId;
    QJsonObject statutForce;
    QJsonObject resolutionForcee;
    QUrl urlOuverte;
    int ouvertures = 0;
    QJsonObject defi{
        {QStringLiteral("session_id"), kId},
        {QStringLiteral("flow"), QStringLiteral("device_code")},
        {QStringLiteral("user_code"), QStringLiteral("ABCD-EFGH")},
        {QStringLiteral("verification_url"), QStringLiteral("https://auth.openai.com/codex/device")},
        {QStringLiteral("expires_in"), 900},
        {QStringLiteral("poll_interval"), 3}};

    Banc()
    {
        serveur.installerAuthentification();
        serveur.activerPasserelle();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("session-acp"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) qFatal("URL du faux Hermes refusée");
        client.setBearerProvider([] { return QByteArrayLiteral("session-acp"); });
        preparation.setDelaisTest(std::chrono::milliseconds(30), std::chrono::seconds(20));
        preparation.setOuvreur([this](const QUrl &url) {
            urlOuverte = url;
            ++ouvertures;
            return true;
        });
        serveur.methodes.insert(QStringLiteral("setup.status"), [this](const QJsonObject &) {
            ++demandesStatut;
            return statutForce.isEmpty() ? QJsonObject{{QStringLiteral("provider_configured"), configure}} : statutForce;
        });
        serveur.methodes.insert(QStringLiteral("setup.runtime_check"), [this](const QJsonObject &) {
            ++demandesResolution;
            return resolutionForcee.isEmpty()
                ? QJsonObject{{QStringLiteral("ok"), disponible},
                              {QStringLiteral("provider"), QStringLiteral("openai-codex")},
                              {QStringLiteral("model"), QStringLiteral("gpt-5.4")},
                              {QStringLiteral("source"), QStringLiteral("oauth")},
                              {QStringLiteral("error"), disponible ? QString() : QStringLiteral("No provider configured")}}
                : resolutionForcee;
        });
        serveur.route("POST", kStart, [this](const RequeteRecue &) {
            auto reponse = ReponseFaux::json(200, defi);
            reponse.delaiMs = delaiStart;
            return reponse;
        });
        serveur.route("GET", kPoll, [this](const RequeteRecue &) {
            auto reponse = ReponseFaux::json(200, QJsonObject{
                {QStringLiteral("session_id"), idReponse}, {QStringLiteral("status"), statut},
                {QStringLiteral("error_message"), QStringLiteral("access_token=secret-fournisseur")}});
            reponse.delaiMs = delaiPoll;
            return reponse;
        });
        serveur.route("DELETE", kCancel, [this](const RequeteRecue &) {
            return ReponseFaux::json(200, QJsonObject{{QStringLiteral("ok"), annulationOk},
                                                     {QStringLiteral("session_id"), kId}});
        });
    }

    void ouvrir()
    {
        preparation.activer();
        passerelle.ouvrir();
        if (!QTest::qWaitFor([this] {
                return passerelle.etat() == GatewayClient::Etat::Pret
                    && preparation.etat() != QStringLiteral("inconnu") && !preparation.occupe();
            }, 10000)) qFatal("préparation initiale jamais terminée");
    }

    void demanderConnexion()
    {
        preparation.connecter();
        if (!QTest::qWaitFor([this] { return preparation.defiActif(); }, 5000))
            qFatal("défi jamais reçu");
    }
};
} // namespace

class TestPreparationHermes : public QObject
{
    Q_OBJECT
private slots:
    void reutiliseLaConfigurationExistante();
    void distingueAbsenceEtRefusDeResolution();
    void reponsesIllisiblesNeDeviennentPasUnCompte();
    void connexionReellePuisControleDuModele();
    void approbationNeGarantitPasLaResolution();
    void annulationPendantLeDemarrage();
    void annulationConfirmeeEtNonConfirmee();
    void refuseLesDefisInvalides_data();
    void refuseLesDefisInvalides();
    void expirationAnnuleLeFlux();
    void reponseDunAutreFluxRefusee();
    void finDeSessionInvalideLesReponsesTardives();
    void changementDeServeurOublieLeDefi();
    void erreurHttpNemetPasDeSecretDansLinterface();
};

void TestPreparationHermes::reutiliseLaConfigurationExistante()
{
    Banc b;
    b.configure = true;
    b.disponible = true;
    b.ouvrir();
    QCOMPARE(b.preparation.etat(), QStringLiteral("pret"));
    QCOMPARE(b.preparation.fournisseur(), QStringLiteral("openai-codex"));
    QCOMPARE(b.preparation.modele(), QStringLiteral("gpt-5.4"));
    QCOMPARE(b.demandesStatut, 1);
    QCOMPARE(b.demandesResolution, 1);
    QCOMPARE(b.serveur.compter("POST", kStart), 0);
    QCOMPARE(b.ouvertures, 0);
    QVERIFY(b.preparation.prochaineAction().contains(QStringLiteral("Aucun appel")));
    const auto statut = b.serveur.tramesDeMethode(QStringLiteral("setup.status"));
    const auto resolution = b.serveur.tramesDeMethode(QStringLiteral("setup.runtime_check"));
    QCOMPARE(statut.size(), 1);
    QCOMPARE(resolution.size(), 1);
    QVERIFY(statut.first().value(QStringLiteral("params")).toObject().isEmpty());
    QVERIFY(resolution.first().value(QStringLiteral("params")).toObject().isEmpty());
    // Un autre fournisseur déjà choisi reste celui de Hermes : aucune sélection forcée.
    b.resolutionForcee = {{QStringLiteral("ok"), true},
                          {QStringLiteral("provider"), QStringLiteral("anthropic")},
                          {QStringLiteral("model"), QStringLiteral("claude-sonnet-4-6")}};
    b.preparation.verifier();
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("pret"));
    QCOMPARE(b.preparation.fournisseur(), QStringLiteral("anthropic"));
    QCOMPARE(b.preparation.modele(), QStringLiteral("claude-sonnet-4-6"));
    QCOMPARE(b.serveur.compter("POST", kStart), 0);
}

void TestPreparationHermes::distingueAbsenceEtRefusDeResolution()
{
    Banc b;
    b.ouvrir();
    QCOMPARE(b.preparation.etat(), QStringLiteral("manquant"));
    QVERIFY(b.preparation.peutConnecter());
    b.configure = true;
    b.preparation.verifier();
    QTRY_VERIFY(!b.preparation.occupe());
    QCOMPARE(b.preparation.etat(), QStringLiteral("erreur"));
    QVERIFY(b.preparation.detail().contains(QStringLiteral("No provider configured")));
    QCOMPARE(b.serveur.compter("POST", kStart), 0);
}

void TestPreparationHermes::reponsesIllisiblesNeDeviennentPasUnCompte()
{
    Banc b;
    b.statutForce = {{QStringLiteral("provider_configured"), QStringLiteral("true")}};
    b.ouvrir();
    QCOMPARE(b.preparation.etat(), QStringLiteral("erreur"));
    QCOMPARE(b.demandesResolution, 0);
    b.statutForce = {};
    b.resolutionForcee = {{QStringLiteral("ok"), true}};
    b.preparation.verifier();
    QTRY_VERIFY(!b.preparation.occupe());
    QCOMPARE(b.preparation.etat(), QStringLiteral("erreur"));
    QVERIFY(b.preparation.modele().isEmpty());
}

void TestPreparationHermes::connexionReellePuisControleDuModele()
{
    Banc b;
    b.ouvrir();
    b.demanderConnexion();
    QCOMPARE(b.preparation.codeAppareil(), QStringLiteral("ABCD-EFGH"));
    QCOMPARE(b.ouvertures, 0); // aucune ouverture du navigateur sans le geste dédié
    QVERIFY(b.preparation.ouvrirVerification());
    QCOMPARE(b.urlOuverte, QUrl(QStringLiteral("https://auth.openai.com/codex/device")));
    QTRY_VERIFY(b.serveur.compter("GET", kPoll) >= 1);
    QCOMPARE(b.preparation.etat(), QStringLiteral("attente"));
    const auto demande = b.serveur.filtrer("POST", kStart).first();
    QCOMPARE(demande.entete("Authorization"), QByteArrayLiteral("Bearer session-acp"));
    QVERIFY(!demande.aEntete("Cookie"));
    QVERIFY(!demande.aEntete("Origin"));
    QVERIFY(demande.json().isEmpty());
    QVERIFY(demande.requete.isEmpty());
    b.configure = true;
    b.disponible = true;
    b.statut = QStringLiteral("approved");
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("pret"));
    QVERIFY(b.preparation.codeAppareil().isEmpty());
    QVERIFY(!b.preparation.defiActif());
    QCOMPARE(b.demandesStatut, 2);
    QCOMPARE(b.demandesResolution, 2);
    QVERIFY(b.preparation.detail().contains(QStringLiteral("Autorisation enregistrée")));
    QCOMPARE(b.serveur.compter("POST", kStart), 1);
}

void TestPreparationHermes::approbationNeGarantitPasLaResolution()
{
    Banc b;
    b.ouvrir();
    b.demanderConnexion();
    b.configure = true; // compte enregistré, mais modèle encore invalide
    b.statut = QStringLiteral("approved");
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("erreur"));
    QCOMPARE(b.demandesResolution, 2);
    QVERIFY(b.preparation.codeAppareil().isEmpty());
    QVERIFY(b.preparation.prochaineAction().contains(QStringLiteral("modèle")));
    QVERIFY(b.preparation.modele().isEmpty());
}

void TestPreparationHermes::annulationPendantLeDemarrage()
{
    Banc b;
    b.delaiStart = 150;
    b.ouvrir();
    b.preparation.connecter();
    b.preparation.annuler();
    QCOMPARE(b.preparation.etat(), QStringLiteral("annulation"));
    QVERIFY(b.preparation.codeAppareil().isEmpty());
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("annule"));
    QCOMPARE(b.serveur.compter("POST", kStart), 1);
    QCOMPARE(b.serveur.compter("DELETE", kCancel), 1);
    QCOMPARE(b.serveur.compter("GET", kPoll), 0);
    QCOMPARE(b.ouvertures, 0);
    QCOMPARE(b.demandesStatut, 1);
}

void TestPreparationHermes::annulationConfirmeeEtNonConfirmee()
{
    Banc b;
    b.ouvrir();
    b.demanderConnexion();
    b.preparation.annuler();
    QVERIFY(b.preparation.codeAppareil().isEmpty()); // effacé avant l'acquittement réseau
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("annule"));
    auto demande = b.serveur.filtrer("DELETE", kCancel).first();
    QCOMPARE(demande.entete("Authorization"), QByteArrayLiteral("Bearer session-acp"));
    QVERIFY(!demande.aEntete("Cookie"));
    b.annulationOk = false;
    b.demanderConnexion();
    b.preparation.annuler();
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("erreur"));
    QVERIFY(b.preparation.detail().contains(QStringLiteral("pas confirmé")));
}

void TestPreparationHermes::refuseLesDefisInvalides_data()
{
    QTest::addColumn<QString>("champ");
    QTest::addColumn<QJsonValue>("valeur");
    QTest::addColumn<int>("annulations");
    QTest::newRow("URL externe") << QStringLiteral("verification_url") << QJsonValue(QStringLiteral("https://pirate.invalid/codex/device")) << 1;
    QTest::newRow("URL paramètre") << QStringLiteral("verification_url") << QJsonValue(QStringLiteral("https://auth.openai.com/codex/device?token=inconnu")) << 1;
    QTest::newRow("HTTP refusé") << QStringLiteral("verification_url") << QJsonValue(QStringLiteral("http://auth.openai.com/codex/device")) << 1;
    QTest::newRow("échéance absente") << QStringLiteral("expires_in") << QJsonValue(QJsonValue::Null) << 1;
    QTest::newRow("échéance nulle") << QStringLiteral("expires_in") << QJsonValue(0) << 1;
    QTest::newRow("intervalle excessif") << QStringLiteral("poll_interval") << QJsonValue(1000) << 1;
    QTest::newRow("autre flow") << QStringLiteral("flow") << QJsonValue(QStringLiteral("pkce")) << 1;
    QTest::newRow("code multiligne") << QStringLiteral("user_code") << QJsonValue(QStringLiteral("ABCD\nEFGH")) << 1;
    QTest::newRow("id chemin arbitraire") << QStringLiteral("session_id") << QJsonValue(QStringLiteral("../../autre")) << 0;
}

void TestPreparationHermes::refuseLesDefisInvalides()
{
    QFETCH(QString, champ);
    QFETCH(QJsonValue, valeur);
    QFETCH(int, annulations);
    Banc b;
    b.defi.insert(champ, valeur);
    b.ouvrir();
    b.preparation.connecter();
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("erreur"));
    QVERIFY(b.preparation.codeAppareil().isEmpty());
    QVERIFY(!b.preparation.ouvrirVerification());
    QCOMPARE(b.ouvertures, 0);
    QCOMPARE(b.serveur.compter("DELETE", kCancel), annulations);
    QCOMPARE(b.serveur.compter("GET", kPoll), 0);
}

void TestPreparationHermes::expirationAnnuleLeFlux()
{
    Banc b;
    b.preparation.setDelaisTest(std::chrono::milliseconds(10), std::chrono::milliseconds(250));
    b.ouvrir();
    b.demanderConnexion();
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("expire"));
    QVERIFY(b.preparation.codeAppareil().isEmpty());
    QCOMPARE(b.serveur.compter("DELETE", kCancel), 1);
    QCOMPARE(b.demandesStatut, 1);
}

void TestPreparationHermes::reponseDunAutreFluxRefusee()
{
    Banc b;
    b.idReponse = QStringLiteral("zyxwvutsrqponmlkjihgfe");
    b.statut = QStringLiteral("approved");
    b.ouvrir();
    b.demanderConnexion();
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("erreur"));
    QVERIFY(b.preparation.detail().contains(QStringLiteral("autre flux")));
    QCOMPARE(b.serveur.compter("DELETE", kCancel), 1);
    QCOMPARE(b.demandesStatut, 1);
}

void TestPreparationHermes::finDeSessionInvalideLesReponsesTardives()
{
    Banc b;
    b.delaiPoll = 180;
    b.statut = QStringLiteral("approved");
    b.ouvrir();
    b.demanderConnexion();
    QTRY_VERIFY(b.serveur.compter("GET", kPoll) >= 1);
    b.preparation.oublier();
    QCOMPARE(b.preparation.etat(), QStringLiteral("inconnu"));
    QVERIFY(b.preparation.codeAppareil().isEmpty());
    QVERIFY(!b.preparation.peutConnecter());
    QTest::qWait(230);
    QCOMPARE(b.preparation.etat(), QStringLiteral("inconnu"));
    QCOMPARE(b.demandesStatut, 1);
    QCOMPARE(b.serveur.compter("DELETE", kCancel), 0); // aucun geste avec la session perdue
}

void TestPreparationHermes::changementDeServeurOublieLeDefi()
{
    Banc b;
    b.delaiPoll = 180;
    b.ouvrir();
    b.demanderConnexion();
    QTRY_VERIFY(b.serveur.compter("GET", kPoll) >= 1);
    FauxHermes autre;
    QVERIFY(!b.client.setBaseUrl(autre.url()).isError());
    QCOMPARE(b.preparation.etat(), QStringLiteral("inconnu"));
    QVERIFY(b.preparation.codeAppareil().isEmpty());
    QVERIFY(b.preparation.modele().isEmpty());
    QVERIFY(!b.preparation.ouvrirVerification());
    QVERIFY(autre.requetes.isEmpty());
}

void TestPreparationHermes::erreurHttpNemetPasDeSecretDansLinterface()
{
    Banc b;
    b.serveur.route("POST", kStart, [](const RequeteRecue &) {
        return ReponseFaux::json(400, QJsonObject{{QStringLiteral("detail"),
            QStringLiteral("Authorization: Bearer temoin-interdit")}}); });
    b.ouvrir();
    b.preparation.connecter();
    QTRY_COMPARE(b.preparation.etat(), QStringLiteral("erreur"));
    QVERIFY(!b.preparation.detail().contains(QStringLiteral("temoin-interdit")));
    QVERIFY(b.preparation.codeAppareil().isEmpty());
    QCOMPARE(b.serveur.compter("POST", kStart), 1);
}

QTEST_MAIN(TestPreparationHermes)
#include "tst_preparation_hermes.moc"