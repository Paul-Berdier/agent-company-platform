/**
 * Client du journal et du flux d’événements d’une tentative (spec Lot E §10).
 *
 * Deux lectures complémentaires :
 * 1. `fetchRunEvents` — page de journal par curseur (`GET /runs/{id}/events`), source de
 *    vérité durable, utilisée pour le passé et pour la réconciliation après coupure ;
 * 2. `openRunStream` — flux `EventSource` (`GET /streams/runs/{id}`) avec
 *    `withCredentials`, reconnexion exponentielle bornée, **déduplication par séquence**
 *    et bascule automatique en interrogation après trois échecs consécutifs.
 *
 * Règles non négociables appliquées ici :
 * - une reconnexion ne rejoue jamais un événement déjà rendu : le curseur est une borne
 *   haute et les événements sans séquence sont dédupliqués par identifiant ;
 * - une coupure n’invente aucun état : l’état exposé reste
 *   `connected | reconnecting | polling | offline`, jamais « à jour » par défaut ;
 * - aucun média ne transite ici : le `payload` d’un événement de média ne porte qu’une
 *   référence d’artefact (`artifact_id`, `content_type`, `size_bytes`, `sha256`,
 *   `stream_kind`), jamais des octets.
 *
 * Le client HTTP est **fourni par le shell** (règle du Lot D) : ce module n’en crée
 * jamais un et ne lit jamais `/auth/session`, sous peine de faire tourner le jeton CSRF.
 */

import type { EventPage, StreamEvent } from "@acp/contracts";

import { WorkspaceApiError, WorkspaceHttpClient, isRecord } from "./workspace-api";

/** Limite par défaut d’une page de journal (la route borne à 500). */
export const EVENTS_PAGE_LIMIT_DEFAULT = 100;
/** Limite maximale acceptée par `GET /runs/{id}/events`. */
export const EVENTS_PAGE_LIMIT_MAX = 500;

/** Premier délai de reconnexion, doublé à chaque échec consécutif. */
export const STREAM_RECONNECT_BASE_MS = 1_000;
/** Plafond du délai de reconnexion : la progression exponentielle reste bornée. */
export const STREAM_RECONNECT_MAX_MS = 15_000;
/** Nombre d’échecs consécutifs après lequel le client bascule en interrogation. */
export const STREAM_FAILURES_BEFORE_POLLING = 3;
/** Période d’interrogation lorsque le flux est indisponible. */
export const STREAM_POLL_INTERVAL_MS = 5_000;
/** Nombre d’interrogations réussies avant une nouvelle tentative de direct. */
export const STREAM_POLLS_BEFORE_LIVE_RETRY = 6;
/** Nombre d’identifiants retenus pour dédupliquer les événements sans séquence. */
export const STREAM_SEEN_IDS_MAX = 1_000;

/**
 * Nom SSE de la trame émise juste avant une rotation propre du flux (§5.2).
 *
 * `streams.py` l’émet comme un **événement nommé** dont le `data` est un payload nu
 * `{cursor, reason}` — ce n’est pas un `StreamEvent`. Un `EventSource` ne remet une
 * trame nommée qu’aux écouteurs enregistrés sous ce nom exact : le client doit donc
 * écouter ce nom, sinon chaque rotation serait vue comme une panne de connexion.
 */
export const STREAM_ROTATE_EVENT_TYPE = "acp.stream.rotate";
/** Nom SSE de la trame de fermeture annoncée par le serveur (`{reason}`). */
export const STREAM_CLOSED_EVENT_TYPE = "acp.stream.closed";
/** Raison de fermeture qui signale une révocation d’accès pendant le flux. */
export const STREAM_CLOSED_REASON_UNAUTHORIZED = "unauthorized";
/** Nom de l’événement SSE nommé qui transporte les `StreamEvent`. */
export const STREAM_EVENT_NAME = "acp.event";

