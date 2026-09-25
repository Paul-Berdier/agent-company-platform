// Réponses d'API fixées, reprises des formes réelles : /v1/meta relevée sur l'image P2
// (hermes/tests/contrat, test_la_meta_repond_avec_une_session_oidc) et contrat attendu de
// /v1/catalogue (docs/refonte/interface.md).
export const META = {
  contrat: "acp-poste/1",
  greffon: { nom: "acp-poste", version: "0.11.0" },
  hermes: { version: "0.21.5", version_testee: "0.21.5", conforme: true, etiquette: "v2026.9.24", commit: "f97608f" },
  image: {
    base: "nousresearch/hermes-agent:v2026.9.24",
    condensat_index: "sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7",
  },
  demarrage: { soul: { etat: "a_jour" } },
  garde_execution: {
    processus: "processus du tableau de bord (sert /api/ws)",
    presente_dans_le_gestionnaire: true,
    outils_admis: ["web_search", "web_extract", "vision_analyze"],
    alerte: null,
  },
  deploiement: { commit: null },
  alertes: [],
};

export const SESSIONS = {
  sessions: [
    { id: "s1", title: "Plan du site vitrine", source: "cli", started_at: 1790300000, last_active: 1790301000, message_count: 12 },
    { id: "s2", title: null, source: "cli", started_at: 1790200000, last_active: 1790200500, message_count: 3 },
  ],
  total: 2,
};

export const CATALOGUE_ACP = {
  schema: "acp-catalogue/1",
  sources: {
    "emilkowalski/skills": {
      url: "https://github.com/emilkowalski/skills",
      commit: "d16ebe60d09a5ba2afcb7054ede9d0a10c9f6128",
      licence: "MIT",
    },
    "affaan-m/ECC": {
      url: "https://github.com/affaan-m/ECC",
      commit: "5064474d4d762dc9640234a41617cccb79185cec",
      licence: "MIT",
    },
  },
  skills: [
    {
      nom: "emil-design-eng",
      source: "emilkowalski/skills",
      cible: "hermes",
      etat: "active",
      profils: ["web"],
      description_fr: "Philosophie de finition d'interface.",
    },
    {
      nom: "security-review",
      source: "affaan-m/ECC",
      cible: "hermes",
      etat: "desactivee",
      profils: ["web"],
      description_fr: "Liste de contrôle de sécurité.",
    },
    {
      nom: "browser-qa",
      source: "affaan-m/ECC",
      cible: "poste",
      etat: "reportee-p8",
      profils: ["web"],
      raison: "Navigateur : relève du poste (P8).",
    },
    { nom: "mle-workflow", source: "affaan-m/ECC", cible: "hermes", etat: "etat-futur", profils: ["donnees"] },
  ],
  mcp: [
    {
      nom: "context7",
      cible: "hermes",
      etat: "actif",
      connexion: "hors_ligne",
      outils_hermes: ["mcp__context7__resolve_library_id", "mcp__context7__query_docs"],
    },
    { nom: "playwright", cible: "poste", etat: "reporte-p8" },
  ],
  profils: { base: {}, web: {}, recherche: {}, donnees: {} },
  hors_catalogue: [{ nom: "ma-skill-locale" }],
  collisions: [],
  desactivations_non_appliquees: ["codex"],
  alertes: ["1 désactivation n'est pas appliquée : codex."],
};

export const SKILLS_HERMES = [
  { name: "hermes-agent", description: "Hermes itself", category: "autonomous-ai-agents", enabled: true },
  { name: "codex", description: "Delegate to Codex", category: "autonomous-ai-agents", enabled: false },
  { name: "arxiv", description: "Search arXiv", category: "research", enabled: true },
];
