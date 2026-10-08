// Chaque page de la station se charge hors écran, ALIMENTÉE par le faux Hermes (formes
// relevées sur l'image), sans liaison cassée, sans texte « undefined » ni libellé anglais
// résiduel, avec des boutons nommés et des états vides honnêtes ; puis la racine se charge
// sur l'écran de connexion (aucune session).
//
// La composition est celle du produit (Application) : le test ne fait que pointer son
// transport vers le faux Hermes et déclarer la session ouverte au temps réel. Les singletons
// QML sont enregistrés une fois par processus : un seul cas de test charge toutes les pages.

#include "api/ApiClient.h"
#include "app/Application.h"
#include "auth/SessionHermes.h"
#include "events/EventStreamService.h"
#include "gateway/DemandesAgent.h"
#include "gateway/GatewayClient.h"
#include "models/JsonListModel.h"
#include "services/CompatibiliteHermes.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/AccueilViewModel.h"
#include "viewmodels/DiscussionViewModel.h"
#include "viewmodels/PosteViewModel.h"
#include "viewmodels/ProjetsViewModel.h"
#include "viewmodels/QuestionsViewModel.h"
#include "viewmodels/QuotasViewModel.h"
#include "viewmodels/RoutageViewModel.h"
#include "viewmodels/SauvegardeViewModel.h"

#include <QDateTime>
#include <QJsonArray>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlProperty>
#include <QQuickItem>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QTemporaryDir>
#include <QTest>

#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kId = QStringLiteral("p_367e23fd51b7");

//! Textes qui trahissent une liaison cassée ou un libellé non traduit.
const QStringList kInterdits = {
    QStringLiteral("undefined"), QStringLiteral("NaN"), QStringLiteral("[object Object]"),
    QStringLiteral("Loading"), QStringLiteral("Error"), QStringLiteral("Unknown"),
    QStringLiteral("Cancel"), QStringLiteral("Submit"), QStringLiteral("Retry"), QStringLiteral("Close"),
    // Textes de transport de Qt, en anglais faute de traducteur (constat de relecture P8).
    QStringLiteral("Connection refused"), QStringLiteral("not found"), QStringLiteral("timed out"),
};

void textesVisibles(QQuickItem *item, QStringList &textes, QStringList &boutonsSansNom)
{
    if (!item || !item->isVisible()) {
        return;
    }
    const QString classe = QString::fromLatin1(item->metaObject()->className());
    if (classe.startsWith(QStringLiteral("AcpButton"))) {
        // Nom annoncé aux technologies d'assistance : le libellé, ou la surcharge
        // `Accessible.name` d'un bouton à icône seule.
        const QString nom = QQmlProperty(item, QStringLiteral("Accessible.name"), qmlContext(item)).read().toString();
        if (nom.trimmed().isEmpty()) {
            boutonsSansNom.append(item->objectName());
        }
    }
    const QVariant texte = item->property("text");
    if (texte.isValid() && texte.canConvert<QString>()) {
        textes.append(texte.toString());
    }
    for (QQuickItem *enfant : item->childItems()) {
        textesVisibles(enfant, textes, boutonsSansNom);
    }
}

QString controler(QQuickItem *racine)
{
    QStringList textes;
    QStringList boutons;
    textesVisibles(racine, textes, boutons);
    QStringList fautes;
    for (const QString &texte : std::as_const(textes)) {
        for (const QString &interdit : kInterdits) {
            const QRegularExpression mot(QStringLiteral("\\b%1\\b").arg(QRegularExpression::escape(interdit)));
            if (mot.match(texte).hasMatch()) {
                fautes.append(QStringLiteral("« %1 » dans « %2 »").arg(interdit, texte.left(120)));
            }
        }
    }
    if (!boutons.isEmpty()) {
        fautes.append(QStringLiteral("bouton sans nom : %1").arg(boutons.join(QStringLiteral(", "))));
    }
    return fautes.join(QLatin1Char('\n'));
}

