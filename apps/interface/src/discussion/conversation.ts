// État d'une discussion réduite (cahier P7 § 9.2) : connexion au JSON-RPC natif par le canal commun (jsonrpc/canal.ts),
// reprise, envoi, texte en flux, questions « clarify », interruption, reconnexion. Module sans React : la page s'y
// abonne (Fil.tsx), les tests le pilotent avec un canal factice.
//
// - Ouvrir : client.capabilities { server_requests: true } (fait par le canal), puis session.resume { session_id: clé
//   STOCKÉE } : messages et requêtes ouvertes (open_requests), rejouées comme si elles venaient d'arriver.
// - Nouvelle discussion : la session n'est créée (session.create, SANS paramètre) qu'au premier envoi ; aucune session
//   vide n'est laissée derrière une page ouverte puis quittée.
// - Envoyer : prompt.submit { session_id, text } ; un seul tour à la fois (l'envoi est fermé pendant un tour : ni file,
//   ni redirection du tour en cours).
// - Lire : message.start, message.delta, message.complete, status.update (une ligne), error, tool.start (une ligne
//   « Outil : nom »), session.title, request.cancel ; texte brut seulement.
// - Interrompre : session.interrupt.
// - Reconnexion : fermeture non voulue → nouvelle tentative après 1, 2, 5, puis 10 s, et aussitôt au retour de la page ;
//   chaque tentative refait session.resume, qui rejoue les requêtes encore ouvertes.
// Rien n'est inventé : un champ illisible est écarté ; une réponse de Hermes est gardée telle quelle (donnée).
import {
  ErreurCanal,
  ouvrirCanal,
  type CanalJsonRpc,
  type EvenementCanal,
  type OptionsCanal,
  type ReponseClarify,
  type RequeteServeur,
} from "../jsonrpc/canal";

export const DELAIS_RECONNEXION_MS = [1_000, 2_000, 5_000, 10_000] as const;
export const DELAI_REPRISE_MS = 60_000;
export const TEXTE_MAX = 20_000;
/** Libellé ajouté par Hermes au premier choix d'une question (tools/clarify_tool.py, RECOMMENDED_LABEL). */
export const MARQUE_RECOMMANDE = "(Recommended)";

export type EtatConnexion = "repos" | "connexion" | "prete" | "reconnexion" | "indisponible" | "introuvable";
export type RoleMessage = "utilisateur" | "hermes" | "outil" | "erreur";
export type FinTour = "complete" | "interrupted" | "error" | null;
export type GenreErreur = "envoi" | "creation" | "reprise" | "interruption" | "reponse" | "tour";

export interface MessageFil {
  id: string;
  role: RoleMessage;
  texte: string;
  /** Réponse de Hermes encore en flux. */
  enCours: boolean;
  fin: FinTour;
}

export interface ChoixClarify {
  /** Texte tel qu'envoyé par Hermes (renvoyé tel quel : Hermes retire lui-même la marque « recommandé »). */
  valeur: string;
  /** Texte montré, sans la marque. */
  libelle: string;
  recommande: boolean;
}

export interface QuestionClarify {
  /** Identifiant de la question dans un lot (« q0 »…), null pour une question seule. */
  qid: string | null;
  texte: string;
  choix: ChoixClarify[];
  multiple: boolean;
  /** Réponse déjà verrouillée côté serveur (rejouée à la reprise d'un lot). */
  dejaRepondu: string | null;
}

export interface DemandeClarify {
  id: string;
  lot: boolean;
  questions: QuestionClarify[];
}

/** Réponse saisie pour une question : choix retenus et texte libre (le texte libre l'emporte s'il est rempli). */
export interface Saisie {
  choix: string[];
  libre: string;
}

