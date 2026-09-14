/**
 * Aperçu GLB isolé et chargé à la demande.
 *
 * Le composant produit par un worker reste une donnée non fiable. Le serveur n'autorise
 * l'aperçu que pour un GLB v2 auto-contenu et cette couche ne fournit que son URL signée
 * à `<model-viewer>`. Aucun mode AR, aucune rotation automatique et aucune URL annexe ne
 * sont activés. La dépendance n'entre dans le navigateur qu'au premier aperçu 3D.
 */

import "./model-preview.css";

export const GLB_CONTENT_TYPE = "model/gltf-binary";
export const MODEL_VIEWER_TAG = "model-viewer";

type ModelViewerLoader = () => Promise<unknown>;
type Registry = Pick<CustomElementRegistry, "get">;

let defaultLoad: Promise<void> | null = null;

function browserRegistry(): Registry | null {
  return typeof customElements === "undefined" ? null : customElements;
}

function prefersReducedMotion(): boolean {
  const matchMedia = (globalThis as {
    matchMedia?: (query: string) => { matches?: unknown };
  }).matchMedia;
  if (typeof matchMedia !== "function") return false;
  try {
    return matchMedia.call(globalThis, "(prefers-reduced-motion: reduce)").matches === true;
  } catch {
    return false;
  }
}

function importModelViewer(): Promise<unknown> {
  return import("@google/model-viewer");
}

/** Charge et vérifie l'enregistrement du custom element, une seule fois par page. */
function ensureModelViewer(registry: Registry, loader: ModelViewerLoader): Promise<void> {
  if (registry.get(MODEL_VIEWER_TAG)) return Promise.resolve();
  return loader().then(() => {
    if (!registry.get(MODEL_VIEWER_TAG)) {
      throw new Error("Le composant model-viewer ne s'est pas enregistré.");
    }
  });
}

function defaultEnsureModelViewer(registry: Registry): Promise<void> {
  if (!defaultLoad) {
    defaultLoad = ensureModelViewer(registry, importModelViewer).catch((error: unknown) => {
      defaultLoad = null;
      throw error;
    });
  }
  return defaultLoad;
}

export interface ModelPreviewOptions {
  /** Points d'injection réservés aux tests ; le produit utilise le registre du navigateur. */
  registry?: Registry | null;
  loader?: ModelViewerLoader;
}

function setState(status: HTMLElement, state: "loading" | "ready" | "error", message: string): void {
  status.dataset.state = state;
  status.textContent = message;
}

/**
 * Construit l'aperçu interactif d'un GLB déjà validé côté serveur.
 *
 * L'URL doit avoir été validée par le client d'artefacts avant cet appel. Elle est posée
 * avec `setAttribute`, jamais interpolée dans du HTML. L'absence de Web Components ou un
 * échec de chargement reste visible et laisse le téléchargement disponible à côté.
 */
export function modelPreviewNode(
  sourceUrl: string,
  label: string,
  options: ModelPreviewOptions = {},
): HTMLElement {
  const frame = document.createElement("figure");
  frame.className = "model-preview";

  const viewer = document.createElement(MODEL_VIEWER_TAG);
  viewer.className = "model-preview-viewer";
  viewer.setAttribute("src", sourceUrl);
  viewer.setAttribute("alt", label);
  viewer.setAttribute("camera-controls", "");
  viewer.setAttribute("interaction-prompt", prefersReducedMotion() ? "none" : "auto");
  viewer.setAttribute("loading", "lazy");
  viewer.setAttribute("reveal", "auto");
  viewer.setAttribute("crossorigin", "anonymous");
  viewer.setAttribute("environment-image", "neutral");
  viewer.setAttribute("shadow-intensity", "1");

  const caption = document.createElement("figcaption");
  caption.className = "model-preview-caption";
  caption.setAttribute("aria-live", "polite");
  setState(caption, "loading", "Chargement de l'aperçu 3D…");

  viewer.addEventListener("load", () => {
    setState(
      caption,
      "ready",
      "Modèle 3D chargé. Utilise la souris, le tactile ou le clavier pour tourner et zoomer.",
    );
  });
  viewer.addEventListener("error", () => {
    setState(
      caption,
      "error",
      "L'aperçu 3D n'a pas pu être chargé. Le téléchargement du fichier reste disponible.",
    );
  });

  frame.append(viewer, caption);

  const registry = options.registry === undefined ? browserRegistry() : options.registry;
  if (!registry) {
    setState(
      caption,
      "error",
      "Aperçu 3D indisponible dans cet environnement. Le téléchargement reste disponible.",
    );
    return frame;
  }

  const load = options.loader
    ? ensureModelViewer(registry, options.loader)
    : defaultEnsureModelViewer(registry);
  void load.catch(() => {
    setState(
      caption,
      "error",
      "Le visualiseur 3D n'a pas pu être chargé. Le téléchargement reste disponible.",
    );
  });
  return frame;
}
