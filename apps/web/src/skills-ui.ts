/**
 * Bibliothèque de skills (route « Bibliothèque », spec Lot D §7).
 *
 * Écrans : recherche (installés + catalogue), import à quatre sources (SKILL.md
 * manuel, archive, dossier autorisé, GitHub épinglé), liste, détail (frontmatter,
 * licence, nature, dépendances, findings indicatifs, arborescence et visionneuse),
 * révisions avec diff / approbation / restauration, rattachements par projet et
 * actions Activer / Désactiver / Révoquer.
 *
 * Deux règles structurent ce module :
 * 1. tout contenu importé (frontmatter, fichiers, findings, catalogue) est une
 *    donnée non fiable : il est inséré via `textContent` uniquement, jamais comme
 *    HTML, et les fichiers texte sont affichés dans un `<pre>` ;
 * 2. aucun faux succès : chargement, vide, hors ligne, refus, réponse invalide et
 *    capacité non configurée ont chacun un panneau explicite, et aucune donnée de
 *    démonstration ne remplace une réponse manquante.
 */

import type {
  Project,
  ProjectExtensions,
  SkillBinding,
  SkillCatalogEntry,
  SkillDetail,
  SkillFile,
  SkillFileContent,
  SkillRevision,
  SkillSummary,
} from "@acp/contracts";

import "./skills.css";
import { AuthApiClient } from "./auth-api";
import {
  SKILLS_ALLOWED_DIRS_ACTION,
  SKILLS_GITHUB_ACTION,
  SkillsApiClient,
  buildSkillFileTree,
  describeSkillsError,
  encodeBase64,
  findingLevelBadge,
  formatFileSize,
  previewFrontmatter,
  skillKindBadge,
  skillSourceLabel,
  skillStatusBadge,
  summarizeRevisionDiff,
  type SkillSourceInput,
  type SkillTreeNode,
} from "./skills-api";
import {
  el,
  errorMessage,
  formatDateTime,
  labeledField,
  normalizeApiError,
  sectionHeader,
  statePanel,
  statusChip,
} from "./ui-primitives";
import {
  WorkspaceApiClient,
  WorkspaceApiError,
  WorkspaceHttpClient,
  type Validator,
} from "./workspace-api";

type Phase = "idle" | "loading" | "ready" | "error";
type ImportTab = "manual" | "archive" | "directory" | "github";
type ImportTarget = "skill" | "revision";
type FeedbackTone = "success" | "error" | "info";
/** Une seule zone `aria-live` est active à la fois : celle où l’action a été déclenchée. */
type FeedbackScope = "library" | "detail";

interface Feedback {
  tone: FeedbackTone;
  message: string;
  scope: FeedbackScope;
}

interface ImportDraft {
  name: string;
  note: string;
  manualText: string;
  archiveFilename: string;
  archiveBase64: string;
  archiveSize: number;
  directoryPath: string;
  githubRepository: string;
  githubRef: string;
  githubPath: string;
}

interface ConfirmState {
  kind: "revoke" | "rollback";
  revisionNumber: number | null;
}

interface LibraryState {
  phase: Phase;
  error: WorkspaceApiError | null;
  query: string;
  skills: SkillSummary[];
  catalog: SkillCatalogEntry[];
  catalogFiltered: boolean;
  catalogError: WorkspaceApiError | null;
  projects: Project[];
  projectsError: WorkspaceApiError | null;
  selectedId: string | null;
  detail: SkillDetail | null;
  detailPhase: Phase;
  detailError: WorkspaceApiError | null;
  revisionNumber: number | null;
  files: SkillFile[];
  filesPhase: Phase;
  filesError: WorkspaceApiError | null;
  filePath: string | null;
  fileContent: SkillFileContent | null;
  filePhase: Phase;
  fileError: WorkspaceApiError | null;
  importOpen: boolean;
  importTab: ImportTab;
  importTarget: ImportTarget;
  bindingProjectId: string;
  extensions: ProjectExtensions | null;
  extensionsError: WorkspaceApiError | null;
  confirm: ConfirmState | null;
  revokeReason: string;
  rollbackNote: string;
  approvalComment: string;
  busy: string | null;
  feedback: Feedback | null;
}

/**
 * Limite locale alignée sur `MAX_TOTAL_BYTES` de l’API (20 Mio, `skills/sources.py`) : au-delà,
 * l’archive serait encodée en base64 puis refusée par un 413. Les 25 Mio de `MAX_GITHUB_BYTES`
 * concernent le seul téléchargement de tarball GitHub, jamais une archive envoyée d’ici.
 * Le serveur reste de toute façon seul juge (413).
 */
const ARCHIVE_MAX_BYTES = 20 * 1024 * 1024;
/** Identifiant du panneau d’onglets d’import (relation `aria-controls`/`aria-labelledby`). */
const IMPORT_PANEL_ID = "skills-import-panel";
const IMPORT_TABS: { id: ImportTab; label: string }[] = [
  { id: "manual", label: "SKILL.md manuel" },
  { id: "archive", label: "Archive" },
  { id: "directory", label: "Dossier autorisé" },
  { id: "github", label: "GitHub" },
];

/**
 * Client de repli, utilisé uniquement quand l’appelant n’en fournit pas.
 *
 * `GET /auth/session` fait **tourner** le jeton CSRF côté serveur (un seul jeton est
 * valide à la fois) : un second client qui relit la session invaliderait celui du shell
 * et ferait échouer ses propres écritures en 403. Le module partage donc le client de
 * l’appelant dès qu’il en reçoit un ; sans client fourni, il ne relit la session qu’au
 * moment où une écriture part réellement sur le réseau — jamais à l’ouverture de la
 * route, jamais pour un refus purement local.
 */
class LazyCsrfHttpClient extends WorkspaceHttpClient {
  override async request<T>(
    path: string,
    validator: Validator<T>,
    init: RequestInit = {},
    security: Parameters<WorkspaceHttpClient["request"]>[3] = {},
  ): Promise<T> {
    const method = (init.method ?? "GET").toUpperCase();
    const mutation = method !== "GET" && method !== "HEAD" && method !== "OPTIONS";
    // `fetchSession` passe par une requête GET : aucune récursion possible ici.
    if (mutation && security.csrf !== false) await ensureCsrf();
    return super.request(path, validator, init, security);
  }
}

const fallbackHttp = new LazyCsrfHttpClient();
let http: WorkspaceHttpClient = fallbackHttp;
let api = new SkillsApiClient({ http });
let authApi = new AuthApiClient({ http });
let workspaceApi = new WorkspaceApiClient({ http });

function initialDraft(): ImportDraft {
  return {
    name: "",
    note: "",
    manualText: "",
    archiveFilename: "",
    archiveBase64: "",
    archiveSize: 0,
    directoryPath: "",
    githubRepository: "",
    githubRef: "",
    githubPath: "",
  };
}

const draft: ImportDraft = initialDraft();

function initialLibraryState(): LibraryState {
  return {
  phase: "idle",
  error: null,
  query: "",
  skills: [],
  catalog: [],
  catalogFiltered: false,
  catalogError: null,
  projects: [],
  projectsError: null,
  selectedId: null,
  detail: null,
  detailPhase: "idle",
  detailError: null,
  revisionNumber: null,
  files: [],
  filesPhase: "idle",
  filesError: null,
  filePath: null,
  fileContent: null,
  filePhase: "idle",
  fileError: null,
  importOpen: false,
  importTab: "manual",
  importTarget: "skill",
  bindingProjectId: "",
  extensions: null,
  extensionsError: null,
  confirm: null,
  revokeReason: "",
  rollbackNote: "",
  approvalComment: "",
  busy: null,
  feedback: null,
  };
}