export interface EtatConversation {
  connexion: EtatConnexion;
  /** Prochaine tentative de reconnexion, en secondes (null hors reconnexion). */
  tentativeDans: number | null;
  /** Clé STOCKÉE de la session (ce qui se reprend), null tant qu'une nouvelle discussion n'a rien envoyé. */
  cle: string | null;
  /** Identifiant d'exécution de la session dans le tableau de bord. */
  sessionId: string | null;
  titre: string | null;
  messages: MessageFil[];
  enCours: boolean;
  /** Dernière ligne d'état (status.update), donnée de Hermes. */
  ligneEtat: string | null;
  demandes: DemandeClarify[];
  /** Requêtes refusées d'office (approbation, mot de passe, secret…) : noms de méthode, donnée. */
  refusees: string[];
  /** Questions retirées par Hermes (délai, interruption…) : raisons (donnée), null si Hermes n'en donne pas. */
  retirees: Array<string | null>;
  erreur: { genre: GenreErreur; detail: string | null } | null;
}

export type OuvrirCanal = (options: OptionsCanal) => Promise<CanalJsonRpc>;

export interface OptionsConversation {
  /** Clé stockée de la session à reprendre ; null : nouvelle discussion. */
  cle: string | null;
  /** Appelé quand une nouvelle discussion reçoit sa clé (la page met l'adresse à jour). */
  surCle?: (cle: string) => void;
  ouvrir?: OuvrirCanal;
  delais?: readonly number[];
}

function chaine(valeur: unknown): string | null {
  return typeof valeur === "string" && valeur.trim() ? valeur : null;
}

function objet(valeur: unknown): Record<string, unknown> | null {
  return valeur && typeof valeur === "object" && !Array.isArray(valeur) ? (valeur as Record<string, unknown>) : null;
}

function detailDe(erreur: unknown): string | null {
  if (erreur instanceof ErreurCanal) return erreur.code === null ? erreur.detail || erreur.genre : `${erreur.code} ${erreur.detail}`.trim();
  return erreur instanceof Error ? erreur.message : null;
}

/** Choix d'une question : chaînes non vides ; la marque « (Recommended) » de Hermes est retirée du libellé. */
export function choixDe(brut: unknown): ChoixClarify[] {
  if (!Array.isArray(brut)) return [];
  const choix: ChoixClarify[] = [];
  for (const valeur of brut) {
    if (typeof valeur !== "string" || !valeur.trim()) continue;
    const net = valeur.trim();
    const recommande = net.toLowerCase().endsWith(MARQUE_RECOMMANDE.toLowerCase());
    const libelle = recommande ? net.slice(0, -MARQUE_RECOMMANDE.length).trim() : net;
    choix.push({ valeur: net, libelle: libelle || net, recommande });
  }
  return choix;
}

/** Demande « clarify » lisible (question seule ou lot), ou null : une demande illisible n'est jamais devinée. */
export function demandeDe(requete: RequeteServeur): DemandeClarify | null {
  const p = requete.params;
  const verrouillees = objet(p.answers) ?? {};
  if (Array.isArray(p.questions) && p.questions.length > 0) {
    const questions: QuestionClarify[] = [];
    for (const brut of p.questions) {
      const q = objet(brut);
      const qid = chaine(q?.qid);
      const texte = chaine(q?.question);
      if (!q || !qid || !texte) return null;
      const deja = verrouillees[qid];
      questions.push({ qid, texte, choix: choixDe(q.choices), multiple: q.multi_select === true,
                       dejaRepondu: typeof deja === "string" ? deja : null });
    }
    return { id: requete.id, lot: true, questions };
  }
  const texte = chaine(p.question);
  if (!texte) return null;
  return { id: requete.id, lot: false,
           questions: [{ qid: null, texte, choix: choixDe(p.choices), multiple: p.multi_select === true, dejaRepondu: null }] };
}

/** Texte de réponse d'une question : le texte libre s'il est rempli, sinon le choix (ou, en choix multiple, la liste
 *  JSON des choix, forme que Hermes sait lire) ; « » vaut « passer » (Hermes : réponse vide = question sautée). */
export function texteDeReponse(question: QuestionClarify, saisie: Saisie | undefined): string {
  const libre = (saisie?.libre ?? "").trim();
  const choix = (saisie?.choix ?? []).filter((c) => question.choix.some((x) => x.valeur === c));
  if (question.multiple) {
    const tous = libre ? [...choix, libre] : choix;
    return tous.length > 0 ? JSON.stringify(tous) : "";
  }
  if (libre) return libre;
  return choix[0] ?? "";
}

