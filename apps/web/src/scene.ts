/**
 * Construction des scènes pixel art à partir des données métier.
 * Le moteur reste agnostique : tout vient de l'overview API et des
 * office-configs fournies par les modules.
 */

import type { AgentInstance, OfficeConfig, Overview, Project } from "@acp/contracts";
import type { EntitySpec, RoomSpec, SceneSpec, StationSpec } from "@acp/pixel-office-engine";

const ROOM_W = 12;
const ROOM_H = 9;
const GAP = 1;

export type OfficeConfigMap = Record<string, OfficeConfig>; // par department_id

function layoutGrid(count: number): { x: number; y: number }[] {
  const cols = Math.max(1, Math.ceil(Math.sqrt(count)));
  return Array.from({ length: count }, (_, i) => ({
    x: GAP + (i % cols) * (ROOM_W + GAP),
    y: GAP + Math.floor(i / cols) * (ROOM_H + GAP),
  }));
}

function sceneSize(count: number): { cols: number; rows: number } {
  const cols = Math.max(1, Math.ceil(Math.sqrt(count)));
  const rows = Math.max(1, Math.ceil(count / cols));
  return {
    cols: GAP + cols * (ROOM_W + GAP),
    rows: GAP + rows * (ROOM_H + GAP),
  };
}

function stationsFor(config: OfficeConfig | undefined): StationSpec[] {
  return (config?.stations ?? []).map((s) => ({ ...s }));
}

function mergedStatusMapping(configs: (OfficeConfig | undefined)[]): Record<string, string> {
  const mapping: Record<string, string> = {
    idle: "coffee", thinking: "think", working: "type",
    reviewing: "think", blocked: "sit", offline: "away",
  };
  for (const config of configs) Object.assign(mapping, config?.status_mapping ?? {});
  return mapping;
}

function agentsOfProject(overview: Overview, projectId: string): AgentInstance[] {
  const teamIds = new Set(
    overview.teams.filter((t) => t.project_id === projectId).map((t) => t.id),
  );
  return overview.agents.filter((a) => a.team_id && teamIds.has(a.team_id));
}

function activeTaskCount(overview: Overview, projectId: string): number {
  return overview.tasks.filter(
    (t) => t.project_id === projectId && !["done", "failed", "backlog"].includes(t.status),
  ).length;
}

function makeEntities(
  agents: AgentInstance[],
  roomId: string,
  stations: StationSpec[],
): EntitySpec[] {
  const desks = stations.filter((s) => s.kind === "desk");
  return agents.map((agent, index) => ({
    id: agent.id,
    name: agent.name,
    role: agent.role_id,
    status: agent.status,
    roomId,
    stationId: desks.length ? desks[index % desks.length].id : undefined,
  }));
}

function projectRoom(
  overview: Overview,
  project: Project,
  pos: { x: number; y: number },
  configs: OfficeConfigMap,
): { room: RoomSpec; entities: EntitySpec[] } {
  const config = project.department_id ? configs[project.department_id] : undefined;
  const stations = stationsFor(config);
  const active = activeTaskCount(overview, project.id);
  const room: RoomSpec = {
    id: project.id,
    name: project.name,
    theme: config?.office_theme ?? "default",
    x: pos.x,
    y: pos.y,
    w: ROOM_W,
    h: ROOM_H,
    badge: active ? `${active} tâche(s) active(s)` : undefined,
    stations,
  };
  return { room, entities: makeEntities(agentsOfProject(overview, project.id), room.id, stations) };
}

/** Company view : un bureau par département, tous workspaces confondus. */
export function companyScene(overview: Overview, configs: OfficeConfigMap): SceneSpec {
  const departments = overview.departments;
  const positions = layoutGrid(departments.length);
  const rooms: RoomSpec[] = [];
  const entities: EntitySpec[] = [];
  departments.forEach((dept, i) => {
    const config = configs[dept.id];
    const stations = stationsFor(config);
    const projects = overview.projects.filter((p) => p.department_id === dept.id);
    const active = projects.reduce((sum, p) => sum + activeTaskCount(overview, p.id), 0);
    const room: RoomSpec = {
      id: dept.id,
      name: dept.name,
      theme: config?.office_theme ?? dept.office_theme ?? "default",
      x: positions[i].x,
      y: positions[i].y,
      w: ROOM_W,
      h: ROOM_H,
      badge: `${projects.length} projet(s) · ${active} actif(s)`,
      stations,
    };
    rooms.push(room);
    const agents = projects.flatMap((p) => agentsOfProject(overview, p.id));
    entities.push(...makeEntities(agents, room.id, stations));
  });
  return {
    ...sceneSize(departments.length),
    rooms,
    entities,
    statusMapping: mergedStatusMapping(Object.values(configs)),
  };
}

/** Workspace view : un bureau par projet du workspace. */
export function workspaceScene(
  overview: Overview,
  workspaceId: string,
  configs: OfficeConfigMap,
): SceneSpec {
  const projects = overview.projects.filter((p) => p.workspace_id === workspaceId);
  const positions = layoutGrid(projects.length);
  const rooms: RoomSpec[] = [];
  const entities: EntitySpec[] = [];
  projects.forEach((project, i) => {
    const built = projectRoom(overview, project, positions[i], configs);
    rooms.push(built.room);
    entities.push(...built.entities);
  });
  return {
    ...sceneSize(projects.length),
    rooms,
    entities,
    statusMapping: mergedStatusMapping(Object.values(configs)),
  };
}

/** Project office view : uniquement l'équipe du projet sélectionné. */
export function projectScene(
  overview: Overview,
  projectId: string,
  configs: OfficeConfigMap,
): SceneSpec {
  const project = overview.projects.find((p) => p.id === projectId);
  if (!project) return { cols: 10, rows: 8, rooms: [], entities: [] };
  const built = projectRoom(overview, project, { x: GAP, y: GAP }, configs);
  const config = project.department_id ? configs[project.department_id] : undefined;
  return {
    cols: ROOM_W + 2 * GAP,
    rows: ROOM_H + 2 * GAP,
    rooms: [built.room],
    entities: built.entities,
    statusMapping: mergedStatusMapping([config]),
  };
}

/** Department view : tous les projets et agents d'un secteur. */
export function departmentScene(
  overview: Overview,
  departmentId: string,
  configs: OfficeConfigMap,
): SceneSpec {
  const projects = overview.projects.filter((p) => p.department_id === departmentId);
  const positions = layoutGrid(projects.length);
  const rooms: RoomSpec[] = [];
  const entities: EntitySpec[] = [];
  projects.forEach((project, i) => {
    const built = projectRoom(overview, project, positions[i], configs);
    rooms.push(built.room);
    entities.push(...built.entities);
  });
  return {
    ...sceneSize(Math.max(1, projects.length)),
    rooms,
    entities,
    statusMapping: mergedStatusMapping([configs[departmentId]]),
  };
}
