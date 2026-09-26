// Point d'entrée du greffon acp-interface (bundle IIFE : hermes/plugins/acp-interface/dashboard/dist/index.js).
import type * as ReactTypes from "react";
import { installer } from "../installer";
import { Accueil } from "./Accueil";
import { Alertes } from "./Alertes";
import { Marque } from "./Marque";
import { VerrouFrancais } from "./VerrouFrancais";

type C = ReactTypes.ComponentType;

installer({
  nom: "acp-interface",
  page: Accueil as C,
  emplacements: [
    ["header-left", Marque as C],
    ["header-banner", Alertes as C],
    ["overlay", VerrouFrancais as C],
  ],
});
