/**
 * Tests du reporter Playwright (Lot E, §8).
 *
 * Aucun navigateur, aucun Playwright réel : les objets `TestCase`, `TestResult`,
 * `TestStep` et `FullConfig` sont synthétiques et reproduisent exactement la forme
 * documentée de l'interface Reporter.
 */

import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AcpPlaywrightReporter, {
  MAX_ANNOTATIONS,
  MAX_ATTACHMENTS,
  MAX_ERROR_CHARS,
  MAX_MESSAGE_CHARS,
  MAX_STEPS,
  MAX_SUITE_DEPTH,
  REPORT_FILE_ENV,
  TRUNCATION_MARKER,
  computeOutcome,
  relativeReportPath,
  relativizePaths,
  stripAnsi,
  truncate,
} from "../src/reporter";

// --- Fabriques d'objets Playwright synthétiques -------------------------------

interface FakeSuite {
  title: string;
  parent?: FakeSuite;
  project?: () => { name: string } | undefined;
}

function suiteChain(root: string, project: string, file: string): FakeSuite {
  const rootSuite: FakeSuite = { title: root };
  const projectSuite: FakeSuite = {
    title: project,
    parent: rootSuite,
    project: () => ({ name: project }),
  };
  return { title: file, parent: projectSuite };
}

interface FakeResult {
  retry: number;
  status: string;
  duration: number;
  error?: unknown;
  errors?: unknown[];
  attachments?: unknown[];
  steps?: unknown[];
  annotations?: unknown[];
}

interface FakeTest {
  id?: string;
  title: string;
  location?: { file: string; line: number; column: number };
  expectedStatus?: string;
  annotations?: unknown[];
  parent?: FakeSuite;
  results?: FakeResult[];
}

function makeTest(overrides: Partial<FakeTest> = {}): FakeTest {
  return {
    id: "suite-a-test-1",
    title: "affiche le tableau de bord",
    location: { file: "C:/projets/app/tests/dashboard.spec.ts", line: 12, column: 3 },
    expectedStatus: "passed",
    annotations: [],
    parent: suiteChain("", "chromium", "tests/dashboard.spec.ts"),
    ...overrides,
  };
}

function makeResult(overrides: Partial<FakeResult> = {}): FakeResult {
  return {
    retry: 0,
    status: "passed",
    duration: 1234.6,
    attachments: [],
    steps: [],
    ...overrides,
  };
}

function makeConfig(rootDir: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    version: "1.55.0",
    rootDir,
    workers: 4,
    projects: [{ name: "chromium", use: { baseURL: "https://app.example.test/base" } }],
    ...overrides,
  };
}

// --- Bac à sable ---------------------------------------------------------------

let sandbox: string;
let reportFile: string;
let previousEnv: string | undefined;

beforeEach(() => {
  sandbox = mkdtempSync(join(tmpdir(), "acp-reporter-"));
  reportFile = join(sandbox, "report.ndjson");
  previousEnv = process.env[REPORT_FILE_ENV];
  process.env[REPORT_FILE_ENV] = reportFile;
});

afterEach(() => {
  if (previousEnv === undefined) {
    delete process.env[REPORT_FILE_ENV];
  } else {
    process.env[REPORT_FILE_ENV] = previousEnv;
  }
  rmSync(sandbox, { recursive: true, force: true });
  vi.restoreAllMocks();
});

/** Crée un fichier de pièce jointe sous la racine de rapport et rend son chemin. */
function attachmentFile(relativePath: string, content = "octets"): string {
  const target = join(sandbox, ...relativePath.split("/"));
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, content);
  return target;
}

/** Vrai si la chaîne porte une demi-paire de substitution (UTF-16 invalide). */
function hasLoneSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) {
        return true;
      }
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return true;
    }
  }
  return false;
}

function readLines(): Record<string, any>[] {
  const raw = readFileSync(reportFile, "utf8");
  expect(raw.endsWith("\n")).toBe(true);
  return raw
    .split("\n")
    .filter((line) => line.length > 0)
    .map((line) => {
      expect(line.includes("\n")).toBe(false);
      return JSON.parse(line) as Record<string, any>;
    });
}

function runScenario(
  cases: Array<{ test: FakeTest; result: FakeResult }>,
  options: { config?: Record<string, unknown>; endStatus?: string } = {},
): Record<string, any>[] {
  const reporter = new AcpPlaywrightReporter();
  reporter.onBegin(options.config ?? makeConfig("C:/projets/app"), { title: "" });
  for (const entry of cases) {
    entry.test.results = [...(entry.test.results ?? []), entry.result];
    reporter.onTestBegin(entry.test, entry.result);
    reporter.onTestEnd(entry.test, entry.result);
  }
  reporter.onEnd({ status: options.endStatus ?? "passed" });
  return readLines();
}

// --- Fonctions pures -----------------------------------------------------------

describe("stripAnsi", () => {
  it("supprime les séquences de couleur et de curseur", () => {
    expect(stripAnsi("\u001B[31mrouge\u001B[39m")).toBe("rouge");
    expect(stripAnsi("\u001B[2K\u001B[1Gligne")).toBe("ligne");
    expect(stripAnsi("\u001B]8;;https://exemple\u0007lien\u001B]8;;\u0007")).toBe("lien");
  });

  it("laisse le texte ordinaire intact, accents compris", () => {
    expect(stripAnsi("échec attendu : « aucune assertion »")).toBe("échec attendu : « aucune assertion »");
  });
});

