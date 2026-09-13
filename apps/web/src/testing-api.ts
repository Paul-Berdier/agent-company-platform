/**
 * Client des résultats de tests structurés d’une tentative (spec Lot E §10).
 *
 * `GET /runs/{run_id}/test-run` renvoie un `TestRunDetail` : exécution, totaux, cas,
 * étapes, pièces jointes et rapport. Deux règles non négociables :
 *
 * 1. **aucun statut n’est réduit à vert/rouge** — `passed`, `failed`, `timedOut`,
 *    `skipped`, `interrupted` et le caractère `flaky` restent distincts dans les
 *    libellés comme dans les tonalités ;
 * 2. **aucun rendu partiel** — une réponse hors contrat (statut inconnu, totaux
 *    incomplets, pièce jointe mal formée) est refusée entièrement : afficher la moitié
 *    d’un rapport de tests reviendrait à mentir sur ce qui a été exécuté.
 *
 * Le client HTTP est fourni par le shell (règle du Lot D) : ce module n’en crée jamais
 * un et ne lit jamais `/auth/session`.
 */

import type {
  ArtifactSummary,
  TestCaseResult,
  TestRunDetail,
  TestRunStatus,
  TestStep,
  TestTotals,
} from "@acp/contracts";

import { WorkspaceApiError, WorkspaceHttpClient, isRecord } from "./workspace-api";

const TEST_STATUSES = new Set(["passed", "failed", "timedOut", "skipped", "interrupted"]);
const TEST_OUTCOMES = new Set(["expected", "unexpected", "flaky", "skipped"]);
const TEST_RUN_STATUSES = new Set(["running", "completed", "failed", "interrupted", "timed_out"]);
const TOTALS_KEYS = ["expected", "unexpected", "flaky", "skipped", "interrupted", "timedOut"] as const;

// --- Validateurs stricts -------------------------------------------------------

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNullableInteger(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isInteger(value));
}

function isInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

/**
 * Forme d’un livrable telle que publiée par l’API. La clé de stockage n’existe pas dans
 * le contrat : `has_content` est la seule information sur la présence d’octets.
 */
export function isArtifactSummary(value: unknown): value is ArtifactSummary {
  if (!isRecord(value)) return false;
  return typeof value.id === "string"
    && typeof value.project_id === "string"
    && typeof value.task_run_id === "string"
    && typeof value.kind === "string"
    && typeof value.stream_kind === "string"
    && typeof value.original_name === "string"
    && typeof value.content_type === "string"
    && isNullableInteger(value.size_bytes)
    && isNullableString(value.checksum)
    && typeof value.source === "string"
    && typeof value.has_content === "boolean"
    && isNullableString(value.created_at);
}

function isTestStep(value: unknown): value is TestStep {
  if (!isRecord(value)) return false;
  return typeof value.title === "string"
    && typeof value.category === "string"
    && isInteger(value.duration_ms)
    && typeof value.error === "boolean";
}

function isTestTotals(value: unknown): value is TestTotals {
  if (!isRecord(value)) return false;
  return TOTALS_KEYS.every((key) => isInteger(value[key]));
}

export function isTestCaseResult(value: unknown): value is TestCaseResult {
  if (!isRecord(value)) return false;
  return typeof value.id === "string"
    && typeof value.test_run_id === "string"
    && Array.isArray(value.suite_path)
    && value.suite_path.every((item) => typeof item === "string")
    && typeof value.title === "string"
    && typeof value.test_id === "string"
    && isRecord(value.location)
    && typeof value.project_name === "string"
    && isInteger(value.attempt)
    && typeof value.expected_status === "string"
    && typeof value.status === "string"
    && TEST_STATUSES.has(value.status)
    && typeof value.outcome === "string"
    && TEST_OUTCOMES.has(value.outcome)
    && isInteger(value.duration_ms)
    && typeof value.error_message === "string"
    && typeof value.error_snippet === "string"
    && Array.isArray(value.steps)
    && value.steps.every(isTestStep)
    && Array.isArray(value.annotations)
    && value.annotations.every(isRecord)
    && Array.isArray(value.attachments)
    && value.attachments.every(isArtifactSummary);
}

export function isTestRunDetail(value: unknown): value is TestRunDetail {
  if (!isRecord(value)) return false;
  return typeof value.id === "string"
    && typeof value.task_run_id === "string"
    && typeof value.project_id === "string"
    && isNullableString(value.worker_id)
    && typeof value.runner === "string"
    && typeof value.runner_version === "string"
    && typeof value.status === "string"
    && TEST_RUN_STATUSES.has(value.status)
    && typeof value.started_at === "string"
    && isNullableString(value.finished_at)
    && isNullableInteger(value.duration_ms)
    && isTestTotals(value.totals)
    && isNullableInteger(value.exit_code)
    && isRecord(value.config)
    && isInteger(value.case_count)
    && Array.isArray(value.cases)
    && value.cases.every(isTestCaseResult)
    && (value.report_artifact === null || isArtifactSummary(value.report_artifact));
}

// --- Client --------------------------------------------------------------------

export class TestingApiClient {
  constructor(private readonly http: WorkspaceHttpClient) {}

  /** Résultat de tests de la tentative. 404 signifie « aucun », pas « erreur ». */
  fetchTestRun(runId: string): Promise<TestRunDetail> {
    return this.http.request(`/runs/${encodeURIComponent(runId)}/test-run`, isTestRunDetail);
  }
}

