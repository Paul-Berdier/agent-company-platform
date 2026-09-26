// Page Projets : corrections de la relecture indépendante de P4 (26/09/2026). Chaque test fixe un défaut
// relevé (résultat coupé sans le dire, raison « Inconnu », « Qui répond » sans objet, pause générale mal
// décrite, réussite annoncée sans lire l'API, décision au plafond, retour du téléphone, état inconnu des
// notifications, affichages techniques, reprise refusée sur crochets shell).
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act } from "react";
import { h } from "../src/react";
import { Projets } from "../src/projets/Projets";
import { ROUTE_CATALOGUE } from "../src/api";
import {
  ROUTE_POSTE,
  ROUTE_PROJETS,
  ROUTE_QUESTIONS,
  routeCarteDuProjet,
  routeConclureTriage,
  routeProjet,
  routeReponse,
  routeReprendreTriage,
} from "../src/projets/api";
import { CATALOGUE } from "./catalogue-chaines";
import { CATALOGUE_PROFILS, DETAIL, LISTE, LISTE_VIDE, POSTE_RELEVE, POSTE_VIDE, QUESTIONS } from "./fixtures-projets";
import { ApiErrorHermes, attendre, installerSdk, rendre, textesHorsCatalogue, type Reponse } from "./sdk-factice";

const NBSP = /[  ]/g;

function texteDe(element: Element | null | undefined): string {
  return (element?.textContent ?? "").replace(NBSP, " ").replace(/\s+/g, " ").trim();
}

function aller(recherche: string): void {
  window.history.replaceState(null, "", `/projets${recherche}`);
}

