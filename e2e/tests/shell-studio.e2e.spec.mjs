import { expect, test } from "@playwright/test";

import { installBrowserRuntimeGuard } from "../lib/browser-runtime-guard.mjs";
import {
  buildBrowserForwardOptions,
  createBrowserRequestGate,
  evaluateCredentialedCorsResponse,
  evaluateCredentialedLoginPreflight,
  evaluateBrowserTarget,
  isAllowedBrowserRequest,
  isRedirectStatus,
  NO_REDIRECT_OR_RETRY,
  safeBrowserTargetLabel,
} from "../lib/network-policy.mjs";
import { readE2EConfiguration } from "../lib/runtime-config.mjs";

const runtime = readE2EConfiguration(process.env);

test.skip(!runtime.enabled, "ACP_E2E=1 est requis pour lancer le navigateur réel.");

function assertRuntimeEnabled() {
  if (!runtime.enabled) throw new Error("Le test E2E a été exécuté sans opt-in.");
  return runtime;
}

async function installNetworkBoundary(context, page, apiRequest, configuration) {
  const allowedOrigins = new Set([configuration.appOrigin, configuration.apiOrigin]);
  const requestGate = createBrowserRequestGate(allowedOrigins, configuration.apiOrigin);
  const violations = new Set();
  let loginAttemptSettled = false;
  let settleLoginAttempt;
  const loginAttempt = new Promise((resolve) => {
    settleLoginAttempt = resolve;
  });
  const reportLoginAttempt = (result) => {
    if (loginAttemptSettled) return;
    loginAttemptSettled = true;
    settleLoginAttempt(Object.freeze(result));
  };
  const recordViolation = (rawUrl, method) => {
    violations.add(safeBrowserTargetLabel(rawUrl, method));
  };

  // This runs in every page and child frame before application scripts. With
  // service workers blocked in the Playwright config, no application-created
  // worker or direct WebTransport/WebRTC primitive remains able to escape the
  // page/frame HTTP and WebSocket boundary.
  await context.addInitScript(installBrowserRuntimeGuard);

  context.on("request", (request) => {
    if (!isAllowedBrowserRequest(
      request.url(),
      request.method(),
      allowedOrigins,
      configuration.apiOrigin,
    )) {
      recordViolation(request.url(), request.method());
    }
  });

  const watchPage = (candidate) => {
    candidate.on("framenavigated", (frame) => {
      if (!evaluateBrowserTarget(frame.url(), allowedOrigins).allowed) {
        recordViolation(frame.url(), "NAVIGATE");
      }
    });
    if (candidate !== page) {
      recordViolation(candidate.url(), "POPUP");
      void candidate.close().catch(() => undefined);
    }
  };
  page.on("framenavigated", (frame) => {
    if (!evaluateBrowserTarget(frame.url(), allowedOrigins).allowed) {
      recordViolation(frame.url(), "NAVIGATE");
    }
  });
  context.on("page", watchPage);

  // BrowserContext routing also covers the initial navigation of a popup. A
  // page-level route starts too late for that first request.
  await context.route("**/*", async (route) => {
    const request = route.request();
    const decision = requestGate.authorize(request.url(), request.method());
    if (!decision.allowed) {
      recordViolation(request.url(), request.method());
      if (decision.exactLogin) {
        reportLoginAttempt({ kind: "duplicate", status: null });
      }
      await route.abort("blockedbyclient");
      return;
    }

    let response;
    const requestLabel = decision.exactLogin ? "LOGIN" : request.method();
    try {
      // Every admitted HTTP request is sent once to the real target and never
      // follows a redirect. EventSource is disabled before page code, so these
      // responses are finite; WebSockets use the separate transparent route.
      const forwardOptions = buildBrowserForwardOptions(
        request.method(),
        await request.allHeaders(),
        request.postDataBuffer(),
      );
      // The test fixture's APIRequestContext is isolated from the browser
      // context. Set-Cookie can therefore affect Chromium only through the
      // unmodified response fulfilled below, while Cookie/Authorization on the
      // outgoing request are exactly the headers Chromium selected.
      response = await apiRequest.fetch(request.url(), forwardOptions);
      const status = response.status();
      if (isRedirectStatus(status)) {
        recordViolation(request.url(), `${requestLabel}_REDIRECT`);
        if (decision.exactLogin) reportLoginAttempt({ kind: "redirect", status });
        await route.abort("blockedbyresponse");
        return;
      }
      if (new URL(request.url()).origin === configuration.apiOrigin
          && configuration.appOrigin !== configuration.apiOrigin) {
        const corsVerdict = evaluateCredentialedCorsResponse(
          response.headers(),
          configuration.appOrigin,
        );
        if (!corsVerdict.allowed) {
          recordViolation(request.url(), `${requestLabel}_CORS_${corsVerdict.reason.toUpperCase()}`);
          if (decision.exactLogin) reportLoginAttempt({ kind: "cors-response", status });
          await route.abort("blockedbyresponse");
          return;
        }
      }
      // The isolated forwarder returned this exact response. Fulfill transfers
      // it without synthetic payload or status/header/body changes.
      await route.fulfill({ response });
      if (decision.exactLogin) reportLoginAttempt({ kind: "response", status });
    } catch {
      recordViolation(request.url(), `${requestLabel}_NETWORK_ERROR`);
      if (decision.exactLogin) reportLoginAttempt({ kind: "network-error", status: null });
      await route.abort("failed").catch(() => undefined);
    } finally {
      await response?.dispose().catch(() => undefined);
    }
  });

  await context.routeWebSocket("**/*", async (webSocket) => {
    const decision = evaluateBrowserTarget(webSocket.url(), allowedOrigins);
    if (!decision.allowed || decision.kind !== "websocket") {
      recordViolation(webSocket.url(), "WEBSOCKET");
      await webSocket.close({ code: 1008, reason: "Origine E2E non autorisée" });
      return;
    }
    // This is a transparent connection to the configured server, never a mock.
    webSocket.connectToServer();
  });

  return Object.freeze({
    loginAttempt,
    loginSnapshot: () => requestGate.snapshot(),
    violations,
  });
}

