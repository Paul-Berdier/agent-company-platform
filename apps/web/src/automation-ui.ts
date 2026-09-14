/** Interface des automatisations du Lot F : aucune donnée simulée, aucun canal fictif. */

import type {
  AlertSeverity,
  AlertSummary,
  AutomationCompletionStatus,
  AutomationCreate,
  AutomationDetail,
  AutomationMissionBudget,
  AutomationMissionTemplateInput,
  AutomationRunOutcome,
  AutomationRunSummary,
  AutomationScheduleInput,
  AutomationSummary,
  AutomationWebhookSecret,
  AutomationWebhookStatus,
  BudgetConsumptionSummary,
  BudgetConsumptionTotals,
  CalendarEntry,
  NotificationPreferencesSummary,
  Project,
  ProjectBudgetPolicy,
  ProjectBudgetPolicySummary,
} from "@acp/contracts";

import "./automation.css";
import { AutomationApiClient } from "./automation-api";
import {
  el,
  errorMessage,
  labeledField,
  normalizeApiError,
  sectionHeader,
  statePanel,
  statusChip,
} from "./ui-primitives";
import { WorkspaceApiClient, WorkspaceApiError, WorkspaceHttpClient } from "./workspace-api";

type Phase = "idle" | "loading" | "ready" | "error";
type AutomationView = "routines" | "calendar" | "alerts" | "settings";
export type FrequencyKind = "daily" | "weekly" | "interval" | "cron";

const AUTOMATION_PAGE_LIMIT = 200;
const ALERT_PAGE_LIMIT = 100;
const CALENDAR_PAGE_LIMIT = 500;

export interface ScheduleDraft {
  frequency: FrequencyKind;
  timezone: string;
  time: string;
  weekday: string;
  intervalValue: string;
  intervalUnit: "minutes" | "hours" | "days";
  cron: string;
}

interface CreateDraft extends ScheduleDraft {
  name: string;
  description: string;
  templateId: string;
  objective: string;
  expectedOutcome: string;
  acceptanceCriteria: string;
  resource: string;
  readOnly: boolean;
  missionMaxCost: string;
  missionCurrency: string;
  missionMaxTokens: string;
  missionMaxToolCalls: string;
  missionDurationSeconds: string;
  missionPriority: string;
  catchupPolicy: "skip" | "run_once";
  maxConcurrentRuns: string;
}

interface Notice {
  tone: "success" | "warning" | "error";
  message: string;
}

interface AutomationState {
  phase: Phase;
  projectPhase: Phase;
  error: WorkspaceApiError | null;
  automationsError: WorkspaceApiError | null;
  calendarError: WorkspaceApiError | null;
  alertsError: WorkspaceApiError | null;
  preferencesError: WorkspaceApiError | null;
  budgetError: WorkspaceApiError | null;
  budgetUsageError: WorkspaceApiError | null;
  projects: Project[];
  projectId: string;
  automations: AutomationSummary[];
  calendar: CalendarEntry[];
  alerts: AlertSummary[];
  preferences: NotificationPreferencesSummary | null;
  budget: ProjectBudgetPolicySummary | null;
  budgetUsage: BudgetConsumptionSummary | null;
  view: AutomationView;
  createOpen: boolean;
  selectedId: string | null;
  detailPhase: Phase;
  detail: AutomationDetail | null;
  runs: AutomationRunSummary[];
  webhook: AutomationWebhookStatus | null;
  oneTimeSecret: string | null;
  oneTimeSecretPending: boolean;
  pendingCreate: { signature: string; key: string } | null;
  pendingWebhookRotations: Record<string, { key: string; secret: string }>;
  pendingManualTriggerKeys: Record<string, string>;
  pendingMutationKeys: Record<string, { signature: string; key: string }>;
  armedWebhookAction: "rotate" | "disable" | null;
  detailError: WorkspaceApiError | null;
  busy: string | null;
  notice: Notice | null;
}

export interface AutomationTemplate {
  id: string;
  label: string;
  description: string;
  objective: string;
  expectedOutcome: string;
  acceptanceCriteria: string[];
  resourceKind: "repository" | "file" | "reference";
  writes: boolean;
}

export const AUTOMATION_TEMPLATES: readonly AutomationTemplate[] = [
  {
    id: "repo-analysis",
    label: "Analyser un dépôt",
    description: "Inspection en lecture seule avec constats sourcés.",
    objective: "Analyser l’état du dépôt et identifier les risques ou améliorations vérifiables.",
    expectedOutcome: "Un rapport priorisé, relié aux fichiers et aux preuves observées.",
    acceptanceCriteria: ["Le dépôt reste inchangé", "Chaque constat cite une preuve vérifiable"],
    resourceKind: "repository",
    writes: false,
  },
  {
    id: "fix-test",
    label: "Corriger et tester",
    description: "Correction bornée puis exécution des tests pertinents.",
    objective: "Diagnostiquer le problème décrit, appliquer une correction minimale et la tester.",
    expectedOutcome: "Une correction limitée au périmètre et des résultats de tests explicites.",
    acceptanceCriteria: ["La cause est expliquée", "Les tests ciblés passent", "Aucune régression connue n’est masquée"],
    resourceKind: "repository",
    writes: true,
  },
  {
    id: "prepare-pr",
    label: "Préparer une pull request",
    description: "Branche, vérifications et résumé, sans fusion implicite.",
    objective: "Préparer une pull request révisable pour le changement demandé.",
    expectedOutcome: "Une branche testée et une proposition de pull request documentée.",
    acceptanceCriteria: ["Le diff reste centré sur la demande", "Les vérifications sont consignées", "La fusion n’est pas effectuée implicitement"],
    resourceKind: "repository",
    writes: true,
  },
  {
    id: "sourced-report",
    label: "Produire un rapport sourcé",
    description: "Synthèse fondée uniquement sur les ressources autorisées.",
    objective: "Étudier la question fournie et produire une synthèse dont chaque affirmation importante est sourcée.",
    expectedOutcome: "Un rapport structuré, daté, avec sources et limites explicites.",
    acceptanceCriteria: ["Les sources sont accessibles", "Les faits et inférences sont distingués"],
    resourceKind: "reference",
    writes: false,
  },
  {
    id: "data-file",
    label: "Analyser un fichier de données",
    description: "Contrôles de qualité et résultats reproductibles.",
    objective: "Analyser le fichier, contrôler sa qualité et répondre aux questions définies.",
    expectedOutcome: "Une analyse reproductible avec anomalies, méthode et résultats.",
    acceptanceCriteria: ["Le fichier source n’est pas modifié", "Les valeurs manquantes sont signalées", "La méthode est reproductible"],
    resourceKind: "file",
    writes: false,
  },
  {
    id: "watch-update",
    label: "Surveiller et mettre à jour",
    description: "Vérification périodique d’une ressource réellement accessible.",
    objective: "Vérifier si la ressource autorisée a changé et préparer une mise à jour uniquement si nécessaire.",
    expectedOutcome: "Un constat horodaté ; une mise à jour bornée seulement lorsqu’un changement réel est observé.",
    acceptanceCriteria: ["L’absence de changement est rapportée comme telle", "Aucun connecteur non configuré n’est supposé disponible"],
    resourceKind: "reference",
    writes: true,
  },
] as const;

function initialDraft(): CreateDraft {
  const template = AUTOMATION_TEMPLATES[0];
  return {
    name: "",
    description: "",
    templateId: template.id,
    objective: template.objective,
    expectedOutcome: template.expectedOutcome,
    acceptanceCriteria: template.acceptanceCriteria.join("\n"),
    resource: "",
    readOnly: true,
    missionMaxCost: "",
    missionCurrency: "EUR",
    missionMaxTokens: "",
    missionMaxToolCalls: "50",
    missionDurationSeconds: "3600",
    missionPriority: "3",
    catchupPolicy: "skip",
    maxConcurrentRuns: "1",
    frequency: "daily",
    timezone: "Europe/Paris",
    time: "09:00",
    weekday: "1",
    intervalValue: "60",
    intervalUnit: "minutes",
    cron: "0 9 * * 1-5",
  };
}

const draft = initialDraft();

function initialState(): AutomationState {
  return {
    phase: "idle",
    projectPhase: "idle",
    error: null,
    automationsError: null,
    calendarError: null,
    alertsError: null,
    preferencesError: null,
    budgetError: null,
    budgetUsageError: null,
    projects: [],
    projectId: "",
    automations: [],
    calendar: [],
    alerts: [],
    preferences: null,
    budget: null,
    budgetUsage: null,
    view: "routines",
    createOpen: false,
    selectedId: null,
    detailPhase: "idle",
    detail: null,
    runs: [],
    webhook: null,
    oneTimeSecret: null,
    oneTimeSecretPending: false,
    pendingCreate: null,
    pendingWebhookRotations: {},
    pendingManualTriggerKeys: {},
    pendingMutationKeys: {},
    armedWebhookAction: null,
    detailError: null,
    busy: null,
    notice: null,
  };
}

const state = initialState();
let mount: HTMLElement | null = null;
let http = new WorkspaceHttpClient();
let api = new AutomationApiClient({ http });
let workspaceApi = new WorkspaceApiClient({ http });
let loadSequence = 0;
let detailSequence = 0;
let mutationSequence = 0;
let requestedFocusKey: string | null = null;

interface MutationContext {
  projectId: string;
  selectedId: string | null;
  isCurrent: () => boolean;
}

function beginMutationContext(): MutationContext {
  const sequence = ++mutationSequence;
  const projectId = state.projectId;
  const selectedId = state.selectedId;
  return {
    projectId,
    selectedId,
    isCurrent: () => sequence === mutationSequence
      && projectId === state.projectId
      && selectedId === state.selectedId
      && mount !== null,
  };
}

function invalidateMutations(): void {
  ++mutationSequence;
  state.busy = null;
}

function focusable<T extends HTMLElement>(node: T, key: string): T {
  node.dataset.focusKey = key;
  return node;
}

