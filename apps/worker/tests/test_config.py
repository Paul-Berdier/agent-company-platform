from pathlib import Path

import pytest

from acp_worker.config import WorkerConfig, WorkerConfigurationError


def base_config(**overrides: object) -> WorkerConfig:
    values: dict[str, object] = {
        "api_url": "https://api.example",
        "gateway_url": "https://gateway.example",
        "gateway_service_token": None,
        "provider_id": "hermes",
        "poll_interval": 2.0,
        "step_seconds": 3.0,
        "state_dir": Path("."),
        "name": "test-worker",
        "max_concurrency": 1,
        "simulation": True,
        "registration_token": None,
    }
    values.update(overrides)
    return WorkerConfig(**values)  # type: ignore[arg-type]


def configure_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACP_API_URL", "https://api.example")
    monkeypatch.setenv("ACP_PROVIDER_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("ACP_WORKER_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("ACP_WORKER_RUNNER_ARGV_JSON", raising=False)
    monkeypatch.delenv("ACP_WORKER_RUN_ROOT", raising=False)


def test_origins_are_normalized_and_http_is_limited_to_loopback():
    config = base_config(
        api_url="https://API.EXAMPLE:443/",
        gateway_url="http://[::1]:80/",
    )

    assert config.api_url == "https://api.example"
    assert config.gateway_url == "http://[::1]"


@pytest.mark.parametrize("field", ["api_url", "gateway_url"])
def test_external_http_origin_is_rejected(field: str):
    with pytest.raises(WorkerConfigurationError, match="HTTPS"):
        base_config(**{field: "http://service.example"})


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@api.example",
        "https://api.example?token=secret",
        "https://api.example?",
        "https://api.example#fragment",
        "https://api.example#",
        "https://api.example/v1",
        "https://api.example%2f.evil",
        "https://api_example",
        "https://api.example:0",
    ],
)
def test_origin_rejects_userinfo_query_fragment_and_path(url: str):
    with pytest.raises(WorkerConfigurationError):
        base_config(api_url=url)


@pytest.mark.parametrize("value", ["", "true", "false", "2", " 1", "1 "])
def test_simulation_environment_is_strict(
    value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_SIMULATION", value)

    with pytest.raises(WorkerConfigurationError, match="uniquement 0 ou 1"):
        WorkerConfig.from_env()


@pytest.mark.parametrize("value, expected", [("0", False), ("1", True)])
def test_simulation_environment_accepts_only_binary_values(
    value: str,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_SIMULATION", value)

    assert WorkerConfig.from_env().simulation is expected


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "0", "301"])
def test_poll_interval_is_finite_and_bounded(
    value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_POLL_INTERVAL", value)

    with pytest.raises(WorkerConfigurationError, match="POLL_INTERVAL"):
        WorkerConfig.from_env()


@pytest.mark.parametrize("value", ["nan", "inf", "-0.1", "3601"])
def test_step_seconds_is_finite_and_bounded(
    value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_STEP_SECONDS", value)

    with pytest.raises(WorkerConfigurationError, match="STEP_SECONDS"):
        WorkerConfig.from_env()


@pytest.mark.parametrize("value", ["0", "33", "1.5", "not-an-int"])
def test_max_concurrency_is_strictly_bounded(
    value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_MAX_CONCURRENCY", value)

    with pytest.raises(WorkerConfigurationError, match="MAX_CONCURRENCY"):
        WorkerConfig.from_env()


def test_direct_boolean_timing_values_are_rejected():
    with pytest.raises(WorkerConfigurationError, match="POLL_INTERVAL"):
        base_config(poll_interval=True)
    with pytest.raises(WorkerConfigurationError, match="STEP_SECONDS"):
        base_config(step_seconds=False)
