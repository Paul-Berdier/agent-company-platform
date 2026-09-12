"""Tests des groupes ``secrets``, ``mcp``, ``skills`` et ``projects extensions`` du CLI.

Chaque commande est vérifiée sur la méthode, le chemin, le corps JSON exact envoyé
et le code de sortie, avec un transport ``httpx.MockTransport`` (aucun réseau).
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from acp_cli.cli import ExitCode, main
from acp_cli.config import Settings, save_settings


def invoke(
    tmp_path: Path,
    args: list[str],
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    stdin: str = "",
    sleep=lambda _seconds: None,
):
    stdout = io.StringIO()
    stderr = io.StringIO()
    config = tmp_path / "config.json"
    code = main(
        [*args, "--config", str(config)],
        transport=httpx.MockTransport(handler),
        stdout=stdout,
        stderr=stderr,
        stdin=io.StringIO(stdin),
        environ={},
        password_reader=lambda _prompt: pytest.fail("aucune invite de mot de passe attendue"),
        sleep=sleep,
        browser_open=lambda _url: pytest.fail("aucune ouverture de navigateur attendue"),
    )
    return code, stdout.getvalue(), stderr.getvalue(), config


def authenticated_config(path: Path) -> None:
    settings = Settings(
        api_url="http://127.0.0.1:8000",
        web_url="http://127.0.0.1:5173",
    ).with_session("session-secret", "csrf-secret", principal_id="u-1")
    save_settings(path, settings)


def ok(payload: Any, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(status, json=payload)


class Recorder:
    """Transport simulé : enregistre chaque requête et rejoue les réponses dans l'ordre."""

    def __init__(self, *responses: Callable[[httpx.Request], httpx.Response]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "raw_path": request.url.raw_path.decode(),
                "params": dict(request.url.params),
                "body": body,
                "csrf": request.headers.get("x-csrf-token"),
                "cookie": request.headers.get("cookie"),
            }
        )
        if not self.responses:
            raise AssertionError(f"requête inattendue : {request.method} {request.url}")
        return self.responses.pop(0)(request)

    @property
    def requests(self) -> list[tuple[str, str, Any]]:
        return [(call["method"], call["path"], call["body"]) for call in self.calls]


def never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("aucune requête HTTP ne doit être envoyée")


PROBE_ID = "pr-1"


def probe(status: str, **extra: Any) -> dict[str, Any]:
    return {"id": PROBE_ID, "server_id": "srv-1", "status": status, "transport": "stdio", **extra}


# --- secrets ----------------------------------------------------------------


@pytest.mark.parametrize(
    "args, method, path, params",
    [
        (["secrets", "status"], "GET", "/secrets/status", {}),
        (["secrets", "list"], "GET", "/secrets", {}),
    ],
)
def test_secrets_read_commands(tmp_path, args, method, path, params):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"configured": True, "items": []}))

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["configured"] is True
    assert recorder.requests == [(method, path, None)]
    assert recorder.calls[0]["params"] == params
    assert recorder.calls[0]["cookie"] == "acp_session=session-secret"


@pytest.mark.parametrize(
    "extra_args, expected_scope",
    [
        ([], {"scope_type": "platform", "project_id": None}),
        (["--project", "p-1"], {"scope_type": "project", "project_id": "p-1"}),
    ],
)
def test_secrets_set_reads_value_from_stdin_and_sends_exact_body(tmp_path, extra_args, expected_scope):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "s-1", "name": "API_TOKEN", "key_id": "abc"}, 201))

    code, out, err, _ = invoke(
        tmp_path,
        ["secrets", "set", "API_TOKEN", "--value-stdin", "--description", "Jeton", *extra_args, "--json"],
        recorder,
        stdin="super-secret-value\n",
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["id"] == "s-1"
    assert "super-secret-value" not in out
    assert recorder.requests == [
        (
            "POST",
            "/secrets",
            {
                "name": "API_TOKEN",
                "value": "super-secret-value",
                "description": "Jeton",
                **expected_scope,
            },
        )
    ]
    assert recorder.calls[0]["csrf"] == "csrf-secret"


def test_secrets_set_keeps_inner_newlines_and_strips_one_trailing_newline(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "s-1"}, 201))

    code, _, _, _ = invoke(
        tmp_path,
        ["secrets", "set", "PEM_KEY", "--value-stdin"],
        recorder,
        stdin="line1\r\nline2\r\n",
    )

    assert code == ExitCode.OK
    assert recorder.calls[0]["body"]["value"] == "line1\r\nline2"


@pytest.mark.parametrize(
    "args",
    [
        ["secrets", "set", "API_TOKEN", "super-secret-value"],
        ["secrets", "set", "API_TOKEN", "super-secret-value", "--value-stdin"],
        ["secrets", "set", "API_TOKEN", "--value=super-secret-value"],
        ["secrets", "set", "API_TOKEN", "--value", "super-secret-value"],
        ["secrets", "rotate", "s-1", "super-secret-value"],
        ["secrets", "rotate", "s-1", "--value=super-secret-value"],
    ],
)
def test_secret_values_in_arguments_are_refused_without_echo(tmp_path, args):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], never, stdin="super-secret-value\n")

    assert code == ExitCode.USAGE
    assert out == ""
    assert "super-secret-value" not in err
    error = json.loads(err)["error"]
    assert error["code"] == "usage"
    assert "--value-stdin" in error["message"]


@pytest.mark.parametrize(
    "args, stdin, fragment",
    [
        (["secrets", "set", "API_TOKEN"], "value\n", "--value-stdin"),
        (["secrets", "set", "API_TOKEN", "--value-stdin"], "", "vide"),
        (["secrets", "set", "API_TOKEN", "--value-stdin"], "\n", "vide"),
        (["secrets", "set", "api_token", "--value-stdin"], "value\n", "nom"),
        (["secrets", "rotate", "s-1"], "value\n", "--value-stdin"),
    ],
)
def test_secret_commands_fail_fast_before_any_request(tmp_path, args, stdin, fragment):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], never, stdin=stdin)

    assert code == ExitCode.USAGE
    assert out == ""
    assert fragment in json.loads(err)["error"]["message"]


