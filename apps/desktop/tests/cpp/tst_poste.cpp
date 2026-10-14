// Page Poste contre les formes RÉELLES de `GET /v1/poste` (fixtures-poste.ts de l'interface
// web, capturées sur l'image) et le faux Hermes :
//  - bandeau, poste enrôlé, inventaire libellés en français ; valeur absente = « Inconnu » ;
//  - gestes offerts selon l'état servi (enrôler, confirmer, relever, révoquer) ;
//  - code d'enrôlement : rendu une fois, décompte, copie, EFFACÉ en quittant la page, à la
//    perte de session et à l'expiration ; jamais recopié dans un autre texte ;
//  - corps exacts de la confirmation et de la révocation ; refus du greffon tels quels ;
//  - relevé : message du greffon tel quel ;
//  - exécutant Railway (P6) : lu seulement si le serveur le publie ;
//  - étape P7 (partie E) : carte « Dépôts » d'après la fixture PARTAGÉE fixtures_poste/depots.json
//    (visibilité MESURÉE, voies fermées pour chaque dépôt, raison du greffon) ; jamais devinée.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/Sondage.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/PosteViewModel.h"

#include <QDateTime>
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
    void preparationDistingueMachineConnexionsEtExecution();
    void preparationNeValidePasUneLectureEnErreur();
    void resumeSondeSansGarderLesSecretsDePage();
    void codeUneFoisPuisOublie();
    void codeEffaceALaPerteDeSessionEtAExpiration();
    void codeEffaceALaPerteDeSessionFenetreReduite();
    void confirmationCorpsExactEtRefusTelQuel();
    void revocationCorpsExactEtBornes();
    void releveMessageDuGreffon();
    void executantSeulementSiPublie();
    void depotsMesuresParLExecutant();
    void assistantsSeparentLaMachineEtLesComptes();
    void guidesCopientSeulementDesCommandesConnues();
    void resultatsRefusentDesIdentifiantsEtCommandesArbitraires();
    void resultatsGardentMetadonneesSansGuideLocal();
    void resultatsDistinguentInconnuVideEtIncomplet();
    void verificationAttendUnNouvelInventaireDeLaMemeMachine();
    void verificationDistingueRetardEtReponseIllisible();
    void verificationInterrompueSurChangementDeMachine();
    void verificationOublieUneReponseTardive();
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
    QCOMPARE(machine.value(QStringLiteral("versionPoste")).toString(), QStringLiteral("1.0.0"));
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

