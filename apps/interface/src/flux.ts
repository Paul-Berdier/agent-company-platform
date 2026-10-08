// Flux d'invalidation du greffon acp-poste (GET /v1/flux ; cahier P7 § 5.4, décision P7-4).
//
// Le flux SIGNALE qu'un sujet a changé ; la page relit alors la route REST du sujet (useDonnees, donnees.ts). Aucune
// donnée métier n'y passe.
//
// UN SEUL flux par onglet (correction K7) : chaque greffon d'interface est un bundle IIFE distinct qui embarque sa
// propre copie de ce module, et acp-interface monte ses alertes sur toutes les pages. Le flux est donc un objet posé
// sur window.__ACP_FLUX__, sous la clé de sa version de partage (un bundle d'une autre version n'en réutilise pas un
// incompatible), compté par abonnés et fermé 5 s après le dernier (pas de reconnexion à chaque changement de vue).
//
// Lu par authedFetch du SDK puis response.body.getReader() et l'analyseur ci-dessous : EventSource ne sait pas
// envoyer l'en-tête du jeton de session qu'exige le tableau de bord en bouclage local (tests). authedFetch ne
// redirige PAS un 401 vers /login (web/src/lib/api.ts de Hermes) : un 401 du flux n'est pas réessayé ; le flux
// s'arrête, les pages reviennent au sondage par fetchJSON, dont la lecture suivante déclenche la redirection.
//
// Chien de garde : sans aucun octet (trame ou battement) pendant 40 s, ouverture comprise, la connexion est annulée et
// comptée comme un échec (relecture finale de P7 : une connexion muette n'est jamais « temps réel »).
// Reprise : aussitôt après « fin » ; sinon 1 s, 2 s, 5 s, 10 s puis 30 s. Trois échecs de suite en 2 min : mode
// sondage (15 s, l'ancien comportement), dit par la page, et nouvel essai du flux toutes les 5 min. Page cachée : flux
// fermé, aucune lecture (D35). SDK sans authedFetch (contrat < 1.1) : mode « indisponible », sondage d'emblée.
import { sdk } from "./sdk";

export const ROUTE_FLUX = "/api/plugins/acp-poste/v1/flux";
export const SUJETS = ["projets", "questions", "poste", "quotas", "notifications", "pause", "discussions"] as const;
export type Sujet = (typeof SUJETS)[number];
/** connexion : flux en cours d'ouverture ; temps_reel : trame « etat » reçue ; sondage : repli (trois échecs, 401) ;
 *  indisponible : SDK sans authedFetch. */
export type ModeFlux = "connexion" | "temps_reel" | "sondage" | "indisponible";

export const VERSION_PARTAGE = 1;
export const REPRISES_MS = [1_000, 2_000, 5_000, 10_000, 30_000] as const;
export const FENETRE_ECHECS_MS = 120_000;
export const ECHECS_AVANT_REPLI = 3;
export const NOUVEL_ESSAI_MS = 300_000;
export const FERMETURE_DIFFEREE_MS = 5_000;
/** Chien de garde (relecture finale de P7) : sans AUCUN octet (trame ou commentaire de battement, toutes les 15 s côté
 *  greffon) pendant ce délai, la connexion est tenue pour morte (veille, réseau changé, connexion à moitié ouverte) :
 *  lecture annulée, comptée comme un échec. Deux battements manqués et une marge. */
export const CHIEN_DE_GARDE_MS = 40_000;
/** Trames gardées pour le diagnostic (noms de sujets seulement, jamais de donnée) : FluxPartage.trames(). */
export const TRAMES_GARDEES = 200;

/** Une trame reçue, pour le diagnostic : instant (performance.now() de l'onglet), événement, sujets. */
export interface TrameRecue {
  t: number;
  evenement: string;
  sujets: Sujet[];
}

// ------------------------------------------------------------------ analyseur SSE (spécification HTML, « event stream »)

export interface TrameSse {
  /** Dernier identifiant connu au moment de la trame (il persiste d'une trame à l'autre, comme pour EventSource). */
  id: string | null;
  evenement: string;
  donnees: string;
}

/** Analyseur incrémental : les morceaux du flux arrivent coupés n'importe où (au milieu d'une ligne, entre « \r » et
 *  « \n ») ; lignes terminées par « \n », « \r\n » ou « \r » ; commentaires (« : … ») comptés et ignorés ; champs
 *  inconnus ignorés ; une trame sans « data » n'est pas émise (mais son « id » compte). */
