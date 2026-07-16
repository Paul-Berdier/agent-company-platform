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
 * Construit la grille de collision d'une scène :
 * tout est bloqué sauf l'intérieur des salles ; la rangée haute de chaque
 * salle (mur visuel) et les footprints des stations `blocking` sont bloqués,
 * les sièges restent praticables.
 */
export function buildCollisionGrid(model: Pick<RenderModel, "cols" | "rows" | "rooms">): CollisionGrid {
  const grid = new CollisionGrid(model.cols, model.rows, true);
  for (const room of model.rooms) {
    const { x, y, w, h } = room.spec;
    for (let j = y + 1; j < y + h; j++) {
      for (let i = x; i < x + w; i++) grid.setBlocked(i, j, false);
    }
  }
  for (const room of model.rooms) {
    for (const station of room.stations) {
      if (station.asset && station.asset.blocking === false) continue;
      const fw = station.footprint.w;
      const fh = station.footprint.h;
      for (let j = 0; j < fh; j++) {
        for (let i = 0; i < fw; i++) {
          grid.setBlocked(station.worldX + i, station.worldY + j, true);
        }
      }
    }
    for (const station of room.stations) {
      for (const seat of station.seats) grid.setBlocked(seat.x, seat.y, false);
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