function clearDetailState(): void {
  invalidateMutations();
  ++detailSequence;
  state.selectedId = null;
  state.detailPhase = "idle";
  state.detail = null;
  state.runs = [];
  state.webhook = null;
  state.oneTimeSecret = null;
  state.oneTimeSecretPending = false;
  state.armedWebhookAction = null;
  state.detailError = null;
}

function useHttp(client?: WorkspaceHttpClient): void {
  const next = client ?? http;
  if (next === http) return;
  http = next;
  api = new AutomationApiClient({ http });
  workspaceApi = new WorkspaceApiClient({ http });
}

export function buildScheduleInput(value: ScheduleDraft): AutomationScheduleInput {
  const timezone = value.timezone.trim() || "Europe/Paris";
  if (value.frequency === "interval") {
    const amount = Number(value.intervalValue);
    if (!Number.isInteger(amount) || amount < 1) throw new Error("L’intervalle doit être un nombre entier positif.");
    const multiplier = value.intervalUnit === "minutes" ? 60 : value.intervalUnit === "hours" ? 3_600 : 86_400;
    const seconds = amount * multiplier;
    if (seconds < 60 || seconds > 31_536_000) throw new Error("L’intervalle doit être compris entre une minute et un an.");
    return { kind: "interval", expression: String(seconds), timezone };
  }
  if (value.frequency === "cron") {
    const expression = value.cron.trim();
    if (!expression) throw new Error("L’expression cron avancée est requise.");
    return { kind: "cron", expression, timezone };
  }
  const match = /^(\d{2}):(\d{2})$/.exec(value.time);
  if (!match) throw new Error("Choisis une heure locale valide.");
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) throw new Error("Choisis une heure locale valide.");
  const day = value.frequency === "weekly" ? value.weekday : "*";
  return { kind: "cron", expression: `${minute} ${hour} * * ${day}`, timezone };
}

const WEEKDAYS: Record<string, string> = {
  "0": "dimanche", "1": "lundi", "2": "mardi", "3": "mercredi",
  "4": "jeudi", "5": "vendredi", "6": "samedi",
};

export function scheduleLabel(schedule: AutomationScheduleInput): string {
  if (schedule.kind === "interval") {
    const seconds = Number(schedule.expression);
    if (Number.isFinite(seconds) && seconds % 86_400 === 0) return `Tous les ${seconds / 86_400} jour(s)`;
    if (Number.isFinite(seconds) && seconds % 3_600 === 0) return `Toutes les ${seconds / 3_600} heure(s)`;
    if (Number.isFinite(seconds) && seconds % 60 === 0) return `Toutes les ${seconds / 60} minute(s)`;
    return `Toutes les ${schedule.expression} seconde(s)`;
  }
  const daily = /^(\d{1,2}) (\d{1,2}) \* \* (\*|[0-6])$/.exec(schedule.expression);
  if (daily) {
    const time = `${daily[2].padStart(2, "0")}:${daily[1].padStart(2, "0")}`;
    return daily[3] === "*" ? `Chaque jour à ${time}` : `Chaque ${WEEKDAYS[daily[3]]} à ${time}`;
  }
  return `Cron ${schedule.expression}`;
}

export function formatBudgetLimit(value: number | null, unit: string): string {
  if (value === null) return "Inconnu / non limité";
  return `${value.toLocaleString("fr-FR", { maximumFractionDigits: 6 })} ${unit}`.trim();
}

export function buildBudgetLimits(
  maxCost: string,
  currency: string,
  maxTokens: string,
  maxToolCalls: string,
): AutomationMissionBudget | null {
  const cost = nullableNumber(maxCost);
  const tokens = nullableWholeNumber(maxTokens);
  const tools = nullableWholeNumber(maxToolCalls);
  if (cost === null && tokens === null && tools === null) return null;
  const normalizedCurrency = currency.trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(normalizedCurrency)) {
    throw new Error("La devise doit être un code ISO de trois lettres, par exemple EUR.");
  }
  return {
    max_cost: cost,
    currency: normalizedCurrency,
    max_tokens: tokens,
    max_tool_calls: tools,
  };
}

function offsetLabel(minutes: number): string {
  const sign = minutes >= 0 ? "+" : "−";
  const absolute = Math.abs(minutes);
  return `UTC${sign}${String(Math.floor(absolute / 60)).padStart(2, "0")}:${String(absolute % 60).padStart(2, "0")}`;
}

function localDateLabel(value: string): string {
  const [date, rawTime = ""] = value.split("T");
  const [year, month, day] = date.split("-");
  const time = rawTime.slice(0, 5);
  return year && month && day ? `${day}/${month}/${year} ${time}` : value;
}

function utcDateLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "UTC inconnu";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date) + " UTC";
}

function outcomeLabel(outcome: AutomationRunOutcome): string {
  return {
    launched: "Mission lancée",
    skipped_catchup: "Ignorée · rattrapage",
    skipped_concurrency: "Ignorée · concurrence",
    skipped_disabled: "Ignorée · pause",
    failed: "Échec",
  }[outcome];
}

function completionLabel(status: AutomationCompletionStatus): string {
  return {
    blocked: "Mission bloquée",
    succeeded: "Mission réussie",
    failed: "Mission échouée",
    cancelled: "Mission annulée",
    interrupted: "Mission interrompue",
  }[status];
}

function completionTone(status: AutomationCompletionStatus): string {
  return status === "succeeded"
    ? "active"
    : status === "cancelled"
      ? "waiting"
      : "failed";
}

function outcomeTone(outcome: AutomationRunOutcome): string {
  return outcome === "launched" ? "active" : outcome === "failed" ? "failed" : "waiting";
}

function errorPanel(error: WorkspaceApiError, retry: () => void): HTMLElement {
  const tone = error.kind === "offline" ? "offline" : error.kind === "forbidden" ? "forbidden" : "error";
  return statePanel(tone, "Chargement impossible", errorMessage(error), retry);
}

function idempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? "web-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

function mutationKey(scope: string, signature: string): string {
  const pending = state.pendingMutationKeys[scope];
  if (pending?.signature === signature) return pending.key;
  const key = idempotencyKey();
  state.pendingMutationKeys[scope] = { signature, key };
  return key;
}

function settleMutationKey(scope: string, error?: unknown): void {
  if (error === undefined) {
    delete state.pendingMutationKeys[scope];
    return;
  }
  const failure = normalizeApiError(error, "La mutation a échoué.");
  if (!mutationResultIsUncertain(failure)) delete state.pendingMutationKeys[scope];
}

function mutationResultIsUncertain(error: WorkspaceApiError): boolean {
  return error.kind === "offline"
    || error.kind === "invalid_response"
    || error.status === 408
    || (error.status !== null && error.status >= 500);
}

function newWebhookSecret(): string {
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error("La génération cryptographique du secret n’est pas disponible dans ce navigateur.");
  }
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(32));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function triggerManually(item: AutomationSummary): Promise<void> {
  const context = beginMutationContext();
  const operationKey = state.pendingManualTriggerKeys[item.id] ?? idempotencyKey();
  state.pendingManualTriggerKeys[item.id] = operationKey;
  state.busy = "trigger:" + item.id;
  state.notice = null;
  render();
  try {
    const run = await api.trigger(item.id, operationKey);
    delete state.pendingManualTriggerKeys[item.id];
    if (!context.isCurrent()) return;
    if (state.selectedId === item.id) {
      state.runs = [run, ...state.runs.filter((candidate) => candidate.id !== run.id)];
    }
    await loadProjectResources();
    if (!context.isCurrent()) return;
    const terminal = run.completion_status;
    state.notice = {
      tone: terminal === "succeeded"
        ? "success"
        : terminal && terminal !== "cancelled"
          ? "error"
          : run.outcome === "launched"
            ? "success"
            : "warning",
      message: "Déclenchement enregistré : "
        + (terminal ? completionLabel(terminal) : outcomeLabel(run.outcome))
        + ".",
    };
  } catch (error) {
    if (!context.isCurrent()) return;
    const failure = normalizeApiError(error, "Le déclenchement manuel a échoué.");
    const uncertain = mutationResultIsUncertain(failure);
    if (!uncertain) delete state.pendingManualTriggerKeys[item.id];
    state.notice = {
      tone: "error",
      message: uncertain
        ? errorMessage(failure) + " Résultat incertain : la prochaine tentative réutilisera la clé " + operationKey + " pour éviter un doublon."
        : errorMessage(failure),
    };
  } finally {
    if (context.isCurrent()) {
      state.busy = null;
      render();
    }
  }
}

function selectedProject(): Project | null {
  return state.projects.find((project) => project.id === state.projectId) ?? null;
}

function selectedTemplate(): AutomationTemplate {
  return AUTOMATION_TEMPLATES.find((template) => template.id === draft.templateId) ?? AUTOMATION_TEMPLATES[0];
}

function setTemplate(templateId: string): void {
  const template = AUTOMATION_TEMPLATES.find((candidate) => candidate.id === templateId);
  if (!template) return;
  draft.templateId = template.id;
  draft.objective = template.objective;
  draft.expectedOutcome = template.expectedOutcome;
  draft.acceptanceCriteria = template.acceptanceCriteria.join("\n");
  draft.readOnly = !template.writes;
}

function dateRange(): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now);
  start.setUTCDate(start.getUTCDate() - 30);
  const end = new Date(now);
  end.setUTCDate(end.getUTCDate() + 90);
  return { start: start.toISOString(), end: end.toISOString() };
}

