import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import httpx

from acp_worker.cli import _doctor, _register, main as cli_main
from acp_worker.config import WorkerConfig
from acp_worker.executors import (
    ExecutorCleanupError,
    ExecutorConfig,
    ExecutorSpec,
)
from acp_worker.local_runner import LocalRunnerConfig
from acp_worker.state import WorkerCredentials, load_credentials, save_credentials


def config(
    tmp_path: Path, *, simulation: bool = True, max_concurrency: int = 1
) -> WorkerConfig:
    return WorkerConfig(
        api_url="https://api.example",
        gateway_url="https://gateway.example",
        gateway_service_token=None,
        provider_id="hermes",
        poll_interval=2.0,
        step_seconds=0.0,
        state_dir=tmp_path,
        name="test-worker",
        max_concurrency=max_concurrency,
        simulation=simulation,
        registration_token="registration-secret",
        project_id="project-1",
        local_runner=None,
    )


def register_args(
    *,
    real: bool = False,
    max_concurrency: int | None = None,
    project_id: str | None = None,
    global_access: bool | None = None,
    capabilities: list[str] | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        name=None,
        capabilities=capabilities or ["git"],
        max_concurrency=max_concurrency,
        real=real,
        project_id=project_id,
        global_access=global_access,
    )


def agent_only_config(
    tmp_path: Path,
    *,
    executor: str = "codex_cli",
    project_id: str = "project-1",
) -> WorkerConfig:
    project = tmp_path / f"workspace-{project_id}"
    auth = tmp_path / f"auth-{executor}"
    executable = tmp_path / "bin" / f"{executor}.exe"
    project.mkdir()
    auth.mkdir()
    executable.parent.mkdir(exist_ok=True)
    executable.write_bytes(b"test")
    spec = ExecutorSpec(executable=executable, auth_directory=auth)
    return replace(
        config(tmp_path, simulation=False),
        executors=ExecutorConfig(
            codex=spec if executor == "codex_cli" else None,
            claude=spec if executor == "claude_code" else None,
            project_roots={project_id: project},
        ),
    )


def test_register_checks_runner_when_environment_disables_simulation(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    assert _register(config(tmp_path, simulation=False), register_args()) == 2
    assert "Mode réel refusé" in capsys.readouterr().err


def test_register_real_flag_rejects_the_mock_evaluator(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )
    real_config = replace(
        config(tmp_path),
        provider_id="mock",
        local_runner=LocalRunnerConfig(
            argv=(sys.executable, "-V"),
            run_root=tmp_path / "runs",
        ),
    )

    assert _register(real_config, register_args(real=True)) == 2
    assert "mock est interdit" in capsys.readouterr().err


def test_register_rejects_explicit_zero_concurrency(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    assert _register(config(tmp_path), register_args(max_concurrency=0)) == 2
    assert "entre 1 et 32" in capsys.readouterr().err


def test_registration_persists_the_normalized_api_origin(tmp_path: Path, monkeypatch):
    request_payload: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> httpx.Response:
        assert kwargs["trust_env"] is False
        request_payload.update(kwargs["json"])  # type: ignore[arg-type]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "worker_id": "worker-1",
                "token": "worker-secret",
                "token_expires_at": "2030-01-01T00:00:00Z",
                "heartbeat_interval_seconds": 15,
                "project_id": "project-1",
                "global_access": False,
            },
        )

    monkeypatch.setattr("acp_worker.cli.httpx.post", post)

    assert _register(config(tmp_path), register_args()) == 0
    credentials = load_credentials(tmp_path, "https://API.EXAMPLE:443/")
    assert credentials is not None
    assert credentials.api_origin == "https://api.example"
    assert request_payload["simulation"] is True
    assert request_payload["project_id"] == "project-1"
    assert request_payload["global_access"] is False
    assert credentials.project_id == "project-1"
    assert credentials.global_access is False


