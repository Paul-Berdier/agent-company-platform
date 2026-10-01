// Client de la passerelle JSON-RPC contre le faux Hermes (HTTP et WebSocket sur le même port).
//
// Prouvé ici : sous-protocoles exacts (`hermes-gateway-v1` + ticket), AUCUN en-tête `Origin`
// reçu par le serveur, un ticket par ouverture (usage unique), 4401 ⇒ un nouveau ticket puis
// refus, poignée refusée (403) ⇒ un nouveau ticket puis refus, 4403 ⇒ refus immédiat,
// `gateway.ready` puis `client.capabilities`, rejeu `session.events.since` avec retenue des
// trames vivantes et dédoublonnage par `seq`, époque changée ⇒ relecture, `open_requests`
// redistribuées, battement perdu ⇒ reconnexion, fermeture sans reconnexion.

#include "api/ApiClient.h"
#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"
#include "support/FauxHermes.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

#include <algorithm>
#include <memory>

using namespace acp;
using namespace acp::test;

namespace {

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    std::unique_ptr<GatewayClient> passerelle;
    QList<QPair<QString, qint64>> recus; //!< (type, seq) rendus par la passerelle, dans l'ordre

    Banc()
    {
        serveur.installerAuthentification();
        serveur.activerPasserelle();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
        passerelle = std::make_unique<GatewayClient>(&client);
        passerelle->setRecul(Backoff(std::chrono::milliseconds(20), std::chrono::milliseconds(40), 0));
        QObject::connect(passerelle.get(), &GatewayClient::evenement, passerelle.get(),
                         [this](const QString &type, const QString &, qint64 seq, const QJsonValue &) {
                             recus.append({type, seq});
                         });
    }

    static QJsonObject evenement(const QString &type, const QString &session, qint64 seq)
    {
        return QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                           {QStringLiteral("method"), QStringLiteral("event")},
                           {QStringLiteral("params"),
                            QJsonObject{{QStringLiteral("type"), type},
                                        {QStringLiteral("session_id"), session},
                                        {QStringLiteral("seq"), seq},
                                        {QStringLiteral("payload"), QJsonObject{}}}}};
    }
};

} // namespace

class TestClientPasserelle : public QObject
{
    Q_OBJECT

private slots:
    void ouvertureNominaleSansOrigine();
    void unTicketParOuverture();
    void ferme4401UnNouveauTicketPuisRefus();
    void poigneeRefuseeUnNouveauTicketPuisRefus();
    void ferme4403RefusImmediat();
    void readyAbsentReconnecte();
    void rejeuRetenueEtDedoublonnage();
    void epoqueChangeeDemandeUneRelecture();
    void openRequestsRedistribueesAuRejeu();
    void battementPerduReconnecte();
    void fermetureSansReconnexion();
};

void TestClientPasserelle::ouvertureNominaleSansOrigine()
{
    Banc banc;
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->ouvrir();
    QVERIFY(prete.wait(10000));
    QCOMPARE(banc.passerelle->etat(), GatewayClient::Etat::Pret);
    QCOMPARE(banc.passerelle->sousProtocoleRetenu(), QStringLiteral("hermes-gateway-v1"));
    QCOMPARE(banc.passerelle->epoque(), QStringLiteral("epoque-1"));

    const auto tickets = banc.serveur.filtrer("POST", QStringLiteral("/api/auth/ws-ticket"));
    QCOMPARE(tickets.size(), 1);
    QCOMPARE(tickets.first().entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
    QCOMPARE(banc.serveur.ouvertures.size(), 1);
    const RequeteRecue ouverture = banc.serveur.ouvertures.first();
    QCOMPARE(ouverture.chemin, QStringLiteral("/api/ws"));
    QVERIFY2(!ouverture.aEntete("origin"), "un client natif n'envoie aucun Origin");
    QVERIFY(!ouverture.aEntete("authorization"));
    QVERIFY(!ouverture.aEntete("cookie"));
    QVERIFY(ouverture.requete.isEmpty()); // le ticket ne voyage jamais dans l'URL
    QStringList protocoles;
    for (const QByteArray &morceau : ouverture.entete("sec-websocket-protocol").split(',')) {
        protocoles.append(QString::fromLatin1(morceau.trimmed()));
    }
    QCOMPARE(protocoles.size(), 2);
    QCOMPARE(protocoles.first(), QStringLiteral("hermes-gateway-v1"));
    QVERIFY(protocoles.at(1).startsWith(QStringLiteral("hermes-gateway-ticket.ticket-faux-")));
    QVERIFY(banc.serveur.ticketsEmis.isEmpty()); // consommé à l'ouverture

    QTRY_COMPARE(banc.serveur.tramesDeMethode(QStringLiteral("client.capabilities")).size(), 1);
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("client.capabilities")).first()
                 .value(QStringLiteral("params")).toObject(),
             (QJsonObject{{QStringLiteral("server_requests"), true}}));
    QVERIFY(banc.passerelle->canal()->battementActif());

    // Le canal est utilisable de bout en bout.
    banc.serveur.methodes.insert(QStringLiteral("session.list"), [](const QJsonObject &) {
        return QJsonValue(QJsonObject{{QStringLiteral("sessions"), QJsonArray{}}});
    });
    AppelRpc *liste = banc.passerelle->canal()->requete(QStringLiteral("session.list"),
                                                        QJsonObject{{QStringLiteral("limit"), 50}});
    QSignalSpy reussi(liste, &AppelRpc::reussi);
    QVERIFY(reussi.wait(5000));
}

