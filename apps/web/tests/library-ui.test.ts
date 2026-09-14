/**
 * Tests de `library-ui.ts` : fonctions pures (onglet mémorisé dans l’URL, filtrage) et
 * chemin de rendu sur un DOM minimal simulé, sans dépendance ajoutée.
 *
 * Le faux DOM **interdit** `innerHTML` : toute tentative d’insertion HTML fait échouer
 * le test, ce qui verrouille la règle « un livrable est une donnée non fiable, insérée
 * par `textContent` uniquement ».
 */

import { describe, expect, it, vi } from "vitest";

// --- DOM minimal --------------------------------------------------------------

type Handler = (event: unknown) => void;

class FakeElement {
  readonly tagName: string;
  className = "";
  textContent = "";
  id = "";
  htmlFor = "";
  type = "";
  value = "";
  placeholder = "";
  href = "";
  src = "";
  crossOrigin = "";
  alt = "";
  download = "";
  target = "";
  rel = "";
  controls = false;
  preload = "";
  tabIndex = 0;
  disabled = false;
  hidden = false;
  readonly children: FakeElement[] = [];
  readonly attributes: Record<string, string> = {};
  readonly dataset: Record<string, string> = {};
  readonly listeners: Record<string, Handler[]> = {};

  constructor(tagName: string) {
    this.tagName = tagName;
  }

  /** Un livrable est une donnée non fiable : ce module ne doit jamais écrire de HTML. */
  set innerHTML(_value: string) {
    throw new Error("innerHTML interdit dans la bibliothèque de livrables");
  }

  append(...nodes: FakeElement[]): void {
    this.children.push(...nodes);
  }

  replaceChildren(...nodes: FakeElement[]): void {
    this.children.length = 0;
    this.children.push(...nodes);
  }

  setAttribute(name: string, value: string): void {
    this.attributes[name] = value;
  }

  getAttribute(name: string): string | null {
    return this.attributes[name] ?? null;
  }

  removeAttribute(name: string): void {
    delete this.attributes[name];
  }

  addEventListener(type: string, handler: Handler): void {
    (this.listeners[type] ??= []).push(handler);
  }

  querySelector(selector: string): FakeElement | null {
    const match = /^\[data-([a-z-]+)='([^']+)'\]$/.exec(selector);
    if (!match) throw new Error(`Sélecteur non simulé : ${selector}`);
    const [, key, value] = match;
    for (const node of walk(this)) {
      if (node.dataset[key] === value) return node;
    }
    return null;
  }
}

function walk(node: FakeElement): FakeElement[] {
  return node.children.flatMap((child) => [child, ...walk(child)]);
}

function textOf(node: FakeElement): string {
  return [node.textContent, ...node.children.map(textOf)].filter(Boolean).join(" ");
}

function findAll(root: FakeElement, predicate: (node: FakeElement) => boolean): FakeElement[] {
  return walk(root).filter(predicate);
}

function byTag(root: FakeElement, tagName: string): FakeElement[] {
  return findAll(root, (node) => node.tagName === tagName);
}

function byClass(root: FakeElement, className: string): FakeElement[] {
  return findAll(root, (node) => node.className.split(" ").includes(className));
}

function buttonLabelled(root: FakeElement, label: string): FakeElement {
  const node = byTag(root, "button").find((candidate) => textOf(candidate).includes(label));
  if (!node) throw new Error(`Bouton introuvable : ${label}`);
  return node;
}

function fire(node: FakeElement, type: string, event: unknown = { preventDefault() {} }): void {
  for (const handler of node.listeners[type] ?? []) handler(event);
}