def test_register_requires_an_explicit_scope_before_http(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    assert _register(replace(config(tmp_path), project_id=None), register_args()) == 2
    assert "Périmètre worker requis" in capsys.readouterr().err


def test_register_refuses_a_response_with_a_different_scope(
    tmp_path: Path, monkeypatch, capsys
):
    def post(url: str, **_kwargs: object) -> httpx.Response:
        return httpx.Response(
            201,
            request=httpx.Request("POST", url),
            json={
                "worker_id": "worker-1",
                "token": "worker-secret",
                "token_expires_at": "2030-01-01T00:00:00Z",
                "heartbeat_interval_seconds": 15,
                "project_id": "project-2",
                "global_access": False,
            },
        )

    monkeypatch.setattr("acp_worker.cli.httpx.post", post)

    assert _register(config(tmp_path), register_args()) == 1
    assert "périmètre renvoyé diffère" in capsys.readouterr().err
    assert not (tmp_path / "worker.json").exists()


def _save_simulation_credentials(tmp_path: Path) -> None:
    save_credentials(
        tmp_path,
        WorkerCredentials(
            worker_id="worker-1",
            token="worker-secret",
            api_origin="https://api.example",
            name="test-worker",
            capabilities=["git"],
            max_concurrency=1,
            simulation=True,
            token_expires_at="2030-01-01T00:00:00Z",
            project_id="project-1",
        ),
    )


def test_doctor_requires_an_authenticated_available_provider(
    tmp_path: Path, monkeypatch, capsys
):
    _save_simulation_credentials(tmp_path)
    worker_config = replace(config(tmp_path), gateway_service_token=None)

    monkeypatch.setattr(
        "acp_worker.cli.httpx.get",
        lambda url, **_kwargs: httpx.Response(
            200, request=httpx.Request("GET", url), json={"status": "ok"}
        ),
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda url, **_kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json={}
        ),
    )

    assert _doctor(worker_config) == 1
    report = capsys.readouterr().out
    assert '"gateway": "ok"' in report
    assert '"provider": "missing_service_token"' in report


def test_doctor_verifies_provider_readiness_with_the_service_token(
    tmp_path: Path, monkeypatch, capsys
):
    _save_simulation_credentials(tmp_path)
    worker_config = replace(config(tmp_path), gateway_service_token="gateway-secret")

    def get(url: str, **kwargs: object) -> httpx.Response:
        assert kwargs["trust_env"] is False
        if url.endswith("/v1/providers/hermes/health"):
            assert kwargs["headers"] == {"Authorization": "Bearer gateway-secret"}
            body = {"provider_id": "hermes", "available": True}
        else:
            body = {"status": "ok"}
        return httpx.Response(200, request=httpx.Request("GET", url), json=body)

    monkeypatch.setattr("acp_worker.cli.httpx.get", get)

    def post(url: str, **kwargs: object) -> httpx.Response:
        assert kwargs["trust_env"] is False
        return httpx.Response(200, request=httpx.Request("POST", url), json={})

    monkeypatch.setattr("acp_worker.cli.httpx.post", post)

    assert _doctor(worker_config) == 0
    report = capsys.readouterr().out
    assert '"provider": "ok"' in report
    assert '"api_readiness": "ready"' in report
    assert '"scope": "project:project-1"' in report
    assert '"agent_executors": []' in report
    assert '"executor_project_roots": 0' in report


def test_doctor_fails_when_the_configured_provider_is_unavailable(
    tmp_path: Path, monkeypatch, capsys
):
    _save_simulation_credentials(tmp_path)
    worker_config = replace(config(tmp_path), gateway_service_token="gateway-secret")

    def get(url: str, **_kwargs: object) -> httpx.Response:
        body = (
            {"provider_id": "hermes", "available": False}
            if url.endswith("/v1/providers/hermes/health")
            else {"status": "ok"}
        )
        return httpx.Response(200, request=httpx.Request("GET", url), json=body)

    monkeypatch.setattr("acp_worker.cli.httpx.get", get)
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda url, **_kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json={}
        ),
    )

    assert _doctor(worker_config) == 1
    assert '"provider": "unavailable"' in capsys.readouterr().out


def _doctor_get_with_readiness(status_code: int, body: object):
    """Simule une API vivante dont ``/ready`` répond ``status_code`` avec ``body``."""

    def get(url: str, **kwargs: object) -> httpx.Response:
        assert kwargs["trust_env"] is False
        request = httpx.Request("GET", url)
        if url.endswith("/ready"):
            return httpx.Response(status_code, request=request, json=body)
        if url.endswith("/v1/providers/hermes/health"):
            return httpx.Response(
                200, request=request, json={"provider_id": "hermes", "available": True}
            )
        return httpx.Response(200, request=request, json={"status": "ok"})

    return get


