/**
 * Route « Bibliothèque » (spec Lot E §10) : deux onglets, `Skills` et `Livrables`.
 *
 * L’onglet `Skills` délègue intégralement à `renderSkillsLibrary` (Lot D) — ce module
 * n’en modifie ni le code ni l’état — et `resetLibraryUiState()` relaie la purge à
 * `resetSkillsUiState()`. L’onglet `Livrables` liste les artefacts d’un projet et d’une
 * tentative, avec recherche, aperçu à la demande, téléchargement explicite, provenance,
 * taille et empreinte.
 *
 * Trois règles gouvernent ce module :
 * 1. **client HTTP fourni par le shell** (règle du Lot D) : aucune lecture de
 *    `/auth/session`, aucun client créé quand un client est passé ;
 * 2. **contenu non fiable** : nom de fichier, type, provenance et empreinte viennent de
 *    l’API et sont insérés par `textContent` / `el()`, jamais par `innerHTML` ; aucun
 *    contenu d’artefact n’est rendu dans l’origine de la plateforme — `text/html`,
 *    `image/svg+xml` et les archives se téléchargent, avec leur avertissement ;
 * 3. **aucun faux succès** : chargement, vide, hors ligne, accès refusé, réponse
 *    inexploitable et signature de liens non configurée ont chacun leur panneau, et le
 *    dernier nomme la variable à définir côté serveur.
 *
 * L’onglet actif est mémorisé dans l’URL (`?onglet=livrables`) pour qu’un lien profond
 * fonctionne. Seule cette valeur, prise dans un ensemble fermé, y est écrite : aucune
 * donnée personnelle, aucun identifiant.
 */

import type { ArtifactLink, ArtifactSummary, Project } from "@acp/contracts";

import "./library.css";
import {
  ARTIFACT_PREVIEW_ORIGIN_ACTION,
  ArtifactsApiClient,
  artifactSourceLabel,
  artifactStreamKindLabel,
  describeArtifactPreview,
  describeArtifactsError,
  formatArtifactSize,
  isSeparateArtifactPreviewUrl,
  shortChecksum,
} from "./artifacts-api";
import { modelPreviewNode } from "./model-preview";
import { renderSkillsLibrary, resetSkillsUiState } from "./skills-ui";
import {
  el,
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
  type MissionSummary,
} from "./workspace-api";

export type LibraryTab = "skills" | "deliverables";

/** Paramètre d’URL portant l’onglet actif, en français comme le reste de l’interface. */
export const LIBRARY_TAB_PARAM = "onglet";

/** Valeurs autorisées dans l’URL : ensemble fermé, jamais une donnée saisie. */
export const LIBRARY_TAB_VALUES: Record<LibraryTab, string> = {
  skills: "skills",
  deliverables: "livrables",
};

const TABS: readonly { id: LibraryTab; label: string }[] = [
  { id: "skills", label: "Skills" },
  { id: "deliverables", label: "Livrables" },
];

const PANEL_ID = "library-tabpanel";

const STREAM_KIND_FILTERS: readonly { value: string; label: string }[] = [
  { value: "", label: "Tous les types" },
  { value: "screenshot", label: "Capture d’écran" },
  { value: "video", label: "Vidéo" },
  { value: "trace", label: "Trace" },
  { value: "report", label: "Rapport" },
  { value: "file", label: "Fichier" },
];

const PREVIEW_ORIGIN_NOTE = "Aperçu chargé depuis une origine distincte de l’application";

const SESSION_DOWNLOAD_NOTE = "Ce lien n’utilise pas de signature : il ne fonctionne que si le "
  + "navigateur transmet le cookie de session à l’origine de l’API.";

export interface LibraryOption {
  id: string;
  label: string;
}

/** Forme minimale attendue d’une mission pour nommer ses tentatives (`MissionSummary` la satisfait). */
export interface LibraryRunSource {
  id: string;
  project_id: string;
  title: string;
  current_run: { id: string; attempt_number: number };
}

// --- Fonctions pures ------------------------------------------------------------

function searchParams(search: string): URLSearchParams {
  return new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
}

/** Onglet présent dans l’URL, ou `null` si le paramètre est absent (choix non exprimé). */
export function libraryTabInSearch(search: string): LibraryTab | null {
  const raw = searchParams(search).get(LIBRARY_TAB_PARAM);
  if (raw === null) return null;
  return raw.trim().toLowerCase() === LIBRARY_TAB_VALUES.deliverables ? "deliverables" : "skills";
}

