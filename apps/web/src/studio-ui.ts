/**
 * Studio en direct d’une tentative (spec Lot E §10, brief E6).
 *
 * Le Studio se rend dans le détail d’une mission et sur le lien profond
 * `/missions?run=<id>&vue=studio`. Il montre, pour **une** tentative :
 * bandeau de mode et de connexion, chronologie du journal, dernière capture de la
 * session, résultats de tests structurés et pièces jointes.
 *
 * Quatre règles gouvernent ce module :
 *
 * 1. **Rien n’est inventé.** Le mode (`Direct`, `Aperçu intermédiaire`, `Replay`,
 *    `Hors ligne / inconnu`) découle de l’état réel du flux et de la présence d’un
 *    événement terminal ; aucun état n’est déduit d’un silence.
 * 2. **Tout contenu venu de l’API est une donnée non fiable** : message d’erreur de test,
 *    extrait de code, nom de fichier, titre de suite, payload d’événement sont insérés par
 *    `textContent` ou par `el()`, jamais par `innerHTML`.
 * 3. **Le contenu d’un artefact n’est jamais rendu dans l’origine de la plateforme** :
 *    images, vidéos et modèles passent uniquement par une URL signée sur une origine
 *    d’aperçu séparée (sinon l’API refuse l’aperçu), et une trace ou un rapport HTML
 *    n’est proposé qu’en téléchargement explicite, avec avertissement. Aucune `iframe`,
 *    aucun `srcdoc`, aucune exécution.
 * 4. **Aucun bouton de prise de contrôle** : la capacité n’est pas livrée dans ce lot et
 *    l’interface le dit au lieu de laisser croire à une action possible.
 *
 * Comme au Lot D, le client HTTP est fourni par le shell : ce module n’en crée jamais un
 * et ne lit jamais `/auth/session`. `resetStudioUiState()` est appelé par le shell à la
 * connexion et à la déconnexion ; il ferme aussi le flux `EventSource` ouvert.
 */

import type {
  ArtifactLink,
  ArtifactSummary,
  StreamEvent,
  TestCaseResult,
  TestRunDetail,
} from "@acp/contracts";

import "./studio.css";
import { isSeparateArtifactPreviewUrl } from "./artifacts-api";
import {
  EVENTS_PAGE_LIMIT_DEFAULT,
  EventsApiClient,
  classifyArtifactPreview,
  describeConnectionState,
  describeStudioMode,
  eventsCursor,
  isRunTerminalEvent,
  lastMediaReference,
  mergeStreamEvents,
  studioMode,
  type MediaReference,
  type RunStreamSubscription,
  type StreamConnectionState,
} from "./events-api";
import { modelPreviewNode } from "./model-preview";
import {
  TestingApiClient,
  buildTestTree,
  describeTestRunStatus,
  formatTestDuration,
  isMissingTestRun,
  summarizeTestTotals,
  testCaseBadge,
  type TestSuiteNode,
} from "./testing-api";
import {
  el,
  errorMessage,
  formatDateTime,
  normalizeApiError,
  sectionHeader,
  statePanel,
  statusChip,
  type StatePanelTone,
} from "./ui-primitives";
import {
  WorkspaceApiError,
  WorkspaceHttpClient,
  isRecord,
  type Validator,
} from "./workspace-api";

/** Variable d’environnement à définir côté API pour émettre des liens signés (§5.3). */
export const ARTIFACT_SIGNING_ACTION = "ACP_ARTIFACT_SIGNING_KEYS";
/** Variable d’environnement de l’origine d’aperçu séparée (§7). */
export const ARTIFACT_PUBLIC_ORIGIN_ACTION = "ACP_ARTIFACT_PUBLIC_ORIGIN";
/** Durée de vie demandée pour un lien signé (la route borne à 900 s). */
export const LINK_TTL_SECONDS = 300;
/** Nombre maximal d’événements rendus : le reste reste chargé mais n’est pas peint. */
export const TIMELINE_RENDER_MAX = 300;
/** Longueur maximale d’un payload rendu en texte brut. */
const PAYLOAD_RENDER_MAX_CHARS = 4_000;
/** `stream_kind` d’une capture d’écran (§3.2). */
const SCREENSHOT_STREAM_KIND = "screenshot";
/** Paramètre de vue qui ouvre le Studio dans le détail d’une mission (spec §2.5). */
export const STUDIO_VIEW_PARAM = "vue";
/** Valeur attendue de ce paramètre. */
export const STUDIO_VIEW_VALUE = "studio";

/**
 * Le Studio est-il demandé par la chaîne de requête courante ?
 *
 * Le shell s’en sert à deux endroits : pour monter le Studio dans le détail d’une
 * mission, et pour **fermer le flux** dès que l’écran est quitté.
 */
export function isStudioViewRequested(search: string): boolean {
  return new URLSearchParams(search).get(STUDIO_VIEW_PARAM) === STUDIO_VIEW_VALUE;
}

/** Lien profond `/missions?run=<id>&vue=studio` d’une tentative (§2.5, §10). */
export function studioRouteLink(runId: string): string {
  const query = new URLSearchParams({ run: runId, [STUDIO_VIEW_PARAM]: STUDIO_VIEW_VALUE });
  return `/missions?${query.toString()}`;
}