bool contientTexte(QQuickItem *racine, const QString &attendu)
{
    QStringList textes;
    QStringList boutons;
    textesVisibles(racine, textes, boutons);
    for (const QString &texte : std::as_const(textes)) {
        if (texte.contains(attendu)) {
            return true;
        }
    }
    return false;
}

} // namespace

class TestPagesBureau : public QObject
{
    Q_OBJECT

private slots:
    void pagesAlimenteesPuisRacine();
};

void TestPagesBureau::pagesAlimenteesPuisRacine()
{
    FauxHermes serveur;
    serveur.installerAuthentification();
    serveur.activerKanban();
    serveur.activerPasserelle();
    serveur.methodes.insert(QStringLiteral("session.list"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{
            QJsonObject{{QStringLiteral("id"), QStringLiteral("s1")}, {QStringLiteral("title"), QStringLiteral("Plan du site")},
                        {QStringLiteral("preview"), QStringLiteral("Faisons le plan")}, {QStringLiteral("started_at"), 1790300000},
                        {QStringLiteral("message_count"), 2}, {QStringLiteral("source"), QStringLiteral("tui")}}}}};
    });
    serveur.methodes.insert(QStringLiteral("session.resume"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("message_count"), 2},
                           {QStringLiteral("messages"), QJsonArray{
                               QJsonObject{{QStringLiteral("role"), QStringLiteral("user")}, {QStringLiteral("text"), QStringLiteral("Bonjour Hermes")}},
                               QJsonObject{{QStringLiteral("role"), QStringLiteral("assistant")},
                                           {QStringLiteral("text"), QStringLiteral("Bonjour, que puis-je faire ?")}}}},
                           {QStringLiteral("info"), QJsonObject{{QStringLiteral("title"), QStringLiteral("Plan du site")}}},
                           {QStringLiteral("running"), false}};
    });
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    QJsonObject projets = fixture(QStringLiteral("projets.json"));
    serveur.route("GET", kP + QStringLiteral("/projets"), [&projets](const RequeteRecue &) { return ReponseFaux::json(200, projets); });
    serveur.route("GET", kP + QStringLiteral("/projets/") + kId,
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projet-detail.json"))); });
    serveur.route("GET", kP + QStringLiteral("/quotas"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("quotas.json"))); });
    // Description du greffon (forme de b3faac0, sans exécutant) : relue par l'accueil.
    serveur.route("GET", kP + QStringLiteral("/meta"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("meta.json"))); });
    serveur.route("GET", kP + QStringLiteral("/catalogue"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("catalogue-profils.json"))); });
    QJsonObject poste = fixture(QStringLiteral("poste-releve.json"));
    serveur.route("GET", kP + QStringLiteral("/poste"), [&poste](const RequeteRecue &) { return ReponseFaux::json(200, poste); });
    serveur.route("POST", kP + QStringLiteral("/poste/enrolement"), [](const RequeteRecue &) {
        QJsonObject code = fixture(QStringLiteral("code-enrolement.json"));
        code.insert(QStringLiteral("expire_le"), QDateTime::currentSecsSinceEpoch() + 600);
        return ReponseFaux::json(201, code);
    });
    QJsonObject routage = fixture(QStringLiteral("routage.json"));
    serveur.route("GET", kP + QStringLiteral("/routage"), [&routage](const RequeteRecue &) { return ReponseFaux::json(200, routage); });
    // Sauvegarde : lancement, fin, archive servie, suppression (formes de hermes_cli/web_routers).
    const QString archiveDistante = QStringLiteral("/opt/data/backups/hermes-backup-essai.zip");
    serveur.route("POST", QStringLiteral("/api/ops/backup"), [&archiveDistante](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("ok"), true}, {QStringLiteral("pid"), 7},
                                                  {QStringLiteral("name"), QStringLiteral("backup")},
                                                  {QStringLiteral("archive"), archiveDistante}});
    });
    serveur.route("GET", QStringLiteral("/api/actions/backup/status"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("running"), false}, {QStringLiteral("exit_code"), 0},
                                                  {QStringLiteral("lines"), QJsonArray{}}});
    });
    serveur.route("GET", QStringLiteral("/api/ops/backup/download"), [](const RequeteRecue &) {
        ReponseFaux reponse;
        reponse.corps = QByteArray(200 * 1024, 'z');
        return reponse;
    });
    serveur.route("DELETE", QStringLiteral("/api/files"), [](const RequeteRecue &) {
        return ReponseFaux::json(403, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Path outside managed files root")}});
    });
    QJsonObject questions = fixture(QStringLiteral("questions.json"));
    serveur.route("GET", kP + QStringLiteral("/questions"),
                  [&questions](const RequeteRecue &) { return ReponseFaux::json(200, questions); });
    serveur.route("GET", QStringLiteral("/api/sessions"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("sessions.json"))); });
    serveur.route("GET", QStringLiteral("/api/plugins/kanban/board"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("latest_event_id"), 1}, {QStringLiteral("columns"), QJsonArray{}}});
    });

    acp::Application application;
    application.registerQmlTypes();
    auto *client = application.findChild<ApiClient *>();
    auto *flux = application.findChild<EventStreamService *>();
    auto *accueil = application.findChild<AccueilViewModel *>();
    auto *pageProjets = application.findChild<ProjetsViewModel *>();
    auto *pageQuestions = application.findChild<QuestionsViewModel *>();
    auto *pagePoste = application.findChild<PosteViewModel *>();
    auto *pageQuotas = application.findChild<QuotasViewModel *>();
    auto *pageRoutage = application.findChild<RoutageViewModel *>();
    auto *pageSauvegarde = application.findChild<SauvegardeViewModel *>();
    auto *discussion = application.findChild<DiscussionViewModel *>();
    auto *demandes = application.findChild<DemandesAgent *>();
    auto *passerelle = application.findChild<GatewayClient *>();
    QVERIFY(client && flux && accueil && pageProjets && pageQuestions && pagePoste && pageQuotas && pageRoutage && pageSauvegarde && discussion && demandes && passerelle);
    client->setAllowInsecureLoopback(true);
    QVERIFY(!client->setBaseUrl(serveur.url()).isError());
    client->setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    flux->setIntervalleFond(std::chrono::hours(1));
    flux->demarrer();

    QQmlApplicationEngine engine;
    QStringList warnings;
    connect(&engine, &QQmlEngine::warnings, this, [&warnings](const QList<QQmlError> &errors) {
        for (const auto &error : errors) warnings.append(error.toString());
    });
    QQuickWindow window;
    window.resize(1280, 850);
    window.show();

    const auto charger = [&](const QString &module, const QString &nom) -> std::unique_ptr<QObject> {
        warnings.clear();
        QQmlComponent component(&engine);
        component.loadFromModule(module, nom);
        if (!QTest::qWaitFor([&component] { return component.status() != QQmlComponent::Loading; }, 5000)
            || !component.isReady()) {
            qWarning("%s", qPrintable(component.errorString()));
            return nullptr;
        }
        std::unique_ptr<QObject> objet(component.create());
        if (auto *item = qobject_cast<QQuickItem *>(objet.get())) {
            item->setParentItem(window.contentItem());
            item->setSize(QSizeF(1280, 850));
        }
        return objet;
    };
    // Rend les fautes d'une étape (vide si aucune). La vérification se fait dans la fonction de
    // test elle-même (VERIFIER), pour qu'un échec l'interrompe aussitôt.
    const auto examiner = [&](QObject *objet, const QString &etape) -> QString {
        QTest::qWait(80);
        auto *item = qobject_cast<QQuickItem *>(objet);
        if (!item) {
            return etape + QStringLiteral(" : la page n'est pas un élément graphique");
        }
        if (!warnings.isEmpty()) {
            return etape + QStringLiteral(" : ") + warnings.join(QLatin1Char('\n'));
        }
        const QString fautes = controler(item);
        // Captures facultatives pour une relecture visuelle (jamais en CI) : ACP_CAPTURES_DIR.
        const QString captures = qEnvironmentVariable("ACP_CAPTURES_DIR");
        if (!captures.isEmpty()) {
            QString fichier = etape;
            fichier.replace(QRegularExpression(QStringLiteral("[^A-Za-z0-9]+")), QStringLiteral("-"));
            window.grabWindow().save(captures + QLatin1Char('/') + fichier + QStringLiteral(".png"));
        }
        return fautes.isEmpty() ? QString() : etape + QStringLiteral(" : ") + fautes;
    };
