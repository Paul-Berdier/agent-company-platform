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

/** Une requête vue par le fetchJSON factice : méthode, corps JSON décodé, en-têtes posés par l'appelant. */
export interface Requete {
  url: string;
  methode: string;
  corps: unknown;
  entetes: Record<string, string>;
}

export interface Installation {
  appels: string[];
  requetes: Requete[];
  langue: { valeur: string; changements: string[] };
}

function entetesDe(init: RequestInit | undefined): Record<string, string> {
  const brut = init?.headers;
  if (!brut) return {};
  if (brut instanceof Headers) return Object.fromEntries([...brut.entries()]);
  if (Array.isArray(brut)) return Object.fromEntries(brut);
  return { ...(brut as Record<string, string>) };
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

/** SDK factice. Une réponse est cherchée sous « <MÉTHODE> <url> » pour une écriture, sous « <url> »
 *  pour une lecture ; la table peut être modifiée par le test entre deux requêtes (état du serveur). */
export function installerSdk(reponses: Record<string, Reponse> = {}, options: { version?: unknown; langue?: string } = {}):
  Installation {
  const installation: Installation = {
    appels: [],
    requetes: [],
    langue: { valeur: options.langue ?? "en", changements: [] },
  };
  const sdk: SdkHermes = {
    sdkVersion: "version" in options ? options.version : "1.1.0",
    React,
    fetchJSON: (async (url: string, init?: RequestInit) => {
      const methode = (init?.method ?? "GET").toUpperCase();
      installation.appels.push(url);
      installation.requetes.push({
        url,
        methode,
        corps: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
        entetes: entetesDe(init),
      });
      const cle = methode === "GET" ? url : `${methode} ${url}`;
      if (!(cle in reponses)) {
        throw new ApiErrorHermes("The server could not find what the dashboard asked for.", 404,
                                 '{"detail":"Not Found"}', url);
      }
      const r = reponses[cle];
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

/** Racines encore montées : démontées après chaque test (tests/preparation.ts), même quand un test
 *  échoue avant son propre démontage (sinon ses minuteries de sondage courent dans le test suivant). */
export const racinesMontees = new Set<Root>();

export async function rendre(element: React.ReactElement): Promise<Rendu> {
  const racine = document.createElement("div");
  document.body.appendChild(racine);
  let root: Root | null = null;
  await act(async () => {
    root = createRoot(racine);
    racinesMontees.add(root);
    root.render(element);
  });
  // Laisser les promesses de chargement se résoudre.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  return {
    racine,
    demonter: () =>
      act(() => {
        if (root) racinesMontees.delete(root);
        root?.unmount();
      }),
    texte: () => (racine.textContent ?? "").replace(/\s+/g, " ").trim(),
  };
}

/** Laisse s'enchaîner les lectures (une lecture qui en déclenche une autre, un envoi puis sa relecture). */
export async function attendre(tours = 4): Promise<void> {
  for (let i = 0; i < tours; i += 1) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
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
