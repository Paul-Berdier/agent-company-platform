/**
 * Génère les assets placeholders ORIGINAUX des packs (personnages 32×48,
 * meubles, effets, tilesets 32×32, atlas JSON, tilemap Tiled de démo et
 * manifests) dans apps/web/public/assets/.
 *
 * Tous les dessins sont produits par ce script (aucun asset tiers).
 * Remplacer un placeholder = déposer un PNG/JSON du même nom.
 *
 * Usage : npm run generate-placeholders -w @acp/pixel-office-engine
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, "..", "..", "..", "apps", "web", "public", "assets");

// ----------------------------------------------------------------- image lib

class Img {
  constructor(w, h) {
    this.png = new PNG({ width: w, height: h });
    this.w = w;
    this.h = h;
  }
  px(x, y, [r, g, b, a = 255]) {
    if (x < 0 || y < 0 || x >= this.w || y >= this.h) return;
    const i = (this.w * y + x) << 2;
    this.png.data[i] = r; this.png.data[i + 1] = g;
    this.png.data[i + 2] = b; this.png.data[i + 3] = a;
  }
  fill(x, y, w, h, c) {
    for (let j = y; j < y + h; j++) for (let i = x; i < x + w; i++) this.px(i, j, c);
  }
  save(file) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, PNG.sync.write(this.png));
  }
}

const hex = (s) => [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16), parseInt(s.slice(5, 7), 16), 255];
const shade = ([r, g, b], f) => [Math.max(0, Math.min(255, r * f | 0)), Math.max(0, Math.min(255, g * f | 0)), Math.max(0, Math.min(255, b * f | 0)), 255];

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

// --------------------------------------------------------------- personnages

const CHAR_W = 32, CHAR_H = 48;

/** Dessine une frame de personnage 32×48 à (ox, oy). */
function drawCharacterFrame(img, ox, oy, pal, anim, f) {
  const skin = hex(pal.skin), hair = hex(pal.hair), shirt = hex(pal.shirt);
  const pants = hex(pal.pants), dark = [30, 34, 42, 255];
  const bob = anim.startsWith("walk") ? 0 : (f % 2); // respiration
  const y = (dy) => oy + dy + bob;
  const sit = anim === "sit";
  const up = anim === "walk-up";
  const side = anim === "walk-left" || anim === "walk-right";
  const mirror = anim === "walk-right";
  const X = (dx) => ox + (mirror ? 31 - dx : dx);
  const fillM = (x0, dy, w, h, c) => {
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) img.px(X(x0 + i), y(dy) + j, c);
  };

  const bodyTop = sit ? 20 : 16;

  // cheveux + tête
  fillM(10, 2, 12, 5, hair);
  fillM(9, 4, 2, 4, hair);
  fillM(21, 4, 2, 4, hair);
  fillM(10, 7, 12, 7, up ? hair : skin);
  if (!up) {
    if (side) {
      img.px(X(13), y(10), dark);
    } else {
      img.px(X(13), y(10), dark);
      img.px(X(18), y(10), dark);
      if (anim === "idle-down" && f === 3) { /* clignement : pas d'yeux */
        img.px(X(13), y(10), skin); img.px(X(18), y(10), skin);
      }
    }
  }

  // corps
  const bw = side ? 12 : 16;
  const bx = side ? 10 : 8;
  fillM(bx, bodyTop, bw, 14, shirt);
  fillM(bx, bodyTop + 12, bw, 2, shade(shirt, 0.8));

  // bras
  if (anim === "type") {
    // mains en avant sur le clavier, alternance
    fillM(6, bodyTop + 1, 2, 8, shirt);
    fillM(24, bodyTop + 1, 2, 8, shirt);
    const lift = f % 2;
    fillM(7, bodyTop + 9 - lift, 3, 2, skin);
    fillM(22, bodyTop + 9 + lift - 1, 3, 2, skin);
  } else if (anim === "think") {
    fillM(6, bodyTop + 1, 2, 10, shirt);
    fillM(6, bodyTop + 11, 2, 2, skin);
    fillM(24, bodyTop - 3 - f, 2, 5, shirt); // bras levé
    fillM(24, bodyTop - 5 - f, 2, 2, skin);
  } else if (side) {
    const swing = anim.startsWith("walk") ? (f % 2 === 0 ? 1 : -1) : 0;
    fillM(14, bodyTop + 1 + swing, 3, 9, shade(shirt, 0.85));
    fillM(14, bodyTop + 10 + swing, 3, 2, skin);
  } else {
    const swing = anim.startsWith("walk") ? (f % 2 === 0 ? 1 : -1) : 0;
    fillM(6, bodyTop + 1 + swing, 2, 9, shirt);
    fillM(6, bodyTop + 10 + swing, 2, 2, skin);
    fillM(24, bodyTop + 1 - swing, 2, 9, shirt);
    fillM(24, bodyTop + 10 - swing, 2, 2, skin);
  }

  // jambes + chaussures
  if (sit) {
    fillM(10, 34, 12, 4, pants);
    fillM(10, 38, 14, 3, pants); // cuisses vers l'avant
    fillM(22, 41, 4, 3, dark);
    fillM(10, 41, 4, 3, dark);
  } else {
    const stepL = anim.startsWith("walk") ? (f % 4 < 2 ? 0 : 2) : 0;
    const stepR = anim.startsWith("walk") ? (f % 4 < 2 ? 2 : 0) : 0;
    fillM(10, 30, 5, 11 - stepL, pants);
    fillM(17, 30, 5, 11 - stepR, pants);
    fillM(10, 41 - stepL, 5, 3, dark);
    fillM(17, 41 - stepR, 5, 3, dark);
  }
}

