// Outil de décompte des chaînes de Hermes restées en anglais (outils/decompte-traductions.mjs), sur
// des entrées synthétiques ; la mesure réelle se fait sur les fichiers extraits de l'image.
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
// @ts-expect-error — module JavaScript de l'outil, sans déclaration de types.
import { aplatir, clesYaml, decompter, evaluerLocale, libellesSansCle, textesEnDur, versMarkdown } from "../outils/decompte-traductions.mjs";

const EN = `import type { Translations } from "./types";
export const en: Translations = {
  common: { save: "Save", cancel: "Cancel", count: (n: number) => \`\${n} items\` },
  app: { brand: "Hermes Agent", nav: { sessions: "Sessions" } },
};`;
const FR = `import { defineLocale } from "./define-locale";
export const fr = defineLocale({
  common: { save: "Enregistrer" },
  app: { brand: "Hermes Agent" },
});`;
const APP = `const A = [
  { path: "/sessions", labelKey: "sessions", label: "Sessions", icon: X },
  { path: "/files", label: "Files", icon: Y },
];`;
const YAML_EN = `# commentaire
approval:
  # sous-commentaire
  denied: "✗ Denied"
  bloc: |
    ligne: pas une clé
    autre
gateway:
  busy: "busy"
`;
const YAML_FR = `approval:
  denied: "✗ Refusé"
  bloc: |
    ligne
`;

describe("décompte des traductions", () => {
  it("évalue une traduction TypeScript et l'aplatit", () => {
    const en = aplatir(evaluerLocale(EN, "en"));
    expect([...en.keys()]).toEqual(["common.save", "common.cancel", "common.count", "app.brand", "app.nav.sessions"]);
    const fr = aplatir(evaluerLocale(FR, "fr"));
    expect([...fr.keys()]).toEqual(["common.save", "app.brand"]);
  });

  it("lit les clés d'un catalogue YAML sans prendre le contenu d'un bloc pour des clés", () => {
    expect([...clesYaml(YAML_EN)].sort()).toEqual(["approval.bloc", "approval.denied", "gateway.busy"]);
  });

  it("trouve les libellés de navigation sans labelKey", () => {
    expect(libellesSansCle(APP)).toEqual([{ chemin: "/files", libelle: "Files" }]);
  });

  it("compte les textes JSX écrits en dur (approximation)", () => {
    const source = 'export const A = () => <div title="Open file"><p>Hello world</p><p>{t.x}</p><p> 42 </p></div>;';
    expect(textesEnDur(source, "a.tsx")).toEqual(["Open file", "Hello world"]);
  });

  it("assemble le décompte complet et un tableau Markdown", () => {
    const racine = mkdtempSync(join(tmpdir(), "acp-decompte-"));
    mkdirSync(join(racine, "web", "src", "i18n"), { recursive: true });
    mkdirSync(join(racine, "web", "src", "pages"), { recursive: true });
    mkdirSync(join(racine, "locales"), { recursive: true });
    writeFileSync(join(racine, "web", "src", "i18n", "en.ts"), EN);
    writeFileSync(join(racine, "web", "src", "i18n", "fr.ts"), FR);
    writeFileSync(join(racine, "web", "src", "App.tsx"), APP);
    writeFileSync(join(racine, "web", "src", "pages", "P.tsx"), "export const P = () => <p>Hello</p>;");
    writeFileSync(join(racine, "locales", "en.yaml"), YAML_EN);
    writeFileSync(join(racine, "locales", "fr.yaml"), YAML_FR);
    const d = decompter(racine);
    expect(d.tableau_de_bord.cles_en).toBe(5);
    expect(d.tableau_de_bord.cles_manquantes_fr).toBe(3);
    expect(d.tableau_de_bord.manquantes_par_section).toEqual({ common: 2, app: 1 });
    expect(d.tableau_de_bord.identiques).toEqual(["app.brand"]);
    expect(d.tableau_de_bord.textes_en_dur_approximation.total).toBe(1);
    expect(d.agent.manquantes).toEqual(["gateway.busy"]);
    const md = versMarkdown(d);
    expect(md).toContain("| … absentes de `fr.ts` (affichées en anglais) | **3** |");
    expect(md).toContain("Files");
  });
});
