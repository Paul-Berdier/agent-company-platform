/**
 * Système de couches du renderer Phaser — modèle complet en 14 bandes :
 *
 *   ground < floor < floor_details < walls_back < windows
 *     < [ furniture_back / stations / agents / furniture_front ]  (tri-Y)
 *     < wall_front < effects < labels < interaction < debug < ui
 *
 * Les quatre couches centrales partagent une bande triée par la coordonnée Y
 * de la base de chaque objet (algorithme du peintre) : un personnage devant
 * un meuble le recouvre, derrière il est recouvert. Les frames `front` des
 * meubles reçoivent un léger biais pour passer devant un personnage assis
 * sur la même rangée.
 */

export const DEPTH_GROUND = -30;
export const DEPTH_FLOOR = -20;
export const DEPTH_FLOOR_DETAILS = -15;
export const DEPTH_WALLS_BACK = -10;
export const DEPTH_WINDOWS = -8;
/** base de la bande y-sorted ; profondeur = DEPTH_SORTED + baseY(px) */
export const DEPTH_SORTED = 0;
/** biais des frames front à baseY égal */
export const FRONT_BIAS = 0.5;
/** murs de premier plan (au-dessus de tout le monde de jeu) */
export const DEPTH_WALL_FRONT = 40_000;
export const DEPTH_EFFECTS = 50_000;
export const DEPTH_LABELS = 55_000;
export const DEPTH_INTERACTION = 58_000;
export const DEPTH_DEBUG = 59_000;
export const DEPTH_UI = 60_000;

/** compat : anciens noms utilisés par les scènes existantes */
export const DEPTH_WALLS = DEPTH_WALLS_BACK;

/** Profondeur d'un objet de la bande triée, à partir de sa base en pixels. */
export function sortedDepth(baseY: number, bias = 0): number {
  return DEPTH_SORTED + baseY + bias;
}