/** Réponse à envoyer : { answer } pour une question seule, { answers: { qid: texte } } pour un lot. */
export function reponseDe(demande: DemandeClarify, saisies: Record<string, Saisie>): ReponseClarify {
  if (!demande.lot) return { answer: texteDeReponse(demande.questions[0] as QuestionClarify, saisies["0"]) };
  const answers: Record<string, string> = {};
  demande.questions.forEach((q, rang) => {
    answers[q.qid as string] = texteDeReponse(q, saisies[String(rang)]);
  });
  return { answers };
}

/** Message affichable d'une ligne de l'historique rendue par session.resume ; null : ligne cachée ou vide. */
export function messageDeHistorique(brut: unknown, rang: number): MessageFil | null {
  const m = objet(brut);
  if (!m || m.display_kind === "hidden") return null;
  const id = `h-${rang}`;
  if (m.role === "tool") {
    const nom = chaine(m.name);
    return nom ? { id, role: "outil", texte: nom, enCours: false, fin: null } : null;
  }
  const texte = chaine(m.text) ?? chaine(m.content);
  if (!texte) return null;
  if (m.role === "user") return { id, role: "utilisateur", texte, enCours: false, fin: null };
  if (m.role === "assistant") return { id, role: "hermes", texte, enCours: false, fin: "complete" };
  return null;
}

/** État avant toute connexion (rien d'inventé : aucune donnée tant que Hermes n'a pas répondu). */
export function etatInitial(cle: string | null): EtatConversation {
  return { connexion: "repos", tentativeDans: null, cle, sessionId: null, titre: null, messages: [], enCours: false,
           ligneEtat: null, demandes: [], refusees: [], retirees: [], erreur: null };
}

export class Conversation {
  private etatCourant: EtatConversation;
  private readonly ecouteurs = new Set<(etat: EtatConversation) => void>();
  private canal: CanalJsonRpc | null = null;
  private generation = 0;
  private tentatives = 0;
  private arrete = false;
  private minuterie: ReturnType<typeof setTimeout> | null = null;
  /** Événements reçus pendant une reprise (session.resume en vol) : rejoués après l'instantané (voir reprendre). */
  private tampon: EvenementCanal[] | null = null;
  private compteur = 0;
  private readonly ouvrir: OuvrirCanal;
  private readonly delais: readonly number[];

  constructor(private readonly options: OptionsConversation) {
    this.etatCourant = etatInitial(options.cle);
    this.ouvrir = options.ouvrir ?? ((o) => ouvrirCanal(o));
    this.delais = options.delais ?? DELAIS_RECONNEXION_MS;
  }

  etat(): EtatConversation {
    return this.etatCourant;
  }

  abonner(ecouteur: (etat: EtatConversation) => void): () => void {
    this.ecouteurs.add(ecouteur);
    return () => this.ecouteurs.delete(ecouteur);
  }

  private poser(changement: Partial<EtatConversation>): void {
    this.etatCourant = { ...this.etatCourant, ...changement };
    for (const ecouteur of [...this.ecouteurs]) ecouteur(this.etatCourant);
  }

  private nouvelId(prefixe: string): string {
    this.compteur += 1;
    return `${prefixe}-${this.compteur}`;
  }

  demarrer(): void {
    this.arrete = false;
    void this.connecter();
  }

  arreter(): void {
    this.arrete = true;
    this.generation += 1;
    if (this.minuterie !== null) clearTimeout(this.minuterie);
    this.minuterie = null;
    this.canal?.fermer();
    this.canal = null;
  }

  /** Retour de la page (téléphone réveillé) : une reconnexion en attente est tentée aussitôt. */
  reveiller(): void {
    if (this.arrete || this.etatCourant.connexion !== "reconnexion") return;
    if (this.minuterie !== null) clearTimeout(this.minuterie);
    this.minuterie = null;
    void this.connecter();
  }

