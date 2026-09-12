/**
 * Centre MCP et coffre de secrets (route « Connexions », spec Lot D §7).
 *
 * Règles appliquées ici :
 * - aucune donnée simulée : chaque écran affiche ce que l’API a réellement
 *   renvoyé, ou un état explicite (chargement, vide, hors ligne, refus, réponse
 *   inexploitable, coffre non configuré) ;
 * - aucune valeur de secret n’est affichée ni conservée : la configuration ne
 *   montre que des références (`secret_id`), et une valeur saisie dans un
 *   formulaire est effacée du champ dès l’envoi ;
 * - les contenus importés (descriptions d’outils, schémas JSON, sorties de
 *   probe) sont des données non fiables : ils sont insérés en `textContent`
 *   (jamais en HTML) et les schémas restent dans des `<pre>` ;
 * - les statuts portent toujours un libellé et une icône textuelle, jamais une
 *   couleur seule ;
 * - une seule session HTTP : le module utilise le client de l’appelant (le shell)
 *   quand il en reçoit un et ne lit jamais `/auth/session` à l’ouverture de la route,
 *   car cette lecture fait tourner le jeton CSRF côté serveur et invaliderait les
 *   écritures des autres écrans ;
 * - rien du compte précédent ne survit : `resetMcpUiState()` vide l’état du module et
 *   chaque montage relit l’API ;
 * - aucun bouton sans action réelle : une action indisponible est absente ou
 *   désactivée avec la raison affichée.
 */

import type {
  McpBinding,
  McpCatalogEntry,
  McpDiscoveredTool,
  McpExport,
  McpExportFormat,
  McpImportApplyResult,
  McpImportEntry,
  McpImportFormat,
  McpImportPreview,
  McpImportSecretCandidate,
  McpProbe,
  McpProbeStatus,
  McpServerConfig,
  McpServerDetail,
  McpServerRevision,
  McpServerStatus,
  McpServerSummary,
  McpTransport,
  Project,
  SecretRef,
  SecretScopeType,
  SecretSummary,
  SecretsStatus,
} from "@acp/contracts";

import "./mcp.css";
import { AuthApiClient } from "./auth-api";
import {
  MCP_IMPORT_FORMATS,
  MCP_IMPORT_MAX_CHARS,
  McpApiClient,
  type RunnerSummary,
} from "./mcp-api";
import { SecretsApiClient } from "./secrets-api";
import {
  el,
  errorMessage,
  formatDateTime,
  labeledField,
  normalizeApiError,
  sectionHeader,
  statePanel,
  statusChip,
  type StatePanelTone,
} from "./ui-primitives";
import {
  WorkspaceApiClient,
  WorkspaceApiError,
  WorkspaceHttpClient,
  type Validator,
} from "./workspace-api";

// --- clients partagés par les deux panneaux de la route ---------------------

/** Rôle de plateforme du compte connecté, tel que le shell l’a lu. */
export type PlatformRole = "owner" | "operator" | "viewer";

/**
 * Client de repli, utilisé uniquement quand l’appelant n’en fournit pas.
 *
 * `GET /auth/session` fait **tourner** le jeton CSRF côté serveur (un seul jeton est
 * valide à la fois) : un second client qui relit la session invaliderait celui du shell
 * et ferait échouer ses écritures en 403 jusqu’au rechargement de la page. Le module
 * partage donc le client de l’appelant dès qu’il en reçoit un ; sans client fourni, il
 * ne relit la session qu’au moment où une écriture part réellement sur le réseau —
 * jamais à l’ouverture de la route, jamais pour un refus purement local.
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
let mcpApi = new McpApiClient({ http });
let secretsApi = new SecretsApiClient({ http });
let authApi = new AuthApiClient({ http });
let workspaceApi = new WorkspaceApiClient({ http });

/** Vrai seulement quand ce module possède son client et lui a déjà posé un jeton CSRF. */
let csrfReady = false;
/** `null` = rôle inconnu : le module ne pré-filtre alors rien, le serveur tranche. */
let platformRole: PlatformRole | null = null;

/**
 * Adopte le client HTTP de l’appelant (le shell) ou retombe sur celui du module.
 * Changer de client remet le jeton à vérifier : les jetons ne sont pas interchangeables.
 */
function useHttpClient(client: WorkspaceHttpClient | undefined): void {
  const next = client ?? fallbackHttp;
  if (next === http) return;
  http = next;
  mcpApi = new McpApiClient({ http });
  secretsApi = new SecretsApiClient({ http });
  authApi = new AuthApiClient({ http });
  workspaceApi = new WorkspaceApiClient({ http });
  csrfReady = false;
}

/** Le propriétaire d’un client injecté gère lui-même son jeton : ce module n’y touche pas. */
function ownsHttpClient(): boolean {
  return http === fallbackHttp;
}

/**
 * Pose le jeton CSRF au moment où une écriture part sur le réseau (appelée par
 * `LazyCsrfHttpClient`), et uniquement si ce module possède son client.
 */
async function ensureCsrf(): Promise<void> {
  if (!ownsHttpClient() || csrfReady) return;
  await authApi.fetchSession();
  csrfReady = true;
}

/**
 * Un 403 peut venir d’un jeton devenu invalide (une autre partie de l’application a relu
 * la session). On réarme alors la demande pour que la tentative suivante reparte d’un
 * jeton frais, au lieu d’échouer définitivement jusqu’au rechargement de la page.
 */
function invalidateCsrfOnRefusal(error: WorkspaceApiError): void {
  if (error.kind === "forbidden") csrfReady = false;
}

/** Le rôle est fourni par le shell à chaque rendu : il ne survit pas à un changement de compte. */
function useRole(role: PlatformRole | null | undefined): void {
  platformRole = role ?? null;
}

/** Rôle propriétaire **confirmé** (sert uniquement à expliquer une restriction). */
function isOwner(): boolean {
  return platformRole === "owner";
}

/**
 * Vrai tant qu’aucun rôle connu n’interdit l’action : rôle inconnu ⇒ on propose l’action
 * et c’est l’API qui tranche (403 affiché tel quel), plutôt que de masquer une capacité
 * réelle sur une supposition.
 */
function mayManagePlatform(): boolean {
  return platformRole === null || platformRole === "owner";
}

// --- états de module --------------------------------------------------------

type Phase = "idle" | "loading" | "ready" | "error";
type NoticeTone = "success" | "warning" | "error" | "pending";
interface Notice { tone: NoticeTone; message: string }

type McpTab = "servers" | "add" | "catalog" | "export" | "import";

interface McpState {
  phase: Phase;
  error: WorkspaceApiError | null;
  tab: McpTab;
  statusFilter: McpServerStatus | "";
  servers: McpServerSummary[];
  pendingProbes: McpProbe[];
  pendingProbesError: WorkspaceApiError | null;
  projects: Project[];
  projectsError: WorkspaceApiError | null;
  runners: RunnerSummary[];
  runnersError: WorkspaceApiError | null;
  catalogPhase: Phase;
  catalog: McpCatalogEntry[];
  catalogError: WorkspaceApiError | null;
  selectedServerId: string | null;
  detailPhase: Phase;
  detail: McpServerDetail | null;
  detailError: WorkspaceApiError | null;
  exportPhase: Phase;
  exportResult: McpExport | null;
  exportError: WorkspaceApiError | null;
  prefill: McpCatalogEntry | null;
  notice: Notice | null;
  busy: boolean;
  revokeOpen: boolean;
}

/** État initial : sert au premier rendu et à `resetMcpUiState()` (changement de compte). */
function initialMcpState(): McpState {
  return {
    phase: "idle",
    error: null,
    tab: "servers",
    statusFilter: "",
    servers: [],
    pendingProbes: [],
    pendingProbesError: null,
    projects: [],
    projectsError: null,
    runners: [],
    runnersError: null,
    catalogPhase: "idle",
    catalog: [],
    catalogError: null,
    selectedServerId: null,
    detailPhase: "idle",
    detail: null,
    detailError: null,
    exportPhase: "idle",
    exportResult: null,
    exportError: null,
    prefill: null,
    notice: null,
    busy: false,
    revokeOpen: false,
  };
}

const mcpState: McpState = initialMcpState();

interface SecretsState {
  phase: Phase;
  error: WorkspaceApiError | null;
  vault: SecretsStatus | null;
  secrets: SecretSummary[];
  notice: Notice | null;
  rotatingId: string | null;
  busy: boolean;
}

function initialSecretsState(): SecretsState {
  return {
    phase: "idle",
    error: null,
    vault: null,
    secrets: [],
    notice: null,
    rotatingId: null,
    busy: false,
  };
}

const secretsState: SecretsState = initialSecretsState();

/** Outils cochés dans le détail courant (conservés entre deux rendus). */
const selectedTools = new Set<string>();

let mcpRoot: HTMLElement | null = null;
let secretsRoot: HTMLElement | null = null;

// --- libellés et tonalités --------------------------------------------------

const SERVER_STATUS_LABELS: Record<McpServerStatus, string> = {
  draft: "Brouillon",
  active: "Actif",
  disabled: "Désactivé",
  revoked: "Révoqué",
};

const SERVER_STATUS_TONES: Record<McpServerStatus, string> = {
  draft: "queued",
  active: "active",
  disabled: "blocked",
  revoked: "failed",
};

const SERVER_STATUS_ICONS: Record<McpServerStatus, string> = {
  draft: "○",
  active: "✓",
  disabled: "!",
  revoked: "✗",
};

const PROBE_STATUS_LABELS: Record<McpProbeStatus, string> = {
  pending_approval: "Autorisation demandée",
  queued: "En file",
  claimed: "Pris par un runner",
  succeeded: "Diagnostic réussi",
  failed: "Diagnostic en échec",
  rejected: "Refusé",
  expired: "Expiré",
  invalidated: "Invalidé",
  cancelled: "Annulé",
};

const PROBE_STATUS_TONES: Record<McpProbeStatus, string> = {
  pending_approval: "waiting",
  queued: "queued",
  claimed: "in_progress",
  succeeded: "active",
  failed: "failed",
  rejected: "failed",
  expired: "blocked",
  invalidated: "blocked",
  cancelled: "blocked",
};

const PROBE_STATUS_ICONS: Record<McpProbeStatus, string> = {
  pending_approval: "!",
  queued: "…",
  claimed: "→",
  succeeded: "✓",
  failed: "✗",
  rejected: "✗",
  expired: "!",
  invalidated: "!",
  cancelled: "○",
};

const TRANSPORT_LABELS: Record<McpTransport, string> = {
  http: "HTTP (Streamable)",
  stdio: "stdio (processus local)",
};

const SOURCE_LABELS: Record<string, string> = {
  catalog: "Catalogue vérifié",
  remote_url: "URL distante",
  import: "Import",
  manual: "Saisie manuelle",
};

const RISK_LEVEL_LABELS: Record<string, string> = {
  info: "Information",
  caution: "Vigilance",
  danger: "Danger",
};

const RISK_LEVEL_TONES: Record<string, string> = {
  info: "queued",
  caution: "waiting",
  danger: "failed",
};

const EXPORT_FORMAT_LABELS: Record<McpExportFormat, string> = {
  hermes: "Hermes (~/.hermes/config.yaml)",
  claude: "Claude Code (.mcp.json)",
  codex: "Codex (config.toml)",
};

function serverStatusChip(status: McpServerStatus): HTMLElement {
  return statusChip(
    `${SERVER_STATUS_ICONS[status]} ${SERVER_STATUS_LABELS[status]}`,
    SERVER_STATUS_TONES[status],
  );
}

function probeStatusChip(status: McpProbeStatus): HTMLElement {
  return statusChip(
    `${PROBE_STATUS_ICONS[status]} ${PROBE_STATUS_LABELS[status]}`,
    PROBE_STATUS_TONES[status],
  );
}

function discoveryChip(current: boolean): HTMLElement {
  return current
    ? statusChip("✓ Découverte à jour", "active")
    : statusChip("! Découverte à refaire", "waiting");
}

function locationLabel(server: Pick<McpServerSummary, "execution_location" | "target_worker_id">): string {
  return server.execution_location === "runner"
    ? `Exécution : runner${server.target_worker_id ? ` ${server.target_worker_id}` : " (non désigné)"}`
    : "Exécution : API de la plateforme";
}

// --- petits utilitaires de rendu -------------------------------------------

function optionalDateTime(value: string | null, fallback = "jamais"): string {
  return value ? formatDateTime(value) : fallback;
}

function panelTone(error: WorkspaceApiError): StatePanelTone {
  if (error.kind === "offline") return "offline";
  if (error.kind === "forbidden") return "forbidden";
  return "error";
}

function panelTitle(error: WorkspaceApiError): string {
  if (error.kind === "offline") return "API hors ligne";
  if (error.kind === "forbidden") {
    return error.status === 403 ? "Accès refusé : réservé au propriétaire" : "Session expirée";
  }
  if (error.kind === "invalid_response") return "Réponse inexploitable";
  return "Erreur de l’API";
}

function panelMessage(error: WorkspaceApiError): string {
  const base = errorMessage(error);
  if (error.kind === "forbidden" && error.status === 403) {
    return `${base} La configuration des serveurs MCP est réservée au propriétaire de la plateforme.`;
  }
  return base;
}

function errorPanel(error: WorkspaceApiError, onRetry?: () => void): HTMLElement {
  return statePanel(panelTone(error), panelTitle(error), panelMessage(error), onRetry);
}

function noticeNode(notice: Notice | null): HTMLElement {
  const node = el("div", "form-feedback mcp-notice");
  node.setAttribute("aria-live", "polite");
  if (notice) {
    node.dataset.tone = notice.tone;
    node.textContent = notice.message;
  }
  return node;
}

