/**
 * Reporter Playwright de la plateforme (Lot E, §8).
 *
 * Ce paquet n'a **aucune dépendance** : il implémente l'interface `Reporter` de
 * Playwright par sa forme, sans importer `@playwright/test`. Playwright reste
 * installé sur le runner, jamais par la plateforme.
 *
 * Le reporter n'effectue **aucun appel réseau** et ne transporte **aucun
 * credential** : il écrit un NDJSON local dans le fichier désigné par
 * `ACP_REPORT_FILE`, une ligne par événement, en ajout synchrone pour survivre à
 * une interruption du processus de test. C'est le worker authentifié qui lit ce
 * fichier, téléverse les pièces jointes et publie les événements avec sa propre
 * identité.
 *
 * Il ne lit de l'environnement que `ACP_REPORT_FILE`, ne journalise ni les
 * variables d'environnement ni la sortie standard des tests, et n'écrit rien
 * d'autre que ses lignes NDJSON.
 *
 * Les statuts bruts de Playwright (`passed`, `failed`, `timedOut`, `skipped`,
 * `interrupted`) sont conservés tels quels, à côté de l'issue calculée
 * (`expected`, `unexpected`, `flaky`, `skipped`) : rien n'est réduit à
 * « vert / rouge ».
 */

import { createHash } from "node:crypto";
import { appendFileSync } from "node:fs";
import { basename, dirname, isAbsolute, relative, resolve, sep } from "node:path";

/** Variable d'environnement désignant le fichier NDJSON à écrire. */
export const REPORT_FILE_ENV = "ACP_REPORT_FILE";

/** Bornes alignées sur `acp_contracts.testing` (contrat d'ingestion). */
export const MAX_ERROR_CHARS = 8000;
export const MAX_MESSAGE_CHARS = 2000;
export const MAX_STEPS = 200;
export const MAX_ANNOTATIONS = 50;
export const MAX_ATTACHMENTS = 50;
export const MAX_SUITE_DEPTH = 20;

/** Marque ajoutée en fin de valeur tronquée (comprise dans la borne). */
export const TRUNCATION_MARKER = "\n…[tronqué]";

const MAX_TEST_ID_CHARS = 200;
const MAX_TITLE_CHARS = 500;
const MAX_CATEGORY_CHARS = 50;
const MAX_NAME_CHARS = 200;
const MAX_CONTENT_TYPE_CHARS = 200;
const MAX_VERSION_CHARS = 50;
const MAX_STATUS_CHARS = 20;
const MAX_ANNOTATION_TYPE_CHARS = 100;
const MAX_ANNOTATION_DESCRIPTION_CHARS = 500;
const MAX_BASE_URL_CHARS = 200;
const MAX_PATH_CHARS = 1000;
const MAX_PROJECTS = 50;
const MAX_WALK_DEPTH = 200;

const DEFAULT_CONTENT_TYPE = "application/octet-stream";

/** Statut brut d'une tentative, tel que Playwright le rapporte. */
export type TestStatus = "passed" | "failed" | "timedOut" | "skipped" | "interrupted";

/** Issue calculée d'un test, au sens de Playwright. */
export type TestOutcome = "expected" | "unexpected" | "flaky" | "skipped";

/** Statut d'une exécution complète, au sens du contrat `TestRunStatus`. */
export type TestRunStatus = "running" | "completed" | "failed" | "interrupted" | "timed_out";

const TEST_STATUSES: readonly TestStatus[] = [
  "passed",
  "failed",
  "timedOut",
  "skipped",
  "interrupted",
];

/**
 * Séquences ANSI (couleurs, curseur, hyperliens OSC 8) émises par Playwright et
 * par les bibliothèques d'assertion. Elles ne doivent pas atteindre la base.
 */
