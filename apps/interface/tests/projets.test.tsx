// Page Projets (greffon acp-projets) : rendu de chaque vue sur les formes réelles des routes, états
// vides, boutons liés à des routes réelles, refus de l'API affichés tels quels, sondage de 15 s.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { h } from "../src/react";
import { Projets } from "../src/projets/Projets";
import { ROUTE_CATALOGUE } from "../src/api";
import {
  ROUTE_PAUSE,
  ROUTE_POSTE,
  ROUTE_PROJETS,
  ROUTE_QUESTIONS,
  routePauseProjet,
  routeProjet,
  routeReponse,
  routeReprendreTriage,
  routeRepriseProjet,
} from "../src/projets/api";
import { CATALOGUE } from "./catalogue-chaines";
import {
  CATALOGUE_PROFILS,
  DETAIL,
  LANCEMENT,
  LISTE,
  LISTE_VIDE,
  PAUSE_GENERALE,
  POSTE_RELEVE,
  POSTE_VIDE,
  QUESTIONS,
  REFUS_AUCUN_INVENTAIRE,
} from "./fixtures-projets";
import { ApiErrorHermes, attendre, installerSdk, rendre, textesHorsCatalogue, type Reponse } from "./sdk-factice";

/** Texte d'un élément, espaces (insécables comprises) ramenées à une espace ordinaire. */
function texteDe(element: Element | null | undefined): string {
  return (element?.textContent ?? "").replace(/\s+/g, " ").trim();
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
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
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

beforeEach(() => aller(""));
afterEach(() => aller(""));

describe("Projets : liste", () => {
  it("rend chaque projet, l'état du poste et des notifications, en français, sans valeur inventée", async () => {
    installerSdk({ [ROUTE_PROJETS]: LISTE });
    const r = await rendre(<Projets />);
    const texte = r.texte();
    for (const attendu of [
      "Projets",
      "Outil",
      "Exploration du dépôt",
      "Veille LLM",
      "En cours",
      "Questions en attente 1",
      "Cartes faites",
      "0 sur 2",
      "2 sur 4",
      "Plan posé : deux recherches.",
      "Aucune carte finie pour l'instant.",
      "Poste",
      "En ligne",
      "poste-simule",
      "Canal",
      "Aucun",
      "Non configurées",
      "Notifications non configurées : leur activation passe par une PR qui déclare les variables ACP_NOTIFICATIONS… dans l'IaC Railway (docs/refonte/railway.md, § 9).",
    ]) {
      expect(texte).toContain(attendu);
    }
    // Le lien de chaque projet mène à son détail ; « Nouveau projet » au formulaire.
    const liens = [...r.racine.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(liens).toContain("/projets?projet=p_367e23fd51b7");
    expect(liens).toContain("/projets?vue=nouveau");
    // Aucun canal configuré : le bouton de test est désactivé et dit pourquoi.
    const test = boutons(r.racine).get("Envoyer une notification de test");
    expect(test?.disabled).toBe(true);
    expect(test?.getAttribute("aria-describedby")).toBe("acp-notifications-note");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("liste vide : le dit, poste « Non configuré », canal « Inconnu » tant que l'émetteur n'a pas tourné", async () => {
    installerSdk({ [ROUTE_PROJETS]: LISTE_VIDE });
    const r = await rendre(<Projets />);
    const texte = r.texte();
    expect(texte).toContain("Aucun projet pour l'instant.");
    expect(texte).toContain("Non configuré");
    expect(texte).toContain("Le poste n'a jamais été vu (connexion prévue à l'étape P5).");
    const notifications = r.racine.querySelector("#acp-projets-notifications")?.parentElement;
    expect(texteDe(notifications)).toContain("Inconnu");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("un canal configuré active « Envoyer une notification de test » (POST /v1/notifications/test)", async () => {
    const liste = { ...LISTE, notifications: { canal: "ntfy", configure: true, connu: true, message: null } };
    const installation = installerSdk({
      [ROUTE_PROJETS]: liste,
      "POST /api/plugins/acp-poste/v1/notifications/test": {
        notification: "test:1790423100",
        etat: "en_attente",
        message: "Notification de test mise en file : la passerelle l'envoie à sa prochaine passe.",
      },
    });
    const r = await rendre(<Projets />);
    expect(r.texte()).toContain("ntfy");
    await cliquer(boutons(r.racine).get("Envoyer une notification de test"));
    expect(ecritures(installation)).toEqual([["POST", "/api/plugins/acp-poste/v1/notifications/test", {}]]);
    expect(r.texte()).toContain("Notification de test mise en file : la passerelle l'envoie à sa prochaine passe.");
    r.demonter();
  });

  it("pause générale : une confirmation, puis POST /v1/pause, puis le bandeau et « Reprendre »", async () => {
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE,
      [`POST ${ROUTE_PAUSE}`]: { pause_generale: PAUSE_GENERALE },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await cliquer(boutons(r.racine).get("Pause générale"));
    // Rien n'est envoyé avant la confirmation.
    expect(ecritures(installation)).toEqual([]);
    expect(r.texte()).toContain("Mettre Hermes en pause générale ?");
    reponses[ROUTE_PROJETS] = { ...LISTE, pause_generale: PAUSE_GENERALE };
    await cliquer(boutons(r.racine).get("Confirmer la pause générale"));
    expect(ecritures(installation)).toEqual([["POST", ROUTE_PAUSE, { generale: true }]]);
    const bandeau = r.racine.querySelector("[data-acp-pause]");
    expect(texteDe(bandeau)).toContain("Hermes est en pause générale");
    expect(texteDe(bandeau)).toContain("ACP : pause du propriétaire");
    // La commande disparaît pendant la pause ; « Reprendre » relève la pause.
    expect(boutons(r.racine).has("Pause générale")).toBe(false);
    reponses[`POST ${ROUTE_PAUSE}`] = { pause_generale: null };
    reponses[ROUTE_PROJETS] = LISTE;
    await cliquer(bandeau?.querySelector("button"));
    expect(ecritures(installation)[1]).toEqual(["POST", ROUTE_PAUSE, { generale: false }]);
    expect(r.racine.querySelector("[data-acp-pause]")).toBeNull();
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("une liste illisible le dit, sans rien inventer", async () => {
    installerSdk({});
    const r = await rendre(<Projets />);
    expect(texteDe(r.racine.querySelector(".acp-erreur"))).toContain(
      "Les projets sont indisponibles : le greffon acp-poste ne répond pas sur /v1/projets.",
    );
    expect(r.racine.querySelector(".acp-projet")).toBeNull();
    r.demonter();
  });
});

describe("Projets : nouveau projet", () => {
  it("sans inventaire du poste : Dépôt désactivé et expliqué, lancement sans dépôt avec sa clé", async () => {
    aller("?vue=nouveau");
    const installation = installerSdk({
      [ROUTE_PROJETS]: LISTE_VIDE,
      [ROUTE_CATALOGUE]: CATALOGUE_PROFILS,
      [ROUTE_POSTE]: POSTE_VIDE,
      [`POST ${ROUTE_PROJETS}`]: LANCEMENT,
      [routeProjet("p_a35a8b99fb0e")]: DETAIL,
    });
    const r = await rendre(<Projets />);
    await attendre();
    const depot = r.racine.querySelector("#acp-projet-depot") as HTMLSelectElement;
    expect(depot.disabled).toBe(true);
    expect(depot.getAttribute("aria-describedby")).toBe("acp-projet-depot-aide");
    expect(r.texte()).toContain("Aucun dépôt connu : le poste n'a encore publié aucun inventaire (étape P5).");
    expect([...depot.options].map((o) => o.textContent)).toEqual(["Sans dépôt"]);
    expect(r.racine.querySelector("#acp-projet-voie")).toBeNull();
    const profils = r.racine.querySelector("#acp-projet-profil") as HTMLSelectElement;
    expect([...profils.options].map((o) => o.textContent)).toEqual(["Base", "Site web", "Recherche", "Données"]);
    // Le bouton reste désactivé tant que titre et objectif manquent.
    expect(boutons(r.racine).get("Lancer le projet")?.disabled).toBe(true);
    await saisir(r.racine.querySelector("#acp-projet-titre-champ"), "Veille LLM");
    await saisir(r.racine.querySelector("#acp-projet-objectif"), "Recenser les modèles.");
    await saisir(profils, "recherche");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    await soumettre(r.racine.querySelector("form"));
    const [lancement] = installation.requetes.filter((q) => q.methode === "POST");
    expect(lancement?.url).toBe(ROUTE_PROJETS);
    expect(lancement?.corps).toEqual({
      titre: "Veille LLM",
      objectif: "Recenser les modèles.",
      profil: "recherche",
      depot: null,
      reponses: "hermes_d_abord",
    });
    expect(lancement?.entetes["Idempotency-Key"]).toMatch(/^[0-9a-f-]{32,36}$/);
    // Après le lancement : le détail du projet créé, adresse à jour.
    expect(window.location.search).toBe("?projet=p_a35a8b99fb0e");
    expect(installation.appels).toContain(routeProjet("p_a35a8b99fb0e"));
    r.demonter();
  });

  it("avec un relevé (factice, signalé) : dépôt, exploration choisie dans le relevé, efforts interdits exclus", async () => {
    aller("?vue=nouveau");
    const installation = installerSdk({
      [ROUTE_PROJETS]: LISTE,
      [ROUTE_CATALOGUE]: CATALOGUE_PROFILS,
      [ROUTE_POSTE]: POSTE_RELEVE,
      [`POST ${ROUTE_PROJETS}`]: { projet: { id: "p_367e23fd51b7" }, deja_lance: false },
      [routeProjet("p_367e23fd51b7")]: DETAIL,
    });
    const r = await rendre(<Projets />);
    await attendre();
    expect(r.texte()).toContain("Relevé factice : ces modèles viennent d'un relevé de test, pas de votre poste.");
    const depot = r.racine.querySelector("#acp-projet-depot") as HTMLSelectElement;
    expect(depot.disabled).toBe(false);
    expect([...depot.options].map((o) => o.value)).toEqual(["", "jetable"]);
    await saisir(depot, "jetable");
    const voie = r.racine.querySelector("#acp-projet-voie") as HTMLSelectElement;
    expect([...voie.options].map((o) => [o.value, o.textContent])).toEqual([
      ["poste-claude", "Poste (Claude)"],
      ["poste-codex", "Poste (Codex)"],
    ]);
    const modele = r.racine.querySelector("#acp-projet-modele") as HTMLSelectElement;
    expect([...modele.options].map((o) => o.value)).toEqual(["", "factice-claude-1", "factice-claude-2"]);
    const effort = r.racine.querySelector("#acp-projet-effort") as HTMLSelectElement;
    expect([...effort.options].map((o) => o.value)).toEqual(["", "low", "medium", "high", "xhigh", "extreme"]);
    await saisir(modele, "factice-claude-2");
    expect([...(r.racine.querySelector("#acp-projet-effort") as HTMLSelectElement).options].map((o) => o.value))
      .toEqual(["", "low"]);
    await saisir(r.racine.querySelector("#acp-projet-effort"), "low");
    await cliquer(r.racine.querySelector('input[value="proprietaire"]'));
    await saisir(r.racine.querySelector("#acp-projet-titre-champ"), "Outil");
    await saisir(r.racine.querySelector("#acp-projet-objectif"), "Écrire outil.py.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    await soumettre(r.racine.querySelector("form"));
    const [lancement] = installation.requetes.filter((q) => q.methode === "POST");
    expect(lancement?.corps).toEqual({
      titre: "Outil",
      objectif: "Écrire outil.py.",
      profil: "base",
      depot: "jetable",
      reponses: "proprietaire",
      exploration: { voie: "poste-claude", modele: "factice-claude-2", effort: "low" },
    });
    r.demonter();
  });

  it("un refus du greffon s'affiche tel quel, et le formulaire reste rempli", async () => {
    aller("?vue=nouveau");
    installerSdk({
      [ROUTE_PROJETS]: LISTE_VIDE,
      [ROUTE_CATALOGUE]: CATALOGUE_PROFILS,
      [ROUTE_POSTE]: POSTE_VIDE,
      [`POST ${ROUTE_PROJETS}`]: new ApiErrorHermes("Refusé", 400, REFUS_AUCUN_INVENTAIRE, ROUTE_PROJETS),
    });
    const r = await rendre(<Projets />);
    await attendre();
    await saisir(r.racine.querySelector("#acp-projet-titre-champ"), "X");
    await saisir(r.racine.querySelector("#acp-projet-objectif"), "Y");
    await soumettre(r.racine.querySelector("form"));
    const alerte = r.racine.querySelector('[role="alert"]');
    expect(texteDe(alerte)).toContain(
      "Refusé par ACP : aucun dépôt autorisé n'est connu : le poste n'a encore publié aucun inventaire (étape P5).",
    );
    expect(texteDe(alerte)).toContain("400");
    expect((r.racine.querySelector("#acp-projet-titre-champ") as HTMLInputElement).value).toBe("X");
    expect(window.location.search).toBe("?vue=nouveau");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});

describe("Projets : détail", () => {
  it("montre l'état, les plafonds, les cartes par rôle, « Modèle servi : Non observé » et le poste", async () => {
    aller("?projet=p_367e23fd51b7");
    installerSdk({ [ROUTE_PROJETS]: LISTE_VIDE, [routeProjet("p_367e23fd51b7")]: DETAIL });
    const r = await rendre(<Projets />);
    await attendre();
    const texte = r.texte();
    for (const attendu of [
      "Outil",
      "Exploration du dépôt",
      "Écrire outil.py.",
      "0 sur 3",
      "2 sur 30",
      "jetable",
      "Moi",
      "Non configuré",
      "la page Projets",
      "Planification",
      "Poste (Claude)",
      "Suspendue",
      "factice-claude-1",
      "Modèle servi",
      "Non observé",
      "quota inconnu",
      "Hermes",
      "En attente",
      "modèle par défaut du profil",
      "Par défaut",
      "Quelle version de Python viser ?",
      "Votre réponse est attendue",
      "Entrées du journal",
    ]) {
      expect(texte).toContain(attendu);
    }
    const cartes = r.racine.querySelector("#acp-projet-cartes")?.parentElement;
    const titresRoles = [...(cartes?.querySelectorAll(".acp-groupe > h3") ?? [])].map((e) => e.textContent);
    expect(titresRoles).toEqual(["Exploration du dépôt", "Planification"]);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("« Mettre en pause » puis « Reprendre » appellent les routes du projet", async () => {
    aller("?projet=p_367e23fd51b7");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE,
      [routeProjet("p_367e23fd51b7")]: DETAIL,
      [`POST ${routePauseProjet("p_367e23fd51b7")}`]: { projet: { etat: "en_pause" }, cartes_planifiees: [] },
      [`POST ${routeRepriseProjet("p_367e23fd51b7")}`]: { projet: { etat: "actif" }, cartes_reveillees: [] },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    reponses[routeProjet("p_367e23fd51b7")] = { projet: { ...DETAIL.projet, etat: "en_pause", etat_derive: "en_pause" } };
    await cliquer(boutons(r.racine).get("Mettre en pause"));
    expect(r.texte()).toContain("En pause");
    reponses[routeProjet("p_367e23fd51b7")] = DETAIL;
    await cliquer(boutons(r.racine).get("Reprendre"));
    expect(ecritures(installation)).toEqual([
      ["POST", routePauseProjet("p_367e23fd51b7"), {}],
      ["POST", routeRepriseProjet("p_367e23fd51b7"), {}],
    ]);
    expect(boutons(r.racine).has("Mettre en pause")).toBe(true);
    r.demonter();
  });

  it("un projet terminé n'a ni pause ni reprise ; un projet inconnu montre le refus", async () => {
    aller("?projet=p_367e23fd51b7");
    installerSdk({
      [ROUTE_PROJETS]: LISTE,
      [routeProjet("p_367e23fd51b7")]: { projet: { ...DETAIL.projet, etat: "termine", termine_le: 1790423999 } },
    });
    const r = await rendre(<Projets />);
    await attendre();
    expect(r.texte()).toContain("Terminé");
    expect(boutons(r.racine).has("Mettre en pause")).toBe(false);
    expect(boutons(r.racine).has("Reprendre")).toBe(false);
    r.demonter();

    aller("?projet=p_inconnu");
    installerSdk({
      [ROUTE_PROJETS]: LISTE,
      [routeProjet("p_inconnu")]: new ApiErrorHermes("x", 404,
        '{"detail": {"code": "projet_inconnu", "message": "Refusé par ACP : projet « p_inconnu » inconnu."}}'),
    });
    const s = await rendre(<Projets />);
    await attendre();
    expect(texteDe(s.racine.querySelector('[role="alert"]'))).toContain("Refusé par ACP : projet « p_inconnu » inconnu.");
    s.demonter();
  });

  it("un code inconnu du greffon est montré tel quel, comme donnée, jamais traduit au hasard", async () => {
    aller("?projet=p_367e23fd51b7");
    const carte = { ...DETAIL.projet.cartes[0], statut: "statut-futur", voie: "poste-futur", role: "role-futur" };
    installerSdk({
      [ROUTE_PROJETS]: LISTE,
      [routeProjet("p_367e23fd51b7")]: { projet: { ...DETAIL.projet, etat: "etat-futur", cartes: [carte] } },
    });
    const r = await rendre(<Projets />);
    await attendre();
    for (const brut of ["etat-futur", "statut-futur", "poste-futur", "role-futur"]) expect(r.texte()).toContain(brut);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});

describe("Projets : questions", () => {
  it("répondre à une question, reprendre un triage ; les cartes bloquées restent en lecture seule", async () => {
    aller("?vue=questions");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE,
      [ROUTE_QUESTIONS]: QUESTIONS,
      [`POST ${routeReponse("q_b627a3c245ec")}`]: { question: "q_b627a3c245ec", etat: "repondue", carte_debloquee: true },
      [`POST ${routeReprendreTriage("acp-veille-llm-b43a", "t_0c1d2e3f")}`]: { carte: "t_0c1d2e3f", reprise: true },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    const texte = r.texte();
    for (const attendu of [
      "Quelle version de Python viser ?",
      "Votre réponse est attendue",
      "politique du projet : le propriétaire répond lui-même",
      "Plafond atteint : tours — votre décision est attendue",
      "Carte à la main",
      "poste-codex",
      "Lecture seule : relancer une carte depuis cette page arrivera à l'étape P7 ; en attendant, le kanban de Hermes le permet.",
    ]) {
      expect(texte).toContain(attendu);
    }
    // Le compteur de l'onglet « Questions » vient de /v1/projets.
    expect(r.racine.querySelector('.acp-onglet[aria-current="page"]')?.textContent).toBe("Questions1");
    expect(r.racine.querySelector("#acp-questions-bloquees")?.parentElement?.querySelector("button")).toBeNull();
    const repondre = boutons(r.racine).get("Répondre");
    expect(repondre?.disabled).toBe(true);
    await saisir(r.racine.querySelector("#acp-reponse-q_b627a3c245ec"), "Python 3.12.");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    reponses[ROUTE_QUESTIONS] = { ...QUESTIONS, questions: [] };
    await soumettre(r.racine.querySelector("#acp-reponse-q_b627a3c245ec")?.closest("form") ?? null);
    await saisir(r.racine.querySelector("#acp-consigne-t_0c1d2e3f"), "Un quatrième tour, pas plus.");
    await soumettre(r.racine.querySelector("#acp-consigne-t_0c1d2e3f")?.closest("form") ?? null);
    expect(ecritures(installation)).toEqual([
      ["POST", routeReponse("q_b627a3c245ec"), { reponse: "Python 3.12." }],
      ["POST", routeReprendreTriage("acp-veille-llm-b43a", "t_0c1d2e3f"), { consigne: "Un quatrième tour, pas plus." }],
    ]);
    expect(r.texte()).toContain("Aucune question en attente.");
    r.demonter();
  });

  it("aucune question : chaque section le dit", async () => {
    aller("?vue=questions");
    installerSdk({ [ROUTE_PROJETS]: LISTE_VIDE, [ROUTE_QUESTIONS]: { questions: [], triage: [], bloquees: [], tableaux_illisibles: [] } });
    const r = await rendre(<Projets />);
    await attendre();
    for (const vide of ["Aucune question en attente.", "Aucune carte en triage.", "Aucune carte bloquée."]) {
      expect(r.texte()).toContain(vide);
    }
    r.demonter();
  });
});

describe("Projets : navigation et sondage", () => {
  it("les onglets changent de vue sans recharger la page, mettent l'adresse à jour et remontent en haut", async () => {
    aller("?profile=default");
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS });
    const r = await rendre(<Projets />);
    const page = r.racine.querySelector('[data-acp-racine="projets"]') as HTMLElement;
    const defilements: unknown[] = [];
    page.scrollIntoView = ((options?: unknown) => {
      defilements.push(options);
    }) as HTMLElement["scrollIntoView"];
    const onglet = [...r.racine.querySelectorAll(".acp-onglet")].find((a) => a.textContent?.startsWith("Questions"));
    expect(onglet?.getAttribute("href")).toBe("/projets?vue=questions");
    await cliquer(onglet);
    expect(window.location.search).toBe("?profile=default&vue=questions");
    expect(r.texte()).toContain("Quelle version de Python viser ?");
    expect(defilements).toEqual([{ block: "start" }]);
    r.demonter();
  });

  it("relit toutes les 15 s tant que la page est visible, plus du tout quand elle est cachée", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let visibilite: DocumentVisibilityState = "visible";
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibilite });
    try {
      const installation = installerSdk({ [ROUTE_PROJETS]: LISTE });
      const r = await rendre(<Projets />);
      const lectures = () => installation.appels.filter((u) => u === ROUTE_PROJETS).length;
      expect(lectures()).toBe(1);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(15_000);
      });
      expect(lectures()).toBe(2);
      visibilite = "hidden";
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"));
        await vi.advanceTimersByTimeAsync(60_000);
      });
      expect(lectures()).toBe(2);
      visibilite = "visible";
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"));
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(lectures()).toBe(3);
      r.demonter();
    } finally {
      delete (document as unknown as { visibilityState?: unknown }).visibilityState;
      vi.useRealTimers();
    }
  });

  it("une actualisation ratée garde les données lues et le dit", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const reponses: Record<string, Reponse> = { [ROUTE_PROJETS]: LISTE };
      installerSdk(reponses);
      const r = await rendre(<Projets />);
      expect(r.texte()).toContain("Veille LLM");
      reponses[ROUTE_PROJETS] = new ApiErrorHermes("x", 0, "TypeError: Failed to fetch");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(15_000);
      });
      expect(r.texte()).toContain("Veille LLM");
      expect(r.texte()).toContain("Dernière actualisation impossible");
      r.demonter();
    } finally {
      vi.useRealTimers();
    }
  });
});