const state: LibraryState = initialLibraryState();

let mount: HTMLElement | null = null;
/** Compteurs distincts : un rechargement de la liste n’annule pas un détail en cours. */
let librarySequence = 0;
let detailSequence = 0;
/** Vrai seulement quand ce module possède son client et lui a déjà posé un jeton CSRF. */
let csrfReady = false;

/**
 * Adopte le client HTTP de l’appelant (le shell) ou retombe sur celui du module.
 * Changer de client remet le jeton à vérifier : les jetons ne sont pas interchangeables.
 */
function useHttpClient(client: WorkspaceHttpClient | undefined): void {
  const next = client ?? fallbackHttp;
  if (next === http) return;
  http = next;
  api = new SkillsApiClient({ http });
  authApi = new AuthApiClient({ http });
  workspaceApi = new WorkspaceApiClient({ http });
  csrfReady = false;
}

/** Le propriétaire d’un client injecté gère lui-même son jeton : ce module n’y touche pas. */
function ownsHttpClient(): boolean {
  return http === fallbackHttp;
}

// --- Primitives locales -------------------------------------------------------

function button(
  label: string,
  variant: "primary" | "secondary",
  onClick: () => void,
  options: { disabled?: boolean; pressed?: boolean; describedBy?: string } = {},
): HTMLButtonElement {
  const node = el("button", `button button-${variant}`, label);
  node.type = "button";
  node.disabled = options.disabled ?? false;
  if (options.pressed !== undefined) node.setAttribute("aria-pressed", String(options.pressed));
  if (options.describedBy) node.setAttribute("aria-describedby", options.describedBy);
  node.addEventListener("click", onClick);
  return node;
}

function textInput(value: string, onInput: (value: string) => void, placeholder = ""): HTMLInputElement {
  const node = el("input", "form-control");
  node.type = "text";
  node.value = value;
  if (placeholder) node.placeholder = placeholder;
  node.addEventListener("input", () => onInput(node.value));
  return node;
}

function textArea(value: string, rows: number, onInput: (value: string) => void): HTMLTextAreaElement {
  const node = el("textarea", "form-control form-textarea");
  node.rows = rows;
  node.value = value;
  node.spellcheck = false;
  node.addEventListener("input", () => onInput(node.value));
  return node;
}

/** Liste de métadonnées clé/valeur : les valeurs sont toujours du texte brut. */
function metaList(entries: [string, string][]): HTMLElement {
  const list = el("dl", "skills-meta");
  for (const [term, value] of entries) {
    list.append(el("dt", "skills-meta-term", term), el("dd", "skills-meta-value", value));
  }
  return list;
}

function chipRow(chips: HTMLElement[]): HTMLElement {
  const row = el("div", "skills-chips");
  row.append(...chips);
  return row;
}

function bulletList(items: string[], className = "skills-list"): HTMLElement {
  const list = el("ul", className);
  for (const item of items) list.append(el("li", "skills-list-item", item));
  return list;
}

/** Panneau d’erreur : ton, titre, message et action serveur à effectuer (jamais exécutée ici). */
function errorPanel(error: WorkspaceApiError, onRetry?: () => void): HTMLElement {
  const described = describeSkillsError(error);
  const panel = statePanel(described.tone, described.title, described.message, onRetry);
  if (described.action) panel.append(el("p", "skills-action", described.action));
  return panel;
}

function feedbackNode(scope: FeedbackScope): HTMLElement {
  const node = el("p", "form-feedback skills-feedback");
  node.setAttribute("role", "status");
  node.setAttribute("aria-live", "polite");
  node.dataset.scope = scope;
  if (state.feedback && state.feedback.scope === scope) {
    node.dataset.tone = state.feedback.tone;
    node.textContent = state.feedback.message;
  }
  return node;
}

function setFeedback(tone: FeedbackTone, message: string, scope: FeedbackScope): void {
  state.feedback = { tone, message, scope };
}

function setErrorFeedback(error: WorkspaceApiError, scope: FeedbackScope): void {
  const described = describeSkillsError(error);
  const action = described.action ? ` ${described.action}` : "";
  setFeedback("error", `${described.title} : ${described.message}${action}`, scope);
}

function projectLabel(projectId: string): string {
  const project = state.projects.find((candidate) => candidate.id === projectId);
  return project ? `${project.name} (${project.id})` : projectId;
}

/** Valeur de frontmatter rendue en texte : aucune interprétation, aucune exécution. */
function frontmatterValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "—";
  try {
    return JSON.stringify(value);
  } catch {
    return "Valeur non représentable";
  }
}

// --- Chargement des données ---------------------------------------------------

/**
 * Pose le jeton CSRF au moment où une écriture part sur le réseau (appelée par
 * `LazyCsrfHttpClient`), et uniquement si ce module possède son client. Deux raisons de ne
 * jamais appeler `/auth/session` à l’ouverture de la route : l’API fait tourner le jeton à
 * chaque lecture de session (un seul est valide à la fois), et une simple consultation ne
 * doit invalider aucune écriture ailleurs dans l’application.
 */
async function ensureCsrf(): Promise<void> {
  if (!ownsHttpClient() || csrfReady) return;
  await authApi.fetchSession();
  csrfReady = true;
}

/**
 * Un 403 peut venir d’un jeton devenu invalide (une autre partie de l’application a relu
 * la session). On réarme alors la demande pour que la prochaine tentative reparte d’un
 * jeton frais, au lieu d’échouer définitivement jusqu’au rechargement de la page.
 */
function invalidateCsrfOnRefusal(error: WorkspaceApiError): void {
  if (error.kind === "forbidden") csrfReady = false;
}

async function loadLibrary(): Promise<void> {
  const sequence = ++librarySequence;
  state.phase = "loading";
  state.error = null;
  state.catalogError = null;
  paint();

  // Aucune lecture de session ici : elle ferait tourner le jeton CSRF partagé (cf. `ensureCsrf`).
  const [searchResult, catalogResult, overviewResult] = await Promise.allSettled([
    api.search(state.query),
    api.fetchCatalog(),
    workspaceApi.fetchOverview(),
  ]);
  if (sequence !== librarySequence) return;

  if (searchResult.status === "fulfilled") {
    state.skills = searchResult.value.installed;
    state.phase = "ready";
    state.error = null;
    if (state.query) {
      state.catalog = searchResult.value.catalog;
      state.catalogFiltered = true;
      state.catalogError = null;
    }
  } else {
    state.phase = "error";
    state.error = normalizeApiError(searchResult.reason, "La liste des skills est indisponible.");
  }

  if (!state.query) {
    state.catalogFiltered = false;
    if (catalogResult.status === "fulfilled") {
      state.catalog = catalogResult.value;
      state.catalogError = null;
    } else {
      state.catalog = [];
      state.catalogError = normalizeApiError(catalogResult.reason, "Le catalogue est indisponible.");
    }
  }

  if (overviewResult.status === "fulfilled") {
    state.projects = overviewResult.value.projects;
    state.projectsError = null;
  } else {
    state.projects = [];
    state.projectsError = normalizeApiError(overviewResult.reason, "La liste des projets est indisponible.");
  }

  paint();
}

async function loadDetail(skillId: string): Promise<void> {
  const sequence = ++detailSequence;
  state.selectedId = skillId;
  state.detailPhase = "loading";
  state.detailError = null;
  state.confirm = null;
  state.extensions = null;
  state.extensionsError = null;
  resetFileViewer();
  paint();
  try {
    const detail = await api.fetchSkill(skillId);
    if (sequence !== detailSequence) return;
    applyDetail(detail);
  } catch (error) {
    if (sequence !== detailSequence) return;
    state.detail = null;
    state.detailPhase = "error";
    state.detailError = normalizeApiError(error, "Le détail du skill est indisponible.");
  }
  paint();
}

