/**
 * Fonctions pures du pipeline d'import LimeZu — testables sans les archives.
 * Aucun pixel LimeZu n'est présent dans ce fichier ni dans le mapping.
 */

/** Ordre des directions dans les bandes de personnages LimeZu. */
export const LIMEZU_DIRECTIONS = ["right", "up", "left", "down"];

export class ImportError extends Error {}

/** Valide la structure du fichier limezu-mapping.json. */
export function validateMapping(mapping) {
  if (!mapping || typeof mapping !== "object") throw new ImportError("mapping non-objet");
  if (mapping.mapping_version !== "1.0") {
    throw new ImportError(`mapping_version "${mapping.mapping_version}" non supportée`);
  }
  if (!mapping.packs || typeof mapping.packs !== "object") {
    throw new ImportError("mapping.packs manquant");
  }
  for (const [packId, pack] of Object.entries(mapping.packs)) {
    if (!pack.archive) throw new ImportError(`pack "${packId}": archive manquante`);
    if (!pack.target_dir) throw new ImportError(`pack "${packId}": target_dir manquant`);
    if (!/^licensed\//.test(pack.target_dir)) {
      throw new ImportError(
        `pack "${packId}": target_dir doit être sous licensed/ (jamais suivi par git)`,
      );
    }
    if (pack.characters) {
      for (const c of pack.characters) {
        if (!c.id || !Array.isArray(c.prefixes) || c.prefixes.length === 0) {
          throw new ImportError(`pack "${packId}": personnage invalide (${c.id ?? "?"})`);
        }
      }
    }
  }
  return mapping;
}

/**
 * Vérifie qu'un chemin de sortie est couvert par le .gitignore du dépôt
 * (défense en profondeur contre la redistribution d'assets sous licence).
 */
export function isPathIgnored(gitignoreContent, relPath) {
  const normalized = relPath.replace(/\\/g, "/");
  return gitignoreContent
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .some((pattern) => {
      const clean = pattern.replace(/\/$/, "");
      if (clean.startsWith("*")) {
        return normalized.endsWith(clean.slice(1));
      }
      return normalized === clean || normalized.startsWith(`${clean}/`)
        || normalized.includes(`/${clean}/`);
    });
}

/** slug stable pour un identifiant logique. */
export function logicalSlug(name) {
  return name
    .replace(/\.png$/i, "")
    .replace(/_?\d+x\d+_?/gi, "_")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
}

/**
 * Découpe une bande horizontale en blocs directionnels LimeZu.
 * 4 × n frames → { right: [0..n-1], up: [...], left: [...], down: [...] }.
 */
export function directionalBlocks(frameCount) {
  if (frameCount % 4 !== 0) return null;
  const perDir = frameCount / 4;
  const blocks = {};
  LIMEZU_DIRECTIONS.forEach((dir, i) => {
    blocks[dir] = Array.from({ length: perDir }, (_, f) => i * perDir + f);
  });
  return blocks;
}

/**
 * Packe des rectangles en étagères sur une ou plusieurs feuilles ≤ maxSize.
 * Retourne [{width, height, items: [{key, x, y, w, h}]}].
 */
export function shelfPack(items, maxSize = 2048) {
  const sheets = [];
  let sheet = null;
  let shelfY = 0;
  let shelfH = 0;
  let cursorX = 0;

  const newSheet = () => {
    sheet = { width: 0, height: 0, items: [] };
    sheets.push(sheet);
    shelfY = 0;
    shelfH = 0;
    cursorX = 0;
  };
  newSheet();

  for (const item of items) {
    if (item.w > maxSize || item.h > maxSize) {
      throw new ImportError(`"${item.key}" (${item.w}×${item.h}) dépasse ${maxSize}px`);
    }
    if (cursorX + item.w > maxSize) {
      shelfY += shelfH;
      shelfH = 0;
      cursorX = 0;
    }
    if (shelfY + item.h > maxSize) newSheet();
    sheet.items.push({ key: item.key, x: cursorX, y: shelfY, w: item.w, h: item.h });
    cursorX += item.w;
    shelfH = Math.max(shelfH, item.h);
    sheet.width = Math.max(sheet.width, cursorX);
    sheet.height = Math.max(sheet.height, shelfY + shelfH);
  }
  return sheets.filter((s) => s.items.length > 0);
}

/** JSON hash TexturePacker pour un jeu de frames placées. */
export function atlasJson(imageFile, sheet) {
  const frames = {};
  for (const item of sheet.items) {
    frames[item.key] = {
      frame: { x: item.x, y: item.y, w: item.w, h: item.h },
      rotated: false,
      trimmed: false,
      sourceSize: { w: item.w, h: item.h },
      spriteSourceSize: { x: 0, y: 0, w: item.w, h: item.h },
    };
  }
  return {
    frames,
    meta: { image: imageFile, size: { w: sheet.width, h: sheet.height }, scale: "1" },
  };
}
