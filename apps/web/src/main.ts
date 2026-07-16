import "./style.css";

import type { AcpEvent, Overview } from "@acp/contracts";
import {
  createOfficeRenderer,
  type IOfficeRenderer,
  type RendererMode,
} from "@acp/pixel-office-engine";
import { badge, el, formatTime, statusColor } from "@acp/ui";

import {
  connectEvents,
  createAndQueueTask,
  fetchOfficeConfig,
  fetchOverview,
  fetchPendingApprovals,
  fetchRecentEvents,
  type PendingApproval,
} from "./api";
import {
  companyScene,
  departmentScene,
  projectScene,
  workspaceScene,
  type OfficeConfigMap,
} from "./scene";

type View =
  | { kind: "company" }
  | { kind: "workspace"; id: string }
  | { kind: "project"; id: string }
  | { kind: "department"; id: string };

let overview: Overview;
const officeConfigs: OfficeConfigMap = {};
let view: View = { kind: "company" };
let engine: IOfficeRenderer;
let selectedAgentId: string | null = null;
let approvals: PendingApproval[] = [];
let eventLog: AcpEvent[] = [];
let refreshTimer: number | null = null;

const sidebar = document.getElementById("sidebar")!;
const topbar = document.getElementById("topbar")!;
const kpis = document.getElementById("kpis")!;
const rail = document.getElementById("rail")!;
const canvasWrap = document.getElementById("canvas-wrap")!;

// ---------------------------------------------------------------- helpers

const DEPT_ICONS: Record<string, string> = {
  "software-engineering": "💻", "data-science": "📊",
  "research": "🔬", "game-development": "🎮",
};

function deptIcon(type: string): string {
  return DEPT_ICONS[type] ?? "⚙";
}

interface TaskStats {
  open: number;
  active: number;
  done: number;
  failed: number;
  health: number; // % de réussite
}

function taskStats(projectIds?: Set<string>): TaskStats {
  const tasks = overview.tasks.filter((t) => !projectIds || projectIds.has(t.project_id));
  const done = tasks.filter((t) => t.status === "done").length;
  const failed = tasks.filter((t) => t.status === "failed").length;
  const open = tasks.filter((t) => !["done", "failed"].includes(t.status)).length;
  const active = tasks.filter((t) =>
    ["queued", "planning", "in_progress", "review"].includes(t.status)).length;
  const health = done + failed === 0 ? 100 : Math.round((done / (done + failed)) * 1000) / 10;
  return { open, active, done, failed, health };
}

function deptProjects(deptId: string): Set<string> {
  return new Set(overview.projects.filter((p) => p.department_id === deptId).map((p) => p.id));
}

function setView(next: View): void {
  view = next;
  renderAll();
  if (next.kind === "department" || next.kind === "project") {
    engine.focusRoom(next.id);
  }
}

function currentScene() {
  switch (view.kind) {
    case "company": return companyScene(overview, officeConfigs);
    case "workspace": return workspaceScene(overview, view.id, officeConfigs);
    case "project": return projectScene(overview, view.id, officeConfigs);
    case "department": return departmentScene(overview, view.id, officeConfigs);
  }
}

function viewMeta(): { icon: string; title: string; subtitle: string } {
  switch (view.kind) {
    case "company":
      return {
        icon: "🏢", title: "Company Campus",
        subtitle: "Vue globale des départements, agents et opérations",
      };
    case "workspace": {
      const ws = overview.workspaces.find((w) => w.id === view.id);
      return { icon: "🗂", title: `Workspace — ${ws?.name ?? "?"}`,
               subtitle: `Contexte ${ws?.kind ?? ""} · un bâtiment par projet` };
    }
    case "project": {
      const p = overview.projects.find((x) => x.id === view.id);
      return { icon: "📁", title: p?.name ?? "Projet",
               subtitle: `Bureau de l'équipe · ${p?.project_type ?? ""}` };
    }
    case "department": {
      const d = overview.departments.find((x) => x.id === view.id);
      return { icon: deptIcon(d?.department_type ?? ""), title: d?.name ?? "Département",
               subtitle: "Projets et agents du secteur" };
    }
  }
}

// ---------------------------------------------------------------- sidebar

