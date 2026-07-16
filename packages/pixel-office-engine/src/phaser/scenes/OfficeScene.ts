/**
 * Scène principale : rend une `SceneSpec` entièrement depuis les packs
 * d'assets (tuiles, meubles, personnages, effets). Aucun visuel métier
 * codé en dur ici — tout vient des manifests.
 */

import Phaser from "phaser";

import type { EngineCallbacks } from "../../contracts/renderer";
import type { Facing, SceneSpec } from "../../contracts/scene";
// (Facing reste utilisé par EntityView.seatFacing)
import {
  buildRenderModel,
  type RenderEntity,
  type RenderModel,
  type RenderRoom,
  type RenderStation,
} from "../adapter/scene-adapter";
import { clipKey, expandFrames, resolveClip, walkClipForDirection } from "../assets/animation-mapper";
import { hashCode, type LoadedAssets } from "../assets/manifest-loader";
import { CameraController } from "../camera/camera-controller";
import { buildCollisionGrid, findPath, type CollisionGrid, type Point } from "../grid/pathfinding";
import { StationReservations } from "../grid/reservations";
import { DEPTH_EFFECTS, DEPTH_FLOOR, DEPTH_UI, DEPTH_WALLS, FRONT_BIAS, sortedDepth } from "../layers";

const TILE = 32;
/** animations qui n'ancrent PAS l'agent à sa station (mêmes règles que legacy) */
const NON_ANCHORING = new Set(["walk", "coffee"]);

interface EntityView {
  model: RenderEntity;
  sprite: Phaser.GameObjects.Sprite;
  label: Phaser.GameObjects.Text;
  px: number; // position pieds, pixels monde
  py: number;
  path: Point[];
  targetTile: Point | null;
  seatFacing: Facing | null;
  wanderAt: number;
  currentClip: string;
  seed: number;
}

interface EmoteView {
  entityId: string;
  object: Phaser.GameObjects.Sprite | Phaser.GameObjects.Text;
  until: number;
}

export interface OfficeSceneData {
  assets: LoadedAssets;
  callbacks: EngineCallbacks;
  onReady: () => void;
}

export class OfficeScene extends Phaser.Scene {
  private assets!: LoadedAssets;
  private callbacks: EngineCallbacks = {};
  private onReadyCallback: (() => void) | null = null;

  private model: RenderModel | null = null;
  private pendingSpec: SceneSpec | null = null;
  private created = false;
  private layoutSignature = "";

  private grid: CollisionGrid | null = null;
  private reservations = new StationReservations();

  private map: Phaser.Tilemaps.Tilemap | null = null;
  private decor: Phaser.GameObjects.GameObject[] = [];
  private entityViews = new Map<string, EntityView>();
  private emotes: EmoteView[] = [];
  private selectionMarker: Phaser.GameObjects.Ellipse | null = null;
  private selectedId: string | null = null;
  private cameraCtl: CameraController | null = null;
  private clickConsumed = false;

  constructor() {
    super({ key: "office" });
  }

  init(data: OfficeSceneData): void {
    this.assets = data.assets;
    this.callbacks = data.callbacks;
    this.onReadyCallback = data.onReady;
  }

  preload(): void {
    for (const atlas of this.assets.atlases) {
      this.load.atlas(atlas.def.id, atlas.urls.image, atlas.urls.data);
    }
    for (const tileset of this.assets.tilesets) {
      this.load.image(tileset.def.id, tileset.urls.image);
    }
    for (const tilemap of this.assets.tilemaps) {
      this.load.tilemapTiledJSON(tilemap.def.id, tilemap.urls.file);
    }
  }

  create(): void {
    this.registerAnimations();
    this.cameraCtl = new CameraController(this, 800, 600);
    this.cameraCtl.attach();
    this.setupInput();
    this.created = true;
    if (this.pendingSpec) {
      const spec = this.pendingSpec;
      this.pendingSpec = null;
      this.applyScene(spec);
    }
    this.scale.on("resize", () => this.cameraCtl?.fit());
    this.onReadyCallback?.();
  }