void TestClientPasserelle::unTicketParOuverture()
{
    Banc banc;
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->ouvrir();
    QVERIFY(prete.wait(10000));
    banc.serveur.couperClient();
    QTRY_COMPARE_WITH_TIMEOUT(prete.count(), 2, 10000);
    QCOMPARE(banc.serveur.filtrer("POST", QStringLiteral("/api/auth/ws-ticket")).size(), 2);
    QCOMPARE(banc.serveur.ouvertures.size(), 2);
    QVERIFY(banc.serveur.ouvertures.at(0).entete("sec-websocket-protocol")
            != banc.serveur.ouvertures.at(1).entete("sec-websocket-protocol"));
    QVERIFY(banc.serveur.ticketsEmis.isEmpty());
    QVERIFY(banc.passerelle->reconnexions() >= 1);
}

void TestClientPasserelle::ferme4401UnNouveauTicketPuisRefus()
{
    Banc banc;
    banc.serveur.fermer4401 = 1;
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->ouvrir();
    QVERIFY(prete.wait(10000));
    QCOMPARE(banc.serveur.filtrer("POST", QStringLiteral("/api/auth/ws-ticket")).size(), 2);

    Banc refuse;
    refuse.serveur.fermer4401 = 2;
    refuse.passerelle->ouvrir();
    QTRY_COMPARE_WITH_TIMEOUT(refuse.passerelle->etat(), GatewayClient::Etat::Refuse, 10000);
    QVERIFY(refuse.passerelle->raison().contains(QStringLiteral("4401")));
    QCOMPARE(refuse.serveur.filtrer("POST", QStringLiteral("/api/auth/ws-ticket")).size(), 2);
    QTest::qWait(200);
    QCOMPARE(refuse.serveur.filtrer("POST", QStringLiteral("/api/auth/ws-ticket")).size(), 2); // plus rien
}

void TestClientPasserelle::poigneeRefuseeUnNouveauTicketPuisRefus()
{
    Banc banc;
    banc.serveur.refuserPoignees = true;
    banc.passerelle->ouvrir();
    QTRY_COMPARE_WITH_TIMEOUT(banc.passerelle->etat(), GatewayClient::Etat::Refuse, 10000);
    QCOMPARE(banc.serveur.filtrer("POST", QStringLiteral("/api/auth/ws-ticket")).size(), 2);
    QCOMPARE(banc.serveur.ouvertures.size(), 2);
    QVERIFY2(banc.passerelle->raison().contains(QStringLiteral("refuse l'ouverture")),
             qPrintable(banc.passerelle->raison()));
    QTest::qWait(200);
    QCOMPARE(banc.serveur.ouvertures.size(), 2);
}

void TestClientPasserelle::ferme4403RefusImmediat()
{
    Banc banc;
    banc.serveur.fermer4403 = 1;
    banc.passerelle->ouvrir();
    QTRY_COMPARE_WITH_TIMEOUT(banc.passerelle->etat(), GatewayClient::Etat::Refuse, 10000);
    QVERIFY(banc.passerelle->raison().contains(QStringLiteral("4403")));
    QCOMPARE(banc.serveur.filtrer("POST", QStringLiteral("/api/auth/ws-ticket")).size(), 1);
    // Un nouvel essai explicite repart.
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->reconnecter();
    QVERIFY(prete.wait(10000));
}