function resetFileViewer(): void {
  state.files = [];
  state.filesPhase = "idle";
  state.filesError = null;
  state.filePath = null;
  state.fileContent = null;
  state.filePhase = "idle";
  state.fileError = null;
}

function applyDetail(detail: SkillDetail): void {
  state.detail = detail;
  state.selectedId = detail.id;
  state.detailPhase = "ready";
  state.detailError = null;
  const current = detail.current_revision?.number ?? detail.revisions[0]?.number ?? null;
  selectRevision(current, detail);
}

function revisionOf(detail: SkillDetail, number: number | null): SkillRevision | null {
  if (number === null) return null;
  if (detail.current_revision?.number === number) return detail.current_revision;
  return detail.revisions.find((revision) => revision.number === number) ?? null;
}

function selectRevision(number: number | null, detail: SkillDetail): void {
  state.revisionNumber = number;
  state.filePath = null;
  state.fileContent = null;
  state.filePhase = "idle";
  state.fileError = null;
  const revision = revisionOf(detail, number);
  if (revision && revision.files.length > 0) {
    state.files = revision.files;
    state.filesPhase = "ready";
    state.filesError = null;
  } else if (revision) {
    state.files = [];
    state.filesPhase = "idle";
    state.filesError = null;
    void loadFiles(detail.id, revision.number);
  } else {
    state.files = [];
    state.filesPhase = "idle";
    state.filesError = null;
  }
}

async function loadFiles(skillId: string, revisionNumber: number): Promise<void> {
  state.filesPhase = "loading";
  state.filesError = null;
  paint();
  try {
    state.files = await api.fetchRevisionFiles(skillId, revisionNumber);
    state.filesPhase = "ready";
  } catch (error) {
    state.files = [];
    state.filesPhase = "error";
    state.filesError = normalizeApiError(error, "Le manifeste de la révision est indisponible.");
  }
  paint();
}

async function openFile(path: string): Promise<void> {
  const detail = state.detail;
  const revisionNumber = state.revisionNumber;
  if (!detail || revisionNumber === null) return;
  state.filePath = path;
  state.filePhase = "loading";
  state.fileError = null;
  state.fileContent = null;
  paint();
  try {
    state.fileContent = await api.fetchFileContent(detail.id, revisionNumber, path);
    state.filePhase = "ready";
  } catch (error) {
    state.filePhase = "error";
    state.fileError = normalizeApiError(error, "Le contenu du fichier est indisponible.");
  }
  paint();
}

/** Enveloppe commune des écritures : verrou, jeton CSRF, message d’état, repeinture. */
async function runAction(key: string, scope: FeedbackScope, action: () => Promise<void>): Promise<void> {
  if (state.busy) return;
  state.busy = key;
  state.feedback = null;
  paint();
  try {
    // Le jeton CSRF est posé par le client, au moment exact où une écriture part sur le réseau.
    await action();
  } catch (error) {
    const failure = normalizeApiError(error, "L’action n’a pas abouti.");
    invalidateCsrfOnRefusal(failure);
    setErrorFeedback(failure, scope);
  } finally {
    state.busy = null;
    paint();
  }
}

async function refreshList(): Promise<void> {
  try {
    const result = await api.search(state.query);
    state.skills = result.installed;
    state.phase = "ready";
    state.error = null;
    if (state.query) {
      state.catalog = result.catalog;
      state.catalogFiltered = true;
    }
  } catch (error) {
    state.phase = "error";
    state.error = normalizeApiError(error, "La liste des skills est indisponible.");
  }
}

// --- Sources d’import ---------------------------------------------------------

function currentSource(): SkillSourceInput {
  switch (state.importTab) {
    case "manual":
      return { kind: "manual", files: [{ path: "SKILL.md", content: draft.manualText }] };
    case "archive":
      return { kind: "archive", filename: draft.archiveFilename, content_base64: draft.archiveBase64 };
    case "directory":
      return { kind: "directory", path: draft.directoryPath };
    case "github":
    default:
      return {
        kind: "github",
        repository: draft.githubRepository,
        ref: draft.githubRef,
        path: draft.githubPath,
      };
  }
}

async function readArchive(file: File): Promise<void> {
  if (file.size > ARCHIVE_MAX_BYTES) {
    draft.archiveFilename = "";
    draft.archiveBase64 = "";
    draft.archiveSize = 0;
    setFeedback(
      "error",
      `Archive trop volumineuse (${formatFileSize(file.size)}) : la limite de l’API est de `
        + `${formatFileSize(ARCHIVE_MAX_BYTES)}. Aucun envoi n’a été effectué.`,
      "library",
    );
    paint();
    return;
  }
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    draft.archiveFilename = file.name;
    draft.archiveBase64 = encodeBase64(bytes);
    draft.archiveSize = file.size;
    setFeedback("info", `Archive « ${file.name} » encodée en base64 dans le navigateur : prête à être envoyée.`, "library");
  } catch {
    draft.archiveFilename = "";
    draft.archiveBase64 = "";
    draft.archiveSize = 0;
    setFeedback("error", "L’archive n’a pas pu être lue par le navigateur : aucun envoi n’a été effectué.", "library");
  }
  paint();
}

async function submitImport(): Promise<void> {
  const source = currentSource();
  if (state.importTarget === "revision") {
    const detail = state.detail;
    if (!detail) {
      setFeedback("error", "Sélectionne d’abord un skill pour lui ajouter une révision.", "library");
      return;
    }
    const updated = await api.createRevision(detail.id, { source, note: draft.note });
    applyDetail(updated);
    await refreshList();
    const number = updated.current_revision?.number ?? updated.revisions[0]?.number ?? null;
    setFeedback(
      "success",
      `Révision ${number ?? "?"} créée pour « ${updated.display_name} ». `
        + (updated.requires_approval
          ? "Elle exige une approbation avant activation."
          : "Aucune approbation supplémentaire n’est exigée."),
      "library",
    );
    return;
  }
  const created = await api.importSkill({ source, name: draft.name, note: draft.note });
  applyDetail(created);
  await refreshList();
  setFeedback(
    "success",
    `Skill « ${created.display_name} » importé en brouillon (révision `
      + `${created.current_revision?.number ?? 1}). Rien n’est activé automatiquement.`,
    "library",
  );
}

// --- Rendu : entête et recherche ----------------------------------------------

function introSection(): HTMLElement {
  const intro = el("section", "page-intro");
  let chip: HTMLElement;
  if (state.phase === "loading") chip = statusChip("Chargement", "waiting");
  else if (state.phase === "error") chip = statusChip("Indisponible", "failed");
  else if (state.phase === "ready") {
    chip = statusChip(
      state.skills.length === 1 ? "1 skill installé" : `${state.skills.length} skills installés`,
      state.skills.length ? "active" : "waiting",
    );
  } else chip = statusChip("Non chargé", "unconfigured");

  intro.append(
    chip,
    el("h2", "page-title", "Bibliothèque"),
    el(
      "p",
      "page-description",
      "Skills au format SKILL.md : import, révisions approuvées explicitement et rattachement par projet. "
        + "Le contenu importé est affiché comme donnée non fiable et n’est jamais exécuté par la plateforme.",
    ),
  );
  return intro;
}

