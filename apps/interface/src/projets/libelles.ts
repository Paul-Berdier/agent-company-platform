// Libellés français des codes renvoyés par le greffon (états, statuts kanban, rôles, exécutants…).
// Un code inconnu n'est jamais traduit au hasard : null, et la page le montre tel quel, comme donnée.
import { T } from "../chaines";

/** Famille de couleur ET de forme d'une étiquette (le pointillé dit « en attente », sans la couleur). */
export type Famille = "succes" | "actif" | "degrade" | "echec" | "neutre";

export interface Libelle {
  texte: string;
  famille: Famille;
}

const L = (texte: string, famille: Famille): Libelle => ({ texte, famille });

export function libelleEtatProjet(etat: unknown, derive: unknown): Libelle | null {
  const e = T.projets.etats;
  switch (etat) {
    case "creation":
      return L(e.creation, "neutre");
    case "en_pause":
      return L(e.enPause, "neutre");
    case "termine":
      return L(e.termine, "succes");
    case "abandonne":
      return L(e.abandonne, "echec");
    case "actif":
      switch (derive) {
        case "exploration":
          return L(e.exploration, "actif");
        case "planification":
          return L(e.planification, "actif");
        case "synthese":
          return L(e.synthese, "actif");
        case "en_cours":
          return L(e.enCours, "actif");
        case "en_attente_du_poste":
          return L(e.enAttenteDuPoste, "degrade");
        case "plafond_atteint":
          return L(e.plafondAtteint, "degrade");
        default:
          return L(e.actif, "actif");
      }
    default:
      return null;
  }
}

export function libelleStatut(statut: unknown): Libelle | null {
  const s = T.projets.statuts;
  switch (statut) {
    case "triage":
      return L(s.triage, "degrade");
    case "todo":
      return L(s.todo, "neutre");
    case "scheduled":
      return L(s.scheduled, "neutre");
    case "ready":
      return L(s.ready, "neutre");
    case "running":
      return L(s.running, "actif");
    case "blocked":
      return L(s.blocked, "echec");
    case "review":
      return L(s.review, "actif");
    case "done":
      return L(s.done, "succes");
    case "archived":
      return L(s.archived, "neutre");
    case "a_creer":
      return L(s.aCreer, "neutre");
    default:
      return null;
  }
}

export function libelleEtatPoste(etat: unknown): Libelle | null {
  const p = T.projets.etatsPoste;
  switch (etat) {
    case "non_configure":
      return L(p.nonConfigure, "neutre");
    case "en_ligne":
      return L(p.enLigne, "succes");
    case "hors_ligne":
      return L(p.horsLigne, "degrade");
    default:
      return null;
  }
}

export function libelleEtatQuestion(etat: unknown): Libelle | null {
  const q = T.projets.etatsQuestion;
  if (etat === "ouverte") return L(q.ouverte, "actif");
  if (etat === "escaladee") return L(q.escaladee, "degrade");
  return null;
}

/** Ordre d'affichage des rôles dans le détail d'un projet (le graphe du § 6 du cahier). */
export const ORDRE_DES_ROLES = [
  "exploration",
  "planification",
  "implementation",
  "relecture",
  "correction",
  "hermes",
  "synthese",
  "repondre",
  "triage",
] as const;

export function libelleRole(role: unknown): string | null {
  const r = T.projets.roles;
  const table: Record<string, string> = {
    exploration: r.exploration,
    planification: r.planification,
    implementation: r.implementation,
    relecture: r.relecture,
    correction: r.correction,
    hermes: r.hermes,
    synthese: r.synthese,
    repondre: r.repondre,
    triage: r.triage,
  };
  return typeof role === "string" ? (table[role] ?? null) : null;
}

export function libelleVoie(voie: unknown): string | null {
  const v = T.projets.voies;
  if (voie === "hermes") return v.hermes;
  if (voie === "poste-codex") return v.posteCodex;
  if (voie === "poste-claude") return v.posteClaude;
  return null;
}

export function libelleProfil(profil: unknown): string | null {
  const c = T.catalogue;
  const table: Record<string, string> = {
    base: c.profilBase,
    web: c.profilWeb,
    recherche: c.profilRecherche,
    donnees: c.profilDonnees,
  };
  return typeof profil === "string" ? (table[profil] ?? null) : null;
}

export function libelleReponses(reponses: unknown): string | null {
  if (reponses === "hermes_d_abord") return T.projets.reponsesHermes;
  if (reponses === "proprietaire") return T.projets.reponsesProprietaire;
  return null;
}

export function libelleCanal(canal: unknown): string | null {
  if (canal === "aucune") return T.projets.canalAucun;
  if (canal === "telegram") return T.projets.canalTelegram;
  if (canal === "ntfy") return T.projets.canalNtfy;
  return null;
}

export function libelleOrigine(origine: unknown): string | null {
  if (origine === "tableau_de_bord") return T.projets.origineTableau;
  if (origine === "discussion") return T.projets.origineDiscussion;
  return null;
}
