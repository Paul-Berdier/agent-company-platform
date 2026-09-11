import type { AcpEvent, Overview, Project, TaskSummary } from "@acp/contracts";

import "./workspace.css";
import {
  MissionQueueError,
  WorkspaceApiClient,
  WorkspaceApiError,
  WorkspaceHttpClient,
  type ApprovalSummary,
  type MissionInput,
  type OnboardingProjectInput,
  type OnboardingStatus,
} from "./workspace-api";
import {
  AuthApiClient,
  type AuthSession,
  type BootstrapInput,
  type LoginInput,
} from "./auth-api";
import {
  ConversationApiClient,
  isTerminalConversationTurn,
  type ConversationSummary,
  type ConversationTurn,
  type HermesDiagnostic,
} from "./conversation-api";
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
type AuthPhase = "checking" | "bootstrap" | "login" | "authenticated" | "offline" | "error";
type ResourcePhase = "idle" | "loading" | "ready" | "error";

interface WorkspaceState {
  phase: LoadPhase;
  overview: Overview | null;
  events: AcpEvent[];
  approvals: ApprovalSummary[];
  onboarding: OnboardingStatus | null;
  primaryError: WorkspaceApiError | null;
  eventsError: WorkspaceApiError | null;
  approvalsError: WorkspaceApiError | null;
  onboardingError: WorkspaceApiError | null;
}

interface MissionNotice {
  tone: "success" | "error" | "warning";
  message: string;
}

interface AuthState {
  phase: AuthPhase;
  session: AuthSession | null;
  error: WorkspaceApiError | null;
}

interface ConversationState {
  phase: ResourcePhase;
  items: ConversationSummary[];
  error: WorkspaceApiError | null;
  activeId: string | null;
  turnsPhase: ResourcePhase;
  turns: ConversationTurn[];
  turnsError: WorkspaceApiError | null;
  notice: MissionNotice | null;
}

interface ConnectionState {
  phase: ResourcePhase;
  diagnostic: HermesDiagnostic | null;
  error: WorkspaceApiError | null;
}

const http = new WorkspaceHttpClient();
const api = new WorkspaceApiClient({ http });
const authApi = new AuthApiClient({ http });
const conversationApi = new ConversationApiClient({ http });
const state: WorkspaceState = {
  phase: "loading",
  overview: null,
  events: [],
  approvals: [],
  onboarding: null,
  primaryError: null,
  eventsError: null,
  approvalsError: null,
  onboardingError: null,
};
const authState: AuthState = { phase: "checking", session: null, error: null };
const conversationState: ConversationState = {
  phase: "idle",
  items: [],
  error: null,
  activeId: null,
  turnsPhase: "idle",
  turns: [],
  turnsError: null,
  notice: null,
};
const connectionState: ConnectionState = {
  phase: "idle",
  diagnostic: null,
  error: null,
};
const conversationDrafts = new Map<string, string>();
const newConversationDraft = { projectId: "", title: "" };
const newProjectDraft = { name: "", description: "", projectType: "generic" };
const conversationFilters: { search: string; status: "" | "active" | "archived" } = {
  search: "",
  status: "",
};

let currentRoute = routeFromPathname(window.location.pathname);
let loadSequence = 0;
let conversationSequence = 0;
let turnsSequence = 0;
let pollSequence = 0;
let connectionSequence = 0;
let missionNotice: MissionNotice | null = null;
let projectNotice: MissionNotice | null = null;
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

const appRoot = document.getElementById("app");
if (!appRoot) throw new Error("Le conteneur #app est absent.");
const root: HTMLElement = appRoot;

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
const userLabel = el("span", "workspace-user");
const logoutButton = el("button", "icon-button", "Se déconnecter");
logoutButton.type = "button";
logoutButton.addEventListener("click", () => void logout());
topbarActions.append(apiStatus, refreshButton, themeButton, userLabel, logoutButton);
topbar.append(topbarTitles, topbarActions);

const content = el("div", "workspace-content");
content.id = "workspace-content";
content.tabIndex = -1;
main.append(topbar, content);

function mountWorkspaceShell(): void {
  root.replaceChildren(skipLink, sidebar, main);
  const user = authState.session?.user;
  userLabel.textContent = user ? user.display_name : "";
  userLabel.title = user ? `${user.login} · ${user.role}` : "";
}

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

function authThemeButton(): HTMLButtonElement {
  const button = el(
    "button",
    "auth-theme-button",
    document.documentElement.dataset.theme === "dark" ? "Thème clair" : "Thème sombre",
  );
  button.type = "button";
  button.addEventListener("click", () => {
    const next: Theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next, true);
    renderAuthGate();
  });
  return button;
}

function authIntro(title: string, description: string): HTMLElement {
  const header = el("header", "auth-header");
  header.append(
    el("span", "workspace-mark", "AC"),
    el("p", "workspace-eyebrow", "Agent Company Platform"),
    el("h1", "auth-title", title),
    el("p", "auth-description", description),
  );
  return header;
}

function authFeedback(): HTMLElement {
  const feedback = el("div", "form-feedback auth-feedback");
  feedback.setAttribute("role", "status");
  feedback.setAttribute("aria-live", "polite");
  if (authState.error) {
    feedback.dataset.tone = "error";
    feedback.textContent = errorMessage(authState.error);
  }
  return feedback;
}