function searchSection(): HTMLElement {
  const section = el("section", "content-section");
  section.dataset.module = "skills-search";
  section.append(sectionHeader(
    "Rechercher et importer",
    "La recherche porte sur les skills installés et sur le catalogue de sources vérifiées.",
  ));

  const form = el("form", "skills-search-form");
  const input = textInput(state.query, (value) => { state.query = value; }, "nom, description ou catégorie");
  form.append(labeledField("Recherche", input, "La requête est bornée à 200 caractères avant envoi."));
  const submit = el("button", "button button-primary", "Rechercher");
  submit.type = "submit";
  const actions = el("div", "skills-actions");
  actions.append(
    submit,
    button("Tout afficher", "secondary", () => {
      state.query = "";
      void loadLibrary();
    }, { disabled: !state.query }),
    button("Actualiser", "secondary", () => void loadLibrary(), { disabled: state.phase === "loading" }),
    button(
      state.importOpen ? "Masquer l’import" : "Importer un skill",
      "secondary",
      () => {
        state.importOpen = !state.importOpen;
        paint();
      },
      { pressed: state.importOpen },
    ),
  );
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void loadLibrary();
  });
  section.append(form, feedbackNode("library"));
  if (state.importOpen) section.append(importPanel());
  return section;
}

function importPanel(): HTMLElement {
  const panel = el("section", "skills-import");
  panel.append(sectionHeader(
    "Importer",
    "Quatre sources : SKILL.md saisi, archive, dossier autorisé du serveur, dépôt GitHub épinglé sur un commit.",
  ));

  const tabs = el("div", "skills-tabs");
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "Source d’import");
  for (const tab of IMPORT_TABS) {
    const node = el("button", "skills-tab", tab.label);
    node.type = "button";
    node.id = `skills-import-tab-${tab.id}`;
    node.setAttribute("role", "tab");
    node.setAttribute("aria-selected", String(state.importTab === tab.id));
    node.setAttribute("aria-controls", IMPORT_PANEL_ID);
    node.addEventListener("click", () => {
      state.importTab = tab.id;
      paint();
    });
    tabs.append(node);
  }
  panel.append(tabs);

  const target = el("select", "form-control");
  const optionSkill = el("option", "", "Nouveau skill");
  optionSkill.value = "skill";
  target.append(optionSkill);
  if (state.detail) {
    const optionRevision = el("option", "", `Nouvelle révision de « ${state.detail.display_name} »`);
    optionRevision.value = "revision";
    target.append(optionRevision);
  } else if (state.importTarget === "revision") {
    state.importTarget = "skill";
  }
  target.value = state.importTarget;
  target.addEventListener("change", () => {
    state.importTarget = target.value === "revision" ? "revision" : "skill";
    paint();
  });
  panel.append(labeledField(
    "Destination",
    target,
    "Une révision réutilise le skill sélectionné ; un nouveau skill part en brouillon, jamais actif.",
  ));

  if (state.importTarget === "skill") {
    panel.append(labeledField(
      "Nom (optionnel)",
      textInput(draft.name, (value) => { draft.name = value; }, "slug minuscule, chiffres et tirets"),
      "Laissé vide, le nom est déduit du frontmatter par l’API.",
    ));
  }

  panel.append(sourceFields());

  panel.append(labeledField(
    "Note",
    textInput(draft.note, (value) => { draft.note = value; }, "contexte de l’import"),
    "Conservée avec la révision pour l’audit.",
  ));

  const busy = state.busy === "import";
  const actions = el("div", "skills-actions");
  actions.append(button(
    busy ? "Import en cours…" : state.importTarget === "revision" ? "Créer la révision" : "Importer",
    "primary",
    () => void runAction("import", "library", submitImport),
    { disabled: busy },
  ));
  panel.append(
    actions,
    el(
      "p",
      "form-hint",
      "L’API applique seule les limites (500 fichiers, 20 Mio, 2 Mio par fichier) et le scan : "
        + "un refus est affiché tel quel, sans contournement possible depuis cette page.",
    ),
  );
  return panel;
}

function sourceFields(): HTMLElement {
  const block = el("div", "skills-source-fields");
  block.id = IMPORT_PANEL_ID;
  block.setAttribute("role", "tabpanel");
  block.setAttribute("aria-labelledby", `skills-import-tab-${state.importTab}`);
  if (state.importTab === "manual") {
    block.append(labeledField(
      "Contenu de SKILL.md",
      textArea(draft.manualText, 12, (value) => {
        draft.manualText = value;
        repaintFrontmatterPreview();
      }),
      "Envoyé tel quel : le frontmatter est analysé par l’API, cet aperçu n’est qu’une aide de saisie.",
    ));
    block.append(frontmatterPreview());
    return block;
  }
  if (state.importTab === "archive") {
    const input = el("input", "form-control skills-file-input");
    input.type = "file";
    // Formats réellement acceptés par l’API (`extract_archive`). Les suffixes simples sont
    // conservés car tous les navigateurs ne comparent pas les extensions composées.
    input.accept = ".zip,.tar,.tar.gz,.tgz,.tar.bz2,.tbz2,.tar.xz,.gz,.bz2,.xz";
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (file) void readArchive(file);
    });
    block.append(labeledField(
      "Archive (.zip, .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz)",
      input,
      `Le fichier est encodé en base64 dans le navigateur ; il n’est jamais décompressé côté client. `
        + `Au-delà de ${formatFileSize(ARCHIVE_MAX_BYTES)} l’API refuse l’envoi (413).`,
    ));
    block.append(el(
      "p",
      "skills-note",
      draft.archiveBase64
        ? `Archive prête : ${draft.archiveFilename} (${formatFileSize(draft.archiveSize)}).`
        : "Aucune archive sélectionnée.",
    ));
    return block;
  }
  if (state.importTab === "directory") {
    block.append(labeledField(
      "Chemin du dossier",
      textInput(draft.directoryPath, (value) => { draft.directoryPath = value; }, "chemin absolu côté serveur"),
      `Le dossier doit être sous un répertoire de ${SKILLS_ALLOWED_DIRS_ACTION} ; sinon l’API répond 403 `
        + "« dossier non autorisé ».",
    ));
    return block;
  }
  block.append(labeledField(
    "Dépôt",
    textInput(draft.githubRepository, (value) => { draft.githubRepository = value; }, "owner/repo"),
  ));
  block.append(labeledField(
    "Commit (SHA)",
    textInput(draft.githubRef, (value) => { draft.githubRef = value; }, "40 caractères hexadécimaux"),
    "Une branche ou une étiquette est refusée : seul un commit épinglé garantit ce qui est installé.",
  ));
  block.append(labeledField(
    "Sous-dossier (optionnel)",
    textInput(draft.githubPath, (value) => { draft.githubPath = value; }, "chemin dans le dépôt"),
  ));
  block.append(el(
    "p",
    "skills-note",
    `L’import GitHub exige ${SKILLS_GITHUB_ACTION}=1 côté API ; sinon la réponse est 503 « non configuré » `
      + "et aucun appel réseau n’est tenté.",
  ));
  return block;
}

function frontmatterPreview(): HTMLElement {
  const block = el("div", "skills-frontmatter-preview");
  block.dataset.role = "frontmatter-preview";
  fillFrontmatterPreview(block);
  return block;
}

