/**
 * HUD de l'application : sidebar, topbar, KPIs, rail droit, barre du bas.
 * Rendu pur : tout l'état vient du HudContext fourni par main.ts.
 * Design system hybride : contenus HTML/CSS, cadres pixel art optionnels
 * (packages/ui/pixel-frames.css, activés si les assets licenciés existent).
 */

import type { AcpEvent, Overview } from "@acp/contracts";
import { badge, el, formatTime, statusColor } from "@acp/ui";

import type { PendingApproval } from "../api";

export type View =
  | { kind: "company" }
  | { kind: "workspace"; id: string }
  | { kind: "project"; id: string }
  | { kind: "department"; id: string };

export interface HudContext {
  overview: Overview;
  approvals: PendingApproval[];
  eventLog: AcpEvent[];
  view: View;
  selectedAgentId: string | null;
  rendererName: string;
  wsConnected: boolean;
  devGalleryEnabled: boolean;
  setView(view: View): void;
  selectAgent(id: string | null): void;
  showGallery(): void;
  zoomStep(direction: 1 | -1): void;
  createDemoTask(projectId: string): Promise<void>;
}

const sidebar = () => document.getElementById("sidebar")!;
const topbar = () => document.getElementById("topbar")!;
const kpis = () => document.getElementById("kpis")!;
const rail = () => document.getElementById("rail")!;
const bottombar = () => document.getElementById("bottombar")!;

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
  health: number;
}

function taskStats(overview: Overview, projectIds?: Set<string>): TaskStats {
  const tasks = overview.tasks.filter((t) => !projectIds || projectIds.has(t.project_id));
  const done = tasks.filter((t) => t.status === "done").length;
  const failed = tasks.filter((t) => t.status === "failed").length;
  const open = tasks.filter((t) => !["done", "failed"].includes(t.status)).length;
  const active = tasks.filter((t) =>
    ["queued", "planning", "in_progress", "review"].includes(t.status)).length;
  const health = done + failed === 0 ? 100 : Math.round((done / (done + failed)) * 1000) / 10;
  return { open, active, done, failed, health };
}

function deptProjects(overview: Overview, deptId: string): Set<string> {
  return new Set(overview.projects.filter((p) => p.department_id === deptId).map((p) => p.id));
}

