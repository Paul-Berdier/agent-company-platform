// Canal JSON-RPC 2.0 de la passerelle de Hermes, sans réseau (testable seul).
//
// Équivalent natif de `JsonRpcRequestChannel` (apps/shared/src/json-rpc-channel.ts de
// Hermes 0.21.5), réduit à ce que la station emploie :
//
//  - un message texte = un objet JSON (plusieurs objets séparés par des fins de ligne sont
//    admis, tui_gateway/ws.py) ; une trame illisible est ignorée, comptée, jamais fatale ;
//  - identifiants du client `d1`, `d2`… (jamais en collision avec `srq-…` du serveur) ;
//  - réponse `{id, result|error}` : règle la requête en attente ; `open_requests` d'un résultat
//    (reprise, rejeu) est redistribué AVANT que l'appelant ne voie le résultat ;
//  - notification `{"method":"event","params":{type, session_id, seq, payload}}` : signal
//    typé ; `gateway.ready` déclenche `client.capabilities {server_requests: true}` et, s'il
//    l'annonce, le battement ;
//  - requête serveur `{id, method, params}` : remise au gestionnaire de CETTE méthode ; sans
//    gestionnaire, réponse immédiate -32601 « Méthode non prise en charge par la station » —
//    la station ne saisit jamais de secret ni de mot de passe pour l'agent ;
//  - délai par requête (120 s par défaut) ; à l'échéance, échec local, identifiant oublié ;
//  - battement `gateway.ping` toutes les 15 s ; échéance 45 s depuis la DERNIÈRE TRAME
//    REÇUE, quelle qu'elle soit (`heartbeatLiveness: 'any-inbound'`) ;
//  - à la fermeture, toute requête en attente échoue en « Connexion perdue » et AUCUNE n'est
//    rejouée (une `prompt.submit` rejouée serait un double tour de l'agent).

#pragma once

#include <QByteArray>
#include <QElapsedTimer>
#include <QHash>
#include <QJsonObject>
#include <QJsonValue>
#include <QObject>
#include <QPointer>
#include <QSet>
#include <QString>

#include <chrono>
#include <functional>

class QTimer;

namespace acp {

//! Erreur d'un appel JSON-RPC : rendue par Hermes, ou locale (délai, connexion perdue).
struct ErreurRpc
{
    int code = 0;
    QString message;
    QJsonValue donnees;
    bool locale = false;
};

/*! Un appel JSON-RPC en attente. Un seul signal terminal ; se détruit ensuite. */
class AppelRpc : public QObject
{
    Q_OBJECT

public:
    AppelRpc(QString identifiant, QString methode, QObject *parent = nullptr);

    [[nodiscard]] const QString &identifiant() const { return m_identifiant; }
    [[nodiscard]] const QString &methode() const { return m_methode; }

signals:
    void reussi(const QJsonValue &resultat);
    void echoue(const acp::ErreurRpc &erreur);

private:
    friend class JsonRpcChannel;
    QString m_identifiant;
    QString m_methode;
    bool m_termine = false;
};

/*! Requête du serveur vers la station (`approval`, `clarify`…). */
struct RequeteServeur
{
    QString identifiant;
    QString methode;
    QJsonObject params;
    bool rejouee = false; //!< Remise par `open_requests` après une reprise, pas en direct.
};

class JsonRpcChannel : public QObject
{
    Q_OBJECT

public:
    //! « Méthode introuvable » (tui_gateway/server.py, `_err(rid, -32601, …)`).
    static constexpr int kMethodeIntrouvable = -32601;

    /*! Émet une trame texte ; faux si le transport l'a refusée. */
    using Transport = std::function<bool(const QByteArray &)>;
    /*! Reçoit une requête serveur ; la réponse viendra par repondre() ou refuser(). */
    using Gestionnaire = std::function<void(const RequeteServeur &)>;

    explicit JsonRpcChannel(QObject *parent = nullptr);
    ~JsonRpcChannel() override;