const ANIMS = {
  "idle-down": 4,
  "walk-down": 4,
  "walk-up": 4,
  "walk-left": 4,
  "walk-right": 4,
  "type": 4,
  "think": 2,
  "sit": 2,
};

function characterAnimationsManifest() {
  const out = {};
  for (const [name, count] of Object.entries(ANIMS)) {
    out[name] = {
      frames: `{CHAR}/${name}/{0..${count - 1}}`,
      frameRate: name.startsWith("walk") ? 8 : name === "type" ? 6 : name === "idle-down" ? 3 : 2,
      repeat: -1,
    };
  }
  return out;
}

/** Génère un atlas PNG+JSON contenant plusieurs personnages. */
function generateCharacterAtlas(dir, atlasId, characters) {
  const totalFrames = Object.values(ANIMS).reduce((a, b) => a + b, 0);
  const cols = 8;
  const rowsPerChar = Math.ceil(totalFrames / cols);
  const img = new Img(cols * CHAR_W, characters.length * rowsPerChar * CHAR_H);
  const frames = {};
  characters.forEach((ch, ci) => {
    let index = 0;
    for (const [anim, count] of Object.entries(ANIMS)) {
      for (let f = 0; f < count; f++) {
        const col = index % cols;
        const row = Math.floor(index / cols) + ci * rowsPerChar;
        const x = col * CHAR_W, y = row * CHAR_H;
        drawCharacterFrame(img, x, y, ch.palette, anim, f);
        frames[`${ch.id}/${anim}/${f}`] = {
          frame: { x, y, w: CHAR_W, h: CHAR_H },
          rotated: false, trimmed: false,
          sourceSize: { w: CHAR_W, h: CHAR_H },
          spriteSourceSize: { x: 0, y: 0, w: CHAR_W, h: CHAR_H },
        };
        index++;
      }
    }
  });
  img.save(path.join(dir, "atlases", `${atlasId}.png`));
  writeJson(path.join(dir, "atlases", `${atlasId}.json`), {
    frames,
    meta: { image: `${atlasId}.png`, size: { w: img.w, h: img.h }, scale: "1" },
  });
}

// ------------------------------------------------------------------- meubles

