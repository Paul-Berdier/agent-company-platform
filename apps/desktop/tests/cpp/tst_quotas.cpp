// Page Quotas contre les formes RÉELLES de `GET /v1/quotas` (fixtures-poste.ts, capturées sur
// l'image) et le faux Hermes :
//  - voies, compteurs et fenêtres libellés ; part utilisée comparée au seuil du routage ;
//  - rien n'est estimé : part absente ou hors bornes = « Inconnu », jauge vide ;
//  - sondage de 60 s, seulement page affichée ; « Relever maintenant » rend le message du greffon.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/Sondage.h"
#include "models/JsonListModel.h"
#include "support/FauxHermes.h"
#include "support/Fixtures.h"
#include "viewmodels/QuotasViewModel.h"

#include <QJsonArray>
#include <QTest>

using namespace acp;
using namespace acp::test;

namespace {

const QString kP = QStringLiteral("/api/plugins/acp-poste/v1");
const QString kNbsp = QStringLiteral(" ");

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    QuotasViewModel quotas{&greffon, &flux};
    QJsonObject vue = fixture(QStringLiteral("quotas.json"));
    ReponseFaux releve = ReponseFaux::json(202, fixture(QStringLiteral("releve-demande.json")));

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
        serveur.route("GET", kP + QStringLiteral("/quotas"), [this](const RequeteRecue &) { return ReponseFaux::json(200, vue); });
        serveur.route("POST", kP + QStringLiteral("/poste/releve"), [this](const RequeteRecue &) { return releve; });
    }

    int lectures() const { return serveur.compter("GET", kP + QStringLiteral("/quotas")); }
};

QJsonObject fenetre(const QJsonValue &utilise, const QJsonValue &restant)
{
    return QJsonObject{{QStringLiteral("key"), QStringLiteral("primary")}, {QStringLiteral("used_percent"), utilise},
                       {QStringLiteral("remaining_percent"), restant}, {QStringLiteral("window_minutes"), 300},
                       {QStringLiteral("resets_at"), QStringLiteral("2026-09-26T12:00:00Z")}};
}

} // namespace

class TestQuotas : public QObject
{
    Q_OBJECT

private slots:
    void voiesLibellees();
    void seuilEtValeursAbsentes();
    void compteurEnEchecDitSonDetail();
    void quotasVidesInconnus();
    void pageLueToutesLes60SecondesSeulementAffichee();
    void releverRendLeMessageDuGreffon();
};

