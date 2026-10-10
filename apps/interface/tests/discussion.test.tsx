// Étape P7, part D (cahier P7 § 9, § 13.4 ; correction K14) : discussion réduite sur le JSON-RPC natif du tableau de
// bord. Canal (liste blanche des méthodes émises et de leurs paramètres, -32601 sur toute requête du serveur autre que
// « clarify », forme des réponses), conversation (création au premier envoi, texte en flux, reprise avec les requêtes
// ouvertes, interruption, reconnexion 1-2-5-10 s), et page (liste, fil, question, textes du catalogue français).
//
// Hermes est joué par un WebSocket factice qui suit le protocole de tui_gateway/ws.py (gateway.ready d'abord, une
// trame par message JSON, sans saut de ligne final) ; le canal RÉEL (src/jsonrpc/canal.ts) s'y connecte.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { h } from "../src/react";
import {
  CODE_NON_TRAITEE,
  ErreurCanal,
  METHODES_PERMISES,
  ouvrirCanal,
  reponseClarifyValide,
  verifierAppel,
  type OptionsCanal,
} from "../src/jsonrpc/canal";
import {
  Conversation,
  demandeDe,
  reponseDe,
  texteDeReponse,
  type EtatConversation,
} from "../src/discussion/conversation";
import { Discussion } from "../src/discussion/Discussion";
import { ROUTE_DISCUSSIONS } from "../src/discussion/Liste";
import { rechercheDeVue, vueDepuisAdresse } from "../src/discussion/vue";
import { CATALOGUE } from "./catalogue-chaines";
import { ApiErrorHermes, attendre, installerSdk, rendre, textesHorsCatalogue } from "./sdk-factice";

type Trame = Record<string, unknown>;

const SID = "rt-0001";
const CLE = "20261002_140000_abc123";
const URL_WS = "ws://hermes.local/api/ws?ticket=t";

/** Hermes factice derrière /api/ws : répond aux méthodes, émet des événements et des requêtes à la demande. */
class HermesWs {
  static instances: HermesWs[] = [];
  static reprise: Trame | { erreur: { code: number; message: string } } = {};
  static actifs: unknown[] = [];
  static silencieux = false;
  /** Joué juste avant la réponse à session.resume (événements et requêtes arrivés pendant la reprise). */
  static avantReprise: ((ws: HermesWs) => void) | null = null;
  envoyes: Trame[] = [];
  brutes: string[] = [];
  ferme = false;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(readonly url: string) {
    HermesWs.instances.push(this);
    setTimeout(() => this.recevoir({ jsonrpc: "2.0", method: "event", params: { type: "gateway.ready", payload: {} } }), 0);
  }

  static dernier(): HermesWs {
    const ws = HermesWs.instances[HermesWs.instances.length - 1];
    if (!ws) throw new Error("aucune connexion");
    return ws;
  }

  recevoir(message: unknown): void {
    if (this.ferme) return;
    this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent);
  }

  evenement(type: string, payload?: unknown, sessionId: string = SID): void {
    this.recevoir({ jsonrpc: "2.0", method: "event",
                    params: { type, session_id: sessionId, ...(payload === undefined ? {} : { payload }) } });
  }

  requete(id: string, methode: string, params: Trame): void {
    this.recevoir({ jsonrpc: "2.0", id, method: methode, params: { session_id: SID, ...params } });
  }

  send(texte: string): void {
    this.brutes.push(texte);
    const m = JSON.parse(texte) as Trame;
    this.envoyes.push(m);
    if (typeof m.method !== "string" || HermesWs.silencieux) return;
    const repondre = (resultat: unknown) =>
      setTimeout(() => this.recevoir({ jsonrpc: "2.0", id: m.id, result: resultat }), 0);
    switch (m.method) {
      case "client.capabilities":
        repondre({ server_requests: ["clarify", "approval", "sudo", "secret"] });
        return;
      case "session.resume": {
        const r = HermesWs.reprise;
        if ("erreur" in r) {
          setTimeout(() => this.recevoir({ jsonrpc: "2.0", id: m.id, error: r.erreur }), 0);
          return;
        }
        const avant = HermesWs.avantReprise;
        if (avant) setTimeout(() => avant(this), 0);
        repondre(r);
        return;
      }
      case "session.create":
        repondre({ session_id: SID, stored_session_id: CLE, message_count: 0, messages: [], info: {} });
        return;
      case "prompt.submit":
        repondre({ status: "streaming" });
        return;
      case "session.interrupt":
        repondre({ status: "interrupted" });
        return;
      case "session.active_list":
        repondre({ sessions: HermesWs.actifs });
        return;
      default:
        repondre({});
    }
  }

  close(): void {
    this.ferme = true;
  }

  /** Fermeture côté serveur ou réseau. */
  couper(): void {
    this.ferme = true;
    this.onclose?.();
  }

  methodes(): string[] {
    return this.envoyes.filter((t) => typeof t.method === "string").map((t) => t.method as string);
  }

  appel(methode: string): Trame | undefined {
    return this.envoyes.find((t) => t.method === methode);
  }

  reponses(): Trame[] {
    return this.envoyes.filter((t) => t.method === undefined);
  }
}

