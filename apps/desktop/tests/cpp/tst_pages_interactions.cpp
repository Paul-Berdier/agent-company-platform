// Gestes réels sur les pages de la station : clics de souris et frappes au clavier sur les
// VRAIS contrôles QML (jamais un appel direct du ViewModel), contre le faux Hermes.
//
// Composition du produit (Application) ; préférences dans un dossier temporaire ; aucune
// connexion ouverte (porteur fixe), donc aucune entrée de coffre. Les singletons QML sont
// enregistrés une fois par processus : la composition est montée dans initTestCase().

#include "api/ApiClient.h"
#include "app/Application.h"
#include "commands/CommandRegistry.h"
#include "events/EventStreamService.h"
#include "events/FluxInvalidation.h"
#include "gateway/GatewayClient.h"
#include "models/JsonListModel.h"
#include "navigation/NavigationModel.h"
#include "services/CompatibiliteHermes.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "gateway/DiscussionsEnAttente.h"
#include "viewmodels/AccueilViewModel.h"
#include "viewmodels/DiscussionViewModel.h"
#include "viewmodels/PosteViewModel.h"
#include "viewmodels/ProjetsViewModel.h"
#include "viewmodels/QuestionsViewModel.h"
#include "viewmodels/QuotasViewModel.h"
#include "viewmodels/ShellViewModel.h"

#include <QClipboard>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QKeySequence>
#include <QJsonArray>
#include <QPointer>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlProperty>
#include <QQuickItem>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QSettings>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>

#include <algorithm>
#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kQuestion = QStringLiteral("q_b627a3c245ec");

void tous(QQuickItem *item, QList<QQuickItem *> &liste)
{
    if (!item) {
        return;
    }
    liste.append(item);
    for (QQuickItem *enfant : item->childItems()) {
        tous(enfant, liste);
    }
}

QQuickItem *parNom(QQuickItem *racine, const QString &nom)
{
    QList<QQuickItem *> liste;
    tous(racine, liste);
    for (QQuickItem *item : std::as_const(liste)) {
        if (item->objectName() == nom) {
            return item;
        }
    }
    return nullptr;
}

} // namespace

class TestPagesInteractions : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();
    void brouillonDeReponseGardeAuSondageEtAuRefus();
    void relanceEtRefusDeRevueParLesVraisBoutons();
    void clotureEtQuiRepondParLesVraisBoutons();
    void executantFermeGriseDansLeFormulaire();
    void questionsReluesAuSignalDuFlux();
    void listeDesProjetsGardeSonDefilement();
    void messageEnvoyeParLeBoutonDeLaDiscussion();
    void dialogueDeChangementDeServeurEnFrancais();
    void copieDuRapportParLaPalette();
    void discussionEnAttenteOuverteParLeBouton();
    void discussionEnAttenteMarqueeDansLaListe();
    void pastilleDesQuestionsDitCeQuElleCompte();
    void greffonSansEtapeP7NiAccueilNiGestes();
    // En dernier : charge la fenêtre racine (App.qml).
    void chaqueRaccourciDeLaPaletteAgit();

private:
    std::unique_ptr<QObject> charger(const QString &nom, const QString &module = QStringLiteral("Acp.Pages"));
    //! Clic gauche réel au centre de l'élément, s'il est visible dans la fenêtre.
    bool cliquer(QQuickItem *item);
    //! Donne le focus au champ par un clic réel, puis tape le texte touche par touche.
    bool taper(QQuickItem *champ, const QString &texte);

    QTemporaryDir m_reglages;
    std::unique_ptr<FauxHermes> m_serveur;
    std::unique_ptr<Application> m_application;
    std::unique_ptr<QQmlApplicationEngine> m_moteur;
    std::unique_ptr<QQuickWindow> m_fenetre;
    QStringList m_avertissements;
    ApiClient *m_client = nullptr;
    EventStreamService *m_flux = nullptr;
    ProjetsViewModel *m_projets = nullptr;
    QuestionsViewModel *m_questions = nullptr;
    QJsonObject m_listeProjets;
    QJsonObject m_listeQuestions;
    ReponseFaux m_reponseQuestion;
    ReponseFaux m_reponseRelance;
};

void TestPagesInteractions::initTestCase()
{
    QVERIFY(m_reglages.isValid());
    QCoreApplication::setOrganizationName(
        QStringLiteral("ACP Test interactions %1").arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
    QCoreApplication::setApplicationName(QStringLiteral("tst_pages_interactions"));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, m_reglages.path());

    m_serveur = std::make_unique<FauxHermes>();
    m_serveur->installerAuthentification();
    m_serveur->activerKanban();
    m_serveur->jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    m_serveur->activerPasserelle();
    m_serveur->methodes.insert(QStringLiteral("session.list"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{QJsonObject{
            {QStringLiteral("id"), QStringLiteral("s1")}, {QStringLiteral("title"), QStringLiteral("Plan du site")},
            {QStringLiteral("started_at"), 1790300000}, {QStringLiteral("message_count"), 0}}}}};
    });
    m_serveur->methodes.insert(QStringLiteral("session.resume"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")}, {QStringLiteral("message_count"), 0},
                           {QStringLiteral("messages"), QJsonArray{}},
                           {QStringLiteral("info"), QJsonObject{{QStringLiteral("title"), QStringLiteral("Plan du site")}}},
                           {QStringLiteral("running"), false}};
    });
    m_serveur->methodes.insert(QStringLiteral("prompt.submit"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("status"), QStringLiteral("streaming")}};
    });
    m_listeQuestions = fixture(QStringLiteral("questions.json"));
    m_serveur->route("GET", kP + QStringLiteral("/questions"),
                     [this](const RequeteRecue &) { return ReponseFaux::json(200, m_listeQuestions); });
    m_serveur->route("POST", kP + QStringLiteral("/questions/%1/reponse").arg(kQuestion),
                     [this](const RequeteRecue &) { return m_reponseQuestion; });
    // Étape P7 : relance d'une carte arrêtée (ARRETEE_RELANCABLE) et revue des fichiers de pilotage.
    m_serveur->route("POST", kP + QStringLiteral("/cartes/acp-outil-3dd5/t_5e6f7a8b/relancer"),
                     [this](const RequeteRecue &) { return m_reponseRelance; });
    // Étape P7 : détail d'un projet, « Changer qui répond » et « Clore le projet ».
    m_serveur->route("GET", kP + QStringLiteral("/projets/p_367e23fd51b7"),
                     [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projet-detail.json"))); });
    m_serveur->route("POST", kP + QStringLiteral("/projets/p_367e23fd51b7/reponses"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("questions_ouvertes_inchangees"), 1}});
    });
    m_serveur->route("POST", kP + QStringLiteral("/projets/p_367e23fd51b7/clore"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("clos"), true}, {QStringLiteral("etat"), QStringLiteral("termine")},
                                                  {QStringLiteral("cartes_archivees"), QJsonArray{}},
                                                  {QStringLiteral("cartes_non_archivees"), QJsonArray{}},
                                                  {QStringLiteral("questions_annulees"), 0},
                                                  {QStringLiteral("branches_rapportees"), QJsonArray{}}});
    });
    m_serveur->route("POST", kP + QStringLiteral("/revues/acp-outil-3dd5/t_aa11bb22/refuser"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte"), QStringLiteral("t_aa11bb22")},
                                                  {QStringLiteral("etat"), QStringLiteral("ready")}});
    });
    // Six projets (copies des deux formes servies, identifiants distincts) : une liste plus
    // haute que la fenêtre.
    m_listeProjets = fixture(QStringLiteral("projets.json"));
    const QJsonArray formes = m_listeProjets.value(QStringLiteral("projets")).toArray();
    QJsonArray six;
    for (int rang = 0; rang < 6; ++rang) {
        QJsonObject projet = formes.at(rang % 2).toObject();
        projet.insert(QStringLiteral("id"), QStringLiteral("p_interaction%1").arg(rang));
        projet.insert(QStringLiteral("titre"), QStringLiteral("Projet d'essai %1").arg(rang + 1));
        six.append(projet);
    }
    m_listeProjets.insert(QStringLiteral("projets"), six);
    m_serveur->route("GET", kP + QStringLiteral("/projets"),
                     [this](const RequeteRecue &) { return ReponseFaux::json(200, m_listeProjets); });

    m_application = std::make_unique<Application>(nullptr, QStringLiteral("AcpTestInteractions"));
    m_application->registerQmlTypes();
    m_client = m_application->findChild<ApiClient *>();
    m_flux = m_application->findChild<EventStreamService *>();
    m_projets = m_application->findChild<ProjetsViewModel *>();
    m_questions = m_application->findChild<QuestionsViewModel *>();
    QVERIFY(m_client && m_flux && m_projets && m_questions);
    m_client->setAllowInsecureLoopback(true);
    QVERIFY(!m_client->setBaseUrl(m_serveur->url()).isError());
    m_client->setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    m_flux->setIntervalleFond(std::chrono::hours(1));
    m_flux->demarrer();
    // Verdict d'un greffon de l'étape P7 (document de référence : clé `accueil`), relayé par la composition réelle :
    // « Qui répond », « Clore » et l'Accueil agrégé sont offerts (seconde relecture de P8b, constat desktop-8).
    auto *compatibilite = m_application->findChild<CompatibiliteHermes *>();
    QVERIFY(compatibilite);
    compatibilite->appliquerLecture(fixture(QStringLiteral("meta.json")));
    QCOMPARE(m_flux->etapeP7(), QStringLiteral("annonce"));

    m_moteur = std::make_unique<QQmlApplicationEngine>();
    connect(m_moteur.get(), &QQmlEngine::warnings, this, [this](const QList<QQmlError> &erreurs) {
        for (const auto &erreur : erreurs) {
            m_avertissements.append(erreur.toString());
        }
    });
    m_fenetre = std::make_unique<QQuickWindow>();
    m_fenetre->resize(1280, 850);
    m_fenetre->show();
    m_fenetre->requestActivate();
    QVERIFY(QTest::qWaitForWindowExposed(m_fenetre.get()));
}

