// Étape P7 (cahier P7 § 3, § 4.2, § 6.2, § 10) : file Questions à cinq sections, « Relancer », cibles des liens
// profonds (requête, jamais fragment), discussions en attente lues par le JSON-RPC natif (lecture seule), « Qui
// répond » et « Clore » dans le détail d'un projet. Chaque message suit la réponse de l'API.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { h } from "../src/react";
import { Projets } from "../src/projets/Projets";
import {
  ROUTE_PROJETS,
  ROUTE_QUESTIONS,
  routeClore,
  routeConclureTriage,
  routeProjet,
  routeRelancerCarte,
  routeReponse,
  routeReponsesProjet,
  routeReprendreTriage,
} from "../src/projets/api";
import { rechercheDeVue, vueDepuisAdresse } from "../src/projets/vue";
import { lireDiscussionsEnAttente, METHODE_LISTE, sessionsEnAttente } from "../src/jsonrpc/discussions";
import { CATALOGUE } from "./catalogue-chaines";
import { ARRETEE_RELANCABLE, DETAIL, LISTE, QUESTIONS } from "./fixtures-projets";
import { attendre, installerSdk, rendre, textesHorsCatalogue, type Reponse } from "./sdk-factice";

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

/** WebSocket factice : rejoue le protocole de /api/ws (gateway.ready, puis réponse à session.active_list). */
class SocketFactice {
  static dernier: SocketFactice | null = null;
  static sessions: unknown[] = [];
  static silencieux = false;
  envoyes: string[] = [];
  ferme = false;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(readonly url: string) {
    SocketFactice.dernier = this;
    setTimeout(() => this.recevoir({ jsonrpc: "2.0", method: "event", params: { type: "gateway.ready", payload: {} } }), 0);
  }

  recevoir(message: unknown): void {
    this.onmessage?.({ data: `${JSON.stringify(message)}\n` } as MessageEvent);
  }

  send(texte: string): void {
    this.envoyes.push(texte);
    const requete = JSON.parse(texte) as { id: string; method: string };
    if (SocketFactice.silencieux) return;
    setTimeout(() => this.recevoir({ jsonrpc: "2.0", id: requete.id, result: { sessions: SocketFactice.sessions } }), 0);
  }

  close(): void {
    this.ferme = true;
  }
}

const SESSIONS = [
  { current: false, id: "s1", last_active: 1790423000, message_count: 4, model: "m", preview: "Quel nom donner au module ?",
    session_key: "20261002_080000_ab12cd", started_at: 1790422000, status: "waiting", title: "Nom du module" },
  { current: false, id: "s2", last_active: 1790423100, message_count: 2, model: "m", preview: "En cours", session_key: "k2",
    started_at: 1790422100, status: "working", title: "Autre" },
  { current: false, id: "s3", last_active: "illisible", message_count: 1, model: "m", preview: "", session_key: "k3",
    started_at: 1, status: "waiting", title: "" },
];

beforeEach(() => {
  aller("");
  SocketFactice.dernier = null;
  SocketFactice.sessions = SESSIONS;
  SocketFactice.silencieux = false;
});
afterEach(() => {
  aller("");
  vi.unstubAllGlobals();
});