const fabrique = (url: string) => new HermesWs(url) as unknown as WebSocket;
const ouvrirFactice = (options: OptionsCanal) => ouvrirCanal({ ...options, fabrique, intervallePingMs: 0 });

const CLARIFY_LOT = {
  questions: [{ qid: "q0", question: "Quel nom donner au module ?", choices: ["outil.py (Recommended)", "module.py"],
                multi_select: false }],
};

function repriseAvec(extra: Trame = {}): Trame {
  return {
    session_id: SID, session_key: CLE, message_count: 3, info: { title: "Nom du module" }, running: false,
    messages: [
      { role: "user", text: "Prépare le module." },
      { role: "system", text: "caché", display_kind: "hidden" },
      { role: "tool", name: "clarify", content: "{}" },
      { role: "assistant", text: "Voici <b>gras</b>\nsur deux lignes." },
    ],
    ...extra,
  };
}

async function tours(n = 6): Promise<void> {
  for (let i = 0; i < n; i += 1) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
}

function installer(options: { buildWsUrl?: boolean; reponses?: Record<string, unknown> } = {}) {
  return installerSdk(options.reponses ?? {}, options.buildWsUrl === false ? {} : {
    buildWsUrl: async (chemin) => {
      if (chemin !== "/api/ws") throw new Error(`chemin inattendu ${chemin}`);
      return URL_WS;
    },
  });
}

beforeEach(() => {
  HermesWs.instances = [];
  HermesWs.reprise = repriseAvec();
  HermesWs.actifs = [];
  HermesWs.silencieux = false;
  HermesWs.avantReprise = null;
  window.history.replaceState(null, "", "/discussion");
});

afterEach(() => {
  vi.useRealTimers();
});

// =================================================================================================== canal

describe("canal : liste blanche des méthodes émises (K14)", () => {
  it("la liste est exacte, et clarify.lock n'en fait pas partie", () => {
    expect(Object.keys(METHODES_PERMISES).sort()).toEqual([
      "client.capabilities", "ping", "prompt.submit", "session.active_list", "session.create", "session.interrupt",
      "session.resume",
    ]);
    expect(METHODES_PERMISES["session.create"]).toEqual([]);
  });

  it("toute autre méthode est refusée avant l'envoi", () => {
    for (const methode of ["session.activate", "clarify.lock", "request.answer", "config.set", "cron.create",
                           "tools.list", "profiles.switch", "session.close", "slash.exec", "shell.exec",
                           "session.delete", "approval.respond"]) {
      expect(() => verifierAppel(methode, {}), methode).toThrow(ErreurCanal);
      try {
        verifierAppel(methode, {});
      } catch (erreur) {
        expect((erreur as ErreurCanal).genre).toBe("methode");
      }
    }
  });

  it("session.create ne part jamais avec fast, model, provider, close_on_disconnect, cwd ni source", () => {
    for (const cle of ["fast", "model", "provider", "close_on_disconnect", "cwd", "source", "reasoning_effort"]) {
      expect(() => verifierAppel("session.create", { [cle]: false }), cle).toThrow(/parametre/);
    }
    expect(() => verifierAppel("session.resume", { session_id: CLE, close_on_disconnect: true })).toThrow(/parametre/);
    expect(() => verifierAppel("prompt.submit", { session_id: SID, text: "x", truncate_before_row_id: 3 }))
      .toThrow(/parametre/);
    expect(() => verifierAppel("session.create", {})).not.toThrow();
  });

  it("un appel hors liste n'envoie rien sur le fil", async () => {
    installer();
    const canal = await ouvrirFactice({ capacites: false });
    const ws = HermesWs.dernier();
    const avant = ws.brutes.length;
    await expect(canal.appeler("config.set" as never, {})).rejects.toMatchObject({ genre: "methode" });
    await expect(canal.appeler("session.create", { fast: true })).rejects.toMatchObject({ genre: "parametre" });
    expect(ws.brutes.length).toBe(avant);
    canal.fermer();
  });
});

