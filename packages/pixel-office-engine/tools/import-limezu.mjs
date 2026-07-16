/**
 * Import des packs LimeZu (assets sous licence) vers le dossier local
 * gitignoré `apps/web/public/assets/licensed/limezu/`.
 *
 * Usage : npm run assets:import-limezu -- "C:\AgentCompanyAssets\LimeZu"
 *
 * Le script ne copie JAMAIS vers un dossier suivi par git, renomme selon la
 * nomenclature logique, génère atlas + manifests + provenance + rapport,
 * et échoue proprement si une archive requise est absente.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { unzipSync } from "fflate";
import { PNG } from "pngjs";

import {
  atlasJson,
  directionalBlocks,
  ImportError,
  isPathIgnored,
  LIMEZU_DIRECTIONS,
  logicalSlug,
  shelfPack,
  validateMapping,
} from "./limezu-lib.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..", "..");
const OUT_BASE = path.join(REPO, "apps", "web", "public", "assets");
const PACKS_JSON = path.join(OUT_BASE, "packs.json");

// ------------------------------------------------------------------ helpers

const report = {
  started_at: new Date().toISOString(),
  packs: {},
  warnings: [],
  missing_archives: [],
};

function warn(message) {
  report.warnings.push(message);
  console.warn(`  ⚠ ${message}`);
}

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

function findArchive(srcDir, pattern) {
  const regex = new RegExp(
    `^${pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*")}$`,
    "i",
  );
  return fs.readdirSync(srcDir).find((f) => regex.test(f)) ?? null;
}

function unzipFiltered(archivePath, predicate) {
  const buffer = fs.readFileSync(archivePath);
  return unzipSync(new Uint8Array(buffer), {
    filter: (file) => predicate(file.name),
  });
}

function decodePng(bytes) {
  return PNG.sync.read(Buffer.from(bytes));
}

function blit(dst, src, dx, dy, sx = 0, sy = 0, w = src.width, h = src.height) {
  for (let y = 0; y < h; y++) {
    const srcStart = ((sy + y) * src.width + sx) * 4;
    const dstStart = ((dy + y) * dst.width + dx) * 4;
    src.data.copy(dst.data, dstStart, srcStart, srcStart + w * 4);
  }
}

/** blit avec alpha (compositions de frames), sous-rectangle source optionnel. */
function blitAlpha(dst, src, dx, dy, sx = 0, sy = 0, w = src.width, h = src.height) {
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const s = (((sy + y) * src.width + sx + x) << 2);
      const alpha = src.data[s + 3];
      if (alpha === 0) continue;
      const d = (((dy + y) * dst.width) + dx + x) << 2;
      if (alpha === 255) {
        dst.data[d] = src.data[s]; dst.data[d + 1] = src.data[s + 1];
        dst.data[d + 2] = src.data[s + 2]; dst.data[d + 3] = 255;
      } else {
        const a = alpha / 255;
        for (let c = 0; c < 3; c++) {
          dst.data[d + c] = Math.round(src.data[s + c] * a + dst.data[d + c] * (1 - a));
        }
        dst.data[d + 3] = Math.max(dst.data[d + 3], alpha);
      }
    }
  }
}

// ------------------------------------- personnages générés (couches bakées)

const GEN_DIRECTIONS = LIMEZU_DIRECTIONS; // ordre des blocs directionnels

function generatedLayerFile(layer, spec) {
  const pad = (n) => String(n).padStart(2, "0");
  switch (layer) {
    case "body": return `Bodies/32x32/Body_32x32_${pad(spec)}.png`;
    case "eyes": return `Eyes/32x32/Eyes_32x32_${pad(spec)}.png`;
    case "outfit": return `Outfits/32x32/Outfit_${pad(spec[0])}_32x32_${pad(spec[1])}.png`;
    case "hair": return `Hairstyles/32x32/Hairstyle_${pad(spec[0])}_32x32_${pad(spec[1])}.png`;
    default: throw new ImportError(`couche inconnue: ${layer}`);
  }
}

