// Ce que la page dit de son actualisation, d'après l'état RÉEL du flux de l'onglet (jamais « temps réel » sans trame
// « etat » reçue) : temps réel, connexion en cours, repli sur le sondage de 15 s, ou SDK sans flux.
import { T } from "./chaines";
import { useEtatFlux } from "./donnees";
import { h, type Noeud } from "./react";

export function EtatActualisation(): Noeud {
  const etat = useEtatFlux();
  const texte =
    etat.mode === "temps_reel"
      ? T.tempsReel.actif
      : etat.mode === "sondage"
        ? T.tempsReel.repli
        : etat.mode === "indisponible"
          ? T.tempsReel.sansFlux
          : T.tempsReel.connexion;
  return (
    <p className={etat.mode === "sondage" ? "acp-alerte-texte" : "acp-discret"} role="status"
       data-acp-temps-reel={etat.mode}>
      {texte}
    </p>
  );
}
