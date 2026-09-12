/**
 * Tests du client d’événements du Studio (`events-api.ts`, spec Lot E §10).
 *
 * Aucune dépendance n’est ajoutée : l’`EventSource` et les minuteries sont injectés
 * par le constructeur, ce qui rend la reconnexion, la déduplication et la bascule en
 * interrogation déterministes sous Node, sans réseau ni navigateur.
 *
 * Les garanties vérifiées ici sont celles de la spécification :
 * une reconnexion ne rejoue jamais un événement déjà vu, trois échecs consécutifs
 * basculent en interrogation, et l’état exposé reste
 * `connected | reconnecting | polling | offline`.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import {
  EVENTS_PAGE_LIMIT_DEFAULT,
  EVENTS_PAGE_LIMIT_MAX,
  EventsApiClient,
  STREAM_CLOSED_EVENT_TYPE,
  STREAM_EVENT_NAME,
  STREAM_FAILURES_BEFORE_POLLING,
  STREAM_POLLS_BEFORE_LIVE_RETRY,
  STREAM_POLL_INTERVAL_MS,
  STREAM_RECONNECT_BASE_MS,
  STREAM_RECONNECT_MAX_MS,
  STREAM_ROTATE_EVENT_TYPE,
  classifyArtifactPreview,
  describeConnectionState,
  describeStudioMode,
  isRunTerminalEvent,
  lastMediaReference,
  mergeStreamEvents,
  streamReconnectDelay,
  studioMode,
  type EventSourceLike,
  type StreamMessageLike,
  type TimerApi,
} from "../src/events-api";
import { WorkspaceApiError, WorkspaceHttpClient } from "../src/workspace-api";

// --- Outillage ----------------------------------------------------------------

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function streamEvent(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "1.0",
    id: "evt-1",
    sequence: 1,
    type: "task.progress",
    occurred_at: "2026-09-12T10:00:00Z",
    project_id: "prj-1",
    conversation_id: null,
    task_id: "task-1",
    task_run_id: "run-1",
    step_id: "step-1",
    executor: "worker:w-1",
    emitted_by: "worker",
    payload: {},
    ...overrides,
  };
}

function page(events: unknown[], overrides: Record<string, unknown> = {}) {
  const sequences = events
    .map((event) => (event as { sequence: number | null }).sequence)
    .filter((value): value is number => typeof value === "number");
  return {
    events,
    next_cursor: sequences.length ? Math.max(...sequences) : null,
    has_more: false,
    retention_days: 90,
    ...overrides,
  };
}

/** Minuteries manuelles : aucune horloge réelle, l’ordre de déclenchement est explicite. */
class ManualTimers {
  private sequence = 0;
  private readonly pending = new Map<number, { run: () => void; delay: number }>();

  readonly api: TimerApi = {
    setTimeout: (handler: () => void, delay: number) => {
      const id = ++this.sequence;
      this.pending.set(id, { run: handler, delay });
      return id;
    },
    clearTimeout: (handle: unknown) => {
      this.pending.delete(handle as number);
    },
  };

  get delays(): number[] {
    return [...this.pending.values()].map((timer) => timer.delay);
  }

  get size(): number {
    return this.pending.size;
  }

  /** Déclenche la minuterie la plus anciennement programmée et laisse les promesses se résoudre. */
  async fire(): Promise<void> {
    const entry = [...this.pending.entries()][0];
    if (!entry) throw new Error("aucune minuterie programmée");
    this.pending.delete(entry[0]);
    entry[1].run();
    await flush();
  }
}

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];

  onopen: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: StreamMessageLike) => void) | null = null;
  closed = false;
  private readonly listeners = new Map<string, ((event: StreamMessageLike) => void)[]>();

  constructor(readonly url: string, readonly init: { withCredentials: boolean }) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: StreamMessageLike) => void): void {
    const existing = this.listeners.get(type) ?? [];
    existing.push(listener);
    this.listeners.set(type, existing);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.onopen?.({});
  }

  fail(): void {
    this.onerror?.({});
  }

  /**
   * Dispatche comme un vrai `EventSource` : une trame nommée n’atteint que les écouteurs
   * enregistrés sous **ce** nom, et `onmessage` ne reçoit que les trames sans nom.
   */
  emit(name: string, data: string): void {
    for (const listener of this.listeners.get(name) ?? []) listener({ data });
    if (name === "message") this.onmessage?.({ data });
  }

  deliver(event: unknown): void {
    this.raw(JSON.stringify(event));
  }

  raw(data: string): void {
    this.emit("acp.event", data);
  }

  /** Trame `event: acp.stream.rotate` telle que l’API l’émet : payload nu, pas un `StreamEvent`. */
  rotate(payload: unknown): void {
    this.emit("acp.stream.rotate", JSON.stringify(payload));
  }

  /** Trame `event: acp.stream.closed` : fin annoncée par le serveur, avec sa raison. */
  serverClosed(reason: string): void {
    this.emit("acp.stream.closed", JSON.stringify({ reason }));
  }
}

