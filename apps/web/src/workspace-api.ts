import type { AcpEvent, Overview, Project, TaskSummary } from "@acp/contracts";

export type ApiFailureKind = "offline" | "forbidden" | "http" | "invalid_response";

export class WorkspaceApiError extends Error {
  readonly kind: ApiFailureKind;
  readonly status: number | null;

  constructor(message: string, kind: ApiFailureKind, status: number | null = null) {
    super(message);
    this.name = "WorkspaceApiError";
    this.kind = kind;
    this.status = status;
  }
}

export interface ApprovalSummary {
  id: string;
  project_id: string;
  task_run_id: string | null;
  action: string;
  reason: string;
  status: string;
  expires_at: string;
}

export interface MissionInput {
  projectId: string;
  title: string;
  objective: string;
  expectedResult: string;
  acceptanceCriteria: string[];
  autonomy: "read_only" | "isolated_work" | "sensitive_on_approval";
  priority: number;
  durationSeconds: number;
  maxToolCalls: number;
}

export type MissionExecutionStatus =
  | "queued"
  | "preparing"
  | "running"
  | "waiting_approval"
  | "blocked"
  | "stopping"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface MissionEvidence {
  id: string;
  task_run_id: string;
  worker_id: string;
  kind: string;
  summary: string;
  data: Record<string, unknown>;
  command: string | null;
  exit_code: number | null;
  uri: string | null;
  checksum: string | null;
  created_at: string | null;
}

export interface MissionRunResource {
  id: string;
  mission_id: string;
  attempt_number: number;
  fencing_token: number;
  status: MissionExecutionStatus;
  stop_requested: boolean;
  technical_validation: {
    status: "pending" | "passed" | "failed";
    summary: string;
    checked_at: string | null;
  };
  user_acceptance: {
    status: "pending" | "accepted" | "rejected";
    comment: string;
    decided_by: string | null;
    decided_at: string | null;
  };
  evidence: MissionEvidence[];
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}

export interface MissionSummary {
  id: string;
  project_id: string;
  team_id: string | null;
  agent_instance_id: string | null;
  title: string;
  objective: string;
  expected_outcome: string;
  acceptance_criteria: string[];
  autonomy: {
    mode: "supervised" | "bounded" | "autonomous";
    allowed_actions: string[];
    forbidden_actions: string[];
    approval_required_actions: string[];
  };
  resources: Array<{
    kind: string;
    identifier: string;
    access: "read" | "write";
    description: string;
  }>;
  budget: {
    max_cost: number | null;
    currency: string;
    max_tokens: number | null;
    max_tool_calls: number | null;
  };
  duration_seconds: number;
  priority: number;
  required_capabilities: string[];
  status: MissionExecutionStatus;
  current_run: MissionRunResource;
  created_at: string | null;
}

export interface MissionDetail extends MissionSummary {
  runs: MissionRunResource[];
}

export interface MissionStopResponse {
  mission_id: string;
  run: MissionRunResource;
  already_stopped: boolean;
}

export interface MissionComment {
  id: string;
  mission_id: string;
  run_id: string | null;
  author_user_id: string;
  body: string;
  created_at: string | null;
}

interface TaskResource extends TaskSummary {
  description?: string;
  meta?: Record<string, unknown>;
}

export interface OnboardingStatus {
  bootstrap_completed: boolean;
  hermes_configured: boolean;
  hermes_ready: boolean;
  hermes_status: string;
  project_count: number;
  runner_ready: boolean;
}

export interface OnboardingProjectInput {
  name: string;
  projectType?: string;
  description?: string;
}

export type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type Validator<T> = (value: unknown) => value is T;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function hasString(value: Record<string, unknown>, key: string): boolean {
  return typeof value[key] === "string";
}

function isTaskResource(value: unknown): value is TaskResource {
  if (!isRecord(value)) return false;
  return hasString(value, "id")
    && hasString(value, "project_id")
    && hasString(value, "title")
    && hasString(value, "status");
}

const MISSION_STATUSES = new Set<MissionExecutionStatus>([
  "queued",
  "preparing",
  "running",
  "waiting_approval",
  "blocked",
  "stopping",
  "succeeded",
  "failed",
  "cancelled",
  "interrupted",
]);

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNonEmptyStringList(value: unknown, required = false): value is string[] {
  if (!Array.isArray(value) || value.length > 100 || (required && value.length === 0)) return false;
  return value.every((item) => typeof item === "string" && Boolean(item.trim()));
}

function isMissionEvidence(value: unknown): value is MissionEvidence {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "task_run_id")
    && hasString(value, "worker_id")
    && hasString(value, "kind")
    && hasString(value, "summary")
    && isRecord(value.data)
    && isNullableString(value.command)
    && (value.exit_code === null || typeof value.exit_code === "number")
    && isNullableString(value.uri)
    && isNullableString(value.checksum)
    && isNullableString(value.created_at);
}

