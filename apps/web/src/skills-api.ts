/**
 * Client typé de la bibliothèque de skills (routes `/skills` et `/projects/{id}/extensions`).
 *
 * Chaque réponse est validée en forme avant d’être rendue : une réponse mal formée
 * produit une `WorkspaceApiError` de type `invalid_response`, jamais un rendu partiel.
 * Les contenus importés (SKILL.md, scripts, frontmatter) sont des données non fiables :
 * le client les transporte tels quels et ne les interprète jamais.
 *
 * Les helpers purs exportés (`encodeSkillFilePath`, `encodeBase64`, `previewFrontmatter`,
 * `describeSkillsError`, `normalizeSkillSource`) sont partagés avec `skills-ui.ts` et
 * testés sous Node.
 */

import type {
  ProjectExtensions,
  SkillBinding,
  SkillCatalogEntry,
  SkillDetail,
  SkillFile,
  SkillFileContent,
  SkillFindingLevel,
  SkillKind,
  SkillRevision,
  SkillRevisionDiff,
  SkillSearchResult,
  SkillSourceKind,
  SkillStatus,
  SkillSummary,
} from "@acp/contracts";

import { errorMessage, type StatePanelTone } from "./ui-primitives";
import {
  WorkspaceApiError,
  WorkspaceHttpClient,
  hasString,
  isRecord,
  type Fetcher,
} from "./workspace-api";

/** Variable d’environnement à définir côté API pour autoriser l’import GitHub (§4.6). */
export const SKILLS_GITHUB_ACTION = "ACP_SKILLS_GITHUB_ENABLED";
/** Variable d’environnement listant les dossiers importables (`os.pathsep`). */
export const SKILLS_ALLOWED_DIRS_ACTION = "ACP_SKILLS_ALLOWED_DIRS";

export const SLUG_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,62})$/;
export const GITHUB_REPOSITORY_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
export const GIT_SHA_PATTERN = /^[0-9a-fA-F]{40}$/;

const SEARCH_QUERY_MAX_CHARS = 200;
const NOTE_MAX_CHARS = 2000;
const FRONTMATTER_VALUE_MAX_CHARS = 240;
const FRONTMATTER_FIELDS_MAX = 40;

const SKILL_KINDS = new Set(["documentary", "scripted", "native_plugin"]);
const SKILL_STATUSES = new Set(["draft", "active", "disabled", "revoked"]);
const SKILL_SOURCE_KINDS = new Set(["manual", "directory", "archive", "github", "catalog"]);
const FINDING_LEVELS = new Set(["info", "caution", "danger"]);
const MCP_SERVER_STATUSES = new Set(["draft", "active", "disabled", "revoked"]);

// --- Entrées ---------------------------------------------------------------

export interface SkillSourceFileInput {
  path: string;
  content: string;
}

export type SkillSourceInput =
  | { kind: "manual"; files: SkillSourceFileInput[] }
  | { kind: "directory"; path: string }
  | { kind: "archive"; filename: string; content_base64: string }
  | { kind: "github"; repository: string; ref: string; path?: string };

export interface SkillImportInput {
  source: SkillSourceInput;
  name?: string | null;
  note?: string;
}

export interface SkillRevisionInput {
  source: SkillSourceInput;
  note?: string;
}

export interface SkillBindingFilter {
  projectId?: string;
  skillId?: string;
}

export interface FrontmatterField {
  key: string;
  value: string;
}

export interface FrontmatterPreview {
  found: boolean;
  fields: FrontmatterField[];
  bodyLength: number;
  warnings: string[];
}

export interface SkillsErrorDescription {
  tone: StatePanelTone;
  title: string;
  message: string;
  /** Action à effectuer côté serveur (jamais exécutée par le web). */
  action: string | null;
}

/** Refus côté client, avant tout appel réseau : même sémantique qu’un 422 serveur, sans statut HTTP. */
function inputError(message: string): WorkspaceApiError {
  return new WorkspaceApiError(message, "http", null);
}

// --- Validateurs de forme ---------------------------------------------------

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isNullableInteger(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isInteger(value));
}

function isRecordArray(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every(isRecord);
}

function isSkillFile(value: unknown): value is SkillFile {
  return isRecord(value)
    && hasString(value, "path")
    && isNonNegativeInteger(value.size)
    && hasString(value, "sha256")
    && typeof value.text === "boolean";
}