function harness(options: { fetcher?: typeof fetch } = {}) {
  FakeEventSource.instances = [];
  const timers = new ManualTimers();
  const fetcher = options.fetcher ?? vi.fn(async () => json(page([])));
  const http = new WorkspaceHttpClient({ baseUrl: "http://api.test", fetcher });
  const client = new EventsApiClient(http, {
    eventSource: (url, init) => new FakeEventSource(url, init),
    timers: timers.api,
  });
  const events: unknown[][] = [];
  const states: string[] = [];
  const handlers = {
    onEvents: (batch: unknown[]) => events.push(batch),
    onState: (state: string) => states.push(state),
  };
  return { client, timers, fetcher, events, states, handlers };
}

function latestSource(): FakeEventSource {
  const source = FakeEventSource.instances[FakeEventSource.instances.length - 1];
  if (!source) throw new Error("aucun EventSource ouvert");
  return source;
}

// --- Lecture paginée ----------------------------------------------------------

describe("EventsApiClient.fetchRunEvents", () => {
  it("lit une page par curseur et borne la limite demandée", async () => {
    const fetcher = vi.fn(async () => json(page([streamEvent()])));
    const http = new WorkspaceHttpClient({ baseUrl: "http://api.test", fetcher });
    const client = new EventsApiClient(http);

    const result = await client.fetchRunEvents("run 1", { afterSeq: 12, limit: 900 });

    expect(fetcher.mock.calls[0][0]).toBe(
      `http://api.test/runs/run%201/events?after_seq=12&limit=${EVENTS_PAGE_LIMIT_MAX}`,
    );
    expect(result.events).toHaveLength(1);
    expect(result.retention_days).toBe(90);
  });

  it("omet le curseur à la première page et applique la limite par défaut", async () => {
    const fetcher = vi.fn(async () => json(page([])));
    const http = new WorkspaceHttpClient({ baseUrl: "http://api.test", fetcher });
    const client = new EventsApiClient(http);

    await client.fetchRunEvents("run-1");

    expect(fetcher.mock.calls[0][0]).toBe(
      `http://api.test/runs/run-1/events?limit=${EVENTS_PAGE_LIMIT_DEFAULT}`,
    );
  });

  it("refuse une page hors contrat au lieu d’en rendre une partie", async () => {
    const fetcher = vi.fn(async () => json(page([streamEvent({ occurred_at: 42 })])));
    const http = new WorkspaceHttpClient({ baseUrl: "http://api.test", fetcher });
    const client = new EventsApiClient(http);

    await expect(client.fetchRunEvents("run-1")).rejects.toMatchObject({
      name: "WorkspaceApiError",
      kind: "invalid_response",
    });
  });

  it("refuse une page dont le curseur n’est pas un entier", async () => {
    const fetcher = vi.fn(async () => json(page([], { next_cursor: "12" })));
    const http = new WorkspaceHttpClient({ baseUrl: "http://api.test", fetcher });
    const client = new EventsApiClient(http);

    await expect(client.fetchRunEvents("run-1")).rejects.toBeInstanceOf(WorkspaceApiError);
  });
});

// --- Helpers purs -------------------------------------------------------------