type Phase = "idle" | "loading" | "ready" | "error";
type LinkPhase = "idle" | "loading" | "ready" | "error" | "expired";

export interface ArtifactLinkState {
  phase: LinkPhase;
  link: ArtifactLink | null;
  error: WorkspaceApiError | null;
}

interface StudioState {
  runId: string | null;
  phase: Phase;
  error: WorkspaceApiError | null;
  events: StreamEvent[];
  pageCursor: number | null;
  hasMore: boolean;
  loadingMore: boolean;
  retentionDays: number | null;
  connection: StreamConnectionState;
  failures: number;
  malformed: number;
  streamError: WorkspaceApiError | null;
  testPhase: Phase;
  testRun: TestRunDetail | null;
  testError: WorkspaceApiError | null;
  testMissing: boolean;
  expandedCases: Set<string>;
  links: Map<string, ArtifactLinkState>;
}

function initialState(): StudioState {
  return {
    runId: null,
    phase: "idle",
    error: null,
    events: [],
    pageCursor: null,
    hasMore: false,
    loadingMore: false,
    retentionDays: null,
    connection: "reconnecting",
    failures: 0,
    malformed: 0,
    streamError: null,
    testPhase: "idle",
    testRun: null,
    testError: null,
    testMissing: false,
    expandedCases: new Set<string>(),
    links: new Map<string, ArtifactLinkState>(),
  };
}

const state: StudioState = initialState();

let mount: HTMLElement | null = null;
let http: WorkspaceHttpClient | null = null;
let events: EventsApiClient | null = null;
let testing: TestingApiClient | null = null;
let subscription: RunStreamSubscription | null = null;
let loadSequence = 0;
let paintScheduled = false;
let createLink: ((artifactId: string, purpose?: "download" | "preview") => Promise<ArtifactLink>) | null = null;
let linkExpiryTimer: ReturnType<typeof globalThis.setTimeout> | null = null;

/** Retire le bearer du DOM avant sa vraie échéance, même si l'horloge dérive légèrement. */
export const STUDIO_LINK_REUSE_MARGIN_MS = 15_000;
const LINK_EXPIRY_TIMER_MAX_MS = 2_147_483_647;

export function isStudioLinkUsable(
  link: ArtifactLink | null,
  now = Date.now(),
): link is ArtifactLink {
  if (!link) return false;
  const expiry = Date.parse(link.expires_at);
  return Number.isFinite(expiry) && expiry - now > STUDIO_LINK_REUSE_MARGIN_MS;
}

/** Purge les URLs périmées tout en conservant l'état nécessaire au message de renouvellement. */
export function invalidateExpiredStudioLinks(
  links: Map<string, ArtifactLinkState>,
  now = Date.now(),
): boolean {
  let changed = false;
  for (const [artifactId, current] of links) {
    if (!current.link || isStudioLinkUsable(current.link, now)) continue;
    links.set(artifactId, { phase: "expired", link: null, error: null });
    changed = true;
  }
  return changed;
}

function clearLinkExpiryTimer(): void {
  if (linkExpiryTimer === null) return;
  globalThis.clearTimeout(linkExpiryTimer);
  linkExpiryTimer = null;
}

function scheduleLinkExpiryInvalidation(): void {
  clearLinkExpiryTimer();
  if (!mount) return;
  let nextInvalidationAt = Number.POSITIVE_INFINITY;
  for (const current of state.links.values()) {
    if (!current.link) continue;
    const expiry = Date.parse(current.link.expires_at);
    if (Number.isFinite(expiry)) {
      nextInvalidationAt = Math.min(
        nextInvalidationAt,
        expiry - STUDIO_LINK_REUSE_MARGIN_MS,
      );
    }
  }
  if (!Number.isFinite(nextInvalidationAt)) return;
  const delay = Math.min(
    LINK_EXPIRY_TIMER_MAX_MS,
    Math.max(1, nextInvalidationAt - Date.now() + 1),
  );
  linkExpiryTimer = globalThis.setTimeout(() => {
    linkExpiryTimer = null;
    invalidateExpiredStudioLinks(state.links);
    paint();
  }, delay);
}

export interface StudioOptions {
  /**
   * Création d’un lien signé. Par défaut, `POST /artifacts/{id}/link` sur le client du
   * shell. E7 peut injecter son `ArtifactsApiClient` sans modifier ce module.
   */
  createArtifactLink?: (
    artifactId: string,
    purpose?: "download" | "preview",
  ) => Promise<ArtifactLink>;
}

// --- Validation locale d’un lien signé -----------------------------------------

const isArtifactLink: Validator<ArtifactLink> = (value: unknown): value is ArtifactLink =>
  isRecord(value)
  && typeof value.artifact_id === "string"
  && typeof value.url === "string"
  && typeof value.expires_at === "string";

