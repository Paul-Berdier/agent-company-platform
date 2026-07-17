/**
 * Prévisualisation statique d'une salle : reproduit la peinture d'OfficeScene
 * (sol, mur, fenêtres, stations triées par Y, porte, sièges) en PNG, sans
 * navigateur. Outil de curation locale (fonctionne avec les packs importés).
 *
 * Usage : node tools/room-preview.mjs <department_type> <out.png> [theme_id]
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..", "..");
const ASSETS = path.join(REPO, "apps", "web", "public", "assets");

const [, , deptType = "software-engineering", outFile = "room-preview.png", themeIdArg] = process.argv;

const TILE = 32;
const ROOM_W = 12, ROOM_H = 9, MARGIN = 1;

function readJson(p) { return JSON.parse(fs.readFileSync(p, "utf-8")); }
function blit(dst, src, dx, dy, sx, sy, w, h) {
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const s = ((sy + y) * src.width + sx + x) << 2;
      const alpha = src.data[s + 3];
      if (alpha === 0) continue;
      const d = ((dy + y) * dst.width + dx + x) << 2;
      if (dy + y < 0 || dx + x < 0 || dy + y >= dst.height || dx + x >= dst.width) continue;
      if (alpha === 255) {
        dst.data[d] = src.data[s]; dst.data[d + 1] = src.data[s + 1];
        dst.data[d + 2] = src.data[s + 2]; dst.data[d + 3] = 255;
      } else {
        const a = alpha / 255;
        for (let c = 0; c < 3; c++) {
          dst.data[d + c] = Math.round(src.data[s + c] * a + dst.data[d + c] * (1 - a));
        }
        dst.data[d + 3] = 255;
      }
    }
  }
}

// fusion minimale des packs : placeholders puis licensed (le dernier gagne)
const packsIndex = readJson(path.join(ASSETS, "packs.json"));
const dirs = [
  ...Object.values(packsIndex.packs),
  ...Object.values(packsIndex.optional_packs ?? {}),
];
const stationsByKind = new Map();
const themes = new Map();
const atlases = new Map(); // atlasId → {png, frames}
const tilesets = new Map(); // tilesetId → {png, columns}

for (const dir of dirs) {
  const manifestPath = path.join(ASSETS, dir, "manifest.json");
  if (!fs.existsSync(manifestPath)) continue;
  const manifest = readJson(manifestPath);
  for (const a of manifest.atlases) {
    const jsonPath = path.join(ASSETS, dir, a.data);
    if (!fs.existsSync(jsonPath)) continue;
    const data = readJson(jsonPath);
    atlases.set(a.id, {
      png: PNG.sync.read(fs.readFileSync(path.join(ASSETS, dir, a.image))),
      frames: data.frames,
    });
  }
  for (const t of manifest.tilesets) {
    tilesets.set(t.id, {
      png: PNG.sync.read(fs.readFileSync(path.join(ASSETS, dir, t.image))),
      columns: t.columns,
    });
  }
  for (const s of manifest.stations) stationsByKind.set(s.kind, s);
  for (const t of manifest.themes) themes.set(t.id, t);
}

// stations de la salle : template du plugin si présent, sinon stations legacy
const plugins = fs.readdirSync(path.join(REPO, "plugins"));
let dept = null;
let template = null;
for (const plugin of plugins) {
  const manifest = readJson(path.join(REPO, "plugins", plugin, "plugin.json"));
  const found = manifest.departments?.find((d) => d.department_type === deptType);
  if (found) dept = found;
  const roomsDir = path.join(REPO, "plugins", plugin, "rooms");
  if (fs.existsSync(roomsDir)) {
    for (const file of fs.readdirSync(roomsDir).filter((f) => f.endsWith(".json"))) {
      const t = readJson(path.join(roomsDir, file));
      if (t.department_type === deptType && (!template || t.capacity < template.capacity)) {
        template = t;
      }
    }
  }
}
if (!dept && !template) throw new Error(`département "${deptType}" introuvable dans plugins/`);
if (template) {
  dept = { ...dept, stations: template.stations, office_theme: template.theme };
}

const ROOM_W2 = template?.width ?? ROOM_W;
const ROOM_H2 = template?.height ?? ROOM_H;

const themeId = themeIdArg ?? dept.office_theme;
const theme = { ...(themes.get(themeId) ?? themes.get("default")) };
// itération rapide sans ré-import : THEME_FLOOR="154,155" THEME_WALL="80"
if (process.env.THEME_FLOOR) theme.floorTiles = process.env.THEME_FLOOR.split(",").map(Number);
if (process.env.THEME_WALL) theme.wallTiles = process.env.THEME_WALL.split(",").map(Number);
const tileset = tilesets.get(theme.tileset);
if (!tileset) throw new Error(`tileset "${theme.tileset}" introuvable`);

const img = new PNG({
  width: (ROOM_W2 + 2 * MARGIN) * TILE,
  height: (ROOM_H2 + 2 * MARGIN) * TILE,
});
// fond sombre
for (let i = 0; i < img.data.length; i += 4) {
  img.data[i] = 32; img.data[i + 1] = 36; img.data[i + 2] = 44; img.data[i + 3] = 255;
}

const drawTile = (index, tx, ty) => {
  const sx = (index % tileset.columns) * TILE;
  const sy = Math.floor(index / tileset.columns) * TILE;
  blit(img, tileset.png, (tx + MARGIN) * TILE, (ty + MARGIN) * TILE, sx, sy, TILE, TILE);
};

// sol + mur + fenêtres
for (let j = 0; j < ROOM_H2; j++) {
  for (let i = 0; i < ROOM_W2; i++) {
    drawTile(theme.floorTiles[(i + j) % theme.floorTiles.length], i, j);
  }
}
for (let i = 0; i < ROOM_W2; i++) drawTile(theme.wallTiles[i % theme.wallTiles.length], i, 0);
if (theme.windowTiles?.length) {
  for (const wx of [2, 5, 9]) drawTile(theme.windowTiles[0], wx, 0);
}
// porte basse (parvis)
drawTile(theme.floorTiles[0], Math.floor(ROOM_W2 / 2), ROOM_H2);

// stations triées par baseY
const placed = [];
for (const station of dept.stations) {
  const asset = stationsByKind.get(station.kind) ?? stationsByKind.get("desk");
  if (!asset) continue;
  const atlas = atlases.get(asset.atlas);
  const frame = atlas?.frames[asset.frames.back]?.frame;
  if (!frame) { console.warn(`frame absente pour kind=${station.kind}`); continue; }
  placed.push({ station, asset, atlas, frame, baseY: (station.y * TILE) + frame.h });
}
placed.sort((a, b) => a.baseY - b.baseY);
for (const p of placed) {
  const footprintBottom = (p.station.y + (p.asset.footprint?.h ?? 1)) * TILE;
  const drawY = p.asset.pivot?.y === 1
    ? footprintBottom - p.frame.h
    : p.station.y * TILE;
  blit(img, p.atlas.png, (p.station.x + MARGIN) * TILE, drawY + MARGIN * TILE,
    p.frame.x, p.frame.y, p.frame.w, p.frame.h);
  // marqueurs de sièges (magenta)
  for (const seat of p.asset.seats ?? []) {
    const sx = (p.station.x + seat.dx + MARGIN) * TILE + 14;
    const sy = (p.station.y + seat.dy + MARGIN) * TILE + 14;
    for (let j = 0; j < 5; j++) for (let i = 0; i < 5; i++) {
      const d = ((sy + j) * img.width + sx + i) << 2;
      img.data[d] = 255; img.data[d + 1] = 0; img.data[d + 2] = 200; img.data[d + 3] = 255;
    }
  }
}

fs.writeFileSync(outFile, PNG.sync.write(img));
console.log(`OK → ${outFile} (thème ${theme.id}, ${placed.length} stations)`);
