// Transport HTTP unique de la station de travail.
//
// Ce qu'il garantit, et pourquoi :
//
//  - URL de base CONFIGURABLE, jamais codée en dur. L'audit constate qu'aucun domaine
//    n'est décidé (section 5.2) ; une origine en dur serait une invention. Tant que
//    l'URL n'est pas posée, tout appel est refusé en français.
//  - HTTPS imposé. Le bouclage en clair n'est accepté que sur autorisation explicite,
//    parce que la question « le desktop doit-il fonctionner contre une pile locale ? »
//    est ouverte (audit, question 14) et qu'un repli silencieux serait le pire choix.
//  - Un seul pot de cookies, partagé par les requêtes courtes ET par les flux longs.
//  - En-tête X-CSRF-Token injecté automatiquement sur POST, PUT, PATCH et DELETE, et sur
//    elles seules — c'est exactement ce que `require_csrf` exige côté serveur.
//  - Sérialisation stricte de l'appel qui fait TOURNER le jeton CSRF. GET /auth/session
//    appelle rotate_csrf_token : deux appels concurrents produisent des 403 sporadiques
//    et non reproductibles (audit, sections 9.2 et 10.3). Un seul appel rotatif est en
//    vol à la fois, et aucune méthode non sûre n'est émise pendant ce vol.
//  - Réessai SÉMANTIQUE : les lectures peuvent être rejouées, une mutation ne l'est
//    jamais sans clé d'idempotence. Le protocole interdit le rejeu ; une mission
//    relancée deux fois est un dégât réel.
//  - Aucune redirection suivie, aucun proxy implicite : le CLI, client non-navigateur
//    déjà en production, fait exactement cela (`follow_redirects=False`,
//    `trust_env=False`).

#pragma once

#include "api/ApiError.h"
#include "api/ApiRequest.h"

#include <QList>
#include <QObject>
#include <QPointer>
#include <QQueue>
#include <QUrl>

#include <chrono>

class QNetworkAccessManager;
class QNetworkReply;
class QTimer;

namespace acp {

class SessionCookieJar;

/*!
    Un appel en cours. Vit le temps de l'appel, se détruit tout seul ensuite.

    L'objet émet exactement UN signal terminal : `succeeded` ou `failed`. Un appelant
    qui n'est plus intéressé appelle `abort()`, ce qui produit `failed` avec
    ApiFailure::Cancelled — jamais un silence.
*/
class ApiCall : public QObject
{
    Q_OBJECT

public:
    explicit ApiCall(ApiRequest request, QObject *parent = nullptr);

    [[nodiscard]] const ApiRequest &request() const { return m_request; }

    /*! Numéro de la tentative en cours, à partir de 1. Publié pour les diagnostics. */
    [[nodiscard]] int attempt() const { return m_attempt; }

    /*! Nombre maximal de tentatives décidé par la politique sémantique. */
    [[nodiscard]] int maxAttempts() const { return m_maxAttempts; }

public slots:
    /*! Annule l'appel. Idempotent : un deuxième appel ne fait rien. */
    void abort();

signals:
    void succeeded(const acp::ApiResponse &response);
    void failed(const acp::ApiError &error);

private:
    friend class ApiClient;

    ApiRequest m_request;
    int m_attempt = 0;
    int m_maxAttempts = 1;
    bool m_finished = false;
    bool m_aborted = false;
    quint64 m_sessionGeneration = 0;
    QUrl m_url;
    QPointer<QNetworkReply> m_reply;
};

class ApiClient : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QUrl baseUrl READ baseUrl WRITE setBaseUrl NOTIFY baseUrlChanged)
    Q_PROPERTY(bool configured READ isConfigured NOTIFY baseUrlChanged)
    Q_PROPERTY(bool hasCsrfToken READ hasCsrfToken NOTIFY csrfTokenChanged)
    Q_PROPERTY(int inFlightCount READ inFlightCount NOTIFY inFlightCountChanged)

