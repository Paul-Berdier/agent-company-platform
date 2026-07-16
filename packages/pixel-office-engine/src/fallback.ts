/**
 * Factory des renderers avec bascule automatique.
 *
 * `phaser` est chargé dynamiquement (le fallback canvas n'embarque jamais
 * Phaser dans le bundle). En mode `auto`, tout échec de chargement ou
 * d'initialisation retombe sur le renderer canvas legacy.
 */

import type { IOfficeRenderer, RendererOptions } from "./contracts/renderer";
import { CanvasRenderer } from "./legacy/canvas-renderer";

export async function createOfficeRenderer(options: RendererOptions): Promise<IOfficeRenderer> {
  const mode = options.mode ?? "auto";

  if (mode === "canvas") {
    return new CanvasRenderer(options.mount, options.callbacks);
  }

  try {
    const { PhaserRenderer } = await import("./phaser/phaser-renderer");
    const renderer = new PhaserRenderer(options);
    await renderer.ready();
    return renderer;
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    if (mode === "phaser") {
      throw new Error(`Renderer Phaser indisponible: ${reason}`);
    }
    console.warn(`[pixel-office-engine] fallback canvas (${reason})`);
    options.callbacks?.onRendererFallback?.(reason);
    return new CanvasRenderer(options.mount, options.callbacks);
  }
}
