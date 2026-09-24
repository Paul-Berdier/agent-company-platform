import type { AutomationCreate, AutomationScheduleKind } from "@acp/contracts";

import type {
  MissionRunResource,
  MissionSummary,
  WorkspaceApiError,
} from "./workspace-api";

export interface MissionRoutineDraftInput {
  name: string;
  scheduleKind: AutomationScheduleKind;
  expression: string;
  timezone: string;
}

export interface RoutineCreationAttempt {
  key: string;
  fingerprint: string;
  input: AutomationCreate;
}

/**
 * Une routine ne peut être dérivée que du résultat courant, techniquement validé
 * puis explicitement accepté. Une tentative historique ne doit jamais faire
 * réapparaître l'action, même si elle avait réussi auparavant.
 */
export function missionCanBecomeRoutine(
  mission: MissionSummary,
  run: MissionRunResource,
  isCurrentRun: boolean,
): boolean {
  return isCurrentRun
    && run.id === mission.current_run.id
    && run.status === "succeeded"
    && run.technical_validation.status === "passed"
    && run.user_acceptance.status === "accepted";
}

export function routineNameForMission(mission: MissionSummary): string {
  const suffix = " — routine";
  return `${mission.title.trim().slice(0, 200 - suffix.length)}${suffix}`;
}

/** Copie sans perte le contrat de mission accepté vers le gabarit récurrent. */
export function buildRoutineAutomationInput(
  mission: MissionSummary,
  draft: MissionRoutineDraftInput,
): AutomationCreate {
  const name = draft.name.trim();
  const expression = draft.expression.trim();
  const timezone = draft.timezone.trim();
  if (!name || name.length > 200) {
    throw new Error("Le nom de la routine doit contenir entre 1 et 200 caractères.");
  }
  if (!expression || expression.length > 200) {
    throw new Error("La planification doit contenir entre 1 et 200 caractères.");
  }
  if (!timezone || timezone.length > 64) {
    throw new Error("Le fuseau doit contenir entre 1 et 64 caractères.");
  }
  if (draft.scheduleKind !== "cron" && draft.scheduleKind !== "interval") {
    throw new Error("Le type de planification est invalide.");
  }

  return {
    name,
    description: `Routine créée depuis la mission acceptée « ${mission.title} » (${mission.id}).`,
    schedule: {
      kind: draft.scheduleKind,
      expression,
      timezone,
    },
    mission_template: {
      title: mission.title,
      objective: mission.objective,
      expected_outcome: mission.expected_outcome,
      acceptance_criteria: [...mission.acceptance_criteria],
      autonomy: {
        mode: mission.autonomy.mode,
        allowed_actions: [...mission.autonomy.allowed_actions],
        forbidden_actions: [...mission.autonomy.forbidden_actions],
        approval_required_actions: [...mission.autonomy.approval_required_actions],
      },
      resources: mission.resources.map((resource) => ({ ...resource })),
      budget: { ...mission.budget },
      duration_seconds: mission.duration_seconds,
      team_id: mission.team_id,
      agent_instance_id: mission.agent_instance_id,
      priority: mission.priority,
      required_capabilities: [...mission.required_capabilities],
      ...(mission.execution !== undefined ? {
        execution: mission.execution === null ? null : {
          ...mission.execution,
          executors: [...mission.execution.executors],
        },
      } : {}),
    },
    catchup_policy: "skip",
    max_concurrent_runs: 1,
  };
}

export function routineCreateResultIsUncertain(error: WorkspaceApiError): boolean {
  return error.kind === "offline"
    || error.kind === "invalid_response"
    || error.status === 408
    || (error.status !== null && error.status >= 500);
}

export function prepareRoutineCreationAttempt(
  current: RoutineCreationAttempt | null,
  input: AutomationCreate,
  createKey: () => string,
): RoutineCreationAttempt {
  if (current) return current;
  return {
    key: createKey(),
    fingerprint: JSON.stringify(input),
    input,
  };
}

export function settleRoutineCreationAttempt(
  attempt: RoutineCreationAttempt,
  error: WorkspaceApiError,
): RoutineCreationAttempt | null {
  return routineCreateResultIsUncertain(error) ? attempt : null;
}
