/**
 * Chargement et fusion des packs d'assets.
 *
 * Module pur (aucun import Phaser) : la validation et la fusion sont testées
 * en Node. Le `fetchJson` est injectable pour les tests.
 */

import type {
  AssetManifest,
  AtlasDef,
  CharacterDef,
  EffectDef,
  PacksIndex,
  StationAssetDef,
  ThemeDef,
  TilemapDef,
  TilesetDef,
} from "../../contracts/assets";
import { ASSET_MANIFEST_VERSION } from "../../contracts/assets";

export class ManifestError extends Error {}

export interface ResolvedUrl<T> {
  def: T;
  packId: string;
  /** URLs absolues (base + dossier du pack) */
  urls: Record<string, string>;
}

export interface LoadedAssets {
  /** packs dans l'ordre de chargement (parents avant enfants) */
  packs: AssetManifest[];
  atlases: ResolvedUrl<AtlasDef>[];
  tilesets: ResolvedUrl<TilesetDef>[];
  tilemaps: ResolvedUrl<TilemapDef>[];
  characters: Map<string, CharacterDef>;
  stationsById: Map<string, StationAssetDef>;
  stationsByKind: Map<string, StationAssetDef>;
  themes: Map<string, ThemeDef>;
  effects: Map<string, EffectDef>;
  roleCharacters: Record<string, string[]>;
  animationAliases: Record<string, string>;
}

export type FetchJson = (url: string) => Promise<unknown>;

const defaultFetchJson: FetchJson = async (url) => {
  const resp = await fetch(url);
  if (!resp.ok) throw new ManifestError(`HTTP ${resp.status} sur ${url}`);
  return resp.json();
};

// ---------------------------------------------------------------- validation

function fail(packId: string, message: string): never {
  throw new ManifestError(`Manifest "${packId}": ${message}`);
}

export function validateManifest(data: unknown): AssetManifest {
  if (typeof data !== "object" || data === null) {
    throw new ManifestError("manifest non-objet");
  }
  const m = data as Partial<AssetManifest>;
  const packId = typeof m.pack_id === "string" ? m.pack_id : "?";
  if (!m.pack_id) fail(packId, "pack_id manquant");
  if (m.manifest_version !== ASSET_MANIFEST_VERSION) {
    fail(packId, `manifest_version "${m.manifest_version}" non supportée (attendu ${ASSET_MANIFEST_VERSION})`);
  }
  if (!m.grid || m.grid.tile !== 32) fail(packId, "grid.tile doit valoir 32");
  if (!m.grid.character || m.grid.character.w !== 32 || m.grid.character.h !== 48) {
    fail(packId, "grid.character doit valoir 32×48");
  }
  for (const c of m.characters ?? []) {
    if (!c.id || !c.atlas) fail(packId, "character sans id ou atlas");
    if (!c.animations || Object.keys(c.animations).length === 0) {
      fail(packId, `character "${c.id}" sans animations`);
    }
    if (c.pivot == null || c.pivot.x < 0 || c.pivot.x > 1 || c.pivot.y < 0 || c.pivot.y > 1) {
      fail(packId, `character "${c.id}" : pivot hors [0,1]`);
    }
  }
  for (const s of m.stations ?? []) {
    if (!s.id || !s.kind || !s.atlas) fail(packId, "station sans id/kind/atlas");
    if (!s.frames?.back) fail(packId, `station "${s.id}" sans frame back`);
    if (!s.footprint || s.footprint.w < 1 || s.footprint.h < 1) {
      fail(packId, `station "${s.id}" : footprint invalide`);
    }
    if (!Array.isArray(s.seats)) fail(packId, `station "${s.id}" : seats manquant`);
  }
  for (const t of m.themes ?? []) {
    if (!t.id || !t.tileset || !t.floorTiles?.length || !t.wallTiles?.length) {
      fail(packId, `thème "${t?.id}" incomplet`);
    }
  }
  return {
    manifest_version: m.manifest_version,
    pack_id: m.pack_id,
    extends: m.extends,
    grid: m.grid,
    atlases: m.atlases ?? [],
    tilesets: m.tilesets ?? [],
    tilemaps: m.tilemaps ?? [],
    characters: m.characters ?? [],
    stations: m.stations ?? [],
    themes: m.themes ?? [],
    effects: m.effects ?? [],
    role_characters: m.role_characters ?? {},
    animation_aliases: m.animation_aliases ?? {},
  };
}

export function validatePacksIndex(data: unknown): PacksIndex {
  const index = data as Partial<PacksIndex>;
  if (!index || typeof index.packs !== "object" || index.packs === null) {
    throw new ManifestError("packs.json invalide : champ packs manquant");
  }
  return { packs: index.packs, department_packs: index.department_packs ?? {} };
}

// -------------------------------------------------------------------- fusion