function isSkillFileList(value: unknown): value is SkillFile[] {
  return Array.isArray(value) && value.every(isSkillFile);
}

function isSkillDependencies(value: unknown): boolean {
  return isRecord(value)
    && isRecordArray(value.required_environment_variables)
    && isStringArray(value.requires_toolsets)
    && isStringArray(value.requires_tools)
    && isStringArray(value.scripts)
    && isStringArray(value.network_indicators)
    && isStringArray(value.platforms);
}

function isScanFinding(value: unknown): boolean {
  return isRecord(value)
    && FINDING_LEVELS.has(String(value.level))
    && hasString(value, "code")
    && hasString(value, "message")
    && isNullableString(value.path);
}

function isRevisionDiff(value: unknown): boolean {
  return isRecord(value)
    && isNullableInteger(value.previous_number)
    && isStringArray(value.files_added)
    && isStringArray(value.files_removed)
    && isStringArray(value.files_changed)
    && isStringArray(value.scripts_added)
    && isStringArray(value.network_indicators_added)
    && isStringArray(value.permissions_added)
    && typeof value.kind_changed === "boolean"
    && typeof value.requires_approval === "boolean"
    && isStringArray(value.reasons);
}

function isSkillRevision(value: unknown): value is SkillRevision {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "skill_id")
    && isNonNegativeInteger(value.number)
    && hasString(value, "fingerprint")
    && isSkillFileList(value.files)
    && isRecord(value.frontmatter)
    && isNullableString(value.license)
    && isSkillDependencies(value.dependencies)
    && Array.isArray(value.scan)
    && value.scan.every(isScanFinding)
    && SKILL_KINDS.has(String(value.kind))
    && (value.change_summary === null || isRevisionDiff(value.change_summary))
    && typeof value.requires_approval === "boolean"
    && typeof value.approved === "boolean"
    && isNullableString(value.approved_at)
    && hasString(value, "source_ref")
    && hasString(value, "note")
    && hasString(value, "created_at")
    && isNullableString(value.superseded_at);
}

function isSkillBinding(value: unknown): value is SkillBinding {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "skill_id")
    && hasString(value, "skill_name")
    && hasString(value, "project_id")
    && hasString(value, "revision_id")
    && isNonNegativeInteger(value.revision_number)
    && typeof value.enabled === "boolean"
    && hasString(value, "created_at")
    && hasString(value, "updated_at")
    && isNullableString(value.revoked_at);
}

function isSkillBindingList(value: unknown): value is SkillBinding[] {
  return Array.isArray(value) && value.every(isSkillBinding);
}

function isSkillSummary(value: unknown): value is SkillSummary {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "name")
    && hasString(value, "display_name")
    && hasString(value, "description")
    && hasString(value, "category")
    && SKILL_KINDS.has(String(value.kind))
    && SKILL_SOURCE_KINDS.has(String(value.source_kind))
    && hasString(value, "origin")
    && SKILL_STATUSES.has(String(value.status))
    && isNullableInteger(value.current_revision_number)
    && isNonNegativeInteger(value.binding_count)
    && typeof value.requires_approval === "boolean"
    && hasString(value, "created_at")
    && hasString(value, "updated_at")
    && isNullableString(value.revoked_at);
}

function isSkillSummaryList(value: unknown): value is SkillSummary[] {
  return Array.isArray(value) && value.every(isSkillSummary);
}

function isSkillDetail(value: unknown): value is SkillDetail {
  if (!isSkillSummary(value)) return false;
  const candidate = value as unknown as Record<string, unknown>;
  return (candidate.current_revision === null || isSkillRevision(candidate.current_revision))
    && Array.isArray(candidate.revisions)
    && candidate.revisions.every(isSkillRevision)
    && isSkillBindingList(candidate.bindings)
    && isStringArray(candidate.apply_notes);
}

function isSkillFileContent(value: unknown): value is SkillFileContent {
  return isRecord(value)
    && hasString(value, "path")
    && typeof value.text === "boolean"
    && isNullableString(value.content)
    && typeof value.truncated === "boolean"
    && isNonNegativeInteger(value.size)
    && hasString(value, "sha256");
}