async function flush(rounds = 10): Promise<void> {
  for (let index = 0; index < rounds; index += 1) {
    if (vi.isFakeTimers()) await vi.advanceTimersByTimeAsync(0);
    else await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

interface FakeLocation {
  pathname: string;
  search: string;
  hash: string;
  href: string;
  origin: string;
}

function installBrowser(search: string): { location: FakeLocation; replaceCalls: string[] } {
  const location: FakeLocation = {
    pathname: "/library",
    search,
    hash: "",
    href: `https://app.example.test/library${search}`,
    origin: "https://app.example.test",
  };
  const replaceCalls: string[] = [];
  const history = {
    replaceState(_state: unknown, _title: string, url: string) {
      replaceCalls.push(url);
      const queryStart = url.indexOf("?");
      location.search = queryStart === -1 ? "" : url.slice(queryStart);
      location.href = `${location.origin}${location.pathname}${location.search}${location.hash}`;
    },
  };
  Object.defineProperty(globalThis, "document", {
    value: { createElement: (tag: string) => new FakeElement(tag) },
    configurable: true,
    writable: true,
  });
  Object.defineProperty(globalThis, "location", { value: location, configurable: true, writable: true });
  Object.defineProperty(globalThis, "window", {
    value: { location }, configurable: true, writable: true,
  });
  Object.defineProperty(globalThis, "history", { value: history, configurable: true, writable: true });
  return { location, replaceCalls };
}

// --- Réponses simulées ---------------------------------------------------------

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function artifact(overrides: Record<string, unknown> = {}) {
  return {
    id: "artifact-1",
    project_id: "project-a",
    task_run_id: "run-1",
    kind: "screenshot",
    stream_kind: "screenshot",
    original_name: "accueil.png",
    content_type: "image/png",
    size_bytes: 2048,
    checksum: "ab12".repeat(16),
    source: "playwright",
    has_content: true,
    created_at: "2026-09-12T10:00:00Z",
    ...overrides,
  };
}

const OVERVIEW = {
  organizations: [],
  workspaces: [],
  departments: [],
  projects: [{
    id: "project-a",
    workspace_id: "workspace-1",
    department_id: null,
    name: "Projet A",
    project_type: "generic",
    description: "",
    status: "active",
  }],
  teams: [],
  team_members: [],
  agents: [],
  tasks: [],
};

function missionSummary(overrides: Record<string, unknown> = {}) {
  return {
    id: "mission-1",
    project_id: "project-a",
    title: "Recette du portail",
    objective: "Vérifier",
    expected_outcome: "Vert",
    acceptance_criteria: [],
    duration_seconds: 600,
    priority: 3,
    status: "succeeded",
    current_run: {
      id: "run-1",
      mission_id: "mission-1",
      attempt_number: 2,
      fencing_token: 4,
      status: "succeeded",
      stop_requested: false,
      technical_validation: { status: "passed", summary: "", checked_at: null },
      user_acceptance: { status: "pending", comment: "", decided_by: null, decided_at: null },
      evidence: [],
      started_at: null,
      finished_at: null,
      created_at: null,
    },
    created_at: "2026-09-12T09:00:00Z",
    ...overrides,
  };
}

type Route = (url: string, init: RequestInit | undefined) => Response | Promise<Response>;

const DEFAULT_ROUTES: [RegExp, Route][] = [
  [/\/overview$/, () => json(OVERVIEW)],
  [/\/missions$/, () => json([missionSummary()])],
  [/\/artifacts\?/, () => json({ items: [artifact()], next_cursor: null })],
];

async function mountLibrary(
  routes: [RegExp, Route][] = DEFAULT_ROUTES,
  options: { search?: string } = {},
): Promise<{
  container: FakeElement;
  fetchMock: ReturnType<typeof vi.fn>;
  location: FakeLocation;
  replaceCalls: string[];
  module: typeof import("../src/library-ui");
  remount: () => Promise<FakeElement>;
}> {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    for (const [pattern, route] of routes) {
      if (pattern.test(url)) return route(url, init);
    }
    return json({ detail: `Route non simulée : ${url}` }, 404);
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  const browser = installBrowser(options.search ?? "");
  vi.resetModules();
  const { WorkspaceHttpClient } = await import("../src/workspace-api");
  const shellHttp = new WorkspaceHttpClient();
  shellHttp.setCsrfToken("csrf-shell");
  const module = await import("../src/library-ui");
  const container = new FakeElement("div");
  module.renderLibrary(container as unknown as HTMLElement, shellHttp);
  await flush();
  return {
    container,
    fetchMock,
    location: browser.location,
    replaceCalls: browser.replaceCalls,
    module,
    remount: async () => {
      const target = new FakeElement("div");
      module.renderLibrary(target as unknown as HTMLElement, shellHttp);
      await flush();
      return target;
    },
  };
}

function calledUrls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map((call) => String(call[0]));
}

// --- Fonctions pures ------------------------------------------------------------

describe("onglet mémorisé dans l’URL", () => {
  it("lit l’onglet demandé et retombe sur Skills", async () => {
    const { libraryTabFromSearch } = await import("../src/library-ui");
    expect(libraryTabFromSearch("")).toBe("skills");
    expect(libraryTabFromSearch("?onglet=livrables")).toBe("deliverables");
    expect(libraryTabFromSearch("?a=1&onglet=LIVRABLES")).toBe("deliverables");
    expect(libraryTabFromSearch("?onglet=skills")).toBe("skills");
    expect(libraryTabFromSearch("?onglet=inconnu")).toBe("skills");
  });

  it("distingue « paramètre absent » de « paramètre égal à skills »", async () => {
    const { libraryTabInSearch } = await import("../src/library-ui");
    expect(libraryTabInSearch("?a=1")).toBeNull();
    expect(libraryTabInSearch("?onglet=skills")).toBe("skills");
    expect(libraryTabInSearch("?onglet=livrables")).toBe("deliverables");
  });

  it("écrit l’onglet sans toucher aux autres paramètres et nettoie la valeur par défaut", async () => {
    const { librarySearchWithTab } = await import("../src/library-ui");
    expect(librarySearchWithTab("?projet=a", "deliverables")).toBe("?projet=a&onglet=livrables");
    expect(librarySearchWithTab("?projet=a&onglet=livrables", "skills")).toBe("?projet=a");
    expect(librarySearchWithTab("", "deliverables")).toBe("?onglet=livrables");
    expect(librarySearchWithTab("?onglet=livrables", "skills")).toBe("");
  });
});

describe("filterArtifacts", () => {
  it("cherche dans le nom, le type, la provenance et l’empreinte, sans casse ni accent", async () => {
    const { filterArtifacts } = await import("../src/library-ui");
    const items = [
      artifact({ id: "a-1", original_name: "Résumé final.pdf", stream_kind: "report" }),
      artifact({ id: "a-2", original_name: "trace.zip", stream_kind: "trace", source: "worker" }),
    ] as never;

    expect(filterArtifacts(items, "")).toHaveLength(2);
    expect(filterArtifacts(items, "resume").map((item) => item.id)).toEqual(["a-1"]);
    expect(filterArtifacts(items, "TRACE").map((item) => item.id)).toEqual(["a-2"]);
    expect(filterArtifacts(items, "worker zip").map((item) => item.id)).toEqual(["a-2"]);
    expect(filterArtifacts(items, "ab12ab12")).toHaveLength(2);
    expect(filterArtifacts(items, "introuvable")).toHaveLength(0);
  });
});

describe("options de filtre", () => {
  it("liste les projets connus puis les projets seulement vus dans les livrables", async () => {
    const { projectOptions } = await import("../src/library-ui");
    const options = projectOptions(
      [{ id: "project-a", name: "Projet A" }],
      [artifact(), artifact({ id: "x", project_id: "project-orphelin" })] as never,
    );
    expect(options[0]).toEqual({ id: "project-a", label: "Projet A" });
    expect(options[1].id).toBe("project-orphelin");
    expect(options[1].label).toContain("project-o");
  });

  it("nomme les tentatives par mission et conserve celles qui ne sont pas la tentative courante", async () => {
    const { runOptions } = await import("../src/library-ui");
    const options = runOptions(
      [missionSummary()] as never,
      [artifact(), artifact({ id: "x", task_run_id: "run-ancien" })] as never,
      "",
    );
    expect(options[0].id).toBe("run-1");
    expect(options[0].label).toContain("Recette du portail");
    expect(options[0].label).toContain("2");
    expect(options.map((option) => option.id)).toContain("run-ancien");
  });

  it("restreint les tentatives au projet sélectionné", async () => {
    const { runOptions } = await import("../src/library-ui");
    const options = runOptions(
      [missionSummary(), missionSummary({ id: "mission-2", project_id: "project-b", title: "Autre" })] as never,
      [] as never,
      "project-a",
    );
    expect(options).toHaveLength(1);
    expect(options[0].label).toContain("Recette du portail");
  });
});

// --- Rendu -----------------------------------------------------------------------

describe("renderLibrary — onglets", () => {
  it("affiche deux onglets et ouvre Skills par défaut, sans lire les livrables", async () => {
    const { container, fetchMock } = await mountLibrary([
      [/\/skills\/search/, () => json({ installed: [], catalog: [] })],
      [/\/skills\/catalog/, () => json([])],
      [/\/overview$/, () => json(OVERVIEW)],
    ]);

    const tabs = findAll(container, (node) => node.getAttribute("role") === "tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Skills", "Livrables"]);
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(byClass(container, "skills-library")).toHaveLength(1);
    expect(calledUrls(fetchMock).some((url) => url.includes("/artifacts"))).toBe(false);
  });

  it("ouvre directement l’onglet Livrables sur un lien profond", async () => {
    const { container, fetchMock } = await mountLibrary(DEFAULT_ROUTES, { search: "?onglet=livrables" });

    const tabs = findAll(container, (node) => node.getAttribute("role") === "tab");
    expect(tabs[1].getAttribute("aria-selected")).toBe("true");
    expect(calledUrls(fetchMock).some((url) => url.includes("/artifacts?"))).toBe(true);
    expect(textOf(container)).toContain("accueil.png");
  });

  it("mémorise le changement d’onglet dans l’URL, sans y écrire autre chose", async () => {
    const routes: [RegExp, Route][] = [
      ...DEFAULT_ROUTES,
      [/\/skills\/search/, () => json({ installed: [], catalog: [] })],
      [/\/skills\/catalog/, () => json([])],
    ];
    const { container, location, replaceCalls } = await mountLibrary(routes, { search: "?projet=a" });

    fire(buttonLabelled(container, "Livrables"), "click");
    await flush();
    expect(location.search).toBe("?projet=a&onglet=livrables");
    expect(replaceCalls[0]).toBe("/library?projet=a&onglet=livrables");

    fire(buttonLabelled(container, "Skills"), "click");
    await flush();
    expect(location.search).toBe("?projet=a");
  });
});

