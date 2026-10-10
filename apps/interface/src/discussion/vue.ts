// Routeur interne de la page Discussion, par paramètre d'adresse (comme la page Projets) :
//   /discussion                      liste des discussions récentes et « Nouvelle discussion »
//   /discussion?session=<clé>        une discussion, reprise par sa clé STOCKÉE (lien « Ouvrir la discussion » de la
//                                    file Questions, ou d'une ligne de la liste)
//   /discussion?session=nouvelle     nouvelle discussion (créée au premier envoi ; l'adresse prend alors sa clé)
// Les autres paramètres de l'adresse (« ?profile=… ») sont gardés.
import { cheminDeBase } from "../sdk";

export const CHEMIN_DISCUSSION = "/discussion";
export const NOUVELLE = "nouvelle";
const CLE = /^[A-Za-z0-9_.:-]{1,200}$/;

export type VueDiscussion = { genre: "liste" } | { genre: "fil"; cle: string | null };

export function vueDepuisAdresse(recherche: string): VueDiscussion {
  const session = new URLSearchParams(recherche).get("session");
  if (session === NOUVELLE) return { genre: "fil", cle: null };
  // Une clé illisible ouvre la liste : jamais devinée.
  if (session && CLE.test(session)) return { genre: "fil", cle: session };
  return { genre: "liste" };
}

export function rechercheDeVue(vue: VueDiscussion, recherche = ""): string {
  const parametres = new URLSearchParams(recherche);
  parametres.delete("session");
  if (vue.genre === "fil") parametres.set("session", vue.cle ?? NOUVELLE);
  const texte = parametres.toString();
  return texte ? `?${texte}` : "";
}

export function adresseDeVue(vue: VueDiscussion): string {
  return `${cheminDeBase()}${CHEMIN_DISCUSSION}${rechercheDeVue(vue)}`;
}

export function changerAdresse(vue: VueDiscussion, remplacer: boolean): void {
  try {
    const { pathname, search } = window.location;
    const suivante = `${pathname}${rechercheDeVue(vue, search)}`;
    if (suivante === `${pathname}${search}`) return;
    if (remplacer) window.history.replaceState(window.history.state, "", suivante);
    else window.history.pushState(window.history.state, "", suivante);
  } catch {
    // Adresse non modifiable (cadre, bac à sable) : la vue change quand même.
  }
}

export type NaviguerDiscussion = (vue: VueDiscussion) => void;
