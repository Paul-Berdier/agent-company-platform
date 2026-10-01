// Point d'entrée du greffon acp-poste-vues (bundle IIFE : hermes/plugins/acp-poste-vues/dashboard/dist/index.js) :
// un onglet « Poste » à trois vues (état, routage, quotas ; décision D62).
import type * as ReactTypes from "react";
import { installer } from "../installer";
import { Poste } from "./Poste";

installer({ nom: "acp-poste-vues", page: Poste as ReactTypes.ComponentType });