export class AnalyseurSse {
  dernierId: string | null = null;
  retry: number | null = null;
  commentaires = 0;
  private reste = "";
  private crEnSuspens = false;
  private evenement = "";
  private donnees: string[] = [];
  private idTampon: string | null = null;

  pousser(morceau: string): TrameSse[] {
    let texte = morceau;
    if (this.crEnSuspens && texte.startsWith("\n")) texte = texte.slice(1);
    if (texte.length > 0) this.crEnSuspens = false;
    const tampon = this.reste + texte;
    const trames: TrameSse[] = [];
    let debut = 0;
    for (let i = 0; i < tampon.length; i += 1) {
      const c = tampon[i];
      if (c !== "\n" && c !== "\r") continue;
      const ligne = tampon.slice(debut, i);
      if (c === "\r") {
        if (i + 1 < tampon.length) {
          if (tampon[i + 1] === "\n") i += 1;
        } else {
          this.crEnSuspens = true;
        }
      }
      debut = i + 1;
      const trame = this.ligne(ligne);
      if (trame) trames.push(trame);
    }
    this.reste = tampon.slice(debut);
    return trames;
  }

  private ligne(ligne: string): TrameSse | null {
    if (ligne === "") return this.expedier();
    if (ligne.startsWith(":")) {
      this.commentaires += 1;
      return null;
    }
    const deuxPoints = ligne.indexOf(":");
    const champ = deuxPoints === -1 ? ligne : ligne.slice(0, deuxPoints);
    let valeur = deuxPoints === -1 ? "" : ligne.slice(deuxPoints + 1);
    if (valeur.startsWith(" ")) valeur = valeur.slice(1);
    if (champ === "event") this.evenement = valeur;
    else if (champ === "data") this.donnees.push(valeur);
    else if (champ === "id" && !valeur.includes("\u0000")) this.idTampon = valeur;
    else if (champ === "retry" && /^\d+$/.test(valeur)) this.retry = Number(valeur);
    return null;
  }

  private expedier(): TrameSse | null {
    this.dernierId = this.idTampon;
    if (this.donnees.length === 0) {
      this.evenement = "";
      return null;
    }
    const trame = { id: this.dernierId, evenement: this.evenement || "message", donnees: this.donnees.join("\n") };
    this.donnees = [];
    this.evenement = "";
    return trame;
  }
}

// ------------------------------------------------------------------ flux partagé par les bundles d'un onglet

export interface EtatFlux {
  mode: ModeFlux;
  /** Le tableau de bord publie-t-il le nombre de discussions en attente ? null tant qu'aucune trame « etat ». */
  discussionsSuivies: boolean | null;
}

interface Abonnement {
  sujets: ReadonlySet<string>;
  rappel: (sujets: Sujet[]) => void;
}

type Minuterie = ReturnType<typeof setTimeout>;

function estSujet(valeur: unknown): valeur is Sujet {
  return typeof valeur === "string" && (SUJETS as readonly string[]).includes(valeur);
}

function visible(): boolean {
  return typeof document === "undefined" || document.visibilityState !== "hidden";
}

/** Ce que les bundles partagent : abonnés, état, une seule connexion. Méthodes seulement (aucun champ lu du dehors),
 *  pour que deux copies du module (deux bundles de la même version) s'en servent pareil. */
export class FluxPartage {
  readonly version = VERSION_PARTAGE;
  private readonly abonnes = new Map<number, Abonnement>();
  private readonly ecouteurs = new Set<(etat: EtatFlux) => void>();
  private compteur = 0;
  private courant: EtatFlux = { mode: "connexion", discussionsSuivies: null };
  private controleur: AbortController | null = null;
  private generation = 0;
  private reprise: Minuterie | null = null;
  private fermeture: Minuterie | null = null;
  private echecs: number[] = [];
  private repliJusqua = 0;
  private dernierId: string | null = null;
  private readonly recues: TrameRecue[] = [];
  private arrete = false;
  private readonly surVisibilite = () => (visible() ? this.ouvrir() : this.fermer());

  constructor() {
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", this.surVisibilite);
  }

