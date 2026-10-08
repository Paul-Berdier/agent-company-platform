// Étape P7, partie E (cahier P7 § 11.2, correction K25) sur la forme RÉELLE de GET /v1/poste : le bloc
// executant.depots vient de la fixture partagée hermes/tests/outils/fixtures_poste/depots.json, produite par
// hermes/tests/image/test_poste_depots.py dans l'image de test (« demo » mesuré public : Codex fermé avec la raison du
// greffon ; « jetable » mesuré privé et lu avec le jeton : Codex ouvert).
// - page Poste : carte « Dépôts » (alias, visibilité mesurée, lecture, date, voies ouvertes ou fermées) ; un dépôt jamais
//   mesuré le dit, jamais « privé » par défaut ;
// - « Nouveau projet » : Codex grisé pour le dépôt qui n'est pas prouvé privé, avec la raison ; jamais envoyé ;
// - file Questions : une carte bloquée pour un secret dit que son travail reste en quarantaine, et la relance annonce
//   une branche neuve d'après la réponse de l'API seulement.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { h } from "../src/react";
import { ROUTE_CATALOGUE } from "../src/api";
import { Poste } from "../src/poste/Poste";
import { ROUTE_POSTE } from "../src/poste/api";
import { Projets } from "../src/projets/Projets";
import { voiesFermeesPourDepot } from "../src/projets/NouveauProjet";
import { ROUTE_PROJETS, ROUTE_QUESTIONS, routeRelancerCarte } from "../src/projets/api";
import type { DepotMesure } from "../src/projets/types";
import { CATALOGUE } from "./catalogue-chaines";
import { FORMES_EXECUTANT } from "./fixtures-executant";
import { ARRETEE_RELANCABLE, CATALOGUE_PROFILS, LISTE, POSTE_RELEVE, QUESTIONS } from "./fixtures-projets";
import { attendre, installerSdk, rendre, textesHorsCatalogue, type Reponse } from "./sdk-factice";

const FIXTURE = join(process.cwd(), "..", "..", "hermes", "tests", "outils", "fixtures_poste", "depots.json");
const DEPOTS = JSON.parse(readFileSync(FIXTURE, "utf8")) as DepotMesure[];
const NBSP = /[  ]/g;

function texteDe(element: Element | null | undefined): string {
  return (element?.textContent ?? "").replace(NBSP, " ").replace(/\s+/g, " ").trim();
}

function copie<T>(valeur: T): T {
  return JSON.parse(JSON.stringify(valeur)) as T;
}

/** Valeur (dd) de la ligne ``libelle`` dans la fiche du dépôt ``alias``. */
function ligne(racine: HTMLElement, alias: string, libelle: string): string {
  const fiche = racine.querySelector(`[data-acp-depot="${alias}"]`);
  const dt = [...(fiche?.querySelectorAll("dt") ?? [])].find((d) => texteDe(d) === libelle);
  if (!dt) throw new Error(`ligne « ${libelle} » absente de la fiche ${alias}`);
  return texteDe(dt.nextElementSibling);
}

function voie(racine: HTMLElement, alias: string, nom: string): string {
  return texteDe(racine.querySelector(`[data-acp-depot="${alias}"] [data-acp-voie="${nom}"]`));
}

