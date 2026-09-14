import type {
  AcpEvent,
  AutomationCreate,
  AutomationScheduleKind,
  Overview,
  Project,
  TaskSummary,
} from "@acp/contracts";

import "./workspace.css";
import { renderMcpCenter, renderSecretsPanel, resetMcpUiState } from "./mcp-ui";
import { renderLibrary, resetLibraryUiState } from "./library-ui";
import { renderAutomations, resetAutomationUiState, unmountAutomationUi } from "./automation-ui";
import { AutomationApiClient } from "./automation-api";
import {
  buildRoutineAutomationInput,
  missionCanBecomeRoutine,
  prepareRoutineCreationAttempt,
  routineNameForMission,
  settleRoutineCreationAttempt,
  type RoutineCreationAttempt,
} from "./mission-routine";
import {
  isStudioViewRequested,
  renderStudio,
  resetStudioUiState,
  studioRouteLink,
} from "./studio-ui";
import {
  el,
  errorMessage,
  formatDateTime,
  labeledField,
  normalizeApiError,
  sectionHeader,
  statePanel,
  statusChip,
} from "./ui-primitives";
import {
  WorkspaceApiClient,
  WorkspaceApiError,
  WorkspaceHttpClient,
  type ApprovalSummary,
  type MissionComment,
  type MissionDetail,
  type MissionInput,
  type MissionRunResource,
  type MissionSummary,
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
  type HermesNativeListing,
  type HermesNativeSkill,
  type HermesNativeToolset,
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
  /** Lecture seule du natif Hermes : chargée après le diagnostic. */
  nativePhase: ResourcePhase;
  native: HermesNativeListing | null;
  nativeError: WorkspaceApiError | null;
  nativeSequence: number;
}

interface MissionState {
  phase: ResourcePhase;
  items: MissionSummary[];
  commentsByMission: Map<string, MissionComment[]>;
  focusedMission: MissionDetail | null;
  focusedRunId: string | null;
  error: WorkspaceApiError | null;
  actionId: string | null;
}

interface MissionRoutineDraftState {
  sourceMissionId: string;
  open: boolean;
  busy: boolean;
  name: string;
  scheduleKind: AutomationScheduleKind;
  expression: string;
  timezone: string;
  pending: RoutineCreationAttempt | null;
  notice: MissionNotice | null;
}

const http = new WorkspaceHttpClient();
const api = new WorkspaceApiClient({ http });
const automationApi = new AutomationApiClient({ http });
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
  nativePhase: "idle",
  native: null,
  nativeError: null,
  nativeSequence: 0,
};
const missionState: MissionState = {
  phase: "idle",
  items: [],
  commentsByMission: new Map(),
  focusedMission: null,
  focusedRunId: null,
  error: null,
  actionId: null,
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
let missionSequence = 0;
let missionNotice: MissionNotice | null = null;
let projectNotice: MissionNotice | null = null;
let fieldSequence = 0;
let missionRoutineDraft: MissionRoutineDraftState | null = null;
let missionRoutineFocusTarget: string | null = null;

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
  connectionState.nativePhase = "idle";
  connectionState.native = null;
  connectionState.nativeError = null;
  ++connectionState.nativeSequence;
  missionState.phase = "idle";
  missionState.items = [];
  missionState.commentsByMission.clear();
  missionState.focusedMission = null;
  missionState.focusedRunId = null;
  missionState.error = null;
  missionState.actionId = null;
  missionRoutineDraft = null;
  missionRoutineFocusTarget = null;
  conversationDrafts.clear();
  newConversationDraft.projectId = "";
  newConversationDraft.title = "";
  newProjectDraft.name = "";
  newProjectDraft.description = "";
  missionNotice = null;
  projectNotice = null;
  // Les modules Connexions et Bibliothèque gardent leur propre état : sans ces purges,
  // ils repeindraient les serveurs, secrets et skills du compte précédent.
  resetMcpUiState();
  // La bibliothèque relaie elle-même la purge à l'onglet Skills.
  resetLibraryUiState();
  resetAutomationUiState();
  // Le Studio retient un journal, des résultats de tests et des liens signés, et garde un
  // flux SSE ouvert : sans cette purge, ils survivraient à un changement de compte.
  resetStudioUiState();
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
  ++missionSequence;
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
      () => void loadWorkspaceData(),
    ));
    return;
  }
  renderReady(state.overview);
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
      () => void loadWorkspaceData(),
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
    routeLink("/automations", "Automatiser"),
    routeLink("/library", "Parcourir les livrables"),
  );
  heroCopy.append(heroActions);
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

const MISSION_STATUS_LABELS: Record<string, string> = {
  queued: "En file",
  preparing: "Préparation",
  running: "En cours",
  waiting_approval: "Validation requise",
  blocked: "Bloquée",
  stopping: "Arrêt en cours",
  succeeded: "Exécution réussie",
  failed: "Échec",
  cancelled: "Annulée",
  interrupted: "Interrompue",
};

function missionStatusTone(status: string): string {
  if (status === "succeeded") return "active";
  if (["failed", "cancelled", "interrupted"].includes(status)) return "failed";
  if (["waiting_approval", "blocked", "stopping"].includes(status)) return "waiting";
  return "queued";
}

