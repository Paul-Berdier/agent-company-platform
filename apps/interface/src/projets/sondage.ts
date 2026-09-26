// Sondage de la page Projets (décision D35) : une lecture au montage, puis toutes les 15 secondes
// TANT QUE LA PAGE EST VISIBLE (visibilitychange) ; une lecture aussitôt au retour de la page, et à
// chaque changement de « cle » (après un geste du propriétaire). Le flux SSE viendra en P7.
//
// Une actualisation qui échoue GARDE la dernière valeur lue et le dit (erreur à côté de la valeur) :
// au téléphone, un réseau instable ne vide pas la page. Aucune valeur n'est inventée pendant
// l'attente : tant que rien n'a été lu, valeur est null.
import { envelopper, type ErreurApi } from "../api";
import { useEffect, useRef, useState } from "../react";

export const INTERVALLE_SONDAGE_MS = 15_000;

export interface Sondage<V> {
  valeur: V | null;
  erreur: ErreurApi | null;
  /** Date (ms) de la dernière lecture réussie. */
  luLe: number | null;
}

function visible(): boolean {
  return typeof document === "undefined" || document.visibilityState !== "hidden";
}

export function useSondage<V>(charger: () => Promise<V>, cle: unknown, intervalle = INTERVALLE_SONDAGE_MS): Sondage<V> {
  const [etat, fixer] = useState<Sondage<V>>({ valeur: null, erreur: null, luLe: null });
  // La fonction de lecture la plus récente, sans relancer l'effet à chaque rendu.
  const lecteur = useRef(charger);
  lecteur.current = charger;
  useEffect(() => {
    let actif = true;
    let numero = 0;
    let minuterie: ReturnType<typeof setTimeout> | null = null;
    const arreter = () => {
      if (minuterie !== null) clearTimeout(minuterie);
      minuterie = null;
    };
    const planifier = () => {
      arreter();
      if (actif && visible()) minuterie = setTimeout(lire, intervalle);
    };
    function lire(): void {
      arreter();
      const ce = (numero += 1);
      lecteur.current().then(
        (valeur) => {
          if (actif && ce === numero) fixer({ valeur, erreur: null, luLe: Date.now() });
        },
        (erreur: unknown) => {
          if (actif && ce === numero) fixer((avant) => ({ ...avant, erreur: envelopper(erreur) }));
        },
      ).finally(() => {
        if (ce === numero) planifier();
      });
    }
    const surVisibilite = () => {
      if (visible()) lire();
      else arreter();
    };
    lire();
    document.addEventListener("visibilitychange", surVisibilite);
    return () => {
      actif = false;
      arreter();
      document.removeEventListener("visibilitychange", surVisibilite);
    };
  }, [cle, intervalle]);
  return etat;
}