function isCatalogEntry(value: unknown): value is SkillCatalogEntry {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "display_name")
    && hasString(value, "description")
    && hasString(value, "repository")
    && hasString(value, "path")
    && hasString(value, "documentation_url")
    && isNullableString(value.license)
    && hasString(value, "verified_at")
    && hasString(value, "verification")
    && hasString(value, "note");
}

function isCatalogList(value: unknown): value is SkillCatalogEntry[] {
  return Array.isArray(value) && value.every(isCatalogEntry);
}

function isSearchResult(value: unknown): value is SkillSearchResult {
  return isRecord(value)
    && isSkillSummaryList(value.installed)
    && isCatalogList(value.catalog);
}

function isProjectExtensions(value: unknown): value is ProjectExtensions {
  return isRecord(value)
    && hasString(value, "project_id")
    && Array.isArray(value.mcp)
    && value.mcp.every((item) => isRecord(item)
      && hasString(item, "server_id")
      && hasString(item, "name")
      && isNonNegativeInteger(item.revision_number)
      && isStringArray(item.allowed_tools)
      && typeof item.enabled === "boolean"
      && MCP_SERVER_STATUSES.has(String(item.server_status)))
    && Array.isArray(value.skills)
    && value.skills.every((item) => isRecord(item)
      && hasString(item, "skill_id")
      && hasString(item, "name")
      && isNonNegativeInteger(item.revision_number)
      && typeof item.enabled === "boolean"
      && SKILL_STATUSES.has(String(item.skill_status)))
    && hasString(value, "resolved_at");
}

// --- Helpers purs ------------------------------------------------------------

/**
 * Encode un chemin de fichier du manifeste segment par segment pour la route
 * `/files/{path:path}`. Les chemins absolus, vides ou contenant `.`/`..`/segments
 * vides ne peuvent pas provenir d’un manifeste normalisé : ils sont refusés ici.
 */
export function encodeSkillFilePath(path: string): string {
  const segments = path.split("/");
  const valid = path.length > 0
    && segments.length > 0
    && segments.every((segment) => segment.length > 0 && segment !== "." && segment !== "..");
  if (!valid) {
    throw new WorkspaceApiError("Chemin de fichier invalide dans le manifeste du skill.", "invalid_response");
  }
  return segments.map((segment) => encodeURIComponent(segment)).join("/");
}

/** Encodage base64 standard d’octets arbitraires (archives), par blocs pour éviter les piles profondes. */
export function encodeBase64(bytes: Uint8Array): string {
  const chunk = 0x8000;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunk) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunk));
  }
  return btoa(binary);
}

function boundedValue(value: string): string {
  return value.length > FRONTMATTER_VALUE_MAX_CHARS
    ? `${value.slice(0, FRONTMATTER_VALUE_MAX_CHARS - 1)}…`
    : value;
}

/**
 * Aperçu du frontmatter d’un `SKILL.md` saisi manuellement : extraction textuelle des
 * clés de premier niveau (bloc YAML entre deux lignes `---`), sans interprétation.
 * Le serveur reste seul juge (`yaml.safe_load` borné) ; cet aperçu n’est qu’une aide.
 */
export function previewFrontmatter(text: string): FrontmatterPreview {
  const normalized = text.replace(/^﻿/, "").replace(/\r\n?/g, "\n");
  const lines = normalized.split("\n");
  if (lines[0]?.trim() !== "---") {
    return {
      found: false,
      fields: [],
      bodyLength: normalized.length,
      warnings: ["Aucun frontmatter détecté : le fichier doit commencer par une ligne « --- »."],
    };
  }
  const closing = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (closing === -1) {
    return {
      found: false,
      fields: [],
      bodyLength: normalized.length,
      warnings: ["Frontmatter non terminé : la ligne « --- » de fermeture est absente."],
    };
  }
  const fields: FrontmatterField[] = [];
  for (const line of lines.slice(1, closing)) {
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    const topLevel = /^([A-Za-z0-9_.-]+)\s*:\s*(.*)$/.exec(line);
    if (topLevel && !/^\s/.test(line)) {
      if (fields.length >= FRONTMATTER_FIELDS_MAX) break;
      fields.push({ key: topLevel[1], value: topLevel[2].trim() });
    } else if (fields.length) {
      const last = fields[fields.length - 1];
      const continuation = line.replace(/^ {2}/, "");
      last.value = last.value ? `${last.value}\n${continuation}` : continuation;
    }
  }
  for (const field of fields) field.value = boundedValue(field.value);
  const keys = new Set(fields.map((field) => field.key));
  const warnings: string[] = [];
  if (!keys.has("name")) warnings.push("Champ « name » absent du frontmatter.");
  if (!keys.has("description")) warnings.push("Champ « description » absent du frontmatter.");
  return {
    found: true,
    fields,
    bodyLength: lines.slice(closing + 1).join("\n").length,
    warnings,
  };
}

