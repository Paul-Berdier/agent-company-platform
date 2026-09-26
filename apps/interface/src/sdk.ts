// Accès typé MINIMAL au SDK des greffons du tableau de bord de Hermes 0.21.5
// (web/src/plugins/registry.ts, exposePluginSDK ; contrat « SPIKE » de plugins/sdk.d.ts).
//
// Seules les parties employées par ACP sont typées. Le SDK est lu à l'appel, jamais au chargement
// du module : les tests installent un SDK factice avant de rendre un composant.
import type * as ReactTypes from "react";

export interface I18nHermes {
  locale?: string;
  setLocale?: (locale: string) => void;
}

export interface SdkHermes {
  sdkVersion?: unknown;
  React?: typeof ReactTypes;
  fetchJSON?: <T = unknown>(url: string, init?: RequestInit) => Promise<T>;
  api?: Record<string, unknown>;
  useI18n?: () => unknown;
}

// Signature RÉELLE de registerSlot : (greffon, emplacement, composant)
// (web/src/plugins/slots.ts:125-129) ; sdk.d.ts de Hermes l'annonce à tort (emplacement, nom).
export interface RegistreHermes {
  register(nom: string, composant: ReactTypes.ComponentType): void;
  registerSlot(greffon: string, emplacement: string, composant: ReactTypes.ComponentType): void;
}

declare global {
  interface Window {
    __HERMES_PLUGIN_SDK__?: SdkHermes;
    __HERMES_PLUGINS__?: RegistreHermes;
    __HERMES_BASE_PATH__?: string;
  }
}

/** Majeure du contrat du SDK que ces greffons savent employer (sdkVersion « 1.1.0 » en 0.21.5). */
export const MAJEURE_ATTENDUE = 1;
export const SDK_ATTENDU = `${MAJEURE_ATTENDUE}.x`;

export type VerdictSdk = { ok: true; version: string } | { ok: false; trouve: string };

/** Accepte seulement un SDK dont la version est une chaîne « 1.x.y » ET qui expose ce que les
 *  greffons emploient (React, fetchJSON). Tout le reste est refusé : on ne devine jamais. */
export function verifierSdk(sdk: unknown): VerdictSdk {
  if (!sdk || typeof sdk !== "object") return { ok: false, trouve: "absent" };
  const brut = (sdk as SdkHermes).sdkVersion;
  if (typeof brut !== "string" || !/^\d+\.\d+\.\d+$/.test(brut)) {
    return { ok: false, trouve: typeof brut === "string" ? brut.slice(0, 40) : "absent" };
  }
  if (Number(brut.split(".")[0]) !== MAJEURE_ATTENDUE) return { ok: false, trouve: brut };
  const s = sdk as SdkHermes;
  if (!s.React || typeof s.React.createElement !== "function" || typeof s.fetchJSON !== "function") {
    return { ok: false, trouve: `${brut} incomplet` };
  }
  return { ok: true, version: brut };
}

/** SDK courant, ou une erreur explicite (jamais un objet inventé). */
export function sdk(): SdkHermes {
  const valeur = window.__HERMES_PLUGIN_SDK__;
  if (!valeur) throw new Error("SDK du tableau de bord absent");
  return valeur;
}

/** Préfixe de base du tableau de bord (web/src/lib/api.ts:12-26), sans barre finale. */
export function cheminDeBase(): string {
  const brut = window.__HERMES_BASE_PATH__ ?? "";
  return typeof brut === "string" ? brut.replace(/\/+$/, "") : "";
}