def test_secrets_rotate_and_revoke(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "s-1", "key_id": "new"}), ok({"id": "s-1", "revoked_at": "2026-09-12T00:00:00Z"}))

    code, out, err, _ = invoke(
        tmp_path,
        ["secrets", "rotate", "s/1", "--value-stdin", "--json"],
        recorder,
        stdin="rotated-secret\n",
    )
    assert code == ExitCode.OK
    assert err == ""
    assert "rotated-secret" not in out

    code, out, err, _ = invoke(tmp_path, ["secrets", "revoke", "s/1", "--json"], recorder)
    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["revoked_at"]

    assert recorder.requests == [
        ("POST", "/secrets/s/1/rotate", {"value": "rotated-secret"}),
        ("DELETE", "/secrets/s/1", None),
    ]
    assert recorder.calls[0]["raw_path"] == "/secrets/s%2F1/rotate"
    assert recorder.calls[1]["raw_path"] == "/secrets/s%2F1"
    assert recorder.calls[1]["csrf"] == "csrf-secret"


# --- mcp : ajout, révision -----------------------------------------------------


def test_mcp_add_http_sends_literal_headers_and_secret_references(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "srv-1", "name": "context7", "status": "draft"}, 201))

    code, out, err, _ = invoke(
        tmp_path,
        [
            "mcp",
            "add",
            "context7",
            "--url",
            "https://mcp.context7.com/mcp",
            "--header",
            "CONTEXT7_API_KEY=@s-1",
            "--header",
            "X-Client=acp=cli",
            "--timeout",
            "30",
            "--display",
            "Context7",
            "--description",
            "Docs à jour",
            "--json",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["id"] == "srv-1"
    assert recorder.requests == [
        (
            "POST",
            "/mcp/servers",
            {
                "name": "context7",
                "display_name": "Context7",
                "description": "Docs à jour",
                "config": {
                    "transport": "http",
                    "http": {
                        "url": "https://mcp.context7.com/mcp",
                        "headers": {"X-Client": "acp=cli"},
                        "header_secrets": {"CONTEXT7_API_KEY": {"secret_id": "s-1"}},
                        "timeout_seconds": 30,
                    },
                },
                "target_worker_id": None,
                "note": "",
            },
        )
    ]
    assert recorder.calls[0]["csrf"] == "csrf-secret"


def test_mcp_add_stdio_sends_env_references_runner_and_cwd(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "srv-2", "name": "filesystem", "status": "draft"}, 201))

    code, _, err, _ = invoke(
        tmp_path,
        [
            "mcp",
            "add",
            "filesystem",
            "--command",
            "/usr/bin/npx",
            "--arg",
            "-y",
            "--arg",
            "@modelcontextprotocol/server-filesystem@2025.8.21",
            "--arg",
            "/srv/data",
            "--env",
            "NODE_ENV=production",
            "--env",
            "FS_TOKEN=@s-9",
            "--cwd",
            "/srv",
            "--runner",
            "w-1",
            "--note",
            "runner Linux",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.requests == [
        (
            "POST",
            "/mcp/servers",
            {
                "name": "filesystem",
                "display_name": "filesystem",
                "description": "",
                "config": {
                    "transport": "stdio",
                    "stdio": {
                        "command": "/usr/bin/npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem@2025.8.21", "/srv/data"],
                        "env": {"NODE_ENV": "production"},
                        "env_secrets": {"FS_TOKEN": {"secret_id": "s-9"}},
                        "cwd": "/srv",
                    },
                },
                "target_worker_id": "w-1",
                "note": "runner Linux",
            },
        )
    ]


@pytest.mark.parametrize(
    "extra_args, fragment",
    [
        ([], "--url"),
        (["--url", "https://a.example/mcp", "--command", "/bin/x"], "--url"),
        (["--url", "https://a.example/mcp", "--arg", "x"], "--arg"),
        (["--url", "https://a.example/mcp", "--runner", "w-1"], "--runner"),
        (["--url", "ftp://a.example/mcp"], "--url"),
        (["--command", "/bin/x", "--header", "A=b"], "--header"),
        (["--command", "npx"], "absolu"),
        (["--url", "https://a.example/mcp", "--header", "NoEquals"], "K=V"),
        (["--url", "https://a.example/mcp", "--header", "=v"], "K=V"),
        (["--url", "https://a.example/mcp", "--header", "A=@"], "vide"),
        (["--url", "https://a.example/mcp", "--header", "A=1", "--header", "A=2"], "deux fois"),
        (["--url", "https://a.example/mcp", "--timeout", "0"], "--timeout"),
        (["--url", "https://a.example/mcp", "--timeout", "121"], "--timeout"),
    ],
)
def test_mcp_add_rejects_inconsistent_options_before_any_request(tmp_path, extra_args, fragment):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, ["mcp", "add", "srv", *extra_args, "--json"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert fragment in json.loads(err)["error"]["message"]


def test_mcp_add_rejects_non_slug_name_before_any_request(tmp_path):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, ["mcp", "add", "Bad Name", "--url", "https://a.example/mcp"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "slug" in err


def test_mcp_update_creates_a_revision_with_a_complete_config(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "srv-1", "current_revision_number": 2}, 201))

    code, out, err, _ = invoke(
        tmp_path,
        [
            "mcp",
            "update",
            "srv/1",
            "--url",
            "https://mcp.example/v2",
            "--header",
            "Authorization=@s-1",
            "--note",
            "nouvel endpoint",
            "--json",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["current_revision_number"] == 2
    assert recorder.requests == [
        (
            "POST",
            "/mcp/servers/srv/1/revisions",
            {
                "config": {
                    "transport": "http",
                    "http": {
                        "url": "https://mcp.example/v2",
                        "headers": {},
                        "header_secrets": {"Authorization": {"secret_id": "s-1"}},
                    },
                },
                "target_worker_id": None,
                "note": "nouvel endpoint",
            },
        )
    ]
    assert recorder.calls[0]["raw_path"] == "/mcp/servers/srv%2F1/revisions"


# --- mcp : lecture ---------------------------------------------------------------


@pytest.mark.parametrize(
    "args, path, params",
    [
        (["mcp", "catalog"], "/mcp/catalog", {}),
        (["mcp", "list"], "/mcp/servers", {}),
        (["mcp", "list", "--status", "active"], "/mcp/servers", {"status": "active"}),
        (["mcp", "show", "srv-1"], "/mcp/servers/srv-1", {}),
        (["mcp", "probes", "list"], "/mcp/probes", {}),
        (["mcp", "probes", "list", "--status", "queued"], "/mcp/probes", {"status": "queued"}),
        (["mcp", "probes", "show", "pr-1"], "/mcp/probes/pr-1", {}),
        (["mcp", "bindings"], "/mcp/bindings", {}),
        (["mcp", "bindings", "--project", "p-1", "--server", "srv-1"], "/mcp/bindings", {"project_id": "p-1", "server_id": "srv-1"}),
        (["mcp", "export", "--format", "hermes"], "/mcp/export", {"format": "hermes"}),
        (["mcp", "export", "--format", "codex", "--project", "p-1"], "/mcp/export", {"format": "codex", "project_id": "p-1"}),
        (["skills", "search", "docs à jour"], "/skills/search", {"q": "docs à jour"}),
        (["skills", "catalog"], "/skills/catalog", {}),
        (["skills", "list"], "/skills", {}),
        (["skills", "show", "sk-1"], "/skills/sk-1", {}),
        (["skills", "files", "sk-1", "--revision", "3"], "/skills/sk-1/revisions/3/files", {}),
        (["skills", "bindings"], "/skills/bindings", {}),
        (["skills", "bindings", "--project", "p-1", "--skill", "sk-1"], "/skills/bindings", {"project_id": "p-1", "skill_id": "sk-1"}),
        (["projects", "extensions", "p-1"], "/projects/p-1/extensions", {}),
    ],
)
def test_read_commands_send_get_with_expected_query(tmp_path, args, path, params):
    authenticated_config(tmp_path / "config.json")
    payload = {"echo": True, "content": "mcp_servers: {}\n"}
    recorder = Recorder(ok(payload))

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out) == payload
    assert recorder.requests == [("GET", path, None)]
    assert recorder.calls[0]["params"] == params
    assert recorder.calls[0]["csrf"] is None


def test_mcp_export_format_is_validated_locally(tmp_path):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, ["mcp", "export", "--format", "yaml"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "hermes" in err


def test_mcp_export_text_mode_prints_content_verbatim_and_notes_on_stderr(tmp_path):
    authenticated_config(tmp_path / "config.json")
    export = {
        "format": "hermes",
        "project_id": None,
        "content": "mcp_servers:\n  context7:\n    headers:\n      CONTEXT7_API_KEY: ${ACP_SECRET_CONTEXT7_API_KEY}\n",
        "placeholders": ["ACP_SECRET_CONTEXT7_API_KEY"],
        "partial_compatibility": ["la restriction par projet repose sur tools.include"],
        "apply_notes": ["Définir les variables ACP_SECRET_* dans ~/.hermes/.env"],
    }
    recorder = Recorder(ok(export))

    code, out, err, _ = invoke(tmp_path, ["mcp", "export", "--format", "hermes"], recorder)

    assert code == ExitCode.OK
    assert out == export["content"]
    assert "ACP_SECRET_CONTEXT7_API_KEY" in err
    assert "tools.include" in err
    assert "~/.hermes/.env" in err


def test_mcp_probes_list_by_server_filters_status_locally(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(
        ok([probe("queued"), {**probe("failed"), "id": "pr-2"}, {**probe("queued"), "id": "pr-3"}])
    )

    code, out, err, _ = invoke(
        tmp_path,
        ["mcp", "probes", "list", "--server", "srv-1", "--status", "queued", "--json"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert [item["id"] for item in json.loads(out)] == ["pr-1", "pr-3"]
    assert recorder.requests == [("GET", "/mcp/servers/srv-1/probes", None)]
    assert recorder.calls[0]["params"] == {}


def test_mcp_tools_extracts_discovered_tools_from_the_current_revision(tmp_path):
    authenticated_config(tmp_path / "config.json")
    detail = {
        "id": "srv-1",
        "current_revision_number": 2,
        "discovery_current": True,
        "current_revision": {
            "number": 2,
            "discovery": {
                "protocol_version": "2025-06-18",
                "tools": [
                    {"name": "resolve", "description": "Résout", "input_schema": {"type": "object"}},
                    {"name": "query", "description": "", "input_schema": {}},
                ],
            },
        },
    }
    recorder = Recorder(ok(detail))

    code, out, err, _ = invoke(tmp_path, ["mcp", "tools", "srv-1", "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out) == {
        "server_id": "srv-1",
        "revision_number": 2,
        "discovery_current": True,
        "tools": detail["current_revision"]["discovery"]["tools"],
    }
    assert recorder.requests == [("GET", "/mcp/servers/srv-1", None)]


def test_mcp_tools_without_discovery_is_explicit_not_a_false_success(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "srv-1", "current_revision_number": None, "current_revision": None, "discovery_current": False}))

    code, out, err, _ = invoke(tmp_path, ["mcp", "tools", "srv-1", "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out) == {
        "server_id": "srv-1",
        "revision_number": None,
        "discovery_current": False,
        "tools": [],
    }


# --- mcp : mutations -------------------------------------------------------------


@pytest.mark.parametrize(
    "args, method, path, body",
    [
        (["mcp", "activate", "srv-1"], "POST", "/mcp/servers/srv-1/activate", None),
        (["mcp", "disable", "srv-1"], "POST", "/mcp/servers/srv-1/disable", None),
        (
            ["mcp", "revoke", "srv-1", "--reason", "clé compromise"],
            "POST",
            "/mcp/servers/srv-1/revoke",
            {"reason": "clé compromise"},
        ),
        (
            ["mcp", "rollback", "srv-1", "--revision", "2"],
            "POST",
            "/mcp/servers/srv-1/rollback",
            {"revision_number": 2, "note": ""},
        ),
        (
            ["mcp", "rollback", "srv-1", "--revision", "2", "--note", "retour"],
            "POST",
            "/mcp/servers/srv-1/rollback",
            {"revision_number": 2, "note": "retour"},
        ),
        (
            ["mcp", "bind", "srv-1", "--project", "p-1", "--tool", "resolve", "--tool", "query", "--tool", "resolve"],
            "POST",
            "/mcp/servers/srv-1/bindings",
            {"project_id": "p-1", "allowed_tools": ["resolve", "query"]},
        ),
        (["mcp", "unbind", "b-1"], "DELETE", "/mcp/bindings/b-1", None),
        (
            ["mcp", "probes", "approve", "pr-1"],
            "POST",
            "/mcp/probes/pr-1/decision",
            {"decision": "approved", "comment": ""},
        ),
        (
            ["mcp", "probes", "reject", "pr-1", "--comment", "commande inconnue"],
            "POST",
            "/mcp/probes/pr-1/decision",
            {"decision": "rejected", "comment": "commande inconnue"},
        ),
        (["skills", "activate", "sk-1"], "POST", "/skills/sk-1/activate", None),
        (["skills", "disable", "sk-1"], "POST", "/skills/sk-1/disable", None),
        (
            ["skills", "revoke", "sk-1", "--reason", "script dangereux"],
            "POST",
            "/skills/sk-1/revoke",
            {"reason": "script dangereux"},
        ),
        (
            ["skills", "rollback", "sk-1", "--revision", "1"],
            "POST",
            "/skills/sk-1/rollback",
            {"revision_number": 1, "note": ""},
        ),
        (
            ["skills", "approve", "sk-1", "--revision", "2"],
            "POST",
            "/skills/sk-1/revisions/2/approve",
            {"comment": ""},
        ),
        (
            ["skills", "approve", "sk-1", "--revision", "2", "--comment", "relu"],
            "POST",
            "/skills/sk-1/revisions/2/approve",
            {"comment": "relu"},
        ),
        (["skills", "bind", "sk-1", "--project", "p-1"], "POST", "/skills/sk-1/bindings", {"project_id": "p-1"}),
        (["skills", "unbind", "sb-1"], "DELETE", "/skills/bindings/sb-1", None),
    ],
)
def test_mutations_send_exact_request_with_csrf(tmp_path, args, method, path, body):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "x-1", "status": "active"}))

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["id"] == "x-1"
    assert recorder.requests == [(method, path, body)]
    assert recorder.calls[0]["csrf"] == "csrf-secret"


@pytest.mark.parametrize(
    "args, fragment",
    [
        (["mcp", "bind", "srv-1", "--project", "p-1"], "--tool"),
        (["mcp", "bind", "srv-1", "--project", "p-1", "--tool", " "], "--tool"),
        (["mcp", "revoke", "srv-1"], "--reason"),
        (["mcp", "revoke", "srv-1", "--reason", " "], "--reason"),
        (["mcp", "rollback", "srv-1"], "--revision"),
        (["mcp", "rollback", "srv-1", "--revision", "0"], "--revision"),
        (["skills", "revoke", "sk-1"], "--reason"),
        (["skills", "approve", "sk-1"], "--revision"),
        (["skills", "rollback", "sk-1", "--revision", "x"], "--revision"),
        (["skills", "bind", "sk-1"], "--project"),
        (["skills", "files", "sk-1", "--revision", "0"], "--revision"),
    ],
)
def test_mutation_options_are_validated_before_any_request(tmp_path, args, fragment):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert fragment in json.loads(err)["error"]["message"]


# --- mcp test ---------------------------------------------------------------------


def test_mcp_test_http_probe_succeeded_exits_zero(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({**probe("succeeded"), "transport": "http", "result": {"tools": []}}))

    code, out, err, _ = invoke(tmp_path, ["mcp", "test", "srv-1", "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["status"] == "succeeded"
    assert recorder.requests == [("POST", "/mcp/servers/srv-1/probe", None)]
    assert recorder.calls[0]["csrf"] == "csrf-secret"


def test_mcp_test_http_probe_failed_exits_remote_and_still_shows_the_probe(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({**probe("failed"), "transport": "http", "error": "host_blocked"}))

    code, out, err, _ = invoke(tmp_path, ["mcp", "test", "srv-1", "--json"], recorder)

    assert code == ExitCode.REMOTE
    assert json.loads(out)["status"] == "failed"
    error = json.loads(err)["error"]
    assert error["code"] == "probe_failed"
    assert "failed" in error["message"]
    assert recorder.requests == [("POST", "/mcp/servers/srv-1/probe", None)]


def test_mcp_test_stdio_without_wait_reports_pending_approval_and_exits_zero(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok(probe("pending_approval")))

    code, out, err, _ = invoke(
        tmp_path,
        ["mcp", "test", "srv-1"],
        recorder,
        sleep=lambda _seconds: pytest.fail("sans --wait, aucune attente"),
    )

    assert code == ExitCode.OK
    assert json.loads(out)["status"] == "pending_approval"
    assert "acp mcp probes approve pr-1" in err
    assert recorder.requests == [("POST", "/mcp/servers/srv-1/probe", None)]


def test_mcp_test_wait_polls_the_probe_until_a_terminal_state(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(
        ok(probe("pending_approval")),
        ok(probe("queued")),
        ok(probe("queued")),
        ok(probe("claimed", worker_id="w-1")),
        ok(probe("succeeded", result={"tools": [{"name": "read_file"}]})),
    )
    sleeps: list[float] = []

    code, out, err, _ = invoke(
        tmp_path,
        ["mcp", "test", "srv-1", "--wait", "--interval", "0.5", "--json"],
        recorder,
        sleep=sleeps.append,
    )

    assert code == ExitCode.OK
    assert err == ""
    lines = [json.loads(line) for line in out.splitlines()]
    assert [line["status"] for line in lines] == ["pending_approval", "queued", "claimed", "succeeded"]
    assert sleeps == [0.5, 0.5, 0.5, 0.5]
    assert recorder.requests == [
        ("POST", "/mcp/servers/srv-1/probe", None),
        ("GET", "/mcp/probes/pr-1", None),
        ("GET", "/mcp/probes/pr-1", None),
        ("GET", "/mcp/probes/pr-1", None),
        ("GET", "/mcp/probes/pr-1", None),
    ]


@pytest.mark.parametrize("final_status", ["failed", "rejected", "expired", "invalidated", "cancelled"])
def test_mcp_test_wait_exits_remote_when_the_probe_does_not_succeed(tmp_path, final_status):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok(probe("queued")), ok(probe(final_status)))

    code, out, err, _ = invoke(tmp_path, ["mcp", "test", "srv-1", "--wait", "--json"], recorder)

    assert code == ExitCode.REMOTE
    assert [json.loads(line)["status"] for line in out.splitlines()] == ["queued", final_status]
    error = json.loads(err)["error"]
    assert error["code"] == "probe_failed"
    assert final_status in error["message"]
    assert len(recorder.requests) == 2


def test_mcp_test_wait_interrupt_leaves_the_probe_running_without_cancellation(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok(probe("pending_approval")), ok(probe("queued")))
    polls = 0

    def interrupt(_seconds: float) -> None:
        nonlocal polls
        polls += 1
        if polls == 2:
            raise KeyboardInterrupt

    code, out, err, _ = invoke(tmp_path, ["mcp", "test", "srv-1", "--wait"], recorder, sleep=interrupt)

    assert code == ExitCode.INTERRUPTED
    assert "pr-1" in err
    assert "continue côté serveur" in err
    assert "aucune annulation" in err
    assert "acp mcp probes show pr-1" in err
    assert recorder.requests == [
        ("POST", "/mcp/servers/srv-1/probe", None),
        ("GET", "/mcp/probes/pr-1", None),
    ]
    assert "pending_approval" in out and "queued" in out


def test_mcp_test_wait_timeout_is_explicit(tmp_path, monkeypatch):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok(probe("queued")), ok(probe("queued")))
    clock = iter([0.0, 5.0, 100.0])
    monkeypatch.setattr("acp_cli.cli.time.monotonic", lambda: next(clock, 200.0))

    code, out, err, _ = invoke(
        tmp_path,
        ["mcp", "test", "srv-1", "--wait", "--timeout", "8", "--json"],
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert [json.loads(line)["status"] for line in out.splitlines()] == ["queued"]
    error = json.loads(err)["error"]
    assert error["code"] == "client"
    assert "continue côté serveur" in error["message"]
    assert recorder.requests == [
        ("POST", "/mcp/servers/srv-1/probe", None),
        ("GET", "/mcp/probes/pr-1", None),
    ]


@pytest.mark.parametrize(
    "args, fragment",
    [
        (["mcp", "test", "srv-1", "--wait", "--interval", "0"], "--interval"),
        (["mcp", "test", "srv-1", "--wait", "--timeout", "-1"], "--timeout"),
    ],
)
def test_mcp_test_wait_options_are_validated(tmp_path, args, fragment):
    authenticated_config(tmp_path / "config.json")

    code, _, err, _ = invoke(tmp_path, args, never)

    assert code == ExitCode.USAGE
    assert fragment in err


def test_mcp_test_rejects_a_malformed_probe_response(tmp_path):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, ["mcp", "test", "srv-1", "--json"], Recorder(ok({"status": "succeeded"})))

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "client"


# --- skills : lecture des fichiers ------------------------------------------------------


def test_skills_files_uses_the_current_revision_when_not_given(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(
        ok({"id": "sk-1", "current_revision_number": 4}),
        ok([{"path": "SKILL.md", "size": 10, "sha256": "a", "text": True}]),
    )

    code, out, err, _ = invoke(tmp_path, ["skills", "files", "sk/1", "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)[0]["path"] == "SKILL.md"
    assert recorder.requests == [("GET", "/skills/sk/1", None), ("GET", "/skills/sk/1/revisions/4/files", None)]
    assert recorder.calls[1]["raw_path"] == "/skills/sk%2F1/revisions/4/files"


def test_skills_files_without_current_revision_is_an_explicit_error(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "sk-1", "current_revision_number": None}))

    code, out, err, _ = invoke(tmp_path, ["skills", "files", "sk-1", "--json"], recorder)

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "no_current_revision"
    assert len(recorder.requests) == 1


def test_skills_cat_prints_text_exactly_as_returned(tmp_path):
    authenticated_config(tmp_path / "config.json")
    content = "---\nname: demo\n---\n<script>alert(1)</script>\n# Titre sans saut final"
    recorder = Recorder(
        ok({"path": "docs/guide.md", "text": True, "content": content, "truncated": False, "size": 60, "sha256": "b"})
    )

    code, out, err, _ = invoke(
        tmp_path,
        ["skills", "cat", "sk-1", "docs\\guide.md", "--revision", "2"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert out == content
    assert recorder.requests == [("GET", "/skills/sk-1/revisions/2/files/docs/guide.md", None)]
    assert recorder.calls[0]["raw_path"] == "/skills/sk-1/revisions/2/files/docs/guide.md"


def test_skills_cat_json_returns_the_file_object(tmp_path):
    authenticated_config(tmp_path / "config.json")
    payload = {"path": "SKILL.md", "text": True, "content": "x", "truncated": True, "size": 300000, "sha256": "c"}
    recorder = Recorder(ok({"id": "sk-1", "current_revision_number": 1}), ok(payload))

    code, out, err, _ = invoke(tmp_path, ["skills", "cat", "sk-1", "SKILL.md", "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out) == payload
    assert recorder.requests[1] == ("GET", "/skills/sk-1/revisions/1/files/SKILL.md", None)


def test_skills_cat_binary_file_is_refused_explicitly(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(
        ok({"path": "assets/logo.png", "text": False, "content": None, "truncated": False, "size": 12, "sha256": "d"})
    )

    code, out, err, _ = invoke(
        tmp_path,
        ["skills", "cat", "sk-1", "assets/logo.png", "--revision", "1", "--json"],
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "binary_file"
    assert "assets/logo.png" in error["message"]


# --- skills : installation -------------------------------------------------------------


def test_skills_install_directory_source(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "sk-1", "status": "draft"}, 201))

    code, out, err, _ = invoke(
        tmp_path,
        ["skills", "install", "dir:/srv/skills/demo", "--name", "demo", "--json"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["id"] == "sk-1"
    assert recorder.requests == [
        (
            "POST",
            "/skills/import",
            {"source": {"kind": "directory", "path": "/srv/skills/demo"}, "name": "demo", "note": ""},
        )
    ]
    assert recorder.calls[0]["csrf"] == "csrf-secret"


def test_skills_install_windows_directory_keeps_the_drive_letter(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "sk-1"}, 201))

    code, _, err, _ = invoke(tmp_path, ["skills", "install", "dir:C:\\skills\\demo"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.calls[0]["body"]["source"] == {"kind": "directory", "path": "C:\\skills\\demo"}


def test_skills_install_archive_reads_the_local_file_and_sends_base64(tmp_path):
    authenticated_config(tmp_path / "config.json")
    archive = tmp_path / "demo.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("SKILL.md", "---\nname: demo\n---\n")
    recorder = Recorder(ok({"id": "sk-2"}, 201))

    code, _, err, _ = invoke(tmp_path, ["skills", "install", f"archive:{archive}", "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.requests == [
        (
            "POST",
            "/skills/import",
            {
                "source": {
                    "kind": "archive",
                    "filename": "demo.zip",
                    "content_base64": base64.b64encode(archive.read_bytes()).decode("ascii"),
                },
                "name": None,
                "note": "",
            },
        )
    ]


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "github:anthropics/skills@0123456789abcdef0123456789ABCDEF01234567",
            {"kind": "github", "repository": "anthropics/skills", "ref": "0123456789abcdef0123456789abcdef01234567", "path": ""},
        ),
        (
            "github:anthropics/skills@0123456789abcdef0123456789abcdef01234567:skills/pdf",
            {"kind": "github", "repository": "anthropics/skills", "ref": "0123456789abcdef0123456789abcdef01234567", "path": "skills/pdf"},
        ),
    ],
)
def test_skills_install_github_source_requires_a_pinned_sha(tmp_path, source, expected):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "sk-3"}, 201))

    code, _, err, _ = invoke(tmp_path, ["skills", "install", source, "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.calls[0]["body"] == {"source": expected, "name": None, "note": ""}


def test_skills_install_skill_md_reads_the_file_and_sends_a_manual_source(tmp_path):
    authenticated_config(tmp_path / "config.json")
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: démo\ndescription: Test\n---\n# Démo\n", encoding="utf-8")
    recorder = Recorder(ok({"id": "sk-4"}, 201))

    code, _, err, _ = invoke(
        tmp_path,
        ["skills", "install", f"skill-md:{skill_md}", "--name", "demo", "--note", "import local", "--json"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.requests == [
        (
            "POST",
            "/skills/import",
            {
                "source": {
                    "kind": "manual",
                    "files": [{"path": "SKILL.md", "content": "---\nname: démo\ndescription: Test\n---\n# Démo\n"}],
                },
                "name": "demo",
                "note": "import local",
            },
        )
    ]


def test_skills_update_sends_a_revision_with_the_parsed_source(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "sk-1", "current_revision_number": 2}, 201))

    code, _, err, _ = invoke(
        tmp_path,
        ["skills", "update", "sk-1", "github:openai/skills@abcdefabcdefabcdefabcdefabcdefabcdefabcd:pack", "--note", "v2"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.requests == [
        (
            "POST",
            "/skills/sk-1/revisions",
            {
                "source": {
                    "kind": "github",
                    "repository": "openai/skills",
                    "ref": "abcdefabcdefabcdefabcdefabcdefabcdefabcd",
                    "path": "pack",
                },
                "note": "v2",
            },
        )
    ]


@pytest.mark.parametrize(
    "source, fragment",
    [
        ("example", "dir:"),
        ("ftp:/x", "dir:"),
        ("dir:", "vide"),
        ("dir:relative/path", "absolu"),
        ("github:anthropics/skills", "@"),
        ("github:anthropics/skills@main", "40"),
        ("github:anthropics@0123456789abcdef0123456789abcdef01234567", "owner/repo"),
        ("archive:{tmp}/missing.zip", "introuvable"),
        ("skill-md:{tmp}/missing/SKILL.md", "introuvable"),
        ("archive:{tmp}", "fichier régulier"),
        ("skill-md:{tmp}", "fichier régulier"),
    ],
)
def test_skills_install_rejects_invalid_sources_before_any_request(tmp_path, source, fragment):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(
        tmp_path,
        ["skills", "install", source.replace("{tmp}", str(tmp_path)), "--json"],
        never,
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert fragment in json.loads(err)["error"]["message"]


def test_skills_install_archive_over_25_mib_is_refused_locally(tmp_path, monkeypatch):
    authenticated_config(tmp_path / "config.json")
    archive = tmp_path / "huge.zip"
    archive.write_bytes(b"PK")
    real_stat = Path.stat

    class FakeStat:
        st_size = 25 * 1024 * 1024 + 1
        st_mode = 0o100644

    monkeypatch.setattr(Path, "stat", lambda self, **kwargs: FakeStat() if self == archive else real_stat(self, **kwargs))

    code, out, err, _ = invoke(tmp_path, ["skills", "install", f"archive:{archive}", "--json"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "25 MiB" in json.loads(err)["error"]["message"]


@pytest.mark.parametrize(
    "prefix, filename, attribute",
    [("archive", "pack.zip", "read_bytes"), ("skill-md", "SKILL.md", "read_text")],
)
def test_skills_install_reports_unreadable_local_source_as_usage_error(
    tmp_path, monkeypatch, prefix, filename, attribute
):
    """Un fichier illisible doit produire une erreur ``USAGE``, jamais une trace Python."""

    authenticated_config(tmp_path / "config.json")
    source = tmp_path / filename
    source.write_bytes(b"PK\x03\x04")
    original = getattr(Path, attribute)

    def denied(self, *args, **kwargs):
        if self == source:
            raise PermissionError(13, "Permission denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, attribute, denied)

    code, out, err, _ = invoke(tmp_path, ["skills", "install", f"{prefix}:{source}", "--json"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "lecture impossible" in json.loads(err)["error"]["message"]


def test_skills_install_skill_md_must_be_utf8(tmp_path):
    authenticated_config(tmp_path / "config.json")
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_bytes(b"---\nname: d\xe9mo\n---\n")

    code, out, err, _ = invoke(tmp_path, ["skills", "install", f"skill-md:{skill_md}", "--json"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "UTF-8" in json.loads(err)["error"]["message"]


# --- erreurs API, non supporté, complétion --------------------------------------------------


@pytest.mark.parametrize(
    "args, stdin",
    [
        (["secrets", "set", "API_TOKEN", "--value-stdin"], "value\n"),
        (["mcp", "add", "srv", "--url", "https://a.example/mcp"], ""),
        (["mcp", "test", "srv-1", "--wait"], ""),
        (["skills", "install", "dir:/srv/skills/demo"], ""),
        (["projects", "extensions", "p-1"], ""),
    ],
)
@pytest.mark.parametrize(
    "status, expected",
    [(401, ExitCode.AUTH), (403, ExitCode.AUTH), (409, ExitCode.REMOTE), (422, ExitCode.REMOTE), (503, ExitCode.REMOTE)],
)
def test_api_errors_map_to_auth_and_remote_exit_codes(tmp_path, args, stdin, status, expected):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"detail": [{"msg": "refusé", "input": "value"}]}, status))

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], recorder, stdin=stdin)

    assert code == expected
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "api"
    assert error["status"] == status
    assert "value" not in error["message"].replace("refusé", "")
    assert len(recorder.requests) == 1


def test_network_failure_keeps_the_dedicated_exit_code(tmp_path):
    authenticated_config(tmp_path / "config.json")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("internal detail", request=request)

    code, out, err, _ = invoke(tmp_path, ["mcp", "list", "--json"], handler)

    assert code == ExitCode.NETWORK
    assert out == ""
    assert json.loads(err)["error"]["code"] == "network"


@pytest.mark.parametrize(
    "args",
    [
        ["mcp", "import", "config.yaml"],
        ["automations", "list"],
    ],
)
def test_import_and_automations_remain_honestly_unsupported(tmp_path, args):
    code, out, err, _ = invoke(tmp_path, [*args, "--json"], never)

    assert code == ExitCode.UNSUPPORTED
    assert out == ""
    payload = json.loads(err)["error"]
    assert payload["code"] == "unsupported"
    assert "pas encore raccordé" in payload["message"]


@pytest.mark.parametrize("shell", ["bash", "zsh", "powershell"])
def test_completion_script_lists_new_groups_and_their_subcommands(tmp_path, shell):
    code, out, err, _ = invoke(tmp_path, ["completion", shell], never)

    assert code == ExitCode.OK
    assert err == ""
    for group in ("secrets", "mcp", "skills", "projects", "automations"):
        assert group in out
    for subcommand in ("rotate", "probes", "rollback", "extensions", "install", "unbind", "catalog", "import"):
        assert subcommand in out


def test_unknown_option_values_are_masked_in_usage_errors(tmp_path):
    code, out, err, _ = invoke(tmp_path, ["secrets", "set", "API_TOKEN", "--valu=super-secret-value", "--json"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "super-secret-value" not in err


# --- compléments : transports, valeurs en tiret, avis machine ------------------------


def test_mcp_add_stdio_without_cwd_omits_the_key(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "srv-5"}, 201))

    code, _, err, _ = invoke(
        tmp_path,
        ["mcp", "add", "solo", "--command", "/usr/local/bin/mcp-solo", "--timeout", "45"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.calls[0]["body"]["config"] == {
        "transport": "stdio",
        "stdio": {
            "command": "/usr/local/bin/mcp-solo",
            "args": [],
            "env": {},
            "env_secrets": {},
            "timeout_seconds": 45,
        },
    }


def test_mcp_update_can_switch_to_a_stdio_transport(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "srv-1", "current_revision_number": 3}, 201))

    code, _, err, _ = invoke(
        tmp_path,
        [
            "mcp",
            "update",
            "srv-1",
            "--command",
            "/usr/bin/npx",
            "--env",
            "FS_TOKEN=@s-9",
            "--runner",
            "w-2",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.requests == [
        (
            "POST",
            "/mcp/servers/srv-1/revisions",
            {
                "config": {
                    "transport": "stdio",
                    "stdio": {
                        "command": "/usr/bin/npx",
                        "args": [],
                        "env": {},
                        "env_secrets": {"FS_TOKEN": {"secret_id": "s-9"}},
                    },
                },
                "target_worker_id": "w-2",
                "note": "",
            },
        )
    ]


@pytest.mark.parametrize(
    "extra_args, fragment",
    [
        (["--env", "K=V"], "--env"),
        (["--cwd", "/srv"], "--cwd"),
    ],
)
def test_mcp_add_http_refuses_stdio_only_options(tmp_path, extra_args, fragment):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(
        tmp_path,
        ["mcp", "add", "srv", "--url", "https://a.example/mcp", *extra_args, "--json"],
        never,
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert fragment in json.loads(err)["error"]["message"]


def test_mcp_add_passes_a_dash_value_verbatim_even_when_it_looks_global(tmp_path):
    """`--arg --json` est un argument du programme MCP, jamais une option du CLI."""

    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"id": "srv-6"}, 201))

    code, out, err, _ = invoke(
        tmp_path,
        ["mcp", "add", "srv", "--command", "/usr/bin/tool", "--arg", "--json", "--arg", "-y"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.calls[0]["body"]["config"]["stdio"]["args"] == ["--json", "-y"]
    # `--json` a été consommé comme valeur : la sortie reste au format lisible.
    assert out.startswith("{\n")


def test_mcp_probes_list_by_server_without_status_returns_the_api_payload(tmp_path):
    authenticated_config(tmp_path / "config.json")
    payload = {"items": [probe("queued")], "next_cursor": None}
    recorder = Recorder(ok(payload))

    code, out, err, _ = invoke(tmp_path, ["mcp", "probes", "list", "--server", "srv-1", "--json"], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out) == payload
    assert recorder.requests == [("GET", "/mcp/servers/srv-1/probes", None)]


def test_mcp_test_refuses_an_unknown_probe_state_instead_of_polling_forever(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok(probe("en-cours-de-quelque-chose")))

    code, out, err, _ = invoke(
        tmp_path,
        ["mcp", "test", "srv-1", "--wait", "--json"],
        recorder,
        sleep=lambda _seconds: pytest.fail("un état inconnu ne doit pas déclencher d'attente"),
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "client"
    assert len(recorder.requests) == 1


def test_mcp_test_json_mode_keeps_stderr_machine_readable(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok(probe("pending_approval")))

    code, out, err, _ = invoke(tmp_path, ["mcp", "test", "srv-1", "--json"], recorder)

    assert code == ExitCode.OK
    assert json.loads(out)["status"] == "pending_approval"
    notice = json.loads(err)["notice"]
    assert notice["code"] == "probe_pending_approval"
    assert "acp mcp probes approve pr-1" in notice["message"]


def test_mcp_test_wait_stops_immediately_on_an_already_terminal_probe(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({**probe("succeeded"), "transport": "http"}))

    code, out, err, _ = invoke(
        tmp_path,
        ["mcp", "test", "srv-1", "--wait", "--json"],
        recorder,
        sleep=lambda _seconds: pytest.fail("un état terminal n'appelle aucune attente"),
    )

    assert code == ExitCode.OK
    assert err == ""
    assert [json.loads(line)["status"] for line in out.splitlines()] == ["succeeded"]
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "args, stdin, fragment",
    [
        (["secrets", "set", "API_TOKEN", "--value-stdin", "--project", " "], "value\n", "--project"),
        (["skills", "install", "dir:/srv/skills/demo", "--name", " "], "", "--name"),
        (["skills", "cat", "sk-1", "../etc/passwd", "--revision", "1"], "", ".."),
        (["skills", "cat", "sk-1", "/", "--revision", "1"], "", "vide"),
    ],
)
def test_blank_or_traversing_options_are_refused_before_any_request(tmp_path, args, stdin, fragment):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], never, stdin=stdin)

    assert code == ExitCode.USAGE
    assert out == ""
    assert fragment in json.loads(err)["error"]["message"]


def test_skills_cat_text_mode_signals_a_truncated_content(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(
        ok({"path": "SKILL.md", "text": True, "content": "début", "truncated": True, "size": 300000, "sha256": "e"})
    )

    code, out, err, _ = invoke(tmp_path, ["skills", "cat", "sk-1", "SKILL.md", "--revision", "1"], recorder)

    assert code == ExitCode.OK
    assert out == "début"
    assert "tronqué" in err


def test_mcp_export_text_mode_stays_silent_without_notes(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(
        ok({"format": "claude", "project_id": None, "content": "{}\n", "placeholders": [], "partial_compatibility": [], "apply_notes": []})
    )

    code, out, err, _ = invoke(tmp_path, ["mcp", "export", "--format", "claude"], recorder)

    assert code == ExitCode.OK
    assert out == "{}\n"
    assert err == ""


def test_mcp_export_text_mode_rejects_a_malformed_payload(tmp_path):
    authenticated_config(tmp_path / "config.json")
    recorder = Recorder(ok({"format": "hermes", "content": None}))

    code, out, err, _ = invoke(tmp_path, ["mcp", "export", "--format", "hermes"], recorder)

    assert code == ExitCode.REMOTE
    assert out == ""
    assert "Erreur" in err


# --- revue adverse : fuites et cibles implicites -------------------------------------


def test_extra_positional_arguments_never_echo_secret_material(tmp_path):
    """Une valeur non guillemetée devient plusieurs arguments : argparse ne doit pas la citer."""

    code, out, err, _ = invoke(
        tmp_path,
        ["secrets", "set", "API_TOKEN", "--value-stdin", "hunter2", "xyzzy", "plugh"],
        never,
        stdin="value\n",
    )

    assert code == ExitCode.USAGE
    assert out == ""
    for fragment in ("hunter2", "xyzzy", "plugh"):
        assert fragment not in err
    # Le refus reste actionnable malgré la censure.
    assert "--value-stdin" in err


@pytest.mark.parametrize(
    "args",
    [
        ["secrets", "revoke", ""],
        ["mcp", "show", ""],
        ["mcp", "activate", " "],
        ["mcp", "bind", "", "--project", "p-1", "--tool", "resolve"],
        ["mcp", "unbind", ""],
        ["skills", "show", ""],
        ["skills", "bind", "", "--project", "p-1"],
        ["projects", "extensions", ""],
    ],
)
def test_blank_identifiers_never_address_a_collection_endpoint(tmp_path, args):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "identifiant" in json.loads(err)["error"]["message"]


@pytest.mark.parametrize(
    "args",
    [
        ["mcp", "bind", "srv-1", "--project", " ", "--tool", "resolve"],
        ["skills", "bind", "sk-1", "--project", " "],
    ],
)
def test_blank_project_on_bind_is_refused_before_any_request(tmp_path, args):
    authenticated_config(tmp_path / "config.json")

    code, out, err, _ = invoke(tmp_path, [*args, "--json"], never)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "--project" in json.loads(err)["error"]["message"]
