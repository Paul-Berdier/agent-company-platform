// Page Poste et page Questions de l'étape P6 sur les formes RÉELLES des routes (tests/fixtures-executant.ts) :
// isolement mesuré (« Inconnu » sans sonde), conditions d'usage, carte en cours, voies fermées, branches prêtes avec
// la commande de récupération (aucun bouton « Pousser »), revues des fichiers de pilotage (« Accepter », « Refuser »
// avec un motif exigé) ; chaque bouton appelle la route réelle ; aucun texte hors du catalogue.
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { h } from "../src/react";
import { Poste } from "../src/poste/Poste";
import { Projets } from "../src/projets/Projets";
import { ROUTE_POSTE } from "../src/poste/api";
import { ROUTE_PROJETS, ROUTE_QUESTIONS, routeAccepterRevue, routeRefuserRevue } from "../src/projets/api";
import { CATALOGUE } from "./catalogue-chaines";
import { FORMES_EXECUTANT } from "./fixtures-executant";
import { LISTE } from "./fixtures-projets";
import { attendre, installerSdk, rendre, textesHorsCatalogue } from "./sdk-factice";

const F = JSON.parse(JSON.stringify(FORMES_EXECUTANT)) as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const NBSP = /[  ]/g;

function texteDe(element: Element | null | undefined): string {
  return (element?.textContent ?? "").replace(NBSP, " ").replace(/\s+/g, " ").trim();
}

function aller(chemin: string): void {
  window.history.replaceState(null, "", chemin);
}

/** Section d'une carte : l'identifiant est porté par son titre (Carte, src/commun.tsx). */
function zone(racine: HTMLElement, id: string): Element | null {
  return racine.querySelector(`section[aria-labelledby="${id}"]`);
}

/** Valeur (dd) de la ligne dont le libellé (dt) est ``libelle`` dans la section ``id``. */
function valeur(racine: HTMLElement, id: string, libelle: string): string {
  const lignes = [...(zone(racine, id)?.querySelectorAll("dt") ?? [])];
  const dt = lignes.find((d) => texteDe(d) === libelle);
  if (!dt) throw new Error(`ligne « ${libelle} » absente de ${id}`);
  return texteDe(dt.nextElementSibling);
}

function boutons(racine: HTMLElement): string[] {
  return [...racine.querySelectorAll("button")].map((b) => (b.textContent ?? "").trim());
}

function bouton(racine: HTMLElement, libelle: string): HTMLButtonElement {
  const trouve = [...racine.querySelectorAll("button")].find((b) => (b.textContent ?? "").trim() === libelle);
  if (!trouve) throw new Error(`bouton « ${libelle} » absent`);
  return trouve as HTMLButtonElement;
}

async function cliquer(element: Element | null | undefined): Promise<void> {
  if (!element) throw new Error("élément absent");
  await act(async () => {
    (element as HTMLElement).click();
  });
  await attendre();
}

