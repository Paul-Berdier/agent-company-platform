// Filtre d'expurgation appliqué à tout ce qui sort de l'application par écrit.
//
// L'audit est explicite (section 10.3) : « le jeton de téléchargement voyage en paramètre
// de requête. Un filtre de journalisation existe côté serveur ; RIEN ne protège les
// journaux, les rapports de plantage et les fichiers de diagnostic du poste client. »
// Ce fichier est cette protection, côté client.
//
// Ce qui est expurgé :
//   - le paramètre `token=` d'une URL (lien signé de téléchargement d'un livrable) ;
//   - toute valeur d'en-tête X-CSRF-Token, X-ACP-Bootstrap-Token,
//     X-Worker-Registration-Token, Authorization, Cookie et Set-Cookie ;
//   - le cookie acp_session, où qu'il apparaisse ;
//   - tout couple `"password": "…"` d'un corps JSON.
//
// Ce que le filtre NE prétend PAS faire : il ne trouve pas un secret arbitraire dans un
// texte arbitraire. C'est une défense en profondeur, pas une garantie. La vraie garantie
// est que rien de secret n'est passé à la journalisation, ce que le code respecte.

#pragma once

#include <QString>

namespace acp {

/*! Remplace toute occurrence reconnue d'un secret par « […expurgé] ». */
[[nodiscard]] QString redactSecrets(const QString &text);

/*! Expurge une URL : le paramètre `token` est remplacé, le reste est conservé. */
[[nodiscard]] QString redactUrl(const QString &url);

//! Texte de remplacement, identique partout pour être reconnaissable dans un journal.
inline constexpr char kRedactionPlaceholder[] = "[…expurgé]";

} // namespace acp
