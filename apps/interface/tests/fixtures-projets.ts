// Réponses des routes P4 d'acp-poste, reprises des formes RÉELLES : relevées le 26/09/2026 sur l'image
// acp-hermes-tests:p4g (routes montées comme dans hermes/tests/image/test_routes_projets.py, base et
// tableaux jetables, relevé FACTICE), puis réduites. Retouches de test, dites : l'avancement du second
// projet de LISTE (tour 1, 2 cartes sur 4, une note) et les entrées « triage » et « bloquees » de
// QUESTIONS (vides au relevé), écrites d'après noyau/questions.lister. Champs ajoutés par les corrections de
// la relecture de P4 (26/09/2026), écrits d'après le greffon corrigé : message « état du canal inconnu »,
// résumés « resume_longueur » et « resume_tronque », « resultat », titre de carte et contexte d'une question,
// genre, gestes et raison des cartes en triage et bloquées.
export const LISTE_VIDE = {
  projets: [],
  poste: {
    pause_reclamations: false,
    cartes_en_attente: 0,
    etat: "non_configure",
    derniere_vue: null,
    hors_ligne_depuis: null,
    machine: null,
    message: "Le poste n'a jamais été vu (connexion prévue à l'étape P5).",
  },
  pause_generale: null,
  notifications: {
    canal: null,
    configure: false,
    connu: false,
    message: "État du canal de notification inconnu : la passerelle ne l'a pas encore publié.",
  },
  questions_ouvertes: 0,
};

export const LISTE = {
  projets: [
    {
      id: "p_367e23fd51b7",
      titre: "Outil",
      tableau: "acp-outil-3dd5",
      etat: "actif",
      profil: "base",
      depot: "jetable",
      reponses: "proprietaire",
      tour: 0,
      origine: "tableau_de_bord",
      etat_derive: "exploration",
      compteurs: { faites: 0, total: 2, en_cours: 0, en_attente_du_poste: 0, bloquees: 0, triage: 0 },
      derniere_note: null,
      questions_ouvertes: 1,
      plafonds: { tours: 3, cartes: 30 },
      cartes_creees: 2,
      cree_le: 1790423039,
    },
    {
      id: "p_a35a8b99fb0e",
      titre: "Veille LLM",
      tableau: "acp-veille-llm-b43a",
      etat: "actif",
      profil: "recherche",
      depot: null,
      reponses: "hermes_d_abord",
      tour: 1,
      origine: "tableau_de_bord",
      etat_derive: "en_cours",
      compteurs: { faites: 2, total: 4, en_cours: 1, en_attente_du_poste: 0, bloquees: 0, triage: 0 },
      derniere_note: "Plan posé : deux recherches.",
      questions_ouvertes: 0,
      plafonds: { tours: 3, cartes: 30 },
      cartes_creees: 4,
      cree_le: 1790423038,
    },
  ],
  poste: {
    pause_reclamations: false,
    cartes_en_attente: 0,
    etat: "en_ligne",
    machine: "poste-simule",
    derniere_vue: 1790423039,
    derniere_vue_lisible: "26/09/2026 13:43",
    hors_ligne_depuis: null,
    source: "simule",
  },
  pause_generale: null,
  notifications: { canal: "aucune", configure: false, connu: true, message: "Notifications non configurées." },
  questions_ouvertes: 1,
};

export const PAUSE_GENERALE = { reason: "ACP : pause du propriétaire", engaged_at: "2026-09-26T11:44:00.073871+00:00" };

export const DETAIL = {
  projet: {
    id: "p_367e23fd51b7",
    titre: "Outil",
    tableau: "acp-outil-3dd5",
    etat: "actif",
    profil: "base",
    depot: "jetable",
    reponses: "proprietaire",
    tour: 0,
    origine: "tableau_de_bord",
    objectif: "Écrire outil.py.",
    etat_derive: "exploration",
    plafonds: { tours: 3, cartes: 30, corrections: 2 },
    restants: { tours: 3, cartes: 28 },
    cartes_creees: 2,
    compteurs: { faites: 0, total: 2 },
    exploration: "Question ouverte (ACP) : q_b627a3c245ec",
    tours: [],
    cartes: [
      {
        carte: "t_7aa28f61",
        titre: "Exploration du dépôt « jetable »",
        role: "exploration",
        classe: "exploration",
        tour: 0,
        ref: "exploration",
        voie: "poste-claude",
        statut: "scheduled",
        modele: "factice-claude-1",
        effort: "low",
        effort_carte: "low",
        palier: "default",
        source_routage: "choix_explicite",
        mention: "quota inconnu",
        modele_servi: "Non observé",
        relue: null,
        resume: "Question ouverte (ACP) : q_b627a3c245ec",
        resume_longueur: 38,
        resume_tronque: false,
      },
      {
        carte: "t_342c81eb",
        titre: "Planification — Outil",
        role: "planification",
        classe: "planification",
        tour: 0,
        ref: "planification",
        voie: "hermes",
        statut: "todo",
        modele: "modèle par défaut du profil",
        effort: null,
        effort_carte: null,
        palier: "default",
        source_routage: "profil",
        mention: null,
        modele_servi: "Non observé",
        relue: null,
        resume: null,
        resume_longueur: null,
        resume_tronque: false,
      },
    ],
    resultat: null,
    questions_ouvertes: [
      { id: "q_b627a3c245ec", carte: "t_7aa28f61", etat: "escaladee", texte: "Quelle version de Python viser ?", carte_repondre: null },
    ],
    cree_le: 1790423039,
    termine_le: null,
    journal: [
      {
        quand: 1790423039,
        acteur: "acp-poste",
        action: "question_escaladee",
        cible: "q_b627a3c245ec",
        detail: "politique du projet : le propriétaire répond lui-même",
      },
      {
        quand: 1790423039,
        acteur: "proprietaire:proprietaire-test",
        action: "lancement",
        cible: "acp-outil-3dd5",
        detail: '{"origine": "tableau_de_bord", "depot": "jetable", "profil": "base"}',
      },
    ],
  },
};

