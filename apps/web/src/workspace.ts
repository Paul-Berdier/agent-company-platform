import type { AcpEvent, Overview, Project, TaskSummary } from "@acp/contracts";

import "./workspace.css";
import {
  MissionQueueError,
  WorkspaceApiClient,
  WorkspaceApiError,
  type ApprovalSummary,
  type MissionInput,
} from "./workspace-api";
import {
  NAVIGATION_ITEMS,
  isActiveTask,
  routeFromPathname,
  taskOutcomeRate,
  taskStatusLabel,
  type WorkspaceRoute,
} from "./workspace-model";

type LoadPhase = "loading" | "ready" | "offline" | "forbidden" | "error";
type Theme = "light" | "dark";

interface WorkspaceState {
  phase: LoadPhase;
  overview: Overview | null;
  events: AcpEvent[];
  approvals: ApprovalSummary[];
  primaryError: WorkspaceApiError | null;
  eventsError: WorkspaceApiError | null;
  approvalsError: WorkspaceApiError | null;
}

interface MissionNotice {
  tone: "success" | "error" | "warning";
  message: string;
}

const api = new WorkspaceApiClient();
const state: WorkspaceState = {
  phase: "loading",
  overview: null,
  events: [],
  approvals: [],
  primaryError: null,
  eventsError: null,
  approvalsError: null,
};

let currentRoute = routeFromPathname(window.location.pathname);
let loadSequence = 0;
let missionNotice: MissionNotice | null = null;
let fieldSequence = 0;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className = "",
  text = "",
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function routeItem(route: WorkspaceRoute) {
  return NAVIGATION_ITEMS.find((item) => item.id === route) ?? NAVIGATION_ITEMS[0];
}

function routeLink(path: string, label: string, className = "button button-secondary"): HTMLAnchorElement {
  const link = el("a", className, label);
  link.href = path;
  link.dataset.workspaceLink = "true";
  return link;
}

const root = document.getElementById("app");
if (!root) throw new Error("Le conteneur #app est absent.");

root.className = "workspace-root";
root.removeAttribute("style");

const skipLink = routeLink("#workspace-content", "Aller au contenu", "skip-link");
delete skipLink.dataset.workspaceLink;

const sidebar = el("aside", "workspace-sidebar");
const brand = el("a", "workspace-brand");
brand.href = "/";
brand.dataset.workspaceLink = "true";
brand.setAttribute("aria-label", "Agent Company Platform — Accueil");
brand.append(el("span", "workspace-mark", "AC"), el("span", "workspace-brand-name", "Agent Company Platform"));

const navigation = el("nav", "workspace-navigation");
navigation.setAttribute("aria-label", "Navigation principale");

const sidebarNavList = el("ul", "workspace-nav-list");
for (const item of NAVIGATION_ITEMS) {
  const listItem = el("li");
  const link = routeLink(item.path, "", "workspace-nav-link");
  link.dataset.route = item.id;
  link.append(
    el("span", "workspace-nav-icon", item.icon),
    el("span", "workspace-nav-label", item.label),
  );
  if (!item.configured) {
    const status = el("span", "workspace-nav-status", "Non configuré");
    status.setAttribute("aria-label", "Fonction non configurée");
    link.append(status);
  }
  listItem.append(link);
  sidebarNavList.append(listItem);
}
navigation.append(sidebarNavList);

const sidebarFooter = el("div", "workspace-sidebar-footer");
sidebarFooter.append(
  el("p", "workspace-eyebrow", "Espace personnel"),
  el("p", "workspace-small", "Les capacités affichées reflètent uniquement les services réellement raccordés."),
);
sidebar.append(brand, navigation, sidebarFooter);

const main = el("main", "workspace-main");
const topbar = el("header", "workspace-topbar");
const topbarTitles = el("div", "workspace-topbar-titles");
const routeEyebrow = el("p", "workspace-eyebrow", "Espace de travail");
const routeTitle = el("h1", "workspace-route-title");
topbarTitles.append(routeEyebrow, routeTitle);

const topbarActions = el("div", "workspace-topbar-actions");
const apiStatus = el("div", "connection-status");
apiStatus.setAttribute("role", "status");
apiStatus.setAttribute("aria-live", "polite");

