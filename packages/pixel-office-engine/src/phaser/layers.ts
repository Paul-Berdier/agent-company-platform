/**
 * Système de couches du renderer Phaser.
 *
 * Ordre (du fond vers l'avant) :
 *   floor < walls < furniture-back / entities / furniture-front < effects < ui
 *
 * Les trois couches centrales partagent une bande de profondeur triée par la
 * coordonnée Y de la base de chaque objet (algorithme du peintre) : un
 * personnage devant un meuble le recouvre, derrière il est recouvert.
 * Les frames `front` des meubles reçoivent un léger biais pour passer devant
 * un personnage assis sur la même rangée.
 */

export const DEPTH_FLOOR = -20;
export const DEPTH_WALLS = -10;
/** base de la bande y-sorted ; profondeur = DEPTH_SORTED + baseY(px) */
export const DEPTH_SORTED = 0;
/** biais des frames front à baseY égal */
export const FRONT_BIAS = 0.5;
export const DEPTH_EFFECTS = 50_000;
export const DEPTH_UI = 60_000;

/** Profondeur d'un objet de la bande triée, à partir de sa base en pixels. */
export function sortedDepth(baseY: number, bias = 0): number {
  return DEPTH_SORTED + baseY + bias;
}