// eslint-disable-next-line no-control-regex
const ANSI_PATTERN =
  /[][[\]()#;?]*(?:(?:(?:(?:;[-a-zA-Z\d/#&.:=?%@~_]+)*|[a-zA-Z\d]+(?:;[-a-zA-Z\d/#&.:=?%@~_]*)*)?)|(?:(?:\d{1,4}(?:;\d{0,4})*)?[\dA-PR-TZcf-nq-uy=><~]))/g;

/** Retire toute séquence ANSI d'un texte, en laissant le reste intact. */
export function stripAnsi(value: string): string {
  return value.replace(ANSI_PATTERN, "");
}

/**
 * Retire la demi-paire de substitution qu'une coupe en unités UTF-16 peut laisser
 * en fin de chaîne. Une demi-paire n'est pas encodable en UTF-8 : Pydantic refuse
 * la chaîne (`string_unicode`) et le worker jetterait la ligne entière.
 */
function dropLoneSurrogate(value: string): string {
  const last = value.charCodeAt(value.length - 1);
  return last >= 0xd800 && last <= 0xdbff ? value.slice(0, value.length - 1) : value;
}

/** Coupe une valeur à `max` caractères, marque comprise, sans casser un caractère. */
export function truncate(value: string, max: number): string {
  if (value.length <= max) {
    return value;
  }
  if (max <= TRUNCATION_MARKER.length) {
    return dropLoneSurrogate(value.slice(0, max));
  }
  return `${dropLoneSurrogate(value.slice(0, max - TRUNCATION_MARKER.length))}${TRUNCATION_MARKER}`;
}

/** Coupe sans marque : titres, noms, types — la borne est structurelle. */
function bounded(value: string, max: number): string {
  return value.length <= max ? value : dropLoneSurrogate(value.slice(0, max));
}

/** Ramène un statut inconnu à `failed` : jamais un succès inventé. */
function normalizeStatus(value: unknown): TestStatus {
  return TEST_STATUSES.includes(value as TestStatus) ? (value as TestStatus) : "failed";
}

/** Statut attendu déclaré par le test ; `passed` par défaut. */
function expectedStatusOf(value: unknown): TestStatus {
  return TEST_STATUSES.includes(value as TestStatus) ? (value as TestStatus) : "passed";
}

/**
 * Issue d'un test après la tentative `result`, selon l'algorithme de Playwright :
 * les tentatives ignorées et interrompues ne comptent pas ; toutes conformes au
 * statut attendu ⇒ `expected` ; au moins une conforme ⇒ `flaky` ; aucune ⇒
 * `unexpected` ; aucune tentative exploitable ⇒ `skipped`.
 */
export function computeOutcome(test: unknown, result: unknown): TestOutcome {
  const expected = expectedStatusOf((test as { expectedStatus?: unknown } | null)?.expectedStatus);
  const history = (test as { results?: unknown } | null)?.results;
  const attempts = Array.isArray(history) && history.length > 0 ? history : [result];
  const statuses = attempts
    .map((attempt) => normalizeStatus((attempt as { status?: unknown } | null)?.status))
    .filter((status) => status !== "skipped" && status !== "interrupted");
  if (statuses.length === 0) {
    return "skipped";
  }
  if (statuses.every((status) => status === expected)) {
    return "expected";
  }
  if (statuses.some((status) => status === expected)) {
    return "flaky";
  }
  return "unexpected";
}

/**
 * Chemin POSIX relatif de `target` sous `root`, ou `null` si le fichier sort de
 * cette racine (autre volume, remontée `..`, racine elle-même). Calcul purement
 * lexical : le worker revalide de façon canonique avant tout téléversement.
 */
export function relativeReportPath(target: string, root: string): string | null {
  if (!target || !root) {
    return null;
  }
  const relativePath = relative(resolve(root), resolve(target));
  if (!relativePath || isAbsolute(relativePath)) {
    return null;
  }
  const posixPath = relativePath.split(sep).join("/");
  if (posixPath === ".." || posixPath.startsWith("../")) {
    return null;
  }
  return posixPath;
}

/** Remplace toutes les occurrences de `needle`, sans tenir compte de la casse. */
function replaceAllInsensitive(haystack: string, needle: string, replacement: string): string {
  if (needle === "") {
    return haystack;
  }
  const lowerHaystack = haystack.toLowerCase();
  const lowerNeedle = needle.toLowerCase();
  let result = "";
  let cursor = 0;
  for (;;) {
    const found = lowerHaystack.indexOf(lowerNeedle, cursor);
    if (found === -1) {
      return result + haystack.slice(cursor);
    }
    result += haystack.slice(cursor, found) + replacement;
    cursor = found + needle.length;
  }
}

/**
 * Rend relatifs à `rootDir` les chemins absolus portés par un texte d'erreur
 * (message, extrait, pile). Playwright republie la pile du runner telle quelle :
 * sans ce nettoyage, `error_message` et `error_snippet` décriraient l'arborescence
 * de la machine de test, que `location` prend déjà soin de ne pas divulguer.
 *
 * Les chemins qui ne sont pas sous `rootDir` (internes de Playwright, `node_modules`
 * d'un autre volume) restent tels quels : le reporter ne les devine pas.
 */
export function relativizePaths(value: string, rootDir: string): string {
  if (value === "" || rootDir === "") {
    return value;
  }
  const bases = new Set<string>();
  for (const candidate of [rootDir, resolve(rootDir)]) {
    const trimmed = candidate.replace(/[\\/]+$/, "");
    if (trimmed === "") {
      continue;
    }
    const parts = trimmed.split(/[\\/]/);
    bases.add(trimmed);
    bases.add(parts.join("/"));
    bases.add(parts.join("\\"));
  }
  const ordered = [...bases].sort((left, right) => right.length - left.length);
  let result = value;
  for (const base of ordered) {
    result = replaceAllInsensitive(result, `${base}/`, "");
    result = replaceAllInsensitive(result, `${base}\\`, "");
  }
  for (const base of ordered) {
    result = replaceAllInsensitive(result, base, ".");
  }
  return result;
}

/** Millisecondes entières et positives. */
function milliseconds(value: unknown): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.round(numeric) : 0;
}

