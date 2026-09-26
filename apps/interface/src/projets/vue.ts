// Routeur interne de la page Projets, par paramètre d'adresse (cahier P4 § 15) :
//   /projets                 liste des projets
//   /projets?projet=<id>     détail d'un projet (lien des notifications : …/projets?projet=<id>)
//   /projets?vue=questions   questions et cartes en attente d'une décision
//   /projets?vue=nouveau     formulaire « Nouveau projet »
//
// Le SDK du tableau de bord n'expose pas le routeur de Hermes : la page change de vue par son état
// et met l'adresse à jour par history.replaceState, en GARDANT l'état de l'historique du routeur et les
// autres paramètres (Hermes ajoute « ?profile=… »). Les liens restent de vrais liens (nouvel onglet).

export type Vue =
  | { genre: "liste" }
  | { genre: "nouveau" }
  | { genre: "questions" }
  | { genre: "detail"; id: string };

export const CHEMIN_PAGE = "/projets";
const IDENTIFIANT = /^[A-Za-z0-9_-]{1,80}$/;

export function vueDepuisAdresse(recherche: string): Vue {
  const parametres = new URLSearchParams(recherche);
  const projet = parametres.get("projet");
  if (projet && IDENTIFIANT.test(projet)) return { genre: "detail", id: projet };
  const vue = parametres.get("vue");
  if (vue === "questions") return { genre: "questions" };
  if (vue === "nouveau") return { genre: "nouveau" };
  return { genre: "liste" };
}

/** Paramètres de la vue, ajoutés aux autres paramètres de l'adresse (« ?profile=… » gardé). */
export function rechercheDeVue(vue: Vue, recherche = ""): string {
  const parametres = new URLSearchParams(recherche);
  parametres.delete("projet");
  parametres.delete("vue");
  if (vue.genre === "detail") parametres.set("projet", vue.id);
  else if (vue.genre !== "liste") parametres.set("vue", vue.genre);
  const texte = parametres.toString();
  return texte ? `?${texte}` : "";
}

export function remplacerAdresse(vue: Vue): void {
  try {
    const { pathname, search } = window.location;
    window.history.replaceState(window.history.state, "", `${pathname}${rechercheDeVue(vue, search)}`);
  } catch {
    // Adresse non modifiable (cadre, bac à sable) : la vue change quand même.
  }
}

export function memeVue(a: Vue, b: Vue): boolean {
  return a.genre === b.genre && (a.genre !== "detail" || (b.genre === "detail" && a.id === b.id));
}
