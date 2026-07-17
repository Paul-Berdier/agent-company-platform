/**
 * Mode wallpaper / ambient autonome (§28-31 du cahier des charges).
 *
 * Routes :
 *   /ambient                         salle pilote (4 à 8 agents si possible)
 *   /projects/:id/ambient            projet précis
 *   /ambient.html?view=company       compatibilité / vue campus
 *
 * Paramètres :
 *   ?profile=performance|balanced|cinematic   (défaut balanced)
 *   ?screensaver=1                            caméra automatique
 *   ?mock=1                                   force les données de démo
 *   ?renderer= / ?timer= / ?debug=            comme l'app principale
 */

import "@acp/ui/src/tokens.css";

import type { AcpEvent, Overview } from "@acp/contracts";
import {
  createOfficeRenderer,
  type IOfficeRenderer,
  type RendererMode,
  type SceneSpec,
} from "@acp/pixel-office-engine";

import {
  ambientAssetPackIds,
  ambientProfile,
  effectiveFps,
  focusAmbientProjectScene,
  resolveAmbientView,
  selectPilotProjectId,
  type AmbientView,
} from "./ambient-config";
import { connectEvents, fetchOfficeConfig, fetchOverview } from "./api";
import { MOCK_CONFIGS, MOCK_OVERVIEW } from "./mock-overview";
import { companyScene, projectScene, type OfficeConfigMap } from "./scene";

interface BatteryManagerLike extends EventTarget {
  charging: boolean;
}

interface NavigatorWithBattery extends Navigator {
  getBattery?: () => Promise<BatteryManagerLike>;
}

const params = new URLSearchParams(location.search);
const profile = ambientProfile(params.get("profile"));
const requestedView = resolveAmbientView(location.pathname, params.get("view")) ?? "pilot";

function requiredElement(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Conteneur #${id} absent`);
  return element;
}

const stage = requiredElement("ambient-stage");
const overlay = requiredElement("ambient-overlay");

document.title = "Agent Company — Ambient";
document.body.style.cssText =
  "margin:0;background:#0b0c12;overflow:hidden;height:100vh;font-family:var(--font-ui)";
stage.style.cssText = "position:fixed;inset:0";
overlay.style.cssText =
  "position:fixed;left:18px;bottom:14px;color:#e8eaf2;opacity:0.75;font-size:13px;" +
  "text-shadow:0 1px 3px #000;pointer-events:none;line-height:1.5";

let overview: Overview;
let dataSource: "api" | "demo" = "demo";
let wsConnected = false;
let visibleAgentIds = new Set<string>();

function renderOverlay(): void {
  const clock = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  const visibleAgents = visibleAgentIds.size
    ? overview.agents.filter((agent) => visibleAgentIds.has(agent.id))
    : overview.agents;
  const working = visibleAgents.filter((agent) =>
    ["working", "thinking", "reviewing"].includes(agent.status)).length;
  const source = dataSource === "demo"
    ? { label: "◌ DEMO", color: "#e9c46a" }
    : wsConnected
      ? { label: "● LIVE", color: "#57cc99" }
      : { label: "◔ LIVE · reconnexion", color: "#e9c46a" };

  const title = document.createElement("b");
  title.textContent = `${overview.organizations[0]?.name ?? "Agent Company"} · ${clock}`;
  const status = document.createElement("span");
  status.style.color = source.color;
  status.textContent = source.label;
  overlay.replaceChildren(
    title,
    document.createElement("br"),
    status,
    document.createTextNode(` · ${working} agent(s) au travail · ${visibleAgents.length} agents`),
  );
}

async function loadData(): Promise<{ configs: OfficeConfigMap }> {
  const configs: OfficeConfigMap = {};
  if (params.get("mock") !== "1") {
    try {
      overview = await Promise.race([
        fetchOverview(),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("timeout")), 2500)),
      ]);
      dataSource = "api";
      await Promise.all(overview.departments.map(async (department) => {
        try {
          configs[department.id] = await fetchOfficeConfig(department.id, 8);
        } catch {
          // Le moteur applique sa configuration de repli.
        }
      }));
      return { configs };
    } catch {
      // Backend injoignable : données de démonstration explicites.
    }
  }
  overview = MOCK_OVERVIEW;
  dataSource = "demo";
  return { configs: { ...MOCK_CONFIGS } };
}

