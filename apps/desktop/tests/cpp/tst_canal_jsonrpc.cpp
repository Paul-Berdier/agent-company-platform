// Canal JSON-RPC de la passerelle, sans réseau.
//
// Exigence du plan prouvée ici : -32601 EXACT pour une requête serveur sans gestionnaire
// (`secret`, `sudo`, méthode inconnue) ; réponse à `approval`/`clarify` avec le même `id` ;
// trames illisibles ignorées ; délai ; `gateway.ping` et échéance « toute trame entrante »
// (minuteries raccourcies) ; aucune requête rejouée après fermeture.

#include "gateway/JsonRpcChannel.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

#include <algorithm>

using namespace acp;

namespace {

struct Capture
{
    QList<QJsonObject> trames;
    JsonRpcChannel::Transport transport()
    {
        return [this](const QByteArray &texte) {
            trames.append(QJsonDocument::fromJson(texte).object());
            return true;
        };
    }
    [[nodiscard]] QList<QJsonObject> parMethode(const QString &methode) const
    {
        QList<QJsonObject> resultat;
        for (const QJsonObject &trame : trames) {
            if (trame.value(QStringLiteral("method")).toString() == methode) {
                resultat.append(trame);
            }
        }
        return resultat;
    }
};

QByteArray json(const QJsonObject &objet)
{
    return QJsonDocument(objet).toJson(QJsonDocument::Compact);
}

QJsonObject evenement(const QString &type, const QJsonObject &payload, const QString &session = {}, int seq = -1)
{
    QJsonObject params{{QStringLiteral("type"), type}, {QStringLiteral("payload"), payload}};
    if (!session.isEmpty()) {
        params.insert(QStringLiteral("session_id"), session);
    }
    if (seq >= 0) {
        params.insert(QStringLiteral("seq"), seq);
    }
    return QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                       {QStringLiteral("method"), QStringLiteral("event")},
                       {QStringLiteral("params"), params}};
}

} // namespace

class TestCanalJsonRpc : public QObject
{
    Q_OBJECT

private slots:
    void requeteServeurSansGestionnaireRendMoins32601();
    void gestionnaireRepondAvecLeMemeIdentifiant();
    void reponseRegleLaRequete();
    void tramesIllisiblesIgnorees();
    void plusieursObjetsParMessage();
    void delaiDeRequete();
    void aucuneRequeteRejoueeApresFermeture();
    void nonConnecteEchoueLocalement();
    void gatewayReadyAnnonceCapacitesEtBattement();
    void battementEcheanceToutesTramesEntrantes();
    void evenementsTypes();
    void openRequestsRedistribueesAvantLeResultat();
};

void TestCanalJsonRpc::requeteServeurSansGestionnaireRendMoins32601()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    QSignalSpy nonPrises(&canal, &JsonRpcChannel::requeteNonPriseEnCharge);
    canal.definirGestionnaire(QStringLiteral("approval"), [](const RequeteServeur &) {});
    const QStringList methodes = {QStringLiteral("secret"), QStringLiteral("sudo"),
                                  QStringLiteral("vault.unlock"), QStringLiteral("inconnue.totalement")};
    int numero = 0;
    for (const QString &methode : methodes) {
        canal.recevoir(json(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                                        {QStringLiteral("id"), QStringLiteral("srq-%1").arg(++numero)},
                                        {QStringLiteral("method"), methode},
                                        {QStringLiteral("params"), QJsonObject{{QStringLiteral("session_id"), QStringLiteral("s1")}}}}));
    }
    QCOMPARE(capture.trames.size(), methodes.size());
    for (qsizetype index = 0; index < methodes.size(); ++index) {
        const QJsonObject trame = capture.trames.at(index);
        QCOMPARE(trame.value(QStringLiteral("jsonrpc")).toString(), QStringLiteral("2.0"));
        QCOMPARE(trame.value(QStringLiteral("id")).toString(), QStringLiteral("srq-%1").arg(index + 1));
        QVERIFY(!trame.contains(QStringLiteral("result")));
        const QJsonObject erreur = trame.value(QStringLiteral("error")).toObject();
        QCOMPARE(erreur.value(QStringLiteral("code")).toInt(), -32601);
        QCOMPARE(erreur.value(QStringLiteral("message")).toString(),
                 QStringLiteral("Méthode non prise en charge par la station : %1").arg(methodes.at(index)));
    }
    QCOMPARE(canal.methodesRefusees(), 4);
    QCOMPARE(nonPrises.count(), 4);
    QVERIFY(!canal.requeteOuverte(QStringLiteral("srq-1")));
}

