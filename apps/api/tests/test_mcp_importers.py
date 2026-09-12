"""Import assisté de configurations MCP existantes (spec Lot D §4.5, §5.2, §10).

Les configurations importées sont des **données non fiables** : aucune valeur n'est
renvoyée en clair dans l'aperçu, aucune entrée n'est appliquée sans choix explicite,
et une entrée non exprimable dans le modèle de la plateforme est signalée plutôt que
transformée en serveur approximatif.

Aucun réseau réel : seules les fonctions pures et les routes sont exercées.
"""

from __future__ import annotations

import json
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api.deps import get_db
from acp_api.main import app
from acp_api.mcp import importers
from acp_api.routers.workers import utcnow
from acp_api.secrets_vault import generate_key
from acp_api.security import create_user_session, hash_password
from acp_database.models import Base, EventModel, McpServerRevisionModel, UserModel

PASSWORD = "correct horse battery staple"

# Valeurs littérales « secrètes » présentes dans les fixtures : aucune ne doit
# ressortir d'un aperçu ou d'un événement.
CLAUDE_CLEAR_SECRET = "ctx-live-abcd1234"
CLAUDE_PROJECT_SECRET = "Bearer proj-token-xyz99"
SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,62}$")

# Valeur sensible portée par une ligne YAML dont le guillemet n'est jamais fermé :
# l'erreur de l'analyseur ne doit pas recopier la ligne fautive (spec §0.3).
HERMES_BROKEN_SECRET = "ghp-live-secret-9999"
HERMES_UNCLOSED_QUOTE = (
    "mcp_servers:\n"
    "  fuite:\n"
    "    headers:\n"
    f'      API_KEY: "{HERMES_BROKEN_SECRET}\n'
    "    url: https://a.example/mcp\n"
)


CLAUDE_CONTENT = json.dumps(
    {
        "mcpServers": {
            "context7": {
                "type": "http",
                "url": "https://mcp.context7.com/mcp",
                "headers": {"CONTEXT7_API_KEY": CLAUDE_CLEAR_SECRET, "X-Client": "acp"},
                "timeout": 30,
            },
            "Filesystem Local": {
                "command": "/usr/local/bin/npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem@2025.8.21", "/data"],
                "env": {"LOG_LEVEL": "${LOG_LEVEL:-info}", "GITHUB_TOKEN": "${GITHUB_TOKEN}"},
            },
            "legacy-sse": {"type": "sse", "url": "https://sse.example/mcp"},
            "oauthy": {
                "type": "http",
                "url": "https://oauth.example/mcp",
                "oauth": {"client_id": "abc"},
                "headersHelper": "/usr/local/bin/headers.sh",
            },
            "broken": {"description": "ni url ni commande"},
        },
        "projects": {
            "C:\\dev\\projet": {
                "mcpServers": {
                    "context7": {
                        "type": "http",
                        "url": "https://proj.example/mcp",
                        "headers": {"Authorization": CLAUDE_PROJECT_SECRET},
                    }
                }
            }
        },
    },
    ensure_ascii=False,
)

CODEX_CONTENT = """
[mcp_servers.github-remote]
url = "https://api.githubcopilot.com/mcp/"
bearer_token_env_var = "GITHUB_PAT"
startup_timeout_sec = 30
enabled_tools = ["search", "fetch"]

[mcp_servers.github-remote.http_headers]
X-Client = "acp"

[mcp_servers.github-remote.env_http_headers]
X-Extra = "EXTRA_HEADER_ENV"

[mcp_servers.local-fs]
command = "/usr/local/bin/npx"
args = ["-y", "@modelcontextprotocol/server-filesystem@2025.8.21", "/data"]
env = { LOG_LEVEL = "info" }
env_vars = ["API_KEY"]
cwd = "/data"
enabled = false
tool_timeout_sec = 45

[mcp_servers.local-fs.tools.search]
enabled = true
"""

HERMES_CONTENT = """
mcp_servers:
  context7:
    url: https://mcp.context7.com/mcp
    headers:
      CONTEXT7_API_KEY: ${CONTEXT7_API_KEY}
      X-Client: acp
    timeout: 20
    tools:
      include: [search]
  legacy:
    url: https://legacy.example/mcp
    auth: oauth
    client_cert: /etc/ssl/client.pem
    identity_header: X-Identity
  local:
    command: /usr/local/bin/mcp-server
    args: ["--root", "/data"]
    env:
      API_KEY: ${API_KEY}
      LOG_LEVEL: ${LOG_LEVEL:-info}
    enabled: false
"""


