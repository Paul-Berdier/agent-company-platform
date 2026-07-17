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

/** Grille de campus à slots de taille variable (max des salles présentes). */
function campusLayout(count: number, slotW = ROOM_W, slotH = ROOM_H): CampusLayout {
  const gridCols = Math.max(1, Math.ceil(Math.sqrt(count)));
  const gridRows = Math.max(1, Math.ceil(count / gridCols));
  const cols = GAP + gridCols * (slotW + GAP);
  const rows = GAP + gridRows * (slotH + GAP);
  const positions = Array.from({ length: count }, (_, i) => ({
    x: GAP + (i % gridCols) * (slotW + GAP),
    y: GAP + Math.floor(i / gridCols) * (slotH + GAP),
  }));

  const paths: CampusLayout["paths"] = [];
  // allées verticales au milieu de chaque couloir (bords inclus)
  for (let c = 0; c <= gridCols; c++) {
    paths.push({ x: c * (slotW + GAP) + 1, y: 0, w: 1, h: rows });
  }
  for (let r = 0; r <= gridRows; r++) {
    paths.push({ x: 0, y: r * (slotH + GAP) + 1, w: cols, h: 1 });
  }
  return { cols, rows, positions, paths };
}

function roomDims(config: OfficeConfig | undefined): { w: number; h: number } {
  return { w: config?.width ?? ROOM_W, h: config?.height ?? ROOM_H };
}

function maxDims(configs: (OfficeConfig | undefined)[]): { w: number; h: number } {
  let w = ROOM_W, h = ROOM_H;
  for (const config of configs) {
    const dims = roomDims(config);
    w = Math.max(w, dims.w);
    h = Math.max(h, dims.h);
  }
  return { w, h };
}

function roomOpenings(
  config: OfficeConfig | undefined,
  dims: { w: number; h: number },
): Pick<RoomSpec, "doors" | "windows"> {
  return {
    doors: config?.doors?.length ? config.doors : [{ x: Math.floor(dims.w / 2), y: dims.h }],
    windows: config?.windows ?? [2, 5, 9].filter((x) => x < dims.w - 1),
  };
}

function decorate(
  layout: CampusLayout,
  rooms: RoomSpec[],
  growth?: GrowthInfo,
): DecorationSpec[] {
  const inRoom = (x: number, y: number) =>
    rooms.some((r) => x >= r.x - 1 && x <= r.x + r.w && y >= r.y - 1 && y <= r.y + r.h);
  const onPath = (x: number, y: number) =>
    layout.paths.some((p) => x >= p.x && x < p.x + p.w && y >= p.y && y < p.y + p.h);
  const decorations: DecorationSpec[] = [];
  // plus l'entreprise grandit, plus le campus est planté
  const density = growth && growth.level >= 5 ? 11 : growth && growth.level >= 4 ? 15 : 23;
  for (let y = 1; y < layout.rows - 1; y++) {
    for (let x = 1; x < layout.cols - 1; x++) {
      if (inRoom(x, y) || onPath(x, y)) continue;
      const roll = (x * 31 + y * 17) % density;
      if (roll === 0) decorations.push({ assetId: "tree-core", x, y });
      else if (roll === 7) decorations.push({ assetId: "plant-core", x, y });
      else if (roll === 14 && !onPath(x, y - 1)) decorations.push({ assetId: "bench-core", x, y });
    }
  }
  // place centrale : fontaine et lampadaires débloqués au niveau 4
  if (growth?.unlocked.includes("decor-plaza")) {
    const cx = Math.floor(layout.cols / 2);
    const cy = Math.floor(layout.rows / 2);
    const spots: DecorationSpec[] = [
      { assetId: "fountain-core", x: cx - 1, y: cy - 1 },
      { assetId: "street-lamp", x: cx - 3, y: cy },
      { assetId: "street-lamp", x: cx + 2, y: cy },
    ];
    for (const spot of spots) {
      if (!inRoom(spot.x, spot.y)) decorations.push(spot);
    }
  }
  return decorations;
}