function defaultCreateArtifactLink(
  artifactId: string,
  purpose: "download" | "preview" = "download",
): Promise<ArtifactLink> {
  if (!http) {
    return Promise.reject(new WorkspaceApiError(
      "Le Studio n’a pas reçu le client HTTP du shell.",
      "invalid_response",
    ));
  }
  const params = new URLSearchParams({ ttl_seconds: String(LINK_TTL_SECONDS) });
  if (purpose === "preview") params.set("purpose", purpose);
  return http.request(
    `/artifacts/${encodeURIComponent(artifactId)}/link?${params.toString()}`,
    isArtifactLink,
    { method: "POST" },
  );
}

// --- Erreurs -------------------------------------------------------------------

interface StudioErrorDescription {
  tone: StatePanelTone;
  title: string;
  message: string;
}

/** Traduit une erreur d’API en panneau d’état honnête (jamais un écran vide silencieux). */
export function describeStudioError(error: WorkspaceApiError, subject: string): StudioErrorDescription {
  if (error.kind === "offline") {
    return { tone: "offline", title: `${subject} est indisponible`, message: errorMessage(error) };
  }
  if (error.kind === "forbidden") {
    return {
      tone: "forbidden",
      title: error.status === 401 ? "Session expirée" : "Accès refusé",
      message: errorMessage(error),
    };
  }
  if (error.kind === "invalid_response") {
    return { tone: "error", title: "Réponse inexploitable", message: error.message };
  }
  if (error.status === 404) {
    return { tone: "empty", title: `${subject} est introuvable`, message: error.message };
  }
  if (error.status === 503) {
    return {
      tone: "unconfigured",
      title: "Capacité non configurée",
      message: `${error.message} Action attendue côté API : définir ${ARTIFACT_SIGNING_ACTION} `
        + `(clé de signature), puis relancer le service. Sans elle, aucun aperçu ni téléchargement `
        + `par lien signé n’est possible.`,
    };
  }
  if (error.status === 424) {
    return {
      tone: "unconfigured",
      title: "Origine d’aperçu non configurée",
      message: `${error.message} Action attendue côté API : définir `
        + `${ARTIFACT_PUBLIC_ORIGIN_ACTION} avec une origine HTTPS distincte.`,
    };
  }
  return { tone: "error", title: `${subject} est indisponible`, message: error.message };
}

function errorPanel(error: WorkspaceApiError, subject: string, onRetry?: () => void): HTMLElement {
  const described = describeStudioError(error, subject);
  return statePanel(described.tone, described.title, described.message, onRetry);
}

// --- Formats -------------------------------------------------------------------

const SIZE_UNITS = ["o", "Kio", "Mio", "Gio"] as const;

/** Taille lisible ; une taille absente reste « inconnue », jamais « 0 o ». */
export function formatArtifactSize(size: number | null): string {
  if (size === null || !Number.isFinite(size) || size < 0) return "Taille inconnue";
  let value = size;
  let unit = 0;
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const formatted = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(value);
  return `${formatted} ${SIZE_UNITS[unit]}`;
}

function artifactName(artifact: ArtifactSummary): string {
  return artifact.original_name || artifact.kind || artifact.id;
}

/**
 * Vrai uniquement pour une URL `http(s)`. Une URL d’un autre schéma renvoyée par l’API
 * (`javascript:`, `data:`) n’est jamais posée dans un `href` ni dans un `src`.
 */