void TestPagesInteractions::cleanupTestCase()
{
    m_fenetre.reset();
    m_moteur.reset();
    m_application.reset();
    m_serveur.reset();
}

std::unique_ptr<QObject> TestPagesInteractions::charger(const QString &nom, const QString &module)
{
    m_avertissements.clear();
    QQmlComponent composant(m_moteur.get());
    composant.loadFromModule(module, nom);
    if (!QTest::qWaitFor([&composant] { return composant.status() != QQmlComponent::Loading; }, 5000)
        || !composant.isReady()) {
        qWarning("%s", qPrintable(composant.errorString()));
        return nullptr;
    }
    std::unique_ptr<QObject> objet(composant.create());
    if (auto *item = qobject_cast<QQuickItem *>(objet.get())) {
        item->setParentItem(m_fenetre->contentItem());
        item->setSize(m_fenetre->size());
    }
    return objet;
}

bool TestPagesInteractions::cliquer(QQuickItem *item)
{
    if (!item || !item->isVisible() || !item->isEnabled()) {
        return false;
    }
    // Comme le propriétaire : la page défile jusqu'au contrôle avant le clic.
    for (QQuickItem *parent = item->parentItem(); parent; parent = parent->parentItem()) {
        if (parent->inherits("QQuickFlickable")) {
            auto *contenu = parent->property("contentItem").value<QQuickItem *>();
            const double haut = item->mapToItem(contenu, QPointF(0, 0)).y();
            const double maximum = std::max(0.0, parent->property("contentHeight").toDouble() - parent->height());
            const double visible = parent->property("contentY").toDouble();
            if (haut < visible || haut + item->height() > visible + parent->height()) {
                parent->setProperty("contentY", std::clamp(haut - 40.0, 0.0, maximum));
            }
            break;
        }
    }
    const QPointF centre = item->mapToScene(QPointF(item->width() / 2, item->height() / 2));
    if (!QRectF(QPointF(0, 0), m_fenetre->size()).contains(centre)) {
        return false;
    }
    QTest::mouseClick(m_fenetre.get(), Qt::LeftButton, Qt::NoModifier, centre.toPoint());
    return true;
}

bool TestPagesInteractions::taper(QQuickItem *champ, const QString &texte)
{
    if (!cliquer(champ) || !QTest::qWaitFor([champ] { return champ->hasActiveFocus(); }, 2000)) {
        return false;
    }
    // QTest n'a pas de keyClicks() pour une QWindow : une touche par caractère (ASCII).
    for (const QChar caractere : texte) {
        if (caractere.unicode() > 0x7f) {
            return false;
        }
        QTest::keyClick(m_fenetre.get(), caractere.toLatin1());
    }
    return true;
}