/**
 * Compose les variantes du Character Generator (corps × yeux × tenue ×
 * coiffure) et découpe les clips depuis la méga-feuille (grille 32×64).
 * Retourne les entrées de manifest ; les frames sont poussées dans `frames`.
 */
function importGeneratedVariants(packId, pack, srcDir, frames) {
  const gen = pack.generated;
  if (!gen) return [];
  const base = gen.base_path;
  const archivePath = path.join(srcDir, pack.archiveFile);

  // fichiers de couches nécessaires (avec replis couleur/style → 01)
  const wanted = new Set();
  for (const variant of gen.variants) {
    wanted.add(generatedLayerFile("body", variant.body));
    wanted.add(generatedLayerFile("eyes", variant.eyes));
    wanted.add(generatedLayerFile("outfit", variant.outfit));
    wanted.add(generatedLayerFile("outfit", [variant.outfit[0], 1]));
    wanted.add(generatedLayerFile("hair", variant.hair));
    wanted.add(generatedLayerFile("hair", [variant.hair[0], 1]));
    wanted.add(generatedLayerFile("hair", [1, 1]));
  }
  const entries = unzipFiltered(archivePath, (name) =>
    name.startsWith(base) && [...wanted].some((w) => name === base + w));
  const cache = new Map();
  const decodeLayer = (file) => {
    if (!cache.has(file)) {
      const bytes = entries[base + file];
      cache.set(file, bytes ? decodePng(bytes) : null);
    }
    return cache.get(file);
  };
  const resolveLayer = (layer, spec, fallbacks) => {
    const candidates = [spec, ...fallbacks];
    for (const candidate of candidates) {
      const png = decodeLayer(generatedLayerFile(layer, candidate));
      if (png) return png;
    }
    return null;
  };

  const FW = 32, FH = 64;
  const characters = [];
  for (const variant of gen.variants) {
    const layers = [
      resolveLayer("body", variant.body, []),
      resolveLayer("eyes", variant.eyes, []),
      resolveLayer("outfit", variant.outfit, [[variant.outfit[0], 1]]),
      resolveLayer("hair", variant.hair, [[variant.hair[0], 1], [1, 1]]),
    ];
    if (layers.some((l) => !l)) {
      warn(`${packId}: variante "${variant.id}" ignorée (couche introuvable)`);
      continue;
    }
    const composeCell = (row, col) => {
      const cell = new PNG({ width: FW, height: FH });
      for (const layer of layers) {
        blitAlpha(cell, layer, 0, 0, col * FW, row * FH, FW, FH);
      }
      return cell;
    };

    const animations = {};
    const charId = `limezu-gen-${variant.id}`;
    for (const [clipName, def] of Object.entries(gen.clips)) {
      if (def.directional) {
        const perDir = def.count / 4;
        GEN_DIRECTIONS.forEach((dir, d) => {
          for (let i = 0; i < perDir; i++) {
            frames.push({
              key: `${charId}/${clipName}-${dir}/${i}`,
              png: composeCell(def.row, def.from + d * perDir + i),
            });
          }
          animations[`${clipName}-${dir}`] = {
            frames: `${charId}/${clipName}-${dir}/{0..${perDir - 1}}`,
            frameRate: def.frameRate, repeat: def.repeat ?? -1,
          };
        });
      } else {
        for (let i = 0; i < def.count; i++) {
          frames.push({
            key: `${charId}/${clipName}/${i}`,
            png: composeCell(def.row, def.from + i),
          });
        }
        animations[clipName] = {
          frames: `${charId}/${clipName}/{0..${def.count - 1}}`,
          frameRate: def.frameRate, repeat: def.repeat ?? -1,
        };
      }
    }
    // clip plat "sit" : les alias communs du pack (type→sit...) restent
    // valides ; le moteur upgrade vers sit-<facing> quand disponible
    if (animations["sit-right"] && !animations["sit"]) {
      animations["sit"] = { ...animations["sit-right"] };
    }
    characters.push({ id: charId, animations });
  }
  return characters;
}