void TestPoste::preparationDistingueMachineConnexionsEtExecution()
{
    const auto preparer = [](const QJsonObject &vue) {
        return PosteViewModel::construirePreparation(vue, true, {});
    };
    QCOMPARE(PosteViewModel::construirePreparation({}, false, {}).value(QStringLiteral("etat")).toString(), QStringLiteral("inconnu"));
    QCOMPARE(preparer({}).value(QStringLiteral("etat")).toString(), QStringLiteral("inconnu"));
    QCOMPARE(preparer(fixture(QStringLiteral("poste-non-configure.json"))).value(QStringLiteral("etat")).toString(), QStringLiteral("machine_absente"));
    QCOMPARE(preparer(fixture(QStringLiteral("poste-a-confirmer.json"))).value(QStringLiteral("action")).toString(), QStringLiteral("confirmer"));
    QJsonObject vue = fixture(QStringLiteral("poste-en-ligne.json"));
    QJsonObject poste = vue.value(QStringLiteral("poste")).toObject();
    poste.insert(QStringLiteral("etat"), QStringLiteral("hors_ligne"));
    vue.insert(QStringLiteral("poste"), poste);
    QCOMPARE(preparer(vue).value(QStringLiteral("etat")).toString(), QStringLiteral("hors_ligne"));
    // Des comptes observés auparavant ne rendent pas la machine en ligne.
    QVERIFY(preparer(vue).value(QStringLiteral("connectes")).toStringList().isEmpty());
    poste.insert(QStringLiteral("etat"), QStringLiteral("en_ligne"));
    poste.insert(QStringLiteral("pause_reclamations"), true);
    vue.insert(QStringLiteral("poste"), poste);
    QCOMPARE(preparer(vue).value(QStringLiteral("etat")).toString(), QStringLiteral("bloque"));
    poste.insert(QStringLiteral("pause_reclamations"), false);
    vue.insert(QStringLiteral("poste"), poste);
    QJsonObject inventaire = vue.value(QStringLiteral("inventaire")).toObject();
    inventaire.insert(QStringLiteral("machine_id"), QStringLiteral("ancienne-machine"));
    vue.insert(QStringLiteral("inventaire"), inventaire);
    QCOMPARE(preparer(vue).value(QStringLiteral("etat")).toString(), QStringLiteral("releve_manquant"));
    QVERIFY(preparer(vue).value(QStringLiteral("connectes")).toStringList().isEmpty());
    inventaire.insert(QStringLiteral("machine_id"), kMachine);
    QJsonObject contenu = inventaire.value(QStringLiteral("contenu")).toObject();
    const auto poserConnexions = [&](const QString &codex, const QString &claude) {
        contenu.insert(QStringLiteral("connexions"), QJsonObject{{QStringLiteral("codex"), codex}, {QStringLiteral("claude"), claude}});
        inventaire.insert(QStringLiteral("contenu"), contenu);
        vue.insert(QStringLiteral("inventaire"), inventaire);
    };
    poserConnexions(QStringLiteral("non_connecte"), QStringLiteral("jeton_absent"));
    QCOMPARE(preparer(vue).value(QStringLiteral("etat")).toString(), QStringLiteral("connexion_manquante"));
    QCOMPARE(preparer(vue).value(QStringLiteral("manquants")).toStringList(), (QStringList{QStringLiteral("codex"), QStringLiteral("claude")}));
    poserConnexions(QStringLiteral("inconnu"), QStringLiteral("jeton_present_non_verifie"));
    QCOMPARE(preparer(vue).value(QStringLiteral("etat")).toString(), QStringLiteral("a_verifier"));
    QVERIFY(preparer(vue).value(QStringLiteral("manquants")).toStringList().isEmpty());
    QCOMPARE(preparer(vue).value(QStringLiteral("aVerifier")).toStringList().size(), 2);
    poserConnexions(QStringLiteral("compte_chatgpt"), QStringLiteral("jeton_absent"));
    const QVariantMap partiel = preparer(vue);
    QCOMPARE(partiel.value(QStringLiteral("etat")).toString(), QStringLiteral("connexion_partielle"));
    QCOMPARE(partiel.value(QStringLiteral("connectes")).toStringList(), QStringList{QStringLiteral("codex")});
    QCOMPARE(partiel.value(QStringLiteral("fournisseur")).toString(), QStringLiteral("claude"));
    QCOMPARE(partiel.value(QStringLiteral("action")).toString(), QStringLiteral("assistants"));
    poserConnexions(QStringLiteral("cle_api"), QStringLiteral("refuse"));
    QVERIFY(preparer(vue).value(QStringLiteral("connectes")).toStringList().isEmpty());
    QCOMPARE(preparer(vue).value(QStringLiteral("etat")).toString(), QStringLiteral("connexion_manquante"));
    poserConnexions(QStringLiteral("compte_chatgpt"), QStringLiteral("jeton_reconnu"));
    QJsonObject catalogue = vue.value(QStringLiteral("catalogue")).toObject();
    catalogue.insert(QStringLiteral("routage"), QJsonObject{{QStringLiteral("valide"), false}});
    vue.insert(QStringLiteral("catalogue"), catalogue);
    QCOMPARE(preparer(vue).value(QStringLiteral("etat")).toString(), QStringLiteral("routage_a_valider"));
    QCOMPARE(preparer(vue).value(QStringLiteral("action")).toString(), QStringLiteral("routage"));
    // Même un routage annoncé valide ne prouve pas une exécution prête.
    catalogue.insert(QStringLiteral("routage"), QJsonObject{{QStringLiteral("valide"), true}});
    vue.insert(QStringLiteral("catalogue"), catalogue);
    QCOMPARE(preparer(vue).value(QStringLiteral("etat")).toString(), QStringLiteral("connexions_observees"));
    QCOMPARE(preparer(vue).value(QStringLiteral("connectes")).toStringList().size(), 2);
}

void TestPoste::preparationNeValidePasUneLectureEnErreur()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    QVERIFY(!banc.poste.preparation().value(QStringLiteral("connectes")).toStringList().isEmpty());
    QSignalSpy change(&banc.poste, &PosteViewModel::preparationChange);
    banc.serveur.route("GET", kP + QStringLiteral("/poste"), [](const RequeteRecue &) {
        return ReponseFaux::json(403, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Accès refusé")}});
    });
    banc.poste.actualiser();
    QTRY_COMPARE(banc.poste.preparation().value(QStringLiteral("etat")).toString(), QStringLiteral("erreur"));
    QVERIFY(!change.isEmpty());
    QVERIFY(banc.poste.preparation().value(QStringLiteral("connectes")).toStringList().isEmpty());
    QVERIFY(!banc.poste.preparation().value(QStringLiteral("detail")).toString().isEmpty());
    QVERIFY(banc.poste.lue()); // La lecture historique reste datée dans la page.
}

