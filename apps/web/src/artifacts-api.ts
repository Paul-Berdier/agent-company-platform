/**
 * Client typé des livrables (routes `/artifacts`, spec Lot E §6 et §7).
 *
 * Trois règles structurent ce module :
 * 1. une réponse est validée en forme avant tout rendu — un JSON hors contrat produit
 *    une `WorkspaceApiError` `invalid_response`, jamais un affichage partiel ;
 * 2. un livrable est un contenu **non fiable** produit par un test ou un worker : le
 *    client décide du mode d’affichage à partir d’une liste blanche fermée, et
 *    `text/html`, `image/svg+xml` et les archives n’obtiennent jamais d’aperçu en ligne ;
 * 3. l’URL d’un lien signé vient du serveur mais reste vérifiée ici : seules
 *    `http(s)://…` et `/chemin` sont acceptées, pour qu’un `javascript:` ou un `data:`
 *    ne puisse jamais atteindre un attribut `src` ou `href`.
 *
 * Le client HTTP est fourni par l’appelant (règle du Lot D) : ce module ne lit jamais
 * `/auth/session` et ne crée un client que si personne ne lui en passe un.
 */

import type { ArtifactLink, ArtifactPage, ArtifactSummary } from "@acp/contracts";

import { errorMessage, type StatePanelTone } from "./ui-primitives";
import { formatFileSize } from "./skills-api";
import {
  WorkspaceApiError,
  WorkspaceHttpClient,
  hasString,
  isRecord,
  type Fetcher,
} from "./workspace-api";

/** Variable d’environnement à définir côté API pour activer les liens signés (§5.3). */
export const ARTIFACT_SIGNING_ACTION = "ACP_ARTIFACT_SIGNING_KEYS";
/** Variable d’environnement d’une origine d’aperçu séparée (§7), optionnelle. */
export const ARTIFACT_PREVIEW_ORIGIN_ACTION = "ACP_ARTIFACT_PUBLIC_ORIGIN";

/** Durées de vie d’un lien signé (§6 : défaut 300 s, plafond 900 s). */
export const ARTIFACT_LINK_DEFAULT_TTL_SECONDS = 300;
export const ARTIFACT_LINK_MAX_TTL_SECONDS = 900;

/** Bornes de pagination appliquées côté client avant l’appel. */
export const ARTIFACT_PAGE_DEFAULT_LIMIT = 50;
export const ARTIFACT_PAGE_MAX_LIMIT = 200;

/** Types affichables en ligne (§7). Toute autre valeur se télécharge. */
const INLINE_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const INLINE_VIDEO_TYPES = new Set(["video/webm", "video/mp4"]);

const HTML_TYPES = new Set(["text/html", "application/xhtml+xml"]);
const SVG_TYPES = new Set(["image/svg+xml"]);
const ARCHIVE_TYPES = new Set([
  "application/zip",
  "application/x-zip-compressed",
  "application/x-zip",
]);

const HTML_EXTENSIONS = new Set(["html", "htm", "xhtml"]);
const SVG_EXTENSIONS = new Set(["svg", "svgz"]);
const ARCHIVE_EXTENSIONS = new Set(["zip"]);

const HTML_WARNING = "Page HTML produite par un test : elle ne s’ouvre jamais dans la plateforme. "
  + "Télécharge le fichier et ouvre-le hors ligne, dans un navigateur isolé.";
const SVG_WARNING = "Une image SVG peut contenir du script : elle se télécharge, elle ne s’affiche "
  + "jamais en ligne dans l’origine de la plateforme.";
const ARCHIVE_WARNING = "Archive à ouvrir avec l’outil Playwright, hors de la plateforme : "
  + "la plateforme n’en extrait ni n’en exécute le contenu.";

/** Filtres de la route `GET /artifacts` (§6). Un champ vide n’est pas envoyé. */
export interface ArtifactListFilter {
  /** Projet propriétaire du livrable. */
  projectId?: string;
  /** Tentative (`task_run_id`) : une mission peut en compter plusieurs. */
  taskRunId?: string;
  /** Type de flux : `screenshot`, `video`, `trace`, `report`, `file`. */
  streamKind?: string;
  cursor?: string;
  limit?: number;
}

export interface ArtifactsErrorDescription {
  tone: StatePanelTone;
  title: string;
  message: string;
  /** Action à effectuer côté serveur (jamais exécutée par le web). */
  action: string | null;
}

export type ArtifactPreviewKind = "image" | "video" | "none";

/** Décision d’affichage d’un livrable : aperçu autorisé, téléchargement, avertissement. */
export interface ArtifactPreviewDecision {
  kind: ArtifactPreviewKind;
  /** Type normalisé (minuscules, sans paramètre) ayant servi à décider. */
  contentType: string;
  /** Vrai lorsque le type est explicitement exclu de l’aperçu en ligne. */
  downloadOnly: boolean;
  /** Vrai seulement si un contenu a réellement été téléversé. */
  downloadable: boolean;
  /** Avertissement à afficher tel quel ; chaîne vide si le type n’en demande aucun. */
  warning: string;
}

