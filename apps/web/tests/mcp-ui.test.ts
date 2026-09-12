/**
 * Tests de `mcp-ui.ts` sur un DOM minimal simulé.
 *
 * Aucune dépendance n’est ajoutée (ni jsdom ni happy-dom) : le stub ci-dessous
 * n’implémente que les API réellement utilisées par le module. Ces tests couvrent
 * deux régressions relevées en revue :
 *
 * 1. **jeton CSRF partagé** — `GET /auth/session` fait tourner le jeton côté serveur
 *    (un seul est valide à la fois). Le module ne doit donc jamais relire la session
 *    à l’ouverture de la route, et doit utiliser le client HTTP du shell dès qu’il en
 *    reçoit un, sinon les écritures du shell tombent en 403 après une simple visite.
 * 2. **état de module** — les données et le rôle d’un compte ne doivent pas survivre à
 *    une déconnexion (`resetMcpUiState`), et une nouvelle visite de la route doit relire
 *    l’API au lieu de repeindre la mémoire.
 */

import { describe, expect, it, vi } from "vitest";

// --- DOM minimal --------------------------------------------------------------

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
  autocomplete = "";
  href = "";
  rel = "";
  target = "";
  min = "";
  max = "";
  step = "";
  maxLength = 0;
  rows = 0;
  tabIndex = 0;
  required = false;
  disabled = false;
  hidden = false;
  checked = false;
  selected = false;
  noValidate = false;
  spellcheck = true;
  parent: FakeElement | null = null;
  readonly children: FakeElement[] = [];
  readonly attributes: Record<string, string> = {};
  readonly dataset: Record<string, string> = {};
  readonly listeners: Record<string, Handler[]> = {};
  private explicitValue: string | null = null;

  constructor(tagName: string) {
    this.tagName = tagName;
  }

  /** `<select>` : à défaut de valeur posée, la première option sélectionnée fait foi. */
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

  focus(): void {
    /* le focus n’a pas d’effet observable hors navigateur */
  }

  reportValidity(): boolean {
    return true;
  }

  /** Seuls sélecteurs utilisés par le module : `#identifiant` et `[data-x='y']`. */
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

function findAll(root: FakeElement, predicate: (node: FakeElement) => boolean): FakeElement[] {
  return walk(root).filter(predicate);
}

function inputNamed(root: FakeElement, name: string): FakeElement {
  const node = findAll(root, (candidate) => candidate.name === name)[0];
  if (!node) throw new Error(`Champ introuvable : ${name}`);
  return node;
}

/** Formulaire de création de secret : le seul qui porte un champ « value ». */
function secretForm(root: FakeElement): FakeElement {
  const node = findAll(root, (candidate) => candidate.tagName === "form"
    && walk(candidate).some((child) => child.name === "value"))[0];
  if (!node) throw new Error("Formulaire de création de secret introuvable");
  return node;
}

function fire(node: FakeElement, type: string, event: unknown = { preventDefault() {} }): void {
  for (const handler of node.listeners[type] ?? []) handler(event);
}

function installDocument(): void {
  (globalThis as unknown as { document: unknown }).document = {
    createElement: (tag: string) => new FakeElement(tag),
  };
}