function isMissionRun(value: unknown): value is MissionRunResource {
  if (!isRecord(value) || !hasString(value, "status")) return false;
  const technical = value.technical_validation;
  const acceptance = value.user_acceptance;
  return hasString(value, "id")
    && hasString(value, "mission_id")
    && typeof value.attempt_number === "number"
    && Number.isInteger(value.attempt_number)
    && typeof value.fencing_token === "number"
    && Number.isInteger(value.fencing_token)
    && MISSION_STATUSES.has(value.status as MissionExecutionStatus)
    && typeof value.stop_requested === "boolean"
    && isRecord(technical)
    && ["pending", "passed", "failed"].includes(String(technical.status))
    && typeof technical.summary === "string"
    && isNullableString(technical.checked_at)
    && isRecord(acceptance)
    && ["pending", "accepted", "rejected"].includes(String(acceptance.status))
    && typeof acceptance.comment === "string"
    && isNullableString(acceptance.decided_by)
    && isNullableString(acceptance.decided_at)
    && Array.isArray(value.evidence)
    && value.evidence.every(isMissionEvidence)
    && isNullableString(value.started_at)
    && isNullableString(value.finished_at)
    && isNullableString(value.created_at);
}

function isMissionAutonomy(value: unknown): value is MissionSummary["autonomy"] {
  return isRecord(value)
    && ["supervised", "bounded", "autonomous"].includes(String(value.mode))
    && Array.isArray(value.allowed_actions)
    && value.allowed_actions.length <= 100
    && value.allowed_actions.every((item) => typeof item === "string")
    && Array.isArray(value.forbidden_actions)
    && value.forbidden_actions.length <= 100
    && value.forbidden_actions.every((item) => typeof item === "string")
    && Array.isArray(value.approval_required_actions)
    && value.approval_required_actions.length <= 100
    && value.approval_required_actions.every((item) => typeof item === "string");
}

function isMissionResource(value: unknown): value is MissionSummary["resources"][number] {
  return isRecord(value)
    && typeof value.kind === "string"
    && value.kind.length >= 1
    && value.kind.length <= 100
    && typeof value.identifier === "string"
    && value.identifier.length >= 1
    && value.identifier.length <= 1_000
    && (value.access === "read" || value.access === "write")
    && typeof value.description === "string"
    && value.description.length <= 1_000;
}

function isMissionBudget(value: unknown): value is MissionSummary["budget"] {
  if (!isRecord(value)
    || !(value.max_cost === null
      || (typeof value.max_cost === "number" && Number.isFinite(value.max_cost) && value.max_cost >= 0))
    || typeof value.currency !== "string"
    || !/^[A-Za-z]{3}$/.test(value.currency)) return false;
  for (const key of ["max_tokens", "max_tool_calls"] as const) {
    const metric = value[key];
    if (!(metric === null || (Number.isSafeInteger(metric) && Number(metric) >= 0))) return false;
  }
  return value.max_cost !== null || value.max_tokens !== null || value.max_tool_calls !== null;
}

function isMissionSummary(value: unknown): value is MissionSummary {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "project_id")
    && isNullableString(value.team_id)
    && isNullableString(value.agent_instance_id)
    && hasString(value, "title")
    && hasString(value, "objective")
    && hasString(value, "expected_outcome")
    && isNonEmptyStringList(value.acceptance_criteria, true)
    && isMissionAutonomy(value.autonomy)
    && Array.isArray(value.resources)
    && value.resources.length <= 100
    && value.resources.every(isMissionResource)
    && isMissionBudget(value.budget)
    && Number.isSafeInteger(value.duration_seconds)
    && Number(value.duration_seconds) >= 1
    && Number(value.duration_seconds) <= 31_536_000
    && Number.isSafeInteger(value.priority)
    && Number(value.priority) >= 1
    && Number(value.priority) <= 5
    && isNonEmptyStringList(value.required_capabilities)
    && hasString(value, "status")
    && MISSION_STATUSES.has(value.status as MissionExecutionStatus)
    && isMissionRun(value.current_run)
    && isNullableString(value.created_at);
}

function isMissionDetail(value: unknown): value is MissionDetail {
  if (!isMissionSummary(value)) return false;
  const candidate = value as unknown as Record<string, unknown>;
  return Array.isArray(candidate.runs) && candidate.runs.every(isMissionRun);
}

function isMissionList(value: unknown): value is MissionSummary[] {
  return Array.isArray(value) && value.every(isMissionSummary);
}

function isMissionStopResponse(value: unknown): value is MissionStopResponse {
  return isRecord(value)
    && hasString(value, "mission_id")
    && typeof value.already_stopped === "boolean"
    && isMissionRun(value.run);
}

