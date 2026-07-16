/**
 * Pixel Office Engine — point d'entrée public.
 *
 * Deux renderers derrière la même interface `IOfficeRenderer` :
 *  - `canvas` : renderer legacy (fallback temporaire) ;
 *  - `phaser` : renderer Phaser 3 piloté par manifests d'assets.
 */

export type {
  EntitySpec,
  Facing,
  RoomSpec,
  SceneSpec,
  StationSpec,
} from "./contracts/scene";
export type {
  EngineCallbacks,
  IOfficeRenderer,
  RendererMode,
  RendererOptions,
} from "./contracts/renderer";
export * from "./contracts/assets";

export { CanvasRenderer } from "./legacy/canvas-renderer";
export { createOfficeRenderer } from "./fallback";

/** @deprecated utiliser createOfficeRenderer ; alias de compatibilité. */
export { CanvasRenderer as PixelOfficeEngine } from "./legacy/canvas-renderer";