function drawDesk(img, x, y) {
  img.fill(x, y + 10, 64, 18, hex("#8a6a4b"));       // plateau
  img.fill(x, y + 10, 64, 2, hex("#a58562"));
  img.fill(x + 4, y + 28, 4, 4, hex("#5f4732"));     // pieds
  img.fill(x + 56, y + 28, 4, 4, hex("#5f4732"));
  img.fill(x + 22, y, 20, 12, hex("#1d2733"));       // écran
  img.fill(x + 24, y + 2, 16, 8, hex("#3fa7d6"));
  img.fill(x + 30, y + 12, 4, 2, hex("#1d2733"));    // pied écran
  img.fill(x + 8, y + 14, 14, 6, hex("#2c333f"));    // clavier
}
function drawDeskFront(img, x, y) {
  img.fill(x, y, 64, 6, hex("#75593e"));             // bord avant du plateau
  img.fill(x, y, 64, 1, hex("#8a6a4b"));
}
function drawWhiteboard(img, x, y) {
  img.fill(x, y, 64, 30, hex("#f5f5f5"));
  img.fill(x, y, 64, 2, hex("#9aa0a6"));
  img.fill(x, y + 28, 64, 2, hex("#9aa0a6"));
  img.fill(x + 6, y + 6, 30, 3, hex("#e63946"));
  img.fill(x + 6, y + 13, 42, 3, hex("#457b9d"));
  img.fill(x + 6, y + 20, 22, 3, hex("#2a9d8f"));
}
function drawServerRack(img, x, y) {
  img.fill(x + 2, y, 28, 62, hex("#333a45"));
  img.fill(x + 2, y, 28, 2, hex("#454e5c"));
  for (let k = 0; k < 5; k++) {
    img.fill(x + 5, y + 5 + k * 12, 22, 8, hex("#222831"));
    img.px(x + 7, y + 7 + k * 12, hex(k % 2 ? "#ffbe0b" : "#57e389"));
    img.px(x + 10, y + 7 + k * 12, hex("#57e389"));
  }
}
function drawBookshelf(img, x, y) {
  img.fill(x, y, 64, 46, hex("#6d4c33"));
  const books = ["#c0392b", "#2980b9", "#27ae60", "#f39c12", "#8e44ad", "#16a085"];
  for (let row = 0; row < 2; row++) {
    img.fill(x + 3, y + 4 + row * 21, 58, 16, hex("#4e3624"));
    for (let k = 0; k < 9; k++) {
      img.fill(x + 5 + k * 6, y + 6 + row * 21, 5, 12, hex(books[(k + row) % books.length]));
    }
  }
}
function drawCouch(img, x, y) {
  img.fill(x + 2, y + 8, 60, 18, hex("#b3542e"));
  img.fill(x + 2, y + 8, 60, 4, hex("#c96a42"));
  img.fill(x, y, 8, 26, hex("#8f4021"));
  img.fill(x + 56, y, 8, 26, hex("#8f4021"));
  img.fill(x + 2, y + 26, 60, 4, hex("#6e2f16"));
}
function drawArtStation(img, x, y) {
  img.fill(x + 6, y + 40, 3, 6, hex("#8d6e63"));   // pieds chevalet
  img.fill(x + 23, y + 40, 3, 6, hex("#8d6e63"));
  img.fill(x + 14, y + 42, 3, 6, hex("#8d6e63"));
  img.fill(x + 4, y + 4, 24, 36, hex("#fffdf5"));  // toile
  img.fill(x + 4, y + 4, 24, 1, hex("#c9c2b0"));
  img.fill(x + 8, y + 10, 10, 8, hex("#9b5de5"));  // esquisse
  img.fill(x + 14, y + 22, 10, 8, hex("#f4845f"));
}

