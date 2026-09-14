import type {
  AlertAcknowledge,
  AlertSeverity,
  AlertSummary,
  AutomationCreate,
  AutomationCompletionStatus,
  AutomationDetail,
  AutomationRunOutcome,
  AutomationRunSummary,
  AutomationSchedule,
  AutomationSummary,
  AutomationUpdate,
  AutomationWebhookSecret,
  AutomationWebhookStatus,
  BudgetConsumptionSummary,
  BudgetConsumptionTotals,
  CalendarEntry,
  NotificationPreferences,
  NotificationPreferencesSummary,
  ProjectBudgetPolicyInput,
  ProjectBudgetPolicySummary,
} from "@acp/contracts";

import {
  WorkspaceApiError,
  WorkspaceHttpClient,
  hasString,
  isRecord,
  type Fetcher,
} from "./workspace-api";

const OUTCOMES = new Set<AutomationRunOutcome>([
  "launched",
  "skipped_catchup",
  "skipped_concurrency",
  "skipped_disabled",
  "failed",
]);
const COMPLETION_STATUSES = new Set<AutomationCompletionStatus>([
  "blocked",
  "succeeded",
  "failed",
  "cancelled",
  "interrupted",
]);
const SEVERITIES = new Set<AlertSeverity>(["info", "warning", "critical"]);

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function hasNonEmptyString(value: Record<string, unknown>, key: string): boolean {
  return typeof value[key] === "string" && Boolean((value[key] as string).trim());
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isAwareIsoInstant(value: unknown): value is string {
  return typeof value === "string"
    && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
    && Number.isFinite(Date.parse(value));
}

function isoOffsetMinutes(value: string): number | null {
  if (/Z$/i.test(value)) return 0;
  const match = /([+-])(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hours = Number(match[2]);
  const minutes = Number(match[3]);
  if (hours > 23 || minutes > 59) return null;
  return (match[1] === "-" ? -1 : 1) * (hours * 60 + minutes);
}

function isIanaTimezone(value: unknown): value is string {
  // Le serveur a déjà validé ce nom avec sa base IANA. Le navigateur peut
  // embarquer une tzdb plus ancienne (renommage ou changement réglementaire) :
  // il ne doit donc vérifier ici que la forme transportée.
  return typeof value === "string"
    && value === value.trim()
    && value.length >= 1
    && value.length <= 64
    && !/[\u0000-\u001f\u007f]/.test(value);
}

function nullableInteger(value: unknown): value is number | null {
  return value === null || (Number.isSafeInteger(value) && finiteNumber(value));
}

function isSchedule(value: unknown): value is AutomationSchedule {
  return isRecord(value)
    && (value.kind === "cron" || value.kind === "interval")
    && hasString(value, "expression")
    && isIanaTimezone(value.timezone);
}

function isAutonomy(value: unknown): boolean {
  return isRecord(value)
    && ["supervised", "bounded", "autonomous"].includes(String(value.mode))
    && Array.isArray(value.allowed_actions)
    && value.allowed_actions.every((item) => typeof item === "string")
    && Array.isArray(value.forbidden_actions)
    && value.forbidden_actions.every((item) => typeof item === "string")
    && Array.isArray(value.approval_required_actions)
    && value.approval_required_actions.every((item) => typeof item === "string");
}

function isBudget(value: unknown): boolean {
  return isRecord(value)
    && (value.max_cost === null || (finiteNumber(value.max_cost) && value.max_cost >= 0))
    && typeof value.currency === "string"
    && /^[A-Za-z]{3}$/.test(value.currency)
    && (value.max_tokens === null || (nullableInteger(value.max_tokens) && value.max_tokens >= 0))
    && (value.max_tool_calls === null || (nullableInteger(value.max_tool_calls) && value.max_tool_calls >= 0))
    && (value.max_cost !== null || value.max_tokens !== null || value.max_tool_calls !== null);
}

function isMissionTemplate(value: unknown): boolean {
  return isRecord(value)
    && hasString(value, "title")
    && hasString(value, "objective")
    && hasString(value, "expected_outcome")
    && Array.isArray(value.acceptance_criteria)
    && value.acceptance_criteria.every((item) => typeof item === "string")
    && isAutonomy(value.autonomy)
    && Array.isArray(value.resources)
    && value.resources.every((resource) => isRecord(resource)
      && hasString(resource, "kind")
      && hasString(resource, "identifier")
      && (resource.access === "read" || resource.access === "write")
      && hasString(resource, "description"))
    && isBudget(value.budget)
    && Number.isInteger(value.duration_seconds)
    && nullableString(value.team_id)
    && nullableString(value.agent_instance_id)
    && Number.isInteger(value.priority)
    && Array.isArray(value.required_capabilities)
    && value.required_capabilities.every((item) => typeof item === "string");
}

function isAutomationSummary(value: unknown): value is AutomationSummary {
  return isRecord(value)
    && hasNonEmptyString(value, "id")
    && hasNonEmptyString(value, "project_id")
    && hasNonEmptyString(value, "name")
    && hasString(value, "description")
    && isSchedule(value.schedule)
    && typeof value.enabled === "boolean"
    && (value.catchup_policy === "skip" || value.catchup_policy === "run_once")
    && Number.isInteger(value.max_concurrent_runs)
    && Number(value.max_concurrent_runs) >= 1
    && Number(value.max_concurrent_runs) <= 5
    && (value.next_run_at === null || isAwareIsoInstant(value.next_run_at))
    && isAwareIsoInstant(value.created_at);
}

function isAutomationRun(value: unknown): value is AutomationRunSummary {
  return isRecord(value)
    && hasNonEmptyString(value, "id")
    && hasNonEmptyString(value, "automation_id")
    && typeof value.fire_key === "string"
    && /^[0-9a-f]{32}$/.test(value.fire_key)
    && isAwareIsoInstant(value.scheduled_for)
    && isAwareIsoInstant(value.fired_at)
    && nullableString(value.task_id)
    && ["manual", "schedule", "webhook"].includes(String(value.trigger_kind))
    && OUTCOMES.has(value.outcome as AutomationRunOutcome)
    && (value.completion_status === null
      || COMPLETION_STATUSES.has(value.completion_status as AutomationCompletionStatus))
    && hasString(value, "detail");
}

function isAutomationDetail(value: unknown): value is AutomationDetail {
  if (!isAutomationSummary(value)) return false;
  const candidate = value as unknown as Record<string, unknown>;
  return isMissionTemplate(candidate.mission_template)
    && Array.isArray(candidate.recent_runs)
    && candidate.recent_runs.every(isAutomationRun);
}

function isCalendarEntry(value: unknown): value is CalendarEntry {
  if (!isRecord(value)
    || !isAwareIsoInstant(value.occurs_at_utc)
    || !isAwareIsoInstant(value.occurs_at_local)
    || !isIanaTimezone(value.timezone)
    || !Number.isInteger(value.utc_offset_minutes)
    || Number(value.utc_offset_minutes) < -1_440
    || Number(value.utc_offset_minutes) > 1_440
    || Date.parse(value.occurs_at_utc) !== Date.parse(value.occurs_at_local)
    || isoOffsetMinutes(value.occurs_at_local) !== value.utc_offset_minutes) return false;
  return hasNonEmptyString(value, "automation_id")
    && hasNonEmptyString(value, "automation_name")
    && (value.state === "planned" || value.state === "past")
    && nullableString(value.task_id)
    && (value.outcome === null || OUTCOMES.has(value.outcome as AutomationRunOutcome));
}

const WEBHOOK_STATUS_FIELDS = ["enabled", "secret_configured", "endpoint_path", "rotated_at"] as const;

function hasExactFields(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value);
  return actual.length === expected.length && expected.every((field) => field in value);
}

function hasWebhookStatusFields(value: unknown): value is AutomationWebhookStatus {
  return isRecord(value)
    && hasExactFields(value, WEBHOOK_STATUS_FIELDS)
    && typeof value.enabled === "boolean"
    && typeof value.secret_configured === "boolean"
    && value.enabled === value.secret_configured
    && hasNonEmptyString(value, "endpoint_path")
    && (value.rotated_at === null || isAwareIsoInstant(value.rotated_at));
}

function isWebhookStatus(value: unknown): value is AutomationWebhookStatus {
  return hasWebhookStatusFields(value);
}

function isWebhookSecret(value: unknown): value is AutomationWebhookSecret {
  if (!isRecord(value)
    || !hasExactFields(value, [...WEBHOOK_STATUS_FIELDS, "secret"])) return false;
  const status = { ...value };
  delete status.secret;
  if (!hasWebhookStatusFields(status)) return false;
  return typeof value.secret === "string"
    && /^[A-Za-z0-9_-]{43,200}$/.test(value.secret)
    && value.secret.length % 4 !== 1
    && Math.floor(value.secret.length * 6 / 8) >= 32;
}

function webhookEndpoint(automationId: string): string {
  return `/automations/${automationId}/webhook/trigger`;
}

function isExpectedAutomationDetail(
  value: unknown,
  automationId: string,
  enabled?: boolean,
): value is AutomationDetail {
  return isAutomationDetail(value)
    && value.id === automationId
    && (enabled === undefined || value.enabled === enabled)
    && value.recent_runs.every((run) => run.automation_id === automationId);
}

function cloneRequestedValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneRequestedValue);
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([, entry]) => entry !== undefined)
      .map(([key, entry]) => [key, cloneRequestedValue(entry)]),
  );
}

