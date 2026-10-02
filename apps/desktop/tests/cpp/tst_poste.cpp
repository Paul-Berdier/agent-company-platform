// Page Poste contre les formes RÉELLES de `GET /v1/poste` (fixtures-poste.ts de l'interface
// web, capturées sur l'image) et le faux Hermes :
//  - bandeau, poste enrôlé, inventaire libellés en français ; valeur absente = « Inconnu » ;
//  - gestes offerts selon l'état servi (enrôler, confirmer, relever, révoquer) ;
//  - code d'enrôlement : rendu une fois, décompte, copie, EFFACÉ en quittant la page, à la
//    perte de session et à l'expiration ; jamais recopié dans un autre texte ;
//  - corps exacts de la confirmation et de la révocation ; refus du greffon tels quels ;
//  - relevé : message du greffon tel quel ;
//  - exécutant Railway (P6) : lu seulement si le serveur le publie.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/PosteViewModel.h"

#include <QJsonArray>
#include <QMetaProperty>
#include <QSignalSpy>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kMachine = QStringLiteral("m1563c2ef174");

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    PosteViewModel poste{&greffon, nullptr, &flux};
    QJsonObject vue = fixture(QStringLiteral("poste-non-configure.json"));
    ReponseFaux reponseCode = ReponseFaux::json(201, fixture(QStringLiteral("code-enrolement.json")));
    ReponseFaux reponseConfirmation = ReponseFaux::json(200, QJsonObject{{QStringLiteral("machine"), kMachine}});
    ReponseFaux reponseRevocation = ReponseFaux::json(200, QJsonObject{{QStringLiteral("machine"), kMachine}});
    ReponseFaux reponseReleve = ReponseFaux::json(202, fixture(QStringLiteral("releve-demande.json")));
    qint64 maintenant = 1790451615; // 600 s avant l'expiration du code de la fixture
    QStringList copies;

    Banc()
    {
        serveur.installerAuthentification();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
        flux.setIntervalleFond(std::chrono::hours(1));
        poste.setHorloge([this] { return maintenant; });
        poste.setPressePapiers([this](const QString &texte) {
            copies.append(texte);
            return true;
        });
        serveur.route("GET", kP + QStringLiteral("/poste"), [this](const RequeteRecue &) { return ReponseFaux::json(200, vue); });
        serveur.route("GET", kP + QStringLiteral("/projets"),
                      [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projets.json"))); });
        serveur.route("POST", kP + QStringLiteral("/poste/enrolement"), [this](const RequeteRecue &) { return reponseCode; });
        serveur.route("POST", kP + QStringLiteral("/poste/confirmation"), [this](const RequeteRecue &) { return reponseConfirmation; });
        serveur.route("POST", kP + QStringLiteral("/poste/revocation"), [this](const RequeteRecue &) { return reponseRevocation; });
        serveur.route("POST", kP + QStringLiteral("/poste/releve"), [this](const RequeteRecue &) { return reponseReleve; });
    }

    void ouvrirLaPage(const QString &nom)
    {
        vue = fixture(nom);
        flux.demarrer();
        poste.setPageVisible(true);
        QTRY_VERIFY(poste.lue());
    }

    //! Relit la page et attend que la réponse soit appliquée.
    void relire()
    {
        QSignalSpy lu(&poste, &PosteViewModel::posteChange);
        poste.actualiser();
        QVERIFY(lu.wait(3000));
    }

    int lectures() const { return serveur.compter("GET", kP + QStringLiteral("/poste")); }
};

QStringList textesExposes(const QObject &objet)
{
    QStringList textes;
    const QMetaObject *meta = objet.metaObject();
    for (int index = 0; index < meta->propertyCount(); ++index) {
        const QMetaProperty propriete = meta->property(index);
        if (QString::fromLatin1(propriete.name()) == QLatin1String("code")) {
            continue;
        }
        const QVariant valeur = propriete.read(&objet);
        if (valeur.canConvert<QString>()) {
            textes.append(valeur.toString());
        }
    }
    return textes;
}

} // namespace