function boutons(racine: HTMLElement): Map<string, HTMLButtonElement> {
  return new Map([...racine.querySelectorAll("button")].map((b) => [(b.textContent ?? "").trim(), b as HTMLButtonElement]));
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

function ecritures(installation: { requetes: Array<{ methode: string; url: string; corps: unknown }> }) {
  return installation.requetes.filter((r) => r.methode !== "GET").map((r) => [r.methode, r.url, r.corps]);
}

const ID = "p_367e23fd51b7";
const RAPPORT = Array.from({ length: 60 }, (_, i) => `Paragraphe ${i} du rapport de recherche, avec ses sources.`).join(" ");

beforeEach(() => aller(""));
afterEach(() => aller(""));

describe("relecture de P4 : résultat d'un projet", () => {
  it("un résumé coupé le dit, se lit en entier, et le résultat du projet est rendu en entier", async () => {
    aller(`?projet=${ID}`);
    const carte = {
      ...DETAIL.projet.cartes[1],
      statut: "done",
      resume: RAPPORT.slice(0, 500),
      resume_longueur: RAPPORT.length,
      resume_tronque: true,
    };
    const conclusion = `Conclusion. ${"Détail vérifié. ".repeat(80)}`.trim();
    const installation = installerSdk({
      [ROUTE_PROJETS]: LISTE,
      [routeProjet(ID)]: {
        projet: {
          ...DETAIL.projet,
          cartes: [carte],
          resultat: { tour: 1, carte: "t_5e5e5e5e", texte: conclusion, longueur: conclusion.length, tronque: false },
        },
      },
      [routeCarteDuProjet(ID, "t_342c81eb")]: {
        carte: { carte: "t_342c81eb", resume: RAPPORT, longueur: RAPPORT.length, tronque: false },
      },
    });
    const r = await rendre(<Projets />);
    await attendre();
    const resultat = r.racine.querySelector("#acp-projet-resultat")?.parentElement;
    expect(texteDe(resultat)).toContain("Résultat du projet");
    expect(texteDe(resultat)).toContain(conclusion);
    const cartes = r.racine.querySelector("#acp-projet-cartes")?.parentElement;
    expect(texteDe(cartes)).toContain(`Extrait : 500 caractères sur ${RAPPORT.length.toLocaleString("fr-FR").replace(NBSP, " ")}`);
    expect(texteDe(cartes)).not.toContain(RAPPORT.slice(500, 560));
    await cliquer(boutons(r.racine).get("Lire le résumé en entier"));
    expect(installation.appels).toContain(routeCarteDuProjet(ID, "t_342c81eb"));
    expect(texteDe(cartes)).toContain(RAPPORT.slice(500, 560));
    expect(boutons(r.racine).has("Lire le résumé en entier")).toBe(false);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("la dernière note d'un projet dit qu'elle n'est qu'un extrait", async () => {
    const liste = { ...LISTE, projets: [{ ...LISTE.projets[1], derniere_note: RAPPORT.slice(0, 200), derniere_note_tronquee: true }] };
    installerSdk({ [ROUTE_PROJETS]: liste });
    const r = await rendre(<Projets />);
    expect(r.texte().replace(NBSP, " ")).toContain("Extrait ; le détail du projet donne les résumés en entier.");
    r.demonter();
  });
});

describe("relecture de P4 : questions et décisions", () => {
  it("une carte bloquée montre sa raison ; une question montre sa carte (titre) et son contexte", async () => {
    aller("?vue=questions");
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS });
    const r = await rendre(<Projets />);
    await attendre();
    const bloquees = texteDe(r.racine.querySelector("#acp-questions-bloquees")?.parentElement);
    expect(bloquees).toContain("Refusé par ACP : carte poste-* non émise par le greffon acp-poste");
    expect(bloquees).not.toContain("Inconnu");
    const question = texteDe(r.racine.querySelector("#acp-questions-ouvertes")?.parentElement);
    expect(question).toContain("Exploration du dépôt « jetable »");
    expect(question).toContain("Le dépôt cible Python 3.11 et 3.12 dans sa CI.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("le message après « Répondre » suit la réponse de l'API (reprise, reprise différée, carte non relancée)", async () => {
    const cas: Array<[Record<string, unknown>, string]> = [
      [{ carte_debloquee: true, reprise_differee: false }, "Réponse envoyée : la carte reprend."],
      [{ carte_debloquee: false, reprise_differee: true }, "Réponse enregistrée : la carte reprendra à la reprise du projet."],
      [{ carte_debloquee: false, reprise_differee: false }, "Réponse enregistrée ; la carte n'a pas été relancée (voir le kanban de Hermes)."],
    ];
    for (const [resultat, attendu] of cas) {
      aller("?vue=questions");
      installerSdk({
        [ROUTE_PROJETS]: LISTE,
        [ROUTE_QUESTIONS]: QUESTIONS,
        [`POST ${routeReponse("q_b627a3c245ec")}`]: { question: "q_b627a3c245ec", etat: "repondue", ...resultat },
      });
      const r = await rendre(<Projets />);
      await attendre();
      await saisir(r.racine.querySelector("#acp-reponse-q_b627a3c245ec"), "Python 3.12.");
      await soumettre(r.racine.querySelector("#acp-reponse-q_b627a3c245ec")?.closest("form"));
      const succes = [...r.racine.querySelectorAll(".acp-succes")].map((e) => texteDe(e));
      expect(succes).toEqual([attendu]);
      r.demonter();
    }
  });

  it("au plafond : « Prolonger » (avec consigne) et « Conclure le projet » appellent leurs routes ; le compteur compte la décision", async () => {
    aller("?vue=questions");
    const liste = { ...LISTE, projets: [LISTE.projets[0], { ...LISTE.projets[1], compteurs: { ...LISTE.projets[1].compteurs, triage: 1 } }] };
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: liste,
      [ROUTE_QUESTIONS]: QUESTIONS,
      [`POST ${routeReprendreTriage("acp-veille-llm-b43a", "t_0c1d2e3f")}`]: {
        carte: "t_0c1d2e3f", reprise: true, action: "prolongation", plafond: { genre: "tours", avant: 3, apres: 4 },
      },
      [`POST ${routeConclureTriage("acp-veille-llm-b43a", "t_0c1d2e3f")}`]: {
        carte: "t_0c1d2e3f", conclu: true, projet: { etat: "termine" },
      },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    // 1 question + 1 décision attendue.
    expect(r.racine.querySelector('.acp-onglet[aria-current="page"]')?.textContent).toBe("Questions2");
    const triage = r.racine.querySelector("#acp-questions-triage")?.parentElement;
    expect(texteDe(triage)).toContain("« Prolonger » accorde un tour de plus : Hermes planifie la suite avec votre consigne.");
    expect(texteDe(triage)).toContain("3 tours planifiés");
    expect(boutons(r.racine).has("Reprendre")).toBe(false);
    await saisir(r.racine.querySelector("#acp-consigne-t_0c1d2e3f"), "Un tour de plus, pour vérifier.");
    await cliquer(boutons(r.racine).get("Prolonger"));
    expect(texteDe(triage)).toContain("Plafond relevé : Hermes planifie la suite avec votre consigne.");
    await cliquer(boutons(r.racine).get("Conclure le projet"));
    expect(ecritures(installation)).toEqual([
      ["POST", routeReprendreTriage("acp-veille-llm-b43a", "t_0c1d2e3f"), { consigne: "Un tour de plus, pour vérifier." }],
      ["POST", routeConclureTriage("acp-veille-llm-b43a", "t_0c1d2e3f"), {}],
    ]);
    expect(texteDe(triage)).toContain("Projet conclu.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("une reprise refusée par Hermes le dit ; une planification sans plan propose « Relancer », un plafond de corrections « Conclure » seul", async () => {
    aller("?vue=questions");
    const triage = [
      { ...QUESTIONS.triage[0], carte: "t_1", titre: "Planification sans plan — votre décision est attendue", genre: "sans_plan", actions: ["relancer", "conclure"] },
      { ...QUESTIONS.triage[0], carte: "t_2", titre: "Plafond atteint : corrections — votre décision est attendue", genre: "corrections", actions: ["conclure"] },
    ];
    installerSdk({
      [ROUTE_PROJETS]: LISTE,
      [ROUTE_QUESTIONS]: { ...QUESTIONS, triage },
      [`POST ${routeReprendreTriage("acp-veille-llm-b43a", "t_1")}`]: { carte: "t_1", reprise: false, action: null, plafond: null },
    });
    const r = await rendre(<Projets />);
    await attendre();
    const zone = r.racine.querySelector("#acp-questions-triage")?.parentElement as HTMLElement;
    const noms = [...zone.querySelectorAll("button")].map((b) => b.textContent);
    expect(noms).toEqual(["Relancer la planification", "Conclure le projet", "Conclure le projet"]);
    expect(texteDe(zone)).toContain("Prolonger le plafond de corrections arrivera à l'étape P6.");
    await soumettre(r.racine.querySelector("#acp-consigne-t_1")?.closest("form"));
    expect(texteDe(zone)).toContain("La carte n'a pas été reprise (voir le kanban de Hermes).");
    expect(texteDe(zone)).not.toContain("Carte reprise");
    r.demonter();
  });
});

describe("relecture de P4 : formulaire, pause, notifications", () => {
  it("sans dépôt, « Qui répond aux questions » est sans objet et le dit ; avec un dépôt, le choix revient", async () => {
    aller("?vue=nouveau");
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_CATALOGUE]: CATALOGUE_PROFILS, [ROUTE_POSTE]: POSTE_RELEVE });
    const r = await rendre(<Projets />);
    await attendre();
    expect(r.racine.querySelectorAll('input[name="acp-projet-reponses"]').length).toBe(0);
    expect(r.texte().replace(NBSP, " ")).toContain("Sans objet sans dépôt : aucune question ne naît d'un projet sans dépôt");
    await saisir(r.racine.querySelector("#acp-projet-depot"), "jetable");
    expect(r.racine.querySelectorAll('input[name="acp-projet-reponses"]').length).toBe(2);
    expect(r.texte()).not.toContain("Sans objet sans dépôt");
    r.demonter();
  });

  it("inventaire du poste illisible : « Dépôts inconnus », jamais « aucun inventaire »", async () => {
    aller("?vue=nouveau");
    installerSdk({
      [ROUTE_PROJETS]: LISTE,
      [ROUTE_CATALOGUE]: CATALOGUE_PROFILS,
      [ROUTE_POSTE]: new ApiErrorHermes("Bad Gateway", 502, "<html>502</html>", ROUTE_POSTE),
    });
    const r = await rendre(<Projets />);
    await attendre();
    const texte = r.texte().replace(NBSP, " ");
    expect(texte).toContain("Dépôts inconnus : l'inventaire du poste est illisible (voir l'erreur ci-dessus).");
    expect(texte).not.toContain("le poste n'a encore publié aucun inventaire");
    r.demonter();

    aller("?vue=nouveau");
    installerSdk({ [ROUTE_PROJETS]: LISTE_VIDE, [ROUTE_CATALOGUE]: CATALOGUE_PROFILS, [ROUTE_POSTE]: POSTE_VIDE });
    const s = await rendre(<Projets />);
    await attendre();
    expect(s.texte().replace(NBSP, " ")).toContain("Aucun dépôt connu : le poste n'a encore publié aucun inventaire (étape P5).");
    s.demonter();
  });

  it("la pause générale dit ce qu'elle arrête vraiment : la discussion reste ouverte", async () => {
    installerSdk({ [ROUTE_PROJETS]: LISTE });
    const r = await rendre(<Projets />);
    const pause = texteDe(r.racine.querySelector("#acp-projets-pause")?.parentElement);
    expect(pause).toContain("Arrête le travail autonome de Hermes");
    expect(pause).toContain("La discussion avec Hermes reste ouverte ; lancer un projet y est refusé.");
    expect(pause).not.toContain("Aucune notification pendant la pause.");
    r.demonter();
  });

  it("pause engagée par la veille des crochets shell : aucun « Reprendre », la marche à suivre", async () => {
    const crochets = { reason: "ACP : crochets shell détectés en cours de route", engaged_at: "2026-09-26T11:44:00+00:00" };
    installerSdk({ [ROUTE_PROJETS]: { ...LISTE, pause_generale: crochets } });
    const r = await rendre(<Projets />);
    const bandeau = r.racine.querySelector("[data-acp-pause]");
    expect(bandeau?.querySelector("button")).toBeNull();
    expect(texteDe(bandeau)).toContain("retirez la clé hooks du config.yaml");
    r.demonter();
  });

  it("canal pas encore publié : « inconnu », jamais « non configurées »", async () => {
    installerSdk({ [ROUTE_PROJETS]: LISTE_VIDE });
    const r = await rendre(<Projets />);
    const carte = texteDe(r.racine.querySelector("#acp-projets-notifications")?.parentElement);
    expect(carte).toContain("État du canal inconnu : la passerelle ne l'a pas encore publié.");
    expect(carte).not.toContain("Notifications non configurées");
    r.demonter();
  });
});

