// Lecture d'une route REST tenue à jour par le flux d'invalidation (cahier P7 § 5.4) ; remplace le sondage de 15 s
// de P4 (useSondage, D35), qui reste le repli.
//
// - Une lecture au montage, et à chaque changement de « cle » (après un geste du propriétaire).
// - Relecture sur signal du flux pour l'un de SES sujets, regroupée sur 300 ms (une rafale de trames, une lecture).
// - Relecture de sûreté toutes les 120 s en temps réel (un changement que l'empreinte ne couvrirait pas finit par
//   apparaître), toutes les 60 s pour une page qui suit les discussions quand le tableau de bord ne publie pas leur
//   nombre, toutes les 15 s quand le flux est indisponible (repli annoncé par la page, EtatActualisation).
// - Page cachée : aucune lecture ; lecture immédiate au retour de la page.
// - Une actualisation qui échoue GARDE la dernière valeur lue et le dit (erreur à côté de la valeur) : au téléphone,
//   un réseau instable ne vide pas la page. Aucune valeur n'est inventée : tant que rien n'a été lu, valeur est null.
import { envelopper, type ErreurApi } from "./api";
import { fluxPartage, type EtatFlux, type Sujet } from "./flux";
import { useEffect, useRef, useState } from "./react";

export const INTERVALLE_SONDAGE_MS = 15_000;
export const RELECTURE_SURETE_MS = 120_000;
export const RELECTURE_DISCUSSIONS_MS = 60_000;
export const REGROUPEMENT_MS = 300;

export interface Lecture<V> {
  valeur: V | null;
  erreur: ErreurApi | null;
  /** Date (ms) de la dernière lecture réussie. */
  luLe: number | null;
}

function visible(): boolean {
  return typeof document === "undefined" || document.visibilityState !== "hidden";
}

declare global {
  interface Window {
    /** Réglage de DIAGNOSTIC (preuve du parcours P7, correction K23) : relecture de sûreté plus LONGUE seulement ;
     *  une valeur plus courte que la normale, ou illisible, est ignorée (jamais plus de requêtes). */
    __ACP_FLUX_REGLAGES__?: { relectureSureteMs?: unknown };
  }
}

/** Relecture de sûreté en temps réel : 120 s, ou plus si le réglage de diagnostic le demande (jamais moins). */
export function relectureDeSurete(): number {
  const demande = typeof window !== "undefined" ? window.__ACP_FLUX_REGLAGES__?.relectureSureteMs : undefined;
  return typeof demande === "number" && Number.isFinite(demande) && demande >= RELECTURE_SURETE_MS
    ? demande
    : RELECTURE_SURETE_MS;
}

/** Intervalle de relecture selon l'état du flux et les sujets de la page. */
export function intervalleDeRelecture(etat: EtatFlux, sujets: readonly Sujet[]): number {
  if (etat.mode !== "temps_reel") return INTERVALLE_SONDAGE_MS;
  if (sujets.includes("discussions") && etat.discussionsSuivies === false) return RELECTURE_DISCUSSIONS_MS;
  return relectureDeSurete();
}

export function useDonnees<V>(charger: () => Promise<V>, cle: unknown, sujets: readonly Sujet[]): Lecture<V> {
  const [etat, fixer] = useState<Lecture<V>>({ valeur: null, erreur: null, luLe: null });
  // La fonction de lecture la plus récente, sans relancer l'effet à chaque rendu.
  const lecteur = useRef(charger);
  lecteur.current = charger;
  const empreinteSujets = sujets.join(",");
  useEffect(() => {
    const liste = empreinteSujets ? (empreinteSujets.split(",") as Sujet[]) : [];
    const flux = fluxPartage();
    let actif = true;
    let enCours = false;
    let aRelire = false;
    let minuterie: ReturnType<typeof setTimeout> | null = null;
    let regroupement: ReturnType<typeof setTimeout> | null = null;
    const arreter = () => {
      if (minuterie !== null) clearTimeout(minuterie);
      if (regroupement !== null) clearTimeout(regroupement);
      minuterie = null;
      regroupement = null;
    };
    const planifier = () => {
      if (minuterie !== null) clearTimeout(minuterie);
      minuterie = null;
      if (actif && !enCours && visible()) minuterie = setTimeout(lire, intervalleDeRelecture(flux.etat(), liste));
    };
    function lire(): void {
      arreter();
      if (!actif || !visible()) return;
      if (enCours) {
        aRelire = true;
        return;
      }
      enCours = true;
      lecteur.current().then(
        (valeur) => {
          if (actif) fixer({ valeur, erreur: null, luLe: Date.now() });
        },
        (erreur: unknown) => {
          if (actif) fixer((avant) => ({ ...avant, erreur: envelopper(erreur) }));
        },
      ).finally(() => {
        enCours = false;
        if (!actif) return;
        if (aRelire) {
          aRelire = false;
          lire();
        } else {
          planifier();
        }
      });
    }
    const surSignal = () => {
      if (!actif || !visible() || regroupement !== null) return;
      regroupement = setTimeout(() => {
        regroupement = null;
        lire();
      }, REGROUPEMENT_MS);
    };
    const surVisibilite = () => {
      if (visible()) lire();
      else arreter();
    };
    lire();
    const desabonner = flux.abonner(liste, surSignal);
    const arreterEcoute = flux.ecouter(() => planifier());
    document.addEventListener("visibilitychange", surVisibilite);
    return () => {
      actif = false;
      arreter();
      desabonner();
      arreterEcoute();
      document.removeEventListener("visibilitychange", surVisibilite);
    };
  }, [cle, empreinteSujets]);
  return etat;
}

/** État du flux de l'onglet (mode, discussions suivies), tenu à jour. */
export function useEtatFlux(): EtatFlux {
  const [etat, fixer] = useState<EtatFlux>(() => fluxPartage().etat());
  useEffect(() => {
    const flux = fluxPartage();
    fixer(flux.etat());
    return flux.ecouter(fixer);
  }, []);
  return etat;
}
