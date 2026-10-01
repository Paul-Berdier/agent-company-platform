#include "gateway/GatewayClient.h"

#include "api/ApiClient.h"
#include "gateway/JsonRpcChannel.h"
#include "storage/CredentialVault.h"

#include <QJsonArray>
#include <QNetworkProxy>
#include <QNetworkRequest>
#include <QTimer>
#include <QWebSocket>
#include <QWebSocketHandshakeOptions>

namespace acp {

GatewayClient::GatewayClient(ApiClient *client, QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_canal(new JsonRpcChannel(this))
    , m_premiereTrame(new QTimer(this))
    , m_relance(new QTimer(this))
{
    m_premiereTrame->setSingleShot(true);
    m_relance->setSingleShot(true);
    connect(m_premiereTrame, &QTimer::timeout, this, [this] {
        couper(QStringLiteral("Hermes n'a pas envoyé gateway.ready dans le délai imparti"));
    });
    connect(m_relance, &QTimer::timeout, this, &GatewayClient::demanderTicket);
    connect(m_canal, &JsonRpcChannel::evenement, this,
            [this](const QString &type, const QString &sessionId, qint64 seq, const QJsonValue &payload,
                   const QJsonObject &) { surEvenement(type, sessionId, seq, payload); });
    connect(m_canal, &JsonRpcChannel::battementEchoue, this, [this](const QString &raison) {
        couper(QStringLiteral("battement perdu (%1)").arg(raison));
    });
}

GatewayClient::~GatewayClient()
{
    m_actif = false;
    if (m_socket) {
        m_socket->disconnect(this);
        m_socket->abort();
    }
}

QString GatewayClient::libelleEtat() const
{
    switch (m_etat) {
    case Etat::Deconnecte: return QStringLiteral("Déconnectée");
    case Etat::Ticket: return QStringLiteral("Demande du ticket");
    case Etat::Ouverture: return QStringLiteral("Ouverture");
    case Etat::Pret: return QStringLiteral("Prête");
    case Etat::Rejeu: return QStringLiteral("Rattrapage des sessions");
    case Etat::Reconnexion: return QStringLiteral("Reconnexion");
    case Etat::Refuse: return QStringLiteral("Refusée");
    }
    return QStringLiteral("Inconnu");
}

QString GatewayClient::dernierSigneDeVie() const
{
    return m_dernierSigne.isValid()
        ? m_dernierSigne.toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm:ss"))
        : QStringLiteral("Jamais");
}

void GatewayClient::changerEtat(Etat etat, const QString &raison)
{
    if (m_etat == etat && m_raison == raison) {
        return;
    }
    m_etat = etat;
    m_raison = raison;
    emit etatChange();
}

QUrl GatewayClient::urlPasserelle() const
{
    QUrl url = m_client->resolve(QStringLiteral("/api/ws"));
    if (url.isEmpty()) {
        return {};
    }
    url.setScheme(url.scheme() == QStringLiteral("https") ? QStringLiteral("wss") : QStringLiteral("ws"));
    return url;
}

// --- Cycle de vie ------------------------------------------------------------------

void GatewayClient::ouvrir()
{
    m_actif = true;
    if (m_etat == Etat::Ticket || m_etat == Etat::Ouverture || m_etat == Etat::Pret
        || m_etat == Etat::Rejeu) {
        return;
    }
    m_ticketReessaye = false;
    m_relance->stop();
    demanderTicket();
}

void GatewayClient::reconnecter()
{
    m_actif = true;
    m_ticketReessaye = false;
    m_relance->stop();
    if (m_socket) {
        m_fermetureVoulue = true;
        m_socket->disconnect(this);
        m_socket->abort();
        m_socket->deleteLater();
        m_socket = nullptr;
    }
    m_canal->detacher(QStringLiteral("reconnexion demandée"));
    demanderTicket();
}

void GatewayClient::fermer()
{
    m_actif = false;
    ++m_generation;
    m_relance->stop();
    m_premiereTrame->stop();
    if (m_appelTicket) {
        m_appelTicket->abort();
        m_appelTicket = nullptr;
    }
    m_retenus.clear();
    m_rejeuxEnCours = 0;
    m_pret = false;
    if (m_socket) {
        m_fermetureVoulue = true;
        m_socket->disconnect(this);
        m_socket->close(QWebSocketProtocol::CloseCodeNormal, QStringLiteral("station fermée"));
        m_socket->deleteLater();
        m_socket = nullptr;
    }
    m_canal->detacher(QStringLiteral("passerelle fermée par la station"));
    changerEtat(Etat::Deconnecte);
}

void GatewayClient::demanderTicket()
{
    if (!m_actif) {
        return;
    }
    const quint64 generation = ++m_generation;
    changerEtat(Etat::Ticket);
    ApiRequest requete;
    requete.method = QByteArrayLiteral("POST");
    requete.path = QStringLiteral("/api/auth/ws-ticket");
    requete.timeout = std::chrono::milliseconds(15000);
    m_appelTicket = m_client->send(requete);
    connect(m_appelTicket, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation) {
            return;
        }
        QByteArray ticket = reponse.json.object().value(QStringLiteral("ticket")).toString().toUtf8();
        if (ticket.isEmpty()) {
            refuser(QStringLiteral("Hermes n'a remis aucun ticket de connexion."));
            return;
        }
        ouvrirSocket(ticket);
        CredentialVault::wipe(ticket);
    });
    connect(m_appelTicket, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generation || erreur.kind() == ApiFailure::Cancelled) {
            return;
        }
        if (erreur.kind() == ApiFailure::Unauthorized || erreur.kind() == ApiFailure::ClientRefusal) {
            // La session gère la reconnexion : la passerelle attend une session valide.
            refuser(QStringLiteral("Ticket refusé : %1").arg(erreur.message()));
            return;
        }
        programmerReconnexion(QStringLiteral("Ticket indisponible : %1").arg(erreur.message()));
    });
}