function isSafeHttpUrl(url: string): boolean {
  try {
    const parsed = new URL(url, linkBaseUrl());
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function linkBaseUrl(): string {
  return typeof window === "undefined" ? "http://localhost" : window.location.href;
}

// --- Chargement ----------------------------------------------------------------

function paint(): void {
  if (!mount) {
    clearLinkExpiryTimer();
    return;
  }
  invalidateExpiredStudioLinks(state.links);
  mount.replaceChildren();
  mount.append(bannerSection(), timelineSection(), captureSection(), testsSection(), handoverSection());
  scheduleLinkExpiryInvalidation();
}

/** Les événements arrivent par rafales : le rendu est groupé sur une micro-tâche. */
function schedulePaint(): void {
  if (paintScheduled) return;
  paintScheduled = true;
  globalThis.setTimeout(() => {
    paintScheduled = false;
    paint();
  }, 0);
}

async function loadStudio(runId: string): Promise<void> {
  if (!events) return;
  const sequence = ++loadSequence;
  state.phase = "loading";
  state.error = null;
  paint();
  try {
    const page = await events.fetchRunEvents(runId, { limit: EVENTS_PAGE_LIMIT_DEFAULT });
    if (sequence !== loadSequence) return;
    state.events = mergeStreamEvents([], page.events);
    state.pageCursor = page.next_cursor ?? eventsCursor(page.events);
    state.hasMore = page.has_more;
    state.retentionDays = page.retention_days;
    state.phase = "ready";
    openStream(runId, state.pageCursor);
  } catch (error) {
    if (sequence !== loadSequence) return;
    state.phase = "error";
    state.error = normalizeApiError(error, "Le journal de la tentative est illisible.");
  }
  paint();
  void loadTestRun(runId, sequence);
}

async function loadMore(): Promise<void> {
  if (!events || !state.runId || state.loadingMore) return;
  const sequence = loadSequence;
  state.loadingMore = true;
  paint();
  try {
    const page = await events.fetchRunEvents(state.runId, {
      afterSeq: state.pageCursor,
      limit: EVENTS_PAGE_LIMIT_DEFAULT,
    });
    if (sequence !== loadSequence) return;
    state.events = mergeStreamEvents(state.events, page.events);
    state.pageCursor = page.next_cursor ?? state.pageCursor;
    state.hasMore = page.has_more;
    state.retentionDays = page.retention_days;
  } catch (error) {
    if (sequence !== loadSequence) return;
    state.streamError = normalizeApiError(error, "La suite du journal est illisible.");
  } finally {
    if (sequence === loadSequence) state.loadingMore = false;
  }
  paint();
}

async function loadTestRun(runId: string, sequence: number): Promise<void> {
  if (!testing) return;
  state.testPhase = "loading";
  state.testError = null;
  state.testMissing = false;
  paint();
  try {
    const detail = await testing.fetchTestRun(runId);
    if (sequence !== loadSequence) return;
    state.testRun = detail;
    state.testPhase = "ready";
  } catch (error) {
    if (sequence !== loadSequence) return;
    const apiError = normalizeApiError(error, "Le résultat de tests est illisible.");
    state.testRun = null;
    if (isMissingTestRun(apiError)) {
      state.testMissing = true;
      state.testPhase = "ready";
    } else {
      state.testPhase = "error";
      state.testError = apiError;
    }
  }
  paint();
}

function openStream(runId: string, cursor: number | null): void {
  if (!events) return;
  subscription?.close();
  subscription = events.openRunStream(runId, cursor, {
    onEvents: (incoming) => {
      state.events = mergeStreamEvents(state.events, incoming);
      const incomingCursor = eventsCursor(incoming);
      if (incomingCursor !== null && (state.pageCursor === null || incomingCursor > state.pageCursor)) {
        // Le flux reprend au curseur de la dernière page : tout ce qui suit arrive ici,
        // il n'y a donc plus de « passé » à charger à la main.
        state.pageCursor = incomingCursor;
        state.hasMore = false;
      }
      if (incoming.some(isRunTerminalEvent) && state.runId) void loadTestRun(state.runId, loadSequence);
      syncStreamState();
      schedulePaint();
    },
    onState: () => {
      syncStreamState();
      schedulePaint();
    },
    onError: (error) => {
      state.streamError = error;
      syncStreamState();
      schedulePaint();
    },
  });
  syncStreamState();
}

function syncStreamState(): void {
  if (!subscription) return;
  state.connection = subscription.state;
  state.failures = subscription.failures;
  state.malformed = subscription.malformed;
}

// --- Bandeau de mode -----------------------------------------------------------

function isTerminal(): boolean {
  return state.events.some(isRunTerminalEvent);
}

function lastScreenshot(): MediaReference | null {
  return lastMediaReference(state.events, SCREENSHOT_STREAM_KIND);
}

function bannerSection(): HTMLElement {
  const mode = studioMode({ connection: state.connection, terminal: isTerminal() });
  const described = describeStudioMode(mode);
  const connection = describeConnectionState(state.connection, state.failures);
  const banner = el("section", "content-section studio-banner");
  banner.dataset.mode = mode;
  banner.setAttribute("aria-live", "polite");

  const head = el("div", "studio-banner-head");
  const labels = el("div", "studio-banner-labels");
  labels.append(
    el("p", "workspace-eyebrow", "Studio de la tentative"),
    el("h3", "studio-banner-title", described.label),
    el("p", "studio-banner-description", described.description),
  );
  const chips = el("div", "studio-chips");
  // Le mode et la connexion portent un libellé textuel : la couleur ne suffit jamais.
  chips.append(statusChip(described.label, described.tone), statusChip(connection.label, connection.tone));
  if (state.malformed > 0) {
    chips.append(statusChip(`${state.malformed} trame(s) illisible(s) ignorée(s)`, "waiting"));
  }
  head.append(labels, chips);

  const facts = el("dl", "studio-facts");
  const screenshot = lastScreenshot();
  appendFact(facts, "Dernière image reçue", screenshot ? formatDateTime(screenshot.occurredAt) : "Aucune image reçue");
  const lastEvent = state.events[state.events.length - 1];
  appendFact(facts, "Dernier événement", lastEvent ? formatDateTime(lastEvent.occurred_at) : "Aucun événement");
  appendFact(facts, "Événements chargés", String(state.events.length));
  appendFact(
    facts,
    "Rétention du journal",
    state.retentionDays === null
      ? "Inconnue"
      : state.retentionDays === 0
        ? "Illimitée"
        : `${state.retentionDays} jours`,
  );
  banner.append(head, facts);

  if (state.connection !== "connected") {
    const actions = el("div", "studio-actions");
    const retry = el("button", "button button-secondary", "Reconnecter le direct");
    retry.type = "button";
    retry.addEventListener("click", () => {
      state.streamError = null;
      subscription?.retryNow();
      syncStreamState();
      paint();
    });
    actions.append(retry);
    banner.append(actions);
  }
  if (state.streamError) {
    const described2 = describeStudioError(state.streamError, "Le flux");
    banner.append(statePanel(described2.tone, described2.title, described2.message));
  }
  return banner;
}

function appendFact(list: HTMLElement, term: string, value: string): void {
  list.append(el("dt", "studio-fact-term", term), el("dd", "studio-fact-value", value));
}

// --- Chronologie ---------------------------------------------------------------

function timelineSection(): HTMLElement {
  const section = el("section", "content-section studio-timeline");
  section.append(sectionHeader(
    "Chronologie",
    "Journal persisté de la tentative : type, horodatage, étape et exécuteur. Le passé se charge par curseur.",
  ));

  if (state.phase === "loading") {
    section.append(statePanel("loading", "Chargement du journal", "Lecture de la première page d’événements…"));
    return section;
  }
  if (state.phase === "error" && state.error) {
    section.append(errorPanel(state.error, "Le journal", () => {
      if (state.runId) void loadStudio(state.runId);
    }));
    return section;
  }
  if (!state.events.length) {
    section.append(statePanel(
      "empty",
      "Aucun événement",
      "Cette tentative n’a encore publié aucun événement. Rien n’est déduit de ce silence.",
    ));
    return section;
  }

  const hidden = Math.max(0, state.events.length - TIMELINE_RENDER_MAX);
  if (hidden > 0) {
    section.append(el(
      "p",
      "studio-note",
      `${hidden} événement(s) plus ancien(s) sont chargés mais ne sont pas affichés ici.`,
    ));
  }
  const list = el("ol", "studio-event-list");
  for (const event of state.events.slice(-TIMELINE_RENDER_MAX)) list.append(eventRow(event));
  section.append(list);

  const actions = el("div", "studio-actions");
  if (state.hasMore) {
    const more = el("button", "button button-secondary", state.loadingMore ? "Chargement…" : "Charger la suite du journal");
    more.type = "button";
    more.disabled = state.loadingMore;
    more.addEventListener("click", () => void loadMore());
    actions.append(more);
  }
  if (actions.childElementCount) section.append(actions);
  return section;
}

function eventRow(event: StreamEvent): HTMLElement {
  const row = el("li", "studio-event");
  const header = el("div", "studio-event-header");
  header.append(
    el("span", "studio-event-type", event.type),
    el("span", "studio-event-time", formatDateTime(event.occurred_at)),
  );
  row.append(header);

  const meta = el("div", "studio-event-meta");
  if (typeof event.sequence === "number") meta.append(el("span", "studio-event-tag", `séquence ${event.sequence}`));
  if (event.step_id) meta.append(el("span", "studio-event-tag", `étape ${event.step_id}`));
  if (event.executor) meta.append(el("span", "studio-event-tag", `exécuteur ${event.executor}`));
  if (event.emitted_by) meta.append(el("span", "studio-event-tag", `émis par ${event.emitted_by}`));
  if (meta.childElementCount) row.append(meta);

  const message = event.payload.message;
  if (typeof message === "string" && message.trim()) {
    // Contenu produit par un programme : inséré en texte, jamais interprété.
    row.append(el("p", "studio-event-message", message.slice(0, 500)));
  }
  const payloadKeys = Object.keys(event.payload);
  if (payloadKeys.length) {
    const details = el("details", "studio-payload");
    details.append(el("summary", "", "Données brutes de l’événement"));
    const pre = el("pre", "studio-pre");
    pre.textContent = safeJson(event.payload);
    details.append(pre);
    row.append(details);
  }
  return row;
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2).slice(0, PAYLOAD_RENDER_MAX_CHARS);
  } catch {
    return "Données non sérialisables.";
  }
}

