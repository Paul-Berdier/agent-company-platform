import { describe, expect, it, vi } from "vitest";

type Handler = (event: { preventDefault(): void }) => void;

class FakeElement {
  readonly tagName: string;
  className = "";
  textContent = "";
  id = "";
  htmlFor = "";
  type = "";
  name = "";
  value = "";
  title = "";
  placeholder = "";
  checked = false;
  selected = false;
  disabled = false;
  required = false;
  maxLength = 0;
  min = "";
  max = "";
  step = "";
  readonly dataset: Record<string, string> = {};
  readonly attributes: Record<string, string> = {};
  readonly children: FakeElement[] = [];
  readonly listeners: Record<string, Handler[]> = {};

  constructor(tagName: string) { this.tagName = tagName; }
  append(...nodes: FakeElement[]): void { this.children.push(...nodes); }
  replaceChildren(...nodes: FakeElement[]): void { this.children.splice(0, this.children.length, ...nodes); }
  setAttribute(name: string, value: string): void { this.attributes[name] = value; }
  removeAttribute(name: string): void { delete this.attributes[name]; }
  addEventListener(type: string, handler: Handler): void { (this.listeners[type] ??= []).push(handler); }
  reportValidity(): boolean { return true; }
  querySelectorAll(selector: string): FakeElement[] {
    return selector === "[data-focus-key]" ? walk(this).filter((node) => Boolean(node.dataset.focusKey)) : [];
  }
  focus(): void {
    (globalThis.document as unknown as { activeElement: FakeElement | null }).activeElement = this;
  }
}

class FakeInput extends FakeElement { constructor() { super("input"); } }
class FakeSelect extends FakeElement { constructor() { super("select"); } }
class FakeTextarea extends FakeElement { constructor() { super("textarea"); } }

function installDom(): void {
  Object.defineProperty(globalThis, "HTMLInputElement", { value: FakeInput, configurable: true });
  Object.defineProperty(globalThis, "HTMLSelectElement", { value: FakeSelect, configurable: true });
  Object.defineProperty(globalThis, "HTMLTextAreaElement", { value: FakeTextarea, configurable: true });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      activeElement: null,
      createElement(tag: string) {
        if (tag === "input") return new FakeInput();
        if (tag === "select") return new FakeSelect();
        if (tag === "textarea") return new FakeTextarea();
        return new FakeElement(tag);
      },
    },
  });
}

function walk(node: FakeElement): FakeElement[] {
  return node.children.flatMap((child) => [child, ...walk(child)]);
}

function textOf(node: FakeElement): string {
  return [node.textContent, ...node.children.map(textOf)].filter(Boolean).join(" ");
}

function button(root: FakeElement, label: string): FakeElement {
  const result = walk(root).find((node) => node.tagName === "button" && textOf(node).includes(label));
  if (!result) throw new Error(`Bouton introuvable : ${label}`);
  return result;
}

function control(root: FakeElement, name: string): FakeElement {
  const result = walk(root).find((node) => node.name === name);
  if (!result) throw new Error(`Contrôle introuvable : ${name}`);
  return result;
}

function fire(node: FakeElement, type: string): void {
  for (const handler of node.listeners[type] ?? []) handler({ preventDefault() {} });
}

