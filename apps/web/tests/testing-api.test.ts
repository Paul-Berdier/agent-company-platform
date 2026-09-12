/**
 * Tests du client de résultats de tests du Studio (`testing-api.ts`, spec Lot E §10).
 *
 * Deux exigences structurent ces tests :
 * 1. les statuts `passed`, `failed`, `timedOut`, `skipped`, `interrupted` et le caractère
 *    `flaky` restent **distincts**, jamais réduits à vert/rouge ;
 * 2. une réponse hors contrat est refusée entièrement : un arbre de tests partiellement
 *    rendu mentirait sur ce qui a réellement été exécuté.
 */

import { describe, expect, it, vi } from "vitest";

import {
  TestingApiClient,
  buildTestTree,
  describeTestRunStatus,
  formatTestDuration,
  isMissingTestRun,
  summarizeTestTotals,
  testCaseBadge,
} from "../src/testing-api";
import { WorkspaceApiError, WorkspaceHttpClient } from "../src/workspace-api";

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function artifact(overrides: Record<string, unknown> = {}) {
  return {
    id: "art-1",
    project_id: "prj-1",
    task_run_id: "run-1",
    kind: "test_attachment",
    stream_kind: "screenshot",
    original_name: "echec.png",
    content_type: "image/png",
    size_bytes: 2048,
    checksum: "a".repeat(64),
    source: "playwright",
    has_content: true,
    created_at: "2026-09-12T10:00:00Z",
    ...overrides,
  };
}

function totals(overrides: Record<string, unknown> = {}) {
  return {
    expected: 3,
    unexpected: 1,
    flaky: 1,
    skipped: 2,
    interrupted: 0,
    timedOut: 1,
    ...overrides,
  };
}

function testCase(overrides: Record<string, unknown> = {}) {
  return {
    id: "case-1",
    test_run_id: "tr-1",
    suite_path: ["panier.spec.ts", "Panier"],
    title: "ajoute un article",
    test_id: "panier.spec.ts:12:3",
    location: { file: "panier.spec.ts", line: 12, column: 3 },
    project_name: "chromium",
    attempt: 1,
    expected_status: "passed",
    status: "passed",
    outcome: "expected",
    duration_ms: 1234,
    error_message: "",
    error_snippet: "",
    steps: [{ title: "cliquer", category: "test.step", duration_ms: 12, error: false }],
    annotations: [],
    attachments: [artifact()],
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    id: "tr-1",
    task_run_id: "run-1",
    project_id: "prj-1",
    worker_id: "wk-1",
    runner: "playwright",
    runner_version: "1.47.0",
    status: "completed",
    started_at: "2026-09-12T10:00:00Z",
    finished_at: "2026-09-12T10:02:00Z",
    duration_ms: 120000,
    totals: totals(),
    exit_code: 1,
    config: { projects: ["chromium"] },
    case_count: 1,
    cases: [testCase()],
    report_artifact: artifact({
      id: "art-report",
      stream_kind: "report",
      original_name: "index.html",
      content_type: "text/html",
    }),
    ...overrides,
  };
}

function clientWith(response: Response) {
  const fetcher = vi.fn(async () => response);
  const http = new WorkspaceHttpClient({ baseUrl: "http://api.test", fetcher });
  return { client: new TestingApiClient(http), fetcher };
}

