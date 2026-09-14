"""Contrat HTTP du groupe ``acp automations``.

Ces tests n'utilisent aucun réseau : ils vérifient la méthode, le chemin encodé,
les paramètres, le corps et la clé d'idempotence reçus par un transport simulé.
"""

from __future__ import annotations

import io
import json
import os
import re
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
    environ: dict[str, str] | None = None,
):
    stdout = io.StringIO()
    stderr = io.StringIO()
    config = tmp_path / "config.json"
    if not config.exists():
        settings = Settings(
            api_url="http://127.0.0.1:8000",
            web_url="http://127.0.0.1:5173",
        ).with_session("session-secret", "csrf-secret", principal_id="u-1")
        save_settings(config, settings)
    code = main(
        [*args, "--config", str(config)],
        transport=httpx.MockTransport(handler),
        stdout=stdout,
        stderr=stderr,
        stdin=io.StringIO(),
        environ=environ or {},
        password_reader=lambda _prompt: pytest.fail("aucune invite attendue"),
        browser_open=lambda _url: pytest.fail("aucun navigateur attendu"),
    )
    return code, stdout.getvalue(), stderr.getvalue()


class Recorder:
    def __init__(self, *responses: tuple[int, Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "raw_path": request.url.raw_path.decode(),
                "params": dict(request.url.params),
                "body": json.loads(request.content) if request.content else None,
                "cookie": request.headers.get("cookie"),
                "csrf": request.headers.get("x-csrf-token"),
                "idempotency_key": request.headers.get("idempotency-key"),
            }
        )
        if not self.responses:
            raise AssertionError(f"requête inattendue : {request.method} {request.url}")
        status, body = self.responses.pop(0)
        return httpx.Response(status, json=body)


def never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("aucune requête HTTP ne doit être envoyée")


TEMPLATE = {
    "title": "Revue",
    "objective": "Relire les alertes",
    "expected_outcome": "Rapport publié",
    "acceptance_criteria": ["Rapport vérifiable"],
    "autonomy": {
        "mode": "bounded",
        "allowed_actions": ["read"],
        "forbidden_actions": [],
        "approval_required_actions": [],
    },
    "resources": [],
    "budget": {
        "max_cost": 2.5,
        "currency": "EUR",
        "max_tokens": 2000,
        "max_tool_calls": 20,
    },
    "duration_seconds": 900,
    "team_id": None,
    "agent_instance_id": None,
    "priority": 3,
    "required_capabilities": [],
}

SCHEDULE = {"kind": "cron", "expression": "0 9 * * 1-5", "timezone": "Europe/Paris"}
SUMMARY = {
    "id": "a-1",
    "project_id": "p-1",
    "name": "Revue",
    "description": "",
    "schedule": SCHEDULE,
    "enabled": False,
    "catchup_policy": "skip",
    "max_concurrent_runs": 1,
    "next_run_at": None,
    "created_at": "2026-09-14T08:00:00Z",
}
RUN = {
    "id": "ar-1",
    "automation_id": "a-1",
    "fire_key": "a" * 32,
    "scheduled_for": "2026-09-14T08:00:00Z",
    "fired_at": "2026-09-14T08:00:01Z",
    "task_id": "task-1",
    "trigger_kind": "manual",
    "outcome": "launched",
    "detail": "Mission créée",
    "completion_status": None,
}
DETAIL = {**SUMMARY, "mission_template": TEMPLATE, "recent_runs": [RUN]}
CREATE_RESPONSE = {
    **DETAIL,
    "schedule": {
        "kind": "cron",
        "expression": "0 9 * * *",
        "timezone": "Europe/Paris",
    },
}
WEBHOOK_STATUS = {
    "enabled": False,
    "secret_configured": False,
    "endpoint_path": "/automations/a-1/webhook/trigger",
    "rotated_at": None,
}