class TestPoste : public QObject
{
    Q_OBJECT

private slots:
    void bandeauSelonLEtat();
    void inventaireLibelle();
    void valeursAbsentesInconnues();
    void gestesSelonLEtatServi();
    void pageLueSeulementAffichee();
    void codeUneFoisPuisOublie();
    void codeEffaceALaPerteDeSessionEtAExpiration();
    void codeEffaceALaPerteDeSessionFenetreReduite();
    void confirmationCorpsExactEtRefusTelQuel();
    void revocationCorpsExactEtBornes();
    void releveMessageDuGreffon();
    void executantSeulementSiPublie();
};

void TestPoste::bandeauSelonLEtat()
{
    const QVariantMap nonConfigure = PosteViewModel::construireEtat(fixture(QStringLiteral("poste-non-configure.json")));
    QCOMPARE(nonConfigure.value(QStringLiteral("libelle")).toString(), QStringLiteral("Non configuré"));
    QCOMPARE(nonConfigure.value(QStringLiteral("cle")).toString(), QStringLiteral("notConfigured"));
    QCOMPARE(nonConfigure.value(QStringLiteral("message")).toString(),
             QStringLiteral("Le poste n'a jamais été vu : enrôlez-le depuis la page Poste."));
    QCOMPARE(nonConfigure.value(QStringLiteral("cartesEnAttente")).toString(), QStringLiteral("0"));

    const QVariantMap aConfirmer = PosteViewModel::construireEtat(fixture(QStringLiteral("poste-a-confirmer.json")));
    QCOMPARE(aConfirmer.value(QStringLiteral("libelle")).toString(), QStringLiteral("À confirmer"));
    QCOMPARE(aConfirmer.value(QStringLiteral("detail")).toString(), QStringLiteral("Empreinte annoncée : 6093-5536"));

    const QVariantMap enLigne = PosteViewModel::construireEtat(fixture(QStringLiteral("poste-en-ligne.json")));
    QCOMPARE(enLigne.value(QStringLiteral("libelle")).toString(), QStringLiteral("En ligne"));
    QCOMPARE(enLigne.value(QStringLiteral("cle")).toString(), QStringLiteral("succeeded"));
    QVERIFY(enLigne.value(QStringLiteral("detail")).toString().startsWith(QStringLiteral("Vu le 26/09/2026")));
    QCOMPARE(enLigne.value(QStringLiteral("politiqueInvalide")).toBool(), false);
    QCOMPARE(enLigne.value(QStringLiteral("message")).toString(), QString());

    // Révoqué, politique invalide, pause des réclamations : dits, jamais devinés.
    QJsonObject revoque = fixture(QStringLiteral("poste-en-ligne.json"));
    QJsonObject poste = revoque.value(QStringLiteral("poste")).toObject();
    poste.insert(QStringLiteral("etat"), QStringLiteral("revoque"));
    poste.insert(QStringLiteral("pause_reclamations"), true);
    revoque.insert(QStringLiteral("poste"), poste);
    QJsonObject machines = revoque.value(QStringLiteral("machine")).toObject();
    QJsonObject machine = machines.value(QStringLiteral("machine")).toObject();
    machine.insert(QStringLiteral("politique_valide"), false);
    machine.insert(QStringLiteral("revoque_le"), QJsonValue::Null);
    machines.insert(QStringLiteral("machine"), machine);
    revoque.insert(QStringLiteral("machine"), machines);
    const QVariantMap r = PosteViewModel::construireEtat(revoque);
    QCOMPARE(r.value(QStringLiteral("libelle")).toString(), QStringLiteral("Révoqué"));
    QCOMPARE(r.value(QStringLiteral("detail")).toString(), QStringLiteral("Révoqué le Inconnu"));
    QCOMPARE(r.value(QStringLiteral("politiqueInvalide")).toBool(), true);
    QCOMPARE(r.value(QStringLiteral("pauseReclamations")).toBool(), true);

    // État inconnu de la station : montré tel quel, pastille « Inconnu ».
    const QVariantMap inconnu = PosteViewModel::construireEtat(
        QJsonObject{{QStringLiteral("poste"), QJsonObject{{QStringLiteral("etat"), QStringLiteral("en_orbite")}}}});
    QCOMPARE(inconnu.value(QStringLiteral("libelle")).toString(), QStringLiteral("en_orbite"));
    QCOMPARE(inconnu.value(QStringLiteral("cle")).toString(), QStringLiteral("unknown"));
}