void TestCanalJsonRpc::gestionnaireRepondAvecLeMemeIdentifiant()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    QList<RequeteServeur> recues;
    const auto noter = [&recues](const RequeteServeur &requete) { recues.append(requete); };
    canal.definirGestionnaire(QStringLiteral("approval"), noter);
    canal.definirGestionnaire(QStringLiteral("clarify"), noter);
    canal.recevoir(json(QJsonObject{{QStringLiteral("id"), QStringLiteral("srq-a1")},
                                    {QStringLiteral("method"), QStringLiteral("approval")},
                                    {QStringLiteral("params"), QJsonObject{{QStringLiteral("command"), QStringLiteral("ls")}}}}));
    canal.recevoir(json(QJsonObject{{QStringLiteral("id"), QStringLiteral("srq-c1")},
                                    {QStringLiteral("method"), QStringLiteral("clarify")},
                                    {QStringLiteral("params"), QJsonObject{{QStringLiteral("question"), QStringLiteral("Quelle base ?")}}}}));
    QCOMPARE(recues.size(), 2);
    QVERIFY(capture.trames.isEmpty()); // la réponse attend le propriétaire
    QVERIFY(canal.requeteOuverte(QStringLiteral("srq-a1")));
    QVERIFY(!recues.first().rejouee);

    QVERIFY(canal.repondre(QStringLiteral("srq-a1"), QJsonObject{{QStringLiteral("choice"), QStringLiteral("once")}}));
    QVERIFY(!canal.repondre(QStringLiteral("srq-a1"), QJsonObject{{QStringLiteral("choice"), QStringLiteral("deny")}}));
    QVERIFY(canal.repondre(QStringLiteral("srq-c1"), QJsonObject{{QStringLiteral("answer"), QStringLiteral("PostgreSQL")}}));
    QCOMPARE(capture.trames.size(), 2);
    QCOMPARE(capture.trames.at(0).value(QStringLiteral("id")).toString(), QStringLiteral("srq-a1"));
    QCOMPARE(capture.trames.at(0).value(QStringLiteral("result")).toObject().value(QStringLiteral("choice")).toString(),
             QStringLiteral("once"));
    QCOMPARE(capture.trames.at(1).value(QStringLiteral("id")).toString(), QStringLiteral("srq-c1"));
    QCOMPARE(capture.trames.at(1).value(QStringLiteral("result")).toObject().value(QStringLiteral("answer")).toString(),
             QStringLiteral("PostgreSQL"));
    // Une requête inconnue ne reçoit rien.
    QVERIFY(!canal.repondre(QStringLiteral("srq-inconnue"), {}));
    QCOMPARE(capture.trames.size(), 2);
}