describe("liens profonds : cibles en paramètres de requête", () => {
  it("lit q et carte, refuse une cible illisible, garde les autres paramètres", () => {
    expect(vueDepuisAdresse("?vue=questions&q=q_b627a3c245ec")).toEqual({ genre: "questions", q: "q_b627a3c245ec" });
    expect(vueDepuisAdresse("?vue=questions&carte=acp-outil-3dd5/t_5e6f7a8b")).toEqual({
      genre: "questions", carte: "acp-outil-3dd5/t_5e6f7a8b" });
    expect(vueDepuisAdresse("?vue=questions&carte=acp-outil-3dd5%2Ft_5e6f7a8b")).toEqual({
      genre: "questions", carte: "acp-outil-3dd5/t_5e6f7a8b" });
    expect(vueDepuisAdresse("?vue=questions&q=<script>")).toEqual({ genre: "questions" });
    expect(vueDepuisAdresse("?vue=questions&carte=sans-barre")).toEqual({ genre: "questions" });
    expect(rechercheDeVue({ genre: "questions", carte: "acp-outil-3dd5/t_5e6f7a8b" }, "?profile=default&q=x")).toBe(
      "?profile=default&vue=questions&carte=acp-outil-3dd5/t_5e6f7a8b");
    expect(rechercheDeVue({ genre: "liste" }, "?vue=questions&q=q_1")).toBe("");
  });

  it("une question ciblée est marquée et défilée ; une cible absente dit « déjà traitée »", async () => {
    aller("?vue=questions&q=q_b627a3c245ec");
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS });
    const defilements: unknown[] = [];
    const avant = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = function (this: HTMLElement, options?: unknown) {
      if (this.hasAttribute("data-acp-cible")) defilements.push(options);
    } as HTMLElement["scrollIntoView"];
    try {
      const r = await rendre(<Projets />);
      await attendre();
      const cibles = [...r.racine.querySelectorAll('[aria-current="true"]')];
      expect(cibles).toHaveLength(1);
      expect(texteDe(cibles[0])).toContain("Quelle version de Python viser ?");
      expect(cibles[0].classList.contains("acp-entree--cible")).toBe(true);
      expect(defilements).toEqual([{ block: "center" }]);
      expect(r.texte()).not.toContain("Cette demande a déjà été traitée");
      r.demonter();
      aller("?vue=questions&carte=acp-veille-llm-b43a/t_0c1d2e3f");
      const r2 = await rendre(<Projets />);
      await attendre();
      expect(texteDe(r2.racine.querySelector('[aria-current="true"]'))).toContain("Plafond atteint");
      r2.demonter();
      aller("?vue=questions&q=q_000000000000");
      const r3 = await rendre(<Projets />);
      await attendre();
      expect(r3.racine.querySelector('[aria-current="true"]')).toBeNull();
      expect(r3.texte()).toContain("Cette demande a déjà été traitée : elle n'est plus dans la file.");
      expect(textesHorsCatalogue(r3.racine, CATALOGUE)).toEqual([]);
      r3.demonter();
    } finally {
      HTMLElement.prototype.scrollIntoView = avant;
    }
  });
});