/** Rogne les bords transparents (les singles LimeZu ont un fort padding). */
function trimTransparent(png) {
  let minX = png.width, minY = png.height, maxX = -1, maxY = -1;
  for (let y = 0; y < png.height; y++) {
    for (let x = 0; x < png.width; x++) {
      if (png.data[((y * png.width + x) << 2) + 3] > 0) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (maxX < 0) return png; // entièrement transparent
  const out = new PNG({ width: maxX - minX + 1, height: maxY - minY + 1 });
  blit(out, png, 0, 0, minX, minY, out.width, out.height);
  return out;
}

/** Compose des frames décodées en atlas PNG+JSON dans targetDir. */
function writeAtlases(targetDir, atlasBaseName, frames) {
  const sheets = shelfPack(frames.map((f) => ({ key: f.key, w: f.png.width, h: f.png.height })));
  const byKey = new Map(frames.map((f) => [f.key, f.png]));
  const atlases = [];
  const atlasOf = new Map(); // frame key → atlas id
  sheets.forEach((sheet, index) => {
    const suffix = sheets.length > 1 ? `-${index + 1}` : "";
    const imageName = `${atlasBaseName}${suffix}.png`;
    const canvas = new PNG({ width: sheet.width, height: sheet.height });
    for (const item of sheet.items) {
      blit(canvas, byKey.get(item.key), item.x, item.y);
    }
    fs.mkdirSync(path.join(targetDir, "atlases"), { recursive: true });
    fs.writeFileSync(path.join(targetDir, "atlases", imageName), PNG.sync.write(canvas));
    writeJson(
      path.join(targetDir, "atlases", `${atlasBaseName}${suffix}.json`),
      atlasJson(imageName, sheet),
    );
    atlases.push({
      id: `${atlasBaseName}${suffix}`,
      image: `atlases/${imageName}`,
      data: `atlases/${atlasBaseName}${suffix}.json`,
    });
    for (const item of sheet.items) atlasOf.set(item.key, `${atlasBaseName}${suffix}`);
  });
  return { atlases, atlasOf };
}

function baseManifest(packId, pack) {
  return {
    manifest_version: "1.0",
    pack_id: packId,
    extends: "core",
    provenance: {
      ...pack.provenance,
      imported_at: new Date().toISOString(),
      archive: pack.archiveFile,
    },
    grid: { tile: 32, character: { w: 32, h: 64 } },
    atlases: [],
    tilesets: [],
    tilemaps: [],
    characters: [],
    stations: [],
    themes: [],
    effects: [],
    role_characters: {},
    animation_aliases: {},
  };
}

function writeProvenance(targetDir, packId, pack, extra = "") {
  fs.mkdirSync(targetDir, { recursive: true });
  fs.writeFileSync(path.join(targetDir, "PROVENANCE.md"), `# ${packId}

- **Source** : ${pack.provenance.source}
- **Archive** : ${pack.archiveFile}
- **Importé le** : ${new Date().toISOString()}
- **Licence** : ${pack.provenance.license}
- **Crédit** : ${pack.provenance.credit_url ?? ""}

Ces fichiers sont sous licence LimeZu : usage dans ce projet uniquement,
**redistribution interdite** — ce dossier est exclu de git.
${extra}`);
}

// --------------------------------------------------------------- characters

function importCharacters(packId, pack, srcDir) {
  const archivePath = path.join(srcDir, pack.archiveFile);
  const base = pack.base_path;
  const entries = unzipFiltered(archivePath, (name) => name.startsWith(base) && name.endsWith(".png"));
  const available = new Set(Object.keys(entries).map((n) => n.slice(base.length)));

  const frames = [];
  const characters = [];
  const frameH = pack.frame.h;
  const frameW = pack.frame.w;

  for (const character of pack.characters) {
    const clips = {};
    let resolvedPrefix = null;
    for (const [clipBase, clipDef] of Object.entries(pack.clips)) {
      let fileName = null;
      for (const prefix of character.prefixes) {
        const candidate = `${prefix}_${clipDef.token}_32x32.png`;
        if (available.has(candidate)) {
          fileName = candidate;
          resolvedPrefix = resolvedPrefix ?? prefix;
          break;
        }
      }
      if (!fileName) continue;
      const png = decodePng(entries[base + fileName]);
      if (png.height !== frameH || png.width % frameW !== 0) {
        warn(`${packId}: ${fileName} dimensions inattendues ${png.width}×${png.height}`);
        continue;
      }
      const count = png.width / frameW;
      const sliceFrame = (index, key) => {
        const cell = new PNG({ width: frameW, height: frameH });
        blit(cell, png, 0, 0, index * frameW, 0, frameW, frameH);
        frames.push({ key, png: cell });
      };

      if (clipDef.directional) {
        const blocks = directionalBlocks(count);
        if (!blocks) {
          warn(`${packId}: ${fileName} n'est pas une bande 4 directions (${count} frames)`);
          continue;
        }
        if (clipDef.keep) {
          const indices = blocks[clipDef.keep];
          indices.forEach((frameIndex, i) => sliceFrame(frameIndex, `${character.id}/${clipBase}/${i}`));
          clips[clipBase] = { frames: indices.length, directional: false };
        } else {
          for (const dir of LIMEZU_DIRECTIONS) {
            blocks[dir].forEach((frameIndex, i) =>
              sliceFrame(frameIndex, `${character.id}/${clipBase}-${dir}/${i}`));
          }
          clips[clipBase] = { frames: count / 4, directional: true };
        }
      } else {
        const kept = Math.min(count, clipDef.max_frames ?? count);
        for (let i = 0; i < kept; i++) sliceFrame(i, `${character.id}/${clipBase}/${i}`);
        clips[clipBase] = { frames: kept, directional: false };
      }
    }

    if (!clips.idle || !clips.walk) {
      warn(`${packId}: personnage "${character.id}" ignoré (idle/walk introuvables, préfixes ${character.prefixes.join(", ")})`);
      continue;
    }
    characters.push({ id: character.id, prefix: resolvedPrefix, clips });
  }

  if (characters.length === 0) throw new ImportError(`${packId}: aucun personnage résolu`);

  const generated = importGeneratedVariants(packId, pack, srcDir, frames);

  const targetDir = path.join(OUT_BASE, ...pack.target_dir.split("/"));
  const { atlases, atlasOf } = writeAtlases(targetDir, "limezu-characters", frames);
  const atlasId = atlases[0].id;
  if (atlases.length > 1) warn(`${packId}: personnages répartis sur ${atlases.length} atlas — vérifier les clés`);
  void atlasOf;

  const manifest = baseManifest(packId, pack);
  manifest.atlases = atlases;
  manifest.characters = characters.map((c) => {
    const animations = {};
    for (const [clipBase, info] of Object.entries(c.clips)) {
      if (info.directional) {
        for (const dir of LIMEZU_DIRECTIONS) {
          animations[`${clipBase}-${dir}`] = {
            frames: `${c.id}/${clipBase}-${dir}/{0..${info.frames - 1}}`,
            frameRate: clipBase === "walk" ? 10 : 4,
            repeat: -1,
          };
        }
      } else {
        animations[clipBase === "idle" ? "idle-down" : clipBase] = {
          frames: `${c.id}/${clipBase}/{0..${info.frames - 1}}`,
          frameRate: clipBase === "walk" ? 10 : 4,
          repeat: -1,
        };
      }
    }
    // idle directionnel → idle-down/up/left/right déjà nommés via clipBase "idle"
    return {
      id: `limezu-${c.id}`,
      atlas: atlasId,
      size: { w: 32, h: 64 },
      pivot: { x: 0.5, y: 0.95 },
      animations,
    };
  });
  manifest.characters.push(...generated.map((g) => ({
    id: g.id,
    atlas: atlasId,
    size: { w: 32, h: 64 },
    pivot: { x: 0.5, y: 0.95 },
    animations: g.animations,
  })));
  const importedIds = new Set(manifest.characters.map((c) => c.id));
  manifest.role_characters = { "*": [...importedIds] };
  for (const [role, ids] of Object.entries(pack.role_characters ?? {})) {
    const valid = ids.filter((id) => importedIds.has(id));
    if (valid.length < ids.length) {
      warn(`${packId}: rôle "${role}" référence des personnages non importés (${ids.filter((id) => !importedIds.has(id)).join(", ")})`);
    }
    if (valid.length) manifest.role_characters[role] = valid;
  }
  manifest.animation_aliases = {
    type: "sit", think: "phone", coffee: "idle-down", chart: "sit",
    write: "read", draw: "sit", play: "phone", point: "phone",
    away: "sit", walk: "walk-down", talk: "phone", celebrate: "idle-down",
    "sit-up": "sit-left", "sit-down": "sit-right",
  };
  writeJson(path.join(targetDir, "manifest.json"), manifest);
  writeProvenance(targetDir, packId, pack,
    `\nPersonnages importés : ${characters.map((c) => c.id).join(", ")}`);

  report.packs[packId] = {
    characters: characters.map((c) => ({ id: c.id, prefix: c.prefix, clips: Object.keys(c.clips) })),
    frames: frames.length,
    atlases: atlases.length,
  };
}

// ------------------------------------------------------------- singles/atlas

function importSingles(packId, pack, srcDir) {
  const archivePath = path.join(srcDir, pack.archiveFile);
  const dirPrefix = pack.singles_glob;
  const include = (name) => {
    if (!name.includes(dirPrefix) || !name.endsWith(".png")) return false;
    const baseName = name.split("/").pop();
    if (pack.include_patterns) {
      return pack.include_patterns.some((p) => baseName.includes(p));
    }
    return true;
  };
  const entries = unzipFiltered(archivePath, include);
  let names = Object.keys(entries).sort();
  if (pack.max_files && names.length > pack.max_files) {
    warn(`${packId}: ${names.length} fichiers filtrés, plafonnés à ${pack.max_files}`);
    names = names.slice(0, pack.max_files);
  }
  if (names.length === 0) throw new ImportError(`${packId}: aucun fichier sélectionné`);

  const frames = [];
  const seen = new Set();
  for (const name of names) {
    let png = decodePng(entries[name]);
    if (pack.trim) png = trimTransparent(png);
    if (!pack.trim && (png.width % 16 !== 0 || png.height % 16 !== 0)) {
      warn(`${packId}: ${name.split("/").pop()} dimensions non multiples de 16 (${png.width}×${png.height})`);
    }
    if (png.width > 2048 || png.height > 2048) {
      warn(`${packId}: ${name.split("/").pop()} ignoré (> 2048px)`);
      continue;
    }
    let key = `${pack.logical_prefix}.${logicalSlug(name.split("/").pop())}`;
    if (seen.has(key)) {
      warn(`${packId}: doublon logique "${key}" — suffixé`);
      let i = 2;
      while (seen.has(`${key}-${i}`)) i++;
      key = `${key}-${i}`;
    }
    seen.add(key);
    frames.push({ key, png });
  }

  // frames composées (ex. bureau nu + plateau écrans) bakées à l'import
  const frameByKey = new Map(frames.map((f) => [f.key, f.png]));
  for (const composed of pack.composed_frames ?? []) {
    const parts = composed.layers.map((layer) => ({
      png: frameByKey.get(layer.frame),
      dx: layer.dx ?? 0,
      dy: layer.dy ?? 0,
      key: layer.frame,
    }));
    const missing = parts.find((p) => !p.png);
    if (missing) {
      warn(`${packId}: composition "${composed.key}" — frame "${missing.key}" introuvable`);
      continue;
    }
    const minX = Math.min(...parts.map((p) => p.dx));
    const minY = Math.min(...parts.map((p) => p.dy));
    const maxX = Math.max(...parts.map((p) => p.dx + p.png.width));
    const maxY = Math.max(...parts.map((p) => p.dy + p.png.height));
    const canvas = new PNG({ width: maxX - minX, height: maxY - minY });
    for (const part of parts) {
      blitAlpha(canvas, part.png, part.dx - minX, part.dy - minY);
    }
    frames.push({ key: composed.key, png: canvas });
    frameByKey.set(composed.key, canvas);
  }

  const targetDir = path.join(OUT_BASE, ...pack.target_dir.split("/"));
  const { atlases, atlasOf } = writeAtlases(targetDir, packId, frames);

  const manifest = baseManifest(packId, pack);
  manifest.atlases = atlases;

  // stations déclarées dans le mapping (curation) → StationAssetDef
  for (const station of pack.stations ?? []) {
    const backAtlas = atlasOf.get(station.frame);
    if (!backAtlas) {
      warn(`${packId}: station "${station.id}" — frame "${station.frame}" introuvable`);
      continue;
    }
    const frontOk = station.front && atlasOf.get(station.front);
    if (station.front && !frontOk) {
      warn(`${packId}: station "${station.id}" — frame front "${station.front}" introuvable`);
    }
    manifest.stations.push({
      kind: station.kind,
      id: station.id,
      atlas: backAtlas,
      frames: { back: station.frame, ...(frontOk ? { front: station.front } : {}) },
      footprint: station.footprint,
      pivot: station.pivot ?? { x: 0, y: 0 },
      seats: station.seats ?? [],
      blocking: station.blocking ?? true,
    });
  }
  manifest.themes = pack.themes ?? [];

  for (const tilesetDef of pack.tilesets ?? []) {
    const tsEntries = unzipFiltered(archivePath, (n) => n === tilesetDef.zip_path);
    const bytes = tsEntries[tilesetDef.zip_path];
    if (!bytes) {
      warn(`${packId}: tileset ${tilesetDef.zip_path} introuvable`);
      continue;
    }
    const png = decodePng(bytes);
    fs.mkdirSync(path.join(targetDir, "tilesets"), { recursive: true });
    fs.writeFileSync(path.join(targetDir, "tilesets", `${tilesetDef.id}.png`), PNG.sync.write(png));
    manifest.tilesets.push({
      id: tilesetDef.id,
      image: `tilesets/${tilesetDef.id}.png`,
      tile: tilesetDef.tile,
      margin: 0,
      spacing: 0,
      columns: png.width / tilesetDef.tile,
    });
  }

  writeJson(path.join(targetDir, "manifest.json"), manifest);
  writeProvenance(targetDir, packId, pack);
  report.packs[packId] = { frames: frames.length, atlases: atlases.length,
                           tilesets: manifest.tilesets.length };
}

// -------------------------------------------------------------------- sheets

function importSheets(packId, pack, srcDir) {
  const archivePath = path.join(srcDir, pack.archiveFile);
  const include = (name) => {
    if (!name.endsWith(".png")) return false;
    const parts = name.split("/");
    if (!name.includes(`/${pack.sheets_glob}`) && !name.startsWith(pack.sheets_glob)) return false;
    const baseName = parts.pop();
    return pack.sheets_patterns.some((p) => baseName.startsWith(p));
  };
  const entries = unzipFiltered(archivePath, include);
  const frames = [];
  for (const [name, bytes] of Object.entries(entries)) {
    const png = decodePng(bytes);
    if (png.width > pack.max_sheet_size || png.height > pack.max_sheet_size) {
      warn(`${packId}: ${name.split("/").pop()} ignoré (${png.width}×${png.height} > ${pack.max_sheet_size})`);
      continue;
    }
    frames.push({ key: `${pack.logical_prefix}.${logicalSlug(name.split("/").pop())}`, png });
  }
  if (frames.length === 0) throw new ImportError(`${packId}: aucune feuille sélectionnée`);
  const targetDir = path.join(OUT_BASE, ...pack.target_dir.split("/"));
  const { atlases } = writeAtlases(targetDir, packId, frames);
  const manifest = baseManifest(packId, pack);
  manifest.atlases = atlases;
  writeJson(path.join(targetDir, "manifest.json"), manifest);
  writeProvenance(targetDir, packId, pack);
  report.packs[packId] = { sheets: frames.length, atlases: atlases.length };
}

// ---------------------------------------------------------------------- main

function main() {
  const srcDir = process.argv[2];
  if (!srcDir || !fs.existsSync(srcDir)) {
    console.error("Usage : npm run assets:import-limezu -- \"C:\\AgentCompanyAssets\\LimeZu\"");
    process.exit(2);
  }

  const mapping = validateMapping(
    JSON.parse(fs.readFileSync(path.join(HERE, "limezu-mapping.json"), "utf-8")),
  );

  // défense en profondeur : la cible doit être ignorée par git
  const gitignore = fs.readFileSync(path.join(REPO, ".gitignore"), "utf-8");
  for (const pack of Object.values(mapping.packs)) {
    const rel = `apps/web/public/assets/${pack.target_dir}/x.png`;
    if (!isPathIgnored(gitignore, rel)) {
      throw new ImportError(`Refus d'importer : "${rel}" n'est pas couvert par .gitignore`);
    }
  }

  for (const [packId, pack] of Object.entries(mapping.packs)) {
    const archiveFile = findArchive(srcDir, pack.archive);
    if (!archiveFile) {
      report.missing_archives.push({ pack: packId, pattern: pack.archive });
      console.error(`✖ ${packId}: archive "${pack.archive}" introuvable dans ${srcDir}`);
      continue;
    }
    pack.archiveFile = archiveFile;
    console.log(`▶ ${packId} ← ${archiveFile}`);
    try {
      if (pack.characters) importCharacters(packId, pack, srcDir);
      else if (pack.sheets_patterns) importSheets(packId, pack, srcDir);
      else importSingles(packId, pack, srcDir);
      console.log(`  ✔ importé`);
    } catch (error) {
      report.warnings.push(`${packId}: ÉCHEC — ${error.message}`);
      console.error(`  ✖ ${error.message}`);
    }
  }

  // mise à jour de packs.json (packs facultatifs)
  const packsIndex = JSON.parse(fs.readFileSync(PACKS_JSON, "utf-8"));
  packsIndex.optional_packs = packsIndex.optional_packs ?? {};
  for (const [packId, pack] of Object.entries(mapping.packs)) {
    if (report.packs[packId]) packsIndex.optional_packs[packId] = pack.target_dir;
  }
  writeJson(PACKS_JSON, packsIndex);

  report.finished_at = new Date().toISOString();
  writeJson(path.join(OUT_BASE, "licensed", "limezu", "import-report.json"), report);

  console.log(`\nRapport : apps/web/public/assets/licensed/limezu/import-report.json`);
  console.log(`Packs importés : ${Object.keys(report.packs).join(", ") || "aucun"}`);
  if (report.warnings.length) console.log(`Avertissements : ${report.warnings.length}`);
  if (report.missing_archives.length) {
    console.error(`Archives manquantes : ${report.missing_archives.map((m) => m.pattern).join(", ")}`);
    process.exit(1);
  }
}

main();