// --- Dernière capture ----------------------------------------------------------

function captureSection(): HTMLElement {
  const section = el("section", "content-section studio-capture");
  section.append(sectionHeader(
    "Dernière capture de la session",
    "Capture publiée par cette tentative uniquement, affichée par lien signé et horodatée.",
  ));
  const screenshot = lastScreenshot();
  if (!screenshot) {
    section.append(statePanel(
      "empty",
      "Aucune capture",
      "Aucun événement de cette tentative ne référence de capture d’écran.",
    ));
    return section;
  }
  const facts = el("dl", "studio-facts");
  appendFact(facts, "Horodatage", formatDateTime(screenshot.occurredAt));
  appendFact(facts, "Type", screenshot.contentType);
  appendFact(facts, "Taille", formatArtifactSize(screenshot.sizeBytes));
  if (screenshot.sha256) appendFact(facts, "Empreinte", screenshot.sha256);
  section.append(facts);
  section.append(mediaBlock(
    screenshot.artifactId,
    screenshot.contentType,
    `Capture du ${formatDateTime(screenshot.occurredAt)}`,
  ));
  return section;
}

// --- Liens signés et médias ----------------------------------------------------

function linkState(artifactId: string): ArtifactLinkState {
  return state.links.get(artifactId) ?? { phase: "idle", link: null, error: null };
}