/** Entier tolérant (ligne, colonne). */
function integer(value: unknown): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.trunc(numeric) : 0;
}

/** Message lisible d'une erreur Playwright, quelle que soit sa forme. */
function messageOf(error: unknown): string {
  if (typeof error === "string") {
    return error;
  }
  const candidate = error as { message?: unknown; value?: unknown } | null;
  if (typeof candidate?.message === "string") {
    return candidate.message;
  }
  if (typeof candidate?.value === "string") {
    return candidate.value;
  }
  return "";
}

/** Base URL sans identifiants, sans requête ni fragment. */
function sanitizeBaseUrl(value: unknown): string | undefined {
  if (typeof value !== "string" || value.trim() === "") {
    return undefined;
  }
  try {
    const url = new URL(value);
    return bounded(`${url.protocol}//${url.host}${url.pathname}`, MAX_BASE_URL_CHARS);
  } catch {
    return undefined;
  }
}

/** Statut global de Playwright ⇒ statut d'exécution du contrat. */
function runStatusOf(value: unknown): TestRunStatus {
  switch (value) {
    case "passed":
      return "completed";
    case "timedout":
      return "timed_out";
    case "interrupted":
      return "interrupted";
    default:
      return "failed";
  }
}

interface StepRecord {
  title: string;
  category: string;
  duration_ms: number;
  error: boolean;
}

interface FinalAttempt {
  status: TestStatus;
  outcome: TestOutcome;
}

/** Aplatit les étapes d'un résultat (parent avant enfants), borne comprise. */
function flattenSteps(steps: unknown, limit: number): StepRecord[] {
  const records: StepRecord[] = [];
  const visit = (candidates: unknown, depth: number): void => {
    if (!Array.isArray(candidates) || depth > MAX_WALK_DEPTH) {
      return;
    }
    for (const candidate of candidates) {
      if (records.length >= limit) {
        return;
      }
      records.push(describeStep(candidate));
      visit((candidate as { steps?: unknown } | null)?.steps, depth + 1);
    }
  };
  visit(steps, 0);
  return records;
}