export const QUESTIONS = {
  questions: [
    {
      id: "q_b627a3c245ec",
      projet: "p_367e23fd51b7",
      projet_titre: "Outil",
      tableau: "acp-outil-3dd5",
      carte: "t_7aa28f61",
      carte_titre: "Exploration du dépôt « jetable »",
      etat: "escaladee",
      texte: "Quelle version de Python viser ?",
      contexte: "Le dépôt cible Python 3.11 et 3.12 dans sa CI.",
      carte_repondre: null,
      motif_escalade: "politique du projet : le propriétaire répond lui-même",
      cree_le: 1790423039,
    },
  ],
  triage: [
    {
      projet: "p_a35a8b99fb0e",
      projet_titre: "Veille LLM",
      tableau: "acp-veille-llm-b43a",
      carte: "t_0c1d2e3f",
      titre: "Plafond atteint : tours — votre décision est attendue",
      assigne: "default",
      abandonnee: false,
      raison: "3 tours planifiés",
      genre: "tours",
      actions: ["prolonger", "conclure"],
    },
  ],
  bloquees: [
    {
      projet: "p_a35a8b99fb0e",
      projet_titre: "Veille LLM",
      tableau: "acp-veille-llm-b43a",
      carte: "t_9a8b7c6d",
      titre: "Carte à la main",
      assigne: "poste-codex",
      abandonnee: false,
      raison: "Refusé par ACP : carte poste-* non émise par le greffon acp-poste ; seul le greffon crée les cartes du poste.",
    },
  ],
  tableaux_illisibles: [],
};

const POLITIQUE = {
  efforts_interdits: ["max", "ultra", "ultracode"],
  paliers_admis: ["default"],
  voies_par_classe: { exploration: ["poste-claude", "poste-codex"], planification: ["hermes"] },
};

export const POSTE_VIDE = {
  poste: LISTE_VIDE.poste,
  catalogue: {
    etat: "inconnu",
    voies: { "poste-codex": { etat: "inconnu", releve_le: null }, "poste-claude": { etat: "inconnu", releve_le: null } },
    hermes: { modele: "modèle par défaut du profil" },
    routage: { valide: false, classes: {} },
    politique: POLITIQUE,
    releve_factice: false,
    message: "Catalogue du poste inconnu : aucun relevé (le poste publie son inventaire à l'étape P5).",
  },
};

function voie(suffixe: string) {
  return {
    etat: "a_jour",
    releve_le: 1790423039,
    releve_le_lisible: "26/09/2026 13:43",
    age_s: 0,
    perime: false,
    source: "releve_factice",
    version_cli: "0.0.0-factice",
    modeles: [
      {
        id: `factice-${suffixe}-1`,
        displayName: `Factice ${suffixe} 1`,
        isDefault: true,
        supportedReasoningEfforts: ["low", "medium", "high", "xhigh", "max", "extreme"],
        defaultReasoningEffort: "medium",
        serviceTiers: ["default", "priority"],
        defaultServiceTier: "default",
      },
      {
        id: `factice-${suffixe}-2`,
        displayName: null,
        isDefault: false,
        supportedReasoningEfforts: ["low"],
        defaultReasoningEffort: null,
        serviceTiers: [],
        defaultServiceTier: null,
      },
    ],
    quotas: null,
    depots: ["jetable"],
  };
}

export const POSTE_RELEVE = {
  poste: LISTE.poste,
  catalogue: {
    etat: "connu",
    voies: { "poste-codex": voie("codex"), "poste-claude": voie("claude") },
    hermes: { modele: "modèle par défaut du profil" },
    routage: { valide: false, classes: {} },
    politique: POLITIQUE,
    releve_factice: true,
  },
};

export const CATALOGUE_PROFILS = {
  profils: {
    base: { libelle: "Base (tous les projets)" },
    web: { libelle: "Site web" },
    recherche: { libelle: "Recherche" },
    donnees: { libelle: "Données" },
  },
};

export const LANCEMENT = {
  projet: {
    id: "p_a35a8b99fb0e",
    titre: "Veille LLM",
    tableau: "acp-veille-llm-b43a",
    etat: "actif",
    profil: "recherche",
    depot: null,
    reponses: "hermes_d_abord",
    tour: 0,
    origine: "tableau_de_bord",
    cartes: { exploration: null, planification: "t_948b1e24" },
  },
  deja_lance: false,
};

/** Refus réel du greffon (400, projet sur dépôt sans inventaire). */
export const REFUS_AUCUN_INVENTAIRE =
  '{"detail": {"code": "aucun_inventaire", "message": "Refusé par ACP : aucun dépôt autorisé n\'est connu : le poste ' +
  "n'a encore publié aucun inventaire (étape P5). Lancez le projet sans dépôt, ou connectez le poste.\"}}";