def test_list_calls_real_api_with_disabled_filter_and_session(tmp_path):
    recorder = Recorder((200, [SUMMARY]))

    code, out, err = invoke(
        tmp_path,
        ["automations", "list", "--project", "p-1", "--disabled", "--limit", "7", "--json"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out) == [SUMMARY]
    assert recorder.calls == [
        {
            "method": "GET",
            "path": "/automations",
            "raw_path": "/automations?limit=7&project_id=p-1&enabled=false",
            "params": {"limit": "7", "project_id": "p-1", "enabled": "false"},
            "body": None,
            "cookie": "acp_session=session-secret",
            "csrf": None,
            "idempotency_key": None,
        }
    ]


def test_create_parses_inline_template_timezone_and_encodes_project(tmp_path):
    recorder = Recorder((201, {
        **DETAIL,
        "project_id": "project/one",
        "name": "Revue matin",
        "description": "Chaque jour ouvré",
        "schedule": {
            "kind": "cron",
            "expression": "0 9 * * 1-5",
            "timezone": "America/Montreal",
        },
        "catchup_policy": "run_once",
        "max_concurrent_runs": 2,
    }))

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "create",
            "--project",
            "project/one",
            "--name",
            "  Revue matin  ",
            "--description",
            "Chaque jour ouvré",
            "--schedule-kind",
            "cron",
            "--expression",
            "0 9 * * 1-5",
            "--timezone",
            "America/Montreal",
            "--template",
            json.dumps(TEMPLATE),
            "--catchup",
            "run_once",
            "--max-concurrent-runs",
            "2",
            "--idempotency-key",
            "create-stable-key",
            "--json",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["id"] == "a-1"
    assert json.loads(out)["idempotency_key"] == "create-stable-key"
    assert recorder.calls[0]["method"] == "POST"
    assert recorder.calls[0]["raw_path"] == "/projects/project%2Fone/automations"
    assert recorder.calls[0]["csrf"] == "csrf-secret"
    assert recorder.calls[0]["idempotency_key"] == "create-stable-key"
    assert recorder.calls[0]["body"] == {
        "name": "Revue matin",
        "description": "Chaque jour ouvré",
        "schedule": {
            "kind": "cron",
            "expression": "0 9 * * 1-5",
            "timezone": "America/Montreal",
        },
        "mission_template": TEMPLATE,
        "catchup_policy": "run_once",
        "max_concurrent_runs": 2,
    }


def test_create_reads_template_file_and_uses_default_timezone(tmp_path):
    template_file = tmp_path / "template.json"
    template_file.write_text(json.dumps(TEMPLATE), encoding="utf-8")
    recorder = Recorder((201, {
        **DETAIL,
        "id": "a-2",
        "name": "Intervalle",
        "schedule": {
            "kind": "interval",
            "expression": "900",
            "timezone": "Europe/Paris",
        },
        "recent_runs": [{**RUN, "automation_id": "a-2"}],
    }))

    code, _, err = invoke(
        tmp_path,
        [
            "automations",
            "create",
            "--project",
            "p-1",
            "--name",
            "Intervalle",
            "--schedule-kind",
            "interval",
            "--expression",
            "15m",
            "--template-file",
            str(template_file),
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.calls[0]["body"]["mission_template"] == TEMPLATE
    assert recorder.calls[0]["body"]["schedule"] == {
        "kind": "interval",
        "expression": "900",
        "timezone": "Europe/Paris",
    }
    assert recorder.calls[0]["idempotency_key"].startswith(
        "acp-cli:automation-create:"
    )


def test_create_accepts_an_utf8_bom_template_file(tmp_path):
    template_file = tmp_path / "template-bom.json"
    template_file.write_text("\ufeff" + json.dumps(TEMPLATE), encoding="utf-8")
    recorder = Recorder((201, {
        **DETAIL,
        "name": "BOM",
        "schedule": {
            "kind": "cron",
            "expression": "0 9 * * *",
            "timezone": "Europe/Paris",
        },
    }))

    code, _, err = invoke(
        tmp_path,
        [
            "automations", "create", "--project", "p-1", "--name", "BOM",
            "--schedule-kind", "cron", "--expression", "0 9 * * *",
            "--template-file", str(template_file),
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.calls[0]["body"]["mission_template"] == TEMPLATE


def _create_args(key: str = "create-retry-key") -> list[str]:
    return [
        "automations",
        "create",
        "--project",
        "p-1",
        "--name",
        "Revue",
        "--schedule-kind",
        "cron",
        "--expression",
        "0 9 * * *",
        "--template",
        json.dumps(TEMPLATE),
        "--idempotency-key",
        key,
        "--json",
    ]


def test_create_accepts_the_contracts_canonical_response(tmp_path):
    submitted_template = {
        "title": "Revue",
        "objective": "Relire les alertes",
        "expected_outcome": "Rapport publié",
        "acceptance_criteria": [" Rapport vérifiable ", "Rapport vérifiable"],
        "autonomy": {"allowed_actions": ["read"]},
        "budget": {
            "max_cost": 2.5,
            "currency": "eur",
            "max_tokens": 2000,
            "max_tool_calls": 20,
        },
        "duration_seconds": 900,
    }
    recorder = Recorder((201, CREATE_RESPONSE))

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "create",
            "--project",
            "p-1",
            "--name",
            "Revue",
            "--schedule-kind",
            "cron",
            "--expression",
            "0 9 * * *",
            "--template",
            json.dumps(submitted_template),
            "--idempotency-key",
            "create-canonical",
            "--json",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["mission_template"] == TEMPLATE
    assert recorder.calls[0]["body"]["mission_template"] == submitted_template


def test_create_network_failure_exposes_same_key_and_replay_instruction(tmp_path):
    def disconnected(request: httpx.Request) -> httpx.Response:
        assert request.headers["idempotency-key"] == "create-retry-key"
        raise httpx.ConnectError("private transport detail", request=request)

    code, out, err = invoke(tmp_path, _create_args(), disconnected)

    assert code == ExitCode.NETWORK
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "network"
    assert error["idempotency_key"] == "create-retry-key"
    assert error["recovery"] == "retry_automation_create_with_same_key"
    assert "acp automations create" in error["message"]
    assert "private transport detail" not in err


@pytest.mark.parametrize("status", [408, 500, 503])
def test_create_uncertain_http_status_keeps_same_key(tmp_path, status):
    recorder = Recorder((status, {"detail": "amont indisponible"}))

    code, out, err = invoke(tmp_path, _create_args(f"create-{status}"), recorder)

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "api"
    assert error["status"] == status
    assert error["idempotency_key"] == f"create-{status}"
    assert recorder.calls[0]["idempotency_key"] == f"create-{status}"


def test_create_invalid_success_is_uncertain_but_422_remains_api_error(tmp_path):
    malformed = Recorder((201, {"id": "created-but-response-truncated"}))
    code, out, err = invoke(
        tmp_path, _create_args("create-protocol"), malformed
    )
    assert code == ExitCode.REMOTE
    assert out == ""
    protocol_error = json.loads(err)["error"]
    assert protocol_error["code"] == "client"
    assert protocol_error["idempotency_key"] == "create-protocol"

    refused = Recorder((422, {"detail": "expression invalide"}))
    code, out, err = invoke(tmp_path, _create_args("create-422"), refused)
    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err) == {
        "error": {
            "code": "api",
            "message": "expression invalide",
            "status": 422,
        }
    }


@pytest.mark.parametrize(
    "response",
    [
        {**CREATE_RESPONSE, "name": "Autre routine"},
        {
            **CREATE_RESPONSE,
            "mission_template": {
                **TEMPLATE,
                "budget": {**TEMPLATE["budget"], "max_tokens": 999},
            },
        },
        {**CREATE_RESPONSE, "enabled": True},
    ],
)
def test_create_structural_2xx_without_requested_postcondition_is_uncertain(
    tmp_path, response
):
    recorder = Recorder((201, response))

    code, out, err = invoke(
        tmp_path,
        _create_args("create-postcondition"),
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "client"
    assert error["idempotency_key"] == "create-postcondition"
    assert error["recovery"] == "retry_automation_create_with_same_key"


def test_update_sends_only_supplied_fields_and_full_schedule(tmp_path):
    recorder = Recorder((200, {
        **DETAIL,
        "id": "a/1",
        "description": "",
        "schedule": {
            "kind": "cron",
            "expression": "30 2 * * *",
            "timezone": "Europe/Paris",
        },
        "max_concurrent_runs": 3,
        "recent_runs": [{**RUN, "automation_id": "a/1"}],
    }))

    code, _, err = invoke(
        tmp_path,
        [
            "automations",
            "update",
            "a/1",
            "--description",
            "",
            "--schedule-kind",
            "cron",
            "--expression",
            "30 2 * * *",
            "--timezone",
            "Europe/Paris",
            "--max-concurrent-runs",
            "3",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.calls[0]["method"] == "PATCH"
    assert recorder.calls[0]["raw_path"] == "/automations/a%2F1"
    assert recorder.calls[0]["body"] == {
        "description": "",
        "schedule": {
            "kind": "cron",
            "expression": "30 2 * * *",
            "timezone": "Europe/Paris",
        },
        "max_concurrent_runs": 3,
    }


def test_update_structural_2xx_without_requested_field_is_explicitly_uncertain(
    tmp_path,
):
    recorder = Recorder((200, DETAIL))

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "update",
            "a-1",
            "--name",
            "Nouveau nom",
            "--json",
        ],
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "client"
    assert "résultat de modification" in error["message"]
    assert "même --idempotency-key" in error["message"]
    assert error["idempotency_key"].startswith("acp-cli:automation-update:")
    assert error["recovery"] == "retry_automation_update_with_same_key_and_payload"


@pytest.mark.parametrize(
    "args,method,raw_path,params",
    [
        (["show", "a/1"], "GET", "/automations/a%2F1", {}),
        (["enable", "a/1"], "POST", "/automations/a%2F1/enable", {}),
        (["disable", "a/1"], "POST", "/automations/a%2F1/disable", {}),
        (["runs", "a/1", "--limit", "25"], "GET", "/automations/a%2F1/runs?limit=25", {"limit": "25"}),
    ],
)
def test_resource_commands_use_expected_verbs_and_encoded_paths(
    tmp_path, args, method, raw_path, params
):
    if args[0] == "runs":
        response = []
    else:
        response = {
            **DETAIL,
            "id": "a/1",
            "enabled": args[0] == "enable",
            "recent_runs": [{**RUN, "automation_id": "a/1"}],
        }
    recorder = Recorder((200, response))

    code, _, err = invoke(tmp_path, ["automations", *args], recorder)

    assert code == ExitCode.OK
    assert err == ""
    assert recorder.calls[0]["method"] == method
    assert recorder.calls[0]["raw_path"] == raw_path
    assert recorder.calls[0]["params"] == params
    if method == "POST":
        assert recorder.calls[0]["csrf"] == "csrf-secret"
        assert recorder.calls[0]["idempotency_key"].startswith(
            f"acp-cli:automation-{args[0]}:"
        )


@pytest.mark.parametrize(
    "action,method,response",
    [
        ("status", "GET", WEBHOOK_STATUS),
        ("disable", "DELETE", WEBHOOK_STATUS),
    ],
)
def test_webhook_status_and_disable_use_real_paths(
    tmp_path, action, method, response
):
    recorder = Recorder((200, response))

    code, out, err = invoke(
        tmp_path,
        ["automations", "webhook", action, "a-1", "--json"],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    output = json.loads(out)
    if method == "DELETE":
        assert output.pop("idempotency_key").startswith(
            "acp-cli:automation-webhook-disable:"
        )
    assert output == WEBHOOK_STATUS
    assert recorder.calls[0]["method"] == method
    assert recorder.calls[0]["raw_path"] == "/automations/a-1/webhook"
    assert recorder.calls[0]["body"] is None
    if method == "DELETE":
        assert recorder.calls[0]["idempotency_key"].startswith(
            "acp-cli:automation-webhook-disable:"
        )
    else:
        assert recorder.calls[0]["idempotency_key"] is None
    if method == "DELETE":
        assert recorder.calls[0]["csrf"] == "csrf-secret"


def test_webhook_rotate_generates_cryptographic_secret_and_idempotency_key(
    tmp_path,
):
    observed: dict[str, Any] = {}

    def rotated(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        observed.update(
            secret=body["secret"],
            key=request.headers.get("idempotency-key"),
        )
        return httpx.Response(
            201,
            json={
                **WEBHOOK_STATUS,
                "enabled": True,
                "secret_configured": True,
                "rotated_at": "2026-09-14T12:00:00Z",
                "secret": body["secret"],
            },
        )

    code, out, err = invoke(
        tmp_path,
        ["automations", "webhook", "rotate", "a-1", "--json"],
        rotated,
    )

    assert code == ExitCode.OK
    assert err == ""
    result = json.loads(out)
    assert result["secret"] == observed["secret"]
    assert result["idempotency_key"] == observed["key"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{43,200}", result["secret"])
    assert observed["key"].startswith("acp-cli:automation-webhook-rotate:")


@pytest.mark.parametrize("source", ["environment", "file"])
def test_webhook_rotate_reads_provided_secret_from_safe_source(tmp_path, source):
    secret = "A" * 43
    extra: list[str]
    environ: dict[str, str] = {}
    if source == "environment":
        extra = ["--secret-env", "ACP_TEST_WEBHOOK_SECRET"]
        environ["ACP_TEST_WEBHOOK_SECRET"] = secret
    else:
        path = tmp_path / "webhook.secret"
        path.write_text(secret + "\n", encoding="utf-8")
        if os.name == "posix":
            path.chmod(0o600)
        extra = ["--secret-file", str(path)]

    def rotated(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"secret": secret}
        assert request.headers["idempotency-key"] == "rotate-stable"
        return httpx.Response(
            201,
            json={
                **WEBHOOK_STATUS,
                "enabled": True,
                "secret_configured": True,
                "rotated_at": "2026-09-14T12:00:00+00:00",
                "secret": secret,
            },
        )

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "webhook",
            "rotate",
            "a-1",
            *extra,
            "--idempotency-key",
            "rotate-stable",
            "--json",
        ],
        rotated,
        environ=environ,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["secret"] == secret


@pytest.mark.skipif(os.name != "posix", reason="permissions POSIX")
def test_webhook_secret_file_requires_private_posix_permissions(tmp_path):
    secret = "P" * 43
    path = tmp_path / "webhook.secret"
    path.write_text(secret, encoding="utf-8")
    path.chmod(0o644)

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "webhook",
            "rotate",
            "a-1",
            "--secret-file",
            str(path),
            "--json",
        ],
        never,
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert "chmod 600" in json.loads(err)["error"]["message"]
    assert secret not in err


@pytest.mark.skipif(os.name != "posix", reason="permissions POSIX")
def test_webhook_secret_file_accepts_mode_0600_from_the_open_descriptor(tmp_path):
    secret = "Q" * 43
    path = tmp_path / "webhook.secret"
    path.write_text(secret, encoding="utf-8")
    path.chmod(0o600)

    def rotated(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"secret": secret}
        return httpx.Response(
            201,
            json={
                **WEBHOOK_STATUS,
                "enabled": True,
                "secret_configured": True,
                "rotated_at": "2026-09-14T12:00:00Z",
                "secret": secret,
            },
        )

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "webhook",
            "rotate",
            "a-1",
            "--secret-file",
            str(path),
            "--json",
        ],
        rotated,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out)["secret"] == secret


@pytest.mark.skipif(os.name != "posix", reason="liens symboliques POSIX")
def test_webhook_secret_file_rejects_a_posix_symlink_before_http(tmp_path):
    secret = "R" * 43
    target = tmp_path / "webhook-target.secret"
    target.write_text(secret, encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "webhook-link.secret"
    link.symlink_to(target)

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "webhook",
            "rotate",
            "a-1",
            "--secret-file",
            str(link),
            "--json",
        ],
        never,
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert "lien symbolique" in json.loads(err)["error"]["message"]
    assert secret not in err


def test_uncertain_webhook_rotate_exposes_exact_key_and_secret_for_replay(
    tmp_path,
):
    observed: dict[str, str] = {}

    def disconnected(request: httpx.Request) -> httpx.Response:
        observed["secret"] = json.loads(request.content)["secret"]
        observed["key"] = request.headers["idempotency-key"]
        raise httpx.ReadError("private socket detail", request=request)

    code, out, err = invoke(
        tmp_path,
        ["automations", "webhook", "rotate", "a-1", "--json"],
        disconnected,
    )

    assert code == ExitCode.NETWORK
    assert out == ""
    error = json.loads(err)["error"]
    assert error["idempotency_key"] == observed["key"]
    assert error["secret"] == observed["secret"]
    assert error["recovery"] == (
        "retry_automation_webhook_rotate_with_same_key_and_secret"
    )
    assert "--secret-env ou --secret-file" in error["message"]
    assert "private socket detail" not in err
    config_text = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert observed["secret"] not in config_text


@pytest.mark.parametrize("status", [408, 500, 503])
def test_uncertain_webhook_http_status_exposes_replay_material(
    tmp_path, status
):
    secret = "B" * 43
    recorder = Recorder((status, {"detail": "amont indisponible"}))

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "webhook",
            "rotate",
            "a-1",
            "--secret-env",
            "ACP_TEST_WEBHOOK_SECRET",
            "--idempotency-key",
            f"rotate-{status}",
            "--json",
        ],
        recorder,
        environ={"ACP_TEST_WEBHOOK_SECRET": secret},
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["status"] == status
    assert error["idempotency_key"] == f"rotate-{status}"
    assert error["secret"] == secret


def test_invalid_webhook_success_is_uncertain_and_4xx_stays_certain(tmp_path):
    secret = "C" * 43
    args = [
        "automations",
        "webhook",
        "rotate",
        "a-1",
        "--secret-env",
        "ACP_TEST_WEBHOOK_SECRET",
        "--idempotency-key",
        "rotate-protocol",
        "--json",
    ]
    malformed = Recorder(
        (
            201,
            {
                **WEBHOOK_STATUS,
                "enabled": True,
                "secret_configured": True,
                "rotated_at": "2026-09-14T12:00:00Z",
            },
        )
    )
    code, out, err = invoke(
        tmp_path,
        args,
        malformed,
        environ={"ACP_TEST_WEBHOOK_SECRET": secret},
    )
    assert code == ExitCode.REMOTE
    assert out == ""
    protocol_error = json.loads(err)["error"]
    assert protocol_error["code"] == "client"
    assert protocol_error["secret"] == secret

    refused = Recorder((422, {"detail": f"secret {secret} invalide"}))
    code, out, err = invoke(
        tmp_path,
        args,
        refused,
        environ={"ACP_TEST_WEBHOOK_SECRET": secret},
    )
    assert code == ExitCode.REMOTE
    assert out == ""
    certain = json.loads(err)["error"]
    assert certain["code"] == "api"
    assert certain["status"] == 422
    assert "idempotency_key" not in certain
    assert secret not in err


def test_webhook_rotate_rejects_a_different_returned_secret_and_keeps_replay_material(
    tmp_path,
):
    secret = "E" * 43
    returned_secret = "F" * 43
    recorder = Recorder(
        (
            201,
            {
                **WEBHOOK_STATUS,
                "enabled": True,
                "secret_configured": True,
                "rotated_at": "2026-09-14T12:00:00Z",
                "secret": returned_secret,
            },
        )
    )

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "webhook",
            "rotate",
            "a-1",
            "--secret-env",
            "ACP_TEST_WEBHOOK_SECRET",
            "--idempotency-key",
            "rotate-secret-mismatch",
            "--json",
        ],
        recorder,
        environ={"ACP_TEST_WEBHOOK_SECRET": secret},
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    failure = json.loads(err)["error"]
    assert failure["code"] == "client"
    assert failure["idempotency_key"] == "rotate-secret-mismatch"
    assert failure["secret"] == secret
    assert returned_secret not in err


@pytest.mark.parametrize(
    "response",
    [
        {**WEBHOOK_STATUS, "secret": "must-not-leak"},
        {**WEBHOOK_STATUS, "endpoint_path": "/wrong"},
        {**WEBHOOK_STATUS, "enabled": True, "secret_configured": False},
        {**WEBHOOK_STATUS, "rotated_at": "2026-09-14T12:00:00"},
    ],
)
def test_webhook_status_rejects_non_strict_response_without_leaking_it(
    tmp_path, response
):
    recorder = Recorder((200, response))

    code, out, err = invoke(
        tmp_path,
        ["automations", "webhook", "status", "a-1", "--json"],
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "client"
    assert "must-not-leak" not in err


def test_calendar_validates_dates_and_sends_encoded_query(tmp_path):
    recorder = Recorder((200, []))

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "calendar",
            "--project",
            "p one",
            "--automation",
            "a/1",
            "--start",
            "2026-09-01T00:00:00+02:00",
            "--end",
            "2026-10-01T00:00:00+02:00",
            "--limit",
            "12",
            "--json",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert out == "[]\n"
    assert err == ""
    assert recorder.calls[0]["method"] == "GET"
    assert recorder.calls[0]["path"] == "/automations/calendar"
    assert recorder.calls[0]["params"] == {
        "limit": "12",
        "project_id": "p one",
        "automation_id": "a/1",
        "start": "2026-09-01T00:00:00+02:00",
        "end": "2026-10-01T00:00:00+02:00",
    }


def test_trigger_sends_explicit_key_and_displays_it(tmp_path):
    response = {**RUN, "automation_id": "a/1"}
    recorder = Recorder((201, response))

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "trigger",
            "a/1",
            "--idempotency-key",
            "stable-key-42",
            "--json",
        ],
        recorder,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert json.loads(out) == {**response, "idempotency_key": "stable-key-42"}
    assert recorder.calls[0]["method"] == "POST"
    assert recorder.calls[0]["raw_path"] == "/automations/a%2F1/trigger"
    assert recorder.calls[0]["body"] is None
    assert recorder.calls[0]["idempotency_key"] == "stable-key-42"


def test_trigger_generates_and_displays_reusable_key(tmp_path):
    response = RUN
    recorder = Recorder((201, response))

    code, out, err = invoke(
        tmp_path, ["automations", "trigger", "a-1", "--json"], recorder
    )

    assert code == ExitCode.OK
    assert err == ""
    key = json.loads(out)["idempotency_key"]
    assert key.startswith("acp-cli:automation-trigger:")
    assert recorder.calls[0]["idempotency_key"] == key


def test_uncertain_trigger_error_exposes_generated_key_for_safe_retry(tmp_path):
    def disconnected(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("internal transport detail", request=request)

    code, out, err = invoke(
        tmp_path, ["automations", "trigger", "a-1", "--json"], disconnected
    )

    assert code == ExitCode.NETWORK
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "network"
    assert error["idempotency_key"].startswith("acp-cli:automation-trigger:")
    assert error["recovery"] == "retry_automation_trigger_with_same_key"
    assert "internal transport detail" not in err


def test_trigger_http_5xx_keeps_status_and_key_for_safe_retry(tmp_path):
    recorder = Recorder((503, {"detail": "planificateur indisponible"}))

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "trigger",
            "a-1",
            "--idempotency-key",
            "retry-503",
            "--json",
        ],
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error == {
        "code": "api",
        "message": (
            "résultat du déclenchement incertain ; rejouez `acp automations trigger` "
            "avec la même --idempotency-key"
        ),
        "idempotency_key": "retry-503",
        "recovery": "retry_automation_trigger_with_same_key",
        "status": 503,
    }


def test_trigger_http_408_is_also_uncertain_and_keeps_the_key(tmp_path):
    recorder = Recorder((408, {"detail": "délai amont"}))

    code, out, err = invoke(
        tmp_path,
        [
            "automations", "trigger", "a-1",
            "--idempotency-key", "retry-408", "--json",
        ],
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["idempotency_key"] == "retry-408"
    assert error["status"] == 408
    assert error["recovery"] == "retry_automation_trigger_with_same_key"


def test_trigger_returns_nonzero_when_no_mission_was_launched(tmp_path):
    recorder = Recorder((201, {**RUN, "outcome": "skipped_concurrency"}))

    code, out, err = invoke(
        tmp_path, ["automations", "trigger", "a-1", "--json"], recorder
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "automation_skipped_concurrency"
    assert error["run"]["outcome"] == "skipped_concurrency"
    assert error["run"]["idempotency_key"].startswith("acp-cli:automation-trigger:")


@pytest.mark.parametrize(
    "args,response",
    [
        (["list"], [{"id": "a-1", "enabled": False}]),
        (["show", "a-1"], {"id": "a-1"}),
        (["show", "a-1"], {**DETAIL, "mission_template": {}}),
        (["enable", "a-1"], {**DETAIL, "enabled": False}),
        (["disable", "a-1"], {**DETAIL, "enabled": True}),
        (["runs", "a-1"], [{"id": "run-only"}]),
        (["calendar"], [{"occurs_at_utc": "not-a-date"}]),
    ],
)
def test_incomplete_success_responses_never_return_exit_zero(tmp_path, args, response):
    recorder = Recorder((200, response))

    code, out, err = invoke(
        tmp_path, ["automations", *args, "--json"], recorder
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "client"


def test_incomplete_trigger_response_is_uncertain_and_keeps_the_key(tmp_path):
    recorder = Recorder((201, {"id": "run-only", "automation_id": "a-1"}))

    code, out, err = invoke(
        tmp_path,
        [
            "automations", "trigger", "a-1",
            "--idempotency-key", "protocol-retry", "--json",
        ],
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "client"
    assert error["idempotency_key"] == "protocol-retry"


def test_api_validation_error_keeps_status_and_server_message(tmp_path):
    recorder = Recorder((422, {"detail": "expression cron invalide"}))

    code, out, err = invoke(
        tmp_path,
        ["automations", "enable", "a-1", "--json"],
        recorder,
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err) == {
        "error": {
            "code": "api",
            "message": "expression cron invalide",
            "status": 422,
        }
    }


@pytest.mark.parametrize(
    "args,fragment",
    [
        (["update", "a-1"], "au moins une modification"),
        (["update", "a-1", "--timezone", "Europe/Paris"], "requis ensemble"),
        (
            ["update", "a-1", "--schedule-kind", "cron", "--expression", "0 9 * * *"],
            "--timezone est requis",
        ),
        (
            [
                "create", "--project", "p-1", "--name", "Routine",
                "--schedule-kind", "interval", "--expression", "30s",
                "--template", json.dumps(TEMPLATE),
            ],
            "compris entre 60",
        ),
        (["update", "a-1", "--max-concurrent-runs", "6"], "compris entre 1 et 5"),
        (["list", "--limit", "0"], "compris entre 1 et 500"),
        (
            ["calendar", "--start", "2026-09-01T00:00:00"],
            "doit porter un décalage UTC",
        ),
        (
            [
                "calendar",
                "--start",
                "2026-10-01T00:00:00Z",
                "--end",
                "2026-09-01T00:00:00Z",
            ],
            "postérieur",
        ),
        (
            [
                "create",
                "--project",
                "p-1",
                "--name",
                "Routine",
                "--schedule-kind",
                "cron",
                "--expression",
                "0 9 * * *",
                "--template",
                "[]",
            ],
            "objet JSON",
        ),
    ],
)
def test_invalid_automation_arguments_fail_before_http(tmp_path, args, fragment):
    code, out, err = invoke(
        tmp_path, ["automations", *args, "--json"], never
    )

    assert code == ExitCode.USAGE
    assert out == ""
    error = json.loads(err)["error"]
    assert error["code"] == "usage"
    assert fragment in error["message"]


def test_malformed_template_never_echoes_its_content(tmp_path):
    malformed = '{"private_token":"do-not-log",}'

    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "create",
            "--project",
            "p-1",
            "--name",
            "Routine",
            "--schedule-kind",
            "cron",
            "--expression",
            "0 9 * * *",
            "--template",
            malformed,
            "--json",
        ],
        never,
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert "do-not-log" not in err
    assert "gabarit JSON invalide" in json.loads(err)["error"]["message"]


@pytest.mark.parametrize(
    "secret_args",
    [
        ["D_never_echo_this_webhook_secret_12345"],
        ["--secret", "D_never_echo_this_webhook_secret_12345"],
    ],
)
def test_webhook_secret_is_never_accepted_or_echoed_from_argv(
    tmp_path, secret_args
):
    secret = "D_never_echo_this_webhook_secret_12345"
    code, out, err = invoke(
        tmp_path,
        [
            "automations",
            "webhook",
            "rotate",
            "a-1",
            *secret_args,
            "--json",
        ],
        never,
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert secret not in err
    assert "--secret-env ou --secret-file" in err


@pytest.mark.parametrize(
    "extra,environ,fragment",
    [
        (["--secret-env", "MISSING_WEBHOOK_SECRET"], {}, "variable"),
        (["--secret-env", "bad-name"], {}, "nom de variable"),
        (
            ["--secret-env", "ACP_TEST_WEBHOOK_SECRET"],
            {"ACP_TEST_WEBHOOK_SECRET": "A" * 42},
            "43 à 200",
        ),
        (
            ["--secret-env", "ACP_TEST_WEBHOOK_SECRET"],
            {"ACP_TEST_WEBHOOK_SECRET": "A" * 45},
            "base64url",
        ),
    ],
)
def test_invalid_webhook_secret_sources_fail_before_http(
    tmp_path, extra, environ, fragment
):
    code, out, err = invoke(
        tmp_path,
        ["automations", "webhook", "rotate", "a-1", *extra, "--json"],
        never,
        environ=environ,
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert fragment in json.loads(err)["error"]["message"]