function block(title: string, hint = ""): HTMLElement {
  const node = el("section", "mcp-block");
  node.append(el("h3", "mcp-block-title", title));
  if (hint) node.append(el("p", "mcp-block-hint", hint));
  return node;
}

function keyValueList(entries: Array<[string, string | HTMLElement]>): HTMLElement {
  const list = el("dl", "mcp-kv");
  for (const [term, value] of entries) {
    list.append(el("dt", "", term));
    if (typeof value === "string") {
      list.append(el("dd", "", value));
    } else {
      const cell = el("dd");
      cell.append(value);
      list.append(cell);
    }
  }
  return list;
}

/** Bloc de texte non fiable : jamais d’HTML, toujours `textContent`. */
function preBlock(text: string, compact = false): HTMLElement {
  const node = el("pre", compact ? "mcp-pre compact" : "mcp-pre");
  node.textContent = text;
  node.tabIndex = 0;
  return node;
}

function jsonBlock(value: unknown, compact = true): HTMLElement {
  let text: string;
  try {
    text = JSON.stringify(value, null, 2) ?? "null";
  } catch {
    text = "Contenu non sérialisable.";
  }
  return preBlock(text, compact);
}

function bulletList(items: readonly string[]): HTMLElement {
  const list = el("ul", "mcp-plain-list bulleted");
  for (const item of items) list.append(el("li", "", item));
  return list;
}

function actionButton(
  label: string,
  variant: "primary" | "secondary",
  onClick: () => void,
  options: { disabled?: boolean; title?: string } = {},
): HTMLButtonElement {
  const button = el("button", `button button-${variant}`, label);
  button.type = "button";
  button.disabled = Boolean(options.disabled);
  if (options.title) button.title = options.title;
  button.addEventListener("click", onClick);
  return button;
}

function textInput(name: string, options: {
  value?: string;
  placeholder?: string;
  required?: boolean;
  maxLength?: number;
  type?: string;
  autocomplete?: AutoFill;
} = {}): HTMLInputElement {
  const input = el("input", "form-control");
  input.name = name;
  input.type = options.type ?? "text";
  if (options.value !== undefined) input.value = options.value;
  if (options.placeholder) input.placeholder = options.placeholder;
  if (options.required) input.required = true;
  if (options.maxLength) input.maxLength = options.maxLength;
  if (options.autocomplete) input.autocomplete = options.autocomplete;
  return input;
}

function numberInput(name: string, value: number, min: number, max: number): HTMLInputElement {
  const input = el("input", "form-control");
  input.name = name;
  input.type = "number";
  input.min = String(min);
  input.max = String(max);
  input.value = String(value);
  input.required = true;
  return input;
}

function textArea(name: string, rows: number, options: {
  value?: string;
  placeholder?: string;
  required?: boolean;
  maxLength?: number;
} = {}): HTMLTextAreaElement {
  const area = el("textarea", "form-control form-textarea");
  area.name = name;
  area.rows = rows;
  if (options.value) area.value = options.value;
  if (options.placeholder) area.placeholder = options.placeholder;
  if (options.required) area.required = true;
  if (options.maxLength) area.maxLength = options.maxLength;
  return area;
}

function selectControl(
  name: string,
  options: ReadonlyArray<{ value: string; label: string; selected?: boolean; disabled?: boolean }>,
): HTMLSelectElement {
  const select = el("select", "form-control");
  select.name = name;
  for (const entry of options) {
    const option = el("option", "", entry.label);
    option.value = entry.value;
    if (entry.selected) option.selected = true;
    if (entry.disabled) option.disabled = true;
    select.append(option);
  }
  return select;
}

/**
 * Groupe de champs composites (éditeur clé/valeur) : `labeledField` associe un
 * `<label for>` à un contrôle unique, ce qui n’a pas de sens ici. Le groupe porte
 * donc son nom accessible via `role="group"` + `aria-label`.
 */
function fieldGroup(title: string, node: HTMLElement, hint = ""): HTMLElement {
  const group = el("div", "form-field");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", title);
  group.append(el("p", "form-label", title), node);
  if (hint) group.append(el("p", "form-hint", hint));
  return group;
}

function projectLabel(projectId: string): string {
  const project = mcpState.projects.find((candidate) => candidate.id === projectId);
  return project ? project.name : `Projet ${projectId}`;
}

function secretLabel(secretId: string): string {
  const secret = secretsState.secrets.find((candidate) => candidate.id === secretId);
  return secret ? secret.name : `secret ${secretId}`;
}

function shortFingerprint(fingerprint: string): string {
  return fingerprint.length > 16 ? `${fingerprint.slice(0, 16)}…` : fingerprint;
}

function confirmAction(message: string): boolean {
  const ask = globalThis.confirm?.bind(globalThis);
  return ask ? ask(message) : true;
}

// --- chargement des données -------------------------------------------------

function paintAll(): void {
  paintMcp();
  paintSecrets();
}

/** Empêche deux chargements concurrents (le shell peut re-rendre la route). */
let mcpLoading = false;
let secretsLoading = false;
/**
 * Incrémenté par `resetMcpUiState()`. Une réponse partie avant une déconnexion appartient
 * au compte précédent : elle est jetée au lieu d’être écrite dans l’état du compte suivant.
 */
let stateGeneration = 0;

/**
 * Recharge la route. `silent` sert au rechargement déclenché par un montage : les
 * données déjà affichées (réelles, issues d’une réponse précédente) restent visibles
 * pendant la relecture, au lieu de clignoter vers un écran de chargement.
 */
async function loadMcp(options: { silent?: boolean } = {}): Promise<void> {
  if (mcpLoading) return;
  mcpLoading = true;
  const generation = stateGeneration;
  const silent = Boolean(options.silent) && mcpState.phase === "ready";
  if (!silent) mcpState.phase = "loading";
  mcpState.error = null;
  paintMcp();

  try {
    // Aucune lecture de session ici : elle ferait tourner le jeton CSRF partagé (cf. `ensureCsrf`).
    const servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
    if (generation !== stateGeneration) return;
    mcpState.servers = servers;
    mcpState.phase = "ready";
  } catch (error) {
    if (generation !== stateGeneration) return;
    mcpState.error = normalizeApiError(error, "La liste des serveurs MCP n’a pas pu être lue.");
    mcpState.phase = "error";
    mcpLoading = false;
    paintMcp();
    return;
  }

  // Lectures secondaires : un échec n’efface jamais la liste principale.
  try {
    const probes = await mcpApi.listProbes("pending_approval");
    if (generation !== stateGeneration) return;
    mcpState.pendingProbes = probes;
    mcpState.pendingProbesError = null;
  } catch (error) {
    if (generation !== stateGeneration) return;
    mcpState.pendingProbes = [];
    mcpState.pendingProbesError = normalizeApiError(error, "Les autorisations en attente n’ont pas pu être lues.");
  }
  try {
    const overview = await workspaceApi.fetchOverview();
    if (generation !== stateGeneration) return;
    mcpState.projects = [...overview.projects];
    mcpState.projectsError = null;
  } catch (error) {
    if (generation !== stateGeneration) return;
    mcpState.projects = [];
    mcpState.projectsError = normalizeApiError(error, "La liste des projets n’a pas pu être lue.");
  }
  try {
    const runners = await mcpApi.fetchRunners();
    if (generation !== stateGeneration) return;
    mcpState.runners = runners;
    mcpState.runnersError = null;
  } catch (error) {
    if (generation !== stateGeneration) return;
    mcpState.runners = [];
    mcpState.runnersError = normalizeApiError(error, "La liste des runners n’a pas pu être lue.");
  }

  if (secretsState.phase === "idle") {
    void loadSecrets();
  }
  if (mcpState.selectedServerId) {
    await reloadDetail(mcpState.selectedServerId);
  }
  if (generation !== stateGeneration) return;
  mcpLoading = false;
  paintAll();
}

async function reloadDetail(serverId: string): Promise<void> {
  const generation = stateGeneration;
  mcpState.detailPhase = "loading";
  paintMcp();
  try {
    const detail = await mcpApi.fetchServer(serverId);
    if (generation !== stateGeneration) return;
    mcpState.detail = detail;
    mcpState.detailError = null;
    mcpState.detailPhase = "ready";
  } catch (error) {
    if (generation !== stateGeneration) return;
    mcpState.detail = null;
    mcpState.detailError = normalizeApiError(error, "Le détail du serveur n’a pas pu être lu.");
    mcpState.detailPhase = "error";
  }
}

async function loadCatalog(): Promise<void> {
  const generation = stateGeneration;
  mcpState.catalogPhase = "loading";
  paintMcp();
  try {
    const catalog = await mcpApi.fetchCatalog();
    if (generation !== stateGeneration) return;
    mcpState.catalog = catalog;
    mcpState.catalogError = null;
    mcpState.catalogPhase = "ready";
  } catch (error) {
    if (generation !== stateGeneration) return;
    mcpState.catalog = [];
    mcpState.catalogError = normalizeApiError(error, "Le catalogue n’a pas pu être lu.");
    mcpState.catalogPhase = "error";
  }
  paintMcp();
}

async function loadSecrets(options: { silent?: boolean } = {}): Promise<void> {
  if (secretsLoading) return;
  secretsLoading = true;
  const generation = stateGeneration;
  const silent = Boolean(options.silent) && secretsState.phase === "ready";
  if (!silent) secretsState.phase = "loading";
  secretsState.error = null;
  paintSecrets();
  try {
    // Aucune lecture de session ici non plus (cf. `ensureCsrf`).
    const vault = await secretsApi.fetchStatus();
    const secrets = await secretsApi.listSecrets();
    if (generation !== stateGeneration) return;
    secretsState.vault = vault;
    secretsState.secrets = secrets;
    secretsState.phase = "ready";
  } catch (error) {
    if (generation !== stateGeneration) return;
    secretsState.error = normalizeApiError(error, "Le coffre de secrets n’a pas pu être lu.");
    secretsState.phase = "error";
  } finally {
    if (generation === stateGeneration) secretsLoading = false;
  }
  if (generation !== stateGeneration) return;
  paintAll();
}

function selectServer(serverId: string | null): void {
  mcpState.selectedServerId = serverId;
  mcpState.detail = null;
  mcpState.detailError = null;
  mcpState.detailPhase = serverId ? "loading" : "idle";
  mcpState.revokeOpen = false;
  selectedTools.clear();
  if (serverId) {
    void reloadDetail(serverId).then(paintMcp);
  }
  paintMcp();
}

/** Exécute une mutation en affichant son déroulement, sans jamais feindre le succès. */
async function runMcpAction(pending: string, action: () => Promise<Notice>): Promise<void> {
  if (mcpState.busy) return;
  mcpState.busy = true;
  mcpState.notice = { tone: "pending", message: pending };
  paintMcp();
  try {
    mcpState.notice = await action();
  } catch (error) {
    const apiError = normalizeApiError(error, "L’action n’a pas pu être exécutée.");
    invalidateCsrfOnRefusal(apiError);
    mcpState.notice = { tone: "error", message: `${panelTitle(apiError)} — ${panelMessage(apiError)}` };
  } finally {
    mcpState.busy = false;
    paintMcp();
  }
}

async function runSecretsAction(pending: string, action: () => Promise<Notice>): Promise<void> {
  if (secretsState.busy) return;
  secretsState.busy = true;
  secretsState.notice = { tone: "pending", message: pending };
  paintSecrets();
  try {
    secretsState.notice = await action();
  } catch (error) {
    const apiError = normalizeApiError(error, "L’action n’a pas pu être exécutée.");
    invalidateCsrfOnRefusal(apiError);
    secretsState.notice = { tone: "error", message: `${panelTitle(apiError)} — ${panelMessage(apiError)}` };
  } finally {
    secretsState.busy = false;
    paintAll();
  }
}

// --- éditeur clé / valeur (en-têtes HTTP, variables d’environnement) --------

type KeyValueMode = "literal" | "secret";

interface KeyValueEditor {
  node: HTMLElement;
  addRow(key?: string, mode?: KeyValueMode, value?: string): void;
  read(): { literal: Record<string, string>; secrets: Record<string, SecretRef> };
}

function availableSecrets(): SecretSummary[] {
  return secretsState.secrets.filter((secret) => !secret.revoked_at);
}

/**
 * Chaque ligne choisit entre une valeur littérale (non secrète) et une référence
 * vers un secret existant. Aucune valeur secrète n’est saisie ici : le coffre est
 * le seul endroit où une valeur est transmise.
 */