/** Onglet demandé par l’URL ; toute valeur inconnue retombe sur `Skills`. */
export function libraryTabFromSearch(search: string): LibraryTab {
  return libraryTabInSearch(search) ?? "skills";
}

/**
 * Chaîne de requête portant l’onglet demandé, les autres paramètres inchangés.
 * L’onglet par défaut n’est pas écrit : un lien reste propre tant qu’on ne l’a pas quitté.
 */
export function librarySearchWithTab(search: string, tab: LibraryTab): string {
  const params = searchParams(search);
  params.delete(LIBRARY_TAB_PARAM);
  if (tab === "deliverables") params.set(LIBRARY_TAB_PARAM, LIBRARY_TAB_VALUES.deliverables);
  const query = params.toString();
  return query ? `?${query}` : "";
}

function normalizeSearchText(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

/**
 * Recherche locale sur la page déjà chargée : tous les termes doivent être présents.
 * Elle complète les filtres serveur (projet, tentative, type) sans jamais les remplacer.
 */
export function filterArtifacts(
  items: readonly ArtifactSummary[],
  query: string,
): ArtifactSummary[] {
  const terms = normalizeSearchText(query).split(/\s+/).filter(Boolean);
  if (!terms.length) return [...items];
  return items.filter((item) => {
    const haystack = normalizeSearchText([
      item.original_name,
      item.kind,
      item.stream_kind,
      artifactStreamKindLabel(item.stream_kind),
      item.source,
      item.content_type,
      item.checksum ?? "",
      item.id,
      item.task_run_id,
    ].join(" "));
    return terms.every((term) => haystack.includes(term));
  });
}

function abbreviate(value: string, max = 12): string {
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

/**
 * Projets proposés au filtre : ceux que la session peut lire, puis ceux qui n’apparaissent
 * que dans les livrables déjà chargés — ces derniers sont nommés par leur identifiant,
 * jamais inventés.
 */
export function projectOptions(
  projects: readonly { id: string; name: string }[],
  artifacts: readonly ArtifactSummary[],
): LibraryOption[] {
  const known = new Map<string, LibraryOption>();
  for (const project of projects) known.set(project.id, { id: project.id, label: project.name });
  const options = [...known.values()].sort((a, b) => a.label.localeCompare(b.label, "fr"));
  const extra = [...new Set(artifacts.map((item) => item.project_id))]
    .filter((id) => id && !known.has(id))
    .sort((a, b) => a.localeCompare(b, "fr"))
    .map((id) => ({ id, label: `Projet ${abbreviate(id)}` }));
  return [...options, ...extra];
}

/**
 * Tentatives proposées au filtre. Les missions fournissent le libellé lisible de leur
 * tentative courante ; les tentatives antérieures apparaissent par leur identifiant dès
 * qu’un livrable y renvoie, pour qu’aucune archive ne devienne inaccessible.
 */
export function runOptions(
  missions: readonly LibraryRunSource[],
  artifacts: readonly ArtifactSummary[],
  projectId: string,
): LibraryOption[] {
  const scoped = missions.filter((mission) => !projectId || mission.project_id === projectId);
  const known = new Map<string, LibraryOption>();
  for (const mission of scoped) {
    known.set(mission.current_run.id, {
      id: mission.current_run.id,
      label: `${mission.title} · tentative ${mission.current_run.attempt_number}`,
    });
  }
  const options = [...known.values()].sort((a, b) => a.label.localeCompare(b.label, "fr"));
  const extra = [...new Set(artifacts.map((item) => item.task_run_id))]
    .filter((id) => id && !known.has(id))
    .sort((a, b) => a.localeCompare(b, "fr"))
    .map((id) => ({ id, label: `Tentative ${abbreviate(id)}` }));
  return [...options, ...extra];
}

// --- État -------------------------------------------------------------------------

interface DeliverablesState {
  phase: "idle" | "loading" | "ready" | "error";
  items: ArtifactSummary[];
  nextCursor: string | null;
  error: WorkspaceApiError | null;
  query: string;
  projectId: string;
  taskRunId: string;
  streamKind: string;
  projects: { id: string; name: string }[];
  missions: LibraryRunSource[];
  referencesLoaded: boolean;
  referencesFailed: boolean;
  loadingMore: boolean;
  signingUnavailable: boolean;
  signingAction: string;
  signingMessage: string;
}

interface RowState {
  previewLink: ArtifactLink | null;
  downloadLink: ArtifactLink | null;
  preview: boolean;
  download: boolean;
  busy: boolean;
  error: string;
}

function initialDeliverables(): DeliverablesState {
  return {
    phase: "idle",
    items: [],
    nextCursor: null,
    error: null,
    query: "",
    projectId: "",
    taskRunId: "",
    streamKind: "",
    projects: [],
    missions: [],
    referencesLoaded: false,
    referencesFailed: false,
    loadingMore: false,
    signingUnavailable: false,
    signingAction: "",
    signingMessage: "",
  };
}

let tab: LibraryTab = "skills";
let state: DeliverablesState = initialDeliverables();
let rows = new Map<string, RowState>();
let loadSequence = 0;
let linkExpiryTimer: ReturnType<typeof globalThis.setTimeout> | null = null;

let mount: HTMLElement | null = null;
let resultsMount: HTMLElement | null = null;

/**
 * Client de repli : il permet aux lectures de fonctionner si personne ne partage de
 * client, mais il ne porte **aucun** jeton CSRF — ce module ne lit jamais
 * `/auth/session`, qui ferait tourner le jeton unique du shell. Sans client partagé, la
 * création d’un lien signé est donc refusée par le serveur et affichée comme telle,
 * plutôt que contournée en silence.
 */
const fallbackHttp = new WorkspaceHttpClient();
let http: WorkspaceHttpClient = fallbackHttp;
let api = new ArtifactsApiClient({ http });
let workspaceApi = new WorkspaceApiClient({ http });

/** Adopte le client HTTP du shell ; changer de client recrée les clients dérivés. */
function useHttpClient(client: WorkspaceHttpClient | undefined): void {
  const next = client ?? fallbackHttp;
  if (next === http) return;
  http = next;
  api = new ArtifactsApiClient({ http });
  workspaceApi = new WorkspaceApiClient({ http });
}

/** Un lien signé expire vite : on n’en réutilise un que s’il reste franchement valable. */
const LINK_REUSE_MARGIN_MS = 15_000;
/** Plafond natif d'un `setTimeout` navigateur ; au-delà, on replanifie par tranche. */
const LINK_EXPIRY_TIMER_MAX_MS = 2_147_483_647;

function isLinkUsable(link: ArtifactLink | null): link is ArtifactLink {
  if (!link) return false;
  const expiry = Date.parse(link.expires_at);
  return Number.isFinite(expiry) && expiry - Date.now() > LINK_REUSE_MARGIN_MS;
}

function rowState(artifactId: string): RowState {
  const existing = rows.get(artifactId);
  if (existing) return existing;
  const created: RowState = {
    previewLink: null,
    downloadLink: null,
    preview: false,
    download: false,
    busy: false,
    error: "",
  };
  rows.set(artifactId, created);
  return created;
}

function expireUnusableRowLinks(row: RowState): void {
  if (row.previewLink && !isLinkUsable(row.previewLink)) row.previewLink = null;
  if (row.downloadLink && !isLinkUsable(row.downloadLink)) row.downloadLink = null;
}

function clearLinkExpiryTimer(): void {
  if (linkExpiryTimer === null) return;
  globalThis.clearTimeout(linkExpiryTimer);
  linkExpiryTimer = null;
}

/**
 * Un seul timer couvre toutes les lignes. Chaque rendu le remplace par l'échéance
 * utile la plus proche ; son callback repeint uniquement les résultats déjà chargés.
 */
function scheduleLinkExpiryInvalidation(): void {
  clearLinkExpiryTimer();
  if (tab !== "deliverables" || !resultsMount) return;

  let nextInvalidationAt = Number.POSITIVE_INFINITY;
  for (const row of rows.values()) {
    for (const link of [row.previewLink, row.downloadLink]) {
      if (!link) continue;
      const expiry = Date.parse(link.expires_at);
      if (Number.isFinite(expiry)) {
        nextInvalidationAt = Math.min(
          nextInvalidationAt,
          expiry - LINK_REUSE_MARGIN_MS,
        );
      }
    }
  }
  if (!Number.isFinite(nextInvalidationAt)) return;

  const delay = Math.min(
    LINK_EXPIRY_TIMER_MAX_MS,
    Math.max(1, nextInvalidationAt - Date.now() + 1),
  );
  linkExpiryTimer = globalThis.setTimeout(() => {
    linkExpiryTimer = null;
    if (tab === "deliverables" && resultsMount) paintResults();
  }, delay);
}

// --- URL ---------------------------------------------------------------------------

function browserLocation(): { pathname: string; search: string; hash: string } | null {
  const candidate = (globalThis as {
    location?: { pathname?: unknown; search?: unknown; hash?: unknown };
  }).location;
  if (!candidate || typeof candidate.search !== "string") return null;
  return {
    pathname: typeof candidate.pathname === "string" ? candidate.pathname : "",
    search: candidate.search,
    hash: typeof candidate.hash === "string" ? candidate.hash : "",
  };
}

/**
 * Écrit l’onglet actif dans l’URL sans empiler d’entrée d’historique : le bouton
 * « Précédent » reste celui du shell, et un rechargement rouvre le même onglet.
 */
function rememberTabInUrl(next: LibraryTab): void {
  const location = browserLocation();
  const history = (globalThis as {
    history?: { replaceState?: (data: unknown, title: string, url: string) => void };
  }).history;
  if (!location || typeof history?.replaceState !== "function") return;
  const search = librarySearchWithTab(location.search, next);
  history.replaceState({}, "", `${location.pathname}${search}${location.hash}`);
}

// --- Chargement ---------------------------------------------------------------------

interface ReferenceData {
  projects: { id: string; name: string }[];
  missions: LibraryRunSource[];
  failed: boolean;
}

/** Listes de référence des filtres. Un échec dégrade les filtres, il ne casse pas la page. */
async function loadReferences(): Promise<ReferenceData> {
  const [overview, missions] = await Promise.allSettled([
    workspaceApi.fetchOverview(),
    workspaceApi.fetchMissions(),
  ]);
  const projects = overview.status === "fulfilled"
    ? (overview.value.projects as Project[]).map((project) => ({ id: project.id, name: project.name }))
    : [];
  const missionList = missions.status === "fulfilled"
    ? (missions.value as MissionSummary[]).map((mission) => ({
        id: mission.id,
        project_id: mission.project_id,
        title: mission.title,
        current_run: {
          id: mission.current_run.id,
          attempt_number: mission.current_run.attempt_number,
        },
      }))
    : [];
  return {
    projects,
    missions: missionList,
    failed: overview.status === "rejected" || missions.status === "rejected",
  };
}

async function loadArtifacts(options: { more?: boolean } = {}): Promise<void> {
  const sequence = ++loadSequence;
  const more = options.more === true && state.nextCursor !== null;
  if (more) {
    state.loadingMore = true;
  } else {
    state.phase = "loading";
    state.error = null;
  }
  paintResults();

  const wantReferences = !state.referencesLoaded;
  const [pageResult, referenceResult] = await Promise.allSettled([
    api.listArtifacts({
      projectId: state.projectId,
      taskRunId: state.taskRunId,
      streamKind: state.streamKind,
      cursor: more ? state.nextCursor ?? undefined : undefined,
    }),
    wantReferences ? loadReferences() : Promise.resolve(null),
  ]);
  if (sequence !== loadSequence) return;

  if (referenceResult.status === "fulfilled" && referenceResult.value) {
    state.projects = referenceResult.value.projects;
    state.missions = referenceResult.value.missions;
    state.referencesFailed = referenceResult.value.failed;
    state.referencesLoaded = true;
  }

  state.loadingMore = false;
  if (pageResult.status === "fulfilled") {
    state.items = more ? [...state.items, ...pageResult.value.items] : pageResult.value.items;
    state.nextCursor = pageResult.value.next_cursor;
    state.phase = "ready";
    state.error = null;
    if (!more) rows = new Map();
  } else if (!more) {
    state.items = [];
    state.nextCursor = null;
    state.error = normalizeApiError(pageResult.reason, "Lecture des livrables impossible.");
    state.phase = "error";
  } else {
    state.error = normalizeApiError(pageResult.reason, "Lecture des livrables impossible.");
    state.phase = "ready";
  }
  // Un rendu ici alors que l'utilisateur est reparti sur « Skills » remonterait ce module
  // pour rien : l'etat est deja a jour, le prochain affichage de l'onglet le peindra.
  if (tab === "deliverables") paint();
}

function applyFilters(): void {
  state.nextCursor = null;
  void loadArtifacts();
}

async function requestLink(artifact: ArtifactSummary, target: "preview" | "download"): Promise<void> {
  const row = rowState(artifact.id);
  if (row.busy) return;
  row.busy = true;
  row.error = "";
  paintResults();
  try {
    const currentLink = target === "preview" ? row.previewLink : row.downloadLink;
    const link = isLinkUsable(currentLink)
      ? currentLink
      : await api.createLink(artifact.id, undefined, target);
    if (target === "preview") {
      row.previewLink = link;
      row.preview = true;
    } else {
      row.downloadLink = link;
      row.download = true;
    }
    state.signingUnavailable = false;
    state.signingMessage = "";
    state.signingAction = "";
  } catch (error) {
    const apiError = normalizeApiError(error, "Création du lien signé impossible.");
    const description = describeArtifactsError(apiError);
    if (apiError.status === 503) {
      state.signingUnavailable = true;
      state.signingMessage = description.message;
      state.signingAction = description.action ?? "";
    } else {
      row.error = `${description.title} : ${description.message}`;
    }
  } finally {
    row.busy = false;
    paint();
  }
}

// --- Rendu des livrables --------------------------------------------------------------

function optionNode(value: string, label: string): HTMLOptionElement {
  const option = el("option", "", label);
  option.value = value;
  return option;
}

function selectField(
  labelText: string,
  className: string,
  options: readonly LibraryOption[],
  selected: string,
  onChange: (value: string) => void,
  hint = "",
): HTMLElement {
  const control = el("select", `form-control ${className}`);
  for (const option of options) control.append(optionNode(option.id, option.label));
  control.value = selected;
  control.addEventListener("change", () => onChange(control.value));
  return labeledField(labelText, control, hint);
}

function filtersSection(): HTMLElement {
  const form = el("div", "library-filters");

  form.append(selectField(
    "Projet",
    "library-filter-project",
    [{ id: "", label: "Tous les projets" }, ...projectOptions(state.projects, state.items)],
    state.projectId,
    (value) => {
      state.projectId = value;
      // Une tentative appartient à un projet : la conserver produirait une liste vide.
      state.taskRunId = "";
      applyFilters();
    },
  ));

  form.append(selectField(
    "Mission (tentative)",
    "library-filter-run",
    [
      { id: "", label: "Toutes les tentatives" },
      ...runOptions(state.missions, state.items, state.projectId),
    ],
    state.taskRunId,
    (value) => {
      state.taskRunId = value;
      applyFilters();
    },
  ));

  form.append(selectField(
    "Type",
    "library-filter-kind",
    STREAM_KIND_FILTERS.map((entry) => ({ id: entry.value, label: entry.label })),
    state.streamKind,
    (value) => {
      state.streamKind = value;
      applyFilters();
    },
  ));

  const search = el("input", "form-control library-search");
  search.type = "search";
  search.value = state.query;
  search.placeholder = "Nom, type, provenance, empreinte";
  search.addEventListener("input", () => {
    state.query = search.value;
    paintResults();
  });
  form.append(labeledField(
    "Rechercher dans la page",
    search,
    "La recherche porte sur les livrables déjà chargés ; les filtres ci-dessus interrogent le serveur.",
  ));

  const actions = el("div", "library-actions");
  const refresh = el("button", "button button-secondary", "Actualiser");
  refresh.type = "button";
  refresh.addEventListener("click", () => applyFilters());
  actions.append(refresh);
  form.append(actions);

  if (state.referencesFailed) {
    form.append(el(
      "p",
      "form-hint library-degraded",
      "Projets et missions illisibles pour cette session : les filtres proposent uniquement les "
        + "identifiant(s) présents dans les livrables chargés.",
    ));
  }
  return form;
}

function metaRow(term: string, value: string): HTMLElement {
  const row = el("div", "library-meta-row");
  row.append(el("dt", "library-meta-term", term), el("dd", "library-meta-value", value));
  return row;
}

function previewNode(
  artifact: ArtifactSummary,
  link: ArtifactLink,
  kind: "image" | "video" | "model",
): HTMLElement {
  const frame = el("div", "library-preview");
  if (!isSeparateArtifactPreviewUrl(link.url)) {
    frame.append(el(
      "p",
      "library-warning",
      `Aperçu bloqué : ${ARTIFACT_PREVIEW_ORIGIN_ACTION} doit désigner une origine distincte `
        + "de l’application. Le fichier reste téléchargeable sans être rendu ici.",
    ));
    frame.append(downloadAnchor(
      link.url,
      artifact.original_name,
      "Télécharger sans aperçu",
    ));
    return frame;
  }
  if (kind === "image") {
    const image = el("img", "library-preview-media");
    image.crossOrigin = "anonymous";
    image.src = link.url;
    image.alt = `Aperçu de ${artifact.original_name || "livrable sans nom"}`;
    image.loading = "lazy";
    frame.append(image);
  } else if (kind === "video") {
    const video = el("video", "library-preview-media");
    video.crossOrigin = "anonymous";
    video.src = link.url;
    video.controls = true;
    video.preload = "metadata";
    frame.append(video);
  } else {
    frame.append(modelPreviewNode(
      link.url,
      `Aperçu 3D de ${artifact.original_name || "livrable sans nom"}`,
    ));
  }
  frame.append(el(
    "p",
    "form-hint",
    `${PREVIEW_ORIGIN_NOTE} Lien valable jusqu’à ${formatDateTime(link.expires_at)}.`,
  ));
  return frame;
}

function downloadAnchor(
  url: string,
  filename: string,
  label: string,
  className = "button button-secondary",
): HTMLAnchorElement {
  const anchor = el("a", className, label);
  anchor.href = url;
  anchor.download = filename || "livrable";
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
}

function artifactRow(artifact: ArtifactSummary): HTMLElement {
  const decision = describeArtifactPreview(artifact);
  const row = rowState(artifact.id);
  // Une URL signée ne reste jamais dans le DOM au-delà de sa fenêtre utile. Garder
  // les booléens permet de distinguer une première demande d'un renouvellement, mais
  // retirer la valeur périmée garantit que ni un média ni une ancre ne la réutilise.
  expireUnusableRowLinks(row);
  const previewNeedsRegeneration = row.preview && !row.previewLink;
  const downloadNeedsRegeneration = row.download && !row.downloadLink;
  const item = el("article", "list-item library-artifact");

  const copy = el("div", "list-item-copy");
  copy.append(el("h3", "list-item-title", artifact.original_name || "Livrable sans nom"));
  copy.append(el(
    "p",
    "list-item-meta",
    `${artifactStreamKindLabel(artifact.stream_kind)} · ${artifactSourceLabel(artifact.source)} · `
      + `${formatArtifactSize(artifact.size_bytes)} · `
      + `${artifact.created_at ? formatDateTime(artifact.created_at) : "Date inconnue"}`,
  ));

  const chips = el("div", "library-chips");
  chips.append(
    statusChip(artifactStreamKindLabel(artifact.stream_kind), "neutral"),
    statusChip(artifactSourceLabel(artifact.source), "neutral"),
    statusChip(artifact.content_type || "Type non déclaré", decision.downloadOnly ? "waiting" : "neutral"),
  );
  if (!artifact.has_content) chips.append(statusChip("Métadonnées seules", "waiting"));
  copy.append(chips);

  const meta = el("dl", "library-meta");
  const project = state.projects.find((candidate) => candidate.id === artifact.project_id);
  meta.append(
    metaRow("Projet", project ? project.name : artifact.project_id),
    metaRow("Tentative", artifact.task_run_id),
    metaRow("Nature", artifact.kind || "Non précisée"),
    metaRow("Type déclaré", artifact.content_type || "Non déclaré"),
    metaRow("Taille", formatArtifactSize(artifact.size_bytes)),
    metaRow("Empreinte", shortChecksum(artifact.checksum)),
  );
  copy.append(meta);

  if (decision.warning) {
    copy.append(el("p", "library-warning", `Attention — ${decision.warning}`));
  }
  if (!artifact.has_content) {
    copy.append(el(
      "p",
      "form-hint",
      "Métadonnées seules : aucun contenu n’a été téléversé pour ce livrable, il n’y a donc "
        + "rien à télécharger.",
    ));
  }

  const actions = el("div", "library-actions");
  if (decision.downloadable && decision.kind !== "none" && !row.previewLink) {
    const preview = el(
      "button",
      "button button-secondary",
      previewNeedsRegeneration ? "Régénérer l’aperçu" : "Aperçu",
    );
    preview.type = "button";
    preview.disabled = row.busy;
    preview.addEventListener("click", () => void requestLink(artifact, "preview"));
    actions.append(preview);
  }
  if (decision.downloadable && !row.downloadLink) {
    const download = el(
      "button",
      "button button-primary",
      downloadNeedsRegeneration
        ? "Régénérer le téléchargement"
        : "Préparer le téléchargement",
    );
    download.type = "button";
    download.disabled = row.busy;
    download.addEventListener("click", () => void requestLink(artifact, "download"));
    actions.append(download);
  }
  if (decision.downloadable && row.downloadLink) {
    actions.append(downloadAnchor(
      row.downloadLink.url,
      artifact.original_name,
      `Télécharger (lien valable jusqu’à ${formatDateTime(row.downloadLink.expires_at)})`,
    ));
  }
  if (decision.downloadable && state.signingUnavailable && !row.downloadLink) {
    actions.append(downloadAnchor(
      api.contentUrl(artifact.id),
      artifact.original_name,
      "Télécharger via la session",
    ));
  }
  if (actions.children.length) copy.append(actions);

  if (previewNeedsRegeneration) {
    const expired = el(
      "p",
      "form-hint library-expired-link",
      "Le lien d’aperçu a expiré. Régénérez-le pour afficher de nouveau ce livrable.",
    );
    expired.setAttribute("role", "status");
    copy.append(expired);
  }
  if (downloadNeedsRegeneration) {
    const expired = el(
      "p",
      "form-hint library-expired-link",
      "Le lien de téléchargement a expiré. Régénérez-le avant de télécharger ce livrable.",
    );
    expired.setAttribute("role", "status");
    copy.append(expired);
  }
  if (decision.downloadable && state.signingUnavailable && !row.downloadLink) {
    copy.append(el("p", "form-hint", SESSION_DOWNLOAD_NOTE));
  }
  if (row.busy) copy.append(el("p", "form-hint", "Création du lien signé…"));
  if (row.error) {
    const failure = el("p", "library-feedback", row.error);
    failure.setAttribute("role", "status");
    copy.append(failure);
  }
  if (row.previewLink && decision.kind !== "none") {
    copy.append(previewNode(artifact, row.previewLink, decision.kind));
  }

  item.append(copy);
  return item;
}

function signingPanel(): HTMLElement {
  const panel = statePanel(
    "unconfigured",
    "Liens signés non configurés",
    `${state.signingMessage} Le téléchargement authentifié par la session reste possible.`,
  );
  if (state.signingAction) panel.append(el("p", "library-action", state.signingAction));
  return panel;
}

function resultNodes(): HTMLElement[] {
  const nodes: HTMLElement[] = [];
  if (state.signingUnavailable) nodes.push(signingPanel());

  // « idle » n'est visible qu'entre le montage et le premier appel : afficher « aucun
  // livrable » à cet instant serait un vide inventé.
  if ((state.phase === "loading" || state.phase === "idle") && !state.items.length) {
    nodes.push(statePanel("loading", "Lecture des livrables", "Interrogation de l’API métier…"));
    return nodes;
  }
  if (state.phase === "error" && state.error) {
    const description = describeArtifactsError(state.error);
    const panel = statePanel(description.tone, description.title, description.message, () => {
      void loadArtifacts();
    });
    if (description.action) panel.append(el("p", "library-action", description.action));
    nodes.push(panel);
    return nodes;
  }
  if (!state.items.length) {
    nodes.push(statePanel(
      "empty",
      "Aucun livrable",
      "Aucun livrable ne correspond à ces filtres. Les livrables apparaissent quand un worker ou une "
        + "suite de tests en téléverse pendant une tentative.",
    ));
    return nodes;
  }

  if (state.phase === "loading") {
    nodes.push(el("p", "form-hint", "Mise à jour de la liste… les livrables ci-dessous sont ceux "
      + "de la requête précédente."));
  }

  const visible = filterArtifacts(state.items, state.query);
  // Seule cette phrase courte est annoncée : une région vivante portant toute la liste
  // ferait relire chaque livrable à chaque frappe.
  const count = el(
    "p",
    "library-count",
    visible.length === state.items.length
      ? `${state.items.length} livrable(s) chargé(s).`
      : `${visible.length} livrable(s) affiché(s) sur ${state.items.length} chargé(s).`,
  );
  count.setAttribute("aria-live", "polite");
  nodes.push(count);
  if (!visible.length) {
    nodes.push(statePanel(
      "empty",
      "Aucun livrable ne correspond à la recherche",
      "Efface la recherche ou élargis les filtres pour retrouver les livrables chargés.",
    ));
    return nodes;
  }

  const list = el("div", "item-list library-list");
  for (const artifact of visible) list.append(artifactRow(artifact));
  nodes.push(list);

  if (state.error) {
    nodes.push(el(
      "p",
      "library-feedback",
      `Page suivante indisponible : ${describeArtifactsError(state.error).message}`,
    ));
  }
  if (state.nextCursor) {
    const more = el("button", "button button-secondary", "Charger la suite");
    more.type = "button";
    more.disabled = state.loadingMore;
    more.addEventListener("click", () => void loadArtifacts({ more: true }));
    nodes.push(more);
  }
  if (state.loadingMore) nodes.push(el("p", "form-hint", "Chargement de la page suivante…"));
  return nodes;
}

function paintResults(): void {
  if (!resultsMount) {
    clearLinkExpiryTimer();
    return;
  }
  // La recherche peut masquer une ligne : invalider tout le registre avant le rendu
  // évite qu'un jeton périmé survive simplement parce que sa carte n'est pas visible.
  for (const row of rows.values()) expireUnusableRowLinks(row);
  resultsMount.replaceChildren(...resultNodes());
  scheduleLinkExpiryInvalidation();
}

function deliverablesPanel(panel: HTMLElement): void {
  panel.append(sectionHeader(
    "Livrables",
    "Captures, vidéos, traces et rapports produits pendant les tentatives. Les contenus sont des "
      + "données non fiables : seuls les images et les vidéos autorisées s’affichent en ligne, tout le "
      + "reste se télécharge.",
  ));
  panel.append(filtersSection());
  resultsMount = el("div", "library-results");
  panel.append(resultsMount);
  paintResults();
}

// --- Onglets ---------------------------------------------------------------------------

function selectTab(next: LibraryTab): void {
  if (tab === next) return;
  tab = next;
  rememberTabInUrl(next);
  paint();
  if (tab === "deliverables" && (state.phase === "idle" || state.phase === "error")) {
    void loadArtifacts();
  }
}

function tabList(): HTMLElement {
  const list = el("div", "library-tabs");
  list.setAttribute("role", "tablist");
  list.setAttribute("aria-label", "Sections de la bibliothèque");
  TABS.forEach((entry, index) => {
    const button = el("button", "library-tab", entry.label);
    button.type = "button";
    button.id = `library-tab-${entry.id}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", PANEL_ID);
    const active = tab === entry.id;
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    button.addEventListener("click", () => selectTab(entry.id));
    button.addEventListener("keydown", (event) => {
      const offset = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!offset) return;
      event.preventDefault();
      selectTab(TABS[(index + offset + TABS.length) % TABS.length].id);
    });
    list.append(button);
  });
  return list;
}

function paint(): void {
  if (!mount) return;
  clearLinkExpiryTimer();
  resultsMount = null;
  const panel = el("section", "library-panel");
  panel.id = PANEL_ID;
  panel.setAttribute("role", "tabpanel");
  panel.setAttribute("aria-labelledby", `library-tab-${tab}`);
  panel.tabIndex = -1;
  mount.replaceChildren(tabList(), panel);
  if (tab === "skills") renderSkillsLibrary(panel, http);
  else deliverablesPanel(panel);
}

/**
 * Rendu de la route « Bibliothèque ». Le shell passe son client HTTP : c’est lui qui
 * porte le jeton CSRF de la session, et un client séparé devrait relire `/auth/session`,
 * ce qui ferait tourner ce jeton unique côté serveur.
 *
 * L’onglet ouvert vient de l’URL quand elle le précise (lien profond), sinon du dernier
 * choix mémorisé dans ce module.
 */
export function renderLibrary(container: HTMLElement, sharedHttp?: WorkspaceHttpClient): void {
  useHttpClient(sharedHttp);
  const location = browserLocation();
  tab = (location && libraryTabInSearch(location.search)) ?? tab;
  mount = el("div", "library");
  container.append(mount);
  paint();
  if (tab === "deliverables" && (state.phase === "idle" || state.phase === "error")) {
    void loadArtifacts();
  }
}

/**
 * Efface tout ce que ce module retient d’un compte : livrables lus, filtres, liens signés
 * créés et projets. La purge est relayée à la bibliothèque de skills, qui garde son propre
 * état. Le compteur de séquence est incrémenté pour qu’une réponse partie avant la purge
 * soit ignorée.
 */
export function resetLibraryUiState(): void {
  loadSequence += 1;
  clearLinkExpiryTimer();
  state = initialDeliverables();
  rows = new Map();
  tab = "skills";
  mount = null;
  resultsMount = null;
  useHttpClient(undefined);
  resetSkillsUiState();
}