function normalizedUniqueStrings(value: unknown): unknown {
  if (!Array.isArray(value) || !value.every((entry) => typeof entry === "string")) return value;
  return [...new Set(value.map((entry) => entry.trim()))];
}

function canonicalMissionTemplateRequest(value: unknown): unknown {
  const cloned = cloneRequestedValue(value);
  if (!isRecord(cloned)) return cloned;
  cloned.resources ??= [];
  cloned.team_id ??= null;
  cloned.agent_instance_id ??= null;
  cloned.priority ??= 3;
  cloned.required_capabilities ??= [];
  cloned.acceptance_criteria = normalizedUniqueStrings(cloned.acceptance_criteria);
  cloned.required_capabilities = normalizedUniqueStrings(cloned.required_capabilities);

  if (isRecord(cloned.autonomy)) {
    cloned.autonomy.mode ??= "bounded";
    cloned.autonomy.allowed_actions ??= [];
    cloned.autonomy.forbidden_actions ??= [];
    cloned.autonomy.approval_required_actions ??= [];
  }
  if (Array.isArray(cloned.resources)) {
    cloned.resources = cloned.resources.map((resource) => {
      if (!isRecord(resource)) return resource;
      return { access: "read", description: "", ...resource };
    });
  }
  if (isRecord(cloned.budget)) {
    cloned.budget.max_cost ??= null;
    cloned.budget.currency ??= "EUR";
    cloned.budget.max_tokens ??= null;
    cloned.budget.max_tool_calls ??= null;
    if (typeof cloned.budget.currency === "string") {
      cloned.budget.currency = cloned.budget.currency.toUpperCase();
    }
  }
  return cloned;
}