  private registerAnimations(): void {
    for (const character of this.assets.characters.values()) {
      for (const [clipName, clip] of Object.entries(character.animations)) {
        const key = clipKey(character.id, clipName);
        if (this.anims.exists(key)) continue;
        this.anims.create({
          key,
          frames: expandFrames(clip.frames).map((frame) => ({ key: character.atlas, frame })),
          frameRate: clip.frameRate,
          repeat: clip.repeat,
        });
      }
    }
    for (const effect of this.assets.effects.values()) {
      const key = `fx:${effect.id}`;
      if (this.anims.exists(key)) continue;
      this.anims.create({
        key,
        frames: expandFrames(effect.animation.frames).map((frame) => ({ key: effect.atlas, frame })),
        frameRate: effect.animation.frameRate,
        repeat: effect.animation.repeat,
      });
    }
  }

  private setupInput(): void {
    this.input.on(
      "gameobjectup",
      (_pointer: Phaser.Input.Pointer, object: Phaser.GameObjects.GameObject) => {
        if (this.cameraCtl?.isDragGesture) return;
        const entityId = object.getData("entityId") as string | undefined;
        if (entityId) {
          this.clickConsumed = true;
          this.selectEntity(entityId);
          this.callbacks.onEntityClick?.(entityId);
        }
      },
    );
    this.input.on(
      "gameobjectover",
      (_pointer: Phaser.Input.Pointer, object: Phaser.GameObjects.GameObject) => {
        const entityId = object.getData("entityId") as string | undefined;
        if (entityId) {
          (object as Phaser.GameObjects.Sprite).setTint(0xd8e6ff);
          this.callbacks.onEntityHover?.(entityId);
        }
      },
    );
    this.input.on(
      "gameobjectout",
      (_pointer: Phaser.Input.Pointer, object: Phaser.GameObjects.GameObject) => {
        (object as Phaser.GameObjects.Sprite).clearTint();
        this.callbacks.onEntityHover?.(null);
      },
    );
    this.input.on("pointerup", (pointer: Phaser.Input.Pointer) => {
      if (this.clickConsumed) {
        this.clickConsumed = false;
        return;
      }
      if (this.cameraCtl?.isDragGesture || !this.model) return;
      const world = this.cameras.main.getWorldPoint(pointer.x, pointer.y);
      const tx = world.x / TILE;
      const ty = world.y / TILE;
      for (const room of this.model.rooms) {
        const { x, y, w, h } = room.spec;
        if (tx >= x && tx <= x + w && ty >= y && ty <= y + h) {
          this.callbacks.onRoomClick?.(room.spec.id);
          return;
        }
      }
    });
  }

  // ------------------------------------------------------------- API moteur

  applyScene(spec: SceneSpec): void {
    if (!this.created) {
      this.pendingSpec = spec;
      return;
    }
    const model = buildRenderModel(spec, this.assets);
    const layoutChanged = model.layoutSignature !== this.layoutSignature;
    this.model = model;
    if (layoutChanged) {
      this.layoutSignature = model.layoutSignature;
      this.rebuildDecor(model);
      this.grid = buildCollisionGrid(model);
      this.reservations.clear();
      for (const view of this.entityViews.values()) {
        view.path = [];
        view.targetTile = null;
      }
      this.cameraCtl?.setWorldSize(model.cols * TILE, model.rows * TILE);
      this.cameraCtl?.fit();
    }
    this.diffEntities(model);
  }

  setEntityStatus(entityId: string, status: string): void {
    const view = this.entityViews.get(entityId);
    if (view) {
      view.model.spec.status = status;
      view.path = [];
      view.targetTile = null;
    }
  }

  showEmote(entityId: string, effectId: string, durationMs = 2500): void {
    const view = this.entityViews.get(entityId);
    if (!view) return;
    const effect = this.assets.effects.get(effectId);
    let object: EmoteView["object"];
    if (effect) {
      object = this.add.sprite(view.px, view.py - 56, effect.atlas);
      object.play(`fx:${effect.id}`);
    } else {
      // compatibilité : glyphe texte brut pendant la migration
      object = this.add.text(view.px, view.py - 56, effectId, {
        fontFamily: "monospace", fontSize: "14px", color: "#ffffff",
      }).setOrigin(0.5, 0.5);
    }
    object.setDepth(DEPTH_EFFECTS);
    this.emotes.push({ entityId, object, until: this.time.now + durationMs });
  }

