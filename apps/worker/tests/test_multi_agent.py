"""Dépôts Git isolés réels et CLIs synthétiques ; aucun modèle consommé."""

import asyncio
import json
import subprocess
from pathlib import Path
from time import monotonic

import httpx
import pytest

from acp_worker.config import WorkerConfig
from acp_worker.executors import ExecutorConfig, ExecutorResult, ExecutorSpec
from acp_worker.multi_agent import run_team, validate_graph, prepare_worktree
from acp_worker.main import process
from acp_worker.local_log import WorkerLogger
from acp_worker.state import WorkerCredentials


def setup(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    (root / "source.txt").write_text("initial\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=NUL", "commit", "-qm", "fixture"], check=True)
    binary = tmp_path / "fake.exe"
    binary.write_bytes(b"unused fixture")
    auth_codex = tmp_path / "auth-codex"
    auth_claude = tmp_path / "auth-claude"
    auth_codex.mkdir()
    auth_claude.mkdir()
    executors = ExecutorConfig(codex=ExecutorSpec(binary, auth_codex), claude=ExecutorSpec(binary, auth_claude), project_roots={"project-1": root})
    config = WorkerConfig(api_url="https://api.test", gateway_url="https://gateway.test", provider_id="hermes",
                          gateway_service_token="fixture", state_dir=tmp_path / "state", executors=executors,
                          poll_interval=.01, step_seconds=0, name="fixture", max_concurrency=1, simulation=False, registration_token=None)
    credentials = WorkerCredentials("worker-1", "fixture", "https://api.test", "fixture", ["agent_team", "codex_cli", "claude_code"], 1, False, "2030-01-01T00:00:00Z", project_id="project-1")
    mission = {"objective": "Travail réparti", "expected_outcome": "Preuve conservée", "acceptance_criteria": ["preuve"],
               "autonomy": {"mode": "supervised", "allowed_actions": [], "forbidden_actions": [], "approval_required_actions": []},
               "resources": [{"kind": "project_workspace", "identifier": "project-1", "access": "write", "description": "fixture"}],
               "budget": {"max_cost": None, "max_tokens": None, "max_tool_calls": 5, "currency": "EUR"},
               "execution": {"mode": "multi_agent", "executors": ["codex_cli", "claude_code"], "max_concurrency": 2}}
    return config, credentials, mission, root


def plan():
    return {"steps": [{"id": "write", "title": "Écrire", "executor": "codex_cli", "depends_on": []},
                      {"id": "read", "title": "Lire", "executor": "claude_code", "depends_on": []},
                      {"id": "review", "title": "Vérifier", "executor": "claude_code", "depends_on": ["write", "read"]}]}


def ledger(request):
    return httpx.Response(200, json={"accepted": True, "idempotent": False, "permit_allowed": True,
        "verdict": {"state": "ok", "measured": True, "limit_reached": None, "cost": None, "currency": "EUR",
                    "tokens_input": None, "tokens_output": None, "tool_calls": 1, "usage_reported": False, "estimated": False}})


def completed(executor, text):
    return ExecutorResult(executor, 0, 1, "a" * 64, "b" * 64, 30, 0,
                          output={"text": text, "truncated": False, "complete": True})


async def test_two_agents_run_concurrently_in_distinct_worktrees_then_dependency(tmp_path, monkeypatch):
    config, credentials, mission, root = setup(tmp_path)
    active = 0
    peak = 0
    first_two = asyncio.Event()
    calls = []
    finished = set()
    snapshots = []

    async def fake_cli(executor, project_id, path, prompt, **kwargs):
        nonlocal active, peak
        workspace = kwargs["config"].project_path(project_id)
        calls.append((executor, workspace))
        active += 1
        peak = max(peak, active)
        try:
            if len(calls) <= 2:
                if active == 2:
                    first_two.set()
                await asyncio.wait_for(first_two.wait(), 5)
                if executor == "codex_cli":
                    assert kwargs["allow_writes"] is True
                    (workspace / "source.txt").write_text("modified by fixture\n")
                else:
                    assert kwargs["allow_writes"] is False
                finished.add(executor)
            else:
                assert finished == {"codex_cli", "claude_code"}
                assert "Réponse codex_cli" in prompt and "modified by fixture" in prompt
            return completed(executor, "Réponse " + executor)
        finally:
            active -= 1

    async def publish(value):
        snapshots.append(value)
        await asyncio.sleep(0)

    monkeypatch.setattr("acp_worker.multi_agent.run_executor", fake_cli)
    async with httpx.AsyncClient(transport=httpx.MockTransport(ledger)) as client:
        kwargs = dict(attempt_id="attempt-team", fencing_token=1, project_id="project-1", mission=mission,
                      plan=plan(), max_agents=3, deadline=monotonic() + 20, on_progress=lambda _: None, publish=publish)
        result = await run_team(client, config, credentials, **kwargs)
        replay = await run_team(client, config, credentials, **kwargs)
    assert result["runner_status"] == "succeeded"
    assert result["technical_validation"] == "passed"
    assert result["spawned_agents"] == 3
    assert replay["runner_status"] == "blocked"
    assert peak == 2 and active == 0 and len(calls) == 3
    assert len({workspace for _, workspace in calls}) == 3
    assert (root / "source.txt").read_text() == "initial\n"
    assert "modified by fixture" in result["steps"][0]["workspace"]["diff"]
    assert all(item["workspace"]["merged"] is False for item in result["steps"])
    assert len(snapshots) >= 6