void TestPoste::inventaireLibelle()
{
    const QJsonObject vue = fixture(QStringLiteral("poste-en-ligne.json"));
    const QVariantMap machine = PosteViewModel::construireMachine(vue);
    QCOMPARE(machine.value(QStringLiteral("presente")).toBool(), true);
    QCOMPARE(machine.value(QStringLiteral("nom")).toString(), QStringLiteral("Poste Windows"));
    QCOMPARE(machine.value(QStringLiteral("versionPoste")).toString(), QStringLiteral("0.11.0"));
    QCOMPARE(machine.value(QStringLiteral("protocole")).toString(), QStringLiteral("acp-machine/1"));

    const QVariantMap inventaire = PosteViewModel::construireInventaire(vue);
    QCOMPARE(inventaire.value(QStringLiteral("present")).toBool(), true);
    QCOMPARE(inventaire.value(QStringLiteral("compte")).toString(), QStringLiteral("Compte dédié acp-poste"));
    QCOMPARE(inventaire.value(QStringLiteral("windows")).toString(), QStringLiteral("10.0.19045"));
    QCOMPARE(inventaire.value(QStringLiteral("python")).toString(), QStringLiteral("3.12.10"));
    QCOMPARE(inventaire.value(QStringLiteral("empreintePolitique")).toString(), QStringLiteral("9c2e41ab07d3"));
    const QVariantList versions = inventaire.value(QStringLiteral("versions")).toList();
    QCOMPARE(versions.size(), 2);
    QCOMPARE(versions.at(0).toMap().value(QStringLiteral("nom")).toString(), QStringLiteral("Codex"));
    QCOMPARE(versions.at(0).toMap().value(QStringLiteral("lue")).toString(), QStringLiteral("0.156.1"));
    QCOMPARE(versions.at(0).toMap().value(QStringLiteral("conforme")).toString(), QStringLiteral("Oui"));
    QCOMPARE(versions.at(1).toMap().value(QStringLiteral("lue")).toString(), QStringLiteral("2.1.280"));
    QCOMPARE(inventaire.value(QStringLiteral("readiness")).toString(), QStringLiteral("ready"));
    QCOMPARE(inventaire.value(QStringLiteral("ecritureAdmise")).toString(), QStringLiteral("Oui"));
    QCOMPARE(inventaire.value(QStringLiteral("stockage")).toString(), QStringLiteral("keyring"));
    QCOMPARE(inventaire.value(QStringLiteral("codexLibelle")).toString(), QStringLiteral("Compte ChatGPT"));
    QCOMPARE(inventaire.value(QStringLiteral("codexCle")).toString(), QStringLiteral("succeeded"));
    QCOMPARE(inventaire.value(QStringLiteral("offre")).toString(), QStringLiteral("prolite"));
    QCOMPARE(inventaire.value(QStringLiteral("claudeLibelle")).toString(), QStringLiteral("Jeton reconnu"));
    QCOMPARE(inventaire.value(QStringLiteral("depots")).toStringList(), QStringList{QStringLiteral("jetable")});
}

