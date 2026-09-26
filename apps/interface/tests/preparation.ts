// Environnement de rendu de React sous Vitest : act() attendu, aucun SDK installé par défaut.
import { afterEach } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  delete window.__HERMES_PLUGIN_SDK__;
  delete window.__HERMES_PLUGINS__;
  delete window.__HERMES_BASE_PATH__;
  document.body.innerHTML = "";
});