/** Types d’événements qui terminent une tentative : au-delà, le Studio est un replay. */
export const RUN_TERMINAL_EVENT_TYPES: ReadonlySet<string> = new Set([
  "task.completed",
  "task.failed",
  "task.cancelled",
  "task.interrupted",
]);

/** Types d’images dont l’aperçu inline est autorisé par la spécification (§7). */
export const PREVIEWABLE_IMAGE_TYPES: ReadonlySet<string> = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
]);

/** Types de vidéos dont l’aperçu inline est autorisé (§7). */
export const PREVIEWABLE_VIDEO_TYPES: ReadonlySet<string> = new Set([
  "video/webm",
  "video/mp4",
]);

/** Type du conteneur GLB auto-contenu accepté par le serveur pour l'aperçu 3D. */
export const PREVIEWABLE_MODEL_TYPES: ReadonlySet<string> = new Set([
  "model/gltf-binary",
]);

export type StreamConnectionState = "connected" | "reconnecting" | "polling" | "offline";

export type StudioMode = "live" | "interim" | "replay" | "unknown";

/** Classement d’un contenu : image et vidéo s’affichent, tout le reste se télécharge. */
export type ArtifactPreviewKind = "image" | "video" | "model" | "download";

/** Référence d’artefact portée par un événement de média (jamais les octets). */
export interface MediaReference {
  eventId: string;
  artifactId: string;
  contentType: string;
  sizeBytes: number | null;
  sha256: string | null;
  streamKind: string;
  occurredAt: string;
}

/** Sous-ensemble de `MessageEvent` réellement utilisé, pour rester testable sous Node. */
export interface StreamMessageLike {
  data: unknown;
  lastEventId?: string;
}

/** Sous-ensemble de `EventSource` réellement utilisé. */
export interface EventSourceLike {
  addEventListener(type: string, listener: (event: StreamMessageLike) => void): void;
  close(): void;
  onopen: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onmessage: ((event: StreamMessageLike) => void) | null;
}

/**
 * Fabrique d’`EventSource`. Renvoyer `null` signale que la capacité n’existe pas dans
 * cet environnement : le client bascule alors immédiatement en interrogation.
 */
export type EventSourceFactory = (
  url: string,
  init: { withCredentials: boolean },
) => EventSourceLike | null;

/** Minuteries injectables : les tests n’ont besoin d’aucune horloge réelle. */
export interface TimerApi {
  setTimeout: (handler: () => void, delayMs: number) => unknown;
  clearTimeout: (handle: unknown) => void;
}

export interface RunStreamHandlers {
  /** Reçoit uniquement des événements nouveaux, dans l’ordre d’arrivée. */
  onEvents: (events: StreamEvent[]) => void;
  onState?: (state: StreamConnectionState) => void;
  onError?: (error: WorkspaceApiError) => void;
}

export interface RunStreamSubscription {
  readonly state: StreamConnectionState;
  /** Séquence la plus haute déjà rendue, ou `null` si aucune. */
  readonly cursor: number | null;
  /** Échecs consécutifs du flux depuis la dernière connexion établie. */
  readonly failures: number;
  /** Trames reçues mais inexploitables : comptées, jamais rendues. */
  readonly malformed: number;
  readonly closed: boolean;
  /** Relance immédiatement le direct depuis le curseur courant. */
  retryNow(): void;
  close(): void;
}

// --- Validateurs stricts -------------------------------------------------------

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNullableInteger(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isInteger(value));
}

export function isStreamEvent(value: unknown): value is StreamEvent {
  if (!isRecord(value)) return false;
  return typeof value.schema_version === "string"
    && typeof value.id === "string"
    && isNullableInteger(value.sequence)
    && typeof value.type === "string"
    && typeof value.occurred_at === "string"
    && isNullableString(value.project_id)
    && isNullableString(value.conversation_id)
    && isNullableString(value.task_id)
    && isNullableString(value.task_run_id)
    && isNullableString(value.step_id)
    && isNullableString(value.executor)
    && isNullableString(value.emitted_by)
    && isRecord(value.payload);
}