void TestPoste::resumeSondeSansGarderLesSecretsDePage()
{
    Banc banc;
    auto *sondage = banc.poste.findChild<Sondage *>();
    QVERIFY(sondage);
    sondage->setIntervalle(std::chrono::milliseconds(60));
    banc.poste.setResumeVisible(true);
    QTest::qWait(100);
    QCOMPARE(banc.lectures(), 0); // Pas de session : aucune lecture de l'accueil.
    banc.flux.demarrer();
    QTRY_VERIFY(banc.poste.lue());
    QVERIFY(!banc.poste.pageVisible());
    QVERIFY(!banc.poste.actif());
    QVERIFY(sondage->actif());
    banc.poste.setPageVisible(true);
    QTRY_VERIFY(banc.poste.actif());
    banc.poste.enroler();
    QTRY_VERIFY(!banc.poste.code().isEmpty());
    banc.poste.ouvrirGuide(QStringLiteral("hermes"));
    QVERIFY(!banc.poste.guide().isEmpty());
    banc.poste.setPageVisible(false);
    QTRY_VERIFY(!banc.poste.actif());
    QVERIFY(banc.poste.code().isEmpty());
    QVERIFY(banc.poste.guide().isEmpty());
    QVERIFY(sondage->actif()); // Le résumé conserve sa propre lecture, pas les secrets de page.
    const int avant = banc.lectures();
    QTRY_VERIFY(banc.lectures() > avant);
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/enrolement")), 1);
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/releve")), 0);
    banc.poste.setResumeVisible(false);
    QTRY_VERIFY(!sondage->actif());
    int lecturesArretees = banc.lectures();
    QTest::qWait(180);
    QCOMPARE(banc.lectures(), lecturesArretees);
    banc.poste.setResumeVisible(true);
    QTRY_VERIFY(banc.lectures() > lecturesArretees);
    banc.flux.setFenetreActive(false);
    QVERIFY(!sondage->actif());
    lecturesArretees = banc.lectures();
    QTest::qWait(180);
    QCOMPARE(banc.lectures(), lecturesArretees);
    banc.flux.arreter();
    banc.poste.oublier();
    QVERIFY(!banc.poste.lue());
    QCOMPARE(banc.poste.preparation().value(QStringLiteral("etat")).toString(), QStringLiteral("inconnu"));
    banc.flux.setFenetreActive(true);
    QTest::qWait(180);
    QCOMPARE(banc.lectures(), lecturesArretees);
    QVERIFY(!sondage->actif());
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

    banc.maintenant += 181; // Le suivi local expire ; un nouvel essai devient possible.
    banc.poste.actualiser();
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
        // Forme RÉELLEMENT servie (routage.voies_fermees : objet {voie: raison}, relecture finale de P7, constat
        // desktop-3 : le test passait un tableau, forme jamais servie).
        {QStringLiteral("voies_fermees"), QJsonObject{}},
        {QStringLiteral("carte_en_cours"), false},
    });
    QCOMPARE(executant.value(QStringLiteral("present")).toBool(), true);
    QCOMPARE(executant.value(QStringLiteral("plateforme")).toString(), QStringLiteral("linux"));
    QCOMPARE(executant.value(QStringLiteral("peutExecuter")).toString(), QStringLiteral("Oui"));
    QCOMPARE(executant.value(QStringLiteral("voiesDisponibles")).toString(), QStringLiteral("Codex, Claude Code"));
    QCOMPARE(executant.value(QStringLiteral("voiesFermees")).toString(), QStringLiteral("Aucune"));
    const QVariantMap regimeB = PosteViewModel::construireExecutant(QStringLiteral("annonce"), QJsonObject{
        {QStringLiteral("voies_fermees"), QJsonObject{
            {QStringLiteral("poste-codex"), QStringLiteral("isolement de l'exécutant (régime B) : Bac à sable Linux "
                                                           "refusé par la plateforme (régime B)")}}}});
    QCOMPARE(regimeB.value(QStringLiteral("voiesFermees")).toString(),
             QStringLiteral("Codex : isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la "
                            "plateforme (régime B)"));
    // Forme jamais servie (tableau) ou raison illisible : « Inconnu », jamais une liste devinée.
    QCOMPARE(PosteViewModel::construireExecutant(QStringLiteral("annonce"), QJsonObject{
                 {QStringLiteral("voies_fermees"), QJsonArray{}}}).value(QStringLiteral("voiesFermees")).toString(),
             QStringLiteral("Inconnu"));
    QCOMPARE(PosteViewModel::construireExecutant(QStringLiteral("annonce"), QJsonObject{
                 {QStringLiteral("voies_fermees"), QJsonObject{{QStringLiteral("poste-codex"), 3}}}})
                 .value(QStringLiteral("voiesFermees")).toString(),
             QStringLiteral("Inconnu"));
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

