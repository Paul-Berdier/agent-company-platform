// Décompte des chaînes de Hermes restées en anglais, mesuré sur les fichiers EXTRAITS DE L'IMAGE
// épinglée (jamais sur un clone) : ce qu'ACP ne traduit pas, il le compte et le publie
// (docs/refonte/interface.md). Rien n'est traduit ni modifié ici.
//
//   node apps/interface/outils/decompte-traductions.mjs <dossier extrait> [--json f.json] [--markdown f.md]
//
// <dossier extrait> reproduit /opt/hermes : web/src/i18n/{en,fr}.ts, web/src/App.tsx,
// web/src/{pages,components}/**/*.tsx et locales/{en,fr}.yaml (docker create + docker cp, voir
// docs/refonte/interface.md). Mesures :
//   1. clés de en.ts absentes de fr.ts, par section (fr.ts évalué avec defineLocale remplacé par
//      l'identité : une clé absente retombe sur l'anglais à l'affichage) ;
//   2. clés de fr.ts dont la valeur est identique à l'anglais (souvent des noms propres : comptées,
//      pas jugées) ;
//   3. libellés de navigation SANS labelKey dans App.tsx (toujours affichés en anglais) ;
//   4. clés de locales/en.yaml absentes de locales/fr.yaml (messages statiques de l'agent) ;
//   5. APPROXIMATION : textes JSX et attributs lisibles écrits en dur dans web/src (pages et
//      composants), hors tests : au moins deux lettres latines, aucun appel de traduction.
// Non mesuré (dit dans la sortie) : bundles des greffons kanban et hermes-achievements, TUI de
// /chat, pages /auth/* du serveur, documentation /docs (iframe distante).
import { readFileSync, readdirSync, writeFileSync, existsSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import vm from "node:vm";
import ts from "typescript";

const ATTRIBUTS_LISIBLES = new Set(["title", "aria-label", "placeholder", "alt", "label"]);

function lire(chemin) {
  if (!existsSync(chemin)) throw new Error(`fichier absent de l'extraction : ${chemin}`);
  return readFileSync(chemin, "utf8");
}

/** Évalue un fichier de traduction TypeScript (en.ts, fr.ts) : types retirés par transpileModule,
 *  imports résolus à la main (defineLocale = identité), exécuté dans un contexte vm isolé. */
export function evaluerLocale(source, nomExport) {
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  const requerir = (specifier) => {
    if (/define-locale$/.test(specifier)) return { defineLocale: (x) => x };
    if (/\/types$/.test(specifier)) return {};
    if (/\/en$/.test(specifier)) return { en: {} };
    throw new Error(`import inattendu dans une traduction : ${specifier}`);
  };
  vm.runInNewContext(js, { module, exports: module.exports, require: requerir }, { timeout: 5000 });
  const valeur = module.exports[nomExport];
  if (!valeur || typeof valeur !== "object") throw new Error(`export ${nomExport} introuvable`);
  return valeur;
}

export function aplatir(valeur, prefixe = "") {
  const sortie = new Map();
  for (const [cle, v] of Object.entries(valeur)) {
    const chemin = prefixe ? `${prefixe}.${cle}` : cle;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      for (const [k, w] of aplatir(v, chemin)) sortie.set(k, w);
    } else {
      sortie.set(chemin, typeof v === "function" ? `ƒ${v.toString().length}` : v);
    }
  }
  return sortie;
}

/** Clés feuilles d'un catalogue YAML simple (cartes imbriquées de chaînes, commentaires, blocs |/>),
 *  par indentation. Contrôlé contre PyYAML dans l'image (docs/refonte/interface.md). */
