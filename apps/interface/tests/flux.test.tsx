// Flux d'invalidation côté interface (cahier P7 § 5.4, § 13.4) : analyseur SSE (trames coupées n'importe où,
// multi-lignes, commentaires, retry, fins de ligne), flux partagé (UN flux par onglet, partagé par deux copies du
// module comme deux bundles, fermé 5 s après le dernier abonné, Last-Event-ID, reprise, repli après trois échecs,
// 401 jamais réessayé, page cachée), useDonnees (relecture sur signal regroupée, intervalles, erreur gardée) et ce que
// la page dit de son actualisation.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EtatActualisation } from "../src/actualisation";
import { INTERVALLE_SONDAGE_MS, intervalleDeRelecture, RELECTURE_DISCUSSIONS_MS, RELECTURE_SURETE_MS, useDonnees } from "../src/donnees";
import {
  AnalyseurSse,
  ECHECS_AVANT_REPLI,
  FERMETURE_DIFFEREE_MS,
  fluxPartage,
  NOUVEL_ESSAI_MS,
  ROUTE_FLUX,
  SUJETS,
  type Sujet,
  type TrameSse,
} from "../src/flux";
import { h, type Noeud } from "../src/react";
import type { SdkHermes } from "../src/sdk";
import { attendre, installerSdk, rendre } from "./sdk-factice";
// @ts-expect-error — module JavaScript de construction, sans déclaration de types.
import { construire } from "../esbuild.mjs";

// ------------------------------------------------------------------ outils : corps de flux et authedFetch factices

class CorpsFactice {
  private file: Array<Uint8Array | null | Error> = [];
  private attente: (() => void) | null = null;
  annule = false;
  private readonly encodeur = new TextEncoder();

  envoyer(texte: string): void {
    this.pousser(this.encodeur.encode(texte));
  }

  fermer(): void {
    this.pousser(null);
  }

  echouer(): void {
    this.pousser(new TypeError("network error"));
  }

  private pousser(element: Uint8Array | null | Error): void {
    this.file.push(element);
    this.attente?.();
    this.attente = null;
  }

  lecteur() {
    return {
      read: async (): Promise<{ value?: Uint8Array; done: boolean }> => {
        while (this.file.length === 0) await new Promise<void>((r) => (this.attente = r));
        const element = this.file.shift();
        if (element instanceof Error) throw element;
        return element === null || element === undefined ? { done: true } : { value: element, done: false };
      },
      cancel: async () => {
        this.annule = true;
      },
    };
  }
}

interface Appel {
  url: string;
  entetes: Record<string, string>;
  corps: CorpsFactice;
  signal: AbortSignal | undefined;
}

/** authedFetch factice : chaque appel ouvre un corps contrôlé par le test ; ``statuts`` impose les statuts suivants. */
function serveurFlux(statuts: number[] = []) {
  const appels: Appel[] = [];
  const authedFetch = (async (url: string, init?: RequestInit) => {
    const corps = new CorpsFactice();
    const entetes = { ...(init?.headers as Record<string, string>) };
    appels.push({ url, entetes, corps, signal: init?.signal ?? undefined });
    init?.signal?.addEventListener("abort", () => corps.echouer());
    const status = statuts.length > 0 ? (statuts.shift() as number) : 200;
    return { status, ok: status >= 200 && status < 300, body: { getReader: () => corps.lecteur() } } as unknown as Response;
  }) as NonNullable<SdkHermes["authedFetch"]>;
  return { appels, authedFetch, dernier: () => appels[appels.length - 1] };
}

const ETAT = (revision: string, sujets: readonly string[] = SUJETS, suivies = true) =>
  `retry: 3000\n\nid: ${revision}\nevent: etat\ndata: ${JSON.stringify({ revision, sujets, discussions_suivies: suivies })}\n\n`;
const CHANGEMENT = (revision: string, sujets: string[]) =>
  `id: ${revision}\nevent: changement\ndata: ${JSON.stringify({ sujets })}\n\n`;
const FIN = 'event: fin\ndata: {"raison":"duree_max"}\n\n';

async function vider(ms = 0): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

// ------------------------------------------------------------------ analyseur