function createLoginForm(): HTMLFormElement {
  const form = el("form", "auth-form");
  const login = el("input", "form-control") as HTMLInputElement;
  login.name = "login";
  login.required = true;
  login.autocomplete = "username";
  login.maxLength = 120;

  const password = el("input", "form-control") as HTMLInputElement;
  password.name = "password";
  password.type = "password";
  password.required = true;
  password.minLength = 12;
  password.maxLength = 256;
  password.autocomplete = "current-password";

  const feedback = authFeedback();
  const submit = el("button", "button button-primary", "Se connecter") as HTMLButtonElement;
  submit.type = "submit";
  form.append(
    labeledField("Identifiant", login),
    labeledField("Mot de passe", password),
    feedback,
    submit,
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const input: LoginInput = { login: login.value, password: password.value };
    submit.disabled = true;
    submit.textContent = "Connexion…";
    feedback.dataset.tone = "pending";
    feedback.textContent = "Vérification de la session propriétaire…";
    authState.error = null;
    try {
      completeAuthentication(await authApi.login(input));
    } catch (error) {
      authState.error = normalizeApiError(error, "Connexion impossible.");
      feedback.dataset.tone = "error";
      feedback.textContent = errorMessage(authState.error);
      submit.disabled = false;
      submit.textContent = "Se connecter";
      password.focus();
      password.select();
    }
  });
  return form;
}

function createBootstrapForm(): HTMLFormElement {
  const form = el("form", "auth-form");
  const displayName = el("input", "form-control") as HTMLInputElement;
  displayName.name = "displayName";
  displayName.required = true;
  displayName.autocomplete = "name";
  displayName.maxLength = 120;

  const login = el("input", "form-control") as HTMLInputElement;
  login.name = "login";
  login.required = true;
  login.autocomplete = "username";
  login.maxLength = 120;

  const password = el("input", "form-control") as HTMLInputElement;
  password.name = "password";
  password.type = "password";
  password.required = true;
  password.minLength = 12;
  password.maxLength = 256;
  password.autocomplete = "new-password";

  const confirmation = password.cloneNode() as HTMLInputElement;
  confirmation.name = "passwordConfirmation";

  const bootstrapToken = el("input", "form-control") as HTMLInputElement;
  bootstrapToken.name = "bootstrapToken";
  bootstrapToken.type = "password";
  bootstrapToken.required = true;
  bootstrapToken.autocomplete = "off";
  bootstrapToken.setAttribute("aria-describedby", "bootstrap-token-hint");

  const tokenField = labeledField(
    "Jeton d’initialisation",
    bootstrapToken,
    "Utilise le secret ACP_BOOTSTRAP_TOKEN fourni directement par l’administrateur. Il n’est pas conservé dans le navigateur.",
  );
  tokenField.querySelector(".form-hint")!.id = "bootstrap-token-hint";

  const feedback = authFeedback();
  const submit = el("button", "button button-primary", "Créer l’accès propriétaire") as HTMLButtonElement;
  submit.type = "submit";
  form.append(
    labeledField("Nom affiché", displayName),
    labeledField("Identifiant", login),
    labeledField("Mot de passe", password, "12 caractères minimum."),
    labeledField("Confirmer le mot de passe", confirmation),
    tokenField,
    feedback,
    submit,
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    if (password.value !== confirmation.value) {
      confirmation.setCustomValidity("Les mots de passe ne correspondent pas.");
      confirmation.reportValidity();
      confirmation.addEventListener("input", () => confirmation.setCustomValidity(""), { once: true });
      return;
    }
    const input: BootstrapInput = {
      login: login.value,
      displayName: displayName.value,
      password: password.value,
      bootstrapToken: bootstrapToken.value,
    };
    submit.disabled = true;
    submit.textContent = "Sécurisation…";
    feedback.dataset.tone = "pending";
    feedback.textContent = "Création atomique du premier accès…";
    authState.error = null;
    try {
      completeAuthentication(await authApi.bootstrap(input));
    } catch (error) {
      authState.error = normalizeApiError(error, "Initialisation impossible.");
      feedback.dataset.tone = "error";
      feedback.textContent = errorMessage(authState.error);
      submit.disabled = false;
      submit.textContent = "Créer l’accès propriétaire";
      bootstrapToken.value = "";
      bootstrapToken.focus();
    }
  });
  return form;
}

function renderAuthGate(): void {
  const shell = el("main", "auth-shell");
  const card = el("section", "auth-card");
  const theme = authThemeButton();
  shell.append(theme, card);
  if (authState.phase === "checking") {
    card.append(
      authIntro("Vérification de l’accès", "La plateforme vérifie si un propriétaire existe et recherche une session sécurisée."),
      statePanel("loading", "Connexion en cours", "Aucune donnée métier n’est chargée avant authentification."),
    );
  } else if (authState.phase === "bootstrap") {
    card.append(
      authIntro("Sécuriser le premier accès", "Crée l’unique accès propriétaire initial. L’inscription publique reste fermée."),
      createBootstrapForm(),
    );
  } else if (authState.phase === "login") {
    card.append(
      authIntro("Retrouver ton espace", "Connecte-toi avec le compte propriétaire déjà initialisé."),
      createLoginForm(),
    );
  } else {
    const offline = authState.phase === "offline";
    card.append(
      authIntro("Accès indisponible", "La vérification de sécurité n’a pas pu aboutir."),
      statePanel(
        offline ? "offline" : "error",
        offline ? "API hors ligne" : "Réponse d’authentification invalide",
        authState.error ? errorMessage(authState.error) : "La plateforme ne peut pas déterminer l’état de l’accès.",
      ),
    );
    const retry = el("button", "button button-primary auth-retry", "Réessayer") as HTMLButtonElement;
    retry.type = "button";
    retry.addEventListener("click", () => void initializeAuthentication());
    card.append(retry);
  }
  root.replaceChildren(shell);
}

function normalizeApiError(error: unknown, fallback: string): WorkspaceApiError {
  return error instanceof WorkspaceApiError
    ? error
    : new WorkspaceApiError(fallback, "invalid_response");
}