async function saisir(element: Element | null, valeur: string): Promise<void> {
  if (!element) throw new Error("champ absent");
  const champ = element as HTMLTextAreaElement;
  await act(async () => {
    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(champ) as object, "value")?.set?.call(champ, valeur);
    champ.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function ecritures(installation: { requetes: Array<{ methode: string; url: string; corps: unknown }> }) {
  return installation.requetes.filter((r) => r.methode !== "GET").map((r) => [r.methode, r.url, r.corps]);
}

beforeEach(() => aller("/poste"));
afterEach(() => aller("/poste"));

describe("page Poste : exécutant Railway (P6)", () => {
  it("isolement mesuré, conditions, carte en cours, voies fermées ; aucun bouton « Pousser »", async () => {
    installerSdk({ [ROUTE_POSTE]: F.poste_executant_carte });
    const r = await rendre(h(Poste, null));
    expect(texteDe(zone(r.racine, "acp-poste-etat"))).toContain("État de l'exécutant Railway");
    const I = "acp-poste-isolement";
    expect(valeur(r.racine, I, "Régime")).toBe("B : bac à sable Linux refusé par la plateforme");
    expect(valeur(r.racine, I, "Réseau des commandes")).toBe("Non coupé");
    expect(valeur(r.racine, I, "Processus visibles dans le bac à sable")).toBe("Oui");
    expect(valeur(r.racine, I, "Identifiants séparés par compte")).toBe("Prouvé par la sonde");
    expect(valeur(r.racine, I, "Écriture Codex")).toBe("Refusée");
    expect(valeur(r.racine, I, "Écriture Claude")).toBe("Admise");
    expect(valeur(r.racine, "acp-poste-conditions", "Codex")).toBe("Décidé le 2026-10-01");
    expect(valeur(r.racine, "acp-poste-conditions", "Cartes par jour")).toBe("20");
    const C = "acp-poste-carte-en-cours";
    expect(valeur(r.racine, C, "Peut exécuter")).toBe("Oui");
    expect(valeur(r.racine, C, "Voies annoncées")).toBe("poste-claude, poste-integration");
    expect(valeur(r.racine, C, "Modèle demandé")).toBe("opus");
    expect(valeur(r.racine, C, "Modèle servi")).toBe("Inconnu");  // jamais inventé : rien d'observé encore
    expect(valeur(r.racine, C, "Statut")).toBe("running");
    expect(valeur(r.racine, C, "Réclamée par l'exécutant")).toBe("Oui");
    expect(texteDe(zone(r.racine, "acp-poste-voies-fermees"))).toContain("poste-codex");
    expect(zone(r.racine, "acp-poste-bac")).toBeNull();  // le bac à sable Windows ne vaut pas sous Linux
    expect(boutons(r.racine).some((b) => /pousser/i.test(b))).toBe(false);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
  });

  it("branche prête : commande de récupération copiée, jamais un push", async () => {
    installerSdk({ [ROUTE_POSTE]: F.poste_executant_branche });
    const copies: string[] = [];
    Object.defineProperty(globalThis.navigator, "clipboard", {
      configurable: true, value: { writeText: async (texte: string) => { copies.push(texte); } },
    });
    const r = await rendre(h(Poste, null));
    const branches = texteDe(zone(r.racine, "acp-poste-branches"));
    const commande = F.poste_executant_branche.executant.branches_pretes[0].commande as string;
    expect(branches).toContain(F.poste_executant_branche.executant.branches_pretes[0].branche);
    expect(branches).toContain(commande);
    await cliquer(bouton(r.racine, "Copier la commande"));
    expect(copies).toEqual([commande]);
    expect(r.texte()).toContain("Commande copiée.");
    expect(boutons(r.racine).some((b) => /pousser/i.test(b))).toBe(false);
  });

  it("sans sonde : l'isolement est « Inconnu » et l'écriture refusée", async () => {
    const sansSonde = JSON.parse(JSON.stringify(F.poste_executant_sans_carte));
    sansSonde.executant.isolement = null;
    installerSdk({ [ROUTE_POSTE]: sansSonde });
    const r = await rendre(h(Poste, null));
    expect(texteDe(zone(r.racine, "acp-poste-isolement"))).toContain(
      "Inconnu : aucune sonde de plateforme publiée ; l'écriture est refusée.");
    expect(texteDe(zone(r.racine, "acp-poste-carte-en-cours"))).toContain("Aucune carte en main.");
  });

  it("poste Windows de P5 : aucun bloc d'isolement Linux, la page garde le bac à sable Codex", async () => {
    const windows = JSON.parse(JSON.stringify(F.poste_executant_sans_carte));
    windows.executant = { ...windows.executant, plateforme: "windows", hote: "pc", isolement: null, conditions: null };
    installerSdk({ [ROUTE_POSTE]: windows });
    const r = await rendre(h(Poste, null));
    expect(zone(r.racine, "acp-poste-isolement")).toBeNull();
    expect(texteDe(zone(r.racine, "acp-poste-etat"))).toContain("État du poste");
    expect(texteDe(zone(r.racine, "acp-poste-conditions"))).toContain(
      "Non publiées par ce poste (inventaire de l'étape P5).");
  });
});

describe("page Questions : revues des fichiers de pilotage (P6)", () => {
  it("liste la revue sans faux aperçu du diff ; « Accepter » appelle la route", async () => {
    aller("/projets?vue=questions");
    const revue = F.questions_revue.revues[0];
    const installation = installerSdk({
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: F.questions_revue,
      [`POST ${routeAccepterRevue(revue.tableau, revue.carte)}`]: F.revue_acceptee,
    });
    const r = await rendre(h(Projets, null));
    const texte = texteDe(zone(r.racine, "acp-questions-revues"));
    expect(texte).toContain(".github/workflows/ci.yml");
    expect(texte).toContain("CLAUDE.md");
    expect(texte).toContain("Le diff reste sur l'exécutant");
    expect(valeur(r.racine, "acp-questions-revues", "Modification")).toBe("1 fichier(s)12 ajout(s)0 retrait(s)");
    // « Refuser » exige un motif.
    expect(bouton(r.racine, "Refuser").disabled).toBe(true);
    await cliquer(bouton(r.racine, "Accepter"));
    expect(ecritures(installation)).toEqual([["POST", routeAccepterRevue(revue.tableau, revue.carte), {}]]);
    expect(r.texte()).toContain("Revue acceptée : la carte est terminée.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
  });

  it("« Refuser » envoie le motif", async () => {
    aller("/projets?vue=questions");
    const revue = F.questions_revue.revues[0];
    const installation = installerSdk({
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: F.questions_revue,
      [`POST ${routeRefuserRevue(revue.tableau, revue.carte)}`]: { carte: revue.carte, etat: "ready" },
    });
    const r = await rendre(h(Projets, null));
    await saisir(r.racine.querySelector(`#acp-motif-revue-${revue.carte}`), "Ne touche pas au workflow de CI.");
    await act(async () => {
      r.racine.querySelector(`#acp-motif-revue-${revue.carte}`)?.closest("form")
        ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await attendre();
    expect(ecritures(installation)).toEqual([["POST", routeRefuserRevue(revue.tableau, revue.carte),
                                              { motif: "Ne touche pas au workflow de CI." }]]);
    expect(r.texte()).toContain("Revue refusée : la carte revient à l'exécutant avec votre motif.");
  });
});
