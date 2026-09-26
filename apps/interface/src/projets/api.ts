// Routes P4 du greffon acp-poste (docs/refonte/projets.md § 4), par le fetchJSON du SDK du tableau de
// bord (cookie de session OIDC) : jamais de fetch direct.
//
// Écriture : POST en JSON (le greffon refuse tout autre Content-Type, 415, et un Origin étranger, 403 :
// le navigateur pose l'Origin du tableau de bord). Un refus du greffon arrive sous la forme
// {"detail": {"code", "message"}} : le message français est rendu TEL QUEL (messageDuRefus).
import { envelopper, ErreurApi, lireJSON } from "../api";
import { sdk } from "../sdk";
import type {
  CarteLue,
  DemandeLancement,
  ListeProjets,
  ListeQuestions,
  ReponseDetail,
  ReponseLancement,
  ReponsePoste,
  ResultatConclusion,
  ResultatReponse,
  ResultatTriage,
} from "./types";

export const RACINE_POSTE = "/api/plugins/acp-poste/v1";
export const ROUTE_PROJETS = `${RACINE_POSTE}/projets`;
export const ROUTE_QUESTIONS = `${RACINE_POSTE}/questions`;
export const ROUTE_POSTE = `${RACINE_POSTE}/poste`;
export const ROUTE_PAUSE = `${RACINE_POSTE}/pause`;
export const ROUTE_NOTIFICATION_TEST = `${RACINE_POSTE}/notifications/test`;

const segment = (valeur: string): string => encodeURIComponent(valeur);

export const routeProjet = (id: string): string => `${ROUTE_PROJETS}/${segment(id)}`;
export const routePauseProjet = (id: string): string => `${routeProjet(id)}/pause`;
export const routeRepriseProjet = (id: string): string => `${routeProjet(id)}/reprise`;
export const routeReponse = (question: string): string => `${ROUTE_QUESTIONS}/${segment(question)}/reponse`;
export const routeReprendreTriage = (tableau: string, carte: string): string =>
  `${RACINE_POSTE}/triage/${segment(tableau)}/${segment(carte)}/reprendre`;
export const routeConclureTriage = (tableau: string, carte: string): string =>
  `${RACINE_POSTE}/triage/${segment(tableau)}/${segment(carte)}/conclure`;
export const routeCarteDuProjet = (id: string, carte: string): string => `${routeProjet(id)}/cartes/${segment(carte)}`;

/** POST JSON par fetchJSON ; toute erreur devient une ErreurApi (message français à l'affichage). */
export async function ecrireJSON<T>(url: string, corps: unknown, entetes: Record<string, string> = {}): Promise<T> {
  const fetchJSON = sdk().fetchJSON;
  if (typeof fetchJSON !== "function") throw new ErreurApi("inattendue", null, "fetchJSON absent du SDK");
  try {
    return await fetchJSON<T>(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...entetes },
      body: JSON.stringify(corps ?? {}),
    });
  } catch (erreur) {
    throw envelopper(erreur);
  }
}

/** Message français d'un refus du greffon ({"detail": {"code", "message"}} ou {"detail": "…"}),
 *  ou null si le corps n'en porte pas (une erreur de réseau, une page d'erreur d'un mandataire…). */
export function messageDuRefus(erreur: ErreurApi): string | null {
  const texte = erreur.detail.trim();
  if (!texte.startsWith("{")) return null;
  try {
    const corps = JSON.parse(texte) as { detail?: unknown };
    const detail = corps?.detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return message.trim();
    }
  } catch {
    return null;
  }
  return null;
}

/** Code stable d'un refus du greffon (« aucun_inventaire », « projets_actifs »…), ou null. */
export function codeDuRefus(erreur: ErreurApi): string | null {
  try {
    const detail = (JSON.parse(erreur.detail) as { detail?: unknown })?.detail;
    const code = detail && typeof detail === "object" ? (detail as { code?: unknown }).code : null;
    return typeof code === "string" ? code : null;
  } catch {
    return null;
  }
}

/** Clé d'idempotence d'un envoi du formulaire (un double appui ne lance qu'un projet). */
export function nouvelleCle(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  const octets = new Uint8Array(16);
  if (c && typeof c.getRandomValues === "function") c.getRandomValues(octets);
  else for (let i = 0; i < octets.length; i += 1) octets[i] = Math.floor(Math.random() * 256);
  return [...octets].map((o) => o.toString(16).padStart(2, "0")).join("");
}

export const lireProjets = (): Promise<ListeProjets> => lireJSON<ListeProjets>(ROUTE_PROJETS);
export const lireProjet = (id: string): Promise<ReponseDetail> => lireJSON<ReponseDetail>(routeProjet(id));
export const lireQuestions = (): Promise<ListeQuestions> => lireJSON<ListeQuestions>(ROUTE_QUESTIONS);
export const lirePoste = (): Promise<ReponsePoste> => lireJSON<ReponsePoste>(ROUTE_POSTE);
export const lireCarte = (id: string, carte: string): Promise<{ carte?: CarteLue }> =>
  lireJSON<{ carte?: CarteLue }>(routeCarteDuProjet(id, carte));

export const lancerProjet = (demande: DemandeLancement, cle: string): Promise<ReponseLancement> =>
  ecrireJSON<ReponseLancement>(ROUTE_PROJETS, demande, { "Idempotency-Key": cle });
export const pauseProjet = (id: string): Promise<unknown> => ecrireJSON(routePauseProjet(id), {});
export const repriseProjet = (id: string): Promise<unknown> => ecrireJSON(routeRepriseProjet(id), {});
export const repondreQuestion = (question: string, reponse: string): Promise<ResultatReponse> =>
  ecrireJSON<ResultatReponse>(routeReponse(question), { reponse });
export const reprendreTriage = (tableau: string, carte: string, consigne: string | null): Promise<ResultatTriage> =>
  ecrireJSON<ResultatTriage>(routeReprendreTriage(tableau, carte), consigne ? { consigne } : {});
export const conclureTriage = (tableau: string, carte: string): Promise<ResultatConclusion> =>
  ecrireJSON<ResultatConclusion>(routeConclureTriage(tableau, carte), {});
export const pauseGenerale = (generale: boolean): Promise<{ pause_generale?: unknown }> =>
  ecrireJSON(ROUTE_PAUSE, { generale });
export const notificationDeTest = (): Promise<{ message?: unknown }> => ecrireJSON(ROUTE_NOTIFICATION_TEST, {});
