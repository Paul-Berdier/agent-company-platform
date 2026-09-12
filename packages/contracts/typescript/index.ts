// Types TypeScript miroir des contrats Pydantic (version 1.0).

export type TaskStatus =
  | "backlog" | "queued" | "planning" | "in_progress" | "review" | "blocked" | "done" | "failed";

export type AgentStatus =
  | "idle" | "thinking" | "working" | "reviewing" | "blocked" | "offline";

export interface Organization { id: string; name: string; description: string }

export interface Workspace {
  id: string; organization_id: string; name: string; kind: string; description: string;
}

export interface Department {
  id: string; workspace_id: string; name: string;
  department_type: string; office_theme: string; config: Record<string, unknown>;
}

export interface Project {
  id: string; workspace_id: string; department_id: string | null;
  name: string; project_type: string; description: string; status: string;
}

export interface Team { id: string; project_id: string; name: string; mission: string }

export interface TeamMember {
  team_id: string; agent_instance_id: string; role_id: string | null;
}

export interface AgentInstance {
  id: string; workspace_id: string; team_id: string | null; name: string;
  role_id: string; module: string; status: AgentStatus; capabilities: string[];
}

export interface TaskSummary {
  id: string; project_id: string; team_id: string | null;
  agent_instance_id: string | null; title: string; status: TaskStatus;
  workflow_step: string | null; priority: number;
}

export interface Overview {
  organizations: Organization[];
  workspaces: Workspace[];
  departments: Department[];
  projects: Project[];
  teams: Team[];
  team_members: TeamMember[];
  agents: AgentInstance[];
  tasks: TaskSummary[];
}

export interface AcpEvent {
  id: string; type: string; occurred_at: string;
  organization_id: string | null; workspace_id: string | null;
  department_id: string | null; project_id: string | null; team_id: string | null;
  agent_instance_id: string | null; task_id: string | null; task_run_id: string | null;
  payload: Record<string, unknown>;
}

// --- Lot D : centre MCP, secrets, skills, extensions (miroir de acp_contracts.mcp/secrets/skills/extensions) ---

export type McpTransport = "http" | "stdio";
export type McpExecutionLocation = "platform" | "runner";
export type McpServerStatus = "draft" | "active" | "disabled" | "revoked";
export type McpProbeStatus =
  | "pending_approval" | "queued" | "claimed" | "succeeded" | "failed"
  | "rejected" | "expired" | "invalidated" | "cancelled";
export type McpSourceKind = "catalog" | "remote_url" | "import" | "manual";
export type McpRiskLevel = "info" | "caution" | "danger";
export type McpImportFormat = "auto" | "hermes" | "claude" | "codex";
export type McpExportFormat = "hermes" | "claude" | "codex";

/** Référence vers un secret du coffre ; jamais une valeur. */
export interface SecretRef { secret_id: string }

export interface McpHttpConfig {
  url: string;
  headers: Record<string, string>;
  header_secrets: Record<string, SecretRef>;
  timeout_seconds: number;
}

export interface McpStdioConfig {
  command: string;
  args: string[];
  env: Record<string, string>;
  env_secrets: Record<string, SecretRef>;
  cwd: string | null;
  timeout_seconds: number;
}

export interface McpServerConfig {
  transport: McpTransport;
  http: McpHttpConfig | null;
  stdio: McpStdioConfig | null;
}

export interface McpRiskFlag { code: string; level: McpRiskLevel; message: string }

export interface McpDiscoveredTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface McpDiscovery {
  protocol_version: string;
  server_info: Record<string, unknown>;
  tools: McpDiscoveredTool[];
  capabilities: Record<string, unknown>;
  truncated: boolean;
}

export interface McpRevisionDiff {
  previous_number: number | null;
  changed_fields: string[];
  endpoint_changed: boolean;
  command_changed: boolean;
  secrets_added: string[];
  secrets_removed: string[];
  tools_added: string[];
  tools_removed: string[];
  requires_approval: boolean;
  reasons: string[];
}

