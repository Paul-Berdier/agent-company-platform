/**
 * Tests du câblage du Studio dans le shell (`workspace.ts`).
 *
 * Un module d’écran livré mais jamais monté n’existe pas pour l’utilisateur : le lien
 * profond `/missions?run=<id>&vue=studio` de la spec §2.5/§10 doit être calculable par le
 * module lui-même, et le shell doit réellement l’importer, le monter et le purger.
 *
 * Deux natures de vérification ici :
 * 1. **comportement** — les fonctions pures du lien profond exposées par `studio-ui.ts` ;
 * 2. **contrat de câblage** — la source de `workspace.ts` est lue et les points de montage
 *    et de purge sont exigés. `workspace.ts` s’exécute au moment de son import (il monte le
 *    shell et lance l’authentification) : il n’est donc pas importable dans un test unitaire,
 *    et cette lecture de source est le seul garde-fou automatisable contre une régression qui
 *    rendrait le Studio de nouveau inatteignable.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  STUDIO_VIEW_PARAM,
  STUDIO_VIEW_VALUE,
  isStudioViewRequested,
  studioRouteLink,
} from "../src/studio-ui";

const workspaceSource = readFileSync(new URL("../src/workspace.ts", import.meta.url), "utf8");

/** Corps d’une fonction de premier niveau de `workspace.ts`, accolade fermante comprise. */
function functionBody(source: string, name: string): string {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`fonction introuvable : ${name}`);
  const end = source.indexOf("\n}", start);
  if (end < 0) throw new Error(`fin de fonction introuvable : ${name}`);
  return source.slice(start, end + 2);
}

describe("lien profond du Studio", () => {
  it("reconnaît la vue Studio demandée dans la chaîne de requête", () => {
    expect(isStudioViewRequested("?run=run-1&vue=studio")).toBe(true);
    expect(isStudioViewRequested(`?${STUDIO_VIEW_PARAM}=${STUDIO_VIEW_VALUE}`)).toBe(true);
    expect(isStudioViewRequested("?run=run-1")).toBe(false);
    expect(isStudioViewRequested("?vue=journal")).toBe(false);
    expect(isStudioViewRequested("")).toBe(false);
  });

  it("construit le lien profond d’une tentative en encodant l’identifiant", () => {
    expect(studioRouteLink("run-1")).toBe("/missions?run=run-1&vue=studio");
    expect(studioRouteLink("run/1 2")).toBe("/missions?run=run%2F1+2&vue=studio");
    expect(isStudioViewRequested(new URL(studioRouteLink("run-1"), "http://x").search)).toBe(true);
  });
});

describe("câblage du Studio dans workspace.ts", () => {
  it("importe le rendu et la purge du Studio", () => {
    expect(workspaceSource).toMatch(
      /import \{[^}]*renderStudio[^}]*resetStudioUiState[^}]*\} from "\.\/studio-ui";/s,
    );
    expect(workspaceSource).toMatch(/isStudioViewRequested/);
  });

  it("monte le Studio avec le client HTTP du shell, jamais avec un client neuf", () => {
    expect(workspaceSource).toMatch(/renderStudio\(\s*\w+,\s*http,/);
    // La règle du Lot D : aucun module d’écran ne fabrique son propre client.
    expect(workspaceSource).not.toMatch(/renderStudio\([^)]*new WorkspaceHttpClient/);
  });

  it("ouvre le Studio sur le lien profond d’une tentative", () => {
    const body = functionBody(workspaceSource, "renderMissions");
    expect(body).toMatch(/isStudioViewRequested\(/);
    expect(body).toMatch(/renderStudio\(/);
    expect(workspaceSource).toMatch(/studioRouteLink\(/);
  });

  it("purge l’état du Studio à la connexion et à la déconnexion", () => {
    const body = functionBody(workspaceSource, "resetPrivateWorkspaceState");
    expect(body).toMatch(/resetStudioUiState\(\);/);
  });

  it("ferme le flux du Studio en quittant l’écran", () => {
    const body = functionBody(workspaceSource, "renderCurrentRoute");
    expect(body).toMatch(/resetStudioUiState\(\);/);
  });
});