function createKeyValueEditor(kind: "header" | "env"): KeyValueEditor {
  const node = el("div", "mcp-kv-editor");
  const rows = el("div", "mcp-kv-rows");
  const empty = el("p", "mcp-kv-empty", kind === "header"
    ? "Aucun en-tête déclaré."
    : "Aucune variable d’environnement déclarée.");
  const secrets = availableSecrets();
  const entries: Array<{
    row: HTMLElement;
    key: HTMLInputElement;
    mode: HTMLSelectElement;
    literal: HTMLInputElement;
    secret: HTMLSelectElement;
  }> = [];

  function refreshEmpty(): void {
    empty.hidden = entries.length > 0;
  }

  function addRow(key = "", mode: KeyValueMode = "literal", value = ""): void {
    const row = el("div", "mcp-kv-row");
    const keyInput = textInput(`${kind}-key`, {
      placeholder: kind === "header" ? "Authorization" : "GITHUB_TOKEN",
      maxLength: 200,
    });
    keyInput.value = key;
    keyInput.setAttribute("aria-label", kind === "header" ? "Nom de l’en-tête" : "Nom de la variable");

    const modeSelect = selectControl(`${kind}-mode`, [
      { value: "literal", label: "Valeur littérale", selected: mode === "literal" },
      {
        value: "secret",
        label: secrets.length ? "Secret existant" : "Secret existant (aucun disponible)",
        selected: mode === "secret" && secrets.length > 0,
        disabled: secrets.length === 0,
      },
    ]);
    modeSelect.setAttribute("aria-label", "Type de valeur");

    const literalInput = textInput(`${kind}-value`, {
      placeholder: "Valeur non secrète",
      maxLength: 2000,
    });
    literalInput.value = value;
    literalInput.setAttribute("aria-label", "Valeur littérale (non secrète)");

    const secretSelect = selectControl(`${kind}-secret`, secrets.map((secret) => ({
      value: secret.id,
      label: `${secret.name}${secret.scope_type === "project" ? " (projet)" : ""}`,
      selected: secret.id === value,
    })));
    secretSelect.setAttribute("aria-label", "Secret du coffre");

    function applyMode(): void {
      const secretMode = modeSelect.value === "secret";
      literalInput.hidden = secretMode;
      literalInput.disabled = secretMode;
      secretSelect.hidden = !secretMode;
      secretSelect.disabled = !secretMode;
    }
    modeSelect.addEventListener("change", applyMode);

    const remove = actionButton("Retirer", "secondary", () => {
      const index = entries.findIndex((entry) => entry.row === row);
      if (index >= 0) entries.splice(index, 1);
      row.remove();
      refreshEmpty();
    });
    remove.setAttribute("aria-label", `Retirer la ligne ${kind === "header" ? "d’en-tête" : "d’environnement"}`);

    row.append(keyInput, modeSelect, literalInput, secretSelect, remove);
    entries.push({ row, key: keyInput, mode: modeSelect, literal: literalInput, secret: secretSelect });
    rows.append(row);
    applyMode();
    refreshEmpty();
  }

  const add = actionButton(
    kind === "header" ? "Ajouter un en-tête" : "Ajouter une variable",
    "secondary",
    () => addRow(),
  );
  const footer = el("div", "mcp-actions");
  footer.append(add);
  if (!secrets.length) {
    footer.append(el(
      "p",
      "form-hint",
      secretsState.vault?.configured === false
        ? "Coffre non configuré : seules des valeurs littérales non secrètes sont possibles pour l’instant."
        : "Aucun secret disponible : crée-le dans le coffre ci-dessous pour pouvoir le référencer.",
    ));
  }

  node.append(rows, empty, footer);
  refreshEmpty();

  return {
    node,
    addRow,
    read(): { literal: Record<string, string>; secrets: Record<string, SecretRef> } {
      const literal: Record<string, string> = {};
      const references: Record<string, SecretRef> = {};
      for (const entry of entries) {
        const key = entry.key.value.trim();
        if (!key) continue;
        if (entry.mode.value === "secret") {
          const secretId = entry.secret.value;
          if (secretId) references[key] = { secret_id: secretId };
        } else {
          literal[key] = entry.literal.value;
        }
      }
      return { literal, secrets: references };
    },
  };
}

// --- centre MCP : rendu -----------------------------------------------------

const MCP_TABS: ReadonlyArray<[McpTab, string]> = [
  ["servers", "Serveurs"],
  ["add", "Ajouter"],
  ["catalog", "Catalogue"],
  ["export", "Export"],
  ["import", "Import"],
];

/** Onglet à refocaliser après un rendu (navigation clavier du `tablist`). */
let pendingTabFocus: McpTab | null = null;

function selectTab(tab: McpTab, focus = false): void {
  mcpState.tab = tab;
  if (focus) pendingTabFocus = tab;
  if (tab === "catalog" && mcpState.catalogPhase === "idle") {
    void loadCatalog();
    return;
  }
  paintMcp();
}

