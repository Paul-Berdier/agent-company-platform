/**
 * Section « Import » de `mcp-ui.ts` (spec Lot D §7), sur un DOM minimal simulé.
 *
 * Aucune dépendance ajoutée (ni jsdom ni happy-dom) : le stub ci-dessous n’implémente
 * que les API réellement utilisées par le module, comme `tests/mcp-ui.test.ts`.
 *
 * Ces tests couvrent ce qu’une relecture ne montre pas : le contenu collé part bien en
 * `POST /mcp/import/preview` (et jamais un chemin de fichier), les candidats de secrets
 * s’affichent masqués et reliés à un secret **existant** du coffre, rien ne part sans
 * case cochée, et le bouton d’application suit réellement l’état des cases — c’est ce
 * dernier point qui a révélé un bouton resté désactivé après un clic (le repeint
 * n’ayant pas lieu, la case cochée n’avait aucun effet visible).
 */

import { describe, expect, it, vi } from "vitest";

type Handler = (event: unknown) => void;

class FakeElement {
  readonly tagName: string;
  className = "";
  textContent = "";
  id = "";
  name = "";
  htmlFor = "";
  type = "";
  placeholder = "";
  title = "";
  maxLength = 0;
  rows = 0;
  tabIndex = 0;
  required = false;
  disabled = false;
  hidden = false;
  checked = false;
  selected = false;
  noValidate = false;
  parent: FakeElement | null = null;
  readonly children: FakeElement[] = [];
  readonly attributes: Record<string, string> = {};
  readonly dataset: Record<string, string> = {};
  readonly listeners: Record<string, Handler[]> = {};
  private explicitValue: string | null = null;

  constructor(tagName: string) {
    this.tagName = tagName;
  }

  get value(): string {
    if (this.explicitValue !== null) return this.explicitValue;
    if (this.tagName === "select") {
      const chosen = this.children.find((child) => child.selected) ?? this.children[0];
      return chosen ? chosen.value : "";
    }
    return "";
  }

  set value(next: string) {
    this.explicitValue = next;
  }

  append(...nodes: FakeElement[]): void {
    for (const node of nodes) node.parent = this;
    this.children.push(...nodes);
  }

  replaceChildren(...nodes: FakeElement[]): void {
    this.children.length = 0;
    this.append(...nodes);
  }

  remove(): void {
    const siblings = this.parent?.children;
    if (!siblings) return;
    const index = siblings.indexOf(this);
    if (index >= 0) siblings.splice(index, 1);
    this.parent = null;
  }

  setAttribute(name: string, value: string): void {
    this.attributes[name] = value;
  }

  getAttribute(name: string): string | null {
    return this.attributes[name] ?? null;
  }

  removeAttribute(name: string): void {
    delete this.attributes[name];
  }

  addEventListener(type: string, handler: Handler): void {
    (this.listeners[type] ??= []).push(handler);
  }

  focus(): void {}

  reportValidity(): boolean {
    return true;
  }

  querySelector(selector: string): FakeElement | null {
    if (selector.startsWith("#")) {
      const id = selector.slice(1);
      return walk(this).find((node) => node.id === id) ?? null;
    }
    const match = /^\[data-([a-z-]+)='([^']+)'\]$/.exec(selector);
    if (!match) throw new Error(`Sélecteur non simulé : ${selector}`);
    const [, key, value] = match;
    return walk(this).find((node) => node.dataset[key] === value) ?? null;
  }
}

function walk(node: FakeElement): FakeElement[] {
  return node.children.flatMap((child) => [child, ...walk(child)]);
}

function textOf(node: FakeElement): string {
  return [node.textContent, ...node.children.map(textOf)].filter(Boolean).join(" ");
}

function fire(node: FakeElement, type: string, event: unknown = { preventDefault() {} }): void {
  for (const handler of node.listeners[type] ?? []) handler(event);
}

(globalThis as unknown as { document: unknown }).document = {
  createElement: (tag: string) => new FakeElement(tag),
};

