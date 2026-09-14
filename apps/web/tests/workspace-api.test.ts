import { describe, expect, it, vi } from "vitest";

import {
  WorkspaceApiClient,
  WorkspaceApiError,
  type MissionInput,
} from "../src/workspace-api";

const overview = {
  organizations: [],
  workspaces: [],
  departments: [],
  projects: [],
  teams: [],
  team_members: [],
  agents: [],
  tasks: [],
};

const mission: MissionInput = {
  projectId: "project/with slash",
  title: "Vérifier le produit",
  objective: "Exécuter une vérification déterministe.",
  expectedResult: "Un rapport vérifiable",
  acceptanceCriteria: ["Les assertions passent"],
  autonomy: "read_only",
  priority: 2,
  durationSeconds: 3600,
  maxToolCalls: 50,
};

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function missionRun(status = "queued") {
  return {
    id: "run-1",
    mission_id: "mission-1",
    attempt_number: 1,
    fencing_token: 1,
    status,
    stop_requested: false,
    technical_validation: { status: "pending", summary: "", checked_at: null },
    user_acceptance: {
      status: "pending",
      comment: "",
      decided_by: null,
      decided_at: null,
    },
    evidence: [],
    started_at: null,
    finished_at: null,
    created_at: "2026-09-11T10:00:00Z",
  };
}

function missionDetail(status = "queued") {
  const run = missionRun(status);
  return {
    id: "mission-1",
    project_id: mission.projectId,
    team_id: null,
    agent_instance_id: "agent-1",
    title: mission.title,
    objective: mission.objective,
    expected_outcome: mission.expectedResult,
    acceptance_criteria: mission.acceptanceCriteria,
    autonomy: {
      mode: "bounded",
      allowed_actions: ["read"],
      forbidden_actions: ["deploy"],
      approval_required_actions: ["git_publish"],
    },
    resources: [{
      kind: "git_repository",
      identifier: "workspace",
      access: "write",
      description: "Dépôt de la mission",
    }],
    budget: {
      max_cost: null,
      currency: "EUR",
      max_tokens: 10_000,
      max_tool_calls: mission.maxToolCalls,
    },
    duration_seconds: mission.durationSeconds,
    priority: mission.priority,
    required_capabilities: ["git"],
    status,
    current_run: run,
    runs: [run],
    created_at: "2026-09-11T10:00:00Z",
  };
}

