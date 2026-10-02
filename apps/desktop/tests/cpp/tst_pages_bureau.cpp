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
#include "events/EventStreamService.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/AccueilViewModel.h"
#include "viewmodels/ProjetsViewModel.h"

#include <QJsonArray>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlProperty>
#include <QQuickItem>
#include <QQuickWindow>
#include <QRegularExpression>
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
    serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
    QJsonObject projets = fixture(QStringLiteral("projets.json"));
    serveur.route("GET", kP + QStringLiteral("/projets"), [&projets](const RequeteRecue &) { return ReponseFaux::json(200, projets); });
    serveur.route("GET", kP + QStringLiteral("/projets/") + kId,
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("projet-detail.json"))); });
    serveur.route("GET", kP + QStringLiteral("/quotas"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("quotas.json"))); });
    serveur.route("GET", kP + QStringLiteral("/catalogue"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("catalogue-profils.json"))); });
    serveur.route("GET", kP + QStringLiteral("/poste"),
                  [](const RequeteRecue &) { return ReponseFaux::json(200, fixture(QStringLiteral("poste-releve.json"))); });
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
    QVERIFY(client && flux && accueil && pageProjets);
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

    // --- La racine : fenêtre, écran de connexion (aucune session) et palette -----------------------
    flux->arreter();
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
