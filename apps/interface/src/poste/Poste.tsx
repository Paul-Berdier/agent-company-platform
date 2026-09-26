// Page « Poste » (greffon acp-poste-vues, étape P5 ; cahier P5 § 13), pensée d'abord pour le téléphone : trois vues
// — l'état du poste (enrôlement, confirmation, révocation, relevé), le routage des exécutants, les quotas relevés.
//
// Aucune route propre : tout passe par les routes d'acp-poste derrière la session du tableau de bord. Chaque bouton
// appelle une route réelle et testée ; aucune donnée inventée (« Inconnu », « Non configuré ») ; sondage de 15 s
// tant que la page est visible ; le code d'enrôlement n'est jamais stocké (état du composant seulement).
import type * as ReactTypes from "react";
import { T } from "../chaines";
import { h, useEffect, useRef, useState, type Noeud } from "../react";
import { cheminDeBase } from "../sdk";
import { EtatPoste } from "./EtatPoste";
import { Quotas } from "./Quotas";
import { Routage } from "./Routage";
import { CHEMIN_POSTE, pousserVuePoste, rechercheDeVuePoste, VUES, vuePosteDepuisAdresse, type VuePoste } from "./vue";

const LIBELLES: Record<VuePoste, string> = { etat: T.poste.vueEtat, routage: T.poste.vueRoutage,
                                             quotas: T.poste.vueQuotas };

function Onglet(props: { vue: VuePoste; courante: VuePoste; naviguer: (v: VuePoste) => void }): Noeud {
  const adresse = `${cheminDeBase()}${CHEMIN_POSTE}${rechercheDeVuePoste(props.vue)}`;
  const surClic = (evenement: ReactTypes.MouseEvent<HTMLAnchorElement>) => {
    if (evenement.defaultPrevented || evenement.button !== 0) return;
    if (evenement.metaKey || evenement.ctrlKey || evenement.shiftKey || evenement.altKey) return;
    evenement.preventDefault();
    props.naviguer(props.vue);
  };
  return (
    <a className="acp-onglet" href={adresse} aria-current={props.vue === props.courante ? "page" : undefined}
       onClick={surClic}>
      <span>{LIBELLES[props.vue]}</span>
    </a>
  );
}

export function Poste(): Noeud {
  const [vue, fixerVue] = useState<VuePoste>(() => vuePosteDepuisAdresse(window.location.search));
  const [jeton, fixerJeton] = useState(0);
  const racine = useRef<HTMLDivElement | null>(null);
  const rafraichir = () => fixerJeton((j) => j + 1);
  const naviguer = (suivante: VuePoste) => {
    fixerVue(suivante);
    pousserVuePoste(suivante);
    rafraichir();
    try {
      racine.current?.scrollIntoView?.({ block: "start" });
    } catch {
      // Défilement impossible : sans effet sur la vue.
    }
  };
  useEffect(() => {
    const surRetour = () => {
      fixerVue(vuePosteDepuisAdresse(window.location.search));
      fixerJeton((j) => j + 1);
    };
    window.addEventListener("popstate", surRetour);
    return () => window.removeEventListener("popstate", surRetour);
  }, []);
  return (
    <div className="acp-page" data-acp-racine="poste" ref={racine}>
      <div className="acp-entete">
        <h1 className="acp-titre">{T.poste.titre}</h1>
        <p className="acp-discret">{T.poste.intro}</p>
      </div>
      <nav className="acp-onglets" aria-label={T.poste.navigation}>
        {VUES.map((v) => (
          <Onglet key={v} vue={v} courante={vue} naviguer={naviguer} />
        ))}
      </nav>
      {vue === "etat" ? <EtatPoste jeton={jeton} apres={rafraichir} /> : null}
      {vue === "routage" ? <Routage jeton={jeton} apres={rafraichir} /> : null}
      {vue === "quotas" ? <Quotas jeton={jeton} apres={rafraichir} /> : null}
      <p className="acp-discret">{T.poste.actualisation}</p>
    </div>
  );
}