public:
    explicit ApiClient(QObject *parent = nullptr);
    ~ApiClient() override;

    // --- Configuration -------------------------------------------------------

    /*!
        Pose l'URL de base du serveur. Toute URL acceptée est normalisée sans chemin
        final ni paramètre. Un changement d'URL purge le pot de cookies et le jeton
        CSRF : une session n'appartient jamais à deux serveurs.

        Renvoie une erreur vide en cas de succès, ou un refus explicite en français.
    */
    ApiError setBaseUrl(const QUrl &url);
    [[nodiscard]] QUrl baseUrl() const { return m_baseUrl; }
    [[nodiscard]] bool isConfigured() const { return !m_baseUrl.isEmpty(); }

    /*!
        Autorise le schéma `http` sur une adresse de bouclage (localhost, 127.0.0.0/8,
        ::1) et sur elle seule. Faux par défaut : l'audit laisse la question ouverte, et
        un repli silencieux vers du clair serait un faux succès.
    */
    void setAllowInsecureLoopback(bool allowed);
    [[nodiscard]] bool allowsInsecureLoopback() const { return m_allowInsecureLoopback; }

    /*! Faux par défaut, comme `trust_env=False` côté CLI : aucun proxy implicite. */
    void setUseSystemProxy(bool enabled);
    [[nodiscard]] bool usesSystemProxy() const { return m_useSystemProxy; }

    /*! Chaîne d'agent utilisateur, incluant la version du produit. */
    void setUserAgent(const QByteArray &userAgent);

    // --- Jeton CSRF ----------------------------------------------------------

    /*!
        Pose le jeton CSRF détenu par le processus. Un seul jeton existe pour toute
        l'application ; il est fourni par POST /auth/login puis renouvelé par
        GET /auth/session.

        La VALEUR n'est jamais publiée : ni propriété QML, ni journal, ni diagnostic.
    */
    void setCsrfToken(const QString &token);
    [[nodiscard]] bool hasCsrfToken() const { return !m_csrfToken.isEmpty(); }
    void clearCsrfToken();

    // --- Émission ------------------------------------------------------------

    /*!
        Émet un appel ordinaire. L'objet renvoyé appartient au client et se détruit
        après son signal terminal ; il n'est jamais nul.
    */
    ApiCall *send(const ApiRequest &request);

    /*!
        Émet un appel dont le serveur fait TOURNER le jeton CSRF — aujourd'hui, et
        uniquement, GET /auth/session.

        Garanties : un seul appel rotatif en vol ; les appels rotatifs suivants sont mis
        en file ; toute méthode non sûre demandée pendant le vol attend la fin de la
        rotation, pour ne jamais partir avec un jeton périmé. C'est la parade exacte au
        « 403 Requête refusée intermittent, indiscernable d'un vrai refus de droits »
        décrit par l'audit.
    */
    ApiCall *sendCsrfRotating(const ApiRequest &request);

    /*! Nombre d'appels en vol, pour la barre d'état et l'écran de diagnostics. */
    [[nodiscard]] int inFlightCount() const;

    // --- Accès partagé pour les flux longs -----------------------------------

    /*!
        Le gestionnaire réseau unique. Le service de flux SSE l'utilise directement pour
        obtenir le QNetworkReply et lire au fil de l'eau : il DOIT être le même, sinon
        le cookie de session ne voyage pas avec le flux.
    */
    [[nodiscard]] QNetworkAccessManager *networkAccessManager() const { return m_manager; }

    [[nodiscard]] SessionCookieJar *cookieJar() const { return m_cookieJar; }

    /*!
        Construit l'URL absolue d'un chemin. Renvoie une URL vide si l'URL de base n'est
        pas posée : l'appelant doit alors refuser, et non deviner une origine.
    */
    [[nodiscard]] QUrl resolve(const QString &path, const QUrlQuery &query = {}) const;

    /*! Purge le pot de cookies et le jeton CSRF. Déconnexion, expiration, révocation. */
    void clearSessionState();

    /*! Invalide les appels et leurs réessais, sans effacer le cookie nécessaire au
        dernier POST /auth/logout. Aucun ancien appel ne change de serveur. */
    void invalidatePendingCalls();
    [[nodiscard]] quint64 sessionGeneration() const { return m_sessionGeneration; }

    // --- Politique, exposée pour les tests -----------------------------------

    /*!
        Nombre de tentatives autorisé pour cette requête.

        - méthode sûre : jusqu'à kMaxAttempts ;
        - méthode non sûre AVEC clé d'idempotence : jusqu'à kMaxAttempts, parce que le
          serveur reconnaît le rejeu et refuse un corps différent ;
        - méthode non sûre SANS clé : exactement 1. Aucune exception.
    */
    [[nodiscard]] static int plannedAttempts(const ApiRequest &request);

    /*! Vrai si l'erreur observée autorise une nouvelle tentative de CETTE requête. */
    [[nodiscard]] static bool shouldRetry(const ApiRequest &request, const ApiError &error,
                                          int attempt);

    /*! Recul avant la tentative suivante, en millisecondes, jitter compris. */
    [[nodiscard]] static std::chrono::milliseconds retryDelay(const ApiError &error, int attempt);

    //! Plafond de tentatives des appels rejouables.
    static constexpr int kMaxAttempts = 3;

signals:
    void baseUrlChanged();
    void csrfTokenChanged();
    void inFlightCountChanged();

    /*! Émis dès qu'un appel reçoit un 401. AuthManager y réagit, pas les écrans. */
    void unauthorizedObserved();

    /*! Émis dès qu'un appel reçoit un 403. Peut signaler un droit manquant OU un jeton
        CSRF périmé : seul AuthManager sait trancher, en tentant une reprise de session. */
    void forbiddenObserved();
    void sessionStateCleared();

private:
    void dispatch(ApiCall *call);
    void startAttempt(ApiCall *call);
    void handleReply(ApiCall *call, QNetworkReply *reply);
    void finishWithError(ApiCall *call, const ApiError &error);
    void finishWithResponse(ApiCall *call, const ApiResponse &response);
    void releaseCall(ApiCall *call);
    void drainPending();
    [[nodiscard]] ApiError validateBeforeSend(const ApiRequest &request) const;

    QNetworkAccessManager *m_manager = nullptr;
    SessionCookieJar *m_cookieJar = nullptr;

    QUrl m_baseUrl;
    bool m_allowInsecureLoopback = false;
    bool m_useSystemProxy = false;
    QByteArray m_userAgent;
    QString m_csrfToken;

    QList<QPointer<ApiCall>> m_inFlight;

    // Portail de rotation du jeton CSRF.
    QPointer<ApiCall> m_rotatingCall;            //!< Appel rotatif actuellement en vol.
    QQueue<QPointer<ApiCall>> m_pendingRotating; //!< Appels rotatifs en attente.
    QQueue<QPointer<ApiCall>> m_pendingUnsafe;   //!< Mutations retenues pendant une rotation.
    quint64 m_sessionGeneration = 0;
    bool m_invalidating = false;
};

} // namespace acp