const refreshButton = el("button", "icon-button", "Actualiser");
refreshButton.type = "button";
refreshButton.addEventListener("click", () => void loadWorkspaceData());

const themeButton = el("button", "icon-button");
themeButton.type = "button";
themeButton.addEventListener("click", () => {
  const next: Theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next, true);
});
topbarActions.append(apiStatus, refreshButton, themeButton);
topbar.append(topbarTitles, topbarActions);

const content = el("div", "workspace-content");
content.id = "workspace-content";
content.tabIndex = -1;
main.append(topbar, content);
root.replaceChildren(skipLink, sidebar, main);

function preferredTheme(): Theme {
  try {
    const stored = localStorage.getItem("acp.theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Le thème système reste disponible lorsque le stockage est bloqué.
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function applyTheme(theme: Theme, persist: boolean): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  themeButton.textContent = theme === "dark" ? "Thème clair" : "Thème sombre";
  themeButton.setAttribute("aria-label", themeButton.textContent);
  if (persist) {
    try {
      localStorage.setItem("acp.theme", theme);
    } catch {
      // Le choix reste appliqué pour l'onglet courant.
    }
  }
}

function failurePhase(error: WorkspaceApiError): Exclude<LoadPhase, "loading" | "ready"> {
  if (error.kind === "offline") return "offline";
  if (error.kind === "forbidden") return "forbidden";
  return "error";
}

function errorMessage(error: WorkspaceApiError): string {
  if (error.kind === "offline") {
    return "L’API métier ne répond pas. Les données de démonstration ne sont jamais utilisées ici.";
  }
  if (error.kind === "forbidden") {
    return "La session courante n’a pas accès à ces données. Aucun écran de connexion n’est simulé.";
  }
  return error.message;
}

function updateConnectionStatus(): void {
  let label = "Connexion en cours";
  let tone = "pending";
  if (state.phase === "ready") {
    const partial = Boolean(state.eventsError || state.approvalsError);
    label = partial ? "API partiellement disponible" : "API connectée";
    tone = partial ? "warning" : "success";
  } else if (state.phase === "offline") {
    label = "API hors ligne";
    tone = "danger";
  } else if (state.phase === "forbidden") {
    label = "Accès refusé";
    tone = "danger";
  } else if (state.phase === "error") {
    label = "API en erreur";
    tone = "danger";
  }
  apiStatus.dataset.tone = tone;
  apiStatus.replaceChildren(el("span", "connection-dot"), document.createTextNode(label));
  refreshButton.disabled = state.phase === "loading";
  refreshButton.setAttribute("aria-busy", String(state.phase === "loading"));
}

async function loadWorkspaceData(): Promise<void> {
  const sequence = ++loadSequence;
  state.phase = "loading";
  state.primaryError = null;
  state.eventsError = null;
  state.approvalsError = null;
  updateConnectionStatus();
  renderCurrentRoute();

  const [overviewResult, eventsResult, approvalsResult] = await Promise.allSettled([
    api.fetchOverview(),
    api.fetchRecentEvents(),
    api.fetchPendingApprovals(),
  ]);
  if (sequence !== loadSequence) return;

  if (overviewResult.status === "rejected") {
    const error = overviewResult.reason instanceof WorkspaceApiError
      ? overviewResult.reason
      : new WorkspaceApiError("Impossible de charger l’espace de travail.", "offline");
    state.overview = null;
    state.primaryError = error;
    state.phase = failurePhase(error);
  } else {
    state.overview = overviewResult.value;
    state.phase = "ready";
  }

  if (eventsResult.status === "fulfilled") {
    state.events = eventsResult.value;
  } else {
    state.events = [];
    state.eventsError = eventsResult.reason instanceof WorkspaceApiError
      ? eventsResult.reason
      : new WorkspaceApiError("Activité récente indisponible.", "offline");
  }

  if (approvalsResult.status === "fulfilled") {
    state.approvals = approvalsResult.value;
  } else {
    state.approvals = [];
    state.approvalsError = approvalsResult.reason instanceof WorkspaceApiError
      ? approvalsResult.reason
      : new WorkspaceApiError("Approbations indisponibles.", "offline");
  }

  updateConnectionStatus();
  renderCurrentRoute();
}

function statePanel(
  tone: "loading" | "empty" | "offline" | "forbidden" | "error" | "unconfigured",
  title: string,
  message: string,
  retry = false,
): HTMLElement {
  const panel = el("section", `state-panel state-${tone}`);
  panel.setAttribute("aria-live", tone === "loading" ? "polite" : "assertive");
  panel.append(
    el("span", "state-icon", tone === "loading" ? "…" : tone === "empty" ? "○" : "!"),
    el("h2", "state-title", title),
    el("p", "state-message", message),
  );
  if (retry) {
    const button = el("button", "button button-secondary", "Réessayer");
    button.type = "button";
    button.addEventListener("click", () => void loadWorkspaceData());
    panel.append(button);
  }
  return panel;
}

function renderDataBoundary(renderReady: (overview: Overview) => void): void {
  if (state.phase === "loading") {
    content.append(statePanel("loading", "Chargement des données réelles", "Connexion à l’API métier en cours."));
    return;
  }
  if (state.phase !== "ready" || !state.overview) {
    const error = state.primaryError;
    const title = state.phase === "offline"
      ? "Plateforme hors ligne"
      : state.phase === "forbidden"
        ? "Accès refusé"
        : "Chargement impossible";
    content.append(statePanel(
      state.phase === "offline" ? "offline" : state.phase === "forbidden" ? "forbidden" : "error",
      title,
      error ? errorMessage(error) : "La réponse reçue est inexploitable.",
      true,
    ));
    return;
  }
  renderReady(state.overview);
}

function sectionHeader(title: string, description = ""): HTMLElement {
  const header = el("div", "section-header");
  const copy = el("div");
  copy.append(el("h2", "section-heading", title));
  if (description) copy.append(el("p", "section-description", description));
  header.append(copy);
  return header;
}

function statusChip(label: string, tone: string): HTMLElement {
  const chip = el("span", "status-chip", label);
  chip.dataset.tone = tone;
  return chip;
}

function projectName(overview: Overview, projectId: string): string {
  return overview.projects.find((project) => project.id === projectId)?.name ?? "Projet inconnu";
}

function renderTaskList(overview: Overview, tasks: readonly TaskSummary[]): HTMLElement {
  const list = el("div", "item-list");
  for (const task of tasks) {
    const item = el("article", "list-item");
    const copy = el("div", "list-item-copy");
    copy.append(
      el("h3", "list-item-title", task.title),
      el("p", "list-item-meta", projectName(overview, task.project_id)),
    );
    item.append(copy, statusChip(taskStatusLabel(task.status), task.status));
    list.append(item);
  }
  return list;
}

function metricCard(label: string, value: string, hint: string, tone = "neutral"): HTMLElement {
  const card = el("article", "metric-card");
  card.dataset.tone = tone;
  card.append(
    el("p", "metric-label", label),
    el("p", "metric-value", value),
    el("p", "metric-hint", hint),
  );
  return card;
}

function unavailableSection(title: string, error: WorkspaceApiError): HTMLElement {
  const section = el("section", "content-section");
  section.append(
    sectionHeader(title),
    statePanel(
      error.kind === "forbidden" ? "forbidden" : error.kind === "offline" ? "offline" : "error",
      `${title} indisponible`,
      errorMessage(error),
      true,
    ),
  );
  return section;
}

function renderHome(overview: Overview): void {
  const hero = el("section", "workspace-hero");
  const heroCopy = el("div", "workspace-hero-copy");
  heroCopy.append(
    el("p", "workspace-eyebrow", "Atelier numérique personnel"),
    el("h2", "workspace-hero-title", "Que veux-tu faire ?"),
    el("p", "workspace-hero-description", "Choisis un projet, lance une mission réelle et garde une vue honnête sur ce qui fonctionne."),
  );
  const heroActions = el("div", "workspace-actions");
  heroActions.append(
    routeLink("/missions", "Lancer une mission", "button button-primary"),
    routeLink("/projects", "Voir les projets"),
  );
  const disabledActions = el("div", "disabled-actions");
  disabledActions.append(
    capabilityTag("Discuter", "Conversation Hermes non configurée"),
    capabilityTag("Connecter un outil", "Centre de connexions non configuré"),
  );
  heroCopy.append(heroActions, disabledActions);
  hero.append(heroCopy);
  content.append(hero);

  const activeTasks = overview.tasks.filter(isActiveTask);
  const outcome = taskOutcomeRate(overview.tasks);
  const metrics = el("section", "metric-grid");
  metrics.setAttribute("aria-label", "Synthèse de l’espace de travail");
  metrics.append(
    metricCard("Travail en cours", String(activeTasks.length), "Tâches métier actives", activeTasks.length ? "accent" : "neutral"),
    metricCard(
      "Validations attendues",
      state.approvalsError ? "Indisponible" : String(state.approvals.length),
      state.approvalsError ? "État API inconnu" : "Approbations métier",
      state.approvalsError ? "warning" : state.approvals.length ? "warning" : "neutral",
    ),
    metricCard("Projets", String(overview.projects.length), "Projets accessibles"),
    metricCard(
      "Résultat des tâches",
      outcome.percentage === null ? "Inconnu" : `${outcome.percentage}%`,
      outcome.sampleSize === 0 ? "Aucune tâche finalisée" : `${outcome.sampleSize} tâche(s) observée(s)`,
      outcome.percentage === null ? "warning" : outcome.failed ? "warning" : "success",
    ),
  );
  content.append(metrics);

  const columns = el("div", "home-columns");
  const work = el("section", "content-section");
  work.append(sectionHeader("Travail en cours", "État fourni par l’API métier."));
  work.append(activeTasks.length
    ? renderTaskList(overview, activeTasks.slice(0, 6))
    : statePanel("empty", "Aucun travail en cours", "Aucune tâche n’est actuellement en file, en préparation ou en exécution."));
  columns.append(work);

  if (state.approvalsError) {
    columns.append(unavailableSection("Validations attendues", state.approvalsError));
  } else {
    const approvals = el("section", "content-section");
    approvals.append(sectionHeader("Validations attendues", "Demandes durables retournées par l’API métier."));
    if (!state.approvals.length) {
      approvals.append(statePanel("empty", "Aucune validation attendue", "L’API ne signale actuellement aucune demande en attente."));
    } else {
      const list = el("div", "item-list");
      for (const approval of state.approvals.slice(0, 6)) {
        const item = el("article", "list-item");
        const copy = el("div", "list-item-copy");
        copy.append(
          el("h3", "list-item-title", approval.reason),
          el("p", "list-item-meta", `${projectName(overview, approval.project_id)} · ${approval.action}`),
        );
        item.append(copy, statusChip("En attente", "waiting"));
        list.append(item);
      }
      approvals.append(list);
    }
    columns.append(approvals);
  }
  content.append(columns);

  const projects = el("section", "content-section");
  const projectsHeader = sectionHeader(
    "Projets disponibles",
    "L’API actuelle ne fournit pas de date d’activité : aucun ordre de récence n’est inventé.",
  );
  projectsHeader.append(routeLink("/projects", "Tous les projets", "text-link"));
  projects.append(projectsHeader);
  projects.append(overview.projects.length
    ? renderProjectGrid(overview.projects.slice(0, 4), overview)
    : statePanel("empty", "Aucun projet", "Ajoute d’abord un projet par un client ou une API autorisée."));
  content.append(projects);

  if (state.eventsError) {
    content.append(unavailableSection("Activité récente", state.eventsError));
  } else {
    const activity = el("section", "content-section");
    activity.append(sectionHeader("Activité récente", "Événements persistés retournés par l’API métier."));
    if (!state.events.length) {
      activity.append(statePanel("empty", "Aucune activité enregistrée", "L’API n’a retourné aucun événement récent."));
    } else {
      const list = el("ol", "activity-list");
      for (const event of state.events.slice(0, 8)) {
        const item = el("li", "activity-item");
        const time = el("time", "activity-time", formatDateTime(event.occurred_at));
        time.dateTime = event.occurred_at;
        item.append(time, el("span", "activity-type", event.type));
        list.append(item);
      }
      activity.append(list);
    }
    content.append(activity);
  }
}

function capabilityTag(label: string, reason: string): HTMLElement {
  const item = el("div", "capability-tag");
  item.setAttribute("aria-disabled", "true");
  item.setAttribute("aria-label", `${label} — ${reason}`);
  item.append(el("span", "capability-label", label), statusChip("Non configuré", "unconfigured"));
  item.title = reason;
  return item;
}

function renderProjectGrid(projects: readonly Project[], overview: Overview): HTMLElement {
  const grid = el("div", "project-grid");
  for (const project of projects) {
    const card = el("article", "project-card");
    const department = overview.departments.find((item) => item.id === project.department_id);
    const tasks = overview.tasks.filter((task) => task.project_id === project.id);
    const active = tasks.filter(isActiveTask).length;
    card.append(
      statusChip(project.status || "État inconnu", project.status === "active" ? "active" : "neutral"),
      el("h3", "project-title", project.name),
      el("p", "project-description", project.description || "Aucune description fournie."),
      el("p", "project-meta", `${department?.name ?? "Sans département"} · ${active} active(s) · ${tasks.length} au total`),
    );
    grid.append(card);
  }
  return grid;
}

function renderProjects(overview: Overview): void {
  const intro = el("section", "page-intro");
  intro.append(
    el("p", "workspace-eyebrow", "Contexte autorisé"),
    el("h2", "page-title", "Projets"),
    el("p", "page-description", "Projets retournés par l’instantané métier. Aucun dépôt supplémentaire n’est importé automatiquement."),
  );
  content.append(intro);
  content.append(overview.projects.length
    ? renderProjectGrid(overview.projects, overview)
    : statePanel("empty", "Aucun projet accessible", "L’API ne retourne aucun projet pour la session courante."));
}

function missionFeedbackNode(): HTMLElement {
  const feedback = el("div", "form-feedback");
  feedback.setAttribute("aria-live", "polite");
  if (missionNotice) {
    feedback.dataset.tone = missionNotice.tone;
    feedback.textContent = missionNotice.message;
  }
  return feedback;
}

function renderMissions(overview: Overview): void {
  const intro = el("section", "page-intro");
  intro.append(
    el("p", "workspace-eyebrow", "Exécution réelle"),
    el("h2", "page-title", "Missions"),
    el("p", "page-description", "Une mission crée une tâche métier puis demande sa mise en file. Le succès n’est affiché qu’après confirmation des deux réponses."),
  );
  content.append(intro);

  const layout = el("div", "missions-layout");
  const composer = el("section", "content-section mission-composer");
  composer.append(sectionHeader("Nouvelle mission", "Les critères sont transmis dans les métadonnées de la tâche."));
  if (!overview.projects.length) {
    composer.append(statePanel("empty", "Projet requis", "Aucun projet n’est disponible pour recevoir une mission."));
  } else {
    composer.append(createMissionForm(overview));
  }

  const existing = el("section", "content-section");
  existing.append(sectionHeader("Tâches et missions", "L’overview actuel ne permet pas encore de distinguer les anciennes tâches des missions."));
  existing.append(overview.tasks.length
    ? renderTaskList(overview, overview.tasks)
    : statePanel("empty", "Aucune mission", "Aucune tâche métier n’a encore été créée."));
  layout.append(composer, existing);
  content.append(layout);
}

function labeledField(labelText: string, control: HTMLElement, hint = ""): HTMLElement {
  const field = el("div", "form-field");
  const id = `mission-field-${++fieldSequence}`;
  control.id = id;
  const label = el("label", "form-label", labelText);
  label.htmlFor = id;
  field.append(label, control);
  if (hint) field.append(el("p", "form-hint", hint));
  return field;
}

function createMissionForm(overview: Overview): HTMLFormElement {
  const form = el("form", "mission-form");
  form.noValidate = true;

  const projectSelect = el("select", "form-control") as HTMLSelectElement;
  projectSelect.name = "projectId";
  projectSelect.required = true;
  for (const project of overview.projects) {
    const option = el("option", "", project.name) as HTMLOptionElement;
    option.value = project.id;
    projectSelect.append(option);
  }

  const titleInput = el("input", "form-control") as HTMLInputElement;
  titleInput.name = "title";
  titleInput.required = true;
  titleInput.maxLength = 160;
  titleInput.placeholder = "Ex. Vérifier et corriger l’export CSV";

  const objectiveInput = el("textarea", "form-control form-textarea") as HTMLTextAreaElement;
  objectiveInput.name = "objective";
  objectiveInput.required = true;
  objectiveInput.rows = 4;
  objectiveInput.maxLength = 4000;
  objectiveInput.placeholder = "Décris le résultat à obtenir et les contraintes importantes.";

  const expectedInput = el("input", "form-control") as HTMLInputElement;
  expectedInput.name = "expectedResult";
  expectedInput.required = true;
  expectedInput.maxLength = 500;
  expectedInput.placeholder = "Ex. Correctif testé et rapport des changements";

  const criteriaInput = el("textarea", "form-control form-textarea compact") as HTMLTextAreaElement;
  criteriaInput.name = "acceptanceCriteria";
  criteriaInput.required = true;
  criteriaInput.rows = 3;
  criteriaInput.maxLength = 2000;
  criteriaInput.placeholder = "Ex. Les tests passent ; les erreurs restent explicites";

  const autonomySelect = el("select", "form-control") as HTMLSelectElement;
  autonomySelect.name = "autonomy";
  const autonomyOptions = [
    ["read_only", "Lecture seule"],
    ["isolated_work", "Travail en environnement isolé"],
    ["sensitive_on_approval", "Actions sensibles sur validation"],
  ] as const;
  for (const [value, label] of autonomyOptions) {
    const option = el("option", "", label) as HTMLOptionElement;
    option.value = value;
    if (value === "isolated_work") option.selected = true;
    autonomySelect.append(option);
  }

  const prioritySelect = el("select", "form-control") as HTMLSelectElement;
  prioritySelect.name = "priority";
  for (const [value, label] of [["3", "Normale"], ["2", "Haute"], ["1", "Urgente"]]) {
    const option = el("option", "", label) as HTMLOptionElement;
    option.value = value;
    prioritySelect.append(option);
  }

  const split = el("div", "form-split");
  split.append(
    labeledField("Niveau d’autonomie", autonomySelect, "Cette valeur est enregistrée ; son application dépend du runner."),
    labeledField("Priorité", prioritySelect),
  );

  const feedback = missionFeedbackNode();
  const submit = el("button", "button button-primary", "Créer et mettre en file") as HTMLButtonElement;
  submit.type = "submit";

  form.append(
    labeledField("Projet", projectSelect),
    labeledField("Titre", titleInput),
    labeledField("Objectif", objectiveInput),
    labeledField("Résultat attendu", expectedInput),
    labeledField("Critères d’acceptation", criteriaInput),
    split,
    feedback,
    submit,
  );

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const input: MissionInput = {
      projectId: String(data.get("projectId") ?? ""),
      title: String(data.get("title") ?? "").trim(),
      objective: String(data.get("objective") ?? "").trim(),
      expectedResult: String(data.get("expectedResult") ?? "").trim(),
      acceptanceCriteria: String(data.get("acceptanceCriteria") ?? "").trim(),
      autonomy: String(data.get("autonomy")) as MissionInput["autonomy"],
      priority: Number(data.get("priority") ?? 3),
    };

    submit.disabled = true;
    submit.textContent = "Création en cours…";
    form.setAttribute("aria-busy", "true");
    feedback.dataset.tone = "pending";
    feedback.textContent = "Création de la tâche métier…";
    missionNotice = null;

    try {
      const result = await api.createAndQueueMission(input);
      missionNotice = {
        tone: "success",
        message: `Mission « ${result.queued.title} » créée et mise en file (identifiant ${result.queued.id}).`,
      };
      await loadWorkspaceData();
    } catch (error) {
      if (error instanceof MissionQueueError) {
        missionNotice = {
          tone: "warning",
          message: `La tâche ${error.taskId} existe, mais sa mise en file n’est pas confirmée : ${error.cause.message}`,
        };
      } else if (error instanceof WorkspaceApiError) {
        missionNotice = { tone: "error", message: errorMessage(error) };
      } else {
        missionNotice = { tone: "error", message: "La mission n’a pas pu être créée." };
      }
      feedback.dataset.tone = missionNotice.tone;
      feedback.textContent = missionNotice.message;
      submit.disabled = false;
      submit.textContent = "Créer et mettre en file";
      form.removeAttribute("aria-busy");
    }
  });
  return form;
}