async function proveRealCredentialedCorsPreflight(apiRequest, configuration) {
  if (configuration.appOrigin === configuration.apiOrigin) return;

  const response = await apiRequest.fetch(`${configuration.apiOrigin}/auth/login`, {
    failOnStatusCode: false,
    headers: {
      "Access-Control-Request-Headers": "content-type",
      "Access-Control-Request-Method": "POST",
      Origin: configuration.appOrigin,
    },
    ...NO_REDIRECT_OR_RETRY,
    method: "OPTIONS",
  });
  try {
    const verdict = evaluateCredentialedLoginPreflight(
      response.status(),
      response.headers(),
      configuration.appOrigin,
    );
    expect(
      verdict.allowed,
      `Le vrai préflight CORS de connexion est refusé (${verdict.reason}, HTTP ${response.status()}).`,
    ).toBe(true);
  } finally {
    await response.dispose();
  }
}

function expectCurrentOrigin(page, expectedOrigin) {
  expect(new URL(page.url()).origin, "Une navigation a quitté l'origine web autorisée.").toBe(expectedOrigin);
}

function decodedPathParameter(rawUrl, prefix, suffix = "") {
  const url = new URL(rawUrl);
  const start = url.pathname.lastIndexOf(prefix);
  if (start < 0 || (suffix && !url.pathname.endsWith(suffix))) return null;
  const valueStart = start + prefix.length;
  const valueEnd = suffix ? url.pathname.length - suffix.length : url.pathname.length;
  try {
    return decodeURIComponent(url.pathname.slice(valueStart, valueEnd));
  } catch {
    return null;
  }
}

