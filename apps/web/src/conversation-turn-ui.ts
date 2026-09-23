import { isTerminalConversationTurn, type ConversationTurn } from "./conversation-api";
import { el } from "./ui-primitives";

/** Présente les états actifs sans inventer une approbation ou une fin distante. */
export function renderConversationTurnProgress(
  turn: ConversationTurn,
  onStop: () => void,
  stopPending = false,
): HTMLElement | null {
  if (isTerminalConversationTurn(turn.status)) return null;
  const progress = el("div", "conversation-pending");
  const messages = {
    submitting: "Le message est accepté par la plateforme…",
    running: "Hermes traite ce tour…",
    waiting_for_approval: "Hermes attend une approbation. La décision n’est pas disponible dans cette interface ; vous pouvez arrêter ce tour.",
    stopping: "Arrêt demandé. En attente de confirmation par Hermes…",
  };
  progress.append(el("p", "", messages[turn.status as keyof typeof messages]));
  const stop = el("button", "button button-secondary", "Arrêter le tour");
  stop.type = "button";
  stop.disabled = stopPending || turn.status === "stopping";
  stop.addEventListener("click", () => {
    if (stop.disabled) return;
    stop.disabled = true;
    onStop();
  });
  progress.append(stop);
  return progress;
}