function resetPrivateWorkspaceState(): void {
  state.phase = "loading";
  state.overview = null;
  state.events = [];
  state.approvals = [];
  state.onboarding = null;
  state.primaryError = null;
  state.eventsError = null;
  state.approvalsError = null;
  state.onboardingError = null;
  conversationState.phase = "idle";
  conversationState.items = [];
  conversationState.error = null;
  conversationState.activeId = null;
  conversationState.turnsPhase = "idle";
  conversationState.turns = [];
  conversationState.turnsError = null;
  conversationState.notice = null;
  connectionState.phase = "idle";
  connectionState.diagnostic = null;
  connectionState.error = null;
  conversationDrafts.clear();
  newConversationDraft.projectId = "";
  newConversationDraft.title = "";
  newProjectDraft.name = "";
  newProjectDraft.description = "";
  missionNotice = null;
  projectNotice = null;
}

function completeAuthentication(session: AuthSession): void {
  resetPrivateWorkspaceState();
  authState.phase = "authenticated";
  authState.session = session;
  authState.error = null;
  logoutButton.disabled = false;
  logoutButton.textContent = "Se déconnecter";
  logoutButton.removeAttribute("title");
  mountWorkspaceShell();
  updateConnectionStatus();
  renderCurrentRoute();
  void loadWorkspaceData();
}

function requireLogin(): void {
  ++loadSequence;
  ++conversationSequence;
  ++turnsSequence;
  ++pollSequence;
  ++connectionSequence;
  authApi.clearLocalSession();
  resetPrivateWorkspaceState();
  authState.phase = "login";
  authState.session = null;
  authState.error = null;
  renderAuthGate();
}

async function initializeAuthentication(): Promise<void> {
  authState.phase = "checking";
  authState.error = null;
  renderAuthGate();
  try {
    const status = await authApi.fetchStatus();
    if (status.bootstrap_required) {
      authState.phase = "bootstrap";
      renderAuthGate();
      return;
    }
    try {
      completeAuthentication(await authApi.fetchSession());
    } catch (error) {
      const apiError = normalizeApiError(error, "Session impossible à vérifier.");
      if (apiError.status === 401) {
        authState.phase = "login";
        authState.error = null;
      } else {
        authState.phase = apiError.kind === "offline" ? "offline" : "error";
        authState.error = apiError;
      }
      renderAuthGate();
    }
  } catch (error) {
    const apiError = normalizeApiError(error, "État d’authentification impossible à vérifier.");
    authState.phase = apiError.kind === "offline" ? "offline" : "error";
    authState.error = apiError;
    renderAuthGate();
  }
}

async function logout(): Promise<void> {
  logoutButton.disabled = true;
  logoutButton.textContent = "Déconnexion…";
  try {
    await authApi.logout();
    requireLogin();
  } catch (error) {
    const apiError = normalizeApiError(error, "Déconnexion impossible.");
    logoutButton.disabled = false;
    logoutButton.textContent = "Réessayer la déconnexion";
    logoutButton.title = errorMessage(apiError);
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
    return error.status === 401
      ? "La session a expiré ou n’est plus valide. Reconnecte-toi pour continuer."
      : "Le compte courant n’a pas accès à cette ressource.";
  }
  return error.message;
}

