/**
 * Résolution statut métier → animation → clip d'atlas.
 *
 * Chaîne : statut ("working") → status_mapping du département ("type")
 *        → animation_aliases du pack (si le clip n'existe pas)
 *        → clip du personnage ; ultime repli : "idle-down".
 *
 * Module pur (aucun import Phaser), couvert par les tests.
 */

import type { AnimationClipDef, CharacterDef } from "../../contracts/assets";

export const FALLBACK_CLIP = "idle-down";

/** Développe "worker-a/walk-down/{0..5}" en liste de noms de frames. */
export function expandFrames(pattern: string): string[] {
  const match = pattern.match(/^(.*)\{(\d+)\.\.(\d+)\}(.*)$/);
  if (!match) return [pattern];
  const [, prefix, fromStr, toStr, suffix] = match;
  const from = parseInt(fromStr, 10);
  const to = parseInt(toStr, 10);
  if (to < from) throw new Error(`motif de frames invalide: ${pattern}`);
  const frames: string[] = [];
  for (let i = from; i <= to; i++) frames.push(`${prefix}${i}${suffix}`);
  return frames;
}

/** Trouve le clip d'un personnage pour un nom d'animation, avec alias. */
export function resolveClip(
  character: CharacterDef,
  animationName: string,
  aliases: Record<string, string> = {},
): { name: string; clip: AnimationClipDef } | null {
  const direct = character.animations[animationName];
  if (direct) return { name: animationName, clip: direct };
  const alias = aliases[animationName];
  if (alias && character.animations[alias]) {
    return { name: alias, clip: character.animations[alias] };
  }
  const fallback = character.animations[FALLBACK_CLIP];
  if (fallback) return { name: FALLBACK_CLIP, clip: fallback };
  return null;
}

/** Résout le clip à jouer pour un statut d'agent. */
export function resolveAnimationForStatus(
  character: CharacterDef,
  status: string,
  statusMapping: Record<string, string> = {},
  aliases: Record<string, string> = {},
): { name: string; clip: AnimationClipDef } | null {
  const animationName = statusMapping[status] ?? FALLBACK_CLIP;
  return resolveClip(character, animationName, aliases);
}

/** Clé Phaser unique d'un clip : "<characterId>:<clipName>". */
export function clipKey(characterId: string, clipName: string): string {
  return `${characterId}:${clipName}`;
}

/**
 * Clip d'un agent assis, orienté par son siège quand le personnage possède
 * une variante directionnelle (`sit-left`, `sit-right`...). Les personnages
 * sans variantes (legacy) gardent leur clip de base — le repli `idle-down`
 * d'une variante manquante n'est jamais préféré au clip de base.
 */
export function resolveSeatedClip(
  character: CharacterDef,
  animationName: string,
  facing: string | null,
  aliases: Record<string, string> = {},
): { name: string; clip: AnimationClipDef } | null {
  const base = resolveClip(character, animationName, aliases);
  if (!base || !facing || !base.name.startsWith("sit")) return base;
  const faced = resolveClip(character, `sit-${facing}`, aliases);
  if (faced && faced.name !== FALLBACK_CLIP) return faced;
  return base;
}

/** Clip de marche selon la direction du déplacement. */
export function walkClipForDirection(
  character: CharacterDef,
  dx: number,
  dy: number,
  aliases: Record<string, string> = {},
): { name: string; clip: AnimationClipDef } | null {
  const direction = Math.abs(dx) > Math.abs(dy)
    ? (dx > 0 ? "right" : "left")
    : (dy > 0 ? "down" : "up");
  return resolveClip(character, `walk-${direction}`, aliases);
}