void TestPoste::depotsMesuresParLExecutant()
{
    // Forme RÉELLE de `executant.depots` (routage.depots_du_poste), fixture partagée avec le greffon et le web.
    const QJsonArray mesures = fixturePartagee(QStringLiteral("fixtures_poste/depots.json")).array();
    QCOMPARE(mesures.size(), 2);
    QJsonObject vue = fixture(QStringLiteral("poste-en-ligne.json"));
    vue.insert(QStringLiteral("executant"), QJsonObject{{QStringLiteral("connu"), true}, {QStringLiteral("depots"), mesures}});
    const QVariantList depots = PosteViewModel::construireDepots(vue);
    QCOMPARE(depots.size(), 2);
    const auto date = [](const char *iso) {
        return QDateTime::fromString(QString::fromLatin1(iso), Qt::ISODate).toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm"));
    };
    const QVariantMap demo = depots.at(0).toMap();
    QCOMPARE(demo.value(QStringLiteral("alias")).toString(), QStringLiteral("demo"));
    QCOMPARE(demo.value(QStringLiteral("visibilite")).toString(), QStringLiteral("Public"));
    QCOMPARE(demo.value(QStringLiteral("visibiliteCle")).toString(), QStringLiteral("pending"));
    QCOMPARE(demo.value(QStringLiteral("lecture")).toString(), QStringLiteral("Réussie"));
    QCOMPARE(demo.value(QStringLiteral("verifieLe")).toString(), date("2026-10-02T15:40:42Z"));
    // Raison du greffon telle quelle ; Claude ouverte (D84).
    const QString raison = mesures.at(0).toObject().value(QStringLiteral("voies_fermees")).toObject()
                               .value(QStringLiteral("poste-codex")).toString();
    QVERIFY(raison.contains(QStringLiteral("non prouvé privé")));
    QCOMPARE(demo.value(QStringLiteral("voies")).toString(),
             QStringLiteral("Codex : Fermée — %1\nClaude Code : Ouverte").arg(raison));
    const QVariantMap jetable = depots.at(1).toMap();
    QCOMPARE(jetable.value(QStringLiteral("alias")).toString(), QStringLiteral("jetable"));
    QCOMPARE(jetable.value(QStringLiteral("visibilite")).toString(), QStringLiteral("Privé"));
    QCOMPARE(jetable.value(QStringLiteral("visibiliteCle")).toString(), QStringLiteral("succeeded"));
    QCOMPARE(jetable.value(QStringLiteral("voies")).toString(), QStringLiteral("Codex : Ouverte\nClaude Code : Ouverte"));

    // Jamais mesurée (null partout) : dit tel quel, jamais « Privé » deviné ; codes inconnus montrés bruts.
    const QVariantList autres = PosteViewModel::construireDepots(QJsonObject{{QStringLiteral("executant"), QJsonObject{
        {QStringLiteral("depots"), QJsonArray{
            QJsonObject{{QStringLiteral("alias"), QStringLiteral("neuf")}, {QStringLiteral("visibilite"), QJsonValue::Null},
                        {QStringLiteral("lecture"), QJsonValue::Null}, {QStringLiteral("verifie_le"), QJsonValue::Null},
                        {QStringLiteral("voies_fermees"), QJsonObject{{QStringLiteral("poste-codex"), QStringLiteral("non mesuré")}}}},
            QJsonObject{{QStringLiteral("alias"), QStringLiteral("bizarre")}, {QStringLiteral("visibilite"), QStringLiteral("pigeon")},
                        {QStringLiteral("lecture"), QStringLiteral("refusee")},
                        {QStringLiteral("voies_fermees"), QJsonObject{{QStringLiteral("poste-codex"), 3}}}},
            QJsonObject{{QStringLiteral("alias"), QStringLiteral("inconnu")}, {QStringLiteral("visibilite"), QStringLiteral("inconnue")},
                        {QStringLiteral("lecture"), QStringLiteral("inconnue")}},
        }}}}});
    QCOMPARE(autres.size(), 3);
    const QVariantMap neuf = autres.at(0).toMap();
    QCOMPARE(neuf.value(QStringLiteral("visibilite")).toString(), QStringLiteral("Jamais mesurée par l'exécutant (Codex fermé)"));
    QCOMPARE(neuf.value(QStringLiteral("visibiliteCle")).toString(), QStringLiteral("degraded"));
    QCOMPARE(neuf.value(QStringLiteral("lecture")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(neuf.value(QStringLiteral("verifieLe")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(neuf.value(QStringLiteral("voies")).toString(), QStringLiteral("Codex : Fermée — non mesuré\nClaude Code : Ouverte"));
    const QVariantMap bizarre = autres.at(1).toMap();
    QCOMPARE(bizarre.value(QStringLiteral("visibilite")).toString(), QStringLiteral("pigeon"));
    QCOMPARE(bizarre.value(QStringLiteral("visibiliteCle")).toString(), QStringLiteral("unknown"));
    QCOMPARE(bizarre.value(QStringLiteral("lecture")).toString(), QStringLiteral("Refusée"));
    // Raison illisible : la voie reste dite fermée, la raison « Inconnu ».
    QCOMPARE(bizarre.value(QStringLiteral("voies")).toString(), QStringLiteral("Codex : Fermée — Inconnu\nClaude Code : Ouverte"));
    const QVariantMap inconnu = autres.at(2).toMap();
    QCOMPARE(inconnu.value(QStringLiteral("visibilite")).toString(), QStringLiteral("Inconnue (Codex fermé)"));
    QCOMPARE(inconnu.value(QStringLiteral("lecture")).toString(), QStringLiteral("Inconnue"));
    // Sans `voies_fermees` : « Inconnu », jamais déduites par la station.
    QCOMPARE(inconnu.value(QStringLiteral("voies")).toString(), QStringLiteral("Inconnu"));

    // Exécutant sans `depots` (avant P7, ou `connu: false`) : la liste publiée dans l'inventaire, jamais mesurée,
    // voies « Inconnu ».
    const QVariantList repli = PosteViewModel::construireDepots(fixture(QStringLiteral("poste-en-ligne.json")));
    QCOMPARE(repli.size(), 1);
    QCOMPARE(repli.at(0).toMap().value(QStringLiteral("alias")).toString(), QStringLiteral("jetable"));
    QCOMPARE(repli.at(0).toMap().value(QStringLiteral("visibilite")).toString(), QStringLiteral("Jamais mesurée par l'exécutant (Codex fermé)"));
    QCOMPARE(repli.at(0).toMap().value(QStringLiteral("voies")).toString(), QStringLiteral("Inconnu"));
    QVERIFY(PosteViewModel::construireDepots(fixture(QStringLiteral("poste-non-configure.json"))).isEmpty());

    // Page lue : la propriété exposée à QML suit la réponse du greffon.
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    QCOMPARE(banc.poste.depots().size(), 1);
    banc.vue = vue;
    banc.relire();
    QCOMPARE(banc.poste.depots().size(), 2);
    QCOMPARE(banc.poste.property("depots").toList().at(0).toMap().value(QStringLiteral("alias")).toString(), QStringLiteral("demo"));
}

void TestPoste::assistantsSeparentLaMachineEtLesComptes()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-assistants-railway.json"));
    QCOMPARE(banc.poste.assistantMachine().value(QStringLiteral("type")).toString(), QStringLiteral("Exécutant Railway"));
    QCOMPARE(banc.poste.assistantMachine().value(QStringLiteral("plateforme")).toString(), QStringLiteral("linux"));
    QCOMPARE(banc.poste.assistants().size(), 2);
    QCOMPARE(banc.poste.assistants().at(0).toMap().value(QStringLiteral("cle")).toString(), QStringLiteral("pending"));
    QCOMPARE(banc.poste.assistants().at(0).toMap().value(QStringLiteral("offre")).toString(), QStringLiteral("Inconnu"));
    QVERIFY(banc.poste.assistants().at(1).toMap().value(QStringLiteral("detail")).toString().contains(QStringLiteral("pas une garantie")));

    // Un ancien inventaire d'une autre machine ne fournit ni compte, ni plateforme, ni état actuel.
    QJsonObject ancien = banc.vue.value(QStringLiteral("inventaire")).toObject();
    ancien.insert(QStringLiteral("machine_id"), QStringLiteral("ancienne-machine"));
    banc.vue.insert(QStringLiteral("inventaire"), ancien);
    banc.relire();
    QCOMPARE(banc.poste.assistants().at(0).toMap().value(QStringLiteral("etat")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(banc.poste.assistantMachine().value(QStringLiteral("releve")).toString(), QStringLiteral("Inconnu"));
    QVERIFY(banc.poste.assistantMachine().value(QStringLiteral("compte")).toString().isEmpty());

    banc.vue = fixture(QStringLiteral("poste-non-configure.json"));
    banc.relire();
    QVERIFY(!banc.poste.assistantMachine().value(QStringLiteral("guideDisponible")).toBool());
    banc.poste.ouvrirGuide(QStringLiteral("codex"));
    QVERIFY(banc.poste.guide().isEmpty());
    banc.poste.relever();
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/releve")), 0);
}

void TestPoste::guidesCopientSeulementDesCommandesConnues()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    banc.poste.ouvrirGuide(QStringLiteral("codex"));
    const QVariantList windows = banc.poste.guide().value(QStringLiteral("etapes")).toList();
    for (const QVariant &etape : windows) {
        QVERIFY(!etape.toMap().value(QStringLiteral("texte")).toString().contains(QStringLiteral("railway"), Qt::CaseInsensitive));
    }
    QCOMPARE(windows.at(0).toMap().value(QStringLiteral("commande")).toString(),
             QStringLiteral("runas /user:acp-poste \"powershell -NoProfile\""));
    banc.poste.copierEtape(1);
    QCOMPARE(banc.copies, QStringList{QStringLiteral("& \"$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd\" connexion codex")});
    banc.poste.copierEtape(-1);
    banc.poste.copierEtape(100);
    QCOMPARE(banc.copies.size(), 1);
    banc.poste.ouvrirGuide(QStringLiteral("claude"));
    QCOMPARE(banc.poste.guide().value(QStringLiteral("etapes")).toList().first().toMap()
                 .value(QStringLiteral("commande")).toString(), QStringLiteral("claude setup-token"));
    for (const QVariant &etape : banc.poste.guide().value(QStringLiteral("etapes")).toList()) {
        QVERIFY(!etape.toMap().value(QStringLiteral("texte")).toString().contains(QStringLiteral("railway"), Qt::CaseInsensitive));
    }

    banc.vue = fixture(QStringLiteral("poste-assistants-railway.json"));
    banc.relire();
    QVERIFY(banc.poste.guide().isEmpty());
    banc.poste.ouvrirGuide(QStringLiteral("codex"));
    QStringList commandes;
    const QVariantList railway = banc.poste.guide().value(QStringLiteral("etapes")).toList();
    const QVariantMap cloture = railway.last().toMap();
    QCOMPARE(cloture.value(QStringLiteral("titre")).toString(), QStringLiteral("Clore l'accès Railway"));
    const QString instructions = cloture.value(QStringLiteral("texte")).toString();
    QVERIFY(instructions.contains(QStringLiteral("railway ssh keys remove --2fa-code <code>")));
    QVERIFY(instructions.contains(QStringLiteral("railway ssh keys est vide")));
    QVERIFY(instructions.contains(QStringLiteral("railway logout")));
    QVERIFY(cloture.value(QStringLiteral("commande")).toString().isEmpty());
    const auto copiesAvantCloture = banc.copies.size();
    banc.poste.copierEtape(static_cast<int>(railway.size()) - 1);
    QCOMPARE(banc.copies.size(), copiesAvantCloture);
    for (const QVariant &etape : railway) {
        const QString commande = etape.toMap().value(QStringLiteral("commande")).toString();
        if (!commande.isEmpty()) {
            commandes.append(commande);
        }
    }
    QCOMPARE(commandes, (QStringList{QStringLiteral("railway ssh -i \"<chemin-cle-SSH>\" --service executant"), QStringLiteral("acp-poste pause"),
                                     QStringLiteral("acp-poste connexion codex"), QStringLiteral("acp-poste reprise"),
                                     QStringLiteral("acp-poste diagnostic")}));
    QVERIFY(banc.poste.guide().value(QStringLiteral("etapes")).toList().first().toMap()
                .value(QStringLiteral("aCompleter")).toBool());
    banc.poste.copierEtape(0);
    QCOMPARE(banc.copies.last(), commandes.first());
    QVERIFY(banc.poste.copieGuide().contains(QStringLiteral("complétez")));
    banc.poste.ouvrirGuide(QStringLiteral("claude"));
    QCOMPARE(banc.poste.guide().value(QStringLiteral("etapes")).toList().last().toMap(), cloture);
    banc.poste.ouvrirGuide(QStringLiteral("hermes"));
    for (const QVariant &etape : banc.poste.guide().value(QStringLiteral("etapes")).toList()) {
        QVERIFY(etape.toMap().value(QStringLiteral("commande")).toString().isEmpty());
    }
    // Un hôte Linux non identifié comme Railway ne reçoit aucun geste de compte Railway.
    QJsonObject machine = banc.vue.value(QStringLiteral("machine")).toObject();
    QJsonObject identite = machine.value(QStringLiteral("machine")).toObject();
    identite.remove(QStringLiteral("hote"));
    machine.insert(QStringLiteral("machine"), identite);
    banc.vue.insert(QStringLiteral("machine"), machine);
    QJsonObject executant = banc.vue.value(QStringLiteral("executant")).toObject();
    executant.remove(QStringLiteral("hote"));
    banc.vue.insert(QStringLiteral("executant"), executant);
    banc.relire();
    for (const QString &fournisseur : {QStringLiteral("codex"), QStringLiteral("claude")}) {
        banc.poste.ouvrirGuide(fournisseur);
        const QVariantList horsRailway = banc.poste.guide().value(QStringLiteral("etapes")).toList();
        QVERIFY(!horsRailway.isEmpty());
        for (const QVariant &etape : horsRailway) {
            QVERIFY(!etape.toMap().value(QStringLiteral("texte")).toString().contains(QStringLiteral("railway"), Qt::CaseInsensitive));
            QVERIFY(!etape.toMap().value(QStringLiteral("commande")).toString().contains(QStringLiteral("railway"), Qt::CaseInsensitive));
        }
    }
    banc.poste.ouvrirGuide(QStringLiteral("codex; commande-arbitraire"));
    QVERIFY(banc.poste.guide().isEmpty());
    banc.poste.ouvrirGuide(QStringLiteral("codex"));
    banc.poste.setPageVisible(false);
    QVERIFY(banc.poste.guide().isEmpty());
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/releve")), 0);
}

namespace {
QJsonObject branchePrete()
{
    return {{QStringLiteral("projet"), QStringLiteral("p_0123456789ab")},
            {QStringLiteral("projet_titre"), QStringLiteral("Un projet réel")},
            {QStringLiteral("depot"), QStringLiteral("jetable")},
            {QStringLiteral("branche"), QStringLiteral("hermes/projet-demo")},
            {QStringLiteral("tete"), QString(40, QLatin1Char('a'))},
            {QStringLiteral("termine_le"), 1790451600},
            {QStringLiteral("commande"), QStringLiteral("commande arbitraire qui ne doit pas être copiée")}};
}
void poserBranches(QJsonObject &vue, const QJsonArray &branches)
{
    QJsonObject executant = vue.value(QStringLiteral("executant")).toObject();
    executant.insert(QStringLiteral("branches_pretes"), branches);
    vue.insert(QStringLiteral("executant"), executant);
}
} // namespace

void TestPoste::resultatsRefusentDesIdentifiantsEtCommandesArbitraires()
{
    const QJsonObject branche = branchePrete();
    QJsonObject vue;
    poserBranches(vue, QJsonArray{branche});
    const QVariantList valides = PosteViewModel::construireResultats(vue);
    QCOMPARE(valides.size(), 1);
    QVERIFY(!valides.first().toMap().contains(QStringLiteral("commande")));
    for (const QString &cle : {QStringLiteral("projet"), QStringLiteral("depot"), QStringLiteral("branche"), QStringLiteral("tete")}) {
        QJsonObject mauvaise = branche;
        mauvaise.insert(cle, branche.value(cle).toString() + QStringLiteral("; commande"));
        poserBranches(vue, QJsonArray{mauvaise});
        QVERIFY(PosteViewModel::construireResultats(vue).isEmpty());
        mauvaise.insert(cle, branche.value(cle).toString() + QStringLiteral("\n"));
        poserBranches(vue, QJsonArray{mauvaise});
        QVERIFY(PosteViewModel::construireResultats(vue).isEmpty());
    }
    QJsonArray nombreuses;
    for (int i = 0; i < 25; ++i) nombreuses.append(branche);
    poserBranches(vue, nombreuses);
    QCOMPARE(PosteViewModel::construireResultats(vue).size(), 20);
}

void TestPoste::resultatsGardentMetadonneesSansGuideLocal()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-assistants-railway.json"));
    QJsonObject branche = branchePrete();
    poserBranches(banc.vue, QJsonArray{branche});
    banc.relire();
    QCOMPARE(banc.poste.resultats().size(), 1);
    const QVariantMap resultat = banc.poste.resultats().first().toMap();
    QCOMPARE(resultat.value(QStringLiteral("branche")).toString(), QStringLiteral("hermes/projet-demo"));
    QCOMPARE(resultat.value(QStringLiteral("tete")).toString(), QString(40, QLatin1Char('a')));
    QVERIFY(!resultat.contains(QStringLiteral("commande")));
    QVERIFY(banc.poste.metaObject()->indexOfMethod("ouvrirGuideRecuperation(QString,QString,QString)") < 0);
    QVERIFY(banc.poste.guide().isEmpty());
    banc.poste.copierEtape(0);
    QVERIFY(banc.copies.isEmpty());
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/releve")), 0);
    banc.poste.oublier();
    QVERIFY(banc.poste.resultats().isEmpty());
}

void TestPoste::resultatsDistinguentInconnuVideEtIncomplet()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    QVERIFY(banc.poste.resultatsMessage().contains(QStringLiteral("ne publie pas")));
    poserBranches(banc.vue, {});
    banc.relire();
    QVERIFY(banc.poste.resultatsMessage().contains(QStringLiteral("Aucune branche")));
    poserBranches(banc.vue, QJsonArray{QJsonObject{{QStringLiteral("branche"), QStringLiteral("hermes/projet-demo")}}});
    banc.relire();
    QVERIFY(banc.poste.resultatsMessage().contains(QStringLiteral("incomplètes")));
    QVERIFY(banc.poste.resultats().isEmpty());
    QVERIFY(banc.poste.guide().isEmpty());
}

void TestPoste::verificationAttendUnNouvelInventaireDeLaMemeMachine()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    banc.poste.relever();
    QTRY_COMPARE(banc.poste.verificationEtat(), QStringLiteral("attente"));
    QVERIFY(banc.poste.verificationEnCours());
    banc.poste.relever(); // Pas de doublon pendant le suivi.
    QCOMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/releve")), 1);
    banc.relire();
    QCOMPARE(banc.poste.verificationEtat(), QStringLiteral("attente"));

    // Même date de sonde malgré un nouvel identifiant : aucune observation fraîche.
    QJsonObject inventaire = banc.vue.value(QStringLiteral("inventaire")).toObject();
    inventaire.insert(QStringLiteral("id"), 2);
    banc.vue.insert(QStringLiteral("inventaire"), inventaire);
    banc.relire();
    QCOMPARE(banc.poste.verificationEtat(), QStringLiteral("attente"));
    inventaire.insert(QStringLiteral("releve_le"), 1790451621);
    inventaire.insert(QStringLiteral("machine_id"), QStringLiteral("autre-machine"));
    banc.vue.insert(QStringLiteral("inventaire"), inventaire);
    banc.relire();
    QCOMPARE(banc.poste.verificationEtat(), QStringLiteral("attente"));

    // Un relevé fraîchement reçu peut révéler des comptes absents ou refusés : pas de faux « connecté ».
    inventaire.insert(QStringLiteral("machine_id"), kMachine);
    QJsonObject contenu = inventaire.value(QStringLiteral("contenu")).toObject();
    contenu.insert(QStringLiteral("connexions"), QJsonObject{{QStringLiteral("codex"), QStringLiteral("non_connecte")},
                                                            {QStringLiteral("claude"), QStringLiteral("refuse")}});
    inventaire.insert(QStringLiteral("contenu"), contenu);
    banc.vue.insert(QStringLiteral("inventaire"), inventaire);
    banc.relire();
    QCOMPARE(banc.poste.verificationEtat(), QStringLiteral("recu"));
    QVERIFY(!banc.poste.verificationEnCours());
    QCOMPARE(banc.poste.assistants().at(0).toMap().value(QStringLiteral("etat")).toString(), QStringLiteral("Non connecté"));
    QCOMPARE(banc.poste.assistants().at(1).toMap().value(QStringLiteral("etat")).toString(), QStringLiteral("Refusé"));
}

void TestPoste::verificationDistingueRetardEtReponseIllisible()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    QJsonObject attente = fixture(QStringLiteral("releve-demande.json"));
    attente.insert(QStringLiteral("en_attente_du_poste"), true);
    banc.reponseReleve = ReponseFaux::json(202, attente);
    banc.poste.relever();
    QTRY_COMPARE(banc.poste.verificationEtat(), QStringLiteral("attente"));
    QVERIFY(banc.poste.verificationMessage().contains(QStringLiteral("hors ligne")));
    banc.maintenant += 181;
    banc.poste.actualiser();
    QCOMPARE(banc.poste.verificationEtat(), QStringLiteral("retard"));
    QVERIFY(!banc.poste.verificationEnCours());
    QVERIFY(banc.poste.verificationMessage().contains(QStringLiteral("peut rester en file")));
    banc.reponseReleve = ReponseFaux::json(202, QJsonObject{});
    banc.poste.relever();
    QTRY_COMPARE(banc.poste.verificationEtat(), QStringLiteral("echec"));
    QVERIFY(banc.poste.erreurGeste().contains(QStringLiteral("illisible")));
}

