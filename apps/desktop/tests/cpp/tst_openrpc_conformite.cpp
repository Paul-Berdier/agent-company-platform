// Conformité de la station au contrat JSON-RPC épinglé (hermes/contrat/gateway-contract.openrpc.json).
//
// Le sous-ensemble employé par la station (cahier P8 § 5.3) doit figurer dans le contrat
// épinglé, avec les champs que la station lit ou envoie ; sinon ce test échoue, et une montée
// de version de Hermes qui retirerait une méthode se voit avant tout déploiement.
// `gateway.ping` n'est PAS une méthode du contrat : il est traité par le transport WebSocket
// lui-même (tui_gateway/ws.py), ce que le test constate aussi.

#include "app/BuildConfig.h"

#include <QCryptographicHash>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSet>
#include <QTest>

namespace {

QJsonObject contrat()
{
    QFile fichier(QStringLiteral(ACP_OPENRPC_FILE));
    if (!fichier.open(QIODevice::ReadOnly)) {
        qFatal("Contrat OpenRPC épinglé introuvable");
    }
    return QJsonDocument::fromJson(fichier.readAll()).object();
}

QSet<QString> noms(const QJsonArray &entrees)
{
    QSet<QString> resultat;
    for (const QJsonValue &entree : entrees) {
        resultat.insert(entree.toObject().value(QStringLiteral("name")).toString());
    }
    return resultat;
}

QJsonObject schema(const QJsonObject &racine, const QString &nom)
{
    return racine.value(QStringLiteral("components")).toObject().value(QStringLiteral("schemas")).toObject()
        .value(nom).toObject();
}

QSet<QString> proprietes(const QJsonObject &schema)
{
    const QStringList cles = schema.value(QStringLiteral("properties")).toObject().keys();
    return QSet<QString>(cles.cbegin(), cles.cend());
}

QSet<QString> requis(const QJsonObject &schema)
{
    QSet<QString> resultat;
    for (const QJsonValue &cle : schema.value(QStringLiteral("required")).toArray()) {
        resultat.insert(cle.toString());
    }
    return resultat;
}

} // namespace

class TestOpenRpcConformite : public QObject
{
    Q_OBJECT

private slots:
    void empreinteEtVersionEpinglees();
    void methodesEmployeesPresentes();
    void requetesServeurGereesPresentes();
    void notificationsTraiteesPresentes();
    void champsLusEtEnvoyes();
    void champsDeLaDiscussion();
    void battementHorsContrat();
};

void TestOpenRpcConformite::empreinteEtVersionEpinglees()
{
    QFile fichier(QStringLiteral(ACP_OPENRPC_FILE));
    QVERIFY(fichier.open(QIODevice::ReadOnly));
    const QByteArray contenu = fichier.readAll();
    QCOMPARE(QCryptographicHash::hash(contenu, QCryptographicHash::Sha256).toHex(),
             QByteArray(ACP_OPENRPC_SHA256));
    QCOMPARE(QJsonDocument::fromJson(contenu).object().value(QStringLiteral("info")).toObject()
                 .value(QStringLiteral("version")).toString(),
             QStringLiteral(ACP_OPENRPC_INFO_VERSION));
}

void TestOpenRpcConformite::methodesEmployeesPresentes()
{
    const QSet<QString> methodes = noms(contrat().value(QStringLiteral("methods")).toArray());
    for (const char *methode : {"client.capabilities", "session.list", "session.create", "session.resume",
                                "session.history", "session.events.since", "session.interrupt",
                                "session.close", "prompt.submit", "approval.respond", "request.answer", "ping",
                                // Étape P8b : discussions en attente (DiscussionsEnAttente).
                                "session.active_list"}) {
        QVERIFY2(methodes.contains(QString::fromLatin1(methode)), methode);
    }
}

void TestOpenRpcConformite::requetesServeurGereesPresentes()
{
    const QSet<QString> requetes = noms(contrat().value(QStringLiteral("x-server-requests")).toArray());
    QVERIFY(requetes.contains(QStringLiteral("approval")));
    QVERIFY(requetes.contains(QStringLiteral("clarify")));
    // Celles que la station refuse en -32601 existent bien : le refus vise des requêtes réelles.
    for (const char *refusee : {"secret", "sudo", "display.install.sudo", "vault.unlock_prompt"}) {
        QVERIFY2(requetes.contains(QString::fromLatin1(refusee)), refusee);
    }
}

void TestOpenRpcConformite::notificationsTraiteesPresentes()
{
    const QSet<QString> notifications = noms(contrat().value(QStringLiteral("x-notifications")).toArray());
    for (const char *type : {"gateway.ready", "message.start", "message.delta", "message.complete",
                             "tool.start", "tool.complete", "status.update", "error", "session.info",
                             "session.title", "sessions.changed", "request.cancel", "notice"}) {
        QVERIFY2(notifications.contains(QString::fromLatin1(type)), type);
    }
}