async function loadProjectResources(): Promise<void> {
  const sequence = ++loadSequence;
  state.projectPhase = "loading";
  state.automationsError = null;
  state.calendarError = null;
  state.alertsError = null;
  state.preferencesError = null;
  state.budgetError = null;
  state.budgetUsageError = null;
  state.notice = null;
  // Un changement de projet ne doit jamais repeindre les données du projet précédent
  // pendant qu’une requête échoue ou reste en vol.
  state.automations = [];
  state.calendar = [];
  state.alerts = [];
  state.preferences = null;
  state.budget = null;
  state.budgetUsage = null;
  render();
  const projectId = state.projectId;
  if (!projectId) {
    state.projectPhase = "ready";
    render();
    return;
  }
  const range = dateRange();
  const results = await Promise.allSettled([
    api.listAutomations(projectId, undefined, AUTOMATION_PAGE_LIMIT),
    api.calendar({ ...range, projectId, limit: CALENDAR_PAGE_LIMIT }),
    api.listAlerts({ projectId, open: true, limit: ALERT_PAGE_LIMIT }),
    api.getNotificationPreferences(projectId),
    api.getBudgetPolicy(projectId),
    api.getBudgetUsage(projectId),
  ]);
  if (sequence !== loadSequence || projectId !== state.projectId) return;
  const [automations, calendar, alerts, preferences, budget, budgetUsage] = results;
  if (automations.status === "fulfilled") state.automations = automations.value;
  else state.automationsError = normalizeApiError(automations.reason, "Les automatisations sont indisponibles.");
  if (calendar.status === "fulfilled") state.calendar = calendar.value;
  else state.calendarError = normalizeApiError(calendar.reason, "Le calendrier est indisponible.");
  if (alerts.status === "fulfilled") state.alerts = alerts.value;
  else state.alertsError = normalizeApiError(alerts.reason, "Les alertes sont indisponibles.");
  if (preferences.status === "fulfilled") state.preferences = preferences.value;
  else state.preferencesError = normalizeApiError(preferences.reason, "Les préférences sont indisponibles.");
  if (budget.status === "fulfilled") state.budget = budget.value;
  else state.budgetError = normalizeApiError(budget.reason, "La politique budgétaire est indisponible.");
  if (budgetUsage.status === "fulfilled") state.budgetUsage = budgetUsage.value;
  else state.budgetUsageError = normalizeApiError(budgetUsage.reason, "La consommation budgétaire est indisponible.");
  state.projectPhase = "ready";
  render();
}

async function loadInitial(): Promise<void> {
  const sequence = ++loadSequence;
  state.phase = "loading";
  state.error = null;
  render();
  try {
    const overview = await workspaceApi.fetchOverview();
    if (sequence !== loadSequence) return;
    state.projects = overview.projects.filter((project) => project.status === "active");
    if (!state.projects.some((project) => project.id === state.projectId)) {
      state.projectId = state.projects[0]?.id ?? "";
    }
    state.phase = "ready";
    await loadProjectResources();
  } catch (error) {
    if (sequence !== loadSequence) return;
    state.phase = "error";
    state.error = normalizeApiError(error, "L’espace Automatisations est indisponible.");
    render();
  }
}

async function loadDetail(automationId: string): Promise<void> {
  invalidateMutations();
  const sequence = ++detailSequence;
  state.selectedId = automationId;
  requestedFocusKey = `detail-close:${automationId}`;
  state.detailPhase = "loading";
  state.detailError = null;
  state.detail = null;
  state.runs = [];
  state.webhook = null;
  state.oneTimeSecret = null;
  state.oneTimeSecretPending = false;
  render();
  const result = await Promise.allSettled([
    api.getAutomation(automationId),
    api.listRuns(automationId),
    api.getWebhook(automationId),
  ]);
  if (sequence !== detailSequence || state.selectedId !== automationId) return;
  const failure = result.find((entry) => entry.status === "rejected") as PromiseRejectedResult | undefined;
  if (failure) {
    state.detailPhase = "error";
    state.detailError = normalizeApiError(failure.reason, "Le détail de la routine est indisponible.");
  } else {
    state.detail = (result[0] as PromiseFulfilledResult<AutomationDetail>).value;
    state.runs = (result[1] as PromiseFulfilledResult<AutomationRunSummary[]>).value;
    state.webhook = (result[2] as PromiseFulfilledResult<AutomationWebhookStatus>).value;
    state.detailPhase = "ready";
  }
  render();
}

async function act(
  key: string,
  action: (context: MutationContext) => Promise<void>,
  fallback: string,
): Promise<void> {
  const context = beginMutationContext();
  state.busy = key;
  state.notice = null;
  render();
  try {
    await action(context);
  } catch (error) {
    if (context.isCurrent() && state.notice === null) {
      state.notice = { tone: "error", message: errorMessage(normalizeApiError(error, fallback)) };
    }
  } finally {
    if (context.isCurrent()) {
      state.busy = null;
      render();
    }
  }
}

function noticeNode(): HTMLElement | null {
  if (!state.notice) return null;
  const node = el("div", "automation-notice", state.notice.message);
  node.dataset.tone = state.notice.tone;
  node.setAttribute("role", "status");
  node.setAttribute("aria-live", "polite");
  return node;
}

function projectToolbar(): HTMLElement {
  const toolbar = el("div", "automation-toolbar");
  const select = focusable(el("select", "form-control automation-project") as HTMLSelectElement, "project-select");
  select.disabled = state.busy !== null;
  select.name = "automationProject";
  for (const project of state.projects) {
    const option = el("option", "", project.name) as HTMLOptionElement;
    option.value = project.id;
    option.selected = project.id === state.projectId;
    select.append(option);
  }
  select.addEventListener("change", () => {
    invalidateMutations();
    state.projectId = select.value;
    clearDetailState();
    void loadProjectResources();
  });
  const field = labeledField("Projet", select, "Les routines restent strictement limitées à ce projet.");
  const refresh = focusable(el("button", "button button-secondary", "Actualiser") as HTMLButtonElement, "project-refresh");
  refresh.type = "button";
  refresh.addEventListener("click", () => void loadProjectResources());
  toolbar.append(field, refresh);
  return toolbar;
}

const VIEWS: readonly { id: AutomationView; label: string }[] = [
  { id: "routines", label: "Routines" },
  { id: "calendar", label: "Calendrier" },
  { id: "alerts", label: "Alertes" },
  { id: "settings", label: "Limites & notifications" },
];

function viewTabs(): HTMLElement {
  const tabs = el("div", "automation-tabs");
  tabs.setAttribute("role", "group");
  tabs.setAttribute("aria-label", "Sections des automatisations");
  for (const view of VIEWS) {
    const count = view.id === "alerts" && state.alerts.length ? ` (${state.alerts.length})` : "";
    const button = focusable(el("button", "automation-tab", `${view.label}${count}`) as HTMLButtonElement, `view:${view.id}`);
    button.type = "button";
    button.setAttribute("aria-pressed", String(state.view === view.id));
    button.addEventListener("click", () => { state.view = view.id; render(); });
    tabs.append(button);
  }
  return tabs;
}

function metrics(): HTMLElement {
  const grid = el("div", "metric-grid automation-metrics");
  const active = state.automations.filter((item) => item.enabled).length;
  const metric = (label: string, value: string, hint: string, tone = ""): HTMLElement => {
    const card = el("article", "metric-card");
    if (tone) card.dataset.tone = tone;
    card.append(el("p", "metric-label", label), el("p", "metric-value", value), el("p", "metric-hint", hint));
    return card;
  };
  const daily = state.budget?.daily_budget;
  const budget = daily
    ? [daily.max_cost !== null ? `${daily.max_cost} ${daily.currency}` : null,
       daily.max_tokens !== null ? `${daily.max_tokens.toLocaleString("fr-FR")} jetons` : null,
       daily.max_tool_calls !== null ? `${daily.max_tool_calls} outils` : null].filter(Boolean).join(" · ")
    : "";
  grid.append(
    state.automationsError
      ? metric("Routines actives", "Indisponible", "L’API des routines n’a pas répondu ; aucun zéro n’est déduit.", "failed")
      : metric("Routines actives chargées", state.automations.length === AUTOMATION_PAGE_LIMIT ? `Au moins ${active}` : String(active), state.automations.length === AUTOMATION_PAGE_LIMIT ? `Vue limitée aux ${AUTOMATION_PAGE_LIMIT} premières routines` : `${state.automations.length - active} en pause parmi les routines chargées`, active ? "accent" : ""),
    state.alertsError
      ? metric("Alertes ouvertes", "Indisponible", "L’API des alertes n’a pas répondu ; aucune absence n’est supposée.", "failed")
      : metric("Alertes ouvertes chargées", state.alerts.length === ALERT_PAGE_LIMIT ? `Au moins ${ALERT_PAGE_LIMIT}` : String(state.alerts.length), state.alerts.length === ALERT_PAGE_LIMIT ? `Vue limitée aux ${ALERT_PAGE_LIMIT} premières alertes` : "Causes à examiner", state.alerts.length ? "warning" : "success"),
    state.budgetError
      ? metric("Budget quotidien", "Indisponible", "La politique budgétaire n’a pas pu être lue.", "failed")
      : metric("Budget quotidien", budget || "Inconnu", budget ? `Fuseau ${state.budget?.timezone}` : "Aucune limite mesurée n’est inventée"),
  );
  return grid;
}

function bindDraft(input: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, key: keyof CreateDraft): void {
  input.addEventListener("input", () => {
    (draft as unknown as Record<string, string | boolean>)[key] = input instanceof HTMLInputElement && input.type === "checkbox"
      ? input.checked
      : input.value;
  });
}

function input(value: string, name: keyof CreateDraft, type = "text"): HTMLInputElement {
  const control = el("input", "form-control") as HTMLInputElement;
  control.type = type;
  control.value = value;
  control.name = String(name);
  bindDraft(control, name);
  return control;
}

function selectControl<T extends string>(
  value: T,
  name: keyof CreateDraft,
  options: readonly { value: T; label: string }[],
): HTMLSelectElement {
  const control = el("select", "form-control") as HTMLSelectElement;
  control.name = String(name);
  for (const item of options) {
    const option = el("option", "", item.label) as HTMLOptionElement;
    option.value = item.value;
    option.selected = item.value === value;
    control.append(option);
  }
  bindDraft(control, name);
  return control;
}

