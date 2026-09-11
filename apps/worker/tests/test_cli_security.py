import argparse
import sys
from dataclasses import replace
from pathlib import Path

import httpx

from acp_worker.cli import _doctor, _register, main as cli_main
from acp_worker.config import WorkerConfig
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
        local_runner=None,
    )


def register_args(
    *, real: bool = False, max_concurrency: int | None = None
) -> argparse.Namespace:
    return argparse.Namespace(
        name=None,
        capabilities=["git"],
        max_concurrency=max_concurrency,
        real=real,
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
        request_payload.update(kwargs["json"])  # type: ignore[arg-type]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "worker_id": "worker-1",
                "token": "worker-secret",
                "token_expires_at": "2030-01-01T00:00:00Z",
                "heartbeat_interval_seconds": 15,
            },
        )

    monkeypatch.setattr("acp_worker.cli.httpx.post", post)

    assert _register(config(tmp_path), register_args()) == 0
    credentials = load_credentials(tmp_path, "https://API.EXAMPLE:443/")
    assert credentials is not None
    assert credentials.api_origin == "https://api.example"
    assert request_payload["simulation"] is True


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
        if url.endswith("/v1/providers/hermes/health"):
            assert kwargs["headers"] == {"Authorization": "Bearer gateway-secret"}
            body = {"provider_id": "hermes", "available": True}
        else:
            body = {"status": "ok"}
        return httpx.Response(200, request=httpx.Request("GET", url), json=body)

    monkeypatch.setattr("acp_worker.cli.httpx.get", get)
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda url, **_kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json={}
        ),
    )

    assert _doctor(worker_config) == 0
    report = capsys.readouterr().out
    assert '"provider": "ok"' in report


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
