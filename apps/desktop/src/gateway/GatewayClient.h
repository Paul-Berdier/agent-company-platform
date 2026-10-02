// Client de la passerelle JSON-RPC de Hermes sur WebSocket (`/api/ws`).
//
// Séquence (hermes_cli/web_server_chat.py, tui_gateway/ws.py, Hermes 0.21.5) :
//   1. `POST /api/auth/ws-ticket` en porteur → `{ticket, ttl_seconds}` (30 s, usage unique) ;
//   2. QWebSocket SANS origine, ouvert sur `wss://<hôte>/api/ws` avec les sous-protocoles
//      `hermes-gateway-v1` et `hermes-gateway-ticket.<ticket>` ; le sous-protocole retenu doit
//      valoir `hermes-gateway-v1`, sinon fermeture et refus ; le ticket est effacé après
//      l'ouverture et n'apparaît dans aucun journal ;
//   3. première trame attendue sous 15 s : `gateway.ready {skin, change_events, replay_epoch,
//      heartbeat}` ; le canal annonce alors `client.capabilities` et démarre le battement ;
//   4. REJEU : pour chaque session suivie (marque de `seq`), `session.events.since
//      {session_id, last_seen}` ; pendant le rejeu, les trames vivantes de ces sessions sont
//      RETENUES puis rendues après le trou, filtrées par `seq` (doublons écartés) ; une
//      époque différente (Hermes redémarré) ou un historique tronqué demandent une relecture
//      de la session ; les `open_requests` sont redistribuées par le canal.
//
// Refus : un ticket refusé (fermeture 4401, ou poignée de main refusée) obtient UN nouveau
// ticket, puis l'état « Refusé » ; 4403 (hôte, origine ou discussion désactivée) et 4404 sont
// refusés tout de suite ; toute autre coupure reconnecte avec recul (1 s à 30 s, gigue).

#pragma once

#include "events/Backoff.h"

#include <QDateTime>
#include <QHash>
#include <QJsonObject>
#include <QJsonValue>
#include <QList>
#include <QObject>
#include <QPointer>
#include <QString>

#include <chrono>

class QTimer;
class QWebSocket;

namespace acp {

class ApiCall;
class ApiClient;
class JsonRpcChannel;

class GatewayClient : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int etat READ etatValeur NOTIFY etatChange)
    Q_PROPERTY(QString libelleEtat READ libelleEtat NOTIFY etatChange)
    Q_PROPERTY(QString raison READ raison NOTIFY etatChange)
    Q_PROPERTY(int reconnexions READ reconnexions NOTIFY etatChange)
    Q_PROPERTY(QString dernierSigneDeVie READ dernierSigneDeVie NOTIFY etatChange)

public:
    enum class Etat {
        Deconnecte,
        Ticket,      //!< Demande du ticket de connexion.
        Ouverture,   //!< Poignée de main WebSocket, puis attente de gateway.ready.
        Pret,
        Rejeu,       //!< Rattrapage des sessions suivies après une reconnexion.
        Reconnexion, //!< Coupure : nouvel essai programmé.
        Refuse,      //!< Refus de Hermes : aucun nouvel essai automatique.
    };
    Q_ENUM(Etat)

    static constexpr char kSousProtocole[] = "hermes-gateway-v1";
    static constexpr char kPrefixeTicket[] = "hermes-gateway-ticket.";

    explicit GatewayClient(ApiClient *client, QObject *parent = nullptr);
    ~GatewayClient() override;

    [[nodiscard]] JsonRpcChannel *canal() const { return m_canal; }

    // --- Réglages (tests) ---------------------------------------------------------
    void setRecul(const Backoff &recul) { m_recul = recul; }
    void setDelaiPremiereTrame(std::chrono::milliseconds delai) { m_delaiPremiereTrame = delai; }

    // --- Cycle de vie -------------------------------------------------------------
    /*! Ouvre la passerelle (session établie). Sans effet si déjà ouverte ou en cours. */
    void ouvrir();
    /*! Ferme proprement (déconnexion, session perdue, arrêt). Aucune requête n'est rejouée. */
    void fermer();
    /*! Nouvel essai immédiat, y compris après un refus. */
    Q_INVOKABLE void reconnecter();

    // --- Sessions suivies (rejeu) -------------------------------------------------
    /*! Suit une session : ses événements sont filtrés par `seq` et rejoués après coupure. */
    void suivreSession(const QString &sessionId, qint64 dernierSeq = -1);
    void oublierSession(const QString &sessionId);
    [[nodiscard]] qint64 marque(const QString &sessionId) const { return m_marques.value(sessionId, -1); }
    [[nodiscard]] const QString &epoque() const { return m_epoque; }

    // --- État -------------------------------------------------------------------
    [[nodiscard]] Etat etat() const { return m_etat; }
    [[nodiscard]] int etatValeur() const { return static_cast<int>(m_etat); }
    [[nodiscard]] QString libelleEtat() const;
    [[nodiscard]] const QString &raison() const { return m_raison; }
    [[nodiscard]] int reconnexions() const { return m_reconnexions; }
    [[nodiscard]] QString dernierSigneDeVie() const;
    [[nodiscard]] QString sousProtocoleRetenu() const { return m_sousProtocole; }

signals:
    void etatChange();
    /*! Événement d'une session, après filtrage par `seq` (vivant ou rejoué). */
    void evenement(const QString &type, const QString &sessionId, qint64 seq, const QJsonValue &payload);
    /*! La session doit être relue (`session.resume`) : époque changée ou rejeu tronqué. */
    void relectureRequise(const QString &sessionId, const QString &raison);
    /*! Passerelle prête (après le rejeu éventuel). */
    void prete();

private:
    void demanderTicket();
    void ouvrirSocket(QByteArray ticket);
    void surConnexion();
    void surFermeture();
    void surErreur();
    void surEvenement(const QString &type, const QString &sessionId, qint64 seq,
                      const QJsonValue &payload);
    void surPret(const QJsonObject &payload);
    void lancerRejeu();
    void terminerRejeu(const QString &sessionId);
    void delivrer(const QString &type, const QString &sessionId, qint64 seq, const QJsonValue &payload);
    void couper(const QString &raison);
    void programmerReconnexion(const QString &raison);
    void refuser(const QString &raison);
    void changerEtat(Etat etat, const QString &raison = {});
    [[nodiscard]] QUrl urlPasserelle() const;

    struct Retenu
    {
        QString type;
        qint64 seq = -1;
        QJsonValue payload;
    };

    ApiClient *m_client = nullptr;
    JsonRpcChannel *m_canal = nullptr;
    QPointer<QWebSocket> m_socket;
    QPointer<ApiCall> m_appelTicket;
    QTimer *m_premiereTrame = nullptr;
    QTimer *m_relance = nullptr;
    Backoff m_recul{std::chrono::milliseconds(1000), std::chrono::milliseconds(30000), 25};
    std::chrono::milliseconds m_delaiPremiereTrame{15000};
    Etat m_etat = Etat::Deconnecte;
    QString m_raison;
    QString m_sousProtocole;
    QString m_epoque;
    QHash<QString, qint64> m_marques;
    QHash<QString, QList<Retenu>> m_retenus; //!< Trames vivantes retenues pendant le rejeu.
    int m_rejeuxEnCours = 0;
    int m_reconnexions = 0;
    bool m_ticketReessaye = false;
    bool m_fermetureVoulue = false;
    bool m_pret = false;
    bool m_actif = false;
    QDateTime m_dernierSigne;
    quint64 m_generation = 0;
};

} // namespace acp
