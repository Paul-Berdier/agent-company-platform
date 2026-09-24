import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationTurn } from "../src/conversation-api";
import { renderConversationTurnProgress } from "../src/conversation-turn-ui";

class Element {
  textContent = "";
  disabled = false;
  children: Element[] = [];
  listeners: Record<string, () => void> = {};
  constructor(readonly tagName: string) {}
  append(...nodes: Element[]): void { this.children.push(...nodes); }
  addEventListener(name: string, handler: () => void): void { this.listeners[name] = handler; }
}

const turn: ConversationTurn = {
  id: "turn-1", client_request_id: "request-1", status: "waiting_for_approval",
  user_content: "Analyse", assistant_content: "Réponse partielle", provider_run_id: "provider-1",
  error: null, created_at: "2026-09-23T12:00:00Z", updated_at: "2026-09-23T12:00:01Z",
};

afterEach(() => vi.unstubAllGlobals());

function render(status: ConversationTurn["status"], onStop = vi.fn(), busy = false) {
  vi.stubGlobal("document", { createElement: (tag: string) => new Element(tag) });
  return renderConversationTurnProgress({ ...turn, status }, onStop, busy) as unknown as Element | null;
}

describe("états actifs d’un tour de conversation", () => {
  it("explique l’approbation externe et permet seulement de demander l’arrêt", () => {
    const onStop = vi.fn();
    const progress = render("waiting_for_approval", onStop)!;
    expect(progress.children[0].textContent).toContain("La décision n’est pas disponible dans cette interface");
    const stop = progress.children[1];
    expect(stop.textContent).toBe("Arrêter le tour");
    expect(stop.disabled).toBe(false);
    stop.listeners.click();
    stop.listeners.click();
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(stop.disabled).toBe(true);
  });

  it("attend le serveur pendant stopping, sans bouton d’arrêt réactivé", () => {
    const progress = render("stopping")!;
    expect(progress.children[0].textContent).toContain("En attente de confirmation par Hermes");
    expect(progress.children[1].disabled).toBe(true);
  });

  it.each(["completed", "failed", "interrupted"] as const)("ne propose plus d’arrêt après %s", (status) => {
    expect(render(status)).toBeNull();
  });

  it("garde le bouton désactivé pendant la requête même si un rendu survient", () => {
    expect(render("running", vi.fn(), true)!.children[1].disabled).toBe(true);
  });
});