function viewMeta(ctx: HudContext): { icon: string; title: string; subtitle: string } {
  const { view, overview } = ctx;
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

function statusLine(color: string, label: string, value: string): HTMLElement {
  const line = el("div", "status-line");
  const left = el("span");
  const dot = el("span", "dot");
  dot.style.background = color;
  left.append(dot, document.createTextNode(label));
  line.append(left, el("b", "", value));
  return line;
}

function drawSparkline(canvas: HTMLCanvasElement, eventLog: AcpEvent[]): void {
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

function describeEvent(event: AcpEvent): string {
  const payload = event.payload as Record<string, string | number | undefined>;
  switch (event.type) {
    case "agent.status_changed": return `${payload.name ?? "Agent"} → ${payload.status}`;
    case "task.status_changed": return `« ${payload.title} » → ${payload.status}`;
    case "task.progress":
      return `${payload.agent ?? ""} : ${payload.step} (${payload.index}/${payload.total})`;
    case "task.plan_ready": return `Plan prêt (${payload.steps} étapes) : ${payload.title}`;
    case "task.created": return `Nouvelle tâche : ${payload.title}`;
    case "task.queued": return `En file : ${payload.title}`;
    case "task.completed": return `✔ Terminé : ${payload.title}`;
    case "task.failed": return `✖ Échec : ${payload.title}`;
    default: return event.type;
  }
}

// ---------------------------------------------------------------- sidebar

export function renderSidebar(ctx: HudContext): void {
  const { overview, view, approvals } = ctx;
  const stats = taskStats(overview);
  const host = sidebar();
  host.innerHTML = "";

  const brand = el("div", "brand");
  brand.append(el("div", "logo", "🤖"), el("span", "", "AGENT COMPANY PLATFORM"));
  host.append(brand);

  host.append(navButton("🏙  Campus", {
    active: view.kind === "company", onClick: () => ctx.setView({ kind: "company" }),
  }));

  host.append(el("div", "section-title", "Départements"));
  for (const dept of overview.departments) {
    const agents = overview.agents.filter((a) => {
      const team = overview.teams.find((t) => t.id === a.team_id);
      const project = overview.projects.find((p) => p.id === team?.project_id);
      return project?.department_id === dept.id;
    });
    host.append(navButton(`${deptIcon(dept.department_type)}  ${dept.name}`, {
      active: view.kind === "department" && view.id === dept.id,
      count: String(agents.length),
      onClick: () => ctx.setView({ kind: "department", id: dept.id }),
    }));
  }

  host.append(el("div", "section-title", "Workspaces"));
  for (const ws of overview.workspaces) {
    host.append(navButton(`🗂  ${ws.name}`, {
      active: view.kind === "workspace" && view.id === ws.id,
      onClick: () => ctx.setView({ kind: "workspace", id: ws.id }),
    }));
    for (const project of overview.projects.filter((p) => p.workspace_id === ws.id)) {
      host.append(navButton(`▸ ${project.name}`, {
        active: view.kind === "project" && view.id === project.id,
        sub: true,
        onClick: () => ctx.setView({ kind: "project", id: project.id }),
      }));
    }
  }

  host.append(el("div", "section-title", "Raccourcis"));
  host.append(navButton("📋  Tâches ouvertes", {
    count: String(stats.open), countClass: stats.open ? "warn" : "",
    onClick: () => ctx.setView({ kind: "company" }),
  }));
  host.append(navButton("🖐  Approbations", {
    count: String(approvals.length), countClass: approvals.length ? "warn" : "",
    onClick: () => document.getElementById("panel-approvals")?.scrollIntoView({ behavior: "smooth" }),
  }));
  host.append(navButton("🚨  Incidents", {
    count: String(stats.failed), countClass: stats.failed ? "bad" : "",
    onClick: () => document.getElementById("panel-incidents")?.scrollIntoView({ behavior: "smooth" }),
  }));
  if (ctx.devGalleryEnabled) {
    host.append(navButton("🖼  Galerie d'assets", { onClick: () => ctx.showGallery() }));
  }
  if (view.kind === "project") {
    const projectId = view.id;
    host.append(navButton("＋ Tâche de démo", {
      onClick: async () => {
        const title = prompt("Titre de la tâche ?", "Nouvelle tâche de démonstration");
        if (title) await ctx.createDemoTask(projectId);
      },
    }));
  }

  host.append(el("div", "section-title", "Statut global"));
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
  host.append(status);
  requestAnimationFrame(() => drawSparkline(spark, ctx.eventLog));

  const user = el("div", "user-card");
  const avatar = el("div", "avatar", "PB");
  const who = el("div", "who");
  who.append(el("b", "", "Paul Berdier"), el("small", "", "Director"));
  user.append(avatar, who, el("div", "online", "● en ligne"));
  host.append(user);
}

// ---------------------------------------------------------------- topbar

export function renderTopbar(ctx: HudContext): void {
  const meta = viewMeta(ctx);
  const host = topbar();
  host.innerHTML = "";
  host.append(el("div", "view-icon", meta.icon));
  const titles = el("div");
  titles.append(el("h1", "", meta.title), el("div", "subtitle", meta.subtitle));
  host.append(titles);

  const clock = el("div", "clock");
  clock.append(
    el("b", "", new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })),
    el("small", "", new Date().toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })),
  );
  host.append(clock);

  if (ctx.devGalleryEnabled) {
    const cta = el("button", "cta", ">_ Command Center");
    cta.onclick = () => ctx.showGallery();
    host.append(cta);
  }
}

// ------------------------------------------------------------------ KPIs

function kpiCard(icon: string, label: string, value: string, hint: string, color: string): HTMLElement {
  const card = el("div", "kpi");
  const iconBox = el("div", "icon", icon);
  iconBox.style.color = color;
  const body = el("div");
  body.append(el("div", "label", label), el("div", "value", value), el("div", "hint", hint));
  card.append(iconBox, body);
  return card;
}

