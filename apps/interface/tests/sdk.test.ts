import { describe, expect, it, vi } from "vitest";
import * as React from "react";
import { verifierSdk, SDK_ATTENDU, type SdkHermes } from "../src/sdk";

const fetchJSON = (async () => null) as unknown as SdkHermes["fetchJSON"];
import { installer } from "../src/installer";

describe("verifierSdk", () => {
  it("accepte le SDK 1.1.0 de Hermes 0.21.5", () => {
    expect(verifierSdk({ sdkVersion: "1.1.0", React, fetchJSON })).toEqual({ ok: true, version: "1.1.0" });
    expect(SDK_ATTENDU).toBe("1.x");
  });

  it.each([
    [undefined, "absent"],
    [null, "absent"],
    [{ React, fetchJSON }, "absent"],
    [{ sdkVersion: 1.1, React, fetchJSON }, "absent"],
    [{ sdkVersion: "2.0.0", React, fetchJSON }, "2.0.0"],
    [{ sdkVersion: "0.9.0", React, fetchJSON }, "0.9.0"],
    [{ sdkVersion: "1.x", React, fetchJSON }, "1.x"],
    [{ sdkVersion: "1.1.0", fetchJSON }, "1.1.0 incomplet"],
    [{ sdkVersion: "1.1.0", React }, "1.1.0 incomplet"],
  ])("refuse %j", (sdk, trouve) => {
    expect(verifierSdk(sdk)).toEqual({ ok: false, trouve });
  });
});

describe("installer", () => {
  function registre() {
    return { register: vi.fn(), registerSlot: vi.fn() };
  }
  const Page = () => null;
  const Emplacement = () => null;

  it("enregistre la page et les emplacements quand le SDK est compatible", () => {
    const r = registre();
    window.__HERMES_PLUGINS__ = r;
    window.__HERMES_PLUGIN_SDK__ = { sdkVersion: "1.1.0", React, fetchJSON };
    expect(installer({ nom: "acp-essai", page: Page, emplacements: [["header-left", Emplacement]] })).toEqual({
      ok: true,
      version: "1.1.0",
    });
    expect(r.register).toHaveBeenCalledWith("acp-essai", Page);
    // Signature réelle de Hermes : (greffon, emplacement, composant).
    expect(r.registerSlot).toHaveBeenCalledWith("acp-essai", "header-left", Emplacement);
  });

  it("enregistre un refus explicite, jamais la page, quand le SDK est incompatible", () => {
    const r = registre();
    const avertir = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    window.__HERMES_PLUGINS__ = r;
    window.__HERMES_PLUGIN_SDK__ = { sdkVersion: "2.0.0", React, fetchJSON };
    expect(installer({ nom: "acp-essai", page: Page, emplacements: [["header-left", Emplacement]] })).toEqual({
      ok: false,
      trouve: "2.0.0",
    });
    expect(r.register).toHaveBeenCalledTimes(1);
    expect(r.register.mock.calls[0][1]).not.toBe(Page);
    expect(r.registerSlot).toHaveBeenCalledTimes(1);
    expect(r.registerSlot.mock.calls[0].slice(0, 2)).toEqual(["acp-essai", "header-banner"]);
    expect(avertir.mock.calls[0][0]).toContain("SDK du tableau de bord incompatible");
  });

  it("n'enregistre rien sans registre, ni sans React pour rendre un refus", () => {
    expect(installer({ nom: "acp-essai", page: Page })).toBeNull();
    const r = registre();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    window.__HERMES_PLUGINS__ = r;
    expect(installer({ nom: "acp-essai", page: Page })).toEqual({ ok: false, trouve: "absent" });
    expect(r.register).not.toHaveBeenCalled();
  });
});