def entry_by_name(preview, name: str):
    for entry in preview.entries:
        if entry.name == name:
            return entry
    raise AssertionError(f"entrée « {name} » absente de {[e.name for e in preview.entries]}")


def candidate_for(entry, key: str):
    for candidate in entry.secret_candidates:
        if candidate.key == key:
            return candidate
    raise AssertionError(f"candidat « {key} » absent de {[c.key for c in entry.secret_candidates]}")


# --- détection de format ------------------------------------------------------------------


@pytest.mark.parametrize(
    "content, expected",
    [
        (CLAUDE_CONTENT, "claude"),
        (CODEX_CONTENT, "codex"),
        (HERMES_CONTENT, "hermes"),
        ('{"servers": {}}', None),
        ("", None),
        ("pas une configuration", None),
    ],
)
def test_detect_format(content, expected):
    assert importers.detect_format(content) == expected


def test_parse_import_auto_detects_each_format():
    for content, expected in ((CLAUDE_CONTENT, "claude"), (CODEX_CONTENT, "codex"), (HERMES_CONTENT, "hermes")):
        preview = importers.parse_import("auto", content, set())
        assert preview.detected_format == expected
        assert preview.errors == []


def test_auto_detection_failure_is_an_explicit_error_not_a_guess():
    preview = importers.parse_import("auto", "ni json ni toml ni yaml : ???", set())
    assert preview.detected_format is None
    assert preview.entries == []
    assert preview.errors and any("format" in message.lower() for message in preview.errors)


# --- Claude Code --------------------------------------------------------------------------


def test_claude_global_entries_are_normalized():
    preview = importers.parse_import("claude", CLAUDE_CONTENT, set())
    context7 = entry_by_name(preview, "context7")
    assert context7.source_name == "context7"
    assert context7.transport == "http"
    assert context7.importable is True
    assert context7.config is not None
    assert context7.config.http is not None
    assert context7.config.http.url == "https://mcp.context7.com/mcp"
    # L'en-tête non secret reste une valeur littérale ; l'en-tête secret est retiré.
    assert context7.config.http.headers == {"X-Client": "acp"}
    assert context7.config.http.header_secrets == {}
    assert context7.config.http.timeout_seconds == 30

    candidate = candidate_for(context7, "CONTEXT7_API_KEY")
    assert candidate.location == "header"
    assert candidate.masked_value == "***34"
    assert candidate.suggested_secret_name == "CONTEXT7_CONTEXT7_API_KEY"


def test_claude_stdio_entry_expands_defaults_and_flags_secret_placeholders():
    preview = importers.parse_import("claude", CLAUDE_CONTENT, set())
    entry = entry_by_name(preview, "filesystem-local")
    assert entry.source_name == "Filesystem Local"
    assert entry.transport == "stdio"
    assert entry.config is not None and entry.config.stdio is not None
    stdio = entry.config.stdio
    assert stdio.command == "/usr/local/bin/npx"
    assert stdio.args == ["-y", "@modelcontextprotocol/server-filesystem@2025.8.21", "/data"]
    # ${LOG_LEVEL:-info} : clé non secrète ⇒ la valeur par défaut est conservée.
    assert stdio.env == {"LOG_LEVEL": "info"}
    assert stdio.env_secrets == {}
    candidate = candidate_for(entry, "GITHUB_TOKEN")
    assert candidate.location == "env"
    assert candidate.suggested_secret_name == "FILESYSTEM_LOCAL_GITHUB_TOKEN"


def test_claude_project_entries_are_read_with_their_path():
    preview = importers.parse_import("claude", CLAUDE_CONTENT, set())
    names = [entry.name for entry in preview.entries]
    # Le doublon de nom entre la section globale et un projet est désambiguïsé.
    assert "context7" in names and "context7-2" in names
    scoped = entry_by_name(preview, "context7-2")
    assert scoped.source_name == "C:\\dev\\projet:context7"
    assert scoped.config is not None and scoped.config.http is not None
    assert scoped.config.http.url == "https://proj.example/mcp"
    assert candidate_for(scoped, "Authorization").location == "header"
    assert any("nom" in warning.lower() for warning in scoped.warnings)


