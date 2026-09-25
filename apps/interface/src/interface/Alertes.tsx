// Bannière d'alertes (emplacement header-banner, sur toutes les pages) : les alertes de
// /v1/meta, déjà rédigées en français par le greffon acp-poste (SOUL divergent, garde absente,
// Hermes hors de la version testée, catalogue non conforme…). Rien n'est affiché sans alerte.
import { T } from "../chaines";
import { lireMeta } from "../api";
import { BlocErreur, Donnee, useChargement } from "../commun";
import { h, type Noeud } from "../react";
import { listeDeChaines, type Meta } from "../types";

export function Alertes(): Noeud {
  const meta = useChargement<Meta>(() => lireMeta());
  if (meta.etat === "chargement") return null;
  if (meta.etat === "erreur") {
    return (
      <div data-acp-racine="alertes" className="acp-banniere">
        <BlocErreur erreur={meta.erreur} message={T.accueil.metaIndisponible} />
      </div>
    );
  }
  const alertes = listeDeChaines(meta.valeur.alertes);
  if (alertes.length === 0) return null;
  return (
    <section data-acp-racine="alertes" className="acp-banniere" aria-labelledby="acp-alertes-titre">
      <h2 className="acp-banniere__titre" id="acp-alertes-titre">
        {T.alertes.titre}
      </h2>
      <ul className="acp-banniere__liste">
        {alertes.map((alerte, rang) => (
          <li key={String(rang)}>
            <Donnee valeur={alerte} />
          </li>
        ))}
      </ul>
    </section>
  );
}