describe("truncate", () => {
  it("laisse une valeur courte intacte", () => {
    expect(truncate("court", 8000)).toBe("court");
  });

  it("borne et signale la troncature", () => {
    const value = "x".repeat(MAX_ERROR_CHARS + 500);
    const truncated = truncate(value, MAX_ERROR_CHARS);
    expect(truncated.length).toBe(MAX_ERROR_CHARS);
    expect(truncated.endsWith(TRUNCATION_MARKER)).toBe(true);
  });

  it("ne coupe jamais une paire de substitution en deux", () => {
    const value = `${"x".repeat(MAX_ERROR_CHARS - 12)}${"\u{1F4A5}".repeat(40)}`;
    const truncated = truncate(value, MAX_ERROR_CHARS);
    expect(truncated.length).toBeLessThanOrEqual(MAX_ERROR_CHARS);
    expect(hasLoneSurrogate(truncated), "demi-paire de substitution émise").toBe(false);
    expect(truncated.endsWith(TRUNCATION_MARKER)).toBe(true);
    // Encodage UTF-8 strict : une demi-paire deviendrait U+FFFD.
    expect(Buffer.from(truncated, "utf8").toString("utf8")).toBe(truncated);
  });
});

describe("relativizePaths", () => {
  it("rend relatifs les chemins sous la racine du projet, quels que soient les séparateurs", () => {
    const text = [
      "Error: boum",
      "    at C:/projets/app/tests/a.spec.ts:12:3",
      "    at C:\\projets\\app\\tests\\b.spec.ts:4:1",
    ].join("\n");
    const scrubbed = relativizePaths(text, "C:/projets/app");
    expect(scrubbed).toContain("tests/a.spec.ts:12:3");
    expect(scrubbed).toContain("b.spec.ts:4:1");
    expect(scrubbed).not.toContain("projets");
  });

  it("laisse le texte intact sans racine connue", () => {
    expect(relativizePaths("at C:/projets/app/tests/a.spec.ts:1:1", "")).toBe(
      "at C:/projets/app/tests/a.spec.ts:1:1",
    );
  });
});

describe("relativeReportPath", () => {
  it("rend un chemin POSIX relatif pour un fichier sous la racine", () => {
    expect(relativeReportPath("C:/sortie/test-results/a/capture.png", "C:/sortie")).toBe(
      "test-results/a/capture.png",
    );
  });

  it("refuse un chemin hors de la racine, y compris par remontée", () => {
    expect(relativeReportPath("C:/ailleurs/capture.png", "C:/sortie")).toBeNull();
    expect(relativeReportPath("C:/sortie/../ailleurs/capture.png", "C:/sortie")).toBeNull();
    expect(relativeReportPath("C:/sortie-bis/capture.png", "C:/sortie")).toBeNull();
  });

  it("refuse la racine elle-même", () => {
    expect(relativeReportPath("C:/sortie", "C:/sortie")).toBeNull();
  });
});

describe("computeOutcome", () => {
  it("classe un succès attendu et un échec inattendu", () => {
    const passed = makeResult({ status: "passed" });
    expect(computeOutcome(makeTest({ results: [passed] }), passed)).toBe("expected");
    const failed = makeResult({ status: "failed" });
    expect(computeOutcome(makeTest({ results: [failed] }), failed)).toBe("unexpected");
  });

  it("classe un échec attendu comme attendu", () => {
    const failed = makeResult({ status: "failed" });
    expect(computeOutcome(makeTest({ expectedStatus: "failed", results: [failed] }), failed)).toBe(
      "expected",
    );
  });

  it("classe une reprise réussie comme flaky", () => {
    const first = makeResult({ status: "failed", retry: 0 });
    const second = makeResult({ status: "passed", retry: 1 });
    const test = makeTest({ results: [first, second] });
    expect(computeOutcome(test, second)).toBe("flaky");
  });

  it("classe un test ignoré et un test interrompu sans résultat exploitable", () => {
    const skipped = makeResult({ status: "skipped" });
    expect(computeOutcome(makeTest({ results: [skipped] }), skipped)).toBe("skipped");
    const interrupted = makeResult({ status: "interrupted" });
    expect(computeOutcome(makeTest({ results: [interrupted] }), interrupted)).toBe("skipped");
  });
});

// --- Sortie NDJSON -------------------------------------------------------------

