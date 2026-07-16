/**
 * Construction des scènes pixel art à partir des données métier.
 * Le moteur reste agnostique : tout vient de l'overview API et des
 * office-configs fournies par les modules. Les vues sont posées sur un
 * campus extérieur (herbe + allées + décor) avec des espaces communs.
 */

import type { AgentInstance, OfficeConfig, Overview, Project } from "@acp/contracts";
import type {
  DecorationSpec,
  EntitySpec,
  RoomSpec,
  SceneSpec,
  StationSpec,
} from "@acp/pixel-office-engine";

const ROOM_W = 12;
const ROOM_H = 9;
const GAP = 3; // large : 1 tuile d'allée + verdure de part et d'autre
const GROUND_THEME = "campus";

export type OfficeConfigMap = Record<string, OfficeConfig>; // par department_id

/** Espaces communs du campus (configuration de présentation de l'app). */
const AMENITIES: { id: string; name: string; subtitle: string; stations: StationSpec[] }[] = [
  {
    id: "amenity-lounge", name: "Lounge", subtitle: "ESPACE DÉTENTE",
    stations: [
      { id: "couch-1", name: "Couch", kind: "couch", x: 2, y: 3 },
      { id: "couch-2", name: "Couch", kind: "couch", x: 7, y: 3 },
      { id: "bench-1", name: "Bench", kind: "bench", x: 4, y: 6 },
      { id: "plant-1", name: "Plant", kind: "plant", x: 1, y: 1 },
      { id: "plant-2", name: "Plant", kind: "plant", x: 10, y: 1 },
    ],
  },
  {
    id: "amenity-reception", name: "Réception", subtitle: "ACCUEIL",
    stations: [
      { id: "reception-1", name: "Accueil", kind: "reception-desk", x: 5, y: 3 },
      { id: "plant-1", name: "Plant", kind: "plant", x: 2, y: 2 },
      { id: "plant-2", name: "Plant", kind: "plant", x: 9, y: 2 },
      { id: "bench-1", name: "Bench", kind: "bench", x: 2, y: 6 },
      { id: "bench-2", name: "Bench", kind: "bench", x: 8, y: 6 },
    ],
  },
  {
    id: "amenity-meeting", name: "Meeting Rooms", subtitle: "3 SALLES DISPONIBLES",
    stations: [
      { id: "table-1", name: "Table", kind: "meeting-table", x: 2, y: 3 },
      { id: "table-2", name: "Table", kind: "meeting-table", x: 8, y: 3 },
      { id: "board-1", name: "Board", kind: "whiteboard", x: 5, y: 1 },
    ],
  },
];

// ------------------------------------------------------------------- layout

interface CampusLayout {
  cols: number;
  rows: number;
  positions: { x: number; y: number }[];
  paths: { x: number; y: number; w: number; h: number }[];
}

function campusLayout(count: number): CampusLayout {
  const gridCols = Math.max(1, Math.ceil(Math.sqrt(count)));
  const gridRows = Math.max(1, Math.ceil(count / gridCols));
  const cols = GAP + gridCols * (ROOM_W + GAP);
  const rows = GAP + gridRows * (ROOM_H + GAP);
  const positions = Array.from({ length: count }, (_, i) => ({
    x: GAP + (i % gridCols) * (ROOM_W + GAP),
    y: GAP + Math.floor(i / gridCols) * (ROOM_H + GAP),
  }));

  const paths: CampusLayout["paths"] = [];
  // allées verticales au milieu de chaque couloir (bords inclus)
  for (let c = 0; c <= gridCols; c++) {
    paths.push({ x: c * (ROOM_W + GAP) + 1, y: 0, w: 1, h: rows });
  }
  for (let r = 0; r <= gridRows; r++) {
    paths.push({ x: 0, y: r * (ROOM_H + GAP) + 1, w: cols, h: 1 });
  }
  return { cols, rows, positions, paths };
}