function tabList(): HTMLElement {
  const list = el("ul", "mcp-tabs");
  list.setAttribute("role", "tablist");
  list.setAttribute("aria-label", "Sections du centre MCP");

  MCP_TABS.forEach(([tab, label], index) => {
    const item = el("li");
    item.setAttribute("role", "presentation");
    const button = el("button", "mcp-tab", label);
    button.type = "button";
    button.id = `mcp-tab-${tab}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", "mcp-tabpanel");
    const active = mcpState.tab === tab;
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    button.addEventListener("click", () => selectTab(tab));
    button.addEventListener("keydown", (event) => {
      const offset = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!offset) return;
      event.preventDefault();
      selectTab(MCP_TABS[(index + offset + MCP_TABS.length) % MCP_TABS.length][0], true);
    });
    item.append(button);
    list.append(item);
  });
  return list;
}

function serverRow(server: McpServerSummary): HTMLElement {
  const item = el("article", "list-item mcp-server-row");
  const copy = el("div", "list-item-copy");
  copy.append(
    el("h3", "list-item-title", server.display_name || server.name),
    el("p", "list-item-meta", `${server.name} · ${TRANSPORT_LABELS[server.transport]} · ${locationLabel(server)}`),
    el("p", "list-item-meta", [
      `Révision ${server.current_revision_number ?? "—"}`,
      `${server.tool_count} outil(s) découvert(s)`,
      `${server.binding_count} rattachement(s)`,
      SOURCE_LABELS[server.source_kind] ?? server.source_kind,
    ].join(" · ")),
  );
  if (server.description) copy.append(el("p", "list-item-meta", server.description));

  const chips = el("div", "mcp-chips");
  chips.append(serverStatusChip(server.status), discoveryChip(server.discovery_current));
  if (server.last_probe_status) chips.append(probeStatusChip(server.last_probe_status));
  copy.append(chips);

  const side = el("div", "mcp-row-side");
  side.append(actionButton("Ouvrir le détail", "secondary", () => selectServer(server.id)));
  side.append(el("p", "list-item-meta", `Dernier probe : ${optionalDateTime(server.last_probe_at)}`));

  item.append(copy, side);
  return item;
}

function pendingAuthorizationsBlock(): HTMLElement | null {
  if (mcpState.pendingProbesError) {
    const node = block("Autorisations de probe en attente");
    node.append(errorPanel(mcpState.pendingProbesError, () => void loadMcp()));
    return node;
  }
  if (!mcpState.pendingProbes.length) return null;
  const node = block(
    "Autorisations de probe en attente",
    "Un probe stdio lance un processus sur un runner : il n’est exécuté qu’après une décision explicite.",
  );
  const list = el("div", "mcp-card-list");
  for (const probe of mcpState.pendingProbes) {
    const card = el("article", "mcp-card");
    const head = el("div", "mcp-card-head");
    head.append(
      el("h4", "mcp-card-title", probe.authorization?.target ?? `Probe ${probe.id}`),
      probeStatusChip(probe.status),
    );
    card.append(
      head,
      el("p", "mcp-card-meta", `Demandé le ${formatDateTime(probe.created_at)} · expire le ${formatDateTime(probe.expires_at)}`),
      actionButton("Ouvrir le serveur concerné", "secondary", () => {
        selectTab("servers");
        selectServer(probe.server_id);
      }),
    );
    list.append(card);
  }
  node.append(list);
  return node;
}

function serversPanel(): HTMLElement {
  const wrapper = el("div", "mcp-panel-body");

  if (mcpState.selectedServerId) {
    wrapper.append(detailView());
    return wrapper;
  }

  const toolbar = el("div", "mcp-actions");
  const filter = selectControl("statusFilter", [
    { value: "", label: "Tous les statuts", selected: mcpState.statusFilter === "" },
    ...(["draft", "active", "disabled", "revoked"] as McpServerStatus[]).map((status) => ({
      value: status,
      label: SERVER_STATUS_LABELS[status],
      selected: mcpState.statusFilter === status,
    })),
  ]);
  filter.addEventListener("change", () => {
    mcpState.statusFilter = filter.value as McpServerStatus | "";
    void loadMcp();
  });
  toolbar.append(
    labeledField("Filtrer par statut", filter),
    actionButton("Actualiser", "secondary", () => void loadMcp(), { disabled: mcpState.phase === "loading" }),
  );
  wrapper.append(toolbar);

  if (mcpState.phase === "loading") {
    wrapper.append(statePanel("loading", "Lecture des serveurs MCP", "Interrogation de l’API /mcp/servers…"));
    return wrapper;
  }
  if (mcpState.phase === "error" && mcpState.error) {
    wrapper.append(errorPanel(mcpState.error, () => void loadMcp()));
    return wrapper;
  }

  const pending = pendingAuthorizationsBlock();
  if (pending) wrapper.append(pending);

  if (!mcpState.servers.length) {
    wrapper.append(statePanel(
      "empty",
      "Aucun serveur MCP déclaré",
      mcpState.statusFilter
        ? "Aucun serveur ne correspond à ce statut. Change le filtre ou déclare un serveur dans l’onglet « Ajouter »."
        : "Déclare un serveur dans l’onglet « Ajouter » ou pars d’une entrée du catalogue vérifié.",
    ));
    return wrapper;
  }

  const list = el("div", "item-list");
  for (const server of mcpState.servers) list.append(serverRow(server));
  wrapper.append(list);
  return wrapper;
}

// --- détail d’un serveur ----------------------------------------------------

function configurationBlock(detail: McpServerDetail): HTMLElement {
  const node = block(
    "Configuration de la révision courante",
    "Les secrets restent des références : aucune valeur n’est transmise au navigateur.",
  );
  const revision = detail.current_revision;
  if (!revision) {
    node.append(statePanel("empty", "Aucune révision courante", "Le serveur n’a pas encore de configuration active."));
    return node;
  }
  const config: McpServerConfig = revision.config;
  const entries: Array<[string, string | HTMLElement]> = [
    ["Transport", TRANSPORT_LABELS[config.transport]],
    ["Lieu d’exécution", locationLabel(detail)],
    ["Empreinte", shortFingerprint(revision.fingerprint)],
  ];

  if (config.transport === "http" && config.http) {
    entries.push(["Point d’entrée", config.http.url]);
    entries.push(["Délai maximal", `${config.http.timeout_seconds} s`]);
    const headers = Object.entries(config.http.headers);
    entries.push([
      "En-têtes littéraux",
      headers.length ? preBlock(headers.map(([key, value]) => `${key}: ${value}`).join("\n"), true) : "aucun",
    ]);
    const secretHeaders = Object.entries(config.http.header_secrets);
    entries.push([
      "En-têtes depuis le coffre",
      secretHeaders.length
        ? preBlock(secretHeaders.map(([key, ref]) => `${key}: référence ${secretLabel(ref.secret_id)}`).join("\n"), true)
        : "aucun",
    ]);
  } else if (config.stdio) {
    entries.push(["Commande", preBlock(config.stdio.command, true)]);
    entries.push(["Arguments", config.stdio.args.length ? preBlock(config.stdio.args.join("\n"), true) : "aucun"]);
    entries.push(["Répertoire de travail", config.stdio.cwd ?? "hérité du runner"]);
    entries.push(["Délai maximal", `${config.stdio.timeout_seconds} s`]);
    const env = Object.entries(config.stdio.env);
    entries.push([
      "Environnement littéral",
      env.length ? preBlock(env.map(([key, value]) => `${key}=${value}`).join("\n"), true) : "aucun",
    ]);
    const envSecrets = Object.entries(config.stdio.env_secrets);
    entries.push([
      "Environnement depuis le coffre",
      envSecrets.length
        ? preBlock(envSecrets.map(([key, ref]) => `${key}=référence ${secretLabel(ref.secret_id)}`).join("\n"), true)
        : "aucun",
    ]);
  }

  node.append(keyValueList(entries));
  if (revision.risk_flags.length) {
    const risks = el("ul", "mcp-plain-list");
    for (const flag of revision.risk_flags) {
      const item = el("li", "mcp-risk");
      item.append(
        statusChip(`${flag.level === "danger" ? "✗" : flag.level === "caution" ? "!" : "○"} ${RISK_LEVEL_LABELS[flag.level] ?? flag.level}`, RISK_LEVEL_TONES[flag.level] ?? "queued"),
        el("span", "", `${flag.message} (${flag.code})`),
      );
      risks.append(item);
    }
    node.append(el("p", "mcp-block-hint", "Signalements de la révision courante :"), risks);
  }
  return node;
}

function toolsBlock(detail: McpServerDetail): HTMLElement {
  const node = block(
    "Outils découverts",
    "Les descriptions et schémas proviennent du serveur MCP : ce sont des données affichées telles quelles, jamais des instructions.",
  );
  const revision = detail.current_revision;
  const discovery = revision?.discovery ?? null;

  if (!discovery) {
    node.append(statePanel(
      "empty",
      "Aucune découverte enregistrée",
      "Lance un diagnostic (probe) pour lister les outils réellement exposés par ce serveur.",
    ));
    return node;
  }

  node.append(keyValueList([
    ["Version du protocole", discovery.protocol_version],
    ["Découverte", revision?.discovery_current ? "à jour avec la configuration" : "obsolète : la configuration a changé depuis"],
    ["Horodatage", optionalDateTime(revision?.discovered_at ?? null, "inconnu")],
    ["Serveur annoncé", jsonBlock(discovery.server_info)],
  ]));

  if (discovery.truncated) {
    node.append(el("p", "mcp-block-hint", "Liste tronquée par la limite de découverte : certains outils ne sont pas affichés."));
  }
  if (!discovery.tools.length) {
    node.append(statePanel("empty", "Aucun outil exposé", "Le serveur a répondu sans déclarer d’outil."));
    return node;
  }

  const list = el("ul", "mcp-tool-list");
  for (const tool of discovery.tools) list.append(toolItem(tool));
  node.append(list);
  return node;
}

function toolItem(tool: McpDiscoveredTool): HTMLElement {
  const item = el("li", "mcp-tool");
  const head = el("div", "mcp-tool-head");
  const checkbox = el("input");
  checkbox.type = "checkbox";
  checkbox.checked = selectedTools.has(tool.name);
  checkbox.id = `mcp-tool-${encodeURIComponent(tool.name)}`;
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) selectedTools.add(tool.name);
    else selectedTools.delete(tool.name);
  });
  const label = el("label", "mcp-tool-name", tool.name);
  label.htmlFor = checkbox.id;
  head.append(checkbox, label);
  item.append(head);

  if (tool.description) {
    const description = el("p", "mcp-tool-description");
    description.textContent = tool.description;
    item.append(description);
  }

  const details = el("details", "mcp-details");
  details.append(el("summary", "", "Schéma d’entrée (texte brut)"), jsonBlock(tool.input_schema));
  item.append(details);
  return item;
}

function bindingsBlock(detail: McpServerDetail): HTMLElement {
  const node = block(
    "Rattachements par projet",
    "Un rattachement autorise un projet à utiliser une liste explicite d’outils de ce serveur.",
  );

  const active = detail.bindings.filter((binding) => !binding.revoked_at);
  const revoked = detail.bindings.filter((binding) => binding.revoked_at);

  if (mcpState.projectsError) {
    node.append(errorPanel(mcpState.projectsError, () => void loadMcp()));
  } else if (!mcpState.projects.length) {
    node.append(statePanel(
      "empty",
      "Aucun projet accessible",
      "Crée un projet dans « Projets » avant de rattacher un serveur MCP.",
    ));
  } else if (detail.status !== "active") {
    node.append(statePanel(
      "unconfigured",
      "Serveur non actif",
      `Un rattachement exige un serveur actif. Statut courant : ${SERVER_STATUS_LABELS[detail.status]}.`,
    ));
  } else {
    node.append(bindingForm(detail));
  }

  if (!active.length && !revoked.length) {
    node.append(statePanel("empty", "Aucun rattachement", "Aucun projet n’utilise encore ce serveur."));
    return node;
  }

  const list = el("div", "mcp-card-list");
  for (const binding of [...active, ...revoked]) list.append(bindingCard(detail, binding));
  node.append(list);
  return node;
}

function bindingForm(detail: McpServerDetail): HTMLElement {
  const form = el("form", "mcp-inline-form");
  form.noValidate = true;
  const projectSelect = selectControl("projectId", mcpState.projects.map((project) => ({
    value: project.id,
    label: project.name,
  })));
  const submit = el("button", "button button-primary", "Rattacher les outils cochés");
  submit.type = "submit";
  submit.disabled = mcpState.busy;

  form.append(
    labeledField("Projet", projectSelect, "Les outils cochés dans la liste ci-dessus composent la liste autorisée."),
    submit,
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const tools = [...selectedTools];
    if (!tools.length) {
      mcpState.notice = { tone: "error", message: "Coche au moins un outil avant de créer un rattachement." };
      paintMcp();
      return;
    }
    const projectId = projectSelect.value;
    void runMcpAction("Création du rattachement…", async () => {
      const binding = await mcpApi.createBinding(detail.id, { projectId, allowedTools: tools });
      await reloadDetail(detail.id);
      mcpState.servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
      return {
        tone: "success",
        message: `Rattachement créé pour ${projectLabel(binding.project_id)} (${binding.allowed_tools.length} outil(s) autorisé(s)).`,
      };
    });
  });
  return form;
}

function bindingCard(detail: McpServerDetail, binding: McpBinding): HTMLElement {
  const card = el("article", "mcp-card");
  const head = el("div", "mcp-card-head");
  head.append(el("h4", "mcp-card-title", projectLabel(binding.project_id)));
  const chips = el("div", "mcp-chips");
  if (binding.revoked_at) {
    chips.append(statusChip("✗ Révoqué", "failed"));
  } else {
    chips.append(binding.enabled ? statusChip("✓ Actif", "active") : statusChip("! Suspendu", "blocked"));
  }
  chips.append(statusChip(`○ Révision ${binding.revision_number}`, "queued"));
  head.append(chips);
  card.append(
    head,
    el("p", "mcp-card-meta", `Créé le ${formatDateTime(binding.created_at)} · mis à jour le ${formatDateTime(binding.updated_at)}`),
  );

  const tools = el("p", "mcp-card-meta");
  tools.textContent = `Outils autorisés : ${binding.allowed_tools.join(", ") || "aucun"}`;
  card.append(tools);

  if (binding.revoked_at) {
    card.append(el("p", "mcp-card-meta", `Révoqué le ${formatDateTime(binding.revoked_at)}`));
    return card;
  }

  const actions = el("div", "mcp-actions");
  actions.append(actionButton(
    binding.enabled ? "Suspendre" : "Réactiver",
    "secondary",
    () => void runMcpAction(binding.enabled ? "Suspension du rattachement…" : "Réactivation du rattachement…", async () => {
      const updated = await mcpApi.updateBinding(binding.id, { enabled: !binding.enabled });
      await reloadDetail(detail.id);
      return {
        tone: "success",
        message: updated.enabled ? "Rattachement réactivé." : "Rattachement suspendu.",
      };
    }),
    { disabled: mcpState.busy },
  ));
  actions.append(actionButton(
    "Remplacer par les outils cochés",
    "secondary",
    () => {
      const tools = [...selectedTools];
      if (!tools.length) {
        mcpState.notice = { tone: "error", message: "Coche au moins un outil avant de remplacer la liste autorisée." };
        paintMcp();
        return;
      }
      void runMcpAction("Mise à jour des outils autorisés…", async () => {
        const updated = await mcpApi.updateBinding(binding.id, { allowedTools: tools });
        await reloadDetail(detail.id);
        return {
          tone: "success",
          message: `Liste autorisée mise à jour (${updated.allowed_tools.length} outil(s)).`,
        };
      });
    },
    { disabled: mcpState.busy },
  ));
  actions.append(actionButton(
    "Révoquer",
    "secondary",
    () => {
      if (!confirmAction(`Révoquer le rattachement du projet « ${projectLabel(binding.project_id)} » ? Cette action est définitive.`)) return;
      void runMcpAction("Révocation du rattachement…", async () => {
        await mcpApi.revokeBinding(binding.id);
        await reloadDetail(detail.id);
        mcpState.servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
        return { tone: "success", message: "Rattachement révoqué." };
      });
    },
    { disabled: mcpState.busy },
  ));
  card.append(actions);
  return card;
}

function revisionCard(detail: McpServerDetail, revision: McpServerRevision): HTMLElement {
  const card = el("article", "mcp-card");
  const isCurrent = detail.current_revision?.id === revision.id;
  card.dataset.current = String(isCurrent);

  const head = el("div", "mcp-card-head");
  head.append(el("h4", "mcp-card-title", `Révision ${revision.number}`));
  const chips = el("div", "mcp-chips");
  if (isCurrent) chips.append(statusChip("✓ Courante", "active"));
  if (revision.requires_approval) chips.append(statusChip("! Approbation requise", "waiting"));
  chips.append(discoveryChip(revision.discovery_current));
  head.append(chips);

  card.append(
    head,
    el("p", "mcp-card-meta", `Créée le ${formatDateTime(revision.created_at)}${revision.superseded_at ? ` · remplacée le ${formatDateTime(revision.superseded_at)}` : ""} · empreinte ${shortFingerprint(revision.fingerprint)}`),
  );
  if (revision.note) {
    const note = el("p", "mcp-card-meta");
    note.textContent = `Note : ${revision.note}`;
    card.append(note);
  }

  const diff = revision.change_summary;
  if (diff) {
    const lines: string[] = [];
    lines.push(`Champs modifiés : ${diff.changed_fields.join(", ") || "aucun"}`);
    if (diff.endpoint_changed) lines.push("Point d’entrée modifié");
    if (diff.command_changed) lines.push("Commande modifiée");
    if (diff.secrets_added.length) lines.push(`Secrets ajoutés : ${diff.secrets_added.join(", ")}`);
    if (diff.secrets_removed.length) lines.push(`Secrets retirés : ${diff.secrets_removed.join(", ")}`);
    if (diff.tools_added.length) lines.push(`Outils apparus : ${diff.tools_added.join(", ")}`);
    if (diff.tools_removed.length) lines.push(`Outils disparus : ${diff.tools_removed.join(", ")}`);
    for (const reason of diff.reasons) lines.push(`Motif : ${reason}`);
    const details = el("details", "mcp-details");
    details.append(el("summary", "", "Différences avec la révision précédente"), preBlock(lines.join("\n"), true));
    card.append(details);
  }

  if (!isCurrent && detail.status !== "revoked" && mayManagePlatform()) {
    card.append(actionButton(
      "Revenir à cette révision",
      "secondary",
      () => {
        if (!confirmAction(`Créer une nouvelle révision identique à la révision ${revision.number} ?`)) return;
        void runMcpAction("Retour à une révision antérieure…", async () => {
          const updated = await mcpApi.rollbackServer(detail.id, revision.number, `Retour à la révision ${revision.number}`);
          mcpState.detail = updated;
          mcpState.servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
          return {
            tone: "success",
            message: `Nouvelle révision ${updated.current_revision_number ?? "?"} créée à partir de la révision ${revision.number}.`,
          };
        });
      },
      { disabled: mcpState.busy },
    ));
  }
  return card;
}

function revisionsBlock(detail: McpServerDetail): HTMLElement {
  const node = block("Révisions", "Chaque modification de configuration crée une révision conservée.");
  if (!detail.revisions.length) {
    node.append(statePanel("empty", "Aucune révision", "Le serveur n’a encore aucune configuration enregistrée."));
    return node;
  }
  const list = el("div", "mcp-card-list");
  for (const revision of [...detail.revisions].sort((a, b) => b.number - a.number)) {
    list.append(revisionCard(detail, revision));
  }
  node.append(list);
  return node;
}

function authorizationBlock(detail: McpServerDetail, probe: McpProbe): HTMLElement {
  const authorization = probe.authorization;
  const node = el("div", "mcp-authorization");
  if (!authorization) return node;

  node.append(el("h5", "mcp-block-title", "Autorisation demandée"));
  node.append(keyValueList([
    ["Action", authorization.action],
    ["Cible", preBlock(authorization.target, true)],
    ["Portée", jsonBlock(authorization.scope)],
    ["Empreinte", shortFingerprint(authorization.fingerprint)],
    ["Expiration", formatDateTime(authorization.expires_at)],
  ]));
  if (authorization.consequences.length) {
    node.append(el("p", "mcp-block-hint", "Conséquences si tu approuves :"), bulletList(authorization.consequences));
  }

  if (!mayManagePlatform()) {
    node.append(el("p", "form-hint", "La décision est réservée au propriétaire de la plateforme."));
    return node;
  }

  const form = el("form", "mcp-inline-form");
  form.noValidate = true;
  const comment = textInput("comment", { placeholder: "Commentaire de décision (facultatif)", maxLength: 500 });
  const actions = el("div", "mcp-actions");
  const approve = el("button", "button button-primary", "Approuver et mettre en file");
  approve.type = "submit";
  approve.disabled = mcpState.busy;
  const reject = actionButton("Refuser", "secondary", () => {
    void decideProbe(detail, probe, "rejected", comment.value);
  }, { disabled: mcpState.busy });
  actions.append(approve, reject);
  form.append(labeledField("Commentaire", comment), actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!confirmAction("Approuver le lancement de ce processus sur le runner désigné ?")) return;
    void decideProbe(detail, probe, "approved", comment.value);
  });
  node.append(form);
  return node;
}

async function decideProbe(
  detail: McpServerDetail,
  probe: McpProbe,
  decision: "approved" | "rejected",
  comment: string,
): Promise<void> {
  await runMcpAction(decision === "approved" ? "Approbation du probe…" : "Refus du probe…", async () => {
    const updated = await mcpApi.decideProbe(probe.id, decision, comment);
    await reloadDetail(detail.id);
    try {
      mcpState.pendingProbes = await mcpApi.listProbes("pending_approval");
      mcpState.pendingProbesError = null;
    } catch (error) {
      mcpState.pendingProbesError = normalizeApiError(error, "Les autorisations en attente n’ont pas pu être relues.");
    }
    return {
      tone: decision === "approved" ? "success" : "warning",
      message: `Décision enregistrée : le probe est désormais « ${PROBE_STATUS_LABELS[updated.status]} ».`,
    };
  });
}

function probeCard(detail: McpServerDetail, probe: McpProbe): HTMLElement {
  const card = el("article", "mcp-card");
  const head = el("div", "mcp-card-head");
  head.append(el("h4", "mcp-card-title", `Probe ${TRANSPORT_LABELS[probe.transport]}`), probeStatusChip(probe.status));
  card.append(
    head,
    el("p", "mcp-card-meta", [
      `Demandé le ${formatDateTime(probe.created_at)}`,
      probe.finished_at ? `terminé le ${formatDateTime(probe.finished_at)}` : "non terminé",
      probe.worker_id ? `runner ${probe.worker_id}` : "sans runner",
    ].join(" · ")),
  );

  if (probe.decided_at) {
    const decision = el("p", "mcp-card-meta");
    decision.textContent = `Décision le ${formatDateTime(probe.decided_at)}${probe.decision_comment ? ` — ${probe.decision_comment}` : ""}`;
    card.append(decision);
  }

  const result = probe.result;
  if (result) {
    const entries: Array<[string, string | HTMLElement]> = [
      ["Protocole", result.protocol_version ?? "non annoncé"],
      ["Outils listés", String(result.tools.length)],
      ["Durée", result.duration_ms === null ? "inconnue" : `${result.duration_ms} ms`],
      ["Code de sortie", result.exit_code === null ? "sans objet" : String(result.exit_code)],
    ];
    if (result.server_info) entries.push(["Serveur annoncé", jsonBlock(result.server_info)]);
    if (result.error) entries.push(["Erreur", preBlock(result.error, true)]);
    if (result.stderr_tail) entries.push(["Fin de la sortie d’erreur", preBlock(result.stderr_tail, true)]);
    const details = el("details", "mcp-details");
    details.append(el("summary", "", "Diagnostic renvoyé"), keyValueList(entries));
    card.append(details);
  } else if (probe.error) {
    const error = el("p", "mcp-card-meta");
    error.textContent = `Erreur : ${probe.error}`;
    card.append(error);
  }

  if (probe.status === "pending_approval") card.append(authorizationBlock(detail, probe));
  return card;
}

function probesBlock(detail: McpServerDetail): HTMLElement {
  const node = block(
    "Diagnostics (probes)",
    "Un probe HTTP est exécuté par l’API ; un probe stdio exige une autorisation explicite puis un runner.",
  );
  if (!detail.probes.length) {
    node.append(statePanel("empty", "Aucun probe enregistré", "Lance un diagnostic pour découvrir les outils du serveur."));
    return node;
  }
  const list = el("div", "mcp-card-list");
  for (const probe of detail.probes) list.append(probeCard(detail, probe));
  node.append(list);
  return node;
}

function lifecycleBlock(detail: McpServerDetail): HTMLElement {
  const node = block("Actions", "Les actions de cycle de vie sont réservées au propriétaire de la plateforme.");
  if (!mayManagePlatform()) {
    node.append(statePanel(
      "forbidden",
      "Réservé au propriétaire",
      "Ce compte peut consulter le serveur et gérer les rattachements de ses projets, mais pas modifier son cycle de vie.",
    ));
    return node;
  }

  const actions = el("div", "mcp-actions");
  const revoked = detail.status === "revoked";

  actions.append(actionButton(
    "Lancer un diagnostic",
    "primary",
    () => void runMcpAction("Lancement du diagnostic…", async () => {
      const probe = await mcpApi.probeServer(detail.id);
      await reloadDetail(detail.id);
      mcpState.servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
      if (probe.status === "pending_approval") {
        try {
          mcpState.pendingProbes = await mcpApi.listProbes("pending_approval");
        } catch {
          mcpState.pendingProbesError = new WorkspaceApiError(
            "Les autorisations en attente n’ont pas pu être relues.",
            "invalid_response",
          );
        }
      }
      return {
        tone: probe.status === "succeeded" ? "success" : probe.status === "failed" ? "error" : "warning",
        message: `Probe ${probe.status === "pending_approval" ? "créé : autorisation requise avant exécution" : `terminé avec le statut « ${PROBE_STATUS_LABELS[probe.status]} »`}.`,
      };
    }),
    { disabled: mcpState.busy || revoked, title: revoked ? "Serveur révoqué." : undefined },
  ));

  const canActivate = !revoked && detail.status !== "active" && detail.discovery_current;
  actions.append(actionButton(
    "Activer",
    "secondary",
    () => void runMcpAction("Activation du serveur…", async () => {
      const updated = await mcpApi.activateServer(detail.id);
      mcpState.detail = updated;
      mcpState.servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
      const notes = updated.apply_notes.length ? ` Notes : ${updated.apply_notes.join(" ")}` : "";
      return { tone: "success", message: `Serveur actif.${notes}` };
    }),
    {
      disabled: mcpState.busy || !canActivate,
      title: revoked
        ? "Serveur révoqué."
        : detail.status === "active"
          ? "Le serveur est déjà actif."
          : !detail.discovery_current
            ? "L’activation exige une découverte à jour : lance un diagnostic."
            : undefined,
    },
  ));

  actions.append(actionButton(
    "Désactiver",
    "secondary",
    () => void runMcpAction("Désactivation du serveur…", async () => {
      const updated = await mcpApi.disableServer(detail.id);
      mcpState.detail = updated;
      mcpState.servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
      return { tone: "warning", message: "Serveur désactivé : les rattachements restent en place mais inactifs." };
    }),
    {
      disabled: mcpState.busy || detail.status !== "active",
      title: detail.status !== "active" ? "Seul un serveur actif peut être désactivé." : undefined,
    },
  ));

  actions.append(actionButton(
    mcpState.revokeOpen ? "Annuler la révocation" : "Révoquer…",
    "secondary",
    () => {
      mcpState.revokeOpen = !mcpState.revokeOpen;
      paintMcp();
    },
    { disabled: mcpState.busy || revoked, title: revoked ? "Serveur déjà révoqué." : undefined },
  ));

  node.append(actions);

  if (detail.apply_notes.length) {
    node.append(el("p", "mcp-block-hint", "Notes d’application de la dernière opération :"), bulletList(detail.apply_notes));
  }

  if (mcpState.revokeOpen && !revoked) {
    const form = el("form", "mcp-inline-form");
    form.noValidate = true;
    const reason = textArea("reason", 2, {
      placeholder: "Raison de la révocation (conservée dans l’historique)",
      required: true,
      maxLength: 2000,
    });
    const submit = el("button", "button button-primary", "Révoquer définitivement");
    submit.type = "submit";
    submit.disabled = mcpState.busy;
    form.append(
      labeledField("Raison", reason, "La révocation est irréversible : les rattachements sont révoqués et les probes en cours annulés."),
      submit,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!reason.value.trim()) {
        mcpState.notice = { tone: "error", message: "La raison de la révocation est obligatoire." };
        paintMcp();
        return;
      }
      if (!confirmAction(`Révoquer définitivement le serveur « ${detail.display_name || detail.name} » ?`)) return;
      const value = reason.value;
      void runMcpAction("Révocation du serveur…", async () => {
        const updated = await mcpApi.revokeServer(detail.id, value);
        mcpState.detail = updated;
        mcpState.revokeOpen = false;
        mcpState.servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
        return { tone: "warning", message: "Serveur révoqué : l’historique reste lisible, les rattachements sont révoqués." };
      });
    });
    node.append(form);
  }

  return node;
}

function detailView(): HTMLElement {
  const wrapper = el("div", "mcp-detail");
  const back = actionButton("← Retour à la liste", "secondary", () => selectServer(null));
  wrapper.append(back);

  if (mcpState.detailPhase === "loading") {
    wrapper.append(statePanel("loading", "Lecture du serveur", "Interrogation de l’API /mcp/servers…"));
    return wrapper;
  }
  if (mcpState.detailError) {
    wrapper.append(errorPanel(mcpState.detailError, () => {
      if (mcpState.selectedServerId) void reloadDetail(mcpState.selectedServerId).then(paintMcp);
    }));
    return wrapper;
  }
  const detail = mcpState.detail;
  if (!detail) {
    wrapper.append(statePanel("empty", "Serveur introuvable", "Le serveur demandé n’est plus disponible."));
    return wrapper;
  }

  const header = el("div", "mcp-detail-header");
  const copy = el("div");
  copy.append(
    el("h3", "mcp-detail-title", detail.display_name || detail.name),
    el("p", "mcp-detail-subtitle", [
      detail.name,
      TRANSPORT_LABELS[detail.transport],
      locationLabel(detail),
      SOURCE_LABELS[detail.source_kind] ?? detail.source_kind,
      detail.origin || "origine non renseignée",
    ].join(" · ")),
    el("p", "mcp-detail-subtitle", `Créé le ${formatDateTime(detail.created_at)} · mis à jour le ${formatDateTime(detail.updated_at)}${detail.revoked_at ? ` · révoqué le ${formatDateTime(detail.revoked_at)}` : ""}`),
  );
  if (detail.description) {
    const description = el("p", "mcp-detail-subtitle");
    description.textContent = detail.description;
    copy.append(description);
  }
  const chips = el("div", "mcp-chips");
  chips.append(serverStatusChip(detail.status), discoveryChip(detail.discovery_current));
  if (detail.last_probe_status) chips.append(probeStatusChip(detail.last_probe_status));
  header.append(copy, chips);

  wrapper.append(
    header,
    lifecycleBlock(detail),
    configurationBlock(detail),
    toolsBlock(detail),
    bindingsBlock(detail),
    revisionsBlock(detail),
    probesBlock(detail),
  );
  return wrapper;
}

// --- formulaire d’ajout -----------------------------------------------------

function runnerOptions(): ReadonlyArray<{ value: string; label: string; disabled?: boolean }> {
  const eligible = mcpState.runners.filter(
    (runner) => runner.capabilities.includes("mcp_stdio_probe") && !runner.simulation,
  );
  if (!eligible.length) {
    return [{ value: "", label: "Aucun runner compatible déclaré", disabled: true }];
  }
  return [
    { value: "", label: "Choisir un runner" },
    ...eligible.map((runner) => ({
      value: runner.id,
      label: `${runner.name} (${runner.status})`,
    })),
  ];
}

function addServerPanel(): HTMLElement {
  const wrapper = el("div", "mcp-panel-body");
  if (!mayManagePlatform()) {
    wrapper.append(statePanel(
      "forbidden",
      "Réservé au propriétaire",
      "Seul le propriétaire de la plateforme peut déclarer un serveur MCP. Les autres comptes gèrent les rattachements de leurs projets depuis le détail d’un serveur actif.",
    ));
    return wrapper;
  }

  const prefill = mcpState.prefill;
  const form = el("form", "mcp-form");
  form.noValidate = true;

  if (prefill) {
    const note = block(
      `Pré-rempli depuis le catalogue : ${prefill.display_name}`,
      `Vérifié le ${prefill.verified_at} — ${prefill.verification}`,
    );
    if (prefill.required_secrets.length) {
      note.append(
        el("p", "mcp-block-hint", "Secrets attendus par cette entrée (à créer dans le coffre puis à référencer) :"),
        bulletList(prefill.required_secrets),
      );
    }
    if (prefill.prerequisites.length) {
      note.append(el("p", "mcp-block-hint", "Prérequis :"), bulletList(prefill.prerequisites));
    }
    if (prefill.risks.length) {
      note.append(el("p", "mcp-block-hint", "Risques signalés :"), bulletList(prefill.risks));
    }
    note.append(actionButton("Repartir d’un formulaire vide", "secondary", () => {
      mcpState.prefill = null;
      paintMcp();
    }));
    wrapper.append(note);
  }

  const prefilledHttp = prefill?.config.transport === "http" ? prefill.config.http : null;
  const prefilledStdio = prefill?.config.transport === "stdio" ? prefill.config.stdio : null;
  const initialTransport: McpTransport = prefill?.transport ?? "http";

  const nameInput = textInput("name", {
    placeholder: "github-mcp",
    required: true,
    maxLength: 64,
    value: prefill ? prefill.id : "",
  });
  const displayInput = textInput("displayName", {
    placeholder: "GitHub MCP",
    required: true,
    maxLength: 120,
    value: prefill ? prefill.display_name : "",
  });
  const descriptionInput = textArea("description", 2, {
    placeholder: "À quoi sert ce serveur dans l’atelier ?",
    maxLength: 2000,
    value: prefill ? prefill.description : "",
  });
  const transportSelect = selectControl("transport", [
    { value: "http", label: TRANSPORT_LABELS.http, selected: initialTransport === "http" },
    { value: "stdio", label: TRANSPORT_LABELS.stdio, selected: initialTransport === "stdio" },
  ]);
  const noteInput = textInput("note", { placeholder: "Note de révision (facultative)", maxLength: 500 });

  // Bloc HTTP
  const httpFieldset = el("fieldset", "mcp-fieldset");
  httpFieldset.append(el("legend", "", "Transport HTTP"));
  const urlInput = textInput("url", {
    placeholder: "https://exemple.test/mcp",
    maxLength: 2000,
    value: prefilledHttp?.url ?? "",
  });
  const httpTimeout = numberInput("httpTimeout", prefilledHttp?.timeout_seconds ?? 15, 1, 120);
  const headerEditor = createKeyValueEditor("header");
  httpFieldset.append(
    labeledField("URL du point d’entrée", urlInput, "HTTPS exigé, sauf adresse explicitement autorisée côté serveur."),
    labeledField("Délai maximal (secondes)", httpTimeout),
    fieldGroup("En-têtes", headerEditor.node, "Une valeur sensible doit être un secret du coffre, jamais une valeur littérale."),
  );
  for (const [key, value] of Object.entries(prefilledHttp?.headers ?? {})) headerEditor.addRow(key, "literal", value);

  // Bloc stdio
  const stdioFieldset = el("fieldset", "mcp-fieldset");
  stdioFieldset.append(el("legend", "", "Transport stdio"));
  const commandInput = textInput("command", {
    placeholder: "C:\\Program Files\\nodejs\\node.exe",
    maxLength: 1000,
    value: prefilledStdio?.command ?? "",
  });
  const argsInput = textArea("args", 3, {
    placeholder: "Un argument par ligne",
    maxLength: 4000,
    value: (prefilledStdio?.args ?? []).join("\n"),
  });
  const cwdInput = textInput("cwd", { placeholder: "Répertoire de travail (facultatif)", maxLength: 1000 });
  const stdioTimeout = numberInput("stdioTimeout", prefilledStdio?.timeout_seconds ?? 20, 1, 120);
  const envEditor = createKeyValueEditor("env");
  const runnerSelect = selectControl("targetWorkerId", runnerOptions());
  stdioFieldset.append(
    labeledField("Commande", commandInput, "Chemin absolu exigé : le serveur refuse une commande relative."),
    labeledField("Arguments", argsInput),
    labeledField("Répertoire de travail", cwdInput),
    labeledField("Délai maximal (secondes)", stdioTimeout),
    fieldGroup("Variables d’environnement", envEditor.node, "Une valeur sensible doit être un secret du coffre, jamais une valeur littérale."),
    labeledField(
      "Runner cible",
      runnerSelect,
      mcpState.runnersError
        ? "Liste des runners indisponible : le champ reste modifiable mais non vérifié ici."
        : "Seuls les runners déclarant la capacité mcp_stdio_probe hors simulation sont proposés.",
    ),
  );
  for (const [key, value] of Object.entries(prefilledStdio?.env ?? {})) envEditor.addRow(key, "literal", value);

  function applyTransport(): void {
    const transport = transportSelect.value as McpTransport;
    httpFieldset.hidden = transport !== "http";
    httpFieldset.disabled = transport !== "http";
    stdioFieldset.hidden = transport !== "stdio";
    stdioFieldset.disabled = transport !== "stdio";
  }
  transportSelect.addEventListener("change", applyTransport);

  const feedback = noticeNode(null);
  const submit = el("button", "button button-primary", "Déclarer le serveur (brouillon)");
  submit.type = "submit";
  submit.disabled = mcpState.busy;

  form.append(
    labeledField("Nom technique", nameInput, "Minuscules, chiffres et tirets ; sert d’identifiant stable."),
    labeledField("Nom affiché", displayInput),
    labeledField("Description", descriptionInput),
    labeledField("Transport", transportSelect),
    httpFieldset,
    stdioFieldset,
    labeledField("Note de révision", noteInput),
    feedback,
    submit,
  );
  applyTransport();

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const transport = transportSelect.value as McpTransport;
    let config: McpServerConfig;
    if (transport === "http") {
      const headers = headerEditor.read();
      const url = urlInput.value.trim();
      if (!url) {
        feedback.dataset.tone = "error";
        feedback.textContent = "L’URL du point d’entrée est obligatoire.";
        return;
      }
      config = {
        transport: "http",
        http: {
          url,
          headers: headers.literal,
          header_secrets: headers.secrets,
          timeout_seconds: Number(httpTimeout.value),
        },
        stdio: null,
      };
    } else {
      const env = envEditor.read();
      const command = commandInput.value.trim();
      if (!command) {
        feedback.dataset.tone = "error";
        feedback.textContent = "La commande est obligatoire pour un serveur stdio.";
        return;
      }
      config = {
        transport: "stdio",
        http: null,
        stdio: {
          command,
          args: argsInput.value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean),
          env: env.literal,
          env_secrets: env.secrets,
          cwd: cwdInput.value.trim() || null,
          timeout_seconds: Number(stdioTimeout.value),
        },
      };
    }

    const input = {
      name: nameInput.value,
      displayName: displayInput.value,
      description: descriptionInput.value,
      sourceKind: (prefill ? "catalog" : "manual") as "catalog" | "manual",
      origin: prefill ? `catalogue:${prefill.id}` : "",
      config,
      targetWorkerId: transport === "stdio" ? runnerSelect.value || null : null,
      note: noteInput.value,
    };

    void runMcpAction("Déclaration du serveur…", async () => {
      const created = await mcpApi.createServer(input);
      mcpState.prefill = null;
      mcpState.servers = await mcpApi.listServers(mcpState.statusFilter || undefined);
      mcpState.tab = "servers";
      mcpState.selectedServerId = created.id;
      mcpState.detail = created;
      mcpState.detailPhase = "ready";
      selectedTools.clear();
      return {
        tone: "success",
        message: `Serveur « ${created.display_name || created.name} » créé en brouillon (révision ${created.current_revision_number ?? 1}). Lance un diagnostic avant l’activation.`,
      };
    });
  });

  wrapper.append(form);
  return wrapper;
}

// --- catalogue --------------------------------------------------------------

function catalogPanel(): HTMLElement {
  const wrapper = el("div", "mcp-panel-body");
  wrapper.append(el(
    "p",
    "mcp-block-hint",
    "Entrées vérifiées par lecture de documentation : rien n’a été exécuté pour les valider. Le pré-remplissage n’installe rien.",
  ));

  if (mcpState.catalogPhase === "loading") {
    wrapper.append(statePanel("loading", "Lecture du catalogue", "Interrogation de l’API /mcp/catalog…"));
    return wrapper;
  }
  if (mcpState.catalogError) {
    wrapper.append(errorPanel(mcpState.catalogError, () => void loadCatalog()));
    return wrapper;
  }
  if (mcpState.catalogPhase === "idle") {
    wrapper.append(statePanel("loading", "Catalogue non chargé", "Ouvre cet onglet pour lancer la lecture du catalogue."));
    return wrapper;
  }
  if (!mcpState.catalog.length) {
    wrapper.append(statePanel("empty", "Catalogue vide", "Aucune entrée vérifiée n’est publiée par l’API."));
    return wrapper;
  }

  const grid = el("div", "mcp-catalog-grid");
  for (const entry of mcpState.catalog) {
    const card = el("article", "mcp-card");
    const head = el("div", "mcp-card-head");
    head.append(el("h4", "mcp-card-title", entry.display_name), statusChip(`○ ${TRANSPORT_LABELS[entry.transport]}`, "queued"));
    card.append(head);
    const description = el("p", "mcp-card-meta");
    description.textContent = entry.description;
    card.append(description, el("p", "mcp-card-meta", `Vérifié le ${entry.verified_at} — ${entry.verification}`));

    if (entry.required_secrets.length) {
      card.append(el("p", "mcp-block-hint", "Secrets requis :"), bulletList(entry.required_secrets));
    }
    if (entry.prerequisites.length) {
      card.append(el("p", "mcp-block-hint", "Prérequis :"), bulletList(entry.prerequisites));
    }
    if (entry.risks.length) {
      card.append(el("p", "mcp-block-hint", "Risques :"), bulletList(entry.risks));
    }
    if (entry.documentation_url) {
      const link = el("a", "mcp-link", "Documentation officielle");
      link.href = entry.documentation_url;
      link.rel = "noreferrer noopener";
      link.target = "_blank";
      card.append(link);
    }
    if (mayManagePlatform()) {
      card.append(actionButton("Pré-remplir le formulaire d’ajout", "secondary", () => {
        mcpState.prefill = entry;
        selectTab("add");
      }));
    } else {
      card.append(el("p", "form-hint", "La déclaration d’un serveur est réservée au propriétaire."));
    }
    grid.append(card);
  }
  wrapper.append(grid);
  return wrapper;
}

// --- export -----------------------------------------------------------------

function exportPanel(): HTMLElement {
  const wrapper = el("div", "mcp-panel-body");
  const form = el("form", "mcp-export-form");
  form.noValidate = true;

  const formatSelect = selectControl("format", (["hermes", "claude", "codex"] as McpExportFormat[]).map((format) => ({
    value: format,
    label: EXPORT_FORMAT_LABELS[format],
    selected: mcpState.exportResult?.format === format,
  })));
  const projectSelect = selectControl("projectId", [
    { value: "", label: "Toute la plateforme (propriétaire)" },
    ...mcpState.projects.map((project) => ({
      value: project.id,
      label: project.name,
      selected: mcpState.exportResult?.project_id === project.id,
    })),
  ]);
  const submit = el("button", "button button-primary", "Générer l’export");
  submit.type = "submit";
  submit.disabled = mcpState.exportPhase === "loading";

  form.append(
    labeledField("Format", formatSelect),
    labeledField("Portée", projectSelect, "Sans projet, l’export couvre la plateforme et exige le rôle propriétaire."),
    submit,
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const format = formatSelect.value as McpExportFormat;
    const projectId = projectSelect.value || null;
    mcpState.exportPhase = "loading";
    mcpState.exportError = null;
    paintMcp();
    void mcpApi.exportServers(format, projectId).then(
      (result) => {
        mcpState.exportResult = result;
        mcpState.exportPhase = "ready";
        paintMcp();
      },
      (error: unknown) => {
        mcpState.exportResult = null;
        mcpState.exportError = normalizeApiError(error, "L’export n’a pas pu être généré.");
        mcpState.exportPhase = "error";
        paintMcp();
      },
    );
  });
  wrapper.append(form);

  if (mcpState.exportPhase === "loading") {
    wrapper.append(statePanel("loading", "Génération de l’export", "Interrogation de l’API /mcp/export…"));
    return wrapper;
  }
  if (mcpState.exportError) {
    wrapper.append(errorPanel(mcpState.exportError));
    return wrapper;
  }
  const result = mcpState.exportResult;
  if (!result) {
    wrapper.append(statePanel(
      "empty",
      "Aucun export généré",
      "Choisis un format et une portée : le contenu est produit par l’API, jamais reconstitué ici.",
    ));
    return wrapper;
  }
  wrapper.append(exportResultView(result));
  return wrapper;
}

function exportResultView(result: McpExport): HTMLElement {
  const node = el("div", "mcp-export-result");
  node.append(keyValueList([
    ["Format", EXPORT_FORMAT_LABELS[result.format]],
    ["Portée", result.project_id ? projectLabel(result.project_id) : "plateforme entière"],
  ]));
  if (result.placeholders.length) {
    node.append(
      el("p", "mcp-block-hint", "Variables à renseigner dans l’environnement cible (aucune valeur n’est exportée) :"),
      bulletList(result.placeholders),
    );
  }
  if (result.partial_compatibility.length) {
    node.append(el("p", "mcp-block-hint", "Compatibilité partielle :"), bulletList(result.partial_compatibility));
  }
  if (result.apply_notes.length) {
    node.append(el("p", "mcp-block-hint", "Notes d’application :"), bulletList(result.apply_notes));
  }
  node.append(preBlock(result.content));

  const clipboard = globalThis.navigator?.clipboard;
  if (clipboard?.writeText) {
    node.append(actionButton("Copier le contenu", "secondary", () => {
      clipboard.writeText(result.content).then(
        () => {
          mcpState.notice = { tone: "success", message: "Contenu de l’export copié dans le presse-papiers." };
          paintMcp();
        },
        () => {
          mcpState.notice = { tone: "error", message: "La copie a été refusée par le navigateur : sélectionne le texte manuellement." };
          paintMcp();
        },
      );
    }));
  }
  return node;
}

// --- import (/mcp/import/*) -------------------------------------------------

/**
 * État de la section « Import ».
 *
 * Il ne survit pas au changement de compte (`resetMcpUiState`) et n’est jamais
 * pré-rempli : tant que l’utilisateur n’a pas coché une entrée et cliqué sur
 * « Appliquer », rien n’est créé.
 */
interface ImportState {
  format: McpImportFormat;
  content: string;
  phase: Phase;
  preview: McpImportPreview | null;
  error: WorkspaceApiError | null;
  selected: Set<string>;
  mapping: Record<string, string>;
  onConflict: "skip" | "new_revision";
  applyPhase: Phase;
  result: McpImportApplyResult | null;
  applyError: WorkspaceApiError | null;
}

function initialImportState(): ImportState {
  return {
    format: "auto",
    content: "",
    phase: "idle",
    preview: null,
    error: null,
    selected: new Set<string>(),
    mapping: {},
    onConflict: "skip",
    applyPhase: "idle",
    result: null,
    applyError: null,
  };
}

const importState: ImportState = initialImportState();

/**
 * Rafraîchit le bouton « Appliquer » après une case cochée, sans repeindre la liste
 * (un repeint ferait perdre le focus). Réinstallé à chaque rendu de la section.
 */
let refreshImportApply: (() => void) | null = null;

const IMPORT_FORMAT_LABELS: Record<McpImportFormat, string> = {
  auto: "Détection automatique",
  hermes: "Hermes (~/.hermes/config.yaml)",
  claude: "Claude Code (.mcp.json / ~/.claude.json)",
  codex: "Codex (~/.codex/config.toml)",
};

const IMPORT_LOCATION_LABELS: Record<string, string> = {
  header: "en-tête",
  env: "variable d’environnement",
  url: "URL",
};

function importConflictChip(entry: McpImportEntry): HTMLElement {
  return entry.conflict === "existing_server"
    ? statusChip("! Nom déjà pris", "waiting")
    : statusChip("✓ Nom disponible", "active");
}

/** Résumé masqué d’une configuration importée : jamais une valeur de secret. */
function importConfigView(config: McpServerConfig): HTMLElement {
  const rows: Array<[string, string | HTMLElement]> = [["Transport", TRANSPORT_LABELS[config.transport]]];
  if (config.transport === "http" && config.http) {
    rows.push(["Point d’entrée", config.http.url]);
    rows.push(["Délai maximal", `${config.http.timeout_seconds} s`]);
    const headers = Object.entries(config.http.headers);
    rows.push([
      "En-têtes repris",
      headers.length ? preBlock(headers.map(([key, value]) => `${key}: ${value}`).join("\n"), true) : "aucun",
    ]);
  } else if (config.stdio) {
    rows.push(["Commande", preBlock(config.stdio.command, true)]);
    rows.push([
      "Arguments",
      config.stdio.args.length ? preBlock(config.stdio.args.join("\n"), true) : "aucun",
    ]);
    rows.push(["Répertoire de travail", config.stdio.cwd ?? "hérité du runner"]);
    rows.push(["Délai maximal", `${config.stdio.timeout_seconds} s`]);
    const env = Object.entries(config.stdio.env);
    rows.push([
      "Environnement repris",
      env.length ? preBlock(env.map(([key, value]) => `${key}=${value}`).join("\n"), true) : "aucun",
    ]);
  }
  return keyValueList(rows);
}

/**
 * Un candidat de secret : la valeur du fichier n’est jamais transmise (elle arrive
 * masquée), et l’import ne peut aboutir que reliée à un secret **déjà** dans le coffre.
 */
function importCandidateRow(candidate: McpImportSecretCandidate): HTMLElement {
  const row = el("div", "mcp-kv-row");
  const label = el("p", "mcp-card-meta");
  label.textContent = `${IMPORT_LOCATION_LABELS[candidate.location] ?? candidate.location} « ${candidate.key} » — valeur du fichier masquée : ${candidate.masked_value}`;

  const secrets = availableSecrets();
  const select = selectControl(`import-secret-${candidate.suggested_secret_name}`, [
    {
      value: "",
      label: secrets.length ? "— choisir un secret du coffre —" : "aucun secret disponible",
      selected: !importState.mapping[candidate.suggested_secret_name],
    },
    ...secrets.map((secret) => ({
      value: secret.id,
      label: `${secret.name} (${secret.scope_type === "project" ? "projet" : "plateforme"})`,
      selected: importState.mapping[candidate.suggested_secret_name] === secret.id,
    })),
  ]);
  select.disabled = secrets.length === 0;
  select.setAttribute(
    "aria-label",
    `Secret du coffre pour ${candidate.key} (nom proposé : ${candidate.suggested_secret_name})`,
  );
  select.addEventListener("change", () => {
    if (select.value) importState.mapping[candidate.suggested_secret_name] = select.value;
    else delete importState.mapping[candidate.suggested_secret_name];
  });

  const hint = el("p", "mcp-block-hint");
  hint.textContent = secrets.length
    ? `Nom proposé si le secret n’existe pas encore : ${candidate.suggested_secret_name} (à créer dans le coffre ci-dessous).`
    : `Crée d’abord le secret ${candidate.suggested_secret_name} dans le coffre : l’import ne transporte aucune valeur.`;

  row.append(label, select, hint);
  return row;
}

function importEntryCard(entry: McpImportEntry): HTMLElement {
  const card = el("article", "mcp-card");
  const head = el("div", "mcp-card-head");

  const title = el("label", "mcp-card-title");
  const checkbox = el("input", "");
  checkbox.type = "checkbox";
  checkbox.checked = importState.selected.has(entry.name);
  checkbox.disabled = !entry.importable;
  if (!entry.importable) {
    checkbox.title = "Entrée non importable : voir les points non supportés ci-dessous.";
  }
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) importState.selected.add(entry.name);
    else importState.selected.delete(entry.name);
    // Mise à jour locale du bouton : un repeint complet ferait perdre le focus de la case.
    refreshImportApply?.();
  });
  title.append(checkbox, el("span", "mcp-import-name", ` ${entry.name}`));

  const chips = el("div", "mcp-chips");
  chips.append(importConflictChip(entry));
  chips.append(entry.importable
    ? statusChip("✓ Importable", "active")
    : statusChip("✗ Non importable", "failed"));
  if (entry.transport) chips.append(statusChip(`○ ${TRANSPORT_LABELS[entry.transport]}`, "queued"));
  head.append(title, chips);
  card.append(head);

  const source = el("p", "mcp-card-meta");
  source.textContent = `Nom d’origine : ${entry.source_name}`;
  card.append(source);

  if (entry.config) card.append(importConfigView(entry.config));

  if (entry.secret_candidates.length) {
    card.append(el(
      "p",
      "mcp-block-hint",
      "Secrets détectés : relie chacun à un secret existant du coffre, sinon l’entrée sera ignorée.",
    ));
    const rows = el("div", "mcp-kv-rows");
    for (const candidate of entry.secret_candidates) rows.append(importCandidateRow(candidate));
    card.append(rows);
  }
  if (entry.unsupported.length) {
    card.append(el("p", "mcp-block-hint", "Non repris par la plateforme :"), bulletList(entry.unsupported));
  }
  if (entry.warnings.length) {
    card.append(el("p", "mcp-block-hint", "À vérifier :"), bulletList(entry.warnings));
  }
  return card;
}

function importResultView(result: McpImportApplyResult): HTMLElement {
  const node = el("div", "mcp-export-result");
  const applied = [...result.created, ...result.revised];
  if (applied.length) {
    const list = el("ul", "mcp-plain-list");
    for (const server of result.created) {
      list.append(el("li", "", `Créé : ${server.name} (brouillon, révision ${server.current_revision_number ?? 1})`));
    }
    for (const server of result.revised) {
      list.append(el(
        "li",
        "",
        `Révisé : ${server.name} (révision ${server.current_revision_number ?? "?"} ; la précédente reste consultable)`,
      ));
    }
    node.append(el("p", "mcp-block-hint", "Serveurs importés (aucun n’est actif avant diagnostic) :"), list);
  } else {
    node.append(statePanel(
      "empty",
      "Aucune entrée importée",
      "Rien n’a été créé : les raisons sont listées ci-dessous.",
    ));
  }
  if (result.skipped.length) {
    node.append(el("p", "mcp-block-hint", "Entrées ignorées :"), bulletList(result.skipped));
  }
  if (result.errors.length) {
    node.append(el("p", "mcp-block-hint", "Refus détaillés :"), bulletList(result.errors));
  }
  node.append(el(
    "p",
    "mcp-block-hint",
    "Les conflits de noms affichés au-dessus datent de l’analyse : relance-la pour les revoir à jour.",
  ));
  return node;
}

function runImportPreview(content: string, format: McpImportFormat): void {
  importState.content = content;
  importState.format = format;
  importState.phase = "loading";
  importState.error = null;
  importState.result = null;
  importState.applyError = null;
  importState.applyPhase = "idle";
  importState.selected.clear();
  importState.mapping = {};
  paintMcp();
  const generation = stateGeneration;
  void mcpApi.previewImport(format, content).then(
    (preview) => {
      if (generation !== stateGeneration) return;
      importState.preview = preview;
      importState.phase = "ready";
      paintMcp();
    },
    (error: unknown) => {
      if (generation !== stateGeneration) return;
      const apiError = normalizeApiError(error, "L’aperçu d’import n’a pas pu être calculé.");
      invalidateCsrfOnRefusal(apiError);
      importState.preview = null;
      importState.error = apiError;
      importState.phase = "error";
      paintMcp();
    },
  );
}

function runImportApply(): void {
  const names = [...importState.selected];
  importState.applyPhase = "loading";
  importState.applyError = null;
  importState.result = null;
  paintMcp();
  const generation = stateGeneration;
  void mcpApi.applyImport({
    format: importState.format,
    content: importState.content,
    names,
    secretMapping: importState.mapping,
    onConflict: importState.onConflict,
  }).then(
    (result) => {
      if (generation !== stateGeneration) return;
      importState.result = result;
      importState.applyPhase = "ready";
      // Les entrées appliquées sont décochées : un second clic ne rejouerait pas l’import.
      importState.selected.clear();
      // La liste des serveurs a changé : elle est relue plutôt que devinée.
      void loadMcp({ silent: true });
      paintMcp();
    },
    (error: unknown) => {
      if (generation !== stateGeneration) return;
      const apiError = normalizeApiError(error, "L’import n’a pas pu être appliqué.");
      invalidateCsrfOnRefusal(apiError);
      importState.applyError = apiError;
      importState.applyPhase = "error";
      paintMcp();
    },
  );
}

function importFormNode(): HTMLElement {
  const form = el("form", "mcp-export-form");
  form.noValidate = true;
  const formatSelect = selectControl(
    "import-format",
    MCP_IMPORT_FORMATS.map((format) => ({
      value: format,
      label: IMPORT_FORMAT_LABELS[format],
      selected: importState.format === format,
    })),
  );
  const area = textArea("import-content", 10, {
    value: importState.content,
    placeholder: "Colle ici le contenu de config.yaml, .mcp.json ou config.toml",
    maxLength: MCP_IMPORT_MAX_CHARS,
  });
  const submit = el("button", "button button-primary", "Analyser (aucune écriture)");
  submit.type = "submit";
  submit.disabled = importState.phase === "loading";

  form.append(
    labeledField("Format", formatSelect, "La détection automatique reconnaît les trois formats."),
    labeledField(
      "Configuration à importer",
      area,
      "Le contenu est analysé côté serveur comme une donnée : il n’est ni exécuté ni appliqué à ce stade.",
    ),
    submit,
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const content = area.value;
    if (!content.trim()) {
      importState.error = new WorkspaceApiError("Colle une configuration à importer.", "http", 422);
      importState.phase = "error";
      importState.preview = null;
      paintMcp();
      return;
    }
    runImportPreview(content, formatSelect.value as McpImportFormat);
  });
  return form;
}

function importSelectionNode(preview: McpImportPreview): HTMLElement {
  const node = el("div", "mcp-export-result");
  const importable = preview.entries.filter((entry) => entry.importable);

  const conflictSelect = selectControl("import-on-conflict", [
    {
      value: "skip",
      label: "Nom déjà pris : ignorer l’entrée",
      selected: importState.onConflict === "skip",
    },
    {
      value: "new_revision",
      label: "Nom déjà pris : ajouter une révision (l’ancienne est conservée)",
      selected: importState.onConflict === "new_revision",
    },
  ]);
  conflictSelect.addEventListener("change", () => {
    importState.onConflict = conflictSelect.value === "new_revision" ? "new_revision" : "skip";
  });
  node.append(labeledField("Conflit de nom", conflictSelect));

  const apply = actionButton("Appliquer les entrées cochées", "primary", () => {
    if (!importState.selected.size) return;
    runImportApply();
  });
  /**
   * Le bouton suit l’état des cases à cocher sans repeindre la liste : une case cochée
   * l’active immédiatement, et le libellé dit combien d’entrées partiront.
   */
  const refresh = (): void => {
    const count = importState.selected.size;
    apply.disabled = count === 0 || importState.applyPhase === "loading";
    apply.textContent = count
      ? `Appliquer ${count} entrée(s) cochée(s)`
      : "Appliquer les entrées cochées";
    apply.title = count
      ? "Les serveurs sont créés en brouillon : diagnostic et activation restent à faire."
      : "Coche au moins une entrée importable : rien n’est importé implicitement.";
  };
  refresh();
  refreshImportApply = refresh;

  const actions = el("div", "mcp-actions");
  actions.append(apply);
  node.append(actions);
  node.append(el(
    "p",
    "mcp-block-hint",
    importable.length
      ? "Les serveurs importés restent en brouillon : ils ne sont ni diagnostiqués ni activés par l’import."
      : "Aucune entrée de cet aperçu n’est importable en l’état.",
  ));
  return node;
}

/**
 * Section « Import » : aperçu normalisé d’une configuration Hermes / Claude Code / Codex,
 * puis application des seules entrées cochées.
 *
 * Règles tenues ici : le contenu collé est une donnée (jamais interprétée dans le
 * navigateur), aucune valeur de secret ne circule (l’API ne renvoie que des candidats
 * masqués, reliés à un secret existant du coffre), et rien n’est créé sans choix
 * explicite — les serveurs importés arrivent en brouillon.
 */
export function renderMcpImportSection(container: HTMLElement): void {
  const node = block(
    "Import de configurations existantes",
    "Hermes (config.yaml), Claude Code (.mcp.json) et Codex (config.toml). L’aperçu n’écrit rien.",
  );
  node.dataset.module = "mcp-import";
  // Le rendu précédent est jeté : son bouton n’existe plus, sa mise à jour non plus.
  refreshImportApply = null;

  if (!mayManagePlatform()) {
    node.append(statePanel(
      "forbidden",
      "Réservé au propriétaire",
      "Seul le propriétaire de la plateforme peut importer des serveurs MCP.",
    ));
    container.append(node);
    return;
  }

  node.append(importFormNode());

  if (importState.phase === "loading") {
    node.append(statePanel("loading", "Analyse en cours", "Interrogation de l’API /mcp/import/preview…"));
    container.append(node);
    return;
  }
  if (importState.error) {
    node.append(errorPanel(importState.error));
    container.append(node);
    return;
  }

  const preview = importState.preview;
  if (!preview) {
    node.append(statePanel(
      "empty",
      "Aucun aperçu",
      "Colle une configuration puis lance l’analyse : les entrées, les secrets détectés et les points non supportés seront listés avant toute écriture.",
    ));
    container.append(node);
    return;
  }

  node.append(keyValueList([
    ["Format détecté", preview.detected_format ? IMPORT_FORMAT_LABELS[preview.detected_format] : "non reconnu"],
    ["Entrées trouvées", String(preview.entries.length)],
  ]));
  if (preview.errors.length) {
    node.append(el("p", "mcp-block-hint", "Analyse :"), bulletList(preview.errors));
  }
  if (!preview.entries.length) {
    node.append(statePanel(
      "empty",
      "Aucune entrée trouvée",
      "Ce contenu ne décrit aucun serveur MCP exploitable : rien n’a été importé.",
    ));
    container.append(node);
    return;
  }

  const list = el("div", "mcp-card-list");
  for (const entry of preview.entries) list.append(importEntryCard(entry));
  node.append(list);
  node.append(importSelectionNode(preview));

  if (importState.applyPhase === "loading") {
    node.append(statePanel("loading", "Import en cours", "Interrogation de l’API /mcp/import/apply…"));
  } else if (importState.applyError) {
    node.append(errorPanel(importState.applyError));
  } else if (importState.result) {
    node.append(importResultView(importState.result));
  }

  container.append(node);
}

// --- assemblage du centre MCP ----------------------------------------------

function paintMcp(): void {
  const root = mcpRoot;
  if (!root) return;
  root.replaceChildren();

  const header = sectionHeader(
    "Centre MCP",
    "Serveurs MCP déclarés, outils réellement découverts, autorisations de diagnostic et rattachements par projet.",
  );
  const headerChips = el("div", "mcp-header-chips");
  if (mcpState.phase === "ready") {
    headerChips.append(statusChip(`○ ${mcpState.servers.length} serveur(s)`, "queued"));
    if (mcpState.pendingProbes.length) {
      headerChips.append(statusChip(`! ${mcpState.pendingProbes.length} autorisation(s) en attente`, "waiting"));
    }
  }
  if (platformRole && !isOwner()) {
    headerChips.append(statusChip("! Lecture et rattachements seulement", "blocked"));
  }
  header.append(headerChips);
  root.append(header, noticeNode(mcpState.notice), tabList());

  const panel = el("div", "mcp-panel");
  panel.id = "mcp-tabpanel";
  panel.setAttribute("role", "tabpanel");
  panel.setAttribute("aria-labelledby", `mcp-tab-${mcpState.tab}`);
  panel.tabIndex = 0;

  if (mcpState.tab === "servers") panel.append(serversPanel());
  else if (mcpState.tab === "add") panel.append(addServerPanel());
  else if (mcpState.tab === "catalog") panel.append(catalogPanel());
  else if (mcpState.tab === "export") panel.append(exportPanel());
  else renderMcpImportSection(panel);

  root.append(panel);

  if (pendingTabFocus) {
    const target = root.querySelector<HTMLButtonElement>(`#mcp-tab-${pendingTabFocus}`);
    pendingTabFocus = null;
    target?.focus();
  }
}

/**
 * Rendu du centre MCP.
 *
 * `sharedHttp` est le client HTTP de l’appelant : le passer est **la** façon correcte de
 * câbler ce module, puisque le jeton CSRF de la session est alors partagé avec le shell.
 * Un client séparé devrait relire `/auth/session`, ce qui fait tourner le jeton côté
 * serveur et invalide celui des autres écrans. `role` est le rôle de plateforme lu par le
 * shell : fourni, il explique les restrictions avant l’appel ; absent, rien n’est
 * pré-filtré et l’API reste seule juge (un 403 est affiché tel quel).
 *
 * Chaque montage relit l’API : les données d’une visite précédente ne sont jamais
 * repeintes telles quelles (elles restent affichées pendant la relecture, pas au-delà).
 */
export function renderMcpCenter(
  container: HTMLElement,
  sharedHttp?: WorkspaceHttpClient,
  role?: PlatformRole | null,
): void {
  useHttpClient(sharedHttp);
  useRole(role);
  const section = el("section", "content-section mcp-center");
  section.dataset.module = "mcp-center";
  mcpRoot = section;
  container.append(section);
  paintMcp();
  queueMicrotask(() => void loadMcp({ silent: true }));
}

// --- coffre de secrets ------------------------------------------------------

function vaultUnconfiguredPanel(status: SecretsStatus): HTMLElement {
  const node = el("div", "mcp-panel-body");
  node.append(statePanel(
    "unconfigured",
    "Coffre de secrets non configuré",
    status.message || "Aucune clé de chiffrement n’est définie : la création de secrets est impossible.",
  ));
  const command = el("pre", "secrets-vault-command");
  command.textContent = [
    "python -m acp_api.secrets_vault generate-key",
    "ACP_SECRETS_KEYS=<clé Fernet générée>",
  ].join("\n");
  command.tabIndex = 0;
  node.append(
    el("p", "mcp-block-hint", "Action à effectuer sur le serveur d’API, puis redémarrage :"),
    command,
  );
  return node;
}

function secretRow(secret: SecretSummary): HTMLElement {
  const item = el("article", "list-item secrets-row");
  const copy = el("div", "list-item-copy");
  copy.append(
    el("h3", "list-item-title", secret.name),
    el("p", "list-item-meta", [
      secret.scope_type === "project"
        ? `Projet : ${secret.project_id ? projectLabel(secret.project_id) : "inconnu"}`
        : "Portée : plateforme",
      `Clé de chiffrement ${secret.key_id}`,
      `Créé le ${formatDateTime(secret.created_at)}`,
      `Rotation : ${optionalDateTime(secret.rotated_at)}`,
      `Dernier usage : ${optionalDateTime(secret.last_used_at)}`,
    ].join(" · ")),
  );
  if (secret.description) {
    const description = el("p", "list-item-meta");
    description.textContent = secret.description;
    copy.append(description);
  }
  copy.append(el(
    "p",
    "list-item-meta",
    secret.referenced_by_mcp_servers.length
      ? `Référencé par ${secret.referenced_by_mcp_servers.length} serveur(s) MCP`
      : "Référencé par aucun serveur MCP",
  ));

  const chips = el("div", "mcp-chips");
  chips.append(secret.revoked_at ? statusChip("✗ Révoqué", "failed") : statusChip("✓ Utilisable", "active"));
  copy.append(chips);

  const side = el("div", "mcp-row-side");
  if (!secret.revoked_at) {
    const actions = el("div", "secrets-row-actions");
    actions.append(actionButton(
      secretsState.rotatingId === secret.id ? "Annuler la rotation" : "Faire tourner",
      "secondary",
      () => {
        secretsState.rotatingId = secretsState.rotatingId === secret.id ? null : secret.id;
        paintSecrets();
      },
      { disabled: secretsState.busy },
    ));
    actions.append(actionButton(
      "Révoquer",
      "secondary",
      () => {
        if (!confirmAction(`Révoquer le secret « ${secret.name} » ? Les serveurs qui le référencent cesseront de fonctionner.`)) return;
        void runSecretsAction("Révocation du secret…", async () => {
          await secretsApi.revokeSecret(secret.id);
          secretsState.secrets = await secretsApi.listSecrets();
          return { tone: "warning", message: `Secret « ${secret.name} » révoqué.` };
        });
      },
      { disabled: secretsState.busy },
    ));
    side.append(actions);
    if (secretsState.rotatingId === secret.id) side.append(rotateForm(secret));
  } else {
    side.append(el("p", "list-item-meta", `Révoqué le ${formatDateTime(secret.revoked_at)}`));
  }

  item.append(copy, side);
  return item;
}

function rotateForm(secret: SecretSummary): HTMLElement {
  const form = el("form", "mcp-inline-form");
  form.noValidate = true;
  const valueInput = textInput("value", {
    type: "password",
    required: true,
    maxLength: 8192,
    autocomplete: "new-password",
    placeholder: "Nouvelle valeur",
  });
  const submit = el("button", "button button-primary", "Remplacer la valeur");
  submit.type = "submit";
  submit.disabled = secretsState.busy;
  form.append(
    labeledField(
      `Nouvelle valeur de ${secret.name}`,
      valueInput,
      "La valeur est envoyée une seule fois puis effacée du formulaire ; elle n’est jamais réaffichée.",
    ),
    submit,
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = valueInput.value;
    valueInput.value = "";
    if (!value.trim()) {
      secretsState.notice = { tone: "error", message: "La nouvelle valeur est requise." };
      paintSecrets();
      return;
    }
    void runSecretsAction("Rotation du secret…", async () => {
      const updated = await secretsApi.rotateSecret(secret.id, value);
      secretsState.rotatingId = null;
      secretsState.secrets = await secretsApi.listSecrets();
      return {
        tone: "success",
        message: `Valeur de « ${updated.name} » remplacée (clé ${updated.key_id}).`,
      };
    });
  });
  return form;
}