export interface GrowthInfo {
  level: number;
  name: string;
  unlocked: string[];
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
  // dans les vues multi-départements, un agent inactif flâne (animation non
  // ancrante) au lieu d'hériter du mapping "idle" d'un autre secteur
  if (configs.filter(Boolean).length > 1) mapping.idle = "coffee";
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

/** Porte d'entrée en bas au centre + fenêtres régulières sur le mur haut. */
function buildingOpenings(): Pick<RoomSpec, "doors" | "windows"> {
  return {
    doors: [{ x: Math.floor(ROOM_W / 2), y: ROOM_H }],
    windows: [2, 5, 9],
  };
}

function amenityRooms(
  positions: { x: number; y: number }[],
  startIndex: number,
  amenities: typeof AMENITIES = AMENITIES,
): RoomSpec[] {
  return amenities.map((amenity, i) => ({
    id: amenity.id,
    name: amenity.name,
    theme: "default",
    x: positions[startIndex + i]?.x ?? GAP,
    y: positions[startIndex + i]?.y ?? GAP,
    w: ROOM_W,
    h: ROOM_H,
    subtitle: amenity.subtitle,
    stations: amenity.stations.map((s) => ({ ...s })),
    ...buildingOpenings(),
  }));
}

function assemble(
  layout: CampusLayout,
  rooms: RoomSpec[],
  entities: EntitySpec[],
  configs: (OfficeConfig | undefined)[],
  growth?: GrowthInfo,
): SceneSpec {
  return {
    cols: layout.cols,
    rows: layout.rows,
    rooms,
    entities,
    groundThemeId: GROUND_THEME,
    paths: layout.paths,
    decorations: decorate(layout, rooms, growth),
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
  const dims = roomDims(config);
  const room: RoomSpec = {
    id: project.id,
    name: project.name,
    theme: config?.office_theme ?? "default",
    x: pos.x,
    y: pos.y,
    w: dims.w,
    h: dims.h,
    subtitle: onlineSubtitle(agents),
    badge: active ? `${active} tâche(s) active(s)` : undefined,
    stations,
    ...roomOpenings(config, dims),
  };
  return { room, entities: makeEntities(agents, room.id, stations) };
}

/**
 * Company view : campus extérieur — un bâtiment (façade) par département,
 * espaces communs débloqués par la croissance. Les agents au travail sont
 * dans les bâtiments ; les autres flânent sur le campus.
 */
export function companyScene(
  overview: Overview,
  configs: OfficeConfigMap,
  growth?: GrowthInfo,
): SceneSpec {
  const departments = overview.departments;
  const amenities = AMENITIES.filter(
    (a) => !growth || growth.unlocked.includes(a.id),
  );
  const slot = maxDims(Object.values(configs));
  // rangées plus espacées : les façades s'élèvent au-dessus de leur parcelle
  const layout = campusLayout(departments.length + amenities.length, slot.w, slot.h + 5);
  const rooms: RoomSpec[] = [];
  const entities: EntitySpec[] = [];
  departments.forEach((dept, i) => {
    const config = configs[dept.id];
    const projects = overview.projects.filter((p) => p.department_id === dept.id);
    const agents = projects.flatMap((p) => agentsOfProject(overview, p.id));
    const working = agents.filter((a) =>
      ["working", "thinking", "reviewing"].includes(a.status));
    const idlers = agents.filter((a) => !working.includes(a));
    const dims = roomDims(config);
    const pos = layout.positions[i];
    const room: RoomSpec = {
      id: dept.id,
      name: dept.name,
      theme: config?.office_theme ?? dept.office_theme ?? "default",
      x: pos.x,
      y: pos.y + 5, // la parcelle est en bas du slot, la façade monte au-dessus
      w: dims.w,
      h: dims.h,
      facade: true,
      subtitle: onlineSubtitle(agents),
      badge: `${working.length} au travail · ${projects.length} projet(s)`,
      stations: [],
      doors: [{ x: Math.floor(dims.w / 2), y: dims.h }],
    };
    rooms.push(room);
    entities.push(...makeEntities(idlers, room.id, []));
  });
  rooms.push(...amenityRooms(
    layout.positions.map((p) => ({ x: p.x, y: p.y + 5 })),
    departments.length,
    amenities,
  ));
  return assemble(layout, rooms, entities, Object.values(configs), growth);
}

/** Workspace view : un bâtiment par projet du workspace. */
export function workspaceScene(
  overview: Overview,
  workspaceId: string,
  configs: OfficeConfigMap,
): SceneSpec {
  const projects = overview.projects.filter((p) => p.workspace_id === workspaceId);
  const slot = maxDims(projects.map((p) => (p.department_id ? configs[p.department_id] : undefined)));
  const layout = campusLayout(projects.length, slot.w, slot.h);
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
  const slot = roomDims(project.department_id ? configs[project.department_id] : undefined);
  const layout = campusLayout(1, slot.w, slot.h);
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
  const slot = roomDims(configs[departmentId]);
  const layout = campusLayout(Math.max(1, projects.length), slot.w, slot.h);
  const rooms: RoomSpec[] = [];
  const entities: EntitySpec[] = [];
  projects.forEach((project, i) => {
    const built = projectRoom(overview, project, layout.positions[i], configs);
    rooms.push(built.room);
    entities.push(...built.entities);
  });
  return assemble(layout, rooms, entities, [configs[departmentId]]);
}
