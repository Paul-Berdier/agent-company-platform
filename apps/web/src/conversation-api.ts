import type {
  HermesNativeListing,
  HermesNativeListingStatus,
  HermesNativeSkill,
  HermesNativeToolset,
} from "@acp/contracts";

import {
  WorkspaceHttpClient,
  hasString,
  isRecord,
  type Fetcher,
} from "./workspace-api";

export type {
  HermesNativeListing,
  HermesNativeListingStatus,
  HermesNativeSkill,
  HermesNativeToolset,
};

const HERMES_NATIVE_STATUSES: readonly HermesNativeListingStatus[] = [
  "available",
  "unavailable",
  "not_configured",
  "unsupported",
];

export type HermesDiagnosticStatus = "connected" | "degraded" | "unavailable";

export interface HermesDiagnostic {
  status: HermesDiagnosticStatus;
  healthy: boolean;
  message: string;
  capabilities: string[];
  checked_at: string;
}

export interface ConversationSummary {
  id: string;
  project_id: string | null;
  title: string;
  status: "active" | "archived";
  updated_at: string;
}

export type ConversationTurnStatus =
  | "submitting"
  | "running"
  | "completed"
  | "failed"
  | "interrupted";

export interface ConversationTurn {
  id: string;
  client_request_id: string;
  status: ConversationTurnStatus;
  user_content: string;
  assistant_content: string | null;
  provider_run_id: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

interface ConversationList {
  items: ConversationSummary[];
}

interface TurnList {
  items: ConversationTurn[];
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isHermesDiagnostic(value: unknown): value is HermesDiagnostic {
  return isRecord(value)
    && ["connected", "degraded", "unavailable"].includes(String(value.status))
    && typeof value.healthy === "boolean"
    && hasString(value, "message")
    && hasString(value, "checked_at")
    && (value.capabilities === undefined || isStringArray(value.capabilities));
}

function normalizeDiagnostic(value: HermesDiagnostic): HermesDiagnostic {
  return { ...value, capabilities: value.capabilities ?? [] };
}

function isHermesNativeSkill(value: unknown): value is HermesNativeSkill {
  return isRecord(value)
    && hasString(value, "name")
    && hasString(value, "description")
    && hasString(value, "category");
}

function isHermesNativeToolset(value: unknown): value is HermesNativeToolset {
  return isRecord(value)
    && hasString(value, "name")
    && hasString(value, "label")
    && hasString(value, "description")
    && typeof value.enabled === "boolean"
    && typeof value.configured === "boolean"
    && isStringArray(value.tools);
}

function isOptionalArrayOf<T>(value: unknown, guard: (item: unknown) => item is T): boolean {
  return value === undefined || Array.isArray(value) && value.every(guard);
}

/**
 * Une liste native n’est acceptée que si sa forme est exactement celle du
 * contrat : aucune entrée partiellement lue n’est affichée comme un succès.
 */
function isHermesNativeListing(value: unknown): value is HermesNativeListing {
  return isRecord(value)
    && HERMES_NATIVE_STATUSES.includes(String(value.status) as HermesNativeListingStatus)
    && hasString(value, "message")
    && (value.read_at === null || value.read_at === undefined || typeof value.read_at === "string")
    && isOptionalArrayOf(value.skills, isHermesNativeSkill)
    && isOptionalArrayOf(value.toolsets, isHermesNativeToolset);
}

function normalizeNativeListing(value: HermesNativeListing): HermesNativeListing {
  return {
    ...value,
    skills: value.skills ?? [],
    toolsets: value.toolsets ?? [],
    read_at: value.read_at ?? null,
  };
}

function isConversationSummary(value: unknown): value is ConversationSummary {
  return isRecord(value)
    && hasString(value, "id")
    && (value.project_id === null || typeof value.project_id === "string")
    && hasString(value, "title")
    && (value.status === "active" || value.status === "archived")
    && hasString(value, "updated_at");
}

function isConversationList(value: unknown): value is ConversationList {
  return isRecord(value)
    && Array.isArray(value.items)
    && value.items.every(isConversationSummary);
}

function isNullableString(value: Record<string, unknown>, key: string): boolean {
  return value[key] === null || typeof value[key] === "string";
}

function isConversationTurn(value: unknown): value is ConversationTurn {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "client_request_id")
    && ["submitting", "running", "completed", "failed", "interrupted"].includes(String(value.status))
    && hasString(value, "user_content")
    && isNullableString(value, "assistant_content")
    && isNullableString(value, "provider_run_id")
    && isNullableString(value, "error")
    && hasString(value, "created_at")
    && hasString(value, "updated_at");
}

function isTurnList(value: unknown): value is TurnList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isConversationTurn);
}

