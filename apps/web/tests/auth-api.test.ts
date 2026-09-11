import { describe, expect, it, vi } from "vitest";

import { AuthApiClient } from "../src/auth-api";

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const session = {
  user: {
    id: "user-1",
    login: "paul",
    display_name: "Paul",
    role: "owner",
  },
  csrf_token: "csrf-rotated",
  expires_at: "2026-09-12T08:00:00Z",
};

describe("AuthApiClient", () => {
  it("détecte le bootstrap sans demander de session", async () => {
    const fetcher = vi.fn(async () => json({ bootstrap_required: true }));
    const client = new AuthApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.fetchStatus()).resolves.toEqual({ bootstrap_required: true });
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/auth/status");
    expect(fetcher.mock.calls[0][1]?.credentials).toBe("include");
  });

  it("initialise le propriétaire avec le jeton dédié, jamais comme Bearer", async () => {
    const fetcher = vi.fn(async () => json(session, 201));
    const client = new AuthApiClient({ baseUrl: "https://api.example.test", fetcher });

    await client.bootstrap({
      login: " paul ",
      displayName: " Paul ",
      password: "long-password",
      bootstrapToken: " bootstrap-secret ",
    });

    const init = fetcher.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("X-ACP-Bootstrap-Token")).toBe("bootstrap-secret");
    expect(headers.get("Authorization")).toBeNull();
    expect(headers.get("X-CSRF-Token")).toBeNull();
    expect(JSON.parse(String(init.body))).toEqual({
      login: "paul",
      display_name: "Paul",
      password: "long-password",
    });
  });

  it("conserve le CSRF seulement en mémoire pour les mutations suivantes", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ status: "signed_out" }));
    const client = new AuthApiClient({ baseUrl: "https://api.example.test", fetcher });

    await client.login({ login: "paul", password: "long-password" });
    const loginHeaders = fetcher.mock.calls[0][1]?.headers as Headers;
    expect(loginHeaders.get("X-CSRF-Token")).toBeNull();

    await client.logout();
    const logoutHeaders = fetcher.mock.calls[1][1]?.headers as Headers;
    expect(logoutHeaders.get("X-CSRF-Token")).toBe("csrf-rotated");
    expect(logoutHeaders.get("Authorization")).toBeNull();
  });

  it("refuse un contrat de session sans jeton CSRF", async () => {
    const client = new AuthApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => json({ ...session, csrf_token: "" }),
    });
    await expect(client.fetchSession()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});