describe("helpers de chronologie", () => {
  it("fusionne sans jamais dupliquer un identifiant déjà présent", () => {
    const first = streamEvent({ id: "a", sequence: 1, occurred_at: "2026-09-12T10:00:00Z" });
    const second = streamEvent({ id: "b", sequence: 2, occurred_at: "2026-09-12T10:00:05Z" });

    const merged = mergeStreamEvents([first, second] as never, [second, first] as never);

    expect(merged.map((event) => event.id)).toEqual(["a", "b"]);
  });

  it("ordonne la chronologie par date puis par séquence", () => {
    const late = streamEvent({ id: "c", sequence: 9, occurred_at: "2026-09-12T10:00:09Z" });
    const early = streamEvent({ id: "a", sequence: 1, occurred_at: "2026-09-12T10:00:00Z" });
    const sameInstant = streamEvent({ id: "b", sequence: 2, occurred_at: "2026-09-12T10:00:00Z" });

    const merged = mergeStreamEvents([] as never, [late, sameInstant, early] as never);

    expect(merged.map((event) => event.id)).toEqual(["a", "b", "c"]);
  });

  it("borne le délai de reconnexion exponentiel", () => {
    expect(streamReconnectDelay(1)).toBe(STREAM_RECONNECT_BASE_MS);
    expect(streamReconnectDelay(2)).toBe(STREAM_RECONNECT_BASE_MS * 2);
    expect(streamReconnectDelay(3)).toBe(STREAM_RECONNECT_BASE_MS * 4);
    expect(streamReconnectDelay(99)).toBe(STREAM_RECONNECT_MAX_MS);
  });

  it("déduit le mode du Studio sans jamais inventer un direct", () => {
    expect(studioMode({ connection: "connected", terminal: false })).toBe("live");
    expect(studioMode({ connection: "polling", terminal: false })).toBe("interim");
    expect(studioMode({ connection: "connected", terminal: true })).toBe("replay");
    expect(studioMode({ connection: "offline", terminal: true })).toBe("replay");
    expect(studioMode({ connection: "offline", terminal: false })).toBe("unknown");
    expect(studioMode({ connection: "reconnecting", terminal: false })).toBe("unknown");
  });

  it("donne un libellé textuel à chaque mode et à chaque état de connexion", () => {
    expect(describeStudioMode("live").label).toBe("Direct");
    expect(describeStudioMode("interim").label).toBe("Aperçu intermédiaire");
    expect(describeStudioMode("replay").label).toBe("Replay");
    expect(describeStudioMode("unknown").label).toBe("Hors ligne / inconnu");
    for (const mode of ["live", "interim", "replay", "unknown"] as const) {
      expect(describeStudioMode(mode).description.length).toBeGreaterThan(0);
    }
    expect(describeConnectionState("connected", 0).label).toBe("Flux connecté");
    expect(describeConnectionState("reconnecting", 0).label).toBe("Connexion au flux…");
    expect(describeConnectionState("reconnecting", 2).label).toBe("Reconnexion…");
    expect(describeConnectionState("polling", 3).label).toBe("Interrogation périodique");
    expect(describeConnectionState("offline", 3).label).toBe("Hors ligne");
  });

  it("reconnaît les événements terminaux d’une tentative", () => {
    expect(isRunTerminalEvent(streamEvent({ type: "task.completed" }) as never)).toBe(true);
    expect(isRunTerminalEvent(streamEvent({ type: "task.failed" }) as never)).toBe(true);
    expect(isRunTerminalEvent(streamEvent({ type: "task.cancelled" }) as never)).toBe(true);
    expect(isRunTerminalEvent(streamEvent({ type: "task.interrupted" }) as never)).toBe(true);
    expect(isRunTerminalEvent(streamEvent({ type: "task.progress" }) as never)).toBe(false);
  });

  it("retient la dernière capture de la session et ignore les autres médias", () => {
    const screenshot = streamEvent({
      id: "s1",
      sequence: 4,
      occurred_at: "2026-09-12T10:00:04Z",
      payload: {
        artifact_id: "art-1",
        content_type: "image/png",
        size_bytes: 2048,
        sha256: "a".repeat(64),
        stream_kind: "screenshot",
      },
    });
    const newer = streamEvent({
      id: "s2",
      sequence: 8,
      occurred_at: "2026-09-12T10:00:08Z",
      payload: {
        artifact_id: "art-2",
        content_type: "image/png",
        size_bytes: 4096,
        sha256: "b".repeat(64),
        stream_kind: "screenshot",
      },
    });
    const video = streamEvent({
      id: "v1",
      sequence: 9,
      occurred_at: "2026-09-12T10:00:09Z",
      payload: { artifact_id: "art-3", content_type: "video/webm", stream_kind: "video" },
    });
    const broken = streamEvent({
      id: "x1",
      sequence: 10,
      occurred_at: "2026-09-12T10:00:10Z",
      payload: { stream_kind: "screenshot" },
    });

    const reference = lastMediaReference([screenshot, newer, video, broken] as never, "screenshot");

    expect(reference?.artifactId).toBe("art-2");
    expect(reference?.contentType).toBe("image/png");
    expect(reference?.sizeBytes).toBe(4096);
    expect(reference?.occurredAt).toBe("2026-09-12T10:00:08Z");
    expect(lastMediaReference([] as never, "screenshot")).toBeNull();
  });

  it("n’autorise l’aperçu que pour les types listés par la spécification", () => {
    expect(classifyArtifactPreview("image/png")).toBe("image");
    expect(classifyArtifactPreview("image/jpeg")).toBe("image");
    expect(classifyArtifactPreview("image/webp")).toBe("image");
    expect(classifyArtifactPreview("image/gif")).toBe("image");
    expect(classifyArtifactPreview("video/webm")).toBe("video");
    expect(classifyArtifactPreview("video/mp4")).toBe("video");
    expect(classifyArtifactPreview("image/svg+xml")).toBe("download");
    expect(classifyArtifactPreview("text/html")).toBe("download");
    expect(classifyArtifactPreview("application/zip")).toBe("download");
    expect(classifyArtifactPreview("")).toBe("download");
    expect(classifyArtifactPreview("IMAGE/PNG; charset=binary")).toBe("image");
  });
});

