// Logotype texte « ACP » (décision D14 : pas encore de logo dessiné), dans l'emplacement
// header-left du tableau de bord, devant la marque de Hermes. Lien vers l'Accueil.
import { T } from "../chaines";
import { h, type Noeud } from "../react";
import { cheminDeBase } from "../sdk";

export function Marque(): Noeud {
  return (
    <span data-acp-racine="marque" className="acp-marque-racine">
      <a className="acp-marque" href={`${cheminDeBase()}/`} aria-label={T.marque.lienAccueil}>
        <span aria-hidden="true">{T.marque.sigle}</span>
      </a>
    </span>
  );
}