function fillFrontmatterPreview(block: HTMLElement): void {
  block.replaceChildren();
  if (!draft.manualText.trim()) {
    block.append(el("p", "skills-note", "Aucun contenu saisi : aucun aperçu de frontmatter."));
    return;
  }
  const preview = previewFrontmatter(draft.manualText);
  block.append(el("h4", "skills-subheading", "Aperçu du frontmatter (indicatif)"));
  if (!preview.found) {
    block.append(bulletList(preview.warnings, "skills-list skills-list-warning"));
    return;
  }
  block.append(metaList(preview.fields.map((field) => [field.key, field.value] as [string, string])));
  if (preview.warnings.length) block.append(bulletList(preview.warnings, "skills-list skills-list-warning"));
  block.append(el("p", "skills-note", `Corps du document : ${preview.bodyLength} caractères.`));
}

/** Rafraîchit l’aperçu sans repeindre la page : la saisie en cours garde le focus. */
function repaintFrontmatterPreview(): void {
  const block = mount?.querySelector<HTMLElement>("[data-role='frontmatter-preview']");
  if (block) fillFrontmatterPreview(block);
}

// --- Rendu : liste ------------------------------------------------------------

function listSection(): HTMLElement {
  const section = el("section", "content-section");
  section.dataset.module = "skills-installed";
  section.append(sectionHeader(
    "Skills installés",
    "Un skill importé reste en brouillon : il n’est appliqué à un projet qu’une fois actif et rattaché.",
  ));

  if (state.phase === "loading" || state.phase === "idle") {
    section.append(statePanel("loading", "Chargement des skills", "Interrogation de l’API /skills en cours."));
    return section;
  }
  if (state.phase === "error" && state.error) {
    section.append(errorPanel(state.error, () => void loadLibrary()));
    return section;
  }
  if (state.skills.length === 0) {
    section.append(statePanel(
      "empty",
      "Aucun skill installé",
      state.query
        ? `Aucun skill installé ne correspond à « ${state.query} ». Le catalogue ci-dessous reste consultable.`
        : "Aucun skill n’a encore été importé. Utilise « Importer un skill » ci-dessus.",
    ));
    return section;
  }

  const list = el("div", "item-list");
  for (const skill of state.skills) list.append(skillRow(skill));
  section.append(list);
  return section;
}

function skillRow(skill: SkillSummary): HTMLElement {
  const item = el("article", "list-item skills-row");
  const copy = el("div", "list-item-copy");
  const revision = skill.current_revision_number === null
    ? "aucune révision"
    : `révision ${skill.current_revision_number}`;
  const bindings = skill.binding_count === 1 ? "1 rattachement" : `${skill.binding_count} rattachements`;
  copy.append(
    el("h3", "list-item-title", skill.display_name),
    el("p", "list-item-meta", `${skill.name} · ${skillSourceLabel(skill.source_kind)} · ${revision} · ${bindings}`),
  );
  if (skill.description) copy.append(el("p", "skills-description", skill.description));
  if (skill.origin) copy.append(el("p", "list-item-meta", `Origine : ${skill.origin}`));

  const status = skillStatusBadge(skill.status);
  const kind = skillKindBadge(skill.kind);
  const chips = [statusChip(status.label, status.tone), statusChip(kind.label, kind.tone)];
  if (skill.requires_approval) chips.push(statusChip("Approbation requise", "waiting"));

  const actions = el("div", "skills-actions");
  actions.append(button(
    "Détail",
    "secondary",
    () => void loadDetail(skill.id),
    { pressed: state.selectedId === skill.id },
  ));

  item.append(copy, chipRow(chips), actions);
  return item;
}

// --- Rendu : détail -----------------------------------------------------------

function detailSection(): HTMLElement {
  const section = el("section", "content-section");
  section.dataset.module = "skills-detail";
  section.append(sectionHeader(
    "Détail du skill",
    "Frontmatter, licence, dépendances, findings du scan, fichiers et historique des révisions.",
  ));

  if (state.detailPhase === "loading") {
    section.append(statePanel("loading", "Chargement du détail", "Interrogation de l’API en cours."));
    return section;
  }
  if (state.detailPhase === "error" && state.detailError) {
    const skillId = state.selectedId;
    section.append(errorPanel(state.detailError, skillId ? () => void loadDetail(skillId) : undefined));
    return section;
  }
  const detail = state.detail;
  if (!detail) return section;

  section.append(detailHeader(detail), feedbackNode("detail"), lifecycleActions(detail));
  if (state.confirm) section.append(confirmPanel(detail));
  if (detail.apply_notes.length) {
    section.append(el("h4", "skills-subheading", "Notes d’application"));
    section.append(bulletList(detail.apply_notes));
  }
  const revision = revisionOf(detail, state.revisionNumber);
  section.append(revisionInspector(detail, revision));
  section.append(filesBlock(detail, revision));
  section.append(revisionsBlock(detail));
  section.append(bindingsBlock(detail));
  return section;
}

function detailHeader(detail: SkillDetail): HTMLElement {
  const header = el("div", "skills-detail-header");
  const status = skillStatusBadge(detail.status);
  const kind = skillKindBadge(detail.kind);
  const chips = [statusChip(status.label, status.tone), statusChip(kind.label, kind.tone)];
  if (detail.requires_approval) chips.push(statusChip("Approbation requise", "waiting"));

  header.append(
    el("h3", "skills-detail-title", detail.display_name),
    chipRow(chips),
    el("p", "skills-kind-hint", kind.hint),
  );
  if (detail.description) header.append(el("p", "skills-description", detail.description));
  header.append(metaList([
    ["Nom technique", detail.name],
    ["Catégorie", detail.category || "non renseignée"],
    ["Source", skillSourceLabel(detail.source_kind)],
    ["Origine", detail.origin || "non renseignée"],
    ["Créé le", formatDateTime(detail.created_at)],
    ["Mis à jour le", formatDateTime(detail.updated_at)],
    ["Révoqué le", detail.revoked_at ? formatDateTime(detail.revoked_at) : "—"],
  ]));
  header.append(button("Fermer le détail", "secondary", () => {
    state.selectedId = null;
    state.detail = null;
    state.detailPhase = "idle";
    state.importTarget = "skill";
    resetFileViewer();
    paint();
  }));
  return header;
}

function lifecycleActions(detail: SkillDetail): HTMLElement {
  const actions = el("div", "skills-actions");
  const busy = state.busy !== null;
  actions.append(button(
    "Activer",
    "primary",
    () => void runAction("activate", "detail", async () => {
      applyDetail(await api.activateSkill(detail.id));
      await refreshList();
      setFeedback("success", `Skill « ${detail.display_name} » activé par l’API.`, "detail");
    }),
    { disabled: busy || detail.status === "active" || detail.status === "revoked" },
  ));
  actions.append(button(
    "Désactiver",
    "secondary",
    () => void runAction("disable", "detail", async () => {
      applyDetail(await api.disableSkill(detail.id));
      await refreshList();
      setFeedback("success", `Skill « ${detail.display_name} » désactivé par l’API.`, "detail");
    }),
    { disabled: busy || detail.status !== "active" },
  ));
  actions.append(button(
    "Révoquer",
    "secondary",
    () => {
      state.confirm = { kind: "revoke", revisionNumber: null };
      paint();
    },
    { disabled: busy || detail.status === "revoked" },
  ));
  if (detail.status === "revoked") {
    actions.append(el("p", "form-hint", "Ce skill est révoqué : il ne figure plus dans les extensions résolues."));
  } else if (detail.requires_approval) {
    actions.append(el(
      "p",
      "form-hint",
      "L’activation est refusée (409) tant que la révision courante n’est pas approuvée ci-dessous.",
    ));
  }
  return actions;
}