async function requestLink(
  artifactId: string,
  purpose: "download" | "preview",
): Promise<void> {
  const provider = createLink ?? defaultCreateArtifactLink;
  const sequence = loadSequence;
  state.links.set(artifactId, { phase: "loading", link: null, error: null });
  paint();
  try {
    const link = await provider(artifactId, purpose);
    if (sequence !== loadSequence) return;
    state.links.set(artifactId, { phase: "ready", link, error: null });
  } catch (error) {
    if (sequence !== loadSequence) return;
    state.links.set(artifactId, {
      phase: "error",
      link: null,
      error: normalizeApiError(error, "Le lien signé n’a pas pu être créé."),
    });
  }
  paint();
}

/**
 * Bloc média d’un artefact. Une image ou une vidéo s’affiche par lien signé ; tout le
 * reste — trace `.zip`, rapport HTML, SVG — n’est proposé qu’en téléchargement explicite,
 * jamais rendu dans l’origine de la plateforme.
 */
function mediaBlock(artifactId: string, contentType: string, label: string): HTMLElement {
  const block = el("div", "studio-media");
  const kind = classifyArtifactPreview(contentType);
  const current = linkState(artifactId);

  if (kind === "download") {
    block.append(el(
      "p",
      "studio-warning",
      "Contenu non affichable dans la plateforme : archive à ouvrir avec l’outil Playwright, "
      + "hors de la plateforme. Le fichier est servi en téléchargement forcé, sans exécution.",
    ));
  }

  if (current.phase === "loading") {
    block.append(statePanel("loading", "Préparation du lien", "Création d’un lien signé et borné dans le temps…"));
    return block;
  }
  if (current.phase === "error" && current.error) {
    block.append(errorPanel(
      current.error,
      "Le lien signé",
      () => void requestLink(artifactId, kind === "download" ? "download" : "preview"),
    ));
    return block;
  }

  const link = current.link;
  if (!link) {
    const expired = current.phase === "expired";
    const button = el(
      "button",
      "button button-secondary",
      expired
        ? (kind === "download" ? "Régénérer le téléchargement" : "Régénérer l’aperçu")
        : (kind === "download" ? "Préparer le téléchargement" : "Afficher l’aperçu"),
    );
    button.type = "button";
    button.addEventListener(
      "click",
      () => void requestLink(artifactId, kind === "download" ? "download" : "preview"),
    );
    block.append(button);
    if (expired) {
      const message = el(
        "p",
        "studio-note studio-expired-link",
        kind === "download"
          ? "Le lien de téléchargement a expiré. Régénérez-le avant de télécharger ce livrable."
          : "Le lien d’aperçu a expiré. Régénérez-le pour afficher de nouveau ce livrable.",
      );
      message.setAttribute("role", "status");
      block.append(message);
    } else {
      block.append(el(
        "p",
        "studio-note",
        `Le lien est signé, lié à ce compte et valable ${LINK_TTL_SECONDS} secondes.`,
      ));
    }
    return block;
  }

  if (!isSafeHttpUrl(link.url)) {
    block.append(statePanel(
      "error",
      "Lien inexploitable",
      "L’API a renvoyé une URL dont le schéma n’est pas http(s) : elle n’est ni ouverte ni affichée.",
    ));
    return block;
  }

  block.append(el("p", "studio-note", `Lien signé valable jusqu’au ${formatDateTime(link.expires_at)}.`));
  const separatePreviewOrigin = isSeparateArtifactPreviewUrl(link.url);
  if (kind !== "download" && !separatePreviewOrigin) {
    block.append(el(
      "p",
      "studio-warning",
      `Aperçu bloqué : les liens pointent vers l’origine de l’application. Configure `
      + `${ARTIFACT_PUBLIC_ORIGIN_ACTION} avec une origine distincte ; le fichier n’est pas rendu ici.`,
    ));
    const anchor = el("a", "button button-secondary", "Télécharger sans aperçu");
    anchor.href = link.url;
    anchor.rel = "noopener noreferrer";
    anchor.download = "";
    block.append(anchor);
  }

  if (kind === "image" && separatePreviewOrigin) {
    const image = el("img", "studio-image");
    image.crossOrigin = "anonymous";
    image.src = link.url;
    image.alt = label;
    image.loading = "lazy";
    image.decoding = "async";
    block.append(image);
  } else if (kind === "video" && separatePreviewOrigin) {
    const video = el("video", "studio-video");
    video.crossOrigin = "anonymous";
    video.src = link.url;
    video.controls = true;
    video.preload = "metadata";
    block.append(video);
  } else if (kind === "model" && separatePreviewOrigin) {
    block.append(modelPreviewNode(link.url, label));
  } else if (kind === "download") {
    const anchor = el("a", "button button-secondary", "Télécharger le fichier");
    anchor.href = link.url;
    anchor.rel = "noopener noreferrer";
    anchor.download = "";
    block.append(anchor);
  }

  const refresh = el("button", "button button-secondary", "Régénérer le lien");
  refresh.type = "button";
  refresh.addEventListener(
    "click",
    () => void requestLink(artifactId, kind === "download" ? "download" : "preview"),
  );
  block.append(refresh);
  return block;
}

// --- Tests ---------------------------------------------------------------------