  private async connecter(): Promise<void> {
    const generation = ++this.generation;
    this.poser({ connexion: this.tentatives > 0 ? "reconnexion" : "connexion", tentativeDans: null });
    let canal: CanalJsonRpc;
    try {
      canal = await this.ouvrir({
        capacites: true,
        surEvenement: (e) => {
          if (generation !== this.generation) return;
          if (this.tampon) this.tampon.push(e);
          else this.surEvenement(e);
        },
        surClarify: (r) => {
          if (generation === this.generation) this.surClarify(r);
        },
        surRefus: (methode) => {
          if (generation === this.generation) this.poser({ refusees: [...this.etatCourant.refusees, methode] });
        },
        surFermeture: (volontaire) => {
          if (generation === this.generation && !volontaire) this.perdue();
        },
      });
    } catch (erreur) {
      if (generation !== this.generation) return;
      if (erreur instanceof ErreurCanal && erreur.genre === "sdk") {
        this.poser({ connexion: "indisponible" });
        return;
      }
      this.planifier();
      return;
    }
    if (generation !== this.generation || this.arrete) {
      canal.fermer();
      return;
    }
    this.canal = canal;
    if (this.etatCourant.cle) {
      try {
        await this.reprendre(canal, this.etatCourant.cle);
      } catch (erreur) {
        if (generation !== this.generation) return;
        canal.fermer();
        this.canal = null;
        if (erreur instanceof ErreurCanal && erreur.genre === "refus" && erreur.code === 4007) {
          this.poser({ connexion: "introuvable", erreur: { genre: "reprise", detail: detailDe(erreur) } });
          return;
        }
        this.poser({ erreur: { genre: "reprise", detail: detailDe(erreur) } });
        this.planifier();
        return;
      }
    }
    if (generation !== this.generation) return;
    this.tentatives = 0;
    this.poser({ connexion: "prete", tentativeDans: null });
  }

  private perdue(): void {
    this.canal = null;
    if (this.arrete) return;
    this.generation += 1;
    this.planifier();
  }

  private planifier(): void {
    if (this.arrete) return;
    const delai = this.delais[Math.min(this.tentatives, this.delais.length - 1)] ?? 10_000;
    this.tentatives += 1;
    this.poser({ connexion: "reconnexion", tentativeDans: Math.round(delai / 1000) });
    if (this.minuterie !== null) clearTimeout(this.minuterie);
    this.minuterie = setTimeout(() => {
      this.minuterie = null;
      void this.connecter();
    }, delai);
  }

  private async reprendre(canal: CanalJsonRpc, cle: string): Promise<void> {
    // Nouvelle connexion : les questions de l'ancienne n'y sont plus répondables ; celles qui arrivent PENDANT la reprise
    // (nouvelle question du tour) sont gardées, celles de l'instantané (open_requests) ajoutées ensuite.
    this.poser({ demandes: [] });
    this.tampon = [];
    let brut: Record<string, unknown> | null;
    try {
      brut = objet(await canal.appeler("session.resume", { session_id: cle }, DELAI_REPRISE_MS));
    } catch (erreur) {
      this.tampon = null;
      throw erreur;
    }
    const tampon = this.tampon ?? [];
    this.tampon = null;
    if (!brut) throw new ErreurCanal("reponse", "session.resume");
    const sessionId = chaine(brut.session_id);
    if (!sessionId) throw new ErreurCanal("reponse", "session.resume sans session_id");
    const messages: MessageFil[] = [];
    (Array.isArray(brut.messages) ? brut.messages : []).forEach((m, rang) => {
      const message = messageDeHistorique(m, rang);
      if (message) messages.push(message);
    });
    const enCours = brut.running === true;
    const inflight = objet(brut.inflight);
    if (enCours && inflight) {
      const utilisateur = chaine(inflight.user);
      const dernier = messages[messages.length - 1];
      if (utilisateur && !(dernier && dernier.role === "utilisateur" && dernier.texte === utilisateur)) {
        messages.push({ id: this.nouvelId("u"), role: "utilisateur", texte: utilisateur, enCours: false, fin: null });
      }
      messages.push({ id: this.nouvelId("r"), role: "hermes", texte: typeof inflight.assistant === "string"
        ? inflight.assistant : "", enCours: true, fin: null });
    }
    const info = objet(brut.info);
    this.poser({
      sessionId, messages, enCours, ligneEtat: null, erreur: null,
      titre: chaine(info?.title) ?? this.etatCourant.titre,
    });
    // Requêtes encore ouvertes : rejouées comme si elles venaient d'arriver (la page de l'autre appareil est fermée).
    for (const ouverte of Array.isArray(brut.open_requests) ? brut.open_requests : []) {
      const o = objet(ouverte);
      const id = chaine(o?.id);
      const methode = chaine(o?.method);
      if (!o || !id || !methode) continue;
      if (methode === "clarify") this.surClarify({ id, methode, params: objet(o.params) ?? {} });
    }
    // Puis les événements arrivés pendant la reprise : la fin d'un tour, un outil, une ligne d'état, une question
    // retirée ne doivent pas se perdre. Le texte en flux (start, delta, interim) n'est pas rejoué : l'instantané l'a
    // déjà, et le texte final du tour (message.complete) fait foi.
    for (const e of tampon) {
      if (e.type !== "message.start" && e.type !== "message.delta" && e.type !== "message.interim") this.surEvenement(e);
    }
  }