describe("TestingApiClient.fetchTestRun", () => {
  it("lit le résultat de tests d’une tentative", async () => {
    const { client, fetcher } = clientWith(json(detail()));

    const result = await client.fetchTestRun("run 1");

    expect(fetcher.mock.calls[0][0]).toBe("http://api.test/runs/run%201/test-run");
    expect(result.cases[0].outcome).toBe("expected");
    expect(result.totals.timedOut).toBe(1);
    expect(result.report_artifact?.content_type).toBe("text/html");
  });

  it("accepte une exécution sans rapport ni worker", async () => {
    const { client } = clientWith(json(detail({
      worker_id: null,
      report_artifact: null,
      finished_at: null,
      duration_ms: null,
      exit_code: null,
      status: "running",
      cases: [],
      case_count: 0,
    })));

    const result = await client.fetchTestRun("run-1");

    expect(result.report_artifact).toBeNull();
    expect(result.status).toBe("running");
  });

  it("refuse un statut de cas hors contrat", async () => {
    const { client } = clientWith(json(detail({ cases: [testCase({ status: "green" })] })));

    await expect(client.fetchTestRun("run-1")).rejects.toMatchObject({
      name: "WorkspaceApiError",
      kind: "invalid_response",
    });
  });

  it("refuse un caractère de résultat hors contrat", async () => {
    const { client } = clientWith(json(detail({ cases: [testCase({ outcome: "maybe" })] })));

    await expect(client.fetchTestRun("run-1")).rejects.toBeInstanceOf(WorkspaceApiError);
  });

  it("refuse des totaux incomplets plutôt que de compléter par des zéros", async () => {
    const incomplete = totals();
    delete (incomplete as Record<string, unknown>).timedOut;
    const { client } = clientWith(json(detail({ totals: incomplete })));

    await expect(client.fetchTestRun("run-1")).rejects.toBeInstanceOf(WorkspaceApiError);
  });

  it("refuse une pièce jointe hors contrat", async () => {
    const { client } = clientWith(json(detail({
      cases: [testCase({ attachments: [artifact({ has_content: "oui" })] })],
    })));

    await expect(client.fetchTestRun("run-1")).rejects.toBeInstanceOf(WorkspaceApiError);
  });

  it("refuse une étape hors contrat", async () => {
    const { client } = clientWith(json(detail({
      cases: [testCase({ steps: [{ title: "cliquer", category: "test.step", duration_ms: 12 }] })],
    })));

    await expect(client.fetchTestRun("run-1")).rejects.toBeInstanceOf(WorkspaceApiError);
  });

  it("distingue l’absence de résultat d’un refus d’accès", async () => {
    const missing = new WorkspaceApiError("Aucun résultat.", "http", 404);
    const forbidden = new WorkspaceApiError("Refusé.", "forbidden", 403);

    expect(isMissingTestRun(missing)).toBe(true);
    expect(isMissingTestRun(forbidden)).toBe(false);
    expect(isMissingTestRun(new Error("boum"))).toBe(false);
  });
});