describe("AnalyseurSse", () => {
  const FLUX = `retry: 3000\n\nid: 7.1\nevent: etat\ndata: {"a":1}\n\n: battement\n\nid: 7.2\nevent: changement\r\n` +
    `data: ligne 1\rdata: ligne 2\r\ndata:sans espace\n\nevent: fin\ndata: {"raison":"duree_max"}\n\n` +
    `champ_inconnu: x\nid\n\nid: 9\n\n`;
  const ATTENDU: TrameSse[] = [
    { id: "7.1", evenement: "etat", donnees: '{"a":1}' },
    { id: "7.2", evenement: "changement", donnees: "ligne 1\nligne 2\nsans espace" },
    { id: "7.2", evenement: "fin", donnees: '{"raison":"duree_max"}' },
  ];

  it("lit trames, multi-lignes, commentaires, retry, identifiant persistant et champs inconnus", () => {
    const analyseur = new AnalyseurSse();
    expect(analyseur.pousser(FLUX)).toEqual(ATTENDU);
    expect(analyseur.retry).toBe(3000);
    expect(analyseur.commentaires).toBe(1);
    // « id » sans valeur vide l'identifiant ; une trame sans « data » n'est pas émise mais son « id » compte.
    expect(analyseur.dernierId).toBe("9");
  });

  it("donne le même résultat quel que soit le découpage des morceaux (y compris entre \\r et \\n)", () => {
    for (let coupe = 0; coupe <= FLUX.length; coupe += 1) {
      for (const pas of [1, 3, 7]) {
        const analyseur = new AnalyseurSse();
        const trames = [...analyseur.pousser(FLUX.slice(0, coupe))];
        for (let i = coupe; i < FLUX.length; i += pas) trames.push(...analyseur.pousser(FLUX.slice(i, i + pas)));
        expect(trames, `coupe ${coupe}, pas ${pas}`).toEqual(ATTENDU);
      }
    }
  });

  it("lit les trames exemples publiées pour le desktop (hermes/tests/outils/fixtures_flux)", () => {
    const dossier = join(process.cwd(), "..", "..", "hermes", "tests", "outils", "fixtures_flux");
    const lire = (nom: string) => new AnalyseurSse().pousser(readFileSync(join(dossier, nom), "utf8"));
    const [ouverture] = lire("ouverture.txt");
    expect(ouverture.evenement).toBe("etat");
    expect(JSON.parse(ouverture.donnees)).toEqual({ revision: "1727791200.41", sujets: [...SUJETS],
                                                    discussions_suivies: true });
    expect(JSON.parse(lire("reprise.txt")[0].donnees).sujets).toEqual([]);
    expect(lire("changement.txt")).toEqual([{ id: "1727791200.42", evenement: "changement",
                                              donnees: '{"sujets":["projets","questions"]}' }]);
    expect(JSON.parse(lire("illisible.txt")[0].donnees).illisibles).toEqual(["projets", "questions"]);
    expect(lire("battement.txt")).toEqual([]);
    expect(lire("fin.txt")[0].evenement).toBe("fin");
  });
});

// ------------------------------------------------------------------ flux partagé