describe("relecture de P4 : navigation et lisibilité", () => {
  it("ouvrir un projet ajoute une entrée d'historique ; le retour ramène à la liste", async () => {
    aller("?profile=default");
    installerSdk({ [ROUTE_PROJETS]: LISTE, [routeProjet(ID)]: DETAIL });
    const r = await rendre(<Projets />);
    const avant = window.history.length;
    const lien = [...r.racine.querySelectorAll("a")].find((a) => a.getAttribute("href") === `/projets?projet=${ID}`);
    await cliquer(lien);
    expect(window.location.search).toBe(`?profile=default&projet=${ID}`);
    expect(window.history.length).toBe(avant + 1);
    expect(r.racine.querySelector("#acp-projet-titre")).not.toBeNull();
    // Le geste « retour » du navigateur : l'adresse revient, puis « popstate ».
    await act(async () => {
      window.history.replaceState(null, "", "/projets?profile=default");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await attendre();
    expect(r.racine.querySelector("#acp-projet-titre")).toBeNull();
    expect(r.racine.querySelector("#acp-projets-liste")).not.toBeNull();
    r.demonter();
  });

  it("journal en français (action, acteur), détail technique replié ; palier « Standard »", async () => {
    aller(`?projet=${ID}`);
    installerSdk({ [ROUTE_PROJETS]: LISTE, [routeProjet(ID)]: DETAIL });
    const r = await rendre(<Projets />);
    await attendre();
    const journal = r.racine.querySelector("#acp-projet-journal")?.parentElement as HTMLElement;
    const entrees = [...journal.querySelectorAll(".acp-journal > li")];
    expect(entrees.map((e) => texteDe(e.firstElementChild?.nextElementSibling))).toEqual([
      "Question transmise au propriétaire",
      "Lancement",
    ]);
    expect(texteDe(entrees[1])).toContain("Vous");
    expect(texteDe(entrees[1])).not.toContain("proprietaire:proprietaire-test");
    expect(entrees[1]?.querySelector("details summary")?.textContent).toBe("Détail technique");
    expect(entrees[1]?.querySelector("details")?.hasAttribute("open")).toBe(false);
    const paliers = [...(r.racine.querySelector("#acp-projet-cartes")?.parentElement?.querySelectorAll(".acp-ligne") ?? [])]
      .filter((l) => l.querySelector("dt")?.textContent === "Palier")
      .map((l) => texteDe(l.querySelector("dd")));
    expect(paliers).toEqual(["Standard", "Standard"]);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});