describe("sortie NDJSON", () => {
  it("écrit une ligne JSON valide par événement, sans tableau englobant", () => {
    const lines = runScenario([{ test: makeTest(), result: makeResult() }]);
    expect(lines.map((line) => line.kind)).toEqual(["run_begin", "test_end", "run_end"]);
  });

  it("décrit l'exécution sans divulguer l'environnement", () => {
    process.env.ACP_TEST_SECRET_PROBE = "valeur-tres-secrete";
    try {
      runScenario([{ test: makeTest(), result: makeResult() }]);
      const raw = readFileSync(reportFile, "utf8");
      expect(raw).not.toContain("valeur-tres-secrete");
      expect(raw).not.toContain("ACP_TEST_SECRET_PROBE");
    } finally {
      delete process.env.ACP_TEST_SECRET_PROBE;
    }
  });

  it("conserve la configuration utile et retire les identifiants de la base URL", () => {
    const config = makeConfig("C:/projets/app", {
      workers: 2,
      shard: { current: 1, total: 3 },
      projects: [
        { name: "chromium", use: { baseURL: "https://admin:motdepasse@app.example.test/base?jeton=x" } },
        { name: "firefox", use: {} },
      ],
    });
    const [begin] = runScenario([], { config });
    expect(begin.kind).toBe("run_begin");
    expect(typeof begin.started_at).toBe("string");
    expect(begin.runner_version).toBe("1.55.0");
    expect(begin.config.workers).toBe(2);
    expect(begin.config.shard).toEqual({ current: 1, total: 3 });
    expect(begin.config.projects).toEqual([
      { name: "chromium", base_url: "https://app.example.test/base" },
      { name: "firefox" },
    ]);
    expect(JSON.stringify(begin)).not.toContain("motdepasse");
    expect(JSON.stringify(begin)).not.toContain("jeton");
  });

  it("ajoute chaque ligne au fil de l'eau pour survivre à une interruption", () => {
    const reporter = new AcpPlaywrightReporter();
    reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
    const test = makeTest();
    const result = makeResult();
    test.results = [result];
    reporter.onTestEnd(test, result);
    // Pas de onEnd : le processus est « tué » ici.
    const lines = readLines();
    expect(lines.map((line) => line.kind)).toEqual(["run_begin", "test_end"]);
  });
});

// --- Statuts et issues ---------------------------------------------------------

describe("statuts", () => {
  it("conserve chaque statut brut avec son issue calculée", () => {
    const scenarios: Array<[string, string, string]> = [
      ["passed", "passed", "expected"],
      ["failed", "passed", "unexpected"],
      ["timedOut", "passed", "unexpected"],
      ["skipped", "passed", "skipped"],
      ["interrupted", "passed", "skipped"],
      ["failed", "failed", "expected"],
    ];
    for (const [status, expectedStatus, outcome] of scenarios) {
      const lines = runScenario([
        {
          test: makeTest({ id: `cas-${status}-${expectedStatus}`, expectedStatus }),
          result: makeResult({ status }),
        },
      ]);
      const testEnd = lines.find((line) => line.kind === "test_end");
      expect(testEnd, `statut ${status}`).toBeDefined();
      expect(testEnd!.status, `statut ${status}`).toBe(status);
      expect(testEnd!.outcome, `issue ${status}`).toBe(outcome);
      expect(testEnd!.expected_status).toBe(expectedStatus);
      rmSync(reportFile, { force: true });
    }
  });

  it("numérote les tentatives et marque la reprise réussie comme flaky", () => {
    const test = makeTest();
    const first = makeResult({ status: "failed", retry: 0 });
    const second = makeResult({ status: "passed", retry: 1 });
    const lines = runScenario([
      { test, result: first },
      { test, result: second },
    ]);
    const ends = lines.filter((line) => line.kind === "test_end");
    expect(ends).toHaveLength(2);
    expect(ends[0].attempt).toBe(1);
    expect(ends[0].status).toBe("failed");
    expect(ends[0].outcome).toBe("unexpected");
    expect(ends[1].attempt).toBe(2);
    expect(ends[1].status).toBe("passed");
    expect(ends[1].outcome).toBe("flaky");
    expect(ends[0].test_id).toBe(ends[1].test_id);
  });

  it("totalise les issues finales et compte les interruptions et dépassements à part", () => {
    const flakyTest = makeTest({ id: "flaky" });
    const lines = runScenario(
      [
        { test: makeTest({ id: "ok" }), result: makeResult({ status: "passed" }) },
        { test: makeTest({ id: "ko" }), result: makeResult({ status: "failed" }) },
        { test: makeTest({ id: "lent" }), result: makeResult({ status: "timedOut" }) },
        { test: makeTest({ id: "ignore" }), result: makeResult({ status: "skipped" }) },
        { test: makeTest({ id: "coupe" }), result: makeResult({ status: "interrupted" }) },
        { test: flakyTest, result: makeResult({ status: "failed", retry: 0 }) },
        { test: flakyTest, result: makeResult({ status: "passed", retry: 1 }) },
      ],
      { endStatus: "failed" },
    );
    const end = lines.find((line) => line.kind === "run_end")!;
    expect(end.run_status).toBe("failed");
    expect(typeof end.finished_at).toBe("string");
    expect(end.totals).toEqual({
      expected: 1,
      unexpected: 2,
      flaky: 1,
      skipped: 2,
      interrupted: 1,
      timedOut: 1,
    });
  });

  it("ne perd pas un échec derrière un test homonyme sans identifiant", () => {
    const suite = suiteChain("", "chromium", "tests/a.spec.ts");
    const ko = makeTest({ id: undefined, title: "cas homonyme", parent: suite });
    const ok = makeTest({ id: undefined, title: "cas homonyme", parent: suite });
    const lines = runScenario(
      [
        { test: ko, result: makeResult({ status: "failed" }) },
        { test: ok, result: makeResult({ status: "passed" }) },
      ],
      { endStatus: "failed" },
    );
    const ends = lines.filter((line) => line.kind === "test_end");
    expect(ends).toHaveLength(2);
    expect(ends[0].outcome).toBe("unexpected");
    expect(ends[1].outcome).toBe("expected");
    const end = lines.find((line) => line.kind === "run_end")!;
    expect(end.totals.unexpected, "l'échec ne doit pas être écrasé").toBe(1);
    expect(end.totals.expected).toBe(1);
  });

  it("traduit le statut global de Playwright en statut d'exécution", () => {
    for (const [playwright, expected] of [
      ["passed", "completed"],
      ["failed", "failed"],
      ["timedout", "timed_out"],
      ["interrupted", "interrupted"],
    ] as Array<[string, string]>) {
      const lines = runScenario([], { endStatus: playwright });
      expect(lines.find((line) => line.kind === "run_end")!.run_status).toBe(expected);
      rmSync(reportFile, { force: true });
    }
  });
});

