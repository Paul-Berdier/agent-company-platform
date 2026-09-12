/**
 * Client du coffre de secrets (`/secrets`, spec Lot D §5.1).
 *
 * Règle absolue : une valeur de secret n’est transmise que dans le corps de la
 * création ou de la rotation, et n’est jamais conservée dans ce module. Les
 * réponses ne contiennent que des résumés (`SecretSummary`) validés strictement ;
 * toute forme inattendue est rejetée en `invalid_response`.
 */

import type { SecretScopeType, SecretSummary, SecretsStatus } from "@acp/contracts";

import {
  WorkspaceApiError,
  WorkspaceHttpClient,
  hasString,
  isRecord,
  type Fetcher,
} from "./workspace-api";

/** Motif serveur des noms de secrets (`acp_contracts.secrets.SECRET_NAME_PATTERN`). */
export const SECRET_NAME_PATTERN = /^[A-Z][A-Z0-9_]{1,62}$/;
export const SECRET_VALUE_MAX_LENGTH = 8192;

export interface SecretCreateInput {
  name: string;
  value: string;
  scopeType: SecretScopeType;
  projectId: string | null;
  description: string;
}

export function isValidSecretName(name: string): boolean {
  return SECRET_NAME_PATTERN.test(name);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/**
 * Champs qu’un résumé ne doit jamais porter : le coffre ne renvoie que des
 * métadonnées. Une réponse qui contiendrait une valeur est traitée comme un
 * contrat violé (`invalid_response`) plutôt que d’être affichée.
 */
const FORBIDDEN_SUMMARY_KEYS = ["value", "secret_value", "plaintext", "secret"];

function carriesSecretValue(value: Record<string, unknown>): boolean {
  return FORBIDDEN_SUMMARY_KEYS.some((key) => key in value);
}

export function isSecretSummary(value: unknown): value is SecretSummary {
  return isRecord(value)
    && !carriesSecretValue(value)
    && hasString(value, "id")
    && hasString(value, "name")
    && (value.scope_type === "platform" || value.scope_type === "project")
    && isNullableString(value.project_id)
    && hasString(value, "description")
    && hasString(value, "key_id")
    && hasString(value, "created_at")
    && isNullableString(value.rotated_at)
    && isNullableString(value.revoked_at)
    && isNullableString(value.last_used_at)
    && isStringArray(value.referenced_by_mcp_servers);
}

function isSecretList(value: unknown): value is SecretSummary[] {
  return Array.isArray(value) && value.every(isSecretSummary);
}

export function isSecretsStatus(value: unknown): value is SecretsStatus {
  return isRecord(value)
    && typeof value.configured === "boolean"
    && isNullableString(value.primary_key_id)
    && typeof value.key_count === "number"
    && Number.isInteger(value.key_count)
    && value.key_count >= 0
    && hasString(value, "message");
}

function localRejection(message: string): WorkspaceApiError {
  return new WorkspaceApiError(message, "http", 422);
}

function checkValue(value: string): void {
  if (!value.trim()) throw localRejection("La valeur du secret est requise.");
  if (value.length > SECRET_VALUE_MAX_LENGTH) {
    throw localRejection(`La valeur du secret dépasse ${SECRET_VALUE_MAX_LENGTH} caractères.`);
  }
}

export class SecretsApiClient {
  readonly http: WorkspaceHttpClient;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
    http?: WorkspaceHttpClient;
  } = {}) {
    this.http = options.http ?? new WorkspaceHttpClient(options);
  }

  fetchStatus(): Promise<SecretsStatus> {
    return this.http.request("/secrets/status", isSecretsStatus);
  }

  listSecrets(): Promise<SecretSummary[]> {
    return this.http.request("/secrets", isSecretList);
  }

  /**
   * La valeur ne transite que dans ce corps de requête ; elle n’est pas retenue.
   * Méthode asynchrone pour que les refus locaux soient aussi des rejets de promesse.
   */
  async createSecret(input: SecretCreateInput): Promise<SecretSummary> {
    const name = input.name.trim();
    if (!isValidSecretName(name)) {
      throw localRejection("Le nom doit commencer par une majuscule et ne contenir que A-Z, 0-9 et _ (2 à 63 caractères).");
    }
    checkValue(input.value);
    if (input.scopeType === "project" && !input.projectId) {
      throw localRejection("Un secret de projet exige un projet.");
    }
    return this.http.request("/secrets", isSecretSummary, {
      method: "POST",
      body: JSON.stringify({
        name,
        value: input.value,
        scope_type: input.scopeType,
        project_id: input.scopeType === "project" ? input.projectId : null,
        description: input.description.trim(),
      }),
    });
  }

  async rotateSecret(secretId: string, value: string): Promise<SecretSummary> {
    checkValue(value);
    return this.http.request(
      `/secrets/${encodeURIComponent(secretId)}/rotate`,
      isSecretSummary,
      { method: "POST", body: JSON.stringify({ value }) },
    );
  }

  revokeSecret(secretId: string): Promise<SecretSummary> {
    return this.http.request(
      `/secrets/${encodeURIComponent(secretId)}`,
      isSecretSummary,
      { method: "DELETE" },
    );
  }
}