async function flush(rounds = 12): Promise<void> {
  for (let index = 0; index < rounds; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

const httpConfig = {
  transport: "http",
  http: {
    url: "https://mcp.context7.com/mcp",
    headers: { "X-Client": "acp" },
    header_secrets: {},
    timeout_seconds: 15,
  },
  stdio: null,
};

const preview = {
  detected_format: "claude",
  entries: [
    {
      name: "context7",
      source_name: "context7",
      transport: "http",
      config: httpConfig,
      secret_candidates: [{
        location: "header",
        key: "CONTEXT7_API_KEY",
        suggested_secret_name: "CONTEXT7_CONTEXT7_API_KEY",
        masked_value: "***34",
      }],
      unsupported: [],
      warnings: ["Transport http : diagnostic requis."],
      conflict: "none",
      importable: true,
    },
    {
      name: "legacy-sse",
      source_name: "legacy-sse",
      transport: null,
      config: null,
      secret_candidates: [],
      unsupported: ["sse : transport « sse » non supporté."],
      warnings: [],
      conflict: "existing_server",
      importable: false,
    },
  ],
  errors: [],
};

const summary = {
  id: "srv-1",
  name: "context7",
  display_name: "context7",
  description: "",
  source_kind: "import",
  origin: "claude",
  transport: "http",
  execution_location: "platform",
  status: "draft",
  current_revision_number: 1,
  discovery_current: false,
  tool_count: 0,
  binding_count: 0,
  target_worker_id: null,
  last_probe_status: null,
  last_probe_at: null,
  created_at: "2026-09-12T10:00:00Z",
  updated_at: "2026-09-12T10:00:00Z",
  revoked_at: null,
};

const secret = {
  id: "secret-1",
  name: "CONTEXT7_API_KEY",
  scope_type: "platform",
  project_id: null,
  description: "",
  key_id: "abcdef012345",
  created_at: "2026-09-12T09:00:00Z",
  rotated_at: null,
  revoked_at: null,
  last_used_at: null,
  referenced_by_mcp_servers: [],
};

describe("section import de mcp-ui", () => {
  it("analyse, affiche les candidats masqués et applique les entrées cochées", async () => {
    const calls: Array<{ url: string; init: RequestInit }> = [];
    const fetcher = vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      if (url.endsWith("/mcp/servers")) return json([]);
      if (url.endsWith("/secrets/status")) {
        return json({ configured: true, primary_key_id: "abcdef012345", key_count: 1, message: "" });
      }
      if (url.endsWith("/secrets")) return json([secret]);
      if (url.endsWith("/mcp/import/preview")) return json(preview);
      if (url.endsWith("/mcp/import/apply")) {
        return json({ created: [summary], revised: [], skipped: ["legacy-sse"], errors: [] });
      }
      return json([]);
    });

    const mcpUi = await import("../src/mcp-ui");
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    const http = new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher: fetcher as never });
    http.setCsrfToken("csrf-1");

    const secretsRoot = new FakeElement("div");
    mcpUi.renderSecretsPanel(secretsRoot as never, http, "owner");
    const root = new FakeElement("div");
    mcpUi.renderMcpCenter(root as never, http, "owner");
    await flush();

    const importTab = root.querySelector("#mcp-tab-import");
    expect(importTab).not.toBeNull();
    fire(importTab as FakeElement, "click");
    await flush();

    const area = walk(root).find((node) => node.name === "import-content");
    expect(area).toBeDefined();
    (area as FakeElement).value = '{"mcpServers": {}}';
    const form = walk(root).find((node) => node.tagName === "form" && walk(node).some((c) => c.name === "import-content"));
    fire(form as FakeElement, "submit");
    await flush();

    const previewCall = calls.find((call) => call.url.endsWith("/mcp/import/preview"));
    expect(previewCall).toBeDefined();
    expect(JSON.parse(String(previewCall!.init.body))).toEqual({
      format: "auto",
      content: '{"mcpServers": {}}',
    });

    const rendered = textOf(root);
    expect(rendered).toContain("context7");
    expect(rendered).toContain("***34");
    expect(rendered).toContain("sse : transport");
    expect(rendered).toContain("Nom déjà pris");

    // Case à cocher de l'entrée importable, puis choix du secret existant.
    const checkboxes = walk(root).filter((node) => node.type === "checkbox");
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes[1].disabled).toBe(true);
    checkboxes[0].checked = true;
    fire(checkboxes[0], "change");

    const secretSelect = walk(root).find((node) => node.name === "import-secret-CONTEXT7_CONTEXT7_API_KEY");
    expect(secretSelect).toBeDefined();
    (secretSelect as FakeElement).value = "secret-1";
    fire(secretSelect as FakeElement, "change");

    const conflictSelect = walk(root).find((node) => node.name === "import-on-conflict");
    (conflictSelect as FakeElement).value = "new_revision";
    fire(conflictSelect as FakeElement, "change");

    const applyButton = walk(root).find((node) => node.tagName === "button"
      && node.textContent.startsWith("Appliquer"));
    expect(applyButton).toBeDefined();
    expect(applyButton!.disabled).toBe(false);
    fire(applyButton as FakeElement, "click");
    await flush();

    const applyCall = calls.find((call) => call.url.endsWith("/mcp/import/apply"));
    expect(applyCall).toBeDefined();
    expect(JSON.parse(String(applyCall!.init.body))).toEqual({
      format: "auto",
      content: '{"mcpServers": {}}',
      names: ["context7"],
      secret_mapping: { CONTEXT7_CONTEXT7_API_KEY: "secret-1" },
      on_conflict: "new_revision",
    });
    expect(textOf(root)).toContain("Créé : context7");
    // Les entrées appliquées sont décochées : un second clic ne rejouerait pas l’import.
    expect(walk(root).filter((node) => node.type === "checkbox").every((node) => !node.checked)).toBe(true);
  });

  it("n’active jamais le bouton d’application sans entrée cochée", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.endsWith("/mcp/import/preview")) return json(preview);
      if (url.endsWith("/secrets/status")) {
        return json({ configured: true, primary_key_id: "abcdef012345", key_count: 1, message: "" });
      }
      if (url.endsWith("/secrets")) return json([secret]);
      return json([]);
    });
    const mcpUi = await import("../src/mcp-ui");
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    mcpUi.resetMcpUiState();
    const http = new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher: fetcher as never });
    http.setCsrfToken("csrf-1");
    const root = new FakeElement("div");
    mcpUi.renderMcpCenter(root as never, http, "owner");
    await flush();
    fire(root.querySelector("#mcp-tab-import") as FakeElement, "click");
    await flush();
    const area = walk(root).find((node) => node.name === "import-content") as FakeElement;
    area.value = "{}";
    const form = walk(root).find((node) => node.tagName === "form"
      && walk(node).some((c) => c.name === "import-content")) as FakeElement;
    fire(form, "submit");
    await flush();
    const applyButton = walk(root).find((node) => node.tagName === "button"
      && node.textContent.startsWith("Appliquer")) as FakeElement;
    expect(applyButton.disabled).toBe(true);
    expect(applyButton.title).toContain("Coche au moins une entrée");
  });

  it("refuse localement un contenu vide sans appeler l’API", async () => {
    const fetcher = vi.fn(async () => json([]));
    const mcpUi = await import("../src/mcp-ui");
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    mcpUi.resetMcpUiState();
    const http = new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher: fetcher as never });
    http.setCsrfToken("csrf-1");
    const root = new FakeElement("div");
    mcpUi.renderMcpCenter(root as never, http, "owner");
    await flush();
    fire(root.querySelector("#mcp-tab-import") as FakeElement, "click");
    await flush();
    const form = walk(root).find((node) => node.tagName === "form"
      && walk(node).some((c) => c.name === "import-content")) as FakeElement;
    fire(form, "submit");
    await flush();
    expect(fetcher.mock.calls.every(([url]) => !String(url).includes("/mcp/import/"))).toBe(true);
    expect(textOf(root)).toContain("Colle une configuration à importer");
  });

  it("cache la section import à un compte non propriétaire", async () => {
    const fetcher = vi.fn(async () => json([]));
    const mcpUi = await import("../src/mcp-ui");
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    mcpUi.resetMcpUiState();
    const http = new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher: fetcher as never });
    const root = new FakeElement("div");
    mcpUi.renderMcpCenter(root as never, http, "operator");
    await flush();
    fire(root.querySelector("#mcp-tab-import") as FakeElement, "click");
    await flush();
    expect(textOf(root)).toContain("Réservé au propriétaire");
    expect(walk(root).some((node) => node.name === "import-content")).toBe(false);
  });
});