function buildMissionTemplate(): AutomationMissionTemplateInput {
  const template = selectedTemplate();
  if (!draft.name.trim() || !draft.objective.trim() || !draft.expectedOutcome.trim()) {
    throw new Error("Le nom, l’objectif et le résultat attendu sont obligatoires.");
  }
  const criteria = draft.acceptanceCriteria.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!criteria.length) throw new Error("Ajoute au moins un critère d’acceptation.");
  const resource = draft.resource.trim();
  const budget = buildBudgetLimits(
    draft.missionMaxCost,
    draft.missionCurrency,
    draft.missionMaxTokens,
    draft.missionMaxToolCalls,
  );
  if (!budget) throw new Error("Le budget de mission doit définir au moins une limite.");
  const durationSeconds = Number(draft.missionDurationSeconds);
  const priority = Number(draft.missionPriority);
  if (!Number.isSafeInteger(durationSeconds) || durationSeconds < 1 || durationSeconds > 31_536_000) {
    throw new Error("La durée maximale doit être un entier compris entre 1 seconde et un an.");
  }
  if (!Number.isSafeInteger(priority) || priority < 1 || priority > 5) {
    throw new Error("La priorité doit être un entier compris entre 1 et 5.");
  }
  return {
    title: draft.name.trim(),
    objective: draft.objective.trim(),
    expected_outcome: draft.expectedOutcome.trim(),
    acceptance_criteria: criteria,
    autonomy: draft.readOnly
      ? { mode: "supervised", allowed_actions: ["read"], forbidden_actions: ["write", "external_effect"], approval_required_actions: [] }
      : { mode: "bounded", allowed_actions: ["read", "write_workspace"], forbidden_actions: [], approval_required_actions: ["external_effect", "sensitive_action"] },
    resources: resource ? [{
      kind: template.resourceKind,
      identifier: resource,
      access: draft.readOnly ? "read" : "write",
      description: "Ressource principale autorisée par la routine",
    }] : [],
    budget,
    duration_seconds: durationSeconds,
    priority,
    required_capabilities: [],
  };
}

function createForm(): HTMLElement {
  const wrapper = el("section", "automation-create");
  wrapper.append(sectionHeader("Assistant de création", "Une routine naît en pause. Tu choisis explicitement quand l’activer."));
  const form = el("form", "automation-form") as HTMLFormElement;
  const name = input(draft.name, "name");
  name.required = true;
  name.maxLength = 200;
  const description = el("textarea", "form-control form-textarea compact") as HTMLTextAreaElement;
  description.value = draft.description;
  description.maxLength = 10_000;
  bindDraft(description, "description");
  const template = selectControl(draft.templateId, "templateId", AUTOMATION_TEMPLATES.map((item) => ({ value: item.id, label: item.label })));
  template.addEventListener("change", () => { setTemplate(template.value); render(); });
  const objective = el("textarea", "form-control form-textarea") as HTMLTextAreaElement;
  objective.value = draft.objective;
  objective.required = true;
  bindDraft(objective, "objective");
  const expected = el("textarea", "form-control form-textarea compact") as HTMLTextAreaElement;
  expected.value = draft.expectedOutcome;
  expected.required = true;
  bindDraft(expected, "expectedOutcome");
  const criteria = el("textarea", "form-control form-textarea") as HTMLTextAreaElement;
  criteria.value = draft.acceptanceCriteria;
  criteria.required = true;
  bindDraft(criteria, "acceptanceCriteria");
  const resource = input(draft.resource, "resource");
  resource.placeholder = "Chemin, dépôt, fichier ou référence déjà accessible";
  const readOnly = input("", "readOnly", "checkbox");
  readOnly.checked = draft.readOnly;
  const missionMaxCost = input(draft.missionMaxCost, "missionMaxCost", "number");
  missionMaxCost.min = "0";
  missionMaxCost.step = "0.000001";
  const missionCurrency = input(draft.missionCurrency, "missionCurrency");
  missionCurrency.maxLength = 3;
  missionCurrency.required = true;
  const missionMaxTokens = input(draft.missionMaxTokens, "missionMaxTokens", "number");
  missionMaxTokens.min = "0";
  missionMaxTokens.step = "1";
  const missionMaxToolCalls = input(draft.missionMaxToolCalls, "missionMaxToolCalls", "number");
  missionMaxToolCalls.min = "0";
  missionMaxToolCalls.step = "1";
  const missionDuration = input(draft.missionDurationSeconds, "missionDurationSeconds", "number");
  missionDuration.min = "1";
  missionDuration.max = "31536000";
  missionDuration.step = "1";
  missionDuration.required = true;
  const missionPriority = input(draft.missionPriority, "missionPriority", "number");
  missionPriority.min = "1";
  missionPriority.max = "5";
  missionPriority.step = "1";
  missionPriority.required = true;

  const frequency = selectControl<FrequencyKind>(draft.frequency, "frequency", [
    { value: "daily", label: "Chaque jour" },
    { value: "weekly", label: "Chaque semaine" },
    { value: "interval", label: "À intervalle fixe" },
    { value: "cron", label: "Cron avancé" },
  ]);
  frequency.addEventListener("change", () => render());
  const scheduleFields = el("div", "form-split automation-schedule-fields");
  if (draft.frequency === "daily" || draft.frequency === "weekly") {
    const at = input(draft.time, "time", "time");
    at.required = true;
    scheduleFields.append(labeledField("Heure locale", at));
    if (draft.frequency === "weekly") {
      scheduleFields.append(labeledField("Jour", selectControl(draft.weekday, "weekday", [
        { value: "1", label: "Lundi" }, { value: "2", label: "Mardi" },
        { value: "3", label: "Mercredi" }, { value: "4", label: "Jeudi" },
        { value: "5", label: "Vendredi" }, { value: "6", label: "Samedi" },
        { value: "0", label: "Dimanche" },
      ])));
    }
  } else if (draft.frequency === "interval") {
    const every = input(draft.intervalValue, "intervalValue", "number");
    every.min = "1";
    every.required = true;
    scheduleFields.append(
      labeledField("Toutes les", every),
      labeledField("Unité", selectControl(draft.intervalUnit, "intervalUnit", [
        { value: "minutes", label: "Minutes" }, { value: "hours", label: "Heures" }, { value: "days", label: "Jours" },
      ])),
    );
  } else {
    const cron = input(draft.cron, "cron");
    cron.required = true;
    cron.placeholder = "0 9 * * 1-5";
    scheduleFields.append(labeledField("Expression cron (5 champs)", cron, "Minute, heure, jour du mois, mois, jour de semaine."));
  }
  const timezone = input(draft.timezone, "timezone");
  timezone.required = true;
  const catchup = selectControl(draft.catchupPolicy, "catchupPolicy", [
    { value: "skip", label: "Ignorer les occurrences manquées" },
    { value: "run_once", label: "Rattraper une seule fois" },
  ]);
  const concurrency = input(draft.maxConcurrentRuns, "maxConcurrentRuns", "number");
  concurrency.min = "1";
  concurrency.max = "5";

  const templateCopy = el("p", "automation-template-copy", selectedTemplate().description);
  const readOnlyField = el("label", "automation-check");
  readOnlyField.append(readOnly, el("span", "", "Essai en lecture seule (recommandé avant activation)"));
  const feedback = el("div", "form-feedback");
  feedback.setAttribute("role", "status");
  const buttons = el("div", "automation-form-actions");
  const cancel = focusable(el("button", "button button-secondary", "Annuler") as HTMLButtonElement, "create-cancel");
  cancel.type = "button";
  cancel.disabled = state.busy !== null;
  cancel.addEventListener("click", () => {
    state.createOpen = false;
    requestedFocusKey = "create-toggle";
    render();
  });
  const submit = focusable(el("button", "button button-primary", state.busy === "create" ? "Création…" : "Créer en pause") as HTMLButtonElement, "create-submit");
  submit.type = "submit";
  submit.disabled = state.busy !== null;
  buttons.append(cancel, submit);
  form.append(
    labeledField("Nom de la routine", name),
    labeledField("Description", description),
    labeledField("Modèle de départ", template),
    templateCopy,
    labeledField("Objectif", objective),
    labeledField("Résultat attendu", expected),
    labeledField("Critères d’acceptation · un par ligne", criteria),
    labeledField("Ressource principale", resource, "Laisse vide si la mission n’a besoin d’aucune ressource supplémentaire."),
    readOnlyField,
    el("h3", "automation-subtitle", "Limites de chaque mission créée"),
    labeledField("Coût maximal", missionMaxCost, "Vide signifie inconnu ; zéro interdit toute dépense."),
    labeledField("Devise", missionCurrency, "Code ISO sur trois lettres."),
    labeledField("Jetons maximaux", missionMaxTokens, "Vide signifie inconnu ; zéro est une limite réelle."),
    labeledField("Appels d’outil maximaux", missionMaxToolCalls, "Au moins une limite de coût, jetons ou outils est requise."),
    labeledField("Durée maximale (secondes)", missionDuration),
    labeledField("Priorité (1 à 5)", missionPriority),
    labeledField("Fréquence", frequency),
    scheduleFields,
    labeledField("Fuseau IANA", timezone, "Les changements d’heure sont calculés par le serveur dans ce fuseau."),
    labeledField("Après une absence", catchup),
    labeledField("Exécutions simultanées maximales", concurrency),
    feedback,
    buttons,
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    let payload: AutomationCreate;
    try {
      const maximum = Number(draft.maxConcurrentRuns);
      if (!Number.isInteger(maximum) || maximum < 1 || maximum > 5) {
        throw new Error("La concurrence doit être un entier compris entre 1 et 5.");
      }
      payload = {
        name: draft.name.trim(),
        description: draft.description.trim(),
        schedule: buildScheduleInput(draft),
        mission_template: buildMissionTemplate(),
        catchup_policy: draft.catchupPolicy,
        max_concurrent_runs: maximum,
      };
    } catch (error) {
      feedback.dataset.tone = "error";
      feedback.textContent = error instanceof Error ? error.message : "Le formulaire est invalide.";
      return;
    }
    const signature = state.projectId + "\n" + JSON.stringify(payload);
    const createRequest = state.pendingCreate?.signature === signature
      ? state.pendingCreate
      : { signature, key: idempotencyKey() };
    state.pendingCreate = createRequest;
    void act("create", async (context) => {
      let created: AutomationDetail;
      try {
        created = await api.createAutomation(context.projectId, payload, createRequest.key);
      } catch (error) {
        if (context.isCurrent()) {
          const failure = normalizeApiError(error, "La création de la routine a échoué.");
          if (mutationResultIsUncertain(failure)) {
            state.notice = {
              tone: "error",
              message: errorMessage(failure)
                + " Résultat incertain : renvoie exactement le même formulaire pour réutiliser la clé "
                + createRequest.key + " sans créer de doublon.",
            };
          } else {
            state.pendingCreate = null;
          }
        }
        throw error;
      }
      if (!context.isCurrent()) return;
      state.pendingCreate = null;
      Object.assign(draft, initialDraft());
      state.createOpen = false;
      requestedFocusKey = "create-toggle";
      await loadProjectResources();
      if (!context.isCurrent()) return;
      state.notice = { tone: "success", message: `« ${created.name} » a été créée en pause. Vérifie-la puis active-la explicitement.` };
    }, "La création de la routine a échoué.");
  });
  wrapper.append(form);
  return wrapper;
}

