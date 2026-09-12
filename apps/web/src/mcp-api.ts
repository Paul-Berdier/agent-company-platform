/**
 * Client du centre MCP (`/mcp`, spec Lot D §5.2, import compris).
 *
 * Chaque réponse est validée par un validateur de forme strict (motif
 * `isRecord`/`hasString` de `workspace-api.ts`). Les configurations reçues ne
 * contiennent que des références de secret (`{ secret_id }`) : toute autre forme
 * dans `header_secrets`/`env_secrets` est refusée comme réponse invalide, ce qui
 * empêche l’affichage accidentel d’une valeur. Les identifiants sont toujours
 * encodés dans les chemins.
 */

import type {
  McpBinding,
  McpCatalogEntry,
  McpDiscoveredTool,
  McpDiscovery,
  McpExport,
  McpExportFormat,
  McpHttpConfig,
  McpImportApplyResult,
  McpImportEntry,
  McpImportFormat,
  McpImportPreview,
  McpImportSecretCandidate,
  McpProbe,
  McpProbeAuthorization,
  McpProbeResult,
  McpProbeStatus,
  McpRevisionDiff,
  McpRiskFlag,
  McpServerConfig,
  McpServerDetail,
  McpServerRevision,
  McpServerStatus,
  McpServerSummary,
  McpSourceKind,
  McpStdioConfig,
  McpTransport,
} from "@acp/contracts";

import {
  WorkspaceApiError,
  WorkspaceHttpClient,
  hasString,
  isRecord,
  type Fetcher,
} from "./workspace-api";

export interface McpServerCreateInput {
  name: string;
  displayName: string;
  description: string;
  sourceKind: McpSourceKind;
  origin: string;
  config: McpServerConfig;
  targetWorkerId: string | null;
  note: string;
}

export interface McpRevisionInput {
  config: McpServerConfig;
  targetWorkerId: string | null;
  note: string;
}

export interface McpBindingInput {
  projectId: string;
  allowedTools: string[];
}

export interface McpBindingPatchInput {
  allowedTools?: string[];
  enabled?: boolean;
}

export interface McpImportApplyInput {
  format: McpImportFormat;
  content: string;
  names: string[];
  secretMapping: Record<string, string>;
  onConflict: "skip" | "new_revision";
}

export interface McpBindingFilter {
  projectId?: string;
  serverId?: string;
}

/** Vue réduite d’un runner (`GET /workers`), lecture auxiliaire pour le choix du runner stdio. */
export interface RunnerSummary {
  id: string;
  name: string;
  status: string;
  capabilities: string[];
  simulation: boolean;
}

export const MCP_SERVER_STATUSES: readonly McpServerStatus[] = ["draft", "active", "disabled", "revoked"];
export const MCP_PROBE_STATUSES: readonly McpProbeStatus[] = [
  "pending_approval",
  "queued",
  "claimed",
  "succeeded",
  "failed",
  "rejected",
  "expired",
  "invalidated",
  "cancelled",
];
export const MCP_IMPORT_FORMATS: readonly McpImportFormat[] = ["auto", "hermes", "claude", "codex"];
/** Borne du contrat `McpImportPreviewRequest.content` : refusée localement avant tout appel. */
export const MCP_IMPORT_MAX_CHARS = 1_000_000;

const SOURCE_KINDS = new Set<string>(["catalog", "remote_url", "import", "manual"]);
const DETECTED_FORMATS = new Set<string>(["hermes", "claude", "codex"]);
const IMPORT_CONFLICTS = new Set<string>(["none", "existing_server"]);
const SECRET_LOCATIONS = new Set<string>(["header", "env", "url"]);
/** Champs qui trahiraient une valeur de secret dans un candidat d’import. */
const CANDIDATE_FORBIDDEN_KEYS = ["value", "secret_value", "plaintext", "secret"];
const RISK_LEVELS = new Set<string>(["info", "caution", "danger"]);
const EXPORT_FORMATS = new Set<string>(["hermes", "claude", "codex"]);
const SERVER_STATUSES = new Set<string>(MCP_SERVER_STATUSES);
const PROBE_STATUSES = new Set<string>(MCP_PROBE_STATUSES);

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNullableInteger(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isInteger(value));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isStringMap(value: unknown): value is Record<string, string> {
  return isRecord(value) && Object.values(value).every((item) => typeof item === "string");
}

