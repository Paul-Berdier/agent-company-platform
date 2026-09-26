// Bundles déterministes et à jour : deux constructions donnent les mêmes octets, identiques aux
// fichiers committés sous hermes/plugins (la CI refait la même vérification par git diff).
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
// @ts-expect-error — module JavaScript de construction, sans déclaration de types.
import { construire } from "../esbuild.mjs";

describe("bundles", () => {
  it("sont déterministes et identiques aux fichiers committés", async () => {
    const premiere: Map<string, string> = await construire();
    const seconde: Map<string, string> = await construire();
    // Trois greffons (acp-interface, acp-catalogue, acp-projets), chacun un script et une feuille de style.
    expect([...premiere.keys()].length).toBe(6);
    for (const [chemin, contenu] of premiere) {
      expect(seconde.get(chemin)).toBe(contenu);
      expect(readFileSync(chemin, "utf8").replace(/\r\n/g, "\n")).toBe(contenu);
      expect(contenu).not.toMatch(/\r/);
    }
  });

  it("chaque bundle s'enregistre sous son nom de manifeste", async () => {
    const sorties: Map<string, string> = await construire();
    const js = [...sorties].filter(([chemin]) => chemin.endsWith("index.js"));
    const nomDe = (chemin: string) => /hermes[\\/]plugins[\\/](acp-[a-z]+)[\\/]/.exec(chemin)?.[1];
    expect(js.map(([chemin]) => nomDe(chemin))).toEqual(["acp-interface", "acp-catalogue", "acp-projets"]);
    for (const [chemin, contenu] of js) {
      const nom = nomDe(chemin);
      const manifeste = JSON.parse(readFileSync(chemin.replace(/dist[\\/]index\.js$/, "manifest.json"), "utf8"));
      expect(manifeste.name).toBe(nom);
      expect(contenu).toContain(`nom: "${nom}"`);
    }
  });
});
