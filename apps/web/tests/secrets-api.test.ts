import { describe, expect, it, vi } from "vitest";

import { SECRET_NAME_PATTERN, SecretsApiClient, isValidSecretName } from "../src/secrets-api";
import { WorkspaceApiError } from "../src/workspace-api";

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const summary = {
  id: "secret-1",
  name: "GITHUB_TOKEN",
  scope_type: "platform",
  project_id: null,
  description: "Jeton GitHub",
  key_id: "abc123def456",
  created_at: "2026-09-11T10:00:00Z",
  rotated_at: null,
  revoked_at: null,
  last_used_at: null,
  referenced_by_mcp_servers: ["server-1"],
};

const status = {
  configured: true,
  primary_key_id: "abc123def456",
  key_count: 2,
  message: "Coffre configuré.",
};

function client(fetcher: ReturnType<typeof vi.fn>): SecretsApiClient {
  const instance = new SecretsApiClient({ baseUrl: "https://api.example.test", fetcher });
  instance.http.setCsrfToken("csrf-current");
  return instance;
}

function requestInit(fetcher: ReturnType<typeof vi.fn>, index = 0): RequestInit {
  return fetcher.mock.calls[index][1] as RequestInit;
}

describe("SecretsApiClient — statut du coffre", () => {
  it("lit le statut du coffre, y compris non configuré, sans en-tête Cache-Control côté client", async () => {
    const fetcher = vi.fn(async () => json({
      configured: false,
      primary_key_id: null,
      key_count: 0,
      message: "Définir ACP_SECRETS_KEYS.",
    }));

    await expect(client(fetcher).fetchStatus()).resolves.toEqual({
      configured: false,
      primary_key_id: null,
      key_count: 0,
      message: "Définir ACP_SECRETS_KEYS.",
    });
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/secrets/status");
    const init = requestInit(fetcher);
    expect(init.method ?? "GET").toBe("GET");
    expect(init.body).toBeUndefined();
    expect((init.headers as Headers).get("Cache-Control")).toBeNull();
    expect(init.credentials).toBe("include");
  });

  it("refuse un statut mal formé", async () => {
    const fetcher = vi.fn(async () => json({ configured: "oui", key_count: 1, message: "" }));
    await expect(client(fetcher).fetchStatus()).rejects.toMatchObject({
      name: "WorkspaceApiError",
      kind: "invalid_response",
    });
  });
});

