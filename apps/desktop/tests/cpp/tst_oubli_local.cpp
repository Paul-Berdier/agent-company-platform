// Oubli local des pages (docs/desktop-security.md, « oubli local complet ») : à la session
// perdue, au changement de serveur et au blocage du greffon, aucune donnée lue ne reste en
// mémoire ni affichée : modèles vidés, « Jamais lu », brouillons effacés, résumé « Inconnu ».
//
// Composition du produit (Application), contre deux faux Hermes : A sert le greffon, B ne le
// sert pas (404). Porteur fixe, aucune connexion ouverte : aucune entrée de coffre n'est écrite.

#include "api/ApiClient.h"
#include "app/Application.h"
#include "auth/SessionHermes.h"
#include "events/EventStreamService.h"
#include "gateway/DiscussionsEnAttente.h"
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

#include <QCoreApplication>
#include <QJsonArray>
#include <QSettings>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>

#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kJamaisLu = QStringLiteral("Jamais lu");

void servirLeGreffon(FauxHermes &serveur, QJsonObject *meta)
{
    serveur.installerAuthentification();
    serveur.activerPasserelle();
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    serveur.methodes.insert(QStringLiteral("session.list"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{QJsonObject{
            {QStringLiteral("id"), QStringLiteral("s1")}, {QStringLiteral("title"), QStringLiteral("Plan du site")},
            {QStringLiteral("started_at"), 1790300000}, {QStringLiteral("message_count"), 2}}}}};
    });
    const QList<QPair<QString, QString>> routes = {
        {QStringLiteral("/projets"), QStringLiteral("projets.json")}, {QStringLiteral("/questions"), QStringLiteral("questions.json")},
        {QStringLiteral("/poste"), QStringLiteral("poste-en-ligne.json")}, {QStringLiteral("/quotas"), QStringLiteral("quotas.json")},
        {QStringLiteral("/routage"), QStringLiteral("routage.json")}};
    for (const auto &[route, nom] : routes) {
        serveur.route("GET", kP + route, [nom](const RequeteRecue &) { return ReponseFaux::json(200, fixture(nom)); });
    }
    serveur.route("GET", QStringLiteral("/api/sessions"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("sessions.json"))); });
    // Étape P8b : bilan quotidien (route native) et discussions en attente (passerelle).
    serveur.route("GET", QStringLiteral("/api/cron/jobs"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonArray{QJsonObject{{QStringLiteral("script"), QStringLiteral("acp-bilan.py")},
                                                             {QStringLiteral("no_agent"), true}, {QStringLiteral("enabled"), true}}});
    });
    serveur.methodes.insert(QStringLiteral("session.active_list"), [](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("sessions"), QJsonArray{QJsonObject{
            {QStringLiteral("session_key"), QStringLiteral("s1")}, {QStringLiteral("status"), QStringLiteral("waiting")},
            {QStringLiteral("title"), QStringLiteral("Plan du site")}}}}};
    });
    serveur.route("GET", kP + QStringLiteral("/meta"), [meta](const RequeteRecue &) { return ReponseFaux::json(200, *meta); });
    // Accueil agrégé (étape P7) : la fixture partagée avec le greffon et la page web.
    serveur.route("GET", kP + QStringLiteral("/accueil"), [](const RequeteRecue &) {
        return ReponseFaux::json(200, fixturePartagee(QStringLiteral("fixtures_accueil/accueil.json")).object());
    });
}

} // namespace

class TestOubliLocal : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void sessionPerdueOublieToutesLesPages();
    void changementDeServeurNAfficheRienDeLAncien();
    void greffonBloqueOublieSesPages();
    void cleanupTestCase();

private:
    //! Pages affichées, session ouverte : chacune lit A jusqu'au bout.
    void ouvrirEtLireA();
    //! Ce qui reste lu ou affiché, page par page (vide si tout est oublié).
    [[nodiscard]] QStringList donneesRestantes() const;

    QTemporaryDir m_reglages;
    QJsonObject m_metaA;
    std::unique_ptr<FauxHermes> m_a;
    std::unique_ptr<FauxHermes> m_b;
    std::unique_ptr<Application> m_application;
    ApiClient *m_client = nullptr;
    SessionHermes *m_session = nullptr;
    EventStreamService *m_flux = nullptr;
    GatewayClient *m_passerelle = nullptr;
    CompatibiliteHermes *m_compatibilite = nullptr;
    AccueilViewModel *m_accueil = nullptr;
    ProjetsViewModel *m_projets = nullptr;
    QuestionsViewModel *m_questions = nullptr;
    PosteViewModel *m_poste = nullptr;
    QuotasViewModel *m_quotas = nullptr;
    RoutageViewModel *m_routage = nullptr;
    DiscussionViewModel *m_discussion = nullptr;
};

