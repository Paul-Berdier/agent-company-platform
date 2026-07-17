import "@acp/ui/src/tokens.css";
import "@acp/ui/src/pixel-frames.css";
import "./style.css";

import type { AcpEvent, Overview } from "@acp/contracts";
import {
  createOfficeRenderer,
  type IOfficeRenderer,
  type RendererMode,
} from "@acp/pixel-office-engine";
import { enablePixelUi } from "@acp/ui";

import {
  connectEvents,
  createAndQueueTask,
  fetchCompanyLevel,
  fetchOfficeConfig,
  fetchOverview,
  fetchPendingApprovals,
  fetchRecentEvents,
  type CompanyLevel,
  type PendingApproval,
} from "./api";
import {
  companyScene,
  departmentScene,
  projectScene,
  workspaceScene,
  type OfficeConfigMap,
} from "./scene";
import {
  renderBottombar,
  renderHud,
  renderKpis,
  renderRail,
  renderTopbar,
  type HudContext,
  type View,
} from "./ui/hud";

let overview: Overview;
const officeConfigs: OfficeConfigMap = {};
let view: View = { kind: "company" };
let engine: IOfficeRenderer;
let selectedAgentId: string | null = null;
let approvals: PendingApproval[] = [];
let eventLog: AcpEvent[] = [];
let refreshTimer: number | null = null;
let rendererName = "auto";
let wsConnected = false;
let devGalleryEnabled = true;
let companyLevel: CompanyLevel | null = null;

const canvasWrap = document.getElementById("canvas-wrap")!;

// ------------------------------------------------------------------- vues

function hudContext(): HudContext {
  return {
    overview,
    approvals,
    eventLog,
    view,
    selectedAgentId,
    rendererName,
    wsConnected,
    devGalleryEnabled,
    companyLevel,
    setView,
    selectAgent(id) {
      selectedAgentId = id;
      engine.selectEntity(id);
      renderRail(this);
    },
    showGallery: () => engine.showGallery(),
    zoomStep: (direction) => engine.zoomStep(direction),
    createDemoTask: async (projectId) => {
      await createAndQueueTask(projectId, "Nouvelle tâche de démonstration");
      await refreshOverview();
    },
  };
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
    case "company": return companyScene(overview, officeConfigs, companyLevel ?? undefined);
    case "workspace": return workspaceScene(overview, view.id, officeConfigs);
    case "project": return projectScene(overview, view.id, officeConfigs);
    case "department": return departmentScene(overview, view.id, officeConfigs);
  }
}

function renderAll(): void {
  renderHud(hudContext());
  engine.setScene(currentScene());
}

// ---------------------------------------------------------------- données

async function refreshOverview(): Promise<void> {
  const [nextOverview, nextApprovals, nextLevel] = await Promise.all([
    fetchOverview(),
    fetchPendingApprovals(),
    fetchCompanyLevel(),
  ]);
  overview = nextOverview;
  approvals = nextApprovals;
  companyLevel = nextLevel;
  const missing = overview.departments.filter((d) => !officeConfigs[d.id]);
  await Promise.all(missing.map(async (dept) => {
    try {
      const deptProjectIds = new Set(
        overview.projects.filter((p) => p.department_id === dept.id).map((p) => p.id));
      const teamIds = new Set(
        overview.teams.filter((t) => deptProjectIds.has(t.project_id)).map((t) => t.id));
      const agentCount = overview.agents.filter((a) => a.team_id && teamIds.has(a.team_id)).length;
      officeConfigs[dept.id] = await fetchOfficeConfig(dept.id, agentCount);
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
  const ctx = hudContext();
  renderRail(ctx);
  renderKpis(ctx);
}

// ------------------------------------------------------------------- boot

async function boot(): Promise<void> {
  const params = new URLSearchParams(location.search);
  const mode = (params.get("renderer") ?? "auto") as RendererMode;
  devGalleryEnabled = !import.meta.env.PROD || import.meta.env.VITE_ACP_DEV_GALLERY === "1";

  engine = await createOfficeRenderer({
    mount: canvasWrap,
    mode,
    forceTimeout: params.get("timer") === "1",
    debug: params.get("debug") === "1",
    callbacks: {
      onRoomClick: (roomId) => {
        if (view.kind === "company" && overview.departments.some((d) => d.id === roomId)) {
          setView({ kind: "department", id: roomId });
        } else if (overview.projects.some((p) => p.id === roomId)) {
          setView({ kind: "project", id: roomId });
        }
      },
      onEntityClick: (entityId) => hudContext().selectAgent(entityId),
      onRendererFallback: (reason) => {
        rendererName = "canvas (fallback)";
        console.warn(`Renderer de secours (canvas) : ${reason}`);
      },
    },
  });
  rendererName = (engine as { name?: string }).name ?? (mode === "canvas" ? "canvas" : "phaser");
  (window as { __acpEngine?: IOfficeRenderer }).__acpEngine = engine; // aide au debug

  await enablePixelUi();
  eventLog = await fetchRecentEvents();
  await refreshOverview();
  connectEvents(handleEvent, (connected) => {
    wsConnected = connected;
    renderBottombar(hudContext());
  });
  window.setInterval(() => renderTopbar(hudContext()), 30_000); // horloge

  // route développeur #/dev/assets[?pack=...] — désactivable en production
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