function isTransport(value: unknown): value is McpTransport {
  return value === "http" || value === "stdio";
}

/** Une référence de secret est exactement `{ secret_id: string }` ; jamais une valeur. */
function isSecretRefMap(value: unknown): boolean {
  return isRecord(value) && Object.values(value).every((item) =>
    isRecord(item) && hasString(item, "secret_id") && Object.keys(item).length === 1);
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isHttpConfig(value: unknown): value is McpHttpConfig {
  return isRecord(value)
    && hasString(value, "url")
    && isStringMap(value.headers)
    && isSecretRefMap(value.header_secrets)
    && isPositiveInteger(value.timeout_seconds);
}

function isStdioConfig(value: unknown): value is McpStdioConfig {
  return isRecord(value)
    && hasString(value, "command")
    && isStringArray(value.args)
    && isStringMap(value.env)
    && isSecretRefMap(value.env_secrets)
    && isNullableString(value.cwd)
    && isPositiveInteger(value.timeout_seconds);
}

export function isMcpServerConfig(value: unknown): value is McpServerConfig {
  if (!isRecord(value) || !isTransport(value.transport)) return false;
  if (value.transport === "http") return isHttpConfig(value.http) && value.stdio === null;
  return isStdioConfig(value.stdio) && value.http === null;
}

export function isMcpDiscoveredTool(value: unknown): value is McpDiscoveredTool {
  return isRecord(value)
    && hasString(value, "name")
    && hasString(value, "description")
    && isRecord(value.input_schema);
}

function isDiscovery(value: unknown): value is McpDiscovery {
  return isRecord(value)
    && hasString(value, "protocol_version")
    && isRecord(value.server_info)
    && Array.isArray(value.tools)
    && value.tools.every(isMcpDiscoveredTool)
    && isRecord(value.capabilities)
    && typeof value.truncated === "boolean";
}

function isRiskFlag(value: unknown): value is McpRiskFlag {
  return isRecord(value)
    && hasString(value, "code")
    && RISK_LEVELS.has(String(value.level))
    && hasString(value, "message");
}

function isRevisionDiff(value: unknown): value is McpRevisionDiff {
  return isRecord(value)
    && isNullableInteger(value.previous_number)
    && isStringArray(value.changed_fields)
    && typeof value.endpoint_changed === "boolean"
    && typeof value.command_changed === "boolean"
    && isStringArray(value.secrets_added)
    && isStringArray(value.secrets_removed)
    && isStringArray(value.tools_added)
    && isStringArray(value.tools_removed)
    && typeof value.requires_approval === "boolean"
    && isStringArray(value.reasons);
}

export function isMcpServerRevision(value: unknown): value is McpServerRevision {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "server_id")
    && isPositiveInteger(value.number)
    && isMcpServerConfig(value.config)
    && hasString(value, "fingerprint")
    && (value.discovery === null || isDiscovery(value.discovery))
    && isNullableString(value.discovered_at)
    && typeof value.discovery_current === "boolean"
    && Array.isArray(value.risk_flags)
    && value.risk_flags.every(isRiskFlag)
    && (value.change_summary === null || isRevisionDiff(value.change_summary))
    && typeof value.requires_approval === "boolean"
    && hasString(value, "note")
    && hasString(value, "created_at")
    && isNullableString(value.superseded_at);
}

function isProbeAuthorization(value: unknown): value is McpProbeAuthorization {
  return isRecord(value)
    && value.action === "mcp_stdio_launch"
    && hasString(value, "target")
    && isStringArray(value.consequences)
    && isRecord(value.scope)
    && hasString(value, "fingerprint")
    && hasString(value, "expires_at");
}

