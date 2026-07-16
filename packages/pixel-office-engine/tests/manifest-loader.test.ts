import { describe, expect, it } from "vitest";

import {
  loadAssetPacks,
  ManifestError,
  resolveCharacter,
  resolveStationAsset,
  resolveTheme,
  validateManifest,
  type FetchJson,
} from "../src/phaser/assets/manifest-loader";

const VALID_CORE = {
  manifest_version: "1.0",
  pack_id: "core",
  grid: { tile: 32, character: { w: 32, h: 48 } },
  atlases: [{ id: "chars", image: "atlases/chars.png", data: "atlases/chars.json" }],
  tilesets: [{ id: "base", image: "tilesets/base.png", tile: 32, columns: 3 }],
  tilemaps: [],
  characters: [
    {
      id: "worker-a", atlas: "chars", size: { w: 32, h: 48 }, pivot: { x: 0.5, y: 0.9 },
      animations: { "idle-down": { frames: "worker-a/idle-down/{0..3}", frameRate: 3, repeat: -1 } },
    },
  ],
  stations: [
    {
      kind: "desk", id: "desk-core", atlas: "furn", frames: { back: "desk/back" },
      footprint: { w: 2, h: 1 }, pivot: { x: 0, y: 0 },
      seats: [{ dx: 1, dy: 1, facing: "up" }],
    },
  ],
  themes: [{ id: "default", tileset: "base", floorTiles: [0, 1], wallTiles: [2], accentColor: "#5b8266" }],
  effects: [],
  role_characters: { "*": ["worker-a"] },
  animation_aliases: { coffee: "idle-down" },
};

const VALID_CHILD = {
  manifest_version: "1.0",
  pack_id: "dept-x",
  extends: "core",
  grid: { tile: 32, character: { w: 32, h: 48 } },
  atlases: [{ id: "chars-x", image: "atlases/chars-x.png", data: "atlases/chars-x.json" }],
  tilesets: [{ id: "floors-x", image: "tilesets/floors-x.png", tile: 32, columns: 3 }],
  tilemaps: [],
  characters: [
    {
      id: "x-a", atlas: "chars-x", size: { w: 32, h: 48 }, pivot: { x: 0.5, y: 0.9 },
      animations: { "idle-down": { frames: "x-a/idle-down/{0..3}", frameRate: 3, repeat: -1 } },
    },
  ],
  stations: [
    {
      kind: "desk", id: "desk-x", atlas: "furn-x", frames: { back: "desk-x/back" },
      footprint: { w: 2, h: 1 }, pivot: { x: 0, y: 0 },
      seats: [{ dx: 1, dy: 1, facing: "up" }],
    },
  ],
  themes: [{ id: "theme-x", tileset: "floors-x", floorTiles: [0], wallTiles: [2], accentColor: "#123456" }],
  effects: [],
  role_characters: { "role-x": ["x-a"] },
  animation_aliases: {},
};

function fakeFetch(files: Record<string, unknown>): FetchJson {
  return async (url: string) => {
    if (url in files) return structuredClone(files[url]);
    throw new ManifestError(`404 ${url}`);
  };
}

const FILES = {
  "/assets/packs.json": {
    packs: { core: "core", "dept-x": "dept-x" },
    department_packs: { x: "dept-x", "*": "core" },
  },
  "/assets/core/manifest.json": VALID_CORE,
  "/assets/dept-x/manifest.json": VALID_CHILD,
};

describe("validateManifest", () => {
  it("accepte un manifest valide", () => {
    const m = validateManifest(structuredClone(VALID_CORE));
    expect(m.pack_id).toBe("core");
    expect(m.characters).toHaveLength(1);
  });

  it("refuse un pack_id manquant", () => {
    const bad = { ...structuredClone(VALID_CORE), pack_id: undefined };
    expect(() => validateManifest(bad)).toThrow(/pack_id/);
  });

  it("refuse une version inconnue", () => {
    const bad = { ...structuredClone(VALID_CORE), manifest_version: "2.0" };
    expect(() => validateManifest(bad)).toThrow(/manifest_version/);
  });

  it("refuse une grille différente de 32", () => {
    const bad = structuredClone(VALID_CORE);
    bad.grid.tile = 16;
    expect(() => validateManifest(bad)).toThrow(/grid.tile/);
  });

  it("refuse un personnage sans animations", () => {
    const bad = structuredClone(VALID_CORE);
    bad.characters[0].animations = {};
    expect(() => validateManifest(bad)).toThrow(/sans animations/);
  });

  it("refuse une station sans frame back", () => {
    const bad = structuredClone(VALID_CORE);
    // @ts-expect-error test de validation
    bad.stations[0].frames = {};
    expect(() => validateManifest(bad)).toThrow(/frame back/);
  });
});

