// Lectures de l'Accueil (étape P7, cahier P7 § 7, § 8) : la route agrégée du greffon (GET /v1/accueil, forme
// partagée hermes/tests/outils/fixtures_accueil/accueil.json) et les tâches cron NATIVES de Hermes (GET et
// POST /api/cron/jobs), avec la session du tableau de bord (fetchJSON du SDK) : rien d'autre.
import { lireJSON } from "../api";
import { ecrireJSON } from "../projets/api";
import type { EtatNotifications, PauseGenerale } from "../projets/types";

export const ROUTE_ACCUEIL = "/api/plugins/acp-poste/v1/accueil";
export const ROUTE_CRON = "/api/cron/jobs";
export const SCRIPT_BILAN = "acp-bilan.py";
/** Tâche du bilan quotidien (cahier P7 § 7.1) : sans agent, 8 h (heure de Paris : fuseau épinglé), livrée en local. */
export const TACHE_BILAN = {
  name: "Bilan ACP",
  schedule: "0 8 * * *",
  prompt: "",
  no_agent: true,
  script: SCRIPT_BILAN,
  deliver: "local",
} as const;

export interface PremiereDemande {
  genre?: string;
  projet?: string;
  projet_titre?: string;
  titre?: string;
  cible?: string;
}

export interface ATraiterAccueil {
  total?: number;
  questions?: number;
  decisions?: number;
  revues?: number;
  arretees?: number;
  premieres?: PremiereDemande[];
  tableaux_illisibles?: unknown;
}

export interface ProjetAccueil {
  id?: string;
  titre?: string;
  etat?: string;
  etat_derive?: string;
  faites?: number | null;
  total?: number | null;
  derniere_note?: string | null;
  derniere_note_tronquee?: boolean;
  questions_ouvertes?: number;
  depot?: string | null;
  branche_prete?: string | null;
}

export interface CarteEnCoursAccueil {
  titre?: string | null;
  projet?: string | null;
  projet_titre?: string | null;
  statut?: string | null;
  voie?: string | null;
  connue?: boolean;
}

export interface ExecutantAccueil {
  etat?: string | null;
  message?: string | null;
  nom?: string | null;
  plateforme?: string | null;
  hote?: string | null;
  derniere_vue?: number | null;
  hors_ligne_depuis?: number | null;
  cartes_en_attente?: number | null;
  pause_reclamations?: boolean | null;
  peut_executer?: boolean | null;
  carte_en_cours?: CarteEnCoursAccueil | null;
  voies_fermees?: Record<string, unknown> | null;
}

export interface QuotaAccueil {
  etat?: string;
  releve_le?: number | null;
  releve_le_lisible?: string | null;
  source?: string | null;
  source_libelle?: string | null;
  libelle?: string | null;
  resume?: { pourcentage_utilise?: number | null; remise_a_zero?: string | null } | null;
}

/** GET /v1/accueil (noyau/accueil.construire) : chaque bloc illisible vaut null, sa raison dans « illisibles ». */
export interface Accueil {
  genere_le?: string;
  a_traiter?: ATraiterAccueil | null;
  chez_hermes?: number | null;
  discussions?: { suivies?: boolean; requetes_ouvertes?: number | null } | null;
  projets?: { en_cours?: number; en_pause?: number; termines_7j?: number; liste?: ProjetAccueil[] } | null;
  executant?: ExecutantAccueil | null;
  quotas?: Record<string, QuotaAccueil> | null;
  notifications?: EtatNotifications | null;
  pause_generale?: PauseGenerale | null;
  illisibles?: Record<string, string>;
}

/** Une tâche cron de Hermes (cron/jobs.py) : seuls les champs lus ici. */
export interface TacheCron {
  id?: string;
  name?: string;
  script?: string | null;
  no_agent?: boolean;
  enabled?: boolean;
  state?: string;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_status?: string | null;
  /** Message de Hermes quand la dernière exécution a échoué (anglais, montré replié). */
  last_error?: string | null;
}

export const lireAccueil = (): Promise<Accueil> => lireJSON<Accueil>(ROUTE_ACCUEIL);

export async function lireTachesCron(): Promise<TacheCron[]> {
  const brut = await lireJSON<unknown>(ROUTE_CRON);
  const liste = Array.isArray(brut) ? brut : (brut as { jobs?: unknown } | null)?.jobs;
  return Array.isArray(liste) ? (liste.filter((t) => t && typeof t === "object") as TacheCron[]) : [];
}

/** Tâches du bilan quotidien : le script de l'image, SANS agent (comme le diagnostic de l'image les admet). */
export function tachesDuBilan(taches: TacheCron[]): TacheCron[] {
  return taches.filter((t) => t.script === SCRIPT_BILAN && t.no_agent === true);
}

export const creerBilanQuotidien = (): Promise<TacheCron> => ecrireJSON<TacheCron>(ROUTE_CRON, TACHE_BILAN);
