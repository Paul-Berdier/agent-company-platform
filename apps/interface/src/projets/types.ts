// Formes des réponses des routes P4 du greffon acp-poste (docs/refonte/projets.md § 4), relevées sur
// l'image construite (formes réelles, tests/fixtures-projets.ts). Tout est facultatif et vérifié à
// l'usage : une valeur absente ou d'un autre type s'affiche « Inconnu », jamais une valeur inventée.

/** Arrêt d'urgence de Hermes (agent/estop.get_state) : présent seulement quand il est engagé. */
export interface PauseGenerale {
  reason?: string | null;
  engaged_at?: string | null;
}

/** Présence du poste (noyau/presence.etat_poste). */
export interface EtatPoste {
  etat?: string;
  machine?: string | null;
  derniere_vue?: number | null;
  derniere_vue_lisible?: string | null;
  hors_ligne_depuis?: number | null;
  cartes_en_attente?: number | null;
  pause_reclamations?: boolean;
  source?: string | null;
  message?: string | null;
}

export interface EtatNotifications {
  canal?: string | null;
  configure?: boolean;
  connu?: boolean;
  message?: string | null;
}

export interface CompteursProjet {
  faites?: number | null;
  total?: number | null;
  en_cours?: number | null;
  en_attente_du_poste?: number | null;
  bloquees?: number | null;
  triage?: number | null;
}

/** Un projet de GET /v1/projets (noyau/projets.lister). */
export interface ResumeProjet {
  id?: string;
  titre?: string;
  tableau?: string;
  etat?: string;
  etat_derive?: string;
  profil?: string;
  depot?: string | null;
  reponses?: string;
  tour?: number;
  origine?: string;
  compteurs?: CompteursProjet;
  derniere_note?: string | null;
  questions_ouvertes?: number;
  plafonds?: { tours?: number; cartes?: number; corrections?: number };
  cartes_creees?: number;
  cree_le?: number;
}

/** GET /v1/projets. */
export interface ListeProjets {
  projets?: ResumeProjet[];
  poste?: EtatPoste;
  pause_generale?: PauseGenerale | null;
  notifications?: EtatNotifications;
  questions_ouvertes?: number;
}

export interface CarteProjet {
  carte?: string | null;
  titre?: string;
  role?: string;
  classe?: string;
  tour?: number;
  ref?: string;
  voie?: string;
  statut?: string;
  modele?: string | null;
  effort?: string | null;
  effort_carte?: string | null;
  palier?: string | null;
  source_routage?: string | null;
  mention?: string | null;
  modele_servi?: string | null;
  relue?: string | null;
  resume?: string | null;
}

export interface TourProjet {
  tour?: number;
  resume?: string;
  decisions?: unknown;
}

export interface QuestionDuProjet {
  id?: string;
  carte?: string;
  etat?: string;
  texte?: string;
  carte_repondre?: string | null;
}

export interface EntreeJournal {
  quand?: number;
  acteur?: string;
  action?: string;
  cible?: string | null;
  detail?: string | null;
}

/** GET /v1/projets/{id} → { projet } (noyau/projets.etat, avec le journal). Ici, les questions
 *  ouvertes sont une LISTE (un nombre dans la liste des projets). */
export interface DetailProjet extends Omit<ResumeProjet, "questions_ouvertes"> {
  objectif?: string;
  restants?: { tours?: number; cartes?: number };
  exploration?: string | null;
  tours?: TourProjet[];
  cartes?: CarteProjet[];
  questions_ouvertes?: QuestionDuProjet[];
  termine_le?: number | null;
  journal?: EntreeJournal[];
}

export interface ReponseDetail {
  projet?: DetailProjet;
}

export interface QuestionOuverte {
  id?: string;
  projet?: string;
  projet_titre?: string;
  tableau?: string;
  carte?: string;
  etat?: string;
  texte?: string;
  carte_repondre?: string | null;
  motif_escalade?: string | null;
  cree_le?: number;
}

export interface CarteEnAttente {
  projet?: string;
  projet_titre?: string;
  tableau?: string;
  carte?: string;
  titre?: string;
  assigne?: string | null;
  abandonnee?: boolean;
  raison?: string | null;
}

/** GET /v1/questions (noyau/questions.lister). */
export interface ListeQuestions {
  questions?: QuestionOuverte[];
  triage?: CarteEnAttente[];
  bloquees?: CarteEnAttente[];
  tableaux_illisibles?: unknown;
}

export interface ModeleReleve {
  id?: string;
  displayName?: string | null;
  isDefault?: boolean;
  supportedReasoningEfforts?: unknown;
  defaultReasoningEffort?: string | null;
}

export interface VoieReleve {
  etat?: string;
  releve_le?: number | null;
  releve_le_lisible?: string | null;
  perime?: boolean;
  source?: string | null;
  modeles?: ModeleReleve[];
  depots?: unknown;
}

/** GET /v1/poste → { poste, catalogue } (noyau/routage.catalogue). */
export interface CatalogueDuPoste {
  etat?: string;
  voies?: Record<string, VoieReleve>;
  politique?: { efforts_interdits?: unknown; paliers_admis?: unknown; voies_par_classe?: Record<string, unknown> };
  releve_factice?: boolean;
  message?: string | null;
}

export interface ReponsePoste {
  poste?: EtatPoste;
  catalogue?: CatalogueDuPoste;
}

/** Corps de POST /v1/projets. */
export interface DemandeLancement {
  titre: string;
  objectif: string;
  profil: string;
  depot: string | null;
  reponses: "hermes_d_abord" | "proprietaire";
  exploration?: { voie: string; modele?: string; effort?: string };
}

export interface ReponseLancement {
  projet?: ResumeProjet & { cartes?: Record<string, string | null> };
  deja_lance?: boolean;
}