/** Fusionne les manifests, parents d'abord : l'enfant écrase par id/kind. */
export function mergeManifests(ordered: { manifest: AssetManifest; dir: string }[],
                               baseUrl: string): LoadedAssets {
  const result: LoadedAssets = {
    packs: ordered.map((o) => o.manifest),
    atlases: [],
    tilesets: [],
    tilemaps: [],
    characters: new Map(),
    stationsById: new Map(),
    stationsByKind: new Map(),
    themes: new Map(),
    effects: new Map(),
    roleCharacters: {},
    animationAliases: {},
  };
  const base = baseUrl.replace(/\/$/, "");
  for (const { manifest, dir } of ordered) {
    const packBase = `${base}/${dir}`;
    for (const a of manifest.atlases) {
      result.atlases.push({
        def: a, packId: manifest.pack_id,
        urls: { image: `${packBase}/${a.image}`, data: `${packBase}/${a.data}` },
      });
    }
    for (const t of manifest.tilesets) {
      result.tilesets.push({
        def: t, packId: manifest.pack_id, urls: { image: `${packBase}/${t.image}` },
      });
    }
    for (const t of manifest.tilemaps) {
      result.tilemaps.push({
        def: t, packId: manifest.pack_id, urls: { file: `${packBase}/${t.file}` },
      });
    }
    for (const c of manifest.characters) result.characters.set(c.id, c);
    for (const s of manifest.stations) {
      result.stationsById.set(s.id, s);
      result.stationsByKind.set(s.kind, s);
    }
    for (const t of manifest.themes) result.themes.set(t.id, t);
    for (const e of manifest.effects) result.effects.set(e.id, e);
    Object.assign(result.roleCharacters, manifest.role_characters);
    Object.assign(result.animationAliases, manifest.animation_aliases);
  }
  return result;
}

// ----------------------------------------------------------------- chargement

export interface LoadOptions {
  baseUrl: string; // ex. "/assets"
  packIds: string[]; // packs demandés par la scène (core implicite)
  fetchJson?: FetchJson;
}

export async function loadAssetPacks(options: LoadOptions): Promise<LoadedAssets> {
  const fetchJson = options.fetchJson ?? defaultFetchJson;
  const base = options.baseUrl.replace(/\/$/, "");
  const index = validatePacksIndex(await fetchJson(`${base}/packs.json`));

  const wanted = ["core", ...options.packIds.filter((p) => p !== "core")];
  const loaded = new Map<string, { manifest: AssetManifest; dir: string }>();

  async function loadPack(packId: string, chain: string[]): Promise<void> {
    if (loaded.has(packId)) return;
    if (chain.includes(packId)) {
      throw new ManifestError(`héritage circulaire: ${[...chain, packId].join(" → ")}`);
    }
    const dir = index.packs[packId];
    if (!dir) throw new ManifestError(`pack inconnu dans packs.json: "${packId}"`);
    const manifest = validateManifest(await fetchJson(`${base}/${dir}/manifest.json`));
    if (manifest.extends) await loadPack(manifest.extends, [...chain, packId]);
    loaded.set(packId, { manifest, dir });
  }

  for (const packId of wanted) await loadPack(packId, []);
  return mergeManifests([...loaded.values()], base);
}

// ------------------------------------------------------------- résolutions

const FALLBACK_STATION_KIND = "desk";

export function resolveStationAsset(
  assets: LoadedAssets,
  spec: { kind: string; assetId?: string },
): StationAssetDef | null {
  if (spec.assetId) {
    const byId = assets.stationsById.get(spec.assetId);
    if (byId) return byId;
  }
  return assets.stationsByKind.get(spec.kind)
    ?? assets.stationsByKind.get(FALLBACK_STATION_KIND)
    ?? null;
}

export function resolveCharacter(
  assets: LoadedAssets,
  spec: { characterId?: string; role: string; id: string },
): CharacterDef | null {
  if (spec.characterId) {
    const explicit = assets.characters.get(spec.characterId);
    if (explicit) return explicit;
  }
  const candidates = assets.roleCharacters[spec.role] ?? assets.roleCharacters["*"] ?? [];
  const pool = candidates
    .map((id) => assets.characters.get(id))
    .filter((c): c is CharacterDef => Boolean(c));
  if (pool.length === 0) {
    const all = [...assets.characters.values()];
    if (all.length === 0) return null;
    return all[hashCode(spec.id) % all.length];
  }
  // choix stable par entité
  return pool[hashCode(spec.id) % pool.length];
}

export function resolveTheme(
  assets: LoadedAssets,
  spec: { themeId?: string; theme: string },
): ThemeDef | null {
  return (spec.themeId ? assets.themes.get(spec.themeId) : undefined)
    ?? assets.themes.get(spec.theme)
    ?? assets.themes.get("default")
    ?? null;
}

export function hashCode(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return Math.abs(h);
}