function navButton(label: string, opts: {
  active?: boolean; sub?: boolean; count?: string; countClass?: string; onClick: () => void;
}): HTMLButtonElement {
  const btn = el("button", `nav-item${opts.sub ? " sub" : ""}${opts.active ? " active" : ""}`);
  btn.append(el("span", "", label));
  if (opts.count !== undefined) {
    btn.append(el("span", `count${opts.countClass ? ` ${opts.countClass}` : ""}`, opts.count));
  }
  btn.onclick = opts.onClick;
  return btn;
}

function renderSidebar(): void {
  const stats = taskStats();
  sidebar.innerHTML = "";

  const brand = el("div", "brand");
  brand.append(el("div", "logo", "🤖"), el("span", "", "AGENT COMPANY PLATFORM"));
  sidebar.append(brand);

  sidebar.append(navButton("🏙  Campus", {
    active: view.kind === "company", onClick: () => setView({ kind: "company" }),
  }));

  sidebar.append(el("div", "section-title", "Départements"));
  for (const dept of overview.departments) {
    const agents = overview.agents.filter((a) => {
      const team = overview.teams.find((t) => t.id === a.team_id);
      const project = overview.projects.find((p) => p.id === team?.project_id);
      return project?.department_id === dept.id;
    });
    sidebar.append(navButton(`${deptIcon(dept.department_type)}  ${dept.name}`, {
      active: view.kind === "department" && view.id === dept.id,
      count: String(agents.length),
      onClick: () => setView({ kind: "department", id: dept.id }),
    }));
  }

  sidebar.append(el("div", "section-title", "Workspaces"));
  for (const ws of overview.workspaces) {
    sidebar.append(navButton(`🗂  ${ws.name}`, {
      active: view.kind === "workspace" && view.id === ws.id,
      onClick: () => setView({ kind: "workspace", id: ws.id }),
    }));
    for (const project of overview.projects.filter((p) => p.workspace_id === ws.id)) {
      sidebar.append(navButton(`▸ ${project.name}`, {
        active: view.kind === "project" && view.id === project.id,
        sub: true,
        onClick: () => setView({ kind: "project", id: project.id }),
      }));
    }
  }

  sidebar.append(el("div", "section-title", "Raccourcis"));
  sidebar.append(navButton("📋  Tâches ouvertes", {
    count: String(stats.open), countClass: stats.open ? "warn" : "",
    onClick: () => setView({ kind: "company" }),
  }));
  sidebar.append(navButton("🖐  Approbations", {
    count: String(approvals.length), countClass: approvals.length ? "warn" : "",
    onClick: () => document.getElementById("panel-approvals")?.scrollIntoView({ behavior: "smooth" }),
  }));
  sidebar.append(navButton("🚨  Incidents", {
    count: String(stats.failed), countClass: stats.failed ? "bad" : "",
    onClick: () => document.getElementById("panel-incidents")?.scrollIntoView({ behavior: "smooth" }),
  }));
  sidebar.append(navButton("🖼  Galerie d'assets", {
    onClick: () => engine.showGallery(),
  }));
  if (view.kind === "project") {
    const projectId = view.id;
    sidebar.append(navButton("＋ Tâche de démo", {
      onClick: async () => {
        const title = prompt("Titre de la tâche ?", "Nouvelle tâche de démonstration");
        if (title) {
          await createAndQueueTask(projectId, title);
          await refreshOverview();
        }
      },
    }));
  }

  sidebar.append(el("div", "section-title", "Statut global"));
  const status = el("div", "global-status");
  const online = overview.agents.filter((a) => a.status !== "offline").length;
  const busy = overview.agents.filter((a) =>
    ["working", "thinking", "reviewing"].includes(a.status)).length;
  status.append(
    statusLine("#57cc99", "Agents en ligne", `${online}/${overview.agents.length}`),
    statusLine("#e9c46a", "Agents occupés", String(busy)),
    statusLine("#7c5cff", "Réussite des runs", `${stats.health}%`),
  );
  const spark = el("canvas", "spark") as HTMLCanvasElement;
  status.append(spark);
  sidebar.append(status);
  requestAnimationFrame(() => drawSparkline(spark));

  const user = el("div", "user-card");
  const avatar = el("div", "avatar", "PB");
  const who = el("div", "who");
  who.append(el("b", "", "Paul Berdier"), el("small", "", "Director"));
  const dot = el("div", "online", "● en ligne");
  user.append(avatar, who, dot);
  sidebar.append(user);
}