describe("canal : connexion et requêtes du serveur", () => {
  it("ticket neuf sur /api/ws, gateway.ready attendu, puis client.capabilities { server_requests: true }", async () => {
    installer();
    const canal = await ouvrirFactice({ capacites: true });
    const ws = HermesWs.dernier();
    expect(ws.url).toBe(URL_WS);
    expect(ws.envoyes[0]).toMatchObject({ jsonrpc: "2.0", method: "client.capabilities",
                                          params: { server_requests: true } });
    expect(ws.brutes.every((t) => t.endsWith("\n"))).toBe(true);
    await ouvrirFactice({ capacites: true });
    expect(HermesWs.instances.length).toBe(2);
    canal.fermer();
    expect(ws.ferme).toBe(true);
  });

  it("toute requête autre que clarify reçoit -32601 aussitôt ; clarify est remise à la page sans réponse", async () => {
    installer();
    const refus: string[] = [];
    const clarify: string[] = [];
    await ouvrirFactice({ capacites: true, surRefus: (m) => refus.push(m), surClarify: (r) => clarify.push(r.id) });
    const ws = HermesWs.dernier();
    const methodes = ["approval", "sudo", "secret", "vault.unlock_prompt", "display.install.sudo", "tour"];
    methodes.forEach((m, i) => ws.requete(`srq-${i}`, m, {}));
    ws.requete("srq-c", "clarify", { question: "Oui ?" });
    expect(refus).toEqual(methodes);
    expect(clarify).toEqual(["srq-c"]);
    expect(ws.reponses()).toEqual(methodes.map((_, i) => ({
      jsonrpc: "2.0", id: `srq-${i}`, error: { code: CODE_NON_TRAITEE, message: "Méthode non traitée par ACP" } })));
  });

  it("réponse à clarify : seulement { answer } ou { answers }, une fois, pour une requête ouverte sur ce canal", async () => {
    expect(reponseClarifyValide({ answer: "a" })).toBe(true);
    expect(reponseClarifyValide({ answers: { q0: "a", q1: "" } })).toBe(true);
    for (const mauvaise of [{}, { answer: 3 }, { answer: "a", answers: {} }, { answers: { q0: 1 } }, { value: "x" },
                            { choice: "once" }, null, [], "a"]) {
      expect(reponseClarifyValide(mauvaise), JSON.stringify(mauvaise)).toBe(false);
    }
    installer();
    const canal = await ouvrirFactice({ capacites: true, surClarify: () => undefined });
    const ws = HermesWs.dernier();
    ws.requete("srq-1", "clarify", { question: "Oui ?" });
    expect(() => canal.repondreClarify("srq-inconnue", { answer: "x" })).toThrow(ErreurCanal);
    expect(() => canal.repondreClarify("srq-1", { value: "x" } as never)).toThrow(ErreurCanal);
    canal.repondreClarify("srq-1", { answer: "Oui." });
    expect(() => canal.repondreClarify("srq-1", { answer: "encore" })).toThrow(ErreurCanal);
    expect(ws.reponses()).toEqual([{ jsonrpc: "2.0", id: "srq-1", result: { answer: "Oui." } }]);
  });

  it("session.resume rejoue les requêtes ouvertes : clarify devient répondable, approval reçoit -32601", async () => {
    installer();
    const refus: string[] = [];
    HermesWs.reprise = repriseAvec({ open_requests: [
      { id: "srq-a", method: "approval", params: { session_id: SID, request_id: "r", command: "rm -rf /" } },
      { id: "srq-c", method: "clarify", params: { session_id: SID, ...CLARIFY_LOT } },
    ] });
    const canal = await ouvrirFactice({ capacites: true, surClarify: () => undefined, surRefus: (m) => refus.push(m) });
    await canal.appeler("session.resume", { session_id: CLE });
    const ws = HermesWs.dernier();
    expect(refus).toEqual(["approval"]);
    canal.repondreClarify("srq-c", { answers: { q0: "outil.py" } });
    expect(ws.reponses()).toEqual([
      { jsonrpc: "2.0", id: "srq-a", error: { code: CODE_NON_TRAITEE, message: "Méthode non traitée par ACP" } },
      { jsonrpc: "2.0", id: "srq-c", result: { answers: { q0: "outil.py" } } },
    ]);
  });

  it("erreur JSON-RPC gardée (code et message) ; SDK sans buildWsUrl ; ticket refusé", async () => {
    installer();
    HermesWs.reprise = { erreur: { code: 4007, message: "session not found" } };
    const canal = await ouvrirFactice({ capacites: true });
    await expect(canal.appeler("session.resume", { session_id: CLE })).rejects.toMatchObject({
      genre: "refus", code: 4007, detail: "session not found" });
    installer({ buildWsUrl: false });
    await expect(ouvrirFactice({})).rejects.toMatchObject({ genre: "sdk" });
    installerSdk({}, { buildWsUrl: async () => { throw new Error("401"); } });
    await expect(ouvrirFactice({})).rejects.toMatchObject({ genre: "ticket" });
  });
});

// =================================================================================================== conversation

function suivre(conversation: Conversation): EtatConversation[] {
  const etats: EtatConversation[] = [];
  conversation.abonner((e) => etats.push(e));
  return etats;
}