void TestOpenRpcConformite::champsLusEtEnvoyes()
{
    const QJsonObject racine = contrat();
    // client.capabilities {server_requests}
    QVERIFY(proprietes(schema(racine, QStringLiteral("ClientCapabilitiesParams"))).contains(QStringLiteral("server_requests")));
    // session.events.since {session_id, last_seen} → {events, latest_seq, truncated, epoch, open_requests}
    const QJsonObject depuis = schema(racine, QStringLiteral("SessionEventsSinceParams"));
    QVERIFY(proprietes(depuis).contains(QStringLiteral("session_id")));
    QVERIFY(proprietes(depuis).contains(QStringLiteral("last_seen")));
    QVERIFY(requis(depuis).contains(QStringLiteral("session_id")));
    const QSet<QString> resultat = requis(schema(racine, QStringLiteral("SessionEventsSinceResult")));
    for (const char *champ : {"events", "latest_seq", "truncated", "epoch", "open_requests"}) {
        QVERIFY2(resultat.contains(QString::fromLatin1(champ)), champ);
    }
    // open_requests : {id, method, params}
    const QSet<QString> ouverte = requis(schema(racine, QStringLiteral("OpenRequestEntry")));
    QCOMPARE(ouverte, (QSet<QString>{QStringLiteral("id"), QStringLiteral("method"), QStringLiteral("params")}));
    // gateway.ready : replay_epoch requis, heartbeat annoncé.
    const QJsonObject pret = schema(racine, QStringLiteral("GatewayReadyPayload"));
    QVERIFY(requis(pret).contains(QStringLiteral("replay_epoch")));
    QVERIFY(proprietes(pret).contains(QStringLiteral("heartbeat")));
}

void TestOpenRpcConformite::champsDeLaDiscussion()
{
    // Champs que DiscussionViewModel et DemandesAgent envoient ou lisent : présents dans le
    // contrat épinglé, sinon une montée de version de Hermes casserait la discussion en silence.
    const QJsonObject racine = contrat();
    const auto exiger = [&racine](const char *nomSchema, std::initializer_list<const char *> champs) {
        const QSet<QString> presentes = proprietes(schema(racine, QString::fromLatin1(nomSchema)));
        for (const char *champ : champs) {
            QVERIFY2(presentes.contains(QString::fromLatin1(champ)),
                     qPrintable(QStringLiteral("%1.%2").arg(QString::fromLatin1(nomSchema), QString::fromLatin1(champ))));
        }
    };
    exiger("SessionListParams", {"limit"});
    // Étape P8b : `session.active_list` (DiscussionsEnAttente) — champs lus, et l'état « waiting » qui les filtre.
    exiger("SessionActiveListResult", {"sessions"});
    exiger("SessionActiveItem", {"session_key", "status", "title", "preview", "last_active"});
    QVERIFY(schema(racine, QStringLiteral("LiveSessionStatus")).value(QStringLiteral("enum")).toArray()
                .contains(QStringLiteral("waiting")));
    exiger("SessionListResult", {"sessions"});
    exiger("SessionListRow", {"id", "title", "preview", "started_at", "message_count", "source"});
    exiger("SessionResumeParams", {"session_id"});
    exiger("SessionResumeResult", {"session_id", "messages", "info", "running", "inflight", "stored_session_id"});
    exiger("SessionCreateResult", {"session_id", "stored_session_id", "messages", "info"});
    exiger("SessionLiveInfo", {"title"});
    exiger("TranscriptMessage", {"role", "text", "timestamp", "name"});
    exiger("InflightTurn", {"assistant"});
    exiger("PromptSubmitParams", {"session_id", "text"});
    exiger("PromptSubmitResult", {"status"});
    exiger("SessionInterruptParams", {"session_id"});
    exiger("SessionCloseParams", {"session_id"});
    exiger("StreamDeltaPayload", {"text"});
    exiger("MessageCompletePayload", {"text", "status", "warning", "error", "failure_reason"});
    exiger("ToolStartPayload", {"tool_id", "name"});
    exiger("ToolCompletePayload", {"tool_id", "name", "summary", "duration_s"});
    exiger("StatusUpdatePayload", {"text"});
    exiger("ErrorPayload", {"message"});
    exiger("NoticePayload", {"message"});
    exiger("SessionTitlePayload", {"session_id", "title"});
    exiger("RequestCancelPayload", {"id", "reason"});
    exiger("ApprovalRequestParams", {"session_id", "command", "description", "choices", "tool_name"});
    exiger("ApprovalResult", {"choice"});
    exiger("ClarifyRequestParams", {"session_id", "question", "choices", "multi_select", "questions", "answers"});
    exiger("ClarifyQuestion", {"qid", "question", "choices", "multi_select"});
    exiger("ClarifyResult", {"answer", "answers"});
    // Valeurs énumérées interprétées par la station.
    QJsonArray statuts = schema(racine, QStringLiteral("PromptSubmitStatus")).value(QStringLiteral("enum")).toArray();
    for (const char *statut : {"streaming", "queued", "steered", "redirected"}) {
        QVERIFY2(statuts.contains(QString::fromLatin1(statut)), statut);
    }
    statuts = schema(racine, QStringLiteral("TurnStatus")).value(QStringLiteral("enum")).toArray();
    for (const char *statut : {"complete", "error", "interrupted"}) {
        QVERIFY2(statuts.contains(QString::fromLatin1(statut)), statut);
    }
    const QJsonArray choix = schema(racine, QStringLiteral("ApprovalChoice")).value(QStringLiteral("enum")).toArray();
    for (const char *valeur : {"once", "session", "always", "deny"}) {
        QVERIFY2(choix.contains(QString::fromLatin1(valeur)), valeur);
    }
}

void TestOpenRpcConformite::battementHorsContrat()
{
    const QSet<QString> methodes = noms(contrat().value(QStringLiteral("methods")).toArray());
    QVERIFY2(!methodes.contains(QStringLiteral("gateway.ping")),
             "gateway.ping est traité par le transport (tui_gateway/ws.py), hors du contrat");
}

QTEST_APPLESS_MAIN(TestOpenRpcConformite)

#include "tst_openrpc_conformite.moc"
