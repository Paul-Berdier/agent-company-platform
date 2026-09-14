from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Event
from typing import Callable

import httpx
import pytest

from acp_cli.cli import (
    ExitCode,
    _clear_operation,
    _execute_pending_operation,
    _reserve_operation,
    main,
)
from acp_cli.client import ACPClient
from acp_cli.config import (
    ConfigError,
    PendingOperation,
    Settings,
    load_settings,
    mutate_settings,
    save_settings,
)


def invoke(
    tmp_path: Path,
    args: list[str],
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    stdin: str = "",
    password_reader=lambda _prompt: "secret",
    sleep=lambda _seconds: None,
    browser_open=lambda _url: True,
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
        password_reader=password_reader,
        sleep=sleep,
        browser_open=browser_open,
    )
    return code, stdout.getvalue(), stderr.getvalue(), config


def authenticated_config(path: Path) -> None:
    settings = Settings(
        api_url="http://127.0.0.1:8000",
        web_url="http://127.0.0.1:5173",
    ).with_session("session-secret", "csrf-secret", principal_id="u-1")
    save_settings(path, settings)


class InteractiveInput(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize("login_args", [[], ["--login", "owner"]])
def test_json_login_never_prompts_or_calls_getpass(tmp_path, login_args):
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = main(
        [
            "login",
            *login_args,
            "--json",
            "--config",
            str(tmp_path / "config.json"),
        ],
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("an incomplete JSON login must not call HTTP")
        ),
        stdout=stdout,
        stderr=stderr,
        stdin=InteractiveInput(),
        environ={},
        password_reader=lambda _prompt: pytest.fail("JSON mode must not call getpass"),
    )

    assert code == ExitCode.USAGE
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["error"]["code"] == "usage"


def test_json_chat_never_prompts_on_an_interactive_stdin(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = main(
        ["chat", "--json", "--config", str(config)],
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("an incomplete JSON chat must not call HTTP")
        ),
        stdout=stdout,
        stderr=stderr,
        stdin=InteractiveInput(),
        environ={},
    )

    assert code == ExitCode.USAGE
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["error"]["code"] == "usage"


