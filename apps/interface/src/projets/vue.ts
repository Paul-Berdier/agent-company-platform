// Routeur interne de la page Projets, par paramètre d'adresse (cahier P4 § 15) :
//   /projets                 liste des projets
//   /projets?projet=<id>     détail d'un projet (lien des notifications : …/projets?projet=<id>)
//   /projets?vue=questions   questions et cartes en attente d'une décision
//   /projets?vue=nouveau     formulaire « Nouveau projet »
//
// Le SDK du tableau de bord n'expose pas le routeur de Hermes : la page change de vue par son état.
// Un changement de vue voulu par le propriétaire (lien, onglet, lancement) AJOUTE une entrée d'historique
// (history.pushState) : au téléphone, le geste « retour » ramène à la vue précédente de la page au lieu de
// quitter la page Projets (relecture de P4) ; la page relit sa vue sur « popstate ». L'état de l'historique
// du routeur de Hermes et les autres paramètres (« ?profile=… ») sont gardés. Les liens restent de vrais
// liens (nouvel onglet).

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

/** Nouvelle entrée d'historique pour la vue (geste du propriétaire) ; rien si l'adresse ne change pas. */
export function pousserAdresse(vue: Vue): void {
  try {
    const { pathname, search } = window.location;
    const suivante = `${pathname}${rechercheDeVue(vue, search)}`;
    if (suivante !== `${pathname}${search}`) window.history.pushState(window.history.state, "", suivante);
  } catch {
    // Adresse non modifiable (cadre, bac à sable) : la vue change quand même.
  }
}

export function memeVue(a: Vue, b: Vue): boolean {
  return a.genre === b.genre && (a.genre !== "detail" || (b.genre === "detail" && a.id === b.id));
}
