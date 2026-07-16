/**
 * Grille de collision et pathfinding A* 4-directions.
 * Module pur (aucun import Phaser), couvert par les tests.
 */

import type { RenderModel } from "../adapter/scene-adapter";

export interface Point {
  x: number;
  y: number;
}

export class CollisionGrid {
  readonly blocked: Uint8Array;

  constructor(readonly cols: number, readonly rows: number, fillBlocked = true) {
    this.blocked = new Uint8Array(cols * rows);
    if (fillBlocked) this.blocked.fill(1);
  }

  index(x: number, y: number): number {
    return y * this.cols + x;
  }

  inBounds(x: number, y: number): boolean {
    return x >= 0 && y >= 0 && x < this.cols && y < this.rows;
  }

  isWalkable(x: number, y: number): boolean {
    return this.inBounds(x, y) && this.blocked[this.index(x, y)] === 0;
  }

  setBlocked(x: number, y: number, value: boolean): void {
    if (this.inBounds(x, y)) this.blocked[this.index(x, y)] = value ? 1 : 0;
  }
}

/**
 * Construit la grille de collision d'une scène.
 *
 * Règles :
 * - l'extérieur (campus) est praticable : herbe et allées, sauf décorations ;
 * - un anneau d'une tuile autour de chaque salle est bloqué : on n'entre et
 *   ne sort que par les portes ;
 * - dans une salle : praticable sauf la rangée de mur haut et les footprints
 *   des stations `blocking` ; les sièges restent praticables ;
 * - chaque porte perce le mur (y=0) ou l'anneau (y=h, x=-1, x=w).
 */
export function buildCollisionGrid(
  model: Pick<RenderModel, "cols" | "rows" | "rooms"> &
    Partial<Pick<RenderModel, "decorations">>,
): CollisionGrid {
  const grid = new CollisionGrid(model.cols, model.rows, true);

  // 1. extérieur praticable partout...
  const inRoom = (x: number, y: number) =>
    model.rooms.some((r) =>
      x >= r.spec.x && x < r.spec.x + r.spec.w && y >= r.spec.y && y < r.spec.y + r.spec.h);
  for (let y = 0; y < model.rows; y++) {
    for (let x = 0; x < model.cols; x++) {
      if (!inRoom(x, y)) grid.setBlocked(x, y, false);
    }
  }
  // ...sauf les décorations (arbres, bancs...)
  for (const decoration of model.decorations ?? []) {
    grid.setBlocked(decoration.spec.x, decoration.spec.y, true);
  }

  // 2. anneau bloquant autour de chaque salle
  for (const room of model.rooms) {
    const { x, y, w, h } = room.spec;
    for (let i = x - 1; i <= x + w; i++) {
      grid.setBlocked(i, y - 1, true);
      grid.setBlocked(i, y + h, true);
    }
    for (let j = y - 1; j <= y + h; j++) {
      grid.setBlocked(x - 1, j, true);
      grid.setBlocked(x + w, j, true);
    }
  }

  // 3. intérieur praticable sauf mur haut
  for (const room of model.rooms) {
    const { x, y, w, h } = room.spec;
    for (let j = y + 1; j < y + h; j++) {
      for (let i = x; i < x + w; i++) grid.setBlocked(i, j, false);
    }
    for (let i = x; i < x + w; i++) grid.setBlocked(i, y, true); // mur haut
  }

  // 4. stations bloquantes, sièges praticables
  for (const room of model.rooms) {
    for (const station of room.stations) {
      if (station.asset && station.asset.blocking === false) continue;
      for (let j = 0; j < station.footprint.h; j++) {
        for (let i = 0; i < station.footprint.w; i++) {
          grid.setBlocked(station.worldX + i, station.worldY + j, true);
        }
      }
    }
    for (const station of room.stations) {
      for (const seat of station.seats) grid.setBlocked(seat.x, seat.y, false);
    }
  }

  // 5. portes : percées dans le mur ou l'anneau, plus la tuile extérieure
  for (const room of model.rooms) {
    const { x, y, h } = room.spec;
    for (const door of room.spec.doors ?? []) {
      const doorX = x + door.x;
      const doorY = y + door.y;
      grid.setBlocked(doorX, doorY, false);
      if (door.y === 0) grid.setBlocked(doorX, y - 1, false); // mur haut → dehors
      if (door.y === h) grid.setBlocked(doorX, y + h + 1, false); // entrée basse
    }
  }
  return grid;
}

interface Node {
  x: number;
  y: number;
  g: number;
  f: number;
  parent: Node | null;
}

const DIRS = [
  { x: 0, y: -1 },
  { x: 0, y: 1 },
  { x: -1, y: 0 },
  { x: 1, y: 0 },
];

/**
 * A* 4-directions. Retourne les waypoints de `from` (exclu) à `to` (inclus),
 * ou null si inaccessible. `bounds` optionnel restreint la recherche (salle).
 */
export function findPath(
  grid: CollisionGrid,
  from: Point,
  to: Point,
  bounds?: { x: number; y: number; w: number; h: number },
): Point[] | null {
  const within = (x: number, y: number): boolean =>
    !bounds || (x >= bounds.x && y >= bounds.y && x < bounds.x + bounds.w && y < bounds.y + bounds.h);
  if (!grid.isWalkable(to.x, to.y) || !within(to.x, to.y)) return null;
  if (from.x === to.x && from.y === to.y) return [];

  const heuristic = (x: number, y: number) => Math.abs(x - to.x) + Math.abs(y - to.y);
  const open: Node[] = [{ x: from.x, y: from.y, g: 0, f: heuristic(from.x, from.y), parent: null }];
  const visited = new Set<number>([grid.index(from.x, from.y)]);
  const maxIterations = grid.cols * grid.rows * 4;

  for (let iter = 0; open.length > 0 && iter < maxIterations; iter++) {
    let best = 0;
    for (let i = 1; i < open.length; i++) if (open[i].f < open[best].f) best = i;
    const current = open.splice(best, 1)[0];

    if (current.x === to.x && current.y === to.y) {
      const path: Point[] = [];
      let node: Node | null = current;
      while (node && node.parent) {
        path.unshift({ x: node.x, y: node.y });
        node = node.parent;
      }
      return path;
    }

    for (const dir of DIRS) {
      const nx = current.x + dir.x;
      const ny = current.y + dir.y;
      const key = grid.index(nx, ny);
      if (visited.has(key)) continue;
      if (!within(nx, ny)) continue;
      // la case d'arrivée est toujours acceptée (siège débloqué en amont)
      if (!grid.isWalkable(nx, ny) && !(nx === to.x && ny === to.y)) continue;
      visited.add(key);
      const g = current.g + 1;
      open.push({ x: nx, y: ny, g, f: g + heuristic(nx, ny), parent: current });
    }
  }
  return null;
}
