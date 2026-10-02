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
// Étape P7, part D : la connexion passe par le canal commun (canal.ts, liste blanche des méthodes émises) ; la seule
// méthode émise ici reste session.active_list.
import { ErreurCanal, ouvrirCanal, type CanalJsonRpc, type GenreErreurCanal } from "./canal";

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

const RAISONS: Partial<Record<GenreErreurCanal, string>> = {
  sdk: "sdk",
  ticket: "ticket",
  connexion: "connexion",
  delai: "delai",
  ferme: "fermee",
};

/** Lit les discussions en attente ; ne rejette jamais (un échec rend { connu: false }). Par le canal commun
 *  (canal.ts : liste blanche), sans client.capabilities ni ping : la seule méthode émise est session.active_list. */
export async function lireDiscussionsEnAttente(
  delaiMs: number = DELAI_LECTURE_MS,
  fabrique: FabriqueSocket = (url) => new WebSocket(url),
): Promise<LectureDiscussions> {
  let canal: CanalJsonRpc | null = null;
  let minuterie: ReturnType<typeof setTimeout> | null = null;
  const delai = new Promise<LectureDiscussions>((resoudre) => {
    minuterie = setTimeout(() => resoudre({ connu: false, raison: "delai" }), delaiMs);
  });
  const lecture = (async (): Promise<LectureDiscussions> => {
    try {
      canal = await ouvrirCanal({ capacites: false, intervallePingMs: 0, fabrique, delaiOuvertureMs: delaiMs,
                                  delaiAppelMs: delaiMs });
      const sessions = sessionsEnAttente(await canal.appeler(METHODE_LISTE, {}));
      return sessions === null ? { connu: false, raison: "reponse" } : { connu: true, sessions };
    } catch (erreur) {
      const genre = erreur instanceof ErreurCanal ? erreur.genre : "reponse";
      return { connu: false, raison: RAISONS[genre] ?? "reponse" };
    }
  })();
  const resultat = await Promise.race([lecture, delai]);
  if (minuterie !== null) clearTimeout(minuterie);
  // Fermée dans tous les cas, y compris quand le délai l'emporte sur une lecture encore en cours.
  void lecture.then(() => (canal as CanalJsonRpc | null)?.fermer());
  (canal as CanalJsonRpc | null)?.fermer();
  return resultat;
}