function generateFurnitureAtlas(dir) {
  const img = new Img(256, 128);
  const frames = {};
  const add = (name, x, y, w, h, draw) => {
    draw(img, x, y);
    frames[name] = {
      frame: { x, y, w, h }, rotated: false, trimmed: false,
      sourceSize: { w, h }, spriteSourceSize: { x: 0, y: 0, w, h },
    };
  };
  add("desk/back", 0, 0, 64, 32, drawDesk);
  add("desk/front", 0, 36, 64, 6, drawDeskFront);
  add("whiteboard/back", 70, 0, 64, 30, drawWhiteboard);
  add("server-rack/back", 140, 0, 32, 62, drawServerRack);
  add("bookshelf/back", 180, 0, 64, 46, drawBookshelf);
  add("couch/back", 0, 48, 64, 30, drawCouch);
  add("art-station/back", 70, 40, 32, 48, drawArtStation);
  img.save(path.join(dir, "atlases", "furniture-core.png"));
  writeJson(path.join(dir, "atlases", "furniture-core.json"), {
    frames,
    meta: { image: "furniture-core.png", size: { w: img.w, h: img.h }, scale: "1" },
  });
}

// -------------------------------------------------------------------- effets

function generateFxAtlas(dir) {
  const img = new Img(128, 48);
  const frames = {};
  const add = (name, x, y, w, h) => {
    frames[name] = {
      frame: { x, y, w, h }, rotated: false, trimmed: false,
      sourceSize: { w, h }, spriteSourceSize: { x: 0, y: 0, w, h },
    };
  };
  // engrenage (task-progress) : carré tournant
  for (let f = 0; f < 4; f++) {
    const x = f * 16, y = 0, c = hex("#e9c46a");
    img.fill(x + 5, y + 5, 6, 6, c);
    if (f % 2 === 0) {
      img.fill(x + 7, y + 1, 2, 4, c); img.fill(x + 7, y + 11, 2, 4, c);
      img.fill(x + 1, y + 7, 4, 2, c); img.fill(x + 11, y + 7, 4, 2, c);
    } else {
      img.fill(x + 2, y + 2, 3, 3, c); img.fill(x + 11, y + 2, 3, 3, c);
      img.fill(x + 2, y + 11, 3, 3, c); img.fill(x + 11, y + 11, 3, 3, c);
    }
    img.fill(x + 7, y + 7, 2, 2, hex("#7a5c00"));
    add(`fx/gear/${f}`, x, y, 16, 16);
  }
  // coche (task-complete) : trait qui se dessine
  for (let f = 0; f < 4; f++) {
    const x = 64 + f * 16, y = 0, c = hex("#57cc99");
    const steps = [[3, 9], [5, 11], [7, 13], [9, 11], [11, 9], [13, 7], [13, 5]];
    for (let s = 0; s <= Math.min(f * 2 + 1, steps.length - 1); s++) {
      img.fill(x + steps[s][0], y + steps[s][1] - 2, 2, 2, c);
    }
    add(`fx/check/${f}`, x, y, 16, 16);
  }
  // croix (task-failed)
  for (let f = 0; f < 4; f++) {
    const x = f * 16, y = 16, c = hex("#e63946");
    const len = 3 + f * 2;
    for (let s = 0; s < len && s < 10; s++) {
      img.fill(x + 3 + s, y + 3 + s, 2, 2, c);
      img.fill(x + 11 - s, y + 3 + s, 2, 2, c);
    }
    add(`fx/cross/${f}`, x, y, 16, 16);
  }
  // pulse (salle active) : anneau qui s'étend
  for (let f = 0; f < 4; f++) {
    const x = 64 + f * 16, y = 16, c = [91, 130, 102, 255 - f * 50];
    const r = 2 + f * 2;
    img.fill(x + 8 - r, y + 8 - r, r * 2, 1, c);
    img.fill(x + 8 - r, y + 8 + r - 1, r * 2, 1, c);
    img.fill(x + 8 - r, y + 8 - r, 1, r * 2, c);
    img.fill(x + 8 + r - 1, y + 8 - r, 1, r * 2, c);
    add(`fx/pulse/${f}`, x, y, 16, 16);
  }
  img.save(path.join(dir, "atlases", "fx-core.png"));
  writeJson(path.join(dir, "atlases", "fx-core.json"), {
    frames,
    meta: { image: "fx-core.png", size: { w: img.w, h: img.h }, scale: "1" },
  });
}

// ------------------------------------------------------------------ tilesets

