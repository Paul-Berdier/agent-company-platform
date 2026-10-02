// Faux Hermes de bouclage pour les tests natifs de la station.
//
// Un serveur HTTP/1.1 minimal sur 127.0.0.1, port choisi par le système, scriptable route
// par route, qui journalise chaque requête reçue (méthode, chemin, en-têtes, corps) pour les
// assertions : `Authorization` présent ou absent, aucun `Origin`, aucun `Cookie` hors de la
// déconnexion. Il ne touche jamais au réseau : les tests ne visent jamais un serveur réel.
//
// `installerAuthentification()` reproduit, d'après le code de Hermes 0.21.5
// (hermes_cli/dashboard_auth/routes.py, native_flow.py, middleware.py), les routes publiques
// de la connexion native et la porte des routes protégées :
//
//  - `/auth/native/authorize` vérifie S256, le défi et l'hôte de bouclage du `redirect_uri`,
//    puis rend 302 vers le bouclage avec un code à usage unique et l'état reçu ;
//  - `/auth/native/token` consomme le code AVANT de vérifier PKCE (pas d'oracle) ;
//  - `/auth/native/refresh` fait TOURNER le jeton de rafraîchissement à chaque succès ; un
//    ancien jeton rejoué rend 503, comme Authelia derrière Hermes (réutilisation détectée,
//    identite.md § 12.1) ; un jeton inconnu rend 401 `session_expired` ;
//  - la porte rend 401 `{error, detail, reason, login_url}` pour un porteur invalide sur
//    une route `/api/*` protégée.

#pragma once

#include <QByteArray>
#include <QHash>
#include <QJsonObject>
#include <QJsonValue>
#include <QList>
#include <QObject>
#include <QPair>
#include <QSet>
#include <QString>
#include <QUrl>
#include <QUrlQuery>

#include <functional>
#include <optional>

class QTcpServer;
class QTcpSocket;
class QWebSocket;
class QWebSocketServer;

namespace acp::test {

struct RequeteRecue
{
    QByteArray methode;
    QString chemin;
    QUrlQuery requete;
    QHash<QByteArray, QByteArray> entetes; //!< Noms en minuscules.
    QByteArray corps;

    [[nodiscard]] bool aEntete(const QByteArray &nom) const { return entetes.contains(nom.toLower()); }
    [[nodiscard]] QByteArray entete(const QByteArray &nom) const { return entetes.value(nom.toLower()); }
    [[nodiscard]] QJsonObject json() const;
};

struct ReponseFaux
{
    int statut = 200;
    QByteArray corps;
    QList<QPair<QByteArray, QByteArray>> entetes;
    int delaiMs = 0; //!< Délai avant l'envoi, pour éprouver les appels concurrents.

    static ReponseFaux json(int statut, const QJsonValue &valeur);
    static ReponseFaux redirection(const QByteArray &cible);
};

class FauxHermes : public QObject
{
public:
    using Gestionnaire = std::function<ReponseFaux(const RequeteRecue &)>;

    explicit FauxHermes(QObject *parent = nullptr);
    ~FauxHermes() override;

    [[nodiscard]] QUrl url() const;
    [[nodiscard]] quint16 port() const;

    /*! Route exacte (méthode, chemin sans paramètres). Remplace une route existante. */
    void route(const QByteArray &methode, const QString &chemin, Gestionnaire gestionnaire);

    /*! Requêtes reçues, dans l'ordre. */
    QList<RequeteRecue> requetes;
    [[nodiscard]] int compter(const QByteArray &methode, const QString &chemin) const;
    [[nodiscard]] QList<RequeteRecue> filtrer(const QByteArray &methode, const QString &chemin) const;

    // --- Authentification native -------------------------------------------------

    /*! Installe les routes publiques et la porte des routes protégées. */
    void installerAuthentification();

    QString fournisseur = QStringLiteral("self-hosted");
    QString utilisateur = QStringLiteral("proprietaire-test");
    bool authRequise = true;
    int dureeAccesSecondes = 3600;

    //! Si non vide, l'état renvoyé au bouclage remplace celui reçu (témoin négatif).
    QByteArray etatForce;
    //! Vrai : la redirection de /authorize omet le paramètre `state`.
    bool omettreEtat = false;
    //! Vrai : les réponses n'ont pas d'en-tête `Date` (que uvicorn pose toujours).
    bool sansDate = false;
    //! Vrai : /auth/native/token rend un `token_type` autre que Bearer.
    bool typeJetonFaux = false;
    //! Vrai : /auth/native/token rend un jeton de rafraîchissement vide.
    bool sansJetonRafraichissement = false;
    //! Nombre de prochains /auth/native/refresh qui rendront 503 sans rien consommer.
    int refresh503 = 0;
    //! Vrai : le prochain /auth/native/refresh valide rend 401 `session_expired`.
    bool refreshExpire = false;
    //! Délai de réponse de /auth/native/refresh.
    int delaiRefreshMs = 0;