void TestCanalJsonRpc::reponseRegleLaRequete()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    AppelRpc *liste = canal.requete(QStringLiteral("session.list"), QJsonObject{{QStringLiteral("limit"), 50}});
    QSignalSpy reussi(liste, &AppelRpc::reussi);
    AppelRpc *envoi = canal.requete(QStringLiteral("prompt.submit"), QJsonObject{{QStringLiteral("text"), QStringLiteral("Bonjour")}});
    QSignalSpy echoue(envoi, &AppelRpc::echoue);
    QCOMPARE(capture.trames.size(), 2);
    const QJsonObject premiere = capture.trames.first();
    QCOMPARE(premiere.value(QStringLiteral("id")).toString(), QStringLiteral("d1"));
    QCOMPARE(premiere.value(QStringLiteral("method")).toString(), QStringLiteral("session.list"));
    QCOMPARE(premiere.value(QStringLiteral("params")).toObject().value(QStringLiteral("limit")).toInt(), 50);
    QCOMPARE(capture.trames.at(1).value(QStringLiteral("id")).toString(), QStringLiteral("d2"));

    canal.recevoir(json(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")}, {QStringLiteral("id"), QStringLiteral("d1")},
                                    {QStringLiteral("result"), QJsonObject{{QStringLiteral("sessions"), QJsonArray{}}}}}));
    canal.recevoir(json(QJsonObject{{QStringLiteral("id"), QStringLiteral("d2")},
                                    {QStringLiteral("error"), QJsonObject{{QStringLiteral("code"), 4009},
                                                                          {QStringLiteral("message"), QStringLiteral("session busy")}}}}));
    QCOMPARE(reussi.count(), 1);
    QVERIFY(reussi.first().first().toJsonValue().toObject().contains(QStringLiteral("sessions")));
    QCOMPARE(echoue.count(), 1);
    const auto erreur = echoue.first().first().value<ErreurRpc>();
    QCOMPARE(erreur.code, 4009);
    QCOMPARE(erreur.message, QStringLiteral("session busy"));
    QVERIFY(!erreur.locale);
    // Une réponse en double ou inconnue est comptée, jamais remise.
    canal.recevoir(json(QJsonObject{{QStringLiteral("id"), QStringLiteral("d1")}, {QStringLiteral("result"), QJsonObject{}}}));
    QCOMPARE(canal.reponsesInconnues(), 1);
    QCOMPARE(reussi.count(), 1);
}

void TestCanalJsonRpc::tramesIllisiblesIgnorees()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    canal.recevoir(QByteArrayLiteral("ce n'est pas du JSON"));
    canal.recevoir(QByteArrayLiteral("[1, 2, 3]"));
    canal.recevoir(QByteArrayLiteral("{\"method\":\"event\",\"params\":{}}"));
    canal.recevoir(QByteArrayLiteral("{\"jsonrpc\":\"2.0\"}"));
    QCOMPARE(canal.tramesIllisibles(), 4);
    // Le canal reste utilisable.
    AppelRpc *appel = canal.requete(QStringLiteral("ping"));
    QSignalSpy reussi(appel, &AppelRpc::reussi);
    canal.recevoir(json(QJsonObject{{QStringLiteral("id"), QStringLiteral("d1")}, {QStringLiteral("result"), QStringLiteral("pong")}}));
    QCOMPARE(reussi.count(), 1);
}

void TestCanalJsonRpc::plusieursObjetsParMessage()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    QSignalSpy evenements(&canal, &JsonRpcChannel::evenement);
    canal.recevoir(json(evenement(QStringLiteral("message.start"), {}, QStringLiteral("s1"), 1)) + '\n'
                   + json(evenement(QStringLiteral("message.delta"), QJsonObject{{QStringLiteral("text"), QStringLiteral("Bon")}},
                                    QStringLiteral("s1"), 2))
                   + "\n\n");
    QCOMPARE(evenements.count(), 2);
    QCOMPARE(canal.tramesIllisibles(), 0);
}

void TestCanalJsonRpc::delaiDeRequete()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    canal.setDelaiRequete(std::chrono::milliseconds(60));
    AppelRpc *appel = canal.requete(QStringLiteral("session.list"));
    QSignalSpy echoue(appel, &AppelRpc::echoue);
    QVERIFY(echoue.wait(2000));
    const auto erreur = echoue.first().first().value<ErreurRpc>();
    QVERIFY(erreur.locale);
    QCOMPARE(erreur.message, QStringLiteral("Hermes n'a pas répondu à session.list."));
    // La réponse tardive est ignorée : l'identifiant est oublié.
    canal.recevoir(json(QJsonObject{{QStringLiteral("id"), QStringLiteral("d1")}, {QStringLiteral("result"), QJsonObject{}}}));
    QCOMPARE(canal.reponsesInconnues(), 1);
    // Délai propre à un appel.
    AppelRpc *long_ = canal.requete(QStringLiteral("session.history"), {}, std::chrono::milliseconds(5000));
    QSignalSpy longEchec(long_, &AppelRpc::echoue);
    QTest::qWait(150);
    QCOMPARE(longEchec.count(), 0);
}

