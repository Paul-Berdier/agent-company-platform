/**
 * Caméra : pan à la souris, zoom par paliers pixel-perfect, focus salle.
 */

import Phaser from "phaser";

export const ZOOM_LEVELS = [0.5, 1, 2, 3];

export class CameraController {
  private dragging = false;
  private dragMoved = false;
  private lastX = 0;
  private lastY = 0;
  private zoomIndex = 1; // 1×

  constructor(
    private scene: Phaser.Scene,
    private worldW: number,
    private worldH: number,
  ) {}

  get camera(): Phaser.Cameras.Scene2D.Camera {
    return this.scene.cameras.main;
  }

  /** vrai si le geste en cours est un déplacement de caméra (pas un clic) */
  get isDragGesture(): boolean {
    return this.dragMoved;
  }

  attach(): void {
    const input = this.scene.input;
    input.on("pointerdown", (pointer: Phaser.Input.Pointer) => {
      this.dragging = true;
      this.dragMoved = false;
      this.lastX = pointer.x;
      this.lastY = pointer.y;
    });
    input.on("pointermove", (pointer: Phaser.Input.Pointer) => {
      if (!this.dragging || !pointer.isDown) return;
      const dx = pointer.x - this.lastX;
      const dy = pointer.y - this.lastY;
      if (Math.abs(pointer.x - pointer.downX) + Math.abs(pointer.y - pointer.downY) > 6) {
        this.dragMoved = true;
      }
      if (this.dragMoved) {
        this.camera.scrollX -= dx / this.camera.zoom;
        this.camera.scrollY -= dy / this.camera.zoom;
      }
      this.lastX = pointer.x;
      this.lastY = pointer.y;
    });
    input.on("pointerup", () => {
      this.dragging = false;
      // dragMoved est lu par les handlers de clic PUIS remis à zéro au tick suivant
      this.scene.time.delayedCall(0, () => (this.dragMoved = false));
    });
    input.on(
      "wheel",
      (pointer: Phaser.Input.Pointer, _objects: unknown, _dx: number, dy: number) => {
        this.stepZoom(dy > 0 ? -1 : 1, pointer);
      },
    );
  }

  setWorldSize(worldW: number, worldH: number): void {
    this.worldW = worldW;
    this.worldH = worldH;
  }

  /** Zoom initial : plus grand palier qui montre toute la scène. */
  fit(): void {
    const view = this.camera;
    const fitZoom = Math.min(view.width / this.worldW, view.height / this.worldH);
    let index = 0;
    for (let i = 0; i < ZOOM_LEVELS.length; i++) {
      if (ZOOM_LEVELS[i] <= fitZoom) index = i;
    }
    this.zoomIndex = index;
    view.setZoom(ZOOM_LEVELS[index]);
    view.centerOn(this.worldW / 2, this.worldH / 2);
  }

  stepZoom(direction: 1 | -1, pointer?: Phaser.Input.Pointer): void {
    const next = Math.min(ZOOM_LEVELS.length - 1, Math.max(0, this.zoomIndex + direction));
    if (next === this.zoomIndex) return;
    const camera = this.camera;
    const anchor = pointer
      ? camera.getWorldPoint(pointer.x, pointer.y)
      : new Phaser.Math.Vector2(camera.midPoint.x, camera.midPoint.y);
    this.zoomIndex = next;
    camera.setZoom(ZOOM_LEVELS[next]);
    camera.centerOn(anchor.x, anchor.y);
  }

  focusRoom(rect: { x: number; y: number; w: number; h: number }): void {
    this.camera.pan(rect.x + rect.w / 2, rect.y + rect.h / 2, 400, "Sine.easeInOut");
  }
}