async function flush(rounds = 12): Promise<void> {
  for (let index = 0; index < rounds; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

// --- Réponses simulées ---------------------------------------------------------

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function serverSummary(overrides: Record<string, unknown> = {}) {
  return {
    id: "server-1",
    name: "github",
    display_name: "GitHub",
    description: "Serveur MCP GitHub",
    source_kind: "manual",
    origin: "",
    transport: "http",
    execution_location: "platform",
    status: "active",
    current_revision_number: 1,
    discovery_current: true,
    tool_count: 2,
    binding_count: 0,
    target_worker_id: null,
    last_probe_status: "succeeded",
    last_probe_at: "2026-09-11T10:00:00Z",
    created_at: "2026-09-11T09:00:00Z",
    updated_at: "2026-09-11T10:00:00Z",
    revoked_at: null,
    ...overrides,
  };
}

function secretSummary(overrides: Record<string, unknown> = {}) {
  return {
    id: "secret-1",
    name: "GITHUB_TOKEN",
    scope_type: "platform",
    project_id: null,
    description: "Jeton d’API GitHub",
    key_id: "key-1",
    created_at: "2026-09-11T09:00:00Z",
    rotated_at: null,
    revoked_at: null,
    last_used_at: null,
    referenced_by_mcp_servers: [],
    ...overrides,
  };
}

const VAULT_READY = {
  configured: true,
  primary_key_id: "key-1",
  key_count: 1,
  message: "Coffre configuré",
};

const SESSION = {
  user: { id: "user-1", login: "owner", display_name: "Propriétaire", role: "owner" },
  csrf_token: "csrf-rotated",
  expires_at: "2026-09-12T12:00:00Z",
};

const OVERVIEW = {
  organizations: [],
  workspaces: [],
  departments: [],
  projects: [{
    id: "project-a",
    workspace_id: "workspace-1",
    department_id: null,
    name: "Projet A",
    project_type: "generic",
    description: "",
    status: "active",
  }],
  teams: [],
  team_members: [],
  agents: [],
  tasks: [],
};

type Route = (url: string, init: RequestInit | undefined) => Response | Promise<Response>;

/** Jeu de routes complet de la route « Connexions » (liste, probes, projets, runners, coffre). */
function routesFor(options: {
  servers?: unknown[];
  secrets?: unknown[];
  created?: unknown;
} = {}): [RegExp, Route][] {
  const servers = options.servers ?? [serverSummary()];
  const secrets = options.secrets ?? [secretSummary()];
  const created = options.created ?? secretSummary({ id: "secret-new", name: "NEW_TOKEN" });
  return [
    [/\/auth\/session$/, () => json(SESSION)],
    [/\/mcp\/servers/, () => json(servers)],
    [/\/mcp\/probes/, () => json([])],
    [/\/workers$/, () => json([])],
    [/\/overview$/, () => json(OVERVIEW)],
    [/\/secrets\/status$/, () => json(VAULT_READY)],
    [/\/secrets$/, (_url, init) => json((init?.method ?? "GET") === "POST" ? created : secrets)],
  ];
}

function recorder(routes: () => [RegExp, Route][]) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    for (const [pattern, route] of routes()) {
      if (pattern.test(url)) return route(url, init);
    }
    return json({ detail: `Route non simulée : ${url}` }, 404);
  });
}

function urlsOf(mock: ReturnType<typeof recorder>): string[] {
  return mock.mock.calls.map(([input]) => String(input));
}

function countOf(mock: ReturnType<typeof recorder>, pattern: RegExp): number {
  return urlsOf(mock).filter((url) => pattern.test(url)).length;
}

function callTo(mock: ReturnType<typeof recorder>, pattern: RegExp, method: string) {
  return mock.mock.calls.filter(([url, init]) => pattern.test(String(url))
    && ((init as RequestInit | undefined)?.method ?? "GET") === method).at(-1);
}

/**
 * Charge une instance fraîche du module avec un `fetch` global instrumenté.
 * `routes` est relu à chaque requête : un test peut changer les réponses entre
 * deux montages pour simuler un changement de compte.
 */
async function loadUi(initialRoutes: [RegExp, Route][] = routesFor()) {
  let routes = initialRoutes;
  const fetchMock = recorder(() => routes);
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  installDocument();
  vi.resetModules();
  const workspaceApi = await import("../src/workspace-api");
  const mcpUi = await import("../src/mcp-ui");
  return {
    mcpUi,
    workspaceApi,
    fetchMock,
    setRoutes(next: [RegExp, Route][]) {
      routes = next;
    },
    container(): FakeElement {
      return new FakeElement("div");
    },
  };
}

// --- Tests ---------------------------------------------------------------------