describe("conversation", () => {
  it("nouvelle discussion : rien n'est créé avant le premier envoi, puis session.create {} et prompt.submit", async () => {
    installer();
    const cles: string[] = [];
    const c = new Conversation({ cle: null, ouvrir: ouvrirFactice, surCle: (k) => cles.push(k) });
    c.demarrer();
    await tours();
    const ws = HermesWs.dernier();
    expect(c.etat().connexion).toBe("prete");
    expect(ws.methodes()).toEqual(["client.capabilities"]);
    expect(await c.envoyer("   ")).toBe(false);
    expect(await c.envoyer("Bonjour Hermes")).toBe(true);
    expect(ws.methodes()).toEqual(["client.capabilities", "session.create", "prompt.submit"]);
    expect(ws.appel("session.create")?.params).toEqual({});
    expect(ws.appel("prompt.submit")?.params).toEqual({ session_id: SID, text: "Bonjour Hermes" });
    expect(cles).toEqual([CLE]);
    expect(c.etat()).toMatchObject({ cle: CLE, sessionId: SID, enCours: true });
    // Aucun paramètre interdit n'a jamais été émis.
    expect(ws.brutes.join("\n")).not.toMatch(/close_on_disconnect|"fast"|"model"|"provider"|"cwd"|"source"/);
    // Un seul tour à la fois : pas d'envoi pendant le tour.
    expect(await c.envoyer("Encore")).toBe(false);
    c.arreter();
  });

  it("texte en flux, fin du tour, ligne d'état, outil, erreur ; les événements d'une autre session sont ignorés", async () => {
    installer();
    const c = new Conversation({ cle: null, ouvrir: ouvrirFactice });
    c.demarrer();
    await tours();
    const ws = HermesWs.dernier();
    const envoi = c.envoyer("Question ?");
    ws.evenement("message.start");
    await envoi;
    ws.evenement("status.update", { kind: "status", text: "Réflexion" });
    ws.evenement("tool.start", { tool_id: "t1", name: "web_search" });
    ws.evenement("message.delta", { text: "Bon" });
    ws.evenement("message.delta", { text: "jour" });
    ws.evenement("message.delta", { text: "INTRUS" }, "autre-session");
    expect(c.etat().messages.map((m) => [m.role, m.texte, m.enCours])).toEqual([
      ["utilisateur", "Question ?", false], ["hermes", "Bonjour", true], ["outil", "web_search", false]]);
    expect(c.etat().ligneEtat).toBe("Réflexion");
    ws.evenement("message.complete", { text: "Bonjour.", status: "complete" });
    expect(c.etat().messages[1]).toMatchObject({ role: "hermes", texte: "Bonjour.", enCours: false, fin: "complete" });
    expect(c.etat()).toMatchObject({ enCours: false, ligneEtat: null });
    ws.evenement("error", { message: "agent init failed" });
    expect(c.etat().messages.at(-1)).toMatchObject({ role: "erreur", texte: "agent init failed" });
    c.arreter();
  });

  it("reprise : historique (lignes cachées écartées), tour en cours, question ouverte rejouée, réponse en lot", async () => {
    installer();
    HermesWs.reprise = repriseAvec({ running: true, inflight: { user: "Et le nom ?", assistant: "Je vous " },
                                     open_requests: [{ id: "srq-c", method: "clarify",
                                                       params: { session_id: SID, ...CLARIFY_LOT } }] });
    const c = new Conversation({ cle: CLE, ouvrir: ouvrirFactice });
    c.demarrer();
    await tours();
    const ws = HermesWs.dernier();
    expect(ws.methodes()).toEqual(["client.capabilities", "session.resume"]);
    expect(ws.appel("session.resume")?.params).toEqual({ session_id: CLE });
    const etat = c.etat();
    expect(etat).toMatchObject({ connexion: "prete", sessionId: SID, titre: "Nom du module", enCours: true });
    expect(etat.messages.map((m) => [m.role, m.texte])).toEqual([
      ["utilisateur", "Prépare le module."], ["outil", "clarify"], ["hermes", "Voici <b>gras</b>\nsur deux lignes."],
      ["utilisateur", "Et le nom ?"], ["hermes", "Je vous "]]);
    expect(etat.demandes).toHaveLength(1);
    const demande = etat.demandes[0]!;
    expect(demande.questions[0]?.choix).toEqual([
      { valeur: "outil.py (Recommended)", libelle: "outil.py", recommande: true },
      { valeur: "module.py", libelle: "module.py", recommande: false }]);
    expect(c.repondre("srq-c", { "0": { choix: ["outil.py (Recommended)"], libre: "" } })).toBe(true);
    expect(ws.reponses()).toEqual([{ jsonrpc: "2.0", id: "srq-c", result: { answers: { q0: "outil.py (Recommended)" } } }]);
    expect(c.etat().demandes).toEqual([]);
    c.arreter();
  });

  it("pendant la reprise : la fin du tour et une nouvelle question ne se perdent pas, le texte en flux n'est pas doublé",
     async () => {
    installer();
    HermesWs.reprise = repriseAvec({ running: true, inflight: { user: "Et le nom ?", assistant: "Je vous " } });
    HermesWs.avantReprise = (ws) => {
      ws.evenement("message.delta", { text: "Je vous " });
      ws.requete("srq-n", "clarify", { question: "Nouvelle ?" });
      ws.evenement("message.complete", { text: "Je vous réponds.", status: "complete" });
    };
    const c = new Conversation({ cle: CLE, ouvrir: ouvrirFactice });
    c.demarrer();
    await tours();
    const etat = c.etat();
    expect(etat.messages.slice(-2).map((m) => [m.role, m.texte, m.enCours])).toEqual([
      ["utilisateur", "Et le nom ?", false], ["hermes", "Je vous réponds.", false]]);
    expect(etat.enCours).toBe(false);
    expect(etat.demandes.map((d) => d.id)).toEqual(["srq-n"]);
    // La question arrivée pendant la reprise est répondable sur ce canal.
    expect(c.repondre("srq-n", { "0": { choix: [], libre: "Oui" } })).toBe(true);
    expect(HermesWs.dernier().reponses()).toEqual([{ jsonrpc: "2.0", id: "srq-n", result: { answer: "Oui" } }]);
    c.arreter();
  });

  it("une fin de tour déjà portée par l'historique repris n'est pas ajoutée une seconde fois", async () => {
    installer();
    HermesWs.avantReprise = (ws) => ws.evenement("message.complete", { text: "Voici <b>gras</b>\nsur deux lignes.",
                                                                       status: "complete" });
    const c = new Conversation({ cle: CLE, ouvrir: ouvrirFactice });
    c.demarrer();
    await tours();
    expect(c.etat().messages.filter((m) => m.role === "hermes").map((m) => m.texte)).toEqual([
      "Voici <b>gras</b>\nsur deux lignes."]);
    c.arreter();
  });

  it("formes de réponse : question seule, texte libre prioritaire, choix multiple en liste JSON, « » = passer", () => {
    const seule = demandeDe({ id: "s", methode: "clarify", params: { question: "Couleur ?", choices: ["bleu", "vert"],
                                                                      multi_select: true } });
    expect(seule).not.toBeNull();
    expect(reponseDe(seule!, { "0": { choix: ["bleu", "vert", "rouge"], libre: "" } })).toEqual({ answer: '["bleu","vert"]' });
    expect(reponseDe(seule!, { "0": { choix: ["bleu"], libre: "violet" } })).toEqual({ answer: '["bleu","violet"]' });
    const ouverte = demandeDe({ id: "o", methode: "clarify", params: { question: "Nom ?" } })!;
    expect(texteDeReponse(ouverte.questions[0]!, { choix: [], libre: "  Paul " })).toBe("Paul");
    expect(reponseDe(ouverte, {})).toEqual({ answer: "" });
    const lot = demandeDe({ id: "l", methode: "clarify", params: { questions: [
      { qid: "q0", question: "A ?", choices: ["x", "y"] }, { qid: "q1", question: "B ?" }], answers: { q1: "déjà" } } })!;
    expect(lot.questions[1]?.dejaRepondu).toBe("déjà");
    expect(reponseDe(lot, { "0": { choix: ["y"], libre: "libre" }, "1": { choix: [], libre: "b" } }))
      .toEqual({ answers: { q0: "libre", q1: "b" } });
    expect(demandeDe({ id: "x", methode: "clarify", params: {} })).toBeNull();
    expect(demandeDe({ id: "x", methode: "clarify", params: { questions: [{ question: "sans qid" }] } })).toBeNull();
  });

  it("question retirée par Hermes (request.cancel) ; interruption par session.interrupt", async () => {
    installer();
    const c = new Conversation({ cle: CLE, ouvrir: ouvrirFactice });
    c.demarrer();
    await tours();
    const ws = HermesWs.dernier();
    ws.requete("srq-9", "clarify", { question: "Encore là ?" });
    expect(c.etat().demandes.map((d) => d.id)).toEqual(["srq-9"]);
    ws.evenement("request.cancel", { id: "srq-9", method: "clarify", reason: "timeout" });
    expect(c.etat().demandes).toEqual([]);
    expect(c.etat().retirees).toEqual(["timeout"]);
    expect(c.repondre("srq-9", {})).toBe(false);
    await c.interrompre();
    expect(ws.appel("session.interrupt")?.params).toEqual({ session_id: SID });
    c.arreter();
  });

  it("reconnexion après 1, 2, 5 puis 10 s ; chaque tentative refait session.resume et rejoue la question", async () => {
    vi.useFakeTimers();
    installer();
    const c = new Conversation({ cle: CLE, ouvrir: ouvrirFactice });
    const etats = suivre(c);
    c.demarrer();
    await vi.advanceTimersByTimeAsync(10);
    expect(c.etat().connexion).toBe("prete");
    HermesWs.dernier().couper();
    expect(c.etat()).toMatchObject({ connexion: "reconnexion", tentativeDans: 1 });
    // Les tickets suivants échouent : 1, 2, 5, 10, 10 s.
    installerSdk({}, { buildWsUrl: async () => { throw new Error("401"); } });
    const attentes: Array<number | null> = [];
    for (const pas of [1_000, 2_000, 5_000, 10_000]) {
      await vi.advanceTimersByTimeAsync(pas);
      attentes.push(c.etat().tentativeDans);
    }
    expect(attentes).toEqual([2, 5, 10, 10]);
    HermesWs.reprise = repriseAvec({ open_requests: [{ id: "srq-r", method: "clarify",
                                                       params: { session_id: SID, question: "Toujours ?" } }] });
    installer();
    await vi.advanceTimersByTimeAsync(10_000 + 10);
    expect(c.etat()).toMatchObject({ connexion: "prete", tentativeDans: null });
    expect(c.etat().demandes.map((d) => d.id)).toEqual(["srq-r"]);
    expect(HermesWs.dernier().methodes()).toEqual(["client.capabilities", "session.resume"]);
    expect(etats.some((e) => e.connexion === "reconnexion")).toBe(true);
    c.arreter();
  });

  it("ticket refusé en 401 (session expirée) : la boucle s'arrête et le dit ; une panne réseau reste réessayée", async () => {
    // Relecture finale de P7 (constat produit-3) : getWsTicket de Hermes lève une ApiError (status 401) sans rediriger ;
    // la conversation se reconnectait sans fin en ne disant que « Connexion perdue ».
    vi.useFakeTimers();
    installer();
    const c = new Conversation({ cle: CLE, ouvrir: ouvrirFactice });
    c.demarrer();
    await vi.advanceTimersByTimeAsync(10);
    expect(c.etat().connexion).toBe("prete");
    let tickets = 0;
    installerSdk({}, { buildWsUrl: async () => {
      tickets += 1;
      throw tickets === 1 ? new TypeError("Failed to fetch")
        : new ApiErrorHermes("Session expired", 401, '{"error":"session_expired","login_url":"/login"}');
    } });
    HermesWs.dernier().couper();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(tickets).toBe(1);
    expect(c.etat()).toMatchObject({ connexion: "reconnexion", tentativeDans: 2 });  // panne réseau : réessayée
    await vi.advanceTimersByTimeAsync(2_000);
    expect(tickets).toBe(2);
    expect(c.etat()).toMatchObject({ connexion: "session_expiree", tentativeDans: null });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(tickets).toBe(2);  // plus aucune tentative
    c.reveiller();
    await vi.advanceTimersByTimeAsync(10);
    expect(tickets).toBe(2);
    c.arreter();
  });

  it("session inconnue (4007) : « introuvable », sans nouvelle tentative ; SDK sans buildWsUrl : « indisponible »", async () => {
    installer();
    HermesWs.reprise = { erreur: { code: 4007, message: "session not found" } };
    const c = new Conversation({ cle: CLE, ouvrir: ouvrirFactice });
    c.demarrer();
    await tours();
    expect(c.etat().connexion).toBe("introuvable");
    expect(HermesWs.instances.length).toBe(1);
    expect(HermesWs.dernier().ferme).toBe(true);
    installer({ buildWsUrl: false });
    const d = new Conversation({ cle: null, ouvrir: ouvrirFactice });
    d.demarrer();
    await tours();
    expect(d.etat().connexion).toBe("indisponible");
  });
});

