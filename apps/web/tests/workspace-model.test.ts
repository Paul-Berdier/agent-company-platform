import { describe, expect, it } from "vitest";

import {
  NAVIGATION_ITEMS,
  isActiveTask,
  routeFromPathname,
  taskOutcomeRate,
  taskStatusLabel,
} from "../src/workspace-model";

const task = (status: string) => ({
  id: `task-${status}`,
  project_id: "project-1",
  team_id: null,
  agent_instance_id: null,
  title: status,
  status: status as "backlog" | "queued" | "planning" | "in_progress" | "review" | "blocked" | "done" | "failed",
  workflow_step: null,
  priority: 3,
});

describe("navigation du workspace", () => {
  it("expose la navigation produit compacte demandée", () => {
    expect(NAVIGATION_ITEMS.map((item) => item.label)).toEqual([
      "Accueil",
      "Projets",
      "Conversations",
      "Missions",
      "Automatisations",
      "Bibliothèque",
      "Connexions",
    ]);
    expect(NAVIGATION_ITEMS.find((item) => item.id === "conversations")?.configured).toBe(true);
    expect(NAVIGATION_ITEMS.find((item) => item.id === "connections")?.configured).toBe(true);
    expect(NAVIGATION_ITEMS.find((item) => item.id === "automations")?.configured).toBe(false);
  });

  it("résout les URLs et tolère un slash final", () => {
    expect(routeFromPathname("/")).toBe("home");
    expect(routeFromPathname("/projects/")).toBe("projects");
    expect(routeFromPathname("/missions")).toBe("missions");
    expect(routeFromPathname("/route-inconnue")).toBe("home");
  });
});

describe("indicateurs honnêtes", () => {
  it("retourne un résultat inconnu sans tâche finalisée", () => {
    expect(taskOutcomeRate([task("queued"), task("in_progress")])).toEqual({
      percentage: null,
      completed: 0,
      failed: 0,
      sampleSize: 0,
    });
  });

  it("calcule le taux uniquement sur les résultats observés", () => {
    expect(taskOutcomeRate([task("done"), task("done"), task("failed"), task("backlog")])).toEqual({
      percentage: 66.7,
      completed: 2,
      failed: 1,
      sampleSize: 3,
    });
  });

  it("identifie les états actifs sans assimiler le backlog à une exécution", () => {
    expect(isActiveTask(task("queued"))).toBe(true);
    expect(isActiveTask(task("review"))).toBe(true);
    expect(isActiveTask(task("blocked"))).toBe(true);
    expect(isActiveTask(task("backlog"))).toBe(false);
    expect(taskStatusLabel("in_progress")).toBe("En cours");
    expect(taskStatusLabel("blocked")).toBe("Bloquée");
  });
});
