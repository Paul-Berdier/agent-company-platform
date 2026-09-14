import { defineConfig } from "@playwright/test";

import { readE2EConfiguration } from "./lib/runtime-config.mjs";

const runtime = readE2EConfiguration(process.env);

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.e2e.spec.mjs",
  outputDir: "./.artifacts/test-results",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  // This proof logs into a real account. A failure must stay visible and must not
  // replay even the authentication mutation automatically.
  retries: 0,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["line"]],
  use: {
    baseURL: runtime.enabled ? runtime.baseURL : "http://127.0.0.1/",
    browserName: "chromium",
    headless: true,
    ignoreHTTPSErrors: false,
    serviceWorkers: "block",
    screenshot: "only-on-failure",
    trace: "off",
    video: "off",
  },
});
