import { describe, expect, it } from "vitest";

import type { RenderRoom } from "../src/phaser/adapter/scene-adapter";
import { buildCollisionGrid, CollisionGrid, findPath } from "../src/phaser/grid/pathfinding";

function room(x: number, y: number, w: number, h: number, stations: Partial<RenderRoom["stations"][0]>[] = []): RenderRoom {
  return {
    spec: { id: "r1", name: "Salle", theme: "default", x, y, w, h, stations: [] },
    theme: null,
    stations: stations.map((s, i) => ({
      key: `r1/s${i}`,
      spec: { id: `s${i}`, name: "S", kind: "desk", x: 0, y: 0 },
      asset: null,
      worldX: s.worldX ?? 0,
      worldY: s.worldY ?? 0,
      footprint: s.footprint ?? { w: 1, h: 1 },
      seats: s.seats ?? [],
    })),
  };
}

describe("buildCollisionGrid", () => {
  it("bloque l'extérieur des salles et la rangée de mur", () => {
    const grid = buildCollisionGrid({ cols: 20, rows: 15, rooms: [room(2, 2, 10, 8)] });
    expect(grid.isWalkable(0, 0)).toBe(false);   // hors salle
    expect(grid.isWalkable(3, 2)).toBe(false);   // mur (rangée haute)
    expect(grid.isWalkable(3, 3)).toBe(true);    // intérieur
    expect(grid.isWalkable(11, 9)).toBe(true);   // intérieur bord
    expect(grid.isWalkable(12, 3)).toBe(false);  // juste après le bord droit
  });

  it("bloque les footprints des stations mais pas les sièges", () => {
    const grid = buildCollisionGrid({
      cols: 20, rows: 15,
      rooms: [room(2, 2, 10, 8, [{
        worldX: 4, worldY: 4, footprint: { w: 2, h: 1 },
        seats: [{ x: 5, y: 5, facing: "up" }],
      }])],
    });
    expect(grid.isWalkable(4, 4)).toBe(false); // meuble
    expect(grid.isWalkable(5, 4)).toBe(false); // meuble (2 tuiles)
    expect(grid.isWalkable(5, 5)).toBe(true);  // siège
  });
});

describe("findPath", () => {
  it("trouve un chemin direct", () => {
    const grid = new CollisionGrid(10, 10, false);
    const path = findPath(grid, { x: 1, y: 1 }, { x: 4, y: 1 });
    expect(path).toEqual([{ x: 2, y: 1 }, { x: 3, y: 1 }, { x: 4, y: 1 }]);
  });

  it("contourne un obstacle", () => {
    const grid = new CollisionGrid(10, 10, false);
    for (let y = 0; y < 9; y++) grid.setBlocked(5, y, true); // mur vertical avec passage en bas
    const path = findPath(grid, { x: 2, y: 2 }, { x: 8, y: 2 });
    expect(path).not.toBeNull();
    expect(path!.some((p) => p.y === 9)).toBe(true); // passe par le bas
    expect(path![path!.length - 1]).toEqual({ x: 8, y: 2 });
    // aucune case du chemin n'est bloquée
    for (const p of path!) expect(grid.isWalkable(p.x, p.y)).toBe(true);
  });

  it("retourne null si la cible est inaccessible", () => {
    const grid = new CollisionGrid(10, 10, false);
    for (let y = 0; y < 10; y++) grid.setBlocked(5, y, true); // mur complet
    expect(findPath(grid, { x: 2, y: 2 }, { x: 8, y: 2 })).toBeNull();
  });

  it("respecte les bornes de la salle", () => {
    const grid = new CollisionGrid(20, 20, false);
    const bounds = { x: 0, y: 0, w: 10, h: 10 };
    const path = findPath(grid, { x: 1, y: 1 }, { x: 15, y: 1 }, bounds);
    expect(path).toBeNull(); // cible hors bornes
  });

  it("chemin vide si départ = arrivée", () => {
    const grid = new CollisionGrid(10, 10, false);
    expect(findPath(grid, { x: 3, y: 3 }, { x: 3, y: 3 })).toEqual([]);
  });
});
