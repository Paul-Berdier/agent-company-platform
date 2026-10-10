// Routeur interne de la page Projets, par paramètre d'adresse (cahier P4 § 15) :
//   /projets                                       liste des projets
//   /projets?projet=<id>                           détail d'un projet (notifications « terminé », « intégration »)
//   /projets?vue=questions                         file Questions (questions, décisions, revues, cartes arrêtées,
//                                                  discussions en attente)
//   /projets?vue=questions&q=<question>            même vue, défilée jusqu'à la question (lien d'une notification)
//   /projets?vue=questions&carte=<tableau>/<carte> même vue, défilée jusqu'à la carte (lien d'une notification)
//   /projets?vue=nouveau                           formulaire « Nouveau projet »
//
// Étape P7 (cahier P7 § 6.2, correction K2) : la cible d'une notification est en PARAMÈTRES DE REQUÊTE, jamais en
// fragment : la porte d'authentification de Hermes ne garde que le chemin et la requête pour le retour après la
// connexion, et le téléphone arrive souvent sans session.
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
  | { genre: "questions"; q?: string; carte?: string }
  | { genre: "detail"; id: string };

export const CHEMIN_PAGE = "/projets";
const IDENTIFIANT = /^[A-Za-z0-9_-]{1,80}$/;
const CIBLE_CARTE = /^[A-Za-z0-9_-]{1,80}\/[A-Za-z0-9_-]{1,80}$/;

export function vueDepuisAdresse(recherche: string): Vue {
  const parametres = new URLSearchParams(recherche);
  const projet = parametres.get("projet");
  if (projet && IDENTIFIANT.test(projet)) return { genre: "detail", id: projet };
  const vue = parametres.get("vue");
  if (vue === "questions") {
    // Une cible illisible est ignorée (la vue s'ouvre sans cible), jamais devinée.
    const q = parametres.get("q");
    const carte = parametres.get("carte");
    if (q && IDENTIFIANT.test(q)) return { genre: "questions", q };
    if (carte && CIBLE_CARTE.test(carte)) return { genre: "questions", carte };
    return { genre: "questions" };
  }
  if (vue === "nouveau") return { genre: "nouveau" };
  return { genre: "liste" };
}

/** Paramètres de la vue, ajoutés aux autres paramètres de l'adresse (« ?profile=… » gardé). */
export function rechercheDeVue(vue: Vue, recherche = ""): string {
  const parametres = new URLSearchParams(recherche);
  for (const cle of ["projet", "vue", "q", "carte"]) parametres.delete(cle);
  if (vue.genre === "detail") parametres.set("projet", vue.id);
  else if (vue.genre !== "liste") parametres.set("vue", vue.genre);
  if (vue.genre === "questions" && vue.q) parametres.set("q", vue.q);
  if (vue.genre === "questions" && vue.carte) parametres.set("carte", vue.carte);
  const texte = parametres.toString().replace(/%2F/g, "/");
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

/** Même vue (pour l'onglet courant) : la cible d'une vue Questions n'en fait pas une autre vue. */
export function memeVue(a: Vue, b: Vue): boolean {
  return a.genre === b.genre && (a.genre !== "detail" || (b.genre === "detail" && a.id === b.id));
}