def test_doctor_reports_a_degraded_api_with_its_failed_checks(
    tmp_path: Path, monkeypatch, capsys
):
    _save_simulation_credentials(tmp_path)
    worker_config = replace(config(tmp_path), gateway_service_token="gateway-secret")
    monkeypatch.setattr(
        "acp_worker.cli.httpx.get",
        _doctor_get_with_readiness(
            503,
            {
                "status": "degraded",
                "checks": {
                    "database": {"ok": True, "reason": "base joignable"},
                    "migrations": {"ok": False, "reason": "schéma hors version"},
                    "skills_storage": {"ok": False, "reason": "racine non inscriptible"},
                    "outbox": {"ok": True, "reason": "relais désactivé"},
                },
            },
        ),
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda url, **_kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json={}
        ),
    )

    assert _doctor(worker_config) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["api"] == "ok"
    assert report["api_readiness"] == "degraded"
    assert report["api_readiness_failed"] == ["migrations", "skills_storage"]
    assert report["authentication"] == "ok"


def test_doctor_never_confuses_a_missing_ready_route_with_readiness(
    tmp_path: Path, monkeypatch, capsys
):
    _save_simulation_credentials(tmp_path)
    worker_config = replace(config(tmp_path), gateway_service_token="gateway-secret")
    monkeypatch.setattr(
        "acp_worker.cli.httpx.get",
        _doctor_get_with_readiness(404, {"detail": "Not Found"}),
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda url, **_kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json={}
        ),
    )

    assert _doctor(worker_config) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["api"] == "ok"
    assert report["api_readiness"] == "unavailable"
    assert "api_readiness_failed" not in report


def test_doctor_reports_a_degraded_api_without_a_readable_body(
    tmp_path: Path, monkeypatch, capsys
):
    _save_simulation_credentials(tmp_path)
    worker_config = replace(config(tmp_path), gateway_service_token="gateway-secret")

    def get(url: str, **_kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        if url.endswith("/ready"):
            return httpx.Response(503, request=request, content=b"<html>panne</html>")
        if url.endswith("/v1/providers/hermes/health"):
            return httpx.Response(
                200, request=request, json={"provider_id": "hermes", "available": True}
            )
        return httpx.Response(200, request=request, json={"status": "ok"})

    monkeypatch.setattr("acp_worker.cli.httpx.get", get)
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda url, **_kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json={}
        ),
    )

    assert _doctor(worker_config) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["api_readiness"] == "degraded"
    assert report["api_readiness_failed"] == []


def test_doctor_skips_readiness_when_the_api_is_unreachable(
    tmp_path: Path, monkeypatch, capsys
):
    _save_simulation_credentials(tmp_path)
    worker_config = replace(config(tmp_path), gateway_service_token="gateway-secret")
    requested: list[str] = []

    def get(url: str, **_kwargs: object) -> httpx.Response:
        requested.append(url)
        if url.endswith("/ready"):
            raise AssertionError("la readiness ne doit pas être interrogée")
        if url.startswith("https://api.example"):
            raise httpx.ConnectError("refusé", request=httpx.Request("GET", url))
        request = httpx.Request("GET", url)
        body = (
            {"provider_id": "hermes", "available": True}
            if url.endswith("/v1/providers/hermes/health")
            else {"status": "ok"}
        )
        return httpx.Response(200, request=request, json=body)

    monkeypatch.setattr("acp_worker.cli.httpx.get", get)

    assert _doctor(worker_config) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["api"] == "unreachable"
    assert report["api_readiness"] == "unchecked"
    assert not any(url.endswith("/ready") for url in requested)


