import { describe, expect, it, vi } from "vitest";

import { AutomationApiClient, automationValidators } from "../src/automation-api";
import { WorkspaceApiError } from "../src/workspace-api";

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

const schedule = { kind: "cron" as const, expression: "0 9 * * 1-5", timezone: "Europe/Paris" };
const missionTemplate = {
  title: "Audit hebdomadaire",
  objective: "Analyser le dépôt.",
  expected_outcome: "Un rapport vérifiable.",
  acceptance_criteria: ["Le dépôt reste inchangé"],
  autonomy: {
    mode: "supervised" as const,
    allowed_actions: ["read"],
    forbidden_actions: ["write"],
    approval_required_actions: [],
  },
  resources: [],
  budget: { max_cost: null, currency: "EUR", max_tokens: null, max_tool_calls: 20 },
  duration_seconds: 3600,
  team_id: null,
  agent_instance_id: null,
  priority: 3,
  required_capabilities: [],
};
const run = {
  id: "run-1",
  automation_id: "automation-1",
  fire_key: "a".repeat(32),
  scheduled_for: "2026-10-25T00:30:00Z",
  fired_at: "2026-10-25T00:30:02Z",
  task_id: "task-1",
  trigger_kind: "manual",
  outcome: "launched",
  completion_status: null,
  detail: "Mission créée",
};
const summary = {
  id: "automation-1",
  project_id: "project/one",
  name: "Audit hebdomadaire",
  description: "",
  schedule,
  enabled: false,
  catchup_policy: "skip",
  max_concurrent_runs: 1,
  next_run_at: null,
  created_at: "2026-09-14T08:00:00Z",
};
const detail = { ...summary, mission_template: missionTemplate, recent_runs: [run] };

describe("configuration d’exécution des routines", () => {
  it("transporte execution sans perte et refuse un serveur qui la retire", async () => {
    const execution = { mode: "multi_agent" as const, executors: ["codex_cli", "claude_code"] as ("codex_cli" | "claude_code")[], max_concurrency: 2 };
    const template = { ...missionTemplate, execution };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ ...detail, mission_template: template }, 201))
      .mockResolvedValueOnce(json(detail, 201));
    const client = new AutomationApiClient({ fetcher });
    const input = { name: summary.name, schedule, mission_template: template };
    await expect(client.createAutomation(summary.project_id, input, "team-key")).resolves.toMatchObject({
      mission_template: { execution },
    });
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body)).mission_template.execution).toEqual(execution);
    await expect(client.createAutomation(summary.project_id, input, "team-key-2")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("refuse une configuration d’exécution inconnue dans le détail serveur", () => {
    expect(automationValidators.detail({
      ...detail, mission_template: { ...missionTemplate, execution: { mode: "unknown" } },
    })).toBe(false);
  });
});
const calendar = {
  occurs_at_utc: "2026-10-25T00:30:00Z",
  occurs_at_local: "2026-10-25T02:30:00+02:00",
  timezone: "Europe/Paris",
  utc_offset_minutes: 120,
  automation_id: "automation-1",
  automation_name: "Audit hebdomadaire",
  state: "planned",
  task_id: null,
  outcome: null,
};
const webhook = {
  enabled: false,
  secret_configured: false,
  endpoint_path: "/automations/automation-1/webhook/trigger",
  rotated_at: null,
};
const webhookSecret = "s".repeat(43);
const alert = {
  id: "alert-1",
  project_id: "project/one",
  kind: "automation.repeated_failure",
  severity: "critical",
  title: "Échecs répétés",
  detail: "La routine a échoué trois fois.",
  task_id: null,
  automation_id: "automation-1",
  acknowledged_at: null,
  acknowledged_by_user_id: null,
  acknowledgement_comment: "",
  created_at: "2026-09-14T09:00:00Z",
};
const preferences = {
  channel: "in_app",
  enabled: true,
  minimum_severity: "warning",
  budget_alerts: true,
  automation_failures: true,
  storage_alerts: true,
  project_id: "project/one",
  updated_at: "2026-09-14T09:00:00Z",
};
const budget = {
  timezone: "Europe/Paris",
  daily_budget: null,
  provider_budgets: [],
  max_concurrent_missions: 2,
  max_retries_per_mission: 1,
  max_spawned_agents_per_run: 3,
  project_id: "project/one",
  updated_at: "2026-09-14T09:00:00Z",
};
const budgetUsage = {
  project_id: "project/one",
  accounting_day: "2026-09-14",
  timezone: "Europe/Paris",
  totals: {
    reports: 1,
    pending_reservations: 0,
    cost: 0,
    currency: "EUR",
    tokens_input: null,
    tokens_output: null,
    tool_calls: 0,
    saturated_metrics: [],
    usage_reported: true,
    estimated: false,
  },
  missions: [],
  providers: [],
};

