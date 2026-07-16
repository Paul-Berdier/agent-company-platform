/**
 * Contrats des manifests d'assets (version 1.0).
 *
 * Tout le visuel du renderer Phaser provient de ces manifests : le moteur ne
 * contient ni palette, ni meuble, ni personnage, ni département codé en dur.
 */

import type { Facing } from "./scene";

export const ASSET_MANIFEST_VERSION = "1.0";

export interface AtlasDef {
  id: string;
  image: string; // chemin relatif au manifest
  data: string; // JSON hash TexturePacker-compatible
}

export interface TilesetDef {
  id: string;
  image: string;
  tile: number;
  margin?: number;
  spacing?: number;
  /** nombre de colonnes de tuiles dans l'image */
  columns: number;
}

export interface TilemapDef {
  id: string;
  file: string; // .tmj (Tiled JSON)
  format: "tiled-json";
}

export interface AnimationClipDef {
  /** motif de frames, ex. "worker-a/walk-down/{0..5}" */
  frames: string;
  frameRate: number;
  /** -1 = boucle infinie, 0 = une fois */
  repeat: number;
}

export interface CharacterDef {
  id: string;
  atlas: string;
  size: { w: number; h: number }; // 32×48 par convention
  pivot: { x: number; y: number }; // (0.5, 0.9) = pieds
  animations: Record<string, AnimationClipDef>;
}

export interface SeatDef {
  dx: number; // offset tuiles depuis l'origine de la station
  dy: number;
  facing: Facing;
}

export interface StationAssetDef {
  /** résolution des stations des scènes actuelles par kind */
  kind: string;
  /** id explicite (prioritaire si StationSpec.assetId est fourni) */
  id: string;
  atlas: string;
  frames: { back: string; front?: string };
  footprint: { w: number; h: number };
  pivot: { x: number; y: number };
  seats: SeatDef[];
  /** participe à la grille de collision (défaut true) */
  blocking?: boolean;
}

export interface ThemeDef {
  id: string;
  tileset: string;
  /** index de tuiles de sol (alternées en damier) */
  floorTiles: number[];
  /** index de tuiles de mur (rangée haute des salles) */
  wallTiles: number[];
  /** index de tuiles d'allées extérieures (thèmes de campus) */
  pathTiles?: number[];
  accentColor: string;
}

export interface EffectDef {
  id: string;
  atlas: string;
  animation: AnimationClipDef;
}

export interface AssetManifest {
  manifest_version: string;
  pack_id: string;
  /** pack parent dont les définitions sont héritées (fusion, le fils gagne) */
  extends?: string;
  grid: { tile: number; character: { w: number; h: number } };
  atlases: AtlasDef[];
  tilesets: TilesetDef[];
  tilemaps: TilemapDef[];
  characters: CharacterDef[];
  stations: StationAssetDef[];
  themes: ThemeDef[];
  effects: EffectDef[];
  /** rôle métier → ids de personnages candidats ; "*" = défaut */
  role_characters: Record<string, string[]>;
  /** nom d'animation métier → clip réellement disponible */
  animation_aliases: Record<string, string>;
}

/** Index des packs disponibles (apps/web/public/assets/packs.json). */
export interface PacksIndex {
  packs: Record<string, string>; // pack_id → dossier relatif
  /** department_type → pack_id ; "*" = pack par défaut */
  department_packs: Record<string, string>;
}