describe("renderLibrary — livrables", () => {
  it("affiche métadonnées, provenance, taille et empreinte par textContent", async () => {
    const { container } = await mountLibrary(DEFAULT_ROUTES, { search: "?onglet=livrables" });
    const text = textOf(container);

    expect(text).toContain("accueil.png");
    expect(text).toContain("Capture d’écran");
    expect(text).toContain("Playwright");
    expect(text).toContain("2 ko");
    expect(text).toContain("ab12ab12");
    expect(text).toContain("Projet A");
  });

  it("rend un nom hostile comme du texte, jamais comme du balisage", async () => {
    const hostile = "<img src=x onerror=alert(1)>.png";
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({ items: [artifact({ original_name: hostile })], next_cursor: null })],
    ], { search: "?onglet=livrables" });

    expect(textOf(container)).toContain(hostile);
    expect(byTag(container, "img")).toHaveLength(0);
  });

  it("avertit et refuse l’aperçu pour un HTML, un SVG ou une archive", async () => {
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({
        items: [
          artifact({ id: "a-html", original_name: "rapport.html", content_type: "text/html", stream_kind: "report" }),
          artifact({ id: "a-trace", original_name: "trace.zip", content_type: "application/zip", stream_kind: "trace" }),
        ],
        next_cursor: null,
      })],
    ], { search: "?onglet=livrables" });

    const text = textOf(container);
    expect(text).toContain("ne s’ouvre jamais dans la plateforme");
    expect(text).toContain("Playwright");
    expect(byClass(container, "library-warning").length).toBeGreaterThanOrEqual(2);
    expect(byTag(container, "img")).toHaveLength(0);
    expect(byTag(container, "video")).toHaveLength(0);
    expect(() => buttonLabelled(container, "Aperçu")).toThrow();
  });

  it("ouvre un aperçu d'image par lien signé, à la demande", async () => {
    const { container, fetchMock } = await mountLibrary([
      ...DEFAULT_ROUTES,
      [/\/artifacts\/artifact-1\/link/, () => json({
        artifact_id: "artifact-1",
        url: "https://api.example.test/artifacts/artifact-1/content?token=v1.a.b.c",
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      })],
    ], { search: "?onglet=livrables" });

    expect(byTag(container, "img")).toHaveLength(0);
    fire(buttonLabelled(container, "Aperçu"), "click");
    await flush();

    const images = byTag(container, "img");
    expect(images).toHaveLength(1);
    expect(images[0].src).toContain("token=v1.a.b.c");
    const linkCall = fetchMock.mock.calls.find((call) => String(call[0]).includes("/link"));
    expect(String(linkCall?.[0])).toContain("ttl_seconds=300");
    expect(((linkCall?.[1] as RequestInit).headers as Headers).get("X-CSRF-Token")).toBe("csrf-shell");
  });

  it("monte un visualiseur interactif seulement pour un GLB cohérent", async () => {
    const model = artifact({
      original_name: "atelier.glb",
      content_type: "model/gltf-binary",
      kind: "model-3d",
      stream_kind: "model",
    });
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({ items: [model], next_cursor: null })],
      [/\/artifacts\/artifact-1\/link/, () => json({
        artifact_id: "artifact-1",
        url: "https://preview.example.test/artifacts/artifact-1/content?token=v1.a.b.c",
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      })],
    ], { search: "?onglet=livrables" });

    fire(buttonLabelled(container, "Aperçu"), "click");
    await flush();

    const viewers = byTag(container, "model-viewer");
    expect(viewers).toHaveLength(1);
    expect(viewers[0].getAttribute("src")).toContain("preview.example.test");
    expect(viewers[0].getAttribute("camera-controls")).toBe("");
    expect(viewers[0].getAttribute("ar")).toBeNull();
    expect(textOf(container)).toContain("Aperçu 3D indisponible dans cet environnement");
  });

  it("bloque tout rendu 3D lorsque le lien reste sur l’origine de l’application", async () => {
    const model = artifact({
      original_name: "atelier.glb",
      content_type: "model/gltf-binary",
      kind: "model-3d",
      stream_kind: "model",
    });
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({ items: [model], next_cursor: null })],
      [/\/artifacts\/artifact-1\/link/, () => json({
        artifact_id: "artifact-1",
        url: "https://app.example.test/artifacts/artifact-1/content?token=v1.a.b.c",
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      })],
    ], { search: "?onglet=livrables" });

    fire(buttonLabelled(container, "Aperçu"), "click");
    await flush();

    expect(byTag(container, "model-viewer")).toHaveLength(0);
    expect(textOf(container)).toContain("Aperçu bloqué");
    expect(byTag(container, "a").some((node) => textOf(node).includes("Télécharger sans aperçu"))).toBe(true);
  });

  it("garde un fichier glTF multi-fichiers en téléchargement sans visualiseur", async () => {
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({
        items: [artifact({ original_name: "scene.gltf", content_type: "model/gltf+json" })],
        next_cursor: null,
      })],
    ], { search: "?onglet=livrables" });

    expect(byTag(container, "model-viewer")).toHaveLength(0);
    expect(textOf(container)).toContain("Seul un fichier .glb auto-contenu");
    expect(() => buttonLabelled(container, "Aperçu")).toThrow();
  });

  it("prépare un téléchargement explicite plutôt que de naviguer seul", async () => {
    const { container } = await mountLibrary([
      ...DEFAULT_ROUTES,
      [/\/artifacts\/artifact-1\/link/, () => json({
        artifact_id: "artifact-1",
        url: "https://api.example.test/artifacts/artifact-1/content?token=v1.a.b.c",
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      })],
    ], { search: "?onglet=livrables" });

    expect(byTag(container, "a")).toHaveLength(0);
    fire(buttonLabelled(container, "Préparer le téléchargement"), "click");
    await flush();

    const anchors = byTag(container, "a");
    expect(anchors).toHaveLength(1);
    expect(anchors[0].href).toContain("token=v1.a.b.c");
    expect(anchors[0].download).toBe("accueil.png");
    expect(anchors[0].rel).toContain("noopener");
  });

  it("ne réutilise jamais un lien de téléchargement comme lien d’aperçu", async () => {
    const mounted = await mountLibrary([
      ...DEFAULT_ROUTES,
      [/\/artifacts\/artifact-1\/link/, (url) => {
        const preview = url.includes("purpose=preview");
        return json({
          artifact_id: "artifact-1",
          url: preview
            ? "https://preview.example.test/artifacts/artifact-1/content?token=preview-token"
            : "https://api.example.test/artifacts/artifact-1/content?token=download-token",
          expires_at: new Date(Date.now() + 300_000).toISOString(),
        });
      }],
    ], { search: "?onglet=livrables" });

    fire(buttonLabelled(mounted.container, "Préparer le téléchargement"), "click");
    await flush();
    fire(buttonLabelled(mounted.container, "Aperçu"), "click");
    await flush();

    const linkCalls = calledUrls(mounted.fetchMock).filter((url) => url.includes("/link"));
    expect(linkCalls).toHaveLength(2);
    expect(linkCalls.some((url) => url.includes("purpose=preview"))).toBe(true);
    expect(byTag(mounted.container, "img")[0].src).toContain("preview-token");
    expect(byTag(mounted.container, "a")[0].href).toContain("download-token");
  });

  it("invalide automatiquement un aperçu expiré et le régénère sans relire les livrables", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-12T10:00:00Z"));
    let generation = 0;
    let mounted: Awaited<ReturnType<typeof mountLibrary>> | null = null;
    try {
      mounted = await mountLibrary([
        ...DEFAULT_ROUTES,
        [/\/artifacts\/artifact-1\/link/, () => {
          generation += 1;
          return json({
            artifact_id: "artifact-1",
            url: `https://preview.example.test/artifacts/artifact-1/content?token=preview-${generation}`,
            expires_at: new Date(Date.now() + 300_000).toISOString(),
          });
        }],
      ], { search: "?onglet=livrables" });

      fire(buttonLabelled(mounted.container, "Aperçu"), "click");
      await flush();
      expect(byTag(mounted.container, "img")[0].src).toContain("preview-1");
      const artifactReads = calledUrls(mounted.fetchMock).filter((url) => url.includes("/artifacts?")).length;
      expect(vi.getTimerCount()).toBe(1);

      // Un repaint intermédiaire remplace le timer existant, il ne l'empile pas.
      fire(byClass(mounted.container, "library-search")[0], "input");
      await flush();
      expect(vi.getTimerCount()).toBe(1);

      // Le timer atteint seul la marge de sécurité de 15 s, sans interaction ni reload.
      await vi.advanceTimersByTimeAsync(285_001);
      await flush();

      expect(byTag(mounted.container, "img")).toHaveLength(0);
      expect(textOf(mounted.container)).toContain("Le lien d’aperçu a expiré");
      expect(calledUrls(mounted.fetchMock).filter((url) => url.includes("/artifacts?"))).toHaveLength(artifactReads);
      expect(calledUrls(mounted.fetchMock).filter((url) => url.includes("/link"))).toHaveLength(1);

      fire(buttonLabelled(mounted.container, "Régénérer l’aperçu"), "click");
      await flush();

      expect(calledUrls(mounted.fetchMock).filter((url) => url.includes("/link"))).toHaveLength(2);
      expect(byTag(mounted.container, "img")[0].src).toContain("preview-2");
      expect(textOf(mounted.container)).not.toContain("Le lien d’aperçu a expiré");
      expect(vi.getTimerCount()).toBe(1);

      mounted.module.resetLibraryUiState();
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      mounted?.module.resetLibraryUiState();
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it("retire un téléchargement expiré et le régénère sans relire les livrables", async () => {
    let now = Date.parse("2026-09-12T10:00:00Z");
    const clock = vi.spyOn(Date, "now").mockImplementation(() => now);
    let generation = 0;
    try {
      const mounted = await mountLibrary([
        ...DEFAULT_ROUTES,
        [/\/artifacts\/artifact-1\/link/, () => {
          generation += 1;
          return json({
            artifact_id: "artifact-1",
            url: `https://api.example.test/artifacts/artifact-1/content?token=download-${generation}`,
            expires_at: new Date(now + 300_000).toISOString(),
          });
        }],
      ], { search: "?onglet=livrables" });

      fire(buttonLabelled(mounted.container, "Préparer le téléchargement"), "click");
      await flush();
      expect(byTag(mounted.container, "a")[0].href).toContain("download-1");
      const artifactReads = calledUrls(mounted.fetchMock).filter((url) => url.includes("/artifacts?")).length;

      now += 286_000;
      fire(byClass(mounted.container, "library-search")[0], "input");
      await flush();

      expect(byTag(mounted.container, "a")).toHaveLength(0);
      expect(textOf(mounted.container)).toContain("Le lien de téléchargement a expiré");
      expect(calledUrls(mounted.fetchMock).filter((url) => url.includes("/artifacts?"))).toHaveLength(artifactReads);
      expect(calledUrls(mounted.fetchMock).filter((url) => url.includes("/link"))).toHaveLength(1);

      fire(buttonLabelled(mounted.container, "Régénérer le téléchargement"), "click");
      await flush();

      expect(calledUrls(mounted.fetchMock).filter((url) => url.includes("/link"))).toHaveLength(2);
      expect(byTag(mounted.container, "a")[0].href).toContain("download-2");
      expect(textOf(mounted.container)).not.toContain("Le lien de téléchargement a expiré");
    } finally {
      clock.mockRestore();
    }
  });

  it("nomme l’action à effectuer quand la signature de liens est absente et propose la voie session", async () => {
    const { container } = await mountLibrary([
      ...DEFAULT_ROUTES,
      [/\/artifacts\/artifact-1\/link/, () => json(
        { detail: "Signature de liens non configurée." },
        503,
      )],
    ], { search: "?onglet=livrables" });

    fire(buttonLabelled(container, "Préparer le téléchargement"), "click");
    await flush();

    const text = textOf(container);
    expect(text).toContain("ACP_ARTIFACT_SIGNING_KEYS");
    const anchors = byTag(container, "a");
    expect(anchors).toHaveLength(1);
    expect(anchors[0].href).toContain("/artifacts/artifact-1/content");
    expect(anchors[0].href).not.toContain("token=");
  });

  it("n’offre ni aperçu ni téléchargement pour un artefact sans contenu", async () => {
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({
        items: [artifact({ has_content: false, size_bytes: null, checksum: null })],
        next_cursor: null,
      })],
    ], { search: "?onglet=livrables" });

    expect(textOf(container)).toContain("Métadonnées seules");
    expect(textOf(container)).toContain("Taille inconnue");
    expect(() => buttonLabelled(container, "Aperçu")).toThrow();
    expect(() => buttonLabelled(container, "Préparer le téléchargement")).toThrow();
  });
});

