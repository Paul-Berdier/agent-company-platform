#include "events/VeilleKanban.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "gateway/GatewayClient.h"
#include "storage/CredentialVault.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkProxy>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrlQuery>
#include <QWebSocket>
#include <QWebSocketHandshakeOptions>

namespace acp {

VeilleKanban::VeilleKanban(ApiClient *client, QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_minuterieRegroupement(new QTimer(this))
    , m_relance(new QTimer(this))
{
    m_minuterieRegroupement->setSingleShot(true);
    m_relance->setSingleShot(true);
    connect(m_minuterieRegroupement, &QTimer::timeout, this, [this] {
        if (!m_tableau.isEmpty()) {
            emit changement(m_tableau);
        }
    });
    connect(m_relance, &QTimer::timeout, this, [this] {
        if (m_curseurConnu) {
            demanderTicket();
        } else {
            lireTableau();
        }
    });
}

VeilleKanban::~VeilleKanban()
{
    ++m_generation;
    if (m_appel) {
        m_appel->disconnect(this);
        m_appel->abort();
    }
    fermerSocket();
}

QString VeilleKanban::libelleEtat() const
{
    switch (m_etat) {
    case Etat::Arretee:
        return QStringLiteral("Arrêtée");
    case Etat::Preparation:
        return QStringLiteral("Ouverture");
    case Etat::Prete:
        return QStringLiteral("Prête");
    case Etat::Reconnexion:
        return QStringLiteral("Reconnexion");
    case Etat::Refusee:
        return QStringLiteral("Refusée");
    }
    return QStringLiteral("Inconnu");
}

void VeilleKanban::surveiller(const QString &tableau)
{
    if (tableau == m_tableau && m_etat != Etat::Arretee && m_etat != Etat::Refusee) {
        return;
    }
    arreter();
    if (!ClientGreffonPoste::identifiantValide(tableau)) {
        refuser(QStringLiteral("Identifiant de tableau illisible : veille refusée par la station."));
        return;
    }
    m_tableau = tableau;
    m_curseur = -1;
    m_curseurConnu = false;
    m_ticketReessaye = false;
    m_recul.reset();
    lireTableau();
}

void VeilleKanban::arreter()
{
    ++m_generation;
    m_relance->stop();
    m_minuterieRegroupement->stop();
    if (m_appel) {
        m_appel->disconnect(this);
        m_appel->abort();
        m_appel = nullptr;
    }
    fermerSocket();
    m_tableau.clear();
    m_curseur = -1;
    m_curseurConnu = false;
    changerEtat(Etat::Arretee);
}

void VeilleKanban::lireTableau()
{
    const quint64 generation = ++m_generation;
    changerEtat(Etat::Preparation);
    ApiRequest requete;
    requete.path = QString::fromLatin1(kCheminTableau);
    requete.query.addQueryItem(QStringLiteral("board"), m_tableau);
    requete.timeout = std::chrono::milliseconds(15000);
    m_appel = m_client->send(requete);
    connect(m_appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation) {
            return;
        }
        m_appel = nullptr;
        const QJsonValue dernier = reponse.json.object().value(QStringLiteral("latest_event_id"));
        // Un identifiant d'événement est un entier positif ou nul ; toute autre forme est
        // refusée plutôt que devinée.
        if (!dernier.isDouble() || dernier.toDouble() < 0 || dernier.toDouble() != static_cast<double>(dernier.toInteger())) {
            refuser(QStringLiteral("Réponse du kanban illisible : « latest_event_id » absent ou invalide."));
            return;
        }
        m_curseur = dernier.toInteger();
        m_curseurConnu = true;
        demanderTicket();
    });
    connect(m_appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generation || erreur.kind() == ApiFailure::Cancelled) {
            return;
        }
        m_appel = nullptr;
        if (erreur.kind() == ApiFailure::NotFound || erreur.httpStatus() == 400) {
            refuser(QStringLiteral("Tableau « %1 » introuvable dans le kanban de Hermes.").arg(m_tableau.left(80)));
            return;
        }
        if (erreur.kind() == ApiFailure::Unauthorized || erreur.kind() == ApiFailure::ClientRefusal
            || erreur.kind() == ApiFailure::Forbidden) {
            refuser(QStringLiteral("Lecture du tableau refusée : %1").arg(erreur.message()));
            return;
        }
        programmerReconnexion(QStringLiteral("Tableau illisible : %1").arg(erreur.message()));
    });
}

void VeilleKanban::demanderTicket()
{
    const quint64 generation = ++m_generation;
    changerEtat(Etat::Preparation);
    ApiRequest requete;
    requete.method = QByteArrayLiteral("POST");
    requete.path = QStringLiteral("/api/auth/ws-ticket");
    requete.timeout = std::chrono::milliseconds(15000);
    m_appel = m_client->send(requete);
    connect(m_appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation) {
            return;
        }
        m_appel = nullptr;
        QByteArray ticket = reponse.json.object().value(QStringLiteral("ticket")).toString().toUtf8();
        if (ticket.isEmpty()) {
            refuser(QStringLiteral("Hermes n'a remis aucun ticket de connexion."));
            return;
        }
        ouvrir(ticket);
        CredentialVault::wipe(ticket);
    });
    connect(m_appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generation || erreur.kind() == ApiFailure::Cancelled) {
            return;
        }
        m_appel = nullptr;
        if (erreur.kind() == ApiFailure::Unauthorized || erreur.kind() == ApiFailure::ClientRefusal) {
            refuser(QStringLiteral("Ticket refusé : %1").arg(erreur.message()));
            return;
        }
        programmerReconnexion(QStringLiteral("Ticket indisponible : %1").arg(erreur.message()));
    });
}