  pulseRoomById(roomId: string): void {
    const room = this.model?.rooms.find((r) => r.spec.id === roomId);
    if (!room) return;
    const accent = Phaser.Display.Color.HexStringToColor(
      room.theme?.accentColor ?? "#5b8266",
    ).color;
    const { x, y, w, h } = room.spec;
    const rect = this.add
      .rectangle(x * TILE + (w * TILE) / 2, y * TILE + (h * TILE) / 2, w * TILE, h * TILE)
      .setStrokeStyle(3, accent)
      .setFillStyle()
      .setDepth(DEPTH_EFFECTS - 1);
    this.tweens.add({
      targets: rect,
      alpha: 0,
      duration: 1100,
      onComplete: () => rect.destroy(),
    });
  }

  selectEntity(entityId: string | null): void {
    this.selectedId = entityId;
    if (!entityId) {
      this.selectionMarker?.setVisible(false);
      return;
    }
    if (!this.selectionMarker) {
      this.selectionMarker = this.add
        .ellipse(0, 0, 26, 12)
        .setStrokeStyle(2, 0xffe066)
        .setFillStyle(0xffe066, 0.25);
    }
    this.selectionMarker.setVisible(true);
  }

  focusRoomById(roomId: string): void {
    const room = this.model?.rooms.find((r) => r.spec.id === roomId);
    if (!room) return;
    this.cameraCtl?.focusRoom({
      x: room.spec.x * TILE, y: room.spec.y * TILE,
      w: room.spec.w * TILE, h: room.spec.h * TILE,
    });
  }

  // ------------------------------------------------------------------ décor

  private rebuildDecor(model: RenderModel): void {
    for (const object of this.decor) object.destroy();
    this.decor = [];
    this.map?.destroy();

    this.map = this.make.tilemap({
      width: model.cols, height: model.rows, tileWidth: TILE, tileHeight: TILE,
    });
    const tilesetRefs = new Map<string, Phaser.Tilemaps.Tileset>();
    for (const tileset of this.assets.tilesets) {
      const ref = this.map.addTilesetImage(
        tileset.def.id, tileset.def.id, TILE, TILE,
        tileset.def.margin ?? 0, tileset.def.spacing ?? 0,
      );
      if (ref) tilesetRefs.set(tileset.def.id, ref);
    }
    const allTilesets = [...tilesetRefs.values()];
    const floorLayer = this.map.createBlankLayer("floor", allTilesets);
    const wallLayer = this.map.createBlankLayer("walls", allTilesets);
    floorLayer?.setDepth(DEPTH_FLOOR);
    wallLayer?.setDepth(DEPTH_WALLS);

    this.paintGround(model, tilesetRefs, floorLayer);
    for (const room of model.rooms) {
      this.paintRoom(room, tilesetRefs, floorLayer, wallLayer);
      this.decorateRoom(room);
    }
    for (const decoration of model.decorations) this.placeDecoration(decoration);
  }

  /** Sol extérieur du campus : herbe partout, allées sur les rectangles `paths`. */
  private paintGround(
    model: RenderModel,
    tilesetRefs: Map<string, Phaser.Tilemaps.Tileset>,
    floorLayer: Phaser.Tilemaps.TilemapLayer | null,
  ): void {
    const theme = model.groundTheme;
    const tileset = theme ? tilesetRefs.get(theme.tileset) : undefined;
    if (!theme || !tileset || !floorLayer) return;
    for (let y = 0; y < model.rows; y++) {
      for (let x = 0; x < model.cols; x++) {
        const local = theme.floorTiles[(x * 7 + y * 13) % theme.floorTiles.length];
        floorLayer.putTileAt(tileset.firstgid + local, x, y);
      }
    }
    const pathTiles = theme.pathTiles?.length ? theme.pathTiles : theme.floorTiles;
    for (const rect of model.paths) {
      for (let y = rect.y; y < rect.y + rect.h; y++) {
        for (let x = rect.x; x < rect.x + rect.w; x++) {
          const local = pathTiles[(x + y) % pathTiles.length];
          floorLayer.putTileAt(tileset.firstgid + local, x, y);
        }
      }
    }
  }