/** Tuile de sol avec bord subtil et mouchetis déterministe. */
function drawFloorTile(img, x, y, base) {
  const b = hex(base);
  img.fill(x, y, 32, 32, b);
  img.fill(x, y, 32, 1, shade(b, 1.08));
  img.fill(x, y + 31, 32, 1, shade(b, 0.92));
  img.fill(x, y, 1, 32, shade(b, 1.05));
  img.fill(x + 31, y, 1, 32, shade(b, 0.95));
  let seed = x * 7 + y * 13 + 5;
  for (let k = 0; k < 6; k++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    img.px(x + (seed % 30) + 1, y + ((seed >> 8) % 30) + 1, shade(b, 0.9));
  }
}

function drawWallTile(img, x, y, base) {
  const b = hex(base);
  img.fill(x, y, 32, 32, b);
  img.fill(x, y, 32, 6, shade(b, 1.25));      // chapeau du mur
  img.fill(x, y + 6, 32, 1, shade(b, 0.7));
  for (let row = 0; row < 3; row++) {          // joints de briques
    img.fill(x, y + 12 + row * 7, 32, 1, shade(b, 0.85));
    img.fill(x + (row % 2 ? 8 : 20), y + 7 + row * 7, 1, 6, shade(b, 0.85));
  }
}

function generateTileset(dir, file, floors, wall) {
  const tiles = [...floors, wall];
  const img = new Img(tiles.length * 32, 32);
  floors.forEach((c, i) => drawFloorTile(img, i * 32, 0, c));
  drawWallTile(img, floors.length * 32, 0, wall);
  img.save(path.join(dir, "tilesets", file));
  return { columns: tiles.length, count: tiles.length };
}

// -------------------------------------------------------------- tilemap démo

function generateDemoTilemap(dir) {
  const W = 24, H = 16;
  const floor = [], walls = [], collision = [];
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      floor.push(((x + y) % 2) + 1); // gid 1..2 (damier)
      const isWall = y === 0 || y === H - 1 || x === 0 || x === W - 1
        || (x === 12 && y < 6); // une cloison de démo
      walls.push(isWall ? 3 : 0); // gid 3 = mur
      collision.push(isWall ? 3 : 0);
    }
  }
  const layer = (id, name, data) => ({
    data, height: H, width: W, id, name, opacity: 1,
    type: "tilelayer", visible: true, x: 0, y: 0,
  });
  writeJson(path.join(dir, "tilemaps", "demo-office.tmj"), {
    compressionlevel: -1,
    height: H, width: W, infinite: false,
    layers: [layer(1, "floor", floor), layer(2, "walls", walls), layer(3, "collision", collision)],
    nextlayerid: 4, nextobjectid: 1,
    orientation: "orthogonal", renderorder: "right-down",
    tiledversion: "1.10.2", type: "map", version: "1.10",
    tilewidth: 32, tileheight: 32,
    tilesets: [{
      firstgid: 1, name: "office-base", image: "../tilesets/office-base.png",
      imagewidth: 96, imageheight: 32, tilewidth: 32, tileheight: 32,
      columns: 3, tilecount: 3, margin: 0, spacing: 0,
    }],
  });
}

// ----------------------------------------------------------------- manifests

const STATIONS = [
  { kind: "desk", id: "desk-core", frames: { back: "desk/back", front: "desk/front" },
    footprint: { w: 2, h: 1 }, seats: [{ dx: 1, dy: 1, facing: "up" }] },
  { kind: "whiteboard", id: "whiteboard-core", frames: { back: "whiteboard/back" },
    footprint: { w: 2, h: 1 }, seats: [{ dx: 1, dy: 1, facing: "up" }] },
  { kind: "server-rack", id: "server-rack-core", frames: { back: "server-rack/back" },
    footprint: { w: 1, h: 2 }, seats: [{ dx: 0, dy: 2, facing: "up" }] },
  { kind: "bookshelf", id: "bookshelf-core", frames: { back: "bookshelf/back" },
    footprint: { w: 2, h: 2 }, seats: [{ dx: 1, dy: 2, facing: "up" }] },
  { kind: "couch", id: "couch-core", frames: { back: "couch/back" },
    footprint: { w: 2, h: 1 }, seats: [{ dx: 0, dy: 1, facing: "down" }, { dx: 1, dy: 1, facing: "down" }] },
  { kind: "art-station", id: "art-station-core", frames: { back: "art-station/back" },
    footprint: { w: 1, h: 2 }, seats: [{ dx: 0, dy: 2, facing: "up" }] },
].map((s) => ({ ...s, atlas: "furniture-core", pivot: { x: 0, y: 0 }, blocking: true }));

