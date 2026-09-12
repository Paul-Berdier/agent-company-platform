/**
 * Bibliothèque de skills (route « Bibliothèque »).
 *
 * Fondation du Lot D : ce rendu affiche un état « non configuré » honnête.
 * L’agent E le remplace par les vrais écrans (recherche, import, liste, détail,
 * révisions, bindings) branchés sur `skills-api.ts`. Aucune donnée n’est simulée ici.
 */

import { el, sectionHeader, statePanel, statusChip } from "./ui-primitives";

const PENDING_TITLE = "Module en cours de raccordement dans cette révision";

export function renderSkillsLibrary(container: HTMLElement): void {
  const intro = el("section", "page-intro");
  intro.append(
    statusChip("Non configuré", "unconfigured"),
    el("h2", "page-title", "Bibliothèque"),
    el(
      "p",
      "page-description",
      "Skills installés, catalogue de sources et rattachements par projet, gérés par l’API.",
    ),
  );
  const section = el("section", "content-section");
  section.dataset.module = "skills-library";
  section.append(
    sectionHeader("Skills", "Format SKILL.md avec frontmatter ; contenu importé traité comme donnée non fiable."),
    statePanel(
      "unconfigured",
      PENDING_TITLE,
      "Aucun skill n’est listé ni simulé : l’écran sera raccordé à l’API /skills dans une prochaine révision.",
    ),
  );
  container.append(intro, section);
}