/** Traduit une erreur API en panneau d’état explicite (ton, titre, message, action serveur). */
export function describeSkillsError(error: WorkspaceApiError): SkillsErrorDescription {
  if (error.kind === "offline") {
    return { tone: "offline", title: "API hors ligne", message: errorMessage(error), action: null };
  }
  if (error.kind === "forbidden") {
    if (error.status === 401) {
      return { tone: "forbidden", title: "Session expirée", message: errorMessage(error), action: null };
    }
    return {
      tone: "forbidden",
      title: "Accès refusé",
      message: `${error.message} Les imports, révisions et actions sur un skill sont réservés au propriétaire `
        + "de la plateforme ; un rattachement exige le rôle membre du projet. Un refus peut aussi venir d’une "
        + "session dont le jeton n’est plus valide : réessayer relance la vérification.",
      action: null,
    };
  }
  if (error.kind === "invalid_response") {
    return { tone: "error", title: "Réponse inexploitable", message: error.message, action: null };
  }
  switch (error.status) {
    case 503:
      return {
        tone: "unconfigured",
        title: "Capacité non configurée",
        message: error.message,
        action: `Définir ${SKILLS_GITHUB_ACTION}=1 (et ${"ACP_GITHUB_TOKEN"} si le dépôt est privé) dans `
          + "l’environnement de l’API, puis la redémarrer. Aucun appel réseau n’a été effectué.",
      };
    case 413:
      return { tone: "error", title: "Limite dépassée", message: error.message, action: null };
    case 409:
      return { tone: "error", title: "Conflit", message: error.message, action: null };
    case 422:
      return { tone: "error", title: "Source refusée", message: error.message, action: null };
    case 404:
      return { tone: "error", title: "Introuvable", message: error.message, action: null };
    default:
      return { tone: "error", title: "Erreur de l’API", message: error.message, action: null };
  }
}

/** Libellé et ton d’un badge : le ton complète le texte, il ne le remplace jamais. */
export interface SkillBadge {
  label: string;
  tone: string;
}

/** Badge de nature d’un skill : le libellé suffit à comprendre le risque, l’aide le détaille. */
export interface SkillKindBadge extends SkillBadge {
  hint: string;
}

const STATUS_BADGES: Record<SkillStatus, SkillBadge> = {
  draft: { label: "Brouillon", tone: "waiting" },
  active: { label: "Actif", tone: "active" },
  disabled: { label: "Désactivé", tone: "blocked" },
  revoked: { label: "Révoqué", tone: "failed" },
};

const KIND_BADGES: Record<SkillKind, SkillKindBadge> = {
  documentary: {
    label: "Documentaire",
    tone: "neutral",
    hint: "Aucun script exécutable relevé par le scan, qui reste indicatif : le contenu est affiché comme donnée.",
  },
  scripted: {
    label: "Scripté",
    tone: "waiting",
    hint: "Contient au moins un script : la plateforme ne l’exécute jamais à l’import ; son exécution dépend de "
      + "l’agent hôte une fois le skill rattaché.",
  },
  native_plugin: {
    label: "Plugin natif : non sandboxé",
    tone: "failed",
    hint: "Un plugin natif est non sandboxé : il s’exécute dans le processus de l’agent, sans bac à sable ni "
      + "limite de la plateforme. Ne l’active que si tu fais confiance à sa source et à chaque révision.",
  },
};

const FINDING_BADGES: Record<SkillFindingLevel, SkillBadge> = {
  info: { label: "Information", tone: "neutral" },
  caution: { label: "Vigilance", tone: "waiting" },
  danger: { label: "Danger", tone: "failed" },
};