const ALIASES = {
  walk: "walk-down", coffee: "idle-down", read: "sit", write: "type",
  chart: "type", draw: "type", play: "type", point: "think", away: "sit",
};

const EFFECTS = [
  { id: "task-progress", animation: { frames: "fx/gear/{0..3}", frameRate: 8, repeat: -1 } },
  { id: "task-complete", animation: { frames: "fx/check/{0..3}", frameRate: 10, repeat: 0 } },
  { id: "task-failed", animation: { frames: "fx/cross/{0..3}", frameRate: 10, repeat: 0 } },
  { id: "room-pulse", animation: { frames: "fx/pulse/{0..3}", frameRate: 10, repeat: 2 } },
].map((e) => ({ ...e, atlas: "fx-core" }));

function charManifest(id, atlas) {
  const animations = {};
  for (const [name, def] of Object.entries(characterAnimationsManifest())) {
    animations[name] = { ...def, frames: def.frames.replace("{CHAR}", id) };
  }
  return { id, atlas, size: { w: 32, h: 48 }, pivot: { x: 0.5, y: 0.9 }, animations };
}

const PACKS = [
  {
    id: "core", dir: "core",
    characters: [
      { id: "worker-a", palette: { skin: "#f2c9a0", hair: "#5b3a29", shirt: "#457b9d", pants: "#2c3e50" } },
      { id: "worker-b", palette: { skin: "#c68642", hair: "#2f2f2f", shirt: "#2a9d8f", pants: "#3a3f4b" } },
      { id: "worker-c", palette: { skin: "#f8d5b8", hair: "#a86b32", shirt: "#e76f51", pants: "#4a4e57" } },
    ],
    atlasId: "characters-core",
    tileset: { id: "office-base", file: "office-base.png", floors: ["#cfc4a5", "#c2b492"], wall: "#7a6a52" },
    theme: { id: "default", accentColor: "#5b8266" },
    roles: { "*": ["worker-a", "worker-b", "worker-c"] },
    hasFurniture: true, hasFx: true, hasTilemap: true,
  },
  {
    id: "dept-software-engineering", dir: "dept-software-engineering", extends: "core",
    characters: [{ id: "dev-a", palette: { skin: "#e0ac69", hair: "#2f2f2f", shirt: "#2b6cb0", pants: "#1f2733" } }],
    atlasId: "characters-dev",
    tileset: { id: "floors-dev", file: "floors-dev.png", floors: ["#a7bcc9", "#98aebc"], wall: "#4f6d7a" },
    theme: { id: "dev-floor", accentColor: "#2b6cb0" },
    roles: {
      "frontend-developer": ["dev-a", "worker-a"],
      "backend-developer": ["dev-a", "worker-b"],
      "qa-engineer": ["worker-c"],
      "tech-lead": ["dev-a"],
    },
  },
  {
    id: "dept-data-science", dir: "dept-data-science", extends: "core",
    characters: [{ id: "data-a", palette: { skin: "#f2c9a0", hair: "#8c8c8c", shirt: "#2f9e8f", pants: "#33424d" } }],
    atlasId: "characters-data",
    tileset: { id: "floors-data", file: "floors-data.png", floors: ["#bcc9c0", "#aebcb2"], wall: "#52796f" },
    theme: { id: "data-lab", accentColor: "#2f9e8f" },
    roles: {
      "data-engineer": ["data-a", "worker-b"],
      "data-scientist": ["data-a", "worker-a"],
      "ml-engineer": ["data-a"],
    },
  },
  {
    id: "dept-research", dir: "dept-research", extends: "core",
    characters: [{ id: "res-a", palette: { skin: "#e0ac69", hair: "#d9b380", shirt: "#8a5a44", pants: "#3d3630" } }],
    atlasId: "characters-research",
    tileset: { id: "floors-research", file: "floors-research.png", floors: ["#d8bd8f", "#cbb080"], wall: "#8a5a44" },
    theme: { id: "library", accentColor: "#a0522d" },
    roles: {
      "researcher": ["res-a", "worker-a"],
      "research-assistant": ["res-a", "worker-c"],
    },
  },
  {
    id: "dept-game-development", dir: "dept-game-development", extends: "core",
    characters: [{ id: "game-a", palette: { skin: "#f8d5b8", hair: "#3a5a8c", shirt: "#9b5de5", pants: "#2d2540" } }],
    atlasId: "characters-game",
    tileset: { id: "floors-game", file: "floors-game.png", floors: ["#b5a3d6", "#a794ca"], wall: "#5e35b1" },
    theme: { id: "game-studio", accentColor: "#ff7043" },
    roles: {
      "game-designer": ["game-a", "worker-a"],
      "gameplay-programmer": ["game-a", "worker-b"],
      "3d-artist": ["game-a"],
      "build-engineer": ["worker-b"],
    },
  },
];