describe("flux partagé de l'onglet", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
  });
  afterEach(() => {
    vi.useRealTimers();
    delete (document as unknown as { visibilityState?: unknown }).visibilityState;
  });

  it("un seul flux pour deux copies du module (deux bundles), fermé 5 s après le dernier abonné", async () => {
    const serveur = serveurFlux();
    installerSdk({}, { authedFetch: serveur.authedFetch });
    vi.resetModules();
    const bundleA = await import("../src/flux");
    vi.resetModules();
    const bundleB = await import("../src/flux");
    expect(bundleA.FluxPartage).not.toBe(bundleB.FluxPartage); // deux copies du code, comme deux bundles IIFE
    const fluxA = bundleA.fluxPartage();
    expect(bundleB.fluxPartage()).toBe(fluxA);
    expect(Object.keys(window.__ACP_FLUX__ ?? {})).toEqual(["v1"]);
    const recusA: Sujet[][] = [];
    const recusB: Sujet[][] = [];
    const finA = fluxA.abonner(["projets"], (s) => recusA.push(s));
    const finB = bundleB.fluxPartage().abonner(["poste", "quotas"], (s) => recusB.push(s));
    await vider();
    expect(serveur.appels.length).toBe(1);
    expect(serveur.dernier().url).toBe(ROUTE_FLUX);
    expect(serveur.dernier().entetes).toEqual({ Accept: "text/event-stream" });
    serveur.dernier().corps.envoyer(ETAT("5.0"));
    await vider();
    expect(fluxA.etat()).toEqual({ mode: "temps_reel", discussionsSuivies: true });
    expect(recusA).toEqual([["projets"]]);
    expect(recusB).toEqual([["poste", "quotas"]]);
    serveur.dernier().corps.envoyer(CHANGEMENT("5.1", ["quotas", "pause"]));
    await vider();
    expect(recusA).toEqual([["projets"]]);
    expect(recusB).toEqual([["poste", "quotas"], ["quotas"]]);
    finA();
    finB();
    await vider(FERMETURE_DIFFEREE_MS - 100);
    expect(serveur.dernier().signal?.aborted).toBe(false); // pas de reconnexion à chaque changement de vue
    const reprise = fluxA.abonner(["projets"], () => undefined);
    await vider(FERMETURE_DIFFEREE_MS + 100);
    expect(serveur.appels.length).toBe(1);
    reprise();
    await vider(FERMETURE_DIFFEREE_MS);
    expect(serveur.dernier().signal?.aborted).toBe(true);
    expect(fluxA.abonnements()).toBe(0);
  });

  it("rouvre aussitôt après « fin » avec Last-Event-ID, et reprend après une coupure", async () => {
    const serveur = serveurFlux();
    installerSdk({}, { authedFetch: serveur.authedFetch });
    const flux = fluxPartage();
    const recus: Sujet[][] = [];
    flux.abonner(["questions"], (s) => recus.push(s));
    await vider();
    serveur.dernier().corps.envoyer(ETAT("8.3") + CHANGEMENT("8.4", ["questions"]) + FIN);
    serveur.dernier().corps.fermer();
    await vider();
    expect(serveur.appels.length).toBe(2);
    expect(serveur.dernier().entetes["Last-Event-ID"]).toBe("8.4");
    serveur.dernier().corps.envoyer(ETAT("8.4", []));
    await vider();
    expect(recus).toEqual([["questions"], ["questions"]]); // rien de plus : la révision n'avait pas bougé
    serveur.dernier().corps.echouer(); // coupure réseau : reprise après 1 s, le mode reste « temps réel »
    await vider();
    expect(flux.etat().mode).toBe("temps_reel");
    await vider(999);
    expect(serveur.appels.length).toBe(2);
    await vider(1);
    expect(serveur.appels.length).toBe(3);
  });

  it("trois échecs de suite en 2 min : repli sur le sondage, nouvel essai toutes les 5 min", async () => {
    const serveur = serveurFlux([503, 429, 502, 200]);
    installerSdk({}, { authedFetch: serveur.authedFetch });
    const flux = fluxPartage();
    const modes: string[] = [];
    flux.ecouter((e) => modes.push(e.mode));
    flux.abonner(["poste"], () => undefined);
    await vider();
    await vider(1_000);
    await vider(2_000);
    expect(serveur.appels.length).toBe(ECHECS_AVANT_REPLI);
    expect(flux.etat().mode).toBe("sondage");
    await vider(NOUVEL_ESSAI_MS - 1);
    expect(serveur.appels.length).toBe(3);
    await vider(1);
    expect(serveur.appels.length).toBe(4);
    serveur.dernier().corps.envoyer(ETAT("9.0"));
    await vider();
    expect(modes).toEqual(["sondage", "temps_reel"]);
  });

  it("un 401 n'est jamais réessayé : le flux s'arrête, les pages sondent par fetchJSON (qui redirige)", async () => {
    const serveur = serveurFlux([401]);
    installerSdk({}, { authedFetch: serveur.authedFetch });
    const flux = fluxPartage();
    flux.abonner(["projets"], () => undefined);
    await vider(NOUVEL_ESSAI_MS * 3);
    expect(serveur.appels.length).toBe(1);
    expect(flux.etat().mode).toBe("sondage");
  });

  it("page cachée : flux fermé ; retour : rouvert", async () => {
    let visibilite: DocumentVisibilityState = "visible";
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibilite });
    const serveur = serveurFlux();
    installerSdk({}, { authedFetch: serveur.authedFetch });
    fluxPartage().abonner(["projets"], () => undefined);
    await vider();
    serveur.dernier().corps.envoyer(ETAT("3.0"));
    await vider();
    visibilite = "hidden";
    document.dispatchEvent(new Event("visibilitychange"));
    await vider(60_000);
    expect(serveur.appels.length).toBe(1);
    expect(serveur.dernier().signal?.aborted).toBe(true);
    visibilite = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    await vider();
    expect(serveur.appels.length).toBe(2);
    expect(serveur.dernier().entetes["Last-Event-ID"]).toBe("3.0");
  });

  it("SDK sans authedFetch : mode « indisponible », aucune requête de flux", async () => {
    installerSdk({});
    const flux = fluxPartage();
    flux.abonner(["projets"], () => undefined);
    await vider();
    expect(flux.etat().mode).toBe("indisponible");
  });

  it("chaque bundle des pages passe par le registre partagé window.__ACP_FLUX__", async () => {
    const sorties: Map<string, string> = await construire();
    for (const [chemin, contenu] of sorties) {
      if (!/acp-(projets|poste-vues)[\\/]dashboard[\\/]dist[\\/]index\.js$/.test(chemin)) continue;
      expect(contenu, chemin).toContain("__ACP_FLUX__");
      expect(contenu, chemin).toContain(ROUTE_FLUX);
    }
  });
});