/** Forme d'étape conservée : titre, catégorie, durée, présence d'erreur. */
function describeStep(step: unknown): StepRecord {
  const candidate = step as
    | { title?: unknown; category?: unknown; duration?: unknown; error?: unknown }
    | null;
  return {
    title: bounded(stripAnsi(String(candidate?.title ?? "")), MAX_TITLE_CHARS),
    category: bounded(stripAnsi(String(candidate?.category ?? "")), MAX_CATEGORY_CHARS),
    duration_ms: milliseconds(candidate?.duration),
    error: Boolean(candidate?.error),
  };
}

/** Options acceptées par Playwright (`reporter: [['@acp/playwright-reporter']]`). */
export interface AcpReporterOptions {
  [key: string]: unknown;
}

/**
 * Reporter NDJSON de la plateforme.
 *
 * Aucune méthode ne lève : une erreur interne dégrade le rapport, jamais
 * l'exécution des tests.
 */
export default class AcpPlaywrightReporter {
  private readonly target: string | null;

  private readonly reportRoot: string;

  private disabled = false;

  private warned = false;

  private rootDir = "";

  private projectNames: string[] = [];

  private readonly pendingSteps = new WeakMap<object, StepRecord[]>();

  /**
   * Numéro interne attribué à chaque objet `TestCase` distinct. Les totaux sont
   * indexés par ce numéro et non par `test_id` : une identité de repli
   * (`suite > titre`, deux tests homonymes) est collisionnable, et un test réussi
   * effacerait alors le total d'un test échoué portant la même identité.
   */
  private readonly testKeys = new WeakMap<object, number>();

  private nextTestKey = 0;

  private readonly finalAttempts = new Map<number, FinalAttempt>();

  constructor(_options: AcpReporterOptions = {}) {
    const configured = process.env[REPORT_FILE_ENV];
    const requested = typeof configured === "string" ? configured.trim() : "";
    if (requested === "") {
      this.target = null;
      this.reportRoot = "";
      this.warn(
        `[@acp/playwright-reporter] ${REPORT_FILE_ENV} n'est pas défini : aucun rapport NDJSON ne sera écrit, l'exécution des tests n'est pas modifiée.`,
      );
      return;
    }
    this.target = resolve(requested);
    this.reportRoot = dirname(this.target);
  }

  /** Le reporter n'écrit rien sur la sortie standard. */
  printsToStdio(): boolean {
    return false;
  }

  onBegin(config: unknown, _suite?: unknown): void {
    this.guard(() => {
      const candidate = config as { rootDir?: unknown; projects?: unknown; version?: unknown } | null;
      this.rootDir = typeof candidate?.rootDir === "string" ? candidate.rootDir : "";
      const projects = Array.isArray(candidate?.projects) ? candidate.projects : [];
      this.projectNames = projects
        .map((project) => (project as { name?: unknown } | null)?.name)
        .filter((name): name is string => typeof name === "string" && name !== "");
      this.emit({
        kind: "run_begin",
        started_at: new Date().toISOString(),
        runner_version: bounded(
          typeof candidate?.version === "string" ? candidate.version : "",
          MAX_VERSION_CHARS,
        ),
        config: this.describeConfig(config, projects),
      });
    });
  }

  onTestBegin(_test: unknown, result?: unknown): void {
    this.guard(() => {
      if (result && typeof result === "object") {
        this.pendingSteps.set(result as object, []);
      }
    });
  }

  onStepBegin(_test: unknown, result: unknown, _step: unknown): void {
    this.guard(() => {
      this.stepBucket(result);
    });
  }

  onStepEnd(_test: unknown, result: unknown, step: unknown): void {
    this.guard(() => {
      const bucket = this.stepBucket(result);
      if (bucket && bucket.length < MAX_STEPS) {
        bucket.push(describeStep(step));
      }
    });
  }