/**
 * Curseur annoncé par une trame `acp.stream.rotate`.
 *
 * La trame nommée porte le payload nu (`{cursor, reason}`) ; la variante historique, où
 * la rotation arrivait comme un `StreamEvent`, le porte dans `payload`. Les deux formes
 * sont acceptées, ainsi que les deux noms de champ plausibles (`cursor`, `after_seq`).
 */
export function streamRotateCursor(value: unknown): number | null {
  if (!isRecord(value)) return null;
  const source = isRecord(value.payload) ? value.payload : value;
  const announced = source.cursor ?? source.after_seq;
  return typeof announced === "number" && Number.isInteger(announced) ? announced : null;
}

/** Raison portée par une trame `acp.stream.closed`, ou `null` si elle est illisible. */
export function streamClosedReason(value: unknown): string | null {
  if (!isRecord(value)) return null;
  const source = isRecord(value.payload) ? value.payload : value;
  return typeof source.reason === "string" && source.reason ? source.reason : null;
}

export function isEventPage(value: unknown): value is EventPage {
  if (!isRecord(value)) return false;
  return Array.isArray(value.events)
    && value.events.every(isStreamEvent)
    && isNullableInteger(value.next_cursor)
    && typeof value.has_more === "boolean"
    && isNullableInteger(value.retention_days);
}

// --- Helpers purs --------------------------------------------------------------

/** Délai de reconnexion exponentiel borné (échec 1 ⇒ base, puis doublement). */
export function streamReconnectDelay(failures: number): number {
  const steps = Math.max(1, Math.floor(failures)) - 1;
  const delay = STREAM_RECONNECT_BASE_MS * 2 ** steps;
  return Math.min(delay, STREAM_RECONNECT_MAX_MS);
}

function eventInstant(event: StreamEvent): number {
  const parsed = Date.parse(event.occurred_at);
  return Number.isNaN(parsed) ? 0 : parsed;
}

/**
 * Fusionne deux listes d’événements sans jamais dupliquer un identifiant et rend la
 * chronologie triée par date puis par séquence. Aucune limite n’est appliquée : le
 * passé chargé explicitement par l’utilisateur ne doit jamais disparaître au profit
 * d’un événement récent.
 */
export function mergeStreamEvents(
  existing: readonly StreamEvent[],
  incoming: readonly StreamEvent[],
): StreamEvent[] {
  const byId = new Map<string, StreamEvent>();
  for (const event of existing) byId.set(event.id, event);
  for (const event of incoming) if (!byId.has(event.id)) byId.set(event.id, event);
  return [...byId.values()].sort((left, right) => {
    const instants = eventInstant(left) - eventInstant(right);
    if (instants !== 0) return instants;
    return (left.sequence ?? 0) - (right.sequence ?? 0);
  });
}

export function isRunTerminalEvent(event: StreamEvent): boolean {
  return RUN_TERMINAL_EVENT_TYPES.has(event.type);
}

/** Curseur le plus haut d’une liste d’événements, ou `null` si aucune séquence. */
export function eventsCursor(events: readonly StreamEvent[]): number | null {
  let cursor: number | null = null;
  for (const event of events) {
    if (typeof event.sequence === "number" && (cursor === null || event.sequence > cursor)) {
      cursor = event.sequence;
    }
  }
  return cursor;
}

/** Construit une référence depuis une table `{artifact_id, content_type, …}`. */
function referenceFrom(event: StreamEvent, source: Record<string, unknown>): MediaReference | null {
  const artifactId = source.artifact_id;
  if (typeof artifactId !== "string" || !artifactId) return null;
  const streamKind = typeof source.stream_kind === "string" ? source.stream_kind : "";
  const contentType = typeof source.content_type === "string" && source.content_type
    ? source.content_type
    : "application/octet-stream";
  return {
    eventId: event.id,
    artifactId,
    contentType,
    sizeBytes: typeof source.size_bytes === "number" && Number.isFinite(source.size_bytes)
      ? source.size_bytes
      : null,
    sha256: typeof source.sha256 === "string" ? source.sha256 : null,
    streamKind,
    occurredAt: event.occurred_at,
  };
}

