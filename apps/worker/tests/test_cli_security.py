import argparse
from pathlib import Path

import httpx

from acp_worker.cli import _register, main as cli_main
from acp_worker.config import WorkerConfig
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
