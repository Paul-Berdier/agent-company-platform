import { describe, expect, it } from "vitest";

import {
  ambientAssetPackIds,
  ambientProfile,
  effectiveFps,
  resolveAmbientView,
  selectPilotProjectId,
} from "../src/ambient-config";
import { MOCK_OVERVIEW } from "../src/mock-overview";

describe("routes ambient", () => {
  it("résout la route générale vers la salle pilote", () => {
    expect(resolveAmbientView("/ambient", null)).toBe("pilot");
    expect(resolveAmbientView("/ambient.html", null)).toBe("pilot");
  });

  it("résout une route projet et décode son identifiant", () => {
    expect(resolveAmbientView("/projects/projet%201/ambient", null)).toBe("project:projet 1");
  });

  it("conserve le paramètre historique et ignore les autres routes", () => {
    expect(resolveAmbientView("/ambient.html", "company")).toBe("company");
    expect(resolveAmbientView("/", null)).toBeNull();
    expect(resolveAmbientView("/", "company")).toBeNull();
  });
});

describe("profils ambient", () => {
  it("utilise balanced par défaut", () => {
    expect(ambientProfile("inconnu").fpsTarget).toBe(30);
  });

  it("limite le rendu à 18 FPS sur batterie", () => {
    expect(effectiveFps(60, true)).toBe(18);
    expect(effectiveFps(30, false)).toBe(30);
  });
});

describe("scène pilote", () => {
  it("sélectionne un projet comportant 4 à 8 agents", () => {
    expect(selectPilotProjectId(MOCK_OVERVIEW)).toBe("p-web");
  });

  it("ne demande pas le pack UI dans le mode autonome", () => {
    const packs = ambientAssetPackIds(MOCK_OVERVIEW, "project:p-web");
    expect(packs).toContain("dept-software-engineering");
    expect(packs).toContain("limezu-office");
    expect(packs).not.toContain("limezu-ui");
  });
});
