// Briques de la page Projets : liens de vue, étiquettes, refus de l'API rendus tels quels, état du
// poste, horodatages. Tout texte vient de chaines.ts ; toute valeur venue de l'API passe par <Donnee>.
import type * as ReactTypes from "react";
import { T } from "../chaines";
import type { ErreurApi } from "../api";
import { BlocErreur, Donnee } from "../commun";
import { dateAbsolue, dateRelative, isoVersMillisecondes, versMillisecondes } from "../format";
import { h, type Noeud } from "../react";
import { cheminDeBase } from "../sdk";
import { messageDuRefus } from "./api";
import type { EtatEnvoi } from "./envoi";
import { libelleEtatPoste, type Libelle } from "./libelles";
import type { EtatPoste } from "./types";
import { CHEMIN_PAGE, rechercheDeVue, type Vue } from "./vue";

export type Naviguer = (vue: Vue) => void;

/** Vrai lien (ouvrable dans un nouvel onglet) ; un clic simple change de vue sans recharger la page. */
export function LienVue(props: {
  vue: Vue;
  naviguer: Naviguer;
  className?: string;
  courant?: boolean;
  children?: Noeud;
}): Noeud {
  const adresse = `${cheminDeBase()}${CHEMIN_PAGE}${rechercheDeVue(props.vue)}`;
  const surClic = (evenement: ReactTypes.MouseEvent<HTMLAnchorElement>) => {
    if (evenement.defaultPrevented || evenement.button !== 0) return;
    if (evenement.metaKey || evenement.ctrlKey || evenement.shiftKey || evenement.altKey) return;
    evenement.preventDefault();
    props.naviguer(props.vue);
  };
  return (
    <a
      className={props.className ?? "acp-lien"}
      href={adresse}
      aria-current={props.courant ? "page" : undefined}
      onClick={surClic}
    >
      {props.children}
    </a>
  );
}

/** Étiquette d'un code connu ; un code inconnu est montré tel quel (donnée), absent : « Inconnu ». */
export function Etiquette(props: { libelle: Libelle | null; brut?: unknown }): Noeud {
  if (props.libelle) {
    return (
      <span className={`acp-pastille acp-pastille--${props.libelle.famille}`}>{props.libelle.texte}</span>
    );
  }
  return <Donnee valeur={typeof props.brut === "string" ? props.brut : null} mono />;
}

/** Refus du greffon rendu TEL QUEL (message français de {"detail": {"code", "message"}}) ; toute autre
 *  erreur (réseau, mandataire) passe par le bloc d'erreur commun. */
export function BlocRefus(props: { erreur: ErreurApi }): Noeud {
  const message = messageDuRefus(props.erreur);
  if (!message) return <BlocErreur erreur={props.erreur} />;
  return (
    <div className="acp-erreur" role="alert">
      <p>
        <Donnee valeur={message} />
      </p>
      {props.erreur.statut !== null ? (
        <p className="acp-discret">
          <span>{T.erreurs.code}</span> <Donnee valeur={props.erreur.statut} mono />
        </p>
      ) : null}
    </div>
  );
}

/** Retour d'un geste : « Envoi… », le refus de l'API, ou le message de réussite donné. */
export function RetourEnvoi<R>(props: { etat: EtatEnvoi<R>; reussite?: string }): Noeud {
  const { etat } = props;
  if (etat.etat === "envoi") {
    return (
      <p className="acp-discret" role="status">
        {T.projets.envoi}
      </p>
    );
  }
  if (etat.etat === "erreur") return <BlocRefus erreur={etat.erreur} />;
  if (etat.etat === "ok" && props.reussite) {
    return (
      <p className="acp-succes" role="status">
        {props.reussite}
      </p>
    );
  }
  return null;
}

/** Date absolue (Europe/Paris) d'un horodatage de l'API (secondes ou ISO 8601), relative en infobulle
 *  lisible par les technologies d'assistance (dateTime) ; illisible : « Inconnu ». */
export function Horodatage(props: { valeur: unknown; relative?: boolean }): Noeud {
  const ms = versMillisecondes(props.valeur) ?? isoVersMillisecondes(props.valeur);
  if (ms === null) return <Donnee valeur={null} />;
  return (
    <time dateTime={new Date(ms).toISOString()}>
      <Donnee valeur={props.relative ? dateRelative(ms) : dateAbsolue(ms)} />
    </time>
  );
}

/** « Non configuré », « En ligne », « Hors ligne depuis <date> » ; jamais un état deviné. */
export function EtatDuPoste(props: { poste: EtatPoste | null | undefined }): Noeud {
  const poste = props.poste;
  const libelle = libelleEtatPoste(poste?.etat);
  return (
    <span className="acp-etat">
      <Etiquette libelle={libelle} brut={poste?.etat} />
      {poste?.etat === "hors_ligne" ? (
        <span>
          <span className="acp-discret">{T.projets.depuis}</span> <Horodatage valeur={poste.hors_ligne_depuis} />
        </span>
      ) : null}
    </span>
  );
}

/** Bouton d'action : 44 px au moins, désactivé pendant l'envoi. */
export function Bouton(props: {
  libelle: string;
  surClic?: () => void;
  desactive?: boolean;
  principal?: boolean;
  danger?: boolean;
  type?: "button" | "submit";
  decritPar?: string;
}): Noeud {
  const classes = ["acp-bouton"];
  if (props.principal) classes.push("acp-bouton--principal");
  if (props.danger) classes.push("acp-bouton--danger");
  return (
    <button
      type={props.type ?? "button"}
      className={classes.join(" ")}
      onClick={props.surClic}
      disabled={props.desactive}
      aria-describedby={props.decritPar}
    >
      {props.libelle}
    </button>
  );
}