function decorate(layout: CampusLayout, rooms: RoomSpec[]): DecorationSpec[] {
  const inRoom = (x: number, y: number) =>
    rooms.some((r) => x >= r.x - 1 && x <= r.x + r.w && y >= r.y - 1 && y <= r.y + r.h);
  const onPath = (x: number, y: number) =>
    layout.paths.some((p) => x >= p.x && x < p.x + p.w && y >= p.y && y < p.y + p.h);
  const decorations: DecorationSpec[] = [];
  for (let y = 1; y < layout.rows - 1; y++) {
    for (let x = 1; x < layout.cols - 1; x++) {
      if (inRoom(x, y) || onPath(x, y)) continue;
      const roll = (x * 31 + y * 17) % 23;
      if (roll === 0) decorations.push({ assetId: "tree-core", x, y });
      else if (roll === 7) decorations.push({ assetId: "plant-core", x, y });
      else if (roll === 14 && !onPath(x, y - 1)) decorations.push({ assetId: "bench-core", x, y });
    }
  }
  return decorations;
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

function onlineSubtitle(agents: AgentInstance[]): string {
  const online = agents.filter((a) => a.status !== "offline").length;
  return `${online} EN LIGNE`;
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

function amenityRooms(positions: { x: number; y: number }[], startIndex: number): RoomSpec[] {
  return AMENITIES.map((amenity, i) => ({
    id: amenity.id,
    name: amenity.name,
    theme: "default",
    x: positions[startIndex + i]?.x ?? GAP,
    y: positions[startIndex + i]?.y ?? GAP,
    w: ROOM_W,
    h: ROOM_H,
    subtitle: amenity.subtitle,
    stations: amenity.stations.map((s) => ({ ...s })),
  }));
}

function assemble(
  layout: CampusLayout,
  rooms: RoomSpec[],
  entities: EntitySpec[],
  configs: (OfficeConfig | undefined)[],
): SceneSpec {
  return {
    cols: layout.cols,
    rows: layout.rows,
    rooms,
    entities,
    groundThemeId: GROUND_THEME,
    paths: layout.paths,
    decorations: decorate(layout, rooms),
    statusMapping: mergedStatusMapping(configs),
  };
}

function projectRoom(
  overview: Overview,
  project: Project,
  pos: { x: number; y: number },
  configs: OfficeConfigMap,
): { room: RoomSpec; entities: EntitySpec[] } {
  const config = project.department_id ? configs[project.department_id] : undefined;
  const stations = stationsFor(config);
  const agents = agentsOfProject(overview, project.id);
  const active = activeTaskCount(overview, project.id);
  const room: RoomSpec = {
    id: project.id,
    name: project.name,
    theme: config?.office_theme ?? "default",
    x: pos.x,
    y: pos.y,
    w: ROOM_W,
    h: ROOM_H,
    subtitle: onlineSubtitle(agents),
    badge: active ? `${active} tâche(s) active(s)` : undefined,
    stations,
  };
  return { room, entities: makeEntities(agents, room.id, stations) };
}

/** Company view : un bâtiment par département + espaces communs du campus. */
export function companyScene(overview: Overview, configs: OfficeConfigMap): SceneSpec {
  const departments = overview.departments;
  const layout = campusLayout(departments.length + AMENITIES.length);
  const rooms: RoomSpec[] = [];
  const entities: EntitySpec[] = [];
  departments.forEach((dept, i) => {
    const config = configs[dept.id];
    const stations = stationsFor(config);
    const projects = overview.projects.filter((p) => p.department_id === dept.id);
    const agents = projects.flatMap((p) => agentsOfProject(overview, p.id));
    const active = projects.reduce((sum, p) => sum + activeTaskCount(overview, p.id), 0);
    const room: RoomSpec = {
      id: dept.id,
      name: dept.name,
      theme: config?.office_theme ?? dept.office_theme ?? "default",
      x: layout.positions[i].x,
      y: layout.positions[i].y,
      w: ROOM_W,
      h: ROOM_H,
      subtitle: onlineSubtitle(agents),
      badge: `${projects.length} projet(s) · ${active} actif(s)`,
      stations,
    };
    rooms.push(room);
    entities.push(...makeEntities(agents, room.id, stations));
  });
  rooms.push(...amenityRooms(layout.positions, departments.length));
  return assemble(layout, rooms, entities, Object.values(configs));
}

/** Workspace view : un bâtiment par projet du workspace. */
export function workspaceScene(
  overview: Overview,
  workspaceId: string,
  configs: OfficeConfigMap,
): SceneSpec {
  const projects = overview.projects.filter((p) => p.workspace_id === workspaceId);
  const layout = campusLayout(projects.length);
  const rooms: RoomSpec[] = [];
  const entities: EntitySpec[] = [];
  projects.forEach((project, i) => {
    const built = projectRoom(overview, project, layout.positions[i], configs);
    rooms.push(built.room);
    entities.push(...built.entities);
  });
  return assemble(layout, rooms, entities, Object.values(configs));
}

/** Project office view : uniquement l'équipe du projet sélectionné. */
export function projectScene(
  overview: Overview,
  projectId: string,
  configs: OfficeConfigMap,
): SceneSpec {
  const project = overview.projects.find((p) => p.id === projectId);
  if (!project) return { cols: 10, rows: 8, rooms: [], entities: [] };
  const layout = campusLayout(1);
  const built = projectRoom(overview, project, layout.positions[0], configs);
  const config = project.department_id ? configs[project.department_id] : undefined;
  return assemble(layout, [built.room], built.entities, [config]);
}

/** Department view : tous les projets et agents d'un secteur. */
export function departmentScene(
  overview: Overview,
  departmentId: string,
  configs: OfficeConfigMap,
): SceneSpec {
  const projects = overview.projects.filter((p) => p.department_id === departmentId);
  const layout = campusLayout(Math.max(1, projects.length));
  const rooms: RoomSpec[] = [];
  const entities: EntitySpec[] = [];
  projects.forEach((project, i) => {
    const built = projectRoom(overview, project, layout.positions[i], configs);
    rooms.push(built.room);
    entities.push(...built.entities);
  });
  return assemble(layout, rooms, entities, [configs[departmentId]]);
}
