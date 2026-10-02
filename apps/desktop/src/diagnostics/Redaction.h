// Filtre d'expurgation appliqué à tout ce qui sort de l'application par écrit.
//
// L'audit est explicite (section 10.3) : « le jeton de téléchargement voyage en paramètre
// de requête. Un filtre de journalisation existe côté serveur ; RIEN ne protège les
// journaux, les rapports de plantage et les fichiers de diagnostic du poste client. »
// Ce fichier est cette protection, côté client.
//
// Ce qui est expurgé :
//   - les paramètres `token=`, `signature=`, `sig=`, `code=`, `state=`, `ticket=` et
//     `code_verifier=` d'une URL (lien signé, rappel de la connexion native, ticket) ;
//   - toute valeur d'en-tête X-CSRF-Token, X-ACP-Bootstrap-Token,
//     X-Worker-Registration-Token, Authorization, Cookie, Set-Cookie et
//     Sec-WebSocket-Protocol (qui porte le ticket de la passerelle) ;
//   - tout jeton `Bearer …`, tout JWT (`eyJ….….…`), tout jeton opaque d'Authelia
//     (`authelia_xx_…`), le sous-protocole `hermes-gateway-ticket.…` ;
//   - le jeton de machine (`acpm_…`) et le code d'enrôlement (`acpe_…`) du greffon acp-poste ;
//   - les cookies acp_session, hermes_session_rt et hermes_session_at ;
//   - les champs JSON password, secret, csrf_token, token, bootstrap_token, access_token,
//     refresh_token, id_token, ticket, code, code_verifier et state.
//
// Ce que le filtre NE prétend PAS faire : il ne trouve pas un secret arbitraire dans un
// texte arbitraire. C'est une défense en profondeur, pas une garantie. La vraie garantie
// est que rien de secret n'est passé à la journalisation, ce que le code respecte.

#pragma once

#include <QString>

namespace acp {

/*! Remplace toute occurrence reconnue d'un secret par « […expurgé] ». */
[[nodiscard]] QString redactSecrets(const QString &text);

/*!
    Vrai si `text` contient une forme de secret reconnue par redactSecrets() : contrôle des
    préférences (aucune valeur ne doit ressembler à un jeton) et des diagnostics.
*/
[[nodiscard]] bool ressembleAUnSecret(const QString &text);

/*! Expurge une URL : le paramètre `token` est remplacé, le reste est conservé. */
[[nodiscard]] QString redactUrl(const QString &url);

//! Texte de remplacement, identique partout pour être reconnaissable dans un journal.
inline constexpr char kRedactionPlaceholder[] = "[…expurgé]";

} // namespace acp