function isMissionComment(value: unknown): value is MissionComment {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "mission_id")
    && isNullableString(value.run_id)
    && hasString(value, "author_user_id")
    && hasString(value, "body")
    && isNullableString(value.created_at);
}

function isMissionCommentList(value: unknown): value is MissionComment[] {
  return Array.isArray(value) && value.every(isMissionComment);
}

function isProjectSummary(value: unknown): boolean {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "workspace_id")
    && hasString(value, "name")
    && hasString(value, "description")
    && hasString(value, "status");
}

function isProjectResource(value: unknown): value is Project {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "workspace_id")
    && (value.department_id === null || typeof value.department_id === "string")
    && hasString(value, "name")
    && hasString(value, "project_type")
    && hasString(value, "description")
    && hasString(value, "status");
}

function isOnboardingStatus(value: unknown): value is OnboardingStatus {
  return isRecord(value)
    && typeof value.bootstrap_completed === "boolean"
    && typeof value.hermes_configured === "boolean"
    && typeof value.hermes_ready === "boolean"
    && typeof value.hermes_status === "string"
    && typeof value.project_count === "number"
    && Number.isInteger(value.project_count)
    && value.project_count >= 0
    && typeof value.runner_ready === "boolean";
}

function isDepartmentSummary(value: unknown): boolean {
  return isRecord(value) && hasString(value, "id") && hasString(value, "name");
}

function isOverview(value: unknown): value is Overview {
  if (!isRecord(value)) return false;
  const arraysPresent = [
    "organizations",
    "workspaces",
    "departments",
    "projects",
    "teams",
    "team_members",
    "agents",
    "tasks",
  ].every((key) => Array.isArray(value[key]));
  return arraysPresent
    && (value.projects as unknown[]).every(isProjectSummary)
    && (value.departments as unknown[]).every(isDepartmentSummary)
    && (value.tasks as unknown[]).every(isTaskResource);
}

function isEventList(value: unknown): value is AcpEvent[] {
  return Array.isArray(value) && value.every((item) =>
    isRecord(item)
    && hasString(item, "id")
    && hasString(item, "type")
    && hasString(item, "occurred_at")
    && isRecord(item.payload));
}

function isApprovalList(value: unknown): value is ApprovalSummary[] {
  return Array.isArray(value) && value.every((item) =>
    isRecord(item)
    && hasString(item, "id")
    && hasString(item, "project_id")
    && hasString(item, "action")
    && hasString(item, "reason")
    && hasString(item, "status")
    && hasString(item, "expires_at"));
}

function asApiError(error: unknown): WorkspaceApiError {
  if (error instanceof WorkspaceApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new WorkspaceApiError("Le délai de réponse de l’API est dépassé.", "offline");
  }
  return new WorkspaceApiError("Impossible de joindre l’API métier.", "offline");
}

function defaultApiBaseUrl(): string {
  const configured = import.meta.env.VITE_ACP_API_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  return import.meta.env.DEV ? "http://localhost:8000" : "";
}

interface RequestSecurity {
  csrf?: boolean;
}

export class WorkspaceHttpClient {
  readonly baseUrl: string;
  private readonly fetcher: Fetcher;
  private readonly timeoutMs: number;
  private csrfToken: string | null = null;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
  } = {}) {
    this.baseUrl = (options.baseUrl ?? defaultApiBaseUrl()).replace(/\/$/, "");
    this.fetcher = options.fetcher ?? globalThis.fetch.bind(globalThis);
    this.timeoutMs = options.timeoutMs ?? 8_000;
  }

  setCsrfToken(token: string | null): void {
    this.csrfToken = token?.trim() || null;
  }

  async request<T>(
    path: string,
    validator: Validator<T>,
    init: RequestInit = {},
    security: RequestSecurity = {},
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), this.timeoutMs);
    const headers = new Headers(init.headers);
    headers.delete("Authorization");
    headers.set("Accept", "application/json");
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    const method = (init.method ?? "GET").toUpperCase();
    const mutation = method !== "GET" && method !== "HEAD" && method !== "OPTIONS";
    if (mutation && security.csrf !== false && this.csrfToken) {
      headers.set("X-CSRF-Token", this.csrfToken);
    }

    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        credentials: "include",
        signal: controller.signal,
      });
    } catch (error) {
      throw asApiError(error);
    } finally {
      globalThis.clearTimeout(timeout);
    }

    if (!response.ok) {
      const kind: ApiFailureKind = response.status === 401 || response.status === 403
        ? "forbidden"
        : "http";
      let detail = "";
      try {
        const payload: unknown = await response.json();
        if (isRecord(payload) && typeof payload.detail === "string") detail = payload.detail.trim();
      } catch {
        // Le statut HTTP reste la source de vérité lorsque le corps est inexploitable.
      }
      throw new WorkspaceApiError(
        detail || (kind === "forbidden"
          ? "Cette session n’est pas autorisée à accéder à cette ressource."
          : `L’API a répondu avec le statut ${response.status}.`),
        kind,
        response.status,
      );
    }

    let value: unknown;
    try {
      value = await response.json();
    } catch {
      throw new WorkspaceApiError("La réponse de l’API n’est pas un JSON valide.", "invalid_response");
    }
    if (!validator(value)) {
      throw new WorkspaceApiError("La réponse de l’API ne respecte pas le contrat attendu.", "invalid_response");
    }
    return value;
  }
}