function generatePack(pack) {
  const dir = path.join(OUT, pack.dir);
  generateCharacterAtlas(dir, pack.atlasId, pack.characters);
  const ts = generateTileset(dir, pack.tileset.file, pack.tileset.floors, pack.tileset.wall);
  if (pack.hasFurniture) generateFurnitureAtlas(dir);
  if (pack.hasFx) generateFxAtlas(dir);
  if (pack.hasTilemap) generateDemoTilemap(dir);

  const manifest = {
    manifest_version: "1.0",
    pack_id: pack.id,
    ...(pack.extends ? { extends: pack.extends } : {}),
    grid: { tile: 32, character: { w: 32, h: 48 } },
    atlases: [
      { id: pack.atlasId, image: `atlases/${pack.atlasId}.png`, data: `atlases/${pack.atlasId}.json` },
      ...(pack.hasFurniture ? [{ id: "furniture-core", image: "atlases/furniture-core.png", data: "atlases/furniture-core.json" }] : []),
      ...(pack.hasFx ? [{ id: "fx-core", image: "atlases/fx-core.png", data: "atlases/fx-core.json" }] : []),
    ],
    tilesets: [{
      id: pack.tileset.id, image: `tilesets/${pack.tileset.file}`,
      tile: 32, margin: 0, spacing: 0, columns: ts.columns,
    }],
    tilemaps: pack.hasTilemap
      ? [{ id: "demo-office", file: "tilemaps/demo-office.tmj", format: "tiled-json" }]
      : [],
    characters: pack.characters.map((c) => charManifest(c.id, pack.atlasId)),
    stations: pack.hasFurniture ? STATIONS : [],
    themes: [{
      id: pack.theme.id, tileset: pack.tileset.id,
      floorTiles: [0, 1], wallTiles: [2], accentColor: pack.theme.accentColor,
    }],
    effects: pack.hasFx ? EFFECTS : [],
    role_characters: pack.roles,
    animation_aliases: ALIASES,
  };
  writeJson(path.join(dir, "manifest.json"), manifest);
}

// ---------------------------------------------------------------------- main

for (const pack of PACKS) generatePack(pack);

writeJson(path.join(OUT, "packs.json"), {
  packs: Object.fromEntries(PACKS.map((p) => [p.id, p.dir])),
  department_packs: {
    "software-engineering": "dept-software-engineering",
    "data-science": "dept-data-science",
    "research": "dept-research",
    "game-development": "dept-game-development",
    "*": "core",
  },
});

console.log(`Placeholders générés dans ${OUT}`);