describe("loadAssetPacks", () => {
  it("charge core implicitement et fusionne le pack enfant", async () => {
    const assets = await loadAssetPacks({
      baseUrl: "/assets", packIds: ["dept-x"], fetchJson: fakeFetch(FILES),
    });
    expect(assets.packs.map((p) => p.pack_id)).toEqual(["core", "dept-x"]);
    // fusion : personnages des deux packs, station desk écrasée par l'enfant
    expect(assets.characters.has("worker-a")).toBe(true);
    expect(assets.characters.has("x-a")).toBe(true);
    expect(assets.stationsByKind.get("desk")?.id).toBe("desk-x");
    expect(assets.themes.has("default")).toBe(true);
    expect(assets.themes.has("theme-x")).toBe(true);
    // rôles fusionnés, alias hérités
    expect(assets.roleCharacters["role-x"]).toEqual(["x-a"]);
    expect(assets.animationAliases["coffee"]).toBe("idle-down");
  });

  it("résout les URLs relativement au dossier du pack", async () => {
    const assets = await loadAssetPacks({
      baseUrl: "/assets", packIds: [], fetchJson: fakeFetch(FILES),
    });
    expect(assets.atlases[0].urls.image).toBe("/assets/core/atlases/chars.png");
    expect(assets.tilesets[0].urls.image).toBe("/assets/core/tilesets/base.png");
  });

  it("échoue clairement sur un pack inconnu", async () => {
    await expect(loadAssetPacks({
      baseUrl: "/assets", packIds: ["inconnu"], fetchJson: fakeFetch(FILES),
    })).rejects.toThrow(/pack inconnu/);
  });

  it("détecte l'héritage circulaire", async () => {
    const files = structuredClone(FILES) as Record<string, any>;
    files["/assets/core/manifest.json"].extends = "dept-x";
    await expect(loadAssetPacks({
      baseUrl: "/assets", packIds: ["dept-x"], fetchJson: fakeFetch(files),
    })).rejects.toThrow(/circulaire/);
  });
});

describe("résolutions", () => {
  async function assets() {
    return loadAssetPacks({ baseUrl: "/assets", packIds: ["dept-x"], fetchJson: fakeFetch(FILES) });
  }

  it("résout une station par assetId puis par kind puis desk", async () => {
    const a = await assets();
    expect(resolveStationAsset(a, { kind: "desk", assetId: "desk-core" })?.id).toBe("desk-core");
    expect(resolveStationAsset(a, { kind: "desk" })?.id).toBe("desk-x");
    expect(resolveStationAsset(a, { kind: "kind-inconnu" })?.id).toBe("desk-x"); // repli desk
  });

  it("résout un personnage par rôle avec repli * stable", async () => {
    const a = await assets();
    expect(resolveCharacter(a, { role: "role-x", id: "e1" })?.id).toBe("x-a");
    const fallback = resolveCharacter(a, { role: "role-inconnu", id: "e1" });
    expect(fallback?.id).toBe("worker-a"); // pool "*"
    // stabilité : même entité → même personnage
    const again = resolveCharacter(a, { role: "role-inconnu", id: "e1" });
    expect(again?.id).toBe(fallback?.id);
  });

  it("résout un thème par themeId, theme, puis default", async () => {
    const a = await assets();
    expect(resolveTheme(a, { themeId: "theme-x", theme: "default" })?.id).toBe("theme-x");
    expect(resolveTheme(a, { theme: "theme-x" })?.id).toBe("theme-x");
    expect(resolveTheme(a, { theme: "inexistant" })?.id).toBe("default");
  });
});