function routineCard(item: AutomationSummary): HTMLElement {
  const card = el("article", "automation-card");
  const heading = el("div", "automation-card-heading");
  const copy = el("div");
  copy.append(el("h3", "list-item-title", item.name));
  if (item.description) copy.append(el("p", "list-item-meta", item.description));
  heading.append(copy, statusChip(item.enabled ? "Active" : "En pause", item.enabled ? "active" : "waiting"));
  const facts = el("dl", "automation-facts");
  const fact = (term: string, value: string): void => {
    facts.append(el("dt", "", term), el("dd", "", value));
  };
  fact("Fréquence", `${scheduleLabel(item.schedule)} · ${item.schedule.timezone}`);
  fact("Prochaine exécution", item.next_run_at ? utcDateLabel(item.next_run_at) : item.enabled ? "Non calculable" : "Aucune tant que la routine est en pause");
  fact("Rattrapage", item.catchup_policy === "run_once" ? "Une occurrence au redémarrage" : "Occurrences manquées ignorées");
  fact("Concurrence", `${item.max_concurrent_runs} maximum`);
  const actions = el("div", "automation-card-actions");
  const toggle = focusable(el("button", "button button-secondary", item.enabled ? "Mettre en pause" : "Activer") as HTMLButtonElement, `toggle:${item.id}`);
  toggle.type = "button";
  toggle.setAttribute("aria-label", `${item.enabled ? "Mettre en pause" : "Activer"} la routine ${item.name}`);
  toggle.disabled = state.busy !== null;
  toggle.addEventListener("click", () => void act(`toggle:${item.id}`, async (context) => {
    const target = !item.enabled;
    const scope = `toggle:${item.id}`;
    const key = mutationKey(scope, JSON.stringify({ enabled: target }));
    let updated: AutomationDetail;
    try {
      updated = await api.setEnabled(item.id, target, key);
    } catch (error) {
      settleMutationKey(scope, error);
      throw error;
    }
    settleMutationKey(scope);
    if (!context.isCurrent()) return;
    state.automations = state.automations.map((candidate) => candidate.id === item.id ? updated : candidate);
    await loadProjectResources();
    if (!context.isCurrent()) return;
    state.notice = { tone: "success", message: updated.enabled ? "Routine activée ; sa prochaine occurrence est affichée." : "Routine mise en pause ; aucune occurrence planifiée ne sera lancée." };
  }, "Le changement d’état a échoué."));
  const trigger = focusable(el("button", "button button-secondary", "Déclencher maintenant") as HTMLButtonElement, `trigger:${item.id}`);
  trigger.type = "button";
  trigger.setAttribute("aria-label", `Déclencher maintenant la routine ${item.name}`);
  trigger.disabled = state.busy !== null;
  trigger.title = item.enabled ? "Créer une occurrence manuelle" : "Le déclenchement manuel reste autorisé pendant la pause";
  trigger.addEventListener("click", () => void triggerManually(item));
  const details = focusable(el("button", "button button-secondary", "Historique et webhook") as HTMLButtonElement, `details:${item.id}`);
  details.type = "button";
  details.disabled = state.busy !== null;
  details.setAttribute("aria-label", `Ouvrir l’historique et le webhook de la routine ${item.name}`);
  details.addEventListener("click", () => void loadDetail(item.id));
  actions.append(toggle, trigger, details);
  card.append(heading, facts, actions);
  return card;
}

function webhookPanel(): HTMLElement {
  const section = el("section", "automation-webhook");
  section.append(el("h4", "automation-subtitle", "Webhook authentifié"));
  if (!state.webhook) {
    section.append(el("p", "list-item-meta", "État non chargé."));
    return section;
  }
  section.append(
    el("p", "list-item-meta", state.webhook.enabled
      ? `Actif sur ${state.webhook.endpoint_path}. Le secret n’est jamais relu.`
      : "Désactivé. Aucun appel externe ne peut déclencher cette routine."),
  );
  if (state.oneTimeSecret) {
    const warning = el("div", "automation-secret");
    warning.append(
      el("strong", "", state.oneTimeSecretPending
        ? "Secret de récupération · résultat encore incertain"
        : "Secret affiché une seule fois"),
      el("code", "", state.oneTimeSecret),
      el("p", "", state.oneTimeSecretPending
        ? "Conserve-le et rejoue la rotation avec la clé indiquée : ce secret peut déjà être actif si le serveur a validé la première requête."
        : "Conserve-le maintenant dans le coffre de l’émetteur. Il disparaîtra en quittant ce détail."),
    );
    section.append(warning);
  }
  const actions = el("div", "automation-card-actions");
  const rotateLabel = state.armedWebhookAction === "rotate"
    ? state.webhook.secret_configured
      ? "Confirmer la rotation du secret"
      : "Confirmer l’activation du webhook"
    : state.webhook.secret_configured ? "Faire tourner le secret" : "Activer le webhook";
  const rotate = focusable(el("button", "button button-secondary", rotateLabel) as HTMLButtonElement, "webhook:rotate");
  rotate.type = "button";
  rotate.disabled = state.busy !== null;
  rotate.addEventListener("click", () => {
    if (state.armedWebhookAction !== "rotate") {
      const alreadyConfigured = Boolean(state.webhook?.secret_configured);
      state.armedWebhookAction = "rotate";
      state.notice = {
        tone: "warning",
        message: alreadyConfigured
          ? "La rotation révoquera immédiatement le secret courant. Active « Confirmer la rotation du secret » pour continuer."
          : "L’activation créera un secret persistant qui autorise des déclenchements externes. Active « Confirmer l’activation du webhook » pour continuer.",
      };
      requestedFocusKey = "webhook:rotate";
      render();
      return;
    }
    state.armedWebhookAction = null;
    void act("webhook:rotate", async (context) => {
      const automationId = context.selectedId!;
      const request = state.pendingWebhookRotations[automationId]
        ?? { key: idempotencyKey(), secret: newWebhookSecret() };
      state.pendingWebhookRotations[automationId] = request;
      let result: AutomationWebhookSecret;
      try {
        result = await api.rotateWebhook(automationId, request.secret, request.key);
      } catch (error) {
        if (context.isCurrent()) {
          const failure = normalizeApiError(error, "Le webhook n’a pas pu être activé ou renouvelé.");
          if (mutationResultIsUncertain(failure)) {
            state.oneTimeSecret = request.secret;
            state.oneTimeSecretPending = true;
            state.notice = {
              tone: "error",
              message: errorMessage(failure)
                + " Résultat incertain : conserve le secret affiché et confirme à nouveau avec la même clé "
                + request.key + ".",
            };
          } else {
            delete state.pendingWebhookRotations[automationId];
          }
        }
        throw error;
      }
      // Une réponse contenant un secret arrivée après fermeture/navigation ne doit
      // pas rester dans l’état mémoire ni réapparaître lors d’un prochain rendu.
      if (!context.isCurrent()) return;
      delete state.pendingWebhookRotations[automationId];
      state.webhook = result;
      state.oneTimeSecret = result.secret;
      state.oneTimeSecretPending = false;
      state.notice = { tone: "warning", message: "Le webhook est actif. Le nouveau secret n’est affiché que dans le panneau de détail." };
    }, "Le webhook n’a pas pu être activé ou renouvelé.");
  });
  actions.append(rotate);
  if (state.webhook.enabled || state.webhook.secret_configured) {
    const disableLabel = state.armedWebhookAction === "disable" ? "Confirmer la désactivation" : "Désactiver le webhook";
    const disable = focusable(el("button", "button button-secondary", disableLabel) as HTMLButtonElement, "webhook:disable");
    disable.type = "button";
    disable.disabled = state.busy !== null;
    disable.addEventListener("click", () => {
      if (state.armedWebhookAction !== "disable") {
        state.armedWebhookAction = "disable";
        state.notice = { tone: "warning", message: "La désactivation révoquera le secret et interrompra l’émetteur. Active « Confirmer la désactivation » pour continuer." };
        requestedFocusKey = "webhook:disable";
        render();
        return;
      }
      state.armedWebhookAction = null;
      void act("webhook:disable", async (context) => {
        const automationId = context.selectedId!;
        const scope = `webhook:disable:${automationId}`;
        const key = mutationKey(scope, "disable");
        let result: AutomationWebhookStatus;
        try {
          result = await api.disableWebhook(automationId, key);
        } catch (error) {
          settleMutationKey(scope, error);
          throw error;
        }
        settleMutationKey(scope);
        if (!context.isCurrent()) return;
        state.webhook = result;
        state.oneTimeSecret = null;
        state.oneTimeSecretPending = false;
        delete state.pendingWebhookRotations[context.selectedId!];
        state.notice = { tone: "success", message: "Webhook désactivé et secret révoqué." };
      }, "Le webhook n’a pas pu être désactivé.");
    });
    actions.append(disable);
  }
  section.append(actions);
  return section;
}