void TestPoste::valeursAbsentesInconnues()
{
    QCOMPARE(PosteViewModel::construireInventaire(fixture(QStringLiteral("poste-non-configure.json")))
                 .value(QStringLiteral("present")).toBool(),
             false);
    QCOMPARE(PosteViewModel::construireMachine(fixture(QStringLiteral("poste-non-configure.json")))
                 .value(QStringLiteral("presente")).toBool(),
             false);
    // Inventaire présent mais vide : tout vaut « Inconnu », rien n'est estimé.
    const QVariantMap vide = PosteViewModel::construireInventaire(
        QJsonObject{{QStringLiteral("inventaire"), QJsonObject{{QStringLiteral("contenu"), QJsonValue::Null}}}});
    QCOMPARE(vide.value(QStringLiteral("present")).toBool(), true);
    for (const char *cle : {"recuLe", "compte", "windows", "readiness", "ecritureAdmise", "offre", "codexLibelle"}) {
        QCOMPARE(vide.value(QString::fromLatin1(cle)).toString(), QStringLiteral("Inconnu"));
    }
    QCOMPARE(vide.value(QStringLiteral("codexCle")).toString(), QStringLiteral("unknown"));
    QCOMPARE(vide.value(QStringLiteral("versions")).toList().at(0).toMap().value(QStringLiteral("conforme")).toString(),
             QStringLiteral("Inconnu"));
    // Connexion d'un code inconnu : montrée brute, pastille « Inconnu ».
    const QVariantMap autre = PosteViewModel::construireInventaire(QJsonObject{{QStringLiteral("inventaire"), QJsonObject{
        {QStringLiteral("contenu"), QJsonObject{{QStringLiteral("connexions"),
                                                 QJsonObject{{QStringLiteral("codex"), QStringLiteral("pigeon")}}}}}}}});
    QCOMPARE(autre.value(QStringLiteral("codexLibelle")).toString(), QStringLiteral("pigeon"));
    QCOMPARE(autre.value(QStringLiteral("codexCle")).toString(), QStringLiteral("unknown"));

    QJsonObject avecOrdre = fixture(QStringLiteral("poste-en-ligne.json"));
    avecOrdre.insert(QStringLiteral("ordres"), QJsonArray{
        QJsonObject{{QStringLiteral("id"), 4}, {QStringLiteral("genre"), QStringLiteral("releve")},
                    {QStringLiteral("cree_le"), 1790451615}, {QStringLiteral("livre"), false}},
        QJsonObject{{QStringLiteral("id"), 5}, {QStringLiteral("genre"), QStringLiteral("teleportation")},
                    {QStringLiteral("livre"), true}}});
    const QJsonArray ordres = PosteViewModel::construireOrdres(avecOrdre);
    QCOMPARE(ordres.at(0).toObject().value(QStringLiteral("genre")).toString(), QStringLiteral("Relevé"));
    QCOMPARE(ordres.at(0).toObject().value(QStringLiteral("livraison")).toString(), QStringLiteral("Pas encore livré"));
    QCOMPARE(ordres.at(1).toObject().value(QStringLiteral("genre")).toString(), QStringLiteral("teleportation"));
    QCOMPARE(ordres.at(1).toObject().value(QStringLiteral("creeLe")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(ordres.at(1).toObject().value(QStringLiteral("livraison")).toString(), QStringLiteral("Livré au poste"));
}

void TestPoste::gestesSelonLEtatServi()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-non-configure.json"));
    QVERIFY(banc.poste.peutEnroler());
    QVERIFY(!banc.poste.peutConfirmer());
    QVERIFY(!banc.poste.peutRelever());
    QVERIFY(!banc.poste.peutRevoquer());

    banc.vue = fixture(QStringLiteral("poste-a-confirmer.json"));
    banc.relire();
    QTRY_VERIFY(banc.poste.peutConfirmer());
    QVERIFY(banc.poste.peutEnroler());
    QVERIFY(!banc.poste.peutRelever());
    QVERIFY(banc.poste.peutRevoquer());

    banc.vue = fixture(QStringLiteral("poste-en-ligne.json"));
    banc.relire();
    QTRY_VERIFY(banc.poste.peutRelever());
    QVERIFY(!banc.poste.peutEnroler());
    QVERIFY(!banc.poste.peutConfirmer());
    QVERIFY(banc.poste.peutRevoquer());

    // Un poste actif n'en laisse pas enrôler un second : refusé par la station, sans envoi.
    banc.poste.enroler();
    QVERIFY(banc.poste.erreurGeste().startsWith(QStringLiteral("Un poste est déjà enrôlé")));
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/enrolement")), 0);
}

void TestPoste::pageLueSeulementAffichee()
{
    Banc banc;
    banc.flux.demarrer();
    QTest::qWait(60);
    QCOMPARE(banc.lectures(), 0);
    banc.poste.setPageVisible(true);
    QTRY_COMPARE(banc.lectures(), 1);
    QTRY_VERIFY(banc.poste.lue());
    QVERIFY(banc.poste.lecture().startsWith(QStringLiteral("Lu à ")));
    banc.poste.setPageVisible(false);
    QTRY_VERIFY(!banc.poste.actif());
}

void TestPoste::codeUneFoisPuisOublie()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-non-configure.json"));
    QCOMPARE(banc.poste.secondesRestantes(), -1);
    banc.poste.enroler();
    QTRY_VERIFY(!banc.poste.gesteEnCours());
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/poste/enrolement"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), QJsonObject{});
    QCOMPARE(banc.poste.code(), QStringLiteral("acpe_CODE-DE-TEST"));
    QCOMPARE(banc.poste.commande(), QStringLiteral("& \"$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd\" enroler"));
    QCOMPARE(banc.poste.secondesRestantes(), 600);
    QCOMPARE(banc.poste.messageGeste(), QStringLiteral("Code d'enrôlement généré : il ne s'affiche qu'une fois."));
    // Le code ne figure dans AUCUNE autre propriété de la page (message, état, lecture…).
    for (const QString &texte : textesExposes(banc.poste)) {
        QVERIFY2(!texte.contains(QStringLiteral("acpe_CODE-DE-TEST")), qPrintable(texte));
    }
    banc.maintenant += 61;
    QCOMPARE(banc.poste.secondesRestantes(), 539);

    banc.poste.copierCode();
    QCOMPARE(banc.copies, QStringList{QStringLiteral("acpe_CODE-DE-TEST")});
    QCOMPARE(banc.poste.messageCopie(), QStringLiteral("Code copié : videz le presse-papiers après usage."));

    // Page quittée : le code quitte la mémoire de la page.
    banc.poste.setPageVisible(false);
    QCOMPARE(banc.poste.code(), QString());
    QCOMPARE(banc.poste.commande(), QString());
    QCOMPARE(banc.poste.messageCopie(), QString());
    QCOMPARE(banc.poste.secondesRestantes(), -1);
    banc.poste.copierCode();
    QCOMPARE(banc.copies.size(), 1);
    QCOMPARE(banc.poste.messageCopie(), QStringLiteral("Copie impossible : sélectionnez le code à la main."));
}

