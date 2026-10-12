// Catalogue HTTP authentifié, distinction texte/runtime, invalidation et actions locales.
#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "support/FauxHermes.h"
#include "viewmodels/CatalogueViewModel.h"

#include <QDate>
#include <QFile>
#include <QJsonDocument>
#include <QSet>
#include <QTest>

using namespace acp;
using namespace acp::test;
namespace {
const QString kCatalogue = QStringLiteral("/api/plugins/acp-poste/v1/catalogue");
QJsonObject document()
{
    // Chaînes ordinaires : moc 6.8 ne repère pas Q_OBJECT après ce JSON en littéral brut.
    return QJsonDocument::fromJson(
        "{"
        "      \"sources\":{\"test/source\":{\"url\":\"https://github.com/test/source\",\"commit\":\"abc\",\"licence\":\"MIT\"}},"
        "      \"skills\":["
        "        {\"nom\":\"analyse\",\"source\":\"test/source\",\"cible\":\"hermes\",\"etat\":\"active\",\"profils\":[\"web\"],\"description_fr\":\"Analyse de code\"},"
        "        {\"nom\":\"archive\",\"source\":\"test/source\",\"cible\":\"hermes\",\"etat\":\"absente\",\"profils\":[],\"description_fr\":\"Texte absent\"}],"
        "      \"mcp\":[{\"nom\":\"context7\",\"cible\":\"hermes\",\"etat\":\"actif\",\"connexion\":\"inconnu\",\"url\":\"https://mcp.context7.com/mcp\",\"transport\":\"http\",\"outils_hermes\":[\"query-docs\"]}],"
        "      \"profils\":{\"web\":{\"skills_poste\":[\"analyse\"]}},\"alertes\":[]"
        "    }").object();
}
QJsonObject parId(const QJsonArray &lignes, const QString &id)
{
    for (const auto &v : lignes) if (v.toObject().value(QStringLiteral("id")) == id) return v.toObject();
    return {};
}
QJsonArray registre()
{
    QFile fichier(QStringLiteral(":/integrations/sources.json"));
    if (!fichier.open(QIODevice::ReadOnly)) return {};
    return QJsonDocument::fromJson(fichier.readAll()).object().value(QStringLiteral("sources")).toArray();
}
struct Banc {
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    CatalogueViewModel catalogue{&greffon, &flux};
    QJsonObject courant = document();
    int statut = 200;
    int delai = 0;
    Banc()
    {
        serveur.installerAuthentification();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) qFatal("URL du faux Hermes refusée");
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
        flux.setIntervalleFond(std::chrono::hours(1));
        serveur.route("GET", kCatalogue, [this](const RequeteRecue &) {
            auto reponse = ReponseFaux::json(statut, courant);
            reponse.delaiMs = delai;
            return reponse;
        });
    }
    void ouvrir() { flux.demarrer(); catalogue.setPageVisible(true); }
};
}

class TestCatalogue : public QObject {
    Q_OBJECT
private slots:
    void registreEpingleSansPromesseDeConnexion();
    void distingueTextesEtConnexionMcp();
    void ignoreIdentifiantsInvalidesEtDoublons();
    void liensHttpsSansIdentifiantsNiParametres();
    void litUniquementAvecSessionEtPageVisible();
    void rechercheEtFiltresSansRequeteSupplementaire();
    void erreurEtSchemaInvalideGardentLaLectureAcceptee();
    void oubliAbandonneLaLectureEnVol();
    void consigneSeulementPourUneSkillConfirmee();
    void gestesLocauxSansInstallationNiEnvoi();
};

