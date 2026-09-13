/**
 * Tests du client des livrables (`artifacts-api.ts`, spec Lot E §6 et §7).
 *
 * Aucun réseau : `fetch` est simulé. Les assertions portent sur la forme exacte des
 * requêtes (chemins encodés, filtres, bornes), sur le refus d’une réponse hors contrat
 * et sur les décisions d’aperçu — un type dangereux ne doit jamais devenir un aperçu.
 */

import { describe, expect, it, vi } from "vitest";

import {
  ARTIFACT_LINK_DEFAULT_TTL_SECONDS,
  ARTIFACT_LINK_MAX_TTL_SECONDS,
  ARTIFACT_PAGE_DEFAULT_LIMIT,
  ARTIFACT_PAGE_MAX_LIMIT,
  ARTIFACT_PREVIEW_ORIGIN_ACTION,
  ARTIFACT_SIGNING_ACTION,
  ArtifactsApiClient,
  artifactSourceLabel,
  artifactStreamKindLabel,
  describeArtifactPreview,
  describeArtifactsError,
  formatArtifactSize,
  shortChecksum,
} from "../src/artifacts-api";
import { WorkspaceApiError } from "../src/workspace-api";

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
    checksum: "a".repeat(64),
    source: "playwright",
    has_content: true,
    created_at: "2026-09-12T10:00:00Z",
    ...overrides,
  };
}

function client(fetcher: ReturnType<typeof vi.fn>): ArtifactsApiClient {
  const instance = new ArtifactsApiClient({ baseUrl: "https://api.example.test", fetcher });
  instance.http.setCsrfToken("csrf-current");
  return instance;
}

function requestUrl(fetcher: ReturnType<typeof vi.fn>, index = 0): string {
  return String(fetcher.mock.calls[index][0]);
}

function requestInit(fetcher: ReturnType<typeof vi.fn>, index = 0): RequestInit {
  return fetcher.mock.calls[index][1] as RequestInit;
}