void TestPoste::codeEffaceALaPerteDeSessionFenetreReduite()
{
    // Fenêtre réduite : les pages sont déjà inactives, la perte de session ne change plus
    // `pagesActives`. Le code doit quand même quitter la mémoire de la page.
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-non-configure.json"));
    banc.poste.enroler();
    QTRY_COMPARE(banc.poste.code(), QStringLiteral("acpe_CODE-DE-TEST"));
    banc.flux.setFenetreActive(false);
    QCOMPARE(banc.poste.code(), QStringLiteral("acpe_CODE-DE-TEST"));
    banc.flux.arreter(); // session perdue, fenêtre réduite
    QCOMPARE(banc.poste.code(), QString());
    QCOMPARE(banc.poste.commande(), QString());
    banc.flux.setFenetreActive(true);
    QCOMPARE(banc.poste.code(), QString());
}

void TestPoste::codeEffaceALaPerteDeSessionEtAExpiration()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-non-configure.json"));
    banc.poste.enroler();
    QTRY_COMPARE(banc.poste.code(), QStringLiteral("acpe_CODE-DE-TEST"));
    banc.flux.arreter(); // session perdue
    QCOMPARE(banc.poste.code(), QString());

    banc.flux.demarrer();
    QTRY_VERIFY(banc.poste.actif());
    banc.poste.enroler();
    QTRY_COMPARE(banc.poste.code(), QStringLiteral("acpe_CODE-DE-TEST"));
    QVERIFY(!banc.poste.codeExpire());
    banc.maintenant += 601;
    QTRY_VERIFY_WITH_TIMEOUT(banc.poste.codeExpire(), 3000);
    QCOMPARE(banc.poste.code(), QString());

    // Réponse sans code : refus dit, aucun code inventé.
    banc.reponseCode = ReponseFaux::json(201, QJsonObject{{QStringLiteral("expire_le"), 1790452215}});
    banc.poste.enroler();
    QTRY_VERIFY(!banc.poste.gesteEnCours());
    QCOMPARE(banc.poste.erreurGeste(), QStringLiteral("Réponse du greffon illisible : aucun code d'enrôlement rendu."));
    QCOMPARE(banc.poste.code(), QString());
}