// Constat de relecture P8 (critique) : le texte tapé dans « Votre réponse » était effacé à
// chaque relecture de la page (15 s) et après un envoi refusé, le délégué étant recréé.
void TestPagesInteractions::brouillonDeReponseGardeAuSondageEtAuRefus()
{
    m_questions->setIntervalle(std::chrono::milliseconds(150));
    auto page = charger(QStringLiteral("QuestionsPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    QTRY_VERIFY_WITH_TIMEOUT(m_questions->lue(), 5000);
    QTest::qWait(100);

    QPointer<QQuickItem> champ = parNom(racine, QStringLiteral("questions-reponse-") + kQuestion);
    QPointer<QQuickItem> consigne = parNom(racine, QStringLiteral("questions-consigne-t_0c1d2e3f"));
    QVERIFY(champ && consigne);
    const QString texte = QStringLiteral("Python 3.12, la CI le teste");
    QVERIFY(taper(champ, texte));
    QCOMPARE(champ->property("text").toString(), texte);
    QVERIFY(taper(consigne, QStringLiteral("Un tour de plus")));

    // Plusieurs relectures par le minuteur de la page : le champ est le MÊME objet, texte et
    // focus compris (sans la mise à jour par identifiant, il était recréé vide).
    const int lectures = m_serveur->compter("GET", kP + QStringLiteral("/questions"));
    QTRY_VERIFY_WITH_TIMEOUT(m_serveur->compter("GET", kP + QStringLiteral("/questions")) >= lectures + 3, 5000);
    QTest::qWait(100);
    QVERIFY2(champ, "le champ de réponse a été détruit par la relecture");
    QCOMPARE(champ->property("text").toString(), texte);
    QVERIFY2(consigne, "le champ de consigne a été détruit par la relecture");
    QCOMPARE(consigne->property("text").toString(), QStringLiteral("Un tour de plus"));
    m_questions->setIntervalle(std::chrono::hours(1));

    // Envoi refusé par Hermes (503 pendant un redéploiement), par un clic réel sur « Répondre ».
    m_reponseQuestion = ReponseFaux::json(503, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Service Unavailable")}});
    QVERIFY(cliquer(parNom(racine, QStringLiteral("questions-repondre-") + kQuestion)));
    QTRY_VERIFY_WITH_TIMEOUT(!m_questions->erreurGeste().isEmpty(), 5000);
    QTRY_VERIFY_WITH_TIMEOUT(!m_questions->gesteEnCours(), 5000);
    QTest::qWait(200); // relecture qui suit le geste
    QCOMPARE(m_serveur->compter("POST", kP + QStringLiteral("/questions/%1/reponse").arg(kQuestion)), 1);
    QVERIFY2(champ, "le champ de réponse a été détruit après le refus");
    QCOMPARE(champ->property("text").toString(), texte);

    // Page quittée puis rouverte : le brouillon revient dans le nouveau champ.
    page.reset();
    QTest::qWait(50);
    page = charger(QStringLiteral("QuestionsPage"));
    racine = qobject_cast<QQuickItem *>(page.get());
    QTRY_VERIFY_WITH_TIMEOUT(parNom(racine, QStringLiteral("questions-reponse-") + kQuestion), 5000);
    champ = parNom(racine, QStringLiteral("questions-reponse-") + kQuestion);
    QCOMPARE(champ->property("text").toString(), texte);

    // Réussite : la réponse part (corps tel que tapé), le champ et le brouillon se vident.
    m_reponseQuestion = ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte_debloquee"), true}});
    QVERIFY(cliquer(parNom(racine, QStringLiteral("questions-repondre-") + kQuestion)));
    QTRY_COMPARE_WITH_TIMEOUT(m_questions->messageGeste(), QStringLiteral("Réponse envoyée : la carte reprend."), 5000);
    const QList<RequeteRecue> envois = m_serveur->filtrer("POST", kP + QStringLiteral("/questions/%1/reponse").arg(kQuestion));
    QCOMPARE(envois.size(), 2);
    QCOMPARE(envois.constLast().json().value(QStringLiteral("reponse")).toString(), texte);
    QTRY_COMPARE_WITH_TIMEOUT(champ->property("text").toString(), QString(), 2000);
    QCOMPARE(m_questions->brouillon(QStringLiteral("q:") + kQuestion), QString());
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    page.reset();
    QTRY_VERIFY(!m_questions->actif());
}

// Étape P7 dans la station : « Relancer » une carte arrêtée avec une consigne tapée, puis
// « Refuser » une revue avec un motif tapé, par les vrais champs et les vrais boutons.
void TestPagesInteractions::relanceEtRefusDeRevueParLesVraisBoutons()
{
    const QJsonObject avant = m_listeQuestions;
    QJsonArray bloquees = m_listeQuestions.value(QStringLiteral("bloquees")).toArray();
    bloquees.append(fixture(QStringLiteral("arretee-relancable.json")));
    m_listeQuestions.insert(QStringLiteral("bloquees"), bloquees);
    m_listeQuestions.insert(QStringLiteral("revues"), QJsonArray{QJsonObject{
        {QStringLiteral("projet"), QStringLiteral("p_367e23fd51b7")}, {QStringLiteral("projet_titre"), QStringLiteral("Outil")},
        {QStringLiteral("tableau"), QStringLiteral("acp-outil-3dd5")}, {QStringLiteral("carte"), QStringLiteral("t_aa11bb22")},
        {QStringLiteral("titre"), QStringLiteral("Implémentation — e2 : règles des agents")},
        {QStringLiteral("chemins"), QJsonArray{QStringLiteral("AGENTS.md")}},
        {QStringLiteral("diffstat"), QJsonObject{{QStringLiteral("fichiers"), 1}, {QStringLiteral("ajouts"), 4}, {QStringLiteral("retraits"), 0}}},
        {QStringLiteral("branche"), QStringLiteral("acp/outil/e2")}, {QStringLiteral("tete"), QStringLiteral("9f8e7d6c")},
        {QStringLiteral("resume"), QJsonValue::Null}, {QStringLiteral("diff"), QStringLiteral("Le diff reste sur l'exécutant.")}}});
    m_reponseRelance = ReponseFaux::json(200, QJsonObject{{QStringLiteral("carte"), QStringLiteral("t_5e6f7a8b")},
                                                          {QStringLiteral("relancee"), true},
                                                          {QStringLiteral("statut_apres"), QStringLiteral("ready")},
                                                          {QStringLiteral("session_neuve"), true},
                                                          {QStringLiteral("branche_neuve"), false}});
    m_questions->setIntervalle(std::chrono::hours(1));
    auto page = charger(QStringLiteral("QuestionsPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    m_questions->actualiser();
    QTRY_VERIFY_WITH_TIMEOUT(m_questions->bloquees()->count() == 2, 5000);
    QTest::qWait(100);

    // Carte étrangère : aucun bouton « Relancer », la raison du greffon est dite.
    QVERIFY(!parNom(racine, QStringLiteral("questions-relancer-t_9a8b7c6d"))->isVisible());
    QCOMPARE(parNom(racine, QStringLiteral("questions-refus-relance-t_9a8b7c6d"))->property("text").toString(),
             QStringLiteral("Relance impossible : Carte non émise par ACP : ACP ne la relance pas."));

    QPointer<QQuickItem> consigne = parNom(racine, QStringLiteral("questions-consigne-relance-t_5e6f7a8b"));
    QVERIFY(consigne && consigne->isVisible());
    QVERIFY(taper(consigne, QStringLiteral("Reprends avec Python 3.12")));
    QVERIFY(cliquer(parNom(racine, QStringLiteral("questions-relancer-t_5e6f7a8b"))));
    QTRY_COMPARE_WITH_TIMEOUT(m_questions->messageGeste(),
                              QStringLiteral("La carte repart : l'agent reprend d'une session neuve, sur la branche déjà "
                                             "commencée. Statut : Prête."), 5000);
    const QList<RequeteRecue> relances = m_serveur->filtrer("POST", kP + QStringLiteral("/cartes/acp-outil-3dd5/t_5e6f7a8b/relancer"));
    QCOMPARE(relances.size(), 1);
    QCOMPARE(relances.first().json(), (QJsonObject{{QStringLiteral("consigne"), QStringLiteral("Reprends avec Python 3.12")}}));
    QTRY_COMPARE_WITH_TIMEOUT(consigne->property("text").toString(), QString(), 2000);
    QQuickItem *bandeau = parNom(racine, QStringLiteral("questions-bandeau"));
    QVERIFY(bandeau && bandeau->isVisible());
    QVERIFY(bandeau->property("texte").toString().startsWith(QStringLiteral("La carte repart")));

    // Refus de revue : « Refuser » reste inerte tant que le motif est vide, puis part avec le motif tapé.
    QQuickItem *refuser = parNom(racine, QStringLiteral("questions-refuser-t_aa11bb22"));
    QVERIFY(refuser && refuser->isVisible());
    QCOMPARE(refuser->property("effectiveEnabled").toBool(), false);
    QVERIFY(taper(parNom(racine, QStringLiteral("questions-motif-t_aa11bb22")), QStringLiteral("Ne touche pas a la CI")));
    QTRY_VERIFY(refuser->property("effectiveEnabled").toBool());
    QVERIFY(cliquer(refuser));
    QTRY_COMPARE_WITH_TIMEOUT(m_questions->messageGeste(),
                              QStringLiteral("Revue refusée : la carte revient à l'exécutant avec votre motif."), 5000);
    const QList<RequeteRecue> refus = m_serveur->filtrer("POST", kP + QStringLiteral("/revues/acp-outil-3dd5/t_aa11bb22/refuser"));
    QCOMPARE(refus.size(), 1);
    QCOMPARE(refus.first().json(), (QJsonObject{{QStringLiteral("motif"), QStringLiteral("Ne touche pas a la CI")}}));
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    page.reset();
    QTRY_VERIFY(!m_questions->actif());
    m_listeQuestions = avant;
}

// Étape P7 dans le détail d'un projet : « Changer qui répond » (choix changé au clavier, puis
// « Enregistrer ») et « Clore le projet » (rien ne part avant « Confirmer la clôture »).
void TestPagesInteractions::clotureEtQuiRepondParLesVraisBoutons()
{
    auto page = charger(QStringLiteral("ProjectsPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    m_projets->ouvrirProjet(QStringLiteral("p_367e23fd51b7"));
    QTRY_VERIFY_WITH_TIMEOUT(m_projets->detailLu(), 5000);
    QTest::qWait(150);
    const QString reponses = kP + QStringLiteral("/projets/p_367e23fd51b7/reponses");
    const QString clore = kP + QStringLiteral("/projets/p_367e23fd51b7/clore");

    // « Changer qui répond » : le formulaire s'ouvre sur le réglage lu (« Moi »), le choix passe à « Hermes d'abord ».
    QVERIFY(cliquer(parNom(racine, QStringLiteral("projets-changer-reponses"))));
    QQuickItem *choix = parNom(racine, QStringLiteral("projets-choix-reponses"));
    QTRY_VERIFY(choix && choix->isVisible());
    QCOMPARE(choix->property("currentIndex").toInt(), 1);
    choix->forceActiveFocus();
    QTRY_VERIFY(choix->hasActiveFocus());
    QTest::keyClick(m_fenetre.get(), Qt::Key_Up);
    QTRY_COMPARE(choix->property("currentIndex").toInt(), 0);
    QCOMPARE(m_serveur->filtrer("POST", reponses).size(), 0); // rien ne part avant « Enregistrer »
    QVERIFY(cliquer(parNom(racine, QStringLiteral("projets-enregistrer-reponses"))));
    QTRY_COMPARE_WITH_TIMEOUT(m_projets->messageGeste(),
                              QStringLiteral("Réglage enregistré pour les questions suivantes. Questions ouvertes qui gardent "
                                             "leur traitement : 1"), 5000);
    QCOMPARE(m_serveur->filtrer("POST", reponses).size(), 1);
    QCOMPARE(m_serveur->filtrer("POST", reponses).first().json(),
             (QJsonObject{{QStringLiteral("reponses"), QStringLiteral("hermes_d_abord")}}));
    QTRY_VERIFY(!choix->isVisible()); // le formulaire se ferme après la réponse du greffon

    // « Clore le projet » : une confirmation qui dit les effets ; « Annuler » ne fait rien partir.
    QVERIFY(cliquer(parNom(racine, QStringLiteral("projets-clore"))));
    QTRY_VERIFY(parNom(racine, QStringLiteral("projets-clore-question"))->isVisible());
    QVERIFY(cliquer(parNom(racine, QStringLiteral("projets-annuler-clore"))));
    QTRY_VERIFY(!parNom(racine, QStringLiteral("projets-clore-question"))->isVisible());
    QCOMPARE(m_serveur->filtrer("POST", clore).size(), 0);
    QVERIFY(cliquer(parNom(racine, QStringLiteral("projets-clore"))));
    QVERIFY(cliquer(parNom(racine, QStringLiteral("projets-confirmer-clore"))));
    QTRY_COMPARE_WITH_TIMEOUT(m_projets->messageGeste(),
                              QStringLiteral("Projet clos : terminé. Cartes archivées : 0 · Questions annulées : 0."), 5000);
    QCOMPARE(m_serveur->filtrer("POST", clore).size(), 1);
    QCOMPARE(m_serveur->filtrer("POST", clore).first().json(), (QJsonObject{{QStringLiteral("confirmation"), true}}));
    QQuickItem *bandeau = parNom(racine, QStringLiteral("projets-bandeau"));
    QVERIFY(bandeau && bandeau->isVisible());
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    m_projets->afficherListe();
    page.reset();
    QTRY_VERIFY(!m_projets->actif());
}

// Étape P7 (partie E) : Codex sur un dépôt non prouvé privé est grisé dans la VRAIE liste « Exécutant »
// (fixture PARTAGÉE fixtures_poste/depots.json) ; le choisir au clavier est refusé et la liste revient.
void TestPagesInteractions::executantFermeGriseDansLeFormulaire()
{
    const QJsonArray mesures = fixturePartagee(QStringLiteral("fixtures_poste/depots.json")).array();
    QJsonObject poste = fixture(QStringLiteral("poste-releve.json"));
    QJsonObject catalogue = poste.value(QStringLiteral("catalogue")).toObject();
    QJsonObject voies = catalogue.value(QStringLiteral("voies")).toObject();
    for (const QString &voie : voies.keys()) {
        QJsonObject releve = voies.value(voie).toObject();
        releve.insert(QStringLiteral("depots"), QJsonArray{QStringLiteral("demo"), QStringLiteral("jetable")});
        voies.insert(voie, releve);
    }
    catalogue.insert(QStringLiteral("voies"), voies);
    poste.insert(QStringLiteral("catalogue"), catalogue);
    poste.insert(QStringLiteral("executant"), QJsonObject{{QStringLiteral("connu"), true}, {QStringLiteral("depots"), mesures}});
    m_serveur->route("GET", kP + QStringLiteral("/poste"), [poste](const RequeteRecue &) { return ReponseFaux::json(200, poste); });
    m_serveur->route("GET", kP + QStringLiteral("/catalogue"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, fixture(QStringLiteral("catalogue-profils.json")));
    });

    auto page = charger(QStringLiteral("ProjectsPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    m_projets->afficherNouveau();
    QTRY_VERIFY_WITH_TIMEOUT(m_projets->formulaire().value(QStringLiteral("pret")).toBool(), 5000);
    QTest::qWait(100);

    // Dépôt « demo » choisi au clavier dans la vraie liste (Sans dépôt, demo, jetable).
    QQuickItem *depot = parNom(racine, QStringLiteral("projets-champ-depot"));
    QVERIFY(depot && depot->isEnabled());
    depot->forceActiveFocus();
    QTRY_VERIFY(depot->hasActiveFocus());
    QTest::keyClick(m_fenetre.get(), Qt::Key_Down);
    QTRY_COMPARE(m_projets->formulaire().value(QStringLiteral("depot")).toString(), QStringLiteral("demo"));
    QTest::qWait(50);

    QQuickItem *voie = parNom(racine, QStringLiteral("projets-champ-voie"));
    QTRY_VERIFY(voie && voie->isVisible());
    QCOMPARE(voie->property("currentValue").toString(), QStringLiteral("poste-claude"));
    QQuickItem *raison = parNom(racine, QStringLiteral("projets-voie-fermee"));
    QVERIFY(raison && raison->isVisible());
    QVERIFY(raison->property("text").toString().contains(QStringLiteral("dépôt « demo » non prouvé privé")));

    // Liste ouverte par un clic réel : l'option Codex est grisée ; un clic dessus ne choisit rien.
    QVERIFY(cliquer(voie));
    QPointer<QQuickItem> codex;
    QTRY_VERIFY((codex = parNom(m_fenetre->contentItem(), QStringLiteral("projets-voie-option-poste-codex"))) && codex->isVisible());
    QCOMPARE(codex->isEnabled(), false);
    QCOMPARE(codex->property("text").toString(), QStringLiteral("Poste (Codex) — fermé pour ce dépôt"));
    QQuickItem *claude = parNom(m_fenetre->contentItem(), QStringLiteral("projets-voie-option-poste-claude"));
    QVERIFY(claude && claude->isEnabled());
    QTest::mouseClick(m_fenetre.get(), Qt::LeftButton, Qt::NoModifier,
                      codex->mapToScene(QPointF(codex->width() / 2, codex->height() / 2)).toPoint());
    QTest::qWait(100);
    QCOMPARE(m_projets->formulaire().value(QStringLiteral("voie")).toString(), QStringLiteral("poste-claude"));
    QTest::keyClick(m_fenetre.get(), Qt::Key_Escape);
    QTRY_VERIFY(!codex || !codex->isVisible());

    // Au clavier, la flèche passe sur Codex : refusé en français, la liste revient sur l'exécutant ouvert.
    voie->forceActiveFocus();
    QTRY_VERIFY(voie->hasActiveFocus());
    QTest::keyClick(m_fenetre.get(), Qt::Key_Down);
    QTRY_VERIFY(m_projets->erreurGeste().startsWith(QStringLiteral("Cet exécutant est fermé pour ce dépôt : dépôt « demo »")));
    QTRY_COMPARE(voie->property("currentValue").toString(), QStringLiteral("poste-claude"));
    QCOMPARE(m_projets->formulaire().value(QStringLiteral("voie")).toString(), QStringLiteral("poste-claude"));
    QCOMPARE(m_serveur->filtrer("POST", kP + QStringLiteral("/projets")).size(), 0);
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    m_projets->afficherListe();
    page.reset();
    QTRY_VERIFY(!m_projets->actif());
}

// Étape P8b : dans la composition réelle, le verdict de /v1/meta qui ANNONCE le flux d'invalidation
// l'ouvre ; la page Questions affichée se relit au signal de ses sujets (trames PARTAGÉES de
// fixtures_flux/trames.json), jamais pour un sujet qu'elle ne suit pas ; le retrait de l'annonce
// le ferme.
void TestPagesInteractions::questionsReluesAuSignalDuFlux()
{
    auto *compatibilite = m_application->findChild<CompatibiliteHermes *>();
    QVERIFY(compatibilite);
    const QJsonObject trames = fixturePartagee(QStringLiteral("fixtures_flux/trames.json")).object()
                                   .value(QStringLiteral("trames")).toObject();
    const auto trame = [&trames](const char *nom) { return trames.value(QString::fromLatin1(nom)).toString().toUtf8(); };
    m_questions->setIntervalle(std::chrono::hours(1)); // aucune relecture par sondage pendant ce test
    m_serveur->activerFlux();
    const int avantOuvertures = m_serveur->compter("GET", kP + QStringLiteral("/flux"));

    auto page = charger(QStringLiteral("QuestionsPage"));
    QVERIFY(page);
    QTRY_VERIFY_WITH_TIMEOUT(m_questions->lue(), 5000);
    QTest::qWait(100);
    QCOMPARE(m_serveur->compter("GET", kP + QStringLiteral("/flux")), avantOuvertures); // rien d'annoncé : rien d'ouvert

    QJsonObject meta = fixture(QStringLiteral("meta.json"));
    meta.insert(QStringLiteral("flux"), QJsonObject{
        {QStringLiteral("chemin"), QStringLiteral("/api/plugins/acp-poste/v1/flux")}, {QStringLiteral("version"), 1},
        {QStringLiteral("sujets"), QJsonArray::fromStringList(FluxInvalidation::sujets())},
        {QStringLiteral("battement_s"), 15}, {QStringLiteral("duree_max_s"), 600}});
    compatibilite->appliquerLecture(meta);
    QTRY_COMPARE_WITH_TIMEOUT(m_serveur->clientsFlux(), 1, 5000);
    QCOMPARE(m_flux->libelleTempsReel(), QStringLiteral("Temps réel : connexion…"));

    const QString route = kP + QStringLiteral("/questions");
    const int lectures = m_serveur->compter("GET", route);
    m_serveur->envoyerFlux(trame("ouverture"));
    QTRY_COMPARE_WITH_TIMEOUT(m_serveur->compter("GET", route), lectures + 1, 5000);
    QVERIFY(m_flux->tempsReel());
    QCOMPARE(m_flux->libelleTempsReel(), QStringLiteral("Temps réel"));

    // Relecture de P8b (constat desktop-4) : en temps réel, la page dit sa cadence RÉELLE (au signal, et relecture de
    // sûreté), jamais « toutes les 15 secondes ». La file Questions est réglée ici à une heure (aucun sondage).
    QQuickItem *cadence = parNom(qobject_cast<QQuickItem *>(page.get()), QStringLiteral("questions-cadence"));
    QVERIFY(cadence && cadence->isVisible());
    QTRY_COMPARE(cadence->property("text").toString(), m_questions->property("cadence").toString());
    QCOMPARE(cadence->property("text").toString(),
             QStringLiteral("Page relue à chaque changement signalé par le serveur (temps réel) et toutes les 60 minutes "
                            "par sûreté, tant qu'elle est affichée."));
    // Les autres pages de pilotage, à leur réglage du produit : sûreté de 2 minutes en temps réel.
    for (QObject *autre : std::initializer_list<QObject *>{m_projets, m_application->findChild<PosteViewModel *>(),
                                                           m_application->findChild<QuotasViewModel *>()}) {
        QVERIFY(autre);
        QCOMPARE(autre->property("cadence").toString(),
                 QStringLiteral("Page relue à chaque changement signalé par le serveur (temps réel) et toutes les 2 "
                                "minutes par sûreté, tant qu'elle est affichée."));
    }
    auto *accueil = m_application->findChild<AccueilViewModel *>();
    QVERIFY(accueil);
    QCOMPARE(accueil->property("cadence").toString(),
             QStringLiteral("Accueil relu à chaque changement signalé par le serveur (temps réel) et toutes les 2 minutes "
                            "par sûreté ; bilan quotidien relu toutes les 2 minutes ; discussions récentes et carte Hermes "
                            "relues toutes les 15 secondes ; tant que la page est affichée."));
    m_serveur->envoyerFlux(trame("changement")); // projets, questions
    QTRY_COMPARE_WITH_TIMEOUT(m_serveur->compter("GET", route), lectures + 2, 5000);
    m_serveur->envoyerFlux(QByteArrayLiteral("id: 1727791200.50\nevent: changement\ndata: {\"sujets\":[\"quotas\"]}\n\n"));
    QTest::qWait(700);
    QCOMPARE(m_serveur->compter("GET", route), lectures + 2); // sujet que la file ne suit pas
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));

    // Verdict oublié (serveur changé, session perdue) : le flux se ferme, la page revient au sondage.
    page.reset();
    QTRY_VERIFY(!m_questions->actif());
    compatibilite->oublier();
    QTRY_COMPARE_WITH_TIMEOUT(m_serveur->clientsFlux(), 0, 5000);
    QVERIFY(!m_flux->tempsReel());
    QVERIFY(m_flux->etatFlux().startsWith(QStringLiteral("Inconnu")));
    // Hors temps réel, le sondage habituel est dit.
    QCOMPARE(m_projets->property("cadence").toString(),
             QStringLiteral("Sans temps réel : page relue toutes les 15 secondes tant qu'elle est affichée."));
    QCOMPARE(m_application->findChild<QuotasViewModel *>()->property("cadence").toString(),
             QStringLiteral("Sans temps réel : page relue toutes les 60 secondes tant qu'elle est affichée."));
    // Seconde relecture de P8b (constat desktop-8) : sans verdict, l'Accueil agrégé ne se lit pas, et sa cadence le dit.
    QCOMPARE(accueil->property("cadence").toString(),
             QStringLiteral("Accueil agrégé non lu (voir ci-dessous) ; discussions récentes et carte Hermes relues toutes les "
                            "15 secondes tant que la page est affichée."));
    // Verdict d'un greffon de P7 sans flux annoncé : sondage habituel de toutes les lectures de l'Accueil.
    compatibilite->appliquerLecture(fixture(QStringLiteral("meta.json")));
    QCOMPARE(accueil->property("cadence").toString(),
             QStringLiteral("Sans temps réel : Accueil, bilan quotidien, discussions récentes et carte Hermes relus toutes "
                            "les 15 secondes tant que la page est affichée."));
}

// Relecture de P8b (constat desktop-5) : le nom accessible de la pastille de la file Questions disait toujours
// « (discussions non comptées) », même quand le total comptait déjà les discussions en attente.
void TestPagesInteractions::pastilleDesQuestionsDitCeQuElleCompte()
{
    auto *passerelle = m_application->findChild<GatewayClient *>();
    QVERIFY(passerelle);
    m_serveur->methodes.insert(QStringLiteral("session.active_list"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{QJsonObject{
            {QStringLiteral("id"), QStringLiteral("rt-s1")}, {QStringLiteral("session_key"), QStringLiteral("s1")},
            {QStringLiteral("status"), QStringLiteral("waiting")}, {QStringLiteral("title"), QStringLiteral("Plan du site")}}}}};
    });
    if (passerelle->etat() != GatewayClient::Etat::Pret) {
        passerelle->ouvrir();
        QTRY_COMPARE_WITH_TIMEOUT(passerelle->etat(), GatewayClient::Etat::Pret, 10000);
    }
    m_flux->noterAccueil(fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object());
    m_flux->discussions()->lire();
    QTRY_VERIFY_WITH_TIMEOUT(m_flux->discussions()->connues(), 5000);
    QCOMPARE(m_flux->discussions()->nombre(), 1);

    auto barre = charger(QStringLiteral("SideNavigation"), QStringLiteral("Acp.Station"));
    QVERIFY(barre);
    QQuickItem *entree = parNom(qobject_cast<QQuickItem *>(barre.get()), QStringLiteral("navigation-questions"));
    QVERIFY(entree);
    const auto nom = [entree] { return QQmlProperty(entree, QStringLiteral("Accessible.name"), qmlContext(entree)).read().toString(); };
    // Discussions lues : le total les compte, le nom ne dit plus le contraire.
    QTRY_COMPARE(nom(), QStringLiteral("Questions (%1 demandes à traiter par vous)").arg(m_flux->aTraiter()));
    // Discussions inconnues (passerelle indisponible, refus) : le nom le dit.
    m_flux->discussions()->oublier();
    QTRY_COMPARE(nom(), QStringLiteral("Questions (%1 demandes à traiter par vous (discussions non comptées))")
                            .arg(m_flux->aTraiter()));
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
}

// Seconde relecture de P8b (constat desktop-8), composition réelle et vraies pages : face à un greffon de P5 ou P6 (même
// contrat acp-poste/1, verdict « Compatible », clé `accueil` absente de /v1/meta), l'Accueil n'affichait qu'un 404, le
// badge restait « Inconnu », et « Clore » et « Qui répond » étaient offerts puis refusés en 404. Désormais : rien de
// /v1/accueil ne part, l'Accueil et le badge disent « Non disponible sur ce serveur », les deux boutons sont absents et
// le détail dit pourquoi ; tout revient avec l'annonce.
void TestPagesInteractions::greffonSansEtapeP7NiAccueilNiGestes()
{
    auto *compatibilite = m_application->findChild<CompatibiliteHermes *>();
    QVERIFY(compatibilite);
    QJsonObject metaP6 = fixture(QStringLiteral("meta.json"));
    metaP6.remove(QStringLiteral("accueil"));
    // L'Accueil relit /v1/meta avec la page : il y lit le même greffon de P6.
    m_serveur->route("GET", kP + QStringLiteral("/meta"), [metaP6](const RequeteRecue &) { return ReponseFaux::json(200, metaP6); });
    compatibilite->appliquerLecture(metaP6);
    QCOMPARE(compatibilite->etat(), CompatibilityStatus::Compatible);
    QCOMPARE(m_flux->etapeP7(), QStringLiteral("absent"));
    const QString accueil = kP + QStringLiteral("/accueil");
    const int lecturesAccueil = m_serveur->compter("GET", accueil);

    auto pageAccueil = charger(QStringLiteral("HomePage"));
    QVERIFY(pageAccueil);
    auto *racineAccueil = qobject_cast<QQuickItem *>(pageAccueil.get());
    QQuickItem *disponibilite = parNom(racineAccueil, QStringLiteral("accueil-disponibilite"));
    QVERIFY(disponibilite);
    QTRY_VERIFY(disponibilite->isVisible());
    QVERIFY2(disponibilite->property("text").toString().startsWith(
                 QStringLiteral("Accueil agrégé : Non disponible sur ce serveur : le greffon acp-poste n'annonce pas l'étape P7")),
             qPrintable(disponibilite->property("text").toString()));
    QVERIFY(!parNom(racineAccueil, QStringLiteral("accueil-carte-a-traiter"))->isVisible());
    QTRY_VERIFY_WITH_TIMEOUT(m_serveur->compter("GET", kP + QStringLiteral("/meta")) > 0, 5000); // la carte Hermes relit
    QTest::qWait(300);
    QCOMPARE(m_serveur->compter("GET", accueil), lecturesAccueil); // ni la page ni le badge
    QCOMPARE(m_flux->libelleATraiter(), QStringLiteral("À traiter par vous : Non disponible sur ce serveur"));
    pageAccueil.reset();

    auto pageProjets = charger(QStringLiteral("ProjectsPage"));
    QVERIFY(pageProjets);
    auto *racine = qobject_cast<QQuickItem *>(pageProjets.get());
    m_projets->ouvrirProjet(QStringLiteral("p_367e23fd51b7"));
    QTRY_VERIFY_WITH_TIMEOUT(m_projets->detailLu(), 5000);
    QTest::qWait(150);
    QQuickItem *raison = parNom(racine, QStringLiteral("projet-gestes-p7"));
    QVERIFY(raison && raison->isVisible());
    QVERIFY2(raison->property("text").toString().startsWith(
                 QStringLiteral("« Qui répond » et « Clore le projet » : Non disponible sur ce serveur")),
             qPrintable(raison->property("text").toString()));
    QVERIFY(!cliquer(parNom(racine, QStringLiteral("projets-clore"))));
    QVERIFY(!cliquer(parNom(racine, QStringLiteral("projets-changer-reponses"))));
    const int clotures = m_serveur->compter("POST", kP + QStringLiteral("/projets/p_367e23fd51b7/clore"));
    const int reglages = m_serveur->compter("POST", kP + QStringLiteral("/projets/p_367e23fd51b7/reponses"));

    // Le greffon redéployé en P7 : les boutons reviennent, sans relecture du détail, et la raison disparaît.
    QJsonObject metaP7 = fixture(QStringLiteral("meta.json"));
    m_serveur->route("GET", kP + QStringLiteral("/meta"), [metaP7](const RequeteRecue &) { return ReponseFaux::json(200, metaP7); });
    compatibilite->appliquerLecture(metaP7);
    QTRY_VERIFY(parNom(racine, QStringLiteral("projets-clore"))->isVisible());
    QVERIFY(parNom(racine, QStringLiteral("projets-changer-reponses"))->isVisible());
    QVERIFY(!raison->isVisible());
    QCOMPARE(m_serveur->compter("POST", kP + QStringLiteral("/projets/p_367e23fd51b7/clore")), clotures);
    QCOMPARE(m_serveur->compter("POST", kP + QStringLiteral("/projets/p_367e23fd51b7/reponses")), reglages);
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    m_projets->afficherListe();
    pageProjets.reset();
    QTRY_VERIFY(!m_projets->actif());
    // Comme avant ce test pour la suite (aucune route /v1/meta servie).
    m_serveur->route("GET", kP + QStringLiteral("/meta"), [](const RequeteRecue &) {
        return ReponseFaux::json(404, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Not Found")}});
    });
}

// Étape P8b : la file Questions liste les discussions en attente lues par la passerelle
// (`session.active_list`) ; « Ouvrir la discussion » (vrai clic) reprend la session par sa clé
// stockée dans la page Discussion.
void TestPagesInteractions::discussionEnAttenteOuverteParLeBouton()
{
    auto *passerelle = m_application->findChild<GatewayClient *>();
    auto *navigation = m_application->findChild<NavigationModel *>();
    QVERIFY(passerelle && navigation);
    m_serveur->methodes.insert(QStringLiteral("session.active_list"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{
            QJsonObject{{QStringLiteral("id"), QStringLiteral("rt-s1")}, {QStringLiteral("session_key"), QStringLiteral("s1")},
                        {QStringLiteral("status"), QStringLiteral("waiting")}, {QStringLiteral("title"), QStringLiteral("Plan du site")},
                        {QStringLiteral("preview"), QStringLiteral("Quel nom de domaine ?")},
                        {QStringLiteral("last_active"), 1790451615}, {QStringLiteral("started_at"), 1790450000},
                        {QStringLiteral("message_count"), 4}, {QStringLiteral("model"), QStringLiteral("modele")},
                        {QStringLiteral("current"), false}},
            QJsonObject{{QStringLiteral("id"), QStringLiteral("rt-s2")}, {QStringLiteral("session_key"), QStringLiteral("s2")},
                        {QStringLiteral("status"), QStringLiteral("idle")}, {QStringLiteral("title"), QStringLiteral("Autre")},
                        {QStringLiteral("preview"), QString()}, {QStringLiteral("last_active"), 1790451615},
                        {QStringLiteral("started_at"), 1790450000}, {QStringLiteral("message_count"), 1},
                        {QStringLiteral("model"), QStringLiteral("modele")}, {QStringLiteral("current"), false}}}}};
    });
    if (passerelle->etat() != GatewayClient::Etat::Pret) {
        passerelle->ouvrir();
        QTRY_COMPARE_WITH_TIMEOUT(passerelle->etat(), GatewayClient::Etat::Pret, 10000);
    }
    auto page = charger(QStringLiteral("QuestionsPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    QTRY_VERIFY_WITH_TIMEOUT(m_questions->discussions().value(QStringLiteral("connues")).toBool(), 5000);
    QTest::qWait(100);
    // Seule la discussion en attente est listée, et le total la compte.
    QVERIFY(parNom(racine, QStringLiteral("questions-discussion-s1")));
    QVERIFY(!parNom(racine, QStringLiteral("questions-discussion-s2")));
    QCOMPARE(m_questions->resume().value(QStringLiteral("mention")).toString(), QString());

    const int reprises = static_cast<int>(m_serveur->tramesDeMethode(QStringLiteral("session.resume")).size());
    QVERIFY(cliquer(parNom(racine, QStringLiteral("questions-ouvrir-discussion-s1"))));
    QTRY_COMPARE(navigation->currentRoute(), QStringLiteral("chat"));
    QTRY_COMPARE_WITH_TIMEOUT(static_cast<int>(m_serveur->tramesDeMethode(QStringLiteral("session.resume")).size()), reprises + 1, 5000);
    QCOMPARE(m_serveur->tramesDeMethode(QStringLiteral("session.resume")).constLast().value(QStringLiteral("params")).toObject()
                 .value(QStringLiteral("session_id")).toString(),
             QStringLiteral("s1"));
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    page.reset();
    QTRY_VERIFY(!m_questions->actif());
}

// Seconde relecture de P8b (constat desktop-11), vraie page Discussion : la discussion dont une demande attend porte la
// marque « En attente d'une réponse » (comme Liste.tsx), son nom accessible le dit ; état d'attente illisible : aucune
// marque, et la page dit que l'absence de marque ne veut rien dire.
void TestPagesInteractions::discussionEnAttenteMarqueeDansLaListe()
{
    auto *passerelle = m_application->findChild<GatewayClient *>();
    auto *discussion = m_application->findChild<DiscussionViewModel *>();
    QVERIFY(passerelle && discussion);
    m_serveur->methodes.insert(QStringLiteral("session.active_list"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{QJsonObject{
            {QStringLiteral("session_key"), QStringLiteral("s1")}, {QStringLiteral("status"), QStringLiteral("waiting")},
            {QStringLiteral("title"), QStringLiteral("Plan du site")}}}}};
    });
    if (passerelle->etat() != GatewayClient::Etat::Pret) {
        passerelle->ouvrir();
        QTRY_COMPARE_WITH_TIMEOUT(passerelle->etat(), GatewayClient::Etat::Pret, 10000);
    }
    auto page = charger(QStringLiteral("DiscussionPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    QTRY_COMPARE_WITH_TIMEOUT(discussion->sessions()->count(), 1, 5000);
    QTRY_VERIFY_WITH_TIMEOUT(parNom(racine, QStringLiteral("discussion-en-attente-s1")), 5000);
    QQuickItem *marque = parNom(racine, QStringLiteral("discussion-en-attente-s1"));
    QTRY_VERIFY(marque->isVisible());
    QCOMPARE(marque->property("label").toString(), QStringLiteral("En attente d'une réponse"));
    QQuickItem *ligne = marque->parentItem() ? marque->parentItem()->parentItem() : nullptr;
    QVERIFY(ligne);
    QCOMPARE(QQmlProperty(ligne, QStringLiteral("Accessible.name"), qmlContext(ligne)).read().toString(),
             QStringLiteral("Ouvrir la discussion « Plan du site », en attente d'une réponse"));
    QQuickItem *inconnue = parNom(racine, QStringLiteral("discussion-attente-inconnue"));
    QVERIFY(inconnue && !inconnue->isVisible());

    m_serveur->methodes.remove(QStringLiteral("session.active_list"));
    discussion->actualiserSessions();
    QTRY_VERIFY_WITH_TIMEOUT(inconnue->isVisible(), 5000);
    QVERIFY2(inconnue->property("text").toString().endsWith(
                 QStringLiteral("l'absence de la marque « En attente d'une réponse » ne veut rien dire.")),
             qPrintable(inconnue->property("text").toString()));
    QTRY_VERIFY(!marque->isVisible());
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    page.reset();
}

// Constat de relecture P8 : la liste des projets remontait en haut à chaque relecture.
void TestPagesInteractions::listeDesProjetsGardeSonDefilement()
{
    m_fenetre->resize(1280, 520);
    auto page = charger(QStringLiteral("ProjectsPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    QTRY_COMPARE_WITH_TIMEOUT(m_projets->projets()->count(), 6, 5000);
    QTest::qWait(200);
    QQuickItem *liste = parNom(racine, QStringLiteral("projets-liste"));
    QVERIFY(liste);
    const double maximum = liste->property("contentHeight").toDouble() - liste->height();
    QVERIFY2(maximum > 200, "la liste doit dépasser la fenêtre");
    liste->setProperty("contentY", maximum);
    QTest::qWait(100);
    const double pose = liste->property("contentY").toDouble();
    QVERIFY(pose > 200);

    // Relecture (bouton « Actualiser » de la page, clic réel), puis un projet modifié : la
    // liste ne remonte pas.
    const int lectures = m_serveur->compter("GET", kP + QStringLiteral("/projets"));
    QJsonArray projets = m_listeProjets.value(QStringLiteral("projets")).toArray();
    QJsonObject dernier = projets.last().toObject();
    dernier.insert(QStringLiteral("titre"), QStringLiteral("Projet d'essai 6, renommé"));
    projets.replace(projets.size() - 1, dernier);
    m_listeProjets.insert(QStringLiteral("projets"), projets);
    QVERIFY(cliquer(parNom(racine, QStringLiteral("projets-actualiser"))));
    QTRY_VERIFY_WITH_TIMEOUT(m_serveur->compter("GET", kP + QStringLiteral("/projets")) > lectures, 5000);
    QTRY_COMPARE_WITH_TIMEOUT(m_projets->projets()->itemAt(5).value(QStringLiteral("titre")).toString(),
                              QStringLiteral("Projet d'essai 6, renommé"), 5000);
    QTest::qWait(200);
    QCOMPARE(liste->property("contentY").toDouble(), pose);
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    page.reset();
    m_fenetre->resize(1280, 850);
    QTRY_VERIFY(!m_projets->actif());
}

// Constat de relecture P8 : aucune preuve ne passait par les contrôles de la Discussion. Le
// message est tapé au clavier puis envoyé par le bouton « Envoyer », puis par Ctrl+Entrée.
void TestPagesInteractions::messageEnvoyeParLeBoutonDeLaDiscussion()
{
    auto *passerelle = m_application->findChild<GatewayClient *>();
    auto *discussion = m_application->findChild<DiscussionViewModel *>();
    QVERIFY(passerelle && discussion);
    passerelle->ouvrir();
    QTRY_COMPARE_WITH_TIMEOUT(passerelle->etat(), GatewayClient::Etat::Pret, 10000);
    auto page = charger(QStringLiteral("DiscussionPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    QTRY_VERIFY_WITH_TIMEOUT(discussion->sessionsLues(), 5000);
    discussion->ouvrir(QStringLiteral("s1"));
    QTRY_COMPARE_WITH_TIMEOUT(discussion->sessionVivante(), QStringLiteral("rt-s1"), 5000);
    QTest::qWait(100);

    QQuickItem *saisie = parNom(racine, QStringLiteral("discussion-saisie"));
    QVERIFY(saisie);
    QVERIFY(taper(saisie, QStringLiteral("Fais le plan du site")));
    QVERIFY(cliquer(parNom(racine, QStringLiteral("discussion-envoyer"))));
    QTRY_COMPARE_WITH_TIMEOUT(m_serveur->tramesDeMethode(QStringLiteral("prompt.submit")).size(), 1, 5000);
    QCOMPARE(m_serveur->tramesDeMethode(QStringLiteral("prompt.submit")).constFirst().value(QStringLiteral("params")).toObject(),
             (QJsonObject{{QStringLiteral("session_id"), QStringLiteral("rt-s1")},
                          {QStringLiteral("text"), QStringLiteral("Fais le plan du site")}}));
    QCOMPARE(saisie->property("text").toString(), QString()); // parti : le champ se vide

    // Ctrl+Entrée dans le champ : même envoi.
    QTRY_VERIFY_WITH_TIMEOUT(!discussion->gesteEnCours(), 5000);
    QVERIFY(taper(saisie, QStringLiteral("Et le budget")));
    QTest::keyClick(m_fenetre.get(), Qt::Key_Return, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(m_serveur->tramesDeMethode(QStringLiteral("prompt.submit")).size(), 2, 5000);
    QCOMPARE(m_serveur->tramesDeMethode(QStringLiteral("prompt.submit")).constLast().value(QStringLiteral("params")).toObject()
                 .value(QStringLiteral("text")).toString(),
             QStringLiteral("Et le budget"));
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    page.reset();
    discussion->quitter();
    passerelle->fermer();
}

// Constat de relecture P8 : le dialogue « Changer de serveur ? » affichait « Cancel » (boutons
// standard de Qt, sans traducteur). Ouvert par un clic réel, il n'a que des libellés français ;
// « Annuler » le ferme sans rien changer.
void TestPagesInteractions::dialogueDeChangementDeServeurEnFrancais()
{
    auto page = charger(QStringLiteral("SettingsPage"));
    QVERIFY(page);
    auto *racine = qobject_cast<QQuickItem *>(page.get());
    QVERIFY(cliquer(parNom(racine, QStringLiteral("reglages-changer-serveur"))));
    QObject *dialogue = page->findChild<QObject *>(QStringLiteral("reglages-changer-serveur-confirmation"));
    QVERIFY(dialogue);
    QTRY_VERIFY(dialogue->property("opened").toBool());
    QStringList textes;
    QList<QQuickItem *> elements;
    for (const char *partie : {"header", "contentItem", "footer"}) {
        tous(dialogue->property(partie).value<QQuickItem *>(), elements);
    }
    for (QQuickItem *element : std::as_const(elements)) {
        if (!element->isVisible()) {
            continue;
        }
        for (const char *nom : {"text", "label", "title"}) {
            const QString texte = element->property(nom).toString();
            if (!texte.isEmpty()) {
                textes.append(texte);
            }
        }
    }
    const QString tout = textes.join(QStringLiteral(" | "));
    QVERIFY2(tout.contains(QStringLiteral("Annuler")) && tout.contains(QStringLiteral("Changer de serveur")), qPrintable(tout));
    for (const QString &anglais : {QStringLiteral("Cancel"), QStringLiteral("OK")}) {
        QVERIFY2(!QRegularExpression(QStringLiteral("\\b%1\\b").arg(anglais)).match(tout).hasMatch(), qPrintable(tout));
    }
    const QUrl avant = m_client->baseUrl();
    QVERIFY(cliquer(parNom(dialogue->property("contentItem").value<QQuickItem *>(),
                           QStringLiteral("reglages-changer-serveur-annuler"))));
    QTRY_VERIFY(!dialogue->property("opened").toBool());
    QCOMPARE(m_client->baseUrl(), avant);
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    page.reset();
}

// Constat de relecture P8 : la commande de palette « Copier le rapport de diagnostic »
// annonçait une copie sans rien écrire dans le presse-papiers.
void TestPagesInteractions::copieDuRapportParLaPalette()
{
    auto *registre = m_application->findChild<CommandRegistry *>();
    QVERIFY(registre);
    QClipboard *presse = QGuiApplication::clipboard(); // presse-papiers de la plateforme hors écran
    presse->setText(QStringLiteral("SENTINELLE-AVANT"));
    const QString message = registre->execute(QStringLiteral("diagnostics.copyReport"));
    QCOMPARE(message, QStringLiteral("Rapport de diagnostic copié dans le presse-papiers (valeurs sensibles expurgées)."));
    QVERIFY2(presse->text().contains(QStringLiteral("== Station ==")), qPrintable(presse->text().left(80)));
    QVERIFY(presse->text().contains(QStringLiteral("Version de la station")));
    QVERIFY(!presse->text().contains(QStringLiteral("jeton-a"))); // expurgé, jamais le porteur
}

// Constat de relecture P8 : la palette affichait Ctrl+6 à Ctrl+9, qu'aucun Shortcut n'installait.
// Chaque raccourci DÉCLARÉ au registre, pressé au clavier sur la vraie fenêtre racine, exécute sa
// commande (les commandes de navigation changent la route affichée).
void TestPagesInteractions::chaqueRaccourciDeLaPaletteAgit()
{
    auto *registre = m_application->findChild<CommandRegistry *>();
    auto *navigation = m_application->findChild<NavigationModel *>();
    auto *coquille = m_application->findChild<ShellViewModel *>();
    QVERIFY(registre && navigation && coquille);
    m_fenetre->hide();
    m_avertissements.clear();
    QVERIFY(m_application->load(m_moteur.get()));
    auto *racine = qobject_cast<QQuickWindow *>(m_moteur->rootObjects().constLast());
    QVERIFY(racine);
    racine->requestActivate();
    QVERIFY(QTest::qWaitForWindowActive(racine));

    const QStringList raccourcis = registre->raccourcis();
    for (const QString &attendu : {QStringLiteral("Ctrl+1"), QStringLiteral("Ctrl+2"), QStringLiteral("Ctrl+3"),
                                   QStringLiteral("Ctrl+4"), QStringLiteral("Ctrl+5"), QStringLiteral("Ctrl+6"),
                                   QStringLiteral("Ctrl+7"), QStringLiteral("Ctrl+8"), QStringLiteral("Ctrl+9"),
                                   QStringLiteral("Ctrl+K"), QStringLiteral("Ctrl+R")}) {
        QVERIFY2(raccourcis.contains(attendu), qPrintable(attendu));
    }
    const QHash<QString, QString> routes = {
        {QStringLiteral("navigation.home"), QStringLiteral("home")},
        {QStringLiteral("navigation.diagnostics"), QStringLiteral("diagnostics")},
        {QStringLiteral("navigation.projects"), QStringLiteral("projects")},
        {QStringLiteral("navigation.questions"), QStringLiteral("questions")},
        {QStringLiteral("navigation.chat"), QStringLiteral("chat")},
        {QStringLiteral("navigation.station"), QStringLiteral("station")},
        {QStringLiteral("navigation.quotas"), QStringLiteral("quotas")},
        {QStringLiteral("navigation.routing"), QStringLiteral("routing")},
        {QStringLiteral("navigation.backup"), QStringLiteral("backup")},
    };
    QSignalSpy executees(registre, &CommandRegistry::commandExecuted);
    for (const QString &raccourci : raccourcis) {
        const QString commande = registre->commandForShortcut(raccourci);
        executees.clear();
        QTest::keySequence(racine, QKeySequence(raccourci));
        QTRY_VERIFY2(!executees.isEmpty(), qPrintable(raccourci + QStringLiteral(" n'exécute rien")));
        QCOMPARE(executees.constFirst().at(0).toString(), commande);
        if (routes.contains(commande)) {
            QCOMPARE(navigation->currentRoute(), routes.value(commande));
        }
        coquille->setCommandPaletteOpen(false);
        QTest::qWait(20);
    }
    QVERIFY2(m_avertissements.isEmpty(), qPrintable(m_avertissements.join(QLatin1Char('\n'))));
    racine->close();
}

QTEST_MAIN(TestPagesInteractions)
#include "tst_pages_interactions.moc"