function updateConnectionStatus(): void {
  let label = "Connexion en cours";
  let tone = "pending";
  if (state.phase === "ready") {
    const partial = Boolean(state.eventsError || state.approvalsError || state.onboardingError);
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
  state.onboardingError = null;
  updateConnectionStatus();
  renderCurrentRoute();

  const [overviewResult, eventsResult, approvalsResult, onboardingResult] = await Promise.allSettled([
    api.fetchOverview(),
    api.fetchRecentEvents(),
    api.fetchPendingApprovals(),
    api.fetchOnboardingStatus(),
  ]);
  if (sequence !== loadSequence) return;

  if (overviewResult.status === "rejected") {
    const error = overviewResult.reason instanceof WorkspaceApiError
      ? overviewResult.reason
      : new WorkspaceApiError("Impossible de charger l’espace de travail.", "offline");
    if (error.status === 401) {
      requireLogin();
      return;
    }
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

  if (onboardingResult.status === "fulfilled") {
    state.onboarding = onboardingResult.value;
  } else {
    state.onboarding = null;
    state.onboardingError = onboardingResult.reason instanceof WorkspaceApiError
      ? onboardingResult.reason
      : new WorkspaceApiError("Progression de l’onboarding indisponible.", "offline");
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

function onboardingStep(label: string, complete: boolean, detail: string): HTMLElement {
  const item = el("li", "onboarding-step");
  item.dataset.complete = String(complete);
  item.append(
    el("span", "onboarding-step-mark", complete ? "✓" : "○"),
    el("strong", "", label),
    el("span", "", detail),
  );
  return item;
}

function renderOnboardingProgress(): HTMLElement {
  const section = el("section", "content-section onboarding-section");
  const header = sectionHeader(
    "Mise en route",
    "Cette progression vient de l’API et reste disponible après reconnexion.",
  );
  section.append(header);
  if (state.onboardingError || !state.onboarding) {
    section.append(statePanel(
      state.onboardingError?.kind === "offline" ? "offline" : "error",
      "Progression indisponible",
      state.onboardingError
        ? errorMessage(state.onboardingError)
        : "Aucun état d’onboarding exploitable n’a été retourné.",
    ));
    return section;
  }
  const progress = state.onboarding;
  const steps = el("ol", "onboarding-steps");
  steps.append(
    onboardingStep("Accès propriétaire", progress.bootstrap_completed, progress.bootstrap_completed ? "Sécurisé" : "À terminer"),
    onboardingStep(
      "Hermes",
      progress.hermes_ready,
      progress.hermes_ready
        ? "Connecté"
        : progress.hermes_configured
          ? `Configuré · ${progress.hermes_status}`
          : "Configuration requise",
    ),
    onboardingStep(
      "Premier projet",
      progress.project_count > 0,
      progress.project_count > 0 ? `${progress.project_count} projet(s)` : "Aucun projet",
    ),
    onboardingStep("Runner", progress.runner_ready, progress.runner_ready ? "Disponible" : "Aucun runner prêt"),
  );
  const actions = el("div", "workspace-actions onboarding-actions");
  if (!progress.hermes_ready) actions.append(routeLink("/connections", "Diagnostiquer Hermes"));
  if (progress.project_count === 0) actions.append(routeLink("/projects", "Ajouter le premier projet", "button button-primary"));
  if (!progress.runner_ready) {
    const runner = capabilityTag("Connecter un runner", "L’enrôlement de runner n’est pas livré dans ce lot.");
    actions.append(runner);
  }
  section.append(steps);
  if (actions.childElementCount) section.append(actions);
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
    routeLink("/conversations", "Ouvrir une conversation"),
  );
  const disabledActions = el("div", "disabled-actions");
  disabledActions.append(
    capabilityTag("Automatiser", "Planificateur non configuré"),
    capabilityTag("Parcourir les livrables", "Bibliothèque sécurisée non configurée"),
  );
  heroCopy.append(heroActions, disabledActions);
  hero.append(heroCopy);
  content.append(hero, renderOnboardingProgress());

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

function createOnboardingProjectForm(): HTMLFormElement {
  const form = el("form", "project-create-form");
  const name = el("input", "form-control") as HTMLInputElement;
  name.required = true;
  name.maxLength = 160;
  name.placeholder = "Ex. Site personnel";
  name.value = newProjectDraft.name;
  name.addEventListener("input", () => { newProjectDraft.name = name.value; });

  const type = el("select", "form-control") as HTMLSelectElement;
  for (const [value, label] of [
    ["generic", "Général"],
    ["software", "Développement logiciel"],
    ["research", "Recherche"],
    ["data-science", "Données"],
  ]) {
    const option = el("option", "", label) as HTMLOptionElement;
    option.value = value;
    type.append(option);
  }
  type.value = newProjectDraft.projectType;
  type.addEventListener("change", () => { newProjectDraft.projectType = type.value; });

  const description = el("textarea", "form-control form-textarea compact") as HTMLTextAreaElement;
  description.maxLength = 2_000;
  description.rows = 3;
  description.placeholder = "Objectif et périmètre du projet";
  description.value = newProjectDraft.description;
  description.addEventListener("input", () => { newProjectDraft.description = description.value; });

  const feedback = el("div", "form-feedback");
  feedback.setAttribute("aria-live", "polite");
  if (projectNotice) {
    feedback.dataset.tone = projectNotice.tone;
    feedback.textContent = projectNotice.message;
  }
  const submit = el("button", "button button-primary", "Ajouter le projet") as HTMLButtonElement;
  submit.type = "submit";
  const split = el("div", "form-split");
  split.append(labeledField("Nom", name), labeledField("Type", type));
  form.append(split, labeledField("Description", description), feedback, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const input: OnboardingProjectInput = {
      name: name.value,
      projectType: type.value,
      description: description.value,
    };
    submit.disabled = true;
    feedback.dataset.tone = "pending";
    feedback.textContent = "Création de l’espace personnel et du projet si nécessaire…";
    try {
      const project = await api.createOnboardingProject(input);
      projectNotice = { tone: "success", message: `Projet « ${project.name} » créé.` };
      newProjectDraft.name = "";
      newProjectDraft.description = "";
      await loadWorkspaceData();
    } catch (error) {
      const apiError = normalizeApiError(error, "Le projet n’a pas pu être créé.");
      if (apiError.status === 401) return requireLogin();
      projectNotice = { tone: "error", message: errorMessage(apiError) };
      feedback.dataset.tone = "error";
      feedback.textContent = projectNotice.message;
      submit.disabled = false;
    }
  });
  return form;
}

function renderProjects(overview: Overview): void {
  const intro = el("section", "page-intro");
  intro.append(
    el("p", "workspace-eyebrow", "Contexte autorisé"),
    el("h2", "page-title", "Projets"),
    el("p", "page-description", "Projets retournés par l’instantané métier. Aucun dépôt supplémentaire n’est importé automatiquement."),
  );
  content.append(intro);
  const canCreate = authState.session?.user.role === "owner";
  const creator = el("section", "content-section project-creator");
  creator.append(sectionHeader(
    "Ajouter un projet",
    "La plateforme crée ou réutilise l’organisation et l’espace personnel côté serveur.",
  ));
  creator.append(canCreate
    ? createOnboardingProjectForm()
    : statePanel("forbidden", "Droit propriétaire requis", "Ce compte peut consulter les projets, mais pas initialiser un nouvel espace."));
  content.append(creator);
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

function conversationStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: "Active",
    archived: "Archivée",
    submitting: "Envoi",
    running: "Hermes travaille",
    completed: "Terminée",
    failed: "Échec",
    interrupted: "Interrompue",
  };
  return labels[status] ?? status;
}

function conversationTone(status: string): string {
  if (status === "active" || status === "completed") return "active";
  if (status === "submitting" || status === "running") return "waiting";
  if (status === "failed") return "failed";
  if (status === "interrupted") return "blocked";
  return "neutral";
}

function renderConversationList(overview: Overview): HTMLElement {
  const section = el("section", "content-section conversation-sidebar");
  const header = sectionHeader(
    "Conversations enregistrées",
    "Une conversation générale reste privée ; une conversation projet suit ses droits d’accès.",
  );
  const reload = el("button", "button button-secondary", "Actualiser") as HTMLButtonElement;
  reload.type = "button";
  reload.disabled = conversationState.phase === "loading";
  reload.addEventListener("click", () => void loadConversations());
  header.append(reload);
  section.append(header, createConversationForm(overview), createConversationFilterForm());

  if (conversationState.phase === "loading" || conversationState.phase === "idle") {
    section.append(statePanel("loading", "Chargement", "Lecture de l’historique persistant…"));
    return section;
  }
  if (conversationState.phase === "error") {
    section.append(statePanel(
      conversationState.error?.kind === "offline" ? "offline" : "error",
      "Conversations indisponibles",
      conversationState.error ? errorMessage(conversationState.error) : "La réponse reçue est inexploitable.",
    ));
    return section;
  }
  if (!conversationState.items.length) {
    section.append(statePanel(
      "empty",
      "Aucune conversation",
      "Crée une conversation générale ou rattache-la explicitement à un projet.",
    ));
    return section;
  }

  const list = el("div", "conversation-list");
  for (const conversation of conversationState.items) {
    const button = el("button", "conversation-list-item") as HTMLButtonElement;
    button.type = "button";
    button.dataset.active = String(conversation.id === conversationState.activeId);
    if (conversation.id === conversationState.activeId) button.setAttribute("aria-current", "true");
    const project = conversation.project_id
      ? projectName(overview, conversation.project_id)
      : "Conversation générale";
    button.append(
      el("span", "conversation-list-title", conversation.title || "Conversation sans titre"),
      el("span", "conversation-list-meta", `${project} · ${formatDateTime(conversation.updated_at)}`),
      statusChip(conversationStatusLabel(conversation.status), conversationTone(conversation.status)),
    );
    button.addEventListener("click", () => selectConversation(conversation.id));
    list.append(button);
  }
  section.append(list);
  return section;
}

function createConversationFilterForm(): HTMLFormElement {
  const form = el("form", "conversation-filter-form");
  form.setAttribute("role", "search");
  const search = el("input", "form-control") as HTMLInputElement;
  search.type = "search";
  search.maxLength = 200;
  search.placeholder = "Rechercher un titre";
  search.setAttribute("aria-label", "Rechercher une conversation");
  search.value = conversationFilters.search;

  const status = el("select", "form-control") as HTMLSelectElement;
  status.setAttribute("aria-label", "Filtrer par état");
  for (const [value, label] of [["", "Toutes"], ["active", "Actives"], ["archived", "Archivées"]]) {
    const option = el("option", "", label) as HTMLOptionElement;
    option.value = value;
    status.append(option);
  }
  status.value = conversationFilters.status;
  const submit = el("button", "button button-secondary", "Filtrer") as HTMLButtonElement;
  submit.type = "submit";
  form.append(search, status, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    conversationFilters.search = search.value;
    conversationFilters.status = status.value as typeof conversationFilters.status;
    void loadConversations();
  });
  return form;
}

function createConversationForm(overview: Overview): HTMLFormElement {
  const form = el("form", "conversation-create-form");
  const project = el("select", "form-control") as HTMLSelectElement;
  const general = el("option", "", "Conversation générale") as HTMLOptionElement;
  general.value = "";
  project.append(general);
  for (const item of overview.projects) {
    const option = el("option", "", item.name) as HTMLOptionElement;
    option.value = item.id;
    project.append(option);
  }
  project.value = newConversationDraft.projectId;
  project.addEventListener("change", () => { newConversationDraft.projectId = project.value; });

  const title = el("input", "form-control") as HTMLInputElement;
  title.maxLength = 160;
  title.placeholder = "Titre facultatif";
  title.value = newConversationDraft.title;
  title.addEventListener("input", () => { newConversationDraft.title = title.value; });

  const submit = el("button", "button button-primary", "Nouvelle conversation") as HTMLButtonElement;
  submit.type = "submit";
  const feedback = el("div", "form-feedback");
  feedback.setAttribute("aria-live", "polite");
  if (conversationState.notice) {
    feedback.dataset.tone = conversationState.notice.tone;
    feedback.textContent = conversationState.notice.message;
  }

  const fields = el("div", "conversation-create-fields");
  fields.append(
    labeledField("Portée", project),
    labeledField("Titre", title),
  );
  form.append(fields, feedback, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    feedback.dataset.tone = "pending";
    feedback.textContent = "Création de la conversation…";
    try {
      const created = await conversationApi.createConversation({
        projectId: project.value || null,
        title: title.value,
      });
      conversationState.items = [created, ...conversationState.items.filter((item) => item.id !== created.id)];
      conversationState.phase = "ready";
      conversationState.activeId = created.id;
      conversationState.turns = [];
      conversationState.turnsPhase = "ready";
      conversationState.turnsError = null;
      conversationState.notice = { tone: "success", message: "Conversation enregistrée." };
      newConversationDraft.title = "";
      renderCurrentRoute();
    } catch (error) {
      const apiError = normalizeApiError(error, "La conversation n’a pas pu être créée.");
      if (apiError.status === 401) return requireLogin();
      conversationState.notice = { tone: "error", message: errorMessage(apiError) };
      feedback.dataset.tone = "error";
      feedback.textContent = conversationState.notice.message;
      submit.disabled = false;
    }
  });
  return form;
}

