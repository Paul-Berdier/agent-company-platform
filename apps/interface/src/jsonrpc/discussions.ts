// Discussions en attente (cahier P7 § 3.5) : cinquième section de la file Questions, lue par le JSON-RPC natif du
// tableau de bord (/api/ws), en LECTURE SEULE.
//
// Seules les sessions ouvertes par /api/ws vivent dans le processus du tableau de bord ; une session « waiting » a une
// requête au client encore ouverte (clarify, approval, sudo, secret : Hermes ne dit pas laquelle). Le lecteur :
// 1. ouvre await sdk().buildWsUrl("/api/ws") (asynchrone : ticket à usage unique en mode protégé, correction K16) ;
// 2. attend l'événement « gateway.ready » ;
// 3. appelle session.active_list SANS client.capabilities : aucune requête ne lui sera adressée, et il ne se rattache à
//    aucune session (jamais session.activate, qui rebrancherait la session) ;
// 4. garde les entrées status == "waiting", ferme la connexion.
// Délai 5 s. Échec, refus ou SDK sans buildWsUrl : « inconnu » (connu: false), jamais zéro.
//
// Protocole « newline-delimited » identique au stdio (tui_gateway/ws.py de Hermes) : une trame texte par message JSON.
// La seule méthode émise ici est session.active_list.
import { sdk } from "../sdk";

export const METHODE_LISTE = "session.active_list";
export const DELAI_LECTURE_MS = 5_000;
const APERCU_MAX = 160;

export interface DiscussionEnAttente {
  /** Clé de la session (session_key) : ce qui permet de la reprendre. */
  cle: string;
  titre: string | null;
  apercu: string | null;
  /** Dernière activité (secondes depuis l'époque), ou null si illisible. */
  derniereActivite: number | null;
}

export type LectureDiscussions = { connu: true; sessions: DiscussionEnAttente[] } | { connu: false; raison: string };

function chaine(valeur: unknown, max = 200): string | null {
  return typeof valeur === "string" && valeur.trim() ? valeur.trim().slice(0, max) : null;
}

/** Entrées « waiting » d'une réponse de session.active_list ; toute entrée illisible est écartée, jamais complétée. */
export function sessionsEnAttente(resultat: unknown): DiscussionEnAttente[] | null {
  const sessions = resultat && typeof resultat === "object" ? (resultat as { sessions?: unknown }).sessions : undefined;
  if (!Array.isArray(sessions)) return null;
  const garde: DiscussionEnAttente[] = [];
  for (const brut of sessions) {
    if (!brut || typeof brut !== "object") continue;
    const s = brut as Record<string, unknown>;
    const cle = chaine(s.session_key, 200);
    if (s.status !== "waiting" || !cle) continue;
    garde.push({
      cle,
      titre: chaine(s.title),
      apercu: chaine(s.preview, APERCU_MAX),
      derniereActivite: typeof s.last_active === "number" && Number.isFinite(s.last_active) ? s.last_active : null,
    });
  }
  return garde;
}

type FabriqueSocket = (url: string) => WebSocket;

/** Lit les discussions en attente ; ne rejette jamais (un échec rend { connu: false }). */
export async function lireDiscussionsEnAttente(
  delaiMs: number = DELAI_LECTURE_MS,
  fabrique: FabriqueSocket = (url) => new WebSocket(url),
): Promise<LectureDiscussions> {
  let construire: unknown;
  try {
    construire = sdk().buildWsUrl;
  } catch {
    construire = undefined;
  }
  if (typeof construire !== "function") return { connu: false, raison: "sdk" };
  let url: string;
  try {
    url = await (construire as (chemin: string) => Promise<string>)("/api/ws");
  } catch {
    return { connu: false, raison: "ticket" };
  }
  return new Promise<LectureDiscussions>((resoudre) => {
    let fini = false;
    let socket: WebSocket | null = null;
    const terminer = (resultat: LectureDiscussions) => {
      if (fini) return;
      fini = true;
      clearTimeout(minuterie);
      try {
        socket?.close();
      } catch {
        // Fermeture impossible : la connexion se fermera d'elle-même.
      }
      resoudre(resultat);
    };
    const minuterie = setTimeout(() => terminer({ connu: false, raison: "delai" }), delaiMs);
    try {
      socket = fabrique(url);
    } catch {
      terminer({ connu: false, raison: "connexion" });
      return;
    }
    let tampon = "";
    socket.onerror = () => terminer({ connu: false, raison: "connexion" });
    socket.onclose = () => terminer({ connu: false, raison: "fermee" });
    socket.onmessage = (evenement: MessageEvent) => {
      if (typeof evenement.data !== "string") return;
      tampon += evenement.data;
      const lignes = tampon.split("\n");
      tampon = lignes.pop() ?? "";
      // Une trame sans saut de ligne final est un message entier (une trame WebSocket par message).
      if (tampon.trim()) {
        lignes.push(tampon);
        tampon = "";
      }
      for (const ligne of lignes) {
        if (!ligne.trim()) continue;
        let message: Record<string, unknown>;
        try {
          message = JSON.parse(ligne) as Record<string, unknown>;
        } catch {
          continue;
        }
        const params = message.params as { type?: unknown } | undefined;
        if (message.method === "event" && params?.type === "gateway.ready") {
          socket?.send(`${JSON.stringify({ jsonrpc: "2.0", id: "acp-1", method: METHODE_LISTE, params: {} })}\n`);
        } else if (message.id === "acp-1") {
          const sessions = "result" in message ? sessionsEnAttente(message.result) : null;
          terminer(sessions === null ? { connu: false, raison: "reponse" } : { connu: true, sessions });
        }
      }
    };
  });
}
