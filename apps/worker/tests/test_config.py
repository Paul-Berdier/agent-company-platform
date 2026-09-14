import json
from pathlib import Path

import pytest

from acp_worker.config import WorkerConfig, WorkerConfigurationError
from acp_worker.executors import (
    CLAUDE_CONFIG_DIR_ENV,
    CLAUDE_ENABLED_ENV,
    CLAUDE_EXECUTABLE_ENV,
    CODEX_ENABLED_ENV,
    CODEX_EXECUTABLE_ENV,
    CODEX_HOME_ENV,
    PROJECTS_ENV,
    TERMINATE_GRACE_ENV,
    TIMEOUT_ENV,
    TOOL_PATH_ENV,
    ExecutorConfig,
    ExecutorSpec,
)
from acp_worker.web_tests import WebTestConfig


EXECUTOR_ENVIRONMENT = (
    CLAUDE_CONFIG_DIR_ENV,
    CLAUDE_ENABLED_ENV,
    CLAUDE_EXECUTABLE_ENV,
    CODEX_ENABLED_ENV,
    CODEX_EXECUTABLE_ENV,
    CODEX_HOME_ENV,
    PROJECTS_ENV,
    TERMINATE_GRACE_ENV,
    TIMEOUT_ENV,
    TOOL_PATH_ENV,
)


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
    monkeypatch.delenv("ACP_WORKER_PROJECT_ID", raising=False)
    monkeypatch.delenv("ACP_WORKER_GLOBAL_ACCESS", raising=False)
    for setting in EXECUTOR_ENVIRONMENT:
        monkeypatch.delenv(setting, raising=False)


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


@pytest.mark.parametrize("value", ["", "true", "2", " 1", "1 "])
def test_global_scope_environment_is_strict(
    value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_GLOBAL_ACCESS", value)

    with pytest.raises(WorkerConfigurationError, match="GLOBAL_ACCESS"):
        WorkerConfig.from_env()


def test_project_and_global_scope_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_PROJECT_ID", "project-1")
    monkeypatch.setenv("ACP_WORKER_GLOBAL_ACCESS", "1")

    with pytest.raises(WorkerConfigurationError, match="simultanément"):
        WorkerConfig.from_env()


def test_project_scope_is_trimmed_and_global_defaults_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_PROJECT_ID", "  project-1  ")

    config = WorkerConfig.from_env()

    assert config.project_id == "project-1"
    assert config.global_access is False


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


@pytest.mark.parametrize(
    "provider_id",
    ["", "Mock", " mock", "mock ", "../mock", "mock/provider", "mock?x=1"],
)
def test_provider_id_is_a_safe_lowercase_path_segment(provider_id: str):
    with pytest.raises(WorkerConfigurationError, match="ORCHESTRATOR_PROVIDER"):
        base_config(provider_id=provider_id)


def test_real_execution_rejects_the_mock_evaluator():
    config = base_config(provider_id="mock", local_runner=object())

    config.validate_execution_mode(simulation=True)
    with pytest.raises(WorkerConfigurationError, match="mock est interdit"):
        config.validate_execution_mode(simulation=False)


def test_worker_config_repr_never_contains_service_secrets():
    config = base_config(
        gateway_service_token="gateway-secret",
        registration_token="registration-secret",
    )

    rendered = repr(config)
    assert "gateway-secret" not in rendered
    assert "registration-secret" not in rendered


def test_worker_config_rejects_partial_executor_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv(CODEX_ENABLED_ENV, "1")

    with pytest.raises(WorkerConfigurationError, match="CODEX_EXECUTABLE"):
        WorkerConfig.from_env()


def test_worker_config_loads_valid_executor_allowlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    project = tmp_path / "project"
    auth = tmp_path / "auth"
    executable = tmp_path / "bin" / "codex.exe"
    project.mkdir()
    auth.mkdir()
    executable.parent.mkdir()
    executable.write_bytes(b"test")
    monkeypatch.setenv(CODEX_ENABLED_ENV, "1")
    monkeypatch.setenv(CODEX_EXECUTABLE_ENV, str(executable))
    monkeypatch.setenv(CODEX_HOME_ENV, str(auth))
    monkeypatch.setenv(PROJECTS_ENV, json.dumps({"project-1": str(project)}))

    config = WorkerConfig.from_env()

    assert config.executors.enabled_executors == frozenset({"codex_cli"})
    assert config.executors.project_path("project-1") == project.resolve()


def test_real_execution_accepts_an_executor_without_a_local_runner(tmp_path: Path):
    project = tmp_path / "project"
    auth = tmp_path / "auth"
    executable = tmp_path / "bin" / "codex.exe"
    project.mkdir()
    auth.mkdir()
    executable.parent.mkdir()
    executable.write_bytes(b"test")
    config = base_config(
        simulation=False,
        local_runner=None,
        executors=ExecutorConfig(
            codex=ExecutorSpec(executable=executable, auth_directory=auth),
            project_roots={"project-1": project},
        ),
    )

    config.validate_execution_mode(simulation=False)


def test_real_web_tests_still_require_a_local_output_runner(tmp_path: Path):
    project = tmp_path / "project"
    auth = tmp_path / "auth"
    executable = tmp_path / "bin" / "codex.exe"
    project.mkdir()
    auth.mkdir()
    executable.parent.mkdir()
    executable.write_bytes(b"test")
    config = base_config(
        simulation=False,
        local_runner=None,
        executors=ExecutorConfig(
            codex=ExecutorSpec(executable=executable, auth_directory=auth),
            project_roots={"project-1": project},
        ),
        web_tests=WebTestConfig(
            enabled=True,
            argv=(str(executable),),
            cwd=project,
        ),
    )

    with pytest.raises(WorkerConfigurationError, match="tests web réels"):
        config.validate_execution_mode(simulation=False)
