/**
 * Couche d'adaptation : traduit les `SceneSpec` historiques en un modèle de
 * rendu résolu contre les packs d'assets (personnages, stations, thèmes).
 * Module pur (aucun import Phaser) : la traduction est testable en Node.
 */

import type { CharacterDef, StationAssetDef, ThemeDef } from "../../contracts/assets";
import type { EntitySpec, RoomSpec, SceneSpec, StationSpec } from "../../contracts/scene";
import {
  resolveCharacter,
  resolveStationAsset,
  resolveTheme,
  type LoadedAssets,
} from "../assets/manifest-loader";
import type { SeatPosition } from "../grid/reservations";

export interface RenderStation {
  key: string; // "<roomId>/<stationId>" — unique dans la scène
  spec: StationSpec;
  asset: StationAssetDef | null;
  /** origine en tuiles absolues */
  worldX: number;
  worldY: number;
  footprint: { w: number; h: number };
  /** sièges en tuiles absolues (limités par StationSpec.capacity) */
  seats: SeatPosition[];
}

export interface RenderRoom {
  spec: RoomSpec;
  theme: ThemeDef | null;
  stations: RenderStation[];
}

export interface RenderEntity {
  spec: EntitySpec;
  character: CharacterDef | null;
  /** station assignée par la scène, résolue en clé unique */
  stationKey: string | null;
}

export interface RenderModel {
  cols: number;
  rows: number;
  tile: number;
  rooms: RenderRoom[];
  entities: RenderEntity[];
  statusMapping: Record<string, string>;
  /** signature de la disposition : si elle change, décor reconstruit */
  layoutSignature: string;
}

function buildStation(room: RoomSpec, spec: StationSpec, assets: LoadedAssets): RenderStation {
  const asset = resolveStationAsset(assets, spec);
  const footprint = spec.footprint ?? asset?.footprint ?? { w: 1, h: 1 };
  const worldX = room.x + spec.x;
  const worldY = room.y + spec.y;
  const seatDefs = asset?.seats?.length
    ? asset.seats
    : [{ dx: 0, dy: footprint.h, facing: "up" as const }];
  const capacity = spec.capacity ?? seatDefs.length;
  const seats: SeatPosition[] = seatDefs.slice(0, Math.max(1, capacity)).map((s) => ({
    x: worldX + s.dx,
    y: worldY + s.dy,
    facing: spec.facing ?? s.facing,
  }));
  return {
    key: `${room.id}/${spec.id}`,
    spec,
    asset,
    worldX,
    worldY,
    footprint,
    seats,
  };
}

export function buildRenderModel(scene: SceneSpec, assets: LoadedAssets): RenderModel {
  const rooms: RenderRoom[] = scene.rooms.map((room) => ({
    spec: room,
    theme: resolveTheme(assets, room),
    stations: room.stations.map((s) => buildStation(room, s, assets)),
  }));

  const stationKeys = new Map<string, string>(); // "<roomId>:<stationId>" → key
  for (const room of rooms) {
    for (const station of room.stations) {
      stationKeys.set(`${room.spec.id}:${station.spec.id}`, station.key);
    }
  }

  const entities: RenderEntity[] = scene.entities.map((spec) => ({
    spec,
    character: resolveCharacter(assets, spec),
    stationKey: spec.stationId
      ? stationKeys.get(`${spec.roomId}:${spec.stationId}`) ?? null
      : null,
  }));

  const layoutSignature = JSON.stringify({
    cols: scene.cols,
    rows: scene.rows,
    rooms: scene.rooms.map((r) => [
      r.id, r.x, r.y, r.w, r.h, r.theme, r.themeId, r.tilemapId,
      r.stations.map((s) => [s.id, s.kind, s.x, s.y, s.assetId]),
    ]),
  });

  return {
    cols: scene.cols,
    rows: scene.rows,
    tile: scene.gridTile ?? 32,
    rooms,
    entities,
    statusMapping: scene.statusMapping ?? {},
    layoutSignature,
  };
}
