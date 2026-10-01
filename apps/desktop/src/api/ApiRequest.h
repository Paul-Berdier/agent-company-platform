// Description d'un appel d'API et de sa réponse.

#pragma once

#include <QByteArray>
#include <QHash>
#include <QJsonDocument>
#include <QString>
#include <QUrlQuery>

#include <chrono>

namespace acp {

/*!
    Un appel à l'API, décrit entièrement avant d'être émis.

    La politique de réessai est SÉMANTIQUE et non configurable au coup par coup : elle se
    déduit de `method` et de `idempotencyKey` (voir ApiClient::plannedAttempts). Il n'y a
    donc volontairement pas de champ « forcer le réessai » : une mutation sans clé
    d'idempotence n'est jamais rejouée, quel que soit le désir de l'appelant.

    Aucun jeton de session n'y figure jamais : l'en-tête d'autorisation est posé par le
    transport au moment de chaque tentative, depuis la session en mémoire.
*/
struct ApiRequest
{
    //! Verbe HTTP en majuscules. « GET », « POST », « PATCH », « PUT », « DELETE ».
    QByteArray method = QByteArrayLiteral("GET");

    //! Chemin relatif à l'URL de base, avec sa barre oblique initiale : « /api/health ».
    QString path;

    //! Paramètres de requête. Aucune donnée sensible ne doit y figurer.
    QUrlQuery query;

    //! Corps JSON. Un document nul signifie « pas de corps ».
    QJsonDocument body;

    //! Clé d'idempotence. Seule `POST /v1/projets` du greffon acp-poste en accepte une ;
    //! validée localement avant l'envoi.
    QString idempotencyKey;

    //! Délai de transfert. Le défaut vise un hébergement distant à démarrage à froid, et
    //! non du bouclage local.
    std::chrono::milliseconds timeout{20000};

    //! Type accepté en réponse.
    QByteArray accept = QByteArrayLiteral("application/json");

    /*!
        Vrai pour les seules routes publiques de Hermes : `/api/health`, `/api/status`,
        `/api/auth/providers`, `/auth/native/token`, `/auth/native/refresh`, `/auth/logout`.

        Sur ces routes, aucune session n'est présentée. Le drapeau est explicite plutôt
        qu'implicite : une route protégée oubliée ici échouerait en 401, ce qui est bruyant
        et donc visible.
    */
    bool publicEndpoint = false;

    //! Vrai si la méthode est sûre au sens HTTP : elle ne modifie rien côté serveur.
    [[nodiscard]] bool isSafeMethod() const
    {
        return method == QByteArrayLiteral("GET") || method == QByteArrayLiteral("HEAD")
            || method == QByteArrayLiteral("OPTIONS");
    }
};

/*!
    Réponse d'un appel réussi.

    Les en-têtes retenus sont une liste blanche : aucun `Set-Cookie`, aucune
    `Authorization`, rien qui puisse porter un secret jusqu'à l'interface ou un journal.
*/
struct ApiResponse
{
    int httpStatus = 0;
    QJsonDocument json;
    QByteArray rawBody;
    QHash<QByteArray, QByteArray> headers;

    [[nodiscard]] QByteArray header(const QByteArray &name) const
    {
        return headers.value(name.toLower());
    }
};

} // namespace acp