def test_doctor_reports_legacy_credentials_without_scope(
    tmp_path: Path, monkeypatch, capsys
):
    save_credentials(
        tmp_path,
        WorkerCredentials(
            worker_id="legacy-worker",
            token="worker-secret",
            api_origin="https://api.example",
            name="legacy",
            capabilities=["git"],
            max_concurrency=1,
            simulation=True,
            token_expires_at="2030-01-01T00:00:00Z",
        ),
    )
    worker_config = replace(
        config(tmp_path), project_id=None, gateway_service_token="gateway-secret"
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    assert _doctor(worker_config) == 1
    report = capsys.readouterr().out
    assert '"scope": "missing"' in report
    assert '"execution": "invalid"' in report


def test_start_refuses_credentials_from_another_api_origin(
    tmp_path: Path, monkeypatch, capsys
):
    save_credentials(
        tmp_path,
        WorkerCredentials(
            worker_id="worker-1",
            token="worker-secret",
            api_origin="https://old-api.example",
            name="test-worker",
            capabilities=["git"],
            max_concurrency=1,
            simulation=True,
            token_expires_at="2030-01-01T00:00:00Z",
        ),
    )
    current_config = config(tmp_path)
    monkeypatch.setattr(
        "acp_worker.cli.WorkerConfig.from_env",
        classmethod(lambda cls: current_config),
    )

    assert cli_main(["start"]) == 2
    assert "autre origine API" in capsys.readouterr().err


def test_start_returns_failure_when_executor_cleanup_is_unconfirmed(
    tmp_path: Path, monkeypatch, capsys
):
    _save_simulation_credentials(tmp_path)
    current_config = config(tmp_path)

    async def stopped_worker(*_args, **_kwargs) -> None:
        raise ExecutorCleanupError("détail local")

    monkeypatch.setattr(
        "acp_worker.cli.WorkerConfig.from_env",
        classmethod(lambda cls: current_config),
    )
    monkeypatch.setattr("acp_worker.cli.run_forever", stopped_worker)

    assert cli_main(["start"]) == 1
    stderr = capsys.readouterr().err
    assert "arrêté par sécurité" in stderr
    assert "détail local" not in stderr


def test_register_refuses_agent_capability_without_matching_executor(
    tmp_path: Path, monkeypatch, capsys
):
    project = tmp_path / "project"
    auth = tmp_path / "auth"
    executable = tmp_path / "bin" / "claude.exe"
    project.mkdir()
    auth.mkdir()
    executable.parent.mkdir()
    executable.write_bytes(b"test")
    claude_only = replace(
        config(tmp_path, simulation=False),
        executors=ExecutorConfig(
            claude=ExecutorSpec(executable=executable, auth_directory=auth),
            project_roots={"project-1": project},
        ),
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    result = _register(
        claude_only,
        register_args(real=True, capabilities=["codex_cli"]),
    )

    assert result == 2
    assert "codex_cli" in capsys.readouterr().err


def test_register_refuses_phantom_git_without_local_runner_before_http(
    tmp_path: Path, monkeypatch, capsys
):
    current_config = agent_only_config(tmp_path, executor="claude_code")
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    result = _register(
        current_config,
        register_args(real=True, capabilities=["git"]),
    )

    assert result == 2
    stderr = capsys.readouterr().err
    assert "git" in stderr
    assert "runner local" in stderr


def test_register_refuses_probe_only_on_an_agent_without_local_runner(
    tmp_path: Path, monkeypatch, capsys
):
    current_config = agent_only_config(tmp_path)
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    result = _register(
        current_config,
        register_args(real=True, capabilities=["mcp_stdio_probe"]),
    )

    assert result == 2
    stderr = capsys.readouterr().err
    assert "mcp_stdio_probe" in stderr
    assert "sonde stdio" in stderr


def test_register_refuses_global_agent_before_http(tmp_path: Path, monkeypatch, capsys):
    current_config = agent_only_config(tmp_path)
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    result = _register(
        current_config,
        register_args(
            real=True,
            global_access=True,
            capabilities=["codex_cli"],
        ),
    )

    assert result == 2
    assert "accès global est refusé" in capsys.readouterr().err


def test_doctor_refuses_stale_agent_scope_before_network(
    tmp_path: Path, monkeypatch, capsys
):
    current_config = agent_only_config(tmp_path, project_id="project-1")
    save_credentials(
        tmp_path,
        WorkerCredentials(
            worker_id="worker-1",
            token="worker-secret",
            api_origin="https://api.example",
            name="test-worker",
            capabilities=["codex_cli"],
            max_concurrency=1,
            simulation=False,
            token_expires_at="2030-01-01T00:00:00Z",
            project_id="project-2",
        ),
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("aucune requête ne doit partir")
        ),
    )

    assert _doctor(current_config) == 1
    report = capsys.readouterr().out
    assert '"execution": "invalid"' in report
    assert "project-2" in report


def test_start_refuses_persisted_global_agent_before_run_loop(
    tmp_path: Path, monkeypatch, capsys
):
    current_config = agent_only_config(tmp_path)
    save_credentials(
        tmp_path,
        WorkerCredentials(
            worker_id="worker-1",
            token="worker-secret",
            api_origin="https://api.example",
            name="test-worker",
            capabilities=["codex_cli"],
            max_concurrency=1,
            simulation=False,
            token_expires_at="2030-01-01T00:00:00Z",
            global_access=True,
        ),
    )
    monkeypatch.setattr(
        "acp_worker.cli.WorkerConfig.from_env",
        classmethod(lambda cls: current_config),
    )

    async def should_not_start(*_args, **_kwargs) -> None:
        raise AssertionError("la boucle worker ne doit pas démarrer")

    monkeypatch.setattr("acp_worker.cli.run_forever", should_not_start)

    assert cli_main(["start"]) == 2
    assert "accès global est refusé" in capsys.readouterr().err
