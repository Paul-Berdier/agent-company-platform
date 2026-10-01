// Routes de la page Poste (étape P5) : chemins exacts du greffon acp-poste, écritures en POST JSON par fetchJSON,
// jamais une route machine, refus d'une table lus entrée par entrée.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  confirmer,
  creerCode,
  refusDeLaTable,
  releverMaintenant,
  revoquer,
  ROUTE_CONFIRMATION,
  ROUTE_ENROLEMENT,
  ROUTE_POLITIQUE,
  ROUTE_POSTE,
  ROUTE_QUOTAS,
  ROUTE_RELEVE,
  ROUTE_RELEVE_ACCEPTE,
  ROUTE_REVOCATION,
  ROUTE_ROUTAGE,
  ROUTE_SURCHARGES,
  routeDesactiverSurcharge,
  validerTable,
} from "../src/poste/api";
import { FORMES } from "./fixtures-poste";
import { installerSdk } from "./sdk-factice";

describe("routes de la page Poste", () => {
  it("sont celles du greffon acp-poste (cahier P5 § 12.3)", () => {
    const racine = "/api/plugins/acp-poste/v1";
    expect([ROUTE_POSTE, ROUTE_ENROLEMENT, ROUTE_CONFIRMATION, ROUTE_REVOCATION, ROUTE_RELEVE, ROUTE_ROUTAGE,
            ROUTE_POLITIQUE, ROUTE_SURCHARGES, ROUTE_RELEVE_ACCEPTE, ROUTE_QUOTAS, routeDesactiverSurcharge(3)]).toEqual([
      `${racine}/poste`, `${racine}/poste/enrolement`, `${racine}/poste/confirmation`, `${racine}/poste/revocation`,
      `${racine}/poste/releve`, `${racine}/routage`, `${racine}/routage/politique`, `${racine}/routage/surcharges`,
      `${racine}/routage/releve-accepte`, `${racine}/quotas`, `${racine}/routage/surcharges/3/desactiver`]);
  });

  it("écrivent en POST JSON par le fetchJSON du SDK", async () => {
    const installation = installerSdk({
      [`POST ${ROUTE_ENROLEMENT}`]: FORMES.code, [`POST ${ROUTE_CONFIRMATION}`]: {}, [`POST ${ROUTE_REVOCATION}`]: {},
      [`POST ${ROUTE_RELEVE}`]: FORMES.releve_demande, [`POST ${ROUTE_ROUTAGE}`]: FORMES.routage,
    });
    await creerCode();
    await confirmer("m0123456789a", "3F9A-0C1B");
    await revoquer("m0123456789a", "PC perdu");
    await releverMaintenant();
    await validerTable({ "poste-codex": 1, "poste-claude": 2 }, { implementation: [{ voie: "poste-codex" }] });
    expect(installation.requetes.map((r) => [r.methode, r.url, r.corps, r.entetes["Content-Type"]])).toEqual([
      ["POST", ROUTE_ENROLEMENT, {}, "application/json"],
      ["POST", ROUTE_CONFIRMATION, { machine_id: "m0123456789a", empreinte: "3F9A-0C1B" }, "application/json"],
      ["POST", ROUTE_REVOCATION, { machine_id: "m0123456789a", motif: "PC perdu" }, "application/json"],
      ["POST", ROUTE_RELEVE, {}, "application/json"],
      ["POST", ROUTE_ROUTAGE, { releves: { "poste-codex": 1, "poste-claude": 2 },
                                classes: { implementation: [{ voie: "poste-codex" }] } }, "application/json"],
    ]);
  });

  it("lit les refus d'une table entrée par entrée", () => {
    const refus = refusDeLaTable(JSON.stringify(FORMES.refus_table));
    expect(refus.map((r) => [r.classe, r.rang])).toEqual([["implementation", 0]]);
    expect(refusDeLaTable("pas du JSON")).toEqual([]);
    expect(refusDeLaTable(JSON.stringify({ detail: { code: "releve_change", message: "x" } }))).toEqual([]);
  });

  it("la page n'appelle jamais une route machine (réservée au jeton du poste)", () => {
    const dossier = join(process.cwd(), "src", "poste");
    for (const nom of readdirSync(dossier)) {
      expect(readFileSync(join(dossier, nom), "utf8"), nom).not.toMatch(/machine\/v1/);
    }
  });
});
