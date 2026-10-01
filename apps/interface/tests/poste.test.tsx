// Page Poste (greffon acp-poste-vues, étape P5) sur les formes RÉELLES des routes (tests/fixtures-poste.ts) : états
// du poste, code d'enrôlement affiché une fois et jamais gardé, confirmation, révocation, relevé, routage (badges,
// suggestion, validation, refus par entrée, relevé accepté, interdits, surcharges), quotas (jauges, seuil) ; chaque
// bouton appelle une route réelle ; refus de l'API rendus tels quels ; aucun texte hors du catalogue.
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { h } from "../src/react";
import { Poste } from "../src/poste/Poste";
import {
  ROUTE_CONFIRMATION,
  ROUTE_ENROLEMENT,
  ROUTE_POLITIQUE,
  ROUTE_POSTE,
  ROUTE_QUOTAS,
  ROUTE_RELEVE,
  ROUTE_RELEVE_ACCEPTE,
  ROUTE_REVOCATION,
  ROUTE_ROUTAGE,
  ROUTE_SURCHARGES,
  routeDesactiverSurcharge,
} from "../src/poste/api";
import { CATALOGUE } from "./catalogue-chaines";
import { FORMES } from "./fixtures-poste";
import { ApiErrorHermes, attendre, installerSdk, rendre, textesHorsCatalogue, type Reponse } from "./sdk-factice";

const F = JSON.parse(JSON.stringify(FORMES)) as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any

/** Réponse de l'enrôlement capturée, valable 10 minutes À PARTIR DE MAINTENANT (expire_le est absolu). */
function codeFrais(): Record<string, unknown> {
  return { ...F.code, expire_le: Math.floor(Date.now() / 1000) + 600 };
}

function texteDe(element: Element | null | undefined): string {
  return (element?.textContent ?? "").replace(/\s+/g, " ").trim();
}

