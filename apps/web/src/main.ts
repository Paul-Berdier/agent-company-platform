import "./style.css";

import type { AcpEvent, Overview } from "@acp/contracts";
import {
  createOfficeRenderer,
  type IOfficeRenderer,
  type RendererMode,
} from "@acp/pixel-office-engine";
import { badge, el, formatTime, statusColor } from "@acp/ui";

import { connectEvents, createAndQueueTask, fetchOfficeConfig, fetchOverview } from "./api";
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
const eventLog: AcpEvent[] = [];
let refreshTimer: number | null = null;

const sidebar = document.getElementById("sidebar")!;
const topbar = document.getElementById("topbar")!;
const inspector = document.getElementById("inspector")!;
const canvasWrap = document.getElementById("canvas-wrap")!;

function setView(next: View): void {
  view = next;
  renderAll();
}

function currentScene() {
  switch (view.kind) {
    case "company": return companyScene(overview, officeConfigs);
    case "workspace": return workspaceScene(overview, view.id, officeConfigs);
    case "project": return projectScene(overview, view.id, officeConfigs);
    case "department": return departmentScene(overview, view.id, officeConfigs);
  }
}

function viewTitle(): string {
  switch (view.kind) {
    case "company":
      return overview.organizations[0]?.name ?? "Entreprise";
    case "workspace":
      return `Workspace — ${overview.workspaces.find((w) => w.id === view.id)?.name ?? "?"}`;
    case "project":
      return `Projet — ${overview.projects.find((p) => p.id === view.id)?.name ?? "?"}`;
    case "department":
      return `Département — ${overview.departments.find((d) => d.id === view.id)?.name ?? "?"}`;
  }
}

// ------------------------------------------------------------------- sidebar

function navButton(label: string, active: boolean, onClick: () => void, sub = false): HTMLButtonElement {
  const btn = el("button", `nav-item${sub ? " sub" : ""}${active ? " active" : ""}`, label);
  btn.onclick = onClick;
  return btn;
}

function renderSidebar(): void {
  sidebar.innerHTML = "";
  sidebar.append(el("div", "section-title", "Entreprise"));
  sidebar.append(navButton("🏢 Vue entreprise", view.kind === "company", () => setView({ kind: "company" })));

  sidebar.append(el("div", "section-title", "Workspaces"));
  for (const ws of overview.workspaces) {
    sidebar.append(navButton(
      `🗂 ${ws.name} (${ws.kind})`,
      view.kind === "workspace" && view.id === ws.id,
      () => setView({ kind: "workspace", id: ws.id }),
    ));
    for (const project of overview.projects.filter((p) => p.workspace_id === ws.id)) {
      sidebar.append(navButton(
        `▸ ${project.name}`,
        view.kind === "project" && view.id === project.id,
        () => setView({ kind: "project", id: project.id }),
        true,
      ));
    }
  }

  sidebar.append(el("div", "section-title", "Départements"));
  for (const dept of overview.departments) {
    sidebar.append(navButton(
      `⚙ ${dept.name}`,
      view.kind === "department" && view.id === dept.id,
      () => setView({ kind: "department", id: dept.id }),
    ));
  }

  if (view.kind === "project") {
    const projectId = view.id;
    const btn = el("button", "action-btn", "+ Tâche de démo");
    btn.onclick = async () => {
      const title = prompt("Titre de la tâche ?", "Nouvelle tâche de démonstration");
      if (title) {
        await createAndQueueTask(projectId, title);
        await refreshOverview();
      }
    };
    sidebar.append(btn);
  }
}

// ------------------------------------------------------------------- inspector

function renderInspector(): void {
  inspector.innerHTML = "";
  if (selectedAgentId) {
    const agent = overview.agents.find((a) => a.id === selectedAgentId);
    if (agent) {
      const card = el("div", "inspector-card");
      card.append(el("h3", "", `👤 ${agent.name}`));
      const status = el("p", "", "Statut : ");
      status.append(badge(agent.status, statusColor(agent.status)));
      card.append(status);
      card.append(el("p", "", `Rôle : ${agent.role_id}`));
      card.append(el("p", "", `Module : ${agent.module}`));
      const tasks = overview.tasks.filter((t) => t.agent_instance_id === agent.id);
      if (tasks.length) {
        card.append(el("p", "", `Tâche : ${tasks[tasks.length - 1].title}`));
      }
      inspector.append(card);
    }
  }

  if (view.kind === "project") {
    const card = el("div", "inspector-card");
    card.append(el("h3", "", "📋 Tâches du projet"));
    const projectTasks = overview.tasks.filter((t) => t.project_id === (view as { id: string }).id);
    for (const task of projectTasks) {
      const p = el("p", "", task.title + " ");
      p.append(badge(task.status, statusColor(task.status)));
      card.append(p);
    }
    if (!projectTasks.length) card.append(el("p", "muted", "Aucune tâche."));
    inspector.append(card);
  }

  const logCard = el("div", "inspector-card");
  logCard.append(el("h3", "", "🔔 Événements"));
  for (const event of eventLog.slice(0, 12)) {
    const entry = el("div", "log-entry");
    const time = document.createElement("time");
    time.textContent = formatTime(event.occurred_at);
    entry.append(time, describeEvent(event));
    logCard.append(entry);
  }
  if (!eventLog.length) logCard.append(el("p", "muted", "En attente d'activité..."));
  inspector.append(logCard);
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
    case "task.completed":
      return `✔ Terminé : ${payload.title}`;
    case "task.failed":
      return `✖ Échec : ${payload.title}`;
    default:
      return event.type;
  }
}

// ------------------------------------------------------------------- topbar

function renderTopbar(): void {
  topbar.innerHTML = "";
  topbar.append(el("h1", "", `🏙 ${viewTitle()}`));
  const counts = el("span", "muted",
    `${overview.agents.length} agents · ${overview.projects.length} projets · ` +
    `${overview.tasks.filter((t) => !["done", "failed"].includes(t.status)).length} tâches ouvertes`);
  topbar.append(counts);
}

function renderAll(): void {
  renderSidebar();
  renderTopbar();
  renderInspector();
  engine.setScene(currentScene());
}

// ------------------------------------------------------------------- données

async function refreshOverview(): Promise<void> {
  overview = await fetchOverview();
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
  if (eventLog.length > 50) eventLog.pop();

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
  renderInspector();
}

// ------------------------------------------------------------------- boot

async function boot(): Promise<void> {
  const params = new URLSearchParams(location.search);
  const mode = (params.get("renderer") ?? "auto") as RendererMode;
  engine = await createOfficeRenderer({
    mount: canvasWrap,
    mode,
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
        renderInspector();
      },
      onRendererFallback: (reason) =>
        console.warn(`Renderer de secours (canvas) : ${reason}`),
    },
  });
  await refreshOverview();
  connectEvents(handleEvent);
  if (params.get("gallery") === "1") engine.showGallery();
}

boot().catch((error) => {
  document.body.innerHTML =
    `<div style="padding:40px;font-family:monospace;color:#e63946">` +
    `Impossible de joindre l'API (${error}).<br>` +
    `Lancez les services : <code>./scripts/dev.ps1</code></div>`;
});
