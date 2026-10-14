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
#include "navigation/NavigationModel.h"
#include "system/SystemAppearance.h"
#include "services/CompatibiliteHermes.h"
#include "support/FauxHermes.h"
#include "support/FauxComptes.h"
#include "viewmodels/ComptesViewModel.h"
#include "viewmodels/JournalExecutionViewModel.h"
#include "support/Fixtures.h"
#include "viewmodels/AccueilViewModel.h"
#include "viewmodels/DiscussionViewModel.h"
#include "viewmodels/ObsidianViewModel.h"
#include "support/FauxCoffre.h"
#include "viewmodels/CatalogueViewModel.h"
#include "viewmodels/PosteViewModel.h"
#include "viewmodels/ProjetsViewModel.h"
#include "viewmodels/QuestionsViewModel.h"
#include "viewmodels/QuotasViewModel.h"
#include "viewmodels/RoutageViewModel.h"
#include "viewmodels/SauvegardeViewModel.h"

#include <QDateTime>
#include <QDir>
#include <QFont>
#include <QRawFont>
#include <QSettings>
#include <QUuid>
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

#include <algorithm>
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

QQuickItem *parNom(QQuickItem *item, const QString &nom)
{
    if (!item) return nullptr;
    if (item->objectName() == nom) return item;
    for (QQuickItem *enfant : item->childItems()) {
        if (auto *trouve = parNom(enfant, nom)) return trouve;
    }
    return nullptr;
}