function canonicalAutomationRequest(
  input: AutomationCreate | AutomationUpdate,
  creating: boolean,
): Record<string, unknown> {
  const cloned = cloneRequestedValue(input);
  if (!isRecord(cloned)) return {};
  if (typeof cloned.name === "string") cloned.name = cloned.name.trim();
  if (creating) {
    cloned.description ??= "";
    cloned.catchup_policy ??= "skip";
    cloned.max_concurrent_runs ??= 1;
  }
  if (isRecord(cloned.schedule)) cloned.schedule.timezone ??= "Europe/Paris";
  if ("mission_template" in cloned) {
    cloned.mission_template = canonicalMissionTemplateRequest(cloned.mission_template);
  }
  return cloned;
}

function requestedPostconditionMatches(actual: unknown, expected: unknown): boolean {
  if (Array.isArray(expected)) {
    return Array.isArray(actual)
      && actual.length === expected.length
      && expected.every((entry, index) => requestedPostconditionMatches(actual[index], entry));
  }
  if (isRecord(expected)) {
    return isRecord(actual)
      && Object.entries(expected).every(([key, entry]) =>
        key in actual && requestedPostconditionMatches(actual[key], entry));
  }
  return actual === expected;
}

function isExpectedAutomationMutation(
  value: unknown,
  automationId: string | null,
  input: AutomationCreate | AutomationUpdate,
  creating: boolean,
): value is AutomationDetail {
  return isAutomationDetail(value)
    && (automationId === null || value.id === automationId)
    && (!creating || value.enabled === false)
    && value.recent_runs.every((run) => run.automation_id === value.id)
    && requestedPostconditionMatches(value, canonicalAutomationRequest(input, creating));
}