export function clesYaml(texte) {
  const cles = new Set();
  const pile = [];
  let blocIndentation = null;
  for (const brute of texte.split(/\r?\n/)) {
    if (!brute.trim() || brute.trimStart().startsWith("#")) continue;
    const indentation = brute.length - brute.trimStart().length;
    if (blocIndentation !== null) {
      if (indentation > blocIndentation) continue;
      blocIndentation = null;
    }
    const m = /^(\s*)([A-Za-z0-9_.-]+|"[^"]+"|'[^']+'):(?:\s+(.*))?$/.exec(brute);
    if (!m) continue;
    const cle = m[2].replace(/^["']|["']$/g, "");
    while (pile.length && pile[pile.length - 1].indentation >= indentation) pile.pop();
    const chemin = [...pile.map((p) => p.cle), cle].join(".");
    const valeur = (m[3] ?? "").replace(/\s+#.*$/, "").trim();
    if (valeur === "") {
      pile.push({ indentation, cle });
    } else {
      cles.add(chemin);
      if (/^[|>][-+]?$/.test(valeur)) blocIndentation = indentation;
    }
  }
  return cles;
}

/** Libellés de navigation d'App.tsx sans labelKey (objets littéraux { path, label } sans labelKey). */
export function libellesSansCle(source) {
  const fichier = ts.createSourceFile("App.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const trouves = [];
  function visiter(n) {
    if (ts.isObjectLiteralExpression(n)) {
      const props = new Map(
        n.properties.filter(ts.isPropertyAssignment).map((p) => [p.name.getText(fichier), p.initializer]),
      );
      if (props.has("path") && props.has("label") && props.has("icon") && !props.has("labelKey")) {
        const label = props.get("label");
        const path = props.get("path");
        if (ts.isStringLiteral(label) && ts.isStringLiteral(path)) trouves.push({ chemin: path.text, libelle: label.text });
      }
    }
    ts.forEachChild(n, visiter);
  }
  visiter(fichier);
  return trouves;
}

function fichiersTsx(dossier) {
  if (!existsSync(dossier)) return [];
  return readdirSync(dossier).flatMap((nom) => {
    const chemin = join(dossier, nom);
    if (statSync(chemin).isDirectory()) return fichiersTsx(chemin);
    return nom.endsWith(".tsx") && !/\.test\.tsx$/.test(nom) ? [chemin] : [];
  });
}

/** APPROXIMATION lexicale : textes JSX et attributs lisibles écrits en dur (≥ 2 lettres latines). */
export function textesEnDur(source, nom) {
  const fichier = ts.createSourceFile(nom, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const trouves = [];
  const lettres = (t) => /[A-Za-z].*[A-Za-z]/.test(t);
  function visiter(n) {
    if (ts.isJsxText(n) && lettres(n.text.trim())) trouves.push(n.text.trim().replace(/\s+/g, " "));
    if (ts.isJsxAttribute(n) && ATTRIBUTS_LISIBLES.has(n.name.getText(fichier)) && n.initializer) {
      const v = ts.isJsxExpression(n.initializer) ? n.initializer.expression : n.initializer;
      if (v && ts.isStringLiteral(v) && lettres(v.text)) trouves.push(v.text);
    }
    ts.forEachChild(n, visiter);
  }
  visiter(fichier);
  return trouves;
}

export function decompter(racine) {
  const en = aplatir(evaluerLocale(lire(join(racine, "web/src/i18n/en.ts")), "en"));
  const fr = aplatir(evaluerLocale(lire(join(racine, "web/src/i18n/fr.ts")), "fr"));
  const manquantes = [...en.keys()].filter((k) => !fr.has(k)).sort();
  const identiques = [...fr.keys()].filter((k) => en.has(k) && typeof en.get(k) === "string" && fr.get(k) === en.get(k)).sort();
  const parSection = {};
  for (const k of manquantes) parSection[k.split(".")[0]] = (parSection[k.split(".")[0]] ?? 0) + 1;
  const navigation = libellesSansCle(lire(join(racine, "web/src/App.tsx")));
  const yamlEn = clesYaml(lire(join(racine, "locales/en.yaml")));
  const yamlFr = clesYaml(lire(join(racine, "locales/fr.yaml")));
  const yamlManquantes = [...yamlEn].filter((k) => !yamlFr.has(k)).sort();
  const enDur = {};
  let totalEnDur = 0;
  for (const dossier of ["web/src/pages", "web/src/components"]) {
    for (const chemin of fichiersTsx(join(racine, dossier))) {
      const textes = textesEnDur(readFileSync(chemin, "utf8"), chemin);
      if (textes.length) {
        enDur[relative(racine, chemin).split(sep).join("/")] = textes.length;
        totalEnDur += textes.length;
      }
    }
  }
  return {
    schema: "acp-decompte-traductions/1",
    tableau_de_bord: {
      cles_en: en.size,
      cles_fr: [...fr.keys()].filter((k) => en.has(k)).length,
      cles_manquantes_fr: manquantes.length,
      manquantes_par_section: Object.fromEntries(Object.entries(parSection).sort((a, b) => b[1] - a[1])),
      manquantes: manquantes,
      cles_fr_identiques_a_l_anglais: identiques.length,
      identiques: identiques,
      navigation_sans_labelKey: navigation,
      textes_en_dur_approximation: { total: totalEnDur, fichiers: Object.keys(enDur).length, par_fichier: enDur },
    },
    agent: {
      cles_en_yaml: yamlEn.size,
      cles_fr_yaml: [...yamlFr].filter((k) => yamlEn.has(k)).length,
      cles_manquantes_fr_yaml: yamlManquantes.length,
      manquantes: yamlManquantes,
    },
    non_mesure: [
      "bundles des greffons kanban et hermes-achievements (compilés, sans catalogue de traduction)",
      "TUI de la page /chat (terminal embarqué)",
      "pages /auth/* servies par le serveur de Hermes",
      "documentation /docs (iframe distante)",
    ],
  };
}

export function versMarkdown(d, entete = "") {
  const t = d.tableau_de_bord;
  const lignes = [];
  if (entete) lignes.push(entete, "");
  lignes.push("| Mesure | Valeur |", "|---|---|");
  lignes.push(`| Clés de \`en.ts\` | ${t.cles_en} |`);
  lignes.push(`| … présentes dans \`fr.ts\` | ${t.cles_fr} |`);
  lignes.push(`| … absentes de \`fr.ts\` (affichées en anglais) | **${t.cles_manquantes_fr}** |`);
  lignes.push(`| Clés de \`fr.ts\` identiques à l'anglais | ${t.cles_fr_identiques_a_l_anglais} |`);
  lignes.push(`| Libellés de navigation sans \`labelKey\` | **${t.navigation_sans_labelKey.length}** (${t.navigation_sans_labelKey.map((n) => n.libelle).join(", ")}) |`);
  lignes.push(`| Textes JSX et attributs écrits en dur (approximation) | ${t.textes_en_dur_approximation.total} dans ${t.textes_en_dur_approximation.fichiers} fichiers |`);
  lignes.push(`| Clés de \`locales/en.yaml\` (messages de l'agent) | ${d.agent.cles_en_yaml} |`);
  lignes.push(`| … absentes de \`locales/fr.yaml\` | **${d.agent.cles_manquantes_fr_yaml}** |`);
  lignes.push("", "Clés absentes de `fr.ts`, par section :", "");
  lignes.push("| Section | Clés |", "|---|---|");
  for (const [s, n] of Object.entries(t.manquantes_par_section)) lignes.push(`| \`${s}\` | ${n} |`);
  lignes.push("", `Non mesuré : ${d.non_mesure.join(" ; ")}.`);
  return lignes.join("\n") + "\n";
}

function principal(argv) {
  const racine = argv[0];
  if (!racine) {
    console.error("usage : node decompte-traductions.mjs <dossier extrait> [--json f.json] [--markdown f.md]");
    process.exit(2);
  }
  const d = decompter(racine);
  const json = JSON.stringify(d, null, 1) + "\n";
  const iJson = argv.indexOf("--json");
  const iMd = argv.indexOf("--markdown");
  if (iJson >= 0) writeFileSync(argv[iJson + 1], json, "utf8");
  if (iMd >= 0) writeFileSync(argv[iMd + 1], versMarkdown(d), "utf8");
  process.stdout.write(versMarkdown(d));
}

if (process.argv[1] && process.argv[1].endsWith("decompte-traductions.mjs")) principal(process.argv.slice(2));