function confirmPanel(detail: SkillDetail): HTMLElement {
  const confirm = state.confirm;
  const panel = el("section", "skills-confirm");
  if (!confirm) return panel;

  if (confirm.kind === "revoke") {
    panel.append(
      el("h4", "skills-subheading", `Révoquer « ${detail.display_name} » ?`),
      el(
        "p",
        "skills-note",
        "La révocation retire le skill des extensions résolues des projets (seuls les skills actifs y figurent). "
          + "Le motif est enregistré dans l’audit.",
      ),
      labeledField(
        "Motif (obligatoire)",
        textInput(state.revokeReason, (value) => { state.revokeReason = value; }),
      ),
    );
    const actions = el("div", "skills-actions");
    actions.append(
      button("Confirmer la révocation", "primary", () => void runAction("revoke", "detail", async () => {
        applyDetail(await api.revokeSkill(detail.id, state.revokeReason));
        await refreshList();
        state.revokeReason = "";
        state.confirm = null;
        setFeedback("success", `Skill « ${detail.display_name} » révoqué par l’API.`, "detail");
      }), { disabled: state.busy !== null }),
      button("Annuler", "secondary", () => {
        state.confirm = null;
        paint();
      }),
    );
    panel.append(actions);
    return panel;
  }

  const number = confirm.revisionNumber;
  panel.append(
    el("h4", "skills-subheading", `Restaurer la révision ${number ?? "?"} ?`),
    el(
      "p",
      "skills-note",
      "La restauration crée une nouvelle révision copiant ces fichiers ; si l’empreinte n’a jamais été approuvée, "
        + "une approbation sera de nouveau exigée avant activation.",
    ),
    labeledField("Note (optionnelle)", textInput(state.rollbackNote, (value) => { state.rollbackNote = value; })),
  );
  const actions = el("div", "skills-actions");
  actions.append(
    button("Confirmer la restauration", "primary", () => void runAction("rollback", "detail", async () => {
      if (number === null) return;
      applyDetail(await api.rollbackSkill(detail.id, number, state.rollbackNote));
      await refreshList();
      state.rollbackNote = "";
      state.confirm = null;
      setFeedback("success", `Révision ${number} restaurée : une nouvelle révision a été créée par l’API.`, "detail");
    }), { disabled: state.busy !== null }),
    button("Annuler", "secondary", () => {
      state.confirm = null;
      paint();
    }),
  );
  panel.append(actions);
  return panel;
}

function revisionInspector(detail: SkillDetail, revision: SkillRevision | null): HTMLElement {
  const block = el("section", "skills-block");
  block.append(el("h4", "skills-subheading", "Révision consultée"));
  if (detail.revisions.length > 1) {
    const select = el("select", "form-control");
    for (const candidate of detail.revisions) {
      const option = el("option", "", `Révision ${candidate.number}${candidate.approved ? " (approuvée)" : ""}`);
      option.value = String(candidate.number);
      select.append(option);
    }
    if (state.revisionNumber !== null) select.value = String(state.revisionNumber);
    select.addEventListener("change", () => {
      selectRevision(Number(select.value), detail);
      paint();
    });
    block.append(labeledField("Révision", select));
  }
  if (!revision) {
    block.append(statePanel(
      "empty",
      "Aucune révision",
      "L’API n’expose aucune révision pour ce skill : il n’y a rien à inspecter.",
    ));
    return block;
  }

  block.append(metaList([
    ["Numéro", String(revision.number)],
    ["Empreinte", revision.fingerprint],
    ["Nature", skillKindBadge(revision.kind).label],
    ["Licence", revision.license ?? "non déclarée"],
    ["Source", revision.source_ref || "non renseignée"],
    ["Note", revision.note || "—"],
    ["Créée le", formatDateTime(revision.created_at)],
    ["Approuvée", revision.approved
      ? `oui${revision.approved_at ? ` le ${formatDateTime(revision.approved_at)}` : ""}`
      : revision.requires_approval ? "non (approbation requise)" : "non (approbation non requise)"],
    ["Remplacée le", revision.superseded_at ? formatDateTime(revision.superseded_at) : "—"],
  ]));

  block.append(el("h4", "skills-subheading", "Frontmatter (donnée non fiable)"));
  const entries = Object.entries(revision.frontmatter);
  if (entries.length === 0) block.append(el("p", "skills-note", "Frontmatter vide ou non exposé par l’API."));
  else block.append(metaList(entries.map(([key, value]) => [key, frontmatterValue(value)] as [string, string])));

  block.append(el("h4", "skills-subheading", "Dépendances déclarées"));
  const dependencies = revision.dependencies;
  const envNames = dependencies.required_environment_variables.map((entry) => {
    const name = entry.name;
    return typeof name === "string" && name ? name : frontmatterValue(entry);
  });
  block.append(metaList([
    ["Variables d’environnement", envNames.length ? envNames.join(", ") : "aucune"],
    ["Toolsets", dependencies.requires_toolsets.length ? dependencies.requires_toolsets.join(", ") : "aucun"],
    ["Outils", dependencies.requires_tools.length ? dependencies.requires_tools.join(", ") : "aucun"],
    ["Scripts", dependencies.scripts.length ? dependencies.scripts.join(", ") : "aucun"],
    ["Indicateurs réseau", dependencies.network_indicators.length
      ? dependencies.network_indicators.join(", ")
      : "aucun"],
    ["Plateformes", dependencies.platforms.length ? dependencies.platforms.join(", ") : "non précisées"],
  ]));

  block.append(el("h4", "skills-subheading", "Findings du scan (indicatifs)"));
  block.append(el(
    "p",
    "skills-note",
    "Le scan est une heuristique indicative, non certifiante : l’absence de finding ne prouve pas l’innocuité.",
  ));
  if (revision.scan.length === 0) {
    block.append(el("p", "skills-note", "Aucun finding renvoyé par l’API pour cette révision."));
  } else {
    const list = el("ul", "skills-findings");
    for (const finding of revision.scan) {
      const badge = findingLevelBadge(finding.level);
      const item = el("li", "skills-finding");
      item.append(statusChip(badge.label, badge.tone));
      const copy = el("div", "skills-finding-copy");
      copy.append(el("p", "skills-finding-message", finding.message));
      copy.append(el("p", "skills-finding-meta", `${finding.code}${finding.path ? ` · ${finding.path}` : ""}`));
      item.append(copy);
      list.append(item);
    }
    block.append(list);
  }

  block.append(el("h4", "skills-subheading", "Comparatif de la révision"));
  block.append(bulletList(summarizeRevisionDiff(revision.change_summary)));
  return block;
}

function filesBlock(detail: SkillDetail, revision: SkillRevision | null): HTMLElement {
  const block = el("section", "skills-block");
  block.append(el("h4", "skills-subheading", "Fichiers de la révision"));
  if (!revision) {
    block.append(el("p", "skills-note", "Aucune révision sélectionnée : aucun fichier à lister."));
    return block;
  }
  if (state.filesPhase === "loading") {
    block.append(statePanel("loading", "Chargement du manifeste", "Interrogation de l’API en cours."));
    return block;
  }
  if (state.filesPhase === "error" && state.filesError) {
    block.append(errorPanel(state.filesError, () => void loadFiles(detail.id, revision.number)));
    return block;
  }
  if (state.files.length === 0) {
    block.append(statePanel(
      "empty",
      "Manifeste vide",
      "L’API ne renvoie aucun fichier pour cette révision ; aucun contenu n’est reconstitué ici.",
    ));
    return block;
  }

  const layout = el("div", "skills-files");
  layout.append(fileTree(buildSkillFileTree(state.files)));
  layout.append(fileViewer());
  block.append(layout);
  return block;
}

