/**
 * Tests de rendu de `skills-ui.ts` sur un DOM minimal simulé.
 *
 * Aucune dépendance n’est ajoutée (ni jsdom ni happy-dom) : le stub ci-dessous
 * n’implémente que les API réellement utilisées par le module. Ces tests vérifient
 * le chemin de rendu et les états honnêtes (hors ligne, non configuré, binaire,
 * refus), pas le rendu visuel réel — celui-ci reste vérifié par `tsc`, le build et
 * une revue humaine.
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
  accept = "";
  href = "";
  target = "";
  rel = "";
  rows = 0;
  tabIndex = 0;
  spellcheck = true;
  disabled = false;
  files: unknown[] | null = null;
  readonly children: FakeElement[] = [];
  readonly attributes: Record<string, string> = {};
  readonly dataset: Record<string, string> = {};
  readonly listeners: Record<string, Handler[]> = {};

  constructor(tagName: string) {
    this.tagName = tagName;
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

  /** Seul sélecteur utilisé par le module : `[data-role='...']`. */
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

function byClass(root: FakeElement, className: string): FakeElement[] {
  return findAll(root, (node) => node.className.split(" ").includes(className));
}

function buttonLabelled(root: FakeElement, label: string): FakeElement {
  const node = findAll(root, (candidate) => candidate.tagName === "button" && textOf(candidate).includes(label))[0];
  if (!node) throw new Error(`Bouton introuvable : ${label}`);
  return node;
}

function fire(node: FakeElement, type: string, event: unknown = { preventDefault() {} }): void {
  for (const handler of node.listeners[type] ?? []) handler(event);
}

function installDocument(): void {
  (globalThis as unknown as { document: unknown }).document = {
    createElement: (tag: string) => new FakeElement(tag),
  };
}

async function flush(rounds = 8): Promise<void> {
  for (let index = 0; index < rounds; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

// --- Réponses simulées ---------------------------------------------------------

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function skillSummary(overrides: Record<string, unknown> = {}) {
  return {
    id: "skill-1",
    name: "demo",
    display_name: "Démo",
    description: "Skill de démonstration",
    category: "general",
    kind: "scripted",
    source_kind: "manual",
    origin: "",
    status: "draft",
    current_revision_number: 1,
    binding_count: 0,
    requires_approval: true,
    created_at: "2026-09-11T10:00:00Z",
    updated_at: "2026-09-11T10:00:00Z",
    revoked_at: null,
    ...overrides,
  };
}

function skillRevision(overrides: Record<string, unknown> = {}) {
  return {
    id: "rev-1",
    skill_id: "skill-1",
    number: 1,
    fingerprint: "a".repeat(64),
    files: [
      { path: "SKILL.md", size: 120, sha256: "b".repeat(64), text: true },
      { path: "assets/logo.png", size: 2048, sha256: "d".repeat(64), text: false },
    ],
    frontmatter: { name: "demo", description: "Skill de démonstration" },
    license: "MIT",
    dependencies: {
      required_environment_variables: [{ name: "DEMO_TOKEN" }],
      requires_toolsets: [],
      requires_tools: [],
      scripts: [],
      network_indicators: [],
      platforms: [],
    },
    scan: [
      { level: "info", code: "advisory_only", message: "contrôle automatique indicatif, non certifiant", path: null },
    ],
    kind: "scripted",
    change_summary: null,
    requires_approval: true,
    approved: false,
    approved_at: null,
    source_ref: "manual",
    note: "",
    created_at: "2026-09-11T10:00:00Z",
    superseded_at: null,
    ...overrides,
  };
}

function skillDetail(overrides: Record<string, unknown> = {}) {
  const current = skillRevision();
  return {
    ...skillSummary(),
    current_revision: current,
    revisions: [current],
    bindings: [],
    apply_notes: ["Hermes recharge les skills au prochain démarrage de session."],
    ...overrides,
  };
}

const SESSION = {
  user: { id: "user-1", login: "owner", display_name: "Propriétaire", role: "owner" },
  csrf_token: "csrf-current",
  expires_at: "2026-09-12T12:00:00Z",
};

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

type Route = (url: string, init: RequestInit | undefined) => Response | Promise<Response>;

/**
 * Monte la route. `shellCsrfToken` simule le shell qui partage son client HTTP :
 * le module doit alors s’en servir tel quel et ne jamais relire `/auth/session`
 * (cet appel fait tourner le jeton CSRF côté serveur et invaliderait celui du shell).
 */
async function mountLibrary(routes: [RegExp, Route][], options: { shellCsrfToken?: string } = {}): Promise<{
  container: FakeElement;
  fetchMock: ReturnType<typeof vi.fn>;
  render: (target: FakeElement) => void;
}> {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    for (const [pattern, route] of routes) {
      if (pattern.test(url)) return route(url, init);
    }
    return json({ detail: `Route non simulée : ${url}` }, 404);
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  installDocument();
  vi.resetModules();
  const { WorkspaceHttpClient } = await import("../src/workspace-api");
  let shellHttp: InstanceType<typeof WorkspaceHttpClient> | undefined;
  if (options.shellCsrfToken !== undefined) {
    shellHttp = new WorkspaceHttpClient();
    shellHttp.setCsrfToken(options.shellCsrfToken);
  }
  const { renderSkillsLibrary } = await import("../src/skills-ui");
  const container = new FakeElement("div");
  renderSkillsLibrary(container as unknown as HTMLElement, shellHttp);
  await flush();
  return {
    container,
    fetchMock,
    render: (target) => renderSkillsLibrary(target as unknown as HTMLElement, shellHttp),
  };
}

function urlsOf(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input));
}

function sessionCallCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return urlsOf(fetchMock).filter((url) => url.endsWith("/auth/session")).length;
}

function csrfOf(fetchMock: ReturnType<typeof vi.fn>, suffix: string): string | null {
  const call = fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix)).at(-1);
  if (!call) throw new Error(`Aucune requête vers ${suffix}`);
  return (call[1]?.headers as Headers).get("X-CSRF-Token");
}

/** `File` minimal : seules `name`, `size` et `arrayBuffer()` sont lues par le module. */
function fakeArchive(name: string, size: number): unknown {
  return { name, size, arrayBuffer: async () => new ArrayBuffer(Math.min(size, 8)) };
}

const SEARCH_EMPTY: [RegExp, Route][] = [
  [/\/auth\/session$/, () => json(SESSION)],
  [/\/overview$/, () => json(OVERVIEW)],
  [/\/skills\/search/, () => json({ installed: [], catalog: [] })],
  [/\/skills\/catalog$/, () => json([])],
];

// --- Tests ---------------------------------------------------------------------

describe("renderSkillsLibrary", () => {
  it("affiche un état hors ligne actionnable plutôt qu’une liste vide quand l’API ne répond pas", async () => {
    const { container } = await mountLibrary([
      [/.*/, () => { throw new TypeError("fetch failed"); }],
    ]);

    const panels = byClass(container, "state-offline");
    expect(panels.length).toBeGreaterThan(0);
    expect(textOf(container)).toContain("API hors ligne");
    expect(textOf(container)).toContain("Réessayer");
    expect(textOf(container)).not.toContain("Démo");
  });

  it("liste les skills installés avec statut, nature et mention du plugin natif non sandboxé", async () => {
    const { container } = await mountLibrary([
      [/\/auth\/session$/, () => json(SESSION)],
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/skills\/search/, () => json({
        installed: [
          skillSummary(),
          skillSummary({ id: "skill-2", name: "plugin", display_name: "Plugin", kind: "native_plugin", status: "active", requires_approval: false }),
        ],
        catalog: [],
      })],
      [/\/skills\/catalog$/, () => json([])],
    ]);

    const rendered = textOf(container);
    expect(rendered).toContain("Démo");
    expect(rendered).toContain("Brouillon");
    expect(rendered).toContain("Approbation requise");
    expect(rendered).toContain("Plugin natif : non sandboxé");
    expect(rendered).toContain("2 skills installés");
  });

  it("affiche l’état vide sans jamais inventer de skill", async () => {
    const { container } = await mountLibrary(SEARCH_EMPTY);

    expect(byClass(container, "state-empty").length).toBeGreaterThan(0);
    expect(textOf(container)).toContain("Aucun skill installé");
  });

  it("remonte le 503 « GitHub non configuré » avec la variable à définir côté API", async () => {
    const { container } = await mountLibrary([
      ...SEARCH_EMPTY,
      [/\/skills\/import$/, () => json({ detail: "Import GitHub non configuré." }, 503)],
    ]);

    fire(buttonLabelled(container, "Importer un skill"), "click");
    fire(buttonLabelled(container, "GitHub"), "click");

    const repository = findAll(container, (node) => node.placeholder === "owner/repo")[0];
    const ref = findAll(container, (node) => node.placeholder === "40 caractères hexadécimaux")[0];
    repository.value = "anthropics/skills";
    fire(repository, "input");
    ref.value = "0".repeat(40);
    fire(ref, "input");

    fire(buttonLabelled(container, "Importer"), "click");
    await flush();

    const feedback = byClass(container, "skills-feedback").find((node) => node.textContent.length > 0);
    expect(feedback?.dataset.tone).toBe("error");
    expect(feedback?.textContent).toContain("Import GitHub non configuré.");
    expect(feedback?.textContent).toContain("ACP_SKILLS_GITHUB_ENABLED");
  });

  it("refuse localement une ref GitHub qui n’est pas un commit épinglé, sans appel réseau", async () => {
    const { container, fetchMock } = await mountLibrary(SEARCH_EMPTY);
    const callsBefore = fetchMock.mock.calls.length;

    fire(buttonLabelled(container, "Importer un skill"), "click");
    fire(buttonLabelled(container, "GitHub"), "click");
    const repository = findAll(container, (node) => node.placeholder === "owner/repo")[0];
    repository.value = "anthropics/skills";
    fire(repository, "input");
    const ref = findAll(container, (node) => node.placeholder === "40 caractères hexadécimaux")[0];
    ref.value = "main";
    fire(ref, "input");

    fire(buttonLabelled(container, "Importer"), "click");
    await flush();

    expect(fetchMock.mock.calls.length).toBe(callsBefore);
    const feedback = byClass(container, "skills-feedback").find((node) => node.textContent.length > 0);
    expect(feedback?.textContent).toContain("SHA de 40 caractères");
  });

  it("met à jour l’aperçu du frontmatter à la saisie, sans repeindre la page", async () => {
    const { container } = await mountLibrary(SEARCH_EMPTY);
    fire(buttonLabelled(container, "Importer un skill"), "click");

    const textarea = findAll(container, (node) => node.tagName === "textarea")[0];
    textarea.value = "---\nname: demo\n---\n# Corps";
    fire(textarea, "input");

    const preview = findAll(container, (node) => node.dataset.role === "frontmatter-preview")[0];
    const rendered = textOf(preview);
    expect(rendered).toContain("Aperçu du frontmatter (indicatif)");
    expect(rendered).toContain("demo");
    expect(rendered).toContain("Champ « description » absent du frontmatter.");
    // la zone de saisie n’a pas été recréée : la frappe conserve le focus
    expect(findAll(container, (node) => node.tagName === "textarea")[0]).toBe(textarea);
  });

  it("le catalogue pré-remplit l’import GitHub sans rien installer", async () => {
    const { container, fetchMock } = await mountLibrary([
      ...SEARCH_EMPTY.filter(([pattern]) => !/catalog/.test(pattern.source)),
      [/\/skills\/catalog$/, () => json([{
        id: "anthropics-skills",
        display_name: "anthropics/skills",
        description: "Skills publiés par Anthropic",
        repository: "anthropics/skills",
        path: "document-skills",
        documentation_url: "https://github.com/anthropics/skills",
        license: "Apache-2.0",
        verified_at: "2026-09-11",
        verification: "dépôt cité par la documentation Hermes 0.21.1 ; contenu non audité par la plateforme",
        note: "épingler un commit (SHA) avant installation",
      }])],
    ]);

    expect(textOf(container)).toContain("contenu non audité par la plateforme");
    expect(textOf(container)).toContain("Non audité");

    fire(buttonLabelled(container, "Pré-remplir l’import GitHub"), "click");

    const repository = findAll(container, (node) => node.placeholder === "owner/repo")[0];
    expect(repository.value).toBe("anthropics/skills");
    expect(findAll(container, (node) => node.placeholder === "chemin dans le dépôt")[0].value)
      .toBe("document-skills");
    const feedback = byClass(container, "skills-feedback").find((node) => node.textContent.length > 0);
    expect(feedback?.textContent).toContain("SHA");
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/skills/import"))).toBe(false);
  });

  it("distingue un refus 403 d’une panne : le message cite le rôle propriétaire", async () => {
    const { container } = await mountLibrary([
      ...SEARCH_EMPTY,
      [/\/skills\/import$/, () => json({ detail: "Action réservée au propriétaire." }, 403)],
    ]);

    fire(buttonLabelled(container, "Importer un skill"), "click");
    const textarea = findAll(container, (node) => node.tagName === "textarea")[0];
    textarea.value = "---\nname: demo\ndescription: x\n---\n# Corps";
    fire(textarea, "input");
    fire(buttonLabelled(container, "Importer"), "click");
    await flush();

    const feedback = byClass(container, "skills-feedback").find((node) => node.textContent.length > 0);
    expect(feedback?.textContent).toContain("Accès refusé");
    expect(feedback?.textContent).toContain("propriétaire");
  });

  it("affiche le contenu d’un fichier en texte brut et refuse d’afficher un binaire", async () => {
    const { container } = await mountLibrary([
      ...SEARCH_EMPTY.filter(([pattern]) => !/search/.test(pattern.source)),
      [/\/skills\/search/, () => json({ installed: [skillSummary()], catalog: [] })],
      [/\/skills\/skill-1\/revisions\/1\/files\/SKILL\.md$/, () => json({
        path: "SKILL.md",
        text: true,
        content: "---\nname: demo\n---\n<script>alert('x')</script>",
        truncated: false,
        size: 120,
        sha256: "b".repeat(64),
      })],
      [/\/skills\/skill-1\/revisions\/1\/files\/assets\/logo\.png$/, () => json({
        path: "assets/logo.png",
        text: false,
        content: null,
        truncated: false,
        size: 2048,
        sha256: "d".repeat(64),
      })],
      [/\/skills\/skill-1$/, () => json(skillDetail())],
    ]);

    fire(buttonLabelled(container, "Détail"), "click");
    await flush();
    expect(textOf(container)).toContain("contrôle automatique indicatif");

    fire(buttonLabelled(container, "SKILL.md"), "click");
    await flush();

    const pre = byClass(container, "skills-file-content")[0];
    expect(pre.tagName).toBe("pre");
    expect(pre.textContent).toContain("<script>alert('x')</script>");
    expect(byClass(container, "skills-tree-file").length).toBe(2);

    fire(buttonLabelled(container, "logo.png"), "click");
    await flush();
    expect(byClass(container, "skills-file-content")).toHaveLength(0);
    expect(textOf(byClass(container, "skills-viewer")[0])).toContain("Fichier binaire");
  });

  it("désactive le rattachement tant que le skill n’est pas actif", async () => {
    const { container } = await mountLibrary([
      ...SEARCH_EMPTY.filter(([pattern]) => !/search/.test(pattern.source)),
      [/\/skills\/search/, () => json({ installed: [skillSummary()], catalog: [] })],
      [/\/skills\/skill-1$/, () => json(skillDetail())],
    ]);

    fire(buttonLabelled(container, "Détail"), "click");
    await flush();

    expect(buttonLabelled(container, "Rattacher au projet").disabled).toBe(true);
    expect(buttonLabelled(container, "Activer").disabled).toBe(false);
    expect(textOf(container)).toContain("L’activation est refusée (409)");
    expect(textOf(container)).toContain("Projet A");
  });

  it("exige un motif confirmé avant toute révocation", async () => {
    const { container, fetchMock } = await mountLibrary([
      ...SEARCH_EMPTY.filter(([pattern]) => !/search/.test(pattern.source)),
      [/\/skills\/search/, () => json({ installed: [skillSummary({ status: "active", requires_approval: false })], catalog: [] })],
      [/\/skills\/skill-1\/revoke$/, () => json(skillDetail({ status: "revoked", revoked_at: "2026-09-12T09:00:00Z" }))],
      [/\/skills\/skill-1$/, () => json(skillDetail({ status: "active", requires_approval: false }))],
    ]);

    fire(buttonLabelled(container, "Détail"), "click");
    await flush();
    fire(buttonLabelled(container, "Révoquer"), "click");

    const confirmPanel = byClass(container, "skills-confirm")[0];
    expect(textOf(confirmPanel)).toContain("Motif (obligatoire)");

    fire(buttonLabelled(confirmPanel, "Confirmer la révocation"), "click");
    await flush();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/revoke"))).toBe(false);
    const filled = byClass(container, "skills-feedback").filter((node) => node.textContent.length > 0);
    // une seule zone `aria-live` porte le message : celle du détail, où l’action a eu lieu
    expect(filled).toHaveLength(1);
    expect(filled[0].dataset.scope).toBe("detail");
    expect(filled[0].textContent).toContain("motif de révocation est obligatoire");

    const reason = findAll(byClass(container, "skills-confirm")[0], (node) => node.tagName === "input")[0];
    expect(reason).toBeDefined();
    reason.value = "source non fiable";
    fire(reason, "input");
    fire(buttonLabelled(byClass(container, "skills-confirm")[0], "Confirmer la révocation"), "click");
    await flush();

    const revoke = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/revoke"));
    expect(revoke).toBeDefined();
    expect(JSON.parse(String(revoke?.[1]?.body))).toEqual({ reason: "source non fiable" });
    expect((revoke?.[1]?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
  });
});

describe("renderSkillsLibrary — jeton CSRF partagé", () => {
  it("n’appelle pas GET /auth/session au premier affichage : le jeton du shell reste valide", async () => {
    const { fetchMock } = await mountLibrary(SEARCH_EMPTY);

    // `GET /auth/session` fait tourner le jeton côté serveur : ouvrir la route ne doit rien invalider.
    expect(sessionCallCount(fetchMock)).toBe(0);
    expect(urlsOf(fetchMock).some((url) => url.includes("/skills/search"))).toBe(true);
  });

  it("écrit avec le jeton du client fourni par le shell sans jamais redemander la session", async () => {
    const { container, fetchMock } = await mountLibrary([
      [/\/auth\/session$/, () => json(SESSION)],
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/skills\/catalog$/, () => json([])],
      [/\/skills\/skill-1\/activate$/, () => json(skillDetail({ status: "active", requires_approval: false }))],
      [/\/skills\/search/, () => json({ installed: [skillSummary({ requires_approval: false })], catalog: [] })],
      [/\/skills\/skill-1$/, () => json(skillDetail({ requires_approval: false }))],
    ], { shellCsrfToken: "csrf-shell" });

    fire(buttonLabelled(container, "Détail"), "click");
    await flush();
    fire(buttonLabelled(container, "Activer"), "click");
    await flush();

    expect(csrfOf(fetchMock, "/activate")).toBe("csrf-shell");
    expect(sessionCallCount(fetchMock)).toBe(0);
  });

  it("réarme la vérification de session après un refus 403 au lieu d’échouer définitivement", async () => {
    let sessions = 0;
    let activations = 0;
    const { container, fetchMock } = await mountLibrary([
      [/\/auth\/session$/, () => {
        sessions += 1;
        return json({ ...SESSION, csrf_token: `csrf-${sessions}` });
      }],
      [/\/overview$/, () => json(OVERVIEW)],
      [/\/skills\/catalog$/, () => json([])],
      [/\/skills\/skill-1\/activate$/, () => {
        activations += 1;
        return activations === 1
          ? json({ detail: "Requête refusée" }, 403)
          : json(skillDetail({ status: "active", requires_approval: false }));
      }],
      [/\/skills\/search/, () => json({ installed: [skillSummary({ requires_approval: false })], catalog: [] })],
      [/\/skills\/skill-1$/, () => json(skillDetail({ requires_approval: false }))],
    ]);

    fire(buttonLabelled(container, "Détail"), "click");
    await flush();
    fire(buttonLabelled(container, "Activer"), "click");
    await flush();

    expect(sessions).toBe(1);
    expect(csrfOf(fetchMock, "/activate")).toBe("csrf-1");
    expect(textOf(container)).toContain("Accès refusé");

    fire(buttonLabelled(container, "Activer"), "click");
    await flush();

    expect(sessions).toBe(2);
    expect(csrfOf(fetchMock, "/activate")).toBe("csrf-2");
    expect(activations).toBe(2);
  });
});

