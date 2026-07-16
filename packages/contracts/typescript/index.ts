// Types TypeScript miroir des contrats Pydantic (version 1.0).

export type TaskStatus =
  | "backlog" | "queued" | "planning" | "in_progress" | "review" | "done" | "failed";

export type AgentStatus =
  | "idle" | "thinking" | "working" | "reviewing" | "blocked" | "offline";

export interface Organization { id: string; name: string; description: string }

export interface Workspace {
  id: string; organization_id: string; name: string; kind: string; description: string;
}

export interface Department {
  id: string; workspace_id: string; name: string;
  department_type: string; office_theme: string; config: Record<string, unknown>;
}

export interface Project {
  id: string; workspace_id: string; department_id: string | null;
  name: string; project_type: string; description: string; status: string;
}

export interface Team { id: string; project_id: string; name: string; mission: string }

export interface TeamMember {
  team_id: string; agent_instance_id: string; role_id: string | null;
}

export interface AgentInstance {
  id: string; workspace_id: string; team_id: string | null; name: string;
  role_id: string; module: string; status: AgentStatus; capabilities: string[];
}

export interface TaskSummary {
  id: string; project_id: string; team_id: string | null;
  agent_instance_id: string | null; title: string; status: TaskStatus;
  workflow_step: string | null; priority: number;
}

export interface Overview {
  organizations: Organization[];
  workspaces: Workspace[];
  departments: Department[];
  projects: Project[];
  teams: Team[];
  team_members: TeamMember[];
  agents: AgentInstance[];
  tasks: TaskSummary[];
}

export interface AcpEvent {
  id: string; type: string; occurred_at: string;
  organization_id: string | null; workspace_id: string | null;
  department_id: string | null; project_id: string | null; team_id: string | null;
  agent_instance_id: string | null; task_id: string | null; task_run_id: string | null;
  payload: Record<string, unknown>;
}

export interface StationDef { id: string; name: string; kind: string; x: number; y: number }

export interface OfficeConfig {
  department_id?: string;
  department_type: string;
  office_theme: string;
  stations: StationDef[];
  available_animations: string[];
  status_mapping: Record<string, string>;
}