export interface McpServerRevision {
  id: string;
  server_id: string;
  number: number;
  config: McpServerConfig;
  fingerprint: string;
  discovery: McpDiscovery | null;
  discovered_at: string | null;
  discovery_current: boolean;
  risk_flags: McpRiskFlag[];
  change_summary: McpRevisionDiff | null;
  requires_approval: boolean;
  note: string;
  created_at: string;
  superseded_at: string | null;
}

export interface McpProbeAuthorization {
  action: "mcp_stdio_launch";
  target: string;
  consequences: string[];
  scope: Record<string, unknown>;
  fingerprint: string;
  expires_at: string;
}

export interface McpProbeResult {
  protocol_version: string | null;
  server_info: Record<string, unknown> | null;
  tools: McpDiscoveredTool[];
  exit_code: number | null;
  stderr_tail: string;
  duration_ms: number | null;
  error: string | null;
}

export interface McpProbe {
  id: string;
  server_id: string;
  revision_id: string;
  transport: McpTransport;
  status: McpProbeStatus;
  authorization: McpProbeAuthorization | null;
  requested_by_user_id: string;
  decided_by_user_id: string | null;
  decided_at: string | null;
  decision_comment: string;
  worker_id: string | null;
  claimed_at: string | null;
  lease_expires_at: string | null;
  result: McpProbeResult | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  expires_at: string;
}

export interface McpBinding {
  id: string;
  server_id: string;
  server_name: string;
  project_id: string;
  revision_id: string;
  revision_number: number;
  allowed_tools: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
}

export interface McpServerSummary {
  id: string;
  name: string;
  display_name: string;
  description: string;
  source_kind: McpSourceKind;
  origin: string;
  transport: McpTransport;
  execution_location: McpExecutionLocation;
  status: McpServerStatus;
  current_revision_number: number | null;
  discovery_current: boolean;
  tool_count: number;
  binding_count: number;
  target_worker_id: string | null;
  last_probe_status: McpProbeStatus | null;
  last_probe_at: string | null;
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
}

export interface McpServerDetail extends McpServerSummary {
  current_revision: McpServerRevision | null;
  revisions: McpServerRevision[];
  bindings: McpBinding[];
  probes: McpProbe[];
  apply_notes: string[];
}

export interface McpCatalogEntry {
  id: string;
  display_name: string;
  description: string;
  transport: McpTransport;
  config: McpServerConfig;
  required_secrets: string[];
  prerequisites: string[];
  risks: string[];
  documentation_url: string;
  verified_at: string;
  verification: string;
}

export interface McpImportSecretCandidate {
  location: "header" | "env" | "url";
  key: string;
  suggested_secret_name: string;
  masked_value: string;
}

export interface McpImportEntry {
  name: string;
  source_name: string;
  transport: McpTransport | null;
  config: McpServerConfig | null;
  secret_candidates: McpImportSecretCandidate[];
  unsupported: string[];
  warnings: string[];
  conflict: "none" | "existing_server";
  importable: boolean;
}

export interface McpImportPreview {
  detected_format: "hermes" | "claude" | "codex" | null;
  entries: McpImportEntry[];
  errors: string[];
}

export interface McpImportApplyResult {
  created: McpServerSummary[];
  revised: McpServerSummary[];
  skipped: string[];
  errors: string[];
}

export interface McpExport {
  format: McpExportFormat;
  project_id: string | null;
  content: string;
  placeholders: string[];
  partial_compatibility: string[];
  apply_notes: string[];
}

export type SecretScopeType = "platform" | "project";

export interface SecretSummary {
  id: string;
  name: string;
  scope_type: SecretScopeType;
  project_id: string | null;
  description: string;
  key_id: string;
  created_at: string;
  rotated_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  referenced_by_mcp_servers: string[];
}

