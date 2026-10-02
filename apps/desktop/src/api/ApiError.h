// Erreurs d'API typées, avec un message français destiné à l'interface.
//
// Règle de doctrine : une erreur affiche la cause telle que le serveur l'a donnée,
// l'action réellement possible, et de quoi la retrouver. Elle ne se déguise jamais en
// état vide, et le client n'invente jamais un texte à la place du serveur : quand le
// serveur fournit un message, c'est lui qui est montré ; le libellé du client sert
// seulement de titre de famille. Seuls les messages FIXES de la porte d'authentification
// de Hermes, rédigés en anglais, sont rendus en français par une table d'équivalence ;
// un message inconnu est montré tel quel.
//
// Trois formes d'erreur sont lues (hermes_cli/dashboard_auth, greffon acp-poste) :
//   - porte de Hermes : `{"error", "detail", "reason", "login_url"}` (401) ;
//   - greffon acp-poste : `{"detail": {"code", "message"}}`, et pour le routage refusé
//     `{"detail": {"code", "message", "refus": [...]}}` (422) ;
//   - FastAPI : `{"detail": "…"}` ou `{"detail": [{"msg", "loc"}…]}`.

#pragma once

#include "app/QmlEnums.h"

#include <QAbstractSocket>
#include <QByteArray>
#include <QJsonArray>
#include <QMetaType>
#include <QNetworkReply>
#include <QString>

#include <optional>

namespace acp {

/*!
    Description complète d'un échec d'appel.

    Le type est un Q_GADGET : il traverse la frontière QML comme une valeur, sans
    propriétaire ni cycle de vie à gérer. Aucun champ ne contient de secret : la
    construction depuis une réponse HTTP ne recopie ni en-tête d'autorisation, ni
    cookie, ni paramètre de requête signé.
*/
class ApiError
{
    Q_GADGET
    Q_PROPERTY(int kind READ kindValue CONSTANT)
    Q_PROPERTY(int httpStatus READ httpStatus CONSTANT)
    Q_PROPERTY(QString title READ title CONSTANT)
    Q_PROPERTY(QString detail READ detail CONSTANT)
    Q_PROPERTY(QString message READ message CONSTANT)
    Q_PROPERTY(QString code READ code CONSTANT)
    Q_PROPERTY(bool retryable READ isRetryable CONSTANT)
    Q_PROPERTY(int retryAfterSeconds READ retryAfterSecondsValue CONSTANT)

public:
    ApiError() = default;

    ApiError(ApiFailure::Kind kind, QString detail, int httpStatus = 0);

    /*! Construit l'erreur correspondant à un code HTTP et au détail déjà extrait. */
    static ApiError fromHttpStatus(int httpStatus, const QString &serverDetail);

    /*!
        Construit l'erreur d'une réponse HTTP en erreur : famille, détail (traduit s'il
        s'agit d'un message fixe de Hermes), code du serveur, raison de la porte, refus
        détaillés du routage. Le corps brut est conservé (hors QML).
    */
    static ApiError fromResponse(int httpStatus, const QByteArray &body);

    /*! Construit un refus émis par le client lui-même, avant tout envoi. */
    static ApiError refusal(QString reason);

    [[nodiscard]] ApiFailure::Kind kind() const { return m_kind; }
    [[nodiscard]] int kindValue() const { return static_cast<int>(m_kind); }
    [[nodiscard]] int httpStatus() const { return m_httpStatus; }

    /*! Titre de famille, en français, choisi par le client. */
    [[nodiscard]] QString title() const;

    /*! Détail donné par le serveur, ou précision du client quand le serveur s'est tu. */
    [[nodiscard]] const QString &detail() const { return m_detail; }

    /*! Titre et détail assemblés pour un affichage sur une seule ligne. */
    [[nodiscard]] QString message() const;

    /*!
        Code machine rendu par le serveur : `detail.code` du greffon (« question_fermee »,
        « origine »…) ou `error` de la porte (« session_expired », « unauthenticated »).
        Vide si le serveur n'en donne pas.
    */
    [[nodiscard]] const QString &code() const { return m_code; }

    /*!
        `reason` de l'enveloppe 401 de la porte d'authentification de Hermes
        (middleware.py, `_unauth_response`). Non vide seulement pour CETTE enveloppe : c'est
        le signe qu'aucun gestionnaire n'a tourné, et qu'un rafraîchissement suivi d'une
        réémission est sûr, même pour une mutation.
    */
    [[nodiscard]] const QString &gateReason() const { return m_gateReason; }
    [[nodiscard]] bool isGateRejection() const { return !m_gateReason.isEmpty(); }

    /*! Refus détaillés d'une table de routage refusée (422), tels que rendus. */
    [[nodiscard]] const QJsonArray &refusals() const { return m_refusals; }

    /*!
        Vrai si la famille d'erreur autorise un nouvel essai du MÊME appel.

        Ce n'est PAS une autorisation de rejouer une mutation : la décision finale
        appartient à ApiClient, qui n'accepte le réessai d'une méthode non sûre que si
        l'appel porte une clé d'idempotence. Voir ApiClient::shouldRetry().
    */
    [[nodiscard]] bool isRetryable() const;

    /*!
        Corps brut de la réponse en erreur.

        Volontairement PAS une Q_PROPERTY : il ne doit pas traverser vers QML par
        inadvertance. Tout affichage passe par acp::redactSecrets().
    */
    [[nodiscard]] const QByteArray &body() const { return m_body; }
    void setBody(const QByteArray &body) { m_body = body; }

    [[nodiscard]] const std::optional<int> &retryAfterSeconds() const { return m_retryAfter; }
    [[nodiscard]] int retryAfterSecondsValue() const { return m_retryAfter.value_or(-1); }
    void setRetryAfterSeconds(int seconds) { m_retryAfter = seconds; }

    [[nodiscard]] bool isError() const { return m_kind != ApiFailure::None; }

private:
    ApiFailure::Kind m_kind = ApiFailure::None;
    int m_httpStatus = 0;
    QString m_detail;
    QString m_code;
    QString m_gateReason;
    QJsonArray m_refusals;
    QByteArray m_body;
    std::optional<int> m_retryAfter;
};

/*!
    Extrait le message lisible d'un corps d'erreur.

    Formes reconnues : `{"detail": "…"}`, `{"detail": [{"msg", "loc"}…]}`,
    `{"detail": {"code", "message"}}` (greffon acp-poste). Toute autre forme renvoie une
    chaîne vide, ce qui fait retomber l'appelant sur le libellé de famille plutôt que
    d'afficher du JSON brut. Les messages fixes de Hermes sont rendus en français.
*/
[[nodiscard]] QString extractProblemDetail(const QByteArray &body);

/*!
    Rend en français un message FIXE de la porte d'authentification de Hermes. Un message
    inconnu est rendu tel quel : le client n'invente jamais une cause.
*/
[[nodiscard]] QString traduireMessageHermes(const QString &message);

/*!
    Libellé FRANÇAIS fixe d'une erreur de transport de Qt (connexion refusée, hôte introuvable,
    délai dépassé, TLS…), suivi de son numéro. Le texte de Qt (`errorString()`) est en anglais
    faute de traducteur chargé : il n'est jamais montré au propriétaire.
*/
[[nodiscard]] QString libelleErreurReseau(QNetworkReply::NetworkError code);

/*! Même règle pour une socket : WebSockets de la passerelle et du kanban, écouteur de bouclage. */
[[nodiscard]] QString libelleErreurSocket(QAbstractSocket::SocketError code);

} // namespace acp

Q_DECLARE_METATYPE(acp::ApiError)
