// Formes des réponses lues par les greffons. Tout est facultatif et vérifié à l'usage : une
// valeur absente ou d'un autre type s'affiche « Inconnu », jamais une valeur inventée.

/** GET /api/plugins/acp-poste/v1/meta (hermes/plugins/acp-poste/meta.py, contrat acp-poste/1). */
export interface Meta {
  contrat?: string;
  greffon?: { nom?: string; version?: string | null };
  hermes?: {
    version?: string | null;
    version_testee?: string | null;
    conforme?: boolean | null;
    etiquette?: string | null;
    commit?: string | null;
  };
  image?: { base?: string | null; condensat_index?: string | null };
  demarrage?: {
    soul?: { etat?: string | null } | null;
    [cle: string]: unknown;
  } | null;
  garde_execution?: {
    processus?: string | null;
    presente_dans_le_gestionnaire?: boolean | null;
    outils_admis?: unknown;
    alerte?: string | null;
  };
  deploiement?: { commit?: string | null };
  /** Bloc attendu du catalogue (ajouté par le greffon acp-poste en P3) : lu s'il existe. */
  catalogue?: ResumeCatalogue | null;
  alertes?: unknown;
}

export interface ResumeCatalogue {
  skills_actives?: number | null;
  skills_attendues?: number | null;
  context7?: string | null;
  conforme?: boolean | null;
  ecarts?: number | null;
}

/** GET /api/plugins/acp-poste/v1/catalogue : verrou du catalogue et état vu par le chargeur de
 *  skills de Hermes (docs/refonte/interface.md, contrat attendu). */
export interface Catalogue {
  schema?: string;
  sources?: Record<string, SourceCatalogue>;
  skills?: SkillCatalogue[];
  mcp?: McpCatalogue[];
  profils?: Record<string, unknown>;
  hors_catalogue?: unknown;
  collisions?: unknown;
  desactivations_non_appliquees?: unknown;
  alertes?: unknown;
}

export interface SourceCatalogue {
  url?: string;
  commit?: string;
  licence?: string;
  auteur?: string;
}

export interface SkillCatalogue {
  nom?: string;
  source?: string;
  cible?: string;
  etat?: string;
  profils?: unknown;
  description_fr?: string;
  raison?: string;
}

export interface McpCatalogue {
  nom?: string;
  cible?: string;
  etat?: string;
  transport?: string;
  url?: string;
  outils_hermes?: unknown;
  connexion?: string;
  raison?: string;
}

/** GET /api/skills de Hermes (web/src/lib/api.ts, SkillInfo). */
export interface SkillHermes {
  name?: string;
  description?: string;
  category?: string;
  enabled?: boolean;
}

/** GET /api/sessions de Hermes (web/src/lib/api.ts, PaginatedSessions / SessionInfo). */
export interface PageSessions {
  sessions?: SessionHermes[];
  total?: number;
}

export interface SessionHermes {
  id?: string;
  title?: string | null;
  source?: string | null;
  started_at?: number;
  last_active?: number;
  message_count?: number;
}

export function chaine(valeur: unknown): string | null {
  return typeof valeur === "string" && valeur.trim() ? valeur : null;
}

export function listeDeChaines(valeur: unknown): string[] {
  return Array.isArray(valeur) ? valeur.filter((v): v is string => typeof v === "string" && v.trim() !== "") : [];
}