// --- Identité, erreurs, étapes -------------------------------------------------

describe("contenu d'un test_end", () => {
  it("porte une identité stable et une localisation relative à la racine du projet", () => {
    const [, testEnd] = runScenario([{ test: makeTest(), result: makeResult() }]);
    expect(testEnd.test_id).toBe("suite-a-test-1");
    expect(testEnd.title).toBe("affiche le tableau de bord");
    expect(testEnd.project_name).toBe("chromium");
    expect(testEnd.suite_path).toEqual(["chromium", "tests/dashboard.spec.ts"]);
    expect(testEnd.location).toEqual({ file: "tests/dashboard.spec.ts", line: 12, column: 3 });
    expect(testEnd.duration_ms).toBe(1235);
  });

  it("ne divulgue pas l'arborescence du runner quand le fichier sort de la racine", () => {
    const test = makeTest({ location: { file: "D:/ailleurs/secret/dashboard.spec.ts", line: 1, column: 1 } });
    const [, testEnd] = runScenario([{ test, result: makeResult() }]);
    expect(testEnd.location).toEqual({ file: "dashboard.spec.ts", line: 1, column: 1 });
    expect(JSON.stringify(testEnd)).not.toContain("secret");
  });

  it("borne l'identité trop longue sans perdre son unicité", () => {
    const long = "a".repeat(400);
    const [, first] = runScenario([{ test: makeTest({ id: `${long}1` }), result: makeResult() }]);
    rmSync(reportFile, { force: true });
    const [, second] = runScenario([{ test: makeTest({ id: `${long}2` }), result: makeResult() }]);
    expect(first.test_id.length).toBeLessThanOrEqual(200);
    expect(second.test_id.length).toBeLessThanOrEqual(200);
    expect(first.test_id).not.toBe(second.test_id);
  });

  it("retombe sur le chemin de suite quand Playwright ne donne pas d'identifiant", () => {
    const [, testEnd] = runScenario([{ test: makeTest({ id: undefined }), result: makeResult() }]);
    expect(testEnd.test_id).toBe("chromium > tests/dashboard.spec.ts > affiche le tableau de bord");
  });

  it("expurge les séquences ANSI du message et de l'extrait d'erreur", () => {
    const result = makeResult({
      status: "failed",
      error: {
        message: "\u001B[31mExpected\u001B[39m 1 to be 2",
        snippet: "\u001B[2m  4 |\u001B[22m expect(1).toBe(2)",
      },
    });
    const [, testEnd] = runScenario([{ test: makeTest(), result }]);
    expect(testEnd.error_message).toBe("Expected 1 to be 2");
    expect(testEnd.error_snippet).toBe("  4 | expect(1).toBe(2)");
    expect(testEnd.error_message).not.toContain("\u001B");
  });

  it("tronque le message et l'extrait à la borne du contrat", () => {
    const result = makeResult({
      status: "failed",
      error: { message: "m".repeat(20000), snippet: "s".repeat(20000) },
    });
    const [, testEnd] = runScenario([{ test: makeTest(), result }]);
    expect(testEnd.error_message.length).toBe(MAX_ERROR_CHARS);
    expect(testEnd.error_snippet.length).toBe(MAX_ERROR_CHARS);
    expect(testEnd.error_message.endsWith(TRUNCATION_MARKER)).toBe(true);
  });

  it("tronque un texte non-BMP sans émettre de demi-paire de substitution", () => {
    const result = makeResult({
      status: "failed",
      error: {
        message: `${"m".repeat(MAX_ERROR_CHARS - 12)}${"\u{1F4A5}".repeat(40)}`,
        snippet: `${"s".repeat(MAX_ERROR_CHARS - 12)}${"\u{1F4A5}".repeat(40)}`,
      },
    });
    const test = makeTest({ title: `${"t".repeat(499)}\u{1F4A5}` });
    const [, testEnd] = runScenario([{ test, result }]);
    expect(hasLoneSurrogate(testEnd.error_message), "message").toBe(false);
    expect(hasLoneSurrogate(testEnd.error_snippet), "extrait").toBe(false);
    expect(hasLoneSurrogate(testEnd.title), "titre").toBe(false);
    const raw = readFileSync(reportFile, "utf8");
    expect(hasLoneSurrogate(raw)).toBe(false);
    // La ligne doit survivre à un encodage UTF-8 strict (Pydantic refuse le reste).
    expect(Buffer.from(raw, "utf8").toString("utf8")).toBe(raw);
  });

  it("rend relatifs les chemins du runner portés par le message et la pile", () => {
    const result = makeResult({
      status: "failed",
      errors: [
        {
          message: "Error: expect(locator).toHaveText à C:/projets/app/tests/dashboard.spec.ts",
          stack: "Error: boum\n    at C:\\projets\\app\\tests\\dashboard.spec.ts:12:3",
        },
      ],
    });
    const lines = runScenario([{ test: makeTest(), result }], {
      config: makeConfig("C:/projets/app"),
    });
    const testEnd = lines.find((line) => line.kind === "test_end")!;
    expect(testEnd.error_message).toContain("tests/dashboard.spec.ts");
    expect(testEnd.error_snippet).toContain("dashboard.spec.ts:12:3");
    const raw = readFileSync(reportFile, "utf8");
    expect(raw, "l'arborescence du runner ne doit pas être décrite").not.toContain("projets");
  });

  it("rend relatifs les chemins du runner portés par une erreur globale", () => {
    const reporter = new AcpPlaywrightReporter();
    reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
    reporter.onError({ message: "Error: boum\n    at C:/projets/app/tests/a.spec.ts:1:1" });
    const [, error] = readLines();
    expect(error.kind).toBe("error");
    expect(error.message).toContain("tests/a.spec.ts:1:1");
    expect(error.message).not.toContain("projets");
  });

  it("agrège plusieurs erreurs et retombe sur la pile sans extrait", () => {
    const result = makeResult({
      status: "failed",
      errors: [{ message: "première" }, { message: "seconde", stack: "at quelque-part" }],
    });
    const [, testEnd] = runScenario([{ test: makeTest(), result }]);
    expect(testEnd.error_message).toBe("première\n\nseconde");
    expect(testEnd.error_snippet).toBe("at quelque-part");
  });

  it("laisse message et extrait vides pour un succès", () => {
    const [, testEnd] = runScenario([{ test: makeTest(), result: makeResult() }]);
    expect(testEnd.error_message).toBe("");
    expect(testEnd.error_snippet).toBe("");
  });

  it("enregistre les étapes vues par les hooks, avec leur erreur", () => {
    const reporter = new AcpPlaywrightReporter();
    reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
    const test = makeTest();
    const result = makeResult({ status: "failed" });
    test.results = [result];
    reporter.onTestBegin(test, result);
    const step = { title: "ouvre la page", category: "test.step", duration: 42.2 };
    reporter.onStepBegin(test, result, step);
    reporter.onStepEnd(test, result, step);
    const failing = { title: "expect(locator)", category: "expect", duration: 8, error: { message: "ko" } };
    reporter.onStepBegin(test, result, failing);
    reporter.onStepEnd(test, result, failing);
    reporter.onTestEnd(test, result);
    reporter.onEnd({ status: "failed" });
    const [, testEnd] = readLines();
    expect(testEnd.steps).toEqual([
      { title: "ouvre la page", category: "test.step", duration_ms: 42, error: false },
      { title: "expect(locator)", category: "expect", duration_ms: 8, error: true },
    ]);
  });

  it("borne les étapes à la limite du contrat", () => {
    const reporter = new AcpPlaywrightReporter();
    reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
    const test = makeTest();
    const result = makeResult();
    test.results = [result];
    reporter.onTestBegin(test, result);
    for (let index = 0; index < MAX_STEPS + 50; index += 1) {
      const step = { title: `étape ${index}`, category: "pw:api", duration: 1 };
      reporter.onStepBegin(test, result, step);
      reporter.onStepEnd(test, result, step);
    }
    reporter.onTestEnd(test, result);
    const [, testEnd] = readLines();
    expect(testEnd.steps).toHaveLength(MAX_STEPS);
    expect(testEnd.steps[0].title).toBe("étape 0");
  });

  it("retombe sur les étapes du résultat, imbriquées comprises, sans les hooks", () => {
    const result = makeResult({
      steps: [
        {
          title: "parent",
          category: "test.step",
          duration: 10,
          steps: [{ title: "enfant", category: "pw:api", duration: 3, error: { message: "ko" } }],
        },
      ],
    });
    const [, testEnd] = runScenario([{ test: makeTest(), result }]);
    expect(testEnd.steps).toEqual([
      { title: "parent", category: "test.step", duration_ms: 10, error: false },
      { title: "enfant", category: "pw:api", duration_ms: 3, error: true },
    ]);
  });

  it("isole les étapes de chaque tentative", () => {
    const reporter = new AcpPlaywrightReporter();
    reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
    const test = makeTest();
    const first = makeResult({ status: "failed", retry: 0 });
    test.results = [first];
    reporter.onTestBegin(test, first);
    reporter.onStepEnd(test, first, { title: "première", category: "test.step", duration: 1 });
    reporter.onTestEnd(test, first);
    const second = makeResult({ status: "passed", retry: 1 });
    test.results = [first, second];
    reporter.onTestBegin(test, second);
    reporter.onStepEnd(test, second, { title: "seconde", category: "test.step", duration: 1 });
    reporter.onTestEnd(test, second);
    const ends = readLines().filter((line) => line.kind === "test_end");
    expect(ends[0].steps.map((step: any) => step.title)).toEqual(["première"]);
    expect(ends[1].steps.map((step: any) => step.title)).toEqual(["seconde"]);
  });

  it("normalise et borne les annotations", () => {
    const annotations = Array.from({ length: MAX_ANNOTATIONS + 10 }, (_value, index) => ({
      type: "issue",
      description: `\u001B[31mticket ${index}\u001B[39m`,
    }));
    const [, testEnd] = runScenario([{ test: makeTest({ annotations }), result: makeResult() }]);
    expect(testEnd.annotations).toHaveLength(MAX_ANNOTATIONS);
    expect(testEnd.annotations[0]).toEqual({ type: "issue", description: "ticket 0" });
  });

  it("borne la profondeur du chemin de suite", () => {
    let suite: FakeSuite = { title: "racine-0" };
    for (let index = 1; index < MAX_SUITE_DEPTH + 15; index += 1) {
      suite = { title: `niveau-${index}`, parent: suite };
    }
    const [, testEnd] = runScenario([{ test: makeTest({ parent: suite }), result: makeResult() }]);
    expect(testEnd.suite_path).toHaveLength(MAX_SUITE_DEPTH);
    expect(testEnd.suite_path[0]).toBe("racine-0");
  });
});

