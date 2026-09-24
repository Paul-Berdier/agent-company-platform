import json
from pathlib import Path

import pytest

from acp_poste.config import (
    STATE_DIR_ENV,
    PosteConfig,
    PosteConfigurationError,
    default_state_dir,
    normalize_service_origin,
)
from acp_poste.executors import (
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


def configure_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(STATE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv("ACP_WORKER_RUNNER_ARGV_JSON", raising=False)
    monkeypatch.delenv("ACP_WORKER_RUN_ROOT", raising=False)
    monkeypatch.delenv("ACP_WORKER_SUBSCRIPTION_QUOTAS", raising=False)
    for setting in EXECUTOR_ENVIRONMENT:
        monkeypatch.delenv(setting, raising=False)


def test_origins_are_normalized_and_http_is_limited_to_loopback():
    assert normalize_service_origin("https://API.EXAMPLE:443/", setting="X") == "https://api.example"
    assert normalize_service_origin("http://[::1]:80/", setting="X") == "http://[::1]"
    assert normalize_service_origin("http://127.0.0.1:9119", setting="X") == "http://127.0.0.1:9119"


def test_external_http_origin_is_rejected():
    with pytest.raises(PosteConfigurationError, match="HTTPS"):
        normalize_service_origin("http://service.example", setting="X")


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
    with pytest.raises(PosteConfigurationError):
        normalize_service_origin(url, setting="X")


def test_the_state_directory_defaults_to_the_dedicated_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.delenv(STATE_DIR_ENV)

    config = PosteConfig.from_env()

    assert config.state_dir == default_state_dir()
    assert config.local_runner is None
    assert config.executors.enabled_executors == frozenset()


def test_poste_config_rejects_partial_executor_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    configure_environment(monkeypatch, tmp_path)
    monkeypatch.setenv(CODEX_ENABLED_ENV, "1")

    with pytest.raises(PosteConfigurationError, match="CODEX_EXECUTABLE"):
        PosteConfig.from_env()


def test_poste_config_loads_valid_executor_allowlist(
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

    config = PosteConfig.from_env()

    assert config.state_dir == tmp_path
    assert config.executors.enabled_executors == frozenset({"codex_cli"})
    assert config.executors.project_path("project-1") == project.resolve()
    assert config.diagnostic() == {
        "local_runner": "missing",
        "agent_executors": ["codex_cli"],
        "executor_project_roots": 1,
        "subscription_quotas": "disabled",
    }


def test_poste_config_refuses_foreign_component_types(tmp_path: Path):
    with pytest.raises(PosteConfigurationError, match="executors"):
        PosteConfig(state_dir=tmp_path, executors=object())  # type: ignore[arg-type]
    with pytest.raises(PosteConfigurationError, match="local_runner"):
        PosteConfig(state_dir=tmp_path, local_runner=object())  # type: ignore[arg-type]