def test_claude_unsupported_transports_and_options_are_listed():
    preview = importers.parse_import("claude", CLAUDE_CONTENT, set())
    sse = entry_by_name(preview, "legacy-sse")
    assert sse.importable is False
    assert any(item.startswith("sse") for item in sse.unsupported)

    oauthy = entry_by_name(preview, "oauthy")
    assert oauthy.importable is True  # l'endpoint reste exprimable
    assert any(item.startswith("oauth") for item in oauthy.unsupported)
    assert any(item.startswith("headersHelper") for item in oauthy.unsupported)


def test_claude_entry_without_url_or_command_is_not_importable():
    preview = importers.parse_import("claude", CLAUDE_CONTENT, set())
    broken = entry_by_name(preview, "broken")
    assert broken.importable is False
    assert broken.transport is None
    assert broken.config is None
    assert broken.warnings or broken.unsupported


def test_claude_ws_transport_is_refused():
    content = json.dumps({"mcpServers": {"socket": {"type": "ws", "url": "wss://ws.example/mcp"}}})
    entry = entry_by_name(importers.parse_import("claude", content, set()), "socket")
    assert entry.importable is False
    assert any(item.startswith("ws") for item in entry.unsupported)


# --- Codex --------------------------------------------------------------------------------


def test_codex_http_entry_maps_bearer_and_header_environment_variables():
    preview = importers.parse_import("codex", CODEX_CONTENT, set())
    entry = entry_by_name(preview, "github-remote")
    assert entry.transport == "http"
    assert entry.config is not None and entry.config.http is not None
    assert entry.config.http.url == "https://api.githubcopilot.com/mcp/"
    assert entry.config.http.headers == {"X-Client": "acp"}
    assert entry.config.http.timeout_seconds == 30
    authorization = candidate_for(entry, "Authorization")
    assert authorization.location == "header"
    assert authorization.suggested_secret_name == "GITHUB_REMOTE_AUTHORIZATION"
    extra = candidate_for(entry, "X-Extra")
    assert extra.location == "header"
    assert any("outils" in warning.lower() for warning in entry.warnings)


def test_codex_stdio_entry_reports_disabled_state_and_per_tool_tables():
    preview = importers.parse_import("codex", CODEX_CONTENT, set())
    entry = entry_by_name(preview, "local-fs")
    assert entry.transport == "stdio"
    assert entry.config is not None and entry.config.stdio is not None
    assert entry.config.stdio.cwd == "/data"
    assert entry.config.stdio.env == {"LOG_LEVEL": "info"}
    assert entry.config.stdio.timeout_seconds == 45
    assert candidate_for(entry, "API_KEY").location == "env"
    assert any("désactivé" in warning for warning in entry.warnings)
    assert any(item.startswith("[mcp_servers.local-fs.tools.search]") for item in entry.unsupported)


def test_codex_invalid_toml_is_reported_as_an_error():
    preview = importers.parse_import("codex", "[mcp_servers.oops\ncommand = ", set())
    assert preview.entries == []
    assert preview.errors


# --- Hermes -------------------------------------------------------------------------------


def test_hermes_entries_are_normalized_with_their_unsupported_options():
    preview = importers.parse_import("hermes", HERMES_CONTENT, set())
    context7 = entry_by_name(preview, "context7")
    assert context7.transport == "http"
    assert context7.config is not None and context7.config.http is not None
    assert context7.config.http.headers == {"X-Client": "acp"}
    assert context7.config.http.timeout_seconds == 20
    assert candidate_for(context7, "CONTEXT7_API_KEY").location == "header"
    assert any("outils" in warning.lower() for warning in context7.warnings)

    legacy = entry_by_name(preview, "legacy")
    assert any(item.startswith("auth") for item in legacy.unsupported)
    assert any(item.startswith("client_cert") for item in legacy.unsupported)
    assert any(item.startswith("identity_header") for item in legacy.unsupported)

    local = entry_by_name(preview, "local")
    assert local.transport == "stdio"
    assert local.config is not None and local.config.stdio is not None
    assert local.config.stdio.env == {"LOG_LEVEL": "info"}
    assert candidate_for(local, "API_KEY").location == "env"
    assert any("désactivé" in warning for warning in local.warnings)