export function renderKpis(ctx: HudContext): void {
  const { overview, approvals } = ctx;
  const stats = taskStats(overview);
  const online = overview.agents.filter((a) => a.status !== "offline").length;
  const host = kpis();
  host.innerHTML = "";
  host.append(
    kpiCard("🤖", "Agents en ligne", String(online), `sur ${overview.agents.length} agents`, "#3fa7d6"),
    kpiCard("💚", "Santé", `${stats.health}%`, stats.failed ? "runs en échec" : "excellent", "#57cc99"),
    kpiCard("✅", "Tâches terminées", String(stats.done), "depuis le début", "#57cc99"),
    kpiCard("⚡", "Tâches actives", String(stats.active), "en cours", "#e9c46a"),
    kpiCard("🖐", "Approbations", String(approvals.length), "en attente", "#f4845f"),
    kpiCard("🚨", "Incidents", String(stats.failed), "tâches en échec", "#e63946"),
  );
}

// ------------------------------------------------------------------ rail

function railPanel(id: string, title: string): HTMLElement {
  const panel = el("div", "rail-panel");
  panel.id = id;
  panel.append(el("h3", "", title));
  return panel;
}

export function renderRail(ctx: HudContext): void {
  const { overview, approvals, eventLog, selectedAgentId, view } = ctx;
  const host = rail();
  host.innerHTML = "";

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
      host.append(panel);
    }
  }

  const health = railPanel("panel-health", "Santé des départements");
  for (const dept of overview.departments) {
    const stats = taskStats(overview, deptProjects(overview, dept.id));
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
  host.append(health);

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
  host.append(queues);

  const approvalsPanel = railPanel("panel-approvals", `Approbations en attente (${approvals.length})`);
  for (const approval of approvals.slice(0, 6)) {
    const row = el("div", "rail-row");
    const goal = (approval.payload as { goal?: string }).goal ?? approval.kind;
    row.append(el("span", "", "🖐"), el("span", "grow", String(goal)), el("small", "", approval.kind));
    approvalsPanel.append(row);
  }
  if (!approvals.length) {
    approvalsPanel.append(el("div", "empty", "Aucune demande (orchestrateur mock actif)."));
  }
  host.append(approvalsPanel);

  const stats = taskStats(overview);
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
  host.append(incidents);

  const eventsPanel = railPanel("panel-events", "Événements récents");
  for (const event of eventLog.slice(0, 14)) {
    const entry = el("div", "log-entry");
    const time = document.createElement("time");
    time.textContent = formatTime(event.occurred_at);
    entry.append(time, el("span", "grow", describeEvent(event)));
    eventsPanel.append(entry);
  }
  if (!eventLog.length) eventsPanel.append(el("div", "empty", "En attente d'activité..."));
  host.append(eventsPanel);

  void view;
}

// -------------------------------------------------------------- bottombar

export function renderBottombar(ctx: HudContext): void {
  const host = bottombar();
  host.innerHTML = "";

  const mode = el("span", "bb-item", `Vue : ${ctx.view.kind}`);
  const renderer = el("span", "bb-item", `Renderer : ${ctx.rendererName}`);
  const live = el("span", "bb-item");
  const dot = el("span", "dot");
  dot.style.background = ctx.wsConnected ? "var(--green)" : "var(--red)";
  live.append(dot, document.createTextNode(ctx.wsConnected ? " live" : " hors ligne"));

  const zoomOut = el("button", "bb-btn", "−");
  zoomOut.title = "Zoom arrière";
  zoomOut.onclick = () => ctx.zoomStep(-1);
  const zoomIn = el("button", "bb-btn", "＋");
  zoomIn.title = "Zoom avant";
  zoomIn.onclick = () => ctx.zoomStep(1);

  const fullscreen = el("button", "bb-btn", "⛶");
  fullscreen.title = "Plein écran";
  fullscreen.onclick = () => {
    const wrap = document.getElementById("canvas-wrap")!;
    if (document.fullscreenElement) document.exitFullscreen();
    else wrap.requestFullscreen();
  };

  const ambient = el("button", "bb-btn bb-disabled", "🌙 ambient");
  ambient.title = "Mode ambient (phase 8)";
  ambient.disabled = true;

  host.append(mode, renderer, live, el("span", "bb-spacer"), zoomOut, zoomIn, fullscreen, ambient);
}

// ------------------------------------------------------------------ tout

export function renderHud(ctx: HudContext): void {
  renderSidebar(ctx);
  renderTopbar(ctx);
  renderKpis(ctx);
  renderRail(ctx);
  renderBottombar(ctx);
}