void TestClientPasserelle::readyAbsentReconnecte()
{
    Banc banc;
    banc.serveur.envoyerReady = false;
    banc.passerelle->setDelaiPremiereTrame(std::chrono::milliseconds(150));
    banc.passerelle->ouvrir();
    QTRY_COMPARE_WITH_TIMEOUT(banc.passerelle->etat(), GatewayClient::Etat::Reconnexion, 5000);
    QVERIFY(banc.passerelle->raison().contains(QStringLiteral("gateway.ready")));
    banc.serveur.envoyerReady = true;
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    QVERIFY(prete.wait(10000));
}

void TestClientPasserelle::rejeuRetenueEtDedoublonnage()
{
    Banc banc;
    banc.passerelle->suivreSession(QStringLiteral("s1"), 5);
    QJsonObject parametresRecus;
    banc.serveur.rejeu = [&banc, &parametresRecus](const QJsonObject &params) {
        parametresRecus = params;
        // Deux trames vivantes partent AVANT la réponse du rejeu : 7 (doublon) et 8.
        banc.serveur.envoyer(Banc::evenement(QStringLiteral("message.delta"), QStringLiteral("s1"), 7));
        banc.serveur.envoyer(Banc::evenement(QStringLiteral("message.complete"), QStringLiteral("s1"), 8));
        return QJsonObject{{QStringLiteral("events"),
                            QJsonArray{QJsonObject{{QStringLiteral("type"), QStringLiteral("message.start")},
                                                   {QStringLiteral("session_id"), QStringLiteral("s1")},
                                                   {QStringLiteral("seq"), 6}, {QStringLiteral("payload"), QJsonObject{}}},
                                       QJsonObject{{QStringLiteral("type"), QStringLiteral("message.delta")},
                                                   {QStringLiteral("session_id"), QStringLiteral("s1")},
                                                   {QStringLiteral("seq"), 7}, {QStringLiteral("payload"), QJsonObject{}}},
                                       QJsonObject{{QStringLiteral("type"), QStringLiteral("message.start")},
                                                   {QStringLiteral("session_id"), QStringLiteral("s1")},
                                                   {QStringLiteral("seq"), 5}, {QStringLiteral("payload"), QJsonObject{}}}}},
                           {QStringLiteral("latest_seq"), 7}, {QStringLiteral("truncated"), false},
                           {QStringLiteral("count"), 3}, {QStringLiteral("epoch"), banc.serveur.epoque},
                           {QStringLiteral("open_requests"), QJsonArray{}}};
    };
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->ouvrir();
    QVERIFY(prete.wait(10000));
    QCOMPARE(parametresRecus.value(QStringLiteral("session_id")).toString(), QStringLiteral("s1"));
    QCOMPARE(parametresRecus.value(QStringLiteral("last_seen")).toInt(), 5);
    QTRY_COMPARE(banc.recus.size(), 3);
    QCOMPARE(banc.recus, (QList<QPair<QString, qint64>>{{QStringLiteral("message.start"), 6},
                                                         {QStringLiteral("message.delta"), 7},
                                                         {QStringLiteral("message.complete"), 8}}));
    QCOMPARE(banc.passerelle->marque(QStringLiteral("s1")), 8);
    // Après le rejeu, un doublon vivant est écarté, une trame neuve passe.
    banc.serveur.envoyer(Banc::evenement(QStringLiteral("message.delta"), QStringLiteral("s1"), 8));
    banc.serveur.envoyer(Banc::evenement(QStringLiteral("status.update"), QStringLiteral("s1"), 9));
    QTRY_COMPARE(banc.recus.size(), 4);
    QCOMPARE(banc.recus.last().second, 9);
}

void TestClientPasserelle::epoqueChangeeDemandeUneRelecture()
{
    Banc banc;
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->ouvrir();
    QVERIFY(prete.wait(10000));
    banc.passerelle->suivreSession(QStringLiteral("s1"), 3);
    QSignalSpy relectures(banc.passerelle.get(), &GatewayClient::relectureRequise);
    banc.serveur.epoque = QStringLiteral("epoque-2"); // Hermes redémarré
    banc.serveur.couperClient();
    QTRY_COMPARE_WITH_TIMEOUT(prete.count(), 2, 10000);
    QCOMPARE(relectures.count(), 1);
    QCOMPARE(relectures.first().first().toString(), QStringLiteral("s1"));
    QVERIFY(relectures.first().at(1).toString().contains(QStringLiteral("redémarré")));
    QCOMPARE(banc.passerelle->marque(QStringLiteral("s1")), -1);
    QCOMPARE(banc.passerelle->epoque(), QStringLiteral("epoque-2"));
    QCOMPARE(banc.serveur.tramesDeMethode(QStringLiteral("session.events.since")).size(), 0);
}

