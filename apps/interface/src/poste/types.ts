// Formes des réponses des routes P5 du greffon acp-poste (cahier P5 § 12.3 à § 12.5 ; hermes/plugins/acp-poste
// /dashboard/plugin_api.py). Tout champ peut manquer ou valoir null : la page affiche alors « Inconnu », jamais
// une valeur inventée.

export interface MachineVue {
  id?: string;
  nom?: string;
  etat?: string;
  empreinte?: string;
  protocole?: string;
  version_poste?: string;
  cree_le?: number | null;
  confirme_le?: number | null;
  revoque_le?: number | null;
  motif_revocation?: string | null;
  derniere_requete?: number | null;
  politique_valide?: boolean;
}

export interface EtatMachines {
  machine?: MachineVue | null;
  machines?: Record<string, number>;
  codes_utilisables?: number;
}

export interface EtatDuPoste {
  etat?: string;
  message?: string | null;
  machine?: string | null;
  derniere_vue?: number | null;
  hors_ligne_depuis?: number | null;
  source?: string;
  pause_reclamations?: boolean;
  cartes_en_attente?: number | null;
}

export interface BacASable {
  readiness?: string;
  mode_lu?: string;
  origine_mode?: string;
  palier_lu?: string | null;
  stockage_identifiants_lu?: string | null;
  ecriture_admise?: boolean;
  raison?: string | null;
  lu_le?: string;
}

export interface VersionCli {
  lue?: string | null;
  testee?: string;
  conforme?: boolean;
}

export interface PolitiquePoste {
  executants?: string[];
  efforts_interdits?: string[];
  paliers_admis?: string[];
  modeles_codex_permis?: string[];
  alias_claude_permis?: string[];
  reseau_executants?: boolean;
}

export interface ContenuInventaire {
  protocole?: string;
  version_poste?: string;
  releve_le?: string;
  poste?: {
    nom?: string;
    compte?: string;
    windows?: string;
    python?: string;
    politique_empreinte?: string;
    hermes_meme_enveloppe_que_codex?: boolean;
  };
  depots?: Array<{ alias?: string }>;
  bac_a_sable_codex?: BacASable;
  connexions?: { codex?: string; plan_codex?: string | null; claude?: string };
  versions?: Record<string, VersionCli>;
  politique?: PolitiquePoste;
}

export interface Inventaire {
  id?: number;
  machine_id?: string;
  recu_le?: number;
  releve_le?: number;
  contenu?: ContenuInventaire | null;
  alertes?: string[];
}

export interface OrdreVue {
  id?: number;
  genre?: string;
  cree_le?: number;
  livre?: boolean;
}

export interface ReponsePostePage {
  poste?: EtatDuPoste;
  machine?: EtatMachines;
  inventaire?: Inventaire | null;
  alertes?: string[];
  ordres?: OrdreVue[];
}

export interface CodeEnrolement {
  code?: string;
  expire_le?: number;
  validite_s?: number;
  commande?: string;
  protocole?: string;
}

export interface ResultatReleve {
  ordre?: number;
  en_attente_du_poste?: boolean;
  message?: string;
}

// ------------------------------------------------------------------ routage

export interface ModeleReleve {
  id?: string;
  displayName?: string | null;
  isDefault?: boolean | null;
  supportedReasoningEfforts?: string[] | null;
  defaultReasoningEffort?: string | null;
  serviceTiers?: string[];
  defaultServiceTier?: string | null;
  nature?: string;
  resolution_documentee?: string | null;
}

export interface VoieCatalogue {
  etat?: string;
  releve_id?: number;
  releve_le?: number | null;
  version_cli?: string | null;
  source?: string;
  modeles?: ModeleReleve[];
  badge?: string;
  badge_libelle?: string;
  origine_liste?: string | null;
  etat_releve?: string | null;
  detail?: string | null;
  documentation_lue_le?: string | null;
}

export interface Entree {
  voie?: string;
  modele?: string | null;
  effort?: string | null;
  palier?: string | null;
}

export interface EntreeJugee extends Entree {
  admise?: boolean;
  code?: string | null;
  message?: string | null;
}

export interface ClasseRoutage {
  etat?: string;
  entrees?: EntreeJugee[];
  voies?: string[];
  valide_le?: number | null;
  suggestion?: { entrees?: Entree[]; remarques?: string[]; libelle?: string | null };
}

export interface Surcharge {
  id?: number;
  classe?: string;
  voie?: string;
  modele?: string | null;
  effort?: string | null;
  palier?: string | null;
  motif?: string;
  cree_le?: number;
}

export interface VueRoutage {
  voies?: Record<string, VoieCatalogue>;
  releves?: Record<string, number | null>;
  classes?: Record<string, ClasseRoutage>;
  politique_hermes?: {
    efforts_interdits?: string[];
    paliers_admis?: string[];
    efforts_hors_enveloppe?: string[];
    confirmation?: string;
  };
  politique_poste?: PolitiquePoste | null;
  surcharges?: Surcharge[];
  releve_factice?: boolean;
}

// ------------------------------------------------------------------ quotas

export interface FenetreQuota {
  key?: string;
  used_percent?: number | null;
  remaining_percent?: number | null;
  window_minutes?: number | null;
  resets_at?: string | null;
}

export interface CompteurQuota {
  provider?: string;
  status?: string;
  plan?: string | null;
  limit_id?: string;
  windows?: FenetreQuota[];
  limit_reached?: boolean | null;
  observed_at?: string;
  detail?: string | null;
  stale?: boolean;
}

export interface QuotasVoie {
  etat?: string;
  releve_le?: number | null;
  compteurs?: CompteurQuota[];
  seuil_pct?: number;
  source_libelle?: string;
  detail?: string | null;
}

export interface VueQuotas {
  "poste-codex"?: QuotasVoie;
  "poste-claude"?: QuotasVoie;
  hermes?: { etat?: string; libelle?: string };
}