bool cliquer(QQuickWindow &fenetre, QQuickItem *racine, const QString &nom)
{
    auto *item = parNom(racine, nom);
    if (!item || !item->isVisible() || !item->isEnabled()) return false;
    for (auto *parent = item->parentItem(); parent; parent = parent->parentItem()) {
        if (parent->inherits("QQuickFlickable")) {
            auto *contenu = parent->property("contentItem").value<QQuickItem *>();
            const double haut = item->mapToItem(contenu, QPointF(0, 0)).y();
            const double maximum = std::max(0.0, parent->property("contentHeight").toDouble() - parent->height());
            const double visible = parent->property("contentY").toDouble();
            if (haut < visible || haut + item->height() > visible + parent->height())
                parent->setProperty("contentY", std::clamp(haut - 40.0, 0.0, maximum));
            break;
        }
    }
    const QPointF centre = item->mapToScene(QPointF(item->width() / 2, item->height() / 2));
    if (!QRectF(QPointF(0, 0), fenetre.size()).contains(centre)) return false;
    QTest::mouseClick(&fenetre, Qt::LeftButton, Qt::NoModifier, centre.toPoint());
    QTest::qWait(50);
    return true;
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
    const auto fonte=QRawFont::fromFont(QFont(QStringLiteral("Segoe UI")));
    QVERIFY2(fonte.isValid() && fonte.supportsCharacter(uint('A')) && fonte.supportsCharacter(uint(0x00e9)),
             "Polices du rendu indisponibles : les captures produiraient des carrés au lieu du texte français.");
    FauxHermes serveur;
    FauxCoffre coffreFactice;
    coffreFactice.installer(serveur);
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
                                           {QStringLiteral("text"), QStringLiteral("Bonjour, que puis-je faire ?\n\n## Proposition\n- Examiner le projet\n- Vérifier les changements\n\n```python\ndef saluer():\n    return \"Bonjour ACP\"\n```\n\nLe résultat restera accompagné de ses preuves.")}}}},
                           {QStringLiteral("info"), QJsonObject{{QStringLiteral("title"), QStringLiteral("Plan du site")},
                               {QStringLiteral("model"), QStringLiteral("modele-fixture")},
                               {QStringLiteral("provider"), QStringLiteral("fournisseur-fixture")},
                               {QStringLiteral("usage"), QJsonObject{{QStringLiteral("context_percent"), 24},
                                   {QStringLiteral("context_estimated"), true}}}}},
                           {QStringLiteral("running"), false}};
    });
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    serveur.route("GET", kP + QStringLiteral("/comptes"), [](const RequeteRecue &) { return ReponseFaux::json(200, comptesTest(connexionTest())); });
    serveur.route("GET", kP + QStringLiteral("/comptes/connexions/") + connexionTestId(), [](const RequeteRecue &) { return ReponseFaux::json(200, connexionTest()); });
    QJsonObject projets = fixture(QStringLiteral("projets.json"));
    serveur.route("GET", kP + QStringLiteral("/projets/") + kId + QStringLiteral("/evenements"), [](const RequeteRecue &r) {
        const bool premier=r.requete.queryItemValue(QStringLiteral("apres"))==QLatin1String("0");
        const QJsonObject evenement{{QStringLiteral("id"),QStringLiteral("journal-test-1")},{QStringLiteral("curseur"),1},
            {QStringLiteral("projet_id"),kId},{QStringLiteral("quand"),QStringLiteral("2026-10-14T10:00:00Z")},
            {QStringLiteral("agent"),QStringLiteral("Développeur simulé")},{QStringLiteral("moteur"),QStringLiteral("codex")},
            {QStringLiteral("genre"),QStringLiteral("outil")},{QStringLiteral("outil"),QStringLiteral("lecture_fichier")},
            {QStringLiteral("carte"),QStringLiteral("Implémentation simulée")},{QStringLiteral("texte"),QStringLiteral("Données simulées pour vérifier le journal natif. Aucun agent personnel n’a été exécuté.")},
            {QStringLiteral("session_native"),QStringLiteral("session-simulee")},{QStringLiteral("run_id"),42}};
        return ReponseFaux::json(200,QJsonObject{{QStringLiteral("projet_id"),kId},{QStringLiteral("evenements"),premier?QJsonArray{evenement}:QJsonArray{}},
            {QStringLiteral("prochain_curseur"),1},{QStringLiteral("encore"),false}});
    });
    serveur.route("GET", kP + QStringLiteral("/projets"), [&projets](const RequeteRecue &) { return ReponseFaux::json(200, projets); });
    serveur.route("GET", kP + QStringLiteral("/projets/") + kId,
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projet-detail.json"))); });
    serveur.route("GET", kP + QStringLiteral("/quotas"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("quotas.json"))); });
    // Description du greffon (forme de b3faac0, sans exécutant) : relue par l'accueil.
    serveur.route("GET", kP + QStringLiteral("/meta"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("meta.json"))); });
    serveur.route("GET", kP + QStringLiteral("/catalogue"),
                  [](const RequeteRecue &) {
                      auto catalogue = fixture(QStringLiteral("catalogue-profils.json"));
                      catalogue.insert(QStringLiteral("skills"), QJsonArray{});
                      catalogue.insert(QStringLiteral("mcp"), QJsonArray{});
                      catalogue.insert(QStringLiteral("sources"), QJsonObject{});
                      return ReponseFaux::json(200, catalogue);
                  });
    // Route NATIVE de Hermes : la tâche du bilan quotidien, active (carte « Bilan quotidien » de l'Accueil).
    serveur.route("GET", QStringLiteral("/api/cron/jobs"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonArray{QJsonObject{
            {QStringLiteral("id"), QStringLiteral("j1")}, {QStringLiteral("script"), QStringLiteral("acp-bilan.py")},
            {QStringLiteral("no_agent"), true}, {QStringLiteral("enabled"), true}, {QStringLiteral("state"), QStringLiteral("scheduled")},
            {QStringLiteral("next_run_at"), QStringLiteral("2026-10-09T06:00:00+00:00")}}});
    });
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
    // Accueil agrégé (étape P7) : la fixture partagée avec le greffon et la page web.
    serveur.route("GET", kP + QStringLiteral("/accueil"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object());
    });
    serveur.route("GET", QStringLiteral("/api/plugins/kanban/board"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("latest_event_id"), 1}, {QStringLiteral("columns"), QJsonArray{}}});
    });

    // Les préférences de la matrice visuelle ne touchent jamais le profil du propriétaire.
    QTemporaryDir preferences;
    QVERIFY(preferences.isValid());
    QCoreApplication::setOrganizationName(QStringLiteral("ACP Test pages %1").arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
    QCoreApplication::setApplicationName(QStringLiteral("tst_pages_bureau"));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, preferences.path());
    acp::Application application(nullptr, QStringLiteral("AcpTestPagesBureau"));
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
    auto *catalogue = application.findChild<CatalogueViewModel *>();
    auto *comptes = application.findChild<ComptesViewModel *>();
    QVERIFY(comptes);
    auto *journalExecution = application.findChild<JournalExecutionViewModel *>();
    QVERIFY(journalExecution);
    auto *coffre = application.findChild<ObsidianViewModel *>();
    QVERIFY(coffre);
    QVERIFY(catalogue);
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
    QQmlComponent pontComposant(&engine);
    pontComposant.loadFromModule(QStringLiteral("Acp.Theme"), QStringLiteral("ThemeBridge"));
    QVERIFY2(pontComposant.isReady(), qPrintable(pontComposant.errorString()));
    std::unique_ptr<QObject> pont(pontComposant.create());
    QVERIFY(pont);
    const QString repertoireCaptures = qEnvironmentVariable("ACP_CAPTURES_DIR");
    if (!repertoireCaptures.isEmpty()) QVERIFY(QDir().mkpath(repertoireCaptures));
    QQuickWindow window;
    window.resize(1280, 850);
    window.show();
    // Marquage uniquement dans le harnais de capture, jamais dans le produit.
    std::unique_ptr<QObject> marquage;
    if (!repertoireCaptures.isEmpty()) {
        QQmlComponent etiquette(&engine);
        etiquette.setData(QByteArrayLiteral("import QtQuick; Rectangle { z: 100000; anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 4; width: 220; height: 22; color: '#25313d'; radius: 3; Text { anchors.centerIn: parent; text: 'TEST · DONNÉES SIMULÉES'; color: '#ffffff'; font.pixelSize: 11 } }"),QUrl());
        QVERIFY2(etiquette.isReady(),qPrintable(etiquette.errorString()));
        marquage.reset(etiquette.createWithInitialProperties({{QStringLiteral("parent"),QVariant::fromValue(window.contentItem())}}));
        auto *etiquetteItem=qobject_cast<QQuickItem *>(marquage.get()); QVERIFY(etiquetteItem);
        etiquetteItem->setParentItem(window.contentItem());
    }

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
            if (!window.grabWindow().save(captures + QLatin1Char('/') + fichier + QStringLiteral(".png")))
                return etape + QStringLiteral(" : capture PNG impossible");
        }
        return fautes.isEmpty() ? QString() : etape + QStringLiteral(" : ") + fautes;
    };