function isExpectedAutomationRun(
  value: unknown,
  automationId: string,
): value is AutomationRunSummary {
  return isAutomationRun(value) && value.automation_id === automationId;
}

function isExpectedWebhookStatus(
  value: unknown,
  automationId: string,
  enabled?: boolean,
): value is AutomationWebhookStatus {
  return isWebhookStatus(value)
    && value.endpoint_path === webhookEndpoint(automationId)
    && (enabled === undefined || value.enabled === enabled);
}

function isExpectedWebhookSecret(
  value: unknown,
  automationId: string,
  secret: string,
): value is AutomationWebhookSecret {
  return isWebhookSecret(value)
    && value.enabled === true
    && value.secret_configured === true
    && value.endpoint_path === webhookEndpoint(automationId)
    && value.rotated_at !== null
    && value.secret === secret;
}

function isExpectedAcknowledgedAlert(
  value: unknown,
  alertId: string,
  input: AlertAcknowledge,
): value is AlertSummary {
  const expectedComment = typeof input.comment === "string" ? input.comment.trim() : "";
  return isAlert(value)
    && value.id === alertId
    && value.acknowledged_at !== null
    && typeof value.acknowledged_by_user_id === "string"
    && Boolean(value.acknowledged_by_user_id)
    && value.acknowledgement_comment === expectedComment;
}

function isExpectedNotificationPreferences(
  value: unknown,
  projectId: string,
  input: NotificationPreferences,
): value is NotificationPreferencesSummary {
  const requested = cloneRequestedValue(input);
  const expected = {
    channel: "in_app",
    enabled: true,
    minimum_severity: "warning",
    budget_alerts: true,
    automation_failures: true,
    storage_alerts: true,
    ...(isRecord(requested) ? requested : {}),
  };
  return isNotificationPreferences(value)
    && value.project_id === projectId
    && requestedPostconditionMatches(value, expected);
}

function canonicalBudgetPolicyRequest(input: ProjectBudgetPolicyInput): Record<string, unknown> {
  const cloned = cloneRequestedValue(input);
  const expected: Record<string, unknown> = {
    timezone: "Europe/Paris",
    daily_budget: null,
    provider_budgets: [],
    max_concurrent_missions: 4,
    max_retries_per_mission: 3,
    max_spawned_agents_per_run: 4,
    ...(isRecord(cloned) ? cloned : {}),
  };
  const normalizeBudget = (candidate: unknown): unknown => {
    if (!isRecord(candidate)) return candidate;
    candidate.max_cost ??= null;
    candidate.currency ??= "EUR";
    candidate.max_tokens ??= null;
    candidate.max_tool_calls ??= null;
    if (typeof candidate.currency === "string") candidate.currency = candidate.currency.toUpperCase();
    return candidate;
  };
  expected.daily_budget = normalizeBudget(expected.daily_budget);
  if (Array.isArray(expected.provider_budgets)) {
    expected.provider_budgets = expected.provider_budgets.map((entry) => {
      if (!isRecord(entry)) return entry;
      if (typeof entry.provider === "string") entry.provider = entry.provider.trim();
      entry.budget = normalizeBudget(entry.budget);
      return entry;
    });
  }
  return expected;
}

function isExpectedBudgetPolicy(
  value: unknown,
  projectId: string,
  input: ProjectBudgetPolicyInput,
): value is ProjectBudgetPolicySummary {
  return isProjectBudgetPolicy(value)
    && value.project_id === projectId
    && requestedPostconditionMatches(value, canonicalBudgetPolicyRequest(input));
}

function isAlert(value: unknown): value is AlertSummary {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "project_id")
    && hasString(value, "kind")
    && SEVERITIES.has(value.severity as AlertSeverity)
    && hasString(value, "title")
    && hasString(value, "detail")
    && nullableString(value.task_id)
    && nullableString(value.automation_id)
    && (value.acknowledged_at === null || isAwareIsoInstant(value.acknowledged_at))
    && nullableString(value.acknowledged_by_user_id)
    && hasString(value, "acknowledgement_comment")
    && isAwareIsoInstant(value.created_at);
}

