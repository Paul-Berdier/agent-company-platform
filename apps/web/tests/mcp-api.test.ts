import { describe, expect, it, vi } from "vitest";

import { McpApiClient } from "../src/mcp-api";

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const httpConfig = {
  transport: "http",
  http: {
    url: "https://mcp.example/mcp",
    headers: { "X-Client": "acp" },
    header_secrets: { Authorization: { secret_id: "secret-1" } },
    timeout_seconds: 15,
  },
  stdio: null,
};

const stdioConfig = {
  transport: "stdio",
  http: null,
  stdio: {
    command: "C:\\tools\\node.exe",
    args: ["server.js", "--port", "0"],
    env: { LOG_LEVEL: "info" },
    env_secrets: { GITHUB_TOKEN: { secret_id: "secret-1" } },
    cwd: null,
    timeout_seconds: 20,
  },
};

const tool = {
  name: "search",
  description: "Recherche documentaire",
  input_schema: { type: "object", properties: { query: { type: "string" } } },
};

const discovery = {
  protocol_version: "2025-06-18",
  server_info: { name: "demo", version: "1.0.0" },
  tools: [tool],
  capabilities: { tools: {} },
  truncated: false,
};

const diff = {
  previous_number: null,
  changed_fields: ["config"],
  endpoint_changed: false,
  command_changed: false,
  secrets_added: ["Authorization"],
  secrets_removed: [],
  tools_added: [],
  tools_removed: [],
  requires_approval: false,
  reasons: [],
};

const revision = {
  id: "revision-1",
  server_id: "server-1",
  number: 1,
  config: httpConfig,
  fingerprint: "a".repeat(64),
  discovery,
  discovered_at: "2026-09-11T10:05:00Z",
  discovery_current: true,
  risk_flags: [{ code: "localhost_target", level: "info", message: "Résolu dans le contexte d’exécution." }],
  change_summary: diff,
  requires_approval: false,
  note: "première révision",
  created_at: "2026-09-11T10:00:00Z",
  superseded_at: null,
};

const binding = {
  id: "binding-1",
  server_id: "server-1",
  server_name: "demo",
  project_id: "project-1",
  revision_id: "revision-1",
  revision_number: 1,
  allowed_tools: ["search"],
  enabled: true,
  created_at: "2026-09-11T10:10:00Z",
  updated_at: "2026-09-11T10:10:00Z",
  revoked_at: null,
};

const probe = {
  id: "probe-1",
  server_id: "server-1",
  revision_id: "revision-1",
  transport: "http",
  status: "succeeded",
  authorization: null,
  requested_by_user_id: "owner-1",
  decided_by_user_id: null,
  decided_at: null,
  decision_comment: "",
  worker_id: null,
  claimed_at: null,
  lease_expires_at: null,
  result: {
    protocol_version: "2025-06-18",
    server_info: { name: "demo" },
    tools: [tool],
    exit_code: null,
    stderr_tail: "",
    duration_ms: 120,
    error: null,
  },
  error: null,
  created_at: "2026-09-11T10:04:00Z",
  finished_at: "2026-09-11T10:05:00Z",
  expires_at: "2026-09-11T11:04:00Z",
};

const stdioProbe = {
  ...probe,
  id: "probe-2",
  transport: "stdio",
  status: "pending_approval",
  authorization: {
    action: "mcp_stdio_launch",
    target: "C:\\tools\\node.exe server.js --port 0",
    consequences: ["Lance un processus local sur le runner désigné."],
    scope: { execution_location: "runner", worker_id: "worker-1" },
    fingerprint: "a".repeat(64),
    expires_at: "2026-09-11T11:04:00Z",
  },
  result: null,
  finished_at: null,
};

const summary = {
  id: "server-1",
  name: "demo",
  display_name: "Serveur de démonstration",
  description: "",
  source_kind: "manual",
  origin: "",
  transport: "http",
  execution_location: "platform",
  status: "draft",
  current_revision_number: 1,
  discovery_current: true,
  tool_count: 1,
  binding_count: 1,
  target_worker_id: null,
  last_probe_status: "succeeded",
  last_probe_at: "2026-09-11T10:05:00Z",
  created_at: "2026-09-11T10:00:00Z",
  updated_at: "2026-09-11T10:05:00Z",
  revoked_at: null,
};