#define VERIFIER(objet, etape)                                                                                     \
    do {                                                                                                           \
        const QString fautes_ = examiner(objet, etape);                                                            \
        QVERIFY2(fautes_.isEmpty(), qPrintable(fautes_));                                                          \
    } while (false)
    // Relecture de P8b (constat desktop-4) : la page affiche la cadence RÉELLE de sa relecture (propriété `cadence` de
    // son ViewModel), jamais un « toutes les 15 secondes » écrit en dur. Ici, aucun flux annoncé : sondage habituel.
#define VERIFIER_CADENCE(objet, modele, attendue)                                                                  \
    do {                                                                                                           \
        const QString cadence_ = (modele)->property("cadence").toString();                                        \
        QCOMPARE(cadence_, QString(attendue));                                                                     \
        QVERIFY2(contientTexte(qobject_cast<QQuickItem *>(objet), cadence_), qPrintable(cadence_));                \
    } while (false)
    const QString kCadencePage = QStringLiteral("Sans temps réel : page relue toutes les 15 secondes tant qu'elle est affichée.");

    // --- Accueil alimenté ------------------------------------------------------------------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("HomePage"));
        QVERIFY(page);
        QTRY_VERIFY_WITH_TIMEOUT(accueil->lue(), 5000);
        QTRY_COMPARE_WITH_TIMEOUT(accueil->sessions()->count(), 2, 5000);
        QTRY_VERIFY_WITH_TIMEOUT(application.findChild<CompatibiliteHermes *>()->lecture().startsWith(QStringLiteral("Lu à")), 5000);
        VERIFIER(page.get(), QStringLiteral("Accueil"));
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QVERIFY(cliquer(window, item, QStringLiteral("accueil-afficher-operations")));
        VERIFIER_CADENCE(page.get(), accueil,
                         QStringLiteral("Sans temps réel : Accueil, bilan quotidien, discussions récentes et carte Hermes "
                                        "relus toutes les 15 secondes tant que la page est affichée."));
        // Les cartes de l'Accueil agrégé, dans l'ordre du navigateur.
        QVERIFY(contientTexte(item, QStringLiteral("À traiter par vous")));
        QVERIFY(contientTexte(item, QStringLiteral("Question : Exploration du dépôt « jetable » · Outil jetable")));
        QVERIFY(contientTexte(item, QStringLiteral("0 sur 2 cartes faites")));
        QVERIFY(contientTexte(item, QStringLiteral("Exécutant Railway")));
        QVERIFY(contientTexte(item, QStringLiteral("Même enveloppe que Codex (déclaré dans poste.toml)")));
        QVERIFY(contientTexte(item, QStringLiteral("Configurées")));
        QVERIFY(contientTexte(item, QStringLiteral("Sans titre"))); // session s2 sans titre
        // Étape P8b : bilan quotidien (tâche cron native de Hermes), comme la carte du navigateur.
        QTRY_VERIFY_WITH_TIMEOUT(accueil->carteBilan().value(QStringLiteral("lu")).toBool(), 5000);
        QTest::qWait(50);
        VERIFIER(page.get(), QStringLiteral("Accueil, bilan quotidien"));
        QVERIFY(contientTexte(item, QStringLiteral("Bilan quotidien")));
        QVERIFY(contientTexte(item, QStringLiteral("Prochaine exécution")));
        QVERIFY(contientTexte(item, QStringLiteral("Pause et suppression : page Cron")));
    }
    QTRY_VERIFY(!accueil->actif());

    // --- Projets : liste, détail, nouveau, liste vide -------------------------------------------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("ProjectsPage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QTRY_COMPARE_WITH_TIMEOUT(pageProjets->projets()->count(), 2, 5000);
        VERIFIER(page.get(), QStringLiteral("Projets, liste"));
        VERIFIER_CADENCE(page.get(), pageProjets, kCadencePage);
        QVERIFY(contientTexte(item, QStringLiteral("Veille LLM")));

        pageProjets->ouvrirProjet(kId);
        QTRY_VERIFY_WITH_TIMEOUT(pageProjets->detailLu(), 5000);
        VERIFIER(page.get(), QStringLiteral("Projets, détail"));
        QVERIFY(contientTexte(item, QStringLiteral("Écrire outil.py.")));
        QVERIFY(contientTexte(item, QStringLiteral("Quelle version de Python viser ?")));
        QVERIFY(cliquer(window, item, QStringLiteral("projets-onglet-reglages")));
        VERIFIER(page.get(), QStringLiteral("Projets, réglages"));
        // Étape P7 : « Qui répond » se lit « Vous » ; les gestes « Changer qui répond » et « Clore le projet ».
        QVERIFY(contientTexte(item, QStringLiteral("Vous")));
        QVERIFY(contientTexte(item, QStringLiteral("Changer qui répond")));
        QVERIFY(contientTexte(item, QStringLiteral("Clore le projet")));

        pageProjets->afficherNouveau();
        QTRY_VERIFY_WITH_TIMEOUT(pageProjets->formulaire().value(QStringLiteral("pret")).toBool(), 5000);
        VERIFIER(page.get(), QStringLiteral("Projets, nouveau projet"));
        QVERIFY(cliquer(window, item, QStringLiteral("projets-routage-manuel")));
        QVERIFY(contientTexte(item, QStringLiteral("Relevé factice")));
        pageProjets->choisirDepot(QStringLiteral("jetable"));
        VERIFIER(page.get(), QStringLiteral("Projets, nouveau projet avec exploration"));
        QVERIFY(contientTexte(item, QStringLiteral("Exploration du dépôt")));

        projets = fixture(QStringLiteral("projets-vide.json"));
        pageProjets->afficherListe();
        pageProjets->actualiser();
        QTRY_COMPARE_WITH_TIMEOUT(pageProjets->projets()->count(), 0, 5000);
        VERIFIER(page.get(), QStringLiteral("Projets, liste vide"));
        QVERIFY(contientTexte(item, QStringLiteral("Votre prochain projet commence ici")));
    }
    QTRY_VERIFY(!pageProjets->actif());

    // --- Questions : questions, triage, bloquées ; puis tout vide -----------------------------------
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("QuestionsPage"));
        QVERIFY(page);
        auto *item = qobject_cast<QQuickItem *>(page.get());
        QTRY_VERIFY_WITH_TIMEOUT(pageQuestions->lue(), 5000);
        VERIFIER(page.get(), QStringLiteral("Questions"));
        VERIFIER_CADENCE(page.get(), pageQuestions, kCadencePage);
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
        VERIFIER(page.get(), QStringLiteral("Assistants guidés"));
        QVERIFY(page->setProperty("diagnosticsOuverts", true));
        VERIFIER(page.get(), QStringLiteral("Poste en ligne"));
        VERIFIER_CADENCE(page.get(), pagePoste, kCadencePage);
        QVERIFY(contientTexte(item, QStringLiteral("Compte dédié acp-poste")));
        // /v1/meta lu par l'accueil, sans `machine.executant` (Hermes sans l'étape P6).
        QVERIFY(contientTexte(item, QStringLiteral("Exécutant : non disponible sur ce serveur (étape P6).")));
        QVERIFY(contientTexte(item, QStringLiteral("Aucun ordre en attente.")));
        // Avant P7 (aucune mesure servie) : le dépôt de l'inventaire, jamais dit privé.
        QVERIFY(contientTexte(item, QStringLiteral("Jamais mesurée par l'exécutant (Codex fermé)")));

        // Étape P7 (partie E) : visibilité mesurée et voies par dépôt, fixture PARTAGÉE avec le greffon et le web.
        poste.insert(QStringLiteral("executant"), QJsonObject{
            {QStringLiteral("connu"), true},
            {QStringLiteral("depots"), fixturePartagee(QStringLiteral("fixtures_poste/depots.json")).array()}});
        pagePoste->actualiser();
        QTRY_COMPARE_WITH_TIMEOUT(pagePoste->depots().size(), 2, 5000);
        QTest::qWait(50);
        VERIFIER(page.get(), QStringLiteral("Poste, dépôts mesurés"));
        QVERIFY(contientTexte(item, QStringLiteral("Codex : Fermée — dépôt « demo » non prouvé privé (visibilité mesurée : public)")));
        QVERIFY(contientTexte(item, QStringLiteral("Codex : Ouverte")));
        QVERIFY(contientTexte(item, QStringLiteral("Privé")));
        QVERIFY(contientTexte(item, QStringLiteral("Public")));
        QVERIFY(contientTexte(item, QStringLiteral("Codex ne travaille que sur un dépôt prouvé privé (D83)")));

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
        VERIFIER_CADENCE(page.get(), pageQuotas,
                         QStringLiteral("Sans temps réel : page relue toutes les 60 secondes tant qu'elle est affichée."));
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
        // L'introduction conserve les verrous prioritaires et le choix manuel d'exploration ; les préférences
        // du plan départagent seulement les entrées autorisées, sans court-circuiter la table (routage.py).
        QVERIFY(contientTexte(item, QStringLiteral("Les verrous actifs du propriétaire restent prioritaires. Le choix manuel d'exploration est explicite")));
        QVERIFY(contientTexte(item, QStringLiteral("les préférences du plan de Hermes départagent uniquement les entrées autorisées de la classe")));
        QVERIFY(!contientTexte(item, QStringLiteral("Chaque étape d'un projet part vers la première entrée admise")));
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

    // Catalogue réel du faux serveur + fiches locales : aucune intégration dite connectée.
    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("OutilsPage"));
        QVERIFY(page);
        QTRY_VERIFY_WITH_TIMEOUT(catalogue->lue(), 5000);
        VERIFIER(page.get(), QStringLiteral("Outils et compétences"));
        QVERIFY(catalogue->entrees()->count() >= 9);
    }

    {
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("ComptesPage"));
        QVERIFY(page); QTRY_VERIFY(comptes->lue()); QTRY_VERIFY(comptes->attente());
        VERIFIER(page.get(), QStringLiteral("Comptes données simulées"));
    }

    // --- Pages sans données de Hermes -------------------------------------------------------------
    for (const QString &nom : {QStringLiteral("FirstRunPage"), QStringLiteral("DiagnosticsPage"), QStringLiteral("SettingsPage")}) {
        auto page = charger(QStringLiteral("Acp.Pages"), nom);
        QVERIFY2(page, qPrintable(nom));
        VERIFIER(page.get(), nom);
    }
    {
        // Relecture finale de P9 (constat produit-3) : l'avertissement affiché quand une publication est disponible
        // laissait croire les paquets publiés signés (« Vérifiez … la signature du paquet ») ; aucun certificat
        // n'existe et les publications de 1.0.0 sont des brouillons non signés (D131 du plan). Lu même masqué.
        auto page = charger(QStringLiteral("Acp.Pages"), QStringLiteral("SettingsPage"));
        QVERIFY(page);
        QObject *avertissement = page->findChild<QObject *>(QStringLiteral("reglages-avertissement-paquet"));
        QVERIFY(avertissement);
        const QString texte = avertissement->property("text").toString();
        QVERIFY2(texte.contains(QStringLiteral("n'est signé que si les notes de sa publication le disent")),
                 qPrintable(texte));
        QVERIFY2(!texte.contains(QStringLiteral("la signature du paquet")), qPrintable(texte));
    }
    {
        auto coquille = charger(QStringLiteral("Acp.Station"), QStringLiteral("ShellRoot"));
        QVERIFY(coquille);
        VERIFIER(coquille.get(), QStringLiteral("Coquille"));
        // Matrice native facultative : vraies pages et faux Hermes isolé, quatre thèmes,
        // deux tailles. Le PNG n'est accepté que si Qt l'a réellement écrit.
        if (!repertoireCaptures.isEmpty()) {
            auto *apparence = application.findChild<SystemAppearance *>();
            auto *navigation = application.findChild<NavigationModel *>();
            auto *item = qobject_cast<QQuickItem *>(coquille.get());
            QVERIFY(apparence && navigation && item);
            const QString familleAvant = apparence->themeFamily();
            const QString themeAvant = apparence->themePreference();
            const QString mouvementAvant = apparence->motionPreference();
            apparence->setMotionPreference(QStringLiteral("reduced"));
            projets = fixture(QStringLiteral("projets.json"));
            for (const QString &famille : {QStringLiteral("pixel"), QStringLiteral("studio")}) {
                apparence->setThemeFamily(famille);
                for (const QString &theme : {QStringLiteral("dark"), QStringLiteral("light")}) {
                    apparence->setThemePreference(theme);
                    for (const QSize taille : {QSize(1366, 768), QSize(1920, 1080)}) {
                        window.resize(taille);
                        item->setSize(taille);
                        const QString nom = QStringLiteral("Test-fixture-Workspace-%1-%2-%3x%4")
                            .arg(famille, theme).arg(taille.width()).arg(taille.height());
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-home")));
                        QTRY_VERIFY(accueil->actif());
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Accueil"));
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-projects")));
                        pageProjets->afficherListe();
                        pageProjets->actualiser();
                        QTRY_COMPARE_WITH_TIMEOUT(pageProjets->projets()->count(), 2, 5000);
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Projets"));
                        QVERIFY(cliquer(window, item, QStringLiteral("projets-ouvrir-") + kId));
                        QTRY_VERIFY_WITH_TIMEOUT(pageProjets->detailLu(), 5000);
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Travail"));
                        QVERIFY(cliquer(window, item, QStringLiteral("projets-onglet-journal")));
                        QTRY_VERIFY(journalExecution->lue()); QTRY_COMPARE(journalExecution->evenements()->count(),1);
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Journal-simule"));
                        QVERIFY(cliquer(window, item, QStringLiteral("projets-onglet-travail")));
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-home")));
                        QTRY_VERIFY(accueil->actif());
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-chat")));
                        QTRY_VERIFY(discussion->actif());
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Discussion"));
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-accounts")));
                        QTRY_VERIFY(comptes->actif()); QTRY_VERIFY(comptes->lue());
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Comptes-simules"));
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-settings")));
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-tools")));
                        QTRY_VERIFY(catalogue->actif());
                        QTRY_VERIFY(catalogue->lue());
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Outils"));
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-settings")));
                        QVERIFY(cliquer(window, item, QStringLiteral("navigation-vault")));
                        QTRY_VERIFY(coffre->actif());
                        QTRY_VERIFY(!coffre->occupe());
                        QVERIFY(cliquer(window, item, QStringLiteral("coffre-actualiser")));
                        QTRY_COMPARE(coffre->etat(), QStringLiteral("pret"));
                        QTRY_VERIFY(!coffre->occupe());
                        coffre->lister();
                        QTRY_COMPARE(coffre->notes()->count(), 2);
                        QTRY_VERIFY(!coffre->occupe());
                        coffre->ouvrirNote(QStringLiteral("Accueil.md"));
                        QTRY_VERIFY(!coffre->occupe());
                        QTRY_VERIFY(!coffre->brouillon().isEmpty());
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Coffre"));
                        coffre->lireGraphe();
                        QTRY_VERIFY(!coffre->occupe());
                        QVERIFY(!coffre->graphe().isEmpty());
                        QVERIFY(cliquer(window, item, QStringLiteral("coffre-graphe-visuel")));
                        VERIFIER(coquille.get(), nom + QStringLiteral("-Coffre-graphe"));
                    }
                }
            }
            apparence->setThemeFamily(familleAvant);
            apparence->setThemePreference(themeAvant);
            apparence->setMotionPreference(mouvementAvant);
            window.resize(1280, 850);
            item->setSize(window.size());
        }
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
