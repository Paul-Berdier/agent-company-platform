/** Petites briques UI partagées (agnostiques du métier). */

/**
 * Active les cadres pixel art Modern UI si les assets sous licence sont
 * installés (sinon, l'interface garde son style plat par défaut).
 */
export async function enablePixelUi(
  slicesBase = "/assets/licensed/limezu/ui/slices",
): Promise<boolean> {
  try {
    const resp = await fetch(`${slicesBase}/panel-round.png`, { method: "HEAD" });
    if (resp.ok) {
      document.body.classList.add("ui-pixel");
      return true;
    }
  } catch {
    /* assets absents : style plat */
  }
  return false;
}

export const STATUS_COLORS: Record<string, string> = {
  idle: "#8d99ae",
  thinking: "#e9c46a",
  working: "#2a9d8f",
  reviewing: "#457b9d",
  blocked: "#e63946",
  offline: "#4a4e57",
  backlog: "#8d99ae",
  queued: "#e9c46a",
  planning: "#f4a261",
  in_progress: "#2a9d8f",
  review: "#457b9d",
  done: "#57cc99",
  failed: "#e63946",
};

export function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "#8d99ae";
}

export function badge(text: string, color: string): HTMLSpanElement {
  const span = document.createElement("span");
  span.className = "acp-badge";
  span.textContent = text;
  span.style.background = color;
  return span;
}

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className = "",
  text = "",
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}