const CAPABILITY_COPY: Record<Exclude<WorkspaceRoute, "home" | "projects" | "missions">, {
  title: string;
  description: string;
  consequence: string;
}> = {
  conversations: {
    title: "Conversations",
    description: "La création et la reprise de conversations Hermes ne sont pas encore raccordées.",
    consequence: "Aucun message ne sera envoyé tant qu’une API de conversation compatible et authentifiée n’est pas configurée.",
  },
  automations: {
    title: "Automatisations",
    description: "Aucun propriétaire de planification n’est encore configuré dans ce shell.",
    consequence: "Aucune routine n’est créée ou exécutée implicitement.",
  },
  library: {
    title: "Bibliothèque",
    description: "La liste sécurisée des livrables et leurs aperçus ne sont pas encore raccordés.",
    consequence: "Le shell ne prétend pas exposer les fichiers tant que leurs autorisations et URLs ne sont pas vérifiées.",
  },
  connections: {
    title: "Connexions",
    description: "Le centre Hermes, MCP et fournisseurs n’est pas encore disponible.",
    consequence: "L’API métier est la seule connexion vérifiée sur cet écran ; aucun outil externe n’est activé automatiquement.",
  },
};

function renderUnconfigured(route: keyof typeof CAPABILITY_COPY): void {
  const copy = CAPABILITY_COPY[route];
  const intro = el("section", "page-intro");
  intro.append(
    statusChip("Non configuré", "unconfigured"),
    el("h2", "page-title", copy.title),
    el("p", "page-description", copy.description),
  );
  content.append(intro, statePanel("unconfigured", "Capacité indisponible", copy.consequence));
  if (route === "connections") {
    const connection = el("section", "content-section");
    connection.append(sectionHeader("État vérifié"));
    const row = el("article", "list-item");
    row.append(
      el("div", "list-item-copy", "API métier"),
      statusChip(
        state.phase === "ready" ? "Connectée" : state.phase === "loading" ? "Vérification" : "Indisponible",
        state.phase === "ready" ? "active" : state.phase === "loading" ? "waiting" : "failed",
      ),
    );
    connection.append(row);
    content.append(connection);
  }
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date inconnue";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  }).format(date);
}

