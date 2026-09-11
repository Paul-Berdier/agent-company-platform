import { describe, expect, it, vi } from "vitest";

import {
  MissionQueueError,
  WorkspaceApiClient,
  WorkspaceApiError,
  readOptionalSessionToken,
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
  acceptanceCriteria: "Les assertions passent",
  autonomy: "isolated_work",
  priority: 2,
};

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function task(status: string) {
  return {
    id: "task-123",
    project_id: mission.projectId,
    team_id: null,
    agent_instance_id: null,
    title: mission.title,
    status,
    workflow_step: null,
    priority: mission.priority,
  };
}

describe("WorkspaceApiClient", () => {
  it("charge l’overview réel et transmet le token de session optionnel", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => json(overview));
    const client = new WorkspaceApiClient({
      baseUrl: "https://api.example.test/",
      sessionToken: "secret-session-token",
      fetcher,
    });

    await expect(client.fetchOverview()).resolves.toEqual(overview);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example.test/overview");
    const headers = fetcher.mock.calls[0][1]?.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer secret-session-token");
  });

  it("vérifie les réponses de création et de mise en file", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json(task("backlog"), 200))
      .mockResolvedValueOnce(json(task("queued"), 200));
    const client = new WorkspaceApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.createAndQueueMission(mission)).resolves.toMatchObject({
      created: { id: "task-123", status: "backlog" },
      queued: { id: "task-123", status: "queued" },
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[1][0]).toBe(
      "https://api.example.test/tasks/task-123/queue",
    );
    const createBody = JSON.parse(String(fetcher.mock.calls[0][1]?.body));
    expect(createBody).toMatchObject({
      project_id: mission.projectId,
      title: mission.title,
      description: mission.objective,
      meta: {
        kind: "mission",
        expected_result: mission.expectedResult,
        acceptance_criteria: mission.acceptanceCriteria,
        autonomy: mission.autonomy,
      },
    });
  });

  it("signale distinctement une tâche créée mais non mise en file", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json(task("backlog")))
      .mockResolvedValueOnce(json({ detail: "runner indisponible" }, 503));
    const client = new WorkspaceApiClient({ baseUrl: "https://api.example.test", fetcher });

    const error = await client.createAndQueueMission(mission).catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(MissionQueueError);
    expect(error).toMatchObject({ taskId: "task-123" });
    expect((error as MissionQueueError).cause).toMatchObject({ kind: "http", status: 503 });
  });

  it("refuse une mise en file dont la réponse ne confirme pas queued", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json(task("backlog")))
      .mockResolvedValueOnce(json(task("in_progress")));
    const client = new WorkspaceApiClient({ baseUrl: "https://api.example.test", fetcher });

    await expect(client.createAndQueueMission(mission)).rejects.toMatchObject({
      name: "MissionQueueError",
      taskId: "task-123",
      cause: { kind: "invalid_response" },
    });
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

describe("token de session", () => {
  it("reste optionnel et ignore une valeur vide", () => {
    expect(readOptionalSessionToken({ getItem: () => "  token  " })).toBe("token");
    expect(readOptionalSessionToken({ getItem: () => "   " })).toBeNull();
  });
});
