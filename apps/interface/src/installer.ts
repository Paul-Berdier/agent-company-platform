// Enregistrement d'un greffon auprès du tableau de bord : contrôle du SDK d'abord.
//
// register() doit être appelé SYNCHRONEMENT pendant l'exécution du script : le tableau de bord
// marque sinon le greffon « NO_REGISTER » (web/src/plugins/usePlugins.ts:115-152).
import type * as ReactTypes from "react";
import { creerRefus } from "./refus";
import { verifierSdk, type VerdictSdk } from "./sdk";

export interface Enregistrement {
  nom: string;
  page: ReactTypes.ComponentType;
  emplacements?: Array<[string, ReactTypes.ComponentType]>;
}

export function installer(enregistrement: Enregistrement): VerdictSdk | null {
  const registre = window.__HERMES_PLUGINS__;
  if (!registre || typeof registre.register !== "function") return null;
  const verdict = verifierSdk(window.__HERMES_PLUGIN_SDK__);
  if (!verdict.ok) {
    console.warn(`[acp] ${enregistrement.nom} désactivé : SDK du tableau de bord incompatible (trouvé ${verdict.trouve}).`);
    if (window.__HERMES_PLUGIN_SDK__?.React) {
      const refus = creerRefus(verdict.trouve) as ReactTypes.ComponentType;
      registre.register(enregistrement.nom, refus);
      if (typeof registre.registerSlot === "function") registre.registerSlot(enregistrement.nom, "header-banner", refus);
    }
    return verdict;
  }
  registre.register(enregistrement.nom, enregistrement.page);
  for (const [emplacement, composant] of enregistrement.emplacements ?? []) {
    registre.registerSlot(enregistrement.nom, emplacement, composant);
  }
  return verdict;
}