    // --- Génération de connexion ---------------------------------------------------
    /*! Lie un transport neuf (nouvelle connexion). Le battement précédent s'arrête. */
    void attacher(Transport transport);
    /*! Délie le transport : battement arrêté, requêtes en attente échouées, jamais rejouées. */
    void detacher(const QString &raison);
    [[nodiscard]] bool estAttache() const { return static_cast<bool>(m_transport); }

    // --- Réglages (tests) ---------------------------------------------------------
    void setDelaiRequete(std::chrono::milliseconds delai) { m_delaiRequete = delai; }
    void setBattement(std::chrono::milliseconds intervalle, std::chrono::milliseconds echeance);

    // --- Requêtes du client -------------------------------------------------------
    /*! Émet `method` ; délai 0 = délai par défaut. Jamais rejouée. */
    AppelRpc *requete(const QString &methode, const QJsonObject &params = {},
                      std::chrono::milliseconds delai = std::chrono::milliseconds(0));

    // --- Requêtes du serveur ------------------------------------------------------
    /*! Gestionnaire d'une méthode serveur (`approval`, `clarify`). Remplace le précédent. */
    void definirGestionnaire(const QString &methode, Gestionnaire gestionnaire);
    /*! Répond à une requête serveur ouverte. Idempotent : la première réponse l'emporte. */
    bool repondre(const QString &identifiant, const QJsonObject &resultat);
    /*! Refuse une requête serveur ouverte par une erreur JSON-RPC. Idempotent. */
    bool refuser(const QString &identifiant, int code, const QString &message);
    /*! Remet une requête serveur aux gestionnaires (direct, ou `open_requests` rejouée). */
    void remettre(const RequeteServeur &requete);
    [[nodiscard]] bool requeteOuverte(const QString &identifiant) const;

    // --- Trames entrantes ---------------------------------------------------------
    /*! Traite un message texte reçu du transport. */
    void recevoir(const QByteArray &texte);

    // --- Battement ------------------------------------------------------------------
    void demarrerBattement();
    void arreterBattement();
    [[nodiscard]] bool battementActif() const;

    // --- Compteurs (diagnostics) ----------------------------------------------------
    [[nodiscard]] int tramesIllisibles() const { return m_tramesIllisibles; }
    [[nodiscard]] int reponsesInconnues() const { return m_reponsesInconnues; }
    [[nodiscard]] int methodesRefusees() const { return m_methodesRefusees; }

signals:
    /*! Notification `event` décodée. `seq` vaut −1 s'il est absent. */
    void evenement(const QString &type, const QString &sessionId, qint64 seq,
                   const QJsonValue &payload, const QJsonObject &parametres);
    /*! L'échéance du battement est dépassée : le propriétaire doit couper la connexion. */
    void battementEchoue(const QString &raison);
    /*! Requête serveur sans gestionnaire, déjà refusée en -32601. */
    void requeteNonPriseEnCharge(const QString &methode);

private:
    void traiterObjet(const QJsonObject &trame);
    void traiterReponse(const QJsonObject &trame);
    void envoyerTrame(const QJsonObject &trame);
    void terminer(AppelRpc *appel, const QJsonValue *resultat, const ErreurRpc *erreur);
    void redistribuerOuvertes(const QJsonValue &resultat);
    void annoncerCapacites();
    void tic();

    Transport m_transport;
    QHash<QString, QPointer<AppelRpc>> m_enAttente;
    QHash<QString, QTimer *> m_delais;
    QHash<QString, Gestionnaire> m_gestionnaires;
    QSet<QString> m_ouvertes;
    QSet<QString> m_pingsEnVol;
    quint64 m_compteur = 0;
    quint64 m_compteurBattement = 0;
    std::chrono::milliseconds m_delaiRequete{120000};
    std::chrono::milliseconds m_intervalleBattement{15000};
    std::chrono::milliseconds m_echeanceBattement{45000};
    QTimer *m_battement = nullptr;
    QElapsedTimer m_derniereTrame;
    int m_tramesIllisibles = 0;
    int m_reponsesInconnues = 0;
    int m_methodesRefusees = 0;
};

} // namespace acp

Q_DECLARE_METATYPE(acp::ErreurRpc)