function isProbeResult(value: unknown): value is McpProbeResult {
  return isRecord(value)
    && isNullableString(value.protocol_version)
    && (value.server_info === null || isRecord(value.server_info))
    && Array.isArray(value.tools)
    && value.tools.every(isMcpDiscoveredTool)
    && isNullableInteger(value.exit_code)
    && hasString(value, "stderr_tail")
    && isNullableInteger(value.duration_ms)
    && isNullableString(value.error);
}

export function isMcpProbe(value: unknown): value is McpProbe {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "server_id")
    && hasString(value, "revision_id")
    && isTransport(value.transport)
    && PROBE_STATUSES.has(String(value.status))
    && (value.authorization === null || isProbeAuthorization(value.authorization))
    && hasString(value, "requested_by_user_id")
    && isNullableString(value.decided_by_user_id)
    && isNullableString(value.decided_at)
    && hasString(value, "decision_comment")
    && isNullableString(value.worker_id)
    && isNullableString(value.claimed_at)
    && isNullableString(value.lease_expires_at)
    && (value.result === null || isProbeResult(value.result))
    && isNullableString(value.error)
    && hasString(value, "created_at")
    && isNullableString(value.finished_at)
    && hasString(value, "expires_at");
}

function isProbeList(value: unknown): value is McpProbe[] {
  return Array.isArray(value) && value.every(isMcpProbe);
}

export function isMcpBinding(value: unknown): value is McpBinding {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "server_id")
    && hasString(value, "server_name")
    && hasString(value, "project_id")
    && hasString(value, "revision_id")
    && isPositiveInteger(value.revision_number)
    && isStringArray(value.allowed_tools)
    && typeof value.enabled === "boolean"
    && hasString(value, "created_at")
    && hasString(value, "updated_at")
    && isNullableString(value.revoked_at);
}

function isBindingList(value: unknown): value is McpBinding[] {
  return Array.isArray(value) && value.every(isMcpBinding);
}

export function isMcpServerSummary(value: unknown): value is McpServerSummary {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "name")
    && hasString(value, "display_name")
    && hasString(value, "description")
    && SOURCE_KINDS.has(String(value.source_kind))
    && hasString(value, "origin")
    && isTransport(value.transport)
    && (value.execution_location === "platform" || value.execution_location === "runner")
    && SERVER_STATUSES.has(String(value.status))
    && isNullableInteger(value.current_revision_number)
    && typeof value.discovery_current === "boolean"
    && typeof value.tool_count === "number"
    && Number.isInteger(value.tool_count)
    && typeof value.binding_count === "number"
    && Number.isInteger(value.binding_count)
    && isNullableString(value.target_worker_id)
    && (value.last_probe_status === null || PROBE_STATUSES.has(String(value.last_probe_status)))
    && isNullableString(value.last_probe_at)
    && hasString(value, "created_at")
    && hasString(value, "updated_at")
    && isNullableString(value.revoked_at);
}

function isServerList(value: unknown): value is McpServerSummary[] {
  return Array.isArray(value) && value.every(isMcpServerSummary);
}

export function isMcpServerDetail(value: unknown): value is McpServerDetail {
  if (!isMcpServerSummary(value)) return false;
  const candidate = value as unknown as Record<string, unknown>;
  return (candidate.current_revision === null || isMcpServerRevision(candidate.current_revision))
    && Array.isArray(candidate.revisions)
    && candidate.revisions.every(isMcpServerRevision)
    && isBindingList(candidate.bindings)
    && isProbeList(candidate.probes)
    && isStringArray(candidate.apply_notes);
}

export function isMcpCatalogEntry(value: unknown): value is McpCatalogEntry {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "display_name")
    && hasString(value, "description")
    && isTransport(value.transport)
    && isMcpServerConfig(value.config)
    && isStringArray(value.required_secrets)
    && isStringArray(value.prerequisites)
    && isStringArray(value.risks)
    && hasString(value, "documentation_url")
    && hasString(value, "verified_at")
    && hasString(value, "verification");
}

