// Appels à l'API du tableau de bord, par le fetchJSON du SDK (authentification du tableau de
// bord : cookie de session OIDC ; redirection vers la connexion sur 401 d'expiration).
//
// Toute erreur est enveloppée dans une ErreurApi au message français ; le détail brut de Hermes
// (souvent en anglais) reste disponible, replié, comme donnée.
import { sdk } from "./sdk";
import type { Catalogue, Meta, PageSessions, SkillHermes } from "./types";

export const ROUTE_META = "/api/plugins/acp-poste/v1/meta";
export const ROUTE_CATALOGUE = "/api/plugins/acp-poste/v1/catalogue";
export const ROUTE_SKILLS = "/api/skills";
export const ROUTE_SESSIONS = "/api/sessions?limit=5&offset=0&order=recent";

export type GenreErreur = "requete" | "reseau" | "inattendue";

export class ErreurApi extends Error {
  readonly genre: GenreErreur;
  readonly statut: number | null;
  readonly detail: string;

  constructor(genre: GenreErreur, statut: number | null, detail: string) {
    super(`${genre}${statut === null ? "" : ` ${statut}`}`);
    this.name = "ErreurApi";
    this.genre = genre;
    this.statut = statut;
    this.detail = detail.slice(0, 2000);
  }
}

/** fetchJSON de Hermes 0.21.5 lève une ApiError (web/src/lib/api-error.ts) : `status` (0 quand la
 *  requête n'a jamais atteint le serveur), `body` (corps brut), message anglais. Les versions plus
 *  anciennes levaient Error("<statut>: <corps>") (encore décrit par plugins/sdk.d.ts) : reconnu aussi. */
export function envelopper(erreur: unknown): ErreurApi {
  if (erreur instanceof ErreurApi) return erreur;
  const message = erreur instanceof Error ? erreur.message : String(erreur);
  const champs = erreur && typeof erreur === "object" ? (erreur as { status?: unknown; body?: unknown }) : {};
  if (typeof champs.status === "number" && Number.isInteger(champs.status)) {
    const corps = typeof champs.body === "string" && champs.body ? champs.body : message;
    return champs.status === 0
      ? new ErreurApi("reseau", null, corps)
      : new ErreurApi("requete", champs.status, corps);
  }
  const trouve = /^(\d{3}):\s?([\s\S]*)$/.exec(message);
  if (trouve) return new ErreurApi("requete", Number(trouve[1]), trouve[2] ?? "");
  if (erreur instanceof TypeError || /fetch|network|réseau|unreachable/i.test(message)) {
    return new ErreurApi("reseau", null, message);
  }
  return new ErreurApi("inattendue", null, message);
}

export async function lireJSON<T>(url: string): Promise<T> {
  const fetchJSON = sdk().fetchJSON;
  if (typeof fetchJSON !== "function") throw new ErreurApi("inattendue", null, "fetchJSON absent du SDK");
  try {
    return await fetchJSON<T>(url);
  } catch (erreur) {
    throw envelopper(erreur);
  }
}

// La méta est lue par l'Accueil ET par la bannière d'alertes : une seule requête à la fois,
// réutilisée 15 secondes.
let enCours: { quand: number; promesse: Promise<Meta> } | null = null;

export function lireMeta(maintenant: number = Date.now()): Promise<Meta> {
  if (enCours && maintenant - enCours.quand < 15_000) return enCours.promesse;
  const promesse = lireJSON<Meta>(ROUTE_META);
  enCours = { quand: maintenant, promesse };
  promesse.catch(() => {
    if (enCours?.promesse === promesse) enCours = null;
  });
  return promesse;
}

export function oublierMeta(): void {
  enCours = null;
}

export const lireCatalogue = (): Promise<Catalogue> => lireJSON<Catalogue>(ROUTE_CATALOGUE);
export const lireSkills = (): Promise<SkillHermes[]> => lireJSON<SkillHermes[]>(ROUTE_SKILLS);
export const lireSessions = (): Promise<PageSessions> => lireJSON<PageSessions>(ROUTE_SESSIONS);
