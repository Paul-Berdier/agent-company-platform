import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { describe, test } from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const unitDirectory = dirname(fileURLToPath(import.meta.url));
const runner = resolve(unitDirectory, "..", "run.mjs");

function invoke(environment) {
  return spawnSync(process.execPath, [runner], {
    env: {
      PATH: process.env.PATH,
      SystemRoot: process.env.SystemRoot,
      ...environment,
    },
    encoding: "utf8",
  });
}

describe("lanceur E2E", () => {
  test("sort explicitement en skipped sans charger Playwright", () => {
    const result = invoke({});
    assert.equal(result.status, 0);
    assert.match(result.stdout, /E2E SKIPPED/);
    assert.equal(result.stderr, "");
  });

  test("refuse un faux opt-in avant de chercher Playwright", () => {
    const result = invoke({ ACP_E2E: "true" });
    assert.equal(result.status, 2);
    assert.match(result.stderr, /E2E CONFIG ERROR/);
    assert.doesNotMatch(result.stderr, /Playwright n'est pas installé/);
  });

  test("refuse une configuration incomplète avant de chercher Playwright", () => {
    const result = invoke({ ACP_E2E: "1" });
    assert.equal(result.status, 2);
    assert.match(result.stderr, /ACP_E2E_BASE_URL est requis/);
    assert.doesNotMatch(result.stderr, /Playwright n'est pas installé/);
  });
});