describe("renderLibrary — filtres et états", () => {
  it("filtre côté serveur par type et repart du premier curseur", async () => {
    const { container, fetchMock } = await mountLibrary(DEFAULT_ROUTES, { search: "?onglet=livrables" });
    const select = byClass(container, "library-filter-kind")[0];
    select.value = "trace";
    fire(select, "change");
    await flush();

    const urls = calledUrls(fetchMock).filter((url) => url.includes("/artifacts?"));
    expect(urls[urls.length - 1]).toContain("stream_kind=trace");
    expect(urls[urls.length - 1]).not.toContain("cursor=");
  });

  it("recherche côté client sans relire l’API", async () => {
    const { container, fetchMock } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({
        items: [artifact(), artifact({ id: "a-2", original_name: "trace.zip", content_type: "application/zip" })],
        next_cursor: null,
      })],
    ], { search: "?onglet=livrables" });

    const before = calledUrls(fetchMock).length;
    const search = byClass(container, "library-search")[0];
    search.value = "trace";
    fire(search, "input");
    await flush();

    expect(textOf(container)).toContain("trace.zip");
    expect(textOf(container)).not.toContain("accueil.png");
    expect(calledUrls(fetchMock)).toHaveLength(before);
  });

  it("charge la suite avec le curseur renvoyé par la page précédente", async () => {
    let page = 0;
    const { container, fetchMock } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => {
        page += 1;
        return page === 1
          ? json({ items: [artifact()], next_cursor: "curseur-2" })
          : json({ items: [artifact({ id: "a-2", original_name: "video.webm" })], next_cursor: null });
      }],
    ], { search: "?onglet=livrables" });

    fire(buttonLabelled(container, "Charger la suite"), "click");
    await flush();

    expect(calledUrls(fetchMock).some((url) => url.includes("cursor=curseur-2"))).toBe(true);
    expect(textOf(container)).toContain("accueil.png");
    expect(textOf(container)).toContain("video.webm");
  });

  it("affiche l’état de chargement tant que l’API n’a pas répondu", async () => {
    let release: ((value: Response) => void) | null = null;
    const pending = new Promise<Response>((resolve) => { release = resolve; });
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => pending],
    ], { search: "?onglet=livrables" });

    expect(byClass(container, "state-loading")).toHaveLength(1);
    expect(textOf(container)).not.toContain("Aucun livrable");
    release?.(json({ items: [artifact()], next_cursor: null }));
    await flush();
    expect(byClass(container, "state-loading")).toHaveLength(0);
    expect(textOf(container)).toContain("accueil.png");
  });

  it("refuse de rendre une réponse hors contrat plutôt que d’en afficher une partie", async () => {
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({ items: [{ id: "a-1", original_name: "partiel.png" }], next_cursor: null })],
    ], { search: "?onglet=livrables" });

    expect(byClass(container, "state-error")).toHaveLength(1);
    expect(textOf(container)).toContain("Réponse inexploitable");
    expect(textOf(container)).not.toContain("partiel.png");
  });

  it("ne lit jamais la session : le jeton CSRF du shell reste le seul en circulation", async () => {
    const { container, fetchMock } = await mountLibrary([
      ...DEFAULT_ROUTES,
      [/\/artifacts\/artifact-1\/link/, () => json({
        artifact_id: "artifact-1",
        url: "https://api.example.test/artifacts/artifact-1/content?token=v1.a.b.c",
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      })],
      [/\/skills\/search/, () => json({ installed: [], catalog: [] })],
      [/\/skills\/catalog/, () => json([])],
    ], { search: "?onglet=livrables" });

    fire(buttonLabelled(container, "Aperçu"), "click");
    await flush();
    fire(buttonLabelled(container, "Skills"), "click");
    await flush();

    expect(calledUrls(fetchMock).some((url) => url.includes("/auth/session"))).toBe(false);
  });

  it("affiche un état vide explicite", async () => {
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({ items: [], next_cursor: null })],
    ], { search: "?onglet=livrables" });

    expect(byClass(container, "state-empty")).toHaveLength(1);
    expect(textOf(container)).toContain("Aucun livrable");
  });

  it("affiche un état hors ligne réessayable, sans donnée de démonstration", async () => {
    let attempts = 0;
    const { container, fetchMock } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => {
        attempts += 1;
        if (attempts === 1) throw new TypeError("fetch failed");
        return json({ items: [artifact()], next_cursor: null });
      }],
    ], { search: "?onglet=livrables" });

    expect(byClass(container, "state-offline")).toHaveLength(1);
    fire(buttonLabelled(container, "Réessayer"), "click");
    await flush();
    expect(textOf(container)).toContain("accueil.png");
    expect(calledUrls(fetchMock).filter((url) => url.includes("/artifacts?"))).toHaveLength(2);
  });

  it("distingue un refus d’accès d’une panne", async () => {
    const { container } = await mountLibrary([
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/missions$/, () => json([])],
      [/\/artifacts\?/, () => json({ detail: "Projet inaccessible." }, 403)],
    ], { search: "?onglet=livrables" });

    expect(byClass(container, "state-forbidden")).toHaveLength(1);
    expect(byClass(container, "state-offline")).toHaveLength(0);
  });

  it("continue d’afficher les livrables si les filtres de référence échouent", async () => {
    const { container } = await mountLibrary([
      [/\/overview$/, () => json({ detail: "non" }, 500)],
      [/\/missions$/, () => json({ detail: "non" }, 500)],
      [/\/artifacts\?/, () => json({ items: [artifact()], next_cursor: null })],
    ], { search: "?onglet=livrables" });

    expect(textOf(container)).toContain("accueil.png");
    expect(textOf(container)).toContain("identifiant");
  });
});

