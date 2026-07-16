/**
 * Renderer Phaser 3 : rendu tilemaps + spritesheets + animations, piloté par
 * les manifests d'assets. Chargé dynamiquement par la factory — le fallback
 * canvas n'embarque jamais Phaser.
 */

import Phaser from "phaser";

import type { IOfficeRenderer, RendererOptions } from "../contracts/renderer";
import type { SceneSpec } from "../contracts/scene";
import { loadAllAssetPacks, type LoadedAssets } from "./assets/manifest-loader";
import { GalleryScene } from "./scenes/GalleryScene";
import { OfficeScene } from "./scenes/OfficeScene";

export class PhaserRenderer implements IOfficeRenderer {
  private game: Phaser.Game | null = null;
  private office: OfficeScene | null = null;
  private assets: LoadedAssets | null = null;
  private galleryOpen = false;
  private readonly readyPromise: Promise<void>;

  constructor(private options: RendererOptions) {
    this.readyPromise = this.boot();
  }

  ready(): Promise<void> {
    return this.readyPromise;
  }

  private debug(stage: string): void {
    (globalThis as { __acpBootStage?: string }).__acpBootStage = stage;
  }

  private async boot(): Promise<void> {
    this.debug("loading-assets");
    const assets = await loadAllAssetPacks(this.options.assetsBaseUrl ?? "/assets");
    this.assets = assets;
    this.debug("assets-loaded");

    const game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: this.options.mount,
      backgroundColor: "#20242c",
      pixelArt: true,
      roundPixels: true,
      scale: {
        mode: Phaser.Scale.RESIZE,
        width: "100%",
        height: "100%",
      },
      fps: this.options.forceTimeout ? { forceSetTimeOut: true } : undefined,
    });
    this.game = game;
    (globalThis as { __acpGame?: Phaser.Game }).__acpGame = game;

    // Contournement : dans un onglet caché dès l'ouverture, le READY du
    // TextureManager peut se perdre et le jeu ne démarre jamais. Si les
    // textures par défaut sont prêtes mais que la boucle n'a pas démarré,
    // on ré-émet l'événement pour relancer la chaîne de boot.
    const watchdog = setInterval(() => {
      if (game.isRunning) {
        clearInterval(watchdog);
      } else if (game.textures.exists("__DEFAULT")) {
        game.textures.emit(Phaser.Textures.Events.READY);
      }
    }, 500);

    await new Promise<void>((resolve) => {
      const done = () => {
        clearInterval(watchdog);
        resolve();
      };
      if (game.isRunning) done();
      else game.events.once(Phaser.Core.Events.READY, done);
    });
    this.debug("game-ready");

    this.office = new OfficeScene();
    await new Promise<void>((resolve) => {
      game.scene.add("office", this.office!, true, {
        assets,
        callbacks: this.options.callbacks ?? {},
        onReady: resolve,
      });
    });
    this.debug("office-created");
  }

  setScene(scene: SceneSpec): void {
    this.office?.applyScene(scene);
  }

  updateEntityStatus(entityId: string, status: string): void {
    this.office?.setEntityStatus(entityId, status);
  }

  emote(entityId: string, effectId: string, durationMs?: number): void {
    this.office?.showEmote(entityId, effectId, durationMs);
  }

  pulseRoom(roomId: string): void {
    this.office?.pulseRoomById(roomId);
  }

  selectEntity(entityId: string | null): void {
    this.office?.selectEntity(entityId);
  }

  focusRoom(roomId: string): void {
    this.office?.focusRoomById(roomId);
  }

  showGallery(): void {
    if (!this.game || !this.assets || this.galleryOpen) return;
    this.galleryOpen = true;
    this.game.scene.sleep("office");
    const data = {
      assets: this.assets,
      onClose: () => {
        this.galleryOpen = false;
        this.game?.scene.stop("gallery");
        this.game?.scene.wake("office");
      },
    };
    if (this.game.scene.getScene("gallery")) {
      this.game.scene.start("gallery", data);
    } else {
      this.game.scene.add("gallery", new GalleryScene(), true, data);
    }
  }

  destroy(): void {
    this.game?.destroy(true);
    this.game = null;
    this.office = null;
  }
}