void TestQuotas::voiesLibellees()
{
    const QJsonObject vue = fixture(QStringLiteral("quotas.json"));
    const QJsonObject codex = QuotasViewModel::construireVoie(QStringLiteral("poste-codex"), vue.value(QStringLiteral("poste-codex")).toObject());
    QCOMPARE(codex.value(QStringLiteral("titre")).toString(), QStringLiteral("Poste (Codex)"));
    QCOMPARE(codex.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Relevé"));
    QCOMPARE(codex.value(QStringLiteral("etatCle")).toString(), QStringLiteral("succeeded"));
    QCOMPARE(codex.value(QStringLiteral("seuil")).toString(), QStringLiteral("90") + kNbsp + QStringLiteral("%"));
    QVERIFY(codex.value(QStringLiteral("releveLe")).toString().startsWith(QStringLiteral("26/09/2026")));
    const QJsonArray compteurs = codex.value(QStringLiteral("compteurs")).toArray();
    QCOMPARE(compteurs.size(), 1);
    const QJsonObject compteur = compteurs.at(0).toObject();
    QCOMPARE(compteur.value(QStringLiteral("compteur")).toString(), QStringLiteral("codex"));
    QCOMPARE(compteur.value(QStringLiteral("offre")).toString(), QStringLiteral("prolite"));
    QCOMPARE(compteur.value(QStringLiteral("limiteAtteinte")).toBool(), false);
    QCOMPARE(compteur.value(QStringLiteral("detail")).toString(), QString());
    const QJsonArray fenetres = compteur.value(QStringLiteral("fenetres")).toArray();
    QCOMPARE(fenetres.size(), 2);
    const QJsonObject primaire = fenetres.at(0).toObject();
    QCOMPARE(primaire.value(QStringLiteral("libelle")).toString(), QStringLiteral("Fenêtre primary · 300 min"));
    QCOMPARE(primaire.value(QStringLiteral("utilise")).toString(), QStringLiteral("41") + kNbsp + QStringLiteral("%"));
    QCOMPARE(primaire.value(QStringLiteral("restant")).toString(), QStringLiteral("59") + kNbsp + QStringLiteral("%"));
    QCOMPARE(primaire.value(QStringLiteral("restantPct")).toDouble(), 59.0);
    // Jauge : part utilisée et seuil, comme la page web (constat de relecture P8).
    QCOMPARE(primaire.value(QStringLiteral("utilisePct")).toDouble(), 41.0);
    QCOMPARE(primaire.value(QStringLiteral("niveau")).toString(), QStringLiteral("normal"));
    QCOMPARE(fenetres.at(1).toObject().value(QStringLiteral("libelle")).toString(), QStringLiteral("Fenêtre secondary · 10080 min"));

    const QJsonObject claude = QuotasViewModel::construireVoie(QStringLiteral("poste-claude"), vue.value(QStringLiteral("poste-claude")).toObject());
    QCOMPARE(claude.value(QStringLiteral("compteurs")).toArray().size(), 0);
    QCOMPARE(claude.value(QStringLiteral("source")).toString(),
             QStringLiteral("Ligne d'état de vos sessions Claude Code sur ce PC (même abonnement déclaré)"));
}

void TestQuotas::seuilEtValeursAbsentes()
{
    const QJsonValue seuil(90);
    QCOMPARE(QuotasViewModel::construireFenetre(fenetre(95, 5), seuil).value(QStringLiteral("niveau")).toString(), QStringLiteral("critical"));
    QCOMPARE(QuotasViewModel::construireFenetre(fenetre(90, 10), seuil).value(QStringLiteral("seuilAtteint")).toBool(), true);
    // Part utilisée absente : « Inconnu », niveau inconnu ; la part restante n'est pas déduite.
    const QJsonObject sansUtilise = QuotasViewModel::construireFenetre(fenetre(QJsonValue::Null, QJsonValue::Null), seuil);
    QCOMPARE(sansUtilise.value(QStringLiteral("utilise")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(sansUtilise.value(QStringLiteral("restant")).toString(), QStringLiteral("Inconnu"));
    QVERIFY(sansUtilise.value(QStringLiteral("restantPct")).isNull());
    QVERIFY(sansUtilise.value(QStringLiteral("utilisePct")).isNull());
    QCOMPARE(sansUtilise.value(QStringLiteral("seuilPct")).toDouble(), 90.0);
    QVERIFY(QuotasViewModel::construireFenetre(fenetre(95, 5), QJsonValue::Null).value(QStringLiteral("seuilPct")).isNull());
    QCOMPARE(sansUtilise.value(QStringLiteral("niveau")).toString(), QStringLiteral("unknown"));
    const QJsonObject restantAbsent = QuotasViewModel::construireFenetre(fenetre(41, QJsonValue::Undefined), seuil);
    QCOMPARE(restantAbsent.value(QStringLiteral("utilise")).toString(), QStringLiteral("41") + kNbsp + QStringLiteral("%"));
    QVERIFY(restantAbsent.value(QStringLiteral("restantPct")).isNull());
    // Hors bornes : jamais affiché comme une mesure.
    QCOMPARE(QuotasViewModel::construireFenetre(fenetre(120, -3), seuil).value(QStringLiteral("utilise")).toString(), QStringLiteral("Inconnu"));
    // Sans seuil : aucune comparaison.
    QCOMPARE(QuotasViewModel::construireFenetre(fenetre(95, 5), QJsonValue::Null).value(QStringLiteral("niveau")).toString(),
             QStringLiteral("unknown"));
    QCOMPARE(QuotasViewModel::construireVoie(QStringLiteral("poste-codex"), QJsonObject{}).value(QStringLiteral("seuil")).toString(),
             QStringLiteral("Inconnu"));
    // Fenêtre sans clé ni durée.
    QCOMPARE(QuotasViewModel::construireFenetre(QJsonObject{}, seuil).value(QStringLiteral("libelle")).toString(),
             QStringLiteral("Fenêtre Inconnu"));
}

void TestQuotas::compteurEnEchecDitSonDetail()
{
    const QJsonObject enEchec = QuotasViewModel::construireCompteur(
        QJsonObject{{QStringLiteral("status"), QStringLiteral("error")}, {QStringLiteral("detail"), QStringLiteral("app-server muet")},
                    {QStringLiteral("limit_reached"), true}},
        90);
    QCOMPARE(enEchec.value(QStringLiteral("detail")).toString(), QStringLiteral("app-server muet"));
    QCOMPARE(enEchec.value(QStringLiteral("limiteAtteinte")).toBool(), true);
    QCOMPARE(enEchec.value(QStringLiteral("compteur")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(enEchec.value(QStringLiteral("releveLe")).toString(), QStringLiteral("Inconnu"));
    const QJsonObject ok = QuotasViewModel::construireCompteur(
        QJsonObject{{QStringLiteral("status"), QStringLiteral("ok")}, {QStringLiteral("detail"), QStringLiteral("ignoré")}}, 90);
    QCOMPARE(ok.value(QStringLiteral("detail")).toString(), QString());
}

void TestQuotas::quotasVidesInconnus()
{
    const QJsonObject vue = fixture(QStringLiteral("quotas-vides.json"));
    const QJsonObject codex = QuotasViewModel::construireVoie(QStringLiteral("poste-codex"), vue.value(QStringLiteral("poste-codex")).toObject());
    QCOMPARE(codex.value(QStringLiteral("etatLibelle")).toString(), QStringLiteral("Inconnu"));
    QCOMPARE(codex.value(QStringLiteral("etatCle")).toString(), QStringLiteral("unknown"));
    QCOMPARE(codex.value(QStringLiteral("compteurs")).toArray().size(), 0);
    QCOMPARE(codex.value(QStringLiteral("releveLe")).toString(), QString());
}

void TestQuotas::pageLueToutesLes60SecondesSeulementAffichee()
{
    Banc banc;
    QCOMPARE(banc.quotas.sondage()->intervalle(), std::chrono::milliseconds(60000));
    banc.flux.demarrer();
    QTest::qWait(60);
    QCOMPARE(banc.lectures(), 0);
    banc.quotas.setPageVisible(true);
    QTRY_VERIFY(banc.quotas.lue());
    QCOMPARE(banc.quotas.voies()->count(), 2);
    QCOMPARE(banc.quotas.hermes(), QStringLiteral("Inconnu"));
    banc.vue.insert(QStringLiteral("hermes"), QJsonObject{{QStringLiteral("etat"), QStringLiteral("releve")},
                                                          {QStringLiteral("libelle"), QStringLiteral("Même enveloppe que Codex")}});
    banc.quotas.actualiser();
    QTRY_COMPARE(banc.quotas.hermes(), QStringLiteral("Même enveloppe que Codex"));
    banc.quotas.setPageVisible(false);
    QTRY_VERIFY(!banc.quotas.actif());
}

void TestQuotas::releverRendLeMessageDuGreffon()
{
    Banc banc;
    banc.flux.demarrer();
    banc.quotas.setPageVisible(true);
    QTRY_VERIFY(banc.quotas.lue());
    const int avant = banc.lectures();
    banc.quotas.relever();
    QTRY_VERIFY(!banc.quotas.gesteEnCours());
    QCOMPARE(banc.serveur.filtrer("POST", kP + QStringLiteral("/poste/releve")).first().json(), QJsonObject{});
    QCOMPARE(banc.quotas.messageGeste(),
             QStringLiteral("Ordre de relevé mis en file : le poste le reçoit à sa prochaine attente."));
    QTRY_VERIFY(banc.lectures() > avant); // relu après le geste

    banc.releve = ReponseFaux::json(409, QJsonObject{{QStringLiteral("detail"), QJsonObject{
        {QStringLiteral("code"), QStringLiteral("aucun_poste_actif")},
        {QStringLiteral("message"), QStringLiteral("Refusé par ACP : aucun poste actif.")}}}});
    banc.quotas.relever();
    QTRY_VERIFY(!banc.quotas.gesteEnCours());
    QCOMPARE(banc.quotas.erreurGeste(), QStringLiteral("Refusé par ACP : aucun poste actif."));
}

QTEST_MAIN(TestQuotas)
#include "tst_quotas.moc"
