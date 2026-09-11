import type { AcpEvent, OfficeConfig, Overview } from "@acp/contracts";

import { AuthApiClient } from "./auth-api";
import { WorkspaceHttpClient, isRecord } from "./workspace-api";

export const API_URL = import.meta.env.VITE_ACP_API_URL ?? "http://localhost:8000";
export const EVENTS_WS_URL =
  import.meta.env.VITE_ACP_EVENTS_WS_URL ?? "ws://localhost:8001/ws";

const legacyHttp = new WorkspaceHttpClient({ baseUrl: API_URL });
const legacyAuth = new AuthApiClient({ http: legacyHttp });

function acceptJson<T>(_value: unknown): _value is T {
  return true;
}

export interface PendingApproval {
  id: string;
  kind: string;
  created_at: string;
  payload: Record<string, unknown>;
}

interface PlatformApproval {
  id: string;
  action: string;
  reason: string;
  expires_at: string;
}

function isPlatformApprovals(value: unknown): value is PlatformApproval[] {
  return Array.isArray(value) && value.every((item) =>
    isRecord(item)
    && typeof item.id === "string"
    && typeof item.action === "string"
    && typeof item.reason === "string"
    && typeof item.expires_at === "string");
}

/** Demandes durables de la plateforme ; le provider-gateway reste interne. */
export async function fetchPendingApprovals(): Promise<PendingApproval[]> {
  const approvals = await legacyHttp.request(
    "/approvals?status=WAITING_APPROVAL",
    isPlatformApprovals,
  );
  return approvals.map((approval) => ({
    id: approval.id,
    kind: approval.action,
    created_at: approval.expires_at,
    payload: { goal: approval.reason },
  }));
}

export interface CompanyLevel {
  level: number;
  name: string;
  metrics: { projects: number; agents: number; completed_tasks: number };
  unlocked: string[];
  next: {
    level: number; name: string;
    min_projects: number; min_agents: number; min_completed_tasks: number;
  } | null;
}

export async function fetchCompanyLevel(): Promise<CompanyLevel | null> {
  try {
    return await legacyHttp.request("/company/level", acceptJson<CompanyLevel>);
  } catch {
    return null;
  }
}

export async function fetchRecentEvents(limit = 200): Promise<AcpEvent[]> {
  return legacyHttp.request(`/events?limit=${Math.max(1, Math.min(limit, 200))}`, acceptJson<AcpEvent[]>);
}

export async function fetchOverview(): Promise<Overview> {
  return legacyHttp.request("/overview", acceptJson<Overview>);
}

export async function fetchOfficeConfig(
  departmentId: string,
  capacity = 0,
): Promise<OfficeConfig> {
  return legacyHttp.request(
    `/departments/${encodeURIComponent(departmentId)}/office-config?capacity=${capacity}`,
    acceptJson<OfficeConfig>,
  );
}

export async function createAndQueueTask(projectId: string, title: string): Promise<void> {
  try {
    await legacyAuth.fetchSession();
  } catch {
    throw new Error(
      "Le bureau pixel ne peut pas créer de tâche sans session sécurisée. Connecte-toi d’abord dans l’espace principal.",
    );
  }
  const task = await legacyHttp.request<{ id: string }>("/tasks", (value): value is { id: string } =>
    isRecord(value) && typeof value.id === "string", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, title }),
  });
  await legacyHttp.request(
    `/tasks/${encodeURIComponent(task.id)}/queue`,
    acceptJson<Record<string, unknown>>,
    { method: "POST" },
  );
}

export function connectEvents(
  onEvent: (event: AcpEvent) => void,
  onStatus?: (connected: boolean) => void,
): () => void {
  let socket: WebSocket | null = null;
  let reconnectTimer: number | null = null;
  let stopped = false;
  const open = () => {
    if (stopped) return;
    socket = new WebSocket(EVENTS_WS_URL);
    socket.onopen = () => onStatus?.(true);
    socket.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data));
      } catch {
        /* message non JSON ignoré */
      }
    };
    socket.onclose = () => {
      onStatus?.(false);
      if (!stopped) reconnectTimer = window.setTimeout(open, 2000);
    };
    socket.onerror = () => socket?.close();
  };
  open();
  return () => {
    stopped = true;
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
    socket?.close();
    socket = null;
  };
}
