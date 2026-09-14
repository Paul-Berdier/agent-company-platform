import { describe, expect, it, vi } from "vitest";

import {
  buildRoutineAutomationInput,
  missionCanBecomeRoutine,
  prepareRoutineCreationAttempt,
  routineCreateResultIsUncertain,
  routineNameForMission,
  settleRoutineCreationAttempt,
} from "../src/mission-routine";
import {
  WorkspaceApiError,
  type MissionRunResource,
  type MissionSummary,
} from "../src/workspace-api";

const acceptedRun: MissionRunResource = {
  id: "run-current",
  mission_id: "mission-1",
  attempt_number: 2,
  fencing_token: 2,
  status: "succeeded",
  stop_requested: false,
  technical_validation: {
    status: "passed",
    summary: "Tests réussis",
    checked_at: "2026-09-14T08:30:00Z",
  },
  user_acceptance: {
    status: "accepted",
    comment: "Résultat validé",
    decided_by: "owner-1",
    decided_at: "2026-09-14T08:31:00Z",
  },
  evidence: [],
  started_at: "2026-09-14T08:00:00Z",
  finished_at: "2026-09-14T08:29:00Z",
  created_at: "2026-09-14T08:00:00Z",
};

const acceptedMission: MissionSummary = {
  id: "mission-1",
  project_id: "project-1",
  team_id: "team-1",
  agent_instance_id: "agent-1",
  title: "Vérifier les sauvegardes",
  objective: "Vérifier que chaque sauvegarde est restaurable.",
  expected_outcome: "Un rapport signé et toutes les restaurations réussies.",
  acceptance_criteria: ["Le rapport existe", "La restauration de test passe"],
  autonomy: {
    mode: "bounded",
    allowed_actions: ["read", "restore_sandbox"],
    forbidden_actions: ["delete_production"],
    approval_required_actions: ["external_effect"],
  },
  resources: [{
    kind: "backup_store",
    identifier: "nightly",
    access: "read",
    description: "Sauvegardes nocturnes",
  }],
  budget: {
    max_cost: 12.5,
    currency: "EUR",
    max_tokens: 20_000,
    max_tool_calls: 80,
  },
  duration_seconds: 3_600,
  priority: 2,
  required_capabilities: ["backup", "reporting"],
  status: "succeeded",
  current_run: acceptedRun,
  created_at: "2026-09-14T08:00:00Z",
};

describe("transformation d’une mission acceptée en routine", () => {
  it("n’affiche l’action que pour la tentative courante réussie, validée et acceptée", () => {
    expect(missionCanBecomeRoutine(acceptedMission, acceptedRun, true)).toBe(true);

    const historical = { ...acceptedRun, id: "run-old", attempt_number: 1 };
    expect(missionCanBecomeRoutine(acceptedMission, historical, false)).toBe(false);
    expect(missionCanBecomeRoutine(acceptedMission, acceptedRun, false)).toBe(false);
    expect(missionCanBecomeRoutine(
      acceptedMission,
      { ...acceptedRun, status: "failed" },
      true,
    )).toBe(false);
    expect(missionCanBecomeRoutine(
      acceptedMission,
      { ...acceptedRun, technical_validation: { ...acceptedRun.technical_validation, status: "pending" } },
      true,
    )).toBe(false);
    expect(missionCanBecomeRoutine(
      acceptedMission,
      { ...acceptedRun, user_acceptance: { ...acceptedRun.user_acceptance, status: "pending" } },
      true,
    )).toBe(false);
  });

  it("préremplit sans perte une routine qui naîtra en pause côté serveur", () => {
    const input = buildRoutineAutomationInput(acceptedMission, {
      name: "  Contrôle sauvegardes  ",
      scheduleKind: "cron",
      expression: " 0 9 * * 1-5 ",
      timezone: " Europe/Paris ",
    });

    expect(input).toEqual({
      name: "Contrôle sauvegardes",
      description: "Routine créée depuis la mission acceptée « Vérifier les sauvegardes » (mission-1).",
      schedule: { kind: "cron", expression: "0 9 * * 1-5", timezone: "Europe/Paris" },
      mission_template: {
        title: acceptedMission.title,
        objective: acceptedMission.objective,
        expected_outcome: acceptedMission.expected_outcome,
        acceptance_criteria: acceptedMission.acceptance_criteria,
        autonomy: acceptedMission.autonomy,
        resources: acceptedMission.resources,
        budget: acceptedMission.budget,
        duration_seconds: acceptedMission.duration_seconds,
        team_id: acceptedMission.team_id,
        agent_instance_id: acceptedMission.agent_instance_id,
        priority: acceptedMission.priority,
        required_capabilities: acceptedMission.required_capabilities,
      },
      catchup_policy: "skip",
      max_concurrent_runs: 1,
    });
    expect(input).not.toHaveProperty("enabled");

    input.mission_template.acceptance_criteria.push("Critère local");
    input.mission_template.autonomy.allowed_actions?.push("action_locale");
    const copiedResource = input.mission_template.resources?.[0];
    if (copiedResource) copiedResource.description = "Description locale";
    expect(acceptedMission.acceptance_criteria).not.toContain("Critère local");
    expect(acceptedMission.autonomy.allowed_actions).not.toContain("action_locale");
    expect(acceptedMission.resources[0]?.description).toBe("Sauvegardes nocturnes");
  });

  it("borne les champs éditables avant tout appel réseau", () => {
    expect(() => buildRoutineAutomationInput(acceptedMission, {
      name: "   ",
      scheduleKind: "cron",
      expression: "0 9 * * *",
      timezone: "Europe/Paris",
    })).toThrow(/nom/);
    expect(() => buildRoutineAutomationInput(acceptedMission, {
      name: "Routine",
      scheduleKind: "cron",
      expression: " ",
      timezone: "Europe/Paris",
    })).toThrow(/planification/);
    expect(routineNameForMission({ ...acceptedMission, title: "x".repeat(400) })).toHaveLength(200);
  });

  it("réutilise strictement la même clé et le même corps après un résultat incertain", () => {
    const input = buildRoutineAutomationInput(acceptedMission, {
      name: "Contrôle sauvegardes",
      scheduleKind: "interval",
      expression: "900",
      timezone: "Europe/Paris",
    });
    const createKey = vi.fn(() => "stable-key");
    const first = prepareRoutineCreationAttempt(null, input, createKey);
    const changed = buildRoutineAutomationInput(acceptedMission, {
      name: "Nom changé",
      scheduleKind: "interval",
      expression: "1800",
      timezone: "UTC",
    });
    const retry = prepareRoutineCreationAttempt(first, changed, createKey);

    expect(retry).toBe(first);
    expect(retry.key).toBe("stable-key");
    expect(retry.input).toBe(input);
    expect(createKey).toHaveBeenCalledTimes(1);

    const offline = new WorkspaceApiError("Réseau coupé", "offline");
    expect(routineCreateResultIsUncertain(offline)).toBe(true);
    expect(settleRoutineCreationAttempt(first, offline)).toBe(first);
    expect(settleRoutineCreationAttempt(
      first,
      new WorkspaceApiError("Payload refusé", "http", 422),
    )).toBeNull();
    expect(routineCreateResultIsUncertain(
      new WorkspaceApiError("Réponse illisible", "invalid_response"),
    )).toBe(true);
    expect(routineCreateResultIsUncertain(
      new WorkspaceApiError("Serveur indisponible", "http", 503),
    )).toBe(true);
  });
});
