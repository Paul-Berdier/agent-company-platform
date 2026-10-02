// Canal JSON-RPC du tableau de bord de Hermes (/api/ws), seul chemin par lequel ACP parle à ce protocole (cahier P7
// § 9.2-9.3, correction K14). Employé par la discussion réduite (greffon acp-discussion) et par la lecture des
// discussions en attente de la file Questions (discussions.ts).
//
// Protocole (Hermes 0.21.5, tui_gateway/ws.py) : « newline-delimited » comme le stdio ; une trame texte par message
// JSON. Le serveur envoie d'abord l'événement « gateway.ready ». Trois sortes de messages arrivent :
// - événements : { method: "event", params: { type, session_id, payload } } ;
// - réponses à nos requêtes : { id: "acp-<n>", result } ou { id, error } ;
// - requêtes du serveur au client : { id: "srq-…", method: "clarify" | "approval" | "sudo" | "secret" | …, params }.
//
// Règles tenues ici, et testées (tests/discussion.test.tsx) :
// - LISTE BLANCHE des méthodes émises, avec la liste exacte de leurs paramètres : toute autre méthode, ou tout autre
//   paramètre, est refusé AVANT l'envoi. session.create part toujours SANS paramètre : jamais fast, model ni provider
//   (le contrat épingle le palier dès que « fast » est présent), jamais close_on_disconnect (sa valeur par défaut,
//   false, garde la session vivante quand le téléphone se ferme), jamais cwd, jamais source (elle choisirait la
//   plateforme, donc les jeux d'outils de l'agent). Aucune méthode de configuration, d'outils, de profils, de cron ou
//   de compte n'est jamais appelée. clarify.lock n'est pas employé (les réponses d'un lot partent en une fois).
// - Requêtes du serveur : « clarify » seulement est remise à la page ; TOUTE autre (approval, sudo, secret, vault.*,
//   display.install.sudo…) reçoit l'erreur -32601 aussitôt : l'agent reçoit un refus et la requête est close
//   (server_requests.py de Hermes). Aucun secret ni mot de passe n'est jamais saisi dans ACP.
// - Une réponse à une requête du serveur ne vaut que pour une « clarify » encore ouverte sur CE canal, et n'a que la
//   forme { answer } (question seule) ou { answers } (lot).
// - L'URL vient TOUJOURS de await sdk().buildWsUrl("/api/ws") (ticket à usage unique en mode protégé, correction
//   K16) : un ticket neuf à chaque connexion ; aucune URL écrite en dur.
import { sdk } from "../sdk";

/** Méthodes que ACP a le droit d'émettre, et les SEULS paramètres permis pour chacune. */
export const METHODES_PERMISES = {
  "client.capabilities": ["server_requests"],
  "session.create": [],
  "session.resume": ["session_id"],
  "session.active_list": [],
  "prompt.submit": ["session_id", "text"],
  "session.interrupt": ["session_id"],
  ping: [],
} as const;

export type MethodePermise = keyof typeof METHODES_PERMISES;

/** Erreur JSON-RPC « méthode introuvable », rendue à toute requête du serveur que ACP ne traite pas. */
export const CODE_NON_TRAITEE = -32601;
export const DELAI_OUVERTURE_MS = 10_000;
export const DELAI_APPEL_MS = 30_000;
export const INTERVALLE_PING_MS = 30_000;

export type GenreErreurCanal =
  | "sdk" // le SDK du tableau de bord n'expose pas buildWsUrl
  | "ticket" // buildWsUrl a échoué (session expirée, ticket refusé)
  | "connexion" // la connexion n'a pas pu s'ouvrir
  | "delai" // pas de réponse dans le délai
  | "ferme" // connexion fermée avant la réponse
  | "refus" // Hermes a répondu par une erreur JSON-RPC (code et message gardés)
  | "methode" // méthode hors de la liste blanche (jamais envoyée)
  | "parametre" // paramètre hors de la liste blanche (jamais envoyé)
  | "reponse"; // réponse illisible

export class ErreurCanal extends Error {
  readonly genre: GenreErreurCanal;
  readonly code: number | null;
  readonly detail: string;

  constructor(genre: GenreErreurCanal, detail = "", code: number | null = null) {
    super(code === null ? genre : `${genre} ${code}`);
    this.name = "ErreurCanal";
    this.genre = genre;
    this.code = code;
    this.detail = detail.slice(0, 2000);
  }
}

export interface EvenementCanal {
  type: string;
  /** Session d'exécution visée par l'événement, ou null pour un événement global. */
  sessionId: string | null;
  payload: unknown;
}