function renderConversationTurn(turn: ConversationTurn): HTMLElement {
  const article = el("article", "conversation-turn");
  article.dataset.status = turn.status;
  const meta = el("div", "conversation-turn-meta");
  const time = el("time", "", formatDateTime(turn.created_at));
  time.dateTime = turn.created_at;
  meta.append(time, statusChip(conversationStatusLabel(turn.status), conversationTone(turn.status)));

  const userMessage = el("section", "conversation-message conversation-message-user");
  userMessage.append(el("h4", "conversation-speaker", "Vous"), el("p", "conversation-copy", turn.user_content));
  article.append(meta, userMessage);

  if (turn.assistant_content) {
    const assistant = el("section", "conversation-message conversation-message-assistant");
    assistant.append(el("h4", "conversation-speaker", "Hermes"), el("p", "conversation-copy", turn.assistant_content));
    article.append(assistant);
  } else if (turn.status === "submitting" || turn.status === "running") {
    article.append(el(
      "p",
      "conversation-pending",
      turn.status === "submitting" ? "Le message est accepté par la plateforme…" : "Hermes traite ce tour…",
    ));
  }
  if (turn.error) article.append(el("p", "conversation-error", turn.error));
  return article;
}

function replaceConversation(updated: ConversationSummary): void {
  conversationState.items = conversationState.items.map((item) => item.id === updated.id ? updated : item);
}