void TestPoste::confirmationCorpsExactEtRefusTelQuel()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-a-confirmer.json"));
    banc.poste.confirmer(QStringLiteral("   "));
    QVERIFY(banc.poste.erreurGeste().startsWith(QStringLiteral("Recopiez l'empreinte")));
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/confirmation")), 0);

    banc.poste.confirmer(QStringLiteral(" 6093-5536 "));
    QTRY_VERIFY(!banc.poste.gesteEnCours());
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/poste/confirmation"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), (QJsonObject{{QStringLiteral("machine_id"), kMachine},
                                                 {QStringLiteral("empreinte"), QStringLiteral("6093-5536")}}));
    QCOMPARE(envois.first().entete("content-type"), QByteArrayLiteral("application/json"));
    QCOMPARE(banc.poste.messageGeste(), QStringLiteral("Poste confirmé : il compte désormais."));

    banc.reponseConfirmation = ReponseFaux::json(409, fixture(QStringLiteral("refus-empreinte.json")));
    banc.poste.confirmer(QStringLiteral("0000-0000"));
    QTRY_VERIFY(!banc.poste.gesteEnCours());
    QCOMPARE(banc.poste.erreurGeste(),
             QStringLiteral("L'empreinte saisie ne correspond pas à celle du poste enrôlé : n'activez pas ce poste ; "
                            "révoquez-le et recommencez."));
    QCOMPARE(banc.poste.messageGeste(), QString());

    // Plus rien à confirmer : refusé par la station, page relue, aucun envoi.
    banc.vue = fixture(QStringLiteral("poste-en-ligne.json"));
    banc.relire();
    QTRY_VERIFY(!banc.poste.peutConfirmer());
    const int avant = banc.serveur.compter("POST", kP + QStringLiteral("/poste/confirmation"));
    banc.poste.confirmer(QStringLiteral("6093-5536"));
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/confirmation")), avant);
    QCOMPARE(banc.poste.erreurGeste(), QStringLiteral("Aucun poste n'attend de confirmation : la page est relue."));
}

void TestPoste::revocationCorpsExactEtBornes()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    banc.poste.revoquer(QString());
    banc.poste.revoquer(QString(201, QLatin1Char('x')));
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/revocation")), 0);
    QCOMPARE(banc.poste.erreurGeste(), QStringLiteral("Indiquez un motif de révocation (200 caractères au plus)."));

    banc.poste.revoquer(QStringLiteral(" PC remplacé "));
    QTRY_VERIFY(!banc.poste.gesteEnCours());
    const auto envois = banc.serveur.filtrer("POST", kP + QStringLiteral("/poste/revocation"));
    QCOMPARE(envois.size(), 1);
    QCOMPARE(envois.first().json(), (QJsonObject{{QStringLiteral("machine_id"), kMachine},
                                                 {QStringLiteral("motif"), QStringLiteral("PC remplacé")}}));
    QCOMPARE(banc.poste.messageGeste(), QStringLiteral("Poste révoqué."));

    banc.reponseRevocation = ReponseFaux::json(409, QJsonObject{{QStringLiteral("detail"), QJsonObject{
        {QStringLiteral("code"), QStringLiteral("deja_revoque")},
        {QStringLiteral("message"), QStringLiteral("Refusé par ACP : ce poste est déjà révoqué.")}}}});
    banc.poste.revoquer(QStringLiteral("encore"));
    QTRY_VERIFY(!banc.poste.gesteEnCours());
    QCOMPARE(banc.poste.erreurGeste(), QStringLiteral("Refusé par ACP : ce poste est déjà révoqué."));
}

void TestPoste::releveMessageDuGreffon()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    banc.poste.relever();
    QTRY_VERIFY(!banc.poste.gesteEnCours());
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/poste/releve")).first().json(), QJsonObject{});
    QCOMPARE(banc.poste.messageGeste(),
             QStringLiteral("Ordre de relevé mis en file : le poste le reçoit à sa prochaine attente."));

    banc.reponseReleve = ReponseFaux::json(409, QJsonObject{{QStringLiteral("detail"), QJsonObject{
        {QStringLiteral("code"), QStringLiteral("aucun_poste_actif")},
        {QStringLiteral("message"), QStringLiteral("Refusé par ACP : aucun poste actif.")}}}});
    banc.poste.relever();
    QTRY_VERIFY(!banc.poste.gesteEnCours());
    QCOMPARE(banc.poste.erreurGeste(), QStringLiteral("Refusé par ACP : aucun poste actif."));
}