describe("mcp-ui — session partagée avec le shell", () => {
  it("ne lit jamais /auth/session à l’ouverture de la route", async () => {
    const { mcpUi, fetchMock } = await loadUi();
    const container = new FakeElement("div");

    mcpUi.renderMcpCenter(container as unknown as HTMLElement);
    mcpUi.renderSecretsPanel(container as unknown as HTMLElement);
    await flush();

    expect(countOf(fetchMock, /\/auth\/session$/)).toBe(0);
    expect(countOf(fetchMock, /\/mcp\/servers/)).toBe(1);
    expect(textOf(container)).toContain("GitHub");
    expect(textOf(container)).toContain("GITHUB_TOKEN");
  });

  it("émet toutes ses lectures avec le client HTTP fourni par le shell", async () => {
    const { mcpUi, workspaceApi, fetchMock } = await loadUi();
    const shellFetch = recorder(() => routesFor());
    const shellHttp = new workspaceApi.WorkspaceHttpClient({
      fetcher: shellFetch as unknown as typeof fetch,
    });
    shellHttp.setCsrfToken("csrf-shell");
    const container = new FakeElement("div");

    mcpUi.renderMcpCenter(container as unknown as HTMLElement, shellHttp);
    mcpUi.renderSecretsPanel(container as unknown as HTMLElement, shellHttp);
    await flush();

    expect(countOf(shellFetch, /\/mcp\/servers/)).toBe(1);
    expect(countOf(shellFetch, /\/secrets\/status$/)).toBe(1);
    expect(countOf(shellFetch, /\/auth\/session$/)).toBe(0);
    // Le client du module n’a servi à rien : aucune requête n’est partie ailleurs.
    expect(urlsOf(fetchMock)).toEqual([]);
  });

  it("écrit avec le jeton CSRF du shell, sans relire la session", async () => {
    const { mcpUi, workspaceApi, fetchMock } = await loadUi();
    const shellFetch = recorder(() => routesFor());
    const shellHttp = new workspaceApi.WorkspaceHttpClient({
      fetcher: shellFetch as unknown as typeof fetch,
    });
    shellHttp.setCsrfToken("csrf-shell");
    const container = new FakeElement("div");
    mcpUi.renderSecretsPanel(container as unknown as HTMLElement, shellHttp, "owner");
    await flush();

    const form = secretForm(container);
    inputNamed(form, "name").value = "NEW_TOKEN";
    inputNamed(form, "value").value = "valeur-a-chiffrer";
    fire(form, "submit");
    await flush();

    const post = callTo(shellFetch, /\/secrets$/, "POST");
    expect(post).toBeDefined();
    expect((post?.[1]?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-shell");
    expect(countOf(shellFetch, /\/auth\/session$/)).toBe(0);
    expect(urlsOf(fetchMock)).toEqual([]);
  });

  it("sans client partagé, ne demande la session qu’au moment d’une écriture", async () => {
    const { mcpUi, fetchMock } = await loadUi();
    const container = new FakeElement("div");
    mcpUi.renderSecretsPanel(container as unknown as HTMLElement);
    await flush();

    expect(countOf(fetchMock, /\/auth\/session$/)).toBe(0);

    const form = secretForm(container);
    inputNamed(form, "name").value = "NEW_TOKEN";
    inputNamed(form, "value").value = "valeur-a-chiffrer";
    fire(form, "submit");
    await flush();

    expect(countOf(fetchMock, /\/auth\/session$/)).toBe(1);
    const post = callTo(fetchMock, /\/secrets$/, "POST");
    expect((post?.[1]?.headers as Headers).get("X-CSRF-Token")).toBe(SESSION.csrf_token);
  });

  it("réarme le jeton après un refus : la tentative suivante repart d’une session fraîche", async () => {
    let refuse = true;
    const routes: [RegExp, Route][] = [
      ...routesFor(),
      [/\/secrets$/, (_url, init) => {
        if ((init?.method ?? "GET") !== "POST") return json([secretSummary()]);
        if (refuse) {
          refuse = false;
          return json({ detail: "Requête refusée" }, 403);
        }
        return json(secretSummary({ id: "secret-new", name: "NEW_TOKEN" }));
      }],
    ];
    // La route spécifique doit primer sur celle de `routesFor`.
    routes.unshift(routes.pop() as [RegExp, Route]);
    const { mcpUi, fetchMock } = await loadUi(routes);
    const container = new FakeElement("div");
    mcpUi.renderSecretsPanel(container as unknown as HTMLElement);
    await flush();

    const submit = () => {
      const form = secretForm(container);
      inputNamed(form, "name").value = "NEW_TOKEN";
      inputNamed(form, "value").value = "valeur-a-chiffrer";
      fire(form, "submit");
    };

    submit();
    await flush();
    expect(countOf(fetchMock, /\/auth\/session$/)).toBe(1);
    expect(textOf(container)).toContain("Accès refusé");

    submit();
    await flush();
    expect(countOf(fetchMock, /\/auth\/session$/)).toBe(2);
    expect(callTo(fetchMock, /\/secrets$/, "POST")).toBeDefined();
    expect(textOf(container)).toContain("NEW_TOKEN");
  });
});

describe("mcp-ui — état de module entre deux comptes", () => {
  it("resetMcpUiState() efface les serveurs, les secrets et le rôle du compte précédent", async () => {
    const { mcpUi, setRoutes } = await loadUi(routesFor({
      secrets: [secretSummary({ name: "ALPHA_TOKEN", description: "Jeton d’API GitHub" })],
    }));
    const first = new FakeElement("div");
    mcpUi.renderMcpCenter(first as unknown as HTMLElement, undefined, "owner");
    mcpUi.renderSecretsPanel(first as unknown as HTMLElement, undefined, "owner");
    await flush();
    expect(textOf(first)).toContain("GitHub");
    expect(textOf(first)).toContain("ALPHA_TOKEN");
    expect(textOf(first)).not.toContain("Lecture et rattachements seulement");

    mcpUi.resetMcpUiState();
    setRoutes(routesFor({
      servers: [serverSummary({
        id: "server-2",
        name: "jira",
        display_name: "Jira",
        description: "Serveur MCP Jira",
      })],
      secrets: [secretSummary({
        id: "secret-2",
        name: "JIRA_TOKEN",
        description: "Jeton d’API Jira",
      })],
    }));

    const second = new FakeElement("div");
    mcpUi.renderMcpCenter(second as unknown as HTMLElement, undefined, "operator");
    mcpUi.renderSecretsPanel(second as unknown as HTMLElement, undefined, "operator");
    await flush();

    const rendered = textOf(second);
    expect(rendered).toContain("Jira");
    expect(rendered).toContain("JIRA_TOKEN");
    expect(rendered).not.toContain("GitHub");
    expect(rendered).not.toContain("ALPHA_TOKEN");
    // Le rôle du compte précédent ne doit plus commander l’affichage.
    expect(rendered).toContain("Lecture et rattachements seulement");
  });

  it("jette une réponse partie avant la déconnexion au lieu de l’écrire dans l’état suivant", async () => {
    // La lecture du compte suivant reste en vol : seule une réponse retenue du compte
    // précédent pourrait peindre « GitHub » dans l’écran du compte suivant.
    const gates: Array<() => void> = [];
    const pending = () => new Promise<void>((resolve) => { gates.push(resolve); });
    let call = 0;
    const slowRoutes: [RegExp, Route][] = [
      [/\/mcp\/servers/, async () => {
        const index = call++;
        const gate = pending();
        await gate;
        return json(index === 0
          ? [serverSummary()]
          : [serverSummary({ id: "server-2", name: "jira", display_name: "Jira", description: "Serveur MCP Jira" })]);
      }],
      ...routesFor(),
    ];
    const { mcpUi } = await loadUi(slowRoutes);
    const first = new FakeElement("div");
    mcpUi.renderMcpCenter(first as unknown as HTMLElement);
    await flush(4);

    mcpUi.resetMcpUiState();
    const second = new FakeElement("div");
    mcpUi.renderMcpCenter(second as unknown as HTMLElement);
    await flush(4);
    // La réponse du compte précédent arrive maintenant, après la purge.
    gates[0]?.();
    await flush();

    expect(textOf(second)).not.toContain("GitHub");
    expect(textOf(second)).toContain("Lecture des serveurs MCP");
    expect(textOf(first)).not.toContain("GitHub");

    // La lecture du compte suivant, elle, est bien affichée.
    gates[1]?.();
    await flush();
    expect(textOf(second)).toContain("Jira");
  });

  it("resetMcpUiState() relâche le client HTTP du shell", async () => {
    const { mcpUi, workspaceApi, fetchMock } = await loadUi();
    const shellFetch = recorder(() => routesFor());
    const shellHttp = new workspaceApi.WorkspaceHttpClient({
      fetcher: shellFetch as unknown as typeof fetch,
    });
    const first = new FakeElement("div");
    mcpUi.renderMcpCenter(first as unknown as HTMLElement, shellHttp);
    await flush();
    const shellCalls = urlsOf(shellFetch).length;
    expect(shellCalls).toBeGreaterThan(0);

    mcpUi.resetMcpUiState();
    const second = new FakeElement("div");
    mcpUi.renderMcpCenter(second as unknown as HTMLElement);
    await flush();

    expect(urlsOf(shellFetch).length).toBe(shellCalls);
    expect(countOf(fetchMock, /\/mcp\/servers/)).toBe(1);
  });

  it("relit l’API à chaque montage de la route plutôt que de repeindre la mémoire", async () => {
    const { mcpUi, setRoutes } = await loadUi(routesFor());
    const first = new FakeElement("div");
    mcpUi.renderMcpCenter(first as unknown as HTMLElement);
    mcpUi.renderSecretsPanel(first as unknown as HTMLElement);
    await flush();
    expect(textOf(first)).toContain("GitHub");

    setRoutes(routesFor({
      servers: [serverSummary({
      id: "server-3",
      name: "gitlab",
      display_name: "GitLab",
      description: "Serveur MCP GitLab",
    })],
      secrets: [secretSummary({
      id: "secret-3",
      name: "GITLAB_TOKEN",
      description: "Jeton d’API GitLab",
    })],
    }));
    const second = new FakeElement("div");
    mcpUi.renderMcpCenter(second as unknown as HTMLElement);
    mcpUi.renderSecretsPanel(second as unknown as HTMLElement);
    await flush();

    const rendered = textOf(second);
    expect(rendered).toContain("GitLab");
    expect(rendered).toContain("GITLAB_TOKEN");
    expect(rendered).not.toContain("GitHub");
  });
});
