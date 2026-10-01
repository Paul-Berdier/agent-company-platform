// Libellés français des codes de l'étape P5 (états du poste, badges des listes, états de la table, connexions,
// classes). Un code inconnu n'est jamais traduit au hasard : null, et la page le montre tel quel, comme donnée.
import { T } from "../chaines";
import type { Libelle } from "../projets/libelles";

const L = (texte: string, famille: Libelle["famille"]): Libelle => ({ texte, famille });

export function libelleEtatDuPoste(etat: unknown): Libelle | null {
  const e = T.poste.etats;
  switch (etat) {
    case "non_configure":
      return L(e.nonConfigure, "neutre");
    case "a_confirmer":
      return L(e.aConfirmer, "degrade");
    case "en_ligne":
      return L(e.enLigne, "succes");
    case "hors_ligne":
      return L(e.horsLigne, "neutre");
    case "redeploiement":
      return L(e.redeploiement, "degrade");
    case "revoque":
      return L(e.revoque, "echec");
    default:
      return null;
  }
}

export function libelleBadge(badge: unknown): Libelle | null {
  const b = T.poste.badges;
  switch (badge) {
    case "releve_du_compte":
      return L(b.releveDuCompte, "succes");
    case "liste_de_secours":
      return L(b.listeDeSecours, "echec");
    case "liste_de_secours_probable":
      return L(b.listeDeSecoursProbable, "degrade");
    case "liste_acceptee":
      return L(b.listeAcceptee, "succes");
    case "alias_documentes":
      return L(b.aliasDocumentes, "actif");
    case "perime":
      return L(b.perime, "degrade");
    case "inconnu":
      return L(b.inconnu, "neutre");
    case "releve_factice":
      return L(b.releveFactice, "degrade");
    case "indisponible":
      return L(b.indisponible, "echec");
    default:
      return null;
  }
}

export function libelleEtatTable(etat: unknown): Libelle | null {
  const e = T.poste.etatsTable;
  switch (etat) {
    case "non_validee":
      return L(e.nonValidee, "neutre");
    case "validee":
      return L(e.validee, "succes");
    case "a_revalider":
      return L(e.aRevalider, "degrade");
    default:
      return null;
  }
}

export function libelleEtatQuotas(etat: unknown): Libelle | null {
  const e = T.poste.etatsQuotas;
  switch (etat) {
    case "releve":
      return L(e.releve, "succes");
    case "perime":
      return L(e.perime, "degrade");
    case "inconnu":
      return L(e.inconnu, "neutre");
    default:
      return null;
  }
}

export function libelleConnexionCodex(etat: unknown): Libelle | null {
  const c = T.poste.connexionsCodex;
  switch (etat) {
    case "compte_chatgpt":
      return L(c.compteChatgpt, "succes");
    case "cle_api":
      return L(c.cleApi, "echec");
    case "autre":
      return L(c.autre, "degrade");
    case "non_connecte":
      return L(c.nonConnecte, "neutre");
    case "inconnu":
      return L(c.inconnu, "neutre");
    default:
      return null;
  }
}

export function libelleConnexionClaude(etat: unknown): Libelle | null {
  const c = T.poste.connexionsClaude;
  switch (etat) {
    case "jeton_reconnu":
      return L(c.jetonReconnu, "succes");
    case "jeton_present_non_verifie":
      return L(c.jetonPresentNonVerifie, "degrade");
    case "refuse":
      return L(c.refuse, "echec");
    case "jeton_absent":
      return L(c.jetonAbsent, "neutre");
    case "inconnu":
      return L(c.inconnu, "neutre");
    default:
      return null;
  }
}

export function libelleGenreOrdre(genre: unknown): string | null {
  const g = T.poste.genresOrdre;
  return genre === "releve" ? g.releve : genre === "pause" ? g.pause : genre === "reprise" ? g.reprise : null;
}

const CLASSES: Record<string, string> = {
  exploration: T.poste.classes.exploration,
  planification: T.poste.classes.planification,
  synthese: T.poste.classes.synthese,
  repondre: T.poste.classes.repondre,
  recherche_web: T.poste.classes.rechercheWeb,
  architecture: T.poste.classes.architecture,
  implementation: T.poste.classes.implementation,
  debogage_tests: T.poste.classes.debogageTests,
  petite_tache: T.poste.classes.petiteTache,
  documentation: T.poste.classes.documentation,
  relecture: T.poste.classes.relecture,
};

export function libelleClasse(classe: unknown): string | null {
  return typeof classe === "string" && classe in CLASSES ? CLASSES[classe] ?? null : null;
}

export function libelleVoie(voie: unknown): string | null {
  const v = T.projets.voies;
  return voie === "hermes" ? v.hermes : voie === "poste-codex" ? v.posteCodex : voie === "poste-claude" ? v.posteClaude
    : null;
}
