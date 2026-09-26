// État d'un geste du propriétaire (lancer, mettre en pause, répondre…) : un seul envoi à la fois, le
// résultat ou le refus de l'API gardé pour l'affichage.
import { envelopper, type ErreurApi } from "../api";
import { useRef, useState } from "../react";

export type EtatEnvoi<R> =
  | { etat: "repos" }
  | { etat: "envoi" }
  | { etat: "ok"; resultat: R }
  | { etat: "erreur"; erreur: ErreurApi };

export interface Envoi<R> {
  etat: EtatEnvoi<R>;
  /** Lance le geste ; rend son résultat, ou null s'il a échoué ou si un envoi est déjà en cours. */
  envoyer: (travail: () => Promise<R>) => Promise<R | null>;
  oublier: () => void;
}

export function useEnvoi<R = unknown>(): Envoi<R> {
  const [etat, fixer] = useState<EtatEnvoi<R>>({ etat: "repos" });
  const enCours = useRef(false);
  const envoyer = async (travail: () => Promise<R>): Promise<R | null> => {
    if (enCours.current) return null;
    enCours.current = true;
    fixer({ etat: "envoi" });
    try {
      const resultat = await travail();
      fixer({ etat: "ok", resultat });
      return resultat;
    } catch (erreur) {
      fixer({ etat: "erreur", erreur: envelopper(erreur) });
      return null;
    } finally {
      enCours.current = false;
    }
  };
  return { etat, envoyer, oublier: () => fixer({ etat: "repos" }) };
}