describe("SecretsApiClient — liste", () => {
  it("retourne les résumés valides sans jamais exposer de valeur", async () => {
    const fetcher = vi.fn(async () => json([summary]));
    const secrets = await client(fetcher).listSecrets();

    expect(secrets).toEqual([summary]);
    expect(JSON.stringify(secrets)).not.toContain("value");
    expect(requestInit(fetcher).body).toBeUndefined();
  });

  it("rejette une liste dont un élément ne respecte pas le contrat", async () => {
    const fetcher = vi.fn(async () => json([summary, { ...summary, referenced_by_mcp_servers: "server-1" }]));
    await expect(client(fetcher).listSecrets()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("rejette un scope inconnu", async () => {
    const fetcher = vi.fn(async () => json([{ ...summary, scope_type: "global" }]));
    await expect(client(fetcher).listSecrets()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("SecretsApiClient — création et rotation", () => {
  it("n’envoie la valeur que dans le corps de la création et ne la conserve pas", async () => {
    const fetcher = vi.fn(async () => json(summary, 201));
    const api = client(fetcher);

    await expect(api.createSecret({
      name: " GITHUB_TOKEN ",
      value: "ghp_secret_value",
      scopeType: "platform",
      projectId: null,
      description: " Jeton GitHub ",
    })).resolves.toEqual(summary);

    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/secrets");
    const init = requestInit(fetcher);
    expect(init.method).toBe("POST");
    expect((init.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
    expect(JSON.parse(String(init.body))).toEqual({
      name: "GITHUB_TOKEN",
      value: "ghp_secret_value",
      scope_type: "platform",
      project_id: null,
      description: "Jeton GitHub",
    });
    expect(JSON.stringify(api)).not.toContain("ghp_secret_value");
    expect(JSON.stringify(Object.getOwnPropertyNames(api).map((key) => (api as unknown as Record<string, unknown>)[key])))
      .not.toContain("ghp_secret_value");
  });

  it("transmet le projet pour un secret de projet", async () => {
    const fetcher = vi.fn(async () => json({ ...summary, scope_type: "project", project_id: "project-1" }, 201));
    await client(fetcher).createSecret({
      name: "API_KEY",
      value: "v",
      scopeType: "project",
      projectId: "project-1",
      description: "",
    });
    expect(JSON.parse(String(requestInit(fetcher).body))).toMatchObject({
      scope_type: "project",
      project_id: "project-1",
    });
  });

  it("refuse localement un nom hors motif avant tout appel réseau", async () => {
    const fetcher = vi.fn();
    await expect(client(fetcher).createSecret({
      name: "github-token",
      value: "v",
      scopeType: "platform",
      projectId: null,
      description: "",
    })).rejects.toMatchObject({ name: "WorkspaceApiError", kind: "http", status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("refuse localement une valeur vide avant tout appel réseau", async () => {
    const fetcher = vi.fn();
    await expect(client(fetcher).createSecret({
      name: "TOKEN",
      value: "",
      scopeType: "platform",
      projectId: null,
      description: "",
    })).rejects.toMatchObject({ kind: "http", status: 422 });
    await expect(client(fetcher).rotateSecret("secret-1", "   ")).rejects.toMatchObject({ kind: "http", status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("encode l’identifiant dans le chemin de rotation et n’envoie que la valeur", async () => {
    const rotated = { ...summary, key_id: "ffeeddccbbaa", rotated_at: "2026-09-12T08:00:00Z" };
    const fetcher = vi.fn(async () => json(rotated));
    await expect(client(fetcher).rotateSecret("secret/1", "nouvelle-valeur")).resolves.toEqual(rotated);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/secrets/secret%2F1/rotate");
    expect(JSON.parse(String(requestInit(fetcher).body))).toEqual({ value: "nouvelle-valeur" });
  });

  it("remonte le refus 503 d’un coffre absent avec le détail serveur", async () => {
    const fetcher = vi.fn(async () => json({ detail: "Coffre de secrets non configuré : définir ACP_SECRETS_KEYS." }, 503));
    const error = await client(fetcher).createSecret({
      name: "TOKEN",
      value: "v",
      scopeType: "platform",
      projectId: null,
      description: "",
    }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(WorkspaceApiError);
    expect(error).toMatchObject({ kind: "http", status: 503 });
    expect((error as WorkspaceApiError).message).toContain("ACP_SECRETS_KEYS");
  });
});

describe("SecretsApiClient — révocation", () => {
  it("révoque via DELETE sur un chemin encodé, sans corps", async () => {
    const revoked = { ...summary, revoked_at: "2026-09-12T09:00:00Z" };
    const fetcher = vi.fn(async () => json(revoked));
    await expect(client(fetcher).revokeSecret("id with space")).resolves.toEqual(revoked);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/secrets/id%20with%20space");
    const init = requestInit(fetcher);
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
    expect((init.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
  });

  it("distingue un refus 403 (réservé au propriétaire) d’une panne réseau", async () => {
    const forbidden = new SecretsApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => json({ detail: "owner required" }, 403),
    });
    await expect(forbidden.listSecrets()).rejects.toMatchObject({ kind: "forbidden", status: 403 });

    const offline = new SecretsApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => { throw new TypeError("network unavailable"); },
    });
    await expect(offline.listSecrets()).rejects.toMatchObject({ kind: "offline" });
  });
});

describe("motif de nom de secret", () => {
  it("reflète le motif serveur ^[A-Z][A-Z0-9_]{1,62}$", () => {
    expect(SECRET_NAME_PATTERN.source).toBe("^[A-Z][A-Z0-9_]{1,62}$");
    expect(isValidSecretName("GITHUB_TOKEN")).toBe(true);
    expect(isValidSecretName("A1")).toBe(true);
    expect(isValidSecretName("A")).toBe(false);
    expect(isValidSecretName("1TOKEN")).toBe(false);
    expect(isValidSecretName("github_token")).toBe(false);
    expect(isValidSecretName(`A${"B".repeat(62)}`)).toBe(true);
    expect(isValidSecretName(`A${"B".repeat(63)}`)).toBe(false);
  });
});

describe("SecretsApiClient — étanchéité des valeurs", () => {
  it("refuse un résumé qui transporte une valeur de secret", async () => {
    const leaking = vi.fn(async () => json([{ ...summary, value: "ghp_valeur_en_clair" }]));
    await expect(client(leaking).listSecrets()).rejects.toMatchObject({ kind: "invalid_response" });

    const leakingRotation = vi.fn(async () => json({ ...summary, secret_value: "ghp_valeur_en_clair" }));
    await expect(client(leakingRotation).rotateSecret("secret-1", "nouvelle-valeur"))
      .rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("refuse localement une valeur de rotation trop longue avant tout appel réseau", async () => {
    const fetcher = vi.fn(async () => json(summary));
    await expect(client(fetcher).rotateSecret("secret-1", "x".repeat(8193)))
      .rejects.toMatchObject({ name: "WorkspaceApiError", kind: "http", status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
