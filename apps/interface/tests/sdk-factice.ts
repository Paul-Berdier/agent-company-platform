// SDK factice du tableau de bord : le VRAI React (celui que Hermes 0.21.5 embarque, 19.2.7),
// un fetchJSON qui répond selon une table et imite les erreurs de Hermes (« <statut>: <corps> »),
// un contexte de langue qui se comporte comme web/src/i18n/context.tsx.
import * as React from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { SdkHermes } from "../src/sdk";

export type Reponse = unknown | Error;

/** Même forme que l'ApiError de Hermes 0.21.5 (web/src/lib/api-error.ts) : statut, corps brut,
 *  message anglais ; statut 0 quand la requête n'a jamais atteint le serveur. */
export class ApiErrorHermes extends Error {
  readonly status: number;
  readonly body: string;
  readonly url: string;

  constructor(message: string, status: number, body: string, url = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.url = url;
  }
}

export interface Installation {
  appels: string[];
  langue: { valeur: string; changements: string[] };
}

const ContexteLangue = React.createContext<{ locale: string; setLocale: (l: string) => void } | null>(null);

export function FournisseurLangue(props: { installation: Installation; children?: React.ReactNode }) {
  const [locale, fixer] = React.useState(props.installation.langue.valeur);
  const setLocale = React.useCallback(
    (l: string) => {
      props.installation.langue.changements.push(l);
      props.installation.langue.valeur = l;
      fixer(l);
    },
    [props.installation],
  );
  return React.createElement(ContexteLangue.Provider, { value: { locale, setLocale } }, props.children);
}

export function installerSdk(reponses: Record<string, Reponse> = {}, options: { version?: unknown; langue?: string } = {}):
  Installation {
  const installation: Installation = { appels: [], langue: { valeur: options.langue ?? "en", changements: [] } };
  const sdk: SdkHermes = {
    sdkVersion: "version" in options ? options.version : "1.1.0",
    React,
    fetchJSON: (async (url: string) => {
      installation.appels.push(url);
      if (!(url in reponses)) {
        throw new ApiErrorHermes("The server could not find what the dashboard asked for.", 404,
                                 '{"detail":"Not Found"}', url);
      }
      const r = reponses[url];
      if (r instanceof Error) throw r;
      return JSON.parse(JSON.stringify(r));
    }) as SdkHermes["fetchJSON"],
    useI18n: () => React.useContext(ContexteLangue),
  };
  window.__HERMES_PLUGIN_SDK__ = sdk;
  return installation;
}

export interface Rendu {
  racine: HTMLElement;
  demonter: () => void;
  texte: () => string;
}

export async function rendre(element: React.ReactElement): Promise<Rendu> {
  const racine = document.createElement("div");
  document.body.appendChild(racine);
  let root: Root | null = null;
  await act(async () => {
    root = createRoot(racine);
    root.render(element);
  });
  // Laisser les promesses de chargement se résoudre.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  return {
    racine,
    demonter: () => act(() => root?.unmount()),
    texte: () => (racine.textContent ?? "").replace(/\s+/g, " ").trim(),
  };
}

/** Nœuds de texte non vides qui ne sont ni dans le catalogue ni sous un élément data-acp-donnee. */
export function textesHorsCatalogue(racine: HTMLElement, catalogue: Set<string>): string[] {
  const hors: string[] = [];
  const parcours = document.createTreeWalker(racine, NodeFilter.SHOW_TEXT);
  let noeud = parcours.nextNode();
  while (noeud) {
    const texte = (noeud.textContent ?? "").trim();
    const parent = noeud.parentElement;
    if (texte && !catalogue.has(texte) && !parent?.closest("[data-acp-donnee]")) hors.push(texte);
    noeud = parcours.nextNode();
  }
  return hors;
}
