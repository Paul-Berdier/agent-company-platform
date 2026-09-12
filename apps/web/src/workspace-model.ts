import type { TaskSummary } from "@acp/contracts";

export type WorkspaceRoute =
  | "home"
  | "projects"
  | "conversations"
  | "missions"
  | "automations"
  | "library"
  | "connections";

export interface NavigationItem {
  id: WorkspaceRoute;
  label: string;
  path: string;
  icon: string;
  configured: boolean;
}

export const NAVIGATION_ITEMS: readonly NavigationItem[] = [
  { id: "home", label: "Accueil", path: "/", icon: "⌂", configured: true },
  { id: "projects", label: "Projets", path: "/projects", icon: "▱", configured: true },
  { id: "conversations", label: "Conversations", path: "/conversations", icon: "◌", configured: true },
  { id: "missions", label: "Missions", path: "/missions", icon: "→", configured: true },
  { id: "automations", label: "Automatisations", path: "/automations", icon: "↻", configured: false },
  { id: "library", label: "Bibliothèque", path: "/library", icon: "◇", configured: true },
  { id: "connections", label: "Connexions", path: "/connections", icon: "⌁", configured: true },
] as const;

const ROUTE_BY_PATH = new Map(
  NAVIGATION_ITEMS.map((item) => [item.path, item.id] as const),
);

export function routeFromPathname(pathname: string): WorkspaceRoute {
  const normalized = pathname !== "/" ? pathname.replace(/\/+$/, "") : pathname;
  return ROUTE_BY_PATH.get(normalized) ?? "home";
}

export interface OutcomeRate {
  percentage: number | null;
  completed: number;
  failed: number;
  sampleSize: number;
}

/**
 * Calcule uniquement le résultat des tâches finalisées. Aucun échantillon ne
 * doit être présenté comme un succès implicite.
 */
export function taskOutcomeRate(tasks: readonly TaskSummary[]): OutcomeRate {
  const completed = tasks.filter((task) => task.status === "done").length;
  const failed = tasks.filter((task) => task.status === "failed").length;
  const sampleSize = completed + failed;
  return {
    percentage: sampleSize === 0 ? null : Math.round((completed / sampleSize) * 1000) / 10,
    completed,
    failed,
    sampleSize,
  };
}

export function isActiveTask(task: TaskSummary): boolean {
  return ["queued", "planning", "in_progress", "review", "blocked"].includes(task.status);
}

const STATUS_LABELS: Record<string, string> = {
  backlog: "À préparer",
  queued: "En file",
  planning: "Préparation",
  in_progress: "En cours",
  review: "En revue",
  blocked: "Bloquée",
  done: "Terminée",
  failed: "Échec",
};

export function taskStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
