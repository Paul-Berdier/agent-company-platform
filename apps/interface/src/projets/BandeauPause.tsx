// Pause générale (décision D31) : l'arrêt d'urgence de Hermes, par POST /v1/pause.
// - Bandeau, tant qu'elle est engagée : « Hermes est en pause générale », sa raison, sa date, et
//   « Reprendre » ;
// - Commande « Pause générale », avec une confirmation explicite (jamais d'un seul appui).
import { T } from "../chaines";
import { Carte, Donnee } from "../commun";
import { h, useState, type Noeud } from "../react";
import { chaine } from "../types";
import { pauseGenerale } from "./api";
import { Bouton, Horodatage, RetourEnvoi } from "./briques";
import { useEnvoi } from "./envoi";
import type { PauseGenerale } from "./types";

export function BandeauPause(props: { pause: PauseGenerale; apres: () => void }): Noeud {
  const envoi = useEnvoi();
  const reprendre = async () => {
    if ((await envoi.envoyer(() => pauseGenerale(false))) !== null) props.apres();
  };
  return (
    <section className="acp-banniere acp-banniere--pause" aria-labelledby="acp-pause-titre" data-acp-pause="">
      <h2 className="acp-banniere__titre" id="acp-pause-titre">
        {T.projets.pauseEnCours}
      </h2>
      <p className="acp-discret">{T.projets.pauseEffet}</p>
      <dl className="acp-liste">
        <div className="acp-ligne">
          <dt>{T.projets.raison}</dt>
          <dd>
            <Donnee valeur={chaine(props.pause.reason)} />
          </dd>
        </div>
        <div className="acp-ligne">
          <dt>{T.projets.depuisLe}</dt>
          <dd>
            <Horodatage valeur={props.pause.engaged_at} />
          </dd>
        </div>
      </dl>
      <div className="acp-actions">
        <Bouton libelle={T.projets.reprendreHermes} principal surClic={reprendre} desactive={envoi.etat.etat === "envoi"} />
      </div>
      <RetourEnvoi etat={envoi.etat} />
    </section>
  );
}

export function CommandePause(props: { apres: () => void }): Noeud {
  const [confirmation, fixerConfirmation] = useState(false);
  const envoi = useEnvoi();
  const confirmer = async () => {
    if ((await envoi.envoyer(() => pauseGenerale(true))) !== null) {
      fixerConfirmation(false);
      props.apres();
    }
  };
  return (
    <Carte titre={T.projets.pauseTitre} id="acp-projets-pause">
      <p className="acp-discret">{T.projets.pauseExplication}</p>
      {confirmation ? (
        <div className="acp-confirmation" role="group" aria-labelledby="acp-pause-question">
          <p id="acp-pause-question">{T.projets.pauseQuestion}</p>
          <div className="acp-actions">
            <Bouton libelle={T.projets.pauseConfirmer} danger surClic={confirmer} desactive={envoi.etat.etat === "envoi"} />
            <Bouton
              libelle={T.projets.annuler}
              surClic={() => {
                fixerConfirmation(false);
                envoi.oublier();
              }}
            />
          </div>
        </div>
      ) : (
        <div className="acp-actions">
          <Bouton libelle={T.projets.pauseGenerale} danger surClic={() => fixerConfirmation(true)} />
        </div>
      )}
      <RetourEnvoi etat={envoi.etat} />
    </Carte>
  );
}
