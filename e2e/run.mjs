#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { E2EConfigurationError, readE2EConfiguration } from "./lib/runtime-config.mjs";

let runtime;
try {
  runtime = readE2EConfiguration(process.env);
} catch (error) {
  const message = error instanceof E2EConfigurationError
    ? error.message
    : "La configuration E2E est invalide.";
  process.stderr.write(`[E2E CONFIG ERROR] ${message}\n`);
  process.exit(2);
}

if (!runtime.enabled) {
  process.stdout.write("[E2E SKIPPED] ACP_E2E n'est pas égal à 1 ; aucun navigateur n'a été chargé.\n");
  process.exit(0);
}

const require = createRequire(import.meta.url);
let playwrightEntry;
try {
  playwrightEntry = require.resolve("@playwright/test");
} catch {
  process.stderr.write(
    "[E2E DEPENDENCY ERROR] Playwright n'est pas installé dans le paquet E2E. "
      + "Exécutez `npm ci --prefix e2e` explicitement, puis relancez.\n",
  );
  process.exit(2);
}

const playwrightCli = join(dirname(playwrightEntry), "cli.js");
if (!existsSync(playwrightCli)) {
  process.stderr.write("[E2E DEPENDENCY ERROR] Le lanceur Playwright installé est introuvable.\n");
  process.exit(2);
}

const e2eDirectory = dirname(fileURLToPath(import.meta.url));
const result = spawnSync(
  process.execPath,
  [playwrightCli, "test", "--config", join(e2eDirectory, "playwright.config.mjs")],
  {
    cwd: e2eDirectory,
    env: process.env,
    stdio: "inherit",
  },
);

if (result.error) {
  process.stderr.write(`[E2E LAUNCH ERROR] ${result.error.message}\n`);
  process.exit(1);
}
process.exit(result.status === null ? 1 : result.status);
