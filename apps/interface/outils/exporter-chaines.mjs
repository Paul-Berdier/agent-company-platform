// Exporte en JSON (sur la sortie standard) toutes les chaînes du catalogue src/chaines.ts, pour le
// test navigateur (hermes/tests/e2e/test_interface_fr.py) : chaque nœud de texte des greffons doit
// en faire partie, ou appartenir à un élément data-acp-donnee.
//
//   node --experimental-strip-types apps/interface/outils/exporter-chaines.mjs
//
// chaines.ts ne contient que des chaînes (tests/chaines.test.ts) : Node l'importe sans compilation.
import { T } from "../src/chaines.ts";

function feuilles(valeur, chemin = "T") {
  if (typeof valeur === "string") return [[chemin, valeur]];
  if (valeur && typeof valeur === "object") {
    return Object.entries(valeur).flatMap(([cle, v]) => feuilles(v, `${chemin}.${cle}`));
  }
  throw new Error(`${chemin} n'est ni une chaîne ni un groupe`);
}

process.stdout.write(JSON.stringify(Object.fromEntries(feuilles(T)), null, 1) + "\n");