// ------------------------------------------------------------------ useDonnees et état affiché

function Sonde(props: { charger: () => Promise<string>; sujets: Sujet[] }): Noeud {
  const lecture = useDonnees(props.charger, 0, props.sujets);
  return (
    <div>
      <span data-test="valeur">{lecture.valeur ?? "rien"}</span>
      <span data-test="erreur">{lecture.erreur ? "erreur" : "ok"}</span>
      <EtatActualisation />
    </div>
  );
}

describe("useDonnees", () => {
  beforeEach(() => {
    // Le temps avance aussi de lui-même : le rendu (rendre) attend une minuterie nulle.
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("intervalles : 120 s en temps réel, 60 s pour des discussions non suivies, 15 s sinon", () => {
    expect(intervalleDeRelecture({ mode: "temps_reel", discussionsSuivies: true }, ["projets"])).toBe(RELECTURE_SURETE_MS);
    expect(intervalleDeRelecture({ mode: "temps_reel", discussionsSuivies: false }, ["discussions"])).toBe(
      RELECTURE_DISCUSSIONS_MS);
    expect(intervalleDeRelecture({ mode: "temps_reel", discussionsSuivies: false }, ["projets"])).toBe(
      RELECTURE_SURETE_MS);
    for (const mode of ["connexion", "sondage", "indisponible"] as const) {
      expect(intervalleDeRelecture({ mode, discussionsSuivies: null }, ["projets"])).toBe(INTERVALLE_SONDAGE_MS);
    }
  });

  it("relit sur signal de SES sujets, regroupé sur 300 ms, et dit le temps réel", async () => {
    const serveur = serveurFlux();
    installerSdk({}, { authedFetch: serveur.authedFetch });
    let lectures = 0;
    const r = await rendre(<Sonde charger={async () => `lecture ${(lectures += 1)}`} sujets={["questions"]} />);
    expect(lectures).toBe(1);
    expect(r.texte()).toContain("Connexion au temps réel en cours");
    serveur.dernier().corps.envoyer(ETAT("4.0"));
    await vider(300);
    expect(lectures).toBe(2); // première trame : tout est relu une fois (rien n'est supposé à jour)
    expect(r.texte()).toContain("Page actualisée en temps réel tant qu'elle est visible.");
    serveur.dernier().corps.envoyer(CHANGEMENT("4.1", ["questions"]) + CHANGEMENT("4.2", ["projets", "questions"]));
    await vider(200);
    expect(lectures).toBe(2);
    await vider(100);
    expect(lectures).toBe(3); // deux trames, une lecture
    serveur.dernier().corps.envoyer(CHANGEMENT("4.3", ["poste"]));
    await vider(1_000);
    expect(lectures).toBe(3); // pas son sujet
    await vider(RELECTURE_SURETE_MS);
    expect(lectures).toBe(4); // relecture de sûreté
    expect(r.racine.querySelector('[data-test="valeur"]')?.textContent).toBe("lecture 4");
    r.demonter();
  });

  it("repli annoncé : sondage de 15 s après trois échecs, et l'erreur d'une lecture garde la valeur", async () => {
    const serveur = serveurFlux([503, 503, 503]);
    installerSdk({}, { authedFetch: serveur.authedFetch });
    let echoue = false;
    let lectures = 0;
    const charger = async () => {
      lectures += 1;
      if (echoue) throw new TypeError("Failed to fetch");
      return "valeur lue";
    };
    const r = await rendre(<Sonde charger={charger} sujets={["projets"]} />);
    await vider(3_000);
    expect(r.texte()).toContain("Temps réel indisponible : actualisation toutes les 15 secondes");
    expect(r.racine.querySelector("[data-acp-temps-reel]")?.getAttribute("data-acp-temps-reel")).toBe("sondage");
    const avant = lectures;
    echoue = true;
    await vider(INTERVALLE_SONDAGE_MS);
    expect(lectures).toBe(avant + 1);
    expect(r.racine.querySelector('[data-test="valeur"]')?.textContent).toBe("valeur lue");
    expect(r.racine.querySelector('[data-test="erreur"]')?.textContent).toBe("erreur");
    r.demonter();
  });

  it("SDK sans authedFetch : la page le dit et sonde toutes les 15 s", async () => {
    installerSdk({});
    let lectures = 0;
    const r = await rendre(<Sonde charger={async () => String((lectures += 1))} sujets={["projets"]} />);
    await attendre();
    expect(r.texte()).toContain("Temps réel non pris en charge par ce tableau de bord");
    await vider(INTERVALLE_SONDAGE_MS);
    expect(lectures).toBe(2);
    r.demonter();
  });
});