// --- Pièces jointes ------------------------------------------------------------

describe("pièces jointes", () => {
  it("rend un chemin relatif à la racine de sortie", () => {
    const nested = join(sandbox, "test-results", "dashboard");
    mkdirSync(nested, { recursive: true });
    const file = join(nested, "capture.png");
    writeFileSync(file, "png");
    const result = makeResult({
      status: "failed",
      attachments: [{ name: "screenshot", contentType: "image/png", path: file }],
    });
    const [, testEnd] = runScenario([{ test: makeTest(), result }]);
    expect(testEnd.attachments).toEqual([
      {
        name: "screenshot",
        content_type: "image/png",
        path: "test-results/dashboard/capture.png",
      },
    ]);
  });

  it("signale une pièce jointe en mémoire au lieu d'embarquer un corps que le contrat refuse", () => {
    const body = Buffer.from('{"clé":"valeur"}', "utf8");
    const result = makeResult({
      attachments: [{ name: "diagnostic", contentType: "application/json", body }],
    });
    const lines = runScenario([{ test: makeTest(), result }]);
    const testEnd = lines.find((line) => line.kind === "test_end")!;
    expect(testEnd.attachments).toEqual([]);
    const warning = lines.find((line) => line.kind === "error")!;
    expect(warning.message).toContain("diagnostic");
    expect(warning.message).toContain("suite-a-test-1");
    const raw = readFileSync(reportFile, "utf8");
    expect(raw, "le contrat d'ingestion refuse body_base64").not.toContain("body_base64");
    expect(raw).not.toContain(body.toString("base64"));
  });

  it("signale sans recopier une pièce jointe hors de la racine de sortie", () => {
    const outside = mkdtempSync(join(tmpdir(), "acp-hors-"));
    const file = join(outside, "trace.zip");
    writeFileSync(file, "zip");
    try {
      const result = makeResult({
        status: "failed",
        attachments: [{ name: "trace", contentType: "application/zip", path: file }],
      });
      const lines = runScenario([{ test: makeTest(), result }]);
      const testEnd = lines.find((line) => line.kind === "test_end")!;
      expect(testEnd.attachments).toEqual([]);
      const warning = lines.find((line) => line.kind === "error");
      expect(warning).toBeDefined();
      expect(warning!.message).toContain("trace");
      expect(warning!.message).toContain("suite-a-test-1");
      const raw = readFileSync(reportFile, "utf8");
      expect(raw).not.toContain(outside.replace(/\\/g, "/"));
      expect(raw).not.toContain(JSON.stringify(file).slice(1, -1));
    } finally {
      rmSync(outside, { recursive: true, force: true });
    }
  });

  it("refuse un corps en mémoire sans perdre les pièces jointes avec fichier", () => {
    const result = makeResult({
      attachments: [
        { name: "video", contentType: "video/webm", body: Buffer.alloc(4096, 0x61) },
        { name: "note", contentType: "text/plain", path: attachmentFile("test-results/note.txt") },
      ],
    });
    const lines = runScenario([{ test: makeTest(), result }]);
    const testEnd = lines.find((line) => line.kind === "test_end")!;
    expect(testEnd.attachments.map((item: any) => item.name)).toEqual(["note"]);
    expect(testEnd.attachments[0].path).toBe("test-results/note.txt");
    const warning = lines.find((line) => line.kind === "error")!;
    expect(warning.message).toContain("video");
  });

  it("signale une pièce jointe sans chemin ni corps", () => {
    const result = makeResult({ attachments: [{ name: "vide", contentType: "text/plain" }] });
    const lines = runScenario([{ test: makeTest(), result }]);
    expect(lines.find((line) => line.kind === "test_end")!.attachments).toEqual([]);
    expect(lines.find((line) => line.kind === "error")!.message).toContain("vide");
  });

  it("borne le nombre de pièces jointes", () => {
    const attachments = Array.from({ length: MAX_ATTACHMENTS + 5 }, (_value, index) => ({
      name: `note-${index}`,
      contentType: "text/plain",
      path: attachmentFile(`test-results/note-${index}.txt`, `${index}`),
    }));
    const result = makeResult({ attachments });
    const [, testEnd] = runScenario([{ test: makeTest(), result }]);
    expect(testEnd.attachments).toHaveLength(MAX_ATTACHMENTS);
  });

  it("applique un type par défaut quand Playwright n'en donne pas", () => {
    const result = makeResult({
      attachments: [{ name: "brut", path: attachmentFile("test-results/brut.bin") }],
    });
    const [, testEnd] = runScenario([{ test: makeTest(), result }]);
    expect(testEnd.attachments[0].content_type).toBe("application/octet-stream");
  });

  it("ne publie jamais une pièce jointe sans chemin", () => {
    const result = makeResult({
      status: "failed",
      attachments: [
        { name: "capture", contentType: "image/png", path: attachmentFile("test-results/c.png") },
        { name: "memoire", contentType: "text/plain", body: Buffer.from("ok", "utf8") },
        { name: "vide", contentType: "text/plain" },
      ],
    });
    const lines = runScenario([{ test: makeTest(), result }]);
    const testEnd = lines.find((line) => line.kind === "test_end")!;
    for (const attachment of testEnd.attachments as Record<string, unknown>[]) {
      expect(typeof attachment.path, "le contrat exige un chemin").toBe("string");
      expect(attachment.path).not.toBe("");
    }
    expect(lines.filter((line) => line.kind === "error")).toHaveLength(2);
  });
});