describe("resetLibraryUiState", () => {
  const routes: [RegExp, Route][] = [
    ...DEFAULT_ROUTES,
    [/\/skills\/search/, () => json({ installed: [], catalog: [] })],
    [/\/skills\/catalog/, () => json([])],
  ];

  function count(fetchMock: ReturnType<typeof vi.fn>, fragment: string): number {
    return calledUrls(fetchMock).filter((url) => url.includes(fragment)).length;
  }

  it("conserve l’état entre deux rendus du shell puis le purge entièrement", async () => {
    const mounted = await mountLibrary(routes, { search: "?onglet=livrables" });
    expect(count(mounted.fetchMock, "/artifacts?")).toBe(1);

    const again = await mounted.remount();
    expect(count(mounted.fetchMock, "/artifacts?")).toBe(1);
    expect(textOf(again)).toContain("accueil.png");

    mounted.module.resetLibraryUiState();
    const afterReset = await mounted.remount();
    expect(count(mounted.fetchMock, "/artifacts?")).toBe(2);
  });

  it("délègue la purge à la bibliothèque de skills", async () => {
    const mounted = await mountLibrary(routes);
    expect(count(mounted.fetchMock, "/skills/search")).toBe(1);

    // Aller-retour entre les onglets : le module Skills garde son état, il ne relit rien.
    fire(buttonLabelled(mounted.container, "Livrables"), "click");
    await flush();
    fire(buttonLabelled(mounted.container, "Skills"), "click");
    await flush();
    expect(count(mounted.fetchMock, "/skills/search")).toBe(1);

    mounted.module.resetLibraryUiState();
    await mounted.remount();
    expect(count(mounted.fetchMock, "/skills/search")).toBe(2);
  });
});
