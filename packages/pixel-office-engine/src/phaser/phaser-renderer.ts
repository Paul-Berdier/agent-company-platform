/**
 * Renderer Phaser 3 — implémentation en cours (étape 2 du plan de migration).
 * Ce stub permet à la factory de compiler ; en mode `auto` la bascule vers le
 * renderer canvas est automatique tant que l'implémentation n'est pas posée.
 */

import type { IOfficeRenderer, RendererOptions } from "../contracts/renderer";
import type { SceneSpec } from "../contracts/scene";

export class PhaserRenderer implements IOfficeRenderer {
  constructor(_options: RendererOptions) {
    throw new Error("Renderer Phaser non implémenté (étape 2 de la migration)");
  }

  async ready(): Promise<void> {}
  setScene(_scene: SceneSpec): void {}
  updateEntityStatus(_entityId: string, _status: string): void {}
  emote(_entityId: string, _effectId: string, _durationMs?: number): void {}
  pulseRoom(_roomId: string): void {}
  selectEntity(_entityId: string | null): void {}
  focusRoom(_roomId: string): void {}
  showGallery(): void {}
  destroy(): void {}
}