void GatewayClient::ouvrirSocket(QByteArray ticket)
{
    const QUrl url = urlPasserelle();
    if (url.isEmpty()) {
        refuser(QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }
    if (m_socket) {
        m_socket->disconnect(this);
        m_socket->abort();
        m_socket->deleteLater();
    }
    m_fermetureVoulue = false;
    m_pret = false;
    // Origine VIDE : un client natif n'en envoie pas ; la garde de Hermes n'exige l'Origin
    // que s'il est présent (web_server_chat.py, `_ws_host_origin_reason`).
    m_socket = new QWebSocket(QString(), QWebSocketProtocol::VersionLatest, this);
    m_socket->setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
    QPointer<QWebSocket> socket(m_socket);
    connect(m_socket, &QWebSocket::connected, this, &GatewayClient::surConnexion);
    connect(m_socket, &QWebSocket::disconnected, this, &GatewayClient::surFermeture);
    connect(m_socket, &QWebSocket::errorOccurred, this, &GatewayClient::surErreur);
    connect(m_socket, &QWebSocket::textMessageReceived, this, [this](const QString &message) {
        m_dernierSigne = QDateTime::currentDateTimeUtc();
        m_canal->recevoir(message.toUtf8());
    });
    connect(m_socket, &QWebSocket::binaryMessageReceived, this, [this](const QByteArray &message) {
        m_dernierSigne = QDateTime::currentDateTimeUtc();
        m_canal->recevoir(message);
    });

    QWebSocketHandshakeOptions options;
    // Le ticket ne voyage que dans le sous-protocole, jamais dans l'URL ni un journal ; Qt en
    // garde une copie dans les options de la poignée de main jusqu'à la fin du socket.
    options.setSubprotocols({QString::fromLatin1(kSousProtocole),
                             QString::fromLatin1(kPrefixeTicket) + QString::fromLatin1(ticket)});
    changerEtat(Etat::Ouverture);
    m_socket->open(QNetworkRequest(url), options);
}

void GatewayClient::surConnexion()
{
    if (!m_socket) {
        return;
    }
    m_sousProtocole = m_socket->subprotocol();
    if (m_sousProtocole != QLatin1String(kSousProtocole)) {
        refuser(QStringLiteral("Sous-protocole inattendu (« %1 ») : connexion refusée par la station.")
                    .arg(m_sousProtocole.isEmpty() ? QStringLiteral("aucun") : m_sousProtocole.left(40)));
        return;
    }
    QPointer<QWebSocket> socket(m_socket);
    m_canal->attacher([socket](const QByteArray &texte) {
        return socket && socket->sendTextMessage(QString::fromUtf8(texte)) >= 0;
    });
    m_dernierSigne = QDateTime::currentDateTimeUtc();
    m_premiereTrame->start(m_delaiPremiereTrame);
}

void GatewayClient::surErreur()
{
    if (!m_socket || m_fermetureVoulue) {
        return;
    }
    const QAbstractSocket::SocketError code = m_socket->error();
    const QString texte = m_socket->errorString();
    if (m_socket->state() == QAbstractSocket::ConnectedState) {
        return; // la fermeture qui suit est traitée par surFermeture
    }
    // Poignée de main refusée par une réponse HTTP (Hermes ferme avant d'accepter : 403) :
    // un ticket périmé ou déjà consommé y ressemble, il obtient UN nouvel essai.
    const bool refusHttp = texte.contains(QStringLiteral("http status code"), Qt::CaseInsensitive)
        || texte.contains(QStringLiteral("403")) || texte.contains(QStringLiteral("401"));
    QWebSocket *ancien = m_socket;
    m_socket = nullptr;
    ancien->disconnect(this);
    ancien->deleteLater();
    m_canal->detacher(QStringLiteral("ouverture impossible"));
    if (refusHttp) {
        if (!m_ticketReessaye) {
            m_ticketReessaye = true;
            demanderTicket();
            return;
        }
        refuser(QStringLiteral("Hermes refuse l'ouverture de la passerelle (%1).").arg(texte));
        return;
    }
    Q_UNUSED(code)
    programmerReconnexion(QStringLiteral("Passerelle injoignable : %1").arg(texte));
}

void GatewayClient::surFermeture()
{
    if (!m_socket) {
        return;
    }
    const int code = static_cast<int>(m_socket->closeCode());
    const QString motif = m_socket->closeReason();
    QWebSocket *ancien = m_socket;
    m_socket = nullptr;
    ancien->disconnect(this);
    ancien->deleteLater();
    m_premiereTrame->stop();
    m_retenus.clear();
    m_rejeuxEnCours = 0;
    m_pret = false;
    m_canal->detacher(QStringLiteral("passerelle fermée (code %1)").arg(code));
    if (m_fermetureVoulue || !m_actif) {
        changerEtat(Etat::Deconnecte);
        return;
    }
    switch (code) {
    case 4401:
        if (!m_ticketReessaye) {
            m_ticketReessaye = true;
            demanderTicket();
            return;
        }
        refuser(QStringLiteral("Ticket de connexion refusé par Hermes (4401)."));
        return;
    case 4403:
        refuser(QStringLiteral("Passerelle refusée par Hermes (4403 : hôte, origine ou discussion "
                               "désactivée)."));
        return;
    case 4404:
        refuser(QStringLiteral("Discussion intégrée désactivée sur ce Hermes (4404)."));
        return;
    default:
        programmerReconnexion(motif.isEmpty()
                                  ? QStringLiteral("Passerelle coupée (code %1).").arg(code)
                                  : QStringLiteral("Passerelle coupée (code %1 : %2).").arg(code).arg(motif));
        return;
    }
}

void GatewayClient::couper(const QString &raison)
{
    if (!m_socket) {
        return;
    }
    QWebSocket *ancien = m_socket;
    m_socket = nullptr;
    ancien->disconnect(this);
    ancien->abort();
    ancien->deleteLater();
    m_premiereTrame->stop();
    m_retenus.clear();
    m_rejeuxEnCours = 0;
    m_pret = false;
    m_canal->detacher(raison);
    programmerReconnexion(QStringLiteral("Passerelle coupée : %1.").arg(raison));
}

void GatewayClient::programmerReconnexion(const QString &raison)
{
    if (!m_actif) {
        changerEtat(Etat::Deconnecte, raison);
        return;
    }
    ++m_reconnexions;
    const auto delai = m_recul.nextDelay();
    m_relance->start(delai);
    changerEtat(Etat::Reconnexion,
                QStringLiteral("%1 Nouvel essai à %2.")
                    .arg(raison, QDateTime::currentDateTime().addMSecs(delai.count())
                                     .toString(QStringLiteral("HH:mm:ss"))));
}

void GatewayClient::refuser(const QString &raison)
{
    m_relance->stop();
    m_premiereTrame->stop();
    if (m_socket) {
        QWebSocket *ancien = m_socket;
        m_socket = nullptr;
        ancien->disconnect(this);
        ancien->abort();
        ancien->deleteLater();
    }
    m_canal->detacher(raison);
    changerEtat(Etat::Refuse, raison);
}

// --- Événements et rejeu -----------------------------------------------------------

void GatewayClient::suivreSession(const QString &sessionId, qint64 dernierSeq)
{
    if (sessionId.isEmpty()) {
        return;
    }
    if (!m_marques.contains(sessionId) || dernierSeq > m_marques.value(sessionId)) {
        m_marques.insert(sessionId, dernierSeq);
    }
}

void GatewayClient::oublierSession(const QString &sessionId)
{
    m_marques.remove(sessionId);
    m_retenus.remove(sessionId);
}

void GatewayClient::surEvenement(const QString &type, const QString &sessionId, qint64 seq,
                                 const QJsonValue &payload)
{
    if (type == QLatin1String("gateway.ready")) {
        surPret(payload.toObject());
        return;
    }
    if (!sessionId.isEmpty() && seq >= 0 && m_retenus.contains(sessionId)) {
        // Rejeu en vol pour cette session : la trame vivante attend la fin du trou.
        m_retenus[sessionId].append(Retenu{type, seq, payload});
        return;
    }
    delivrer(type, sessionId, seq, payload);
}

void GatewayClient::delivrer(const QString &type, const QString &sessionId, qint64 seq,
                             const QJsonValue &payload)
{
    if (!sessionId.isEmpty() && seq >= 0 && m_marques.contains(sessionId)) {
        if (seq <= m_marques.value(sessionId)) {
            return; // doublon : déjà rendu (vivant ou rejoué)
        }
        m_marques.insert(sessionId, seq);
    }
    emit evenement(type, sessionId, seq, payload);
}

void GatewayClient::surPret(const QJsonObject &payload)
{
    m_premiereTrame->stop();
    m_ticketReessaye = false;
    m_recul.reset();
    m_pret = true;
    const QString epoque = payload.value(QStringLiteral("replay_epoch")).toString();
    if (!m_epoque.isEmpty() && !epoque.isEmpty() && epoque != m_epoque) {
        // Hermes a redémarré : les marques décrivent une numérotation qui n'existe plus.
        for (auto it = m_marques.begin(); it != m_marques.end(); ++it) {
            it.value() = -1;
            emit relectureRequise(it.key(), QStringLiteral("Hermes a redémarré : la session est relue."));
        }
    }
    if (!epoque.isEmpty()) {
        m_epoque = epoque;
    }
    lancerRejeu();
}

void GatewayClient::lancerRejeu()
{
    QList<QPair<QString, qint64>> aRejouer;
    for (auto it = m_marques.cbegin(); it != m_marques.cend(); ++it) {
        if (it.value() >= 0) {
            aRejouer.append({it.key(), it.value()});
        }
    }
    if (aRejouer.isEmpty()) {
        changerEtat(Etat::Pret);
        emit prete();
        return;
    }
    changerEtat(Etat::Rejeu);
    m_rejeuxEnCours = static_cast<int>(aRejouer.size());
    for (const auto &[sessionId, marque] : aRejouer) {
        m_retenus.insert(sessionId, {});
    }
    const quint64 generation = m_generation;
    for (const auto &[sessionId, marque] : aRejouer) {
        AppelRpc *appel = m_canal->requete(QStringLiteral("session.events.since"),
                                           QJsonObject{{QStringLiteral("session_id"), sessionId},
                                                       {QStringLiteral("last_seen"), marque}},
                                           std::chrono::milliseconds(10000));
        const QString id = sessionId;
        connect(appel, &AppelRpc::reussi, this, [this, generation, id](const QJsonValue &brut) {
            if (generation != m_generation) {
                return;
            }
            const QJsonObject resultat = brut.toObject();
            const QString epoque = resultat.value(QStringLiteral("epoch")).toString();
            if (!epoque.isEmpty() && !m_epoque.isEmpty() && epoque != m_epoque) {
                m_epoque = epoque;
                m_marques.insert(id, -1);
                emit relectureRequise(id, QStringLiteral("Époque de rejeu différente : la session est relue."));
            } else {
                for (const QJsonValue &valeur : resultat.value(QStringLiteral("events")).toArray()) {
                    const QJsonObject evt = valeur.toObject();
                    const QString type = evt.value(QStringLiteral("type")).toString();
                    if (type.isEmpty()) {
                        continue;
                    }
                    const QJsonValue seq = evt.value(QStringLiteral("seq"));
                    delivrer(type, id, seq.isDouble() ? static_cast<qint64>(seq.toDouble()) : -1,
                             evt.value(QStringLiteral("payload")));
                }
                if (resultat.value(QStringLiteral("truncated")).toBool()) {
                    const QJsonValue dernier = resultat.value(QStringLiteral("latest_seq"));
                    if (dernier.isDouble()) {
                        m_marques.insert(id, static_cast<qint64>(dernier.toDouble()));
                    }
                    emit relectureRequise(id, QStringLiteral("Historique de rejeu tronqué : la session est relue."));
                }
            }
            terminerRejeu(id);
        });
        connect(appel, &AppelRpc::echoue, this, [this, generation, id](const ErreurRpc &erreur) {
            if (generation != m_generation) {
                return;
            }
            emit relectureRequise(id, QStringLiteral("Rejeu impossible (%1) : la session est relue.")
                                          .arg(erreur.message));
            terminerRejeu(id);
        });
    }
}

void GatewayClient::terminerRejeu(const QString &sessionId)
{
    const QList<Retenu> retenus = m_retenus.take(sessionId);
    for (const Retenu &trame : retenus) {
        delivrer(trame.type, sessionId, trame.seq, trame.payload);
    }
    if (--m_rejeuxEnCours <= 0) {
        m_rejeuxEnCours = 0;
        changerEtat(Etat::Pret);
        emit prete();
    }
}

} // namespace acp