function isNotificationPreferences(value: unknown): value is NotificationPreferencesSummary {
  return isRecord(value)
    && value.channel === "in_app"
    && typeof value.enabled === "boolean"
    && SEVERITIES.has(value.minimum_severity as AlertSeverity)
    && typeof value.budget_alerts === "boolean"
    && typeof value.automation_failures === "boolean"
    && typeof value.storage_alerts === "boolean"
    && hasString(value, "project_id")
    && isAwareIsoInstant(value.updated_at);
}

function isProjectBudgetPolicy(value: unknown): value is ProjectBudgetPolicySummary {
  if (!isRecord(value)
    || !isIanaTimezone(value.timezone)
    || !(value.daily_budget === null || isBudget(value.daily_budget))
    || !Array.isArray(value.provider_budgets)
    || !value.provider_budgets.every((entry) => isRecord(entry)
      && typeof entry.provider === "string"
      && Boolean(entry.provider.trim())
      && entry.provider.length <= 100
      && isBudget(entry.budget))
    || !Number.isInteger(value.max_concurrent_missions)
    || Number(value.max_concurrent_missions) < 1
    || Number(value.max_concurrent_missions) > 100
    || !Number.isInteger(value.max_retries_per_mission)
    || Number(value.max_retries_per_mission) < 0
    || Number(value.max_retries_per_mission) > 20
    || !Number.isInteger(value.max_spawned_agents_per_run)
    || Number(value.max_spawned_agents_per_run) < 1
    || Number(value.max_spawned_agents_per_run) > 32
    || !hasString(value, "project_id")
    || !isAwareIsoInstant(value.updated_at)) return false;
  const providers = value.provider_budgets.map((entry) =>
    (entry as Record<string, unknown>).provider as string
  );
  return new Set(providers.map((provider) => provider.trim().toLocaleLowerCase())).size === providers.length;
}

function isIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

type BudgetSaturatedMetric = BudgetConsumptionTotals["saturated_metrics"][number];
const BUDGET_SATURATED_METRICS: readonly BudgetSaturatedMetric[] = [
  "reports",
  "pending_reservations",
  "tokens_input",
  "tokens_output",
  "tool_calls",
];

function isBudgetSaturatedMetric(value: unknown): value is BudgetSaturatedMetric {
  return typeof value === "string"
    && BUDGET_SATURATED_METRICS.includes(value as BudgetSaturatedMetric);
}

function isTruthfulBudgetSaturation(
  totals: Record<string, unknown>,
  metric: unknown,
): boolean {
  return isBudgetSaturatedMetric(metric)
    && totals[metric] === Number.MAX_SAFE_INTEGER;
}

function isBudgetConsumptionTotals(value: unknown): value is BudgetConsumptionTotals {
  if (!isRecord(value)
    || !Number.isSafeInteger(value.reports)
    || Number(value.reports) < 0
    || !Number.isSafeInteger(value.pending_reservations)
    || Number(value.pending_reservations) < 0
    || !(value.cost === null || (finiteNumber(value.cost) && value.cost >= 0))
    || !(value.currency === null || (typeof value.currency === "string" && /^[A-Za-z]{3}$/.test(value.currency)))
    || !(value.tokens_input === null || (Number.isSafeInteger(value.tokens_input) && Number(value.tokens_input) >= 0))
    || !(value.tokens_output === null || (Number.isSafeInteger(value.tokens_output) && Number(value.tokens_output) >= 0))
    || !(value.tool_calls === null || (Number.isSafeInteger(value.tool_calls) && Number(value.tool_calls) >= 0))
    || !Array.isArray(value.saturated_metrics)
    || !value.saturated_metrics.every(isBudgetSaturatedMetric)
    || new Set(value.saturated_metrics).size !== value.saturated_metrics.length
    || !value.saturated_metrics.every((metric) => isTruthfulBudgetSaturation(value, metric))
    || typeof value.usage_reported !== "boolean"
    || typeof value.estimated !== "boolean") return false;
  if (value.cost !== null && value.currency === null) return false;
  return value.reports !== 0 || (
    value.pending_reservations === 0
    && value.cost === null
    && value.currency === null
    && value.tokens_input === null
    && value.tokens_output === null
    && value.tool_calls === null
    && value.saturated_metrics.length === 0
    && value.usage_reported === false
    && value.estimated === false
  );
}

