import { describe, expect, it } from "vitest";
import { act } from "react";
import * as React from "react";
import { h } from "../src/react";
import { forcerFrancais, VerrouFrancais } from "../src/interface/VerrouFrancais";
import { FournisseurLangue, installerSdk, rendre } from "./sdk-factice";

describe("verrou du français (D10)", () => {
  it("passe au français au chargement puis y revient à chaque changement", async () => {
    const installation = installerSdk({}, { langue: "en" });
    let changerLangue: ((l: string) => void) | null = null;
    function Sonde() {
      const i18n = window.__HERMES_PLUGIN_SDK__!.useI18n!() as { locale: string; setLocale: (l: string) => void };
      changerLangue = i18n.setLocale;
      return React.createElement("span", { "data-langue": i18n.locale });
    }
    const r = await rendre(
      <FournisseurLangue installation={installation}>
        <VerrouFrancais />
        <Sonde />
      </FournisseurLangue>,
    );
    expect(installation.langue.valeur).toBe("fr");
    expect(r.racine.querySelector("[data-langue]")?.getAttribute("data-langue")).toBe("fr");
    await act(async () => changerLangue!("de"));
    expect(installation.langue.changements).toEqual(["fr", "de", "fr"]);
    expect(r.racine.querySelector("[data-langue]")?.getAttribute("data-langue")).toBe("fr");
    r.demonter();
  });

  it("ne demande rien si la langue est déjà le français ou si le SDK ne l'expose pas", () => {
    const appels: string[] = [];
    expect(forcerFrancais({ locale: "fr", setLocale: (l: string) => appels.push(l) })).toBe(false);
    expect(forcerFrancais({ locale: "en" })).toBe(false);
    expect(forcerFrancais(null)).toBe(false);
    expect(forcerFrancais({ locale: "en", setLocale: (l: string) => appels.push(l) })).toBe(true);
    expect(appels).toEqual(["fr"]);
  });
});