function statusLine(color: string, label: string, value: string): HTMLElement {
  const line = el("div", "status-line");
  const left = el("span");
  const dot = el("span", "dot");
  dot.style.background = color;
  left.append(dot, document.createTextNode(label));
  line.append(left, el("b", "", value));
  return line;
}

function drawSparkline(canvas: HTMLCanvasElement): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  canvas.width = canvas.clientWidth || 180;
  canvas.height = 26;
  const now = Date.now();
  const buckets = new Array(20).fill(0);
  for (const event of eventLog) {
    const age = now - new Date(event.occurred_at).getTime();
    const bucket = 19 - Math.floor(age / 60_000);
    if (bucket >= 0 && bucket < 20) buckets[bucket]++;
  }
  const max = Math.max(1, ...buckets);
  ctx.strokeStyle = "#7c5cff";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  buckets.forEach((v, i) => {
    const x = (i / 19) * (canvas.width - 2) + 1;
    const y = canvas.height - 3 - (v / max) * (canvas.height - 8);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
}

// ---------------------------------------------------------------- topbar

function renderTopbar(): void {
  const meta = viewMeta();
  topbar.innerHTML = "";
  topbar.append(el("div", "view-icon", meta.icon));
  const titles = el("div");
  titles.append(el("h1", "", meta.title), el("div", "subtitle", meta.subtitle));
  topbar.append(titles);

  const clock = el("div", "clock");
  const time = el("b", "", new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }));
  const date = el("small", "", new Date().toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }));
  clock.append(time, date);
  topbar.append(clock);

  const cta = el("button", "cta", ">_ Command Center");
  cta.onclick = () => engine.showGallery();
  topbar.append(cta);
}

// ---------------------------------------------------------------- KPIs

function kpiCard(icon: string, label: string, value: string, hint: string, color: string): HTMLElement {
  const card = el("div", "kpi");
  const iconBox = el("div", "icon", icon);
  iconBox.style.color = color;
  const body = el("div");
  body.append(el("div", "label", label), el("div", "value", value), el("div", "hint", hint));
  card.append(iconBox, body);
  return card;
}

function renderKpis(): void {
  const stats = taskStats();
  const online = overview.agents.filter((a) => a.status !== "offline").length;
  kpis.innerHTML = "";
  kpis.append(
    kpiCard("🤖", "Agents en ligne", String(online), `sur ${overview.agents.length} agents`, "#3fa7d6"),
    kpiCard("💚", "Santé", `${taskStats().health}%`, stats.failed ? "runs en échec" : "excellent", "#57cc99"),
    kpiCard("✅", "Tâches terminées", String(stats.done), "depuis le début", "#57cc99"),
    kpiCard("⚡", "Tâches actives", String(stats.active), "en cours", "#e9c46a"),
    kpiCard("🖐", "Approbations", String(approvals.length), "en attente", "#f4845f"),
    kpiCard("🚨", "Incidents", String(stats.failed), "tâches en échec", "#e63946"),
  );
}

// ---------------------------------------------------------------- rail

function railPanel(id: string, title: string): HTMLElement {
  const panel = el("div", "rail-panel");
  panel.id = id;
  panel.append(el("h3", "", title));
  return panel;
}

