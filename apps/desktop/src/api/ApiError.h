// Erreurs d'API typées, avec un message français destiné à l'interface.
//
// Règle de doctrine : une erreur affiche la cause telle que le serveur l'a donnée,
// l'action réellement possible, et de quoi la retrouver. Elle ne se déguise jamais en
// état vide, et le client n'invente jamais un texte à la place du serveur : quand le
// serveur fournit un `detail`, c'est lui qui est montré ; le libellé du client sert
// seulement de titre de famille.

#pragma once

#include "app/QmlEnums.h"

#include <QByteArray>
#include <QMetaType>
#include <QString>

#include <optional>

namespace acp {

/*!
    Description complète d'un échec d'appel.

    Le type est un Q_GADGET : il traverse la frontière QML comme une valeur, sans
    propriétaire ni cycle de vie à gérer. Aucun champ ne contient de secret : le corps
    brut n'est conservé que tronqué, et la construction depuis une réponse HTTP ne recopie
    ni en-tête d'autorisation, ni cookie, ni paramètre de requête signé.
*/
class ApiError
{
    Q_GADGET
    Q_PROPERTY(int kind READ kindValue CONSTANT)
    Q_PROPERTY(int httpStatus READ httpStatus CONSTANT)
    Q_PROPERTY(QString title READ title CONSTANT)
    Q_PROPERTY(QString detail READ detail CONSTANT)
    Q_PROPERTY(QString message READ message CONSTANT)
    Q_PROPERTY(bool retryable READ isRetryable CONSTANT)
    Q_PROPERTY(int retryAfterSeconds READ retryAfterSecondsValue CONSTANT)

public:
    ApiError() = default;

    ApiError(ApiFailure::Kind kind, QString detail, int httpStatus = 0);

    /*! Construit l'erreur correspondant à un code HTTP et au `detail` renvoyé par l'API. */
    static ApiError fromHttpStatus(int httpStatus, const QString &serverDetail);

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
        Vrai si la famille d'erreur autorise un nouvel essai du MÊME appel.

        Ce n'est PAS une autorisation de rejouer une mutation : la décision finale
        appartient à ApiClient, qui n'accepte le réessai d'une méthode non sûre que si
        l'appel porte une clé d'idempotence. Voir ApiClient::shouldRetry().
    */
    [[nodiscard]] bool isRetryable() const;

    /*!
        Corps brut de la réponse en erreur.

        Volontairement PAS une Q_PROPERTY : il ne doit pas traverser vers QML par
        inadvertance. Il n'existe que pour les réponses structurées que la station doit
        lire malgré leur code d'erreur — le cas réel est `/ready` en 503, qui détaille ses
        contrôles. Tout affichage passe par acp::redactSecrets().
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
    QByteArray m_body;
    std::optional<int> m_retryAfter;
};

/*!
    Extrait le champ `detail` d'un corps d'erreur FastAPI.

    L'API renvoie `{"detail": "..."}` pour une HTTPException et
    `{"detail": [{"msg": "...", "loc": [...]}, ...]}` pour une erreur de validation 422.
    Les deux formes sont reconnues ; toute autre forme renvoie une chaîne vide, ce qui
    fait retomber l'appelant sur le libellé de famille plutôt que d'afficher du JSON brut.
*/
[[nodiscard]] QString extractProblemDetail(const QByteArray &body);

} // namespace acp

Q_DECLARE_METATYPE(acp::ApiError)