describe("WorkspaceApiClient", () => {
  it("charge l’overview réel avec le cookie cross-origin sans Bearer navigateur", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => json(overview));
    const client = new WorkspaceApiClient({
      baseUrl: "https://api.example.test/",
      fetcher,
    });

    await expect(client.fetchOverview()).resolves.toEqual(overview);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/overview");
    const headers = fetcher.mock.calls[0][1]?.headers as Headers;
    expect(headers.get("Authorization")).toBeNull();
    expect(fetcher.mock.calls[0][1]?.credentials).toBe("include");
  });

  it("crée atomiquement une mission et sa première tentative", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json(missionDetail(), 201));
    const client = new WorkspaceApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-current");

    await expect(client.createMission(mission, "create-key")).resolves.toMatchObject({
      id: "mission-1",
      status: "queued",
      current_run: { attempt_number: 1, technical_validation: { status: "pending" } },
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/missions");
    const createBody = JSON.parse(String(fetcher.mock.calls[0][1]?.body));
    const createHeaders = fetcher.mock.calls[0][1]?.headers as Headers;
    expect(createHeaders.get("X-CSRF-Token")).toBe("csrf-current");
    expect(createHeaders.get("Idempotency-Key")).toBe("create-key");
    expect(createBody).toMatchObject({
      project_id: mission.projectId,
      title: mission.title,
      objective: mission.objective,
      expected_outcome: mission.expectedResult,
      acceptance_criteria: mission.acceptanceCriteria,
      autonomy: { mode: "supervised", allowed_actions: [] },
      resources: [],
      budget: { max_tool_calls: 50 },
      duration_seconds: 3600,
    });
  });

  it("conserve tous les champs réutilisables d’une mission et refuse une réponse tronquée", async () => {
    const complete = missionDetail("succeeded");
    const validClient = new WorkspaceApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => json([complete]),
    });
    await expect(validClient.fetchMissions()).resolves.toEqual([complete]);

    for (const key of [
      "team_id",
      "agent_instance_id",
      "autonomy",
      "resources",
      "budget",
      "required_capabilities",
    ]) {
      const truncated: Record<string, unknown> = { ...complete };
      delete truncated[key];
      const client = new WorkspaceApiClient({
        baseUrl: "https://api.example.test",
        fetcher: async () => json([truncated]),
      });
      await expect(client.fetchMissions()).rejects.toMatchObject({
        kind: "invalid_response",
        status: null,
      });
    }

    const noLimit = {
      ...complete,
      budget: { max_cost: null, currency: "EUR", max_tokens: null, max_tool_calls: null },
    };
    const invalidBudgetClient = new WorkspaceApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => json([noLimit]),
    });
    await expect(invalidBudgetClient.fetchMissions()).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("reprend l’onboarding et crée le premier projet via la route atomique", async () => {
    const project = {
      id: "project-1",
      workspace_id: "workspace-personal",
      department_id: null,
      name: "Premier projet",
      project_type: "software",
      description: "Périmètre réel",
      status: "active",
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({
        bootstrap_completed: true,
        hermes_configured: false,
        hermes_ready: false,
        hermes_status: "unavailable",
        project_count: 0,
        runner_ready: false,
      }))
      .mockResolvedValueOnce(json(project, 201));
    const client = new WorkspaceApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-current");

    await expect(client.fetchOnboardingStatus()).resolves.toMatchObject({ project_count: 0 });
    await expect(client.createOnboardingProject({
      name: " Premier projet ",
      projectType: "software",
      description: " Périmètre réel ",
    })).resolves.toEqual(project);
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/onboarding/projects");
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-current");
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({
      name: "Premier projet",
      project_type: "software",
      description: "Périmètre réel",
    });
  });

  it("pilote l’arrêt et la relance avec des clés d’idempotence explicites", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({
        mission_id: "mission-1",
        run: { ...missionRun("stopping"), stop_requested: true },
        already_stopped: false,
      }))
      .mockResolvedValueOnce(json({ ...missionRun(), attempt_number: 2, fencing_token: 2 }));
    const client = new WorkspaceApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-current");

    await expect(client.stopMission("mission-1", "stop-key")).resolves.toMatchObject({
      run: { status: "stopping", stop_requested: true },
    });
    await expect(client.retryMission("mission-1", "nouvelle tentative", "retry-key")).resolves.toMatchObject({
      attempt_number: 2,
      fencing_token: 2,
    });
    expect((fetcher.mock.calls[0][1]?.headers as Headers).get("Idempotency-Key")).toBe("stop-key");
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("Idempotency-Key")).toBe("retry-key");
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({ reason: "nouvelle tentative" });
  });

  it("sépare l’acceptation utilisateur et le commentaire de tentative", async () => {
    const acceptedRun = {
      ...missionRun("succeeded"),
      technical_validation: {
        status: "passed",
        summary: "Assertions réussies",
        checked_at: "2026-09-11T10:05:00Z",
      },
      user_acceptance: {
        status: "accepted",
        comment: "",
        decided_by: "owner-1",
        decided_at: "2026-09-11T10:06:00Z",
      },
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json(acceptedRun))
      .mockResolvedValueOnce(json({
        id: "comment-1",
        mission_id: "mission-1",
        run_id: "run-1",
        author_user_id: "owner-1",
        body: "Preuve vérifiée",
        created_at: "2026-09-11T10:07:00Z",
      }, 201))
      .mockResolvedValueOnce(json([{
        id: "comment-1",
        mission_id: "mission-1",
        run_id: "run-1",
        author_user_id: "owner-1",
        body: "Preuve vérifiée",
        created_at: "2026-09-11T10:07:00Z",
      }]));
    const client = new WorkspaceApiClient({ baseUrl: "https://api.example.test", fetcher });
    client.http.setCsrfToken("csrf-current");

    await expect(client.decideMissionAcceptance("mission-1", "run-1", "accepted"))
      .resolves.toMatchObject({ user_acceptance: { status: "accepted" } });
    await expect(client.addMissionComment("mission-1", "run-1", " Preuve vérifiée ", "comment-key"))
      .resolves.toMatchObject({ body: "Preuve vérifiée" });
    expect(fetcher.mock.calls[0][0]).toBe(
      "https://api.example.test/missions/mission-1/runs/run-1/acceptance",
    );
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({
      run_id: "run-1",
      body: "Preuve vérifiée",
    });
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("Idempotency-Key"))
      .toBe("comment-key");
    await expect(client.fetchMissionComments("mission-1"))
      .resolves.toEqual([expect.objectContaining({ id: "comment-1", run_id: "run-1" })]);
    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/missions/mission-1/comments",
    );
  });

  it("résout directement une mission depuis un identifiant de run", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json(missionDetail()));
    const client = new WorkspaceApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.fetchMissionByRun("run/1")).resolves.toMatchObject({ id: "mission-1" });
    expect(fetcher.mock.calls[0][0]).toBe(
      "https://api.example.test/missions/by-run/run%2F1",
    );
  });

  it("distingue accès refusé et indisponibilité réseau", async () => {
    const forbidden = new WorkspaceApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => json({ detail: "forbidden" }, 403),
    });
    await expect(forbidden.fetchOverview()).rejects.toMatchObject({
      name: "WorkspaceApiError",
      kind: "forbidden",
      status: 403,
    });

    const offline = new WorkspaceApiClient({
      baseUrl: "https://api.example.test",
      fetcher: async () => { throw new TypeError("network unavailable"); },
    });
    await expect(offline.fetchOverview()).rejects.toBeInstanceOf(WorkspaceApiError);
    await expect(offline.fetchOverview()).rejects.toMatchObject({ kind: "offline" });
  });
});