async function renameConversation(conversation: ConversationSummary): Promise<void> {
  const title = window.prompt("Nouveau titre de la conversation", conversation.title)?.trim();
  if (!title || title === conversation.title) return;
  try {
    replaceConversation(await conversationApi.updateConversation(conversation.id, { title }));
    conversationState.notice = { tone: "success", message: "Conversation renommée." };
  } catch (error) {
    const apiError = normalizeApiError(error, "La conversation n’a pas pu être renommée.");
    if (apiError.status === 401) return requireLogin();
    conversationState.notice = { tone: "error", message: errorMessage(apiError) };
  }
  renderCurrentRoute();
}

async function toggleConversationArchive(conversation: ConversationSummary): Promise<void> {
  const status = conversation.status === "archived" ? "active" : "archived";
  try {
    const updated = await conversationApi.updateConversation(conversation.id, { status });
    replaceConversation(updated);
    conversationState.notice = {
      tone: "success",
      message: status === "archived" ? "Conversation archivée." : "Conversation réactivée.",
    };
    ++pollSequence;
  } catch (error) {
    const apiError = normalizeApiError(error, "L’état de la conversation n’a pas pu être modifié.");
    if (apiError.status === 401) return requireLogin();
    conversationState.notice = { tone: "error", message: errorMessage(apiError) };
  }
  renderCurrentRoute();
}

