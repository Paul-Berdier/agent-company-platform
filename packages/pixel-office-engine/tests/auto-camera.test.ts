import { describe, expect, it } from "vitest";

import { autoCameraDelay, nextAutoCameraIndex } from "../src/phaser/camera/auto-camera";

describe("caméra automatique", () => {
  it("utilise neuf secondes par défaut et refuse une boucle trop rapide", () => {
    expect(autoCameraDelay(undefined)).toBe(9000);
    expect(autoCameraDelay(100)).toBe(1000);
    expect(autoCameraDelay(5000)).toBe(5000);
  });

  it("cycle les salles dans l'ordre", () => {
    expect(nextAutoCameraIndex(0, 3)).toEqual({ roomIndex: 0, nextIndex: 1 });
    expect(nextAutoCameraIndex(2, 3)).toEqual({ roomIndex: 2, nextIndex: 3 });
    expect(nextAutoCameraIndex(3, 3)).toEqual({ roomIndex: 0, nextIndex: 4 });
  });

  it("ne produit aucune destination sans salle", () => {
    expect(nextAutoCameraIndex(0, 0)).toBeNull();
  });
});
