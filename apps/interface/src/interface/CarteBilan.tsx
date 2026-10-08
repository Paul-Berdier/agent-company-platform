// Carte « Bilan quotidien » de l'Accueil (cahier P7 § 7.1, décision P7-6) : la tâche cron NATIVE de Hermes, sans
// agent, qui lance le script de l'image acp-bilan.py à 8 h (heure de Paris). Seul le propriétaire la crée : le
// bouton appelle, avec SA session, la route native POST /api/cron/jobs ; l'agent ne le peut pas (cronjob coupé).
// La carte lit GET /api/cron/jobs et dit « Actif », « En pause », « En erreur » ou « Non créé », la prochaine et la
// dernière EXÉCUTION (relecture finale de P7 : Hermes date last_run_at même en échec ; le script ne fait qu'enfiler la
// notification) et l'issue de la dernière, d'après last_status (≠ « ok » : alerte, last_error replié). Pause et
// suppression : page Cron de Hermes (lien). Canal non configuré : le bilan ne partira pas, et la carte le dit. Un refus
// de la route native (anglais) est dit en français, le détail replié.
import { T } from "../chaines";
import { BlocErreur, Carte, Donnee, EnChargement, Ligne, Lien } from "../commun";
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

/** Tâche que Hermes a mise en erreur (prochaine exécution incalculable) : elle ne s'exécute plus d'elle-même. */
export function bilanEnErreur(tache: TacheCron): boolean {
  return !bilanEnPause(tache) && tache.state === "error";
}

/** Dernière exécution en échec : exécutée (last_run_at) et issue autre que « ok » (error, delivery_failed…). */
export function derniereEnEchec(tache: TacheCron): boolean {
  return Boolean(tache.last_run_at) && tache.last_status !== "ok";
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
        {creation.etat.etat === "erreur" ? (
          <BlocErreur erreur={creation.etat.erreur} message={T.accueil.bilanCreationRefusee} />
        ) : (
          <RetourEnvoi etat={creation.etat} />
        )}
      </div>
    );
  } else {
    const pause = bilanEnPause(tache);
    const erreur = bilanEnErreur(tache);
    const echec = derniereEnEchec(tache);
    const detail = chaine(tache.last_error);
    contenu = (
      <div className="acp-sections">
        <dl className="acp-liste">
          <Ligne libelle={T.accueil.etat}>
            <Etiquette libelle={pause ? { texte: T.accueil.bilanEnPause, famille: "neutre" }
              : erreur ? { texte: T.accueil.bilanEnErreur, famille: "echec" }
                : { texte: T.accueil.bilanActif, famille: "succes" }} />
          </Ligne>
          {pause || erreur ? null : (
            <Ligne libelle={T.accueil.prochainEnvoi}>
              <Horodatage valeur={chaine(tache.next_run_at)} />
            </Ligne>
          )}
          <Ligne libelle={T.accueil.dernierEnvoi}>
            {tache.last_run_at ? <Horodatage valeur={chaine(tache.last_run_at)} /> : <span>{T.accueil.jamais}</span>}
          </Ligne>
        </dl>
        {erreur ? <p className="acp-alerte-texte" role="status">{T.accueil.bilanTacheEnErreur}</p>
          : echec ? <p className="acp-alerte-texte" role="status">{T.accueil.bilanDerniereEchec}</p> : null}
        {(erreur || echec) && (detail || tache.last_status) ? (
          <details className="acp-details">
            <summary>{T.commun.detailTechnique}</summary>
            <dl className="acp-liste">
              <Ligne libelle={T.accueil.bilanStatut}>
                <Donnee valeur={chaine(tache.last_status)} mono />
              </Ligne>
              <Ligne libelle={T.accueil.bilanErreurHermes}>
                <Donnee valeur={detail} mono />
              </Ligne>
            </dl>
          </details>
        ) : null}
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
