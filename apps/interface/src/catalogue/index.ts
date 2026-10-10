// Point d'entrée du greffon acp-catalogue (bundle IIFE : hermes/plugins/acp-catalogue/dashboard/dist/index.js).
import type * as ReactTypes from "react";
import { installer } from "../installer";
import { Catalogue } from "./Catalogue";

installer({ nom: "acp-catalogue", page: Catalogue as ReactTypes.ComponentType });
