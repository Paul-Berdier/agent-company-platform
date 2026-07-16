/**
 * Galerie d'assets : montre tous les packs chargés — personnages (avec cycle
 * automatique de toutes leurs animations), stations, tuiles de thèmes,
 * effets et la tilemap de démonstration. Banc de validation visuelle.
 */

import Phaser from "phaser";

import { clipKey } from "../assets/animation-mapper";
import type { LoadedAssets } from "../assets/manifest-loader";

const MARGIN = 24;
const CYCLE_MS = 1600;

interface CyclingSprite {
  sprite: Phaser.GameObjects.Sprite;
  label: Phaser.GameObjects.Text;
  clips: string[];
  names: string[];
  index: number;
}

export interface GallerySceneData {
  assets: LoadedAssets;
  onClose: () => void;
}

export class GalleryScene extends Phaser.Scene {
  private assets!: LoadedAssets;
  private onClose: (() => void) | null = null;
  private cycling: CyclingSprite[] = [];
  private cursorY = MARGIN;

  constructor() {
    super({ key: "gallery" });
  }

  init(data: GallerySceneData): void {
    this.assets = data.assets;
    this.onClose = data.onClose;
  }

  create(): void {
    this.cycling = [];
    this.cursorY = MARGIN;
    this.cameras.main.setBackgroundColor("#181b22");
    this.cameras.main.setZoom(1);
    this.cameras.main.setScroll(0, 0);

    for (const pack of this.assets.packs) {
      this.heading(`▌ Pack « ${pack.pack_id} »`, "#ffe066", 18);
      if (pack.characters.length) {
        this.heading("Personnages (cycle de toutes les animations)", "#8d99ae", 12);
        this.characterRow(pack.pack_id);
      }
      if (pack.stations.length) {
        this.heading("Stations", "#8d99ae", 12);
        this.stationRow(pack.pack_id);
      }
      if (pack.themes.length) {
        this.heading("Tuiles des thèmes", "#8d99ae", 12);
        this.themeRow(pack.pack_id);
      }
      if (pack.effects.length) {
        this.heading("Effets", "#8d99ae", 12);
        this.effectRow(pack.pack_id);
      }
      if (pack.tilemaps.length) {
        this.heading("Tilemap de démonstration", "#8d99ae", 12);
        this.tilemapBlock(pack.pack_id);
      }
      this.cursorY += 20;
    }

    this.time.addEvent({ delay: CYCLE_MS, loop: true, callback: () => this.cycleAnimations() });

    // navigation : molette + drag vertical
    this.input.on("wheel", (_p: unknown, _o: unknown, _dx: number, dy: number) => {
      this.cameras.main.scrollY = Math.max(0, this.cameras.main.scrollY + dy * 0.6);
    });
    this.input.on("pointermove", (pointer: Phaser.Input.Pointer) => {
      if (pointer.isDown) {
        this.cameras.main.scrollY = Math.max(
          0, this.cameras.main.scrollY - (pointer.y - pointer.prevPosition.y),
        );
      }
    });

    const close = this.add.text(this.scale.width - MARGIN, MARGIN, "✕ Fermer la galerie", {
      fontFamily: "monospace", fontSize: "14px", color: "#ffffff",
      backgroundColor: "#e63946", padding: { x: 8, y: 4 },
    }).setOrigin(1, 0).setScrollFactor(0).setInteractive({ useHandCursor: true }).setDepth(1000);
    close.on("pointerup", () => this.onClose?.());
  }

  private heading(text: string, color: string, size: number): void {
    this.add.text(MARGIN, this.cursorY, text, {
      fontFamily: "monospace", fontSize: `${size}px`, color,
    });
    this.cursorY += size + 10;
  }

  private packManifest(packId: string) {
    return this.assets.packs.find((p) => p.pack_id === packId)!;
  }

