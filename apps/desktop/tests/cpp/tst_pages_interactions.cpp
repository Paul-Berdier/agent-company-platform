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
#include "gateway/GatewayClient.h"
#include "models/JsonListModel.h"
#include "navigation/NavigationModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/DiscussionViewModel.h"
#include "viewmodels/ProjetsViewModel.h"
#include "viewmodels/QuestionsViewModel.h"
#include "viewmodels/ShellViewModel.h"

#include <QClipboard>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QKeySequence>
#include <QJsonArray>
#include <QPointer>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickWindow>
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
    void listeDesProjetsGardeSonDefilement();
    void messageEnvoyeParLeBoutonDeLaDiscussion();
    void copieDuRapportParLaPalette();
    // En dernier : charge la fenêtre racine (App.qml).
    void chaqueRaccourciDeLaPaletteAgit();

private:
    std::unique_ptr<QObject> charger(const QString &nom);
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

std::unique_ptr<QObject> TestPagesInteractions::charger(const QString &nom)
{
    m_avertissements.clear();
    QQmlComponent composant(m_moteur.get());
    composant.loadFromModule(QStringLiteral("Acp.Pages"), nom);
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
