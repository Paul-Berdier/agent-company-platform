// Briques communes aux deux greffons. Tout texte vient de chaines.ts ; toute valeur venue de
// l'API passe par <Donnee>, qui la marque data-acp-donnee (le test navigateur s'en sert pour
// distinguer une donnée d'un libellé).
import { T } from "./chaines";
import { ErreurApi, envelopper } from "./api";
import { cheminDeBase } from "./sdk";
import { h, useEffect, useState, type Noeud } from "./react";

export type CleEtat = keyof typeof T.etats;

type Famille = "succes" | "degrade" | "echec" | "neutre";

const FAMILLES: Record<CleEtat, Famille> = {
  conforme: "succes",
  connecte: "succes",
  active: "succes",
  activee: "succes",
  aJour: "succes",
  deposee: "succes",
  livree: "succes",
  presente: "succes",
  nonConforme: "degrade",
  divergente: "degrade",
  ambigue: "degrade",
  absente: "echec",
  nonOrdinaire: "echec",
  inconnu: "neutre",
  nonConfigure: "neutre",
  horsLigne: "neutre",
  reportee: "neutre",
  desactivee: "neutre",
};

/** Une valeur venue de l'API, ou « Inconnu » (libellé) si elle manque. */
export function Donnee(props: { valeur: string | number | null | undefined; mono?: boolean }): Noeud {
  const { valeur, mono } = props;
  if (valeur === null || valeur === undefined || valeur === "") {
    return <span className="acp-inconnu">{T.commun.inconnu}</span>;
  }
  return (
    <span data-acp-donnee="" className={mono ? "acp-donnee acp-mono" : "acp-donnee"}>
      {String(valeur)}
    </span>
  );
}

/** Pastille d'état : libellé du catalogue, famille de couleur ET de forme (trait pointillé pour
 *  les états inconnus, non configurés ou hors ligne : lisible sans la couleur). */
export function Pastille(props: { etat: CleEtat }): Noeud {
  return (
    <span className={`acp-pastille acp-pastille--${FAMILLES[props.etat]}`}>{T.etats[props.etat]}</span>
  );
}

export function Carte(props: { titre: string; id: string; children?: Noeud }): Noeud {
  return (
    <section className="acp-carte" aria-labelledby={props.id}>
      <h2 className="acp-carte__titre" id={props.id}>
        {props.titre}
      </h2>
      {props.children}
    </section>
  );
}

/** Ligne « libellé — valeur » d'une liste de définitions. */
export function Ligne(props: { libelle: string; children?: Noeud }): Noeud {
  return (
    <div className="acp-ligne">
      <dt>{props.libelle}</dt>
      <dd>{props.children}</dd>
    </div>
  );
}

/** Lien interne du tableau de bord (préfixe de base compris) ; navigation complète. */
export function Lien(props: { vers: string; children?: Noeud; ariaLabel?: string }): Noeud {
  return (
    <a className="acp-lien" href={`${cheminDeBase()}${props.vers}`} aria-label={props.ariaLabel}>
      {props.children}
    </a>
  );
}

export function BlocErreur(props: { erreur: unknown; message?: string }): Noeud {
  const erreur = props.erreur instanceof ErreurApi ? props.erreur : envelopper(props.erreur);
  const message =
    props.message ??
    (erreur.genre === "reseau" ? T.erreurs.reseau : erreur.genre === "requete" ? T.erreurs.requete : T.erreurs.inattendue);
  return (
    <div className="acp-erreur" role="alert">
      <p>{message}</p>
      {erreur.statut !== null ? (
        <p className="acp-discret">
          <span>{T.erreurs.code}</span> <Donnee valeur={erreur.statut} mono />
        </p>
      ) : null}
      {erreur.detail ? (
        <details className="acp-details">
          <summary>{T.commun.detailTechnique}</summary>
          <Donnee valeur={erreur.detail} mono />
        </details>
      ) : null}
    </div>
  );
}

export type Chargement<V> =
  | { etat: "chargement" }
  | { etat: "ok"; valeur: V }
  | { etat: "erreur"; erreur: ErreurApi };

/** Charge une donnée une fois au montage ; aucune valeur par défaut inventée pendant l'attente. */
export function useChargement<V>(charger: () => Promise<V>): Chargement<V> {
  const [etat, fixer] = useState<Chargement<V>>({ etat: "chargement" });
  useEffect(() => {
    let actif = true;
    charger().then(
      (valeur) => {
        if (actif) fixer({ etat: "ok", valeur });
      },
      (erreur: unknown) => {
        if (actif) fixer({ etat: "erreur", erreur: envelopper(erreur) });
      },
    );
    return () => {
      actif = false;
    };
  }, []);
  return etat;
}

export function EnChargement(): Noeud {
  return (
    <p className="acp-discret" aria-live="polite" aria-busy="true">
      {T.commun.chargement}
    </p>
  );
}