  private placeDecoration(decoration: { spec: { x: number; y: number }; asset: { atlas: string; frames: { back: string } } | null }): void {
    const asset = decoration.asset;
    if (!asset) return;
    const x = decoration.spec.x * TILE;
    const y = decoration.spec.y * TILE;
    const image = this.add.image(x, y, asset.atlas, asset.frames.back).setOrigin(0, 0);
    // ancre au sol : la base du sprite définit sa profondeur
    image.setY(y + TILE - image.height);
    image.setDepth(sortedDepth(y + TILE));
    this.decor.push(image);
  }

  private paintRoom(
    room: RenderRoom,
    tilesetRefs: Map<string, Phaser.Tilemaps.Tileset>,
    floorLayer: Phaser.Tilemaps.TilemapLayer | null,
    wallLayer: Phaser.Tilemaps.TilemapLayer | null,
  ): void {
    const theme = room.theme;
    const tileset = theme ? tilesetRefs.get(theme.tileset) : undefined;
    if (!theme || !tileset || !floorLayer || !wallLayer) return;
    const { x, y, w, h } = room.spec;
    for (let j = 0; j < h; j++) {
      for (let i = 0; i < w; i++) {
        const local = theme.floorTiles[(i + j) % theme.floorTiles.length];
        floorLayer.putTileAt(tileset.firstgid + local, x + i, y + j);
      }
    }
    for (let i = 0; i < w; i++) {
      const local = theme.wallTiles[i % theme.wallTiles.length];
      wallLayer.putTileAt(tileset.firstgid + local, x + i, y);
    }
  }

  private decorateRoom(room: RenderRoom): void {
    const { x, y, w, h } = room.spec;
    const accent = room.theme?.accentColor ?? "#5b8266";
    const accentColor = Phaser.Display.Color.HexStringToColor(accent).color;
    const centerX = x * TILE + (w * TILE) / 2;

    for (const station of room.stations) this.placeStation(station);

    // enseigne : nom centré sur un cartouche, sous-titre en dessous
    const name = this.add.text(centerX, y * TILE + 8, room.spec.name.toUpperCase(), {
      fontFamily: "monospace", fontSize: "12px", color: "#ffffff", fontStyle: "bold",
    }).setOrigin(0.5, 0.5).setDepth(DEPTH_UI + 1);
    const plate = this.add
      .rectangle(centerX, y * TILE + 8, name.width + 18, 18, 0x14161c, 0.88)
      .setStrokeStyle(1, accentColor)
      .setDepth(DEPTH_UI);
    this.decor.push(plate, name);
    if (room.spec.subtitle) {
      const sub = this.add.text(centerX, y * TILE + 24, room.spec.subtitle, {
        fontFamily: "monospace", fontSize: "10px", color: accent,
      }).setOrigin(0.5, 0.5).setDepth(DEPTH_UI + 1);
      const subPlate = this.add
        .rectangle(centerX, y * TILE + 24, sub.width + 12, 13, 0x14161c, 0.75)
        .setDepth(DEPTH_UI);
      this.decor.push(subPlate, sub);
    }
    if (room.spec.badge) {
      const badge = this.add.text(x * TILE + 6, (y + h) * TILE - 16, room.spec.badge, {
        fontFamily: "monospace", fontSize: "10px", color: accent,
        backgroundColor: "#14161cbb", padding: { x: 4, y: 2 },
      }).setDepth(DEPTH_UI);
      this.decor.push(badge);
    }
    const border = this.add
      .rectangle(centerX, y * TILE + (h * TILE) / 2, w * TILE, h * TILE)
      .setStrokeStyle(2, accentColor, 0.5)
      .setFillStyle()
      .setDepth(DEPTH_WALLS + 1);
    this.decor.push(border);
  }

