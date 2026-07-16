import { describe, expect, it } from "vitest";

import type { CharacterDef } from "../src/contracts/assets";
import {
  clipKey,
  expandFrames,
  resolveAnimationForStatus,
  resolveClip,
  walkClipForDirection,
} from "../src/phaser/assets/animation-mapper";

const CHARACTER: CharacterDef = {
  id: "worker-a",
  atlas: "chars",
  size: { w: 32, h: 48 },
  pivot: { x: 0.5, y: 0.9 },
  animations: {
    "idle-down": { frames: "worker-a/idle-down/{0..3}", frameRate: 3, repeat: -1 },
    "walk-down": { frames: "worker-a/walk-down/{0..3}", frameRate: 8, repeat: -1 },
    "walk-left": { frames: "worker-a/walk-left/{0..3}", frameRate: 8, repeat: -1 },
    "type": { frames: "worker-a/type/{0..3}", frameRate: 6, repeat: -1 },
    "sit": { frames: "worker-a/sit/{0..1}", frameRate: 2, repeat: -1 },
  },
};

const ALIASES = { coffee: "idle-down", write: "type", walk: "walk-down" };

describe("expandFrames", () => {
  it("développe un motif {a..b}", () => {
    expect(expandFrames("c/anim/{0..3}")).toEqual(["c/anim/0", "c/anim/1", "c/anim/2", "c/anim/3"]);
  });

  it("laisse un nom sans motif inchangé", () => {
    expect(expandFrames("c/pose")).toEqual(["c/pose"]);
  });

  it("refuse un intervalle inversé", () => {
    expect(() => expandFrames("c/a/{5..2}")).toThrow(/invalide/);
  });
});

describe("resolveClip", () => {
  it("retourne le clip direct s'il existe", () => {
    expect(resolveClip(CHARACTER, "type", ALIASES)?.name).toBe("type");
  });

  it("suit un alias quand le clip est absent", () => {
    expect(resolveClip(CHARACTER, "coffee", ALIASES)?.name).toBe("idle-down");
    expect(resolveClip(CHARACTER, "write", ALIASES)?.name).toBe("type");
  });

  it("retombe sur idle-down pour un nom inconnu", () => {
    expect(resolveClip(CHARACTER, "animation-mystere", ALIASES)?.name).toBe("idle-down");
  });

  it("retourne null si même idle-down est absent", () => {
    const noIdle: CharacterDef = { ...CHARACTER, animations: { sit: CHARACTER.animations["sit"] } };
    expect(resolveClip(noIdle, "animation-mystere")).toBeNull();
  });
});

describe("resolveAnimationForStatus", () => {
  const STATUS_MAPPING = { working: "type", idle: "coffee", blocked: "sit" };

  it("suit la chaîne statut → mapping → alias → clip", () => {
    expect(resolveAnimationForStatus(CHARACTER, "working", STATUS_MAPPING, ALIASES)?.name).toBe("type");
    expect(resolveAnimationForStatus(CHARACTER, "idle", STATUS_MAPPING, ALIASES)?.name).toBe("idle-down");
    expect(resolveAnimationForStatus(CHARACTER, "blocked", STATUS_MAPPING, ALIASES)?.name).toBe("sit");
  });

  it("statut hors mapping → idle-down", () => {
    expect(resolveAnimationForStatus(CHARACTER, "statut-inconnu", STATUS_MAPPING, ALIASES)?.name)
      .toBe("idle-down");
  });
});

describe("walkClipForDirection", () => {
  it("choisit l'axe dominant", () => {
    expect(walkClipForDirection(CHARACTER, -1, 0.2, ALIASES)?.name).toBe("walk-left");
    expect(walkClipForDirection(CHARACTER, 0.1, 1, ALIASES)?.name).toBe("walk-down");
  });

  it("retombe sur idle-down si la direction n'a pas de clip", () => {
    // walk-up absent du personnage de test
    expect(walkClipForDirection(CHARACTER, 0, -1, ALIASES)?.name).toBe("idle-down");
  });
});

describe("clipKey", () => {
  it("préfixe par le personnage", () => {
    expect(clipKey("worker-a", "type")).toBe("worker-a:type");
  });
});