export class WorkspaceApiClient {
  readonly http: WorkspaceHttpClient;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
    http?: WorkspaceHttpClient;
  } = {}) {
    this.http = options.http ?? new WorkspaceHttpClient(options);
  }

  fetchOverview(): Promise<Overview> {
    return this.http.request("/overview", isOverview);
  }

  fetchRecentEvents(limit = 40): Promise<AcpEvent[]> {
    const bounded = Math.max(1, Math.min(limit, 200));
    return this.http.request(`/events?limit=${bounded}`, isEventList);
  }

  fetchPendingApprovals(): Promise<ApprovalSummary[]> {
    return this.http.request("/approvals?status=WAITING_APPROVAL", isApprovalList);
  }

  fetchOnboardingStatus(): Promise<OnboardingStatus> {
    return this.http.request("/onboarding/status", isOnboardingStatus);
  }

  createOnboardingProject(input: OnboardingProjectInput): Promise<Project> {
    return this.http.request("/onboarding/projects", isProjectResource, {
      method: "POST",
      body: JSON.stringify({
        name: input.name.trim(),
        project_type: input.projectType?.trim() || "generic",
        description: input.description?.trim() || "",
      }),
    });
  }

  fetchMissions(): Promise<MissionSummary[]> {
    return this.http.request("/missions", isMissionList);
  }

  fetchMission(missionId: string): Promise<MissionDetail> {
    return this.http.request(`/missions/${encodeURIComponent(missionId)}`, isMissionDetail);
  }

  fetchMissionByRun(runId: string): Promise<MissionDetail> {
    return this.http.request(`/missions/by-run/${encodeURIComponent(runId)}`, isMissionDetail);
  }

  createMission(input: MissionInput, idempotencyKey: string): Promise<MissionDetail> {
    const autonomy = input.autonomy === "read_only"
      ? {
          mode: "supervised",
          allowed_actions: [],
          forbidden_actions: ["write", "external_effect"],
          approval_required_actions: [],
        }
      : {
          mode: "bounded",
          allowed_actions: ["read", "write_workspace"],
          forbidden_actions: [],
          approval_required_actions: input.autonomy === "sensitive_on_approval"
            ? ["external_effect", "sensitive_action"]
            : ["external_effect"],
        };
    return this.http.request("/missions", isMissionDetail, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        project_id: input.projectId,
        title: input.title.trim(),
        objective: input.objective.trim(),
        expected_outcome: input.expectedResult.trim(),
        acceptance_criteria: input.acceptanceCriteria,
        autonomy,
        resources: [],
        budget: { max_tool_calls: input.maxToolCalls },
        duration_seconds: input.durationSeconds,
        priority: input.priority,
      }),
    });
  }

  stopMission(missionId: string, idempotencyKey: string): Promise<MissionStopResponse> {
    return this.http.request(
      `/missions/${encodeURIComponent(missionId)}/stop`,
      isMissionStopResponse,
      { method: "POST", headers: { "Idempotency-Key": idempotencyKey } },
    );
  }

  retryMission(missionId: string, reason: string, idempotencyKey: string): Promise<MissionRunResource> {
    return this.http.request(
      `/missions/${encodeURIComponent(missionId)}/retry`,
      isMissionRun,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({ reason: reason.trim() }),
      },
    );
  }

  decideMissionAcceptance(
    missionId: string,
    runId: string,
    decision: "accepted" | "rejected",
    comment = "",
  ): Promise<MissionRunResource> {
    return this.http.request(
      `/missions/${encodeURIComponent(missionId)}/runs/${encodeURIComponent(runId)}/acceptance`,
      isMissionRun,
      { method: "POST", body: JSON.stringify({ decision, comment: comment.trim() }) },
    );
  }

  addMissionComment(
    missionId: string,
    runId: string,
    body: string,
    idempotencyKey: string,
  ): Promise<MissionComment> {
    return this.http.request(
      `/missions/${encodeURIComponent(missionId)}/comments`,
      isMissionComment,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({ run_id: runId, body: body.trim() }),
      },
    );
  }

  fetchMissionComments(missionId: string): Promise<MissionComment[]> {
    return this.http.request(
      `/missions/${encodeURIComponent(missionId)}/comments`,
      isMissionCommentList,
    );
  }
}
