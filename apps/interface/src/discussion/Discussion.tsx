// Page « Discussion » (greffon acp-discussion, étape P7 ; cahier P7 § 9), pensée d'abord pour le téléphone : la liste
// des discussions, ou une discussion (reprise, envoi, texte en flux, questions « clarify », interruption).
//
// Vues par paramètre d'adresse (vue.ts) ; un changement de vue voulu par le propriétaire AJOUTE une entrée d'historique,
// et la page relit sa vue sur « popstate ».
import { T } from "../chaines";
import { EtatActualisation } from "../actualisation";
import { h, useEffect, useState, type Noeud } from "../react";
import { Fil } from "./Fil";
import { Liste } from "./Liste";
import { changerAdresse, NOUVELLE, vueDepuisAdresse, type NaviguerDiscussion, type VueDiscussion } from "./vue";

export function Discussion(): Noeud {
  const [vue, fixerVue] = useState<VueDiscussion>(() => vueDepuisAdresse(window.location.search));
  // Change à chaque ouverture voulue : une nouvelle discussion ouverte deux fois de suite repart à neuf.
  const [ouverture, fixerOuverture] = useState(0);
  const naviguer: NaviguerDiscussion = (suivante) => {
    fixerVue(suivante);
    fixerOuverture((n) => n + 1);
    changerAdresse(suivante, false);
  };
  useEffect(() => {
    const surRetour = () => {
      fixerVue(vueDepuisAdresse(window.location.search));
      fixerOuverture((n) => n + 1);
    };
    window.addEventListener("popstate", surRetour);
    return () => window.removeEventListener("popstate", surRetour);
  }, []);
  // Une nouvelle discussion reçoit sa clé au premier envoi : l'adresse la prend (un rechargement la reprend), sans
  // remonter la discussion en cours.
  const surCle = (cle: string) => changerAdresse({ genre: "fil", cle }, true);

  return (
    <div className="acp-page acp-discussion" data-acp-racine="discussion">
      <div className="acp-entete">
        <h1 className="acp-titre">{T.discussion.titre}</h1>
        <p className="acp-discret">{T.discussion.intro}</p>
      </div>
      {vue.genre === "liste" ? (
        <Liste naviguer={naviguer} />
      ) : (
        <Fil key={`${vue.cle ?? NOUVELLE}-${ouverture}`} cle={vue.cle} naviguer={naviguer} surCle={surCle} />
      )}
      <p className="acp-discret">{T.discussion.limites}</p>
      <p className="acp-discret">{T.discussion.persistance}</p>
      {vue.genre === "liste" ? <EtatActualisation portee="discussions" /> : null}
    </div>
  );
}