// Relecture finale de P7 (constats scenario-1 et produit-1) : le serveur retire de la file une question répondue
// (questions.lister ne sert que « ouverte » et « escaladee ») et une carte sortie du triage ; le message tiré de la
// réponse de l'API doit survivre à cette relecture, et une cible que la page vient de traiter n'est pas « déjà traitée ».
describe("réponses et décisions : le message de l'API survit à la sortie de la file", () => {
  const SANS_QUESTION = { ...QUESTIONS, questions: [], compteurs: { ...QUESTIONS.compteurs, questions: 0, a_traiter: 2 } };
  const SANS_TRIAGE = { ...QUESTIONS, triage: [], compteurs: { ...QUESTIONS.compteurs, decisions: 0, a_traiter: 2 } };

  function statuts(racine: HTMLElement): string[] {
    return [...racine.querySelectorAll('[role="status"]')].map((e) => texteDe(e));
  }

  it("lien profond q= : reprise différée annoncée, jamais « déjà traitée »", async () => {
    aller("?vue=questions&q=q_b627a3c245ec");
    const route = routeReponse("q_b627a3c245ec");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS,
      [`POST ${route}`]: { question: "q_b627a3c245ec", etat: "repondue", carte_debloquee: false, reprise_differee: true },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    await saisir(r.racine.querySelector("#acp-reponse-q_b627a3c245ec"), "Python 3.12.");
    reponses[ROUTE_QUESTIONS] = SANS_QUESTION;  // comme le serveur réel : la question répondue quitte la file
    await soumettre(r.racine.querySelector("#acp-reponse-q_b627a3c245ec")?.closest("form"));
    expect(ecritures(installation)).toEqual([["POST", route, { reponse: "Python 3.12." }]]);
    expect(r.racine.querySelector("#acp-reponse-q_b627a3c245ec")).toBeNull();
    const section = texteDe(r.racine.querySelector("#acp-questions-ouvertes")?.parentElement);
    expect(section).toContain("Réponse enregistrée : la carte reprendra à la reprise du projet.");
    expect(r.texte()).not.toContain("déjà été traitée");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("sans lien profond : « carte non relancée » reste visible, en alerte", async () => {
    aller("?vue=questions");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS,
      [`POST ${routeReponse("q_b627a3c245ec")}`]: {
        question: "q_b627a3c245ec", etat: "repondue", carte_debloquee: false, reprise_differee: false },
    };
    installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    await saisir(r.racine.querySelector("#acp-reponse-q_b627a3c245ec"), "Python 3.12.");
    reponses[ROUTE_QUESTIONS] = SANS_QUESTION;
    await soumettre(r.racine.querySelector("#acp-reponse-q_b627a3c245ec")?.closest("form"));
    const alerte = r.racine.querySelector("#acp-questions-ouvertes")?.parentElement?.querySelector(".acp-alerte-texte");
    expect(texteDe(alerte)).toBe("Réponse enregistrée ; la carte n'a pas été relancée (voir le kanban de Hermes).");
    expect(statuts(r.racine)).toContain("Réponse enregistrée ; la carte n'a pas été relancée (voir le kanban de Hermes).");
    r.demonter();
  });

  it("lien profond carte= : « Prolonger » refusé par Hermes puis « Conclure » restent annoncés", async () => {
    aller("?vue=questions&carte=acp-veille-llm-b43a/t_0c1d2e3f");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS,
      [`POST ${routeReprendreTriage("acp-veille-llm-b43a", "t_0c1d2e3f")}`]: {
        carte: "t_0c1d2e3f", reprise: false, action: "prolongation" },
    };
    installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    reponses[ROUTE_QUESTIONS] = SANS_TRIAGE;
    await cliquer(boutons(r.racine).get("Prolonger"));
    const section = () => texteDe(r.racine.querySelector("#acp-questions-triage")?.parentElement);
    expect(section()).toContain("La carte n'a pas été reprise (voir le kanban de Hermes).");
    expect(r.texte()).not.toContain("déjà été traitée");
    r.demonter();

    aller("?vue=questions&carte=acp-veille-llm-b43a/t_0c1d2e3f");
    const reponses2: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS,
      [`POST ${routeConclureTriage("acp-veille-llm-b43a", "t_0c1d2e3f")}`]: {
        carte: "t_0c1d2e3f", conclu: true, projet: { etat: "termine" } },
    };
    installerSdk(reponses2);
    const r2 = await rendre(<Projets />);
    await attendre();
    reponses2[ROUTE_QUESTIONS] = SANS_TRIAGE;
    await cliquer(boutons(r2.racine).get("Conclure le projet"));
    expect(texteDe(r2.racine.querySelector("#acp-questions-triage")?.parentElement)).toContain("Projet conclu.");
    expect(r2.texte()).not.toContain("déjà été traitée");
    expect(textesHorsCatalogue(r2.racine, CATALOGUE)).toEqual([]);
    r2.demonter();
  });

  it("une carte arrêtée relancée depuis son lien profond n'est pas « déjà traitée »", async () => {
    aller("?vue=questions&carte=acp-outil-3dd5/t_5e6f7a8b");
    const file = { ...QUESTIONS, bloquees: [...QUESTIONS.bloquees, ARRETEE_RELANCABLE] };
    const route = routeRelancerCarte("acp-outil-3dd5", "t_5e6f7a8b");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: file,
      [`POST ${route}`]: { carte: "t_5e6f7a8b", relancee: true, statut_apres: "ready", session_neuve: true },
    };
    installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    reponses[ROUTE_QUESTIONS] = QUESTIONS;
    await cliquer(boutons(r.racine).get("Relancer"));
    expect(texteDe(r.racine.querySelector("#acp-questions-bloquees")?.parentElement)).toContain("La carte repart");
    expect(r.texte()).not.toContain("déjà été traitée");
    r.demonter();
  });

  it("une cible sur un tableau illisible dit que son état est inconnu, pas « déjà traitée »", async () => {
    aller("?vue=questions&carte=acp-illisible-0000/t_11112222");
    installerSdk({ [ROUTE_PROJETS]: LISTE,
                   [ROUTE_QUESTIONS]: { ...QUESTIONS, tableaux_illisibles: ["acp-illisible-0000"] } });
    const r = await rendre(<Projets />);
    await attendre();
    expect(r.texte()).not.toContain("déjà été traitée");
    expect(statuts(r.racine)).toContain(
      "Le tableau de cette demande n'a pas pu être lu : son état est inconnu (voir « Tableaux illisibles »).");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});

