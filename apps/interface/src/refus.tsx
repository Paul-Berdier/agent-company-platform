// Composant de refus quand le SDK du tableau de bord n'est pas celui que ces greffons savent
// employer : l'interface ACP se désactive et le dit, au lieu de fonctionner à moitié.
import { T } from "./chaines";
import { Donnee } from "./commun";
import { h, type Noeud } from "./react";
import { SDK_ATTENDU } from "./sdk";

export function creerRefus(trouve: string): () => Noeud {
  return function RefusSdk(): Noeud {
    return (
      <div data-acp-racine="refus" className="acp-banniere acp-banniere--refus" role="alert">
        <p>{T.refus.sdk}</p>
        <p className="acp-discret">
          <span>{T.refus.attendu}</span> <Donnee valeur={SDK_ATTENDU} mono /> <span>{T.commun.separateur}</span>{" "}
          <span>{T.refus.trouve}</span> <Donnee valeur={trouve} mono />
        </p>
      </div>
    );
  };
}