/**
 * Toutes les références d’artefact d’un événement, dans l’ordre où il les porte.
 *
 * Deux formes coexistent côté serveur et il faut lire les deux : un événement de média
 * dédié, dont le payload **est** la référence, et un `test.case.finished`, qui range ses
 * références sous `payload.attachments[]` (`testing_service._attachment_references`).
 * Ne lire que le premier niveau laissait la capture d’une vraie exécution Playwright
 * invisible du Studio, faute d’événement de la première forme.
 */
export function mediaReferences(event: StreamEvent): MediaReference[] {
  const payload = event.payload;
  const references: MediaReference[] = [];
  const top = referenceFrom(event, payload);
  if (top) references.push(top);
  const attachments = payload.attachments;
  if (Array.isArray(attachments)) {
    for (const attachment of attachments) {
      if (!attachment || typeof attachment !== "object" || Array.isArray(attachment)) continue;
      const reference = referenceFrom(event, attachment as Record<string, unknown>);
      if (reference) references.push(reference);
    }
  }
  return references;
}

/** Première référence de média portée par un événement, ou `null` s’il n’en porte aucune. */
export function mediaReference(event: StreamEvent): MediaReference | null {
  return mediaReferences(event)[0] ?? null;
}

/**
 * Dernière référence de média d’un `stream_kind` donné dans **cette** liste d’événements.
 * La liste étant toujours celle d’une seule tentative, une capture d’un autre run ne peut
 * pas y apparaître.
 */
export function lastMediaReference(
  events: readonly StreamEvent[],
  streamKind: string,
): MediaReference | null {
  let found: MediaReference | null = null;
  for (const event of events) {
    for (const reference of mediaReferences(event)) {
      if (reference.streamKind === streamKind) found = reference;
    }
  }
  return found;
}

/** Classe un type MIME déclaré : hors allowlist, le contenu se télécharge (§7). */
export function classifyArtifactPreview(contentType: string): ArtifactPreviewKind {
  const normalized = contentType.split(";")[0]?.trim().toLowerCase() ?? "";
  if (PREVIEWABLE_IMAGE_TYPES.has(normalized)) return "image";
  if (PREVIEWABLE_VIDEO_TYPES.has(normalized)) return "video";
  if (PREVIEWABLE_MODEL_TYPES.has(normalized)) return "model";
  return "download";
}

/**
 * Mode du bandeau du Studio. Aucun direct n’est annoncé sans flux connecté, et une
 * tentative terminée est toujours un replay, même si le flux reste ouvert.
 */
export function studioMode(input: {
  connection: StreamConnectionState;
  terminal: boolean;
}): StudioMode {
  if (input.terminal) return "replay";
  if (input.connection === "connected") return "live";
  if (input.connection === "polling") return "interim";
  return "unknown";
}

export function describeStudioMode(mode: StudioMode): {
  label: string;
  description: string;
  tone: string;
} {
  switch (mode) {
    case "live":
      return {
        label: "Direct",
        description: "Le flux d’événements est connecté : la chronologie se complète en temps réel.",
        tone: "active",
      };
    case "interim":
      return {
        label: "Aperçu intermédiaire",
        description: "Le flux est indisponible : la vue est rafraîchie par lectures périodiques du journal.",
        tone: "waiting",
      };
    case "replay":
      return {
        label: "Replay",
        description: "La tentative est terminée : la chronologie affichée est relue depuis le journal persisté.",
        tone: "done",
      };
    default:
      return {
        label: "Hors ligne / inconnu",
        description: "Aucune source n’est confirmée : l’état réel de la tentative n’est pas connu d’ici.",
        tone: "failed",
      };
  }
}