const detail = {
  ...summary,
  current_revision: revision,
  revisions: [revision],
  bindings: [binding],
  probes: [probe, stdioProbe],
  apply_notes: ["Recharger Hermes après activation."],
};

const catalogEntry = {
  id: "filesystem",
  display_name: "Système de fichiers",
  description: "Accès en lecture à un dossier.",
  transport: "stdio",
  config: { ...stdioConfig, stdio: { ...stdioConfig.stdio, env_secrets: {} } },
  required_secrets: [],
  prerequisites: ["Node.js 20+"],
  risks: ["Accès disque local"],
  documentation_url: "https://example.test/docs",
  verified_at: "2026-09-11",
  verification: "documentation lue",
};

const exportResult = {
  format: "hermes",
  project_id: null,
  content: "mcp_servers:\n  demo:\n    url: https://mcp.example/mcp\n",
  placeholders: ["ACP_SECRET_GITHUB_TOKEN"],
  partial_compatibility: [],
  apply_notes: ["Renseigner ACP_SECRET_GITHUB_TOKEN dans l’environnement Hermes."],
};

function client(fetcher: ReturnType<typeof vi.fn>): McpApiClient {
  const instance = new McpApiClient({ baseUrl: "https://api.example.test", fetcher });
  instance.http.setCsrfToken("csrf-current");
  return instance;
}

function requestInit(fetcher: ReturnType<typeof vi.fn>, index = 0): RequestInit {
  return fetcher.mock.calls[index][1] as RequestInit;
}

function body(fetcher: ReturnType<typeof vi.fn>, index = 0): unknown {
  return JSON.parse(String(requestInit(fetcher, index).body));
}

