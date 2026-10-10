// Routes P5 du greffon acp-poste (cahier P5 § 12.3), par le fetchJSON du SDK du tableau de bord (cookie de session
// OIDC) : jamais de fetch direct. Les routes du poste lui-même (enrôlement, attente, inventaire) ne sont jamais
// appelées d'ici : la couture d'authentification de Hermes les réserve au jeton machine.
import { lireJSON } from "../api";
import { ecrireJSON, RACINE_POSTE, ROUTE_POSTE } from "../projets/api";
import type {
  CodeEnrolement,
  Entree,
  ReponsePostePage,
  ResultatReleve,
  VueQuotas,
  VueRoutage,
} from "./types";

export { ROUTE_POSTE };
export const ROUTE_ENROLEMENT = `${ROUTE_POSTE}/enrolement`;
export const ROUTE_CONFIRMATION = `${ROUTE_POSTE}/confirmation`;
export const ROUTE_REVOCATION = `${ROUTE_POSTE}/revocation`;
export const ROUTE_RELEVE = `${ROUTE_POSTE}/releve`;
export const ROUTE_ROUTAGE = `${RACINE_POSTE}/routage`;
export const ROUTE_POLITIQUE = `${ROUTE_ROUTAGE}/politique`;
export const ROUTE_SURCHARGES = `${ROUTE_ROUTAGE}/surcharges`;
export const ROUTE_RELEVE_ACCEPTE = `${ROUTE_ROUTAGE}/releve-accepte`;
export const ROUTE_QUOTAS = `${RACINE_POSTE}/quotas`;

export const routeDesactiverSurcharge = (id: number): string => `${ROUTE_SURCHARGES}/${encodeURIComponent(String(id))}/desactiver`;

export const lirePostePage = (): Promise<ReponsePostePage> => lireJSON<ReponsePostePage>(ROUTE_POSTE);
export const lireRoutage = (): Promise<VueRoutage> => lireJSON<VueRoutage>(ROUTE_ROUTAGE);
export const lireQuotas = (): Promise<VueQuotas> => lireJSON<VueQuotas>(ROUTE_QUOTAS);

export const creerCode = (): Promise<CodeEnrolement> => ecrireJSON<CodeEnrolement>(ROUTE_ENROLEMENT, {});
export const confirmer = (machineId: string, empreinte: string): Promise<unknown> =>
  ecrireJSON(ROUTE_CONFIRMATION, { machine_id: machineId, empreinte });
export const revoquer = (machineId: string, motif: string): Promise<unknown> =>
  ecrireJSON(ROUTE_REVOCATION, { machine_id: machineId, motif });
export const releverMaintenant = (): Promise<ResultatReleve> => ecrireJSON<ResultatReleve>(ROUTE_RELEVE, {});

export const validerTable = (releves: Record<string, number | null>, classes: Record<string, Entree[]>):
  Promise<VueRoutage> => ecrireJSON<VueRoutage>(ROUTE_ROUTAGE, { releves, classes });
export const poserPolitique = (corps: {
  efforts_interdits: string[];
  paliers_admis: string[];
  motif: string;
  confirmation: string | null;
}): Promise<VueRoutage> => ecrireJSON<VueRoutage>(ROUTE_POLITIQUE, corps);
export const creerSurcharge = (corps: Entree & { classe: string; motif: string }): Promise<unknown> =>
  ecrireJSON(ROUTE_SURCHARGES, corps);
export const desactiverSurcharge = (id: number): Promise<unknown> => ecrireJSON(routeDesactiverSurcharge(id), {});
export const accepterReleve = (releveId: number): Promise<VueRoutage> =>
  ecrireJSON<VueRoutage>(ROUTE_RELEVE_ACCEPTE, { releve_id: releveId });

/** Liste des refus d'une table refusée (422 table_refusee : {"detail": {"refus": [...]}}) ; vide sinon. */
export function refusDeLaTable(detail: string): Array<{ classe?: string; rang?: number; message?: string }> {
  try {
    const corps = JSON.parse(detail) as { detail?: { refus?: unknown } };
    const refus = corps?.detail?.refus;
    return Array.isArray(refus) ? (refus as Array<{ classe?: string; rang?: number; message?: string }>) : [];
  } catch {
    return [];
  }
}