function updateActiveNavigation(): void {
  for (const link of sidebar.querySelectorAll<HTMLAnchorElement>("[data-route]")) {
    const active = link.dataset.route === currentRoute;
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function renderCurrentRoute(): void {
  const item = routeItem(currentRoute);
  routeTitle.textContent = item.label;
  document.title = `${item.label} — Agent Company Platform`;
  updateActiveNavigation();
  content.replaceChildren();

  if (currentRoute === "home") {
    renderDataBoundary(renderHome);
  } else if (currentRoute === "projects") {
    renderDataBoundary(renderProjects);
  } else if (currentRoute === "missions") {
    renderDataBoundary(renderMissions);
  } else {
    renderUnconfigured(currentRoute);
  }
}

function navigate(path: string, focusContent: boolean): void {
  const url = new URL(path, window.location.href);
  if (url.origin !== window.location.origin) return;
  window.history.pushState({}, "", `${url.pathname}${url.search}${url.hash}`);
  currentRoute = routeFromPathname(url.pathname);
  renderCurrentRoute();
  if (focusContent) content.focus();
}

root.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) return;
  const link = event.target.closest<HTMLAnchorElement>("a[data-workspace-link='true']");
  if (!link || event instanceof MouseEvent && (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)) return;
  if (link.target && link.target !== "_self") return;
  event.preventDefault();
  navigate(link.href, true);
});

window.addEventListener("popstate", () => {
  currentRoute = routeFromPathname(window.location.pathname);
  renderCurrentRoute();
  content.focus();
});

applyTheme(preferredTheme(), false);
updateConnectionStatus();
renderCurrentRoute();
void loadWorkspaceData();