void TestPoste::executantSeulementSiPublie()
{
    // Constat de relecture P8 : `null` (étape P6 en place, aucun exécutant connu) était confondu
    // avec une clé absente, et la page affirmait l'étape non déployée.
    const QVariantMap aucun = PosteViewModel::construireExecutant(QStringLiteral("aucun"), {});
    QCOMPARE(aucun.value(QStringLiteral("present")).toBool(), false);
    QVERIFY(aucun.value(QStringLiteral("message")).toString().startsWith(QStringLiteral("Aucun exécutant connu pour l'instant")));
    const QVariantMap absent = PosteViewModel::construireExecutant(QStringLiteral("absent"), {});
    QCOMPARE(absent.value(QStringLiteral("message")).toString(), QStringLiteral("Exécutant : non disponible sur ce serveur (étape P6)."));
    QVERIFY(PosteViewModel::construireExecutant(QStringLiteral("illisible"), {}).value(QStringLiteral("message")).toString()
                .contains(QStringLiteral("base du greffon est illisible")));
    QVERIFY(PosteViewModel::construireExecutant(QStringLiteral("inconnu"), {}).value(QStringLiteral("message")).toString()
                .contains(QStringLiteral("n'a pas été lue")));
    const QVariantMap executant = PosteViewModel::construireExecutant(QStringLiteral("annonce"), QJsonObject{
        {QStringLiteral("plateforme"), QStringLiteral("linux")},
        {QStringLiteral("hote"), QStringLiteral("acp-executant")},
        {QStringLiteral("regime"), QStringLiteral("inconnu")},
        {QStringLiteral("peut_executer"), true},
        {QStringLiteral("voies_disponibles"), QJsonArray{QStringLiteral("poste-codex"), QStringLiteral("poste-claude")}},
        {QStringLiteral("voies_fermees"), QJsonArray{}},
        {QStringLiteral("carte_en_cours"), false},
    });
    QCOMPARE(executant.value(QStringLiteral("present")).toBool(), true);
    QCOMPARE(executant.value(QStringLiteral("plateforme")).toString(), QStringLiteral("linux"));
    QCOMPARE(executant.value(QStringLiteral("peutExecuter")).toString(), QStringLiteral("Oui"));
    QCOMPARE(executant.value(QStringLiteral("voiesDisponibles")).toString(), QStringLiteral("Poste (Codex), Poste (Claude)"));
    QCOMPARE(executant.value(QStringLiteral("voiesFermees")).toString(), QStringLiteral("Aucune"));
    QCOMPARE(executant.value(QStringLiteral("carteEnCours")).toString(), QStringLiteral("Non"));
    // Forme non conforme : « Inconnu », jamais une liste devinée.
    const QVariantMap illisible = PosteViewModel::construireExecutant(QStringLiteral("annonce"), QJsonObject{
        {QStringLiteral("voies_disponibles"), QJsonArray{QJsonObject{{QStringLiteral("voie"), QStringLiteral("x")}}}},
        {QStringLiteral("erreur"), QStringLiteral("OperationalError")}});
    QCOMPARE(illisible.value(QStringLiteral("voiesDisponibles")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(illisible.value(QStringLiteral("hote")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(illisible.value(QStringLiteral("erreur")).toString(), QStringLiteral("OperationalError"));

    // Sans compatibilité lue : « inconnu », jamais « non disponible sur ce serveur ».
    Banc banc;
    QCOMPARE(banc.poste.executant().value(QStringLiteral("present")).toBool(), false);
    QVERIFY(banc.poste.executant().value(QStringLiteral("message")).toString().contains(QStringLiteral("n'a pas été lue")));
}

QTEST_MAIN(TestPoste)
#include "tst_poste.moc"
