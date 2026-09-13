#!/usr/bin/env node
/**
 * Lance la Vitest déjà installée dans le dépôt, sans ajouter de dépendance.
 *
 * Ce paquet est volontairement sans dépendance : il n'apporte ni `@playwright/test`
 * ni `vitest`. Vitest est déjà présent dans `apps/web` et `packages/pixel-office-engine`
 * mais n'est pas remonté à la racine, donc `vitest run` seul ne résout rien depuis ce
 * workspace. Ce lanceur cherche l'installation existante la plus proche et la démarre
 * avec le répertoire du paquet comme racine. Aucun accès réseau, aucune installation.
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const toolsDir = dirname(fileURLToPath(import.meta.url));
const packageDir = resolve(toolsDir, "..");
const repoRoot = resolve(packageDir, "..", "..");

const candidates = [
  join(packageDir, "node_modules", "vitest", "vitest.mjs"),
  join(repoRoot, "node_modules", "vitest", "vitest.mjs"),
  join(repoRoot, "apps", "web", "node_modules", "vitest", "vitest.mjs"),
  join(repoRoot, "packages", "pixel-office-engine", "node_modules", "vitest", "vitest.mjs"),
];

const binary = candidates.find((candidate) => existsSync(candidate));

if (!binary) {
  process.stderr.write(
    "[@acp/playwright-reporter] Vitest est introuvable dans le dépôt. " +
      "Installez les dépendances Node du dépôt (npm install) puis relancez.\n",
  );
  process.exit(1);
}

const result = spawnSync(process.execPath, [binary, ...process.argv.slice(2)], {
  cwd: packageDir,
  stdio: "inherit",
});

process.exit(result.status === null ? 1 : result.status);