  onTestEnd(test: unknown, result: unknown): void {
    this.guard(() => {
      const suitePath = this.suitePathOf(test);
      const testId = identityOf(test, suitePath);
      const status = normalizeStatus((result as { status?: unknown } | null)?.status);
      const outcome = computeOutcome(test, result);
      const retry = Number((result as { retry?: unknown } | null)?.retry);
      const attempt = Number.isFinite(retry) ? Math.max(1, Math.trunc(retry) + 1) : 1;
      const { message, snippet } = describeErrors(result, this.rootDir);
      const { attachments, warnings } = this.describeAttachments(result, testId);

      this.finalAttempts.set(this.totalsKeyOf(test), { status, outcome });
      this.emit({
        kind: "test_end",
        test_id: testId,
        title: bounded(
          stripAnsi(String((test as { title?: unknown } | null)?.title ?? "")),
          MAX_TITLE_CHARS,
        ),
        suite_path: suitePath,
        location: this.describeLocation((test as { location?: unknown } | null)?.location),
        project_name: this.projectNameOf(test, suitePath),
        attempt,
        expected_status: bounded(
          expectedStatusOf((test as { expectedStatus?: unknown } | null)?.expectedStatus),
          MAX_STATUS_CHARS,
        ),
        status,
        outcome,
        duration_ms: milliseconds((result as { duration?: unknown } | null)?.duration),
        error_message: message,
        error_snippet: snippet,
        steps: this.stepsOf(result),
        annotations: annotationsOf(test, result),
        attachments,
      });
      for (const warning of warnings) {
        this.emit({ kind: "error", message: truncate(warning, MAX_MESSAGE_CHARS) });
      }
    });
  }

  onError(error: unknown): void {
    this.guard(() => {
      const text = relativizePaths(stripAnsi(messageOf(error)), this.rootDir).trim();
      this.emit({
        kind: "error",
        message: truncate(text === "" ? "Erreur globale sans message." : text, MAX_MESSAGE_CHARS),
      });
    });
  }

  onEnd(result: unknown): void {
    this.guard(() => {
      const totals = {
        expected: 0,
        unexpected: 0,
        flaky: 0,
        skipped: 0,
        interrupted: 0,
        timedOut: 0,
      };
      for (const attempt of this.finalAttempts.values()) {
        if (attempt.outcome === "expected") {
          totals.expected += 1;
        } else if (attempt.outcome === "unexpected") {
          totals.unexpected += 1;
        } else if (attempt.outcome === "flaky") {
          totals.flaky += 1;
        } else {
          totals.skipped += 1;
        }
        if (attempt.status === "interrupted") {
          totals.interrupted += 1;
        }
        if (attempt.status === "timedOut") {
          totals.timedOut += 1;
        }
      }
      this.emit({
        kind: "run_end",
        finished_at: new Date().toISOString(),
        run_status: runStatusOf((result as { status?: unknown } | null)?.status),
        totals,
      });
    });
  }

  // --- Interne ---------------------------------------------------------------

  /** Exécute un traitement de reporter sans jamais faire échouer les tests. */
  private guard(action: () => void): void {
    try {
      action();
    } catch (error) {
      this.warn(
        `[@acp/playwright-reporter] Rapport incomplet : ${bounded(
          stripAnsi(messageOf(error) || String(error)).replace(/[\r\n]+/g, " "),
          MAX_MESSAGE_CHARS,
        )}`,
      );
    }
  }

  /** Une seule ligne d'avertissement par exécution, sur `stderr`. */
  private warn(message: string): void {
    if (this.warned) {
      return;
    }
    this.warned = true;
    try {
      process.stderr.write(`${message}\n`);
    } catch {
      // Une sortie d'erreur indisponible ne doit pas faire échouer les tests.
    }
  }