export interface RequeteServeur {
  id: string;
  methode: string;
  params: Record<string, unknown>;
}

export type ReponseClarify = { answer: string } | { answers: Record<string, string> };

export interface OptionsCanal {
  /** Annonce client.capabilities { server_requests: true } : le client répond aux requêtes du serveur. Sans elle,
   *  Hermes n'adresse aucune requête à ce client (lecture seule). */
  capacites?: boolean;
  delaiOuvertureMs?: number;
  delaiAppelMs?: number;
  /** Ping de vie (méthode « ping ») ; 0 : aucun. */
  intervallePingMs?: number;
  fabrique?: (url: string) => WebSocket;
  surEvenement?: (evenement: EvenementCanal) => void;
  surClarify?: (requete: RequeteServeur) => void;
  /** Une requête du serveur a été refusée d'office (-32601) : son nom de méthode, pour le dire dans la page. */
  surRefus?: (methode: string) => void;
  /** La connexion est fermée ; volontaire : fermée par ACP (fermer()). */
  surFermeture?: (volontaire: boolean) => void;
}

/** Ce que la page emploie d'un canal (les tests le remplacent par un canal factice). */
export interface CanalJsonRpc {
  appeler(methode: MethodePermise, params?: Record<string, unknown>, delaiMs?: number): Promise<unknown>;
  repondreClarify(id: string, reponse: ReponseClarify): void;
  /** Refuse (-32601) une « clarify » ouverte que la page ne sait pas lire : jamais devinée. */
  refuserClarify(id: string): void;
  /** « clarify » retirée par le serveur (request.cancel) : elle n'est plus répondable. */
  oublierClarify(id: string): void;
  fermer(): void;
}

/** Vérifie méthode et paramètres contre la liste blanche ; lève sans rien envoyer. */
export function verifierAppel(methode: string, params: Record<string, unknown>): void {
  if (!Object.prototype.hasOwnProperty.call(METHODES_PERMISES, methode)) {
    throw new ErreurCanal("methode", methode);
  }
  const permis: readonly string[] = METHODES_PERMISES[methode as MethodePermise];
  const etrangers = Object.keys(params).filter((cle) => !permis.includes(cle));
  if (etrangers.length > 0) throw new ErreurCanal("parametre", `${methode} : ${etrangers.join(", ")}`);
}

/** Forme permise d'une réponse à « clarify » : { answer: chaîne } ou { answers: { qid: chaîne } }, rien d'autre. */
export function reponseClarifyValide(reponse: unknown): reponse is ReponseClarify {
  if (!reponse || typeof reponse !== "object" || Array.isArray(reponse)) return false;
  const cles = Object.keys(reponse);
  if (cles.length !== 1) return false;
  const r = reponse as Record<string, unknown>;
  if (cles[0] === "answer") return typeof r.answer === "string";
  if (cles[0] !== "answers" || !r.answers || typeof r.answers !== "object" || Array.isArray(r.answers)) return false;
  return Object.values(r.answers as Record<string, unknown>).every((v) => typeof v === "string");
}

function texteErreur(erreur: unknown): { code: number | null; message: string } {
  if (!erreur || typeof erreur !== "object") return { code: null, message: "" };
  const e = erreur as { code?: unknown; message?: unknown };
  return {
    code: typeof e.code === "number" && Number.isInteger(e.code) ? e.code : null,
    message: typeof e.message === "string" ? e.message : "",
  };
}

interface Attente {
  methode: MethodePermise;
  resoudre: (valeur: unknown) => void;
  rejeter: (erreur: ErreurCanal) => void;
  minuterie: ReturnType<typeof setTimeout>;
}

