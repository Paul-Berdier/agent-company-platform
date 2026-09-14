import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { NAVIGATION_ITEMS } from "../src/workspace-model";

const workspaceSource = readFileSync(new URL("../src/workspace.ts", import.meta.url), "utf8");
const uiSource = readFileSync(new URL("../src/automation-ui.ts", import.meta.url), "utf8");

function functionBody(source: string, name: string): string {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`fonction introuvable : ${name}`);
  const end = source.indexOf("\n}", start);
  if (end < 0) throw new Error(`fin de fonction introuvable : ${name}`);
  return source.slice(start, end + 2);
}

describe("câblage des automatisations", () => {
  it("rend la route accessible et la monte avec le client HTTP authentifié du shell", () => {
    expect(NAVIGATION_ITEMS.find((item) => item.id === "automations")?.configured).toBe(true);
    expect(workspaceSource).toMatch(/import \{ renderAutomations, resetAutomationUiState, unmountAutomationUi \} from "\.\/automation-ui";/);
    expect(functionBody(workspaceSource, "renderCurrentRoute")).toMatch(/renderAutomations\(content, http\)/);
    expect(functionBody(workspaceSource, "renderCurrentRoute")).toMatch(/currentRoute !== "automations"\) unmountAutomationUi\(\)/);
    expect(workspaceSource).not.toMatch(/renderAutomations\([^)]*new WorkspaceHttpClient/);
  });

  it("relie l’accueil aux automatisations et aux livrables réellement disponibles", () => {
    const home = functionBody(workspaceSource, "renderHome");
    expect(home).toContain('routeLink("/automations", "Automatiser")');
    expect(home).toContain('routeLink("/library", "Parcourir les livrables")');
    expect(home).not.toContain("Planificateur non configuré");
    expect(home).not.toContain("Bibliothèque sécurisée non configurée");
  });

  it("purge les routines, secrets à affichage unique et alertes lors d’un changement de compte", () => {
    expect(functionBody(workspaceSource, "resetPrivateWorkspaceState")).toMatch(/resetAutomationUiState\(\);/);
    expect(functionBody(uiSource, "resetAutomationUiState")).toMatch(/Object\.assign\(state, initialState\(\)\)/);
    expect(functionBody(uiSource, "resetAutomationUiState")).toMatch(/Object\.assign\(draft, initialDraft\(\)\)/);
    expect(functionBody(uiSource, "unmountAutomationUi")).toMatch(/clearDetailState\(\)/);
    expect(functionBody(uiSource, "clearDetailState")).toMatch(/state\.oneTimeSecret = null/);
    expect(functionBody(uiSource, "clearDetailState")).toMatch(/state\.webhook = null/);
    expect(functionBody(uiSource, "clearDetailState")).toMatch(/state\.runs = \[\]/);
  });

  it("n’affiche que le canal de notification réellement implémenté", () => {
    expect(uiSource).toContain("Canal réellement disponible : in-app uniquement");
    expect(uiSource).toContain('channel: "in_app"');
    expect(uiSource).not.toMatch(/<option[^>]*>(Courriel|SMS|Slack)/i);
  });
});