async function exportConversation(conversation: ConversationSummary): Promise<void> {
  try {
    const exported = await conversationApi.exportConversation(conversation.id);
    const blob = new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const download = el("a");
    const safeTitle = (conversation.title || "conversation")
      .normalize("NFKD")
      .replace(/[^a-zA-Z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase() || "conversation";
    download.href = url;
    download.download = `${safeTitle}.json`;
    download.hidden = true;
    document.body.append(download);
    download.click();
    download.remove();
    globalThis.setTimeout(() => URL.revokeObjectURL(url), 0);
    conversationState.notice = { tone: "success", message: "Export JSON préparé localement." };
  } catch (error) {
    const apiError = normalizeApiError(error, "L’export n’a pas pu être préparé.");
    if (apiError.status === 401) return requireLogin();
    conversationState.notice = { tone: "error", message: errorMessage(apiError) };
  }
  renderCurrentRoute();
}

function renderActiveConversation(overview: Overview): HTMLElement {
  const section = el("section", "content-section conversation-thread");
  const conversation = conversationState.items.find((item) => item.id === conversationState.activeId);
  if (!conversation) {
    section.append(statePanel(
      "empty",
      "Choisis une conversation",
      "L’historique et le formulaire de message apparaîtront ici.",
    ));
    return section;
  }

  const scope = conversation.project_id ? projectName(overview, conversation.project_id) : "Privée · générale";
  const header = sectionHeader(conversation.title || "Conversation sans titre", scope);
  const actions = el("div", "conversation-actions");
  const rename = el("button", "button button-secondary", "Renommer") as HTMLButtonElement;
  rename.type = "button";
  rename.addEventListener("click", () => void renameConversation(conversation));
  const archive = el(
    "button",
    "button button-secondary",
    conversation.status === "archived" ? "Réactiver" : "Archiver",
  ) as HTMLButtonElement;
  archive.type = "button";
  archive.addEventListener("click", () => void toggleConversationArchive(conversation));
  const exportButton = el("button", "button button-secondary", "Exporter") as HTMLButtonElement;
  exportButton.type = "button";
  exportButton.addEventListener("click", () => void exportConversation(conversation));
  actions.append(rename, archive, exportButton);
  header.append(actions);
  section.append(header);
  if (conversationState.turnsPhase === "idle") {
    conversationState.turnsPhase = "loading";
    queueMicrotask(() => void loadConversationTurns(conversation.id));
  }
  if (conversationState.turnsPhase === "loading") {
    section.append(statePanel("loading", "Historique en cours", "Lecture des tours enregistrés…"));
  } else if (conversationState.turnsPhase === "error") {
    const retry = el("button", "button button-secondary", "Réessayer") as HTMLButtonElement;
    retry.type = "button";
    retry.addEventListener("click", () => void loadConversationTurns(conversation.id));
    section.append(
      statePanel(
        conversationState.turnsError?.kind === "offline" ? "offline" : "error",
        "Historique indisponible",
        conversationState.turnsError
          ? errorMessage(conversationState.turnsError)
          : "Impossible de lire les tours de cette conversation.",
      ),
      retry,
    );
  } else {
    const log = el("div", "conversation-turns");
    log.setAttribute("aria-live", "polite");
    if (!conversationState.turns.length) {
      log.append(statePanel("empty", "Conversation vide", "Écris le premier message. Aucun contenu de démonstration n’est injecté."));
    } else {
      for (const turn of conversationState.turns) log.append(renderConversationTurn(turn));
    }
    section.append(log);
    if (conversation.status === "active") {
      section.append(createTurnForm(conversation));
    } else {
      section.append(statePanel(
        "unconfigured",
        "Conversation archivée",
        "Réactive-la pour envoyer un nouveau message. Son historique reste consultable et exportable.",
      ));
    }
  }
  return section;
}

function createTurnForm(conversation: ConversationSummary): HTMLFormElement {
  const form = el("form", "conversation-composer");
  const textarea = el("textarea", "form-control form-textarea") as HTMLTextAreaElement;
  textarea.required = true;
  textarea.rows = 5;
  textarea.maxLength = 20_000;
  textarea.placeholder = "Décris ce que tu veux demander à Hermes…";
  textarea.value = conversationDrafts.get(conversation.id) ?? "";
  textarea.addEventListener("input", () => conversationDrafts.set(conversation.id, textarea.value));

  const feedback = el("div", "form-feedback");
  feedback.setAttribute("aria-live", "polite");
  if (conversationState.notice) {
    feedback.dataset.tone = conversationState.notice.tone;
    feedback.textContent = conversationState.notice.message;
  }
  const submit = el("button", "button button-primary", "Envoyer à Hermes") as HTMLButtonElement;
  submit.type = "submit";
  form.append(
    labeledField("Message", textarea, "Le brouillon reste présent tant que l’API n’a pas accepté le tour."),
    feedback,
    submit,
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const contentValue = textarea.value.trim();
    if (!contentValue) return;
    conversationDrafts.set(conversation.id, textarea.value);
    submit.disabled = true;
    feedback.dataset.tone = "pending";
    feedback.textContent = "Envoi durable du message…";
    const clientRequestId = globalThis.crypto.randomUUID();
    try {
      const turn = await conversationApi.createTurn({
        conversationId: conversation.id,
        clientRequestId,
        content: contentValue,
      });
      conversationDrafts.delete(conversation.id);
      conversationState.turns = [
        ...conversationState.turns.filter((item) => item.id !== turn.id),
        turn,
      ];
      conversationState.notice = isTerminalConversationTurn(turn.status)
        ? null
        : { tone: "success", message: "Message accepté. Suivi du traitement en cours." };
      renderCurrentRoute();
      if (!isTerminalConversationTurn(turn.status)) void pollConversationTurn(conversation.id, turn.id);
    } catch (error) {
      const apiError = normalizeApiError(error, "Le message n’a pas pu être envoyé.");
      if (apiError.status === 401) return requireLogin();
      conversationState.notice = { tone: "error", message: errorMessage(apiError) };
      feedback.dataset.tone = "error";
      feedback.textContent = conversationState.notice.message;
      submit.disabled = false;
    }
  });
  return form;
}

function selectConversation(conversationId: string): void {
  if (conversationState.activeId === conversationId && conversationState.turnsPhase === "ready") return;
  ++turnsSequence;
  ++pollSequence;
  conversationState.activeId = conversationId;
  conversationState.turns = [];
  conversationState.turnsPhase = "idle";
  conversationState.turnsError = null;
  conversationState.notice = null;
  renderCurrentRoute();
}

async function loadConversations(): Promise<void> {
  const sequence = ++conversationSequence;
  conversationState.phase = "loading";
  conversationState.error = null;
  if (currentRoute === "conversations") renderCurrentRoute();
  try {
    const conversations = await conversationApi.listConversations({
      search: conversationFilters.search,
      status: conversationFilters.status || undefined,
    });
    if (sequence !== conversationSequence) return;
    conversationState.items = conversations;
    conversationState.phase = "ready";
    if (!conversations.some((item) => item.id === conversationState.activeId)) {
      conversationState.activeId = conversations[0]?.id ?? null;
      conversationState.turns = [];
      conversationState.turnsPhase = "idle";
      conversationState.turnsError = null;
    }
  } catch (error) {
    if (sequence !== conversationSequence) return;
    const apiError = normalizeApiError(error, "Les conversations n’ont pas pu être chargées.");
    if (apiError.status === 401) return requireLogin();
    conversationState.phase = "error";
    conversationState.error = apiError;
  }
  if (currentRoute === "conversations") renderCurrentRoute();
}

async function loadConversationTurns(conversationId: string): Promise<void> {
  const sequence = ++turnsSequence;
  conversationState.turnsPhase = "loading";
  conversationState.turnsError = null;
  if (currentRoute === "conversations") renderCurrentRoute();
  try {
    const turns = await conversationApi.listTurns(conversationId);
    if (sequence !== turnsSequence || conversationState.activeId !== conversationId) return;
    conversationState.turns = turns;
    conversationState.turnsPhase = "ready";
    for (const turn of turns) {
      if (!isTerminalConversationTurn(turn.status)) {
        void pollConversationTurn(conversationId, turn.id);
      }
    }
  } catch (error) {
    if (sequence !== turnsSequence || conversationState.activeId !== conversationId) return;
    const apiError = normalizeApiError(error, "L’historique n’a pas pu être chargé.");
    if (apiError.status === 401) return requireLogin();
    conversationState.turnsPhase = "error";
    conversationState.turnsError = apiError;
  }
  if (currentRoute === "conversations") renderCurrentRoute();
}

function waitForPoll(milliseconds: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}

async function pollConversationTurn(conversationId: string, turnId: string): Promise<void> {
  const sequence = pollSequence;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await waitForPoll(attempt < 5 ? 1_000 : 2_000);
    if (
      sequence !== pollSequence
      || conversationState.activeId !== conversationId
      || currentRoute !== "conversations"
    ) return;
    try {
      const turn = await conversationApi.fetchTurn(conversationId, turnId);
      if (sequence !== pollSequence) return;
      conversationState.turns = conversationState.turns.map((item) => item.id === turn.id ? turn : item);
      conversationState.notice = null;
      renderCurrentRoute();
      if (isTerminalConversationTurn(turn.status)) return;
    } catch (error) {
      const apiError = normalizeApiError(error, "Le suivi du tour a été interrompu.");
      if (apiError.status === 401) return requireLogin();
      conversationState.notice = {
        tone: "warning",
        message: `Suivi interrompu : ${errorMessage(apiError)} Le traitement peut encore continuer côté Hermes.`,
      };
      renderCurrentRoute();
      return;
    }
  }
  conversationState.notice = {
    tone: "warning",
    message: "Le suivi automatique a atteint sa limite. Actualise la conversation pour réconcilier son état réel.",
  };
  if (currentRoute === "conversations") renderCurrentRoute();
}

function renderConversations(overview: Overview): void {
  const intro = el("section", "page-intro");
  intro.append(
    el("p", "workspace-eyebrow", "Historique durable"),
    el("h2", "page-title", "Conversations"),
    el(
      "p",
      "page-description",
      "Les messages sont persistés par la plateforme puis traduits vers un run Hermes. Un état incomplet n’est jamais présenté comme une réponse réussie.",
    ),
  );
  content.append(intro);
  if (conversationState.phase === "idle") {
    conversationState.phase = "loading";
    queueMicrotask(() => void loadConversations());
  }
  const layout = el("div", "conversation-layout");
  layout.append(renderConversationList(overview), renderActiveConversation(overview));
  content.append(layout);
}

