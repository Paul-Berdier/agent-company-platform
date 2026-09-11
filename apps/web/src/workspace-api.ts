import type { AcpEvent, Overview, Project, TaskStatus, TaskSummary } from "@acp/contracts";

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

export class MissionQueueError extends Error {
  readonly taskId: string;
  readonly cause: WorkspaceApiError;

  constructor(taskId: string, cause: WorkspaceApiError) {
    super(`La mission ${taskId} a été créée, mais sa mise en file a échoué.`);
    this.name = "MissionQueueError";
    this.taskId = taskId;
    this.cause = cause;
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
  acceptanceCriteria: string;
  autonomy: "read_only" | "isolated_work" | "sensitive_on_approval";
  priority: number;
}

export interface TaskResource extends TaskSummary {
  description?: string;
  meta?: Record<string, unknown>;
}

export interface QueuedMission {
  created: TaskResource;
  queued: TaskResource;
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

  async createAndQueueMission(input: MissionInput): Promise<QueuedMission> {
    const created = await this.http.request("/tasks", isTaskResource, {
      method: "POST",
      body: JSON.stringify({
        project_id: input.projectId,
        title: input.title,
        description: input.objective,
        priority: input.priority,
        meta: {
          kind: "mission",
          source: "web-workspace",
          expected_result: input.expectedResult,
          acceptance_criteria: input.acceptanceCriteria,
          autonomy: input.autonomy,
        },
      }),
    });

    let queued: TaskResource;
    try {
      queued = await this.http.request(
        `/tasks/${encodeURIComponent(created.id)}/queue`,
        isTaskResource,
        { method: "POST" },
      );
    } catch (error) {
      throw new MissionQueueError(created.id, asApiError(error));
    }

    if (queued.id !== created.id || queued.status !== ("queued" satisfies TaskStatus)) {
      throw new MissionQueueError(
        created.id,
        new WorkspaceApiError(
          "La réponse de mise en file ne confirme pas l’état « queued ».",
          "invalid_response",
        ),
      );
    }
    return { created, queued };
  }
}