  private characterRow(packId: string): void {
    let x = MARGIN + 24;
    for (const character of this.packManifest(packId).characters) {
      const clipNames = Object.keys(character.animations);
      const sprite = this.add.sprite(x, this.cursorY + 72, character.atlas).setScale(2);
      sprite.setOrigin(0.5, 1);
      const label = this.add.text(x, this.cursorY + 78, "", {
        fontFamily: "monospace", fontSize: "10px", color: "#aab2c5", align: "center",
      }).setOrigin(0.5, 0);
      const idText = this.add.text(x, this.cursorY + 92, character.id, {
        fontFamily: "monospace", fontSize: "11px", color: "#ffffff",
      }).setOrigin(0.5, 0);
      void idText;
      const entry: CyclingSprite = {
        sprite, label,
        clips: clipNames.map((n) => clipKey(character.id, n)),
        names: clipNames,
        index: 0,
      };
      this.playCycle(entry);
      this.cycling.push(entry);
      x += 110;
      if (x > this.scale.width - 80) { x = MARGIN + 24; this.cursorY += 130; }
    }
    this.cursorY += 130;
  }

  private stationRow(packId: string): void {
    let x = MARGIN;
    for (const station of this.packManifest(packId).stations) {
      const back = this.add.image(x, this.cursorY, station.atlas, station.frames.back).setOrigin(0, 0);
      if (station.frames.front) {
        this.add.image(x, this.cursorY + back.height - 6, station.atlas, station.frames.front)
          .setOrigin(0, 0);
      }
      this.add.text(x, this.cursorY + Math.max(back.height, 40) + 4, station.kind, {
        fontFamily: "monospace", fontSize: "11px", color: "#ffffff",
      });
      x += Math.max(back.width, 72) + 24;
      if (x > this.scale.width - 100) { x = MARGIN; this.cursorY += 110; }
    }
    this.cursorY += 110;
  }

  private themeRow(packId: string): void {
    let x = MARGIN;
    for (const theme of this.packManifest(packId).themes) {
      const texture = this.textures.get(theme.tileset);
      const tiles = [...theme.floorTiles, ...theme.wallTiles];
      tiles.forEach((tileIndex, i) => {
        const frameName = `gallery-tile-${theme.tileset}-${tileIndex}`;
        if (!texture.has(frameName)) {
          texture.add(frameName, 0, tileIndex * 32, 0, 32, 32);
        }
        this.add.image(x + i * 40, this.cursorY, theme.tileset, frameName).setOrigin(0, 0).setScale(1.2);
      });
      this.add.text(x + tiles.length * 40 + 12, this.cursorY + 12, theme.id, {
        fontFamily: "monospace", fontSize: "12px", color: theme.accentColor,
      });
      this.cursorY += 52;
    }
  }

  private effectRow(packId: string): void {
    let x = MARGIN + 16;
    for (const effect of this.packManifest(packId).effects) {
      const sprite = this.add.sprite(x, this.cursorY + 16, effect.atlas).setScale(2);
      const key = `fx:${effect.id}`;
      if (this.anims.exists(key)) {
        sprite.play({ key, repeat: -1 });
      }
      this.add.text(x, this.cursorY + 36, effect.id, {
        fontFamily: "monospace", fontSize: "10px", color: "#ffffff",
      }).setOrigin(0.5, 0);
      x += 130;
    }
    this.cursorY += 64;
  }

  private tilemapBlock(packId: string): void {
    for (const tilemapDef of this.packManifest(packId).tilemaps) {
      try {
        const map = this.make.tilemap({ key: tilemapDef.id });
        const tilesets = map.tilesets
          .map((ts) => map.addTilesetImage(ts.name, ts.name))
          .filter((ts): ts is Phaser.Tilemaps.Tileset => Boolean(ts));
        for (const layerName of ["floor", "walls"]) {
          if (map.getLayer(layerName)) {
            map.createLayer(layerName, tilesets, MARGIN, this.cursorY)?.setScale(0.75);
          }
        }
        this.cursorY += map.heightInPixels * 0.75 + 16;
      } catch {
        this.add.text(MARGIN, this.cursorY, `(tilemap ${tilemapDef.id} illisible)`, {
          fontFamily: "monospace", fontSize: "11px", color: "#e63946",
        });
        this.cursorY += 24;
      }
    }
  }

  private playCycle(entry: CyclingSprite): void {
    const key = entry.clips[entry.index];
    if (this.anims.exists(key)) {
      entry.sprite.play({ key, repeat: -1 });
      entry.label.setText(entry.names[entry.index]);
    }
  }

  private cycleAnimations(): void {
    for (const entry of this.cycling) {
      entry.index = (entry.index + 1) % entry.clips.length;
      this.playCycle(entry);
    }
  }
}