function editAutomationPanel(detail: AutomationDetail): HTMLElement {
  const disclosure = el("details", "automation-edit") as HTMLDetailsElement;
  disclosure.append(el("summary", "automation-edit-summary", "Modifier les réglages"));
  const form = el("form", "automation-edit-form") as HTMLFormElement;
  const name = el("input", "form-control") as HTMLInputElement;
  name.value = detail.name;
  name.required = true;
  name.maxLength = 200;
  const description = el("textarea", "form-control form-textarea compact") as HTMLTextAreaElement;
  description.value = detail.description;
  description.maxLength = 10_000;
  const catchup = el("select", "form-control") as HTMLSelectElement;
  for (const item of [
    { value: "skip", label: "Ignorer les occurrences manquées" },
    { value: "run_once", label: "Rattraper une seule fois" },
  ] as const) {
    const option = el("option", "", item.label) as HTMLOptionElement;
    option.value = item.value;
    option.selected = item.value === detail.catchup_policy;
    catchup.append(option);
  }
  const concurrency = el("input", "form-control") as HTMLInputElement;
  concurrency.type = "number";
  concurrency.min = "1";
  concurrency.max = "5";
  concurrency.value = String(detail.max_concurrent_runs);
  const feedback = el("div", "form-feedback");
  feedback.setAttribute("role", "status");
  const save = focusable(el("button", "button button-primary", "Enregistrer les réglages") as HTMLButtonElement, "automation-save");
  save.type = "submit";
  save.disabled = state.busy !== null;
  form.append(
    labeledField("Nom", name),
    labeledField("Description", description),
    labeledField("Après une absence", catchup),
    labeledField("Exécutions simultanées maximales", concurrency),
    el("p", "form-hint", `Fréquence actuelle : ${scheduleLabel(detail.schedule)} · ${detail.schedule.timezone}. Une modification de calendrier passe par l’API avancée tant qu’un assistant de migration n’est pas disponible.`),
    feedback,
    save,
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const maximum = Number(concurrency.value);
    if (!Number.isInteger(maximum) || maximum < 1 || maximum > 5) {
      feedback.dataset.tone = "error";
      feedback.textContent = "La concurrence doit être un entier compris entre 1 et 5.";
      return;
    }
    const update = {
      name: name.value.trim(),
      description: description.value.trim(),
      catchup_policy: catchup.value as "skip" | "run_once",
      max_concurrent_runs: maximum,
    };
    void act("automation:update", async (context) => {
      const scope = `update:${detail.id}`;
      const signature = JSON.stringify(update);
      const key = mutationKey(scope, signature);
      let updated: AutomationDetail;
      try {
        updated = await api.updateAutomation(detail.id, update, key);
      } catch (error) {
        settleMutationKey(scope, error);
        throw error;
      }
      settleMutationKey(scope);
      if (!context.isCurrent()) return;
      state.detail = updated;
      state.automations = state.automations.map((item) => item.id === updated.id ? updated : item);
      state.notice = { tone: "success", message: "Réglages de la routine enregistrés." };
    }, "Les réglages n’ont pas pu être enregistrés.");
  });
  disclosure.append(form);
  return disclosure;
}

function detailPanel(): HTMLElement | null {
  if (!state.selectedId) return null;
  const automationId = state.selectedId;
  const panel = el("aside", "automation-detail");
  const close = focusable(el("button", "button button-secondary automation-detail-close", "Fermer le détail") as HTMLButtonElement, `detail-close:${automationId}`);
  close.type = "button";
  close.disabled = state.busy !== null;
  close.addEventListener("click", () => {
    clearDetailState();
    requestedFocusKey = `details:${automationId}`;
    render();
  });
  panel.append(close);
  if (state.detailPhase === "loading") {
    panel.append(statePanel("loading", "Détail en cours", "Chargement de la mission, de l’historique et du webhook."));
    return panel;
  }
  if (state.detailPhase === "error" && state.detailError) {
    panel.append(errorPanel(state.detailError, () => void loadDetail(state.selectedId!)));
    return panel;
  }
  if (!state.detail) return panel;
  panel.append(
    el("p", "workspace-eyebrow", "Routine"),
    el("h3", "automation-detail-title", state.detail.name),
    el("p", "list-item-meta", state.detail.mission_template.objective),
    editAutomationPanel(state.detail),
  );
  const runs = el("section", "automation-runs");
  runs.append(el("h4", "automation-subtitle", "Historique réel"));
  if (!state.runs.length) runs.append(el("p", "list-item-meta", "Aucun déclenchement enregistré."));
  for (const run of state.runs) {
    const row = el("article", "automation-run");
    const title = el("div", "automation-run-title");
    const label = run.completion_status === null
      ? outcomeLabel(run.outcome)
      : completionLabel(run.completion_status);
    const tone = run.completion_status === null
      ? outcomeTone(run.outcome)
      : completionTone(run.completion_status);
    title.append(statusChip(label, tone), el("time", "", utcDateLabel(run.fired_at)));
    row.append(title, el("p", "list-item-meta", `${run.trigger_kind === "manual" ? "Manuel" : run.trigger_kind === "webhook" ? "Webhook" : "Calendrier"} · ${run.detail || "Aucun détail"}`));
    if (run.task_id) row.append(el("code", "automation-task-id", `Mission ${run.task_id}`));
    runs.append(row);
  }
  panel.append(runs, webhookPanel());
  return panel;
}

function routinesView(): HTMLElement {
  const section = el("section", "content-section automation-routines");
  const header = sectionHeader("Routines du projet", "Pause, reprise, déclenchement manuel et historique reposent sur l’API réelle.");
  const create = focusable(el("button", "button button-primary", state.createOpen ? "Fermer l’assistant" : "Nouvelle routine") as HTMLButtonElement, "create-toggle");
  create.type = "button";
  create.addEventListener("click", () => { state.createOpen = !state.createOpen; render(); });
  header.append(create);
  section.append(header);
  if (state.createOpen) section.append(createForm());
  if (state.automationsError) section.append(errorPanel(state.automationsError, () => void loadProjectResources()));
  else if (!state.automations.length) section.append(statePanel("empty", "Aucune routine", "Crée une première routine : elle restera en pause jusqu’à ton activation explicite."));
  else {
    const layout = el("div", "automation-list-layout");
    if (state.automations.length === AUTOMATION_PAGE_LIMIT) {
      const warning = el("p", "automation-usage-unknown", `Liste limitée aux ${AUTOMATION_PAGE_LIMIT} premières routines ; les métriques ne prétendent pas couvrir les suivantes.`);
      warning.setAttribute("role", "note");
      section.append(warning);
    }
    const list = el("div", "automation-list");
    for (const item of state.automations) list.append(routineCard(item));
    layout.append(list);
    const detail = detailPanel();
    if (detail) layout.append(detail);
    section.append(layout);
  }
  return section;
}

function calendarView(): HTMLElement {
  const section = el("section", "content-section");
  section.append(sectionHeader("Calendrier sur 120 jours", "Les heures locales proviennent du fuseau de la routine ; UTC reste visible pour lever toute ambiguïté."));
  if (state.calendarError) {
    section.append(errorPanel(state.calendarError, () => void loadProjectResources()));
    return section;
  }
  if (!state.calendar.length) {
    section.append(statePanel("empty", "Aucune occurrence", "Aucune occurrence passée ou future n’est disponible sur cette période."));
    return section;
  }
  if (state.calendar.length === CALENDAR_PAGE_LIMIT) {
    const warning = el("p", "automation-usage-unknown", `Calendrier limité aux ${CALENDAR_PAGE_LIMIT} premières occurrences ; la période peut être tronquée.`);
    warning.setAttribute("role", "note");
    section.append(warning);
  }
  const offsets = new Set(state.calendar.map((entry) => `${entry.timezone}:${entry.utc_offset_minutes}`));
  if (offsets.size > new Set(state.calendar.map((entry) => entry.timezone)).size) {
    const dst = el("p", "automation-dst-note", "Changement d’heure visible : le décalage UTC varie dans cette période. Les heures locales affichées restent l’autorité utilisateur.");
    dst.setAttribute("role", "note");
    section.append(dst);
  }
  const list = el("ol", "automation-calendar");
  for (const entry of state.calendar) {
    const row = el("li", "automation-calendar-entry");
    const when = el("div", "automation-calendar-when");
    when.append(
      el("strong", "", localDateLabel(entry.occurs_at_local)),
      el("span", "", `${entry.timezone} · ${offsetLabel(entry.utc_offset_minutes)}`),
      el("span", "", utcDateLabel(entry.occurs_at_utc)),
    );
    const what = el("div", "automation-calendar-what");
    what.append(el("strong", "", entry.automation_name));
    what.append(entry.outcome
      ? statusChip(outcomeLabel(entry.outcome), outcomeTone(entry.outcome))
      : statusChip(entry.state === "planned" ? "Prévue" : "Passée", entry.state === "planned" ? "queued" : "waiting"));
    row.append(when, what);
    list.append(row);
  }
  section.append(list);
  return section;
}

