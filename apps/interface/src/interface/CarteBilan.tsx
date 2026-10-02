// Carte « Bilan quotidien » de l'Accueil (cahier P7 § 7.1, décision P7-6) : la tâche cron NATIVE de Hermes, sans
// agent, qui lance le script de l'image acp-bilan.py à 8 h (heure de Paris). Seul le propriétaire la crée : le
// bouton appelle, avec SA session, la route native POST /api/cron/jobs ; l'agent ne le peut pas (cronjob coupé).
// La carte lit GET /api/cron/jobs et dit « Actif, prochain envoi : … », « En pause » ou « Non créé ». Pause et
// suppression : page Cron de Hermes (lien). Canal non configuré : le bilan ne partira pas, et la carte le dit.
import { T } from "../chaines";
import { BlocErreur, Carte, EnChargement, Ligne, Lien } from "../commun";
import { useDonnees } from "../donnees";
import { h, type Noeud } from "../react";
import { chaine } from "../types";
import { Bouton, Etiquette, Horodatage, RetourEnvoi } from "../projets/briques";
import { useEnvoi } from "../projets/envoi";
import type { EtatNotifications } from "../projets/types";
import { creerBilanQuotidien, lireTachesCron, tachesDuBilan, type TacheCron } from "./accueil-api";

/** État d'une tâche du bilan : en pause (désactivée ou « paused »), sinon active. */
export function bilanEnPause(tache: TacheCron): boolean {
  return tache.enabled === false || tache.state === "paused";
}

export function CarteBilan(props: { notifications: EtatNotifications | null | undefined; jeton: number;
                                    apres: () => void }): Noeud {
  const lecture = useDonnees(lireTachesCron, props.jeton, []);
  const creation = useEnvoi<TacheCron>();
  const taches = lecture.valeur === null ? null : tachesDuBilan(lecture.valeur);
  const tache = taches && taches.length > 0 ? taches[0] : null;
  const creer = async () => {
    if ((await creation.envoyer(creerBilanQuotidien)) !== null) props.apres();
  };
  const notif = props.notifications ?? null;
  let contenu: Noeud;
  if (taches === null) {
    contenu = lecture.erreur ? <BlocErreur erreur={lecture.erreur} message={T.accueil.bilanIllisible} /> : <EnChargement />;
  } else if (tache === null) {
    contenu = (
      <div className="acp-sections">
        <p className="acp-etat">
          <Etiquette libelle={{ texte: T.accueil.bilanNonCree, famille: "neutre" }} />
        </p>
        <p className="acp-discret">{T.accueil.bilanExplication}</p>
        <div className="acp-actions">
          <Bouton libelle={T.accueil.creerBilan} principal surClic={() => void creer()}
                  desactive={creation.etat.etat === "envoi"} />
        </div>
        <RetourEnvoi etat={creation.etat} />
      </div>
    );
  } else {
    const pause = bilanEnPause(tache);
    contenu = (
      <div className="acp-sections">
        <dl className="acp-liste">
          <Ligne libelle={T.accueil.etat}>
            <Etiquette libelle={pause ? { texte: T.accueil.bilanEnPause, famille: "neutre" }
              : { texte: T.accueil.bilanActif, famille: "succes" }} />
          </Ligne>
          {pause ? null : (
            <Ligne libelle={T.accueil.prochainEnvoi}>
              <Horodatage valeur={chaine(tache.next_run_at)} />
            </Ligne>
          )}
          <Ligne libelle={T.accueil.dernierEnvoi}>
            {tache.last_run_at ? <Horodatage valeur={chaine(tache.last_run_at)} /> : <span>{T.accueil.jamais}</span>}
          </Ligne>
        </dl>
        {taches.length > 1 ? <p className="acp-alerte-texte">{T.accueil.bilanPlusieurs}</p> : null}
        {creation.etat.etat === "ok" ? (
          <p className="acp-succes" role="status">
            {T.accueil.bilanCree}
          </p>
        ) : null}
      </div>
    );
  }
  return (
    <Carte titre={T.accueil.bilanTitre} id="acp-accueil-bilan">
      {contenu}
      {notif?.connu === true && notif.configure !== true ? (
        <p className="acp-alerte-texte">{T.accueil.bilanSansCanal}</p>
      ) : null}
      <p>
        <Lien vers="/cron">{T.accueil.ouvrirCron}</Lien>
      </p>
    </Carte>
  );
}