describe("ArtifactsApiClient — liste paginée", () => {
  it("liste sans filtre avec une limite bornée par défaut", async () => {
    const fetcher = vi.fn(async () => json({ items: [artifact()], next_cursor: null }));
    const page = await client(fetcher).listArtifacts();

    expect(page.items).toHaveLength(1);
    expect(page.next_cursor).toBeNull();
    expect(requestUrl(fetcher)).toBe(
      `https://api.example.test/artifacts?limit=${ARTIFACT_PAGE_DEFAULT_LIMIT}`,
    );
    const init = requestInit(fetcher);
    expect(init.method ?? "GET").toBe("GET");
    expect(init.credentials).toBe("include");
  });

  it("transmet les filtres projet, tentative et type, et encode les valeurs", async () => {
    const fetcher = vi.fn(async () => json({ items: [], next_cursor: "curseur suivant" }));
    const page = await client(fetcher).listArtifacts({
      projectId: "projet/à risque",
      taskRunId: "run 2",
      streamKind: "video",
      cursor: "c/1",
      limit: 25,
    });

    expect(page.next_cursor).toBe("curseur suivant");
    const url = requestUrl(fetcher);
    expect(url).toContain("project_id=projet%2F%C3%A0+risque");
    expect(url).toContain("task_run_id=run+2");
    expect(url).toContain("stream_kind=video");
    expect(url).toContain("cursor=c%2F1");
    expect(url).toContain("limit=25");
  });

  it("borne la limite demandée sans jamais la relâcher", async () => {
    const fetcher = vi.fn(async () => json({ items: [], next_cursor: null }));
    const api = client(fetcher);
    await api.listArtifacts({ limit: 10_000 });
    await api.listArtifacts({ limit: 0 });
    await api.listArtifacts({ limit: Number.NaN });

    expect(requestUrl(fetcher, 0)).toContain(`limit=${ARTIFACT_PAGE_MAX_LIMIT}`);
    expect(requestUrl(fetcher, 1)).toContain("limit=1");
    expect(requestUrl(fetcher, 2)).toContain(`limit=${ARTIFACT_PAGE_DEFAULT_LIMIT}`);
  });

  it("ignore les filtres vides plutôt que d’envoyer des paramètres vides", async () => {
    const fetcher = vi.fn(async () => json({ items: [], next_cursor: null }));
    await client(fetcher).listArtifacts({ projectId: "   ", taskRunId: "", streamKind: "  " });

    expect(requestUrl(fetcher)).toBe(
      `https://api.example.test/artifacts?limit=${ARTIFACT_PAGE_DEFAULT_LIMIT}`,
    );
  });

  it("refuse une page dont un élément est hors contrat", async () => {
    const fetcher = vi.fn(async () => json({
      items: [artifact(), artifact({ has_content: "oui" })],
      next_cursor: null,
    }));
    await expect(client(fetcher).listArtifacts()).rejects.toMatchObject({
      name: "WorkspaceApiError",
      kind: "invalid_response",
    });
  });

  it("refuse une taille négative ou non entière", async () => {
    const negative = vi.fn(async () => json({ items: [artifact({ size_bytes: -1 })], next_cursor: null }));
    const fractional = vi.fn(async () => json({ items: [artifact({ size_bytes: 1.5 })], next_cursor: null }));

    await expect(client(negative).listArtifacts()).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(client(fractional).listArtifacts()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("accepte une taille, une empreinte et une date absentes", async () => {
    const fetcher = vi.fn(async () => json({
      items: [artifact({ size_bytes: null, checksum: null, created_at: null, has_content: false })],
      next_cursor: null,
    }));
    const page = await client(fetcher).listArtifacts();
    expect(page.items[0].size_bytes).toBeNull();
    expect(page.items[0].has_content).toBe(false);
  });
});

describe("ArtifactsApiClient — détail", () => {
  it("encode l’identifiant dans le chemin", async () => {
    const fetcher = vi.fn(async () => json(artifact({ id: "a/../b" })));
    await client(fetcher).fetchArtifact("a/../b");
    expect(requestUrl(fetcher)).toBe("https://api.example.test/artifacts/a%2F..%2Fb");
  });

  it("refuse un identifiant vide sans appeler l’API", async () => {
    const fetcher = vi.fn(async () => json(artifact()));
    await expect(client(fetcher).fetchArtifact("   ")).rejects.toMatchObject({
      name: "WorkspaceApiError",
    });
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("ArtifactsApiClient — lien signé", () => {
  it("crée un lien avec la durée par défaut, le CSRF et sans corps", async () => {
    const fetcher = vi.fn(async () => json({
      artifact_id: "artifact-1",
      url: "https://artifacts.example.test/artifacts/artifact-1/content?token=v1.x.y.z",
      expires_at: "2026-09-12T10:05:00Z",
    }));
    const link = await client(fetcher).createLink("artifact-1");

    expect(link.url).toContain("token=");
    expect(requestUrl(fetcher)).toBe(
      `https://api.example.test/artifacts/artifact-1/link?ttl_seconds=${ARTIFACT_LINK_DEFAULT_TTL_SECONDS}`,
    );
    const init = requestInit(fetcher);
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
    expect((init.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
  });

  it("refuse une durée hors bornes avant tout appel réseau", async () => {
    const fetcher = vi.fn(async () => json({ artifact_id: "a", url: "/x", expires_at: "2026-09-12T10:05:00Z" }));
    const api = client(fetcher);

    await expect(api.createLink("artifact-1", ARTIFACT_LINK_MAX_TTL_SECONDS + 1)).rejects.toMatchObject({
      name: "WorkspaceApiError",
    });
    await expect(api.createLink("artifact-1", 0)).rejects.toMatchObject({ name: "WorkspaceApiError" });
    await expect(api.createLink("artifact-1", 12.5)).rejects.toMatchObject({ name: "WorkspaceApiError" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("refuse une URL de lien qui n’est pas http(s) ou absolue de chemin", async () => {
    for (const url of ["javascript:alert(1)", "data:text/html,<script>", "//evil.test/x", "ftp://x/y"]) {
      const fetcher = vi.fn(async () => json({
        artifact_id: "artifact-1",
        url,
        expires_at: "2026-09-12T10:05:00Z",
      }));
      await expect(client(fetcher).createLink("artifact-1")).rejects.toMatchObject({
        kind: "invalid_response",
      });
    }
  });

  it("accepte une URL relative à la racine servie par l’API", async () => {
    const fetcher = vi.fn(async () => json({
      artifact_id: "artifact-1",
      url: "/artifacts/artifact-1/content?token=v1.a.b.c",
      expires_at: "2026-09-12T10:05:00Z",
    }));
    await expect(client(fetcher).createLink("artifact-1")).resolves.toMatchObject({
      url: "/artifacts/artifact-1/content?token=v1.a.b.c",
    });
  });
});

describe("ArtifactsApiClient — URL de contenu", () => {
  it("construit l’URL de contenu authentifiée par session", () => {
    const fetcher = vi.fn(async () => json(artifact()));
    expect(client(fetcher).contentUrl("a b/c")).toBe(
      "https://api.example.test/artifacts/a%20b%2Fc/content",
    );
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("describeArtifactsError", () => {
  it("nomme la variable à définir lorsque la signature de liens est absente", () => {
    const description = describeArtifactsError(
      new WorkspaceApiError("Signature de liens non configurée.", "http", 503),
    );
    expect(description.tone).toBe("unconfigured");
    expect(description.action).toContain(ARTIFACT_SIGNING_ACTION);
  });

  it("distingue hors ligne, session expirée et accès refusé", () => {
    expect(describeArtifactsError(new WorkspaceApiError("x", "offline")).tone).toBe("offline");
    expect(describeArtifactsError(new WorkspaceApiError("x", "forbidden", 401)).title).toContain("Session");
    expect(describeArtifactsError(new WorkspaceApiError("x", "forbidden", 403)).tone).toBe("forbidden");
    expect(describeArtifactsError(new WorkspaceApiError("x", "invalid_response")).tone).toBe("error");
    expect(describeArtifactsError(new WorkspaceApiError("x", "http", 404)).title).toBe("Introuvable");
  });
});

describe("describeArtifactPreview", () => {
  it("autorise l’aperçu des images et des vidéos de la liste blanche", () => {
    for (const contentType of ["image/png", "image/jpeg", "image/webp", "image/gif"]) {
      expect(describeArtifactPreview(artifact({ content_type: contentType })).kind).toBe("image");
    }
    for (const contentType of ["video/webm", "video/mp4"]) {
      expect(describeArtifactPreview(artifact({ content_type: contentType, stream_kind: "video" })).kind)
        .toBe("video");
    }
  });

  it("ignore les paramètres du type et la casse", () => {
    const decision = describeArtifactPreview(artifact({ content_type: "IMAGE/PNG; charset=binary" }));
    expect(decision.kind).toBe("image");
  });

  it("n’affiche jamais en ligne un HTML, un SVG ou une archive et explique pourquoi", () => {
    for (const contentType of ["text/html", "image/svg+xml", "application/zip"]) {
      const decision = describeArtifactPreview(artifact({ content_type: contentType }));
      expect(decision.kind).toBe("none");
      expect(decision.downloadOnly).toBe(true);
      expect(decision.warning.length).toBeGreaterThan(0);
    }
  });

  it("se fie à l’extension quand le type déclaré la contredit", () => {
    const decision = describeArtifactPreview(
      artifact({ content_type: "image/png", original_name: "rapport.svg" }),
    );
    expect(decision.kind).toBe("none");
    expect(decision.warning).toContain("SVG");
  });

  it("mentionne l’outil Playwright pour une trace", () => {
    const decision = describeArtifactPreview(
      artifact({ content_type: "application/zip", stream_kind: "trace", original_name: "trace.zip" }),
    );
    expect(decision.warning).toContain("Playwright");
  });

  it("ne propose ni aperçu ni téléchargement sans contenu téléversé", () => {
    const decision = describeArtifactPreview(artifact({ has_content: false }));
    expect(decision.kind).toBe("none");
    expect(decision.downloadable).toBe(false);
  });

  it("laisse un type inconnu en téléchargement neutre, sans avertissement", () => {
    const decision = describeArtifactPreview(
      artifact({ content_type: "application/octet-stream", original_name: "resultat.bin" }),
    );
    expect(decision.kind).toBe("none");
    expect(decision.warning).toBe("");
    expect(decision.downloadable).toBe(true);
  });
});

describe("formats", () => {
  it("formate une taille absente et une taille connue", () => {
    expect(formatArtifactSize(null)).toBe("Taille inconnue");
    expect(formatArtifactSize(2048)).toContain("ko");
  });

  it("raccourcit une empreinte et nomme son absence", () => {
    expect(shortChecksum(null)).toBe("Empreinte absente");
    expect(shortChecksum("a".repeat(64))).toContain("…");
    expect(shortChecksum("a".repeat(64))).toContain("aaaaaaaa");
  });

  it("traduit les types de flux et les provenances, sans masquer une valeur inconnue", () => {
    expect(artifactStreamKindLabel("screenshot")).toBe("Capture d’écran");
    expect(artifactStreamKindLabel("trace")).toBe("Trace");
    expect(artifactStreamKindLabel("inconnu-du-client")).toBe("inconnu-du-client");
    expect(artifactSourceLabel("playwright")).toBe("Playwright");
    expect(artifactSourceLabel("worker")).toBe("Worker");
    expect(artifactSourceLabel("autre")).toBe("autre");
  });

  it("expose la variable d’origine d’aperçu à documenter", () => {
    expect(ARTIFACT_PREVIEW_ORIGIN_ACTION).toBe("ACP_ARTIFACT_PUBLIC_ORIGIN");
  });
});