void VeilleKanban::ouvrir(QByteArray ticket)
{
    QUrlQuery requete;
    requete.addQueryItem(QStringLiteral("since"), QString::number(m_curseur));
    requete.addQueryItem(QStringLiteral("board"), m_tableau);
    QUrl url = m_client->resolve(QString::fromLatin1(kCheminEvenements), requete);
    if (url.isEmpty()) {
        refuser(QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }
    url.setScheme(url.scheme() == QStringLiteral("https") ? QStringLiteral("wss") : QStringLiteral("ws"));
    fermerSocket();
    // Origine VIDE, comme la passerelle : un client natif n'envoie pas d'en-tête Origin.
    m_socket = new QWebSocket(QString(), QWebSocketProtocol::VersionLatest, this);
    m_socket->setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
    connect(m_socket, &QWebSocket::connected, this, [this] {
        if (!m_socket) {
            return;
        }
        // La route du kanban accepte sans choisir de sous-protocole ; un sous-protocole autre
        // que celui de la passerelle serait une réponse hors contrat.
        const QString retenu = m_socket->subprotocol();
        if (!retenu.isEmpty() && retenu != QLatin1String(GatewayClient::kSousProtocole)) {
            refuser(QStringLiteral("Sous-protocole inattendu du kanban (« %1 »).").arg(retenu.left(40)));
            return;
        }
        m_ticketReessaye = false;
        m_recul.reset();
        m_dernierSigne = QDateTime::currentDateTimeUtc();
        changerEtat(Etat::Prete);
    });
    connect(m_socket, &QWebSocket::disconnected, this, &VeilleKanban::surFermeture);
    connect(m_socket, &QWebSocket::errorOccurred, this, &VeilleKanban::surErreur);
    connect(m_socket, &QWebSocket::textMessageReceived, this, &VeilleKanban::surMessage);

    QWebSocketHandshakeOptions options;
    options.setSubprotocols({QString::fromLatin1(GatewayClient::kSousProtocole),
                             QString::fromLatin1(GatewayClient::kPrefixeTicket) + QString::fromLatin1(ticket)});
    changerEtat(Etat::Preparation);
    m_socket->open(QNetworkRequest(url), options);
}

void VeilleKanban::surMessage(const QString &message)
{
    m_dernierSigne = QDateTime::currentDateTimeUtc();
    const QJsonObject lot = QJsonDocument::fromJson(message.toUtf8()).object();
    const QJsonValue curseur = lot.value(QStringLiteral("cursor"));
    const qsizetype nombre = lot.value(QStringLiteral("events")).toArray().size();
    if (!curseur.isDouble() || nombre == 0) {
        return; // lot vide ou illisible : rien n'a bougé à notre connaissance
    }
    const qint64 nouveau = curseur.toInteger();
    if (nouveau <= m_curseur) {
        return;
    }
    m_curseur = nouveau;
    ++m_lots;
    // Regroupement : une rafale de lots ne déclenche qu'une relecture.
    m_minuterieRegroupement->start(m_regroupement);
}

void VeilleKanban::surFermeture()
{
    if (!m_socket) {
        return;
    }
    QWebSocket *ancien = m_socket;
    m_socket = nullptr;
    ancien->disconnect(this);
    ancien->deleteLater();
    if (m_tableau.isEmpty()) {
        changerEtat(Etat::Arretee);
        return;
    }
    programmerReconnexion(QStringLiteral("Veille du kanban coupée."));
}

void VeilleKanban::surErreur()
{
    if (!m_socket) {
        return;
    }
    if (m_socket->state() == QAbstractSocket::ConnectedState) {
        return; // la fermeture qui suit est traitée par surFermeture
    }
    const QString texte = m_socket->errorString();
    QWebSocket *ancien = m_socket;
    m_socket = nullptr;
    ancien->disconnect(this);
    ancien->deleteLater();
    if (m_tableau.isEmpty()) {
        return;
    }
    // Poignée refusée (ticket périmé ou consommé : 403 avant acceptation) : UN nouvel essai.
    const bool refusHttp = texte.contains(QStringLiteral("http status code"), Qt::CaseInsensitive)
        || texte.contains(QStringLiteral("403")) || texte.contains(QStringLiteral("401"));
    if (refusHttp) {
        if (!m_ticketReessaye) {
            m_ticketReessaye = true;
            demanderTicket();
            return;
        }
        refuser(QStringLiteral("Veille du kanban refusée par Hermes (poignée de main refusée)."));
        return;
    }
    programmerReconnexion(QStringLiteral("Veille du kanban injoignable."));
}

void VeilleKanban::programmerReconnexion(const QString &raison)
{
    ++m_reconnexions;
    const auto delai = m_recul.nextDelay();
    changerEtat(Etat::Reconnexion, raison);
    m_relance->start(delai);
}

void VeilleKanban::refuser(const QString &raison)
{
    ++m_generation;
    m_relance->stop();
    fermerSocket();
    changerEtat(Etat::Refusee, raison);
}

void VeilleKanban::fermerSocket()
{
    if (!m_socket) {
        return;
    }
    QWebSocket *ancien = m_socket;
    m_socket = nullptr;
    ancien->disconnect(this);
    ancien->close(QWebSocketProtocol::CloseCodeNormal, QStringLiteral("veille fermée par la station"));
    ancien->deleteLater();
}

void VeilleKanban::changerEtat(Etat etat, const QString &raison)
{
    if (etat == m_etat && raison == m_raison) {
        return;
    }
    m_etat = etat;
    m_raison = raison;
    emit etatChange();
}

} // namespace acp