    QSet<QByteArray> jetonsAccesValides;
    QByteArray jetonRafraichissementCourant;
    QSet<QByteArray> jetonsRafraichissementTournes;
    QList<QByteArray> jetonsRevoques; //!< Lus dans le cookie de /auth/logout.
    QList<QByteArray> ticketsEmis;

    // Dernière demande d'autorisation reçue.
    QByteArray dernierDefi;
    QString dernierRedirectUri;
    QByteArray dernierEtat;

    /*! Émet une paire de jetons comme après une connexion réussie (sans passer par le flux). */
    QJsonObject emettreJetons();

    /*! Révoque tous les jetons d'accès courants (le prochain appel protégé rend 401). */
    void expirerAcces() { jetonsAccesValides.clear(); }

    // --- Passerelle JSON-RPC (/api/ws) ----------------------------------------------
    //
    // Sur le MÊME port que le HTTP, comme Hermes : la requête d'ouverture est lue (sans être
    // consommée), journalisée avec ses en-têtes, le ticket passé en sous-protocole est
    // consommé (usage unique) ; un ticket absent, inconnu ou déjà servi reçoit 403 avant
    // toute acceptation, comme Hermes derrière uvicorn. Accepté, le client reçoit
    // `gateway.ready`, puis la passerelle répond à `gateway.ping`, `client.capabilities` et
    // `session.events.since`, et à toute méthode scriptée dans `methodes`.

    void activerPasserelle();
    QString epoque = QStringLiteral("epoque-1");
    bool battementAnnonce = true;
    bool envoyerReady = true;
    QString sousProtocoleServi = QStringLiteral("hermes-gateway-v1");
    int fermer4401 = 0; //!< Nombre de prochaines connexions acceptées puis fermées en 4401.
    int fermer4403 = 0;
    bool refuserPoignees = false; //!< Toute ouverture reçoit 403 (ticket ou non).
    bool repondreAuxPings = true;
    QHash<QString, std::function<QJsonValue(const QJsonObject &)>> methodes;
    std::function<QJsonObject(const QJsonObject &)> rejeu; //!< Résultat de session.events.since.
    QList<QJsonObject> tramesRecues; //!< Trames reçues des clients de la passerelle.
    QList<RequeteRecue> ouvertures;  //!< Requêtes d'ouverture WebSocket reçues.
    int connexionsAcceptees = 0;

    /*! Envoie une trame au dernier client connecté. */
    void envoyer(const QJsonObject &trame);
    /*! Coupe brutalement le dernier client (perte de lien). */
    void couperClient();
    [[nodiscard]] int clientsConnectes() const;
    [[nodiscard]] QList<QJsonObject> tramesDeMethode(const QString &methode) const;

    // --- Veille du kanban (/api/plugins/kanban/events) ------------------------------
    //
    // Même port, comme `stream_events` de Hermes (plugins/kanban/dashboard/plugin_api.py) :
    // la garde `_ws_auth_ok` lit le ticket dans le sous-protocole (avec `hermes-gateway-v1`,
    // un seul ticket) ou, à défaut, dans `?ticket=` ; un ticket absent, inconnu ou déjà servi
    // reçoit 403 avant toute acceptation ; accepté, le serveur ne choisit AUCUN sous-protocole
    // (`ws.accept()` nu). `GET /api/plugins/kanban/board` est une route ordinaire (route()).

    void activerKanban();
    /*! Envoie un lot `{events, cursor}` au dernier client du kanban. */
    void envoyerKanban(const QJsonObject &lot);
    void couperKanban();
    [[nodiscard]] int clientsKanban() const;
    QList<RequeteRecue> ouverturesKanban;
    bool refuserKanban = false; //!< Toute ouverture du kanban reçoit 403.

private:
    void accepter();
    void lire(QTcpSocket *socket);
    void repondre(QTcpSocket *socket, const ReponseFaux &reponse);
    [[nodiscard]] ReponseFaux traiter(const RequeteRecue &requete);
    [[nodiscard]] bool estPublique(const QString &chemin) const;

    bool ouvrirPasserelle(QTcpSocket *socket);
    bool ouvrirKanban(QTcpSocket *socket, const RequeteRecue &requete, qsizetype finEntetes);
    void accepterPasserelle();

    QTcpServer *m_serveur = nullptr;
    QWebSocketServer *m_passerelle = nullptr;
    QWebSocketServer *m_kanban = nullptr;
    QList<QWebSocket *> m_clientsKanban;
    QList<QWebSocket *> m_clients;
    QHash<QString, Gestionnaire> m_routes;
    bool m_porte = false;
    int m_compteur = 0;
    QHash<QByteArray, QByteArray> m_codes; //!< code → défi
};

/*! base64url(SHA-256(vérificateur)) sans remplissage, calcul indépendant de la station. */
[[nodiscard]] QByteArray defiS256Reference(const QByteArray &verificateur);

} // namespace acp::test