void TestOubliLocal::initTestCase()
{
    QVERIFY(m_reglages.isValid());
    QCoreApplication::setOrganizationName(
        QStringLiteral("ACP Test oubli %1").arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
    QCoreApplication::setApplicationName(QStringLiteral("tst_oubli_local"));
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, m_reglages.path());

    m_metaA = fixture(QStringLiteral("meta.json"));
    m_a = std::make_unique<FauxHermes>();
    servirLeGreffon(*m_a, &m_metaA);
    m_b = std::make_unique<FauxHermes>(); // aucune route du greffon : 404
    m_b->installerAuthentification();
    m_b->jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));

    m_application = std::make_unique<Application>(nullptr, QStringLiteral("AcpTestOubli"));
    m_client = m_application->findChild<ApiClient *>();
    m_session = m_application->findChild<SessionHermes *>();
    m_flux = m_application->findChild<EventStreamService *>();
    m_passerelle = m_application->findChild<GatewayClient *>();
    m_compatibilite = m_application->findChild<CompatibiliteHermes *>();
    m_accueil = m_application->findChild<AccueilViewModel *>();
    m_projets = m_application->findChild<ProjetsViewModel *>();
    m_questions = m_application->findChild<QuestionsViewModel *>();
    m_poste = m_application->findChild<PosteViewModel *>();
    m_quotas = m_application->findChild<QuotasViewModel *>();
    m_routage = m_application->findChild<RoutageViewModel *>();
    m_discussion = m_application->findChild<DiscussionViewModel *>();
    QVERIFY(m_client && m_session && m_flux && m_passerelle && m_compatibilite && m_accueil && m_projets
            && m_questions && m_poste && m_quotas && m_routage && m_discussion);
    m_client->setAllowInsecureLoopback(true);
    m_client->setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
    m_flux->setIntervalleFond(std::chrono::hours(1));
}

void TestOubliLocal::cleanupTestCase()
{
    m_application.reset();
    m_a.reset();
    m_b.reset();
}