// --- Compatibilité avec le contrat d'ingestion ---------------------------------

/** Champs de `acp_contracts.testing.ReporterEvent` (`extra="forbid"`). */
const REPORTER_EVENT_FIELDS = new Set([
  "kind",
  "started_at",
  "runner_version",
  "config",
  "test_id",
  "title",
  "suite_path",
  "location",
  "project_name",
  "attempt",
  "expected_status",
  "status",
  "outcome",
  "duration_ms",
  "error_message",
  "error_snippet",
  "steps",
  "annotations",
  "attachments",
  "finished_at",
  "totals",
  "run_status",
  "exit_code",
  "report_path",
  "message",
]);

/** Champs de `ReporterAttachment` (`extra="forbid"`, `path` obligatoire). */
const REPORTER_ATTACHMENT_FIELDS = new Set(["name", "content_type", "path", "sha256", "size_bytes"]);

const TEST_STEP_FIELDS = new Set(["title", "category", "duration_ms", "error"]);
const TEST_TOTALS_FIELDS = new Set([
  "expected",
  "unexpected",
  "flaky",
  "skipped",
  "interrupted",
  "timedOut",
]);

describe("compatibilité du contrat d'ingestion", () => {
  it("n'émet aucun champ hors du contrat ReporterEvent", () => {
    const file = join(sandbox, "test-results", "capture.png");
    mkdirSync(join(sandbox, "test-results"), { recursive: true });
    writeFileSync(file, "png");
    const test = makeTest({ annotations: [{ type: "issue", description: "ACP-1" }] });
    const result = makeResult({
      status: "failed",
      error: { message: "ko", snippet: "12 | expect" },
      steps: [{ title: "étape", category: "expect", duration: 4 }],
      attachments: [{ name: "capture", contentType: "image/png", path: file }],
    });
    const reporter = new AcpPlaywrightReporter();
    reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
    test.results = [result];
    reporter.onTestBegin(test, result);
    reporter.onTestEnd(test, result);
    reporter.onError({ message: "boum" });
    reporter.onEnd({ status: "failed" });

    const lines = readLines();
    expect(lines).toHaveLength(4);
    for (const line of lines) {
      for (const key of Object.keys(line)) {
        expect(REPORTER_EVENT_FIELDS.has(key), `champ inattendu « ${key} »`).toBe(true);
      }
      for (const attachment of (line.attachments ?? []) as Record<string, unknown>[]) {
        for (const key of Object.keys(attachment)) {
          expect(REPORTER_ATTACHMENT_FIELDS.has(key), `pièce jointe « ${key} »`).toBe(true);
        }
        expect(typeof attachment.path, "« path » est obligatoire au contrat").toBe("string");
      }
      for (const step of (line.steps ?? []) as Record<string, unknown>[]) {
        expect(new Set(Object.keys(step))).toEqual(TEST_STEP_FIELDS);
      }
      if (line.totals) {
        expect(new Set(Object.keys(line.totals))).toEqual(TEST_TOTALS_FIELDS);
      }
    }
  });

  it("respecte les bornes de longueur du contrat", () => {
    const test = makeTest({
      id: "x".repeat(500),
      title: "t".repeat(900),
      annotations: [{ type: "y".repeat(300), description: "d".repeat(900) }],
    });
    const result = makeResult({
      status: "failed",
      error: { message: "m".repeat(20000), snippet: "s".repeat(20000) },
      attachments: [
        {
          name: "n".repeat(400),
          contentType: "c".repeat(400),
          path: attachmentFile("test-results/borne.bin"),
        },
      ],
    });
    const [, testEnd] = runScenario([{ test, result }]);
    expect(testEnd.test_id.length).toBeLessThanOrEqual(200);
    expect(testEnd.title.length).toBeLessThanOrEqual(500);
    expect(testEnd.expected_status.length).toBeLessThanOrEqual(20);
    expect(testEnd.error_message.length).toBeLessThanOrEqual(MAX_ERROR_CHARS);
    expect(testEnd.error_snippet.length).toBeLessThanOrEqual(MAX_ERROR_CHARS);
    expect(testEnd.annotations[0].type.length).toBeLessThanOrEqual(100);
    expect(testEnd.annotations[0].description.length).toBeLessThanOrEqual(500);
    expect(testEnd.attachments[0].name.length).toBeLessThanOrEqual(200);
    expect(testEnd.attachments[0].content_type.length).toBeLessThanOrEqual(200);
  });

  it("ne produit jamais de chemin absolu ni de remontée dans une pièce jointe", () => {
    const nested = join(sandbox, "a", "b");
    mkdirSync(nested, { recursive: true });
    const file = join(nested, "video.webm");
    writeFileSync(file, "webm");
    const result = makeResult({
      attachments: [{ name: "video", contentType: "video/webm", path: file }],
    });
    const [, testEnd] = runScenario([{ test: makeTest(), result }]);
    const path = testEnd.attachments[0].path as string;
    expect(path).toBe("a/b/video.webm");
    expect(path.startsWith("/")).toBe(false);
    expect(path.includes("..")).toBe(false);
    expect(path.includes("\\")).toBe(false);
    expect(path.slice(1, 2)).not.toBe(":");
  });
});

