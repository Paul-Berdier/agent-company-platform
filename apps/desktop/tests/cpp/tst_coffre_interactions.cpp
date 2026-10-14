// Gestes sur la vraie page QML : création, conflit, comparaison et navigation du graphe.
// Identité et coffre jetables ; aucune fenêtre personnelle ou instance Obsidian utilisée.
#include "api/ApiClient.h"
#include "app/Application.h"
#include "events/EventStreamService.h"
#include "services/CompatibiliteHermes.h"
#include "support/FauxCoffre.h"
#include "support/Fixtures.h"
#include "viewmodels/ObsidianViewModel.h"
#include <QGuiApplication>
#include <QKeySequence>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickWindow>
#include <QtQuickTest/quicktest.h>
#include <QSettings>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>
#include <algorithm>
#include <memory>
using namespace acp;
using namespace acp::test;
namespace {
QQuickItem *parNom(QQuickItem *racine,const QString &nom)
{
    if (!racine) return nullptr;
    if (racine->objectName()==nom) return racine;
    for (auto *enfant:racine->childItems()) if (auto *trouve=parNom(enfant,nom)) return trouve;
    return nullptr;
}
bool cliquer(QQuickWindow &fenetre,QQuickItem *item)
{
    // Le retour à une note en conflit réaffiche la comparaison et agrandit le
    // contenu. Attendre le layout avant de mesurer la limite de défilement ;
    // un délai fixe après la mesure peut laisser le bouton hors de la fenêtre.
    if (!QQuickTest::qWaitForPolish(&fenetre,2000)) {
        qWarning() << "Mise en page inachevée avant le défilement";
        return false;
    }
    if (!item || !item->isVisible() || !item->isEnabled()) {
        qWarning() << "Clic impossible avant défilement" << (item ? item->objectName() : QStringLiteral("absent"))
                   << "visible" << (item && item->isVisible()) << "actif" << (item && item->isEnabled());
        return false;
    }
    for (auto *parent=item->parentItem();parent;parent=parent->parentItem()) {
        if (!parent->inherits("QQuickFlickable")) continue;
        auto *contenu=parent->property("contentItem").value<QQuickItem *>();
        if (!contenu) continue;
        const double haut=item->mapToItem(contenu,QPointF(0,0)).y();
        const double maximum=std::max(0.0,parent->property("contentHeight").toDouble()-parent->height());
        const double actuel=parent->property("contentY").toDouble();
        if (haut<actuel || haut+item->height()>actuel+parent->height())
            parent->setProperty("contentY",std::clamp(haut-30.0,0.0,maximum));
    }
    if (!QQuickTest::qWaitForPolish(&fenetre,2000)) {
        qWarning() << "Mise en page inachevée après le défilement";
        return false;
    }
    const auto point=item->mapToScene(QPointF(item->width()/2,item->height()/2));
    if (!QRectF(QPointF(0,0),fenetre.size()).contains(point)) {
        qWarning() << "Clic hors fenêtre après défilement" << item->objectName() << "centre" << point << "fenêtre" << fenetre.size();
        for (auto *parent=item->parentItem();parent;parent=parent->parentItem())
            if (parent->inherits("QQuickFlickable"))
                qWarning() << "Défilement" << parent->objectName() << "y" << parent->property("contentY")
                           << "contenu" << parent->property("contentHeight") << "hauteur" << parent->height();
        return false;
    }
    QTest::mouseClick(&fenetre,Qt::LeftButton,Qt::NoModifier,point.toPoint()); return true;
}
bool taper(QQuickWindow &fenetre,QQuickItem *item,const QString &texte,bool remplacer=false)
{
    if (!cliquer(fenetre,item) || !QTest::qWaitFor([item]{return item->hasActiveFocus();},2000)) return false;
    if (remplacer) QTest::keySequence(&fenetre,QKeySequence::SelectAll);
    for (const QChar c:texte) { if (c.unicode()>127) return false; QTest::keyClick(&fenetre,c.toLatin1()); }
    return true;
}
}
class TestCoffreInteractions : public QObject
{
    Q_OBJECT
private slots:
    void creerComparerEtNaviguerDansLesVraiesNotes();
};
void TestCoffreInteractions::creerComparerEtNaviguerDansLesVraiesNotes()
{
    QTemporaryDir reglages; QVERIFY(reglages.isValid());
    QCoreApplication::setOrganizationName(QStringLiteral("ACP Coffre Test %1").arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
    QCoreApplication::setApplicationName(QStringLiteral("tst_coffre_interactions"));
    QSettings::setDefaultFormat(QSettings::IniFormat); QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,reglages.path());
    FauxHermes serveur; FauxCoffre disque;
    serveur.installerAuthentification(); serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a")); disque.installer(serveur);
    Application application(nullptr,QStringLiteral("AcpTestCoffre")); application.registerQmlTypes();
    auto *client=application.findChild<ApiClient *>(); auto *flux=application.findChild<EventStreamService *>();
    auto *vue=application.findChild<ObsidianViewModel *>(); auto *compatibilite=application.findChild<CompatibiliteHermes *>();
    QVERIFY(client && flux && vue && compatibilite);
    client->setAllowInsecureLoopback(true); QVERIFY(!client->setBaseUrl(serveur.url()).isError());
    client->setBearerProvider([]{return QByteArrayLiteral("jeton-a");}); flux->setIntervalleFond(std::chrono::hours(1)); flux->demarrer();
    compatibilite->appliquerLecture(fixture(QStringLiteral("meta.json")));
    QQmlApplicationEngine moteur; QStringList avertissements;
    connect(&moteur,&QQmlEngine::warnings,this,[&](const QList<QQmlError> &erreurs){for(const auto &e:erreurs) avertissements.append(e.toString());});
    QQuickWindow fenetre; fenetre.resize(1440,1000); fenetre.show(); fenetre.requestActivate(); QVERIFY(QTest::qWaitForWindowExposed(&fenetre));
    QQmlComponent composant(&moteur); composant.loadFromModule(QStringLiteral("Acp.Pages"),QStringLiteral("CoffrePage"));
    QTRY_VERIFY_WITH_TIMEOUT(composant.status()!=QQmlComponent::Loading,5000); QVERIFY2(composant.isReady(),qPrintable(composant.errorString()));
    std::unique_ptr<QObject> page(composant.create()); auto *racine=qobject_cast<QQuickItem *>(page.get()); QVERIFY(racine);
    racine->setParentItem(fenetre.contentItem()); racine->setSize(fenetre.size());
    QTRY_COMPARE(vue->etat(),QStringLiteral("pret"));
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-lister")))); QTRY_COMPARE(vue->notes()->count(),2);
    auto *champ=parNom(parNom(racine,QStringLiteral("coffre-nouveau-chemin")),QStringLiteral("acpTextFieldInput"));
    QVERIFY(taper(fenetre,champ,QStringLiteral("Nouvelle.md")));
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-nouvelle")))); QTRY_COMPARE(vue->chemin(),QStringLiteral("Nouvelle.md"));
    auto *editeur=parNom(racine,QStringLiteral("coffre-editeur"));
    QVERIFY(taper(fenetre,editeur,QStringLiteral("Version locale")));
    QCOMPARE(vue->brouillon(),QStringLiteral("Version locale"));
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-sauvegarder"))));
    QTRY_COMPARE(disque.fichiers.value(QStringLiteral("Nouvelle.md")),QStringLiteral("Version locale")); QTRY_VERIFY(!vue->occupe()); QVERIFY(!vue->modifie());
    QCOMPARE(disque.demandes.last().value(QStringLiteral("action")).toString(),QStringLiteral("creer"));
    disque.fichiers[QStringLiteral("Nouvelle.md")]=QStringLiteral("Version modifiee dans Obsidian");
    QVERIFY(taper(fenetre,editeur,QStringLiteral("Brouillon a conserver"),true));
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-sauvegarder")))); QTRY_VERIFY(vue->conflit());
    QCOMPARE(editeur->property("text").toString(),QStringLiteral("Brouillon a conserver"));
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-relire")))); QTRY_VERIFY(vue->versionServeurDisponible());
    QCOMPARE(vue->versionServeur(),QStringLiteral("Version modifiee dans Obsidian"));
    QCOMPARE(editeur->property("text").toString(),QStringLiteral("Brouillon a conserver"));
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-graphe")))); QTRY_VERIFY(!vue->graphe().isEmpty()); QTRY_VERIFY(!vue->occupe());
    QTRY_VERIFY(parNom(racine,QStringLiteral("coffre-noeud-0")));
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-noeud-0")))); QTRY_COMPARE(vue->chemin(),QStringLiteral("Accueil.md")); QTRY_VERIFY(!vue->occupe());
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-noeud-1")))); QTRY_COMPARE(vue->chemin(),QStringLiteral("Nouvelle.md"));
    QCOMPARE(vue->brouillon(),QStringLiteral("Brouillon a conserver")); QVERIFY(vue->conflit());
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-revoquer"))));
    auto *confirmation=page->findChild<QObject *>(QStringLiteral("coffre-confirmation")); QVERIFY(confirmation);
    QTRY_VERIFY(confirmation->property("visible").toBool());
    racine->setVisible(false); QTRY_VERIFY(!confirmation->property("visible").toBool());
    racine->setVisible(true); QTRY_VERIFY(vue->actif()); QTRY_VERIFY(!vue->occupe());
    QVERIFY(cliquer(fenetre,parNom(racine,QStringLiteral("coffre-revoquer")))); QTRY_VERIFY(confirmation->property("visible").toBool());
    flux->arreter(); QTRY_VERIFY(!confirmation->property("visible").toBool());
    QCOMPARE(serveur.compter("POST",disque.prefixe+QStringLiteral("/revoquer")),0);
    QVERIFY2(avertissements.isEmpty(),qPrintable(avertissements.join(QLatin1Char('\n'))));
    racine->setParentItem(nullptr); page.reset(); flux->arreter();
}
QTEST_MAIN(TestCoffreInteractions)
#include "tst_coffre_interactions.moc"