void TestOubliLocal::ouvrirEtLireA()
{
    QVERIFY(!m_client->setBaseUrl(m_a->url()).isError());
    m_flux->demarrer();
    m_passerelle->ouvrir();
    QTRY_COMPARE_WITH_TIMEOUT(m_passerelle->etat(), GatewayClient::Etat::Pret, 10000);
    for (PageViewModel *page : std::initializer_list<PageViewModel *>{m_accueil, m_projets, m_questions, m_poste,
                                                                       m_quotas, m_routage, m_discussion}) {
        page->setPageVisible(true);
    }
    QTRY_VERIFY_WITH_TIMEOUT(m_accueil->sessionsLues(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(m_accueil->lue(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(m_projets->listeLue(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(m_questions->lue(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(m_poste->lue(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(m_quotas->lue(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(m_routage->lue(), 10000);
    QTRY_COMPARE_WITH_TIMEOUT(m_discussion->sessions()->count(), 1, 10000);
    QTRY_VERIFY(m_flux->aTraiter() >= 0);
    QTRY_VERIFY_WITH_TIMEOUT(m_accueil->carteBilan().value(QStringLiteral("lu")).toBool(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(m_flux->discussions()->connues(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(m_questions->discussions().value(QStringLiteral("connues")).toBool(), 10000);
    m_questions->setBrouillon(QStringLiteral("q:q_b627a3c245ec"), QStringLiteral("Brouillon tapé sur A"));
    m_routage->appliquerSuggestion(QStringLiteral("exploration"));
    QVERIFY(m_routage->brouillonModifie());
    QVERIFY2(donneesRestantes().size() >= 20, qPrintable(donneesRestantes().join(QStringLiteral(", "))));
}

QStringList TestOubliLocal::donneesRestantes() const
{
    QStringList restes;
    const auto si = [&restes](bool condition, const char *nom) {
        if (condition) {
            restes.append(QString::fromLatin1(nom));
        }
    };
    si(m_accueil->lue(), "accueil.lue");
    si(m_accueil->carteATraiter().value(QStringLiteral("lisible")).toBool(), "accueil.carteATraiter");
    si(m_accueil->projetsEnCours()->count() > 0, "accueil.projetsEnCours");
    si(m_accueil->carteQuotas().value(QStringLiteral("lisible")).toBool(), "accueil.carteQuotas");
    si(m_accueil->sessions()->count() > 0, "accueil.sessions");
    si(m_accueil->sessionsLues(), "accueil.sessionsLues");
    si(m_accueil->lectureAccueil() != kJamaisLu, "accueil.lectureAccueil");
    si(m_accueil->lectureSessions() != kJamaisLu, "accueil.lectureSessions");
    si(m_projets->projets()->count() > 0, "projets.liste");
    si(m_projets->listeLue(), "projets.listeLue");
    si(m_projets->lectureListe() != kJamaisLu, "projets.lectureListe");
    si(m_questions->questions()->count() > 0, "questions.questions");
    si(m_questions->triage()->count() > 0, "questions.triage");
    si(m_questions->bloquees()->count() > 0, "questions.bloquees");
    si(m_questions->lue(), "questions.lue");
    si(m_questions->lecture() != kJamaisLu, "questions.lecture");
    si(m_questions->nombreBrouillons() > 0, "questions.brouillons");
    si(m_poste->lue(), "poste.lue");
    si(m_poste->ordres()->count() > 0, "poste.ordres");
    si(m_poste->lecture() != kJamaisLu, "poste.lecture");
    si(m_quotas->lue(), "quotas.lue");
    si(m_quotas->voies()->count() > 0, "quotas.voies");
    si(m_quotas->lecture() != kJamaisLu, "quotas.lecture");
    si(m_routage->lue(), "routage.lue");
    si(m_routage->listes()->count() > 0, "routage.listes");
    si(m_routage->classes()->count() > 0, "routage.classes");
    si(m_routage->brouillonModifie(), "routage.brouillon");
    si(m_routage->lecture() != kJamaisLu, "routage.lecture");
    si(m_discussion->sessions()->count() > 0, "discussion.sessions");
    si(m_discussion->sessionsLues(), "discussion.sessionsLues");
    si(m_flux->aTraiter() >= 0, "resume.aTraiter");
    si(m_accueil->carteBilan().value(QStringLiteral("lu")).toBool(), "accueil.carteBilan");
    si(m_accueil->lectureBilan() != kJamaisLu, "accueil.lectureBilan");
    si(m_flux->discussions()->connues(), "resume.discussions");
    si(m_questions->discussions().value(QStringLiteral("connues")).toBool(), "questions.discussions");
    return restes;
}

// Constats de relecture P8 : la déconnexion n'effaçait pas les données des pages.
void TestOubliLocal::sessionPerdueOublieToutesLesPages()
{
    ouvrirEtLireA();
    if (QTest::currentTestFailed()) {
        return;
    }
    QVERIFY(QMetaObject::invokeMethod(m_session, "sessionPerdue", Q_ARG(QString, QStringLiteral("Déconnexion d'essai"))));
    QVERIFY2(donneesRestantes().isEmpty(), qPrintable(donneesRestantes().join(QStringLiteral(", "))));
    QTest::qWait(200); // aucune lecture en vol ne republie quoi que ce soit
    QVERIFY2(donneesRestantes().isEmpty(), qPrintable(donneesRestantes().join(QStringLiteral(", "))));
}

// Constat de relecture P8 : après un changement de serveur, les pages gardaient les lignes de
// l'ancien, datées de son « Lu à », à côté de l'erreur du nouveau.
void TestOubliLocal::changementDeServeurNAfficheRienDeLAncien()
{
    ouvrirEtLireA();
    if (QTest::currentTestFailed()) {
        return;
    }
    // Une lecture de A en vol au moment du changement : sa réponse ne doit jamais arriver.
    m_a->route("GET", kP + QStringLiteral("/questions"), [](const RequeteRecue &) {
        ReponseFaux reponse = ReponseFaux::json(200, fixture(QStringLiteral("questions.json")));
        reponse.delaiMs = 400;
        return reponse;
    });
    m_questions->actualiser();
    QTest::qWait(50);
    QVERIFY(!m_client->setBaseUrl(m_b->url()).isError());
    QVERIFY2(donneesRestantes().isEmpty(), qPrintable(donneesRestantes().join(QStringLiteral(", "))));
    // Les pages, toujours affichées, relisent : B n'a pas le greffon (404, puis greffon bloqué
    // par le verdict de l'accueil) ; l'erreur s'affiche, rien de A ne revient.
    m_questions->actualiser();
    QTRY_VERIFY_WITH_TIMEOUT(!m_questions->erreur().isEmpty(), 5000);
    QTest::qWait(600);
    QCOMPARE(m_questions->questions()->count(), 0);
    QCOMPARE(m_questions->lecture(), kJamaisLu);
    QVERIFY(!m_questions->lue());
    m_a->route("GET", kP + QStringLiteral("/questions"),
               [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("questions.json"))); });
}

// Greffon bloqué par le verdict de compatibilité (contrat d'une autre majeure) : ses pages
// oublient ce qu'elles en avaient lu, le résumé redevient « Inconnu ».
void TestOubliLocal::greffonBloqueOublieSesPages()
{
    ouvrirEtLireA();
    if (QTest::currentTestFailed()) {
        return;
    }
    m_metaA.insert(QStringLiteral("contrat"), QStringLiteral("acp-poste/2"));
    m_compatibilite->verifier();
    QTRY_COMPARE(m_compatibilite->etat(), CompatibilityStatus::Incompatible);
    QStringList restes = donneesRestantes();
    // La Discussion ne dépend pas du greffon : sa liste reste.
    restes.removeAll(QStringLiteral("discussion.sessions"));
    restes.removeAll(QStringLiteral("discussion.sessionsLues"));
    // Les sessions de l'accueil viennent de /api/sessions (Hermes) : relues aussitôt.
    restes.removeAll(QStringLiteral("accueil.sessions"));
    restes.removeAll(QStringLiteral("accueil.sessionsLues"));
    restes.removeAll(QStringLiteral("accueil.lectureSessions"));
    // Le bilan quotidien vient de /api/cron/jobs (route native de Hermes) : relu aussitôt aussi (carte cachée tant que
    // l'accueil du greffon n'est pas lu).
    restes.removeAll(QStringLiteral("accueil.carteBilan"));
    restes.removeAll(QStringLiteral("accueil.lectureBilan"));
    // Les pages du greffon, encore affichées, essaient de relire : refus de la station, sans
    // donnée ; leur « Lu à » reste « Jamais lu ».
    QVERIFY2(restes.isEmpty(), qPrintable(restes.join(QStringLiteral(", "))));
    QTest::qWait(300);
    restes = donneesRestantes();
    for (const QString &permis : {QStringLiteral("discussion.sessions"), QStringLiteral("discussion.sessionsLues"),
                                  QStringLiteral("accueil.sessions"), QStringLiteral("accueil.sessionsLues"),
                                  QStringLiteral("accueil.lectureSessions"), QStringLiteral("accueil.carteBilan"),
                                  QStringLiteral("accueil.lectureBilan")}) {
        restes.removeAll(permis);
    }
    QVERIFY2(restes.isEmpty(), qPrintable(restes.join(QStringLiteral(", "))));
    // Aucune boucle : l'accueil relit /v1/meta à son rythme (15 s), le verdict republié ne fait
    // pas oublier puis relire les pages en continu.
    const int lecturesMeta = m_a->compter("GET", kP + QStringLiteral("/meta"));
    QTest::qWait(600);
    QVERIFY2(m_a->compter("GET", kP + QStringLiteral("/meta")) - lecturesMeta <= 1,
             qPrintable(QString::number(m_a->compter("GET", kP + QStringLiteral("/meta")) - lecturesMeta)));
    m_metaA.insert(QStringLiteral("contrat"), QString::fromLatin1("acp-poste/1"));
}

QTEST_MAIN(TestOubliLocal)
#include "tst_oubli_local.moc"
