import { beforeEach, describe, expect, it } from "vitest";
import { h } from "../src/react";
import { Accueil } from "../src/interface/Accueil";
import { oublierMeta, ROUTE_META, ROUTE_SESSIONS } from "../src/api";
import { CATALOGUE } from "./catalogue-chaines";
import { META, SESSIONS } from "./fixtures";
import { ApiErrorHermes, installerSdk, rendre, textesHorsCatalogue } from "./sdk-factice";

beforeEach(() => oublierMeta());

function carte(racine: HTMLElement, id: string): Element | null | undefined {
  return racine.querySelector(`#${id}`)?.parentElement;
}

describe("Accueil", () => {
  it("affiche l'état relevé, en français, sans texte hors du catalogue", async () => {
    installerSdk({ [ROUTE_META]: META, [ROUTE_SESSIONS]: SESSIONS });
    window.__HERMES_BASE_PATH__ = "/hermes";
    const r = await rendre(<Accueil />);
    const texte = r.texte();
    for (const attendu of [
      "Accueil",
      "Version en service",
      "0.21.5",
      "Conforme",
      "fca358f12efd",
      "Active",
      "À jour",
      "Plan du site vitrine",
      "Sans titre",
      "Non configuré",
      "Discussion",
      "Kanban",
    ]) {
      expect(texte).toContain(attendu);
    }
    // Aucun commit déployé connu : « Inconnu », jamais une valeur inventée.
    const ligneCommit = [...r.racine.querySelectorAll(".acp-ligne")].find((l) =>
      l.textContent?.startsWith("Commit déployé"),
    );
    expect(ligneCommit?.textContent).toBe("Commit déployéInconnu");
    // Bloc catalogue absent de /v1/meta : inconnu.
    expect(carte(r.racine, "acp-accueil-catalogue")?.textContent).toContain("Inconnu");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    const liens = [...r.racine.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(liens).toContain("/hermes/projets");
    expect(liens).toContain("/hermes/chat");
    expect(liens).toContain("/hermes/catalogue");
    expect(r.racine.querySelector("[data-acp-racine='accueil'] h1")?.textContent).toBe("Accueil");
    r.demonter();
  });

  it.each([
    ["divergent", "Modifiée par le propriétaire"],
    ["depose", "Déposée à ce démarrage"],
    ["non_ordinaire", "Fichier non ordinaire"],
    ["autre-chose", "Inconnu"],
  ])("persona %s", async (etat, libelle) => {
    installerSdk({ [ROUTE_META]: { ...META, demarrage: { soul: { etat } } }, [ROUTE_SESSIONS]: SESSIONS });
    const r = await rendre(<Accueil />);
    expect(carte(r.racine, "acp-accueil-persona")?.textContent).toContain(libelle);
    r.demonter();
  });

  it("montre le résumé du catalogue quand /v1/meta le fournit", async () => {
    installerSdk({
      [ROUTE_META]: { ...META, catalogue: { skills_actives: 17, skills_attendues: 17, context7: "connecte" } },
      [ROUTE_SESSIONS]: SESSIONS,
    });
    const r = await rendre(<Accueil />);
    const bloc = carte(r.racine, "acp-accueil-catalogue");
    expect(bloc?.textContent).toContain("17");
    expect(bloc?.textContent).toContain("Connecté");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("dit « Inconnu » pour chaque valeur absente, et la garde absente", async () => {
    installerSdk({
      [ROUTE_META]: {
        contrat: "acp-poste/1",
        garde_execution: {
          presente_dans_le_gestionnaire: false,
          alerte: "Garde d'exécution absente du processus du tableau de bord.",
        },
      },
      [ROUTE_SESSIONS]: { sessions: [] },
    });
    const r = await rendre(<Accueil />);
    const hermes = carte(r.racine, "acp-accueil-hermes");
    // Version, version testée, condensat, commit : 4 « Inconnu » ; conformité : pastille « Inconnu ».
    expect(hermes?.querySelectorAll(".acp-inconnu").length).toBe(4);
    expect(hermes?.querySelector(".acp-pastille")?.textContent).toBe("Inconnu");
    const garde = carte(r.racine, "acp-accueil-garde");
    expect(garde?.textContent).toContain("Absente");
    expect(garde?.textContent).toContain("Garde d'exécution absente");
    expect(r.texte()).toContain("Aucune session pour l'instant.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("dit que l'état est indisponible quand /v1/meta ne répond pas, sans rien inventer", async () => {
    installerSdk({ [ROUTE_SESSIONS]: SESSIONS });
    const r = await rendre(<Accueil />);
    expect(r.texte()).toContain("L'état de la plateforme est indisponible");
    expect(r.racine.querySelector("#acp-accueil-hermes")).toBeNull();
    expect(r.racine.querySelector("[role='alert']")?.textContent).toContain("404");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("enveloppe une erreur réseau en français", async () => {
    installerSdk({
      [ROUTE_META]: META,
      [ROUTE_SESSIONS]: new ApiErrorHermes("Hermes dashboard cannot reach the Hermes service.", 0,
                                           "TypeError: Failed to fetch"),
    });
    const r = await rendre(<Accueil />);
    expect(carte(r.racine, "acp-accueil-sessions")?.textContent).toContain("Le tableau de bord ne répond pas.");
    r.demonter();
  });
});