function testsSection(): HTMLElement {
  const section = el("section", "content-section studio-tests");
  section.append(sectionHeader(
    "Résultats de tests",
    "Statuts conservés distinctement : réussi, échec, délai dépassé, ignoré, interrompu et instable.",
  ));

  if (state.testPhase === "loading") {
    section.append(statePanel("loading", "Chargement des tests", "Lecture du résultat structuré de la tentative…"));
    return section;
  }
  if (state.testPhase === "error" && state.testError) {
    section.append(errorPanel(state.testError, "Le résultat de tests", () => {
      if (state.runId) void loadTestRun(state.runId, loadSequence);
    }));
    return section;
  }
  if (state.testMissing || !state.testRun) {
    section.append(statePanel(
      "empty",
      "Aucun résultat de test",
      "Aucune exécution de tests n’est rattachée à cette tentative. Aucun succès n’est supposé.",
    ));
    return section;
  }

  const detail = state.testRun;
  const described = describeTestRunStatus(detail.status);
  const chips = el("div", "studio-chips");
  chips.append(
    statusChip(described.label, described.tone),
    statusChip(`${detail.runner} ${detail.runner_version}`.trim(), "waiting"),
  );
  section.append(chips);

  const facts = el("dl", "studio-facts");
  appendFact(facts, "Totaux", summarizeTestTotals(detail.totals));
  appendFact(facts, "Cas exécutés", String(detail.case_count));
  appendFact(facts, "Code de sortie", detail.exit_code === null ? "Inconnu" : String(detail.exit_code));
  appendFact(facts, "Début", formatDateTime(detail.started_at));
  appendFact(facts, "Fin", detail.finished_at ? formatDateTime(detail.finished_at) : "En cours");
  appendFact(facts, "Durée", formatTestDuration(detail.duration_ms));
  section.append(facts);

  if (detail.case_count === 0) {
    section.append(statePanel(
      "empty",
      "Aucune assertion exécutée",
      "L’exécution n’a produit aucun cas de test : ce résultat ne vaut pas un succès.",
    ));
  }

  const tree = buildTestTree(detail.cases);
  if (tree.length) {
    const container = el("div", "studio-tree");
    for (const node of tree) container.append(suiteNode(node, 0));
    section.append(container);
  }

  if (detail.report_artifact) {
    const report = el("div", "studio-report");
    report.append(el("h4", "studio-subheading", "Rapport d’exécution"));
    report.append(artifactFacts(detail.report_artifact));
    report.append(mediaBlock(
      detail.report_artifact.id,
      detail.report_artifact.content_type,
      artifactName(detail.report_artifact),
    ));
    section.append(report);
  }
  return section;
}

function suiteNode(node: TestSuiteNode, depth: number): HTMLElement {
  const block = el("section", "studio-suite");
  block.dataset.depth = String(depth);
  const header = el("div", "studio-suite-header");
  header.append(el("h4", "studio-suite-title", node.title));
  const chips = el("div", "studio-chips");
  chips.append(statusChip(`${node.caseCount} cas`, "waiting"));
  if (node.unexpectedCount > 0) {
    chips.append(statusChip(`${node.unexpectedCount} inattendu(s)`, "failed"));
  }
  header.append(chips);
  block.append(header);

  for (const item of node.cases) block.append(caseRow(item));
  for (const child of node.suites) block.append(suiteNode(child, depth + 1));
  return block;
}

function caseRow(item: TestCaseResult): HTMLElement {
  const row = el("article", "studio-case");
  const badge = testCaseBadge(item);
  const header = el("div", "studio-case-header");
  header.append(el("h5", "studio-case-title", item.title));
  const chips = el("div", "studio-chips");
  chips.append(statusChip(badge.label, badge.tone));
  chips.append(statusChip(`statut ${item.status}`, "waiting"));
  chips.append(statusChip(`résultat ${item.outcome}`, "waiting"));
  if (item.attempt > 1) chips.append(statusChip(`tentative ${item.attempt}`, "waiting"));
  header.append(chips);
  row.append(header);

  const meta = el("div", "studio-case-meta");
  meta.append(el("span", "studio-event-tag", formatTestDuration(item.duration_ms)));
  if (item.project_name) meta.append(el("span", "studio-event-tag", item.project_name));
  const location = formatLocation(item);
  if (location) meta.append(el("span", "studio-event-tag", location));
  if (item.expected_status && item.expected_status !== "passed") {
    meta.append(el("span", "studio-event-tag", `attendu : ${item.expected_status}`));
  }
  row.append(meta);

  if (item.error_message) {
    const pre = el("pre", "studio-pre studio-error");
    pre.textContent = item.error_message;
    row.append(pre);
  }
  if (item.error_snippet) {
    const details = el("details", "studio-payload");
    details.append(el("summary", "", "Extrait de code"));
    const pre = el("pre", "studio-pre");
    pre.textContent = item.error_snippet;
    details.append(pre);
    row.append(details);
  }
  if (item.steps.length) {
    const details = el("details", "studio-payload");
    details.open = state.expandedCases.has(item.id);
    details.append(el("summary", "", `Étapes (${item.steps.length})`));
    details.addEventListener("toggle", () => {
      if (details.open) state.expandedCases.add(item.id);
      else state.expandedCases.delete(item.id);
    });
    const list = el("ol", "studio-step-list");
    for (const step of item.steps) {
      const entry = el("li", "studio-step");
      entry.append(el("span", "studio-step-title", step.title));
      if (step.category) entry.append(el("span", "studio-event-tag", step.category));
      entry.append(el("span", "studio-event-tag", formatTestDuration(step.duration_ms)));
      if (step.error) entry.append(statusChip("étape en erreur", "failed"));
      list.append(entry);
    }
    details.append(list);
    row.append(details);
  }
  if (item.annotations.length) {
    const details = el("details", "studio-payload");
    details.append(el("summary", "", `Annotations (${item.annotations.length})`));
    const pre = el("pre", "studio-pre");
    pre.textContent = safeJson(item.annotations);
    details.append(pre);
    row.append(details);
  }
  if (item.attachments.length) {
    const attachments = el("div", "studio-attachments");
    attachments.append(el("h6", "studio-subheading", `Pièces jointes (${item.attachments.length})`));
    for (const artifact of item.attachments) attachments.append(attachmentRow(artifact));
    row.append(attachments);
  }
  return row;
}