  /** S'abonne aux sujets ; rend la fonction de désabonnement. Le flux s'ouvre au premier abonné. */
  abonner(sujets: readonly Sujet[], rappel: (sujets: Sujet[]) => void): () => void {
    this.compteur += 1;
    const numero = this.compteur;
    this.abonnes.set(numero, { sujets: new Set(sujets), rappel });
    if (this.fermeture !== null) {
      clearTimeout(this.fermeture);
      this.fermeture = null;
    }
    this.ouvrir();
    return () => {
      if (!this.abonnes.delete(numero) || this.abonnes.size > 0) return;
      if (this.fermeture !== null) clearTimeout(this.fermeture);
      this.fermeture = setTimeout(() => {
        this.fermeture = null;
        if (this.abonnes.size === 0) this.fermer();
      }, FERMETURE_DIFFEREE_MS);
    };
  }

  /** Suit les changements d'état (mode, discussions suivies) ; rend la fonction d'arrêt. */
  ecouter(rappel: (etat: EtatFlux) => void): () => void {
    this.ecouteurs.add(rappel);
    return () => {
      this.ecouteurs.delete(rappel);
    };
  }

  etat(): EtatFlux {
    return this.courant;
  }

  /** Dernières trames reçues (« etat », « changement », « fin »), pour le diagnostic et la preuve du parcours P7 (une
   *  relecture de la page suit-elle une trame ?). Aucune donnée : des noms de sujets. */
  trames(): TrameRecue[] {
    return this.recues.map((r) => ({ ...r, sujets: [...r.sujets] }));
  }

  /** Nombre d'abonnés (tests et diagnostic). */
  abonnements(): number {
    return this.abonnes.size;
  }

  /** Ferme tout et oublie les écouteurs (tests). */
  detruire(): void {
    this.abonnes.clear();
    this.ecouteurs.clear();
    if (this.fermeture !== null) clearTimeout(this.fermeture);
    this.fermeture = null;
    this.fermer();
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", this.surVisibilite);
  }

  private poser(etat: Partial<EtatFlux>): void {
    const suivant = { ...this.courant, ...etat };
    if (suivant.mode === this.courant.mode && suivant.discussionsSuivies === this.courant.discussionsSuivies) return;
    this.courant = suivant;
    for (const ecouteur of [...this.ecouteurs]) ecouteur(suivant);
  }

  private diffuser(sujets: Sujet[]): void {
    if (sujets.length === 0) return;
    for (const abonnement of [...this.abonnes.values()]) {
      const vises = sujets.filter((s) => abonnement.sujets.has(s));
      if (vises.length > 0) abonnement.rappel(vises);
    }
  }

  private ouvrir(): void {
    if (this.abonnes.size === 0 || !visible() || this.controleur !== null || this.reprise !== null) return;
    let authedFetch: unknown;
    try {
      authedFetch = sdk().authedFetch;
    } catch {
      authedFetch = undefined;
    }
    if (typeof authedFetch !== "function") {
      this.poser({ mode: "indisponible" });
      return;
    }
    if (this.arrete) {
      this.poser({ mode: "sondage" });
      return;
    }
    const attente = this.repliJusqua - Date.now();
    if (attente > 0) {
      this.poser({ mode: "sondage" });
      this.planifier(attente);
      return;
    }
    void this.connecter(authedFetch as (url: string, init?: RequestInit) => Promise<Response>);
  }

  private fermer(): void {
    this.generation += 1;
    if (this.reprise !== null) clearTimeout(this.reprise);
    this.reprise = null;
    const controleur = this.controleur;
    this.controleur = null;
    controleur?.abort();
  }

  private planifier(delai: number): void {
    if (this.reprise !== null) clearTimeout(this.reprise);
    this.reprise = setTimeout(() => {
      this.reprise = null;
      this.ouvrir();
    }, delai);
  }

