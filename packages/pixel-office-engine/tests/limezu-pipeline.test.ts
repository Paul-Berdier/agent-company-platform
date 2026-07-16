import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// @ts-expect-error module JS pur sans types
import {
  directionalBlocks,
  isPathIgnored,
  logicalSlug,
  shelfPack,
  validateMapping,
} from "../tools/limezu-lib.mjs";
import { loadAssetPacks, type FetchJson } from "../src/phaser/assets/manifest-loader";

const HERE = join(__dirname, "..");

describe("validateMapping", () => {
  const realMapping = JSON.parse(
    readFileSync(join(HERE, "tools", "limezu-mapping.json"), "utf-8"),
  );

  it("accepte le mapping réel committé", () => {
    expect(() => validateMapping(structuredClone(realMapping))).not.toThrow();
  });

  it("refuse une cible hors de licensed/ (anti-redistribution)", () => {
    const bad = structuredClone(realMapping);
    bad.packs["limezu-office"].target_dir = "core/limezu";
    expect(() => validateMapping(bad)).toThrow(/licensed/);
  });

  it("refuse une version inconnue", () => {
    const bad = { ...structuredClone(realMapping), mapping_version: "9.9" };
    expect(() => validateMapping(bad)).toThrow(/mapping_version/);
  });
});

describe("isPathIgnored (contre le vrai .gitignore du dépôt)", () => {
  const gitignore = readFileSync(join(HERE, "..", "..", ".gitignore"), "utf-8");

  it("ignore toutes les cibles d'import sous licence", () => {
    expect(isPathIgnored(gitignore, "apps/web/public/assets/licensed/limezu/x.png")).toBe(true);
    expect(isPathIgnored(gitignore, "Limzu/pack.zip")).toBe(true);
    expect(isPathIgnored(gitignore, "local-assets/a.png")).toBe(true);
    expect(isPathIgnored(gitignore, "art/source.aseprite")).toBe(true);
  });

  it("n'ignore pas les placeholders libres", () => {
    expect(isPathIgnored(gitignore, "apps/web/public/assets/core/manifest.json")).toBe(false);
  });
});

describe("shelfPack", () => {
  it("place sans chevauchement et respecte la taille max", () => {
    const items = Array.from({ length: 30 }, (_, i) => ({ key: `k${i}`, w: 500, h: 300 }));
    const sheets = shelfPack(items, 2048);
    for (const sheet of sheets) {
      expect(sheet.width).toBeLessThanOrEqual(2048);
      expect(sheet.height).toBeLessThanOrEqual(2048);
      // pas de chevauchement
      for (let a = 0; a < sheet.items.length; a++) {
        for (let b = a + 1; b < sheet.items.length; b++) {
          const A = sheet.items[a], B = sheet.items[b];
          const overlap = A.x < B.x + B.w && B.x < A.x + A.w && A.y < B.y + B.h && B.y < A.y + A.h;
          expect(overlap).toBe(false);
        }
      }
    }
    expect(sheets.flatMap((s) => s.items)).toHaveLength(30);
  });

  it("rejette un élément plus grand que la feuille", () => {
    expect(() => shelfPack([{ key: "huge", w: 4000, h: 10 }], 2048)).toThrow(/dépasse/);
  });
});

describe("directionalBlocks", () => {
  it("découpe 24 frames en 4 directions LimeZu", () => {
    const blocks = directionalBlocks(24);
    expect(blocks.right).toEqual([0, 1, 2, 3, 4, 5]);
    expect(blocks.down).toEqual([18, 19, 20, 21, 22, 23]);
  });

  it("retourne null si non divisible par 4", () => {
    expect(directionalBlocks(9)).toBeNull();
  });
});

describe("logicalSlug", () => {
  it("normalise les noms de fichiers fournisseurs", () => {
    expect(logicalSlug("ME_Singles_Camping_32x32_Tree_1.png")).toBe("me-singles-camping-tree-1");
    expect(logicalSlug("Modern_UI_Style_1.png")).toBe("modern-ui-style-1");
  });
});

describe("packs facultatifs (assets sous licence absents)", () => {
  const CORE = {
    manifest_version: "1.0", pack_id: "core",
    grid: { tile: 32, character: { w: 32, h: 48 } },
    atlases: [], tilesets: [], tilemaps: [],
    characters: [{
      id: "w", atlas: "a", size: { w: 32, h: 48 }, pivot: { x: 0.5, y: 0.9 },
      animations: { "idle-down": { frames: "w/idle-down/0", frameRate: 1, repeat: -1 } },
    }],
    stations: [], themes: [], effects: [], role_characters: {}, animation_aliases: {},
  };
  const LIMEZU = {
    ...structuredClone(CORE), pack_id: "limezu-characters", extends: "core",
    grid: { tile: 32, character: { w: 32, h: 64 } },
    characters: [{
      id: "limezu-adam", atlas: "lz", size: { w: 32, h: 64 }, pivot: { x: 0.5, y: 0.95 },
      animations: { "idle-down": { frames: "adam/idle-down/{0..5}", frameRate: 4, repeat: -1 } },
    }],
  };

  function fetcher(withLicensed: boolean): FetchJson {
    return async (url: string) => {
      if (url.endsWith("/packs.json")) {
        return {
          packs: { core: "core" },
          optional_packs: { "limezu-characters": "licensed/limezu/characters" },
          department_packs: {},
        };
      }
      if (url.includes("/core/")) return structuredClone(CORE);
      if (url.includes("/licensed/") && withLicensed) return structuredClone(LIMEZU);
      throw new Error(`404 ${url}`);
    };
  }

  it("absents : app fonctionnelle, pack signalé manquant", async () => {
    const assets = await loadAssetPacks({ baseUrl: "/assets", packIds: [], fetchJson: fetcher(false) });
    expect(assets.missingPacks).toEqual(["limezu-characters"]);
    expect(assets.characters.has("w")).toBe(true);
  });

  it("présents : personnages 32×64 chargés et fusionnés", async () => {
    const assets = await loadAssetPacks({ baseUrl: "/assets", packIds: [], fetchJson: fetcher(true) });
    expect(assets.missingPacks).toEqual([]);
    expect(assets.characters.has("limezu-adam")).toBe(true);
    expect(assets.characters.get("limezu-adam")?.size.h).toBe(64);
  });
});