const SOURCE_LABELS: Record<SkillSourceKind, string> = {
  manual: "Saisie manuelle",
  directory: "Dossier autorisé",
  archive: "Archive",
  github: "GitHub",
  catalog: "Catalogue",
};

/** Statut d’un skill en français, avec un ton de chip qui ne porte jamais seul l’information. */
export function skillStatusBadge(status: SkillStatus): SkillBadge {
  return STATUS_BADGES[status] ?? { label: "Statut inconnu", tone: "failed" };
}

/** Nature d’un skill ; `native_plugin` affiche explicitement « non sandboxé ». */
export function skillKindBadge(kind: SkillKind): SkillKindBadge {
  return KIND_BADGES[kind] ?? {
    label: "Nature inconnue",
    tone: "failed",
    hint: "L’API a renvoyé une nature non reconnue : traite ce skill comme non vérifié.",
  };
}

/** Niveau d’un finding de scan (toujours présenté comme indicatif, jamais certifiant). */
export function findingLevelBadge(level: SkillFindingLevel): SkillBadge {
  return FINDING_BADGES[level] ?? { label: "Niveau inconnu", tone: "failed" };
}

/** Provenance d’un skill installé. */
export function skillSourceLabel(kind: SkillSourceKind): string {
  return SOURCE_LABELS[kind] ?? "Source inconnue";
}

/** Nœud d’arborescence construit à partir du manifeste d’une révision. */
export interface SkillTreeNode {
  name: string;
  path: string;
  kind: "directory" | "file";
  file: SkillFile | null;
  children: SkillTreeNode[];
}

function sortTree(nodes: SkillTreeNode[]): SkillTreeNode[] {
  nodes.sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === "directory" ? -1 : 1;
    return left.name.localeCompare(right.name, "fr");
  });
  for (const node of nodes) sortTree(node.children);
  return nodes;
}

/**
 * Construit l’arborescence affichée dans le détail d’un skill. Les chemins viennent
 * du manifeste renvoyé par l’API : ils sont regroupés tels quels, jamais réécrits.
 * Les dossiers sont listés avant les fichiers, chaque niveau trié alphabétiquement.
 */
export function buildSkillFileTree(files: SkillFile[]): SkillTreeNode[] {
  const roots: SkillTreeNode[] = [];
  for (const file of files) {
    const segments = file.path.split("/").filter((segment) => segment.length > 0);
    if (segments.length === 0) continue;
    let level = roots;
    let prefix = "";
    segments.forEach((segment, index) => {
      prefix = prefix ? `${prefix}/${segment}` : segment;
      const leaf = index === segments.length - 1;
      let node = level.find((candidate) => candidate.name === segment);
      if (!node) {
        node = { name: segment, path: prefix, kind: leaf ? "file" : "directory", file: null, children: [] };
        level.push(node);
      }
      if (leaf) node.file = file;
      level = node.children;
    });
  }
  return sortTree(roots);
}

function diffLine(label: string, values: string[]): string | null {
  return values.length ? `${label} : ${values.join(", ")}` : null;
}

/**
 * Résume un diff de révision en phrases françaises. Un `change_summary` absent n’est
 * jamais remplacé par un comparatif inventé : l’absence est affichée telle quelle.
 */
export function summarizeRevisionDiff(diff: SkillRevisionDiff | null): string[] {
  if (!diff) return ["Aucun comparatif n’est fourni par l’API pour cette révision."];
  const lines: string[] = [
    diff.previous_number === null
      ? "Première révision : aucune version précédente."
      : `Comparée à la révision ${diff.previous_number}.`,
  ];
  const changes = [
    diffLine("Fichiers ajoutés", diff.files_added),
    diffLine("Fichiers retirés", diff.files_removed),
    diffLine("Fichiers modifiés", diff.files_changed),
    diffLine("Scripts ajoutés", diff.scripts_added),
    diffLine("Indicateurs réseau ajoutés", diff.network_indicators_added),
    diffLine("Permissions ajoutées", diff.permissions_added),
  ].filter((line): line is string => line !== null);
  if (changes.length === 0) lines.push("Aucun fichier ajouté, retiré ni modifié.");
  else lines.push(...changes);
  if (diff.kind_changed) {
    lines.push("Nature du skill modifiée (documentaire, scripté ou plugin natif).");
  }
  if (diff.requires_approval) {
    const reasons = diff.reasons.length ? diff.reasons.join(", ") : "motif non précisé par l’API";
    lines.push(`Approbation requise : ${reasons}.`);
  }
  return lines;
}

