import { afterEach, describe, expect, it, vi } from "vitest";

import { MODEL_VIEWER_TAG, modelPreviewNode } from "../src/model-preview";

type Handler = () => void;

class FakeElement {
  className = "";
  textContent = "";
  readonly children: FakeElement[] = [];
  readonly attributes: Record<string, string> = {};
  readonly dataset: Record<string, string> = {};
  readonly listeners: Record<string, Handler[]> = {};

  constructor(readonly tagName: string) {}

  append(...nodes: FakeElement[]): void {
    this.children.push(...nodes);
  }

  setAttribute(name: string, value: string): void {
    this.attributes[name] = value;
  }

  addEventListener(name: string, handler: Handler): void {
    (this.listeners[name] ??= []).push(handler);
  }

  emit(name: string): void {
    for (const handler of this.listeners[name] ?? []) handler();
  }
}

function installDocument(): void {
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { createElement: (tagName: string) => new FakeElement(tagName) },
  });
}

function installMotionPreference(matches: boolean): void {
  Object.defineProperty(globalThis, "matchMedia", {
    configurable: true,
    value: vi.fn(() => ({ matches })),
  });
}

function nodes(frame: HTMLElement): { viewer: FakeElement; caption: FakeElement } {
  const children = (frame as unknown as FakeElement).children;
  return { viewer: children[0], caption: children[1] };
}

describe("modelPreviewNode", () => {
  afterEach(() => {
    Reflect.deleteProperty(globalThis, "matchMedia");
  });

  it("configure un visualiseur sans AR, autoplay ni HTML injecté", async () => {
    installDocument();
    installMotionPreference(false);
    let registered = false;
    const loader = vi.fn(async () => { registered = true; });
    const registry = { get: (name: string) => name === MODEL_VIEWER_TAG && registered ? class {} : undefined };

    const frame = modelPreviewNode(
      "https://preview.example.test/model.glb?token=secret",
      "Modèle <hostile>",
      { registry: registry as never, loader },
    );
    const { viewer, caption } = nodes(frame);
    await Promise.resolve();
    await Promise.resolve();

    expect(viewer.tagName).toBe("model-viewer");
    expect(viewer.attributes.src).toContain("token=secret");
    expect(viewer.attributes.alt).toBe("Modèle <hostile>");
    expect(viewer.attributes["camera-controls"]).toBe("");
    expect(viewer.attributes["interaction-prompt"]).toBe("auto");
    expect(viewer.attributes.crossorigin).toBe("anonymous");
    expect(viewer.attributes.ar).toBeUndefined();
    expect(viewer.attributes.autoplay).toBeUndefined();
    expect(loader).toHaveBeenCalledOnce();
    expect(caption.dataset.state).toBe("loading");

    viewer.emit("load");
    expect(caption.dataset.state).toBe("ready");
    expect(caption.textContent).toContain("clavier");
  });

  it("rend l'échec du module et celui du modèle sans masquer le téléchargement", async () => {
    installDocument();
    const frame = modelPreviewNode("https://preview.test/model.glb", "Modèle", {
      registry: { get: () => undefined } as never,
      loader: async () => { throw new Error("module absent"); },
    });
    const { viewer, caption } = nodes(frame);
    await Promise.resolve();
    await Promise.resolve();

    expect(caption.dataset.state).toBe("error");
    expect(caption.textContent).toContain("téléchargement reste disponible");

    viewer.emit("error");
    expect(caption.dataset.state).toBe("error");
    expect(caption.textContent).toContain("aperçu 3D");
  });

  it("désactive le prompt animé lorsque les mouvements réduits sont demandés", () => {
    installDocument();
    installMotionPreference(true);

    const frame = modelPreviewNode("https://preview.test/model.glb", "Modèle", {
      registry: { get: () => class {} } as never,
    });

    expect(nodes(frame).viewer.attributes["interaction-prompt"]).toBe("none");
  });
});