function createSecretForm(configured: boolean): HTMLElement {
  const node = block(
    "Ajouter un secret",
    "La valeur est chiffrée au repos par l’API et n’est jamais renvoyée au navigateur.",
  );

  if (platformRole === "viewer") {
    node.append(statePanel(
      "forbidden",
      "Réservé aux membres d’un projet",
      "Un compte en lecture seule ne peut pas créer de secret.",
    ));
    return node;
  }

  const form = el("form", "mcp-form");
  form.noValidate = true;
  const fieldset = el("fieldset", "mcp-fieldset");
  fieldset.append(el("legend", "", "Nouveau secret"));
  fieldset.disabled = !configured;

  const nameInput = textInput("name", {
    placeholder: "GITHUB_TOKEN",
    required: true,
    maxLength: 63,
  });
  const valueInput = textInput("value", {
    type: "password",
    required: true,
    maxLength: 8192,
    autocomplete: "new-password",
    placeholder: "Valeur à chiffrer",
  });
  const scopeSelect = selectControl("scopeType", [
    {
      value: "platform",
      label: mayManagePlatform() ? "Plateforme" : "Plateforme (réservé au propriétaire)",
      selected: mayManagePlatform(),
      disabled: !mayManagePlatform(),
    },
    { value: "project", label: "Projet", selected: !mayManagePlatform() },
  ]);
  const projectSelect = selectControl("projectId", mcpState.projects.length
    ? mcpState.projects.map((project) => ({ value: project.id, label: project.name }))
    : [{ value: "", label: "Aucun projet accessible", disabled: true }]);
  const descriptionInput = textInput("description", { placeholder: "À quoi sert ce secret ?", maxLength: 500 });

  function applyScope(): void {
    const projectScope = scopeSelect.value === "project";
    projectField.hidden = !projectScope;
    projectSelect.disabled = !projectScope;
  }
  const projectField = labeledField("Projet", projectSelect);
  scopeSelect.addEventListener("change", applyScope);

  const submit = el("button", "button button-primary", "Créer le secret");
  submit.type = "submit";
  submit.disabled = secretsState.busy || !configured;

  fieldset.append(
    labeledField("Nom", nameInput, "Majuscules, chiffres et « _ » : de 2 à 63 caractères (ex. GITHUB_TOKEN)."),
    labeledField("Valeur", valueInput, "Envoyée une seule fois ; le champ est vidé dès l’envoi."),
    labeledField("Portée", scopeSelect),
    projectField,
    labeledField("Description", descriptionInput),
    submit,
  );
  form.append(fieldset);
  applyScope();

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const scopeType = scopeSelect.value as SecretScopeType;
    const value = valueInput.value;
    valueInput.value = "";
    const input = {
      name: nameInput.value,
      value,
      scopeType,
      projectId: scopeType === "project" ? projectSelect.value || null : null,
      description: descriptionInput.value,
    };
    void runSecretsAction("Création du secret…", async () => {
      const created = await secretsApi.createSecret(input);
      nameInput.value = "";
      descriptionInput.value = "";
      secretsState.secrets = await secretsApi.listSecrets();
      return {
        tone: "success",
        message: `Secret « ${created.name} » enregistré (clé ${created.key_id}). Sa valeur n’est plus affichable.`,
      };
    });
  });

  if (!configured) {
    node.append(el("p", "form-hint", "Formulaire désactivé tant que ACP_SECRETS_KEYS n’est pas défini côté API."));
  }
  node.append(form);
  return node;
}