function isCatalogList(value: unknown): value is McpCatalogEntry[] {
  return Array.isArray(value) && value.every(isMcpCatalogEntry);
}

/**
 * Un candidat de secret ne transporte **jamais** de valeur : `masked_value` est masquée
 * (`***` + deux caractères au plus) et aucun champ supplémentaire n’est toléré. Une réponse
 * qui fuirait une valeur est traitée comme un contrat violé, jamais affichée.
 */
export function isMcpImportSecretCandidate(value: unknown): value is McpImportSecretCandidate {
  if (!isRecord(value)) return false;
  if (CANDIDATE_FORBIDDEN_KEYS.some((key) => key in value)) return false;
  if (!SECRET_LOCATIONS.has(String(value.location))) return false;
  if (!hasString(value, "key") || !hasString(value, "suggested_secret_name")) return false;
  if (!hasString(value, "masked_value")) return false;
  const masked = value.masked_value as string;
  return masked.startsWith("***") && masked.length <= 5;
}

function isImportEntry(value: unknown): value is McpImportEntry {
  return isRecord(value)
    && hasString(value, "name")
    && hasString(value, "source_name")
    && (value.transport === null || isTransport(value.transport))
    && (value.config === null || isMcpServerConfig(value.config))
    && Array.isArray(value.secret_candidates)
    && value.secret_candidates.every(isMcpImportSecretCandidate)
    && isStringArray(value.unsupported)
    && isStringArray(value.warnings)
    && IMPORT_CONFLICTS.has(String(value.conflict))
    && typeof value.importable === "boolean";
}

export function isMcpImportPreview(value: unknown): value is McpImportPreview {
  return isRecord(value)
    && (value.detected_format === null || DETECTED_FORMATS.has(String(value.detected_format)))
    && Array.isArray(value.entries)
    && value.entries.every(isImportEntry)
    && isStringArray(value.errors);
}

export function isMcpImportApplyResult(value: unknown): value is McpImportApplyResult {
  return isRecord(value)
    && Array.isArray(value.created)
    && value.created.every(isMcpServerSummary)
    && Array.isArray(value.revised)
    && value.revised.every(isMcpServerSummary)
    && isStringArray(value.skipped)
    && isStringArray(value.errors);
}

export function isMcpExport(value: unknown): value is McpExport {
  return isRecord(value)
    && EXPORT_FORMATS.has(String(value.format))
    && isNullableString(value.project_id)
    && hasString(value, "content")
    && isStringArray(value.placeholders)
    && isStringArray(value.partial_compatibility)
    && isStringArray(value.apply_notes);
}

function isRunnerSnapshot(value: unknown): value is Record<string, unknown> & {
  id: string;
  name: string;
  status: string;
  capabilities: string[];
  simulation: boolean;
} {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "name")
    && hasString(value, "status")
    && isStringArray(value.capabilities)
    && typeof value.simulation === "boolean";
}

function isRunnerList(value: unknown): value is Array<Record<string, unknown> & RunnerSummary> {
  return Array.isArray(value) && value.every(isRunnerSnapshot);
}

function localRejection(message: string): WorkspaceApiError {
  return new WorkspaceApiError(message, "http", 422);
}

/** Refus local d’un contenu vide ou hors bornes : inutile d’envoyer ce que l’API refusera. */
function checkedImportContent(content: string): string {
  if (!content.trim()) throw localRejection("Colle une configuration à importer.");
  if (content.length > MCP_IMPORT_MAX_CHARS) {
    throw localRejection(
      `La configuration dépasse ${MCP_IMPORT_MAX_CHARS} caractères : importe-la par fichiers séparés.`,
    );
  }
  return content;
}

function serverPath(serverId: string, suffix = ""): string {
  return `/mcp/servers/${encodeURIComponent(serverId)}${suffix}`;
}

function serializeConfig(config: McpServerConfig): McpServerConfig {
  return config.transport === "http"
    ? { transport: "http", http: config.http, stdio: null }
    : { transport: "stdio", http: null, stdio: config.stdio };
}