def test_hermes_yaml_aliases_are_refused_instead_of_being_expanded():
    """« Billion laughs » : un alias YAML peut démultiplier un petit fichier en mémoire."""

    bomb = "mcp_servers:\n  a: &x\n    url: https://a.example/mcp\n  b: *x\n"
    preview = importers.parse_import("hermes", bomb, set())
    assert preview.entries == []
    assert preview.errors and "alias" in preview.errors[0].lower()


@pytest.mark.parametrize("import_format", ["claude", "auto"])
def test_deeply_nested_content_is_reported_as_an_error_not_a_crash(import_format):
    """Une imbrication extrême épuise la pile des analyseurs : état explicite, jamais un 500."""

    depth = 20_000
    preview = importers.parse_import(import_format, "[" * depth + "]" * depth, set())
    assert preview.entries == []
    assert preview.errors


@pytest.mark.parametrize("value", [{"host": "a.example"}, 42, ["https://a.example/mcp"]])
def test_a_non_textual_url_or_command_is_refused_rather_than_stringified(value):
    """Sans ce contrôle, ``str(valeur)`` fabriquerait une URL ou une commande fantaisiste."""

    content = json.dumps({"mcpServers": {"s": {"url": value}, "t": {"command": value}}})
    preview = importers.parse_import("claude", content, set())
    for name in ("s", "t"):
        entry = entry_by_name(preview, name)
        assert entry.importable is False, name
        assert entry.config is None, name


def test_an_out_of_bounds_value_makes_the_entry_non_importable():
    content = json.dumps({"mcpServers": {"long": {"url": "https://a.example/" + "x" * 2100}}})
    entry = entry_by_name(importers.parse_import("claude", content, set()), "long")
    assert entry.importable is False
    assert entry.config is None
    assert entry.unsupported


def test_hermes_invalid_yaml_is_reported_as_an_error():
    preview = importers.parse_import("hermes", "mcp_servers:\n  - [oups\n", set())
    assert preview.entries == []
    assert preview.errors


def test_an_unreadable_yaml_situates_the_problem_without_echoing_the_faulty_line():
    """Un YAML mal fermé est situé (ligne/colonne) sans recopier son extrait de source.

    ``MarkedYAMLError.__str__`` inclut l'extrait de la ligne fautive : le formater
    ferait ressortir la valeur qui s'y trouve — exactement ce que le masquage
    ``***`` interdit.
    """

    preview = importers.parse_import("hermes", HERMES_UNCLOSED_QUOTE, set())
    assert preview.entries == []
    assert preview.errors
    assert HERMES_BROKEN_SECRET not in preview.model_dump_json()
    assert "ligne 4" in preview.errors[0]


@pytest.mark.parametrize(
    "content",
    [
        f'mcp_servers:\n  a:\n    url: "{HERMES_BROKEN_SECRET}\n',
        f"mcp_servers:\n\ta: {HERMES_BROKEN_SECRET}\n",
        f"mcp_servers: [{HERMES_BROKEN_SECRET}\n",
        f"mcp_servers:\n  a: !{HERMES_BROKEN_SECRET} 1\n",
        f"mcp_servers: &{HERMES_BROKEN_SECRET}\n  a: 1\n  b: *{HERMES_BROKEN_SECRET}\n",
    ],
    ids=["guillemet", "tabulation", "sequence", "etiquette", "ancre"],
)
def test_no_fragment_of_an_invalid_yaml_is_copied_into_the_errors(content):
    """Aucune forme de YAML invalide ne recopie un fragment du document analysé."""

    preview = importers.parse_import("hermes", content, set())
    assert preview.errors, content
    assert HERMES_BROKEN_SECRET not in preview.model_dump_json(), preview.errors