void TestCanalJsonRpc::aucuneRequeteRejoueeApresFermeture()
{
    JsonRpcChannel canal;
    Capture premiere;
    canal.attacher(premiere.transport());
    AppelRpc *envoi = canal.requete(QStringLiteral("prompt.submit"),
                                    QJsonObject{{QStringLiteral("session_id"), QStringLiteral("s1")},
                                                {QStringLiteral("text"), QStringLiteral("Fais le point")}});
    QSignalSpy echoue(envoi, &AppelRpc::echoue);
    canal.definirGestionnaire(QStringLiteral("approval"), [](const RequeteServeur &) {});
    canal.recevoir(json(QJsonObject{{QStringLiteral("id"), QStringLiteral("srq-1")},
                                    {QStringLiteral("method"), QStringLiteral("approval")}}));
    canal.detacher(QStringLiteral("coupure du réseau"));
    QCOMPARE(echoue.count(), 1);
    const auto erreur = echoue.first().first().value<ErreurRpc>();
    QVERIFY(erreur.locale);
    QCOMPARE(erreur.message, QStringLiteral("Connexion perdue : coupure du réseau"));
    QVERIFY(!canal.requeteOuverte(QStringLiteral("srq-1")));

    Capture seconde;
    canal.attacher(seconde.transport());
    QTest::qWait(20);
    QVERIFY2(seconde.trames.isEmpty(), "aucune requête n'est rejouée sur la nouvelle connexion");
    // Une réponse tardive à la requête d'une connexion perdue n'atteint personne.
    QVERIFY(!canal.repondre(QStringLiteral("srq-1"), {}));
    QVERIFY(seconde.trames.isEmpty());
}

void TestCanalJsonRpc::nonConnecteEchoueLocalement()
{
    JsonRpcChannel canal;
    AppelRpc *appel = canal.requete(QStringLiteral("session.list"));
    QSignalSpy echoue(appel, &AppelRpc::echoue);
    QVERIFY(echoue.wait(1000));
    QVERIFY(echoue.first().first().value<ErreurRpc>().locale);
    QVERIFY(echoue.first().first().value<ErreurRpc>().message.contains(QStringLiteral("non connectée")));
}

void TestCanalJsonRpc::gatewayReadyAnnonceCapacitesEtBattement()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    canal.recevoir(json(evenement(QStringLiteral("gateway.ready"),
                                  QJsonObject{{QStringLiteral("heartbeat"), false}, {QStringLiteral("replay_epoch"), QStringLiteral("e1")}})));
    const auto capacites = capture.parMethode(QStringLiteral("client.capabilities"));
    QCOMPARE(capacites.size(), 1);
    QCOMPARE(capacites.first().value(QStringLiteral("params")).toObject(),
             (QJsonObject{{QStringLiteral("server_requests"), true}}));
    QVERIFY(!canal.battementActif());

    JsonRpcChannel avecBattement;
    Capture autre;
    avecBattement.attacher(autre.transport());
    avecBattement.recevoir(json(evenement(QStringLiteral("gateway.ready"), QJsonObject{{QStringLiteral("heartbeat"), true}})));
    QVERIFY(avecBattement.battementActif());
}