async def test_stop_cancels_all_children_and_retains_checkpoint(tmp_path, monkeypatch):
    config, credentials, mission, _ = setup(tmp_path)
    started = asyncio.Event()
    active = 0
    calls = 0

    async def fake_cli(*args, **kwargs):
        nonlocal active, calls
        active += 1
        calls += 1
        try:
            if active == 2:
                started.set()
            await asyncio.Event().wait()
        finally:
            active -= 1

    async def publish(_):
        pass

    monkeypatch.setattr("acp_worker.multi_agent.run_executor", fake_cli)
    async with httpx.AsyncClient(transport=httpx.MockTransport(ledger)) as client:
        kwargs = dict(attempt_id="cancelled-team", fencing_token=1, project_id="project-1", mission=mission,
                      plan=plan(), max_agents=3, deadline=monotonic() + 20, on_progress=lambda _: None, publish=publish)
        pending = asyncio.create_task(run_team(client, config, credentials, **kwargs))
        await asyncio.wait_for(started.wait(), 10)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        result = await run_team(client, config, credentials, **kwargs)
    assert active == 0 and calls == 2
    assert result["runner_status"] == "blocked"
    assert result["spawned_agents"] == 2


@pytest.mark.parametrize("mutation", ["cycle", "missing", "executor", "duplicate", "quota"])
def test_invalid_graph_is_refused_before_any_effect(mutation):
    value = plan()
    limit = 3
    if mutation == "cycle":
        value["steps"][0]["depends_on"] = ["review"]
    elif mutation == "missing":
        value["steps"][0]["depends_on"] = ["absent"]
    elif mutation == "executor":
        value["steps"][0]["executor"] = "unknown"
    elif mutation == "duplicate":
        value["steps"][1]["id"] = "write"
    else:
        limit = 2
    with pytest.raises(RuntimeError):
        validate_graph(value, {"executors": ["codex_cli", "claude_code"]}, limit)


async def test_git_include_cannot_hide_a_checkout_filter(tmp_path):
    config, _, _, root = setup(tmp_path)
    hidden = tmp_path / "included.gitconfig"
    hidden.write_text('[filter "fixture"]\n\tsmudge = forbidden-command\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "config", "include.path", str(hidden)], check=True)
    with pytest.raises(RuntimeError, match="inclusions Git"):
        await prepare_worktree(config, "project-1", "attempt", "step", monotonic()+5)
    assert not (config.state_dir / "team-worktrees").exists()


async def test_process_routes_team_and_passes_all_outputs_to_real_evaluation_contract(tmp_path, monkeypatch):
    config, credentials, mission, _ = setup(tmp_path)
    mission.update(id="task-1", duration_seconds=60)
    claim = {"task": {"id": "task-1", "title": "Équipe", "meta": {}}, "task_run": {"id": "run-1"},
             "agent": {"name": "Équipe"}, "session": {"session_id": "session-1", "project_id": "project-1"},
             "attempt_id": "run-1", "attempt_number": 1, "fencing_token": 9, "stop_requested": False,
             "required_capabilities": credentials.capabilities, "mission": mission, "execution_limits": {"max_agents": 3}}
    patches, evaluations, invocations = [], [], []

    async def cli(executor, *args, **kwargs):
        invocations.append(executor)
        return completed(executor, "réponse " + executor)

    def api(request):
        if "/budget/" in request.url.path:
            return ledger(request)
        if request.method == "PATCH": patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    def gateway(request):
        operation = request.url.path.split("/operations/")[1].split("/")[0]
        if request.method == "POST":
            payload = json.loads(request.content)
            if operation == "plan":
                assert payload["context"]["execution"] == mission["execution"]
                assert payload["context"]["execution_limits"] == {"max_agents": 3}
            else:
                evaluations.append(payload)
        result = {"plan_id": "plan-team", **plan()} if operation == "plan" else {"approved": True, "provider_id": "hermes"}
        return httpx.Response(200, json={"provider_id": "hermes", "operation": operation, "run_id": operation,
            "status": "completed", "result": result, "error": None, "replayed": False})

    monkeypatch.setattr("acp_worker.multi_agent.run_executor", cli)
    async with httpx.AsyncClient(transport=httpx.MockTransport(api)) as api_client, httpx.AsyncClient(transport=httpx.MockTransport(gateway)) as gateway_client:
        await process(api_client, gateway_client, config, credentials, claim, WorkerLogger(config.state_dir))
    assert patches[-1]["status"] == "succeeded"
    assert patches[-1]["result"]["spawned_agents"] == 3
    assert invocations.count("codex_cli") == 1 and invocations.count("claude_code") == 2
    assert len(evaluations[0]["produced_output"]["execution_evidence_all"]) == 3
    assert len(evaluations[0]["produced_output"]["output"]["steps"]) == 3