async function flush(rounds = 12): Promise<void> {
  for (let index = 0; index < rounds; index += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

const PROJECT = {
  id: "project-1", workspace_id: "workspace-1", department_id: null,
  name: "Portail", project_type: "software", description: "", status: "active",
};
const OVERVIEW = {
  organizations: [], workspaces: [], departments: [], projects: [PROJECT], teams: [], team_members: [], agents: [], tasks: [],
};
const TEMPLATE = {
  title: "Audit", objective: "Analyser le dépôt", expected_outcome: "Rapport",
  acceptance_criteria: ["Constats vérifiables"],
  autonomy: { mode: "supervised", allowed_actions: ["read"], forbidden_actions: ["write"], approval_required_actions: [] },
  resources: [], budget: { max_cost: null, currency: "EUR", max_tokens: null, max_tool_calls: 50 },
  duration_seconds: 3600, team_id: null, agent_instance_id: null, priority: 3, required_capabilities: [],
};
const SUMMARY = {
  id: "automation-1", project_id: "project-1", name: "Audit", description: "",
  schedule: { kind: "cron", expression: "0 9 * * *", timezone: "Europe/Paris" },
  enabled: false, catchup_policy: "skip", max_concurrent_runs: 1,
  next_run_at: null, created_at: "2026-09-14T08:00:00Z",
};
const DETAIL = { ...SUMMARY, mission_template: TEMPLATE, recent_runs: [] };
const RUN = {
  id: "run-1", automation_id: "automation-1", fire_key: "a".repeat(32),
  scheduled_for: "2026-09-14T08:00:00Z", fired_at: "2026-09-14T08:00:01Z",
  task_id: "task-1", trigger_kind: "manual", outcome: "launched", completion_status: null, detail: "Mission créée",
};
const PREFS = {
  channel: "in_app", enabled: true, minimum_severity: "warning", budget_alerts: true,
  automation_failures: true, storage_alerts: true, project_id: "project-1", updated_at: "2026-09-14T08:00:00Z",
};
const POLICY = {
  timezone: "Europe/Paris", daily_budget: null, provider_budgets: [], max_concurrent_missions: 4,
  max_retries_per_mission: 3, max_spawned_agents_per_run: 4, project_id: "project-1", updated_at: "2026-09-14T08:00:00Z",
};
const BUDGET_USAGE = {
  project_id: "project-1", accounting_day: "2026-09-14", timezone: "Europe/Paris",
  totals: { reports: 0, pending_reservations: 0, cost: null, currency: null, tokens_input: null, tokens_output: null, tool_calls: null, saturated_metrics: [], usage_reported: false, estimated: false },
  missions: [], providers: [],
};

describe("renderAutomations", () => {
  it("rend les données réelles et relie le bouton Activer à la mutation puis au rechargement", async () => {
    installDom();
    let enabled = false;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/overview")) return json(OVERVIEW);
      if (url.includes("/automations/calendar?")) return json([]);
      if (url.includes("/automations?")) return json([{ ...SUMMARY, enabled, next_run_at: enabled ? "2026-09-15T07:00:00Z" : null }]);
      if (url.includes("/alerts?")) return json([]);
      if (url.endsWith("/notification-preferences")) return json(PREFS);
      if (url.endsWith("/budget-policy")) return json(POLICY);
      if (url.endsWith("/automations/automation-1/enable")) {
        enabled = true;
        return json({ ...DETAIL, enabled: true, next_run_at: "2026-09-15T07:00:00Z" });
      }
      return json({ detail: `Route inattendue : ${url}` }, 404);
    });
    vi.resetModules();
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    const { renderAutomations, resetAutomationUiState } = await import("../src/automation-ui");
    const container = new FakeElement("div");
    renderAutomations(container as unknown as HTMLElement, new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher }));
    await flush();

    expect(textOf(container)).toContain("Automatisations vérifiables");
    expect(textOf(container)).toContain("Audit");
    expect(textOf(container)).toContain("Aucune tant que la routine est en pause");
    fire(button(container, "Activer"), "click");
    await flush(20);

    expect(fetcher.mock.calls.some((call) => String(call[0]).endsWith("/automations/automation-1/enable"))).toBe(true);
    expect(textOf(container)).toContain("Routine activée");
    expect(textOf(container)).toContain("15/09/2026");
    resetAutomationUiState();
  });

  it("affiche un échec explicite sans injecter de données de démonstration", async () => {
    installDom();
    const fetcher = vi.fn(async () => json({ detail: "Service indisponible" }, 503));
    vi.resetModules();
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    const { renderAutomations, resetAutomationUiState } = await import("../src/automation-ui");
    const container = new FakeElement("div");
    renderAutomations(container as unknown as HTMLElement, new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher }));
    await flush();

    expect(textOf(container)).toContain("Chargement impossible");
    expect(textOf(container)).toContain("Service indisponible");
    expect(textOf(container)).not.toContain("Audit hebdomadaire");
    resetAutomationUiState();
  });

  it("réutilise la clé idempotente après un résultat réseau incertain", async () => {
    installDom();
    const triggerKeys: string[] = [];
    let triggerAttempt = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/overview")) return json(OVERVIEW);
      if (url.endsWith("/automations/automation-1/trigger")) {
        triggerKeys.push((init?.headers as Headers).get("Idempotency-Key") ?? "");
        triggerAttempt += 1;
        if (triggerAttempt === 1) throw new TypeError("connection lost");
        return json(RUN, 201);
      }
      if (url.includes("/automations/calendar?")) return json([]);
      if (url.includes("/automations?")) return json([SUMMARY]);
      if (url.includes("/alerts?")) return json([]);
      if (url.endsWith("/notification-preferences")) return json(PREFS);
      if (url.endsWith("/budget-policy")) return json(POLICY);
      return json({ detail: `Route inattendue : ${url}` }, 404);
    });
    vi.resetModules();
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    const { renderAutomations, resetAutomationUiState } = await import("../src/automation-ui");
    const container = new FakeElement("div");
    renderAutomations(container as unknown as HTMLElement, new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher }));
    await flush();

    fire(button(container, "Déclencher maintenant"), "click");
    await flush(20);
    expect(textOf(container)).toContain("Résultat incertain");
    fire(button(container, "Déclencher maintenant"), "click");
    await flush(20);

    expect(triggerKeys).toHaveLength(2);
    expect(triggerKeys[0]).not.toBe("");
    expect(triggerKeys[1]).toBe(triggerKeys[0]);
    expect(textOf(container)).toContain("Déclenchement enregistré");
    resetAutomationUiState();
  });

  it("n’invente aucun zéro lors d’échecs partiels et conserve le focus des onglets", async () => {
    installDom();
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/overview")) return json(OVERVIEW);
      if (url.includes("/automations?") || url.includes("/alerts?")) throw new TypeError("offline");
      if (url.includes("/automations/calendar?")) return json([]);
      if (url.endsWith("/notification-preferences")) return json(PREFS);
      if (url.endsWith("/budget-policy")) return json({ ...POLICY, daily_budget: { max_cost: 25, currency: "USD", max_tokens: null, max_tool_calls: null } });
      return json({ detail: `Route inattendue : ${url}` }, 404);
    });
    vi.resetModules();
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    const { renderAutomations, resetAutomationUiState } = await import("../src/automation-ui");
    const container = new FakeElement("div");
    renderAutomations(container as unknown as HTMLElement, new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher }));
    await flush();

    expect(textOf(container)).toContain("Routines actives Indisponible");
    expect(textOf(container)).toContain("Alertes indisponibles");
    expect(textOf(container)).not.toContain("Aucune alerte ouverte");
    const settings = button(container, "Limites & notifications");
    settings.focus();
    fire(settings, "click");
    expect(textOf(container)).toContain("Coût quotidien (USD)");
    expect(textOf(globalThis.document.activeElement as unknown as FakeElement)).toContain("Limites & notifications");
    resetAutomationUiState();
  });

  it("rejoue une création incertaine avec la même clé et le même corps", async () => {
    installDom();
    const createKeys: string[] = [];
    const createBodies: unknown[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/overview")) return json(OVERVIEW);
      if (url.endsWith("/projects/project-1/automations") && init?.method === "POST") {
        createKeys.push((init.headers as Headers).get("Idempotency-Key") ?? "");
        const body = JSON.parse(String(init.body));
        createBodies.push(body);
        if (createKeys.length === 1) throw new TypeError("connection lost");
        return json({
          ...DETAIL,
          name: body.name,
          description: body.description,
          schedule: body.schedule,
          mission_template: {
            ...TEMPLATE,
            ...body.mission_template,
            team_id: body.mission_template.team_id ?? null,
            agent_instance_id: body.mission_template.agent_instance_id ?? null,
          },
          catchup_policy: body.catchup_policy,
          max_concurrent_runs: body.max_concurrent_runs,
        }, 201);
      }
      if (url.includes("/automations/calendar?")) return json([]);
      if (url.includes("/automations?")) return json([SUMMARY]);
      if (url.includes("/alerts?")) return json([]);
      if (url.endsWith("/notification-preferences")) return json(PREFS);
      if (url.endsWith("/budget-policy")) return json(POLICY);
      if (url.endsWith("/budget-usage")) return json(BUDGET_USAGE);
      return json({ detail: `Route inattendue : ${url}` }, 404);
    });
    vi.resetModules();
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    const { renderAutomations, resetAutomationUiState } = await import("../src/automation-ui");
    const container = new FakeElement("div");
    renderAutomations(container as unknown as HTMLElement, new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher }));
    await flush();

    fire(button(container, "Nouvelle routine"), "click");
    const name = control(container, "name");
    name.value = "Routine stable";
    fire(name, "input");
    fire(button(container, "Créer en pause"), "submit");
    // Le submit appartient au formulaire, pas au bouton.
    const form = walk(container).find((node) => node.tagName === "form" && walk(node).some((child) => child.name === "name"));
    if (!form) throw new Error("Formulaire de création introuvable");
    fire(form, "submit");
    await flush(20);
    expect(textOf(container)).toContain("Résultat incertain");
    const retryForm = walk(container).find((node) => node.tagName === "form" && walk(node).some((child) => child.name === "name"));
    if (!retryForm) throw new Error("Formulaire de rejeu introuvable");
    fire(retryForm, "submit");
    await flush(20);

    expect(createKeys).toHaveLength(2);
    expect(createKeys[0]).not.toBe("");
    expect(createKeys[1]).toBe(createKeys[0]);
    expect(createBodies[1]).toEqual(createBodies[0]);
    expect(textOf(container)).toContain("créée en pause");
    resetAutomationUiState();
  });

  it("exige une confirmation avant de révoquer un secret webhook", async () => {
    installDom();
    let rotations = 0;
    const rotationKeys: string[] = [];
    const rotationSecrets: string[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/overview")) return json(OVERVIEW);
      if (url.includes("/automations/calendar?")) return json([]);
      if (url.includes("/automations?")) return json([SUMMARY]);
      if (url.includes("/alerts?")) return json([]);
      if (url.endsWith("/notification-preferences")) return json(PREFS);
      if (url.endsWith("/budget-policy")) return json(POLICY);
      if (url.endsWith("/budget-usage")) return json(BUDGET_USAGE);
      if (url.endsWith("/automations/automation-1/runs?limit=50")) {
        return json([
          { ...RUN, completion_status: "failed" },
          {
            ...RUN,
            id: "run-skip",
            fire_key: "b".repeat(32),
            task_id: null,
            outcome: "skipped_catchup",
            completion_status: null,
          },
        ]);
      }
      if (url.endsWith("/automations/automation-1/webhook") && method === "GET") {
        return json({ enabled: true, secret_configured: true, endpoint_path: "/automations/automation-1/webhook/trigger", rotated_at: "2026-09-14T08:00:00Z" });
      }
      if (url.endsWith("/automations/automation-1/webhook") && method === "POST") {
        rotations += 1;
        const secret = String((JSON.parse(String(init?.body)) as { secret: string }).secret);
        rotationSecrets.push(secret);
        rotationKeys.push((init?.headers as Headers).get("Idempotency-Key") ?? "");
        if (rotations === 1) throw new TypeError("connection lost");
        return json({ enabled: true, secret_configured: true, endpoint_path: "/automations/automation-1/webhook/trigger", rotated_at: "2026-09-14T09:00:00Z", secret });
      }
      if (url.endsWith("/automations/automation-1")) return json(DETAIL);
      return json({ detail: `Route inattendue : ${url}` }, 404);
    });
    vi.resetModules();
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    const { renderAutomations, resetAutomationUiState } = await import("../src/automation-ui");
    const container = new FakeElement("div");
    renderAutomations(container as unknown as HTMLElement, new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher }));
    await flush();
    fire(button(container, "Historique et webhook"), "click");
    await flush(20);

    expect(textOf(container)).toContain("Mission échouée");
    expect(textOf(container)).toContain("Ignorée · rattrapage");

    fire(button(container, "Faire tourner le secret"), "click");
    expect(rotations).toBe(0);
    expect(textOf(container)).toContain("révoquera immédiatement");
    fire(button(container, "Confirmer la rotation"), "click");
    await flush(20);
    expect(rotations).toBe(1);
    expect(textOf(container)).toContain("Secret de récupération");
    expect(rotationSecrets[0]).toHaveLength(64);
    fire(button(container, "Faire tourner le secret"), "click");
    fire(button(container, "Confirmer la rotation"), "click");
    await flush(20);
    expect(rotations).toBe(2);
    expect(rotationKeys[0]).not.toBe("");
    expect(rotationKeys[1]).toBe(rotationKeys[0]);
    expect(rotationSecrets[1]).toBe(rotationSecrets[0]);
    expect(textOf(container)).toContain(rotationSecrets[0]);
    resetAutomationUiState();
  });

  it("exige aussi une confirmation avant la première activation du webhook", async () => {
    installDom();
    let activations = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/overview")) return json(OVERVIEW);
      if (url.includes("/automations/calendar?")) return json([]);
      if (url.includes("/automations?")) return json([SUMMARY]);
      if (url.includes("/alerts?")) return json([]);
      if (url.endsWith("/notification-preferences")) return json(PREFS);
      if (url.endsWith("/budget-policy")) return json(POLICY);
      if (url.endsWith("/budget-usage")) return json(BUDGET_USAGE);
      if (url.endsWith("/automations/automation-1/runs?limit=50")) return json([]);
      if (url.endsWith("/automations/automation-1/webhook") && method === "GET") {
        return json({ enabled: false, secret_configured: false, endpoint_path: "/automations/automation-1/webhook/trigger", rotated_at: null });
      }
      if (url.endsWith("/automations/automation-1/webhook") && method === "POST") {
        activations += 1;
        const secret = String((JSON.parse(String(init?.body)) as { secret: string }).secret);
        return json({ enabled: true, secret_configured: true, endpoint_path: "/automations/automation-1/webhook/trigger", rotated_at: "2026-09-14T09:00:00Z", secret });
      }
      if (url.endsWith("/automations/automation-1")) return json(DETAIL);
      return json({ detail: `Route inattendue : ${url}` }, 404);
    });
    vi.resetModules();
    const { WorkspaceHttpClient } = await import("../src/workspace-api");
    const { renderAutomations, resetAutomationUiState } = await import("../src/automation-ui");
    const container = new FakeElement("div");
    renderAutomations(container as unknown as HTMLElement, new WorkspaceHttpClient({ baseUrl: "https://api.test", fetcher }));
    await flush();
    fire(button(container, "Historique et webhook"), "click");
    await flush(20);

    fire(button(container, "Activer le webhook"), "click");
    expect(activations).toBe(0);
    expect(textOf(container)).toContain("créera un secret persistant");
    fire(button(container, "Confirmer l’activation du webhook"), "click");
    await flush(20);

    expect(activations).toBe(1);
    expect(textOf(container)).toContain("Secret affiché une seule fois");
    resetAutomationUiState();
  });
});