function alertCard(alert: AlertSummary): HTMLElement {
  const card = el("article", "automation-alert");
  const title = el("div", "automation-card-heading");
  const severity = { info: "Information", warning: "Attention", critical: "Critique" }[alert.severity];
  title.append(el("h3", "list-item-title", alert.title), statusChip(severity, alert.severity === "critical" ? "failed" : alert.severity === "warning" ? "waiting" : "active"));
  const comment = el("input", "form-control") as HTMLInputElement;
  comment.maxLength = 500;
  comment.placeholder = "Commentaire d’acquittement (facultatif)";
  const acknowledge = focusable(el("button", "button button-secondary", "Acquitter") as HTMLButtonElement, `ack:${alert.id}`);
  acknowledge.type = "button";
  acknowledge.setAttribute("aria-label", `Acquitter l’alerte ${alert.title}`);
  acknowledge.disabled = state.busy !== null;
  acknowledge.addEventListener("click", () => void act(`ack:${alert.id}`, async (context) => {
    await api.acknowledgeAlert(alert.id, { comment: comment.value.trim() });
    if (!context.isCurrent()) return;
    state.alerts = state.alerts.filter((candidate) => candidate.id !== alert.id);
    requestedFocusKey = "view:alerts";
    state.notice = { tone: "success", message: "Alerte acquittée. La cause reste traçable dans l’historique." };
  }, "L’alerte n’a pas pu être acquittée."));
  const actions = el("div", "automation-alert-actions");
  actions.append(labeledField(`Commenter l’alerte « ${alert.title} »`, comment), acknowledge);
  card.append(title, el("p", "automation-alert-kind", alert.kind), el("p", "list-item-meta", alert.detail), actions);
  return card;
}

function alertsView(): HTMLElement {
  const section = el("section", "content-section");
  section.append(sectionHeader("Alertes ouvertes", "Une alerte est une cause durable dans l’atelier, pas la promesse d’un courriel ou d’un webhook sortant."));
  if (state.alertsError) section.append(errorPanel(state.alertsError, () => void loadProjectResources()));
  else if (!state.alerts.length) section.append(statePanel("empty", "Aucune alerte ouverte", "Aucune cause active ne demande d’acquittement pour ce projet."));
  else {
    if (state.alerts.length === ALERT_PAGE_LIMIT) {
      const warning = el("p", "automation-usage-unknown", `Liste limitée aux ${ALERT_PAGE_LIMIT} premières alertes ouvertes.`);
      warning.setAttribute("role", "note");
      section.append(warning);
    }
    const list = el("div", "automation-alert-list");
    for (const alert of state.alerts) list.append(alertCard(alert));
    section.append(list);
  }
  return section;
}

function nullableNumber(value: string): number | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const number = Number(normalized);
  if (!Number.isFinite(number) || number < 0) throw new Error("Une limite doit être vide ou être un nombre positif, zéro compris.");
  return number;
}

function nullableWholeNumber(value: string): number | null {
  const number = nullableNumber(value);
  if (number !== null && !Number.isSafeInteger(number)) {
    throw new Error("Les limites de jetons et d’appels d’outil doivent être des entiers représentables sans perte.");
  }
  return number;
}

function budgetConsumptionFacts(totals: BudgetConsumptionTotals): string[] {
  const cost = totals.cost === null
    ? "Coût : inconnu"
    : `Coût : ${totals.cost.toLocaleString("fr-FR", { maximumFractionDigits: 6 })} ${totals.currency ?? "devise inconnue"}`;
  const input = totals.tokens_input === null
    ? "entrée inconnue"
    : `${totals.tokens_input.toLocaleString("fr-FR")} en entrée`;
  const output = totals.tokens_output === null
    ? "sortie inconnue"
    : `${totals.tokens_output.toLocaleString("fr-FR")} en sortie`;
  const tools = totals.tool_calls === null
    ? "Appels d’outil : inconnus"
    : `Appels d’outil : ${totals.tool_calls.toLocaleString("fr-FR")}`;
  const facts = [
    cost,
    `Jetons : ${input}, ${output}`,
    tools,
    `Rapports : ${totals.reports.toLocaleString("fr-FR")} · réservations en attente : ${totals.pending_reservations.toLocaleString("fr-FR")}`,
    `Mesure fournisseur : ${totals.usage_reported ? "oui" : "non"} · estimation présente : ${totals.estimated ? "oui" : "non"}`,
  ];
  if (totals.saturated_metrics.length > 0) {
    facts.push(
      `Valeurs plafonnées à l’entier sûr maximal : ${totals.saturated_metrics.join(", ")}`,
    );
  }
  return facts;
}

function budgetConsumptionPanel(): HTMLElement {
  const usage = state.budgetUsage;
  const panel = el("section", "automation-budget-usage");
  panel.append(el("h4", "automation-subtitle", "Consommation comptabilisée"));
  if (state.budgetUsageError) {
    panel.append(errorPanel(state.budgetUsageError, () => void loadProjectResources()));
    return panel;
  }
  if (!usage) {
    panel.append(el("p", "automation-usage-unknown", "Consommation indisponible : aucune valeur n’est remplacée par zéro."));
    return panel;
  }
  panel.append(
    el("p", "list-item-meta", `Jour comptable ${usage.accounting_day} · ${usage.timezone}`),
    el("p", "automation-usage-summary", budgetConsumptionFacts(usage.totals).join(" · ")),
  );
  if (usage.providers.length) {
    const providers = el("div", "automation-provider-list");
    providers.append(el("h5", "automation-subtitle", "Consommation par fournisseur"));
    for (const provider of usage.providers) {
      const row = el("div", "automation-provider");
      row.append(
        el("strong", "", provider.provider),
        el("span", "", budgetConsumptionFacts(provider.totals).join(" · ")),
      );
      providers.append(row);
    }
    panel.append(providers);
  }
  return panel;
}

function preferencesPanel(): HTMLElement {
  const section = el("section", "automation-settings-card");
  section.append(el("h3", "list-item-title", "Notifications dans l’atelier"), el("p", "list-item-meta", "Canal réellement disponible : in-app uniquement. Aucun courriel, SMS ou webhook sortant n’est annoncé."));
  if (state.preferencesError) {
    section.append(errorPanel(state.preferencesError, () => void loadProjectResources()));
    return section;
  }
  if (!state.preferences) return section;
  const enabled = el("input") as HTMLInputElement;
  enabled.type = "checkbox";
  enabled.checked = state.preferences.enabled;
  const severity = el("select", "form-control") as HTMLSelectElement;
  for (const item of [{ value: "info", label: "Information et plus" }, { value: "warning", label: "Attention et critique" }, { value: "critical", label: "Critique uniquement" }] as const) {
    const option = el("option", "", item.label) as HTMLOptionElement;
    option.value = item.value;
    option.selected = item.value === state.preferences.minimum_severity;
    severity.append(option);
  }
  const category = (label: string, checked: boolean): HTMLInputElement => {
    const box = el("input") as HTMLInputElement;
    box.type = "checkbox";
    box.checked = checked;
    const wrapper = el("label", "automation-check");
    wrapper.append(box, el("span", "", label));
    section.append(wrapper);
    return box;
  };
  const top = el("label", "automation-check");
  top.append(enabled, el("span", "", "Afficher les alertes de ce projet dans l’atelier"));
  section.append(top, labeledField("Sévérité minimale", severity));
  const budget = category("Budgets et limites", state.preferences.budget_alerts);
  const failures = category("Échecs répétés d’automatisation", state.preferences.automation_failures);
  const storage = category("Saturation du stockage", state.preferences.storage_alerts);
  const save = focusable(el("button", "button button-primary", "Enregistrer les préférences") as HTMLButtonElement, "preferences-save");
  save.type = "button";
  save.disabled = state.busy !== null;
  save.addEventListener("click", () => void act("preferences", async (context) => {
    const preferences = await api.putNotificationPreferences(context.projectId, {
      channel: "in_app",
      enabled: enabled.checked,
      minimum_severity: severity.value as AlertSeverity,
      budget_alerts: budget.checked,
      automation_failures: failures.checked,
      storage_alerts: storage.checked,
    });
    if (!context.isCurrent()) return;
    state.preferences = preferences;
    state.notice = { tone: "success", message: "Préférences in-app enregistrées." };
  }, "Les préférences n’ont pas pu être enregistrées."));
  section.append(save);
  return section;
}