const SIZE_UNITS = ["o", "ko", "Mo", "Go"];

/** Taille d’un fichier en français ; une taille absente ou négative reste « Taille inconnue ». */
export function formatFileSize(size: number): string {
  if (!Number.isFinite(size) || size < 0) return "Taille inconnue";
  let value = size;
  let unit = 0;
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const formatted = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(value);
  return `${formatted} ${SIZE_UNITS[unit]}`;
}

function normalizeRelativePath(path: string): string {
  return path.trim().replace(/\\/g, "/").replace(/^(?:\.\/)+/, "").replace(/^\/+|\/+$/g, "");
}

function normalizeNote(note: string | undefined): string {
  const trimmed = (note ?? "").trim();
  if (trimmed.length > NOTE_MAX_CHARS) {
    throw inputError(`La note dépasse ${NOTE_MAX_CHARS} caractères.`);
  }
  return trimmed;
}

/**
 * Valide et normalise une source d’import avant envoi (miroir des validateurs pydantic
 * §3.2). Le contenu des fichiers n’est jamais modifié.
 */
export function normalizeSkillSource(source: SkillSourceInput): SkillSourceInput {
  switch (source.kind) {
    case "manual": {
      if (!Array.isArray(source.files) || source.files.length === 0) {
        throw inputError("La source manuelle doit contenir au moins un fichier.");
      }
      const files = source.files.map((file) => {
        const path = normalizeRelativePath(file.path);
        if (!path || path.split("/").some((segment) => segment === "..")) {
          throw inputError(`Chemin de fichier invalide : « ${file.path} ».`);
        }
        return { path, content: file.content };
      });
      if (!files.some((file) => file.path === "SKILL.md")) {
        throw inputError("La source manuelle doit contenir un fichier SKILL.md à la racine.");
      }
      return { kind: "manual", files };
    }
    case "directory": {
      const path = source.path.trim();
      if (!path) throw inputError("Le chemin du dossier est requis.");
      return { kind: "directory", path };
    }
    case "archive": {
      const filename = source.filename.trim();
      if (!filename || filename.length > 255) throw inputError("Le nom de l’archive est requis (255 caractères max).");
      if (!source.content_base64) throw inputError("Le contenu de l’archive est vide.");
      return { kind: "archive", filename, content_base64: source.content_base64 };
    }
    case "github": {
      const repository = source.repository.trim();
      if (!GITHUB_REPOSITORY_PATTERN.test(repository)) {
        throw inputError("Dépôt GitHub invalide : format « owner/repo » attendu.");
      }
      const ref = source.ref.trim();
      if (!GIT_SHA_PATTERN.test(ref)) {
        throw inputError("Ref invalide : épingle un commit complet (SHA de 40 caractères hexadécimaux), jamais une branche.");
      }
      return { kind: "github", repository, ref: ref.toLowerCase(), path: normalizeRelativePath(source.path ?? "") };
    }
    default:
      throw inputError("Type de source inconnu.");
  }
}

function normalizeName(name: string | null | undefined): string | null {
  const trimmed = (name ?? "").trim();
  if (!trimmed) return null;
  if (!SLUG_PATTERN.test(trimmed)) {
    throw inputError("Le nom doit être un slug : minuscules, chiffres et tirets (63 caractères max).");
  }
  return trimmed;
}

function revisionSegment(revisionNumber: number): string {
  if (!Number.isInteger(revisionNumber) || revisionNumber < 1) {
    throw inputError("Numéro de révision invalide.");
  }
  return String(revisionNumber);
}

function skillPath(skillId: string, suffix = ""): string {
  return `/skills/${encodeURIComponent(skillId)}${suffix}`;
}

// --- Client -------------------------------------------------------------------