function missionActionKey(action: string, missionId: string): string {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${++fieldSequence}`;
  return `web-${action}-${missionId}-${random}`;
}

function requestedMissionRunId(): string | null {
  const value = new URLSearchParams(window.location.search).get("run")?.trim() ?? "";
  return value && value.length <= 200 ? value : null;
}

function displayedMissionRun(mission: MissionSummary): MissionRunResource {
  if (missionState.focusedMission?.id !== mission.id || !missionState.focusedRunId) {
    return mission.current_run;
  }
  return missionState.focusedMission.runs.find((run) => run.id === missionState.focusedRunId)
    ?? mission.current_run;
}

async function loadMissions(): Promise<void> {
  const sequence = ++missionSequence;
  missionState.phase = "loading";
  missionState.error = null;
  if (currentRoute === "missions") renderCurrentRoute();
  try {
    const requestedRunId = requestedMissionRunId();
    const missions = await api.fetchMissions();
    const focusedMission = requestedRunId
      ? await api.fetchMissionByRun(requestedRunId)
      : null;
    if (focusedMission && !missions.some((mission) => mission.id === focusedMission.id)) {
      missions.unshift(focusedMission);
    }
    const commentEntries = await Promise.all(
      missions.map(async (mission) => [
        mission.id,
        await api.fetchMissionComments(mission.id),
      ] as const),
    );
    if (sequence !== missionSequence) return;
    missionState.items = missions;
    missionState.commentsByMission = new Map(commentEntries);
    missionState.focusedMission = focusedMission;
    missionState.focusedRunId = requestedRunId;
    missionState.phase = "ready";
  } catch (error) {
    if (sequence !== missionSequence) return;
    const apiError = normalizeApiError(error, "Les missions n’ont pas pu être chargées.");
    if (apiError.status === 401) return requireLogin();
    missionState.items = [];
    missionState.commentsByMission.clear();
    missionState.focusedMission = null;
    missionState.focusedRunId = null;
    missionState.phase = "error";
    missionState.error = apiError;
  }
  if (currentRoute === "missions") renderCurrentRoute();
}

async function performMissionAction(
  mission: MissionSummary,
  action: "stop" | "retry" | "accept" | "reject",
): Promise<void> {
  missionState.actionId = mission.id;
  missionNotice = null;
  if (currentRoute === "missions") renderCurrentRoute();
  try {
    if (action === "stop") {
      await api.stopMission(mission.id, missionActionKey("stop", mission.id));
      missionNotice = { tone: "success", message: `L’arrêt de « ${mission.title} » a été demandé.` };
    } else if (action === "retry") {
      await api.retryMission(
        mission.id,
        "Relance contrôlée demandée depuis l’interface web.",
        missionActionKey("retry", mission.id),
      );
      missionNotice = { tone: "success", message: `Une nouvelle tentative a été créée pour « ${mission.title} ».` };
    } else {
      await api.decideMissionAcceptance(
        mission.id,
        mission.current_run.id,
        action === "accept" ? "accepted" : "rejected",
      );
      missionNotice = {
        tone: action === "accept" ? "success" : "warning",
        message: action === "accept"
          ? `Le résultat de « ${mission.title} » a été accepté.`
          : `Le résultat de « ${mission.title} » a été refusé.`,
      };
    }
    await loadMissions();
  } catch (error) {
    const apiError = normalizeApiError(error, "L’action sur la mission a échoué.");
    if (apiError.status === 401) return requireLogin();
    missionNotice = { tone: "error", message: errorMessage(apiError) };
  } finally {
    missionState.actionId = null;
    if (currentRoute === "missions") renderCurrentRoute();
  }
}

async function submitMissionComment(
  mission: MissionSummary,
  runId: string,
  body: string,
): Promise<void> {
  const normalized = body.trim();
  if (!normalized) return;
  missionState.actionId = mission.id;
  missionNotice = null;
  if (currentRoute === "missions") renderCurrentRoute();
  try {
    const comment = await api.addMissionComment(
      mission.id,
      runId,
      normalized,
      missionActionKey("comment", mission.id),
    );
    const existing = missionState.commentsByMission.get(mission.id) ?? [];
    missionState.commentsByMission.set(
      mission.id,
      [...existing.filter((item) => item.id !== comment.id), comment],
    );
    missionNotice = { tone: "success", message: `Commentaire ajouté à « ${mission.title} ».` };
  } catch (error) {
    const apiError = normalizeApiError(error, "Le commentaire n’a pas pu être ajouté.");
    if (apiError.status === 401) return requireLogin();
    missionNotice = { tone: "error", message: errorMessage(apiError) };
  } finally {
    missionState.actionId = null;
    if (currentRoute === "missions") renderCurrentRoute();
  }
}

function missionRoutinePanelId(missionId: string): string {
  return `mission-routine-panel-${missionId}`;
}

function missionRoutineToggleId(missionId: string): string {
  return `mission-routine-toggle-${missionId}`;
}

function missionRoutineNameId(missionId: string): string {
  return `mission-routine-name-${missionId}`;
}

function missionRoutineSubmitId(missionId: string): string {
  return `mission-routine-submit-${missionId}`;
}

function rerenderMissionsWithFocus(targetId: string): void {
  missionRoutineFocusTarget = targetId;
  if (currentRoute === "missions") renderCurrentRoute();
}

function defaultMissionRoutineTimezone(): string {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone?.trim() ?? "";
  return timezone && timezone.length <= 64 ? timezone : "Europe/Paris";
}

function openMissionRoutine(mission: MissionSummary): void {
  const current = missionRoutineDraft;
  if (current && current.sourceMissionId !== mission.id && (current.busy || current.pending)) return;
  if (current?.sourceMissionId === mission.id) {
    current.open = true;
  } else {
    missionRoutineDraft = {
      sourceMissionId: mission.id,
      open: true,
      busy: false,
      name: routineNameForMission(mission),
      scheduleKind: "cron",
      expression: "0 9 * * 1-5",
      timezone: defaultMissionRoutineTimezone(),
      pending: null,
      notice: null,
    };
  }
  rerenderMissionsWithFocus(
    missionRoutineDraft?.pending
      ? missionRoutineSubmitId(mission.id)
      : missionRoutineNameId(mission.id),
  );
}

function closeMissionRoutine(mission: MissionSummary): void {
  const current = missionRoutineDraft;
  if (!current || current.sourceMissionId !== mission.id || current.busy) return;
  if (current.pending) {
    current.open = false;
  } else {
    missionRoutineDraft = null;
  }
  rerenderMissionsWithFocus(missionRoutineToggleId(mission.id));
}

function routineList(title: string, values: string[], emptyLabel: string): HTMLElement {
  const section = el("section", "mission-routine-summary-section");
  section.append(el("h5", "mission-routine-summary-title", title));
  if (!values.length) {
    section.append(el("p", "form-hint", emptyLabel));
    return section;
  }
  const list = el("ul", "mission-criteria");
  for (const value of values) list.append(el("li", "", value));
  section.append(list);
  return section;
}

function routineDetailRow(list: HTMLDListElement, label: string, value: string): void {
  const row = el("div", "mission-routine-detail-row");
  row.append(el("dt", "mission-validation-label", label), el("dd", "", value));
  list.append(row);
}

async function submitMissionRoutine(mission: MissionSummary): Promise<void> {
  const draft = missionRoutineDraft;
  if (!draft || draft.sourceMissionId !== mission.id || draft.busy) return;

  let input: AutomationCreate;
  try {
    input = draft.pending?.input ?? buildRoutineAutomationInput(mission, draft);
  } catch (error) {
    draft.notice = {
      tone: "error",
      message: error instanceof Error ? error.message : "Le préremplissage de la routine est invalide.",
    };
    rerenderMissionsWithFocus(missionRoutineNameId(mission.id));
    return;
  }

  const attempt = prepareRoutineCreationAttempt(
    draft.pending,
    input,
    () => missionActionKey("routine", mission.id),
  );
  draft.pending = attempt;
  draft.busy = true;
  draft.notice = {
    tone: "warning",
    message: "Création en cours : la routine ne sera annoncée qu’après confirmation du serveur.",
  };
  rerenderMissionsWithFocus(missionRoutinePanelId(mission.id));

  try {
    const created = await automationApi.createAutomation(
      mission.project_id,
      attempt.input,
      attempt.key,
    );
    const current = missionRoutineDraft;
    if (!current
      || current.sourceMissionId !== mission.id
      || current.pending?.key !== attempt.key) return;
    if (created.enabled || created.project_id !== mission.project_id) {
      throw new WorkspaceApiError(
        "La réponse de création ne confirme pas une routine en pause dans le projet attendu.",
        "invalid_response",
      );
    }
    current.pending = null;
    current.busy = false;
    missionRoutineDraft = null;
    missionNotice = {
      tone: "success",
      message: `La routine « ${created.name} » (${created.id}) a été créée en pause.`,
    };
    rerenderMissionsWithFocus(missionRoutineToggleId(mission.id));
  } catch (error) {
    const failure = normalizeApiError(error, "La routine n’a pas pu être créée.");
    if (failure.status === 401) return requireLogin();
    const current = missionRoutineDraft;
    if (!current
      || current.sourceMissionId !== mission.id
      || current.pending?.key !== attempt.key) return;
    current.busy = false;
    current.pending = settleRoutineCreationAttempt(attempt, failure);
    current.notice = {
      tone: "error",
      message: current.pending
        ? `${errorMessage(failure)} La prochaine tentative réutilisera la même clé et exactement le même préremplissage.`
        : errorMessage(failure),
    };
    rerenderMissionsWithFocus(missionRoutineSubmitId(mission.id));
  }
}

function renderMissionRoutineConfirmation(mission: MissionSummary): HTMLElement {
  const draft = missionRoutineDraft;
  if (!draft || draft.sourceMissionId !== mission.id) {
    throw new Error("Aucun préremplissage de routine pour cette mission.");
  }
  const frozen = draft.busy || draft.pending !== null;
  const panel = el("section", "mission-routine-confirmation");
  const panelId = missionRoutinePanelId(mission.id);
  const titleId = `${panelId}-title`;
  panel.id = panelId;
  panel.tabIndex = -1;
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-labelledby", titleId);
  const title = el("h4", "diagnostic-subtitle", "Confirmer la transformation en routine");
  title.id = titleId;
  panel.append(
    title,
    el(
      "p",
      "form-hint",
      "La routine sera créée en pause. Vérifiez le calendrier et l’intégralité du gabarit avant de confirmer.",
    ),
  );

  const form = el("form", "mission-routine-form") as HTMLFormElement;
  const nameInput = el("input", "form-control") as HTMLInputElement;
  nameInput.id = missionRoutineNameId(mission.id);
  nameInput.name = "routineName";
  nameInput.required = true;
  nameInput.maxLength = 200;
  nameInput.value = draft.name;
  nameInput.disabled = frozen;
  nameInput.autocomplete = "off";
  const nameField = labeledField("Nom de la routine", nameInput, "Ce nom identifie la routine ; la mission source reste inchangée.");
  const nameLabel = nameField.querySelector("label");
  nameInput.id = missionRoutineNameId(mission.id);
  if (nameLabel) nameLabel.htmlFor = nameInput.id;
  nameInput.addEventListener("input", () => {
    if (missionRoutineDraft?.sourceMissionId === mission.id && !missionRoutineDraft.pending) {
      missionRoutineDraft.name = nameInput.value;
    }
  });

  const kindSelect = el("select", "form-control") as HTMLSelectElement;
  kindSelect.name = "scheduleKind";
  kindSelect.disabled = frozen;
  for (const [value, label] of [["cron", "Cron"], ["interval", "Intervalle"]] as const) {
    const option = el("option", "", label) as HTMLOptionElement;
    option.value = value;
    option.selected = value === draft.scheduleKind;
    kindSelect.append(option);
  }

  const expressionInput = el("input", "form-control") as HTMLInputElement;
  expressionInput.name = "scheduleExpression";
  expressionInput.required = true;
  expressionInput.maxLength = 200;
  expressionInput.value = draft.expression;
  expressionInput.disabled = frozen;
  expressionInput.autocomplete = "off";

  const timezoneInput = el("input", "form-control") as HTMLInputElement;
  timezoneInput.name = "timezone";
  timezoneInput.required = true;
  timezoneInput.maxLength = 64;
  timezoneInput.value = draft.timezone;
  timezoneInput.disabled = frozen;
  timezoneInput.autocomplete = "off";

  const expressionField = labeledField(
    "Expression",
    expressionInput,
    draft.scheduleKind === "cron" ? "Ex. 0 9 * * 1-5" : "Secondes entre deux occurrences, ex. 900",
  );
  const expressionHint = expressionField.querySelector<HTMLElement>(".form-hint");

  kindSelect.addEventListener("change", () => {
    const current = missionRoutineDraft;
    if (!current || current.sourceMissionId !== mission.id || current.pending) return;
    const previous = current.scheduleKind;
    current.scheduleKind = kindSelect.value as AutomationScheduleKind;
    if (previous === "cron" && current.scheduleKind === "interval" && expressionInput.value === "0 9 * * 1-5") {
      expressionInput.value = "900";
    } else if (previous === "interval" && current.scheduleKind === "cron" && expressionInput.value === "900") {
      expressionInput.value = "0 9 * * 1-5";
    }
    current.expression = expressionInput.value;
    if (expressionHint) {
      expressionHint.textContent = current.scheduleKind === "cron"
        ? "Ex. 0 9 * * 1-5"
        : "Secondes entre deux occurrences, ex. 900";
    }
  });
  expressionInput.addEventListener("input", () => {
    if (missionRoutineDraft?.sourceMissionId === mission.id && !missionRoutineDraft.pending) {
      missionRoutineDraft.expression = expressionInput.value;
    }
  });
  timezoneInput.addEventListener("input", () => {
    if (missionRoutineDraft?.sourceMissionId === mission.id && !missionRoutineDraft.pending) {
      missionRoutineDraft.timezone = timezoneInput.value;
    }
  });

  const scheduleFields = el("div", "form-split");
  scheduleFields.append(
    labeledField("Type de calendrier", kindSelect),
    expressionField,
  );

  const summary = el("div", "mission-routine-summary");
  summary.append(
    routineList("Objectif", [mission.objective], "Objectif absent"),
    routineList("Résultat attendu", [mission.expected_outcome], "Résultat absent"),
    routineList("Critères d’acceptation", mission.acceptance_criteria, "Aucun critère"),
  );
  const autonomy = routineList(
    `Autonomie · ${mission.autonomy.mode}`,
    [
      ...mission.autonomy.allowed_actions.map((value) => `Autorisée : ${value}`),
      ...mission.autonomy.forbidden_actions.map((value) => `Interdite : ${value}`),
      ...mission.autonomy.approval_required_actions.map((value) => `Approbation requise : ${value}`),
    ],
    "Aucune action détaillée",
  );
  const resources = routineList(
    "Ressources",
    mission.resources.map((resource) => {
      const description = resource.description ? ` · ${resource.description}` : "";
      return `${resource.kind} · ${resource.access} · ${resource.identifier}${description}`;
    }),
    "Aucune ressource",
  );
  const details = el("dl", "mission-routine-details") as HTMLDListElement;
  routineDetailRow(
    details,
    "Budget coût",
    mission.budget.max_cost === null
      ? `Non plafonné (${mission.budget.currency})`
      : `${mission.budget.max_cost} ${mission.budget.currency}`,
  );
  routineDetailRow(details, "Budget jetons", mission.budget.max_tokens === null ? "Non plafonné" : String(mission.budget.max_tokens));
  routineDetailRow(details, "Budget outils", mission.budget.max_tool_calls === null ? "Non plafonné" : String(mission.budget.max_tool_calls));
  routineDetailRow(details, "Durée maximale", `${mission.duration_seconds} secondes`);
  routineDetailRow(details, "Priorité", String(mission.priority));
  routineDetailRow(details, "Équipe", mission.team_id ?? "Non affectée");
  routineDetailRow(details, "Agent", mission.agent_instance_id ?? "Non affecté");
  summary.append(
    autonomy,
    resources,
    routineList("Capacités requises", mission.required_capabilities, "Aucune capacité requise"),
    details,
    el("p", "form-hint", "Rattrapage : ignorer · concurrence maximale : 1 exécution"),
  );

  const feedback = el("div", "form-feedback");
  feedback.setAttribute("aria-live", draft.notice?.tone === "error" ? "assertive" : "polite");
  if (draft.notice) {
    feedback.dataset.tone = draft.notice.tone;
    feedback.textContent = draft.notice.message;
  }
  const buttons = el("div", "mission-result-actions");
  const submit = el(
    "button",
    "button button-primary",
    draft.busy
      ? "Création en cours…"
      : draft.pending ? "Réessayer avec la même clé" : "Confirmer et créer en pause",
  ) as HTMLButtonElement;
  submit.id = missionRoutineSubmitId(mission.id);
  submit.type = "submit";
  submit.disabled = draft.busy;
  const cancel = el(
    "button",
    "button button-secondary",
    draft.pending ? "Masquer · clé conservée" : "Annuler",
  ) as HTMLButtonElement;
  cancel.type = "button";
  cancel.disabled = draft.busy;
  cancel.addEventListener("click", () => closeMissionRoutine(mission));
  buttons.append(submit, cancel);

  form.append(
    nameField,
    scheduleFields,
    labeledField("Fuseau IANA", timezoneInput, "Ex. Europe/Paris ; les changements d’heure sont évalués côté serveur."),
    summary,
    feedback,
    buttons,
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    void submitMissionRoutine(mission);
  });
  panel.append(form);
  return panel;
}

function renderMissionList(overview: Overview): HTMLElement {
  const list = el("div", "item-list mission-results");
  for (const mission of missionState.items) {
    const run = displayedMissionRun(mission);
    const isCurrentRun = run.id === mission.current_run.id;
    const isFocusedRun = missionState.focusedRunId === run.id;
    const item = el("article", "mission-result-card");
    if (isFocusedRun) {
      item.dataset.focused = "true";
      item.setAttribute("aria-label", `Tentative demandée : ${mission.title}`);
    }
    const header = el("div", "mission-result-header");
    const copy = el("div", "list-item-copy");
    copy.append(
      el("h3", "list-item-title", mission.title),
      el("p", "list-item-meta", `${projectName(overview, mission.project_id)} · tentative ${run.attempt_number}`),
    );
    header.append(copy, statusChip(MISSION_STATUS_LABELS[run.status] ?? run.status, missionStatusTone(run.status)));
    if (!isCurrentRun) {
      copy.append(el("p", "form-hint", "Tentative historique ouverte depuis le lien direct ; les actions portent uniquement sur la tentative courante."));
    }

    const validation = el("div", "mission-validation-grid");
    const technical = el("div", "mission-validation-item");
    technical.append(
      el("span", "mission-validation-label", "Validation technique"),
      statusChip(
        run.technical_validation.status === "passed"
          ? "Réussie"
          : run.technical_validation.status === "failed" ? "Échouée" : "En attente",
        run.technical_validation.status === "passed"
          ? "active"
          : run.technical_validation.status === "failed" ? "failed" : "waiting",
      ),
    );
    const acceptance = el("div", "mission-validation-item");
    acceptance.append(
      el("span", "mission-validation-label", "Acceptation utilisateur"),
      statusChip(
        run.user_acceptance.status === "accepted"
          ? "Acceptée"
          : run.user_acceptance.status === "rejected" ? "Refusée" : "En attente",
        run.user_acceptance.status === "accepted"
          ? "active"
          : run.user_acceptance.status === "rejected" ? "failed" : "waiting",
      ),
    );
    validation.append(technical, acceptance);

    const criteria = el("ul", "mission-criteria");
    for (const criterion of mission.acceptance_criteria) criteria.append(el("li", "", criterion));
    const evidence = el("div", "mission-evidence");
    evidence.append(el("h4", "diagnostic-subtitle", `Preuves (${run.evidence.length})`));
    if (run.evidence.length) {
      const evidenceList = el("ul", "mission-criteria");
      for (const proof of run.evidence) {
        const suffix = proof.exit_code === null ? "" : ` · code ${proof.exit_code}`;
        evidenceList.append(el("li", "", `${proof.kind} — ${proof.summary}${suffix}`));
      }
      evidence.append(evidenceList);
    } else {
      evidence.append(el("p", "form-hint", "Aucune preuve structurée n’a encore été enregistrée."));
    }

    const actions = el("div", "mission-result-actions");
    const busy = missionState.actionId === mission.id;
    const routineEligible = missionCanBecomeRoutine(mission, run, isCurrentRun);
    // Lien profond vers le Studio de **cette** tentative (spec §2.5) : chronologie du
    // journal, dernière capture de la session et résultats de tests. Inutile de le
    // proposer sur la tentative dont le Studio est déjà ouvert.
    if (!(isFocusedRun && isStudioViewRequested(window.location.search))) {
      actions.append(routeLink(studioRouteLink(run.id), "Ouvrir le Studio"));
    }
    if (isCurrentRun && ["queued", "preparing", "running", "waiting_approval", "blocked"].includes(run.status)) {
      const stop = el("button", "button button-secondary", busy ? "Action en cours…" : "Arrêter") as HTMLButtonElement;
      stop.type = "button";
      stop.disabled = busy;
      stop.addEventListener("click", () => void performMissionAction(mission, "stop"));
      actions.append(stop);
    }
    if (
      isCurrentRun
      && (["failed", "cancelled", "interrupted"].includes(run.status)
      || (run.status === "succeeded" && run.user_acceptance.status === "rejected"))
    ) {
      const retry = el("button", "button button-secondary", busy ? "Action en cours…" : "Relancer") as HTMLButtonElement;
      retry.type = "button";
      retry.disabled = busy;
      retry.addEventListener("click", () => void performMissionAction(mission, "retry"));
      actions.append(retry);
    }
    if (
      isCurrentRun
      && run.status === "succeeded"
      && run.technical_validation.status === "passed"
      && run.user_acceptance.status === "pending"
    ) {
      const accept = el("button", "button button-primary", "Accepter") as HTMLButtonElement;
      const reject = el("button", "button button-secondary", "Refuser") as HTMLButtonElement;
      accept.type = "button";
      reject.type = "button";
      accept.disabled = busy;
      reject.disabled = busy;
      accept.addEventListener("click", () => void performMissionAction(mission, "accept"));
      reject.addEventListener("click", () => void performMissionAction(mission, "reject"));
      actions.append(accept, reject);
    }
    if (routineEligible) {
      const draft = missionRoutineDraft?.sourceMissionId === mission.id
        ? missionRoutineDraft
        : null;
      const unresolvedElsewhere = Boolean(
        missionRoutineDraft
        && missionRoutineDraft.sourceMissionId !== mission.id
        && (missionRoutineDraft.busy || missionRoutineDraft.pending),
      );
      const toggle = el(
        "button",
        "button button-primary",
        draft?.open
          ? "Masquer la transformation"
          : draft?.pending ? "Réessayer la création de routine" : "Transformer en routine",
      ) as HTMLButtonElement;
      toggle.id = missionRoutineToggleId(mission.id);
      toggle.type = "button";
      toggle.disabled = busy || Boolean(draft?.busy) || unresolvedElsewhere;
      toggle.setAttribute("aria-controls", missionRoutinePanelId(mission.id));
      toggle.setAttribute("aria-expanded", String(Boolean(draft?.open)));
      if (unresolvedElsewhere) {
        toggle.title = "Résolvez d’abord la création de routine restée incertaine sur une autre mission.";
      }
      toggle.addEventListener("click", () => {
        if (draft?.open) closeMissionRoutine(mission);
        else openMissionRoutine(mission);
      });
      actions.append(toggle);
    }

    const comments = (missionState.commentsByMission.get(mission.id) ?? [])
      .filter((comment) => comment.run_id === run.id);
    const commentHistory = el("div", "mission-comments");
    commentHistory.append(el("h4", "diagnostic-subtitle", `Commentaires (${comments.length})`));
    if (comments.length) {
      const commentList = el("ul", "mission-comment-list");
      for (const comment of comments) {
        const date = comment.created_at ? ` · ${formatDateTime(comment.created_at)}` : "";
        commentList.append(el("li", "", `${comment.body} — ${comment.author_user_id}${date}`));
      }
      commentHistory.append(commentList);
    } else {
      commentHistory.append(el("p", "form-hint", "Aucun commentaire pour cette tentative."));
    }

    const commentForm = el("form", "mission-comment-form") as HTMLFormElement;
    const commentInput = el("input", "form-control") as HTMLInputElement;
    commentInput.name = "comment";
    commentInput.maxLength = 20_000;
    commentInput.required = true;
    commentInput.placeholder = "Commenter cette tentative…";
    const commentSubmit = el("button", "button button-secondary", "Ajouter") as HTMLButtonElement;
    commentSubmit.type = "submit";
    commentSubmit.disabled = busy;
    commentForm.append(commentInput, commentSubmit);
    commentForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!commentForm.reportValidity()) return;
      void submitMissionComment(mission, run.id, commentInput.value);
    });

    item.append(
      header,
      el("p", "mission-objective", mission.objective),
      validation,
      el("h4", "diagnostic-subtitle", "Critères d’acceptation"),
      criteria,
      evidence,
      actions,
    );
    if (
      routineEligible
      && missionRoutineDraft?.sourceMissionId === mission.id
      && missionRoutineDraft.open
    ) {
      item.append(renderMissionRoutineConfirmation(mission));
    }
    item.append(commentHistory, commentForm);
    list.append(item);
  }
  return list;
}

function renderMissions(overview: Overview): void {
  const intro = el("section", "page-intro");
  intro.append(
    el("p", "workspace-eyebrow", "Exécution réelle"),
    el("h2", "page-title", "Missions"),
    el("p", "page-description", "Chaque mission conserve ses tentatives, son arrêt réel, ses preuves et ses validations sans confondre exécution et acceptation."),
  );
  content.append(intro);

  const layout = el("div", "missions-layout");
  const composer = el("section", "content-section mission-composer");
  composer.append(sectionHeader("Nouvelle mission", "La création est atomique et produit immédiatement une première tentative en file."));
  if (!overview.projects.length) {
    composer.append(statePanel("empty", "Projet requis", "Aucun projet n’est disponible pour recevoir une mission."));
  } else {
    composer.append(createMissionForm(overview));
  }

  const existing = el("section", "content-section");
  existing.append(sectionHeader("Missions et résultats", "État d’exécution, validation technique et acceptation utilisateur restent séparés."));
  if (missionState.phase === "idle") {
    missionState.phase = "loading";
    queueMicrotask(() => void loadMissions());
  }
  if (missionState.phase === "loading") {
    existing.append(statePanel("loading", "Chargement des missions", "Lecture des tentatives et des preuves persistées…"));
  } else if (missionState.phase === "error") {
    existing.append(statePanel(
      missionState.error?.kind === "offline" ? "offline" : "error",
      "Missions indisponibles",
      missionState.error ? errorMessage(missionState.error) : "La réponse reçue est inexploitable.",
    ));
  } else {
    existing.append(missionState.items.length
      ? renderMissionList(overview)
      : statePanel("empty", "Aucune mission", "Aucune mission n’a encore été créée."));
  }
  layout.append(composer, existing);
  content.append(layout);

  // Studio en direct : uniquement sur le lien profond `/missions?run=<id>&vue=studio`, et
  // uniquement pour la tentative ciblée. `http` est le client du shell (règle du Lot D :
  // le Studio ne crée jamais de client et ne lit jamais `/auth/session`).
  const studioRunId = missionState.focusedRunId;
  if (studioRunId && isStudioViewRequested(window.location.search)) {
    const studio = el("section", "content-section");
    content.append(studio);
    renderStudio(studio, http, studioRunId);
  }
  if (missionRoutineFocusTarget) {
    const targetId = missionRoutineFocusTarget;
    missionRoutineFocusTarget = null;
    queueMicrotask(() => document.getElementById(targetId)?.focus());
  }
}

function createMissionForm(overview: Overview): HTMLFormElement {
  const form = el("form", "mission-form");
  form.noValidate = true;
  let pendingCreate: { fingerprint: string; key: string } | null = null;

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
    ["isolated_work", "Travail isolé (runner compatible requis)"],
    ["sensitive_on_approval", "Actions sensibles (runner compatible requis)"],
  ] as const;
  for (const [value, label] of autonomyOptions) {
    const option = el("option", "", label) as HTMLOptionElement;
    option.value = value;
    if (value === "read_only") option.selected = true;
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
    labeledField("Niveau d’autonomie", autonomySelect, "Le backend local Lot C n'accepte que le mode Lecture seule supervisé."),
    labeledField("Priorité", prioritySelect),
  );

  const durationInput = el("input", "form-control") as HTMLInputElement;
  durationInput.name = "durationMinutes";
  durationInput.type = "number";
  durationInput.min = "1";
  durationInput.max = "525600";
  durationInput.value = "60";
  durationInput.required = true;

  const maxToolCallsInput = el("input", "form-control") as HTMLInputElement;
  maxToolCallsInput.name = "maxToolCalls";
  maxToolCallsInput.type = "number";
  maxToolCallsInput.min = "1";
  maxToolCallsInput.max = "10000";
  maxToolCallsInput.value = "50";
  maxToolCallsInput.required = true;

  const limits = el("div", "form-split");
  limits.append(
    labeledField("Durée maximale (minutes)", durationInput),
    labeledField("Budget d’appels outils", maxToolCallsInput, "Une limite inconnue n’est jamais assimilée à zéro."),
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
    limits,
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
      acceptanceCriteria: String(data.get("acceptanceCriteria") ?? "")
        .split(/[;\n]+/)
        .map((criterion) => criterion.trim())
        .filter(Boolean),
      autonomy: String(data.get("autonomy")) as MissionInput["autonomy"],
      priority: Number(data.get("priority") ?? 3),
      durationSeconds: Math.round(Number(data.get("durationMinutes") ?? 60) * 60),
      maxToolCalls: Math.round(Number(data.get("maxToolCalls") ?? 50)),
    };

    submit.disabled = true;
    submit.textContent = "Création en cours…";
    form.setAttribute("aria-busy", "true");
    feedback.dataset.tone = "pending";
    feedback.textContent = "Création de la mission et de sa première tentative…";
    missionNotice = null;

    const fingerprint = JSON.stringify(input);
    if (!pendingCreate || pendingCreate.fingerprint !== fingerprint) {
      pendingCreate = {
        fingerprint,
        key: missionActionKey("create", input.projectId),
      };
    }

    try {
      const result = await api.createMission(input, pendingCreate.key);
      pendingCreate = null;
      missionNotice = {
        tone: "success",
        message: `Mission « ${result.title} » créée et mise en file (identifiant ${result.id}).`,
      };
      missionState.phase = "idle";
      await loadWorkspaceData();
      await loadMissions();
    } catch (error) {
      if (!(error instanceof WorkspaceApiError) || error.kind !== "offline") {
        pendingCreate = null;
      }
      if (error instanceof WorkspaceApiError) {
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

  /**
   * Lecture seule des skills et toolsets natifs : aucune écriture n'est
   * possible ici, Hermes reste la source de vérité de sa configuration.
   */
  const loadNativeListing = async (): Promise<void> => {
    const sequence = ++connectionState.nativeSequence;
    try {
      const listing = await conversationApi.fetchHermesNativeListing();
      if (sequence !== connectionState.nativeSequence) return;
      connectionState.native = listing;
      connectionState.nativePhase = "ready";
    } catch (error) {
      if (sequence !== connectionState.nativeSequence) return;
      const apiError = normalizeApiError(
        error,
        "Les skills et toolsets natifs d’Hermes n’ont pas pu être lus.",
      );
      if (apiError.status === 401) return requireLogin();
      connectionState.native = null;
      connectionState.nativePhase = "error";
      connectionState.nativeError = apiError;
    }
    if (currentRoute === "connections") renderCurrentRoute();
  };

  // La lecture native suit le diagnostic : elle ne démarre qu'une fois celui-ci
  // terminé, et ne se relance pas d'elle-même.
  if (
    connectionState.nativePhase === "idle"
    && (connectionState.phase === "ready" || connectionState.phase === "error")
  ) {
    connectionState.nativePhase = "loading";
    queueMicrotask(() => void loadNativeListing());
  }

  const nativeSkillItem = (skill: HermesNativeSkill): HTMLElement => {
    const item = el("article", "list-item");
    const copy = el("div", "list-item-copy");
    copy.append(el("h4", "list-item-title", skill.name));
    if (skill.description) copy.append(el("p", "list-item-meta", skill.description));
    item.append(copy, statusChip(skill.category || "Sans catégorie", "neutral"));
    return item;
  };

  const nativeToolsetItem = (toolset: HermesNativeToolset): HTMLElement => {
    const item = el("article", "list-item");
    const copy = el("div", "list-item-copy");
    copy.append(el("h4", "list-item-title", toolset.label || toolset.name));
    const details = [`Nom Hermes : ${toolset.name}`];
    if (toolset.description) details.push(toolset.description);
    details.push(toolset.configured ? "Configuré côté Hermes" : "Non configuré côté Hermes");
    details.push(
      toolset.tools.length
        ? `Outils annoncés : ${toolset.tools.join(", ")}`
        : "Aucun outil annoncé.",
    );
    for (const detail of details) copy.append(el("p", "list-item-meta", detail));
    item.append(
      copy,
      statusChip(toolset.enabled ? "Activé" : "Désactivé", toolset.enabled ? "active" : "unconfigured"),
    );
    return item;
  };

  const nativeSection = el("section", "content-section");
  nativeSection.append(sectionHeader(
    "Skills et toolsets natifs Hermes",
    "Lecture seule de ce qu’Hermes annonce. Leur configuration reste côté Hermes et n’est jamais dupliquée ici.",
  ));
  const listing = connectionState.native;
  if (connectionState.nativePhase === "idle") {
    nativeSection.append(statePanel(
      "loading",
      "En attente du diagnostic",
      "La lecture des skills et toolsets natifs démarre une fois le diagnostic Hermes terminé.",
    ));
  } else if (connectionState.nativePhase === "loading") {
    nativeSection.append(statePanel(
      "loading",
      "Lecture en cours",
      "Consultation des skills et toolsets annoncés par Hermes…",
    ));
  } else if (connectionState.nativePhase === "error" || !listing) {
    nativeSection.append(statePanel(
      connectionState.nativeError?.kind === "offline" ? "offline" : "error",
      "Lecture indisponible",
      connectionState.nativeError
        ? errorMessage(connectionState.nativeError)
        : "L’API n’a retourné aucune liste exploitable.",
    ));
  } else if (listing.status === "not_configured") {
    nativeSection.append(statePanel("unconfigured", "Hermes non configuré", listing.message));
  } else if (listing.status === "unsupported") {
    nativeSection.append(statePanel(
      "unconfigured",
      "Consultation non supportée",
      listing.message,
    ));
  } else if (listing.status === "unavailable") {
    nativeSection.append(statePanel("error", "Lecture impossible", listing.message));
  } else {
    const card = el("article", "diagnostic-card");
    const title = el("div", "diagnostic-title");
    title.append(
      el("h3", "list-item-title", "Déclaré par Hermes"),
      statusChip("Lu", "active"),
    );
    card.append(title, el("p", "diagnostic-message", listing.message));
    if (listing.read_at) {
      const read = el("time", "diagnostic-time", `Source : Hermes, lu le ${formatDateTime(listing.read_at)}`);
      read.dateTime = listing.read_at;
      card.append(read);
    }
    card.append(el("h3", "diagnostic-subtitle", `Skills (${listing.skills.length})`));
    if (listing.skills.length) {
      const skills = el("div", "item-list");
      for (const skill of listing.skills) skills.append(nativeSkillItem(skill));
      card.append(skills);
    } else {
      card.append(el("p", "diagnostic-empty", "Aucun skill natif annoncé par Hermes."));
    }
    card.append(el("h3", "diagnostic-subtitle", `Toolsets (${listing.toolsets.length})`));
    if (listing.toolsets.length) {
      const toolsets = el("div", "item-list");
      for (const toolset of listing.toolsets) toolsets.append(nativeToolsetItem(toolset));
      card.append(toolsets);
    } else {
      card.append(el("p", "diagnostic-empty", "Aucun toolset natif annoncé par Hermes."));
    }
    card.append(el(
      "p",
      "diagnostic-empty",
      "Consultation seule : la configuration MCP native d’Hermes s’applique par export côté service Hermes.",
    ));
    nativeSection.append(card);
  }

  const section = el("section", "content-section");
  const header = sectionHeader("Hermes Agent", "Moteur agentique principal, exécuté comme service séparé.");
  const check = el("button", "button button-primary", "Relancer le diagnostic") as HTMLButtonElement;
  check.type = "button";
  check.disabled = connectionState.phase === "loading";
  check.addEventListener("click", () => {
    // La relecture du natif Hermes suit le diagnostic : elle est simplement
    // remise à l'état initial, aucune écriture n'est déclenchée.
    ++connectionState.nativeSequence;
    connectionState.nativePhase = "idle";
    connectionState.native = null;
    connectionState.nativeError = null;
    void loadHermesDiagnostic(true);
  });
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

  content.append(nativeSection);

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

  if (currentRoute !== "automations") unmountAutomationUi();

  // Le Studio ne vit que dans `/missions?vue=studio` : quitter cet écran doit fermer son
  // flux SSE, sinon il consomme une des connexions autorisées du compte en arrière-plan.
  if (currentRoute !== "missions" || !isStudioViewRequested(window.location.search)) {
    resetStudioUiState();
  }

  if (currentRoute === "home") {
    renderDataBoundary(renderHome);
  } else if (currentRoute === "projects") {
    renderDataBoundary(renderProjects);
  } else if (currentRoute === "conversations") {
    renderDataBoundary(renderConversations);
  } else if (currentRoute === "missions") {
    renderDataBoundary(renderMissions);
  } else if (currentRoute === "automations") {
    renderAutomations(content, http);
  } else if (currentRoute === "connections") {
    renderConnections();
    // Le client du shell porte le jeton CSRF de la session : un client séparé devrait
    // relire `/auth/session`, ce qui ferait tourner ce jeton unique côté serveur.
    renderMcpCenter(content, http, authState.session?.user.role ?? null);
    renderSecretsPanel(content, http, authState.session?.user.role ?? null);
  } else if (currentRoute === "library") {
    // Deux onglets : Skills (Lot D, délégué tel quel) et Livrables (Lot E).
    renderLibrary(content, http);
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
  if (currentRoute === "missions") missionState.phase = "idle";
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
  if (currentRoute === "missions") missionState.phase = "idle";
  renderCurrentRoute();
  content.focus();
});

applyTheme(preferredTheme(), false);
void initializeAuthentication();
