/**
 * Contrats de scène du Pixel Office Engine.
 *
 * Interfaces publiques historiques (`SceneSpec`, `RoomSpec`, `StationSpec`,
 * `EntitySpec`) préservées ; uniquement étendues par des champs optionnels.
 * Le moteur ne connaît aucun secteur métier : tout est décrit par ces données.
 */

export type Facing = "up" | "down" | "left" | "right";

export interface StationSpec {
  id: string;
  name: string;
  kind: string; // desk, whiteboard, server-rack, bookshelf, couch, art-station...
  x: number; // coordonnées tuile relatives à la salle
  y: number;
  /** id d'asset station d'un pack (sinon résolution par kind) */
  assetId?: string;
  facing?: Facing;
  /** emprise en tuiles, défaut 1×1 */
  footprint?: { w: number; h: number };
  /** nombre de sièges, défaut 1 */
  capacity?: number;
  layerHint?: "furniture-back" | "furniture-front";
}

export interface RoomSpec {
  id: string;
  name: string;
  theme: string; // office_theme fourni par les données
  x: number; // coordonnées tuile absolues
  y: number;
  w: number;
  h: number;
  badge?: string; // ex: "3 tâches actives"
  /** sous-titre de l'enseigne, ex: "5 EN LIGNE" */
  subtitle?: string;
  stations: StationSpec[];
  /** thème d'un pack d'assets (prioritaire sur `theme`) */
  themeId?: string;
  /** salle dessinée depuis une tilemap Tiled d'un pack */
  tilemapId?: string;
  /**
   * Portes, en tuiles relatives à la salle. `y === 0` = percée dans le mur
   * haut ; `y === h` = entrée par le bas. Les agents ne franchissent la
   * frontière d'une salle qu'aux portes.
   */
  doors?: { x: number; y: number }[];
  /** offsets x des fenêtres sur le mur haut */
  windows?: number[];
}

export interface EntitySpec {
  id: string;
  name: string;
  role: string;
  status: string;
  roomId: string;
  stationId?: string;
  sprite?: string;
  /** personnage d'un pack d'assets (sinon résolution par sprite/role) */
  characterId?: string;
  /** vitesse de déplacement, défaut 3 tuiles/s */
  speedTilesPerSec?: number;
}

/** Élément de décor hors salle (arbre, plante, banc...), résolu par assetId. */
export interface DecorationSpec {
  assetId: string;
  x: number; // tuiles absolues
  y: number;
}

export interface SceneSpec {
  cols: number;
  rows: number;
  rooms: RoomSpec[];
  entities: EntitySpec[];
  /** thème peint sur toute la scène sous les salles (campus extérieur) */
  groundThemeId?: string;
  /** rectangles d'allées peints avec les pathTiles du ground theme */
  paths?: { x: number; y: number; w: number; h: number }[];
  /** décor extérieur (arbres, bancs...) */
  decorations?: DecorationSpec[];
  /** statut logique → animation, fourni par les modules (jamais codé en dur) */
  statusMapping?: Record<string, string>;
  /** animation → glyphe texte (renderer legacy uniquement) */
  animationGlyphs?: Record<string, string>;
  /** packs d'assets à charger pour cette scène (renderer Phaser) */
  assetPackIds?: string[];
  /** taille de tuile en pixels, défaut 32 */
  gridTile?: number;
}