function fileTree(nodes: SkillTreeNode[]): HTMLElement {
  const list = el("ul", "skills-tree");
  for (const node of nodes) {
    const item = el("li", "skills-tree-item");
    item.dataset.kind = node.kind;
    if (node.file) {
      const file = node.file;
      const trigger = el("button", "skills-tree-file", node.name);
      trigger.type = "button";
      trigger.setAttribute("aria-pressed", String(state.filePath === node.path));
      trigger.append(el(
        "span",
        "skills-tree-meta",
        `${formatFileSize(file.size)} · ${file.text ? "texte" : "binaire"}`,
      ));
      trigger.addEventListener("click", () => void openFile(node.path));
      item.append(trigger);
    } else {
      item.append(el("span", "skills-tree-directory", `${node.name}/`));
    }
    if (node.children.length) item.append(fileTree(node.children));
    list.append(item);
  }
  return list;
}

function fileViewer(): HTMLElement {
  const viewer = el("div", "skills-viewer");
  if (!state.filePath) {
    viewer.append(el("p", "skills-note", "Sélectionne un fichier pour afficher son contenu en texte brut."));
    return viewer;
  }
  viewer.append(el("h5", "skills-viewer-title", state.filePath));
  if (state.filePhase === "loading") {
    viewer.append(statePanel("loading", "Lecture du fichier", "Interrogation de l’API en cours."));
    return viewer;
  }
  if (state.filePhase === "error" && state.fileError) {
    const path = state.filePath;
    viewer.append(errorPanel(state.fileError, () => void openFile(path)));
    return viewer;
  }
  const content = state.fileContent;
  if (!content) return viewer;

  viewer.append(el(
    "p",
    "skills-viewer-meta",
    `${formatFileSize(content.size)} · sha256 ${content.sha256}${content.truncated ? " · contenu tronqué" : ""}`,
  ));
  if (!content.text || content.content === null) {
    viewer.append(statePanel(
      "empty",
      "Fichier binaire",
      "Le contenu n’est pas affiché : seule l’empreinte et la taille sont exposées.",
    ));
    return viewer;
  }
  if (content.truncated) {
    viewer.append(el(
      "p",
      "skills-note",
      "Contenu tronqué par l’API : la fin du fichier n’est pas affichée.",
    ));
  }
  const pre = el("pre", "skills-file-content");
  pre.tabIndex = 0;
  pre.textContent = content.content;
  viewer.append(pre);
  return viewer;
}

function revisionsBlock(detail: SkillDetail): HTMLElement {
  const block = el("section", "skills-block");
  block.append(el("h4", "skills-subheading", "Révisions"));
  if (detail.revisions.length === 0) {
    block.append(statePanel("empty", "Aucune révision", "L’API n’expose aucune révision pour ce skill."));
    return block;
  }
  const list = el("div", "item-list");
  for (const revision of detail.revisions) {
    const item = el("article", "list-item skills-revision");
    const copy = el("div", "list-item-copy");
    copy.append(
      el("h5", "list-item-title", `Révision ${revision.number}`),
      el("p", "list-item-meta", `${formatDateTime(revision.created_at)} · ${revision.source_ref || "source inconnue"}`),
    );
    if (revision.note) copy.append(el("p", "skills-description", revision.note));
    copy.append(bulletList(summarizeRevisionDiff(revision.change_summary), "skills-list skills-diff"));

    const chips: HTMLElement[] = [];
    if (detail.current_revision?.number === revision.number) chips.push(statusChip("Courante", "in_progress"));
    chips.push(revision.approved
      ? statusChip("Approuvée", "active")
      : statusChip(revision.requires_approval ? "Approbation requise" : "Non approuvée", "waiting"));

    const actions = el("div", "skills-actions");
    const busy = state.busy !== null;
    if (revision.requires_approval && !revision.approved) {
      copy.append(labeledField(
        `Commentaire d’approbation (révision ${revision.number})`,
        textInput(state.approvalComment, (value) => { state.approvalComment = value; }),
        "Enregistré avec l’approbation ; l’approbation porte sur l’empreinte affichée ci-dessus.",
      ));
      actions.append(button(
        `Approuver la révision ${revision.number}`,
        "primary",
        () => void runAction(`approve-${revision.number}`, "detail", async () => {
          applyDetail(await api.approveRevision(detail.id, revision.number, state.approvalComment));
          await refreshList();
          state.approvalComment = "";
          setFeedback("success", `Révision ${revision.number} approuvée : l’activation est désormais possible.`, "detail");
        }),
        { disabled: busy },
      ));
    }
    if (detail.current_revision?.number !== revision.number) {
      actions.append(button(
        "Restaurer",
        "secondary",
        () => {
          state.confirm = { kind: "rollback", revisionNumber: revision.number };
          paint();
        },
        { disabled: busy },
      ));
    }
    actions.append(button(
      "Inspecter",
      "secondary",
      () => {
        selectRevision(revision.number, detail);
        paint();
      },
      { pressed: state.revisionNumber === revision.number },
    ));

    item.append(copy, chipRow(chips), actions);
    list.append(item);
  }
  block.append(list);
  return block;
}

function bindingsBlock(detail: SkillDetail): HTMLElement {
  const block = el("section", "skills-block");
  block.append(el("h4", "skills-subheading", "Rattachements par projet"));
  block.append(el(
    "p",
    "skills-note",
    "Un rattachement n’est appliqué que si le skill est actif : les extensions résolues d’un projet ne retiennent "
      + "que les skills actifs et non révoqués.",
  ));

  const active = detail.bindings.filter((binding) => binding.revoked_at === null);
  if (active.length === 0) {
    block.append(statePanel("empty", "Aucun rattachement", "Ce skill n’est rattaché à aucun projet."));
  } else {
    const list = el("div", "item-list");
    for (const binding of active) list.append(bindingRow(detail, binding));
    block.append(list);
  }

  block.append(bindingForm(detail));
  block.append(extensionsBlock());
  return block;
}

function bindingRow(detail: SkillDetail, binding: SkillBinding): HTMLElement {
  const item = el("article", "list-item");
  const copy = el("div", "list-item-copy");
  copy.append(
    el("h5", "list-item-title", projectLabel(binding.project_id)),
    el("p", "list-item-meta", `Révision ${binding.revision_number} · créé le ${formatDateTime(binding.created_at)}`),
  );
  const actions = el("div", "skills-actions");
  actions.append(button(
    "Révoquer le rattachement",
    "secondary",
    () => void runAction(`binding-${binding.id}`, "detail", async () => {
      await api.revokeBinding(binding.id);
      applyDetail(await api.fetchSkill(detail.id));
      await refreshList();
      setFeedback("success", `Rattachement au projet ${binding.project_id} révoqué.`, "detail");
    }),
    { disabled: state.busy !== null },
  ));
  item.append(copy, chipRow([statusChip(binding.enabled ? "Actif" : "Désactivé", binding.enabled ? "active" : "blocked")]), actions);
  return item;
}

