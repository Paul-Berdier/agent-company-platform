import type { SceneSpec } from "./scene";

export interface EngineCallbacks {
  onRoomClick?: (roomId: string) => void;
  onEntityClick?: (entityId: string) => void;
  onEntityHover?: (entityId: string | null) => void;
  /** appelé quand le renderer demandé a dû être remplacé par le fallback */
  onRendererFallback?: (reason: string) => void;
}

/** Interface commune à tous les renderers (canvas legacy, Phaser, futurs). */
export interface IOfficeRenderer {
  setScene(scene: SceneSpec): void;
  updateEntityStatus(entityId: string, status: string): void;
  /**
   * Affiche une émote au-dessus d'une entité.
   * `effectId` : id d'effet d'un pack d'assets ; un glyphe texte brut est
   * accepté en compatibilité pendant la migration.
   */
  emote(entityId: string, effectId: string, durationMs?: number): void;
  pulseRoom(roomId: string): void;
  selectEntity(entityId: string | null): void;
  focusRoom(roomId: string): void;
  /** ouvre la galerie d'assets ; `filterPack` limite l'affichage à un pack */
  showGallery(filterPack?: string): void;
  destroy(): void;
}

export type RendererMode = "canvas" | "phaser" | "auto";

export interface RendererOptions {
  /** élément hôte ; le renderer y crée son canvas */
  mount: HTMLElement;
  mode?: RendererMode;
  callbacks?: EngineCallbacks;
  /** base des packs d'assets (défaut "/assets") */
  assetsBaseUrl?: string;
  /**
   * Boucle setTimeout au lieu de requestAnimationFrame (Phaser) : permet de
   * continuer à tourner dans un onglet en arrière-plan.
   */
  forceTimeout?: boolean;
  /** couche debug : grille de collision + états de déplacement (`?debug=1`) */
  debug?: boolean;
}
