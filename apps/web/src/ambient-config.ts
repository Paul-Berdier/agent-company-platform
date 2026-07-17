import type { Overview } from "@acp/contracts";

export const AMBIENT_PROFILES = {
  performance: { fpsTarget: 18, wanderScale: 2.5 },
  balanced: { fpsTarget: 30, wanderScale: 1.5 },
  cinematic: { fpsTarget: 60, wanderScale: 1 },
} as const;

export type AmbientProfileName = keyof typeof AMBIENT_PROFILES;
export type AmbientView = "pilot" | "company" | `project:${string}`;

const DEPARTMENT_PACKS: Record<string, string> = {
  "software-engineering": "dept-software-engineering",
  "data-science": "dept-data-science",
  research: "dept-research",
  "game-development": "dept-game-development",
};

function explicitView(value: string | null): AmbientView | null {
  if (value === "pilot" || value === "company") return value;
  if (value?.startsWith("project:") && value.length > "project:".length) {
    return value as `project:${string}`;
  }
  return null;
}

/** Résout les routes publiques et l'ancien paramètre `?view=` compatible. */
export function resolveAmbientView(pathname: string, viewParam: string | null): AmbientView | null {
  const projectMatch = pathname.match(/^\/projects\/([^/]+)\/ambient\/?$/);
  if (projectMatch) {
    try {
      return `project:${decodeURIComponent(projectMatch[1])}`;
    } catch {
      return `project:${projectMatch[1]}`;
    }
  }
  if (/^\/ambient(?:\.html)?\/?$/.test(pathname)) {
    return explicitView(viewParam) ?? "pilot";
  }
  return null;
}

export function ambientProfile(name: string | null) {
  return AMBIENT_PROFILES[name as AmbientProfileName] ?? AMBIENT_PROFILES.balanced;
}

export function effectiveFps(target: number, onBattery: boolean): number {
  return onBattery ? Math.min(target, AMBIENT_PROFILES.performance.fpsTarget) : target;
}

/** Choisit une équipe de 4 à 8 agents, sinon le projet le plus peuplé. */
export function selectPilotProjectId(overview: Overview): string | null {
  const ranked = overview.projects.map((project) => {
    const teamIds = new Set(
      overview.teams.filter((team) => team.project_id === project.id).map((team) => team.id),
    );
    const agentCount = overview.agents.filter(
      (agent) => Boolean(agent.team_id) && teamIds.has(agent.team_id!),
    ).length;
    return { id: project.id, agentCount };
  }).sort((a, b) => b.agentCount - a.agentCount);
  return ranked.find((item) => item.agentCount >= 4 && item.agentCount <= 8)?.id
    ?? ranked[0]?.id
    ?? null;
}

/** Packs strictement utiles au rendu ambient courant (le core reste implicite). */
export function ambientAssetPackIds(overview: Overview, view: AmbientView): string[] {
  const departmentTypes = new Set<string>();
  if (view === "company" || view === "pilot") {
    for (const department of overview.departments) departmentTypes.add(department.department_type);
  } else {
    const projectId = view.slice("project:".length);
    const project = overview.projects.find((item) => item.id === projectId);
    const department = overview.departments.find((item) => item.id === project?.department_id);
    if (department) departmentTypes.add(department.department_type);
  }

  const packs = [...departmentTypes]
    .map((type) => DEPARTMENT_PACKS[type])
    .filter((pack): pack is string => Boolean(pack));
  packs.push("limezu-characters", "limezu-exterior");
  if (view !== "company") packs.push("limezu-office");
  return [...new Set(packs)];
}