// --- Erreurs globales et robustesse -------------------------------------------

describe("robustesse", () => {
  it("écrit une ligne d'erreur globale bornée", () => {
    const reporter = new AcpPlaywrightReporter();
    reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
    reporter.onError({ message: `\u001B[31m${"e".repeat(MAX_MESSAGE_CHARS + 500)}\u001B[39m` });
    const [, error] = readLines();
    expect(error.kind).toBe("error");
    expect(error.message.length).toBe(MAX_MESSAGE_CHARS);
    expect(error.message).not.toContain("\u001B");
  });

  it("avertit une seule fois sur stderr et n'écrit rien sans ACP_REPORT_FILE", () => {
    delete process.env[REPORT_FILE_ENV];
    const stderr = vi.spyOn(process.stderr, "write").mockReturnValue(true);
    const reporter = new AcpPlaywrightReporter();
    const test = makeTest();
    const result = makeResult();
    test.results = [result];
    expect(() => {
      reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
      reporter.onTestBegin(test, result);
      reporter.onTestEnd(test, result);
      reporter.onError({ message: "boum" });
      reporter.onEnd({ status: "passed" });
    }).not.toThrow();
    expect(stderr).toHaveBeenCalledTimes(1);
    const [message] = stderr.mock.calls[0] as [string];
    expect(message).toContain(REPORT_FILE_ENV);
    expect(message.endsWith("\n")).toBe(true);
    expect(message.split("\n").filter((part) => part.length > 0)).toHaveLength(1);
  });

  it("n'échoue jamais l'exécution quand le fichier de rapport est inaccessible", () => {
    process.env[REPORT_FILE_ENV] = join(sandbox, "absent", "report.ndjson");
    const stderr = vi.spyOn(process.stderr, "write").mockReturnValue(true);
    const reporter = new AcpPlaywrightReporter();
    const test = makeTest();
    const result = makeResult();
    test.results = [result];
    expect(() => {
      reporter.onBegin(makeConfig("C:/projets/app"), { title: "" });
      reporter.onTestEnd(test, result);
      reporter.onEnd({ status: "passed" });
    }).not.toThrow();
    expect(stderr).toHaveBeenCalledTimes(1);
  });

  it("survit à des objets Playwright incomplets", () => {
    const reporter = new AcpPlaywrightReporter();
    expect(() => {
      reporter.onBegin({} as never, { title: "" } as never);
      reporter.onTestEnd({ title: "sans parent" } as never, { status: "passed" } as never);
      reporter.onEnd({} as never);
    }).not.toThrow();
    const lines = readLines();
    const testEnd = lines.find((line) => line.kind === "test_end")!;
    expect(testEnd.status).toBe("passed");
    expect(testEnd.attempt).toBe(1);
    expect(testEnd.suite_path).toEqual([]);
    expect(lines.find((line) => line.kind === "run_end")!.run_status).toBe("failed");
  });

  it("normalise un statut inconnu sans jamais inventer un succès", () => {
    const [, testEnd] = runScenario([
      { test: makeTest(), result: makeResult({ status: "quelque-chose" }) },
    ]);
    expect(testEnd.status).toBe("failed");
    expect(testEnd.outcome).toBe("unexpected");
  });

  it("déclare ne rien écrire sur la sortie standard", () => {
    const reporter = new AcpPlaywrightReporter();
    expect(reporter.printsToStdio()).toBe(false);
  });

  it("ne contient ni appel réseau ni autre lecture de l'environnement", () => {
    const source = readFileSync(new URL("../src/reporter.ts", import.meta.url), "utf8");
    for (const forbidden of [
      "node:http",
      "node:https",
      "node:net",
      "node:dgram",
      "node:child_process",
      "fetch(",
      "XMLHttpRequest",
      "WebSocket",
      "writeFileSync",
      "mkdirSync",
    ]) {
      expect(source.includes(forbidden), `motif interdit « ${forbidden} »`).toBe(false);
    }
    expect(source.split("process.env").length - 1).toBe(1);
    expect(source.includes("process.env[REPORT_FILE_ENV]")).toBe(true);
  });
});