export function describeConnectionState(
  state: StreamConnectionState,
  failures: number,
): { label: string; tone: string } {
  switch (state) {
    case "connected":
      return { label: "Flux connecté", tone: "active" };
    case "reconnecting":
      return failures === 0
        ? { label: "Connexion au flux…", tone: "waiting" }
        : { label: "Reconnexion…", tone: "waiting" };
    case "polling":
      return { label: "Interrogation périodique", tone: "waiting" };
    default:
      return { label: "Hors ligne", tone: "failed" };
  }
}

// --- Flux ----------------------------------------------------------------------

function defaultEventSource(url: string, init: { withCredentials: boolean }): EventSourceLike | null {
  if (typeof EventSource === "undefined") return null;
  return new EventSource(url, init) as unknown as EventSourceLike;
}

const defaultTimers: TimerApi = {
  setTimeout: (handler, delayMs) => globalThis.setTimeout(handler, delayMs),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/** Fin de flux annoncée par le serveur, avant la fermeture effective de la connexion. */
type StreamEndAnnouncement = { kind: "rotate" } | { kind: "closed"; reason: string | null };

function asApiError(error: unknown, fallback: string): WorkspaceApiError {
  return error instanceof WorkspaceApiError
    ? error
    : new WorkspaceApiError(fallback, "invalid_response");
}

class RunStream implements RunStreamSubscription {
  state: StreamConnectionState = "reconnecting";
  cursor: number | null;
  failures = 0;
  malformed = 0;
  closed = false;

  private source: EventSourceLike | null = null;
  private timer: unknown = null;
  /** Fin de flux annoncée par le serveur : attendue, donc jamais comptée comme panne. */
  private announcedEnd: StreamEndAnnouncement | null = null;
  private pollsSinceLiveAttempt = 0;
  private readonly seenIds = new Set<string>();
  private readonly seenOrder: string[] = [];

  constructor(
    private readonly client: EventsApiClient,
    private readonly runId: string,
    cursor: number | null,
    private readonly handlers: RunStreamHandlers,
    private readonly factory: EventSourceFactory,
    private readonly timers: TimerApi,
    private readonly streamUrl: (runId: string, cursor: number | null) => string,
  ) {
    this.cursor = cursor;
    this.openSource();
  }

  retryNow(): void {
    if (this.closed) return;
    this.failures = 0;
    this.pollsSinceLiveAttempt = 0;
    this.openSource();
  }

  close(): void {
    this.closed = true;
    this.clearTimer();
    this.closeSource();
  }

  // --- Machine à états ---------------------------------------------------------

  private setState(state: StreamConnectionState): void {
    if (this.closed || this.state === state) return;
    this.state = state;
    this.handlers.onState?.(state);
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      this.timers.clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private closeSource(): void {
    if (this.source) {
      this.source.onopen = null;
      this.source.onerror = null;
      this.source.onmessage = null;
      this.source.close();
      this.source = null;
    }
  }

  private openSource(): void {
    if (this.closed) return;
    this.clearTimer();
    this.closeSource();
    this.announcedEnd = null;
    const source = this.factory(this.streamUrl(this.runId, this.cursor), { withCredentials: true });
    if (!source) {
      // Capacité absente : l’interrogation est le seul mode honnête disponible.
      void this.poll();
      return;
    }
    this.source = source;
    const onMessage = (message: StreamMessageLike) => this.receive(message);
    source.addEventListener(STREAM_EVENT_NAME, onMessage);
    // Les trames de service sont des événements SSE **nommés** : sans écouteur dédié,
    // elles n’atteindraient ni cet `addEventListener` ni `onmessage`, et chaque rotation
    // serait comptée comme une panne (bandeau « Reconnexion… » toutes les 15 minutes).
    source.addEventListener(STREAM_ROTATE_EVENT_TYPE, (message) => this.receiveRotate(message));
    source.addEventListener(STREAM_CLOSED_EVENT_TYPE, (message) => this.receiveClosed(message));
    source.onmessage = onMessage;
    source.onopen = () => {
      if (this.closed) return;
      this.failures = 0;
      this.pollsSinceLiveAttempt = 0;
      this.setState("connected");
    };
    source.onerror = () => this.handleStreamFailure();
  }

  private handleStreamFailure(): void {
    if (this.closed) return;
    this.closeSource();
    const announced = this.announcedEnd;
    this.announcedEnd = null;
    if (announced) {
      if (announced.kind === "closed" && announced.reason === STREAM_CLOSED_REASON_UNAUTHORIZED) {
        // Accès révoqué pendant le flux : rouvrir en boucle annoncerait un direct qui
        // n’existe plus. L’interrogation fait apparaître le vrai refus HTTP (401/403).
        void this.poll();
        return;
      }
      // Rotation ou fermeture propre annoncée : ce n’est pas une panne, on reprend au curseur.
      this.openSource();
      return;
    }
    if (this.state === "polling" || this.state === "offline") {
      // Échec d’une tentative de retour au direct : l’interrogation reprend son rythme
      // sans compter d’échec supplémentaire ni annoncer un direct qui n’existe pas.
      this.schedulePoll(STREAM_POLL_INTERVAL_MS);
      return;
    }
    this.failures += 1;
    if (this.failures >= STREAM_FAILURES_BEFORE_POLLING) {
      void this.poll();
      return;
    }
    this.setState("reconnecting");
    this.timer = this.timers.setTimeout(() => {
      this.timer = null;
      this.openSource();
    }, streamReconnectDelay(this.failures));
  }

  // --- Réception ---------------------------------------------------------------

  /** Décode le `data` d’une trame ; `undefined` signale une trame illisible (comptée). */
  private decode(message: StreamMessageLike): unknown {
    const raw = message.data;
    if (typeof raw !== "string") {
      this.malformed += 1;
      return undefined;
    }
    try {
      return JSON.parse(raw);
    } catch {
      this.malformed += 1;
      return undefined;
    }
  }

  private receive(message: StreamMessageLike): void {
    if (this.closed) return;
    const parsed = this.decode(message);
    if (parsed === undefined) return;
    if (!isStreamEvent(parsed)) {
      this.malformed += 1;
      return;
    }
    // Variante historique : la trame de service arrive par le canal `acp.event`.
    if (parsed.type === STREAM_ROTATE_EVENT_TYPE) {
      this.announceRotate(parsed);
      return;
    }
    if (parsed.type === STREAM_CLOSED_EVENT_TYPE) {
      this.announceClosed(parsed);
      return;
    }
    this.deliver([parsed]);
  }

  /** Trame `event: acp.stream.rotate` : reprise annoncée, jamais une ligne de chronologie. */
  private receiveRotate(message: StreamMessageLike): void {
    if (this.closed) return;
    // Le nom SSE suffit à annoncer la rotation : un payload illisible est compté, mais
    // il ne transforme pas une fin attendue en panne — seul le curseur n’avance pas.
    this.announceRotate(this.decode(message));
  }

  /** Trame `event: acp.stream.closed` : fin décidée par le serveur, avec sa raison. */
  private receiveClosed(message: StreamMessageLike): void {
    if (this.closed) return;
    this.announceClosed(this.decode(message));
  }

  private announceRotate(payload: unknown): void {
    this.announcedEnd = { kind: "rotate" };
    const announced = streamRotateCursor(payload);
    if (announced !== null && (this.cursor === null || announced > this.cursor)) {
      this.cursor = announced;
    }
  }

  private announceClosed(payload: unknown): void {
    this.announcedEnd = { kind: "closed", reason: streamClosedReason(payload) };
  }

  /** Filtre les événements déjà rendus, avance le curseur, puis notifie l’appelant. */
  private deliver(events: readonly StreamEvent[]): void {
    const fresh: StreamEvent[] = [];
    for (const event of events) {
      if (typeof event.sequence === "number") {
        if (this.cursor !== null && event.sequence <= this.cursor) continue;
        this.cursor = event.sequence;
      } else if (this.seenIds.has(event.id)) {
        continue;
      }
      this.remember(event.id);
      fresh.push(event);
    }
    if (fresh.length) this.handlers.onEvents(fresh);
  }

  private remember(id: string): void {
    if (this.seenIds.has(id)) return;
    this.seenIds.add(id);
    this.seenOrder.push(id);
    while (this.seenOrder.length > STREAM_SEEN_IDS_MAX) {
      const oldest = this.seenOrder.shift();
      if (oldest !== undefined) this.seenIds.delete(oldest);
    }
  }

  // --- Interrogation -----------------------------------------------------------

  private schedulePoll(delayMs: number): void {
    if (this.closed) return;
    this.clearTimer();
    this.timer = this.timers.setTimeout(() => {
      this.timer = null;
      void this.poll();
    }, delayMs);
  }

  private async poll(): Promise<void> {
    if (this.closed) return;
    this.clearTimer();
    this.closeSource();
    let page: EventPage;
    try {
      page = await this.client.fetchRunEvents(this.runId, { afterSeq: this.cursor });
    } catch (error) {
      if (this.closed) return;
      this.setState("offline");
      this.handlers.onError?.(asApiError(error, "Le journal de la tentative est illisible."));
      this.schedulePoll(STREAM_POLL_INTERVAL_MS);
      return;
    }
    if (this.closed) return;
    this.setState("polling");
    this.deliver(page.events);
    this.pollsSinceLiveAttempt += 1;
    if (this.pollsSinceLiveAttempt >= STREAM_POLLS_BEFORE_LIVE_RETRY) {
      // Le direct est retenté sans quitter le mode « interrogation » : tant qu’aucune
      // connexion n’est établie, l’interface ne doit pas annoncer un direct.
      this.pollsSinceLiveAttempt = 0;
      this.openSource();
      return;
    }
    this.schedulePoll(page.has_more ? 0 : STREAM_POLL_INTERVAL_MS);
  }
}

export class EventsApiClient {
  private readonly factory: EventSourceFactory;
  private readonly timers: TimerApi;

  /**
   * `http` est le client du shell : le passer est la seule façon correcte de câbler ce
   * module (jeton CSRF partagé, aucune lecture de `/auth/session`).
   */
  constructor(
    private readonly http: WorkspaceHttpClient,
    options: { eventSource?: EventSourceFactory; timers?: TimerApi } = {},
  ) {
    this.factory = options.eventSource ?? defaultEventSource;
    this.timers = options.timers ?? defaultTimers;
  }

  fetchRunEvents(
    runId: string,
    options: { afterSeq?: number | null; limit?: number } = {},
  ): Promise<EventPage> {
    const limit = Math.max(1, Math.min(options.limit ?? EVENTS_PAGE_LIMIT_DEFAULT, EVENTS_PAGE_LIMIT_MAX));
    const query = new URLSearchParams();
    if (typeof options.afterSeq === "number") query.set("after_seq", String(options.afterSeq));
    query.set("limit", String(limit));
    return this.http.request(
      `/runs/${encodeURIComponent(runId)}/events?${query.toString()}`,
      isEventPage,
    );
  }

  openRunStream(
    runId: string,
    cursor: number | null,
    handlers: RunStreamHandlers,
  ): RunStreamSubscription {
    return new RunStream(
      this,
      runId,
      cursor,
      handlers,
      this.factory,
      this.timers,
      (id, at) => this.streamUrl(id, at),
    );
  }

  private streamUrl(runId: string, cursor: number | null): string {
    const suffix = cursor === null ? "" : `?after_seq=${cursor}`;
    return `${this.http.baseUrl}/streams/runs/${encodeURIComponent(runId)}${suffix}`;
  }
}