function bindingForm(detail: SkillDetail): HTMLElement {
  const form = el("div", "skills-binding-form");
  if (state.projects.length > 0) {
    const select = el("select", "form-control");
    const empty = el("option", "", "Choisir un projet");
    empty.value = "";
    select.append(empty);
    for (const project of state.projects) {
      const option = el("option", "", `${project.name} (${project.id})`);
      option.value = project.id;
      select.append(option);
    }
    select.value = state.bindingProjectId;
    select.addEventListener("change", () => { state.bindingProjectId = select.value; });
    form.append(labeledField("Projet", select, "Le rôle membre du projet est exigé par l’API."));
  } else {
    const hint = state.projectsError
      ? `Liste des projets indisponible (${errorMessage(state.projectsError)}) : saisis l’identifiant du projet.`
      : "Aucun projet listé : saisis l’identifiant du projet.";
    form.append(labeledField(
      "Identifiant de projet",
      textInput(state.bindingProjectId, (value) => { state.bindingProjectId = value; }),
      hint,
    ));
  }

  const actions = el("div", "skills-actions");
  actions.append(button(
    "Rattacher au projet",
    "primary",
    () => void runAction("binding-create", "detail", async () => {
      const binding = await api.createBinding(detail.id, state.bindingProjectId);
      applyDetail(await api.fetchSkill(detail.id));
      await refreshList();
      setFeedback("success", `Skill rattaché au projet ${projectLabel(binding.project_id)}.`, "detail");
    }),
    { disabled: state.busy !== null || detail.status !== "active" },
  ));
  actions.append(button(
    "Vérifier les extensions du projet",
    "secondary",
    () => void runAction("extensions", "detail", async () => {
      const projectId = state.bindingProjectId.trim();
      if (!projectId) {
        setFeedback("error", "Choisis d’abord un projet pour lire ses extensions résolues.", "detail");
        return;
      }
      try {
        state.extensions = await api.fetchProjectExtensions(projectId);
        state.extensionsError = null;
      } catch (error) {
        state.extensions = null;
        state.extensionsError = normalizeApiError(error, "Les extensions du projet sont indisponibles.");
        throw state.extensionsError;
      }
    }),
    { disabled: state.busy !== null },
  ));
  if (detail.status !== "active") {
    actions.append(el(
      "p",
      "form-hint",
      "Le rattachement est refusé (409) tant que le skill n’est pas actif.",
    ));
  }
  form.append(actions);
  return form;
}

function extensionsBlock(): HTMLElement {
  const block = el("div", "skills-extensions");
  if (state.extensionsError) {
    block.append(errorPanel(state.extensionsError));
    return block;
  }
  const extensions = state.extensions;
  if (!extensions) return block;

  block.append(el("h5", "skills-subheading", `Extensions résolues du projet ${projectLabel(extensions.project_id)}`));
  block.append(el("p", "skills-note", `Résolues le ${formatDateTime(extensions.resolved_at)} par l’API.`));
  const skills = extensions.skills.map((entry) => `${entry.name} — révision ${entry.revision_number}`);
  const servers = extensions.mcp.map((entry) => `${entry.name} — révision ${entry.revision_number}`);
  block.append(el("p", "skills-note", "Skills appliqués :"));
  block.append(skills.length ? bulletList(skills) : el("p", "skills-note", "aucun"));
  block.append(el("p", "skills-note", "Serveurs MCP appliqués :"));
  block.append(servers.length ? bulletList(servers) : el("p", "skills-note", "aucun"));
  return block;
}

// --- Rendu : catalogue --------------------------------------------------------

function catalogSection(): HTMLElement {
  const section = el("section", "content-section");
  section.dataset.module = "skills-catalog";
  section.append(sectionHeader(
    "Catalogue de sources",
    "Dépôts cités par la documentation Hermes : la plateforme n’audite pas leur contenu.",
  ));

  if (state.phase === "loading") {
    section.append(statePanel("loading", "Chargement du catalogue", "Interrogation de l’API en cours."));
    return section;
  }
  if (state.catalogError) {
    section.append(errorPanel(state.catalogError, () => void loadLibrary()));
    return section;
  }
  if (state.catalog.length === 0) {
    section.append(statePanel(
      "empty",
      "Catalogue vide",
      state.catalogFiltered
        ? `Aucune entrée du catalogue ne correspond à « ${state.query} ».`
        : "L’API ne renvoie aucune entrée de catalogue.",
    ));
    return section;
  }
  if (state.catalogFiltered) {
    section.append(el("p", "skills-note", `Entrées filtrées par la recherche « ${state.query} ».`));
  }

  const list = el("div", "item-list");
  for (const entry of state.catalog) list.append(catalogRow(entry));
  section.append(list);
  return section;
}

function catalogRow(entry: SkillCatalogEntry): HTMLElement {
  const item = el("article", "list-item");
  const copy = el("div", "list-item-copy");
  copy.append(
    el("h3", "list-item-title", entry.display_name),
    el("p", "list-item-meta", `${entry.repository}${entry.path ? ` · ${entry.path}` : ""}`),
    el("p", "skills-description", entry.description),
  );
  copy.append(metaList([
    ["Licence", entry.license ?? "non déclarée"],
    ["Vérification", entry.verification],
    ["Vérifié le", entry.verified_at],
    ["Note", entry.note],
  ]));
  if (entry.documentation_url.startsWith("https://")) {
    const link = el("a", "text-link", entry.documentation_url);
    link.href = entry.documentation_url;
    link.target = "_blank";
    link.rel = "noreferrer noopener";
    copy.append(link);
  } else if (entry.documentation_url) {
    copy.append(el("p", "skills-note", `Documentation : ${entry.documentation_url}`));
  }

  const actions = el("div", "skills-actions");
  actions.append(button("Pré-remplir l’import GitHub", "secondary", () => {
    state.importOpen = true;
    state.importTab = "github";
    state.importTarget = "skill";
    draft.githubRepository = entry.repository;
    draft.githubPath = entry.path;
    setFeedback(
      "info",
      `Import GitHub pré-rempli avec ${entry.repository}. Renseigne le SHA du commit à épingler : `
        + "aucune installation n’est faite sans commit explicite.",
      "library",
    );
    paint();
  }, { disabled: state.busy !== null }));

  item.append(copy, chipRow([statusChip("Non audité", "waiting")]), actions);
  return item;
}

// --- Assemblage ----------------------------------------------------------------

function paint(): void {
  if (!mount) return;
  mount.replaceChildren();
  mount.append(introSection(), searchSection(), listSection());
  if (state.selectedId) mount.append(detailSection());
  mount.append(catalogSection());
}

/**
 * Rendu de la route « Bibliothèque ». L’état est conservé entre deux rendus du shell
 * (navigation, actualisation globale) : seule une première visite ou un échec
 * précédent relance le chargement.
 *
 * `sharedHttp` est le client HTTP de l’appelant. Le passer est **la** façon correcte de câbler
 * ce module : le jeton CSRF de la session est alors partagé, alors qu’un client séparé
 * doit relire `/auth/session`, ce qui fait tourner le jeton côté serveur et invalide celui
 * des autres écrans. Sans argument, le module retombe sur son propre client (compatibilité)
 * et ne demande la session qu’au moment d’une écriture.
 */
export function renderSkillsLibrary(container: HTMLElement, sharedHttp?: WorkspaceHttpClient): void {
  useHttpClient(sharedHttp);
  mount = el("div", "skills-library");
  container.append(mount);
  paint();
  if (state.phase === "idle" || state.phase === "error") void loadLibrary();
}

/**
 * Efface tout ce que ce module retient d'un compte : skills lus, catalogue, projets,
 * détail, fichiers, brouillon d'import, client HTTP adopté et jeton CSRF.
 *
 * Le shell doit l'appeler en même temps que ses propres purges (déconnexion et
 * connexion). Sans cela, la route « Bibliothèque » repeindrait les skills et les
 * projets du compte précédent jusqu'au rechargement de la page. Les compteurs de
 * séquence sont incrémentés pour qu'une réponse partie avant la purge soit ignorée.
 */
export function resetSkillsUiState(): void {
  librarySequence += 1;
  detailSequence += 1;
  Object.assign(state, initialLibraryState());
  Object.assign(draft, initialDraft());
  mount = null;
  useHttpClient(undefined);
  fallbackHttp.setCsrfToken(null);
  csrfReady = false;
}