  /** Ajoute une ligne NDJSON, en synchrone, pour survivre à une interruption. */
  private emit(event: Record<string, unknown>): void {
    if (this.target === null || this.disabled) {
      return;
    }
    let line: string;
    try {
      line = JSON.stringify(event);
    } catch {
      this.warn("[@acp/playwright-reporter] Événement non sérialisable : ligne ignorée.");
      return;
    }
    try {
      appendFileSync(this.target, `${line}\n`, { encoding: "utf8" });
    } catch (error) {
      this.disabled = true;
      this.warn(
        `[@acp/playwright-reporter] Écriture du rapport impossible, rapport abandonné : ${bounded(
          stripAnsi(messageOf(error) || String(error)).replace(/[\r\n]+/g, " "),
          MAX_MESSAGE_CHARS,
        )}`,
      );
    }
  }

  /** Configuration publiable : ni secret, ni environnement, ni identifiants. */
  private describeConfig(config: unknown, projects: unknown[]): Record<string, unknown> {
    const candidate = config as { version?: unknown; workers?: unknown; shard?: unknown } | null;
    const description: Record<string, unknown> = {};
    if (typeof candidate?.version === "string") {
      description.version = bounded(candidate.version, MAX_VERSION_CHARS);
    }
    const workers = Number(candidate?.workers);
    if (Number.isFinite(workers)) {
      description.workers = Math.max(0, Math.trunc(workers));
    }
    const shard = candidate?.shard as { current?: unknown; total?: unknown } | null | undefined;
    if (shard && Number.isFinite(Number(shard.current)) && Number.isFinite(Number(shard.total))) {
      description.shard = {
        current: Math.trunc(Number(shard.current)),
        total: Math.trunc(Number(shard.total)),
      };
    }
    description.projects = projects.slice(0, MAX_PROJECTS).map((project) => {
      const entry = project as { name?: unknown; use?: { baseURL?: unknown } } | null;
      const described: Record<string, unknown> = {
        name: bounded(typeof entry?.name === "string" ? entry.name : "", MAX_NAME_CHARS),
      };
      const baseUrl = sanitizeBaseUrl(entry?.use?.baseURL);
      if (baseUrl !== undefined) {
        described.base_url = baseUrl;
      }
      return described;
    });
    return description;
  }

  /** Localisation relative à la racine du projet : jamais l'arborescence du runner. */
  private describeLocation(location: unknown): Record<string, unknown> {
    const candidate = location as { file?: unknown; line?: unknown; column?: unknown } | null;
    const file = typeof candidate?.file === "string" ? candidate.file : "";
    if (file === "") {
      return {};
    }
    const relativeFile = this.rootDir === "" ? null : relativeReportPath(file, this.rootDir);
    return {
      file: bounded(relativeFile ?? basename(file), MAX_PATH_CHARS),
      line: integer(candidate?.line),
      column: integer(candidate?.column),
    };
  }

  /** Titres des suites englobantes, de la plus externe à la plus interne. */
  private suitePathOf(test: unknown): string[] {
    const titles: string[] = [];
    let suite = (test as { parent?: unknown } | null)?.parent as
      | { title?: unknown; parent?: unknown }
      | null
      | undefined;
    let depth = 0;
    while (suite && depth < MAX_WALK_DEPTH) {
      const title = typeof suite.title === "string" ? stripAnsi(suite.title).trim() : "";
      if (title !== "") {
        titles.push(bounded(title, MAX_TITLE_CHARS));
      }
      suite = suite.parent as { title?: unknown; parent?: unknown } | null | undefined;
      depth += 1;
    }
    titles.reverse();
    return titles.slice(0, MAX_SUITE_DEPTH);
  }

  /** Nom du projet Playwright du test, par la suite projet puis par repli. */
  private projectNameOf(test: unknown, suitePath: string[]): string {
    let suite = (test as { parent?: unknown } | null)?.parent as
      | { project?: unknown; parent?: unknown }
      | null
      | undefined;
    let depth = 0;
    while (suite && depth < MAX_WALK_DEPTH) {
      if (typeof suite.project === "function") {
        const project = (suite.project as () => { name?: unknown } | undefined)();
        if (project && typeof project.name === "string" && project.name !== "") {
          return bounded(project.name, MAX_NAME_CHARS);
        }
      }
      suite = suite.parent as { project?: unknown; parent?: unknown } | null | undefined;
      depth += 1;
    }
    const outermost = suitePath[0];
    if (outermost !== undefined && this.projectNames.includes(outermost)) {
      return bounded(outermost, MAX_NAME_CHARS);
    }
    return "";
  }