void TestCatalogue::registreEpingleSansPromesseDeConnexion()
{
    const auto sources = registre();
    QVERIFY(!sources.isEmpty());
    QSet<QString> identifiants;
    for (const auto &v : sources) {
        const auto s = v.toObject();
        const QString id = s.value(QStringLiteral("id")).toString();
        QVERIFY(!id.isEmpty());
        QVERIFY(!identifiants.contains(id));
        identifiants.insert(id);
        QVERIFY(CatalogueViewModel::urlSourceAdmise(QUrl(s.value(QStringLiteral("url")).toString())));
        QVERIFY(CatalogueViewModel::urlSourceAdmise(QUrl(s.value(QStringLiteral("licenceUrl")).toString())));
        if (s.value(QStringLiteral("reference")) == QLatin1String("documentation-officielle")) {
            QVERIFY(s.value(QStringLiteral("commit")).toString().isEmpty());
            QVERIFY(QDate::fromString(s.value(QStringLiteral("date_consultation")).toString(), Qt::ISODate).isValid());
            QVERIFY(CatalogueViewModel::urlSourceAdmise(QUrl(s.value(QStringLiteral("documentationUrl")).toString())));
        } else QCOMPARE(s.value(QStringLiteral("commit")).toString().size(), 40);
        QVERIFY(!s.value(QStringLiteral("configuration")).toString().isEmpty());
    }
    for (const QString &id : {QStringLiteral("crm"), QStringLiteral("rea"), QStringLiteral("dtk"),
         QStringLiteral("ml-intern"), QStringLiteral("hackingtool"), QStringLiteral("ponytail"),
         QStringLiteral("graphify"), QStringLiteral("addy"), QStringLiteral("omniroute"), QStringLiteral("obsidian")})
        QVERIFY2(identifiants.contains(id), qPrintable(id));
    const auto lignes = CatalogueViewModel::construireEntrees({}, sources);
    QCOMPARE(parId(lignes, QStringLiteral("integration:crm")).value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("À configurer"));
    QCOMPARE(parId(lignes, QStringLiteral("integration:addy")).value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Textes non confirmés"));
    QCOMPARE(parId(lignes, QStringLiteral("integration:ml-intern")).value(QStringLiteral("etat")).toString(), QStringLiteral("archive"));
    QCOMPARE(parId(lignes, QStringLiteral("integration:hackingtool")).value(QStringLiteral("etat")).toString(), QStringLiteral("reference"));
    QCOMPARE(parId(lignes, QStringLiteral("integration:obsidian")).value(QStringLiteral("etat")).toString(), QStringLiteral("a-verifier"));
    QVERIFY(!parId(lignes, QStringLiteral("integration:obsidian")).value(QStringLiteral("peutConsigne")).toBool());
    auto d = document();
    auto skills = d.value(QStringLiteral("skills")).toArray();
    auto skill = skills.first().toObject();
    skill.insert(QStringLiteral("source"), QStringLiteral("addyosmani/agent-skills"));
    skills.replace(0, skill); d.insert(QStringLiteral("skills"), skills);
    const auto associes = CatalogueViewModel::construireEntrees(d, sources);
    QCOMPARE(parId(associes, QStringLiteral("integration:addy")).value(QStringLiteral("etat")).toString(), QStringLiteral("textes-charges"));
    QCOMPARE(parId(associes, QStringLiteral("integration:crm")).value(QStringLiteral("etat")).toString(), QStringLiteral("a-configurer"));
}
void TestCatalogue::distingueTextesEtConnexionMcp()
{
    auto d = document();
    auto lignes = CatalogueViewModel::construireEntrees(d, {});
    QCOMPARE(parId(lignes, QStringLiteral("skill:analyse")).value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Texte chargé"));
    QVERIFY(!parId(lignes, QStringLiteral("skill:archive")).value(QStringLiteral("peutConsigne")).toBool());
    QCOMPARE(parId(lignes, QStringLiteral("mcp:context7")).value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Connexion non confirmée"));
    auto mcp = d.value(QStringLiteral("mcp")).toArray();
    auto serveur = mcp.first().toObject(); serveur.insert(QStringLiteral("connexion"), QStringLiteral("connecte"));
    mcp.replace(0, serveur); d.insert(QStringLiteral("mcp"), mcp);
    lignes = CatalogueViewModel::construireEntrees(d, {});
    QCOMPARE(parId(lignes, QStringLiteral("mcp:context7")).value(QStringLiteral("etat")).toString(), QStringLiteral("connecte"));
    serveur.insert(QStringLiteral("cible"), QStringLiteral("poste"));
    mcp.replace(0, serveur); d.insert(QStringLiteral("mcp"), mcp);
    lignes = CatalogueViewModel::construireEntrees(d, {});
    QCOMPARE(parId(lignes, QStringLiteral("mcp:context7")).value(QStringLiteral("etat")).toString(), QStringLiteral("inconnu"));
}
void TestCatalogue::ignoreIdentifiantsInvalidesEtDoublons()
{
    auto d = document(); auto skills = d.value(QStringLiteral("skills")).toArray();
    skills.append(skills.first());
    skills.append(QJsonObject{{QStringLiteral("nom"), QStringLiteral("../secret")}});
    d.insert(QStringLiteral("skills"), skills);
    QCOMPARE(CatalogueViewModel::construireEntrees(d, {}).size(), 3);
    QVERIFY(CatalogueViewModel::catalogueValide(d));
    d.insert(QStringLiteral("mcp"), QStringLiteral("illisible"));
    QVERIFY(!CatalogueViewModel::catalogueValide(d));
    QVERIFY(!CatalogueViewModel::catalogueValide({}));
}
void TestCatalogue::liensHttpsSansIdentifiantsNiParametres()
{
    QVERIFY(CatalogueViewModel::urlSourceAdmise(QUrl(QStringLiteral("https://github.com/test/source"))));
    for (const QString &url : {QStringLiteral("http://github.com/test/source"), QStringLiteral("file:///secret"),
         QStringLiteral("javascript:alert(1)"), QStringLiteral("https://user:pass@example.com/path"),
         QStringLiteral("https://example.com/path?token=secret"), QStringLiteral("https://example.com/#code"),
         QStringLiteral("https://example.com:444/path")})
        QVERIFY2(!CatalogueViewModel::urlSourceAdmise(QUrl(url)), qPrintable(url));
}
void TestCatalogue::litUniquementAvecSessionEtPageVisible()
{
    Banc b;
    b.catalogue.setPageVisible(true); b.catalogue.actualiser();
    QTest::qWait(100);
    QCOMPARE(b.serveur.compter("GET", kCatalogue), 0);
    b.flux.demarrer();
    QTRY_VERIFY(b.catalogue.lue());
    QCOMPARE(b.serveur.compter("GET", kCatalogue), 1);
    const auto r = b.serveur.filtrer("GET", kCatalogue).first();
    QCOMPARE(r.entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
    QVERIFY(!r.aEntete("origin")); QVERIFY(!r.aEntete("cookie")); QVERIFY(r.corps.isEmpty());
    b.catalogue.setPageVisible(false);
    QTRY_VERIFY(!b.catalogue.actif());
    b.catalogue.actualiser(); b.flux.signalerLien(false); b.flux.signalerLien(true);
    QTest::qWait(100);
    QCOMPARE(b.serveur.compter("GET", kCatalogue), 1);
    b.catalogue.setPageVisible(true); QTRY_VERIFY(b.catalogue.actif());
    b.flux.setFenetreActive(false); QTRY_VERIFY(!b.catalogue.actif());
    QTRY_VERIFY(!b.catalogue.chargement());
    const auto avant = b.serveur.compter("GET", kCatalogue);
    b.catalogue.actualiser(); QTest::qWait(100);
    QCOMPARE(b.serveur.compter("GET", kCatalogue), avant);
}
void TestCatalogue::rechercheEtFiltresSansRequeteSupplementaire()
{
    Banc b; b.ouvrir(); QTRY_VERIFY(b.catalogue.lue());
    b.catalogue.setTypeFiltre(QStringLiteral("skills"));
    QCOMPARE(b.catalogue.entrees()->count(), 2);
    b.catalogue.setRecherche(QStringLiteral("ANALYSE web"));
    QCOMPARE(b.catalogue.entrees()->count(), 1);
    b.catalogue.selectionner(QStringLiteral("skill:analyse"));
    QCOMPARE(b.catalogue.selection().value(QStringLiteral("nom")).toString(), QStringLiteral("analyse"));
    b.catalogue.setTypeFiltre(QStringLiteral("invente"));
    QCOMPARE(b.catalogue.typeFiltre(), QStringLiteral("skills"));
    b.catalogue.setRecherche(QStringLiteral("absent"));
    QCOMPARE(b.catalogue.entrees()->count(), 1);
    QCOMPARE(b.catalogue.entrees()->itemAt(0).value(QStringLiteral("id")).toString(), QStringLiteral("skill:archive"));
    QCOMPARE(b.serveur.compter("GET", kCatalogue), 1);
}
void TestCatalogue::erreurEtSchemaInvalideGardentLaLectureAcceptee()
{
    Banc b; b.ouvrir(); QTRY_VERIFY(b.catalogue.lue());
    b.catalogue.selectionner(QStringLiteral("skill:analyse"));
    const auto luA = b.catalogue.lecture();
    b.statut = 503; b.catalogue.actualiser();
    QTRY_VERIFY(!b.catalogue.erreur().isEmpty());
    QCOMPARE(b.catalogue.lecture(), luA);
    QCOMPARE(b.catalogue.selection().value(QStringLiteral("nom")).toString(), QStringLiteral("analyse"));
    QVERIFY(b.catalogue.consignePour(QStringLiteral("skill:analyse")).isEmpty());
    QTest::qWait(1100); // Une réponse mal formée ne doit pas rafraîchir la date de la précédente preuve.
    b.statut = 200; b.courant = {}; b.catalogue.actualiser();
    QTRY_VERIFY(b.catalogue.erreur().startsWith(QStringLiteral("Catalogue illisible")));
    QCOMPARE(b.catalogue.lecture(), luA);
    QCOMPARE(b.catalogue.selection().value(QStringLiteral("nom")).toString(), QStringLiteral("analyse"));
}
void TestCatalogue::oubliAbandonneLaLectureEnVol()
{
    Banc b; b.delai = 200; b.ouvrir();
    QTRY_COMPARE(b.serveur.compter("GET", kCatalogue), 1);
    b.flux.arreter(); b.catalogue.oublier();
    QTest::qWait(350);
    QVERIFY(!b.catalogue.lue()); QVERIFY(b.catalogue.selection().isEmpty());
    QCOMPARE(b.catalogue.lecture(), QStringLiteral("Catalogue serveur non lu"));
    b.catalogue.setTypeFiltre(QStringLiteral("skills"));
    QCOMPARE(b.catalogue.entrees()->count(), 0);
    QVERIFY(b.catalogue.consignePour(QStringLiteral("skill:analyse")).isEmpty());
    b.delai = 0; b.flux.demarrer(); QTRY_VERIFY(b.catalogue.lue());
    QCOMPARE(b.catalogue.entrees()->count(), 2);
}
void TestCatalogue::consigneSeulementPourUneSkillConfirmee()
{
    Banc b;
    QVERIFY(b.catalogue.consignePour(QStringLiteral("skill:analyse")).isEmpty());
    b.ouvrir(); QTRY_VERIFY(b.catalogue.lue());
    QVERIFY(b.catalogue.consignePour(QStringLiteral("skill:analyse")).contains(QStringLiteral("analyse")));
    QVERIFY(b.catalogue.consignePour(QStringLiteral("skill:archive")).isEmpty());
    QVERIFY(b.catalogue.consignePour(QStringLiteral("mcp:context7")).isEmpty());
    QVERIFY(b.catalogue.consignePour(QStringLiteral("arbitraire")).isEmpty());
    b.flux.arreter();
    QVERIFY(b.catalogue.consignePour(QStringLiteral("skill:analyse")).isEmpty());
    const auto preparation = b.catalogue.consignePour(QStringLiteral("integration:crm"));
    QVERIFY(preparation.contains(QStringLiteral("À configurer")));
    QVERIFY(preparation.contains(QStringLiteral("N'installe rien")));
}
void TestCatalogue::gestesLocauxSansInstallationNiEnvoi()
{
    Banc b; QUrl ouverte; QString copie;
    b.catalogue.setOuvreur([&](const QUrl &url) { ouverte = url; return true; });
    b.catalogue.setPressePapier([&](const QString &texte) { copie = texte; return true; });
    QVERIFY(!b.catalogue.ouvrirSource(QStringLiteral("https://example.com")));
    QVERIFY(!b.catalogue.copierConfiguration(QStringLiteral("arbitraire")));
    QVERIFY(b.catalogue.ouvrirSource(QStringLiteral("integration:crm")));
    QCOMPARE(ouverte, QUrl(QStringLiteral("https://github.com/trycompai/crm")));
    QVERIFY(b.catalogue.copierConfiguration(QStringLiteral("integration:crm")));
    QVERIFY(copie.contains(QStringLiteral("POST /rest/contacts/search")));
    QVERIFY(b.catalogue.messageGeste().contains(QStringLiteral("Rien n'a été installé")));
    QVERIFY(b.serveur.requetes.isEmpty());
    b.catalogue.setPressePapier([](const QString &) { return false; });
    QVERIFY(!b.catalogue.copierConfiguration(QStringLiteral("integration:crm")));
    QVERIFY(!b.catalogue.erreurGeste().isEmpty());
}
QTEST_MAIN(TestCatalogue)
#include "tst_catalogue.moc"