def test_two_pasted_documents_are_diagnosed_as_such_and_not_as_a_tag():
    """Coller deux configurations à la suite doit nommer le vrai problème.

    Le propriétaire qui colle deux fichiers obtient une erreur de composition YAML.
    La renvoyer comme « étiquette ou ancre » l'enverrait chercher un problème
    inexistant ; le libellé de l'analyseur est ici purement structurel et ne
    contient aucun fragment du document.
    """

    content = (
        f"mcp_servers:\n  a:\n    url: https://a.example/{HERMES_BROKEN_SECRET}\n"
        f"---\nmcp_servers:\n  b:\n    url: https://b.example/mcp\n"
    )

    preview = importers.parse_import("hermes", content, set())

    assert preview.errors
    assert HERMES_BROKEN_SECRET not in preview.model_dump_json()
    assert "étiquette" not in preview.errors[0], preview.errors
    assert "document" in preview.errors[0].lower(), preview.errors


# --- secrets : masquage, candidats, non-divulgation ---------------------------------------


def test_no_clear_secret_value_survives_a_preview():
    for fmt, content in (("claude", CLAUDE_CONTENT), ("codex", CODEX_CONTENT), ("hermes", HERMES_CONTENT)):
        dumped = importers.parse_import(fmt, content, set()).model_dump_json()
        assert CLAUDE_CLEAR_SECRET not in dumped
        assert CLAUDE_PROJECT_SECRET not in dumped


@pytest.mark.parametrize(
    ("label", "block"),
    [
        ("auth_bearer", "    auth:\n      type: bearer\n      token: {secret}\n"),
        ("auth_oauth", "    auth:\n      type: oauth\n      client_secret: {secret}\n"),
        ("timeout", "    timeout: {secret}\n"),
        ("identity_header", "    identity_header:\n      name: X-User\n      value: {secret}\n"),
        ("client_cert", "    client_cert: {secret}\n"),
    ],
)
def test_a_valid_hermes_block_never_echoes_its_own_values(label, block):
    """Un contenu **valide** ne doit pas non plus renvoyer ce qu'il transporte.

    Un bloc ``auth:`` Hermes porte typiquement un jeton en clair. Le signaler comme
    non supporté est correct ; en recopier la valeur la ferait ressortir dans la
    réponse de l'aperçu, dans le DOM de l'écran d'import et dans la sortie du CLI.
    """

    secret = "ghp_valeur_de_jeton_en_clair_9999"
    content = (
        "mcp_servers:\n"
        "  serveur:\n"
        "    url: https://exemple.test/mcp\n"
    ) + block.format(secret=secret)

    preview = importers.parse_import("hermes", content, set())

    assert preview.entries, label
    assert secret not in preview.model_dump_json(), label


def test_masked_value_keeps_at_most_two_characters():
    content = json.dumps({"mcpServers": {"s": {"url": "https://a.example/mcp", "headers": {"X-Api-Key": "ab"}}}})
    entry = entry_by_name(importers.parse_import("claude", content, set()), "s")
    assert candidate_for(entry, "X-Api-Key").masked_value == "***"


def test_a_placeholder_value_has_nothing_to_mask_and_names_its_variable():
    """``${GITHUB_TOKEN}`` ne contient pas de valeur : le nom de la variable guide le choix."""

    entry = entry_by_name(importers.parse_import("claude", CLAUDE_CONTENT, set()), "filesystem-local")
    candidate = candidate_for(entry, "GITHUB_TOKEN")
    assert candidate.masked_value == "***"
    assert any("GITHUB_TOKEN" in warning for warning in entry.warnings)


def test_codex_bearer_and_header_variables_are_named_in_the_warnings():
    entry = entry_by_name(importers.parse_import("codex", CODEX_CONTENT, set()), "github-remote")
    assert candidate_for(entry, "Authorization").masked_value == "***"
    assert any("GITHUB_PAT" in warning for warning in entry.warnings)
    assert any("EXTRA_HEADER_ENV" in warning for warning in entry.warnings)


def test_every_suggested_secret_name_matches_the_vault_pattern():
    for fmt, content in (("claude", CLAUDE_CONTENT), ("codex", CODEX_CONTENT), ("hermes", HERMES_CONTENT)):
        for entry in importers.parse_import(fmt, content, set()).entries:
            for candidate in entry.secret_candidates:
                assert SECRET_NAME_RE.fullmatch(candidate.suggested_secret_name), candidate