void TestClientPasserelle::openRequestsRedistribueesAuRejeu()
{
    Banc banc;
    QList<RequeteServeur> recues;
    banc.passerelle->canal()->definirGestionnaire(QStringLiteral("clarify"),
                                                  [&recues](const RequeteServeur &requete) { recues.append(requete); });
    banc.passerelle->suivreSession(QStringLiteral("s1"), 2);
    banc.serveur.rejeu = [&banc](const QJsonObject &) {
        return QJsonObject{{QStringLiteral("events"), QJsonArray{}}, {QStringLiteral("latest_seq"), 2},
                           {QStringLiteral("truncated"), false}, {QStringLiteral("count"), 0},
                           {QStringLiteral("epoch"), banc.serveur.epoque},
                           {QStringLiteral("open_requests"),
                            QJsonArray{QJsonObject{{QStringLiteral("id"), QStringLiteral("srq-7")},
                                                   {QStringLiteral("method"), QStringLiteral("clarify")},
                                                   {QStringLiteral("params"), QJsonObject{{QStringLiteral("question"), QStringLiteral("Quelle base ?")}}}},
                                       QJsonObject{{QStringLiteral("id"), QStringLiteral("srq-8")},
                                                   {QStringLiteral("method"), QStringLiteral("sudo")},
                                                   {QStringLiteral("params"), QJsonObject{}}}}}};
    };
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->ouvrir();
    QVERIFY(prete.wait(10000));
    QCOMPARE(recues.size(), 1);
    QVERIFY(recues.first().rejouee);
    QCOMPARE(recues.first().params.value(QStringLiteral("question")).toString(), QStringLiteral("Quelle base ?"));
    // `sudo` est refusé en -32601, et la réponse au `clarify` porte le même identifiant.
    QVERIFY(banc.passerelle->canal()->repondre(QStringLiteral("srq-7"),
                                               QJsonObject{{QStringLiteral("answer"), QStringLiteral("PostgreSQL")}}));
    QTRY_VERIFY(std::any_of(banc.serveur.tramesRecues.cbegin(), banc.serveur.tramesRecues.cend(), [](const QJsonObject &t) {
        return t.value(QStringLiteral("id")).toString() == QStringLiteral("srq-7") && t.contains(QStringLiteral("result"));
    }));
    QTRY_VERIFY(std::any_of(banc.serveur.tramesRecues.cbegin(), banc.serveur.tramesRecues.cend(), [](const QJsonObject &t) {
        return t.value(QStringLiteral("id")).toString() == QStringLiteral("srq-8")
            && t.value(QStringLiteral("error")).toObject().value(QStringLiteral("code")).toInt() == -32601;
    }));
}

void TestClientPasserelle::battementPerduReconnecte()
{
    Banc banc;
    banc.serveur.repondreAuxPings = false;
    banc.passerelle->canal()->setBattement(std::chrono::milliseconds(30), std::chrono::milliseconds(200));
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->ouvrir();
    QVERIFY(prete.wait(10000));
    QTRY_VERIFY_WITH_TIMEOUT(banc.passerelle->raison().contains(QStringLiteral("battement perdu"))
                                 || prete.count() >= 2,
                             5000);
    QTRY_COMPARE_WITH_TIMEOUT(prete.count(), 2, 10000);
    QVERIFY(!banc.serveur.tramesDeMethode(QStringLiteral("gateway.ping")).isEmpty());
}

void TestClientPasserelle::fermetureSansReconnexion()
{
    Banc banc;
    QSignalSpy prete(banc.passerelle.get(), &GatewayClient::prete);
    banc.passerelle->ouvrir();
    QVERIFY(prete.wait(10000));
    AppelRpc *enAttente = banc.passerelle->canal()->requete(QStringLiteral("prompt.submit"),
                                                            QJsonObject{{QStringLiteral("text"), QStringLiteral("x")}});
    QSignalSpy echoue(enAttente, &AppelRpc::echoue);
    banc.passerelle->fermer();
    QCOMPARE(banc.passerelle->etat(), GatewayClient::Etat::Deconnecte);
    QCOMPARE(echoue.count(), 1);
    QTRY_COMPARE(banc.serveur.clientsConnectes(), 0);
    QTest::qWait(200);
    QCOMPARE(banc.serveur.filtrer("POST", QStringLiteral("/api/auth/ws-ticket")).size(), 1);
    QCOMPARE(banc.passerelle->etat(), GatewayClient::Etat::Deconnecte);
}

QTEST_GUILESS_MAIN(TestClientPasserelle)

#include "tst_client_passerelle.moc"