test("le shell authentifié ouvre le Studio d'une tentative réelle", async ({ context, page, request }) => {
  const configuration = assertRuntimeEnabled();
  const networkBoundary = await installNetworkBoundary(context, page, request, configuration);

  const shellResponse = await page.goto("/", { waitUntil: "domcontentloaded" });
  expect(shellResponse, "Le serveur web n'a renvoyé aucune réponse de document.").not.toBeNull();
  expect(shellResponse.ok(), `Le shell a répondu HTTP ${shellResponse.status()}.`).toBe(true);
  expectCurrentOrigin(page, configuration.appOrigin);

  await expect(page.getByRole("heading", { name: "Retrouver ton espace" })).toBeVisible();
  expect(await page.evaluate(() => {
    const blocked = {};
    for (const name of [
      "Worker",
      "SharedWorker",
      "WebTransport",
      "RTCPeerConnection",
      "webkitRTCPeerConnection",
      "WebSocketStream",
    ]) {
      try {
        Reflect.construct(globalThis[name], ["data:text/javascript,"]);
        blocked[name] = false;
      } catch (error) {
        blocked[name] = error instanceof Error && error.message.includes("frontière E2E");
      }
    }
    return blocked;
  })).toEqual({
    RTCPeerConnection: true,
    SharedWorker: true,
    WebSocketStream: true,
    WebTransport: true,
    Worker: true,
    webkitRTCPeerConnection: true,
  });
  expect(await page.evaluate(() => typeof EventSource)).toBe("undefined");
  // The APIRequestContext call bypasses BrowserContext routing entirely. It
  // proves the deployed server's credentialed CORS response before either
  // credential is entered in the page.
  await proveRealCredentialedCorsPreflight(request, configuration);
  await page.getByLabel("Identifiant").fill(configuration.login);
  await page.getByLabel("Mot de passe").fill(configuration.password);

  const loginResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.origin === configuration.apiOrigin
      && url.pathname === "/auth/login"
      && url.search === ""
      && url.hash === "";
  });
  await page.getByRole("button", { name: "Se connecter" }).click();
  const loginAttempt = await networkBoundary.loginAttempt;
  expect(
    loginAttempt.kind,
    `La connexion réelle n'a pas produit une réponse directe (résultat: ${loginAttempt.kind}).`,
  ).toBe("response");
  expect(
    loginAttempt.status >= 200 && loginAttempt.status < 300,
    `L'authentification réelle a répondu HTTP ${loginAttempt.status}.`,
  ).toBe(true);
  const loginResponse = await loginResponsePromise;
  expect(loginResponse.ok(), `L'authentification réelle a répondu HTTP ${loginResponse.status()}.`).toBe(true);
  expect(networkBoundary.loginSnapshot()).toEqual({ loginAttempts: 1 });

  const navigation = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(navigation).toBeVisible();
  await expect(page.locator(".connection-status")).toContainText("API connectée");
  await expect(page).toHaveTitle("Accueil — Agent Company Platform");
  expectCurrentOrigin(page, configuration.appOrigin);

  await navigation.getByRole("link", { name: "Missions", exact: true }).click();
  await expect(page.locator("h1.workspace-route-title")).toHaveText("Missions");
  expect(new URL(page.url()).pathname).toBe("/missions");

  const query = new URLSearchParams({ run: configuration.runId, vue: "studio" });
  const [missionResponse, eventsResponse, studioResponse] = await Promise.all([
    page.waitForResponse((response) => (
      response.request().method() === "GET"
      && new URL(response.url()).origin === configuration.apiOrigin
      && decodedPathParameter(response.url(), "/missions/by-run/") === configuration.runId
    )),
    page.waitForResponse((response) => (
      response.request().method() === "GET"
      && new URL(response.url()).origin === configuration.apiOrigin
      && decodedPathParameter(response.url(), "/runs/", "/events") === configuration.runId
    )),
    page.goto(`/missions?${query.toString()}`, { waitUntil: "domcontentloaded" }),
  ]);
  expect(studioResponse, "Le lien profond Studio n'a renvoyé aucune réponse de document.").not.toBeNull();
  expect(studioResponse.ok(), `Le lien profond Studio a répondu HTTP ${studioResponse.status()}.`).toBe(true);
  expect(
    missionResponse.ok(),
    `La lecture réelle de la tentative a répondu HTTP ${missionResponse.status()}.`,
  ).toBe(true);
  expect(
    eventsResponse.ok(),
    `Le chargement réel du journal a répondu HTTP ${eventsResponse.status()}.`,
  ).toBe(true);
  const missionPayload = await missionResponse.json();
  const loadedConfiguredRun = Array.isArray(missionPayload?.runs)
    && missionPayload.runs.some((run) => run && typeof run === "object" && run.id === configuration.runId);
  expect(loadedConfiguredRun, "La réponse mission ne contient pas la tentative configurée.").toBe(true);
  expectCurrentOrigin(page, configuration.appOrigin);

  await expect(page.getByText("Studio de la tentative", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Chronologie", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Prise de contrôle non livrée", exact: true })).toBeVisible();
  await expect(page.locator(".studio")).toBeVisible();
  await expect(page.locator(".studio .state-loading")).toHaveCount(0);
  await expect(
    page.locator(".studio .state-error, .studio .state-offline, .studio .state-forbidden"),
  ).toHaveCount(0);

  expect(
    [...networkBoundary.violations],
    "Le parcours a tenté de contacter une origine non autorisée ; les requêtes ont été bloquées.",
  ).toEqual([]);
  expect(networkBoundary.loginSnapshot()).toEqual({ loginAttempts: 1 });
});