export class SkillsApiClient {
  readonly http: WorkspaceHttpClient;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
    http?: WorkspaceHttpClient;
  } = {}) {
    this.http = options.http ?? new WorkspaceHttpClient(options);
  }

  async search(query: string): Promise<SkillSearchResult> {
    const bounded = query.trim().slice(0, SEARCH_QUERY_MAX_CHARS);
    return this.http.request(`/skills/search?q=${encodeURIComponent(bounded)}`, isSearchResult);
  }

  async fetchCatalog(): Promise<SkillCatalogEntry[]> {
    return this.http.request("/skills/catalog", isCatalogList);
  }

  async importSkill(input: SkillImportInput): Promise<SkillDetail> {
    const body = {
      source: normalizeSkillSource(input.source),
      name: normalizeName(input.name),
      note: normalizeNote(input.note),
    };
    return this.http.request("/skills/import", isSkillDetail, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async fetchSkills(): Promise<SkillSummary[]> {
    return this.http.request("/skills", isSkillSummaryList);
  }

  async fetchSkill(skillId: string): Promise<SkillDetail> {
    return this.http.request(skillPath(skillId), isSkillDetail);
  }

  async fetchRevisionFiles(skillId: string, revisionNumber: number): Promise<SkillFile[]> {
    return this.http.request(
      skillPath(skillId, `/revisions/${revisionSegment(revisionNumber)}/files`),
      isSkillFileList,
    );
  }

  async fetchFileContent(skillId: string, revisionNumber: number, path: string): Promise<SkillFileContent> {
    const revision = revisionSegment(revisionNumber);
    return this.http.request(
      skillPath(skillId, `/revisions/${revision}/files/${encodeSkillFilePath(path)}`),
      isSkillFileContent,
    );
  }

  async createRevision(skillId: string, input: SkillRevisionInput): Promise<SkillDetail> {
    const body = { source: normalizeSkillSource(input.source), note: normalizeNote(input.note) };
    return this.http.request(skillPath(skillId, "/revisions"), isSkillDetail, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async approveRevision(skillId: string, revisionNumber: number, comment = ""): Promise<SkillDetail> {
    return this.http.request(
      skillPath(skillId, `/revisions/${revisionSegment(revisionNumber)}/approve`),
      isSkillDetail,
      { method: "POST", body: JSON.stringify({ comment: normalizeNote(comment) }) },
    );
  }

  async activateSkill(skillId: string): Promise<SkillDetail> {
    return this.http.request(skillPath(skillId, "/activate"), isSkillDetail, { method: "POST" });
  }

  async disableSkill(skillId: string): Promise<SkillDetail> {
    return this.http.request(skillPath(skillId, "/disable"), isSkillDetail, { method: "POST" });
  }

  async revokeSkill(skillId: string, reason: string): Promise<SkillDetail> {
    const trimmed = normalizeNote(reason);
    if (!trimmed) throw inputError("Le motif de révocation est obligatoire.");
    return this.http.request(skillPath(skillId, "/revoke"), isSkillDetail, {
      method: "POST",
      body: JSON.stringify({ reason: trimmed }),
    });
  }

  async rollbackSkill(skillId: string, revisionNumber: number, note = ""): Promise<SkillDetail> {
    const body = { revision_number: Number(revisionSegment(revisionNumber)), note: normalizeNote(note) };
    return this.http.request(skillPath(skillId, "/rollback"), isSkillDetail, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async createBinding(skillId: string, projectId: string): Promise<SkillBinding> {
    const trimmed = projectId.trim();
    if (!trimmed) throw inputError("Le projet à rattacher est requis.");
    return this.http.request(skillPath(skillId, "/bindings"), isSkillBinding, {
      method: "POST",
      body: JSON.stringify({ project_id: trimmed }),
    });
  }

  async fetchBindings(filter: SkillBindingFilter = {}): Promise<SkillBinding[]> {
    const params = new URLSearchParams();
    if (filter.projectId) params.set("project_id", filter.projectId);
    if (filter.skillId) params.set("skill_id", filter.skillId);
    const query = params.toString();
    return this.http.request(`/skills/bindings${query ? `?${query}` : ""}`, isSkillBindingList);
  }

  async revokeBinding(bindingId: string): Promise<SkillBinding> {
    return this.http.request(`/skills/bindings/${encodeURIComponent(bindingId)}`, isSkillBinding, {
      method: "DELETE",
    });
  }

  async fetchProjectExtensions(projectId: string): Promise<ProjectExtensions> {
    return this.http.request(`/projects/${encodeURIComponent(projectId)}/extensions`, isProjectExtensions);
  }
}
