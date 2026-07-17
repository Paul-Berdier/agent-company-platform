/**
 * Données de démonstration du mode wallpaper autonome : utilisées quand le
 * backend est injoignable (Wallpaper Engine, écran secondaire hors ligne...).
 * Aucune tâche n'est inventée côté rendu : ces données sont statiques et
 * l'overlay affiche clairement « DEMO ».
 */

import type { OfficeConfig, Overview } from "@acp/contracts";

export const MOCK_OVERVIEW: Overview = {
  organizations: [{ id: "org", name: "Virtual Company", description: "" }],
  workspaces: [
    { id: "ws", organization_id: "org", name: "Démo", kind: "demo", description: "" },
  ],
  departments: [
    { id: "d-dev", workspace_id: "ws", name: "Software Engineering",
      department_type: "software-engineering", office_theme: "dev-floor", config: {} },
    { id: "d-data", workspace_id: "ws", name: "Data Science",
      department_type: "data-science", office_theme: "data-lab", config: {} },
  ],
  projects: [
    { id: "p-web", workspace_id: "ws", department_id: "d-dev", name: "Plateforme Web",
      project_type: "web-app", description: "", status: "active" },
    { id: "p-pipe", workspace_id: "ws", department_id: "d-data", name: "Pipeline",
      project_type: "data-pipeline", description: "", status: "active" },
  ],
  teams: [
    { id: "t-web", project_id: "p-web", name: "Web Team", mission: "" },
    { id: "t-data", project_id: "p-pipe", name: "Data Team", mission: "" },
  ],
  team_members: [],
  agents: [
    { id: "a1", workspace_id: "ws", team_id: "t-web", name: "Alice",
      role_id: "frontend-developer", module: "software-development", status: "working", capabilities: [] },
    { id: "a2", workspace_id: "ws", team_id: "t-web", name: "Bob",
      role_id: "backend-developer", module: "software-development", status: "idle", capabilities: [] },
    { id: "a3", workspace_id: "ws", team_id: "t-web", name: "Chloé",
      role_id: "qa-engineer", module: "software-development", status: "reviewing", capabilities: [] },
    { id: "a7", workspace_id: "ws", team_id: "t-web", name: "Grace",
      role_id: "product-designer", module: "software-development", status: "idle", capabilities: [] },
    { id: "a4", workspace_id: "ws", team_id: "t-data", name: "David",
      role_id: "data-engineer", module: "data-science", status: "working", capabilities: [] },
    { id: "a5", workspace_id: "ws", team_id: "t-data", name: "Emma",
      role_id: "data-scientist", module: "data-science", status: "idle", capabilities: [] },
    { id: "a6", workspace_id: "ws", team_id: "t-data", name: "Farid",
      role_id: "ml-engineer", module: "data-science", status: "thinking", capabilities: [] },
  ],
  tasks: [
    { id: "k1", project_id: "p-web", team_id: "t-web", agent_instance_id: "a1",
      title: "Interface de supervision", status: "in_progress", workflow_step: null, priority: 2 },
    { id: "k2", project_id: "p-pipe", team_id: "t-data", agent_instance_id: "a4",
      title: "Ingestion quotidienne", status: "in_progress", workflow_step: null, priority: 1 },
  ],
};

export const MOCK_CONFIGS: Record<string, OfficeConfig> = {
  "d-dev": {
    department_id: "d-dev",
    department_type: "software-engineering",
    office_theme: "dev-floor",
    stations: [
      { id: "desk-1", name: "Desk", kind: "desk", x: 1, y: 3 },
      { id: "desk-2", name: "Desk", kind: "desk", x: 4, y: 3 },
      { id: "desk-3", name: "Desk", kind: "desk", x: 7, y: 3 },
      { id: "desk-4", name: "Desk", kind: "desk", x: 4, y: 6 },
      { id: "board", name: "Board", kind: "whiteboard", x: 4, y: 1 },
      { id: "coffee", name: "Coffee", kind: "coffee-machine", x: 9, y: 1 },
      { id: "plant", name: "Plant", kind: "plant", x: 0, y: 1 },
    ],
    available_animations: [],
    status_mapping: { idle: "coffee", thinking: "think", working: "type", reviewing: "point" },
  },
  "d-data": {
    department_id: "d-data",
    department_type: "data-science",
    office_theme: "data-lab",
    stations: [
      { id: "desk-1", name: "Desk", kind: "desk", x: 1, y: 3 },
      { id: "desk-2", name: "Desk", kind: "desk", x: 4, y: 3 },
      { id: "rack", name: "Rack", kind: "server-rack", x: 10, y: 3 },
      { id: "board", name: "Board", kind: "whiteboard", x: 6, y: 1 },
      { id: "plant", name: "Plant", kind: "plant", x: 11, y: 1 },
    ],
    available_animations: [],
    status_mapping: { idle: "coffee", thinking: "think", working: "chart", reviewing: "think" },
  },
};
