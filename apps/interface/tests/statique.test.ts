// Garde statique des sources ET des bundles committés : rendu par React uniquement, aucun accès
// direct au réseau, au stockage ou à une URL externe.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const ICI = process.cwd();
const SRC = join(ICI, "src");
const DEPOT = join(ICI, "..", "..");
const BUNDLES = ["acp-interface", "acp-catalogue"].map((nom) =>
  join(DEPOT, "hermes", "plugins", nom, "dashboard", "dist", "index.js"),
);

function fichiers(dossier: string): string[] {
  return readdirSync(dossier, { withFileTypes: true }).flatMap((e): string[] =>
    e.isDirectory() ? fichiers(join(dossier, e.name)) : /\.tsx?$/.test(e.name) ? [join(dossier, e.name)] : [],
  );
}

/** Identifiants et propriétés interdits, relevés sur l'arbre syntaxique (commentaires ignorés). */
const INTERDITS = new Set([
  "dangerouslySetInnerHTML",
  "innerHTML",
  "outerHTML",
  "insertAdjacentHTML",
  "eval",
  "localStorage",
  "sessionStorage",
  "XMLHttpRequest",
  "WebSocket",
  "importScripts",
]);

export function constatsSource(nom: string, source: string): string[] {
  const fichier = ts.createSourceFile(nom, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const trouves: string[] = [];
  function visiter(n: ts.Node): void {
    if ((ts.isIdentifier(n) || ts.isPrivateIdentifier(n)) && INTERDITS.has(n.text)) trouves.push(n.text);
    if (ts.isNewExpression(n) && n.expression.getText(fichier) === "Function") trouves.push("new Function");
    if (ts.isCallExpression(n) && ["fetch", "window.fetch", "globalThis.fetch"].includes(n.expression.getText(fichier))) {
      trouves.push("fetch direct");
    }
    if ((ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) && /https?:\/\/|\/\/[a-z0-9-]+\./i.test(n.text)) {
      trouves.push(`URL externe « ${n.text} »`);
    }
    if (ts.isPropertyAccessExpression(n) && n.name.text === "write" && n.expression.getText(fichier) === "document") {
      trouves.push("document.write");
    }
    ts.forEachChild(n, visiter);
  }
  visiter(fichier);
  return trouves.map((t) => `${nom} : ${t}`);
}

describe("garde statique", () => {
  it("aucune source n'emploie d'API interdite", () => {
    const tous = fichiers(SRC).flatMap((f) => constatsSource(f.slice(SRC.length + 1), readFileSync(f, "utf8")));
    expect(tous).toEqual([]);
  });

  it("témoins négatifs : chaque interdit est vu", () => {
    const temoin = [
      "const a = <div dangerouslySetInnerHTML={{ __html: x }} />;",
      "el.innerHTML = x;",
      "eval('1');",
      "new Function('return 1');",
      "fetch('/api');",
      "localStorage.setItem('a', 'b');",
      "const u = 'https://exemple.test/police.css';",
      "document.write('x');",
      "// innerHTML dans un commentaire n'est pas un appel",
    ].join("\n");
    expect(constatsSource("temoin.tsx", temoin)).toEqual([
      "temoin.tsx : dangerouslySetInnerHTML",
      "temoin.tsx : innerHTML",
      "temoin.tsx : eval",
      "temoin.tsx : new Function",
      "temoin.tsx : fetch direct",
      "temoin.tsx : localStorage",
      "temoin.tsx : URL externe « https://exemple.test/police.css »",
      "temoin.tsx : document.write",
    ]);
  });

  it("les bundles committés n'embarquent ni API interdite, ni URL, ni React", () => {
    for (const chemin of BUNDLES) {
      const code = readFileSync(chemin, "utf8");
      expect(constatsSource(chemin.slice(DEPOT.length + 1), code)).toEqual([]);
      expect(code).not.toMatch(/react\.production|react-dom|__SECRET_INTERNALS|node_modules/);
      expect(code.startsWith("/* acp-")).toBe(true);
    }
  });
});
