import { describe, expect, it, vi } from "vitest";

import {
  ConversationApiClient,
  isTerminalConversationTurn,
} from "../src/conversation-api";

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const conversation = {
  id: "conversation/1",
  project_id: null,
  title: "Conversation générale",
  status: "active",
  updated_at: "2026-09-11T08:00:00Z",
};

const turn = {
  id: "turn/1",
  client_request_id: "5ce74d58-a098-4e73-aee8-7c64c92a62e0",
  status: "running",
  user_content: "Vérifie le dépôt",
  assistant_content: null,
  provider_run_id: "hermes-42",
  error: null,
  created_at: "2026-09-11T08:00:00Z",
  updated_at: "2026-09-11T08:00:01Z",
};

describe("ConversationApiClient", () => {
  it.each(["waiting_for_approval", "stopping"] as const)("accepte %s sans arrêter le suivi", async (status) => {
    const response = { ...turn, status };
    const client = new ConversationApiClient({ fetcher: async () => json({ items: [response] }) });
    await expect(client.listTurns(conversation.id)).resolves.toEqual([response]);
    expect(isTerminalConversationTurn(status)).toBe(false);
  });

  it("demande l’arrêt authentifié sans inventer un état terminal", async () => {
    const fetcher = vi.fn(async () => json({ ...turn, status: "stopping" }, 202));
    const client = new ConversationApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-current");
    await expect(client.stopTurn(conversation.id, turn.id)).resolves.toMatchObject({ status: "stopping" });
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/conversations/conversation%2F1/turns/turn%2F1/stop");
    const init = fetcher.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect((init.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
    expect(init.body).toBeUndefined();
  });

  it("refuse toujours un état de tour inconnu", async () => {
    const client = new ConversationApiClient({ fetcher: async () => json({ ...turn, status: "invented" }) });
    await expect(client.fetchTurn(conversation.id, turn.id)).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("lit un diagnostic honnête et normalise les capacités absentes", async () => {
    const fetcher = vi.fn(async () => json({
      status: "unavailable",
      healthy: false,
      message: "HERMES_API_KEY absente",
      checked_at: "2026-09-11T08:00:00Z",
    }));
    const client = new ConversationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.fetchHermesDiagnostic()).resolves.toMatchObject({
      status: "unavailable",
      healthy: false,
      capabilities: [],
    });
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/connections/hermes/diagnostic");
  });

  it("crée une conversation générale avec cookie et CSRF", async () => {
    const fetcher = vi.fn(async () => json(conversation, 201));
    const client = new ConversationApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-current");

    await expect(client.createConversation({ projectId: null })).resolves.toEqual(conversation);
    const init = fetcher.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe("include");
    expect((init.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
    expect(JSON.parse(String(init.body))).toEqual({ project_id: null });
  });

  it("encode les identifiants et envoie l’idempotence applicative du tour", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ items: [turn] }))
      .mockResolvedValueOnce(json(turn, 202))
      .mockResolvedValueOnce(json({ ...turn, status: "completed", assistant_content: "Terminé" }));
    const client = new ConversationApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-current");

    await expect(client.listTurns(conversation.id)).resolves.toEqual([turn]);
    expect(fetcher.mock.calls[0][0]).toBe(
      "https://api.example.test/conversations/conversation%2F1/turns",
    );

    await client.createTurn({
      conversationId: conversation.id,
      clientRequestId: turn.client_request_id,
      content: turn.user_content,
    });
    const createBody = JSON.parse(String(fetcher.mock.calls[1][1]?.body));
    expect(createBody).toEqual({
      client_request_id: turn.client_request_id,
      content: turn.user_content,
    });
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");

    await expect(client.fetchTurn(conversation.id, turn.id)).resolves.toMatchObject({
      status: "completed",
      assistant_content: "Terminé",
    });
    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/conversations/conversation%2F1/turns/turn%2F1",
    );
  });

  it("filtre, renomme, archive et exporte sans contourner le CSRF", async () => {
    const archived = { ...conversation, status: "archived", title: "Audit renommé" };
    const exported = { conversation: archived, turns: [] };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ items: [conversation] }))
      .mockResolvedValueOnce(json(archived))
      .mockResolvedValueOnce(json(exported));
    const client = new ConversationApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-current");

    await client.listConversations({ search: " audit urgent ", status: "active" });
    expect(fetcher.mock.calls[0][0]).toBe(
      "https://api.example.test/conversations?search=audit+urgent&status=active",
    );
    await client.updateConversation(conversation.id, { title: "Audit renommé", status: "archived" });
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({
      title: "Audit renommé",
      status: "archived",
    });
    await expect(client.exportConversation(conversation.id)).resolves.toEqual(exported);
    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/conversations/conversation%2F1/export",
    );
  });

  it("lit les skills et toolsets natifs annoncés par Hermes, sans les écrire", async () => {
    const listing = {
      status: "available",
      skills: [{ name: "pdf-report", description: "Rapport PDF", category: "documents" }],
      toolsets: [{
        name: "filesystem",
        label: "Système de fichiers",
        description: "Lecture locale",
        enabled: true,
        configured: true,
        tools: ["read_file"],
      }],
      message: "Lecture Hermes : 1 skill(s) et 1 toolset(s) annoncés.",
      read_at: "2026-09-12T08:30:00Z",
    };
    const fetcher = vi.fn(async () => json(listing));
    const client = new ConversationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.fetchHermesNativeListing()).resolves.toEqual(listing);
    expect(fetcher.mock.calls[0][0]).toBe(
      "https://api.example.test/connections/hermes/native-listing",
    );
    const init = fetcher.mock.calls[0][1] as RequestInit;
    expect((init.method ?? "GET").toUpperCase()).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("normalise un état sans contenu et refuse une forme invalide", async () => {
    const unavailable = {
      status: "unsupported",
      message: "Cette instance Hermes n’expose pas ses skills natifs.",
      read_at: null,
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json(unavailable))
      .mockResolvedValueOnce(json({ status: "available", skills: [{ name: 42 }], toolsets: [], message: "x", read_at: "2026-09-12T08:30:00Z" }))
      .mockResolvedValueOnce(json({ status: "inconnu", skills: [], toolsets: [], message: "x", read_at: null }));
    const client = new ConversationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.fetchHermesNativeListing()).resolves.toEqual({
      ...unavailable,
      skills: [],
      toolsets: [],
    });
    await expect(client.fetchHermesNativeListing()).rejects.toThrow();
    await expect(client.fetchHermesNativeListing()).rejects.toThrow();
  });

  it("distingue les tours terminaux des états encore suivis", () => {
    expect(isTerminalConversationTurn("submitting")).toBe(false);
    expect(isTerminalConversationTurn("running")).toBe(false);
    expect(isTerminalConversationTurn("completed")).toBe(true);
    expect(isTerminalConversationTurn("failed")).toBe(true);
    expect(isTerminalConversationTurn("interrupted")).toBe(true);
  });
});