describe("AutomationApiClient", () => {
  it("liste, crée et modifie une routine sur les routes réelles", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json([summary]))
      .mockResolvedValueOnce(json(detail, 201))
      .mockResolvedValueOnce(json({ ...detail, name: "Audit renommé" }));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-shell");

    await expect(client.listAutomations("project/one", false)).resolves.toEqual([summary]);
    await expect(client.createAutomation("project/one", {
      name: summary.name,
      schedule,
      mission_template: missionTemplate,
    }, "create-key")).resolves.toMatchObject({ id: "automation-1", enabled: false });
    await expect(client.updateAutomation("automation-1", { name: "Audit renommé" }, "update-key")).resolves.toMatchObject({ name: "Audit renommé" });

    expect(String(fetcher.mock.calls[0][0])).toContain("/automations?project_id=project%2Fone&enabled=false&limit=200");
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/projects/project%2Fone/automations");
    expect(fetcher.mock.calls[1][1]?.method).toBe("POST");
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-shell");
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("Idempotency-Key")).toBe("create-key");
    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({ name: "Audit renommé" });
    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("Idempotency-Key")).toBe("update-key");
  });

  it("pilote activation, pause, déclenchement idempotent et historique", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ ...detail, enabled: true }))
      .mockResolvedValueOnce(json({ ...detail, enabled: false }))
      .mockResolvedValueOnce(json(run, 201))
      .mockResolvedValueOnce(json([run]));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await client.setEnabled("automation-1", true, "enable-key");
    await client.setEnabled("automation-1", false, "disable-key");
    await expect(client.trigger("automation-1", "manual-key")).resolves.toMatchObject({ outcome: "launched" });
    await expect(client.listRuns("automation-1", 12)).resolves.toEqual([run]);

    expect(fetcher.mock.calls.map((call) => String(call[0]))).toEqual([
      "https://api.example.test/automations/automation-1/enable",
      "https://api.example.test/automations/automation-1/disable",
      "https://api.example.test/automations/automation-1/trigger",
      "https://api.example.test/automations/automation-1/runs?limit=12",
    ]);
    expect((fetcher.mock.calls[0][1]?.headers as Headers).get("Idempotency-Key")).toBe("enable-key");
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("Idempotency-Key")).toBe("disable-key");
    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("Idempotency-Key")).toBe("manual-key");
  });

  it("charge le calendrier DST et gère le webhook sans jamais relire son secret", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json([calendar]))
      .mockResolvedValueOnce(json(webhook))
      .mockResolvedValueOnce(json({ ...webhook, enabled: true, secret_configured: true, secret: webhookSecret, rotated_at: "2026-09-14T10:00:00Z" }, 201))
      .mockResolvedValueOnce(json(webhook));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.calendar({
      start: "2026-10-24T00:00:00Z",
      end: "2026-10-26T00:00:00Z",
      projectId: "project/one",
    })).resolves.toEqual([calendar]);
    await expect(client.getWebhook("automation-1")).resolves.not.toHaveProperty("secret");
    await expect(client.rotateWebhook("automation-1", webhookSecret, "rotate-key")).resolves.toMatchObject({ secret: webhookSecret });
    await expect(client.disableWebhook("automation-1", "webhook-disable-key")).resolves.toMatchObject({ enabled: false });

    const calendarUrl = String(fetcher.mock.calls[0][0]);
    expect(calendarUrl).toContain("/automations/calendar?");
    expect(calendarUrl).toContain("project_id=project%2Fone");
    expect(fetcher.mock.calls[2][1]?.method).toBe("POST");
    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({ secret: webhookSecret });
    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("Idempotency-Key")).toBe("rotate-key");
    expect(fetcher.mock.calls[3][1]?.method).toBe("DELETE");
    expect((fetcher.mock.calls[3][1]?.headers as Headers).get("Idempotency-Key")).toBe("webhook-disable-key");
  });

  it("liste/acquitte les alertes et persiste uniquement le canal in-app et les budgets", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json([alert]))
      .mockResolvedValueOnce(json({
        ...alert,
        acknowledged_at: "2026-09-14T10:00:00Z",
        acknowledged_by_user_id: "user-1",
        acknowledgement_comment: "Traité",
      }))
      .mockResolvedValueOnce(json(preferences))
      .mockResolvedValueOnce(json({ ...preferences, enabled: false }))
      .mockResolvedValueOnce(json(budget))
      .mockResolvedValueOnce(json(budgetUsage))
      .mockResolvedValueOnce(json({ ...budget, daily_budget: { max_cost: 0, currency: "EUR", max_tokens: null, max_tool_calls: null } }));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.listAlerts({ projectId: "project/one", open: true })).resolves.toEqual([alert]);
    await expect(client.acknowledgeAlert("alert-1", { comment: "Traité" })).resolves.toMatchObject({ acknowledgement_comment: "Traité" });
    await client.getNotificationPreferences("project/one");
    await client.putNotificationPreferences("project/one", { channel: "in_app", enabled: false });
    await expect(client.getBudgetPolicy("project/one")).resolves.toMatchObject({ daily_budget: null });
    await expect(client.getBudgetUsage("project/one")).resolves.toMatchObject({
      accounting_day: "2026-09-14",
      totals: { cost: 0, tokens_input: null, tool_calls: 0 },
    });
    await expect(client.putBudgetPolicy("project/one", {
      timezone: "Europe/Paris",
      daily_budget: { max_cost: 0, currency: "EUR", max_tokens: null, max_tool_calls: null },
      provider_budgets: [],
      max_concurrent_missions: 2,
      max_retries_per_mission: 1,
      max_spawned_agents_per_run: 3,
    })).resolves.toMatchObject({ daily_budget: { max_cost: 0 } });

    expect(String(fetcher.mock.calls[0][0])).toContain("open=true");
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({ comment: "Traité" });
    expect(JSON.parse(String(fetcher.mock.calls[3][1]?.body))).toEqual({ channel: "in_app", enabled: false });
    expect(String(fetcher.mock.calls[5][0])).toContain("/projects/project%2Fone/budget-usage");
    expect(JSON.parse(String(fetcher.mock.calls[6][1]?.body)).daily_budget.max_cost).toBe(0);
  });

  it("distingue un refus HTTP d’une réponse qui viole le contrat", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ detail: "Accès refusé" }, 403))
      .mockResolvedValueOnce(json([{ ...summary, enabled: "yes" }]));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.listAlerts()).rejects.toMatchObject<Partial<WorkspaceApiError>>({ kind: "forbidden", status: 403 });
    await expect(client.listAutomations()).rejects.toMatchObject<Partial<WorkspaceApiError>>({ kind: "invalid_response" });
    expect(automationValidators.detail({
      ...detail,
      mission_template: {
        ...missionTemplate,
        budget: { max_cost: null, currency: "EUR", max_tokens: null, max_tool_calls: null },
      },
    })).toBe(false);
    expect(automationValidators.summary({ ...summary, created_at: null })).toBe(false);
    expect(automationValidators.summary({ ...summary, max_concurrent_runs: 6 })).toBe(false);
    expect(automationValidators.run({ ...run, fire_key: "not-a-fire-key" })).toBe(false);
    expect(automationValidators.run({ ...run, fired_at: "2026-09-14T09:00:00" })).toBe(false);
    expect(automationValidators.run({ ...run, completion_status: undefined })).toBe(false);
    expect(automationValidators.run({ ...run, completion_status: "running" })).toBe(false);
    expect(automationValidators.run({
      ...run,
      task_id: null,
      outcome: "skipped_catchup",
      completion_status: null,
    })).toBe(true);
    expect(automationValidators.run({ ...run, completion_status: "interrupted" })).toBe(true);
    expect(automationValidators.calendarEntry({ ...calendar, utc_offset_minutes: 60 })).toBe(false);
    expect(automationValidators.calendarEntry({ ...calendar, occurs_at_local: "2026-10-25T02:30:00" })).toBe(false);
    expect(automationValidators.calendarEntry({
      ...calendar,
      occurs_at_utc: "2026-10-25T00:01:00Z",
      occurs_at_local: "2026-10-25T09:00:00+09:00",
      utc_offset_minutes: 540,
    })).toBe(false);
    // Le serveur est l'autorité IANA : le client vérifie l'instant et l'offset
    // transporté sans ré-arbitrer avec une base de fuseaux locale potentiellement
    // plus ancienne après un changement réglementaire.
    expect(automationValidators.calendarEntry({
      ...calendar,
      occurs_at_utc: "2040-06-01T00:00:00Z",
      occurs_at_local: "2040-06-01T03:00:00+03:00",
      utc_offset_minutes: 180,
    })).toBe(true);
    expect(automationValidators.alert({ ...alert, created_at: null })).toBe(false);
    expect(automationValidators.alert({ ...alert, acknowledged_at: "2026-09-14T10:00:00" })).toBe(false);
    expect(automationValidators.notificationPreferences({ ...preferences, updated_at: null })).toBe(false);
    expect(automationValidators.projectBudgetPolicy({
      ...budget,
      daily_budget: { max_cost: -1, currency: "EUR", max_tokens: null, max_tool_calls: null },
    })).toBe(false);
    expect(automationValidators.projectBudgetPolicy({
      ...budget,
      timezone: " ",
      daily_budget: { max_cost: -1, currency: "", max_tokens: null, max_tool_calls: null },
    })).toBe(false);
    expect(automationValidators.projectBudgetPolicy({
      ...budget,
      provider_budgets: [
        { provider: "OpenAI", budget: { max_cost: 1, currency: "EUR", max_tokens: null, max_tool_calls: null } },
        { provider: " openai ", budget: { max_cost: 2, currency: "EUR", max_tokens: null, max_tool_calls: null } },
      ],
    })).toBe(false);
    expect(automationValidators.projectBudgetPolicy({ ...budget, max_concurrent_missions: 0 })).toBe(false);
    expect(automationValidators.projectBudgetPolicy({ ...budget, updated_at: null })).toBe(false);
    expect(automationValidators.budgetConsumptionSummary(budgetUsage)).toBe(true);
    expect(automationValidators.budgetConsumptionSummary({
      ...budgetUsage,
      totals: { ...budgetUsage.totals, cost: null, currency: "EUR" },
    })).toBe(true);
    expect(automationValidators.budgetConsumptionSummary({
      ...budgetUsage,
      totals: { ...budgetUsage.totals, reports: 0, cost: 0 },
    })).toBe(false);
    expect(automationValidators.budgetConsumptionSummary({
      ...budgetUsage,
      totals: {
        ...budgetUsage.totals,
        tokens_input: Number.MAX_SAFE_INTEGER,
        saturated_metrics: ["tokens_input"],
      },
    })).toBe(true);
    expect(automationValidators.budgetConsumptionSummary({
      ...budgetUsage,
      totals: {
        ...budgetUsage.totals,
        tokens_input: 42,
        saturated_metrics: ["tokens_input"],
      },
    })).toBe(false);
    expect(automationValidators.budgetConsumptionSummary({
      ...budgetUsage,
      accounting_day: "2026-02-30",
    })).toBe(false);
  });

  it("refuse qu’un GET de statut webhook réintroduise le secret à affichage unique", async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ ...webhook, secret: webhookSecret }));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.getWebhook("automation-1")).rejects.toMatchObject<Partial<WorkspaceApiError>>({ kind: "invalid_response" });
    const emptySecretClient = new AutomationApiClient({
      baseUrl: "https://api.example.test",
      fetcher: vi.fn().mockResolvedValue(json({ ...webhook, secret: "" })),
    });
    await expect(emptySecretClient.rotateWebhook("automation-1", webhookSecret, "rotate-key")).rejects.toMatchObject<Partial<WorkspaceApiError>>({ kind: "invalid_response" });
  });

  it("refuse les faux succès de mutation visant une autre routine ou un mauvais état", async () => {
    const wrongRun = { ...run, automation_id: "automation-2" };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ ...detail, id: "automation-2", enabled: true }))
      .mockResolvedValueOnce(json({ ...detail, enabled: false }))
      .mockResolvedValueOnce(json(wrongRun, 201))
      .mockResolvedValueOnce(json({
        ...webhook,
        enabled: false,
        secret_configured: false,
        secret: webhookSecret,
      }, 201))
      .mockResolvedValueOnce(json({
        ...webhook,
        enabled: true,
        secret_configured: true,
        rotated_at: "2026-09-14T10:00:00Z",
        secret: "x".repeat(32),
      }, 201))
      .mockResolvedValueOnce(json({
        ...webhook,
        enabled: true,
        secret_configured: true,
        rotated_at: "2026-09-14T10:00:00Z",
      }));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.setEnabled("automation-1", true, "wrong-enable-1")).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.setEnabled("automation-1", true, "wrong-enable-2")).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.trigger("automation-1", "same-manual-key")).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.rotateWebhook("automation-1", webhookSecret, "same-rotate-key"))
      .rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.rotateWebhook("automation-1", webhookSecret, "same-rotate-key"))
      .rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.disableWebhook("automation-1", "wrong-disable")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("accepte une politique budgétaire matérialisée avec les defaults du contrat", async () => {
    const response = {
      ...budget,
      timezone: "Europe/Paris",
      daily_budget: {
        max_cost: null,
        currency: "EUR",
        max_tokens: null,
        max_tool_calls: 4,
      },
      provider_budgets: [{
        provider: "hermes",
        budget: {
          max_cost: null,
          currency: "EUR",
          max_tokens: 100,
          max_tool_calls: null,
        },
      }],
      max_concurrent_missions: 4,
      max_retries_per_mission: 3,
      max_spawned_agents_per_run: 4,
    };
    const fetcher = vi.fn().mockResolvedValueOnce(json(response));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.putBudgetPolicy("project/one", {
      daily_budget: { max_tool_calls: 4 },
      provider_budgets: [{ provider: " hermes ", budget: { max_tokens: 100 } }],
    })).resolves.toEqual(response);
  });

  it("refuse les 2xx qui ne prouvent pas toutes les postconditions demandées", async () => {
    const acknowledged = {
      ...alert,
      acknowledged_at: "2026-09-14T10:00:00Z",
      acknowledged_by_user_id: "user-1",
      acknowledgement_comment: "Traité",
    };
    const requestedBudget = {
      timezone: "Europe/Paris",
      daily_budget: { max_cost: 0, currency: "EUR", max_tokens: null, max_tool_calls: null },
      provider_budgets: [],
      max_concurrent_missions: 2,
      max_retries_per_mission: 1,
      max_spawned_agents_per_run: 3,
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ ...detail, name: "Autre routine" }, 201))
      .mockResolvedValueOnce(json({ ...detail, id: "" }, 201))
      .mockResolvedValueOnce(json({
        ...detail,
        schedule: { ...schedule, expression: "15 9 * * 1-5" },
      }))
      .mockResolvedValueOnce(json({ ...acknowledged, id: "alert-2" }))
      .mockResolvedValueOnce(json({ ...acknowledged, acknowledged_at: null }))
      .mockResolvedValueOnce(json({ ...preferences, enabled: true }))
      .mockResolvedValueOnce(json({ ...preferences, project_id: "project/two", enabled: false }))
      .mockResolvedValueOnce(json({
        ...budget,
        ...requestedBudget,
        max_retries_per_mission: 2,
      }))
      .mockResolvedValueOnce(json({
        ...budget,
        ...requestedBudget,
        project_id: "project/two",
      }));
    const client = new AutomationApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.createAutomation("project/one", {
      name: summary.name,
      schedule,
      mission_template: missionTemplate,
    }, "create-key")).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.createAutomation("project/one", {
      name: summary.name,
      schedule,
      mission_template: missionTemplate,
    }, "create-key-empty-id")).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.updateAutomation("automation-1", {
      schedule,
    }, "uncertain-update")).rejects.toMatchObject({
      kind: "invalid_response",
      message: expect.stringMatching(/résultat incertain.*recharge.*ne rejoue pas/iu),
    });
    await expect(client.acknowledgeAlert("alert-1", { comment: " Traité " }))
      .rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.acknowledgeAlert("alert-1", { comment: "Traité" }))
      .rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.putNotificationPreferences("project/one", {
      channel: "in_app",
      enabled: false,
    })).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.putNotificationPreferences("project/one", {
      channel: "in_app",
      enabled: false,
    })).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.putBudgetPolicy("project/one", requestedBudget))
      .rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client.putBudgetPolicy("project/one", requestedBudget))
      .rejects.toMatchObject({ kind: "invalid_response" });
  });
});