function formatLocation(item: TestCaseResult): string {
  const file = item.location.file;
  if (typeof file !== "string" || !file) return "";
  const line = item.location.line;
  return typeof line === "number" ? `${file}:${line}` : file;
}

function artifactFacts(artifact: ArtifactSummary): HTMLElement {
  const facts = el("dl", "studio-facts");
  appendFact(facts, "Fichier", artifactName(artifact));
  appendFact(facts, "Type", artifact.content_type);
  appendFact(facts, "Taille", formatArtifactSize(artifact.size_bytes));
  appendFact(facts, "Provenance", artifact.source);
  if (artifact.checksum) appendFact(facts, "Empreinte", artifact.checksum);
  if (artifact.created_at) appendFact(facts, "Publié le", formatDateTime(artifact.created_at));
  return facts;
}

function attachmentRow(artifact: ArtifactSummary): HTMLElement {
  const row = el("div", "studio-attachment");
  row.append(artifactFacts(artifact));
  if (!artifact.has_content) {
    row.append(statePanel(
      "empty",
      "Contenu absent",
      "Cet artefact n’a que des métadonnées : aucun fichier n’a été téléversé pour cette tentative.",
    ));
    return row;
  }
  row.append(mediaBlock(artifact.id, artifact.content_type, artifactName(artifact)));
  return row;
}

// --- Prise de contrôle : non livrée ---------------------------------------------

function handoverSection(): HTMLElement {
  const section = el("section", "content-section studio-handover");
  section.append(statePanel(
    "unconfigured",
    "Prise de contrôle non livrée",
    "Le Studio est en lecture seule dans cette version : aucune reprise de la main sur le navigateur "
    + "de la tentative n’est possible, et aucun bouton ne le laisse croire. La capacité est prévue "
    + "pour un lot ultérieur.",
  ));
  return section;
}

// --- Point d’entrée -------------------------------------------------------------

/**
 * Rend le Studio d’une tentative dans `container`.
 *
 * `sharedHttp` est le client du shell : le passer est **la** façon correcte de câbler ce
 * module (jeton CSRF partagé ; relire `/auth/session` ferait tourner le jeton et
 * invaliderait celui des autres écrans). `runId` est l’identifiant de la tentative
 * (`task_run_id`), résolu par le shell.
 *
 * L’appel est idempotent : repeindre la route ne relance ni le chargement ni le flux tant
 * que la tentative affichée ne change pas.
 */
export function renderStudio(
  container: HTMLElement,
  sharedHttp: WorkspaceHttpClient,
  runId: string,
  options: StudioOptions = {},
): void {
  const changed = state.runId !== runId || http !== sharedHttp;
  http = sharedHttp;
  createLink = options.createArtifactLink ?? null;
  if (changed) {
    clearLinkExpiryTimer();
    subscription?.close();
    subscription = null;
    loadSequence += 1;
    Object.assign(state, initialState());
    state.runId = runId;
    events = new EventsApiClient(sharedHttp);
    testing = new TestingApiClient(sharedHttp);
  }
  mount = el("div", "studio");
  container.append(mount);
  paint();
  if (state.phase === "idle") void loadStudio(runId);
}

/**
 * Efface tout ce que ce module retient d’un compte — journal, résultats de tests, liens
 * signés — et **ferme le flux `EventSource`**.
 *
 * Le shell doit l’appeler à la connexion et à la déconnexion, comme `resetSkillsUiState()`,
 * et lorsqu’il quitte l’écran du Studio : sans cela, une connexion SSE resterait ouverte et
 * la chronologie d’un compte précédent pourrait être repeinte.
 */
export function resetStudioUiState(): void {
  loadSequence += 1;
  clearLinkExpiryTimer();
  subscription?.close();
  subscription = null;
  Object.assign(state, initialState());
  mount = null;
  http = null;
  events = null;
  testing = null;
  createLink = null;
  paintScheduled = false;
}
