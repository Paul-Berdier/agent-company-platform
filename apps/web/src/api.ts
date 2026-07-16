import type { AcpEvent, OfficeConfig, Overview } from "@acp/contracts";

export const API_URL = import.meta.env.VITE_ACP_API_URL ?? "http://localhost:8000";
export const EVENTS_WS_URL =
  import.meta.env.VITE_ACP_EVENTS_WS_URL ?? "ws://localhost:8001/ws";
export const GATEWAY_URL =
  import.meta.env.VITE_ACP_GATEWAY_URL ?? "http://localhost:8002";

export interface PendingApproval {
  id: string;
  kind: string;
  created_at: string;
  payload: Record<string, unknown>;
}

/** Demandes en attente de l'orchestrateur manuel (vide si gateway absent). */
export async function fetchPendingApprovals(): Promise<PendingApproval[]> {
  try {
    const resp = await fetch(`${GATEWAY_URL}/v1/manual/pending`);
    return resp.ok ? resp.json() : [];
  } catch {
    return [];
  }
}

export async function fetchRecentEvents(limit = 200): Promise<AcpEvent[]> {
  try {
    const resp = await fetch(`${API_URL}/events?limit=${limit}`);
    return resp.ok ? resp.json() : [];
  } catch {
    return [];
  }
}

export async function fetchOverview(): Promise<Overview> {
  const resp = await fetch(`${API_URL}/overview`);
  if (!resp.ok) throw new Error(`overview: ${resp.status}`);
  return resp.json();
}

export async function fetchOfficeConfig(departmentId: string): Promise<OfficeConfig> {
  const resp = await fetch(`${API_URL}/departments/${departmentId}/office-config`);
  if (!resp.ok) throw new Error(`office-config: ${resp.status}`);
  return resp.json();
}

export async function createAndQueueTask(projectId: string, title: string): Promise<void> {
  const resp = await fetch(`${API_URL}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, title }),
  });
  if (!resp.ok) throw new Error(`create task: ${resp.status}`);
  const task = await resp.json();
  await fetch(`${API_URL}/tasks/${task.id}/queue`, { method: "POST" });
}

export function connectEvents(onEvent: (event: AcpEvent) => void): void {
  let socket: WebSocket | null = null;
  const open = () => {
    socket = new WebSocket(EVENTS_WS_URL);
    socket.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data));
      } catch {
        /* message non JSON ignoré */
      }
    };
    socket.onclose = () => setTimeout(open, 2000);
    socket.onerror = () => socket?.close();
  };
  open();
}
