const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const UNSPECIFIED_HOSTS = new Set(["0.0.0.0", "[::]"]);

export class E2EConfigurationError extends Error {
  constructor(message) {
    super(message);
    this.name = "E2EConfigurationError";
  }
}

/**
 * The real browser suite is enabled by one value only. Empty and `0` mean an
 * intentional skip; values such as `true` are rejected so a typo cannot look
 * like a successful opt-in.
 */
export function parseE2EOptIn(value) {
  if (value === undefined || value === "" || value === "0") return false;
  if (value === "1") return true;
  throw new E2EConfigurationError("ACP_E2E doit valoir exactement 1 pour activer les tests, ou 0 pour les ignorer.");
}

function requiredValue(environment, name) {
  const value = environment[name];
  if (typeof value !== "string" || value.length === 0) {
    throw new E2EConfigurationError(`${name} est requis quand ACP_E2E=1.`);
  }
  if (value !== value.trim()) {
    throw new E2EConfigurationError(`${name} ne doit pas contenir d'espace en début ou en fin.`);
  }
  if (CONTROL_CHARACTERS.test(value)) {
    throw new E2EConfigurationError(`${name} contient un caractère de contrôle interdit.`);
  }
  return value;
}

/**
 * Parse an operator-provided browser target without ever echoing its raw value
 * in an error. Remote clear-text HTTP, embedded credentials and URL decorations
 * are all refused. The shell is currently rooted at `/`, so sub-path targets are
 * rejected rather than silently exercising a different route.
 */
export function parseSafeOrigin(environment, name) {
  const raw = requiredValue(environment, name);
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new E2EConfigurationError(`${name} doit être une URL absolue HTTP(S).`);
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new E2EConfigurationError(`${name} doit utiliser HTTP ou HTTPS.`);
  }
  if (parsed.username || parsed.password) {
    throw new E2EConfigurationError(`${name} ne doit contenir aucun identifiant.`);
  }
  if (parsed.search || parsed.hash) {
    throw new E2EConfigurationError(`${name} ne doit contenir ni requête ni fragment.`);
  }
  if (parsed.pathname !== "/") {
    throw new E2EConfigurationError(`${name} doit désigner la racine d'une origine, sans sous-chemin.`);
  }
  if (UNSPECIFIED_HOSTS.has(parsed.hostname)) {
    throw new E2EConfigurationError(`${name} ne peut pas cibler une adresse d'écoute non routable.`);
  }
  if (parsed.protocol === "http:" && !LOOPBACK_HOSTS.has(parsed.hostname)) {
    throw new E2EConfigurationError(`${name} doit utiliser HTTPS hors de la machine locale.`);
  }

  return parsed;
}

function readLogin(environment) {
  const login = requiredValue(environment, "ACP_E2E_LOGIN");
  if (login.length > 120) {
    throw new E2EConfigurationError("ACP_E2E_LOGIN dépasse la borne de 120 caractères.");
  }
  return login;
}

function readPassword(environment) {
  const password = environment.ACP_E2E_PASSWORD;
  if (typeof password !== "string" || password.length < 12 || password.length > 256) {
    throw new E2EConfigurationError("ACP_E2E_PASSWORD doit contenir entre 12 et 256 caractères.");
  }
  if (CONTROL_CHARACTERS.test(password)) {
    throw new E2EConfigurationError("ACP_E2E_PASSWORD contient un caractère de contrôle interdit.");
  }
  return password;
}

function readRunId(environment) {
  const runId = requiredValue(environment, "ACP_E2E_RUN_ID");
  if (runId.length > 200) {
    throw new E2EConfigurationError("ACP_E2E_RUN_ID dépasse la borne de 200 caractères.");
  }
  return runId;
}

/**
 * Read the complete runtime configuration. No target or credential is needed
 * while disabled, which keeps the repository's default install and test paths
 * browser-free.
 */
export function readE2EConfiguration(environment = process.env) {
  const enabled = parseE2EOptIn(environment.ACP_E2E);
  if (!enabled) return Object.freeze({ enabled: false });

  const baseUrl = parseSafeOrigin(environment, "ACP_E2E_BASE_URL");
  const confirmedOrigin = parseSafeOrigin(environment, "ACP_E2E_ALLOWED_ORIGIN");
  const apiOrigin = parseSafeOrigin(environment, "ACP_E2E_API_ORIGIN");
  if (baseUrl.origin !== confirmedOrigin.origin) {
    throw new E2EConfigurationError(
      "ACP_E2E_ALLOWED_ORIGIN doit confirmer exactement l'origine de ACP_E2E_BASE_URL.",
    );
  }

  return Object.freeze({
    enabled: true,
    baseURL: baseUrl.href,
    appOrigin: baseUrl.origin,
    apiOrigin: apiOrigin.origin,
    login: readLogin(environment),
    password: readPassword(environment),
    runId: readRunId(environment),
  });
}