  private placeStation(station: RenderStation): void {
    const asset = station.asset;
    if (!asset) return;
    const x = station.worldX * TILE;
    const y = station.worldY * TILE;
    const back = this.add.image(x, y, asset.atlas, asset.frames.back).setOrigin(0, 0);
    const baseY = y + back.height;
    back.setDepth(sortedDepth(baseY));
    this.decor.push(back);
    if (asset.frames.front) {
      const front = this.add.image(x, y, asset.atlas, asset.frames.front).setOrigin(0, 0);
      front.setY(y + back.height - front.height);
      front.setDepth(sortedDepth(baseY + TILE, FRONT_BIAS));
      this.decor.push(front);
    }
  }

  // --------------------------------------------------------------- entités

  private diffEntities(model: RenderModel): void {
    const seen = new Set<string>();
    for (const entity of model.entities) {
      seen.add(entity.spec.id);
      const existing = this.entityViews.get(entity.spec.id);
      if (existing) {
        const roomChanged = existing.model.spec.roomId !== entity.spec.roomId;
        existing.model = entity;
        existing.label.setText(entity.spec.name);
        if (roomChanged) {
          const home = this.entityHomePx(entity, model);
          existing.px = home.x;
          existing.py = home.y;
          existing.path = [];
          existing.targetTile = null;
          this.reservations.release(entity.spec.id);
        }
      } else {
        this.createEntityView(entity, model);
      }
    }
    for (const [id, view] of [...this.entityViews]) {
      if (!seen.has(id)) {
        view.sprite.destroy();
        view.label.destroy();
        this.reservations.release(id);
        this.entityViews.delete(id);
        if (this.selectedId === id) this.selectEntity(null);
      }
    }
  }

  private entityHomePx(entity: RenderEntity, model: RenderModel): { x: number; y: number } {
    const room = model.rooms.find((r) => r.spec.id === entity.spec.roomId);
    if (!room) return { x: 16, y: 26 };
    const seed = hashCode(entity.spec.id);
    const tx = room.spec.x + 1 + (seed % Math.max(1, room.spec.w - 2));
    const ty = room.spec.y + 2 + ((seed >> 3) % Math.max(1, room.spec.h - 3));
    return { x: tx * TILE + TILE / 2, y: ty * TILE + 26 };
  }

  private createEntityView(entity: RenderEntity, model: RenderModel): void {
    const character = entity.character;
    if (!character) return;
    const home = this.entityHomePx(entity, model);
    const sprite = this.add.sprite(home.x, home.y, character.atlas);
    sprite.setOrigin(character.pivot.x, character.pivot.y);
    sprite.setInteractive({ useHandCursor: true });
    sprite.setData("entityId", entity.spec.id);
    const idle = resolveClip(character, "idle-down", this.assets.animationAliases);
    if (idle) sprite.play(clipKey(character.id, idle.name));

    const label = this.add.text(home.x, home.y + 4, entity.spec.name, {
      fontFamily: "monospace", fontSize: "10px", color: "#e6e6e6",
      stroke: "#14161c", strokeThickness: 2,
    }).setOrigin(0.5, 0);

    this.entityViews.set(entity.spec.id, {
      model: entity,
      sprite,
      label,
      px: home.x,
      py: home.y,
      path: [],
      targetTile: null,
      seatFacing: null,
      wanderAt: 0,
      currentClip: idle ? clipKey(character.id, idle.name) : "",
      seed: hashCode(entity.spec.id),
    });
  }

  // ------------------------------------------------------------------ tick

  update(time: number, delta: number): void {
    if (!this.model || !this.grid) return;
    for (const view of this.entityViews.values()) {
      this.updateEntity(view, time, delta);
    }
    this.updateEmotes(time);
    this.updateSelection();
  }

  private tileOf(view: EntityView): Point {
    return { x: Math.floor(view.px / TILE), y: Math.floor(view.py / TILE) };
  }

  private playClip(view: EntityView, clipName: string | null): void {
    const character = view.model.character;
    if (!character || !clipName) return;
    const key = clipKey(character.id, clipName);
    if (view.currentClip !== key && this.anims.exists(key)) {
      view.currentClip = key;
      view.sprite.play(key);
    }
  }