// --- Flux SSE -----------------------------------------------------------------

describe("EventsApiClient.openRunStream", () => {
  it("ouvre le flux avec les credentials, le curseur, et passe à connecté", () => {
    const { client, handlers, states } = harness();

    const subscription = client.openRunStream("run 1", 7, handlers);
    expect(subscription.state).toBe("reconnecting");
    const source = latestSource();
    expect(source.url).toBe("http://api.test/streams/runs/run%201?after_seq=7");
    expect(source.init.withCredentials).toBe(true);

    source.open();

    expect(subscription.state).toBe("connected");
    expect(states).toEqual(["connected"]);
    subscription.close();
  });

  it("transmet les événements reçus et avance le curseur", () => {
    const { client, handlers, events } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    const source = latestSource();
    source.open();

    source.deliver(streamEvent({ id: "a", sequence: 1 }));
    source.deliver(streamEvent({ id: "b", sequence: 2 }));

    expect(events.flat().map((event) => (event as { id: string }).id)).toEqual(["a", "b"]);
    expect(subscription.cursor).toBe(2);
    subscription.close();
  });

  it("ne rejoue jamais un événement déjà vu après une reconnexion", async () => {
    const { client, handlers, events, timers } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    const first = latestSource();
    first.open();
    first.deliver(streamEvent({ id: "a", sequence: 1 }));
    first.deliver(streamEvent({ id: "b", sequence: 2 }));

    first.fail();
    expect(subscription.state).toBe("reconnecting");
    expect(timers.delays).toEqual([STREAM_RECONNECT_BASE_MS]);
    await timers.fire();

    const second = latestSource();
    expect(second).not.toBe(first);
    expect(second.url).toBe("http://api.test/streams/runs/run-1?after_seq=2");
    second.open();
    second.deliver(streamEvent({ id: "b", sequence: 2 }));
    second.deliver(streamEvent({ id: "c", sequence: 3 }));

    expect(events.flat().map((event) => (event as { id: string }).id)).toEqual(["a", "b", "c"]);
    expect(subscription.cursor).toBe(3);
    subscription.close();
  });

  it("déduplique aussi les événements sans séquence, par identifiant", () => {
    const { client, handlers, events } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    const source = latestSource();
    source.open();

    source.deliver(streamEvent({ id: "z", sequence: null }));
    source.deliver(streamEvent({ id: "z", sequence: null }));

    expect(events.flat()).toHaveLength(1);
    expect(subscription.cursor).toBeNull();
    subscription.close();
  });

  it("ignore une trame illisible sans rompre la connexion", () => {
    const { client, handlers, events } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    const source = latestSource();
    source.open();

    source.raw("{ceci n’est pas du JSON");
    source.deliver({ id: "incomplet" });
    source.deliver(streamEvent({ id: "a", sequence: 1 }));

    expect(subscription.malformed).toBe(2);
    expect(subscription.state).toBe("connected");
    expect(events.flat().map((event) => (event as { id: string }).id)).toEqual(["a"]);
    subscription.close();
  });

  it("traite la rotation du flux comme une reprise immédiate, sans compter d’échec", async () => {
    const { client, handlers, events, timers } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    const first = latestSource();
    first.open();
    first.deliver(streamEvent({ id: "a", sequence: 5 }));
    first.deliver(streamEvent({
      id: "rot",
      sequence: null,
      type: "acp.stream.rotate",
      payload: { cursor: 5 },
    }));

    expect(events.flat().map((event) => (event as { id: string }).id)).toEqual(["a"]);

    first.fail();

    expect(subscription.failures).toBe(0);
    expect(timers.size).toBe(0);
    const second = latestSource();
    expect(second.url).toBe("http://api.test/streams/runs/run-1?after_seq=5");
    expect(first.closed).toBe(true);
    subscription.close();
  });

  it("adopte le curseur d’une rotation reçue sous son propre nom SSE, sans compter d’échec", () => {
    const { client, handlers, events, timers } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    const first = latestSource();
    first.open();
    first.deliver(streamEvent({ id: "a", sequence: 5 }));

    // Trame réellement émise par l’API (`streams.py`) : `event: acp.stream.rotate`, avec un
    // payload nu `{cursor, reason}` qui n’est pas un `StreamEvent`.
    first.rotate({ cursor: 5, reason: "max_seconds" });
    first.fail();

    expect(events.flat().map((event) => (event as { id: string }).id)).toEqual(["a"]);
    expect(subscription.failures).toBe(0);
    expect(subscription.malformed).toBe(0);
    expect(timers.size).toBe(0);
    expect(first.closed).toBe(true);
    expect(latestSource().url).toBe("http://api.test/streams/runs/run-1?after_seq=5");
    subscription.close();
  });

  it("compte une trame de rotation illisible mais reprend quand même au curseur courant", () => {
    const { client, handlers, timers } = harness();
    const subscription = client.openRunStream("run-1", 4, handlers);
    const first = latestSource();
    first.open();

    first.emit("acp.stream.rotate", "{ceci n’est pas du JSON");
    first.fail();

    expect(subscription.malformed).toBe(1);
    expect(subscription.failures).toBe(0);
    expect(timers.size).toBe(0);
    expect(latestSource().url).toBe("http://api.test/streams/runs/run-1?after_seq=4");
    subscription.close();
  });

  it("ne compte pas d’échec quand le serveur annonce une fermeture propre", () => {
    const { client, handlers, timers } = harness();
    const subscription = client.openRunStream("run-1", 7, handlers);
    const first = latestSource();
    first.open();

    first.serverClosed("shutdown");
    first.fail();

    expect(subscription.failures).toBe(0);
    expect(subscription.malformed).toBe(0);
    expect(timers.size).toBe(0);
    expect(latestSource()).not.toBe(first);
    subscription.close();
  });

  it("bascule en interrogation quand le serveur ferme le flux pour révocation d’accès", async () => {
    const fetcher = vi.fn(async () => json(page([])));
    const { client, handlers, states, timers } = harness({ fetcher: fetcher as never });
    const subscription = client.openRunStream("run-1", 3, handlers);
    const first = latestSource();
    first.open();

    first.serverClosed("unauthorized");
    first.fail();
    await flush();

    // Rouvrir en boucle un flux dont l’accès est révoqué mentirait : l’interrogation fait
    // apparaître le vrai refus HTTP au lieu d’un direct fantôme.
    expect(subscription.failures).toBe(0);
    expect(subscription.state).toBe("polling");
    expect(states).toEqual(["connected", "polling"]);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(fetcher.mock.calls[0][0]).toBe(
      `http://api.test/runs/run-1/events?after_seq=3&limit=${EVENTS_PAGE_LIMIT_DEFAULT}`,
    );
    expect(timers.delays).toEqual([STREAM_POLL_INTERVAL_MS]);
    subscription.close();
  });

  it("bascule en interrogation après trois échecs consécutifs et ne rejoue rien", async () => {
    const fetcher = vi.fn(async () => json(page([
      streamEvent({ id: "a", sequence: 1 }),
      streamEvent({ id: "b", sequence: 2 }),
    ])));
    const { client, handlers, events, states, timers } = harness({ fetcher: fetcher as never });
    const subscription = client.openRunStream("run-1", null, handlers);

    latestSource().open();
    latestSource().deliver(streamEvent({ id: "a", sequence: 1 }));
    latestSource().fail();
    await timers.fire();
    latestSource().fail();
    await timers.fire();
    latestSource().fail();
    await flush();

    expect(subscription.failures).toBe(STREAM_FAILURES_BEFORE_POLLING);
    expect(subscription.state).toBe("polling");
    expect(states).toEqual(["connected", "reconnecting", "polling"]);
    expect(fetcher.mock.calls[0][0]).toBe(
      `http://api.test/runs/run-1/events?after_seq=1&limit=${EVENTS_PAGE_LIMIT_DEFAULT}`,
    );
    expect(events.flat().map((event) => (event as { id: string }).id)).toEqual(["a", "b"]);
    expect(timers.delays).toEqual([STREAM_POLL_INTERVAL_MS]);
    subscription.close();
  });

  it("passe hors ligne quand l’interrogation échoue, puis revient quand elle répond", async () => {
    const responses = [
      () => Promise.reject(new TypeError("réseau indisponible")),
      () => Promise.resolve(json(page([streamEvent({ id: "a", sequence: 1 })]))),
    ];
    const fetcher = vi.fn(async () => (responses.shift() ?? (() => Promise.resolve(json(page([])))))());
    const { client, handlers, states, timers } = harness({ fetcher: fetcher as never });
    const subscription = client.openRunStream("run-1", null, handlers);

    for (let attempt = 0; attempt < STREAM_FAILURES_BEFORE_POLLING; attempt += 1) {
      latestSource().fail();
      if (timers.size > 0) await timers.fire();
    }
    await flush();

    expect(subscription.state).toBe("offline");
    await timers.fire();
    expect(subscription.state).toBe("polling");
    // L’état « interrogation » n’est annoncé qu’après une lecture réellement réussie.
    expect(states).toEqual(["offline", "polling"]);
    subscription.close();
  });

  it("retente le direct après quelques interrogations réussies", async () => {
    const fetcher = vi.fn(async () => json(page([])));
    const { client, handlers, timers } = harness({ fetcher: fetcher as never });
    const subscription = client.openRunStream("run-1", null, handlers);
    const opened = FakeEventSource.instances.length;

    for (let attempt = 0; attempt < STREAM_FAILURES_BEFORE_POLLING; attempt += 1) {
      latestSource().fail();
      if (timers.size > 0) await timers.fire();
    }
    await flush();
    expect(subscription.state).toBe("polling");

    // La première interrogation a déjà eu lieu : les suivantes restent en interrogation
    // jusqu’à la N-ième, qui retente le direct.
    for (let poll = 2; poll < STREAM_POLLS_BEFORE_LIVE_RETRY; poll += 1) {
      await timers.fire();
      expect(subscription.state).toBe("polling");
    }
    await timers.fire();

    expect(FakeEventSource.instances.length).toBe(opened + STREAM_FAILURES_BEFORE_POLLING);
    latestSource().open();
    expect(subscription.state).toBe("connected");
    expect(subscription.failures).toBe(0);
    subscription.close();
  });

  it("interroge immédiatement quand le navigateur n’expose pas EventSource", async () => {
    const fetcher = vi.fn(async () => json(page([])));
    const http = new WorkspaceHttpClient({ baseUrl: "http://api.test", fetcher: fetcher as never });
    const timers = new ManualTimers();
    const client = new EventsApiClient(http, { eventSource: () => null, timers: timers.api });

    const subscription = client.openRunStream("run-1", 3, { onEvents: () => {} });
    await flush();

    expect(subscription.state).toBe("polling");
    expect(fetcher).toHaveBeenCalledTimes(1);
    subscription.close();
  });

  it("ferme tout et n’émet plus rien après close()", async () => {
    const { client, handlers, events, timers } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    const source = latestSource();
    source.open();

    subscription.close();

    expect(source.closed).toBe(true);
    expect(subscription.closed).toBe(true);
    expect(timers.size).toBe(0);
    source.deliver(streamEvent({ id: "a", sequence: 1 }));
    source.fail();
    await flush();
    expect(events).toHaveLength(0);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("retryNow() relance le direct depuis le curseur courant", async () => {
    const { client, handlers, timers } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    latestSource().open();
    latestSource().deliver(streamEvent({ id: "a", sequence: 4 }));
    latestSource().fail();
    expect(timers.size).toBe(1);

    subscription.retryNow();

    expect(timers.size).toBe(0);
    expect(subscription.failures).toBe(0);
    expect(latestSource().url).toBe("http://api.test/streams/runs/run-1?after_seq=4");
    subscription.close();
  });

  it("signale une erreur d’interrogation à l’appelant sans jeter", async () => {
    const fetcher = vi.fn(async () => json({ detail: "Accès refusé." }, 403));
    const errors: WorkspaceApiError[] = [];
    const { client, timers } = harness({ fetcher: fetcher as never });
    const subscription = client.openRunStream("run-1", null, {
      onEvents: () => {},
      onError: (error) => errors.push(error),
    });

    for (let attempt = 0; attempt < STREAM_FAILURES_BEFORE_POLLING; attempt += 1) {
      latestSource().fail();
      if (timers.size > 0) await timers.fire();
    }
    await flush();

    expect(errors).toHaveLength(1);
    expect(errors[0].kind).toBe("forbidden");
    expect(subscription.state).toBe("offline");
    subscription.close();
  });
});

// --- Conformité aux trames réellement émises par l’API --------------------------

/**
 * Les tests ci-dessus simulent les trames ; ceux-ci **lisent la source du serveur**
 * (`apps/api/src/acp_api/streams.py`) et rejouent ses octets à travers un découpage SSE
 * conforme au navigateur.
 *
 * Raison d’être : un `EventSource` ne remet une trame **nommée** qu’aux écouteurs
 * enregistrés sous ce nom exact. Un client qui aiguillerait la rotation sur
 * `StreamEvent.type` — ou des noms qui divergeraient entre le serveur et le client —
 * ne casserait aucun test de simulation, mais compterait chaque rotation propre comme
 * une panne de connexion en production (bandeau « Reconnexion… » toutes les 15 minutes,
 * curseur annoncé jamais adopté). Le garde-fou vit donc ici, lié à la source servante.
 */
const streamsSource = readFileSync(
  new URL("../../api/src/acp_api/streams.py", import.meta.url),
  "utf8",
);

/** Valeur d’une constante de chaîne de premier niveau de `streams.py`. */
function serverConstant(name: string): string {
  const match = new RegExp(`^${name} = "([^"]*)"`, "m").exec(streamsSource);
  if (!match) throw new Error(`constante introuvable dans streams.py : ${name}`);
  return match[1];
}

/** `_KEEPALIVE_FRAME` : un commentaire SSE, jamais une donnée. */
const SERVER_KEEPALIVE_FRAME = ": ping\n\n";

/** `_frame_event` : `id:`, nom `acp.event`, et un `StreamEvent` complet en `data`. */
function serverEventFrame(cursor: number, event: unknown): string {
  const name = serverConstant("SSE_EVENT_NAME");
  return `id: ${cursor}\nevent: ${name}\ndata: ${JSON.stringify(event)}\n\n`;
}

/** `_frame_rotate` : payload **nu** `{cursor, reason}`, qui n’est pas un `StreamEvent`. */
function serverRotateFrame(cursor: number): string {
  const name = serverConstant("SSE_ROTATE_EVENT");
  const data = JSON.stringify({ cursor, reason: "max_seconds" });
  return `id: ${cursor}\nevent: ${name}\ndata: ${data}\n\n`;
}

/** `_frame_closed` : fin décidée par le serveur, sans `id:`, avec sa raison. */
function serverClosedFrame(reason: string): string {
  const name = serverConstant("SSE_CLOSED_EVENT");
  return `event: ${name}\ndata: ${JSON.stringify({ reason })}\n\n`;
}

/**
 * Découpe des trames SSE littérales et les dispatche comme un `EventSource` : une trame
 * nommée n’atteint que les écouteurs de ce nom, un commentaire n’atteint personne, et une
 * trame sans champ `data` ne déclenche aucun événement.
 */
function feedServerFrames(source: FakeEventSource, raw: string): void {
  for (const frame of raw.split("\n\n")) {
    if (!frame) continue;
    let name = "message";
    const data: string[] = [];
    let hasData = false;
    for (const line of frame.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      const separator = line.indexOf(":");
      const field = separator < 0 ? line : line.slice(0, separator);
      const rawValue = separator < 0 ? "" : line.slice(separator + 1);
      const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
      if (field === "event") name = value;
      else if (field === "data") {
        data.push(value);
        hasData = true;
      }
    }
    if (!hasData) continue;
    source.emit(name, data.join("\n"));
  }
}

describe("conformité aux trames réellement émises par streams.py", () => {
  it("écoute exactement les noms de trames déclarés par le serveur", () => {
    expect(STREAM_EVENT_NAME).toBe(serverConstant("SSE_EVENT_NAME"));
    expect(STREAM_ROTATE_EVENT_TYPE).toBe(serverConstant("SSE_ROTATE_EVENT"));
    expect(STREAM_CLOSED_EVENT_TYPE).toBe(serverConstant("SSE_CLOSED_EVENT"));
  });

  it("rejoue la séquence réelle du serveur : keep-alive, événement, rotation", () => {
    const { client, handlers, events, timers } = harness();
    const subscription = client.openRunStream("run-1", null, handlers);
    const first = latestSource();
    first.open();

    feedServerFrames(
      first,
      SERVER_KEEPALIVE_FRAME
        + serverEventFrame(7, streamEvent({ id: "a", sequence: 7 }))
        + serverRotateFrame(7),
    );
    // `run_event_stream` rend la main juste après la rotation : la connexion tombe.
    first.fail();

    expect(events.flat().map((event) => (event as { id: string }).id)).toEqual(["a"]);
    // Le commentaire de keep-alive n’est ni une donnée ni une trame illisible, et le
    // payload nu de rotation ne doit pas être compté comme un `StreamEvent` invalide.
    expect(subscription.malformed).toBe(0);
    // Une rotation est une fin **attendue** : ni échec, ni délai d’attente, ni bandeau
    // « Reconnexion… » — la reprise est immédiate, au curseur annoncé par le serveur.
    expect(subscription.failures).toBe(0);
    expect(subscription.state).toBe("connected");
    expect(timers.size).toBe(0);
    expect(first.closed).toBe(true);
    expect(latestSource()).not.toBe(first);
    expect(latestSource().url).toBe("http://api.test/streams/runs/run-1?after_seq=7");
    subscription.close();
  });

  it("bascule en interrogation sur la trame de fermeture réelle d’un accès révoqué", async () => {
    const fetcher = vi.fn(async () => json(page([])));
    const { client, handlers, states, timers } = harness({ fetcher: fetcher as never });
    const subscription = client.openRunStream("run-1", 2, handlers);
    const first = latestSource();
    first.open();

    feedServerFrames(first, serverClosedFrame("unauthorized"));
    first.fail();
    await flush();

    expect(subscription.failures).toBe(0);
    expect(subscription.malformed).toBe(0);
    expect(states).toEqual(["connected", "polling"]);
    // Rouvrir en boucle un flux dont l’accès est révoqué annoncerait un direct fantôme.
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(fetcher.mock.calls[0][0]).toBe(
      `http://api.test/runs/run-1/events?after_seq=2&limit=${EVENTS_PAGE_LIMIT_DEFAULT}`,
    );
    expect(timers.delays).toEqual([STREAM_POLL_INTERVAL_MS]);
    subscription.close();
  });
});
