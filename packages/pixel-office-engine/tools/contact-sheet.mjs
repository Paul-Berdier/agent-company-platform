/**
 * Planche contact numérotée des frames d'un atlas (outil de curation locale).
 *
 * Usage :
 *   node tools/contact-sheet.mjs <dossier-pack> <atlas-id> <dossier-sortie>
 * Ex :
 *   node tools/contact-sheet.mjs ../../apps/web/public/assets/licensed/limezu/office limezu-office C:/temp/contact
 */

import fs from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";

const [, , packDir, atlasId, outDir] = process.argv;
if (!packDir || !atlasId || !outDir) {
  console.error("Usage: node tools/contact-sheet.mjs <pack-dir> <atlas-id> <out-dir>");
  process.exit(2);
}

const DIGITS = {
  "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
  "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
  "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
  "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
  "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
};

function drawNumber(img, x, y, text) {
  let cx = x;
  for (const ch of text) {
    const glyph = DIGITS[ch];
    if (!glyph) { cx += 4; continue; }
    for (let j = 0; j < 5; j++) {
      for (let i = 0; i < 3; i++) {
        const on = glyph[j][i] === "1";
        const idx = ((y + j) * img.width + cx + i) << 2;
        img.data[idx] = on ? 255 : 0;
        img.data[idx + 1] = on ? 240 : 0;
        img.data[idx + 2] = on ? 60 : 0;
        img.data[idx + 3] = 255;
      }
    }
    cx += 4;
  }
}

function blit(dst, src, dx, dy, sx, sy, w, h) {
  for (let y = 0; y < h; y++) {
    const s = ((sy + y) * src.width + sx) * 4;
    const d = ((dy + y) * dst.width + dx) * 4;
    src.data.copy(dst.data, d, s, s + w * 4);
  }
}

const atlasJson = JSON.parse(
  fs.readFileSync(path.join(packDir, "atlases", `${atlasId}.json`), "utf-8"),
);
const atlasPng = PNG.sync.read(
  fs.readFileSync(path.join(packDir, "atlases", atlasJson.meta.image)),
);
const entries = Object.entries(atlasJson.frames)
  .map(([key, def]) => ({
    num: parseInt(key.match(/(\d+)$/)?.[1] ?? "0", 10),
    key,
    f: def.frame,
  }))
  .sort((a, b) => a.num - b.num);

fs.mkdirSync(outDir, { recursive: true });
const PER_SHEET = 60, COLS = 10, CELL_W = 110, CELL_H = 150;
for (let s = 0; s * PER_SHEET < entries.length; s++) {
  const slice = entries.slice(s * PER_SHEET, (s + 1) * PER_SHEET);
  const rows = Math.ceil(slice.length / COLS);
  const img = new PNG({ width: COLS * CELL_W, height: rows * CELL_H });
  img.data.fill(40);
  slice.forEach((e, i) => {
    const cx = (i % COLS) * CELL_W;
    const cy = Math.floor(i / COLS) * CELL_H;
    const w = Math.min(e.f.w, CELL_W - 8);
    const h = Math.min(e.f.h, CELL_H - 22);
    blit(img, atlasPng, cx + 4, cy + 16, e.f.x, e.f.y, w, h);
    drawNumber(img, cx + 4, cy + 4, String(e.num));
  });
  fs.writeFileSync(path.join(outDir, `${atlasId}-${s + 1}.png`), PNG.sync.write(img));
}
console.log(`OK → ${outDir} (${Math.ceil(entries.length / PER_SHEET)} planches, ${entries.length} frames)`);
