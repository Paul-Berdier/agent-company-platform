// Clés d'idempotence : validation identique à celle du CLI, appliquée AVANT l'envoi.
//
// L'audit établit la règle serveur : une clé fait de 1 à 200 caractères ASCII visibles,
// et elle est liée au principal ET à l'empreinte canonique du payload. Rejouer la même
// clé avec un corps différent est un refus serveur, pas un doublon. Le client valide donc
// la forme localement pour échouer tôt et en français, comme le fait déjà
// apps/cli/src/acp_cli/client.py.

#pragma once

#include <QString>

namespace acp {

//! Borne serveur, relevée dans l'audit : 1 à 200 caractères.
inline constexpr int kIdempotencyKeyMaxLength = 200;

/*!
    Vrai si la clé respecte la forme acceptée par l'API : 1 à 200 caractères dont le point
    de code est compris entre 33 et 126 inclus (ASCII visible, espace exclu).
*/
[[nodiscard]] bool isValidIdempotencyKey(const QString &key);

/*!
    Fabrique une clé d'idempotence nouvelle, stable et lisible dans un journal.

    La clé est un UUID version 4 sans accolades ni tirets, préfixé par l'intention.
    Elle ne contient aucune donnée d'identité : elle sert uniquement à ce que le serveur
    reconnaisse un rejeu, et elle est destinée à être PERSISTÉE avec son payload avant
    l'envoi, afin qu'une fermeture de l'application ne produise pas un doublon.
*/
[[nodiscard]] QString makeIdempotencyKey(const QString &intent);

} // namespace acp