async function saisir(element: Element | null, valeur: string): Promise<void> {
  if (!element) throw new Error("champ absent");
  const champ = element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
  await act(async () => {
    const proto = Object.getPrototypeOf(champ) as object;
    Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(champ, valeur);
    champ.dispatchEvent(new Event(champ instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}

async function soumettre(formulaire: Element | null | undefined): Promise<void> {
  if (!formulaire) throw new Error("formulaire absent");
  await act(async () => {
    formulaire.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await attendre();
}

function aller(chemin: string): void {
  window.history.replaceState(null, "", chemin);
}

afterEach(() => aller("/"));

/** Réponse réelle de GET /v1/poste (exécutant sans carte), avec le bloc executant.depots de la fixture partagée. */
function posteAvecDepots(depots: unknown): Record<string, unknown> {
  const reponse = copie(FORMES_EXECUTANT.poste_executant_sans_carte) as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
  reponse.executant.depots = depots;
  return reponse;
}

describe("page Poste : carte « Dépôts » (visibilité mesurée)", () => {
  it("chaque dépôt : visibilité, lecture, date de la mesure, voies ouvertes ou fermées avec la raison", async () => {
    aller("/poste");
    expect(DEPOTS.map((d) => d.alias)).toEqual(["demo", "jetable"]);
    installerSdk({ [ROUTE_POSTE]: posteAvecDepots(DEPOTS) });
    const r = await rendre(h(Poste, null));
    expect(texteDe(r.racine.querySelector("#acp-poste-depots")?.parentElement)).toContain(
      "Codex ne travaille que sur un dépôt prouvé privé (D83), Claude sur tout dépôt (D84).");
    expect(ligne(r.racine, "demo", "Visibilité mesurée")).toBe("Public");
    expect(ligne(r.racine, "demo", "Lecture par l'exécutant")).toBe("Réussie");
    expect(ligne(r.racine, "demo", "Mesurée")).not.toBe("Inconnu");
    expect(voie(r.racine, "demo", "poste-codex")).toBe(`Poste (Codex) Fermée ${DEPOTS[0].voies_fermees?.["poste-codex"]}`
      .replace(NBSP, " ").replace(/\s+/g, " "));
    expect(voie(r.racine, "demo", "poste-claude")).toBe("Poste (Claude) Ouverte");
    expect(ligne(r.racine, "jetable", "Visibilité mesurée")).toBe("Privé");
    expect(ligne(r.racine, "jetable", "Lecture par l'exécutant")).toBe("Réussie");
    expect(voie(r.racine, "jetable", "poste-codex")).toBe("Poste (Codex) Ouverte");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("un dépôt jamais mesuré le dit (jamais « Privé » par défaut) ; sans le bloc, les alias de l'inventaire seuls", async () => {
    aller("/poste");
    const nonMesure = [{ alias: "jetable", visibilite: null, lecture: null, verifie_le: null,
                         voies_fermees: { "poste-codex": "dépôt « jetable » non prouvé privé" } }];
    installerSdk({ [ROUTE_POSTE]: posteAvecDepots(nonMesure) });
    let r = await rendre(h(Poste, null));
    expect(ligne(r.racine, "jetable", "Visibilité mesurée")).toBe("Jamais mesurée par l'exécutant (Codex fermé)");
    expect(ligne(r.racine, "jetable", "Lecture par l'exécutant")).toBe("Inconnu");
    expect(ligne(r.racine, "jetable", "Mesurée")).toBe("Inconnu");
    expect(voie(r.racine, "jetable", "poste-codex")).toContain("Fermée");
    r.demonter();
    const sansBloc = posteAvecDepots(undefined);
    delete (sansBloc.executant as Record<string, unknown>).depots;
    installerSdk({ [ROUTE_POSTE]: sansBloc });
    r = await rendre(h(Poste, null));
    const alias = FORMES_EXECUTANT.poste_executant_sans_carte.inventaire.contenu.depots.map((d) => d.alias);
    for (const a of alias) {
      expect(ligne(r.racine, a, "Visibilité mesurée")).toBe("Jamais mesurée par l'exécutant (Codex fermé)");
      expect(ligne(r.racine, a, "Voies pour ce dépôt")).toBe("Inconnu");
    }
    r.demonter();
    // Sans le bloc, mais avec la mesure publiée dans l'inventaire : elle est montrée, les voies restent « Inconnu ».
    const mesureeDansInventaire = copie(sansBloc) as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
    mesureeDansInventaire.inventaire.contenu.depots = [
      { alias: "jetable", visibilite: "prive", lecture: "ok", verifie_le: "2026-10-02T15:40:42Z" }];
    installerSdk({ [ROUTE_POSTE]: mesureeDansInventaire });
    r = await rendre(h(Poste, null));
    expect(ligne(r.racine, "jetable", "Visibilité mesurée")).toBe("Privé");
    expect(ligne(r.racine, "jetable", "Lecture par l'exécutant")).toBe("Réussie");
    expect(ligne(r.racine, "jetable", "Voies pour ce dépôt")).toBe("Inconnu");
    r.demonter();
  });
});

describe("Nouveau projet : Codex grisé pour un dépôt non prouvé privé", () => {
  const poste = { ...copie(POSTE_RELEVE), executant: { connu: true, depots: DEPOTS } } as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
  for (const v of Object.values(poste.catalogue.voies) as Array<{ depots: string[] }>) v.depots = ["demo", "jetable"];

  it("voies fermées lues dans la vue du greffon, dépôt par dépôt", () => {
    expect(voiesFermeesPourDepot(poste, "demo")).toEqual(DEPOTS[0].voies_fermees);
    expect(voiesFermeesPourDepot(poste, "jetable")).toEqual({});
    expect(voiesFermeesPourDepot(poste, "")).toEqual({});
    expect(voiesFermeesPourDepot(null, "demo")).toEqual({});
  });

  it("dépôt public : Codex grisé avec la raison, jamais envoyé ; dépôt privé : Codex choisi", async () => {
    aller("/projets?vue=nouveau");
    const installation = installerSdk({
      [ROUTE_PROJETS]: LISTE, [ROUTE_CATALOGUE]: CATALOGUE_PROFILS, [ROUTE_POSTE]: poste,
      [`POST ${ROUTE_PROJETS}`]: { projet: { id: "p_367e23fd51b7" }, deja_lance: false },
    });
    const r = await rendre(<Projets />);
    await attendre();
    await saisir(r.racine.querySelector("#acp-projet-depot"), "jetable");
    let select = r.racine.querySelector("#acp-projet-voie") as HTMLSelectElement;
    await saisir(select, "poste-codex");
    expect(select.value).toBe("poste-codex");
    expect([...select.options].map((o) => [o.value, o.disabled])).toEqual([["poste-claude", false],
                                                                         ["poste-codex", false]]);
    expect(r.racine.querySelector("#acp-projet-voie-fermee")).toBeNull();
    // Dépôt « demo » (mesuré public) : Codex grisé, la voie retenue repasse sur Claude, la raison est dite.
    await saisir(r.racine.querySelector("#acp-projet-depot"), "demo");
    select = r.racine.querySelector("#acp-projet-voie") as HTMLSelectElement;
    expect([...select.options].map((o) => [o.value, o.disabled])).toEqual([["poste-claude", false],
                                                                         ["poste-codex", true]]);
    expect(select.value).toBe("poste-claude");
    expect(select.getAttribute("aria-describedby")).toBe("acp-projet-voie-fermee");
    const raison = texteDe(r.racine.querySelector("#acp-projet-voie-fermee"));
    expect(raison).toContain("Poste (Codex) Fermé pour ce dépôt (grisé dans la liste)");
    expect(raison).toContain("non prouvé privé");
    // Même forcée (option grisée sélectionnée par programme), une voie fermée pour ce dépôt n'est jamais retenue.
    await saisir(select, "poste-codex");
    await saisir(r.racine.querySelector("#acp-projet-titre-champ"), "Outil");
    await saisir(r.racine.querySelector("#acp-projet-objectif"), "Écrire outil.py.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    await soumettre(r.racine.querySelector("form"));
    const [lancement] = installation.requetes.filter((q) => q.methode === "POST");
    expect((lancement?.corps as { depot: string; exploration: { voie: string } }).depot).toBe("demo");
    expect((lancement?.corps as { exploration: { voie: string } }).exploration.voie).toBe("poste-claude");
    r.demonter();
  });
});

describe("Nouveau projet : aucun exécutant ouvert pour le dépôt", () => {
  it("la page le dit et le projet part sans exploration (jamais une voie fermée envoyée)", async () => {
    aller("/projets?vue=nouveau");
    const toutesFermees = [{ ...DEPOTS[0], voies_fermees: { "poste-codex": "fermée (test)", "poste-claude": "fermée (test)" } }];
    const poste = { ...copie(POSTE_RELEVE), executant: { connu: true, depots: toutesFermees } } as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
    for (const v of Object.values(poste.catalogue.voies) as Array<{ depots: string[] }>) v.depots = ["demo"];
    const installation = installerSdk({
      [ROUTE_PROJETS]: LISTE, [ROUTE_CATALOGUE]: CATALOGUE_PROFILS, [ROUTE_POSTE]: poste,
      [`POST ${ROUTE_PROJETS}`]: { projet: { id: "p_367e23fd51b7" }, deja_lance: false },
    });
    const r = await rendre(<Projets />);
    await attendre();
    await saisir(r.racine.querySelector("#acp-projet-depot"), "demo");
    expect(texteDe(r.racine.querySelector("#acp-projet-sans-exploration"))).toBe(
      "Aucun exécutant ouvert pour ce dépôt. Le projet part sans exploration du dépôt.");
    const select = r.racine.querySelector("#acp-projet-voie") as HTMLSelectElement;
    expect([...select.options].every((o) => o.disabled)).toBe(true);
    await saisir(r.racine.querySelector("#acp-projet-titre-champ"), "Outil");
    await saisir(r.racine.querySelector("#acp-projet-objectif"), "Écrire outil.py.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    await soumettre(r.racine.querySelector("form"));
    const [lancement] = installation.requetes.filter((q) => q.methode === "POST");
    expect(lancement?.corps).not.toHaveProperty("exploration");
    expect((lancement?.corps as { depot: string }).depot).toBe("demo");
    r.demonter();
  });
});

describe("file Questions : carte bloquée pour un secret (K25)", () => {
  const secret = { ...ARRETEE_RELANCABLE, abandonnee: false, quarantaine: true,
                   raison: "Secret détecté dans la production de l'exécutant." };
  const file = { ...QUESTIONS, bloquees: [...QUESTIONS.bloquees, secret],
                 compteurs: { ...QUESTIONS.compteurs, arretees: 2, a_traiter: 4 } };

  it("la quarantaine est dite ; la relance annonce une branche neuve d'après la réponse", async () => {
    aller("/projets?vue=questions");
    const route = routeRelancerCarte("acp-outil-3dd5", "t_5e6f7a8b");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: file,
      [`POST ${route}`]: { carte: "t_5e6f7a8b", relancee: true, statut_apres: "ready", session_neuve: true,
                           branche_neuve: true },
    };
    installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    const section = r.racine.querySelector("#acp-questions-bloquees")?.parentElement;
    expect(texteDe(section)).toContain("Le travail fautif reste en quarantaine sur l'exécutant, jamais intégré ni poussé.");
    expect(texteDe(section)).not.toContain("sur la branche déjà commencée");
    reponses[ROUTE_QUESTIONS] = { ...QUESTIONS };
    await soumettre(r.racine.querySelector("#acp-relance-t_5e6f7a8b")?.closest("form"));
    expect(texteDe(section)).toContain(
      "La carte repart sur une branche neuve, en session neuve. Le travail en quarantaine n'est pas repris.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});
