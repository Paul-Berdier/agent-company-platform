import type { AcpEvent, Overview, TaskStatus, TaskSummary } from "@acp/contracts";

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

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type Validator<T> = (value: unknown) => value is T;

const SESSION_TOKEN_KEY = "acp.session-token";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasString(value: Record<string, unknown>, key: string): boolean {
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

export function readOptionalSessionToken(storage?: Pick<Storage, "getItem">): string | null {
  try {
    const source = storage ?? globalThis.sessionStorage;
    const value = source.getItem(SESSION_TOKEN_KEY)?.trim();
    return value || null;
  } catch {
    return null;
  }
}

function defaultApiBaseUrl(): string {
  const configured = import.meta.env.VITE_ACP_API_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  return import.meta.env.DEV ? "http://localhost:8000" : "";
}

export class WorkspaceApiClient {
  readonly baseUrl: string;
  private readonly fetcher: Fetcher;
  private readonly sessionToken: string | null;
  private readonly timeoutMs: number;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    sessionToken?: string | null;
    timeoutMs?: number;
  } = {}) {
    this.baseUrl = (options.baseUrl ?? defaultApiBaseUrl()).replace(/\/$/, "");
    this.fetcher = options.fetcher ?? globalThis.fetch.bind(globalThis);
    this.sessionToken = Object.hasOwn(options, "sessionToken")
      ? options.sessionToken ?? null
      : readOptionalSessionToken();
    this.timeoutMs = options.timeoutMs ?? 8_000;
  }

  private async request<T>(
    path: string,
    validator: Validator<T>,
    init: RequestInit = {},
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), this.timeoutMs);
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    if (this.sessionToken) headers.set("Authorization", `Bearer ${this.sessionToken}`);

    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        credentials: "same-origin",
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
      throw new WorkspaceApiError(
        kind === "forbidden"
          ? "Cette session n’est pas autorisée à accéder à cette ressource."
          : `L’API a répondu avec le statut ${response.status}.`,
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

  fetchOverview(): Promise<Overview> {
    return this.request("/overview", isOverview);
  }

  fetchRecentEvents(limit = 40): Promise<AcpEvent[]> {
    const bounded = Math.max(1, Math.min(limit, 200));
    return this.request(`/events?limit=${bounded}`, isEventList);
  }

  fetchPendingApprovals(): Promise<ApprovalSummary[]> {
    return this.request("/approvals?status=WAITING_APPROVAL", isApprovalList);
  }

  async createAndQueueMission(input: MissionInput): Promise<QueuedMission> {
    const created = await this.request("/tasks", isTaskResource, {
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
      queued = await this.request(
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
