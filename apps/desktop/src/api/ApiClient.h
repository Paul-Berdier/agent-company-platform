// Transport HTTP unique de la station de travail.
//
// Ce qu'il garantit, et pourquoi :
//
//  - URL de base CONFIGURABLE, jamais codée en dur. Tant que l'URL n'est pas posée, tout
//    appel est refusé en français.
//  - HTTPS imposé. Le bouclage en clair n'est accepté que sur autorisation explicite.
//  - Aucun cookie : le pot de cookies de Qt est neutralisé, et aucun `Set-Cookie` n'est
//    jamais appliqué ni relu. La session de Hermes voyage en porteur (`Authorization:
//    Bearer`), posé au moment de CHAQUE tentative depuis la session en mémoire ; il n'est
//    jamais stocké dans la requête.
//  - Sur le 401 de la PORTE de Hermes (enveloppe portant `reason`, middleware.py), un
//    seul rafraîchissement est demandé à la session, puis l'appel est réémis UNE fois,
//    mutation comprise : la porte répond avant tout gestionnaire, rien n'a été exécuté.
//    Tout autre 401 (greffon, second refus) termine l'appel.
//  - Toute écriture porte `Content-Type: application/json` (garde 415 du greffon) et un
//    corps de 64 Kio au plus, contrôlé avant l'envoi ; aucun en-tête `Origin` n'est posé
//    (garde 403 du greffon).
//  - Réessai SÉMANTIQUE : les lectures peuvent être rejouées, une mutation ne l'est
//    jamais sans clé d'idempotence.
//  - Aucune redirection suivie, aucun proxy implicite.

#pragma once

#include "api/ApiError.h"
#include "api/ApiRequest.h"

#include <QList>
#include <QObject>
#include <QPointer>
#include <QUrl>

#include <chrono>
#include <functional>

class QNetworkAccessManager;
class QNetworkReply;

namespace acp {

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
    bool m_bearerPresented = false; //!< La dernière tentative portait un jeton d'accès.
    bool m_replayedAfterRefresh = false; //!< Déjà réémis une fois après rafraîchissement.
    quint64 m_sessionGeneration = 0;
    QUrl m_url;
    QPointer<QNetworkReply> m_reply;
};

class ApiClient : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QUrl baseUrl READ baseUrl WRITE setBaseUrl NOTIFY baseUrlChanged)
    Q_PROPERTY(bool configured READ isConfigured NOTIFY baseUrlChanged)
    Q_PROPERTY(int inFlightCount READ inFlightCount NOTIFY inFlightCountChanged)

public:
    explicit ApiClient(QObject *parent = nullptr);
    ~ApiClient() override;

    // --- Configuration -------------------------------------------------------

    /*!
        Pose l'URL de base du serveur. Toute URL acceptée est normalisée sans chemin
        final ni paramètre. Un changement d'URL invalide les appels en cours : une
        session n'appartient jamais à deux serveurs.

        Renvoie une erreur vide en cas de succès, ou un refus explicite en français.
    */
    ApiError setBaseUrl(const QUrl &url);
    [[nodiscard]] QUrl baseUrl() const { return m_baseUrl; }
    [[nodiscard]] bool isConfigured() const { return !m_baseUrl.isEmpty(); }

    /*!
        Autorise le schéma `http` sur une adresse de bouclage (localhost, 127.0.0.0/8,
        ::1) et sur elle seule. Faux par défaut.
    */
    void setAllowInsecureLoopback(bool allowed);
    [[nodiscard]] bool allowsInsecureLoopback() const { return m_allowInsecureLoopback; }

    /*! Faux par défaut : aucun proxy implicite. */
    void setUseSystemProxy(bool enabled);
    [[nodiscard]] bool usesSystemProxy() const { return m_useSystemProxy; }

    /*! Chaîne d'agent utilisateur, incluant la version du produit. */
    void setUserAgent(const QByteArray &userAgent);

    // --- Session en porteur --------------------------------------------------

    /*!
        Rend le jeton d'accès courant (sans le préfixe « Bearer »), ou un tableau vide hors
        session. Appelé au moment de chaque tentative ; la valeur rendue est effacée dès
        que l'en-tête est posé.
    */
    using BearerProvider = std::function<QByteArray()>;
    void setBearerProvider(BearerProvider provider);

    /*!
        Fin du rafraîchissement demandé par `refreshRequested()`. En cas de succès, les
        appels en attente sont réémis une fois avec le nouveau jeton ; sinon ils échouent
        en « Session expirée ». Sans appel en attente, sans effet.
    */
    void refreshFinished(bool succeeded);

    //! Plafond du corps d'une écriture (garde du greffon acp-poste).
    static constexpr qsizetype kMaxWriteBodyBytes = 64 * 1024;

    // --- Émission ------------------------------------------------------------

    /*!
        Émet un appel. L'objet renvoyé appartient au client et se détruit après son
        signal terminal ; il n'est jamais nul.
    */
    ApiCall *send(const ApiRequest &request);

    /*! Nombre d'appels en vol, pour la barre d'état et l'écran de diagnostics. */
    [[nodiscard]] int inFlightCount() const;

    /*!
        Le gestionnaire réseau unique, pour les flux longs qui lisent au fil de l'eau.
        Il ne porte aucun cookie.
    */
    [[nodiscard]] QNetworkAccessManager *networkAccessManager() const { return m_manager; }

    /*!
        Construit l'URL absolue d'un chemin. Renvoie une URL vide si l'URL de base n'est
        pas posée : l'appelant doit alors refuser, et non deviner une origine.
    */
    [[nodiscard]] QUrl resolve(const QString &path, const QUrlQuery &query = {}) const;

    /*! Invalide les appels et leurs réessais. Aucun ancien appel ne change de serveur. */
    void invalidatePendingCalls();
    [[nodiscard]] quint64 sessionGeneration() const { return m_sessionGeneration; }

    // --- Politique, exposée pour les tests -----------------------------------

    /*!
        Nombre de tentatives autorisé pour cette requête.

        - méthode sûre : jusqu'à kMaxAttempts ;
        - méthode non sûre AVEC clé d'idempotence : jusqu'à kMaxAttempts ;
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
    void inFlightCountChanged();

    /*! Un appel a reçu le 401 de la porte : la session doit tourner ses jetons. */
    void refreshRequested();

    /*! Un appel porteur a reçu un 401 définitif : la session n'est plus acceptée. */
    void bearerRejected(const acp::ApiError &error);

private:
    void startAttempt(ApiCall *call);
    void handleReply(ApiCall *call, QNetworkReply *reply);
    void handleUnauthorized(ApiCall *call, const ApiError &error);
    void finishWithError(ApiCall *call, const ApiError &error);
    void finishWithResponse(ApiCall *call, const ApiResponse &response);
    void releaseCall(ApiCall *call);
    [[nodiscard]] ApiError validateBeforeSend(const ApiRequest &request) const;

    QNetworkAccessManager *m_manager = nullptr;

    QUrl m_baseUrl;
    bool m_allowInsecureLoopback = false;
    bool m_useSystemProxy = false;
    QByteArray m_userAgent;

    QList<QPointer<ApiCall>> m_inFlight;
    QList<QPointer<ApiCall>> m_awaitingRefresh;
    bool m_refreshPending = false;
    BearerProvider m_bearerProvider;
    quint64 m_sessionGeneration = 0;
    bool m_invalidating = false;
};

} // namespace acp