#define VERIFIER(objet, etape)                                                                                     \
    do {                                                                                                           \
        const QString fautes_ = examiner(objet, etape);                                                            \
        QVERIFY2(fautes_.isEmpty(), qPrintable(fautes_));                                                          \
    } while (false)

    // --- Accueil alimenté ------------------------------------------------------------------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("HomePage"));
        QVERIFY(page);
        QTRY_VERIFY_WITH_TIMEOUT(accueil->carteProjets().value(QStringLiteral("lisible")).toBool(), 5000);
        QTRY_COMPARE_WITH_TIMEOUT(accueil->sessions()->count(), 2, 5000);
        QTRY_VERIFY_WITH_TIMEOUT(accueil->carteQuotas().value(QStringLiteral("connu")).toBool(), 5000);
        QTRY_VERIFY_WITH_TIMEOUT(application.findChild<CompatibiliteHermes *>()->lecture().startsWith(QStringLiteral("Lu à")), 5000);
        VERIFIER(page.get(), QStringLiteral("Accueil"));
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QVERIFY(contientTexte(item, QStringLiteral("Plan posé : deux recherches.")));
        QVERIFY(contientTexte(item, QStringLiteral("poste-simule")));
        QVERIFY(contientTexte(item, QStringLiteral("Sans titre"))); // session s2 sans titre
    }
    QTRY_VERIFY(!accueil->actif());

    // --- Projets : liste, détail, nouveau, liste vide -------------------------------------------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("ProjectsPage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QTRY_COMPARE_WITH_TIMEOUT(pageProjets->projets()->count(), 2, 5000);
        VERIFIER(page.get(), QStringLiteral("Projets, liste"));
        QVERIFY(contientTexte(item, QStringLiteral("Veille LLM")));

        pageProjets->ouvrirProjet(kId);
        QTRY_VERIFY_WITH_TIMEOUT(pageProjets->detailLu(), 5000);
        VERIFIER(page.get(), QStringLiteral("Projets, détail"));
        QVERIFY(contientTexte(item, QStringLiteral("Écrire outil.py.")));
        // Étape P7 : « Qui répond » se lit « Vous » ; les gestes « Changer qui répond » et « Clore le projet ».
        QVERIFY(contientTexte(item, QStringLiteral("Vous")));
        QVERIFY(contientTexte(item, QStringLiteral("Changer qui répond")));
        QVERIFY(contientTexte(item, QStringLiteral("Clore le projet")));
        QVERIFY(contientTexte(item, QStringLiteral("Quelle version de Python viser ?")));

        pageProjets->afficherNouveau();
        QTRY_VERIFY_WITH_TIMEOUT(pageProjets->formulaire().value(QStringLiteral("pret")).toBool(), 5000);
        VERIFIER(page.get(), QStringLiteral("Projets, nouveau projet"));
        QVERIFY(contientTexte(item, QStringLiteral("Relevé factice")));
        pageProjets->choisirDepot(QStringLiteral("jetable"));
        VERIFIER(page.get(), QStringLiteral("Projets, nouveau projet avec exploration"));
        QVERIFY(contientTexte(item, QStringLiteral("Exploration du dépôt")));

        projets = fixture(QStringLiteral("projets-vide.json"));
        pageProjets->afficherListe();
        pageProjets->actualiser();
        QTRY_COMPARE_WITH_TIMEOUT(pageProjets->projets()->count(), 0, 5000);
        VERIFIER(page.get(), QStringLiteral("Projets, liste vide"));
        QVERIFY(contientTexte(item, QStringLiteral("Aucun projet pour l'instant")));
    }
    QTRY_VERIFY(!pageProjets->actif());

    // --- Questions : questions, triage, bloquées ; puis tout vide -----------------------------------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("QuestionsPage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QTRY_VERIFY_WITH_TIMEOUT(pageQuestions->lue(), 5000);
        VERIFIER(page.get(), QStringLiteral("Questions"));
        QVERIFY(contientTexte(item, QStringLiteral("Quelle version de Python viser ?")));
        QVERIFY(contientTexte(item, QStringLiteral("3 tours planifiés")));
        // Étape P7 : compteurs du greffon, raison d'une carte non relançable, discussions en attente.
        QVERIFY(contientTexte(item, QStringLiteral("À traiter par vous")));
        QVERIFY(contientTexte(item, QStringLiteral("Relance impossible : Carte non émise par ACP : ACP ne la relance pas.")));
        QVERIFY(contientTexte(item, QStringLiteral("Requêtes ouvertes dans le tableau de bord : 0")));

        questions = QJsonObject{{QStringLiteral("questions"), QJsonArray{}}, {QStringLiteral("triage"), QJsonArray{}},
                                {QStringLiteral("bloquees"), QJsonArray{}}, {QStringLiteral("tableaux_illisibles"), QJsonArray{}}};
        pageQuestions->actualiser();
        QTRY_COMPARE_WITH_TIMEOUT(pageQuestions->questions()->count(), 0, 5000);
        VERIFIER(page.get(), QStringLiteral("Questions vides"));
        QVERIFY(contientTexte(item, QStringLiteral("Aucune question en attente.")));
        QVERIFY(contientTexte(item, QStringLiteral("Aucune carte en triage.")));
    }
    QTRY_VERIFY(!pageQuestions->actif());

    // --- Poste : en ligne avec son inventaire ; puis non configuré, avec un code d'enrôlement ------
    {
        poste = fixture(QStringLiteral("poste-en-ligne.json"));
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("PostePage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QTRY_VERIFY_WITH_TIMEOUT(pagePoste->lue() && pagePoste->peutRelever(), 5000);
        VERIFIER(page.get(), QStringLiteral("Poste en ligne"));
        QVERIFY(contientTexte(item, QStringLiteral("Compte dédié acp-poste")));
        // /v1/meta lu par l'accueil, sans `machine.executant` (Hermes sans l'étape P6).
        QVERIFY(contientTexte(item, QStringLiteral("Exécutant : non disponible sur ce serveur (étape P6).")));
        QVERIFY(contientTexte(item, QStringLiteral("Aucun ordre en attente.")));

        poste = fixture(QStringLiteral("poste-non-configure.json"));
        pagePoste->actualiser();
        QTRY_VERIFY_WITH_TIMEOUT(pagePoste->peutEnroler(), 5000);
        pagePoste->enroler();
        QTRY_COMPARE_WITH_TIMEOUT(pagePoste->code(), QStringLiteral("acpe_CODE-DE-TEST"), 5000);
        VERIFIER(page.get(), QStringLiteral("Poste non configuré, code d'enrôlement"));
        QVERIFY(contientTexte(item, QStringLiteral("acpe_CODE-DE-TEST")));
        QVERIFY(contientTexte(item, QStringLiteral("Aucun inventaire reçu.")));
    }
    // Page quittée : le code d'enrôlement a quitté la mémoire de la station.
    QTRY_VERIFY(!pagePoste->actif());
    QCOMPARE(pagePoste->code(), QString());

    // --- Quotas : compteurs et fenêtres relevés ------------------------------------------------------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("QuotasPage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QTRY_VERIFY_WITH_TIMEOUT(pageQuotas->lue(), 5000);
        VERIFIER(page.get(), QStringLiteral("Quotas"));
        QVERIFY(contientTexte(item, QStringLiteral("Fenêtre primary · 300 min")));
        QVERIFY(contientTexte(item, QStringLiteral("Aucun compteur relevé.")));
    }
    QTRY_VERIFY(!pageQuotas->actif());

    // --- Routage : table, brouillon d'une suggestion, puis liste de secours à accepter ---------------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("RoutagePage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QTRY_VERIFY_WITH_TIMEOUT(pageRoutage->lue(), 5000);
        VERIFIER(page.get(), QStringLiteral("Routage"));
        QVERIFY(contientTexte(item, QStringLiteral("Exploration du dépôt")));
        QVERIFY(contientTexte(item, QStringLiteral("Aucune surcharge active.")));
        pageRoutage->appliquerSuggestion(QStringLiteral("exploration"));
        VERIFIER(page.get(), QStringLiteral("Routage, brouillon"));
        QVERIFY(contientTexte(item, QStringLiteral("Brouillon modifié")));
        QVERIFY(contientTexte(item, QStringLiteral("À valider")));

        routage = fixture(QStringLiteral("routage-secours.json"));
        pageRoutage->actualiser();
        QTRY_VERIFY_WITH_TIMEOUT(pageRoutage->listes()->itemAt(0).value(QStringLiteral("peutAccepter")).toBool(), 5000);
        VERIFIER(page.get(), QStringLiteral("Routage, liste de secours"));
        QVERIFY(contientTexte(item, QStringLiteral("Accepter ce relevé comme celui de mon compte")));
    }
    QTRY_VERIFY(!pageRoutage->actif());

    // --- Sauvegarde : au repos, puis un export réel (DPAPI) dont la suppression est refusée --------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("SauvegardePage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        VERIFIER(page.get(), QStringLiteral("Sauvegarde au repos"));
        QVERIFY(contientTexte(item, QStringLiteral("Aucun export en cours")));
        QTemporaryDir dossier;
        pageSauvegarde->setIntervalleSuivi(std::chrono::milliseconds(20));
        pageSauvegarde->exporter(dossier.filePath(QStringLiteral("essai.acpb")));
        QTRY_VERIFY_WITH_TIMEOUT(pageSauvegarde->phase() == SauvegardeViewModel::Phase::Termine
                                     || pageSauvegarde->phase() == SauvegardeViewModel::Phase::Echec,
                                 10000);
        QCOMPARE(pageSauvegarde->phase(), SauvegardeViewModel::Phase::Termine);
        VERIFIER(page.get(), QStringLiteral("Sauvegarde exportée, archive restante"));
        QVERIFY(contientTexte(item, QStringLiteral("Export terminé")));
        QVERIFY(contientTexte(item, archiveDistante));
    }

    // --- Discussion : sessions, transcription, puis une demande d'autorisation de l'agent --------
    {
        passerelle->ouvrir();
        QTRY_COMPARE_WITH_TIMEOUT(passerelle->etat(), GatewayClient::Etat::Pret, 10000);
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("DiscussionPage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QTRY_VERIFY_WITH_TIMEOUT(discussion->sessionsLues(), 5000);
        VERIFIER(page.get(), QStringLiteral("Discussion, liste"));
        QVERIFY(contientTexte(item, QStringLiteral("Choisissez une discussion")));
        discussion->ouvrir(QStringLiteral("s1"));
        QTRY_COMPARE_WITH_TIMEOUT(discussion->transcription()->count(), 2, 5000);
        VERIFIER(page.get(), QStringLiteral("Discussion, session ouverte"));
        QVERIFY(contientTexte(item, QStringLiteral("Bonjour, que puis-je faire ?")));
        serveur.envoyer(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")}, {QStringLiteral("id"), QStringLiteral("srq-1")},
                                    {QStringLiteral("method"), QStringLiteral("approval")},
                                    {QStringLiteral("params"), QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")},
                                                                           {QStringLiteral("request_id"), QStringLiteral("r1")},
                                                                           {QStringLiteral("command"), QStringLiteral("rm -rf /tmp/essai")},
                                                                           {QStringLiteral("description"), QStringLiteral("Suppression")},
                                                                           {QStringLiteral("choices"), QJsonArray{QStringLiteral("once"), QStringLiteral("deny")}}}}});
        QTRY_COMPARE_WITH_TIMEOUT(demandes->nombre(), 1, 5000);
        VERIFIER(page.get(), QStringLiteral("Discussion, demande d'autorisation"));
        QVERIFY(contientTexte(item, QStringLiteral("rm -rf /tmp/essai")));
    }
    {
        // La même demande, dans la section « Demandes de vos discussions » des Questions.
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("QuestionsPage"));
        QVERIFY(page);
        QTRY_VERIFY_WITH_TIMEOUT(pageQuestions->lue(), 5000);
        VERIFIER(page.get(), QStringLiteral("Questions avec demande de l'agent"));
        QVERIFY(contientTexte(qobject_cast<QQuickItem *>(page.get()), QStringLiteral("Suppression")));
    }

    // --- Pages sans données de Hermes -------------------------------------------------------------
    for (const QString &nom : {QStringLiteral("FirstRunPage"), QStringLiteral("DiagnosticsPage"), QStringLiteral("SettingsPage")}) {
        auto page = charger(QStringLiteral("Acp.Pages"), nom);
        QVERIFY2(page, qPrintable(nom));
        VERIFIER(page.get(), nom);
    }
    {
        auto coquille = charger(QStringLiteral("Acp.Station"), QStringLiteral("ShellRoot"));
        QVERIFY(coquille);
        VERIFIER(coquille.get(), QStringLiteral("Coquille"));
    }
    window.hide();

    // --- Aucun secret exposé à QML ------------------------------------------------------------------
    // Après le parcours complet (porteur, tickets de la passerelle et du kanban émis, code
    // d'enrôlement rendu), aucune propriété d'aucun objet de l'application ne contient le jeton,
    // un ticket ni le code.
    {
        QList<QObject *> objets = application.findChildren<QObject *>();
        objets.prepend(&application);
        int lues = 0;
        for (QObject *objet : std::as_const(objets)) {
            const QMetaObject *meta = objet->metaObject();
            for (int index = 0; index < meta->propertyCount(); ++index) {
                const QMetaProperty propriete = meta->property(index);
                const QVariant valeur = propriete.read(objet);
                if (!valeur.canConvert<QString>()) {
                    continue;
                }
                ++lues;
                const QString texte = valeur.toString();
                // Ni le porteur, ni un ticket, ni le code d'enrôlement (page Poste quittée).
                QVERIFY2(!texte.contains(QStringLiteral("jeton-a")) && !texte.contains(QStringLiteral("ticket-faux-"))
                             && !texte.contains(QStringLiteral("acpe_CODE-DE-TEST")),
                         qPrintable(QStringLiteral("%1.%2").arg(QString::fromLatin1(meta->className()),
                                                                QString::fromLatin1(propriete.name()))));
            }
        }
        QVERIFY(lues > 100); // le contrôle a bien parcouru les objets de la station
    }

    // --- Session perdue : passerelle fermée, temps réel arrêté, discussion oubliée -----------------
    {
        auto *session = application.findChild<SessionHermes *>();
        QVERIFY(session);
        QCOMPARE(discussion->sessionVivante(), QStringLiteral("rt-s1"));
        const auto fermeturesAvant = serveur.tramesDeMethode(QStringLiteral("session.close")).size();
        QVERIFY(QMetaObject::invokeMethod(session, "sessionPerdue", Q_ARG(QString, QStringLiteral("essai"))));
        QCOMPARE(passerelle->etat(), GatewayClient::Etat::Deconnecte);
        QVERIFY(!flux->sessionOuverte());
        QCOMPARE(discussion->sessionVivante(), QString());
        QCOMPARE(discussion->transcription()->count(), 0);
        QCOMPARE(demandes->nombre(), 0);
        QTest::qWait(100);
        QCOMPARE(serveur.tramesDeMethode(QStringLiteral("session.close")).size(), fermeturesAvant);
    }

    // --- La racine : fenêtre, écran de connexion (aucune session) et palette -----------------------
    warnings.clear();
    QVERIFY(application.load(&engine));
    QTest::qWait(100);
    QVERIFY2(warnings.isEmpty(), qPrintable(QStringLiteral("App : ") + warnings.join(QLatin1Char('\n'))));
    auto *racine = qobject_cast<QQuickWindow *>(engine.rootObjects().constLast());
    QVERIFY(racine);
    QVERIFY(racine->findChild<QObject *>(QStringLiteral("connexion-se-connecter")));
    racine->close();
#undef VERIFIER
}

QTEST_MAIN(TestPagesBureau)
#include "tst_pages_bureau.moc"
