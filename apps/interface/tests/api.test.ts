import { describe, expect, it } from "vitest";
import { envelopper, ErreurApi, lireMeta, oublierMeta, ROUTE_META } from "../src/api";
import { ApiErrorHermes, installerSdk } from "./sdk-factice";

describe("enveloppe des erreurs de l'API", () => {
  it("reconnaît l'ApiError de Hermes 0.21.5", () => {
    const e = envelopper(new ApiErrorHermes("The server could not find what the dashboard asked for.", 404,
                                            '{"detail":"Not Found"}'));
    expect([e.genre, e.statut, e.detail]).toEqual(["requete", 404, '{"detail":"Not Found"}']);
    const r = envelopper(new ApiErrorHermes("Hermes dashboard cannot reach the Hermes service.", 0, "TypeError: x"));
    expect([r.genre, r.statut, r.detail]).toEqual(["reseau", null, "TypeError: x"]);
  });

  it("reconnaît l'ancienne forme « <statut>: <corps> » et les autres erreurs", () => {
    expect(envelopper(new Error('503: {"detail":"x"}'))).toMatchObject({ genre: "requete", statut: 503 });
    expect(envelopper(new TypeError("Failed to fetch"))).toMatchObject({ genre: "reseau", statut: null });
    expect(envelopper("bizarre")).toMatchObject({ genre: "inattendue", statut: null, detail: "bizarre" });
    const deja = new ErreurApi("requete", 500, "x");
    expect(envelopper(deja)).toBe(deja);
    expect(envelopper(new Error("x".repeat(5000))).detail.length).toBe(2000);
  });

  it("une seule requête /v1/meta à la fois, oubliée après une erreur", async () => {
    oublierMeta();
    const installation = installerSdk({ [ROUTE_META]: { contrat: "acp-poste/1" } });
    await Promise.all([lireMeta(1000), lireMeta(2000)]);
    expect(installation.appels).toEqual([ROUTE_META]);
    await lireMeta(20_000);
    expect(installation.appels).toEqual([ROUTE_META, ROUTE_META]);
    oublierMeta();
    const panne = installerSdk({});
    await expect(lireMeta(1000)).rejects.toMatchObject({ genre: "requete", statut: 404 });
    await expect(lireMeta(1001)).rejects.toBeInstanceOf(ErreurApi);
    expect(panne.appels).toEqual([ROUTE_META, ROUTE_META]);
  });
});