class Canal implements CanalJsonRpc {
  private readonly attentes = new Map<string, Attente>();
  /** Requêtes « clarify » du serveur encore ouvertes sur ce canal. */
  private readonly clarifyOuvertes = new Set<string>();
  private compteur = 0;
  private ferme = false;
  private volontaire = false;
  /** Faux tant que l'ouverture n'a pas abouti : un échec d'ouverture n'est pas annoncé comme une fermeture. */
  private actif = false;
  private ping: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly socket: WebSocket,
    private readonly options: OptionsCanal,
  ) {}

  /** Une trame reçue (une ou plusieurs lignes JSON). */
  recevoir(donnees: unknown): void {
    if (typeof donnees !== "string") return;
    for (const ligne of donnees.split("\n")) {
      if (!ligne.trim()) continue;
      let message: Record<string, unknown>;
      try {
        message = JSON.parse(ligne) as Record<string, unknown>;
      } catch {
        continue;
      }
      if (message && typeof message === "object") this.traiter(message);
    }
  }

  private traiter(message: Record<string, unknown>): void {
    const methode = message.method;
    if (methode === "event") {
      const params = (message.params && typeof message.params === "object" ? message.params : {}) as
        Record<string, unknown>;
      if (typeof params.type !== "string") return;
      this.options.surEvenement?.({
        type: params.type,
        sessionId: typeof params.session_id === "string" ? params.session_id : null,
        payload: params.payload,
      });
      return;
    }
    if (typeof methode === "string") {
      // Requête du serveur au client.
      const id = message.id;
      if (typeof id !== "string" && typeof id !== "number") return;
      const params = (message.params && typeof message.params === "object" && !Array.isArray(message.params)
        ? message.params : {}) as Record<string, unknown>;
      if (methode === "clarify" && this.options.capacites && typeof id === "string" && this.options.surClarify) {
        this.clarifyOuvertes.add(id);
        this.options.surClarify({ id, methode, params });
        return;
      }
      this.envoyerBrut({ jsonrpc: "2.0", id, error: { code: CODE_NON_TRAITEE, message: "Méthode non traitée par ACP" } });
      this.options.surRefus?.(methode);
      return;
    }
    const id = message.id;
    if (typeof id !== "string") return;
    const attente = this.attentes.get(id);
    if (!attente) return;
    this.attentes.delete(id);
    clearTimeout(attente.minuterie);
    if ("error" in message) {
      const { code, message: texte } = texteErreur(message.error);
      attente.rejeter(new ErreurCanal("refus", texte, code));
    } else if ("result" in message) {
      if (attente.methode === "session.resume") this.adopterRequetesOuvertes(message.result);
      attente.resoudre(message.result);
    } else {
      attente.rejeter(new ErreurCanal("reponse"));
    }
  }

  /** Requêtes encore ouvertes rejouées par session.resume (open_requests) : une « clarify » devient répondable sur ce
   *  canal ; toute autre reçoit -32601, comme si elle venait d'arriver. */
  private adopterRequetesOuvertes(resultat: unknown): void {
    const ouvertes = resultat && typeof resultat === "object" ? (resultat as { open_requests?: unknown }).open_requests
      : undefined;
    if (!Array.isArray(ouvertes)) return;
    for (const brut of ouvertes) {
      if (!brut || typeof brut !== "object") continue;
      const { id, method } = brut as { id?: unknown; method?: unknown };
      if (typeof id !== "string" || typeof method !== "string") continue;
      if (method === "clarify" && this.options.capacites && this.options.surClarify) {
        this.clarifyOuvertes.add(id);
      } else {
        this.envoyerBrut({ jsonrpc: "2.0", id, error: { code: CODE_NON_TRAITEE, message: "Méthode non traitée par ACP" } });
        this.options.surRefus?.(method);
      }
    }
  }

  private envoyerBrut(objet: unknown): boolean {
    if (this.ferme) return false;
    try {
      this.socket.send(`${JSON.stringify(objet)}\n`);
      return true;
    } catch {
      return false;
    }
  }

  appeler(methode: MethodePermise, params: Record<string, unknown> = {}, delaiMs?: number): Promise<unknown> {
    try {
      verifierAppel(methode, params);
    } catch (erreur) {
      return Promise.reject(erreur);
    }
    if (this.ferme) return Promise.reject(new ErreurCanal("ferme"));
    this.compteur += 1;
    const id = `acp-${this.compteur}`;
    return new Promise<unknown>((resoudre, rejeter) => {
      const minuterie = setTimeout(() => {
        this.attentes.delete(id);
        rejeter(new ErreurCanal("delai", methode));
      }, delaiMs ?? this.options.delaiAppelMs ?? DELAI_APPEL_MS);
      this.attentes.set(id, { methode, resoudre, rejeter, minuterie });
      if (!this.envoyerBrut({ jsonrpc: "2.0", id, method: methode, params })) {
        clearTimeout(minuterie);
        this.attentes.delete(id);
        rejeter(new ErreurCanal("ferme", methode));
      }
    });
  }

  repondreClarify(id: string, reponse: ReponseClarify): void {
    if (!this.clarifyOuvertes.has(id)) throw new ErreurCanal("reponse", `requête ${id} non ouverte sur ce canal`);
    if (!reponseClarifyValide(reponse)) throw new ErreurCanal("reponse", "forme de réponse refusée");
    this.clarifyOuvertes.delete(id);
    if (!this.envoyerBrut({ jsonrpc: "2.0", id, result: reponse })) throw new ErreurCanal("ferme", "réponse non envoyée");
  }

  refuserClarify(id: string): void {
    if (!this.clarifyOuvertes.delete(id)) return;
    this.envoyerBrut({ jsonrpc: "2.0", id, error: { code: CODE_NON_TRAITEE, message: "Méthode non traitée par ACP" } });
  }

  oublierClarify(id: string): void {
    this.clarifyOuvertes.delete(id);
  }

  demarrerPing(): void {
    const intervalle = this.options.intervallePingMs ?? INTERVALLE_PING_MS;
    if (intervalle <= 0 || this.ping !== null) return;
    this.ping = setInterval(() => {
      // Sans réponse : la connexion est tenue pour perdue (la page se reconnecte).
      this.appeler("ping", {}, Math.min(intervalle, 15_000)).catch((erreur: unknown) => {
        if (erreur instanceof ErreurCanal && erreur.genre === "delai") this.couper();
      });
    }, intervalle);
  }

  activer(): void {
    this.actif = true;
  }

  /** Fermeture constatée (socket fermé par le serveur ou le réseau). */
  surFermetureSocket(): void {
    if (this.ferme) return;
    this.ferme = true;
    this.liberer();
    if (this.actif) this.options.surFermeture?.(this.volontaire);
  }

  private couper(): void {
    try {
      this.socket.close();
    } catch {
      // Déjà fermé.
    }
    this.surFermetureSocket();
  }

  private liberer(): void {
    if (this.ping !== null) clearInterval(this.ping);
    this.ping = null;
    for (const [, attente] of this.attentes) {
      clearTimeout(attente.minuterie);
      attente.rejeter(new ErreurCanal("ferme"));
    }
    this.attentes.clear();
    this.clarifyOuvertes.clear();
  }

  fermer(): void {
    this.volontaire = true;
    this.couper();
  }
}