  /**
   * Clé de totalisation d'un test : stable entre les tentatives du même objet
   * `TestCase` (une reprise remplace bien son échec précédent) et distincte pour
   * deux tests différents, fussent-ils homonymes et sans identifiant.
   */
  private totalsKeyOf(test: unknown): number {
    if (test && typeof test === "object") {
      const known = this.testKeys.get(test as object);
      if (known !== undefined) {
        return known;
      }
      this.nextTestKey += 1;
      this.testKeys.set(test as object, this.nextTestKey);
      return this.nextTestKey;
    }
    this.nextTestKey += 1;
    return this.nextTestKey;
  }

  /** Accumulateur d'étapes de la tentative en cours. */
  private stepBucket(result: unknown): StepRecord[] | null {
    if (!result || typeof result !== "object") {
      return null;
    }
    const existing = this.pendingSteps.get(result as object);
    if (existing) {
      return existing;
    }
    const created: StepRecord[] = [];
    this.pendingSteps.set(result as object, created);
    return created;
  }

  /** Étapes vues par les hooks, sinon celles portées par le résultat. */
  private stepsOf(result: unknown): StepRecord[] {
    if (result && typeof result === "object") {
      const recorded = this.pendingSteps.get(result as object);
      this.pendingSteps.delete(result as object);
      if (recorded && recorded.length > 0) {
        return recorded.slice(0, MAX_STEPS);
      }
    }
    return flattenSteps((result as { steps?: unknown } | null)?.steps, MAX_STEPS);
  }

  /**
   * Pièces jointes publiables : un chemin relatif au répertoire de rapport, et
   * rien d'autre. Le contrat d'ingestion (`ReporterAttachment`, `extra="forbid"`)
   * exige un `path` et ne connaît pas de corps encodé : une pièce jointe en
   * mémoire (`testInfo.attach(nom, { body })`) ferait rejeter la ligne `test_end`
   * entière, donc le statut et l'erreur du test avec elle. Elle est signalée par
   * une ligne `error`, comme un chemin hors du répertoire de rapport — dont le
   * chemin fautif n'est jamais recopié, il décrirait l'arborescence du runner.
   */
  private describeAttachments(
    result: unknown,
    testId: string,
  ): { attachments: Record<string, unknown>[]; warnings: string[] } {
    const source = (result as { attachments?: unknown } | null)?.attachments;
    const attachments: Record<string, unknown>[] = [];
    const warnings: string[] = [];
    if (!Array.isArray(source)) {
      return { attachments, warnings };
    }
    for (let index = 0; index < source.length; index += 1) {
      if (attachments.length >= MAX_ATTACHMENTS) {
        warnings.push(
          `Test ${testId} : ${source.length - index} pièce(s) jointe(s) ignorée(s) au-delà de la borne de ${MAX_ATTACHMENTS}.`,
        );
        break;
      }
      const candidate = source[index] as
        | { name?: unknown; contentType?: unknown; path?: unknown; body?: unknown }
        | null;
      const name = bounded(stripAnsi(String(candidate?.name ?? "")), MAX_NAME_CHARS);
      const contentType =
        typeof candidate?.contentType === "string" && candidate.contentType.trim() !== ""
          ? bounded(candidate.contentType.trim(), MAX_CONTENT_TYPE_CHARS)
          : DEFAULT_CONTENT_TYPE;

      const declaredPath = typeof candidate?.path === "string" ? candidate.path.trim() : "";
      if (declaredPath !== "") {
        const relativePath =
          this.reportRoot === "" ? null : relativeReportPath(declaredPath, this.reportRoot);
        if (relativePath === null) {
          warnings.push(
            `Pièce jointe « ${name} » du test ${testId} ignorée : son chemin sort du répertoire de rapport.`,
          );
          continue;
        }
        attachments.push({
          name,
          content_type: contentType,
          path: bounded(relativePath, MAX_PATH_CHARS),
        });
        continue;
      }

      if (candidate?.body !== undefined && candidate.body !== null) {
        warnings.push(
          `Pièce jointe « ${name} » du test ${testId} ignorée : corps en mémoire, sans fichier. Le contrat d'ingestion n'accepte qu'un chemin sous le répertoire de rapport ; utilisez testInfo.attach(nom, { path }).`,
        );
        continue;
      }
      warnings.push(
        `Pièce jointe « ${name} » du test ${testId} ignorée : ni chemin ni corps exploitable.`,
      );
    }
    return { attachments, warnings };
  }
}