function diagnosticLabel(diagnostic: HermesDiagnostic): string {
  if (diagnostic.status === "connected" && diagnostic.healthy) return "Connecté";
  if (diagnostic.status === "degraded") return "Dégradé";
  return "Indisponible";
}

async function loadHermesDiagnostic(force: boolean): Promise<void> {
  const sequence = ++connectionSequence;
  connectionState.phase = "loading";
  connectionState.error = null;
  if (currentRoute === "connections") renderCurrentRoute();
  try {
    const diagnostic = force
      ? await conversationApi.runHermesDiagnostic()
      : await conversationApi.fetchHermesDiagnostic();
    if (sequence !== connectionSequence) return;
    connectionState.diagnostic = diagnostic;
    connectionState.phase = "ready";
  } catch (error) {
    if (sequence !== connectionSequence) return;
    const apiError = normalizeApiError(error, "Le diagnostic Hermes n’a pas pu être obtenu.");
    if (apiError.status === 401) return requireLogin();
    connectionState.diagnostic = null;
    connectionState.phase = "error";
    connectionState.error = apiError;
  }
  if (currentRoute === "connections") renderCurrentRoute();
}

function renderConnections(): void {
  const intro = el("section", "page-intro");
  intro.append(
    el("p", "workspace-eyebrow", "Services raccordés"),
    el("h2", "page-title", "Connexions"),
    el(
      "p",
      "page-description",
      "Les diagnostics affichent uniquement l’état mesuré par l’API. Une configuration absente reste visible comme telle.",
    ),
  );
  content.append(intro);

  if (connectionState.phase === "idle") {
    connectionState.phase = "loading";
    queueMicrotask(() => void loadHermesDiagnostic(false));
  }
  const section = el("section", "content-section");
  const header = sectionHeader("Hermes Agent", "Moteur agentique principal, exécuté comme service séparé.");
  const check = el("button", "button button-primary", "Relancer le diagnostic") as HTMLButtonElement;
  check.type = "button";
  check.disabled = connectionState.phase === "loading";
  check.addEventListener("click", () => void loadHermesDiagnostic(true));
  header.append(check);
  section.append(header);

  if (connectionState.phase === "loading") {
    section.append(statePanel("loading", "Diagnostic en cours", "Vérification de la santé et des capacités exposées par Hermes…"));
  } else if (connectionState.phase === "error" || !connectionState.diagnostic) {
    section.append(statePanel(
      connectionState.error?.kind === "offline" ? "offline" : "error",
      "Diagnostic indisponible",
      connectionState.error
        ? errorMessage(connectionState.error)
        : "L’API n’a retourné aucun diagnostic exploitable.",
    ));
  } else {
    const diagnostic = connectionState.diagnostic;
    const card = el("article", "diagnostic-card");
    const title = el("div", "diagnostic-title");
    title.append(
      el("h3", "list-item-title", "État observé"),
      statusChip(diagnosticLabel(diagnostic), diagnostic.healthy ? "active" : diagnostic.status === "degraded" ? "waiting" : "failed"),
    );
    const checked = el("time", "diagnostic-time", `Vérifié le ${formatDateTime(diagnostic.checked_at)}`);
    checked.dateTime = diagnostic.checked_at;
    card.append(title, el("p", "diagnostic-message", diagnostic.message), checked);
    if (diagnostic.capabilities.length) {
      const capabilities = el("ul", "diagnostic-capabilities");
      for (const capability of diagnostic.capabilities) capabilities.append(el("li", "", capability));
      card.append(el("h4", "diagnostic-subtitle", "Capacités annoncées"), capabilities);
    } else {
      card.append(el("p", "diagnostic-empty", "Aucune capacité exploitable n’a été annoncée."));
    }
    section.append(card);
  }
  content.append(section);

  const business = el("section", "content-section");
  business.append(sectionHeader("Plateforme métier"));
  const row = el("article", "list-item");
  row.append(
    el("div", "list-item-copy", "API authentifiée par cookie de session HttpOnly"),
    statusChip(state.phase === "ready" ? "Connectée" : "Indisponible", state.phase === "ready" ? "active" : "failed"),
  );
  business.append(row);
  content.append(business);
}

type UnconfiguredRoute = "automations" | "library";

const CAPABILITY_COPY: Record<UnconfiguredRoute, {
  title: string;
  description: string;
  consequence: string;
}> = {
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
};

function renderUnconfigured(route: UnconfiguredRoute): void {
  const copy = CAPABILITY_COPY[route];
  const intro = el("section", "page-intro");
  intro.append(
    statusChip("Non configuré", "unconfigured"),
    el("h2", "page-title", copy.title),
    el("p", "page-description", copy.description),
  );
  content.append(intro, statePanel("unconfigured", "Capacité indisponible", copy.consequence));
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
  } else if (currentRoute === "conversations") {
    renderDataBoundary(renderConversations);
  } else if (currentRoute === "missions") {
    renderDataBoundary(renderMissions);
  } else if (currentRoute === "connections") {
    renderConnections();
  } else {
    renderUnconfigured(currentRoute as UnconfiguredRoute);
  }
}

function navigate(path: string, focusContent: boolean): void {
  const url = new URL(path, window.location.href);
  if (url.origin !== window.location.origin) return;
  if (currentRoute === "conversations" && routeFromPathname(url.pathname) !== "conversations") {
    ++pollSequence;
  }
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
  if (currentRoute === "conversations") ++pollSequence;
  currentRoute = routeFromPathname(window.location.pathname);
  renderCurrentRoute();
  content.focus();
});

applyTheme(preferredTheme(), false);
void initializeAuthentication();