function renderRail(): void {
  rail.innerHTML = "";

  if (selectedAgentId) {
    const agent = overview.agents.find((a) => a.id === selectedAgentId);
    if (agent) {
      const panel = railPanel("panel-agent", "Agent sélectionné");
      panel.classList.add("agent-card");
      const row = el("div", "rail-row");
      const grow = el("div", "grow");
      grow.append(el("b", "", `👤 ${agent.name}`), el("div", "role", agent.role_id));
      row.append(grow, badge(agent.status, statusColor(agent.status)));
      panel.append(row);
      const task = overview.tasks.filter((t) => t.agent_instance_id === agent.id).at(-1);
      if (task) {
        const taskRow = el("div", "rail-row");
        taskRow.append(el("small", "grow", `Tâche : ${task.title}`));
        panel.append(taskRow);
      }
      rail.append(panel);
    }
  }

  // santé des départements
  const health = railPanel("panel-health", "Santé des départements");
  for (const dept of overview.departments) {
    const stats = taskStats(deptProjects(dept.id));
    const row = el("div", "rail-row");
    row.append(
      el("span", "", deptIcon(dept.department_type)),
      el("span", "grow", dept.name),
      el("b", "", `${stats.health}%`),
    );
    const bar = el("div", "bar");
    const fill = el("i");
    fill.style.width = `${stats.health}%`;
    fill.style.background = stats.health > 90 ? "var(--green)" : stats.health > 60 ? "var(--yellow)" : "var(--red)";
    bar.append(fill);
    row.append(bar);
    health.append(row);
  }
  rail.append(health);

  // files actives par projet
  const queues = railPanel("panel-queues", "Files actives");
  let hasQueue = false;
  for (const project of overview.projects) {
    const open = overview.tasks.filter((t) =>
      t.project_id === project.id && !["done", "failed"].includes(t.status));
    if (!open.length) continue;
    hasQueue = true;
    const urgent = open.some((t) => t.priority <= 1);
    const level = urgent ? "high" : open.length > 2 ? "medium" : "low";
    const row = el("div", "rail-row");
    row.append(
      el("span", "grow", project.name),
      el("b", "", String(open.length)),
      el("span", `pill ${level}`, urgent ? "haute" : open.length > 2 ? "moyenne" : "basse"),
    );
    queues.append(row);
  }
  if (!hasQueue) queues.append(el("div", "empty", "Aucune tâche ouverte."));
  rail.append(queues);

  // approbations (orchestrateur manuel du gateway)
  const approvalsPanel = railPanel("panel-approvals", `Approbations en attente (${approvals.length})`);
  for (const approval of approvals.slice(0, 6)) {
    const row = el("div", "rail-row");
    const goal = (approval.payload as { goal?: string }).goal ?? approval.kind;
    row.append(
      el("span", "", "🖐"),
      el("span", "grow", String(goal)),
      el("small", "", approval.kind),
    );
    approvalsPanel.append(row);
  }
  if (!approvals.length) {
    approvalsPanel.append(el("div", "empty", "Aucune demande (orchestrateur mock actif)."));
  }
  rail.append(approvalsPanel);

  // incidents = tâches en échec
  const stats = taskStats();
  const incidents = railPanel("panel-incidents", `Incidents actifs (${stats.failed})`);
  for (const task of overview.tasks.filter((t) => t.status === "failed").slice(0, 6)) {
    const project = overview.projects.find((p) => p.id === task.project_id);
    const row = el("div", "rail-row");
    row.append(
      el("span", "pill high", "échec"),
      el("span", "grow", task.title),
      el("small", "", project?.name ?? ""),
    );
    incidents.append(row);
  }
  if (!stats.failed) incidents.append(el("div", "empty", "Aucun incident. 🎉"));
  rail.append(incidents);

  // événements récents
  const eventsPanel = railPanel("panel-events", "Événements récents");
  for (const event of eventLog.slice(0, 14)) {
    const entry = el("div", "log-entry");
    const time = document.createElement("time");
    time.textContent = formatTime(event.occurred_at);
    entry.append(time, el("span", "grow", describeEvent(event)));
    eventsPanel.append(entry);
  }
  if (!eventLog.length) eventsPanel.append(el("div", "empty", "En attente d'activité..."));
  rail.append(eventsPanel);
}

function describeEvent(event: AcpEvent): string {
  const payload = event.payload as Record<string, string | number | undefined>;
  switch (event.type) {
    case "agent.status_changed":
      return `${payload.name ?? "Agent"} → ${payload.status}`;
    case "task.status_changed":
      return `« ${payload.title} » → ${payload.status}`;
    case "task.progress":
      return `${payload.agent ?? ""} : ${payload.step} (${payload.index}/${payload.total})`;
    case "task.plan_ready":
      return `Plan prêt (${payload.steps} étapes) : ${payload.title}`;
    case "task.created":
      return `Nouvelle tâche : ${payload.title}`;
    case "task.queued":
      return `En file : ${payload.title}`;
    case "task.completed":
      return `✔ Terminé : ${payload.title}`;
    case "task.failed":
      return `✖ Échec : ${payload.title}`;
    default:
      return event.type;
  }
}

