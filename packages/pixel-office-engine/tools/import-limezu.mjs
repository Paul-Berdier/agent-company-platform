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

/** Compose des frames décodées en atlas PNG+JSON dans targetDir. */
function writeAtlases(targetDir, atlasBaseName, frames) {
  const sheets = shelfPack(frames.map((f) => ({ key: f.key, w: f.png.width, h: f.png.height })));
  const byKey = new Map(frames.map((f) => [f.key, f.png]));
  const atlases = [];
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
  });
  return atlases;
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

  const targetDir = path.join(OUT_BASE, ...pack.target_dir.split("/"));
  const atlases = writeAtlases(targetDir, "limezu-characters", frames);
  const atlasId = atlases.length === 1 ? atlases[0].id : atlases[0].id; // personnages tiennent sur 1 feuille sinon warning
  if (atlases.length > 1) warn(`${packId}: personnages répartis sur ${atlases.length} atlas — vérifier les clés`);

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
    away: "sit", walk: "walk-down",
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
    const png = decodePng(entries[name]);
    if (png.width % 16 !== 0 || png.height % 16 !== 0) {
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

  const targetDir = path.join(OUT_BASE, ...pack.target_dir.split("/"));
  const atlases = writeAtlases(targetDir, packId, frames);

  const manifest = baseManifest(packId, pack);
  manifest.atlases = atlases;

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
  const atlases = writeAtlases(targetDir, packId, frames);
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
