from pathlib import Path

import pytest

from acp_worker.executors import (
    claude_command,
    codex_command,
    resolve_project_path,
    restricted_environment,
)


def test_executor_commands_are_argument_lists_with_safe_modes():
    project = Path("C:/projects/example")
    codex = codex_command(project, "Run tests")
    assert codex[:3] == ["codex", "exec", "--json"]
    assert "--ephemeral" in codex
    assert codex[codex.index("--sandbox") + 1] == "workspace-write"
    assert "danger-full-access" not in codex

    claude = claude_command(project, "Inspect repository")
    assert claude[:2] == ["claude", "-p"]
    assert claude[claude.index("--permission-mode") + 1] == "plan"
    assert "--dangerously-skip-permissions" not in claude


def test_project_path_cannot_escape_root():
    root = Path.cwd().resolve()
    assert resolve_project_path(root, "apps/worker") == (root / "apps/worker").resolve()
    with pytest.raises(ValueError, match="sort"):
        resolve_project_path(root, "../")


def test_worker_secrets_are_not_forwarded(monkeypatch):
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", "worker-secret")
    monkeypatch.setenv("HERMES_SERVICE_TOKEN", "hermes-secret")
    monkeypatch.setenv("PATH", "safe-path")
    environment = restricted_environment()
    assert environment["PATH"] == "safe-path"
    assert "ACP_WORKER_REGISTRATION_TOKEN" not in environment
    assert "HERMES_SERVICE_TOKEN" not in environment
