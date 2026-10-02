// Garde statique des sources ET des bundles committés : rendu par React uniquement, aucun accès
// direct au réseau, au stockage ou à une URL externe.
//
// Une seule exception, bornée à un dossier (étape P7, cahier P7 § 3.5 et § 9) : ``WebSocket`` dans src/jsonrpc/, le
// client du JSON-RPC NATIF du tableau de bord (/api/ws), dont l'URL vient TOUJOURS de sdk().buildWsUrl (ticket de la
// session du tableau de bord ; aucune URL écrite en dur : la règle « URL externe » reste appliquée partout). Dans les
// bundles, l'exception ne vaut que dans la section du module src/jsonrpc/ (commentaire de chemin posé par esbuild).
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const ICI = process.cwd();
const SRC = join(ICI, "src");
const DEPOT = join(ICI, "..", "..");
const BUNDLES = ["acp-interface", "acp-catalogue", "acp-projets", "acp-poste-vues"].map((nom) =>
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

/** Interdits admis, par préfixe du chemin du module (relatif à src/, séparateur « / »). */
export const EXCEPTIONS: Record<string, string[]> = { WebSocket: ["jsonrpc/"] };

function admis(module: string, interdit: string): boolean {
  const chemin = module.split("\\").join("/");
  return (EXCEPTIONS[interdit] ?? []).some((prefixe) => chemin.startsWith(prefixe));
}

/** Constats d'un module source, exceptions de son dossier retirées. */
export function constatsModule(module: string, source: string): string[] {
  return constatsSource(module, source).filter((c) => !admis(module, c.slice(module.length + 3)));
}

/** Constats d'un bundle : chaque section de module (« // src/<chemin> » posé par esbuild) est jugée avec les exceptions
 *  de son dossier ; le préambule et l'enrobage sont jugés sans exception. */
export function constatsBundle(nom: string, code: string): string[] {
  const sections = code.split(/^ {2}\/\/ src\/(.+)$/m);
  const trouves = constatsSource(nom, sections[0] ?? "");
  for (let i = 1; i < sections.length; i += 2) {
    const module = sections[i] ?? "";
    trouves.push(...constatsSource(nom, sections[i + 1] ?? "").filter((c) => !admis(module, c.slice(nom.length + 3))));
  }
  return trouves;
}

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
    const tous = fichiers(SRC).flatMap((f) => constatsModule(f.slice(SRC.length + 1), readFileSync(f, "utf8")));
    expect(tous).toEqual([]);
  });

  it("l'exception WebSocket ne vaut que dans src/jsonrpc/, et nulle part ailleurs", () => {
    const temoin = "const s = new WebSocket(url);";
    expect(constatsModule("jsonrpc/discussions.ts", temoin)).toEqual([]);
    expect(constatsModule("projets/Questions.tsx", temoin)).toEqual(["projets/Questions.tsx : WebSocket"]);
    expect(constatsModule("jsonrpc/discussions.ts", "const u = 'wss://exemple.test/api/ws';")).toEqual([
      "jsonrpc/discussions.ts : URL externe « wss://exemple.test/api/ws »",
    ]);
    const bundle = ["(() => {", "  // src/flux.ts", "  const a = new WebSocket(x);", "  // src/jsonrpc/discussions.ts",
                    "  const b = new WebSocket(y);", "})();"].join("\n");
    expect(constatsBundle("bundle.js", bundle)).toEqual(["bundle.js : WebSocket"]);
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
      expect(constatsBundle(chemin.slice(DEPOT.length + 1), code)).toEqual([]);
      expect(code).not.toMatch(/react\.production|react-dom|__SECRET_INTERNALS|node_modules/);
      expect(code.startsWith("/* acp-")).toBe(true);
    }
  });
});
