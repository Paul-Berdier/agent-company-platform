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
  /** La note est un extrait (200 premiers caractères) : le détail donne les résumés en entier. */
  derniere_note_tronquee?: boolean;
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
  /** Longueur du résumé entier, et vrai si « resume » n'en est qu'un extrait (500 caractères). */
  resume_longueur?: number | null;
  resume_tronque?: boolean;
}

/** Résultat du projet : la synthèse faite du dernier tour, en entier (borne haute dite). */
export interface ResultatProjet {
  tour?: number;
  carte?: string;
  texte?: string;
  longueur?: number;
  tronque?: boolean;
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
  resultat?: ResultatProjet | null;
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
  carte_titre?: string | null;
  etat?: string;
  texte?: string;
  contexte?: string | null;
  carte_repondre?: string | null;
  motif_escalade?: string | null;
  cree_le?: number;
  /** Étape P7 (règle unique, correction K6) : « hermes » si la carte « répondre » existe et la question est ouverte. */
  chez?: string;
  carte_repondre_statut?: string | null;
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
  /** Carte de décision du greffon : « tours », « cartes », « corrections », « sans_plan » ; null sinon. */
  genre?: string | null;
  /** Gestes offerts : « prolonger », « relancer », « conclure », « reprendre ». */
  actions?: unknown;
  /** Étape P7 (carte arrêtée) : se relance-t-elle, sinon pourquoi ; carte de l'exécutant (session neuve). */
  relancable?: boolean;
  refus_relance?: string | null;
  executant?: boolean;
  /** Partie E (K25) : bloquée pour un secret ; le travail fautif reste en quarantaine sur l'exécutant. */
  quarantaine?: boolean;
}

/** POST /v1/questions/{q}/reponse. */
export interface ResultatReponse {
  question?: string;
  etat?: string;
  carte_debloquee?: boolean;
  /** Projet en pause : la carte reprendra à la reprise du projet. */
  reprise_differee?: boolean;
}

/** POST /v1/triage/{tableau}/{carte}/reprendre. */
export interface ResultatTriage {
  carte?: string;
  reprise?: boolean;
  action?: string | null;
  plafond?: { genre?: string; avant?: number; apres?: number } | null;
}

/** POST /v1/triage/{tableau}/{carte}/conclure. */
export interface ResultatConclusion {
  carte?: string;
  conclu?: boolean;
  projet?: ResumeProjet;
}

/** GET /v1/projets/{id}/cartes/{carte} → { carte }. */
export interface CarteLue {
  carte?: string;
  titre?: string;
  role?: string;
  statut?: string;
  resume?: string | null;
  longueur?: number;
  tronque?: boolean;
}

/** GET /v1/questions (noyau/questions.lister). */
/** Carte en revue pour des fichiers de pilotage des agents (étape P6, cahier P6 § 5.4, § 9.3). */
export interface RevuePilotage {
  projet?: string;
  projet_titre?: string;
  tableau?: string;
  carte?: string;
  titre?: string;
  role?: string;
  voie?: string;
  chemins?: unknown;
  diffstat?: { fichiers?: number; ajouts?: number; retraits?: number } | null;
  branche?: string | null;
  tete?: string | null;
  resume?: string | null;
  diff?: string;
}

export interface ResultatRevue {
  carte?: string;
  etat?: string | null;
}

/** Cinquième section (étape P7, cahier P7 § 3.5) : nombre de requêtes ouvertes du tableau de bord, en lecture seule. */
export interface DiscussionsServeur {
  suivies?: boolean;
  requetes_ouvertes?: number | null;
  message?: string | null;
  limite?: string | null;
}

/** Compteurs de la file (étape P7, cahier P7 § 3.2) : les discussions en attente sont comptées par le client. */
export interface CompteursFile {
  a_traiter?: number;
  chez_hermes?: number;
  questions?: number;
  decisions?: number;
  revues?: number;
  arretees?: number;
}

export interface ListeQuestions {
  questions?: QuestionOuverte[];
  triage?: CarteEnAttente[];
  bloquees?: CarteEnAttente[];
  tableaux_illisibles?: unknown;
  revues?: RevuePilotage[];
  discussions?: DiscussionsServeur;
  compteurs?: CompteursFile;
}

/** POST /v1/cartes/{tableau}/{carte}/relancer. */
export interface ResultatRelance {
  carte?: string;
  relancee?: boolean;
  statut_apres?: string | null;
  session_neuve?: boolean;
  /** Partie E (K25) : la carte repart sur une branche neuve, sans le travail en quarantaine. */
  branche_neuve?: boolean;
}

/** POST /v1/projets/{id}/reponses. */
export interface ResultatReglageReponses {
  projet?: ResumeProjet;
  avant?: string;
  apres?: string;
  questions_ouvertes_inchangees?: number;
}

/** POST /v1/projets/{id}/clore. */
export interface ResultatCloture {
  projet?: ResumeProjet;
  clos?: boolean;
  etat?: string;
  cartes_archivees?: unknown;
  cartes_non_archivees?: unknown;
  questions_annulees?: number;
  branches_rapportees?: unknown;
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

/** Étape P7 (cahier P7 § 11.2) : un dépôt du dernier inventaire, sa visibilité MESURÉE par l'exécutant (null :
 *  jamais mesurée) et les voies du poste fermées pour lui (calcul du routage du greffon, raison française). */
export interface DepotMesure {
  alias?: string;
  visibilite?: string | null;
  lecture?: string | null;
  verifie_le?: string | null;
  voies_fermees?: Record<string, string>;
}

export interface ReponsePoste {
  poste?: EtatPoste;
  catalogue?: CatalogueDuPoste;
  /** Étape P7 : visibilité des dépôts (grisage de Codex dans « Nouveau projet »). */
  executant?: { connu?: boolean; depots?: DepotMesure[] };
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
