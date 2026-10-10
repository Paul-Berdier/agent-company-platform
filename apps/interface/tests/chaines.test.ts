// Test des chaînes, sur l'ARBRE SYNTAXIQUE TypeScript des sources (pas sur des expressions
// régulières) : aucun texte d'interface ne peut exister hors du catalogue français src/chaines.ts.
//
// Refusé dans tout fichier .tsx de src/ :
// - un texte JSX non blanc (<p>Hello</p>) ;
// - une chaîne ou un gabarit en enfant JSX ({"Hello"}, {`Hello ${x}`}) ;
// - une chaîne ou un gabarit dans un attribut lisible (title, aria-label, placeholder, alt, label…).
// Exigé dans src/chaines.ts : typographie française (espace insécable avant « : ; ! ? » et à
// l'intérieur des guillemets), aucune chaîne vide ni entourée d'espaces, aucune fonction.
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { T } from "../src/chaines";
import { feuilles } from "./catalogue-chaines";

const SRC = join(process.cwd(), "src");
const ATTRIBUTS_LISIBLES = new Set([
  "title",
  "aria-label",
  "aria-description",
  "aria-placeholder",
  "aria-roledescription",
  "aria-valuetext",
  "placeholder",
  "alt",
  "label",
]);

function fichiers(dossier: string, extensions: string[]): string[] {
  return readdirSync(dossier, { withFileTypes: true }).flatMap((e): string[] => {
    const chemin = join(dossier, e.name);
    if (e.isDirectory()) return fichiers(chemin, extensions);
    return extensions.some((x) => e.name.endsWith(x)) ? [chemin] : [];
  });
}

function estTexte(n: ts.Node): boolean {
  return ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n);
}

/** {" "} : une espace de mise en page entre deux éléments, pas un texte. */
function estBlanc(n: ts.Node): boolean {
  return (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) && n.text.trim() === "";
}

/** Constats pour un fichier TSX : « fichier:ligne motif ». */
export function constats(chemin: string, source: string): string[] {
  const fichier = ts.createSourceFile(chemin, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const trouves: string[] = [];
  const ou = (n: ts.Node) => `${relative(SRC, chemin)}:${fichier.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
  function visiter(n: ts.Node): void {
    if (ts.isJsxText(n) && n.text.trim() !== "") {
      trouves.push(`${ou(n)} texte JSX « ${n.text.trim()} »`);
    }
    if (ts.isJsxExpression(n) && n.expression && estTexte(n.expression) && !estBlanc(n.expression) &&
        !ts.isJsxAttribute(n.parent)) {
      trouves.push(`${ou(n)} chaîne en enfant JSX`);
    }
    if (ts.isJsxAttribute(n)) {
      const nom = n.name.getText(fichier);
      const valeur = n.initializer;
      if (ATTRIBUTS_LISIBLES.has(nom) && valeur) {
        const expression = ts.isJsxExpression(valeur) ? valeur.expression : valeur;
        if (expression && estTexte(expression)) trouves.push(`${ou(n)} attribut ${nom} écrit en dur`);
      }
    }
    ts.forEachChild(n, visiter);
  }
  visiter(fichier);
  return trouves;
}

const REGLES_TYPOGRAPHIQUES: Array<[RegExp, string]> = [
  [/ [:;!?]/, "espace ordinaire avant « : ; ! ? » (espace insécable attendue)"],
  [/[^  ][:;!?](\s|$)/, "ponctuation haute sans espace insécable avant"],
  [/« |«[^  ]/, "guillemet ouvrant sans espace insécable"],
  [/ »|[^  ]»/, "guillemet fermant sans espace insécable"],
  [/\.\.\./, "trois points au lieu de « … »"],
];

describe("catalogue des chaînes", () => {
  it("chaque composant ne tire son texte que de src/chaines.ts", () => {
    const tsx = fichiers(SRC, [".tsx"]);
    expect(tsx.length).toBeGreaterThanOrEqual(7);
    const tous = tsx.flatMap((f) => constats(f, readFileSync(f, "utf8")));
    expect(tous).toEqual([]);
  });

  it("le test voit bien les textes écrits en dur (témoins négatifs)", () => {
    const temoin = [
      "export const A = () => <p>Hello</p>;",
      'export const B = () => <p>{"Bonjour"}</p>;',
      "export const C = (x: string) => <p>{`Salut ${x}`}</p>;",
      'export const D = () => <a title="Ouvrir" aria-label={"Ouvrir"} href="/x" />;',
      "export const E = () => <input placeholder={`Nom`} />;",
      "export const F = () => <p>   </p>;",
      'export const G = () => <a className="acp-lien" href="/chat" />;',
      'export const H = () => <p><span>a</span>{" "}<span>b</span></p>;',
    ].join("\n");
    const trouves = constats(join(SRC, "temoin.tsx"), temoin);
    expect(trouves).toEqual([
      "temoin.tsx:1 texte JSX « Hello »",
      "temoin.tsx:2 chaîne en enfant JSX",
      "temoin.tsx:3 chaîne en enfant JSX",
      "temoin.tsx:4 attribut title écrit en dur",
      "temoin.tsx:4 attribut aria-label écrit en dur",
      "temoin.tsx:5 attribut placeholder écrit en dur",
      "temoin.tsx:8 texte JSX « a »",
      "temoin.tsx:8 texte JSX « b »",
    ]);
  });

  it("respecte la typographie française", () => {
    const fautes: string[] = [];
    for (const [chemin, valeur] of feuilles(T)) {
      if (valeur === "" || valeur !== valeur.trim()) fautes.push(`${chemin} : vide ou entourée d'espaces`);
      for (const [motif, raison] of REGLES_TYPOGRAPHIQUES) {
        // Une route d'API (« /v1/meta ») ou un identifiant n'est pas de la prose : « : » y est absent.
        if (motif.test(valeur)) fautes.push(`${chemin} : ${raison} dans « ${valeur} »`);
      }
    }
    expect(fautes).toEqual([]);
  });

  it("les règles typographiques rougissent sur des témoins", () => {
    const temoins = ["Attendu :", "Attendu:", "« Inconnu »", "Chargement...", "Vraiment ?"];
    for (const t of temoins) {
      expect(REGLES_TYPOGRAPHIQUES.some(([motif]) => motif.test(t)), t).toBe(true);
    }
    for (const t of ["Attendu :", "« Inconnu »", "Chargement…"]) {
      expect(REGLES_TYPOGRAPHIQUES.some(([motif]) => motif.test(t)), t).toBe(false);
    }
  });

  it("chaines.ts ne contient que des chaînes, lisibles par node --experimental-strip-types", () => {
    const source = readFileSync(join(SRC, "chaines.ts"), "utf8");
    const fichier = ts.createSourceFile("chaines.ts", source, ts.ScriptTarget.Latest, true);
    const interdits: string[] = [];
    function visiter(n: ts.Node): void {
      if (ts.isFunctionLike(n) || ts.isEnumDeclaration(n) || ts.isImportDeclaration(n) || ts.isTemplateExpression(n)) {
        interdits.push(ts.SyntaxKind[n.kind]);
      }
      ts.forEachChild(n, visiter);
    }
    visiter(fichier);
    expect(interdits).toEqual([]);
    expect(feuilles(T).length).toBeGreaterThan(60);
  });
});