def test_a_url_carrying_a_variable_is_refused_rather_than_imported_broken():
    content = json.dumps({"mcpServers": {"s": {"url": "https://a.example/mcp?key=${API_KEY}"}}})
    entry = entry_by_name(importers.parse_import("claude", content, set()), "s")
    assert entry.importable is False
    assert candidate_for(entry, "url").location == "url"
    assert any(item.startswith("url") for item in entry.unsupported)


def test_existing_names_are_flagged_as_conflicts():
    preview = importers.parse_import("claude", CLAUDE_CONTENT, {"context7"})
    assert entry_by_name(preview, "context7").conflict == "existing_server"
    assert entry_by_name(preview, "broken").conflict == "none"


def test_a_truncated_preview_says_so_instead_of_pretending_to_be_complete():
    servers = {f"srv-{index:04d}": {"url": f"https://s{index}.example/mcp"} for index in range(250)}
    preview = importers.parse_import("claude", json.dumps({"mcpServers": servers}), set())
    assert len(preview.entries) == importers.MAX_ENTRIES
    assert preview.errors and "limité" in preview.errors[0]


def test_oversized_content_is_refused_without_parsing():
    preview = importers.parse_import("claude", "x" * (importers.MAX_IMPORT_CHARS + 1), set())
    assert preview.entries == []
    assert preview.detected_format is None
    assert preview.errors


# --- routes ------------------------------------------------------------------------------


@pytest.fixture
def import_context(monkeypatch):
    bootstrap_token = f"bootstrap-{uuid4().hex}"
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", bootstrap_token)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    monkeypatch.delenv("ACP_OUTBOUND_PRIVATE_ALLOWLIST", raising=False)
    monkeypatch.delenv("ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP", raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            bootstrap = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": bootstrap_token},
                json={"login": "owner", "display_name": "Propriétaire", "password": PASSWORD},
            )
            assert bootstrap.status_code == 201, bootstrap.text
            owner = (client.cookies.get("acp_session"), bootstrap.json()["csrf_token"])
            client.headers["X-CSRF-Token"] = owner[1]
            yield {"client": client, "session_factory": session_factory, "owner": owner}
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _as_owner(context) -> None:
    client = context["client"]
    session_token, csrf_token = context["owner"]
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token


def _create_secret(context, name: str, value: str) -> str:
    response = context["client"].post("/secrets", json={"name": name, "value": value})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_operator(context):
    with context["session_factory"]() as db:
        user = UserModel(
            login_normalized=f"operator-{uuid4().hex[:8]}",
            display_name="Opérateur",
            password_hash=hash_password(PASSWORD),
            platform_role="operator",
            password_changed_at=utcnow(),
        )
        db.add(user)
        db.flush()
        _, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
    return session_token, csrf_token