describe("arbre et libellés de tests", () => {
  it("regroupe les cas par suite en conservant l’ordre d’apparition", () => {
    const tree = buildTestTree([
      testCase({ id: "a", suite_path: ["panier.spec.ts", "Panier"], title: "ajoute" }),
      testCase({ id: "b", suite_path: ["panier.spec.ts", "Panier"], title: "retire" }),
      testCase({ id: "c", suite_path: ["panier.spec.ts", "Remises"], title: "applique" }),
      testCase({ id: "d", suite_path: [], title: "sans suite" }),
    ] as never);

    expect(tree.map((node) => node.title)).toEqual(["panier.spec.ts", "Sans suite"]);
    expect(tree[0].suites.map((node) => node.title)).toEqual(["Panier", "Remises"]);
    expect(tree[0].suites[0].cases.map((item) => item.title)).toEqual(["ajoute", "retire"]);
    expect(tree[0].cases).toHaveLength(0);
    expect(tree[1].cases.map((item) => item.title)).toEqual(["sans suite"]);
  });

  it("compte les cas de chaque suite, sous-suites comprises", () => {
    const tree = buildTestTree([
      testCase({ id: "a", suite_path: ["s.spec.ts", "A"], status: "passed", outcome: "expected" }),
      testCase({ id: "b", suite_path: ["s.spec.ts", "A"], status: "failed", outcome: "unexpected" }),
      testCase({ id: "c", suite_path: ["s.spec.ts", "B"], status: "skipped", outcome: "skipped" }),
    ] as never);

    expect(tree[0].caseCount).toBe(3);
    expect(tree[0].unexpectedCount).toBe(1);
    expect(tree[0].suites[0].caseCount).toBe(2);
    expect(tree[0].suites[0].unexpectedCount).toBe(1);
    expect(tree[0].suites[1].unexpectedCount).toBe(0);
  });

  it("garde chaque statut distinct, sans réduction à vert ou rouge", () => {
    expect(testCaseBadge(testCase({ status: "passed", outcome: "expected" }) as never).label)
      .toBe("Réussi");
    expect(testCaseBadge(testCase({ status: "failed", outcome: "unexpected" }) as never).label)
      .toBe("Échec");
    expect(testCaseBadge(testCase({ status: "failed", outcome: "expected" }) as never).label)
      .toBe("Échec attendu");
    expect(testCaseBadge(testCase({ status: "passed", outcome: "flaky" }) as never).label)
      .toBe("Instable (flaky)");
    expect(testCaseBadge(testCase({ status: "failed", outcome: "flaky" }) as never).label)
      .toBe("Instable (flaky)");
    expect(testCaseBadge(testCase({ status: "skipped", outcome: "skipped" }) as never).label)
      .toBe("Ignoré");
    expect(testCaseBadge(testCase({ status: "timedOut", outcome: "unexpected" }) as never).label)
      .toBe("Délai dépassé");
    expect(testCaseBadge(testCase({ status: "interrupted", outcome: "unexpected" }) as never).label)
      .toBe("Interrompu");
    expect(testCaseBadge(testCase({ status: "passed", outcome: "unexpected" }) as never).label)
      .toBe("Réussi alors qu’un échec était attendu");
  });

  it("n’attribue jamais la même tonalité à un succès et à un statut non concluant", () => {
    expect(testCaseBadge(testCase({ status: "passed", outcome: "expected" }) as never).tone).toBe("done");
    expect(testCaseBadge(testCase({ status: "timedOut", outcome: "unexpected" }) as never).tone).toBe("failed");
    expect(testCaseBadge(testCase({ status: "skipped", outcome: "skipped" }) as never).tone).toBe("waiting");
    expect(testCaseBadge(testCase({ status: "passed", outcome: "flaky" }) as never).tone).toBe("waiting");
  });

  it("résume les totaux en affichant les six compteurs", () => {
    expect(summarizeTestTotals(totals() as never)).toBe(
      "3 attendus · 1 inattendu · 1 instable · 2 ignorés · 0 interrompu · 1 délai dépassé",
    );
    expect(summarizeTestTotals(totals({
      expected: 1,
      unexpected: 0,
      flaky: 0,
      skipped: 0,
      interrupted: 2,
      timedOut: 3,
    }) as never)).toBe(
      "1 attendu · 0 inattendu · 0 instable · 0 ignoré · 2 interrompus · 3 délais dépassés",
    );
  });

  it("met en forme les durées sans jamais inventer une valeur", () => {
    expect(formatTestDuration(0)).toBe("0 ms");
    expect(formatTestDuration(850)).toBe("850 ms");
    expect(formatTestDuration(1234)).toBe("1,2 s");
    expect(formatTestDuration(61500)).toBe("1 min 2 s");
    expect(formatTestDuration(null)).toBe("Durée inconnue");
    expect(formatTestDuration(-5)).toBe("Durée inconnue");
    expect(formatTestDuration(Number.NaN)).toBe("Durée inconnue");
  });

  it("décrit chaque statut d’exécution de tests", () => {
    expect(describeTestRunStatus("running").label).toBe("Exécution en cours");
    expect(describeTestRunStatus("completed").label).toBe("Exécution terminée");
    expect(describeTestRunStatus("failed").label).toBe("Exécution en échec");
    expect(describeTestRunStatus("interrupted").label).toBe("Exécution interrompue");
    expect(describeTestRunStatus("timed_out").label).toBe("Délai d’exécution dépassé");
    expect(describeTestRunStatus("completed").tone).not.toBe(describeTestRunStatus("failed").tone);
  });
});