void TestPoste::verificationInterrompueSurChangementDeMachine()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    banc.poste.relever();
    QTRY_COMPARE(banc.poste.verificationEtat(), QStringLiteral("attente"));
    auto enveloppe = banc.vue.value(QStringLiteral("machine")).toObject();
    auto machine = enveloppe.value(QStringLiteral("machine")).toObject();
    machine.insert(QStringLiteral("id"), QStringLiteral("machine-remplacee"));
    enveloppe.insert(QStringLiteral("machine"), machine);
    banc.vue.insert(QStringLiteral("machine"), enveloppe);
    banc.relire();
    QTRY_COMPARE(banc.poste.verificationEtat(), QStringLiteral("interrompue"));
    QVERIFY(!banc.poste.verificationEnCours());
    QCOMPARE(banc.poste.assistants().at(0).toMap().value(QStringLiteral("etat")).toString(), QStringLiteral("Inconnu"));
}

void TestPoste::verificationOublieUneReponseTardive()
{
    Banc banc;
    banc.ouvrirLaPage(QStringLiteral("poste-en-ligne.json"));
    banc.reponseReleve.delaiMs = 250;
    banc.poste.ouvrirGuide(QStringLiteral("codex"));
    banc.poste.relever();
    QTRY_COMPARE(banc.serveur.compter("POST", kP + QStringLiteral("/poste/releve")), 1);
    banc.flux.setFenetreActive(false);
    banc.flux.arreter();
    QCOMPARE(banc.poste.verificationEtat(), QStringLiteral("repos"));
    QVERIFY(banc.poste.guide().isEmpty());
    QTest::qWait(350);
    QCOMPARE(banc.poste.verificationEtat(), QStringLiteral("repos"));
    QVERIFY(!banc.poste.gesteEnCours());
    QVERIFY(banc.poste.messageGeste().isEmpty());
    QVERIFY(banc.poste.verificationMessage().isEmpty());
}
QTEST_MAIN(TestPoste)
#include "tst_poste.moc"
