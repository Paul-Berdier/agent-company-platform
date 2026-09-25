import { describe, expect, it } from "vitest";
import { act } from "react";
import { h } from "../src/react";
import { Catalogue } from "../src/catalogue/Catalogue";
import { ROUTE_CATALOGUE, ROUTE_SKILLS } from "../src/api";
import { CATALOGUE } from "./catalogue-chaines";
import { CATALOGUE_ACP, SKILLS_HERMES } from "./fixtures";
import { installerSdk, rendre, textesHorsCatalogue } from "./sdk-factice";

function noms(racine: HTMLElement, id: string): string[] {
  const carte = racine.querySelector(`#${id}`)?.parentElement;
  return [...(carte?.querySelectorAll(".acp-entree__nom") ?? [])].map((e) => e.textContent ?? "");
}

async function choisir(racine: HTMLElement, id: string, valeur: string): Promise<void> {
  const select = racine.querySelector(`#${id}`) as HTMLSelectElement;
  await act(async () => {
    select.value = valeur;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("Catalogue", () => {
  it("rend le verrou en lecture seule, en français, sans aucun bouton", async () => {
    installerSdk({ [ROUTE_CATALOGUE]: CATALOGUE_ACP, [ROUTE_SKILLS]: SKILLS_HERMES });
    const r = await rendre(<Catalogue />);
    expect(noms(r.racine, "acp-catalogue-skills")).toEqual([
      "emil-design-eng",
      "security-review",
      "browser-qa",
      "mle-workflow",
    ]);
    const texte = r.texte();
    for (const attendu of [
      "emilkowalski/skills@d16ebe60",
      "MIT",
      "Hermes (Railway)",
      "Poste Windows",
      "Active",
      "Désactivée",
      "Candidate pour le poste, non planifiée",
      "Prévu au poste (P8)",
      "Hors v1",
      "Site web",
      "Données",
      "mcp__context7__query_docs",
      "Hors ligne",
      "ma-skill-locale",
      "codex",
      "1 désactivation n'est pas appliquée : codex.",
    ]) {
      expect(texte).toContain(attendu);
    }
    // Un état inconnu du greffon est montré tel quel, comme donnée, jamais traduit au hasard.
    expect(texte).toContain("etat-futur");
    expect(r.racine.querySelectorAll("button").length).toBe(0);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    // Vu par Hermes : 3 skills, 2 activées, 1 désactivée.
    const hermes = r.racine.querySelector("#acp-catalogue-hermes")?.parentElement;
    expect([...(hermes?.querySelectorAll(".acp-ligne dd") ?? [])].map((d) => d.textContent)).toEqual(["3", "2", "1"]);
    r.demonter();
  });

  it("filtre par profil, source et cible", async () => {
    installerSdk({ [ROUTE_CATALOGUE]: CATALOGUE_ACP, [ROUTE_SKILLS]: SKILLS_HERMES });
    const r = await rendre(<Catalogue />);
    await choisir(r.racine, "acp-filtre-profil", "donnees");
    expect(noms(r.racine, "acp-catalogue-skills")).toEqual(["mle-workflow"]);
    await choisir(r.racine, "acp-filtre-profil", "");
    await choisir(r.racine, "acp-filtre-cible", "poste");
    expect(noms(r.racine, "acp-catalogue-skills")).toEqual(["browser-qa"]);
    expect(noms(r.racine, "acp-catalogue-mcp")).toEqual(["playwright", "figma"]);
    await choisir(r.racine, "acp-filtre-source", "emilkowalski/skills");
    expect(r.racine.querySelector("#acp-catalogue-skills")?.parentElement?.textContent).toContain(
      "Aucune entrée pour ces filtres.",
    );
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("dit que le catalogue est indisponible sans /v1/catalogue, et montre quand même ce que voit Hermes", async () => {
    installerSdk({ [ROUTE_SKILLS]: SKILLS_HERMES });
    const r = await rendre(<Catalogue />);
    expect(r.texte()).toContain("Catalogue ACP indisponible : le greffon acp-poste ne sert pas la route /v1/catalogue.");
    expect(r.racine.querySelector("#acp-catalogue-skills")).toBeNull();
    expect(r.racine.querySelector("#acp-catalogue-hermes")).not.toBeNull();
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("ne plante pas sur un catalogue vide ou mal formé", async () => {
    installerSdk({ [ROUTE_CATALOGUE]: { skills: "pas une liste", mcp: null }, [ROUTE_SKILLS]: [] });
    const r = await rendre(<Catalogue />);
    expect(r.texte()).toContain("Aucune entrée pour ces filtres.");
    expect(r.texte()).toContain("Aucun écart relevé.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});