function paintSecrets(): void {
  const root = secretsRoot;
  if (!root) return;
  root.replaceChildren();

  const header = sectionHeader(
    "Coffre de secrets",
    "Références chiffrées au repos, injectées uniquement au moment d’un appel autorisé ; aucune valeur n’est affichée.",
  );
  const chips = el("div", "mcp-header-chips");
  const vault = secretsState.vault;
  if (vault) {
    chips.append(vault.configured
      ? statusChip(`✓ Coffre configuré (${vault.key_count} clé(s))`, "active")
      : statusChip("! Coffre non configuré", "blocked"));
    if (vault.configured && vault.primary_key_id) {
      chips.append(statusChip(`○ Clé primaire ${vault.primary_key_id}`, "queued"));
    }
  }
  header.append(chips);
  root.append(header, noticeNode(secretsState.notice));

  if (secretsState.phase === "loading" || secretsState.phase === "idle") {
    root.append(statePanel("loading", "Lecture du coffre", "Interrogation de l’API /secrets…"));
    return;
  }
  if (secretsState.error) {
    root.append(errorPanel(secretsState.error, () => void loadSecrets()));
    return;
  }

  if (vault && !vault.configured) {
    root.append(vaultUnconfiguredPanel(vault));
  }

  if (!secretsState.secrets.length) {
    root.append(statePanel(
      "empty",
      "Aucun secret enregistré",
      "Les serveurs MCP ne peuvent référencer que des secrets déjà créés ici.",
    ));
  } else {
    const list = el("div", "item-list secrets-list");
    for (const secret of secretsState.secrets) list.append(secretRow(secret));
    root.append(list);
  }

  root.append(createSecretForm(Boolean(vault?.configured)));
}