/** Ouvre un canal : ticket neuf, connexion, « gateway.ready », puis client.capabilities si demandé. Rejette par une
 *  ErreurCanal (jamais une exception brute) ; la connexion est fermée en cas d'échec. */
export async function ouvrirCanal(options: OptionsCanal = {}): Promise<CanalJsonRpc> {
  let construire: unknown;
  try {
    construire = sdk().buildWsUrl;
  } catch {
    construire = undefined;
  }
  if (typeof construire !== "function") throw new ErreurCanal("sdk");
  let url: string;
  try {
    url = await (construire as (chemin: string) => Promise<string>)("/api/ws");
  } catch (erreur) {
    throw new ErreurCanal("ticket", erreur instanceof Error ? erreur.message : String(erreur));
  }
  const fabrique = options.fabrique ?? ((adresse: string) => new WebSocket(adresse));
  const canal = await new Promise<Canal>((resoudre, rejeter) => {
    let pret = false;
    let socket: WebSocket;
    try {
      socket = fabrique(url);
    } catch (erreur) {
      rejeter(new ErreurCanal("connexion", erreur instanceof Error ? erreur.message : String(erreur)));
      return;
    }
    const instance = new Canal(socket, options);
    const echouer = (erreur: ErreurCanal) => {
      if (pret) return;
      pret = true;
      clearTimeout(minuterie);
      instance.fermer();
      rejeter(erreur);
    };
    const minuterie = setTimeout(() => echouer(new ErreurCanal("delai", "gateway.ready")),
                                 options.delaiOuvertureMs ?? DELAI_OUVERTURE_MS);
    socket.onerror = () => echouer(new ErreurCanal("connexion"));
    socket.onclose = () => {
      if (!pret) echouer(new ErreurCanal("ferme", "avant gateway.ready"));
      else instance.surFermetureSocket();
    };
    socket.onmessage = (evenement: MessageEvent) => {
      if (!pret && typeof evenement.data === "string" && /"gateway\.ready"/.test(evenement.data)) {
        const lignes = evenement.data.split("\n").filter((l) => l.trim());
        const prete = lignes.some((l) => {
          try {
            const m = JSON.parse(l) as { method?: unknown; params?: { type?: unknown } };
            return m.method === "event" && m.params?.type === "gateway.ready";
          } catch {
            return false;
          }
        });
        if (prete) {
          pret = true;
          clearTimeout(minuterie);
          resoudre(instance);
          return;
        }
      }
      instance.recevoir(evenement.data);
    };
  });
  if (options.capacites) {
    try {
      await canal.appeler("client.capabilities", { server_requests: true }, options.delaiOuvertureMs ?? DELAI_OUVERTURE_MS);
    } catch (erreur) {
      canal.fermer();
      throw erreur instanceof ErreurCanal ? erreur : new ErreurCanal("reponse");
    }
  }
  canal.activer();
  canal.demarrerPing();
  return canal;
}