function budgetPanel(): HTMLElement {
  const section = el("section", "automation-settings-card");
  section.append(el("h3", "list-item-title", "Limites de projet"), el("p", "list-item-meta", "Un champ vide reste inconnu/non limité. La valeur 0 est une limite réelle à zéro."));
  if (state.budgetError) {
    section.append(errorPanel(state.budgetError, () => void loadProjectResources()));
    return section;
  }
  const policy = state.budget;
  if (!policy) return section;
  section.append(budgetConsumptionPanel());
  const daily = policy.daily_budget;
  const cost = el("input", "form-control") as HTMLInputElement;
  cost.type = "number"; cost.min = "0"; cost.step = "0.000001"; cost.value = daily?.max_cost?.toString() ?? "";
  const currency = el("input", "form-control") as HTMLInputElement;
  currency.value = daily?.currency ?? "EUR"; currency.required = true; currency.maxLength = 3;
  const tokens = el("input", "form-control") as HTMLInputElement;
  tokens.type = "number"; tokens.min = "0"; tokens.step = "1"; tokens.value = daily?.max_tokens?.toString() ?? "";
  const tools = el("input", "form-control") as HTMLInputElement;
  tools.type = "number"; tools.min = "0"; tools.step = "1"; tools.value = daily?.max_tool_calls?.toString() ?? "";
  const timezone = el("input", "form-control") as HTMLInputElement;
  timezone.value = policy.timezone; timezone.required = true; timezone.maxLength = 64;
  const concurrent = el("input", "form-control") as HTMLInputElement;
  concurrent.type = "number"; concurrent.min = "1"; concurrent.max = "100"; concurrent.step = "1"; concurrent.value = String(policy.max_concurrent_missions);
  const retries = el("input", "form-control") as HTMLInputElement;
  retries.type = "number"; retries.min = "0"; retries.max = "20"; retries.step = "1"; retries.value = String(policy.max_retries_per_mission);
  const agents = el("input", "form-control") as HTMLInputElement;
  agents.type = "number"; agents.min = "1"; agents.max = "32"; agents.step = "1"; agents.value = String(policy.max_spawned_agents_per_run);
  const formGrid = el("div", "automation-budget-grid");
  formGrid.append(
    labeledField(`Coût quotidien (${daily?.currency ?? "EUR"})`, cost, formatBudgetLimit(daily?.max_cost ?? null, daily?.currency ?? "EUR")),
    labeledField("Devise quotidienne", currency, "Code ISO sur trois lettres."),
    labeledField("Jetons quotidiens", tokens, formatBudgetLimit(daily?.max_tokens ?? null, "jetons")),
    labeledField("Appels d’outil quotidiens", tools, formatBudgetLimit(daily?.max_tool_calls ?? null, "appels")),
    labeledField("Fuseau du jour budgétaire", timezone),
    labeledField("Missions simultanées", concurrent),
    labeledField("Relances par mission", retries),
    labeledField("Agents engendrés par exécution", agents),
  );
  section.append(formGrid);
  interface ProviderEditor {
    row: HTMLElement;
    provider: HTMLInputElement;
    cost: HTMLInputElement;
    currency: HTMLInputElement;
    tokens: HTMLInputElement;
    tools: HTMLInputElement;
  }
  const providerEditors: ProviderEditor[] = [];
  const providers = el("div", "automation-provider-list automation-provider-editors");
  providers.append(
    el("h4", "automation-subtitle", "Limites par fournisseur"),
    el("p", "form-hint", "Chaque fournisseur peut porter ses propres plafonds. Une ligne entièrement vide est ignorée."),
  );
  const addProviderEditor = (item?: ProjectBudgetPolicySummary["provider_budgets"][number]): void => {
    const row = el("div", "automation-provider-editor");
    const provider = el("input", "form-control") as HTMLInputElement;
    provider.value = item?.provider ?? ""; provider.maxLength = 100; provider.placeholder = "openai";
    const providerCost = el("input", "form-control") as HTMLInputElement;
    providerCost.type = "number"; providerCost.min = "0"; providerCost.step = "0.000001"; providerCost.value = item?.budget.max_cost?.toString() ?? "";
    const providerCurrency = el("input", "form-control") as HTMLInputElement;
    providerCurrency.value = item?.budget.currency ?? "EUR"; providerCurrency.maxLength = 3;
    const providerTokens = el("input", "form-control") as HTMLInputElement;
    providerTokens.type = "number"; providerTokens.min = "0"; providerTokens.step = "1"; providerTokens.value = item?.budget.max_tokens?.toString() ?? "";
    const providerTools = el("input", "form-control") as HTMLInputElement;
    providerTools.type = "number"; providerTools.min = "0"; providerTools.step = "1"; providerTools.value = item?.budget.max_tool_calls?.toString() ?? "";
    const remove = el("button", "button button-secondary", "Retirer") as HTMLButtonElement;
    remove.type = "button";
    remove.setAttribute("aria-label", `Retirer la limite fournisseur ${item?.provider ?? "sans nom"}`);
    const editor: ProviderEditor = { row, provider, cost: providerCost, currency: providerCurrency, tokens: providerTokens, tools: providerTools };
    remove.addEventListener("click", () => {
      const index = providerEditors.indexOf(editor);
      if (index >= 0) providerEditors.splice(index, 1);
      row.remove();
    });
    row.append(
      labeledField("Fournisseur", provider),
      labeledField("Coût", providerCost),
      labeledField("Devise", providerCurrency),
      labeledField("Jetons", providerTokens),
      labeledField("Outils", providerTools),
      remove,
    );
    providerEditors.push(editor);
    providers.append(row);
  };
  for (const item of policy.provider_budgets) addProviderEditor(item);
  const addProvider = el("button", "button button-secondary", "Ajouter un fournisseur") as HTMLButtonElement;
  addProvider.type = "button";
  addProvider.disabled = state.busy !== null;
  addProvider.addEventListener("click", () => addProviderEditor());
  providers.append(addProvider);
  section.append(providers);
  const feedback = el("div", "form-feedback");
  feedback.setAttribute("role", "status");
  const save = focusable(el("button", "button button-primary", "Enregistrer les limites") as HTMLButtonElement, "budget-save");
  save.type = "button";
  save.disabled = state.busy !== null;
  save.addEventListener("click", () => {
    let payload: ProjectBudgetPolicy;
    try {
      const nextDaily = buildBudgetLimits(cost.value, currency.value, tokens.value, tools.value);
      const providerBudgets = providerEditors.flatMap((editor) => {
        const provider = editor.provider.value.trim();
        const providerBudget = buildBudgetLimits(
          editor.cost.value,
          editor.currency.value,
          editor.tokens.value,
          editor.tools.value,
        );
        if (!provider && !providerBudget) return [];
        if (!provider || !providerBudget) {
          throw new Error("Chaque limite fournisseur doit avoir un nom et au moins un plafond.");
        }
        return [{ provider, budget: providerBudget }];
      });
      const normalizedProviders = providerBudgets.map((item) => item.provider.toLocaleLowerCase());
      if (new Set(normalizedProviders).size !== normalizedProviders.length) {
        throw new Error("Un fournisseur ne peut apparaître qu’une seule fois.");
      }
      const concurrencyLimit = Number(concurrent.value);
      const retryLimit = Number(retries.value);
      const agentLimit = Number(agents.value);
      if (!Number.isInteger(concurrencyLimit) || concurrencyLimit < 1 || concurrencyLimit > 100
        || !Number.isInteger(retryLimit) || retryLimit < 0 || retryLimit > 20
        || !Number.isInteger(agentLimit) || agentLimit < 1 || agentLimit > 32) {
        throw new Error("Les bornes de concurrence, relance et agents doivent être des entiers dans les intervalles affichés.");
      }
      const budgetTimezone = timezone.value.trim();
      if (!budgetTimezone) throw new Error("Le fuseau du jour budgétaire est requis.");
      payload = {
        timezone: budgetTimezone,
        daily_budget: nextDaily,
        provider_budgets: providerBudgets,
        max_concurrent_missions: concurrencyLimit,
        max_retries_per_mission: retryLimit,
        max_spawned_agents_per_run: agentLimit,
      };
    } catch (error) {
      feedback.dataset.tone = "error";
      feedback.textContent = error instanceof Error ? error.message : "Les limites sont invalides.";
      return;
    }
    void act("budget", async (context) => {
      const budget = await api.putBudgetPolicy(context.projectId, payload);
      if (!context.isCurrent()) return;
      state.budget = budget;
      state.notice = { tone: "success", message: "Limites budgétaires enregistrées. Les champs vides restent explicitement inconnus." };
    }, "Les limites n’ont pas pu être enregistrées.");
  });
  section.append(feedback, save);
  return section;
}

function settingsView(): HTMLElement {
  const layout = el("div", "automation-settings");
  layout.append(preferencesPanel(), budgetPanel());
  return layout;
}

function renderReady(): void {
  if (!mount) return;
  const intro = el("section", "page-intro automation-intro");
  const heading = el("div");
  heading.append(el("p", "workspace-eyebrow", "Planification propriétaire · Europe/Paris par défaut"), el("h2", "page-title", "Automatisations vérifiables"), el("p", "page-description", "Planifie des missions réelles, examine leur prochaine occurrence et garde la main sur chaque activation."));
  const alertStatus = state.alertsError
    ? statusChip("Alertes indisponibles", "failed")
    : state.alerts.length === ALERT_PAGE_LIMIT
      ? statusChip(`Au moins ${ALERT_PAGE_LIMIT} alertes ouvertes`, "waiting")
      : state.alerts.length
      ? statusChip(`${state.alerts.length} alerte(s) ouverte(s)`, "waiting")
      : statusChip("Aucune alerte ouverte", "active");
  intro.append(heading, alertStatus);
  mount.append(intro);
  if (!state.projects.length) {
    mount.append(statePanel("empty", "Aucun projet actif", "Crée ou réactive un projet avant de définir une routine."));
    return;
  }
  mount.append(projectToolbar());
  const notice = noticeNode();
  if (notice) mount.append(notice);
  if (state.projectPhase === "loading") {
    mount.append(statePanel("loading", "Lecture du projet", "Chargement des routines, du calendrier, des alertes et des limites."));
    return;
  }
  mount.append(metrics(), viewTabs());
  if (state.view === "routines") mount.append(routinesView());
  else if (state.view === "calendar") mount.append(calendarView());
  else if (state.view === "alerts") mount.append(alertsView());
  else mount.append(settingsView());
}

function render(): void {
  if (!mount) return;
  const active = document.activeElement as HTMLElement | null | undefined;
  const focusKey = requestedFocusKey ?? active?.dataset?.focusKey ?? null;
  requestedFocusKey = null;
  mount.replaceChildren();
  if (state.phase === "idle" || state.phase === "loading") {
    mount.append(statePanel("loading", "Ouverture des automatisations", "Lecture des projets avant toute opération."));
  } else if (state.phase === "error" && state.error) {
    mount.append(errorPanel(state.error, () => void loadInitial()));
  } else {
    renderReady();
  }
  if (focusKey && typeof mount.querySelectorAll === "function") {
    const next = Array.from(mount.querySelectorAll<HTMLElement>("[data-focus-key]"))
      .find((candidate) => candidate.dataset.focusKey === focusKey);
    next?.focus();
  }
}

export function renderAutomations(container: HTMLElement, sharedHttp?: WorkspaceHttpClient): void {
  useHttp(sharedHttp);
  mount = container;
  render();
  if (state.phase === "idle") void loadInitial();
}

export function unmountAutomationUi(): void {
  ++loadSequence;
  clearDetailState();
  state.phase = "idle";
  state.projectPhase = "idle";
  requestedFocusKey = null;
  mount = null;
}

export function resetAutomationUiState(): void {
  unmountAutomationUi();
  Object.assign(state, initialState());
  Object.assign(draft, initialDraft());
}
