// Point d'entrée du greffon acp-projets (bundle IIFE : hermes/plugins/acp-projets/dashboard/dist/index.js).
import type * as ReactTypes from "react";
import { installer } from "../installer";
import { Projets } from "./Projets";

installer({ nom: "acp-projets", page: Projets as ReactTypes.ComponentType });
