// Routeur interne de la page Poste, par paramètre d'adresse (cahier P5 § 13.2) :
//   /poste                 état du poste, enrôlement, confirmation, révocation, relevé
//   /poste?vue=routage     table de routage, interdits, surcharges
//   /poste?vue=quotas      quotas relevés par voie
// Même mécanique que la page Projets (src/projets/vue.ts) : une entrée d'historique par changement de vue voulu,
// les autres paramètres (« ?profile=… ») gardés.

export type VuePoste = "etat" | "routage" | "quotas";

export const CHEMIN_POSTE = "/poste";
export const VUES: readonly VuePoste[] = ["etat", "routage", "quotas"];

export function vuePosteDepuisAdresse(recherche: string): VuePoste {
  const vue = new URLSearchParams(recherche).get("vue");
  return vue === "routage" || vue === "quotas" ? vue : "etat";
}

export function rechercheDeVuePoste(vue: VuePoste, recherche = ""): string {
  const parametres = new URLSearchParams(recherche);
  parametres.delete("vue");
  if (vue !== "etat") parametres.set("vue", vue);
  const texte = parametres.toString();
  return texte ? `?${texte}` : "";
}

export function pousserVuePoste(vue: VuePoste): void {
  try {
    const { pathname, search } = window.location;
    const suivante = `${pathname}${rechercheDeVuePoste(vue, search)}`;
    if (suivante !== `${pathname}${search}`) window.history.pushState(window.history.state, "", suivante);
  } catch {
    // Adresse non modifiable (cadre, bac à sable) : la vue change quand même.
  }
}
