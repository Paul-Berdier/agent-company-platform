import { T } from "../src/chaines";

export function feuilles(valeur: unknown, chemin = "T"): Array<[string, string]> {
  if (typeof valeur === "string") return [[chemin, valeur]];
  if (valeur && typeof valeur === "object") {
    return Object.entries(valeur).flatMap(([cle, v]) => feuilles(v, `${chemin}.${cle}`));
  }
  throw new Error(`${chemin} n'est ni une chaîne ni un groupe`);
}

export const CATALOGUE = new Set(feuilles(T).map(([, v]) => v.trim()));
