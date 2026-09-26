// Construction des bundles des greffons ACP du tableau de bord de Hermes.
//
//   node esbuild.mjs           écrit les bundles sous hermes/plugins/<greffon>/dashboard/dist/
//   node esbuild.mjs --check   n'écrit rien ; échoue si un bundle committé est périmé
//
// Sorties DÉTERMINISTES (aucun horodatage, aucun chemin absolu) : deux constructions donnent les
// mêmes octets, et la CI refuse un bundle committé qui ne correspond plus aux sources. React n'est
// pas embarqué : il vient du SDK du tableau de bord (src/react.ts) ; la construction échoue si un
// fichier hors de src/ entre dans un bundle (aucun code tiers, donc aucune licence tierce à porter).
import { build } from "esbuild";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ICI = dirname(fileURLToPath(import.meta.url));
const RACINE_DEPOT = resolve(ICI, "..", "..");
const VERSION = JSON.parse(readFileSync(join(ICI, "package.json"), "utf8")).version;

export const GREFFONS = [
  { nom: "acp-interface", entree: "src/interface/index.ts" },
  { nom: "acp-catalogue", entree: "src/catalogue/index.ts" },
];

function bandeau(nom, genre) {
  const texte =
    `${nom} ${VERSION} (ACP) — ${genre} généré par apps/interface/esbuild.mjs depuis apps/interface/src ; ` +
    "ne pas modifier à la main. Aucun code tiers embarqué : React vient du SDK du tableau de bord de Hermes.";
  return `/* ${texte} */\n`;
}

export async function construire() {
  const sorties = new Map();
  const css = readFileSync(join(ICI, "src", "style", "acp.css"), "utf8").replace(/\r\n/g, "\n");
  for (const { nom, entree } of GREFFONS) {
    const resultat = await build({
      absWorkingDir: ICI,
      entryPoints: [entree],
      bundle: true,
      write: false,
      format: "iife",
      platform: "browser",
      target: "es2020",
      charset: "ascii",
      legalComments: "none",
      minify: false,
      sourcemap: false,
      jsx: "transform",
      jsxFactory: "h",
      jsxFragment: "Fragment",
      metafile: true,
      outfile: "index.js",
      logLevel: "silent",
      banner: { js: bandeau(nom, "bundle") },
    });
    const etrangers = Object.keys(resultat.metafile.inputs).filter(
      (entreeMeta) => !entreeMeta.split("/").join(sep).startsWith(`src${sep}`),
    );
    if (etrangers.length > 0) {
      throw new Error(`REFUS : ${nom} embarquerait du code hors de src/ : ${etrangers.join(", ")}`);
    }
    const dist = join(RACINE_DEPOT, "hermes", "plugins", nom, "dashboard", "dist");
    sorties.set(join(dist, "index.js"), resultat.outputFiles[0].text.replace(/\r\n/g, "\n"));
    sorties.set(join(dist, "style.css"), bandeau(nom, "style") + css);
  }
  return sorties;
}

async function principal() {
  const verifier = process.argv.includes("--check");
  const sorties = await construire();
  const perimes = [];
  for (const [chemin, contenu] of sorties) {
    const affiche = relative(RACINE_DEPOT, chemin).split(sep).join("/");
    if (verifier) {
      const actuel = existsSync(chemin) ? readFileSync(chemin, "utf8").replace(/\r\n/g, "\n") : null;
      if (actuel !== contenu) perimes.push(affiche);
    } else {
      mkdirSync(dirname(chemin), { recursive: true });
      writeFileSync(chemin, contenu, "utf8");
      console.log(`écrit : ${affiche} (${Buffer.byteLength(contenu, "utf8")} octets)`);
    }
  }
  if (verifier) {
    if (perimes.length > 0) {
      console.error("REFUS : bundles périmés (relancer npm run build --prefix apps/interface) :");
      for (const p of perimes) console.error(`  - ${p}`);
      process.exit(1);
    }
    console.log(`${sorties.size} fichiers de greffons à jour.`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  principal().catch((erreur) => {
    console.error(erreur instanceof Error ? erreur.message : erreur);
    process.exit(1);
  });
}
