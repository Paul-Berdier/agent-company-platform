// Ce que la page dit de son actualisation, d'après l'état RÉEL du flux de l'onglet (jamais « temps réel » sans trame
// « etat » reçue) : temps réel, connexion en cours, repli sur le sondage de 15 s, ou SDK sans flux.
//
// Relecture finale de P7 (constat produit-12) : là où toute la page ne suit pas le flux, la phrase dit sa portée
// exacte (``portee``) : l'Accueil (bilan relu toutes les 2 min ; sessions récentes et système lus à l'ouverture), la
// liste des discussions (relue toutes les 2 min, seules les discussions en attente suivent le flux).
import { T } from "./chaines";
import { useEtatFlux } from "./donnees";
import { h, type Noeud } from "./react";

export type PorteeActualisation = "page" | "accueil" | "discussions";

export function EtatActualisation(props: { portee?: PorteeActualisation } = {}): Noeud {
  const etat = useEtatFlux();
  const portee = props.portee ?? "page";
  const actif = portee === "accueil" ? T.tempsReel.actifAccueil
    : portee === "discussions" ? T.tempsReel.actifDiscussions : T.tempsReel.actif;
  const texte =
    etat.mode === "temps_reel"
      ? actif
      : etat.mode === "sondage"
        ? T.tempsReel.repli
        : etat.mode === "indisponible"
          ? T.tempsReel.sansFlux
          : T.tempsReel.connexion;
  return (
    <p className={etat.mode === "sondage" ? "acp-alerte-texte" : "acp-discret"} role="status"
       data-acp-temps-reel={etat.mode}>
      <span>{texte}</span>
      {portee === "accueil" ? <span> {T.tempsReel.noteAccueil}</span> : null}
    </p>
  );
}