function isBudgetConsumptionSummary(value: unknown): value is BudgetConsumptionSummary {
  return isRecord(value)
    && hasString(value, "project_id")
    && isIsoDate(value.accounting_day)
    && isIanaTimezone(value.timezone)
    && isBudgetConsumptionTotals(value.totals)
    && Array.isArray(value.missions)
    && value.missions.every((mission) => isRecord(mission)
      && hasString(mission, "mission_id")
      && Array.isArray(mission.task_run_ids)
      && mission.task_run_ids.every((runId) => typeof runId === "string")
      && isBudgetConsumptionTotals(mission.totals))
    && Array.isArray(value.providers)
    && value.providers.every((provider) => isRecord(provider)
      && hasString(provider, "provider")
      && String(provider.provider).length <= 100
      && isBudgetConsumptionTotals(provider.totals));
}

const arrayOf = <T>(validator: (value: unknown) => value is T) =>
  (value: unknown): value is T[] => Array.isArray(value) && value.every(validator);

function queryString(entries: Record<string, string | number | boolean | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(entries)) {
    if (value !== null && value !== undefined && value !== "") query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

export interface CalendarQuery {
  start: string;
  end: string;
  projectId?: string;
  automationId?: string;
  limit?: number;
}

export interface AlertQuery {
  projectId?: string;
  open?: boolean;
  severity?: AlertSeverity;
  kind?: string;
  limit?: number;
}

export class AutomationApiClient {
  readonly http: WorkspaceHttpClient;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
    http?: WorkspaceHttpClient;
  } = {}) {
    this.http = options.http ?? new WorkspaceHttpClient(options);
  }

  listAutomations(projectId?: string, enabled?: boolean, limit = 200): Promise<AutomationSummary[]> {
    return this.http.request(
      `/automations${queryString({ project_id: projectId, enabled, limit })}`,
      arrayOf(isAutomationSummary),
    );
  }

  createAutomation(projectId: string, input: AutomationCreate, idempotencyKey: string): Promise<AutomationDetail> {
    return this.http.request(
      `/projects/${encodeURIComponent(projectId)}/automations`,
      (value): value is AutomationDetail => isExpectedAutomationMutation(value, null, input, true)
        && value.project_id === projectId
        && value.recent_runs.every((run) => run.automation_id === value.id),
      { method: "POST", body: JSON.stringify(input), headers: { "Idempotency-Key": idempotencyKey } },
    );
  }

  getAutomation(automationId: string): Promise<AutomationDetail> {
    return this.http.request(
      `/automations/${encodeURIComponent(automationId)}`,
      (value): value is AutomationDetail => isExpectedAutomationDetail(value, automationId),
    );
  }

  async updateAutomation(
    automationId: string,
    input: AutomationUpdate,
    idempotencyKey: string,
  ): Promise<AutomationDetail> {
    try {
      return await this.http.request(`/automations/${encodeURIComponent(automationId)}`,
        (value): value is AutomationDetail => isExpectedAutomationMutation(
          value, automationId, input, false,
        ), {
        method: "PATCH",
        body: JSON.stringify(input),
        headers: { "Idempotency-Key": idempotencyKey },
      });
    } catch (error) {
      if (error instanceof WorkspaceApiError && error.kind === "invalid_response") {
        throw new WorkspaceApiError(
          "Résultat incertain : recharge la routine par GET avant toute nouvelle modification ; ne rejoue pas ce PATCH aveuglément.",
          "invalid_response",
        );
      }
      throw error;
    }
  }

  setEnabled(automationId: string, enabled: boolean, idempotencyKey: string): Promise<AutomationDetail> {
    return this.http.request(
      `/automations/${encodeURIComponent(automationId)}/${enabled ? "enable" : "disable"}`,
      (value): value is AutomationDetail => isExpectedAutomationDetail(value, automationId, enabled),
      { method: "POST", headers: { "Idempotency-Key": idempotencyKey } },
    );
  }

  trigger(automationId: string, idempotencyKey: string): Promise<AutomationRunSummary> {
    return this.http.request(
      `/automations/${encodeURIComponent(automationId)}/trigger`,
      (value): value is AutomationRunSummary => isExpectedAutomationRun(value, automationId),
      { method: "POST", headers: { "Idempotency-Key": idempotencyKey } },
    );
  }

  listRuns(automationId: string, limit = 50): Promise<AutomationRunSummary[]> {
    return this.http.request(
      `/automations/${encodeURIComponent(automationId)}/runs${queryString({ limit })}`,
      arrayOf((value): value is AutomationRunSummary => isExpectedAutomationRun(value, automationId)),
    );
  }

  calendar(query: CalendarQuery): Promise<CalendarEntry[]> {
    return this.http.request(`/automations/calendar${queryString({
      start: query.start,
      end: query.end,
      project_id: query.projectId,
      automation_id: query.automationId,
      limit: query.limit ?? 500,
    })}`, arrayOf(isCalendarEntry));
  }

  getWebhook(automationId: string): Promise<AutomationWebhookStatus> {
    return this.http.request(
      `/automations/${encodeURIComponent(automationId)}/webhook`,
      (value): value is AutomationWebhookStatus => isExpectedWebhookStatus(value, automationId),
    );
  }

  rotateWebhook(automationId: string, secret: string, idempotencyKey: string): Promise<AutomationWebhookSecret> {
    return this.http.request(`/automations/${encodeURIComponent(automationId)}/webhook`,
      (value): value is AutomationWebhookSecret => isExpectedWebhookSecret(value, automationId, secret), {
      method: "POST",
      body: JSON.stringify({ secret }),
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  disableWebhook(automationId: string, idempotencyKey: string): Promise<AutomationWebhookStatus> {
    return this.http.request(`/automations/${encodeURIComponent(automationId)}/webhook`,
      (value): value is AutomationWebhookStatus => isExpectedWebhookStatus(value, automationId, false), {
      method: "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  listAlerts(query: AlertQuery = {}): Promise<AlertSummary[]> {
    return this.http.request(`/alerts${queryString({
      project_id: query.projectId,
      open: query.open,
      severity: query.severity,
      kind: query.kind,
      limit: query.limit ?? 100,
    })}`, arrayOf(isAlert));
  }

  acknowledgeAlert(alertId: string, input: AlertAcknowledge = {}): Promise<AlertSummary> {
    return this.http.request(
      `/alerts/${encodeURIComponent(alertId)}/acknowledge`,
      (value): value is AlertSummary => isExpectedAcknowledgedAlert(value, alertId, input), {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  getNotificationPreferences(projectId: string): Promise<NotificationPreferencesSummary> {
    return this.http.request(
      `/projects/${encodeURIComponent(projectId)}/notification-preferences`,
      isNotificationPreferences,
    );
  }

  putNotificationPreferences(
    projectId: string,
    input: NotificationPreferences,
  ): Promise<NotificationPreferencesSummary> {
    return this.http.request(
      `/projects/${encodeURIComponent(projectId)}/notification-preferences`,
      (value): value is NotificationPreferencesSummary =>
        isExpectedNotificationPreferences(value, projectId, input),
      { method: "PUT", body: JSON.stringify(input) },
    );
  }

  getBudgetPolicy(projectId: string): Promise<ProjectBudgetPolicySummary> {
    return this.http.request(
      `/projects/${encodeURIComponent(projectId)}/budget-policy`,
      isProjectBudgetPolicy,
    );
  }

  getBudgetUsage(projectId: string, day?: string): Promise<BudgetConsumptionSummary> {
    return this.http.request(
      `/projects/${encodeURIComponent(projectId)}/budget-usage${queryString({ day })}`,
      isBudgetConsumptionSummary,
    );
  }

  putBudgetPolicy(projectId: string, input: ProjectBudgetPolicyInput): Promise<ProjectBudgetPolicySummary> {
    return this.http.request(
      `/projects/${encodeURIComponent(projectId)}/budget-policy`,
      (value): value is ProjectBudgetPolicySummary =>
        isExpectedBudgetPolicy(value, projectId, input),
      { method: "PUT", body: JSON.stringify(input) },
    );
  }
}

export const automationValidators = {
  summary: isAutomationSummary,
  detail: isAutomationDetail,
  run: isAutomationRun,
  calendarEntry: isCalendarEntry,
  alert: isAlert,
  notificationPreferences: isNotificationPreferences,
  projectBudgetPolicy: isProjectBudgetPolicy,
  budgetConsumptionSummary: isBudgetConsumptionSummary,
};
