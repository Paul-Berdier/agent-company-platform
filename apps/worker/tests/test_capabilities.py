import json
from pathlib import Path

import pytest

from acp_worker import capabilities as capability_module
from acp_worker.capabilities import detect_capabilities, missing_capabilities
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


def test_missing_capabilities_is_deterministic():
    assert missing_capabilities(["git", "blender", "git"], ["git"]) == ["blender"]


def test_cli_presence_in_path_is_not_an_agent_capability(
    monkeypatch: pytest.MonkeyPatch,
):
    for setting in EXECUTOR_ENVIRONMENT:
        monkeypatch.delenv(setting, raising=False)
    monkeypatch.setattr(capability_module.shutil, "which", lambda executable: executable)

    capabilities = detect_capabilities(
        simulation=False, local_runner_configured=False
    )

    assert "codex_cli" not in capabilities
    assert "claude_code" not in capabilities
    assert "shell_restricted" not in capabilities
    assert "filesystem_project" not in capabilities
    assert "git" not in capabilities


def test_valid_opt_in_advertises_executor_only_in_real_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    for setting in EXECUTOR_ENVIRONMENT:
        monkeypatch.delenv(setting, raising=False)
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

    real_capabilities = detect_capabilities(
        simulation=False, local_runner_configured=False
    )
    assert "codex_cli" in real_capabilities
    assert "shell_restricted" not in real_capabilities
    assert "filesystem_project" not in real_capabilities
    assert "codex_cli" not in detect_capabilities(simulation=True)


def test_real_local_runner_advertises_generic_mission_capabilities(
    monkeypatch: pytest.MonkeyPatch,
):
    for setting in EXECUTOR_ENVIRONMENT:
        monkeypatch.delenv(setting, raising=False)
    monkeypatch.setattr(capability_module.shutil, "which", lambda _executable: None)

    capabilities = detect_capabilities(
        simulation=False, local_runner_configured=True
    )

    assert "filesystem_project" in capabilities
    assert "shell_restricted" in capabilities