// =================================================================================================== page

const PAGE_SESSIONS = {
  sessions: [
    { id: CLE, title: "Nom du module", source: "tui", started_at: 1790422000, last_active: 1790423000, message_count: 4 },
    { id: "20261001_090000_ffff00", title: null, source: "tui", started_at: 1790300000, last_active: 1790300100,
      message_count: 2 },
  ],
  total: 2,
};

function texteDe(element: Element | null | undefined): string {
  return (element?.textContent ?? "").replace(/\s+/g, " ").trim();
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

async function soumettre(formulaire: Element | null | undefined): Promise<void> {
  if (!formulaire) throw new Error("formulaire absent");
  await act(async () => {
    formulaire.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await tours();
}

describe("page Discussion", () => {
  it("adresse : liste, discussion par sa clé, nouvelle ; clé illisible → liste", () => {
    expect(vueDepuisAdresse("")).toEqual({ genre: "liste" });
    expect(vueDepuisAdresse(`?session=${CLE}`)).toEqual({ genre: "fil", cle: CLE });
    expect(vueDepuisAdresse("?session=nouvelle")).toEqual({ genre: "fil", cle: null });
    expect(vueDepuisAdresse("?session=%3Cscript%3E")).toEqual({ genre: "liste" });
    expect(rechercheDeVue({ genre: "fil", cle: CLE }, "?profile=p")).toBe(`?profile=p&session=${CLE}`);
    expect(rechercheDeVue({ genre: "liste" }, `?session=${CLE}`)).toBe("");
  });

  it("liste : vingt dernières sessions « tui », discussion en attente marquée, liens vers chaque discussion", async () => {
    vi.stubGlobal("WebSocket", HermesWs);
    HermesWs.actifs = [{ current: false, id: SID, last_active: 1790423000, message_count: 4, model: "m",
                         preview: "Quel nom ?", session_key: CLE, started_at: 1790422000, status: "waiting",
                         title: "Nom du module" }];
    installer({ reponses: { [ROUTE_DISCUSSIONS]: PAGE_SESSIONS } });
    expect(ROUTE_DISCUSSIONS).toBe("/api/sessions?limit=20&offset=0&order=recent&source=tui");
    const r = await rendre(<Discussion />);
    await tours(8);
    const entrees = [...r.racine.querySelectorAll("ul.acp-entrees > li")];
    expect(entrees.map((e) => texteDe(e.querySelector("h3")))).toEqual(["Nom du module", "Sans titre"]);
    expect(texteDe(entrees[0])).toContain("En attente d'une réponse");
    expect(texteDe(entrees[1])).not.toContain("En attente");
    const liens = [...r.racine.querySelectorAll("a")].map((a) => [texteDe(a), a.getAttribute("href")]);
    expect(liens).toContainEqual(["Nouvelle discussion", "/discussion?session=nouvelle"]);
    expect(liens).toContainEqual(["Ouvrir", `/discussion?session=${CLE}`]);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("liste : état d'attente illisible dit, jamais « rien en attente » par défaut", async () => {
    // Relecture finale de P7 (constat produit-4) : sans état d'attente lu, l'absence de marque passait pour « rien ».
    installerSdk({ [ROUTE_DISCUSSIONS]: PAGE_SESSIONS }, { buildWsUrl: async () => { throw new Error("ticket"); } });
    const r = await rendre(<Discussion />);
    await tours(8);
    expect(r.racine.querySelectorAll("ul.acp-entrees > li").length).toBe(2);
    expect(r.texte()).toContain("Discussions en attente : état inconnu (le tableau de bord n'a pas pu être interrogé)");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("discussion reprise : question rejouée, réponse par choix, texte brut (aucun HTML interprété)", async () => {
    vi.stubGlobal("WebSocket", HermesWs);
    window.history.replaceState(null, "", `/discussion?session=${CLE}`);
    HermesWs.reprise = repriseAvec({ open_requests: [{ id: "srq-c", method: "clarify",
                                                       params: { session_id: SID, ...CLARIFY_LOT } }] });
    installer();
    const r = await rendre(<Discussion />);
    await tours(8);
    const ws = HermesWs.dernier();
    expect(r.racine.querySelector('[data-acp-connexion="prete"]')).not.toBeNull();
    expect(texteDe(r.racine.querySelector("#acp-discussion-titre"))).toBe("Nom du module");
    // Texte brut : la balise reste du texte.
    expect(r.racine.querySelector(".acp-fil b")).toBeNull();
    expect(texteDe(r.racine.querySelector(".acp-fil"))).toContain("Voici <b>gras</b>");
    expect(texteDe(r.racine.querySelector(".acp-fil"))).toContain("Outil : clarify");
    const carte = r.racine.querySelector("[data-acp-clarify]")?.closest("section");
    expect(texteDe(carte)).toContain("Hermes vous pose une question");
    expect(texteDe(carte)).toContain("Quel nom donner au module ?");
    expect(texteDe(carte)).not.toContain("Recommended");
    const repondre = [...(carte?.querySelectorAll("button") ?? [])].find((b) => texteDe(b) === "Répondre");
    expect(repondre?.disabled).toBe(true);
    const choix = [...(carte?.querySelectorAll("button.acp-choix-bouton") ?? [])];
    expect(choix.map((b) => [texteDe(b.querySelector("[data-acp-donnee]")), texteDe(b.querySelector(".acp-discret"))]))
      .toEqual([["outil.py", "recommandé"], ["module.py", ""]]);
    await cliquer(choix[0]);
    expect(choix[0]?.getAttribute("aria-pressed")).toBe("true");
    expect(repondre?.disabled).toBe(false);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    await soumettre(r.racine.querySelector("[data-acp-clarify]"));
    expect(ws.reponses()).toEqual([{ jsonrpc: "2.0", id: "srq-c", result: { answers: { q0: "outil.py (Recommended)" } } }]);
    expect(r.racine.querySelector("[data-acp-clarify]")).toBeNull();
    r.demonter();
    expect(ws.ferme).toBe(true);
  });

  it("envoi, texte en flux, « Interrompre » pendant le tour ; demande refusée d'office dite en français", async () => {
    vi.stubGlobal("WebSocket", HermesWs);
    window.history.replaceState(null, "", "/discussion?session=nouvelle");
    installer();
    const r = await rendre(<Discussion />);
    await tours(8);
    const ws = HermesWs.dernier();
    expect(r.texte()).toContain("Écrivez votre premier message");
    const envoyer = () => [...r.racine.querySelectorAll("button")].find((b) => texteDe(b) === "Envoyer");
    expect(envoyer()?.disabled).toBe(true);
    await saisir(r.racine.querySelector("#acp-discussion-message"), "OUTIL:clarify");
    expect(envoyer()?.disabled).toBe(false);
    await soumettre(r.racine.querySelector("#acp-discussion-message")?.closest("form"));
    expect(window.location.search).toBe(`?session=${CLE}`);
    expect((r.racine.querySelector("#acp-discussion-message") as HTMLTextAreaElement).value).toBe("");
    await act(async () => {
      ws.evenement("message.start");
      ws.evenement("message.delta", { text: "Je réfléchis" });
    });
    const bulle = (role: string) => {
      const b = r.racine.querySelector(`[data-acp-message="${role}"]`);
      return [texteDe(b?.querySelector(".acp-bulle__auteur")), texteDe(b?.querySelector(".acp-bulle__texte"))];
    };
    expect(bulle("utilisateur")).toEqual(["Vous", "OUTIL:clarify"]);
    expect(bulle("hermes")).toEqual(["Hermes", "Je réfléchis"]);
    expect(envoyer()?.disabled).toBe(true);
    expect(r.texte()).toContain("Un tour est en cours");
    await act(async () => {
      ws.requete("srq-a", "approval", { request_id: "r", command: "rm -rf /" });
    });
    expect(r.texte()).toContain("Demande refusée automatiquement : ACP ne traite ni approbation, ni mot de passe, ni secret.");
    const interrompre = [...r.racine.querySelectorAll("button")].find((b) => texteDe(b) === "Interrompre");
    await cliquer(interrompre);
    expect(ws.appel("session.interrupt")?.params).toEqual({ session_id: SID });
    await act(async () => {
      ws.evenement("message.complete", { text: "", status: "interrupted" });
    });
    expect(r.texte()).toContain("Tour interrompu.");
    expect([...r.racine.querySelectorAll("button")].some((b) => texteDe(b) === "Interrompre")).toBe(false);
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  // Relecture finale de P7 (constats produit-5 et produit-13) : pendant une tentative, la page affichait « Nouvelle
  // tentative dans Inconnu s » ; à la reconnexion, la réponse en cours de saisie d'une question était effacée.
  it("reconnexion : tentative en cours dite, réponse en cours de saisie gardée", async () => {
    vi.stubGlobal("WebSocket", HermesWs);
    window.history.replaceState(null, "", `/discussion?session=${CLE}`);
    const ouverte = [{ id: "srq-g", method: "clarify", params: { session_id: SID, question: "Quel nom ?" } }];
    HermesWs.reprise = repriseAvec({ open_requests: ouverte });
    let suspendre = false;
    let liberer: (() => void) | null = null;
    installerSdk({}, { buildWsUrl: async () => {
      if (suspendre) await new Promise<void>((r) => (liberer = r));
      return URL_WS;
    } });
    const r = await rendre(<Discussion />);
    await tours(8);
    const champ = () => r.racine.querySelector('[data-acp-clarify="srq-g"] textarea') as HTMLTextAreaElement | null;
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    await saisir(champ(), "outil.py, avec un test");
    suspendre = true;
    await act(async () => {
      HermesWs.dernier().couper();
      await new Promise((attente) => setTimeout(attente, 1_100));
    });
    await tours();
    const connexion = r.racine.querySelector('[data-acp-connexion="reconnexion"]');
    expect(texteDe(connexion)).toBe("Connexion perdue : nouvelle tentative en cours…");
    expect(texteDe(connexion)).not.toContain("Inconnu");
    suspendre = false;
    await act(async () => {
      (liberer as (() => void) | null)?.();
    });
    await tours(10);
    expect(r.racine.querySelector('[data-acp-connexion="prete"]')).not.toBeNull();
    expect(champ()?.value).toBe("outil.py, avec un test");
    r.demonter();
  });

  it("session expirée : la page le dit et propose de recharger (la connexion ramène à la discussion)", async () => {
    vi.stubGlobal("WebSocket", HermesWs);
    window.history.replaceState(null, "", `/discussion?session=${CLE}`);
    installerSdk({}, { buildWsUrl: async () => {
      throw new ApiErrorHermes("Session expired", 401, '{"error":"session_expired","login_url":"/login"}');
    } });
    const r = await rendre(<Discussion />);
    await tours(8);
    const bloc = r.racine.querySelector('[data-acp-connexion="session_expiree"]');
    expect(texteDe(bloc?.querySelector("p"))).toBe(
      "Session expirée : reconnectez-vous pour reprendre la discussion (elle vous attend).");
    expect(bloc?.querySelector("a")?.getAttribute("href")).toBe(`/discussion?session=${CLE}`);
    expect(texteDe(bloc?.querySelector("a"))).toBe("Recharger la page");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("SDK sans buildWsUrl : la page le dit, sans faire semblant", async () => {
    window.history.replaceState(null, "", `/discussion?session=${CLE}`);
    installer({ buildWsUrl: false });
    const r = await rendre(<Discussion />);
    await tours();
    expect(r.racine.querySelector('[data-acp-connexion="indisponible"]')).not.toBeNull();
    expect(r.texte()).toContain("Discussion indisponible : ce tableau de bord n'expose pas buildWsUrl");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});
