// Machine à états de la session humaine.
//
// Rappel des faits d'API, relevés par l'audit (section 3.2) et non négociables :
//
//   - il n'existe QUE quatre modes d'authentification, et aucun bearer utilisateur,
//     aucune clé d'API personnelle, aucun OAuth ;
//   - la session humaine est portée par le cookie `acp_session`, HttpOnly,
//     SameSite=strict ; les DEUX routes SSE lisent ce même cookie et rien d'autre ;
//   - l'en-tête `X-CSRF-Token` est obligatoire sur POST, PUT, PATCH et DELETE ;
//   - `GET /auth/session` relit la session, met `last_seen_at` à jour, FAIT TOURNER le
//     jeton CSRF, et n'allonge PAS `expires_at` ;
//   - le routeur d'authentification n'expose que cinq routes : aucun changement de mot
//     de passe, aucune création d'un second compte, aucun listage ni révocation des
//     autres sessions.
//
// Conséquences implémentées ici :
//
//   - aucun secret n'atteint QML. Ni le mot de passe, ni le cookie, ni le jeton CSRF ne
//     sont exposés en propriété ; le mot de passe voyage en QByteArray et est effacé
//     juste après l'envoi ;
//   - l'appel qui fait tourner le jeton CSRF passe par ApiClient::sendCsrfRotating(),
//     qui garantit son unicité ;
//   - un 401 fait passer l'état à Revoked ou Expired selon ce que le serveur dit, jamais
//     à « peut-être encore connecté » ;
//   - un 403 ne fait PAS tomber la session : il peut venir d'un droit manquant. Une
//     seule tentative de reprise de session est déclenchée, et une seule.

#pragma once

#include "api/ApiError.h"
#include "app/QmlEnums.h"

#include <QDateTime>
#include <QJsonObject>
#include <QObject>
#include <QString>

namespace acp {

class ApiClient;

/*! Identité publique de l'utilisateur connecté. Ne contient aucun secret. */
struct AuthenticatedUser
{
    QString id;
    QString displayName;
    QString platformRole; //!< « owner », « operator », « member » ou « viewer ».

    [[nodiscard]] bool isValid() const { return !id.isEmpty(); }
};

class AuthManager : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int state READ stateValue NOTIFY stateChanged)
    Q_PROPERTY(QString stateLabel READ stateLabel NOTIFY stateChanged)
    Q_PROPERTY(QString userDisplayName READ userDisplayName NOTIFY userChanged)
    Q_PROPERTY(QString userId READ userId NOTIFY userChanged)
    Q_PROPERTY(QString platformRole READ platformRole NOTIFY userChanged)
    Q_PROPERTY(QDateTime expiresAt READ expiresAt NOTIFY userChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY stateChanged)
    Q_PROPERTY(bool bootstrapRequired READ bootstrapRequired NOTIFY bootstrapRequiredChanged)
    Q_PROPERTY(bool busy READ isBusy NOTIFY stateChanged)

public:
    explicit AuthManager(ApiClient *client, QObject *parent = nullptr);

    [[nodiscard]] SessionStatus::State state() const { return m_state; }
    [[nodiscard]] int stateValue() const { return static_cast<int>(m_state); }
    [[nodiscard]] QString stateLabel() const;
    [[nodiscard]] QString userDisplayName() const { return m_user.displayName; }
    [[nodiscard]] QString userId() const { return m_user.id; }
    [[nodiscard]] QString platformRole() const { return m_user.platformRole; }
    [[nodiscard]] const QDateTime &expiresAt() const { return m_expiresAt; }
    [[nodiscard]] const QString &lastError() const { return m_lastError; }
    [[nodiscard]] bool bootstrapRequired() const { return m_bootstrapRequired; }
    [[nodiscard]] bool isBusy() const { return m_state == SessionStatus::Connecting; }

    /*! Interroge `GET /auth/status`. Public : appelable avant toute session. */
    Q_INVOKABLE void refreshBootstrapStatus();

    /*!
        Tente `POST /auth/login`.

        Le mot de passe est reçu en QString parce que QML ne sait pas produire autre
        chose ; il est converti en QByteArray, envoyé, puis le tampon est écrasé. C'est
        la meilleure garantie possible depuis QML, et elle est documentée comme telle
        dans docs/native-desktop-architecture.md.
    */
    Q_INVOKABLE void logIn(const QString &login, const QString &password);

    /*! Corps de `POST /auth/login`, conforme à `LoginRequest` côté serveur. */
    [[nodiscard]] static QJsonObject loginRequestBody(const QString &login,
                                                      const QString &password);

    /*! Applique une réponse de session (`AuthSessionResponse` côté serveur). Appelé après
        connexion et reprise ; public pour que les tests l'éprouvent sur la forme
        réellement servie par l'API. */
    void applySessionPayload(const QJsonObject &payload);

    /*! Tente `POST /auth/logout`, puis purge l'état local quoi qu'il arrive. */
    Q_INVOKABLE void logOut();

    /*!
        Reprise au lancement : relit `GET /auth/session`.

        Sans cookie détenu, la reprise échoue immédiatement en Disconnected, SANS appel
        réseau : la station ne fait pas semblant d'essayer.
    */
    Q_INVOKABLE void resumeSession();

    /*! Purge locale : cookies, jeton CSRF, identité. N'appelle pas le serveur. */
    void forgetLocalSession(SessionStatus::State newState, const QString &reason);

signals:
    void stateChanged();
    void userChanged();
    void bootstrapRequiredChanged();

    /*! Émis à chaque transition vers un état non connecté, avec une raison française. */
    void sessionLost(const QString &reason);

    /*! Émis quand une session vient d'être établie. Les services qui dépendent d'une
        session (flux, compatibilité) s'y accrochent. */
    void sessionEstablished();

private:
    void setState(SessionStatus::State state, const QString &reason = {});
    void handleUnauthorized();
    void handleForbidden();

    ApiClient *m_client = nullptr;
    SessionStatus::State m_state = SessionStatus::Disconnected;
    AuthenticatedUser m_user;
    QDateTime m_expiresAt;
    QString m_lastError;
    bool m_bootstrapRequired = false;
    bool m_recoveryAttempted = false; //!< Une seule reprise après un 403, et une seule.
    quint64 m_operation = 0;
};

} // namespace acp
