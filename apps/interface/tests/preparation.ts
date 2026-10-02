// Environnement de rendu de React sous Vitest : act() attendu, aucun SDK installé par défaut.
import { act } from "react";
import { afterEach } from "vitest";
import { racinesMontees } from "./sdk-factice";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  for (const root of racinesMontees) act(() => root.unmount());
  racinesMontees.clear();
  // Étape P7 : le flux partagé de l'onglet (window.__ACP_FLUX__) est fermé et oublié entre deux tests.
  for (const flux of Object.values(window.__ACP_FLUX__ ?? {})) flux?.detruire();
  delete window.__ACP_FLUX__;
  delete window.__HERMES_PLUGIN_SDK__;
  delete window.__HERMES_PLUGINS__;
  delete window.__HERMES_BASE_PATH__;
  document.body.innerHTML = "";
});