  private updateEntity(view: EntityView, time: number, delta: number): void {
    const model = this.model!;
    const grid = this.grid!;
    const spec = view.model.spec;
    const room = model.rooms.find((r) => r.spec.id === spec.roomId);
    const character = view.model.character;
    if (!room || !character) return;
    const aliases = this.assets.animationAliases;

    const animName = model.statusMapping[spec.status] ?? "idle-down";
    const anchored = Boolean(view.model.stationKey) && !NON_ANCHORING.has(animName)
      && animName !== "idle-down";
    const bounds = {
      x: room.spec.x, y: room.spec.y + 1,
      w: room.spec.w, h: room.spec.h - 1,
    };

    if (anchored) {
      const station = room.stations.find((s) => s.key === view.model.stationKey);
      if (station) {
        const reservation = this.reservations.reserve(spec.id, station.key, station.seats);
        if (reservation) {
          const target = { x: reservation.seat.x, y: reservation.seat.y };
          view.seatFacing = reservation.seat.facing;
          if (!view.targetTile || view.targetTile.x !== target.x || view.targetTile.y !== target.y) {
            const path = findPath(grid, this.tileOf(view), target, bounds);
            if (path) {
              view.path = path;
              view.targetTile = target;
            }
          }
        }
      }
    } else {
      this.reservations.release(spec.id);
      view.seatFacing = null;
      const atTarget = view.path.length === 0;
      if (atTarget && time > view.wanderAt) {
        view.wanderAt = time + 2500 + (view.seed % 3000);
        const target = this.randomWalkableTile(room, grid);
        if (target) {
          const path = findPath(grid, this.tileOf(view), target, bounds);
          if (path) {
            view.path = path;
            view.targetTile = target;
          }
        }
      }
    }

    // suivi du chemin
    if (view.path.length > 0) {
      const next = view.path[0];
      const targetX = next.x * TILE + TILE / 2;
      const targetY = next.y * TILE + 26;
      const dx = targetX - view.px;
      const dy = targetY - view.py;
      const dist = Math.hypot(dx, dy);
      const speed = (spec.speedTilesPerSec ?? 3) * TILE * (delta / 1000);
      if (dist <= speed) {
        view.px = targetX;
        view.py = targetY;
        view.path.shift();
      } else {
        view.px += (dx / dist) * speed;
        view.py += (dy / dist) * speed;
      }
      const walk = walkClipForDirection(character, dx, dy, aliases);
      this.playClip(view, walk?.name ?? null);
    } else {
      view.targetTile = null;
      const clip = resolveClip(character, animName, aliases);
      this.playClip(view, clip?.name ?? null);
    }

    view.sprite.setPosition(Math.round(view.px), Math.round(view.py));
    view.sprite.setDepth(sortedDepth(view.py, 0.25));
    view.sprite.setAlpha(spec.status === "offline" ? 0.4 : 1);
    view.label.setPosition(Math.round(view.px), Math.round(view.py) + 4);
    view.label.setDepth(sortedDepth(view.py, 0.3));
  }

  private randomWalkableTile(room: RenderRoom, grid: CollisionGrid): Point | null {
    const { x, y, w, h } = room.spec;
    for (let attempt = 0; attempt < 12; attempt++) {
      const tx = x + 1 + Math.floor(Math.random() * Math.max(1, w - 2));
      const ty = y + 2 + Math.floor(Math.random() * Math.max(1, h - 3));
      if (grid.isWalkable(tx, ty)) return { x: tx, y: ty };
    }
    return null;
  }

  private updateEmotes(time: number): void {
    this.emotes = this.emotes.filter((emote) => {
      const view = this.entityViews.get(emote.entityId);
      if (!view || time > emote.until) {
        emote.object.destroy();
        return false;
      }
      emote.object.setPosition(Math.round(view.px), Math.round(view.py) - 56);
      return true;
    });
  }

  private updateSelection(): void {
    if (!this.selectedId || !this.selectionMarker) return;
    const view = this.entityViews.get(this.selectedId);
    if (!view) return;
    this.selectionMarker.setPosition(Math.round(view.px), Math.round(view.py) + 2);
    this.selectionMarker.setDepth(sortedDepth(view.py, -0.5));
  }
}