/** Refus côté client, avant tout appel réseau : même sémantique qu’un 422 serveur. */
function inputError(message: string): WorkspaceApiError {
  return new WorkspaceApiError(message, "http", null);
}

// --- Validateurs de forme -----------------------------------------------------

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNullableSize(value: unknown): value is number | null {
  return value === null
    || (typeof value === "number" && Number.isInteger(value) && value >= 0);
}

function isArtifactSummary(value: unknown): value is ArtifactSummary {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "project_id")
    && hasString(value, "task_run_id")
    && hasString(value, "kind")
    && hasString(value, "stream_kind")
    && hasString(value, "original_name")
    && hasString(value, "content_type")
    && hasString(value, "source")
    && isNullableSize(value.size_bytes)
    && isNullableString(value.checksum)
    && typeof value.has_content === "boolean"
    && isNullableString(value.created_at);
}

function isArtifactPage(value: unknown): value is ArtifactPage {
  return isRecord(value)
    && Array.isArray(value.items)
    && value.items.every(isArtifactSummary)
    && isNullableString(value.next_cursor);
}

/**
 * Une URL de lien signé n’est jamais rendue telle quelle sans contrôle : seules une
 * origine `http(s)` et un chemin absolu sont acceptés. Un `javascript:`, un `data:` ou
 * une URL protocole-relative (`//hôte`) est traité comme une réponse hors contrat.
 */
export function isSafeArtifactUrl(value: unknown): value is string {
  if (typeof value !== "string" || !value) return false;
  if (value.startsWith("//")) return false;
  if (value.startsWith("/")) return true;
  const scheme = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(value);
  if (!scheme) return false;
  return scheme[1].toLowerCase() === "http" || scheme[1].toLowerCase() === "https";
}

function isArtifactLink(value: unknown): value is ArtifactLink {
  return isRecord(value)
    && hasString(value, "artifact_id")
    && isSafeArtifactUrl(value.url)
    && hasString(value, "expires_at");
}

// --- Helpers purs --------------------------------------------------------------

const STREAM_KIND_LABELS: Record<string, string> = {
  screenshot: "Capture d’écran",
  video: "Vidéo",
  trace: "Trace",
  report: "Rapport",
  file: "Fichier",
};

const SOURCE_LABELS: Record<string, string> = {
  worker: "Worker",
  playwright: "Playwright",
  platform: "Plateforme",
};

/** Libellé français d’un type de flux ; une valeur inconnue est rendue telle quelle. */
export function artifactStreamKindLabel(streamKind: string): string {
  return STREAM_KIND_LABELS[streamKind] ?? (streamKind || "Non classé");
}

/** Libellé de provenance ; une valeur inconnue est rendue telle quelle, jamais masquée. */
export function artifactSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? (source || "Provenance inconnue");
}

/** Taille lisible ; une taille absente reste « Taille inconnue », jamais « 0 o ». */
export function formatArtifactSize(size: number | null): string {
  return size === null ? "Taille inconnue" : formatFileSize(size);
}

/** Empreinte abrégée pour l’affichage ; la valeur complète reste dans le détail. */
export function shortChecksum(checksum: string | null): string {
  const trimmed = (checksum ?? "").trim();
  if (!trimmed) return "Empreinte absente";
  return trimmed.length <= 20 ? trimmed : `${trimmed.slice(0, 16)}…`;
}

function normalizeContentType(contentType: string): string {
  return contentType.split(";")[0].trim().toLowerCase();
}

function extensionOf(originalName: string): string {
  const name = originalName.trim().toLowerCase();
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot + 1) : "";
}

/**
 * Décide du mode d’affichage d’un livrable (§7). L’extension et le type déclaré sont
 * examinés tous les deux : un fichier nommé `.svg` reste un téléchargement même si le
 * serveur annonce `image/png`, parce que le nom est fourni par le producteur du test.
 */
export function describeArtifactPreview(artifact: ArtifactSummary): ArtifactPreviewDecision {
  const contentType = normalizeContentType(artifact.content_type);
  const extension = extensionOf(artifact.original_name);
  const downloadable = artifact.has_content;

  let warning = "";
  if (HTML_TYPES.has(contentType) || HTML_EXTENSIONS.has(extension)) warning = HTML_WARNING;
  else if (SVG_TYPES.has(contentType) || SVG_EXTENSIONS.has(extension)) warning = SVG_WARNING;
  else if (ARCHIVE_TYPES.has(contentType) || ARCHIVE_EXTENSIONS.has(extension)) warning = ARCHIVE_WARNING;

  if (warning) {
    return { kind: "none", contentType, downloadOnly: true, downloadable, warning };
  }
  if (downloadable && INLINE_IMAGE_TYPES.has(contentType)) {
    return { kind: "image", contentType, downloadOnly: false, downloadable, warning: "" };
  }
  if (downloadable && INLINE_VIDEO_TYPES.has(contentType)) {
    return { kind: "video", contentType, downloadOnly: false, downloadable, warning: "" };
  }
  return { kind: "none", contentType, downloadOnly: false, downloadable, warning: "" };
}

