// Jetons d'une session Hermes obtenus par la connexion native.
//
// Forme rendue par `/auth/native/token` et `/auth/native/refresh` (routes.py,
// `_bearer_payload`) : `{access_token, refresh_token, token_type: "Bearer", expires_at,
// provider, user_id}`. Avec le fournisseur `self-hosted`, le jeton d'accès est l'ID token
// RS256 d'Authelia (1 h) ; la station ne le décode pas : Hermes le vérifie à chaque requête.
//
// Ces valeurs ne vivent qu'en mémoire (le jeton de rafraîchissement peut aller au coffre
// Windows, jamais ailleurs) ; elles ne sont jamais journalisées ni publiées vers QML.

#pragma once

#include <QByteArray>
#include <QDateTime>
#include <QJsonObject>
#include <QString>

namespace acp {

struct JetonsHermes
{
    QByteArray acces;
    QByteArray rafraichissement;
    QDateTime expireLe; //!< UTC, depuis `expires_at` (secondes Unix).
    QString fournisseur;
    QString utilisateur;

    [[nodiscard]] bool estVide() const { return acces.isEmpty(); }

    /*! Écrase les deux jetons et vide les autres champs. */
    void effacer();

    /*!
        Lit une réponse de jetons. Rend une chaîne vide si elle est acceptée, sinon la
        raison française du refus. Contrôles : `token_type` = Bearer, `provider` égal au
        fournisseur attendu, `access_token` non vide, `expires_at` dans le futur,
        `user_id` présent. Un `refresh_token` vide est admis : la session ne vaut alors que
        pour cette ouverture de la station.

        `dateServeur` : l'en-tête `Date` de la réponse, s'il est lisible. L'échéance est alors
        jugée contre l'heure de HERMES, pas contre celle du poste (une horloge du poste en
        avance ne fait plus refuser un jeton valable), et `expireLe` est ramenée à l'horloge
        du poste avec la même durée restante, pour que le renouvellement soit planifié au bon
        moment. Sans en-tête lisible, l'horloge du poste fait foi.
    */
    [[nodiscard]] static QString lire(const QJsonObject &reponse, const QString &fournisseurAttendu,
                                      const QDateTime &maintenant, JetonsHermes &sortie,
                                      const QDateTime &dateServeur = {});

    /*! Date d'un en-tête HTTP `Date` (IMF-fixdate, RFC 9110 § 5.6.7), en UTC ; invalide sinon. */
    [[nodiscard]] static QDateTime dateHttp(const QByteArray &valeur);
};

} // namespace acp