def test_login_reads_password_from_stdin_and_never_outputs_secrets(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/login"
        assert json.loads(request.content) == {"login": "owner", "password": "stdin-secret"}
        return httpx.Response(
            200,
            headers={"set-cookie": "acp_session=cookie-secret; Path=/; HttpOnly"},
            json={
                "user": {"id": "u-1", "login": "owner", "role": "owner"},
                "csrf_token": "csrf-secret",
                "expires_at": "2030-01-01T00:00:00Z",
            },
        )

    code, out, err, config = invoke(
        tmp_path,
        ["login", "--login", "owner", "--password-stdin", "--json", "--non-interactive"],
        handler,
        stdin="stdin-secret\n",
        password_reader=lambda _prompt: pytest.fail("getpass should not be called"),
    )

    assert code == ExitCode.OK
    assert err == ""
    assert "cookie-secret" not in out
    assert "csrf-secret" not in out
    payload = json.loads(out)
    assert payload["authenticated"] is True
    stored = json.loads(config.read_text(encoding="utf-8"))
    assert stored["session_cookie"] == "cookie-secret"
    assert stored["csrf_token"] == "csrf-secret"
    assert stored["session_origin"] == "http://127.0.0.1:8000"
    assert stored["principal_id"] == "u-1"


def test_stale_login_response_cannot_overwrite_newer_session_or_endpoint(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(_request: httpx.Request) -> httpx.Response:
        newer = Settings(
            api_url="https://new-api.example.test/v2",
            web_url="https://new-app.example.test",
        ).with_session("newer-cookie", "newer-csrf", principal_id="u-new")
        save_settings(config, newer)
        return httpx.Response(
            200,
            headers={"set-cookie": "acp_session=stale-cookie; Path=/; HttpOnly"},
            json={
                "user": {"id": "u-stale", "login": "stale", "role": "owner"},
                "csrf_token": "stale-csrf",
            },
        )

    code, out, err, _ = invoke(
        tmp_path,
        [
            "login",
            "--login",
            "stale",
            "--password-stdin",
            "--non-interactive",
            "--json",
        ],
        handler,
        stdin="password\n",
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert "réponse obsolète" in json.loads(err)["error"]["message"]
    current = load_settings(config, environ={})
    assert current.api_url == "https://new-api.example.test/v2"
    assert current.session_cookie == "newer-cookie"
    assert current.csrf_token == "newer-csrf"
    assert current.principal_id == "u-new"


def test_projects_list_accepts_json_after_subcommand_and_sends_session(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/projects"
        assert request.url.params["workspace_id"] == "w-1"
        assert request.headers["cookie"] == "acp_session=session-secret"
        return httpx.Response(200, json=[{"id": "p-1", "name": "Projet"}])

    code, out, err, _ = invoke(
        tmp_path,
        ["projects", "list", "--workspace", "w-1", "--json"],
        handler,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)[0]["id"] == "p-1"


def test_project_add_sends_csrf_and_expected_payload(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/projects"
        assert request.headers["x-csrf-token"] == "csrf-secret"
        assert json.loads(request.content) == {
            "workspace_id": "w-1",
            "department_id": None,
            "name": "CLI",
            "project_type": "generic",
            "description": "",
        }
        return httpx.Response(200, json={"id": "p-1", "name": "CLI"})

    code, _, err, _ = invoke(
        tmp_path,
        ["projects", "add", "--workspace", "w-1", "--name", "CLI"],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""


def test_doctor_rotates_csrf_without_exposing_it(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/status":
            return httpx.Response(200, json={"bootstrap_required": False})
        if request.url.path == "/auth/session":
            return httpx.Response(
                200,
                json={
                    "user": {"id": "u-1", "login": "owner", "role": "owner"},
                    "csrf_token": "rotated-csrf-secret",
                    "expires_at": "2030-01-01T00:00:00Z",
                },
            )
        raise AssertionError(request.url)

    code, out, err, stored_path = invoke(
        tmp_path,
        ["doctor", "--json"],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""
    assert "rotated-csrf-secret" not in out
    assert json.loads(out)["authenticated"] is True
    assert json.loads(stored_path.read_text(encoding="utf-8"))["csrf_token"] == "rotated-csrf-secret"


def test_session_mutations_merge_without_erasing_pending(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Pending mission"],
        lambda request: (_ for _ in ()).throw(
            httpx.ReadError("uncertain", request=request)
        ),
    )
    original_pending = load_settings(config, environ={}).pending_operation
    assert original_pending is not None

    def doctor_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/status":
            return httpx.Response(200, json={"bootstrap_required": False})
        return httpx.Response(
            200,
            json={
                "user": {"id": "u-1", "login": "owner", "role": "owner"},
                "csrf_token": "doctor-csrf",
            },
        )

    code, _, err, _ = invoke(tmp_path, ["doctor", "--json"], doctor_handler)
    assert code == ExitCode.OK
    assert err == ""
    after_doctor = load_settings(config, environ={})
    assert after_doctor.pending_operation == original_pending
    assert after_doctor.csrf_token == "doctor-csrf"

    def login_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"set-cookie": "acp_session=new-cookie; Path=/; HttpOnly"},
            json={
                "user": {"id": "u-2", "login": "other", "role": "owner"},
                "csrf_token": "login-csrf",
            },
        )

    code, _, err, _ = invoke(
        tmp_path,
        ["login", "--login", "other", "--password-stdin", "--non-interactive"],
        login_handler,
        stdin="password\n",
    )
    assert code == ExitCode.OK
    assert err == ""
    after_login = load_settings(config, environ={})
    assert after_login.pending_operation == original_pending
    assert after_login.session_cookie == "new-cookie"
    assert after_login.principal_id == "u-2"


def test_logout_does_not_erase_a_newer_concurrent_session(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["cookie"] == "acp_session=session-secret"
        current = load_settings(config, environ={})
        save_settings(
            config,
            current.with_session("newer-cookie", "newer-csrf", principal_id="u-2"),
        )
        return httpx.Response(204)

    code, _, err, _ = invoke(tmp_path, ["logout", "--json"], handler)
    assert code == ExitCode.OK
    assert err == ""
    current = load_settings(config, environ={})
    assert current.session_cookie == "newer-cookie"
    assert current.csrf_token == "newer-csrf"
    assert current.principal_id == "u-2"


def test_run_builds_complete_mission_payload(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/missions"
        key = request.headers["idempotency-key"]
        assert key.startswith("acp-cli:mission-create:")
        assert len(key) < 200
        payload = json.loads(request.content)
        assert payload["project_id"] == "p-1"
        assert payload["objective"] == "Compiler le rapport"
        assert payload["expected_outcome"] == "Compiler le rapport"
        assert payload["autonomy"]["mode"] == "supervised"
        assert payload["budget"] == {
            "max_cost": None,
            "currency": "EUR",
            "max_tokens": None,
            "max_tool_calls": 100,
        }
        assert payload["resources"] == [
            {
                "kind": "repository",
                "identifier": "C:\\work",
                "access": "read",
                "description": "",
            }
        ]
        assert payload["acceptance_criteria"]
        return httpx.Response(201, json={"id": "m-1", "status": "queued"})

    code, out, err, _ = invoke(
        tmp_path,
        [
            "run",
            "--project",
            "p-1",
            "--goal",
            "Compiler le rapport",
            "--resource",
            "repository=C:\\work:read",
            "--json",
        ],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""
    result = json.loads(out)
    assert result["id"] == "m-1"
    assert result["idempotency_key"].startswith("acp-cli:mission-create:")
    assert json.loads(config.read_text(encoding="utf-8"))["pending_operation"] is None


def test_watch_terminal_run_never_calls_stop(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        return httpx.Response(
            200,
            json={
                "id": "m-1",
                "current_run": {"id": "r-1", "status": "succeeded"},
            },
        )

    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "watch", "m-1", "--json"],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["run"]["status"] == "succeeded"
    assert requests == [("GET", "/missions/m-1")]


def test_watch_treats_blocked_as_a_stable_terminal_state(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"current_run": {"id": "r-1", "status": "blocked"}},
        )

    code, _, err, _ = invoke(
        tmp_path,
        ["runs", "watch", "m-1"],
        handler,
        sleep=lambda _seconds: pytest.fail("blocked must not keep polling"),
    )
    assert code == ExitCode.OK
    assert err == ""
    assert calls == 1


def test_runs_stop_uses_mission_endpoint_and_csrf(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.raw_path == b"/missions/m%2F1/stop"
        assert request.headers["x-csrf-token"] == "csrf-secret"
        assert request.headers["idempotency-key"].startswith(
            "acp-cli:mission-stop:"
        )
        return httpx.Response(
            200,
            json={
                "mission_id": "m/1",
                "run": {"id": "r-1", "status": "stopping"},
                "already_stopped": False,
            },
        )

    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "stop", "m/1", "--json"],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["run"]["status"] == "stopping"


def test_interrupting_watch_returns_130_without_stop(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.method)
        return httpx.Response(
            200,
            json={"current_run": {"id": "r-1", "status": "running"}},
        )

    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    code, _, err, _ = invoke(
        tmp_path,
        ["runs", "watch", "m-1"],
        handler,
        sleep=interrupt,
    )
    assert code == ExitCode.INTERRUPTED
    assert "aucun arrêt" in err
    assert requests == ["GET"]


def test_chat_creates_conversation_and_prints_completed_answer(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/conversations":
            return httpx.Response(201, json={"id": "c-1"})
        if request.url.path == "/conversations/c-1/turns":
            return httpx.Response(
                202,
                json={
                    "id": "t-1",
                    "status": "completed",
                    "assistant_content": "Réponse Hermes",
                },
            )
        raise AssertionError(request.url)

    code, out, err, _ = invoke(
        tmp_path,
        ["chat", "--project", "p-1", "Bonjour"],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""
    assert out.strip() == "Réponse Hermes"
    assert paths == ["/conversations", "/conversations/c-1/turns"]


def test_artifacts_are_filtered_by_run_even_if_server_ignores_query(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["task_run_id"] == "r-1"
        return httpx.Response(
            200,
            json=[
                {"id": "a-1", "task_run_id": "r-1"},
                {"id": "a-2", "task_run_id": "r-2"},
            ],
        )

    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "list", "--run", "r-1", "--json"],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""
    assert [item["id"] for item in json.loads(out)] == ["a-1"]


def test_open_prints_url_without_browser_unless_explicit(tmp_path):
    called: list[str] = []

    def no_http(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("open must not call the API")

    code, out, err, _ = invoke(
        tmp_path,
        ["open", "--run", "run / 1"],
        no_http,
        browser_open=lambda url: called.append(url),
    )
    assert code == ExitCode.OK
    assert err == ""
    assert out.strip() == "http://127.0.0.1:5173/missions?run=run+%2F+1"
    assert called == []


def test_automations_list_is_connected_and_returns_api_payload(tmp_path):
    automation = {
        "id": "automation-1",
        "project_id": "project-1",
        "name": "Revue quotidienne",
        "description": "",
        "schedule": {
            "kind": "cron",
            "expression": "0 9 * * *",
            "timezone": "Europe/Paris",
        },
        "enabled": False,
        "catchup_policy": "skip",
        "max_concurrent_runs": 1,
        "next_run_at": None,
        "created_at": "2026-09-14T08:00:00Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/automations"
        assert request.url.params["limit"] == "100"
        return httpx.Response(200, json=[automation])

    code, out, err, _ = invoke(
        tmp_path,
        ["automations", "list", "--json"],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out) == [automation]


def test_help_uses_injected_output_and_returns_success(tmp_path):
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = main(
        ["--help"],
        stdout=stdout,
        stderr=stderr,
        stdin=io.StringIO(),
        environ={"ACP_CONFIG_PATH": str(tmp_path / "unused.json")},
    )

    assert code == ExitCode.OK
    assert "Agent Company Platform CLI" in stdout.getvalue()
    assert stderr.getvalue() == ""


@pytest.mark.parametrize("status, expected", [(401, ExitCode.AUTH), (403, ExitCode.AUTH), (500, ExitCode.REMOTE)])
def test_api_errors_have_stable_exit_codes_and_hide_response_input(tmp_path, status, expected):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"detail": [{"msg": "invalid", "input": "secret-value"}]},
        )

    code, out, err, _ = invoke(tmp_path, ["projects", "list", "--json"], handler)
    assert code == expected
    assert out == ""
    assert "secret-value" not in err
    assert json.loads(err)["error"]["status"] == status


def test_network_failure_has_dedicated_exit_code(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("contains-internal-network-detail", request=request)

    code, out, err, _ = invoke(
        tmp_path,
        ["workers", "list", "--json"],
        handler,
    )
    assert code == ExitCode.NETWORK
    assert out == ""
    assert "contains-internal-network-detail" not in err
    assert json.loads(err)["error"]["code"] == "network"


def test_api_origin_override_never_sends_bound_credentials(tmp_path):
    config = tmp_path / "config.json"
    stored = Settings(
        api_url="https://api.example.test/v1",
        web_url="https://app.example.test",
    ).with_session("do-not-send-cookie", "do-not-send-csrf")
    save_settings(config, stored)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "other.example.test"
        assert "cookie" not in request.headers
        assert "x-csrf-token" not in request.headers
        return httpx.Response(200, json={"id": "p-other"})

    code, out, err, _ = invoke(
        tmp_path,
        [
            "projects",
            "add",
            "--workspace",
            "w-1",
            "--name",
            "Other origin",
            "--api-url",
            "https://other.example.test/v1",
            "--json",
        ],
        handler,
    )

    assert code == ExitCode.OK
    assert json.loads(out)["id"] == "p-other"
    assert err == ""


def test_same_normalized_origin_still_sends_bound_credentials(tmp_path):
    config = tmp_path / "config.json"
    stored = Settings(
        api_url="https://API.Example.Test:443/v1",
        web_url="https://app.example.test",
    ).with_session("same-origin-cookie", "same-origin-csrf")
    save_settings(config, stored)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.example.test"
        assert request.url.path == "/v2/projects"
        assert request.headers["cookie"] == "acp_session=same-origin-cookie"
        assert request.headers["x-csrf-token"] == "same-origin-csrf"
        return httpx.Response(200, json={"id": "p-1"})

    code, out, err, _ = invoke(
        tmp_path,
        [
            "projects",
            "add",
            "--workspace",
            "w-1",
            "--name",
            "Same origin",
            "--api-url",
            "https://api.example.test/v2",
            "--json",
        ],
        handler,
    )

    assert code == ExitCode.OK
    assert json.loads(out)["id"] == "p-1"
    assert err == ""


def test_explicit_idempotency_key_is_forwarded_unchanged(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["idempotency-key"] == "stable-client-retry-1"
        return httpx.Response(201, json={"id": "m-1", "status": "queued"})

    code, _, err, _ = invoke(
        tmp_path,
        [
            "run",
            "--project",
            "p-1",
            "--goal",
            "Goal",
            "--idempotency-key",
            "stable-client-retry-1",
        ],
        handler,
    )
    assert code == ExitCode.OK
    assert err == ""


def test_run_reuses_pending_key_after_uncertain_network_response(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    seen_keys: list[str] = []

    def uncertain(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["idempotency-key"])
        raise httpx.ReadError("response lost after request", request=request)

    code, out, err, stored_path = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Same mission", "--json"],
        uncertain,
    )

    assert code == ExitCode.NETWORK
    assert out == ""
    error = json.loads(err)["error"]
    assert error["idempotency_key"] == seen_keys[0]
    assert error["recovery"] == "retry_same_run_command"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    pending = stored["pending_operation"]
    assert pending["idempotency_key"] == seen_keys[0]
    assert pending["api_endpoint"] == "http://127.0.0.1:8000"
    assert len(pending["payload_fingerprint"]) == 64
    assert len(pending["principal_session_fingerprint"]) == 64
    assert "session-secret" not in json.dumps(pending)
    assert "csrf-secret" not in json.dumps(pending)

    # Une rotation de session du même principal ne doit pas perdre la reprise.
    pending_settings = load_settings(stored_path, environ={})
    save_settings(
        stored_path,
        pending_settings.with_session(
            "rotated-session-secret",
            "rotated-csrf-secret",
            principal_id="u-1",
        ),
    )

    def recovered(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["idempotency-key"])
        assert request.headers["cookie"] == "acp_session=rotated-session-secret"
        return httpx.Response(201, json={"id": "m-recovered", "status": "queued"})

    code, out, err, stored_path = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Same mission", "--json"],
        recovered,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert seen_keys[1] == seen_keys[0]
    result = json.loads(out)
    assert result["id"] == "m-recovered"
    assert result["idempotency_key"] == seen_keys[0]
    assert json.loads(stored_path.read_text(encoding="utf-8"))["pending_operation"] is None


def test_run_refuses_payload_or_explicit_key_divergence_while_pending(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    def uncertain(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("uncertain", request=request)

    code, _, _, _ = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Original"],
        uncertain,
    )
    assert code == ExitCode.NETWORK

    code, out, err, _ = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Different", "--json"],
        lambda _request: pytest.fail("a divergent pending operation must not call the API"),
    )
    assert code == ExitCode.USAGE
    assert out == ""
    assert "exactement la commande initiale" in json.loads(err)["error"]["message"]

    code, out, err, _ = invoke(
        tmp_path,
        [
            "run",
            "--project",
            "p-1",
            "--goal",
            "Original",
            "--idempotency-key",
            "different-explicit-key",
            "--json",
        ],
        lambda _request: pytest.fail("a colliding key must not call the API"),
    )
    assert code == ExitCode.USAGE
    assert out == ""
    assert "diverge" in json.loads(err)["error"]["message"]


def test_run_clears_pending_operation_after_certain_api_error(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    code, out, err, stored_path = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Rejected", "--json"],
        lambda _request: httpx.Response(422, json={"detail": "mission refusée"}),
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["status"] == 422
    assert json.loads(stored_path.read_text(encoding="utf-8"))["pending_operation"] is None


def test_retry_does_not_clear_prior_uncertainty_on_a_certain_rejection(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    seen_keys: list[str] = []

    def uncertain(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["idempotency-key"])
        raise httpx.ReadError("lost response", request=request)

    code, _, _, _ = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "May be committed"],
        uncertain,
    )
    assert code == ExitCode.NETWORK

    def expired_session(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["idempotency-key"])
        return httpx.Response(401, json={"detail": "session expired"})

    code, out, err, stored_path = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "May be committed", "--json"],
        expired_session,
    )
    assert code == ExitCode.AUTH
    assert out == ""
    error = json.loads(err)["error"]
    assert error["idempotency_key"] == seen_keys[0] == seen_keys[1]
    assert error["status"] == 401
    pending = json.loads(stored_path.read_text(encoding="utf-8"))["pending_operation"]
    assert pending["idempotency_key"] == seen_keys[0]
    assert pending["dispatch_count"] == 2


@pytest.mark.parametrize(
    "response_kind, expected_error",
    [
        ("server_error", "api"),
        ("redirect", "client"),
        ("invalid_json", "client"),
        ("empty_success", "client"),
        ("wrong_shape", "client"),
    ],
)
def test_run_keeps_pending_after_semantically_uncertain_response(
    tmp_path,
    response_kind,
    expected_error,
):
    config = tmp_path / "config.json"
    authenticated_config(config)
    seen_key = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_key
        seen_key = request.headers["idempotency-key"]
        if response_kind == "server_error":
            return httpx.Response(500, json={"detail": "post-commit failure"})
        if response_kind == "redirect":
            return httpx.Response(307, headers={"location": "/other"})
        if response_kind == "invalid_json":
            return httpx.Response(201, content=b"{")
        if response_kind == "empty_success":
            return httpx.Response(201, content=b"")
        return httpx.Response(201, json={"status": "queued"})

    code, out, err, stored_path = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Uncertain", "--json"],
        handler,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == expected_error
    assert error["idempotency_key"] == seen_key
    assert error["recovery"] == "retry_same_run_command"
    if response_kind == "server_error":
        assert error["status"] == 500
    pending = json.loads(stored_path.read_text(encoding="utf-8"))["pending_operation"]
    assert pending["idempotency_key"] == seen_key


def test_pending_is_bound_to_full_api_endpoint_path(tmp_path):
    config = tmp_path / "config.json"
    save_settings(
        config,
        Settings(
            api_url="https://api.example.test/v1",
            web_url="https://app.example.test",
        ).with_session("cookie", "csrf", principal_id="u-1"),
    )

    code, _, _, _ = invoke(
        tmp_path,
        [
            "run",
            "--project",
            "p-1",
            "--goal",
            "Endpoint-bound",
            "--api-url",
            "https://api.example.test/v1",
        ],
        lambda request: (_ for _ in ()).throw(
            httpx.ReadError("uncertain", request=request)
        ),
    )
    assert code == ExitCode.NETWORK

    code, out, err, _ = invoke(
        tmp_path,
        [
            "run",
            "--project",
            "p-1",
            "--goal",
            "Endpoint-bound",
            "--api-url",
            "https://api.example.test/v2",
            "--json",
        ],
        lambda _request: pytest.fail("a different endpoint must not receive the retry"),
    )
    assert code == ExitCode.USAGE
    assert out == ""
    assert "autre endpoint" in json.loads(err)["error"]["message"]


def test_stop_reuses_pending_key_after_network_uncertainty(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    seen_keys: list[str] = []

    def uncertain(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["idempotency-key"])
        raise httpx.ReadError("response lost", request=request)

    code, _, err, stored_path = invoke(
        tmp_path,
        ["runs", "stop", "m-1", "--json"],
        uncertain,
    )
    assert code == ExitCode.NETWORK
    error = json.loads(err)["error"]
    assert error["operation"] == "mission-stop"
    assert error["recovery"] == "retry_same_stop_command"
    pending = json.loads(stored_path.read_text(encoding="utf-8"))["pending_operation"]
    assert pending["operation"] == "mission-stop"

    def recovered(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["idempotency-key"])
        return httpx.Response(
            200,
            json={
                "mission_id": "m-1",
                "run": {"id": "r-1", "status": "stopping"},
                "already_stopped": True,
            },
        )

    code, out, err, stored_path = invoke(
        tmp_path,
        ["runs", "stop", "m-1", "--json"],
        recovered,
    )
    assert code == ExitCode.OK
    assert err == ""
    assert seen_keys[1] == seen_keys[0]
    assert json.loads(out)["idempotency_key"] == seen_keys[0]
    assert json.loads(stored_path.read_text(encoding="utf-8"))["pending_operation"] is None


def test_pending_show_and_confirmed_discard_never_expose_secrets(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)

    code, _, _, _ = invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Recover me"],
        lambda request: (_ for _ in ()).throw(
            httpx.ConnectError("uncertain", request=request)
        ),
    )
    assert code == ExitCode.NETWORK

    no_http = lambda _request: pytest.fail("pending commands must remain local")
    code, out, err, _ = invoke(tmp_path, ["pending", "show", "--json"], no_http)
    assert code == ExitCode.OK
    assert err == ""
    shown = json.loads(out)
    assert shown["pending"] is True
    assert shown["operation"] == "mission-create"
    assert "principal_session_fingerprint" not in shown
    assert "session-secret" not in out
    assert "csrf-secret" not in out

    code, out, err, stored_path = invoke(
        tmp_path,
        ["pending", "discard", "--json", "--non-interactive"],
        no_http,
    )
    assert code == ExitCode.USAGE
    assert out == ""
    assert "--yes" in json.loads(err)["error"]["message"]
    assert load_settings(stored_path, environ={}).pending_operation is not None

    code, out, err, stored_path = invoke(
        tmp_path,
        ["pending", "discard", "--yes", "--json", "--non-interactive"],
        no_http,
    )
    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["discarded"] is True
    assert load_settings(stored_path, environ={}).pending_operation is None


def test_pending_discard_requires_positive_interactive_confirmation(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    invoke(
        tmp_path,
        ["run", "--project", "p-1", "--goal", "Recover me"],
        lambda request: (_ for _ in ()).throw(
            httpx.ConnectError("uncertain", request=request)
        ),
    )
    no_http = lambda _request: pytest.fail("pending commands must remain local")

    code, out, err, stored_path = invoke(
        tmp_path,
        ["pending", "discard"],
        no_http,
        stdin="non\n",
    )
    assert code == ExitCode.OK
    assert err == ""
    assert "Confirmer" in out
    assert load_settings(stored_path, environ={}).pending_operation is not None

    code, out, err, stored_path = invoke(
        tmp_path,
        ["pending", "discard"],
        no_http,
        stdin="oui\n",
    )
    assert code == ExitCode.OK
    assert err == ""
    assert "Confirmer" in out
    assert load_settings(stored_path, environ={}).pending_operation is None


def test_concurrent_identical_mutation_cannot_send_a_second_request(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    settings = load_settings(config, environ={})
    first_started = Event()
    release_first = Event()
    seen_keys: list[str] = []

    def first_handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["idempotency-key"])
        first_started.set()
        if not release_first.wait(5):
            raise AssertionError("the first request was not released")
        return httpx.Response(201, json={"id": "m-one", "status": "queued"})

    def second_handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("a concurrent mutation must not reach the API")

    first_client = ACPClient(settings, transport=httpx.MockTransport(first_handler))
    second_client = ACPClient(settings, transport=httpx.MockTransport(second_handler))
    payload = {"project_id": "p-1", "objective": "same"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            _execute_pending_operation,
            first_client,
            config,
            operation="mission-create",
            payload=payload,
            path="/missions",
            explicit_key=None,
            baseline_settings=settings,
        )
        assert first_started.wait(2)
        second = executor.submit(
            _execute_pending_operation,
            second_client,
            config,
            operation="mission-create",
            payload=payload,
            path="/missions",
            explicit_key=None,
            baseline_settings=settings,
        )
        try:
            with pytest.raises(ConfigError, match="déjà en cours"):
                second.result(timeout=2)
        finally:
            release_first.set()
        result, _ = first.result(timeout=2)

    assert result["id"] == "m-one"
    assert result["idempotency_key"] == seen_keys[0]
    assert len(seen_keys) == 1
    assert load_settings(config, environ={}).pending_operation is None


def test_concurrent_reservations_share_one_key_and_clear_is_conditional(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    stale_settings = load_settings(config, environ={})
    barrier = Barrier(2)
    payload = {"project_id": "p-1", "objective": "same"}

    def reserve():
        barrier.wait()
        return _reserve_operation(
            stale_settings,
            config,
            operation="mission-create",
            payload=payload,
            explicit_key=None,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result() for future in [executor.submit(reserve) for _ in range(2)]]

    assert results[0][0] == results[1][0]
    assert {result[2].dispatch_count for result in results} == {1, 2}
    assert {result[3] for result in results} == {False, True}

    original_token = min(results, key=lambda result: result[2].dispatch_count)[2]
    replacement = PendingOperation(
        operation="mission-stop",
        api_endpoint=original_token.api_endpoint,
        principal_session_fingerprint=original_token.principal_session_fingerprint,
        payload_fingerprint="f" * 64,
        idempotency_key="replacement-key",
    )

    def replace_pending(current: Settings):
        return replace(current, pending_operation=replacement), None

    mutate_settings(config, replace_pending, environ={})
    _clear_operation(config, original_token)
    assert load_settings(config, environ={}).pending_operation == replacement


def test_pending_mutations_preserve_a_concurrent_session_refresh(tmp_path):
    config = tmp_path / "config.json"
    authenticated_config(config)
    selected = load_settings(config, environ={})
    _, _, token, _ = _reserve_operation(
        selected,
        config,
        operation="mission-create",
        payload={"project_id": "p-1", "objective": "merge"},
        explicit_key=None,
    )

    def rotate(current: Settings):
        return current.with_session(
            "new-cookie",
            "new-csrf",
            principal_id="u-1",
        ), None

    mutate_settings(config, rotate, environ={})
    _clear_operation(config, token)
    current = load_settings(config, environ={})
    assert current.pending_operation is None
    assert current.session_cookie == "new-cookie"
    assert current.csrf_token == "new-csrf"
