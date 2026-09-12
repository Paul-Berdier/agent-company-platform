/**
 * Primitives d’interface partagées par le shell (`workspace.ts`) et les modules
 * du Lot D (`mcp-ui.ts`, `skills-ui.ts`).
 *
 * Extraites de `workspace.ts` sans changement de comportement. Les fonctions qui
 * touchent au DOM (`el`, `statePanel`, `sectionHeader`, `statusChip`, `labeledField`)
 * ne sont appelées qu’en environnement navigateur ; `formatDateTime`,
 * `normalizeApiError` et `errorMessage` sont pures et testées sous Node.
 */

import { WorkspaceApiError } from "./workspace-api";

export type StatePanelTone = "loading" | "empty" | "offline" | "forbidden" | "error" | "unconfigured";

let fieldSequence = 0;

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

/**
 * Panneau d’état accessible. `onRetry` remplace l’ancien booléen `retry` :
 * le bouton « Réessayer » n’apparaît que si un gestionnaire est fourni.
 */
export function statePanel(
  tone: StatePanelTone,
  title: string,
  message: string,
  onRetry?: () => void,
): HTMLElement {
  const panel = el("section", `state-panel state-${tone}`);
  panel.setAttribute("aria-live", tone === "loading" ? "polite" : "assertive");
  panel.append(
    el("span", "state-icon", tone === "loading" ? "…" : tone === "empty" ? "○" : "!"),
    el("h2", "state-title", title),
    el("p", "state-message", message),
  );
  if (onRetry) {
    const button = el("button", "button button-secondary", "Réessayer");
    button.type = "button";
    button.addEventListener("click", () => onRetry());
    panel.append(button);
  }
  return panel;
}

export function sectionHeader(title: string, description = ""): HTMLElement {
  const header = el("div", "section-header");
  const copy = el("div");
  copy.append(el("h2", "section-heading", title));
  if (description) copy.append(el("p", "section-description", description));
  header.append(copy);
  return header;
}

export function statusChip(label: string, tone: string): HTMLElement {
  const chip = el("span", "status-chip", label);
  chip.dataset.tone = tone;
  return chip;
}

export function labeledField(labelText: string, control: HTMLElement, hint = ""): HTMLElement {
  const field = el("div", "form-field");
  const id = `mission-field-${++fieldSequence}`;
  control.id = id;
  const label = el("label", "form-label", labelText);
  label.htmlFor = id;
  field.append(label, control);
  if (hint) field.append(el("p", "form-hint", hint));
  return field;
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date inconnue";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  }).format(date);
}

export function normalizeApiError(error: unknown, fallback: string): WorkspaceApiError {
  return error instanceof WorkspaceApiError
    ? error
    : new WorkspaceApiError(fallback, "invalid_response");
}

export function errorMessage(error: WorkspaceApiError): string {
  if (error.kind === "offline") {
    return "L’API métier ne répond pas. Les données de démonstration ne sont jamais utilisées ici.";
  }
  if (error.kind === "forbidden") {
    return error.status === 401
      ? "La session a expiré ou n’est plus valide. Reconnecte-toi pour continuer."
      : "Le compte courant n’a pas accès à cette ressource.";
  }
  return error.message;
}