export class ConversationApiClient {
  readonly http: WorkspaceHttpClient;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
    http?: WorkspaceHttpClient;
  } = {}) {
    this.http = options.http ?? new WorkspaceHttpClient(options);
  }

  async fetchHermesDiagnostic(): Promise<HermesDiagnostic> {
    return normalizeDiagnostic(await this.http.request(
      "/connections/hermes/diagnostic",
      isHermesDiagnostic,
    ));
  }

  async runHermesDiagnostic(): Promise<HermesDiagnostic> {
    return normalizeDiagnostic(await this.http.request(
      "/connections/hermes/diagnostic",
      isHermesDiagnostic,
      { method: "POST" },
    ));
  }

  /**
   * Lit les skills et toolsets qu’Hermes annonce lui-même. Lecture seule :
   * aucune écriture n’est possible depuis l’interface, Hermes reste la source
   * de vérité de sa configuration native.
   */
  async fetchHermesNativeListing(): Promise<HermesNativeListing> {
    return normalizeNativeListing(await this.http.request(
      "/connections/hermes/native-listing",
      isHermesNativeListing,
    ));
  }

  async listConversations(filters: { search?: string; status?: "active" | "archived" } = {}): Promise<ConversationSummary[]> {
    const query = new URLSearchParams();
    if (filters.search?.trim()) query.set("search", filters.search.trim());
    if (filters.status) query.set("status", filters.status);
    const suffix = query.size ? `?${query.toString()}` : "";
    return (await this.http.request(`/conversations${suffix}`, isConversationList)).items;
  }

  createConversation(input: { projectId: string | null; title?: string }): Promise<ConversationSummary> {
    return this.http.request("/conversations", isConversationSummary, {
      method: "POST",
      body: JSON.stringify({
        project_id: input.projectId,
        ...(input.title?.trim() ? { title: input.title.trim() } : {}),
      }),
    });
  }

  updateConversation(
    conversationId: string,
    input: { title?: string; status?: "active" | "archived" },
  ): Promise<ConversationSummary> {
    return this.http.request(
      `/conversations/${encodeURIComponent(conversationId)}`,
      isConversationSummary,
      {
        method: "PATCH",
        body: JSON.stringify(input),
      },
    );
  }

  exportConversation(conversationId: string): Promise<Record<string, unknown>> {
    return this.http.request(
      `/conversations/${encodeURIComponent(conversationId)}/export`,
      isRecord,
    );
  }

  async listTurns(conversationId: string): Promise<ConversationTurn[]> {
    return (await this.http.request(
      `/conversations/${encodeURIComponent(conversationId)}/turns`,
      isTurnList,
    )).items;
  }

  createTurn(input: {
    conversationId: string;
    clientRequestId: string;
    content: string;
    model?: string;
  }): Promise<ConversationTurn> {
    return this.http.request(
      `/conversations/${encodeURIComponent(input.conversationId)}/turns`,
      isConversationTurn,
      {
        method: "POST",
        body: JSON.stringify({
          client_request_id: input.clientRequestId,
          content: input.content,
          ...(input.model?.trim() ? { model: input.model.trim() } : {}),
        }),
      },
    );
  }

  fetchTurn(conversationId: string, turnId: string): Promise<ConversationTurn> {
    return this.http.request(
      `/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(turnId)}`,
      isConversationTurn,
    );
  }
}

export function isTerminalConversationTurn(status: ConversationTurnStatus): boolean {
  return status === "completed" || status === "failed" || status === "interrupted";
}
