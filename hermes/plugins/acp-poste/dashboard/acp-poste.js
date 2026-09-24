// Greffon acp-poste, côté navigateur : aucune page propre (onglet caché).
// Le tableau de bord charge le script de chaque greffon activé et attend qu'il
// s'enregistre (web/src/plugins/usePlugins.ts:115-152) ; ce composant ne fait que
// l'expliquer si l'on ouvre /acp-poste à la main. L'interface ACP arrive avec le
// greffon acp-interface (P3).
(function () {
  "use strict";
  var sdk = window.__HERMES_PLUGIN_SDK__;
  var registre = window.__HERMES_PLUGINS__;
  if (!sdk || !sdk.React || !registre || typeof registre.register !== "function") {
    return;
  }
  var h = sdk.React.createElement;
  registre.register("acp-poste", function PageAcpPoste() {
    return h(
      "p",
      { style: { padding: "1rem" } },
      "Le greffon acp-poste n'a pas de page : il sert l'API /api/plugins/acp-poste/v1/ au poste Windows et au client desktop."
    );
  });
})();