  private surClarify(requete: RequeteServeur): void {
    const demande = demandeDe(requete);
    if (!demande) {
      // Illisible : refusée plutôt que devinée (la requête est close, l'agent reçoit un refus).
      this.canal?.refuserClarify(requete.id);
      this.poser({ refusees: [...this.etatCourant.refusees, requete.methode] });
      return;
    }
    if (this.etatCourant.demandes.some((d) => d.id === demande.id)) return;
    this.poser({ demandes: [...this.etatCourant.demandes, demande] });
  }

  private surEvenement(e: EvenementCanal): void {
    const etat = this.etatCourant;
    if (e.sessionId !== null && etat.sessionId !== null && e.sessionId !== etat.sessionId) return;
    const payload = objet(e.payload) ?? {};
    switch (e.type) {
      case "message.start": {
        this.poser({ enCours: true, messages: [...etat.messages, {
          id: this.nouvelId("r"), role: "hermes", texte: "", enCours: true, fin: null }] });
        return;
      }
      case "message.delta": {
        const texte = typeof payload.text === "string" ? payload.text : "";
        if (!texte) return;
        this.poser({ messages: this.ajouterAuFlux(texte) });
        return;
      }
      case "message.interim": {
        const texte = typeof payload.text === "string" ? payload.text : "";
        if (texte && payload.already_streamed === false) this.poser({ messages: this.ajouterAuFlux(texte) });
        return;
      }
      case "message.complete": {
        const fin: FinTour = payload.status === "interrupted" || payload.status === "error" ? payload.status : "complete";
        const final = typeof payload.text === "string" && payload.text.trim() ? payload.text : null;
        const messages = [...this.etatCourant.messages];
        const rang = messages.map((m) => m.role === "hermes" && m.enCours).lastIndexOf(true);
        const dernier = messages[messages.length - 1];
        if (rang >= 0) {
          const courant = messages[rang] as MessageFil;
          messages[rang] = { ...courant, texte: final ?? courant.texte, enCours: false, fin };
        } else if (final && !(dernier && dernier.role === "hermes" && dernier.texte === final)) {
          // Sans bulle en cours (tour fini pendant une reprise) : ajoutée, sauf si l'historique repris la porte déjà.
          messages.push({ id: this.nouvelId("r"), role: "hermes", texte: final, enCours: false, fin });
        }
        const erreurTour = fin === "error" ? chaine(payload.error) ?? chaine(payload.failure_reason) : null;
        this.poser({ messages, enCours: false, ligneEtat: null,
                     erreur: fin === "error" ? { genre: "tour", detail: erreurTour } : this.etatCourant.erreur });
        return;
      }
      case "status.update": {
        const texte = chaine(payload.text);
        if (texte) this.poser({ ligneEtat: texte.slice(0, 300) });
        return;
      }
      case "error": {
        const texte = chaine(payload.message);
        if (texte) this.poser({ messages: [...etat.messages, {
          id: this.nouvelId("e"), role: "erreur", texte: texte.slice(0, 2000), enCours: false, fin: null }] });
        return;
      }
      case "tool.start": {
        const nom = chaine(payload.name);
        if (nom) this.poser({ messages: [...etat.messages, {
          id: this.nouvelId("o"), role: "outil", texte: nom.slice(0, 120), enCours: false, fin: null }] });
        return;
      }
      case "session.title": {
        const titre = chaine(payload.title);
        if (titre) this.poser({ titre: titre.slice(0, 200) });
        return;
      }
      case "request.cancel": {
        const id = chaine(payload.id);
        if (!id || !etat.demandes.some((d) => d.id === id)) return;
        this.canal?.oublierClarify(id);
        this.poser({ demandes: etat.demandes.filter((d) => d.id !== id),
                     retirees: [...etat.retirees, chaine(payload.reason)] });
        return;
      }
      default:
        return;
    }
  }