function renderAll(): void {
  renderSidebar();
  renderTopbar();
  renderKpis();
  renderRail();
  engine.setScene(currentScene());
}

// ---------------------------------------------------------------- données

async function refreshOverview(): Promise<void> {
  const [nextOverview, nextApprovals] = await Promise.all([
    fetchOverview(),
    fetchPendingApprovals(),
  ]);
  overview = nextOverview;
  approvals = nextApprovals;
  const missing = overview.departments.filter((d) => !officeConfigs[d.id]);
  await Promise.all(missing.map(async (dept) => {
    try {
      officeConfigs[dept.id] = await fetchOfficeConfig(dept.id);
    } catch {
      /* configuration par défaut côté moteur */
    }
  }));
  renderAll();
}

function scheduleRefresh(): void {
  if (refreshTimer !== null) return;
  refreshTimer = window.setTimeout(async () => {
    refreshTimer = null;
    await refreshOverview();
  }, 1500);
}

function handleEvent(event: AcpEvent): void {
  eventLog.unshift(event);
  if (eventLog.length > 400) eventLog.pop();

  if (event.type === "agent.status_changed" && event.agent_instance_id) {
    const status = String((event.payload as { status?: string }).status ?? "idle");
    engine.updateEntityStatus(event.agent_instance_id, status);
    const agent = overview.agents.find((a) => a.id === event.agent_instance_id);
    if (agent) agent.status = status as typeof agent.status;
  }
  if (event.type === "task.progress" && event.agent_instance_id) {
    engine.emote(event.agent_instance_id, "task-progress");
  }
  if (event.type === "task.completed" && event.agent_instance_id) {
    engine.emote(event.agent_instance_id, "task-complete", 4000);
  }
  if (event.type === "task.failed" && event.agent_instance_id) {
    engine.emote(event.agent_instance_id, "task-failed", 4000);
  }
  if (event.project_id) engine.pulseRoom(event.project_id);
  if (event.department_id) engine.pulseRoom(event.department_id);

  if (event.type.startsWith("task.") && event.type !== "task.progress") {
    scheduleRefresh();
  }
  renderRail();
  renderKpis();
}

// ---------------------------------------------------------------- boot

async function boot(): Promise<void> {
  const params = new URLSearchParams(location.search);
  const mode = (params.get("renderer") ?? "auto") as RendererMode;
  engine = await createOfficeRenderer({
    mount: canvasWrap,
    mode,
    forceTimeout: params.get("timer") === "1",
    callbacks: {
      onRoomClick: (roomId) => {
        if (view.kind === "company" && overview.departments.some((d) => d.id === roomId)) {
          setView({ kind: "department", id: roomId });
        } else if (overview.projects.some((p) => p.id === roomId)) {
          setView({ kind: "project", id: roomId });
        }
      },
      onEntityClick: (entityId) => {
        selectedAgentId = entityId;
        engine.selectEntity(entityId);
        renderRail();
      },
      onRendererFallback: (reason) =>
        console.warn(`Renderer de secours (canvas) : ${reason}`),
    },
  });
  (window as { __acpEngine?: IOfficeRenderer }).__acpEngine = engine; // aide au debug
  eventLog = await fetchRecentEvents();
  await refreshOverview();
  connectEvents(handleEvent);
  window.setInterval(renderTopbar, 30_000); // horloge

  // route développeur #/dev/assets[?pack=...] — désactivable en production
  const devGalleryEnabled =
    !import.meta.env.PROD || import.meta.env.VITE_ACP_DEV_GALLERY === "1";
  const applyHashRoute = () => {
    if (!devGalleryEnabled) return;
    const hash = location.hash;
    if (hash.startsWith("#/dev/assets")) {
      const pack = new URLSearchParams(hash.split("?")[1] ?? "").get("pack") ?? undefined;
      engine.showGallery(pack);
    }
  };
  window.addEventListener("hashchange", applyHashRoute);
  applyHashRoute();
  if (params.get("gallery") === "1") engine.showGallery();
}

boot().catch((error) => {
  document.body.innerHTML =
    `<div style="padding:40px;font-family:monospace;color:#e63946">` +
    `Impossible de joindre l'API (${error}).<br>` +
    `Lancez les services : <code>./scripts/dev.ps1</code></div>`;
});
