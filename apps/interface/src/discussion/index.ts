// Point d'entrée du greffon acp-discussion (bundle IIFE : hermes/plugins/acp-discussion/dashboard/dist/index.js) :
// un onglet « Discussion » (/discussion), la discussion réduite sur le JSON-RPC natif du tableau de bord (cahier P7
// § 9, décision P7-8).
import type * as ReactTypes from "react";
import { installer } from "../installer";
import { Discussion } from "./Discussion";

installer({ nom: "acp-discussion", page: Discussion as ReactTypes.ComponentType });