function buildScene(configs: OfficeConfigMap): { scene: SceneSpec; view: AmbientView } {
  if (requestedView === "company") {
    return { scene: companyScene(overview, configs), view: requestedView };
  }
  if (requestedView.startsWith("project:")) {
    return {
      scene: focusAmbientProjectScene(
        projectScene(overview, requestedView.slice("project:".length), configs),
      ),
      view: requestedView,
    };
  }
  const projectId = selectPilotProjectId(overview);
  if (projectId) {
    return {
      scene: focusAmbientProjectScene(projectScene(overview, projectId, configs)),
      view: `project:${projectId}`,
    };
  }
  return { scene: companyScene(overview, configs), view: "company" };
}

async function getBattery(): Promise<BatteryManagerLike | null> {
  try {
    return await (navigator as NavigatorWithBattery).getBattery?.() ?? null;
  } catch {
    return null;
  }
}

async function boot(): Promise<void> {
  const [{ configs }, battery] = await Promise.all([loadData(), getBattery()]);
  const { scene, view } = buildScene(configs);
  visibleAgentIds = new Set(scene.entities.map((entity) => entity.id));
  const engine: IOfficeRenderer = await createOfficeRenderer({
    mount: stage,
    mode: (params.get("renderer") ?? "auto") as RendererMode,
    forceTimeout: params.get("timer") === "1",
    debug: params.get("debug") === "1",
    fpsTarget: effectiveFps(profile.fpsTarget, battery?.charging === false),
    wanderScale: profile.wanderScale,
    assetPackIds: ambientAssetPackIds(overview, view),
    callbacks: {}, // interactions limitées : pan/zoom caméra uniquement
  });
  (window as { __acpEngine?: IOfficeRenderer }).__acpEngine = engine;

  engine.setScene(scene);
  if (params.get("screensaver") === "1") engine.setAutoCamera(true, 9000);

  const applyVisibility = () => engine.setRenderingPaused(document.hidden);
  const applyBattery = () => {
    engine.setFpsTarget(effectiveFps(profile.fpsTarget, battery?.charging === false));
  };
  document.addEventListener("visibilitychange", applyVisibility);
  battery?.addEventListener("chargingchange", applyBattery);
  applyVisibility();

  renderOverlay();
  const overlayTimer = window.setInterval(renderOverlay, 30_000);
  let disconnectEvents: (() => void) | undefined;

  if (dataSource === "api") {
    disconnectEvents = connectEvents(
      (event: AcpEvent) => {
        if (event.type === "agent.status_changed" && event.agent_instance_id) {
          const status = String((event.payload as { status?: string }).status ?? "idle");
          engine.updateEntityStatus(event.agent_instance_id, status);
          const agent = overview.agents.find((item) => item.id === event.agent_instance_id);
          if (agent) agent.status = status as typeof agent.status;
          renderOverlay();
        }
        if (event.type === "task.progress" && event.agent_instance_id) {
          engine.emote(event.agent_instance_id, "task-progress");
        }
        if (event.type === "task.completed" && event.agent_instance_id) {
          engine.emote(event.agent_instance_id, "task-complete", 4000);
        }
        if (event.project_id) engine.pulseRoom(event.project_id);
      },
      (connected) => {
        wsConnected = connected;
        renderOverlay();
      },
    );
  }

  window.addEventListener("pagehide", () => {
    window.clearInterval(overlayTimer);
    disconnectEvents?.();
    document.removeEventListener("visibilitychange", applyVisibility);
    battery?.removeEventListener("chargingchange", applyBattery);
    engine.destroy();
  }, { once: true });
}

boot().catch((error) => {
  overlay.textContent = `Ambient indisponible : ${error}`;
});