/** Mêmes règles que `renderMcpCenter` pour `sharedHttp` et `role` (client et jeton uniques). */
export function renderSecretsPanel(
  container: HTMLElement,
  sharedHttp?: WorkspaceHttpClient,
  role?: PlatformRole | null,
): void {
  useHttpClient(sharedHttp);
  useRole(role);
  const section = el("section", "content-section secrets-panel");
  section.dataset.module = "secrets-panel";
  secretsRoot = section;
  container.append(section);
  paintSecrets();
  queueMicrotask(() => void loadSecrets({ silent: true }));
}

/**
 * Efface tout ce que ce module garde en mémoire d’un compte : données lues, rôle,
 * sélection d’outils, client HTTP adopté et jeton CSRF.
 *
 * À appeler par le shell au même moment que ses propres purges (déconnexion et
 * connexion) : sans cela, la route « Connexions » repeindrait les serveurs, les noms de
 * secrets et le gating de rôle du compte précédent jusqu’au rechargement de la page.
 */
export function resetMcpUiState(): void {
  stateGeneration += 1;
  Object.assign(mcpState, initialMcpState());
  Object.assign(secretsState, initialSecretsState());
  Object.assign(importState, initialImportState());
  selectedTools.clear();
  refreshImportApply = null;
  mcpRoot = null;
  secretsRoot = null;
  pendingTabFocus = null;
  mcpLoading = false;
  secretsLoading = false;
  platformRole = null;
  useHttpClient(undefined);
  fallbackHttp.setCsrfToken(null);
  csrfReady = false;
}