/** Traduit une erreur API en panneau d’état explicite (ton, titre, message, action serveur). */
export function describeArtifactsError(error: WorkspaceApiError): ArtifactsErrorDescription {
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
      message: `${error.message} Les livrables ne sont lisibles que par un membre du projet auquel ils `
        + "appartiennent. Un refus peut aussi venir d’une session dont le jeton n’est plus valide : "
        + "réessayer relance la vérification.",
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
        title: "Liens signés non configurés",
        message: error.message,
        action: `Définir ${ARTIFACT_SIGNING_ACTION} (une ou plusieurs clés séparées par une virgule, `
          + "32 caractères minimum) dans l’environnement de l’API, puis la redémarrer. "
          + `Une origine d’aperçu séparée se déclare avec ${ARTIFACT_PREVIEW_ORIGIN_ACTION}.`,
      };
    case 413:
      return { tone: "error", title: "Limite dépassée", message: error.message, action: null };
    case 410:
      return { tone: "error", title: "Lien expiré", message: error.message, action: null };
    case 404:
      return { tone: "error", title: "Introuvable", message: error.message, action: null };
    default:
      return { tone: "error", title: "Erreur de l’API", message: error.message, action: null };
  }
}

function checkedIdentifier(value: string, label: string): string {
  const trimmed = value.trim();
  if (!trimmed) throw inputError(`${label} est requis.`);
  return encodeURIComponent(trimmed);
}

function boundedLimit(limit: number | undefined): number {
  if (limit === undefined || !Number.isFinite(limit)) return ARTIFACT_PAGE_DEFAULT_LIMIT;
  return Math.max(1, Math.min(Math.trunc(limit), ARTIFACT_PAGE_MAX_LIMIT));
}

/**
 * Durée de vie d’un lien signé. Contrairement à la limite de pagination — un simple
 * confort — une durée hors bornes est **refusée** et non rabotée : c’est une borne de
 * sécurité, et un appelant qui demande plus doit corriger son appel.
 */
function checkedTtl(ttlSeconds: number | undefined): number {
  if (ttlSeconds === undefined) return ARTIFACT_LINK_DEFAULT_TTL_SECONDS;
  if (!Number.isInteger(ttlSeconds) || ttlSeconds < 1 || ttlSeconds > ARTIFACT_LINK_MAX_TTL_SECONDS) {
    throw inputError(
      `La durée d’un lien signé doit être un entier de 1 à ${ARTIFACT_LINK_MAX_TTL_SECONDS} secondes.`,
    );
  }
  return ttlSeconds;
}

// --- Client --------------------------------------------------------------------

export class ArtifactsApiClient {
  readonly http: WorkspaceHttpClient;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
    http?: WorkspaceHttpClient;
  } = {}) {
    this.http = options.http ?? new WorkspaceHttpClient(options);
  }

  /** Page de livrables filtrée côté serveur ; le curseur vient de la page précédente. */
  async listArtifacts(filter: ArtifactListFilter = {}): Promise<ArtifactPage> {
    const params = new URLSearchParams();
    const projectId = filter.projectId?.trim();
    const taskRunId = filter.taskRunId?.trim();
    const streamKind = filter.streamKind?.trim();
    const cursor = filter.cursor?.trim();
    if (projectId) params.set("project_id", projectId);
    if (taskRunId) params.set("task_run_id", taskRunId);
    if (streamKind) params.set("stream_kind", streamKind);
    if (cursor) params.set("cursor", cursor);
    params.set("limit", String(boundedLimit(filter.limit)));
    return this.http.request(`/artifacts?${params.toString()}`, isArtifactPage);
  }

  async fetchArtifact(artifactId: string): Promise<ArtifactSummary> {
    const encoded = checkedIdentifier(artifactId, "L’identifiant du livrable");
    return this.http.request(`/artifacts/${encoded}`, isArtifactSummary);
  }

  /** Crée un lien signé borné dans le temps ; 503 si aucune clé de signature n’est définie. */
  async createLink(artifactId: string, ttlSeconds?: number): Promise<ArtifactLink> {
    const encoded = checkedIdentifier(artifactId, "L’identifiant du livrable");
    const ttl = checkedTtl(ttlSeconds);
    return this.http.request(`/artifacts/${encoded}/link?ttl_seconds=${ttl}`, isArtifactLink, {
      method: "POST",
    });
  }

  /**
   * URL de contenu authentifiée par la session (§6). Elle ne fonctionne que si le
   * navigateur envoie le cookie de session à cette origine ; le chemin nominal reste le
   * lien signé, qui n’en dépend pas.
   */
  contentUrl(artifactId: string): string {
    const encoded = checkedIdentifier(artifactId, "L’identifiant du livrable");
    return `${this.http.baseUrl}/artifacts/${encoded}/content`;
  }
}