describe("cartes arrêtées : Relancer", () => {
  const file = { ...QUESTIONS, bloquees: [...QUESTIONS.bloquees, ARRETEE_RELANCABLE],
                 compteurs: { ...QUESTIONS.compteurs, arretees: 2, a_traiter: 4 } };

  it("une carte de l'exécutant se relance avec sa consigne ; le message suit la réponse (session neuve)", async () => {
    aller("?vue=questions");
    const route = routeRelancerCarte("acp-outil-3dd5", "t_5e6f7a8b");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: file,
      [`POST ${route}`]: { carte: "t_5e6f7a8b", relancee: true, statut_apres: "ready", session_neuve: true },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    const section = r.racine.querySelector("#acp-questions-bloquees")?.parentElement;
    expect(texteDe(section)).toContain("L'agent repart d'une session neuve, sur la branche déjà commencée.");
    // La carte étrangère n'a pas de bouton ; la carte relançable en a un.
    expect([...(section?.querySelectorAll("button") ?? [])].map((b) => b.textContent)).toEqual(["Relancer"]);
    await saisir(r.racine.querySelector("#acp-relance-t_5e6f7a8b"), "Rétablis l'effort medium.");
    reponses[ROUTE_QUESTIONS] = { ...QUESTIONS };  // la carte quitte la liste après la relance
    await soumettre(r.racine.querySelector("#acp-relance-t_5e6f7a8b")?.closest("form"));
    expect(ecritures(installation)).toEqual([["POST", route, { consigne: "Rétablis l'effort medium." }]]);
    expect(texteDe(section)).toContain(
      "La carte repart : l'agent reprend d'une session neuve, sur la branche déjà commencée. Statut : Prête");
    expect(texteDe(section)).not.toContain("ready");  // constat produit-6 : jamais le code kanban brut
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("une carte d'intégration (sans agent) se relance sans consigne ; aucune session neuve promise", async () => {
    // Relecture finale de P7 (constat scenario-2) : l'exécutant rejoue la même fusion sans lire de consigne.
    aller("?vue=questions");
    const integration = {
      ...ARRETEE_RELANCABLE, carte: "t_1a2b3c4d", titre: "Intégration des branches du projet", assigne: "poste-integration",
      abandonnee: false, raison: "Conflit d'intégration : README.md : aucune résolution automatique.", integration: true,
      quarantaine: false,
    };
    const route = routeRelancerCarte("acp-outil-3dd5", "t_1a2b3c4d");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: { ...QUESTIONS, bloquees: [integration] },
      [`POST ${route}`]: { carte: "t_1a2b3c4d", relancee: true, statut_apres: "ready", session_neuve: false,
                           branche_neuve: false },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    const section = () => texteDe(r.racine.querySelector("#acp-questions-bloquees")?.parentElement);
    expect(section()).toContain(
      "Carte d'intégration, sans agent : « Relancer » rejoue la même fusion des branches, sans consigne.");
    expect(section()).not.toContain("session neuve");
    expect(r.racine.querySelector("#acp-relance-t_1a2b3c4d")).toBeNull();
    reponses[ROUTE_QUESTIONS] = { ...QUESTIONS, bloquees: [] };
    await cliquer(boutons(r.racine).get("Relancer"));
    expect(ecritures(installation)).toEqual([["POST", route, { consigne: null }]]);
    expect(section()).toContain("La carte repart : l'exécutant rejoue la même fusion.");
    expect(section()).not.toContain("session neuve");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("sans consigne : null ; une relance refusée par Hermes le dit ; un refus de l'API est rendu tel quel", async () => {
    aller("?vue=questions");
    const route = routeRelancerCarte("acp-outil-3dd5", "t_5e6f7a8b");
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: file,
      [`POST ${route}`]: { carte: "t_5e6f7a8b", relancee: false, statut_apres: "blocked", session_neuve: false },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    await cliquer(boutons(r.racine).get("Relancer"));
    expect(ecritures(installation)).toEqual([["POST", route, { consigne: null }]]);
    expect(r.texte()).toContain("La carte n'a pas été relancée. Statut : Bloquée");
    r.demonter();
  });
});

describe("discussions en attente (JSON-RPC natif, lecture seule)", () => {
  it("sessionsEnAttente ne garde que « waiting », n'invente rien", () => {
    expect(sessionsEnAttente({ sessions: SESSIONS })).toEqual([
      { cle: "20261002_080000_ab12cd", titre: "Nom du module", apercu: "Quel nom donner au module ?",
        derniereActivite: 1790423000 },
      { cle: "k3", titre: null, apercu: null, derniereActivite: null },
    ]);
    expect(sessionsEnAttente({})).toBeNull();
    expect(sessionsEnAttente(null)).toBeNull();
  });

  it("une seule méthode émise, session.active_list, sans client.capabilities ; connexion fermée", async () => {
    let urlDemandee = "";
    installerSdk({}, { buildWsUrl: async (chemin) => { urlDemandee = chemin; return "ws://hermes.local/api/ws?ticket=t"; } });
    const lecture = await lireDiscussionsEnAttente(1_000, (url) => new SocketFactice(url) as unknown as WebSocket);
    expect(urlDemandee).toBe("/api/ws");
    expect(lecture).toEqual({ connu: true, sessions: sessionsEnAttente({ sessions: SESSIONS }) });
    const socket = SocketFactice.dernier;
    expect(socket?.url).toBe("ws://hermes.local/api/ws?ticket=t");
    expect(socket?.envoyes.map((t) => (JSON.parse(t) as { method: string }).method)).toEqual([METHODE_LISTE]);
    expect(socket?.envoyes.every((t) => t.endsWith("\n"))).toBe(true);
    expect(socket?.ferme).toBe(true);
  });

  it("SDK sans buildWsUrl, ticket refusé ou délai dépassé : inconnu, jamais zéro", async () => {
    installerSdk({});
    expect(await lireDiscussionsEnAttente(50)).toEqual({ connu: false, raison: "sdk" });
    installerSdk({}, { buildWsUrl: async () => { throw new Error("401"); } });
    expect(await lireDiscussionsEnAttente(50)).toEqual({ connu: false, raison: "ticket" });
    installerSdk({}, { buildWsUrl: async () => "ws://x/api/ws" });
    SocketFactice.silencieux = true;
    const lecture = await lireDiscussionsEnAttente(30, (url) => new SocketFactice(url) as unknown as WebSocket);
    expect(lecture).toEqual({ connu: false, raison: "delai" });
    expect(SocketFactice.dernier?.ferme).toBe(true);
  });

  it("la file liste les discussions en attente et les compte dans « À traiter par vous »", async () => {
    aller("?vue=questions");
    vi.stubGlobal("WebSocket", SocketFactice);
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS },
                 { buildWsUrl: async () => "ws://hermes.local/api/ws?ticket=t" });
    const r = await rendre(<Projets />);
    await attendre(8);
    const section = texteDe(r.racine.querySelector("#acp-questions-discussions")?.parentElement);
    expect(section).toContain("Nom du module");
    expect(section).toContain("Quel nom donner au module ?");
    expect(section).toContain("En attente d'une réponse");
    expect(section).toContain("Sans titre");
    expect(section).not.toContain("Autre");
    expect(section).toContain("Les questions posées dans la discussion en terminal (/chat) ne sont visibles que dans cette discussion.");
    // 3 du greffon + 2 discussions en attente.
    expect(r.racine.querySelector('.acp-onglet[aria-current="page"]')?.textContent).toBe("Questions5");
    expect(r.texte()).not.toContain("non comptées");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});

// Relecture finale de P7 : libellés cohérents d'une page à l'autre, jamais un code brut (constats produit-7, produit-9,
// produit-10, produit-11).
describe("libellés de la file, du détail et de la liste", () => {
  it("les sections de la file portent les noms de l'Accueil (produit-9)", async () => {
    aller("?vue=questions");
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS });
    const r = await rendre(<Projets />);
    await attendre();
    const titres = ["#acp-questions-ouvertes", "#acp-questions-triage", "#acp-questions-revues",
                    "#acp-questions-bloquees"].map((id) => texteDe(r.racine.querySelector(id)));
    expect(titres).toEqual(["Questions", "Décisions", "Revues", "Cartes arrêtées"]);
    r.demonter();
  });

  it("une question ouverte sans carte « répondre » est dite « à vous » partout (produit-11)", async () => {
    aller("?vue=questions");
    const [q] = QUESTIONS.questions;
    const ouverte = { ...q, etat: "ouverte", carte_repondre: null, chez: "proprietaire", motif_escalade: null };
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: { ...QUESTIONS, questions: [ouverte] } });
    const r = await rendre(<Projets />);
    await attendre();
    const entree = texteDe(r.racine.querySelector("#acp-questions-ouvertes")?.parentElement);
    expect(entree).toContain("ÉtatVotre réponse est attendue");
    expect(entree).not.toContain("Hermes cherche la réponse");
    r.demonter();
    aller(`?projet=${DETAIL.projet.id}`);
    const detail = { projet: { ...DETAIL.projet, questions_ouvertes: [
      { id: "q_b627a3c245ec", carte: "t_7aa28f61", etat: "ouverte", texte: "Quelle version de Python viser ?",
        carte_repondre: null, chez: "proprietaire" }] } };
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS, [routeProjet(DETAIL.projet.id)]: detail });
    const r2 = await rendre(<Projets />);
    await attendre();
    expect(texteDe(r2.racine.querySelector("#acp-projet-questions")?.parentElement)).toContain("Votre réponse est attendue");
    r2.demonter();
  });

  it("le journal du projet dit en français les actions de P6 et de P7 (produit-7)", async () => {
    aller(`?projet=${DETAIL.projet.id}`);
    const actions = ["relance", "reglage_reponses", "cloture", "revue_acceptee", "revue_refusee", "integration",
                     "carte_servie", "carte_bloquee", "carte_bloquee_ecart", "carte_non_construite", "carte_voie_fermee",
                     "carte_etrangere_bloquee", "attente_quota_levee"];
    const journal = actions.map((action, rang) => ({ quand: 1790423039 + rang, acteur: "acp-poste", action,
                                                     cible: "t_7aa28f61", detail: null }));
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS,
                   [routeProjet(DETAIL.projet.id)]: { projet: { ...DETAIL.projet, journal } } });
    const r = await rendre(<Projets />);
    await attendre();
    const bloc = r.racine.querySelector("#acp-projet-journal")?.parentElement;
    const textes = texteDe(bloc);
    for (const action of actions) expect(textes, action).not.toContain(action);
    for (const libelle of ["Carte relancée", "Qui répond changé", "Projet clos", "Revue acceptée", "Revue refusée",
                           "Intégration demandée", "Carte servie à l'exécutant", "Carte bloquée par l'exécutant"]) {
      expect(textes).toContain(libelle);
    }
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("la carte de la machine dit « Exécutant Railway », « Poste Windows » ou « Exécutant », jamais à tort (produit-10)",
     async () => {
    for (const [poste, titre] of [[{ hote: "railway", plateforme: "linux" }, "Exécutant Railway"],
                                  [{ hote: "pc", plateforme: "windows" }, "Poste Windows"],
                                  [null, "Exécutant"]] as const) {
      aller("");
      installerSdk({ [ROUTE_PROJETS]: { ...LISTE, poste: { ...LISTE.poste, poste } }, [ROUTE_QUESTIONS]: QUESTIONS });
      const r = await rendre(<Projets />);
      await attendre();
      expect(texteDe(r.racine.querySelector("#acp-projets-poste"))).toBe(titre);
      r.demonter();
    }
  });
});