  private ajouterAuFlux(texte: string): MessageFil[] {
    const messages = [...this.etatCourant.messages];
    const rang = messages.map((m) => m.role === "hermes" && m.enCours).lastIndexOf(true);
    if (rang >= 0) {
      const courant = messages[rang] as MessageFil;
      messages[rang] = { ...courant, texte: courant.texte + texte };
    } else {
      messages.push({ id: this.nouvelId("r"), role: "hermes", texte, enCours: true, fin: null });
    }
    return messages;
  }

  /** Envoie un message ; rend vrai s'il a été accepté (la page vide alors le champ). */
  async envoyer(texte: string): Promise<boolean> {
    const propre = texte.trim();
    const canal = this.canal;
    if (!propre || propre.length > TEXTE_MAX || !canal || this.etatCourant.connexion !== "prete" || this.etatCourant.enCours) {
      return false;
    }
    let sessionId = this.etatCourant.sessionId;
    if (!sessionId) {
      try {
        const cree = objet(await canal.appeler("session.create", {}));
        sessionId = chaine(cree?.session_id);
        const cle = chaine(cree?.stored_session_id) ?? sessionId;
        if (!sessionId || !cle) throw new ErreurCanal("reponse", "session.create");
        this.poser({ sessionId, cle });
        this.options.surCle?.(cle);
      } catch (erreur) {
        this.poser({ erreur: { genre: "creation", detail: detailDe(erreur) } });
        return false;
      }
    }
    this.poser({ enCours: true, erreur: null });
    try {
      await canal.appeler("prompt.submit", { session_id: sessionId, text: propre });
    } catch (erreur) {
      this.poser({ enCours: false, erreur: { genre: "envoi", detail: detailDe(erreur) } });
      return false;
    }
    // Le message de l'utilisateur précède la réponse en flux, même si message.start est arrivé avant la réponse RPC.
    const messages = [...this.etatCourant.messages];
    const rang = messages.findIndex((m) => m.role === "hermes" && m.enCours);
    const utilisateur: MessageFil = { id: this.nouvelId("u"), role: "utilisateur", texte: propre, enCours: false, fin: null };
    if (rang >= 0) messages.splice(rang, 0, utilisateur);
    else messages.push(utilisateur);
    this.poser({ messages });
    return true;
  }

  async interrompre(): Promise<void> {
    const canal = this.canal;
    const sessionId = this.etatCourant.sessionId;
    if (!canal || !sessionId) return;
    try {
      await canal.appeler("session.interrupt", { session_id: sessionId });
    } catch (erreur) {
      this.poser({ erreur: { genre: "interruption", detail: detailDe(erreur) } });
    }
  }

  /** Répond à une demande « clarify » ; rend vrai si la réponse est partie. */
  repondre(id: string, saisies: Record<string, Saisie>): boolean {
    const demande = this.etatCourant.demandes.find((d) => d.id === id);
    const canal = this.canal;
    if (!demande || !canal) return false;
    try {
      canal.repondreClarify(id, reponseDe(demande, saisies));
    } catch (erreur) {
      this.poser({ erreur: { genre: "reponse", detail: detailDe(erreur) } });
      return false;
    }
    this.poser({ demandes: this.etatCourant.demandes.filter((d) => d.id !== id), erreur: null });
    return true;
  }
}
