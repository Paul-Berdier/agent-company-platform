import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("../src/workspace.ts", import.meta.url), "utf8");

function functionBody(name: string): string {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`fonction introuvable : ${name}`);
  const end = source.indexOf("\n}", start);
  if (end < 0) throw new Error(`fin de fonction introuvable : ${name}`);
  return source.slice(start, end + 2);
}

describe("câblage mission acceptée vers routine", () => {
  it("conditionne le seul bouton de transformation au prédicat strict", () => {
    const render = functionBody("renderMissionList");
    expect(render).toContain("missionCanBecomeRoutine(mission, run, isCurrentRun)");
    expect(render).toContain("Transformer en routine");
    expect(render).toContain('toggle.setAttribute("aria-controls"');
    expect(render).toContain('toggle.setAttribute("aria-expanded"');
    expect(render).toMatch(/if \(routineEligible\)[\s\S]*Transformer en routine/);
  });

  it("présente explicitement le gabarit et confirme une création en pause", () => {
    const confirmation = functionBody("renderMissionRoutineConfirmation");
    for (const label of [
      "Objectif",
      "Résultat attendu",
      "Critères d’acceptation",
      "Autonomie",
      "Ressources",
      "Budget coût",
      "Équipe",
      "Agent",
      "Capacités requises",
      "Confirmer et créer en pause",
    ]) {
      expect(confirmation).toContain(label);
    }
    expect(confirmation).toContain('panel.setAttribute("aria-labelledby"');
    expect(confirmation).not.toContain("innerHTML");
  });

  it("attend et contrôle la réponse serveur avant tout succès", () => {
    const submit = functionBody("submitMissionRoutine");
    const request = submit.indexOf("await automationApi.createAutomation(");
    const success = submit.indexOf('tone: "success"');
    expect(request).toBeGreaterThanOrEqual(0);
    expect(success).toBeGreaterThan(request);
    expect(submit).toContain("attempt.input");
    expect(submit).toContain("attempt.key");
    expect(submit).toContain("settleRoutineCreationAttempt(attempt, failure)");
    expect(submit).toContain("created.enabled || created.project_id !== mission.project_id");
  });

  it("purge le brouillon et sa clé lors d’un changement de compte", () => {
    const reset = functionBody("resetPrivateWorkspaceState");
    expect(reset).toContain("missionRoutineDraft = null");
    expect(reset).toContain("missionRoutineFocusTarget = null");
  });
});