void TestCanalJsonRpc::battementEcheanceToutesTramesEntrantes()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    canal.setBattement(std::chrono::milliseconds(30), std::chrono::milliseconds(300));
    QSignalSpy echec(&canal, &JsonRpcChannel::battementEchoue);
    canal.demarrerBattement();
    // Pendant 400 ms, une notification arrive toutes les 40 ms : aucune échéance (300 ms).
    for (int tour = 0; tour < 10; ++tour) {
        QTest::qWait(40);
        canal.recevoir(json(evenement(QStringLiteral("status.update"), QJsonObject{})));
    }
    QCOMPARE(echec.count(), 0);
    const auto pings = capture.parMethode(QStringLiteral("gateway.ping"));
    QVERIFY2(pings.size() >= 3, qPrintable(QString::number(pings.size())));
    QCOMPARE(pings.first().value(QStringLiteral("params")).toObject(), QJsonObject{});
    // Les pongs ne sont jamais pris pour une réponse inconnue.
    canal.recevoir(json(QJsonObject{{QStringLiteral("id"), pings.last().value(QStringLiteral("id"))},
                                    {QStringLiteral("result"), QJsonObject{}}}));
    QCOMPARE(canal.reponsesInconnues(), 0);
    // Silence : l'échéance tombe, le battement s'arrête.
    QVERIFY(echec.wait(1000));
    QVERIFY(!canal.battementActif());
    QVERIFY(echec.first().first().toString().contains(QStringLiteral("aucune trame reçue")));
}

void TestCanalJsonRpc::evenementsTypes()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    QSignalSpy evenements(&canal, &JsonRpcChannel::evenement);
    canal.recevoir(json(evenement(QStringLiteral("message.delta"), QJsonObject{{QStringLiteral("text"), QStringLiteral("jour")}},
                                  QStringLiteral("session-7"), 42)));
    canal.recevoir(json(evenement(QStringLiteral("sessions.changed"), QJsonObject{})));
    QCOMPARE(evenements.count(), 2);
    QCOMPARE(evenements.at(0).at(0).toString(), QStringLiteral("message.delta"));
    QCOMPARE(evenements.at(0).at(1).toString(), QStringLiteral("session-7"));
    QCOMPARE(evenements.at(0).at(2).toLongLong(), 42);
    QCOMPARE(evenements.at(0).at(3).toJsonValue().toObject().value(QStringLiteral("text")).toString(), QStringLiteral("jour"));
    QCOMPARE(evenements.at(1).at(2).toLongLong(), -1);
}

void TestCanalJsonRpc::openRequestsRedistribueesAvantLeResultat()
{
    JsonRpcChannel canal;
    Capture capture;
    canal.attacher(capture.transport());
    QStringList ordre;
    canal.definirGestionnaire(QStringLiteral("clarify"), [&ordre](const RequeteServeur &requete) {
        ordre.append(QStringLiteral("clarify:%1:%2").arg(requete.identifiant).arg(requete.rejouee));
    });
    AppelRpc *reprise = canal.requete(QStringLiteral("session.resume"), QJsonObject{{QStringLiteral("session_id"), QStringLiteral("s1")}});
    connect(reprise, &AppelRpc::reussi, this, [&ordre] { ordre.append(QStringLiteral("resultat")); });
    canal.recevoir(json(QJsonObject{
        {QStringLiteral("id"), QStringLiteral("d1")},
        {QStringLiteral("result"), QJsonObject{{QStringLiteral("session_id"), QStringLiteral("s1-vivant")},
                                               {QStringLiteral("open_requests"),
                                                QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("srq-9")},
                                                                       {QStringLiteral("method"), QStringLiteral("clarify")},
                                                                       {QStringLiteral("params"), QJsonObject{}}},
                                                           QJsonObject{{QStringLiteral("id"), QStringLiteral("srq-10")},
                                                                       {QStringLiteral("method"), QStringLiteral("secret")}}}}}}}));
    QCOMPARE(ordre, (QStringList{QStringLiteral("clarify:srq-9:1"), QStringLiteral("resultat")}));
    // La requête `secret` rejouée est refusée en -32601 comme en direct.
    const auto refus = std::find_if(capture.trames.cbegin(), capture.trames.cend(), [](const QJsonObject &trame) {
        return trame.value(QStringLiteral("id")).toString() == QStringLiteral("srq-10");
    });
    QVERIFY(refus != capture.trames.cend());
    QCOMPARE(refus->value(QStringLiteral("error")).toObject().value(QStringLiteral("code")).toInt(), -32601);
}

QTEST_GUILESS_MAIN(TestCanalJsonRpc)

#include "tst_canal_jsonrpc.moc"
