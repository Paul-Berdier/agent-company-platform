import {
  WorkspaceApiError,
  WorkspaceHttpClient,
  hasString,
  isRecord,
  type Fetcher,
} from "./workspace-api";

export interface AuthUser {
  id: string;
  login: string;
  display_name: string;
  role: "owner" | "operator" | "viewer";
}

export interface AuthStatus {
  bootstrap_required: boolean;
}

export interface AuthSession {
  user: AuthUser;
  csrf_token: string;
  expires_at: string;
}

export interface BootstrapInput {
  login: string;
  displayName: string;
  password: string;
  bootstrapToken: string;
}

export interface LoginInput {
  login: string;
  password: string;
}

function isAuthStatus(value: unknown): value is AuthStatus {
  return isRecord(value) && typeof value.bootstrap_required === "boolean";
}

function isAuthUser(value: unknown): value is AuthUser {
  return isRecord(value)
    && hasString(value, "id")
    && hasString(value, "login")
    && hasString(value, "display_name")
    && ["owner", "operator", "viewer"].includes(String(value.role));
}

function isAuthSession(value: unknown): value is AuthSession {
  return isRecord(value)
    && isAuthUser(value.user)
    && typeof value.csrf_token === "string"
    && hasString(value, "expires_at")
    && value.csrf_token.length > 0;
}

function isSignedOut(value: unknown): value is { status: "signed_out" } {
  return isRecord(value) && value.status === "signed_out";
}

export class AuthApiClient {
  readonly http: WorkspaceHttpClient;

  constructor(options: {
    baseUrl?: string;
    fetcher?: Fetcher;
    timeoutMs?: number;
    http?: WorkspaceHttpClient;
  } = {}) {
    this.http = options.http ?? new WorkspaceHttpClient(options);
  }

  fetchStatus(): Promise<AuthStatus> {
    return this.http.request("/auth/status", isAuthStatus);
  }

  async fetchSession(): Promise<AuthSession> {
    const session = await this.http.request("/auth/session", isAuthSession);
    this.http.setCsrfToken(session.csrf_token);
    return session;
  }

  async bootstrap(input: BootstrapInput): Promise<AuthSession> {
    const token = input.bootstrapToken.trim();
    if (!token) {
      throw new WorkspaceApiError("Le jeton d’initialisation est requis.", "forbidden", 403);
    }
    const session = await this.http.request("/auth/bootstrap", isAuthSession, {
      method: "POST",
      headers: { "X-ACP-Bootstrap-Token": token },
      body: JSON.stringify({
        login: input.login.trim(),
        display_name: input.displayName.trim(),
        password: input.password,
      }),
    }, { csrf: false });
    this.http.setCsrfToken(session.csrf_token);
    return session;
  }

  async login(input: LoginInput): Promise<AuthSession> {
    const session = await this.http.request("/auth/login", isAuthSession, {
      method: "POST",
      body: JSON.stringify({ login: input.login.trim(), password: input.password }),
    }, { csrf: false });
    this.http.setCsrfToken(session.csrf_token);
    return session;
  }

  async logout(): Promise<void> {
    await this.http.request("/auth/logout", isSignedOut, { method: "POST" });
    this.http.setCsrfToken(null);
  }

  clearLocalSession(): void {
    this.http.setCsrfToken(null);
  }
}
