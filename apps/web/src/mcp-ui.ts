/**
 * Centre MCP et coffre de secrets (route « Connexions »).
 *
 * Fondation du Lot D : ces rendus affichent un état « non configuré » honnête.
 * L’agent D les remplace par les vrais écrans (liste, formulaire, catalogue,
 * détail, probes, export/import) branchés sur `mcp-api.ts` et `secrets-api.ts`.
 * Aucune donnée n’est simulée ici.
 */

import { el, sectionHeader, statePanel, statusChip } from "./ui-primitives";

const PENDING_TITLE = "Module en cours de raccordement dans cette révision";

export function renderMcpCenter(container: HTMLElement): void {
  const section = el("section", "content-section");
  section.dataset.module = "mcp-center";
  const header = sectionHeader(
    "Centre MCP",
    "Serveurs MCP déclarés, outils découverts, autorisations de probe et rattachements par projet.",
  );
  header.append(statusChip("Non configuré", "unconfigured"));
  section.append(
    header,
    statePanel(
      "unconfigured",
      PENDING_TITLE,
      "Aucun serveur MCP n’est listé ni simulé : l’écran sera raccordé à l’API /mcp dans une prochaine révision.",
    ),
  );
  container.append(section);
}

export function renderSecretsPanel(container: HTMLElement): void {
  const section = el("section", "content-section");
  section.dataset.module = "secrets-panel";
  const header = sectionHeader(
    "Coffre de secrets",
    "Références chiffrées au repos, utilisées par les serveurs MCP ; aucune valeur n’est jamais affichée.",
  );
  header.append(statusChip("Non configuré", "unconfigured"));
  section.append(
    header,
    statePanel(
      "unconfigured",
      PENDING_TITLE,
      "L’état du coffre et la gestion des secrets seront raccordés à l’API /secrets dans une prochaine révision.",
    ),
  );
  container.append(section);
}