  private async connecter(authedFetch: (url: string, init?: RequestInit) => Promise<Response>): Promise<void> {
    this.generation += 1;
    const generation = this.generation;
    const controleur = new AbortController();
    this.controleur = controleur;
    // Le mode ne change pas ici : une réouverture après « fin » (toutes les 10 min) ou une reprise isolée garde
    // « temps réel » (la trame « etat » dira ce qui a changé entre-temps) ; seuls trois échecs le font tomber.
    let fin = false;
    // Chien de garde (relecture finale de P7, constat scenario-4) : ouverture comprise, chaque octet reçu le relance ;
    // échu, il annule la connexion, ce qui la fait finir en échec (jamais « temps réel » sans trame ni battement).
    let chien: Minuterie | null = null;
    const relancerChien = () => {
      if (chien !== null) clearTimeout(chien);
      chien = setTimeout(() => {
        chien = null;
        if (generation === this.generation) controleur.abort();
      }, CHIEN_DE_GARDE_MS);
    };
    relancerChien();
    try {
      const entetes: Record<string, string> = { Accept: "text/event-stream" };
      if (this.dernierId !== null) entetes["Last-Event-ID"] = this.dernierId;
      const reponse = await authedFetch(ROUTE_FLUX, { headers: entetes, signal: controleur.signal, cache: "no-store" });
      if (generation !== this.generation) return;
      if (reponse.status === 401) {
        // Session expirée : jamais réessayé ici ; la prochaine lecture par fetchJSON redirige vers /login.
        this.arrete = true;
        this.controleur = null;
        this.poser({ mode: "sondage" });
        return;
      }
      if (!reponse.ok || reponse.body === null) throw new Error(`flux ${reponse.status}`);
      relancerChien();
      const lecteur = reponse.body.getReader();
      const decodeur = new TextDecoder();
      const analyseur = new AnalyseurSse();
      for (;;) {
        const { value, done } = await lecteur.read();
        if (generation !== this.generation) {
          void lecteur.cancel().catch(() => undefined);
          return;
        }
        if (done) break;
        relancerChien();
        for (const trame of analyseur.pousser(decodeur.decode(value, { stream: true }))) {
          if (trame.id !== null) this.dernierId = trame.id;
          fin = this.traiter(trame) || fin;
        }
      }
    } catch {
      if (generation !== this.generation) return; // fermé par la page : rien à reprendre
    } finally {
      if (chien !== null) clearTimeout(chien);
      chien = null;
    }
    if (generation !== this.generation) return;
    this.controleur = null;
    if (fin) {
      this.ouvrir(); // fin propre (durée maximale) : réouverture aussitôt, avec Last-Event-ID
      return;
    }
    this.echec();
  }

  /** Traite une trame ; rend vrai pour « fin ». */
  private noter(evenement: string, sujets: Sujet[]): void {
    const t = typeof performance !== "undefined" ? performance.now() : Date.now();
    this.recues.push({ t, evenement, sujets });
    if (this.recues.length > TRAMES_GARDEES) this.recues.splice(0, this.recues.length - TRAMES_GARDEES);
  }

  private traiter(trame: TrameSse): boolean {
    if (trame.evenement === "fin") {
      this.noter("fin", []);
      return true;
    }
    if (trame.evenement !== "etat" && trame.evenement !== "changement") return false;
    let donnees: unknown;
    try {
      donnees = JSON.parse(trame.donnees);
    } catch {
      return false;
    }
    const brut = donnees && typeof donnees === "object" ? (donnees as Record<string, unknown>) : {};
    const sujets = Array.isArray(brut.sujets) ? brut.sujets.filter(estSujet) : [];
    this.noter(trame.evenement, sujets);
    if (trame.evenement === "etat") {
      this.echecs = [];
      this.repliJusqua = 0;
      const suivies = typeof brut.discussions_suivies === "boolean" ? brut.discussions_suivies : null;
      this.poser({ mode: "temps_reel", discussionsSuivies: suivies });
    }
    this.diffuser(sujets);
    return false;
  }

  private echec(): void {
    const maintenant = Date.now();
    this.echecs = [...this.echecs.filter((t) => maintenant - t <= FENETRE_ECHECS_MS), maintenant];
    if (this.echecs.length >= ECHECS_AVANT_REPLI) {
      this.echecs = [];
      this.repliJusqua = maintenant + NOUVEL_ESSAI_MS;
      this.poser({ mode: "sondage" });
      this.planifier(NOUVEL_ESSAI_MS);
      return;
    }
    this.planifier(REPRISES_MS[Math.min(this.echecs.length - 1, REPRISES_MS.length - 1)]);
  }
}

declare global {
  interface Window {
    __ACP_FLUX__?: Record<string, FluxPartage | undefined>;
  }
}

/** Le flux de l'onglet (créé au premier appel, puis partagé par tous les bundles de la même version de partage). */
export function fluxPartage(): FluxPartage {
  const registre = window.__ACP_FLUX__ ?? (window.__ACP_FLUX__ = {});
  const cle = `v${VERSION_PARTAGE}`;
  const existant = registre[cle];
  if (existant && typeof existant.abonner === "function" && existant.version === VERSION_PARTAGE) return existant;
  const flux = new FluxPartage();
  registre[cle] = flux;
  return flux;
}