describe("renderSkillsLibrary — archive importée", () => {
  it("refuse localement une archive au-delà de la limite réelle de l’API (20 Mio)", async () => {
    const { container, fetchMock } = await mountLibrary(SEARCH_EMPTY);
    const callsBefore = fetchMock.mock.calls.length;

    fire(buttonLabelled(container, "Importer un skill"), "click");
    fire(buttonLabelled(container, "Archive"), "click");
    const input = findAll(container, (node) => node.type === "file")[0];
    input.files = [fakeArchive("skill.zip", 22 * 1024 * 1024)];
    fire(input, "change");
    await flush();

    const feedback = byClass(container, "skills-feedback").find((node) => node.textContent.length > 0);
    expect(feedback?.dataset.tone).toBe("error");
    expect(feedback?.textContent).toContain("20 Mo");
    expect(feedback?.textContent).not.toContain("25 Mo");
    expect(textOf(container)).toContain("Aucune archive sélectionnée");
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });

  it("accepte une archive sous la limite et l’encode sans appel réseau", async () => {
    const { container, fetchMock } = await mountLibrary(SEARCH_EMPTY);
    const callsBefore = fetchMock.mock.calls.length;

    fire(buttonLabelled(container, "Importer un skill"), "click");
    fire(buttonLabelled(container, "Archive"), "click");
    const input = findAll(container, (node) => node.type === "file")[0];
    input.files = [fakeArchive("skill.tar.gz", 4096)];
    fire(input, "change");
    await flush();

    expect(textOf(container)).toContain("skill.tar.gz");
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });

  it("propose au sélecteur les formats d’archive réellement acceptés par l’API", async () => {
    const { container } = await mountLibrary(SEARCH_EMPTY);

    fire(buttonLabelled(container, "Importer un skill"), "click");
    fire(buttonLabelled(container, "Archive"), "click");
    const input = findAll(container, (node) => node.type === "file")[0];

    for (const extension of [".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz"]) {
      expect(input.accept).toContain(extension);
    }
  });
});
