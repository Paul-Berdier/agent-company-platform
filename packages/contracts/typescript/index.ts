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

/** Miroir de `acp_contracts.conversations` : lecture seule du natif Hermes. */
export type HermesNativeListingStatus =
  | "available"
  | "unavailable"
  | "not_configured"
  | "unsupported";

export interface HermesNativeSkill {
  name: string;
  description: string;
  category: string;
}

export interface HermesNativeToolset {
  name: string;
  label: string;
  description: string;
  enabled: boolean;
  configured: boolean;
  tools: string[];
}

/** `read_at` n’est renseigné que lorsque les listes ont réellement été lues. */
export interface HermesNativeListing {
  status: HermesNativeListingStatus;
  skills: HermesNativeSkill[];
  toolsets: HermesNativeToolset[];
  message: string;
  read_at: string | null;
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

// --- Lot E : flux durable, tests structurés et bibliothèque de livrables ------

/** Version du schéma d’événement transporté par le flux (`StreamEvent`). */
export const EVENT_SCHEMA_VERSION = "1.0";

/**
 * Événement rendu par le flux SSE et par les lectures paginées.
 *
 * `sequence` est le curseur de reprise alloué par tentative ; il est `null` pour
 * les événements historiques et pour ceux qui n’appartiennent pas à un run.
 * Aucun média ne transite ici : le `payload` d’un événement de média ne porte
 * qu’une référence d’artefact.
 */
export interface StreamEvent {
  schema_version: string;
  id: string;
  sequence: number | null;
  type: string;
  occurred_at: string;
  project_id: string | null;
  conversation_id: string | null;
  task_id: string | null;
  task_run_id: string | null;
  step_id: string | null;
  executor: string | null;
  emitted_by: string | null;
  payload: Record<string, unknown>;
}

/** Page de journal : `retention_days` vaut 0 quand la rétention est illimitée. */
export interface EventPage {
  events: StreamEvent[];
  next_cursor: number | null;
  has_more: boolean;
  retention_days: number | null;
}

/** Statuts Playwright conservés distinctement, jamais réduits à vert/rouge. */
export type TestStatus = "passed" | "failed" | "timedOut" | "skipped" | "interrupted";

export type TestOutcome = "expected" | "unexpected" | "flaky" | "skipped";

export type TestRunStatus =
  | "running"
  | "completed"
  | "failed"
  | "interrupted"
  | "timed_out";

export interface TestStep {
  title: string;
  category: string;
  duration_ms: number;
  error: boolean;
}

export interface TestTotals {
  expected: number;
  unexpected: number;
  flaky: number;
  skipped: number;
  interrupted: number;
  timedOut: number;
}

export interface TestCaseResult {
  id: string;
  test_run_id: string;
  suite_path: string[];
  title: string;
  test_id: string;
  location: Record<string, unknown>;
  project_name: string;
  attempt: number;
  expected_status: string;
  status: TestStatus;
  outcome: TestOutcome;
  duration_ms: number;
  error_message: string;
  error_snippet: string;
  steps: TestStep[];
  annotations: Record<string, unknown>[];
  attachments: ArtifactSummary[];
}

export interface TestRunSummary {
  id: string;
  task_run_id: string;
  project_id: string;
  worker_id: string | null;
  runner: string;
  runner_version: string;
  status: TestRunStatus;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  totals: TestTotals;
  exit_code: number | null;
  config: Record<string, unknown>;
  case_count: number;
}

export interface TestRunDetail extends TestRunSummary {
  cases: TestCaseResult[];
  report_artifact: ArtifactSummary | null;
}

/**
 * Métadonnées d’un livrable. La clé de stockage n’est jamais publiée :
 * `has_content` distingue un contenu téléversé d’un artefact « métadonnées seules ».
 */
export interface ArtifactSummary {
  id: string;
  project_id: string;
  task_run_id: string;
  kind: string;
  stream_kind: string;
  original_name: string;
  content_type: string;
  size_bytes: number | null;
  checksum: string | null;
  source: string;
  has_content: boolean;
  created_at: string | null;
}

/** Lien signé, borné dans le temps, lié à un artefact et à un utilisateur. */
export interface ArtifactLink {
  artifact_id: string;
  url: string;
  expires_at: string;
}

export interface ArtifactPage {
  items: ArtifactSummary[];
  next_cursor: string | null;
}

// --- Lot F : automatisations, calendrier, budgets et alertes -----------------

export type AutomationScheduleKind = "cron" | "interval";
export type AutomationCatchupPolicy = "skip" | "run_once";
export type AutomationTriggerKind = "manual" | "schedule" | "webhook";
export type AutomationRunOutcome =
  | "launched"
  | "skipped_concurrency"
  | "skipped_disabled"
  | "failed";
export type CalendarEntryState = "planned" | "past";
export type BudgetState = "unknown" | "ok" | "warning" | "exceeded";
export type BudgetLimitName = "max_cost" | "max_tokens" | "max_tool_calls";
export type BudgetUsagePhase = "planning" | "execution" | "evaluation" | "tool";
export type BudgetUsageSource = "provider" | "platform";
export type AlertSeverity = "info" | "warning" | "critical";
export type NotificationChannel = "in_app";

export interface AutomationSchedule {
  kind: AutomationScheduleKind;
  expression: string;
  timezone: string;
}

export interface AutomationScheduleInput {
  kind: AutomationScheduleKind;
  expression: string;
  timezone?: string;
}

export interface AutomationMissionAutonomy {
  mode: "supervised" | "bounded" | "autonomous";
  allowed_actions: string[];
  forbidden_actions: string[];
  approval_required_actions: string[];
}

export interface AutomationMissionAutonomyInput {
  mode?: "supervised" | "bounded" | "autonomous";
  allowed_actions?: string[];
  forbidden_actions?: string[];
  approval_required_actions?: string[];
}

export interface AutomationMissionResource {
  kind: string;
  identifier: string;
  access: "read" | "write";
  description: string;
}

export interface AutomationMissionResourceInput {
  kind: string;
  identifier: string;
  access?: "read" | "write";
  description?: string;
}

export interface AutomationMissionBudget {
  max_cost: number | null;
  currency: string;
  max_tokens: number | null;
  max_tool_calls: number | null;
}

export interface AutomationMissionBudgetInput {
  max_cost?: number | null;
  currency?: string;
  max_tokens?: number | null;
  max_tool_calls?: number | null;
}

export interface AutomationMissionTemplate {
  title: string;
  objective: string;
  expected_outcome: string;
  acceptance_criteria: string[];
  autonomy: AutomationMissionAutonomy;
  resources: AutomationMissionResource[];
  budget: AutomationMissionBudget;
  duration_seconds: number;
  team_id: string | null;
  agent_instance_id: string | null;
  priority: number;
  required_capabilities: string[];
}

export interface AutomationMissionTemplateInput {
  title: string;
  objective: string;
  expected_outcome: string;
  acceptance_criteria: string[];
  autonomy: AutomationMissionAutonomyInput;
  resources?: AutomationMissionResourceInput[];
  budget: AutomationMissionBudgetInput;
  duration_seconds: number;
  team_id?: string | null;
  agent_instance_id?: string | null;
  priority?: number;
  required_capabilities?: string[];
}

export interface AutomationCreate {
  name: string;
  description?: string;
  schedule: AutomationScheduleInput;
  mission_template: AutomationMissionTemplateInput;
  catchup_policy?: AutomationCatchupPolicy;
  max_concurrent_runs?: number;
}

export interface AutomationUpdate {
  name?: string;
  description?: string;
  schedule?: AutomationScheduleInput;
  mission_template?: AutomationMissionTemplateInput;
  catchup_policy?: AutomationCatchupPolicy;
  max_concurrent_runs?: number;
}

export interface AutomationSummary {
  id: string;
  project_id: string;
  name: string;
  description: string;
  schedule: AutomationSchedule;
  enabled: boolean;
  catchup_policy: AutomationCatchupPolicy;
  max_concurrent_runs: number;
  next_run_at: string | null;
  created_at: string | null;
}

export interface AutomationRunSummary {
  id: string;
  automation_id: string;
  fire_key: string;
  scheduled_for: string;
  fired_at: string;
  task_id: string | null;
  trigger_kind: AutomationTriggerKind;
  outcome: AutomationRunOutcome;
  detail: string;
}

export interface AutomationDetail extends AutomationSummary {
  mission_template: AutomationMissionTemplate;
  recent_runs: AutomationRunSummary[];
}

export interface CalendarEntry {
  occurs_at_utc: string;
  occurs_at_local: string;
  timezone: string;
  utc_offset_minutes: number;
  automation_id: string;
  automation_name: string;
  state: CalendarEntryState;
  task_id: string | null;
  outcome: AutomationRunOutcome | null;
}

export interface AutomationWebhookTrigger {
  event_id: string;
  payload?: Record<string, unknown>;
}

export interface AutomationWebhookStatus {
  enabled: boolean;
  secret_configured: boolean;
  endpoint_path: string;
  rotated_at: string | null;
}

export interface AutomationWebhookSecret extends AutomationWebhookStatus {
  secret: string;
}

export interface BudgetUsageDelta {
  report_id: string;
  permit_id?: string | null;
  provider: string;
  phase: BudgetUsagePhase;
  source: BudgetUsageSource;
  cost?: number | null;
  currency?: string | null;
  tokens_input?: number | null;
  tokens_output?: number | null;
  tool_calls?: number | null;
  estimated?: boolean;
}

export interface BudgetPermitRequest {
  permit_id: string;
  provider: string;
  phase: BudgetUsagePhase;
  cost?: number | null;
  currency?: string | null;
  tokens_input?: number | null;
  tokens_output?: number | null;
  tool_calls?: number | null;
}

export interface ProviderBudgetLimit {
  provider: string;
  budget: AutomationMissionBudget;
}

export interface ProviderBudgetLimitInput {
  provider: string;
  budget: AutomationMissionBudgetInput;
}

export interface ProjectBudgetPolicy {
  timezone: string;
  daily_budget: AutomationMissionBudget | null;
  provider_budgets: ProviderBudgetLimit[];
  max_concurrent_missions: number;
  max_retries_per_mission: number;
  max_spawned_agents_per_run: number;
}

export interface ProjectBudgetPolicyInput {
  timezone?: string;
  daily_budget?: AutomationMissionBudgetInput | null;
  provider_budgets?: ProviderBudgetLimitInput[];
  max_concurrent_missions?: number;
  max_retries_per_mission?: number;
  max_spawned_agents_per_run?: number;
}

export interface ProjectBudgetPolicySummary extends ProjectBudgetPolicy {
  project_id: string;
  updated_at: string | null;
}

export interface BudgetVerdict {
  state: BudgetState;
  measured: boolean;
  limit_reached: BudgetLimitName | null;
  cost: number | null;
  currency: string;
  tokens_input: number | null;
  tokens_output: number | null;
  tool_calls: number | null;
  usage_reported: boolean;
  estimated: boolean;
}

export interface BudgetMutationResult {
  accepted: boolean;
  idempotent: boolean;
  permit_allowed: boolean;
  verdict: BudgetVerdict;
}

export interface AlertSummary {
  id: string;
  project_id: string;
  kind: string;
  severity: AlertSeverity;
  title: string;
  detail: string;
  task_id: string | null;
  automation_id: string | null;
  acknowledged_at: string | null;
  acknowledged_by_user_id: string | null;
  acknowledgement_comment: string;
  created_at: string | null;
}

export interface AlertAcknowledge {
  comment?: string;
}

export interface NotificationPreferences {
  channel?: NotificationChannel;
  enabled?: boolean;
  minimum_severity?: AlertSeverity;
  budget_alerts?: boolean;
  automation_failures?: boolean;
  storage_alerts?: boolean;
}

export interface NotificationPreferencesSummary {
  channel: NotificationChannel;
  enabled: boolean;
  minimum_severity: AlertSeverity;
  budget_alerts: boolean;
  automation_failures: boolean;
  storage_alerts: boolean;
  project_id: string;
  updated_at: string | null;
}
