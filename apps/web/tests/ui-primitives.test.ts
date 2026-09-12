import { describe, expect, it } from "vitest";

import { errorMessage, formatDateTime, normalizeApiError } from "../src/ui-primitives";
import { WorkspaceApiError } from "../src/workspace-api";

describe("formatDateTime", () => {
  it("formate en français sur le fuseau Europe/Paris (heure d'été)", () => {
    expect(formatDateTime("2026-09-11T10:30:00Z")).toMatch(/^11\/09\/2026,? 12:30$/);
  });

  it("bascule de jour selon Europe/Paris (heure d'hiver)", () => {
    expect(formatDateTime("2026-01-15T23:30:00Z")).toMatch(/^16\/01\/2026,? 00:30$/);
  });

  it("signale une date invalide sans lever", () => {
    expect(formatDateTime("pas une date")).toBe("Date inconnue");
    expect(formatDateTime("")).toBe("Date inconnue");
  });
});

describe("normalizeApiError", () => {
  it("conserve une erreur API telle quelle", () => {
    const error = new WorkspaceApiError("refusé", "forbidden", 403);
    expect(normalizeApiError(error, "repli")).toBe(error);
  });

  it("enveloppe toute autre erreur avec le message de repli", () => {
    const normalized = normalizeApiError(new TypeError("boom"), "Réponse inexploitable");
    expect(normalized).toBeInstanceOf(WorkspaceApiError);
    expect(normalized.message).toBe("Réponse inexploitable");
    expect(normalized.kind).toBe("invalid_response");
    expect(normalized.status).toBeNull();
    expect(normalizeApiError("chaîne", "repli").message).toBe("repli");
  });
});

describe("errorMessage", () => {
  it("décrit une API hors ligne sans données de démonstration", () => {
    const message = errorMessage(new WorkspaceApiError("x", "offline"));
    expect(message).toContain("ne répond pas");
    expect(message).toContain("démonstration");
  });

  it("distingue session expirée (401) et accès refusé (403)", () => {
    expect(errorMessage(new WorkspaceApiError("x", "forbidden", 401))).toContain("session a expiré");
    expect(errorMessage(new WorkspaceApiError("x", "forbidden", 403))).toContain("n’a pas accès");
  });

  it("retourne le message brut pour les autres erreurs", () => {
    expect(errorMessage(new WorkspaceApiError("Réponse mal formée", "invalid_response", 200)))
      .toBe("Réponse mal formée");
  });
});