/** Identité stable et bornée d'un test, avec empreinte si elle doit être coupée. */
function identityOf(test: unknown, suitePath: string[]): string {
  const declared = (test as { id?: unknown } | null)?.id;
  const title = String((test as { title?: unknown } | null)?.title ?? "");
  const raw =
    typeof declared === "string" && declared.trim() !== ""
      ? declared.trim()
      : [...suitePath, title].filter((part) => part !== "").join(" > ");
  const identity = raw === "" ? "test-sans-identite" : raw;
  if (identity.length <= MAX_TEST_ID_CHARS) {
    return identity;
  }
  const digest = createHash("sha256").update(identity).digest("hex").slice(0, 8);
  return `${bounded(identity, MAX_TEST_ID_CHARS - digest.length - 1)}#${digest}`;
}

/** Message agrégé et extrait de code d'une tentative, expurgés et bornés. */
function describeErrors(result: unknown, rootDir: string): { message: string; snippet: string } {
  const candidate = result as { error?: unknown; errors?: unknown } | null;
  const list =
    Array.isArray(candidate?.errors) && candidate.errors.length > 0
      ? candidate.errors
      : candidate?.error
        ? [candidate.error]
        : [];
  const messages = list.map(messageOf).filter((value) => value !== "");
  const withSnippet = list.find((error) => {
    const value = (error as { snippet?: unknown } | null)?.snippet;
    return typeof value === "string" && value !== "";
  }) as { snippet?: string } | undefined;
  const withStack = list.find((error) => {
    const value = (error as { stack?: unknown } | null)?.stack;
    return typeof value === "string" && value !== "";
  }) as { stack?: string } | undefined;
  const snippet = withSnippet?.snippet ?? withStack?.stack ?? "";
  return {
    message: truncate(
      relativizePaths(stripAnsi(messages.join("\n\n")), rootDir),
      MAX_ERROR_CHARS,
    ),
    snippet: truncate(relativizePaths(stripAnsi(snippet), rootDir), MAX_ERROR_CHARS),
  };
}

/** Annotations du test (ou de la tentative), normalisées et bornées. */
function annotationsOf(test: unknown, result: unknown): Record<string, string>[] {
  const fromResult = (result as { annotations?: unknown } | null)?.annotations;
  const fromTest = (test as { annotations?: unknown } | null)?.annotations;
  const source = Array.isArray(fromResult) && fromResult.length > 0 ? fromResult : fromTest;
  if (!Array.isArray(source)) {
    return [];
  }
  return source.slice(0, MAX_ANNOTATIONS).map((annotation) => {
    const candidate = annotation as { type?: unknown; description?: unknown } | null;
    const entry: Record<string, string> = {
      type: bounded(stripAnsi(String(candidate?.type ?? "")), MAX_ANNOTATION_TYPE_CHARS),
    };
    if (candidate?.description !== undefined && candidate.description !== null) {
      entry.description = bounded(
        stripAnsi(String(candidate.description)),
        MAX_ANNOTATION_DESCRIPTION_CHARS,
      );
    }
    return entry;
  });
}