describe("McpApiClient — catalogue et liste", () => {
  it("lit le catalogue vérifié par documentation", async () => {
    const fetcher = vi.fn(async () => json([catalogEntry]));
    await expect(client(fetcher).fetchCatalog()).resolves.toEqual([catalogEntry]);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/catalog");
    const init = requestInit(fetcher);
    expect(init.body).toBeUndefined();
    expect((init.headers as Headers).get("Cache-Control")).toBeNull();
  });

  it("refuse une entrée de catalogue sans configuration exploitable", async () => {
    const fetcher = vi.fn(async () => json([{ ...catalogEntry, config: { transport: "stdio", http: null, stdio: null } }]));
    await expect(client(fetcher).fetchCatalog()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("liste les serveurs avec un filtre de statut encodé", async () => {
    const fetcher = vi.fn(async () => json([summary]));
    await expect(client(fetcher).listServers("active")).resolves.toEqual([summary]);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/servers?status=active");
    await client(fetcher).listServers();
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/mcp/servers");
  });

  it("rejette un résumé au statut inconnu ou au transport incohérent", async () => {
    const unknownStatus = vi.fn(async () => json([{ ...summary, status: "pending" }]));
    await expect(client(unknownStatus).listServers()).rejects.toMatchObject({ kind: "invalid_response" });
    const badTransport = vi.fn(async () => json([{ ...summary, transport: "ws" }]));
    await expect(client(badTransport).listServers()).rejects.toMatchObject({ kind: "invalid_response" });
    const badCount = vi.fn(async () => json([{ ...summary, tool_count: "1" }]));
    await expect(client(badCount).listServers()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("McpApiClient — détail et création", () => {
  it("charge un détail complet (révisions, bindings, probes, autorisation stdio)", async () => {
    const fetcher = vi.fn(async () => json(detail));
    const loaded = await client(fetcher).fetchServer("server/1");
    expect(loaded).toEqual(detail);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/servers/server%2F1");
    expect(loaded.probes[1].authorization?.action).toBe("mcp_stdio_launch");
  });

  it("refuse un détail dont une référence de secret n’est pas une simple référence", async () => {
    const leaked = {
      ...detail,
      current_revision: {
        ...revision,
        config: {
          ...httpConfig,
          http: { ...httpConfig.http, header_secrets: { Authorization: "Bearer clair" } },
        },
      },
    };
    const fetcher = vi.fn(async () => json(leaked));
    await expect(client(fetcher).fetchServer("server-1")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("refuse un détail dont un outil découvert n’a pas de schéma objet", async () => {
    const broken = {
      ...detail,
      current_revision: {
        ...revision,
        discovery: { ...discovery, tools: [{ name: "x", description: "", input_schema: "string" }] },
      },
    };
    const fetcher = vi.fn(async () => json(broken));
    await expect(client(fetcher).fetchServer("server-1")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("refuse une probe au statut inconnu", async () => {
    const fetcher = vi.fn(async () => json({ ...detail, probes: [{ ...probe, status: "done" }] }));
    await expect(client(fetcher).fetchServer("server-1")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("crée un serveur en snake_case avec CSRF et sans valeur de secret", async () => {
    const fetcher = vi.fn(async () => json(detail, 201));
    await expect(client(fetcher).createServer({
      name: " demo ",
      displayName: " Serveur de démonstration ",
      description: "",
      sourceKind: "manual",
      origin: "",
      config: httpConfig as never,
      targetWorkerId: null,
      note: " première révision ",
    })).resolves.toEqual(detail);

    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/servers");
    const init = requestInit(fetcher);
    expect(init.method).toBe("POST");
    expect((init.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
    expect(body(fetcher)).toEqual({
      name: "demo",
      display_name: "Serveur de démonstration",
      description: "",
      source_kind: "manual",
      origin: "",
      config: httpConfig,
      target_worker_id: null,
      note: "première révision",
    });
  });

  it("crée une révision et un rollback sur des chemins encodés", async () => {
    const fetcher = vi.fn(async () => json(detail, 201));
    const api = client(fetcher);
    await api.createRevision("server 1", { config: stdioConfig as never, targetWorkerId: "worker-1", note: "" });
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/servers/server%201/revisions");
    expect(body(fetcher)).toEqual({ config: stdioConfig, target_worker_id: "worker-1", note: "" });

    await api.rollbackServer("server 1", 1, " retour ");
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/mcp/servers/server%201/rollback");
    expect(body(fetcher, 1)).toEqual({ revision_number: 1, note: "retour" });
  });
});

describe("McpApiClient — cycle de vie", () => {
  it("active, désactive et révoque avec une raison obligatoire", async () => {
    const fetcher = vi.fn(async () => json({ ...detail, status: "active" }));
    const api = client(fetcher);
    await expect(api.activateServer("server-1")).resolves.toMatchObject({ status: "active" });
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/servers/server-1/activate");
    expect(requestInit(fetcher).method).toBe("POST");
    expect(requestInit(fetcher).body).toBeUndefined();

    await api.disableServer("server-1");
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/mcp/servers/server-1/disable");

    await api.revokeServer("server-1", " compromis ");
    expect(fetcher.mock.calls[2][0]).toBe("https://api.example.test/mcp/servers/server-1/revoke");
    expect(body(fetcher, 2)).toEqual({ reason: "compromis" });

    await expect(api.revokeServer("server-1", "   ")).rejects.toMatchObject({ kind: "http", status: 422 });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("lance un probe et lit les probes d’un serveur", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json(stdioProbe))
      .mockResolvedValueOnce(json([probe, stdioProbe]));
    const api = client(fetcher);
    await expect(api.probeServer("server-1")).resolves.toMatchObject({ status: "pending_approval" });
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/servers/server-1/probe");
    expect(requestInit(fetcher).method).toBe("POST");
    await expect(api.listServerProbes("server-1")).resolves.toHaveLength(2);
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/mcp/servers/server-1/probes");
  });

  it("liste, lit et décide les probes globales", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json([stdioProbe]))
      .mockResolvedValueOnce(json(stdioProbe))
      .mockResolvedValueOnce(json({ ...stdioProbe, status: "queued" }))
      .mockResolvedValueOnce(json({ ...stdioProbe, status: "rejected", decision_comment: "non" }));
    const api = client(fetcher);
    await api.listProbes("pending_approval");
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/probes?status=pending_approval");
    await api.fetchProbe("probe/2");
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/mcp/probes/probe%2F2");
    await expect(api.decideProbe("probe-2", "approved")).resolves.toMatchObject({ status: "queued" });
    expect(fetcher.mock.calls[2][0]).toBe("https://api.example.test/mcp/probes/probe-2/decision");
    expect(body(fetcher, 2)).toEqual({ decision: "approved", comment: "" });
    await expect(api.decideProbe("probe-2", "rejected", " non ")).resolves.toMatchObject({ status: "rejected" });
    expect(body(fetcher, 3)).toEqual({ decision: "rejected", comment: "non" });
  });
});

describe("McpApiClient — bindings", () => {
  it("crée un binding par projet avec une liste d’outils non vide", async () => {
    const fetcher = vi.fn(async () => json(binding, 201));
    const api = client(fetcher);
    await expect(api.createBinding("server-1", { projectId: "project-1", allowedTools: ["search"] }))
      .resolves.toEqual(binding);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/servers/server-1/bindings");
    expect(body(fetcher)).toEqual({ project_id: "project-1", allowed_tools: ["search"] });
    await expect(api.createBinding("server-1", { projectId: "project-1", allowedTools: [] }))
      .rejects.toMatchObject({ kind: "http", status: 422 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("filtre les bindings par projet ou serveur", async () => {
    const fetcher = vi.fn(async () => json([binding]));
    const api = client(fetcher);
    await api.listBindings({ projectId: "project 1" });
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/bindings?project_id=project+1");
    await api.listBindings({ serverId: "server-1" });
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/mcp/bindings?server_id=server-1");
    await api.listBindings();
    expect(fetcher.mock.calls[2][0]).toBe("https://api.example.test/mcp/bindings");
  });

  it("modifie et révoque un binding", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ ...binding, enabled: false }))
      .mockResolvedValueOnce(json({ ...binding, allowed_tools: ["search", "read"] }))
      .mockResolvedValueOnce(json({ ...binding, revoked_at: "2026-09-12T09:00:00Z" }));
    const api = client(fetcher);
    await expect(api.updateBinding("binding-1", { enabled: false })).resolves.toMatchObject({ enabled: false });
    expect(requestInit(fetcher).method).toBe("PATCH");
    expect(body(fetcher)).toEqual({ enabled: false });
    await api.updateBinding("binding-1", { allowedTools: ["search", "read"] });
    expect(body(fetcher, 1)).toEqual({ allowed_tools: ["search", "read"] });
    await expect(api.revokeBinding("binding/1")).resolves.toMatchObject({ revoked_at: "2026-09-12T09:00:00Z" });
    expect(fetcher.mock.calls[2][0]).toBe("https://api.example.test/mcp/bindings/binding%2F1");
    expect(requestInit(fetcher, 2).method).toBe("DELETE");
    expect(requestInit(fetcher, 2).body).toBeUndefined();
  });

  it("rejette un binding dont allowed_tools n’est pas une liste de chaînes", async () => {
    const fetcher = vi.fn(async () => json([{ ...binding, allowed_tools: [1] }]));
    await expect(client(fetcher).listBindings()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("McpApiClient — export", () => {
  it("demande un export au format choisi, avec projet optionnel encodé", async () => {
    const fetcher = vi.fn(async () => json(exportResult));
    const api = client(fetcher);
    await expect(api.exportServers("hermes")).resolves.toEqual(exportResult);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/export?format=hermes");
    await api.exportServers("claude", "project/1");
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/mcp/export?format=claude&project_id=project%2F1");
    expect(requestInit(fetcher, 1).body).toBeUndefined();
  });

  it("refuse un export dont les placeholders ne sont pas des chaînes", async () => {
    const fetcher = vi.fn(async () => json({ ...exportResult, placeholders: [{ name: "x" }] }));
    await expect(client(fetcher).exportServers("codex")).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("McpApiClient — runners (lecture auxiliaire)", () => {
  it("liste les runners avec leurs capacités pour le sélecteur stdio", async () => {
    const runner = {
      id: "worker-1",
      name: "Poste Windows",
      capabilities: ["git", "mcp_stdio_probe"],
      max_concurrency: 1,
      active_runs: 0,
      status: "online",
      simulation: false,
      metadata: {},
      last_seen_at: null,
      lease_expires_at: null,
      token_expires_at: "2026-10-01T00:00:00Z",
      created_at: null,
    };
    const fetcher = vi.fn(async () => json([runner]));
    await expect(client(fetcher).fetchRunners()).resolves.toEqual([
      { id: "worker-1", name: "Poste Windows", status: "online", capabilities: ["git", "mcp_stdio_probe"], simulation: false },
    ]);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/workers");
  });

  it("distingue accès refusé (403) et hors ligne", async () => {
    const forbidden = new McpApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => json({ detail: "owner required" }, 403),
    });
    await expect(forbidden.createServer({
      name: "demo",
      displayName: "Demo",
      description: "",
      sourceKind: "manual",
      origin: "",
      config: httpConfig as never,
      targetWorkerId: null,
      note: "",
    })).rejects.toMatchObject({ kind: "forbidden", status: 403 });

    const offline = new McpApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => { throw new TypeError("network unavailable"); },
    });
    await expect(offline.listServers()).rejects.toMatchObject({ kind: "offline" });
  });
});

describe("McpApiClient — refus locaux du formulaire", () => {
  it("n’envoie que le bloc du transport choisi, même si le brouillon garde l’autre", async () => {
    const fetcher = vi.fn(async () => json(detail, 201));
    const draft = { transport: "http", http: httpConfig.http, stdio: stdioConfig.stdio };
    await client(fetcher).createServer({
      name: "demo",
      displayName: "Demo",
      description: "",
      sourceKind: "catalog",
      origin: "catalogue:demo",
      config: draft as never,
      targetWorkerId: "  ",
      note: "",
    });
    const sent = body(fetcher) as { config: { stdio: unknown; http: unknown }; target_worker_id: unknown };
    expect(sent.config.stdio).toBeNull();
    expect(sent.config.http).toEqual(httpConfig.http);
    expect(sent.target_worker_id).toBeNull();
  });

  it("refuse localement un patch de binding vide et une raison de révocation hors bornes", async () => {
    const fetcher = vi.fn(async () => json(detail));
    const api = client(fetcher);
    await expect(api.updateBinding("binding-1", {})).rejects.toMatchObject({ kind: "http", status: 422 });
    await expect(api.revokeServer("server-1", "   ")).rejects.toMatchObject({ kind: "http", status: 422 });
    await expect(api.revokeServer("server-1", "x".repeat(2001))).rejects.toMatchObject({ kind: "http", status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });
});

const importCandidate = {
  location: "header",
  key: "CONTEXT7_API_KEY",
  suggested_secret_name: "CONTEXT7_CONTEXT7_API_KEY",
  masked_value: "***34",
};

const importEntry = {
  name: "context7",
  source_name: "context7",
  transport: "http",
  config: httpConfig,
  secret_candidates: [importCandidate],
  unsupported: [],
  warnings: ["Transport http : diagnostic requis avant activation."],
  conflict: "none",
  importable: true,
};

const importPreview = {
  detected_format: "claude",
  entries: [
    importEntry,
    {
      ...importEntry,
      name: "broken",
      source_name: "broken",
      transport: null,
      config: null,
      secret_candidates: [],
      unsupported: ["entrée sans « url » ni « command » : rien à importer."],
      warnings: [],
      conflict: "existing_server",
      importable: false,
    },
  ],
  errors: [],
};

const importResult = {
  created: [summary],
  revised: [],
  skipped: ["broken"],
  errors: ["Entrée « broken » non importable : rien à importer."],
};

describe("McpApiClient — import", () => {
  it("demande un aperçu en envoyant le contenu, jamais un chemin de fichier", async () => {
    const fetcher = vi.fn(async () => json(importPreview));
    await expect(client(fetcher).previewImport("auto", "{\"mcpServers\": {}}"))
      .resolves.toEqual(importPreview);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/import/preview");
    expect(requestInit(fetcher).method).toBe("POST");
    expect(body(fetcher)).toEqual({ format: "auto", content: "{\"mcpServers\": {}}" });
    expect((requestInit(fetcher).headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
  });

  it("refuse localement un contenu vide ou hors bornes, sans appel réseau", async () => {
    const fetcher = vi.fn(async () => json(importPreview));
    const api = client(fetcher);
    await expect(api.previewImport("auto", "   ")).rejects.toMatchObject({ kind: "http", status: 422 });
    await expect(api.previewImport("auto", "x".repeat(1_000_001))).rejects.toMatchObject({ kind: "http", status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("refuse un aperçu dont un candidat transporte une valeur en clair", async () => {
    const leaked = vi.fn(async () => json({
      ...importPreview,
      entries: [{ ...importEntry, secret_candidates: [{ ...importCandidate, masked_value: "ctx-live-abcd1234" }] }],
    }));
    await expect(client(leaked).previewImport("auto", "{}")).rejects.toMatchObject({ kind: "invalid_response" });

    const extraField = vi.fn(async () => json({
      ...importPreview,
      entries: [{ ...importEntry, secret_candidates: [{ ...importCandidate, value: "ctx-live-abcd1234" }] }],
    }));
    await expect(client(extraField).previewImport("auto", "{}")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("refuse un aperçu dont une entrée porte une configuration inexploitable", async () => {
    const fetcher = vi.fn(async () => json({
      ...importPreview,
      entries: [{ ...importEntry, config: { transport: "http", http: null, stdio: null } }],
    }));
    await expect(client(fetcher).previewImport("claude", "{}")).rejects.toMatchObject({ kind: "invalid_response" });

    const unknownFormat = vi.fn(async () => json({ ...importPreview, detected_format: "cursor" }));
    await expect(client(unknownFormat).previewImport("auto", "{}")).rejects.toMatchObject({ kind: "invalid_response" });

    const unknownConflict = vi.fn(async () => json({
      ...importPreview,
      entries: [{ ...importEntry, conflict: "maybe" }],
    }));
    await expect(client(unknownConflict).previewImport("auto", "{}")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("applique les entrées choisies en snake_case, avec le mapping de secrets", async () => {
    const fetcher = vi.fn(async () => json(importResult));
    await expect(client(fetcher).applyImport({
      format: "claude",
      content: "{\"mcpServers\": {}}",
      names: [" context7 ", "context7", "broken"],
      secretMapping: { CONTEXT7_CONTEXT7_API_KEY: "secret-1" },
      onConflict: "new_revision",
    })).resolves.toEqual(importResult);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/mcp/import/apply");
    expect(body(fetcher)).toEqual({
      format: "claude",
      content: "{\"mcpServers\": {}}",
      names: ["context7", "broken"],
      secret_mapping: { CONTEXT7_CONTEXT7_API_KEY: "secret-1" },
      on_conflict: "new_revision",
    });
  });

  it("refuse localement une application sans entrée choisie", async () => {
    const fetcher = vi.fn(async () => json(importResult));
    await expect(client(fetcher).applyImport({
      format: "auto",
      content: "{}",
      names: ["  "],
      secretMapping: {},
      onConflict: "skip",
    })).rejects.toMatchObject({ kind: "http", status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("refuse un résultat d’application de forme inattendue", async () => {
    const fetcher = vi.fn(async () => json({ ...importResult, skipped: [{ name: "broken" }] }));
    await expect(client(fetcher).applyImport({
      format: "auto",
      content: "{}",
      names: ["context7"],
      secretMapping: {},
      onConflict: "skip",
    })).rejects.toMatchObject({ kind: "invalid_response" });
  });
});