/**
 * Vrai lorsque l’API a répondu « aucun résultat de test » (404). À distinguer d’un refus
 * d’accès ou d’une panne : l’interface affiche un état vide, pas une erreur.
 */
export function isMissingTestRun(error: unknown): boolean {
  return error instanceof WorkspaceApiError && error.status === 404;
}

// --- Arbre des tests -----------------------------------------------------------

export interface TestSuiteNode {
  title: string;
  /** Chemin complet depuis la racine, pour un identifiant stable côté DOM. */
  path: string[];
  suites: TestSuiteNode[];
  cases: TestCaseResult[];
  /** Cas de cette suite et de ses sous-suites. */
  caseCount: number;
  /** Cas au résultat inattendu (sous-suites comprises) : jamais masqué par un total. */
  unexpectedCount: number;
}

const ORPHAN_SUITE_TITLE = "Sans suite";

/**
 * Clé d’indexation d’une suite : la sérialisation JSON du chemin. Aucun séparateur
 * « magique » n’est employé — un titre de suite vient du rapport et peut contenir
 * n’importe quel caractère, y compris celui qu’on aurait choisi comme séparateur.
 */
function suiteKey(path: readonly string[]): string {
  return JSON.stringify(path);
}

function emptyNode(title: string, path: string[]): TestSuiteNode {
  return { title, path, suites: [], cases: [], caseCount: 0, unexpectedCount: 0 };
}

/**
 * Regroupe les cas par `suite_path` en conservant l’ordre d’apparition (celui du
 * rapport). Les cas sans suite sont rassemblés sous une racine explicite plutôt que
 * dispersés : rien n’est masqué.
 */
export function buildTestTree(cases: readonly TestCaseResult[]): TestSuiteNode[] {
  const roots: TestSuiteNode[] = [];
  const index = new Map<string, TestSuiteNode>();

  for (const item of cases) {
    const segments = item.suite_path.length ? item.suite_path : [ORPHAN_SUITE_TITLE];
    let siblings = roots;
    let node: TestSuiteNode | null = null;
    const path: string[] = [];
    for (const segment of segments) {
      path.push(segment);
      const key = suiteKey(path);
      let child = index.get(key);
      if (!child) {
        child = emptyNode(segment, [...path]);
        index.set(key, child);
        siblings.push(child);
      }
      node = child;
      siblings = child.suites;
    }
    if (!node) continue;
    node.cases.push(item);
    const unexpected = item.outcome === "unexpected" ? 1 : 0;
    for (let depth = 1; depth <= path.length; depth += 1) {
      const ancestor = index.get(suiteKey(path.slice(0, depth)));
      if (!ancestor) continue;
      ancestor.caseCount += 1;
      ancestor.unexpectedCount += unexpected;
    }
  }
  return roots;
}

// --- Libellés ------------------------------------------------------------------

/**
 * Libellé et tonalité d’un cas. L’ordre des tests compte : `flaky` l’emporte sur le
 * statut final, sinon un cas rejoué avec succès apparaîtrait comme un simple succès.
 */
export function testCaseBadge(item: TestCaseResult): { label: string; tone: string } {
  if (item.outcome === "flaky") return { label: "Instable (flaky)", tone: "waiting" };
  switch (item.status) {
    case "skipped":
      return { label: "Ignoré", tone: "waiting" };
    case "timedOut":
      return { label: "Délai dépassé", tone: "failed" };
    case "interrupted":
      return { label: "Interrompu", tone: "failed" };
    case "failed":
      return item.outcome === "expected"
        ? { label: "Échec attendu", tone: "waiting" }
        : { label: "Échec", tone: "failed" };
    default:
      return item.outcome === "unexpected"
        ? { label: "Réussi alors qu’un échec était attendu", tone: "waiting" }
        : { label: "Réussi", tone: "done" };
  }
}

function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${Math.abs(count) > 1 ? pluralForm : singular}`;
}

/** Résumé listant les six compteurs, y compris ceux à zéro : rien n’est masqué. */
export function summarizeTestTotals(totals: TestTotals): string {
  return [
    plural(totals.expected, "attendu", "attendus"),
    plural(totals.unexpected, "inattendu", "inattendus"),
    plural(totals.flaky, "instable", "instables"),
    plural(totals.skipped, "ignoré", "ignorés"),
    plural(totals.interrupted, "interrompu", "interrompus"),
    plural(totals.timedOut, "délai dépassé", "délais dépassés"),
  ].join(" · ");
}

/** Durée lisible. Une valeur absente ou aberrante reste « inconnue », jamais « 0 ». */
export function formatTestDuration(durationMs: number | null): string {
  if (durationMs === null || !Number.isFinite(durationMs) || durationMs < 0) return "Durée inconnue";
  if (durationMs < 1_000) return `${Math.round(durationMs)} ms`;
  if (durationMs < 60_000) return `${(durationMs / 1_000).toFixed(1).replace(".", ",")} s`;
  const minutes = Math.floor(durationMs / 60_000);
  const seconds = Math.round((durationMs % 60_000) / 1_000);
  return `${minutes} min ${seconds} s`;
}

export function describeTestRunStatus(status: TestRunStatus): { label: string; tone: string } {
  switch (status) {
    case "running":
      return { label: "Exécution en cours", tone: "in_progress" };
    case "completed":
      return { label: "Exécution terminée", tone: "done" };
    case "interrupted":
      return { label: "Exécution interrompue", tone: "failed" };
    case "timed_out":
      return { label: "Délai d’exécution dépassé", tone: "failed" };
    default:
      return { label: "Exécution en échec", tone: "failed" };
  }
}