describe("détail : « Qui répond » et « Clore le projet »", () => {
  it("« Qui répond » ne change qu'après la réponse de l'API, et dit les questions ouvertes non touchées", async () => {
    aller(`?projet=${DETAIL.projet.id}`);
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS, [routeProjet(DETAIL.projet.id)]: DETAIL,
      [`POST ${routeReponsesProjet(DETAIL.projet.id)}`]: {
        projet: { ...DETAIL.projet, reponses: "hermes_d_abord" }, avant: "proprietaire", apres: "hermes_d_abord",
        questions_ouvertes_inchangees: 1 },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    await cliquer(boutons(r.racine).get("Changer qui répond"));
    const choix = r.racine.querySelector("#acp-projet-qui-repond") as HTMLSelectElement;
    expect(choix.value).toBe("proprietaire");
    await saisir(choix, "hermes_d_abord");
    // Rien ne change avant la réponse (dt puis dd) ; le réglage se lit « Vous », comme dans la file (constat produit-9).
    expect(r.texte()).toContain("Qui répondVous");
    reponses[routeProjet(DETAIL.projet.id)] = { projet: { ...DETAIL.projet, reponses: "hermes_d_abord" } };
    await soumettre(choix.closest("form"));
    expect(ecritures(installation)).toEqual([["POST", routeReponsesProjet(DETAIL.projet.id), { reponses: "hermes_d_abord" }]]);
    expect(r.texte()).toContain("Réglage enregistré pour les questions suivantes. Questions ouvertes qui gardent leur traitement : 1");
    expect(r.texte()).toContain("Qui répondHermes d'abord");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("projet sans dépôt : « Qui répond » est sans objet, aucun bouton", async () => {
    aller(`?projet=${DETAIL.projet.id}`);
    installerSdk({ [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS,
                   [routeProjet(DETAIL.projet.id)]: { projet: { ...DETAIL.projet, depot: null } } });
    const r = await rendre(<Projets />);
    await attendre();
    expect(r.texte()).toContain("Qui répondSans objet (projet sans dépôt)");
    expect(boutons(r.racine).has("Changer qui répond")).toBe(false);
    r.demonter();
  });

  it("« Clore le projet » : confirmation qui dit les quatre points, puis le résultat de l'API", async () => {
    aller(`?projet=${DETAIL.projet.id}`);
    const reponses: Record<string, Reponse> = {
      [ROUTE_PROJETS]: LISTE, [ROUTE_QUESTIONS]: QUESTIONS, [routeProjet(DETAIL.projet.id)]: DETAIL,
      [`POST ${routeClore(DETAIL.projet.id)}`]: {
        projet: { ...DETAIL.projet, etat: "abandonne" }, clos: true, etat: "abandonne",
        cartes_archivees: ["t_7aa28f61", "t_8bb39f72"], cartes_non_archivees: [], questions_annulees: 1,
        branches_rapportees: ["acp/p_367e23fd51b7/t_7aa28f61"] },
    };
    const installation = installerSdk(reponses);
    const r = await rendre(<Projets />);
    await attendre();
    await cliquer(boutons(r.racine).get("Clore le projet"));
    const confirmation = texteDe(r.racine.querySelector(".acp-confirmation"));
    for (const point of [
      "Clore ce projet ?",
      "Les cartes ouvertes du projet sont archivées ; un travail en cours est arrêté.",
      "Ses questions ouvertes sont annulées.",
      "Le projet passe « Terminé » si la synthèse du tour en cours est faite, sinon « Abandonné ».",
      "Aucune notification n'est envoyée ; les branches déjà rapportées restent sur l'exécutant jusqu'à leur purge (7 jours).",
    ]) {
      expect(confirmation).toContain(point);
    }
    expect(ecritures(installation)).toEqual([]);  // rien avant la confirmation
    reponses[routeProjet(DETAIL.projet.id)] = { projet: { ...DETAIL.projet, etat: "abandonne" } };
    await cliquer(boutons(r.racine).get("Confirmer la clôture"));
    expect(ecritures(installation)).toEqual([["POST", routeClore(DETAIL.projet.id), { confirmation: true }]]);
    const texte = r.texte();
    expect(texte).toContain("Projet clos : abandonné (la synthèse du tour en cours n'était pas faite).");
    expect(texte).toContain("Cartes archivées : 2");
    expect(texte).toContain("Questions annulées : 1");
    expect(texte).toContain("acp/p_367e23fd51b7/t_7aa28f61");
    expect(boutons(r.racine).has("Clore le projet")).toBe(false);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});