function aller(recherche: string): void {
  window.history.replaceState(null, "", `/poste${recherche}`);
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
  const champ = element as HTMLInputElement | HTMLSelectElement;
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(champ) as object, "value")?.set;
    setter?.call(champ, valeur);
    champ.dispatchEvent(new Event(champ instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}

async function soumettre(formulaire: Element | null): Promise<void> {
  if (!formulaire) throw new Error("formulaire absent");
  await act(async () => {
    formulaire.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await attendre();
}

function ecritures(installation: { requetes: Array<{ methode: string; url: string; corps: unknown }> }) {
  return installation.requetes.filter((r) => r.methode !== "GET").map((r) => [r.methode, r.url, r.corps]);
}

function refus(statut: number, corps: unknown, url: string): ApiErrorHermes {
  return new ApiErrorHermes("Request failed", statut, JSON.stringify(corps), url);
}

beforeEach(() => aller(""));
afterEach(() => aller(""));

describe("vue Poste", () => {
  it("non configuré : bandeau, enrôlement, code affiché une fois puis oublié au changement de vue", async () => {
    const reponses: Record<string, Reponse> = { [ROUTE_POSTE]: F.poste_non_configure, [`POST ${ROUTE_ENROLEMENT}`]: codeFrais(),
                                                [ROUTE_ROUTAGE]: F.routage_vide };
    const installation = installerSdk(reponses);
    const r = await rendre(h(Poste, null));
    expect(texteDe(r.racine.querySelector("#acp-poste-etat")?.parentElement)).toContain("Non configuré");
    expect(r.texte()).toContain("Le poste n'a jamais été vu : enrôlez-le depuis la page Poste.");
    expect(r.racine.querySelector("[data-acp-code]")).toBeNull();
    await cliquer(bouton(r.racine, "Générer un code d'enrôlement"));
    expect(ecritures(installation)).toEqual([["POST", ROUTE_ENROLEMENT, {}]]);
    const code = r.racine.querySelector("[data-acp-code]");
    expect(texteDe(code)).toContain("acpe_CODE-DE-TEST");
    expect(texteDe(code)).toContain('& "$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd" enroler');
    expect(texteDe(code)).toContain("Ce code ne s'affiche qu'une fois");
    expect(bouton(r.racine, "Copier le code")).toBeTruthy();
    // Changement de vue, puis retour : le code a disparu (jamais stocké).
    await cliquer(r.racine.querySelector('a[href="/poste?vue=routage"]'));
    await cliquer(r.racine.querySelector('a[href="/poste"]'));
    expect(r.racine.querySelector("[data-acp-code]")).toBeNull();
    expect(r.racine.innerHTML).not.toContain("acpe_CODE-DE-TEST");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
  });

  it("code expiré : la page le dit et ne l'affiche plus", async () => {
    installerSdk({ [ROUTE_POSTE]: F.poste_non_configure,
                   [`POST ${ROUTE_ENROLEMENT}`]: { ...F.code, expire_le: Math.floor(Date.now() / 1000) - 1 } });
    const r = await rendre(h(Poste, null));
    await cliquer(bouton(r.racine, "Générer un code d'enrôlement"));
    expect(r.racine.querySelector("[data-acp-code]")).toBeNull();
    expect(r.texte()).toContain("Code expiré : générez-en un nouveau.");
  });

  it("copie : le presse-papiers reçoit le code, ou la page dit que c'est impossible", async () => {
    installerSdk({ [ROUTE_POSTE]: F.poste_non_configure, [`POST ${ROUTE_ENROLEMENT}`]: codeFrais() });
    const copies: string[] = [];
    Object.defineProperty(globalThis.navigator, "clipboard", {
      configurable: true, value: { writeText: async (t: string) => { copies.push(t); } } });
    const r = await rendre(h(Poste, null));
    await cliquer(bouton(r.racine, "Générer un code d'enrôlement"));
    await cliquer(bouton(r.racine, "Copier le code"));
    expect(copies).toEqual(["acpe_CODE-DE-TEST"]);
    expect(r.texte()).toContain("Code copié");
    Object.defineProperty(globalThis.navigator, "clipboard", { configurable: true, value: undefined });
    await cliquer(bouton(r.racine, "Copier le code"));
    expect(r.texte()).toContain("Copie impossible");
  });

  it("à confirmer : empreinte annoncée, refus rendu tel quel, puis confirmation", async () => {
    const machine = F.poste_a_confirmer.machine.machine;
    const reponses: Record<string, Reponse> = {
      [ROUTE_POSTE]: F.poste_a_confirmer,
      [`POST ${ROUTE_CONFIRMATION}`]: refus(409, F.refus_empreinte, ROUTE_CONFIRMATION),
    };
    const installation = installerSdk(reponses);
    const r = await rendre(h(Poste, null));
    expect(texteDe(r.racine.querySelector("#acp-poste-etat")?.parentElement)).toContain("À confirmer");
    expect(texteDe(r.racine.querySelector("#acp-poste-confirmation")?.parentElement)).toContain(machine.empreinte);
    await saisir(r.racine.querySelector("#acp-poste-empreinte"), "0000-0000");
    await soumettre(r.racine.querySelector("#acp-poste-confirmation")?.parentElement?.querySelector("form") ?? null);
    expect(ecritures(installation)).toEqual([["POST", ROUTE_CONFIRMATION, { machine_id: machine.id,
                                                                           empreinte: "0000-0000" }]]);
    expect(texteDe(r.racine.querySelector('[role="alert"]'))).toContain(
      "L'empreinte saisie ne correspond pas à celle du poste enrôlé");
    reponses[`POST ${ROUTE_CONFIRMATION}`] = { machine: { machine: { ...machine, etat: "actif" } } };
    await saisir(r.racine.querySelector("#acp-poste-empreinte"), machine.empreinte);
    await soumettre(r.racine.querySelector("#acp-poste-confirmation")?.parentElement?.querySelector("form") ?? null);
    expect(r.texte()).toContain("Poste confirmé : il compte désormais.");
  });

  it("en ligne : inventaire lu, relevé demandé, révocation confirmée avec un motif", async () => {
    const machine = F.poste_en_ligne.machine.machine;
    const reponses: Record<string, Reponse> = {
      [ROUTE_POSTE]: F.poste_en_ligne,
      [`POST ${ROUTE_RELEVE}`]: F.releve_demande,
      [`POST ${ROUTE_REVOCATION}`]: { machine: { machine: { ...machine, etat: "revoque" } } },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(h(Poste, null));
    expect(texteDe(r.racine.querySelector("#acp-poste-etat")?.parentElement)).toContain("En ligne");
    expect(texteDe(r.racine.querySelector("#acp-poste-compte")?.parentElement)).toContain("Compte dédié acp-poste");
    const bac = texteDe(r.racine.querySelector("#acp-poste-bac")?.parentElement);
    expect(bac).toContain("elevated");
    expect(bac).toContain("sessionFlags");
    expect(bac).toContain("Oui");
    const connexions = texteDe(r.racine.querySelector("#acp-poste-connexions")?.parentElement);
    expect(connexions).toContain("Compte ChatGPT");
    expect(connexions).toContain("Jeton reconnu");
    expect(texteDe(r.racine.querySelector("#acp-poste-depots")?.parentElement)).toContain("jetable");
    expect(texteDe(r.racine.querySelector("#acp-poste-versions")?.parentElement)).toContain("0.156.1");
    await cliquer(bouton(r.racine, "Relever maintenant"));
    expect(r.texte()).toContain(F.releve_demande.message);
    await cliquer(bouton(r.racine, "Révoquer"));
    expect(bouton(r.racine, "Confirmer la révocation").disabled).toBe(true);  // motif exigé
    await saisir(r.racine.querySelector("#acp-poste-motif"), "PC perdu");
    await cliquer(bouton(r.racine, "Confirmer la révocation"));
    expect(ecritures(installation)).toEqual([["POST", ROUTE_RELEVE, {}],
                                             ["POST", ROUTE_REVOCATION, { machine_id: machine.id, motif: "PC perdu" }]]);
    expect(r.texte()).toContain("Poste révoqué.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
  });

  it("poste illisible : erreur dite, jamais un état inventé", async () => {
    installerSdk({ [ROUTE_POSTE]: new ApiErrorHermes("boom", 500, "{}", ROUTE_POSTE) });
    const r = await rendre(h(Poste, null));
    expect(r.texte()).toContain("État du poste indisponible.");
    expect(r.texte()).not.toContain("En ligne");
  });
});

describe("vue Routage", () => {
  it("listes relevées, badges, suggestion appliquée puis table validée", async () => {
    aller("?vue=routage");
    const reponses: Record<string, Reponse> = { [ROUTE_ROUTAGE]: F.routage, [`POST ${ROUTE_ROUTAGE}`]: F.routage };
    const installation = installerSdk(reponses);
    const r = await rendre(h(Poste, null));
    const listes = texteDe(r.racine.querySelector("#acp-poste-listes")?.parentElement);
    expect(listes).toContain("Relevé du compte");
    expect(listes).toContain("Alias documentés");
    expect(listes).toContain("factice-codex-1");
    expect(listes).toContain("opus[1m]");
    expect(listes).toContain("claude-opus-5-5");
    // haiku : liste d'efforts VIDE (aucun documenté), distincte d'efforts inconnus (null).
    expect(listes).toContain("Aucun effort documenté");
    expect(listes).not.toContain("Efforts inconnus");
    const implementation = r.racine.querySelector("#acp-routage-implementation")?.parentElement as HTMLElement;
    expect(texteDe(implementation)).toContain("Non validée");
    await cliquer(bouton(implementation, "Appliquer la suggestion"));
    await cliquer(bouton(r.racine, "Valider la table"));
    const [[methode, url, corps]] = ecritures(installation);
    expect([methode, url]).toEqual(["POST", ROUTE_ROUTAGE]);
    expect(corps).toMatchObject({ releves: F.routage.releves, classes: { implementation: [
      { voie: "poste-codex", modele: "factice-codex-1", effort: "medium", palier: "default" }] } });
    expect(r.texte()).toContain("Table validée.");
  });

  it("voie Claude : aucun « Modèle par défaut du relevé » offert, un choix explicite est exigé", async () => {
    // Relecture de P5 (D73) : le relevé Claude ne désigne aucun modèle par défaut (D59) ; le serveur refuserait
    // toujours une entrée sans modèle sur cette voie.
    aller("?vue=routage");
    installerSdk({ [ROUTE_ROUTAGE]: F.routage });
    const r = await rendre(h(Poste, null));
    const implementation = r.racine.querySelector("#acp-routage-implementation")?.parentElement as HTMLElement;
    await cliquer(bouton(implementation, "Ajouter une entrée"));
    const premiere = () => (r.racine.querySelector("#acp-routage-implementation-0-modele") as HTMLSelectElement).options[0];
    expect(premiere()?.textContent?.trim()).toBe("Modèle par défaut du relevé");  // Codex : factice-codex-1 l'est
    expect(premiere()?.disabled).toBe(false);
    await saisir(r.racine.querySelector("#acp-routage-implementation-0-voie"), "poste-claude");
    expect(premiere()?.textContent?.trim()).toBe("Choisissez un modèle (le relevé n'en désigne aucun par défaut)");
    expect(premiere()?.disabled).toBe(true);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
  });

  it("table refusée : les refus de l'API sont rendus tels quels, entrée par entrée", async () => {
    aller("?vue=routage");
    installerSdk({ [ROUTE_ROUTAGE]: F.routage,
                   [`POST ${ROUTE_ROUTAGE}`]: refus(422, F.refus_table, ROUTE_ROUTAGE) });
    const r = await rendre(h(Poste, null));
    const implementation = r.racine.querySelector("#acp-routage-implementation")?.parentElement as HTMLElement;
    await cliquer(bouton(implementation, "Ajouter une entrée"));
    await cliquer(bouton(r.racine, "Valider la table"));
    const alerte = texteDe(r.racine.querySelector("#acp-poste-table")?.parentElement);
    expect(alerte).toContain("Table de routage refusée : 1 entrée(s) refusée(s) ; rien n'a été enregistré.");
    expect(alerte).toContain("Entrées refusées");
    expect(alerte).toContain("Refusé par ACP : le modèle « inexistant » ne figure pas dans le relevé de la voie poste-codex");
  });

  it("liste de secours probable : acceptation du relevé par sa route", async () => {
    aller("?vue=routage");
    const releve = F.routage_secours.voies["poste-codex"].releve_id;
    const installation = installerSdk({ [ROUTE_ROUTAGE]: F.routage_secours,
                                        [`POST ${ROUTE_RELEVE_ACCEPTE}`]: F.routage });
    const r = await rendre(h(Poste, null));
    expect(texteDe(r.racine.querySelector("#acp-poste-listes")?.parentElement)).toContain("Liste de secours probable");
    await cliquer(bouton(r.racine, "Accepter ce relevé comme celui de mon compte"));
    expect(ecritures(installation)).toEqual([["POST", ROUTE_RELEVE_ACCEPTE, { releve_id: releve }]]);
    expect(r.texte()).toContain("Relevé accepté.");
  });

  it("interdits côté Hermes : phrase de confirmation transmise, refus rendu tel quel", async () => {
    aller("?vue=routage");
    const refusPolitique = { detail: { code: "confirmation_requise", message: "Refusé par ACP : effort « max » levé : dépense hors enveloppe ; recopiez exactement la phrase « J'accepte une dépense hors enveloppe » pour confirmer." } };
    const reponses: Record<string, Reponse> = { [ROUTE_ROUTAGE]: F.routage,
                                                [`POST ${ROUTE_POLITIQUE}`]: refus(422, refusPolitique, ROUTE_POLITIQUE) };
    const installation = installerSdk(reponses);
    const r = await rendre(h(Poste, null));
    expect(texteDe(r.racine.querySelector("#acp-poste-politique")?.parentElement)).toContain(
      "J'accepte une dépense hors enveloppe");
    await saisir(r.racine.querySelector("#acp-poste-efforts"), "ultra, ultracode");
    await saisir(r.racine.querySelector("#acp-poste-politique-motif"), "gros travail");
    await soumettre(r.racine.querySelector("#acp-poste-politique")?.parentElement?.querySelector("form") ?? null);
    expect(ecritures(installation)).toEqual([["POST", ROUTE_POLITIQUE, { efforts_interdits: ["ultra", "ultracode"],
      paliers_admis: ["default"], motif: "gros travail", confirmation: null }]]);
    expect(r.texte()).toContain("recopiez exactement la phrase");
    const poste = texteDe(r.racine.querySelector("#acp-poste-politique-poste")?.parentElement);
    expect(poste).toContain("Interdit par le poste");
    expect(poste).toContain("opus[1m]");
  });

  it("surcharges globales : création et désactivation par leurs routes", async () => {
    aller("?vue=routage");
    const avecSurcharge = { ...F.routage, surcharges: [{ id: 7, classe: "implementation", voie: "poste-codex",
      modele: "factice-codex-2", effort: null, palier: null, motif: "essai", cree_le: 1790451620 }] };
    const installation = installerSdk({ [ROUTE_ROUTAGE]: avecSurcharge, [`POST ${ROUTE_SURCHARGES}`]: { surcharge: 8 },
                                        [`POST ${routeDesactiverSurcharge(7)}`]: { surcharges: [] } });
    const r = await rendre(h(Poste, null));
    await cliquer(bouton(r.racine, "Désactiver"));
    await saisir(r.racine.querySelector("#acp-surcharge-classe"), "implementation");
    await saisir(r.racine.querySelector("#acp-surcharge-modele"), "factice-codex-1");
    await saisir(r.racine.querySelector("#acp-surcharge-motif"), "urgence");
    await soumettre(r.racine.querySelector("#acp-poste-surcharges")?.parentElement?.querySelector("form") ?? null);
    expect(ecritures(installation)).toEqual([
      ["POST", routeDesactiverSurcharge(7), {}],
      ["POST", ROUTE_SURCHARGES, { classe: "implementation", voie: "poste-codex", modele: "factice-codex-1",
                                   effort: null, palier: null, motif: "urgence" }]]);
  });
});

describe("vue Quotas", () => {
  it("jauges, seuil, remise à zéro, offre ; Claude et Hermes dits tels quels", async () => {
    aller("?vue=quotas");
    const installation = installerSdk({ [ROUTE_QUOTAS]: F.quotas, [`POST ${ROUTE_RELEVE}`]: F.releve_demande });
    const r = await rendre(h(Poste, null));
    const codex = r.racine.querySelector("#acp-quotas-poste-codex")?.parentElement as HTMLElement;
    const jauges = [...codex.querySelectorAll('[role="meter"]')].map((j) => j.getAttribute("aria-valuenow"));
    expect(jauges).toEqual(["41", "12"]);
    expect(texteDe(codex)).toContain("Relevé");
    expect(texteDe(codex)).toContain("90 %");
    expect(texteDe(codex)).toContain("prolite");
    const claude = texteDe(r.racine.querySelector("#acp-quotas-poste-claude")?.parentElement);
    expect(claude).toContain("Aucun compteur relevé.");
    expect(claude).toContain("Ligne d'état de vos sessions");
    expect(texteDe(r.racine.querySelector("#acp-quotas-hermes")?.parentElement)).toContain("Inconnu");
    await cliquer(bouton(r.racine, "Relever maintenant"));
    expect(ecritures(installation)).toEqual([["POST", ROUTE_RELEVE, {}]]);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
  });

  it("sans relevé : « Inconnu », aucune jauge inventée", async () => {
    aller("?vue=quotas");
    installerSdk({ [ROUTE_QUOTAS]: F.quotas_vides });
    const r = await rendre(h(Poste, null));
    expect(r.racine.querySelectorAll('[role="meter"]').length).toBe(0);
    expect(texteDe(r.racine.querySelector("#acp-quotas-poste-codex")?.parentElement)).toContain("Inconnu");
  });
});