def test_preview_route_returns_the_normalized_entries(import_context):
    response = import_context["client"].post(
        "/mcp/import/preview", json={"format": "auto", "content": CLAUDE_CONTENT}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["detected_format"] == "claude"
    names = [entry["name"] for entry in body["entries"]]
    assert "context7" in names
    assert CLAUDE_CLEAR_SECRET not in response.text


def test_preview_route_is_reserved_to_the_owner(import_context):
    client = import_context["client"]
    session_token, csrf_token = _create_operator(import_context)
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token
    response = client.post("/mcp/import/preview", json={"format": "auto", "content": CLAUDE_CONTENT})
    assert response.status_code == 403


def test_import_routes_refuse_a_request_without_a_valid_csrf_token(import_context):
    client = import_context["client"]
    for path in ("/mcp/import/preview", "/mcp/import/apply"):
        response = client.post(
            path,
            json={"format": "auto", "content": CLAUDE_CONTENT, "names": []},
            headers={"X-CSRF-Token": "jeton-invalide"},
        )
        assert response.status_code == 403, path


def test_preview_route_refuses_content_over_one_million_characters(import_context):
    response = import_context["client"].post(
        "/mcp/import/preview", json={"format": "auto", "content": "x" * 1_000_001}
    )
    assert response.status_code == 422


def test_preview_route_reports_invalid_content_without_a_server_error(import_context):
    response = import_context["client"].post(
        "/mcp/import/preview", json={"format": "claude", "content": "{ceci n'est pas du json"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["entries"] == []
    assert body["errors"]


def test_apply_creates_draft_servers_with_secret_references(import_context):
    client = import_context["client"]
    secret_id = _create_secret(import_context, "CONTEXT7_API_KEY", CLAUDE_CLEAR_SECRET)
    response = client.post(
        "/mcp/import/apply",
        json={
            "format": "auto",
            "content": CLAUDE_CONTENT,
            "names": ["context7"],
            "secret_mapping": {"CONTEXT7_CONTEXT7_API_KEY": secret_id},
            "on_conflict": "skip",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [server["name"] for server in body["created"]] == ["context7"]
    assert body["revised"] == []
    assert body["errors"] == []
    created = body["created"][0]
    assert created["status"] == "draft"
    assert created["source_kind"] == "import"
    assert created["origin"] == "claude"

    detail = client.get(f"/mcp/servers/{created['id']}").json()
    config = detail["current_revision"]["config"]["http"]
    assert config["header_secrets"] == {"CONTEXT7_API_KEY": {"secret_id": secret_id}}
    assert CLAUDE_CLEAR_SECRET not in json.dumps(detail)


def test_apply_skips_an_entry_whose_secret_is_not_mapped(import_context):
    response = import_context["client"].post(
        "/mcp/import/apply",
        json={"format": "auto", "content": CLAUDE_CONTENT, "names": ["context7"], "secret_mapping": {}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == []
    assert body["skipped"] == ["context7"]
    assert body["errors"] and "CONTEXT7_CONTEXT7_API_KEY" in body["errors"][0]


def test_apply_refuses_an_entry_that_is_not_importable(import_context):
    response = import_context["client"].post(
        "/mcp/import/apply",
        json={"format": "auto", "content": CLAUDE_CONTENT, "names": ["legacy-sse", "inconnue"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == []
    assert sorted(body["skipped"]) == ["inconnue", "legacy-sse"]
    assert len(body["errors"]) == 2


def test_apply_with_conflict_skip_keeps_the_existing_server_untouched(import_context):
    client = import_context["client"]
    secret_id = _create_secret(import_context, "CONTEXT7_API_KEY", CLAUDE_CLEAR_SECRET)
    mapping = {"CONTEXT7_CONTEXT7_API_KEY": secret_id}
    payload = {
        "format": "auto",
        "content": CLAUDE_CONTENT,
        "names": ["context7"],
        "secret_mapping": mapping,
        "on_conflict": "skip",
    }
    first = client.post("/mcp/import/apply", json=payload).json()
    server_id = first["created"][0]["id"]

    second = client.post("/mcp/import/apply", json=payload).json()
    assert second["created"] == []
    assert second["revised"] == []
    assert second["skipped"] == ["context7"]

    detail = client.get(f"/mcp/servers/{server_id}").json()
    assert len(detail["revisions"]) == 1


def test_apply_with_conflict_new_revision_keeps_the_previous_revision_as_a_backup(import_context):
    client = import_context["client"]
    secret_id = _create_secret(import_context, "CONTEXT7_API_KEY", CLAUDE_CLEAR_SECRET)
    mapping = {"CONTEXT7_CONTEXT7_API_KEY": secret_id}
    first = client.post(
        "/mcp/import/apply",
        json={
            "format": "auto",
            "content": CLAUDE_CONTENT,
            "names": ["context7"],
            "secret_mapping": mapping,
            "on_conflict": "skip",
        },
    ).json()
    server_id = first["created"][0]["id"]

    changed = json.loads(CLAUDE_CONTENT)
    changed["mcpServers"]["context7"]["url"] = "https://mcp.context7.com/v2/mcp"
    second = client.post(
        "/mcp/import/apply",
        json={
            "format": "auto",
            "content": json.dumps(changed, ensure_ascii=False),
            "names": ["context7"],
            "secret_mapping": mapping,
            "on_conflict": "new_revision",
        },
    ).json()
    assert second["created"] == []
    assert [server["name"] for server in second["revised"]] == ["context7"]

    detail = client.get(f"/mcp/servers/{server_id}").json()
    numbers = sorted(revision["number"] for revision in detail["revisions"])
    assert numbers == [1, 2]
    assert detail["current_revision"]["number"] == 2
    assert detail["current_revision"]["config"]["http"]["url"] == "https://mcp.context7.com/v2/mcp"
    # L'ancienne révision reste lisible : c'est la sauvegarde.
    previous = next(revision for revision in detail["revisions"] if revision["number"] == 1)
    assert previous["config"]["http"]["url"] == "https://mcp.context7.com/mcp"
    assert previous["superseded_at"] is not None


def test_apply_records_an_audit_event_without_any_value(import_context):
    client = import_context["client"]
    secret_id = _create_secret(import_context, "CONTEXT7_API_KEY", CLAUDE_CLEAR_SECRET)
    client.post(
        "/mcp/import/apply",
        json={
            "format": "auto",
            "content": CLAUDE_CONTENT,
            "names": ["context7", "broken"],
            "secret_mapping": {"CONTEXT7_CONTEXT7_API_KEY": secret_id},
        },
    )
    with import_context["session_factory"]() as db:
        events = db.query(EventModel).filter(EventModel.type == "mcp.import.applied").all()
        assert len(events) == 1
        payload = events[0].payload
        assert payload["format"] == "claude"
        assert payload["created"] == ["context7"]
        assert payload["skipped"] == ["broken"]
        serialized = json.dumps(payload, ensure_ascii=False)
        assert CLAUDE_CLEAR_SECRET not in serialized
        assert secret_id not in serialized or payload.get("secret_mapping") is None


def test_apply_refuses_a_configuration_that_the_creation_rules_reject(import_context):
    content = json.dumps(
        {"mcpServers": {"relative": {"command": "npx", "args": ["-y", "server@1.0.0"]}}}
    )
    response = import_context["client"].post(
        "/mcp/import/apply", json={"format": "claude", "content": content, "names": ["relative"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == []
    assert body["skipped"] == ["relative"]
    assert any("relative_command" in message for message in body["errors"])


def test_apply_refuses_a_mapping_towards_an_unknown_secret(import_context):
    response = import_context["client"].post(
        "/mcp/import/apply",
        json={
            "format": "auto",
            "content": CLAUDE_CONTENT,
            "names": ["context7"],
            "secret_mapping": {"CONTEXT7_CONTEXT7_API_KEY": "secret-inexistant"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == []
    assert body["errors"] and "secret-inexistant" in body["errors"][0]


def test_import_routes_never_echo_the_faulty_line_of_an_unreadable_yaml(import_context):
    """Ni l'aperçu ni l'application ne renvoient la ligne YAML fautive du contenu importé."""

    client = import_context["client"]
    body = {"format": "hermes", "content": HERMES_UNCLOSED_QUOTE}
    preview = client.post("/mcp/import/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["errors"]
    assert HERMES_BROKEN_SECRET not in preview.text
    applied = client.post("/mcp/import/apply", json={**body, "names": ["fuite"]})
    assert applied.status_code == 200, applied.text
    assert applied.json()["errors"]
    assert HERMES_BROKEN_SECRET not in applied.text


def test_apply_refuses_more_names_than_a_preview_can_hold(import_context):
    """La sélection est bornée comme l'aperçu : aucune boucle serveur ouverte sur l'entrée."""

    names = [f"srv-{index:05d}" for index in range(importers.MAX_ENTRIES + 1)]
    response = import_context["client"].post(
        "/mcp/import/apply",
        json={"format": "auto", "content": CLAUDE_CONTENT, "names": names},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == []
    assert body["revised"] == []
    assert body["skipped"] == []
    assert len(body["errors"]) == 1
    assert str(importers.MAX_ENTRIES) in body["errors"][0]


def test_apply_reports_a_repeated_name_only_once(import_context):
    """Un nom répété est traité une seule fois : la réponse ne s'amplifie pas."""

    response = import_context["client"].post(
        "/mcp/import/apply",
        json={"format": "auto", "content": CLAUDE_CONTENT, "names": ["absent"] * 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skipped"] == ["absent"]
    assert len(body["errors"]) == 1


def test_apply_route_is_reserved_to_the_owner(import_context):
    client = import_context["client"]
    session_token, csrf_token = _create_operator(import_context)
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token
    response = client.post(
        "/mcp/import/apply", json={"format": "auto", "content": CLAUDE_CONTENT, "names": ["context7"]}
    )
    assert response.status_code == 403
    _as_owner(import_context)
    with import_context["session_factory"]() as db:
        assert db.query(McpServerRevisionModel).count() == 0