export interface SecretsStatus {
  configured: boolean;
  primary_key_id: string | null;
  key_count: number;
  message: string;
}

export type SkillKind = "documentary" | "scripted" | "native_plugin";
export type SkillStatus = "draft" | "active" | "disabled" | "revoked";
export type SkillSourceKind = "manual" | "directory" | "archive" | "github" | "catalog";
export type SkillFindingLevel = "info" | "caution" | "danger";

export interface SkillFile { path: string; size: number; sha256: string; text: boolean }

export interface SkillDependencies {
  required_environment_variables: Record<string, unknown>[];
  requires_toolsets: string[];
  requires_tools: string[];
  scripts: string[];
  network_indicators: string[];
  platforms: string[];
}

export interface SkillScanFinding {
  level: SkillFindingLevel;
  code: string;
  message: string;
  path: string | null;
}

export interface SkillRevisionDiff {
  previous_number: number | null;
  files_added: string[];
  files_removed: string[];
  files_changed: string[];
  scripts_added: string[];
  network_indicators_added: string[];
  permissions_added: string[];
  kind_changed: boolean;
  requires_approval: boolean;
  reasons: string[];
}

export interface SkillRevision {
  id: string;
  skill_id: string;
  number: number;
  fingerprint: string;
  files: SkillFile[];
  frontmatter: Record<string, unknown>;
  license: string | null;
  dependencies: SkillDependencies;
  scan: SkillScanFinding[];
  kind: SkillKind;
  change_summary: SkillRevisionDiff | null;
  requires_approval: boolean;
  approved: boolean;
  approved_at: string | null;
  source_ref: string;
  note: string;
  created_at: string;
  superseded_at: string | null;
}

export interface SkillBinding {
  id: string;
  skill_id: string;
  skill_name: string;
  project_id: string;
  revision_id: string;
  revision_number: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
}

export interface SkillSummary {
  id: string;
  name: string;
  display_name: string;
  description: string;
  category: string;
  kind: SkillKind;
  source_kind: SkillSourceKind;
  origin: string;
  status: SkillStatus;
  current_revision_number: number | null;
  binding_count: number;
  requires_approval: boolean;
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
}

export interface SkillDetail extends SkillSummary {
  current_revision: SkillRevision | null;
  revisions: SkillRevision[];
  bindings: SkillBinding[];
  apply_notes: string[];
}

export interface SkillFileContent {
  path: string;
  text: boolean;
  content: string | null;
  truncated: boolean;
  size: number;
  sha256: string;
}

export interface SkillCatalogEntry {
  id: string;
  display_name: string;
  description: string;
  repository: string;
  path: string;
  documentation_url: string;
  license: string | null;
  verified_at: string;
  verification: string;
  note: string;
}

export interface SkillSearchResult {
  installed: SkillSummary[];
  catalog: SkillCatalogEntry[];
}

export interface ProjectMcpExtension {
  server_id: string;
  name: string;
  revision_number: number;
  allowed_tools: string[];
  enabled: boolean;
  server_status: McpServerStatus;
}

export interface ProjectSkillExtension {
  skill_id: string;
  name: string;
  revision_number: number;
  enabled: boolean;
  skill_status: SkillStatus;
}

export interface ProjectExtensions {
  project_id: string;
  mcp: ProjectMcpExtension[];
  skills: ProjectSkillExtension[];
  resolved_at: string;
}

export interface StationDef { id: string; name: string; kind: string; x: number; y: number }

export interface OfficeConfig {
  department_id?: string;
  department_type: string;
  office_theme: string;
  stations: StationDef[];
  available_animations: string[];
  status_mapping: Record<string, string>;
  /** présents quand un template de salle a été sélectionné */
  template_id?: string;
  width?: number;
  height?: number;
  capacity?: number;
  doors?: { x: number; y: number }[];
  windows?: number[];
  upgrade_to?: string | null;
}