export class McpApiClient {
  readonly http: WorkspaceHttpClient;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
    http?: WorkspaceHttpClient;
  } = {}) {
    this.http = options.http ?? new WorkspaceHttpClient(options);
  }

  // --- catalogue et serveurs -------------------------------------------------

  fetchCatalog(): Promise<McpCatalogEntry[]> {
    return this.http.request("/mcp/catalog", isCatalogList);
  }

  listServers(status?: McpServerStatus): Promise<McpServerSummary[]> {
    const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.http.request(`/mcp/servers${suffix}`, isServerList);
  }

  fetchServer(serverId: string): Promise<McpServerDetail> {
    return this.http.request(serverPath(serverId), isMcpServerDetail);
  }

  createServer(input: McpServerCreateInput): Promise<McpServerDetail> {
    return this.http.request("/mcp/servers", isMcpServerDetail, {
      method: "POST",
      body: JSON.stringify({
        name: input.name.trim(),
        display_name: input.displayName.trim(),
        description: input.description.trim(),
        source_kind: input.sourceKind,
        origin: input.origin.trim(),
        config: serializeConfig(input.config),
        target_worker_id: input.targetWorkerId?.trim() || null,
        note: input.note.trim(),
      }),
    });
  }

  createRevision(serverId: string, input: McpRevisionInput): Promise<McpServerDetail> {
    return this.http.request(serverPath(serverId, "/revisions"), isMcpServerDetail, {
      method: "POST",
      body: JSON.stringify({
        config: serializeConfig(input.config),
        target_worker_id: input.targetWorkerId?.trim() || null,
        note: input.note.trim(),
      }),
    });
  }

  rollbackServer(serverId: string, revisionNumber: number, note = ""): Promise<McpServerDetail> {
    return this.http.request(serverPath(serverId, "/rollback"), isMcpServerDetail, {
      method: "POST",
      body: JSON.stringify({ revision_number: revisionNumber, note: note.trim() }),
    });
  }

  // --- cycle de vie ---------------------------------------------------------

  activateServer(serverId: string): Promise<McpServerDetail> {
    return this.http.request(serverPath(serverId, "/activate"), isMcpServerDetail, { method: "POST" });
  }

  disableServer(serverId: string): Promise<McpServerDetail> {
    return this.http.request(serverPath(serverId, "/disable"), isMcpServerDetail, { method: "POST" });
  }

  /** Irréversible : la raison est obligatoire (contrôle local puis serveur). */
  async revokeServer(serverId: string, reason: string): Promise<McpServerDetail> {
    const trimmed = reason.trim();
    if (!trimmed) throw localRejection("La raison de la révocation est obligatoire.");
    if (trimmed.length > 2000) throw localRejection("La raison de la révocation dépasse 2000 caractères.");
    return this.http.request(serverPath(serverId, "/revoke"), isMcpServerDetail, {
      method: "POST",
      body: JSON.stringify({ reason: trimmed }),
    });
  }

  // --- probes ---------------------------------------------------------------

  probeServer(serverId: string): Promise<McpProbe> {
    return this.http.request(serverPath(serverId, "/probe"), isMcpProbe, { method: "POST" });
  }

  listServerProbes(serverId: string): Promise<McpProbe[]> {
    return this.http.request(serverPath(serverId, "/probes"), isProbeList);
  }

  listProbes(status?: McpProbeStatus): Promise<McpProbe[]> {
    const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.http.request(`/mcp/probes${suffix}`, isProbeList);
  }

  fetchProbe(probeId: string): Promise<McpProbe> {
    return this.http.request(`/mcp/probes/${encodeURIComponent(probeId)}`, isMcpProbe);
  }

  decideProbe(probeId: string, decision: "approved" | "rejected", comment = ""): Promise<McpProbe> {
    return this.http.request(`/mcp/probes/${encodeURIComponent(probeId)}/decision`, isMcpProbe, {
      method: "POST",
      body: JSON.stringify({ decision, comment: comment.trim() }),
    });
  }

  // --- bindings -------------------------------------------------------------

  async createBinding(serverId: string, input: McpBindingInput): Promise<McpBinding> {
    const tools = input.allowedTools.map((tool) => tool.trim()).filter(Boolean);
    if (!tools.length) throw localRejection("Sélectionne au moins un outil pour le rattachement.");
    return this.http.request(serverPath(serverId, "/bindings"), isMcpBinding, {
      method: "POST",
      body: JSON.stringify({ project_id: input.projectId, allowed_tools: tools }),
    });
  }

  listBindings(filter: McpBindingFilter = {}): Promise<McpBinding[]> {
    const query = new URLSearchParams();
    if (filter.projectId) query.set("project_id", filter.projectId);
    if (filter.serverId) query.set("server_id", filter.serverId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return this.http.request(`/mcp/bindings${suffix}`, isBindingList);
  }

  async updateBinding(bindingId: string, patch: McpBindingPatchInput): Promise<McpBinding> {
    const payload: Record<string, unknown> = {};
    if (patch.allowedTools !== undefined) {
      const tools = patch.allowedTools.map((tool) => tool.trim()).filter(Boolean);
      if (!tools.length) throw localRejection("Un rattachement conserve au moins un outil autorisé.");
      payload.allowed_tools = tools;
    }
    if (patch.enabled !== undefined) payload.enabled = patch.enabled;
    if (!Object.keys(payload).length) throw localRejection("Aucune modification à appliquer.");
    return this.http.request(`/mcp/bindings/${encodeURIComponent(bindingId)}`, isMcpBinding, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  revokeBinding(bindingId: string): Promise<McpBinding> {
    return this.http.request(`/mcp/bindings/${encodeURIComponent(bindingId)}`, isMcpBinding, {
      method: "DELETE",
    });
  }

  // --- import ---------------------------------------------------------------

  /**
   * Aperçu normalisé d’une configuration existante : seul le **contenu** est envoyé,
   * jamais un chemin de fichier (le serveur ne lit aucun fichier du poste client).
   * Aucune écriture n’a lieu ; les valeurs de secrets restent masquées côté serveur.
   */
  async previewImport(format: McpImportFormat, content: string): Promise<McpImportPreview> {
    return this.http.request("/mcp/import/preview", isMcpImportPreview, {
      method: "POST",
      body: JSON.stringify({ format, content: checkedImportContent(content) }),
    });
  }

  /** Applique les seules entrées explicitement choisies ; les serveurs créés restent en brouillon. */
  async applyImport(input: McpImportApplyInput): Promise<McpImportApplyResult> {
    const names: string[] = [];
    for (const raw of input.names) {
      const name = raw.trim();
      if (name && !names.includes(name)) names.push(name);
    }
    if (!names.length) throw localRejection("Choisis au moins une entrée à importer.");
    return this.http.request("/mcp/import/apply", isMcpImportApplyResult, {
      method: "POST",
      body: JSON.stringify({
        format: input.format,
        content: checkedImportContent(input.content),
        names,
        secret_mapping: { ...input.secretMapping },
        on_conflict: input.onConflict,
      }),
    });
  }

  // --- export ---------------------------------------------------------------

  exportServers(format: McpExportFormat, projectId?: string | null): Promise<McpExport> {
    const query = new URLSearchParams({ format });
    if (projectId) query.set("project_id", projectId);
    return this.http.request(`/mcp/export?${query.toString()}`, isMcpExport);
  }

  // --- lecture auxiliaire (hors §5.2) ---------------------------------------

  /** Runners connus, réduits aux champs utiles au choix d’un runner stdio. */
  async fetchRunners(): Promise<RunnerSummary[]> {
    const workers = await this.http.request("/workers", isRunnerList);
    return workers.map((worker) => ({
      id: worker.id,
      name: worker.name,
      status: worker.status,
      capabilities: worker.capabilities,
      simulation: worker.simulation,
    }));
  }
}
