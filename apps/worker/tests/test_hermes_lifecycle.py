"""Transport Hermes synthétique : aucun fournisseur authentifié n'est appelé."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from time import monotonic

import httpx
import pytest

from acp_worker.checkpoints import read_checkpoint, write_checkpoint
from acp_worker.executors import ExecutorCleanupError
from acp_worker.hermes_lifecycle import run_operation
from acp_worker.config import WorkerConfig


def config():
    return WorkerConfig(api_url="https://api.test", gateway_url="https://gateway.test",
        gateway_service_token="fixture", provider_id="hermes", poll_interval=0.1,
        step_seconds=0, state_dir=Path("."), name="test", max_concurrency=1,
        simulation=False, registration_token=None)


def envelope(status="completed", result=None):
    return {"provider_id": "hermes", "operation": "plan", "run_id": "run-test",
            "status": status, "result": result, "error": None, "replayed": False}


async def invoke(client, tmp_path, payload=None, seconds=2):
    return await run_operation(client, replace(config(), state_dir=tmp_path), attempt_id="attempt-1",
        operation="plan", payload=payload or {"goal": "test"}, headers={"Authorization": "Bearer fixture"},
        deadline=monotonic() + seconds)


async def test_lost_admission_reuses_key_body_and_persists_run_before_poll(tmp_path):
    admissions = []
    polls = []

    def handler(request):
        if request.method == "POST":
            admissions.append((request.headers["Idempotency-Key"], request.content))
            if len(admissions) == 1:
                raise httpx.ReadError("lost after commit", request=request)
            return httpx.Response(200, json=envelope(result=None))
        stored = read_checkpoint(replace(config(), state_dir=tmp_path), "attempt-1", "hermes-plan")
        assert stored["run_id"] == "run-test"
        assert "fixture" not in json.dumps(stored)
        polls.append(request)
        return httpx.Response(200, json=envelope(result={"plan_id": "p"}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await invoke(client, tmp_path) == {"plan_id": "p"}
        assert await invoke(client, tmp_path) == {"plan_id": "p"}
    assert len(admissions) == 2
    assert admissions[0] == admissions[1]
    assert len(polls) == 2


async def test_changed_body_and_expired_ambiguous_admission_never_start_new_run(tmp_path):
    def handler(request):
        return httpx.Response(200, json=envelope(result={"plan_id": "p"}))

    worker = replace(config(), state_dir=tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await invoke(client, tmp_path)
        with pytest.raises(RuntimeError, match="hors contexte"):
            await invoke(client, tmp_path, {"goal": "different"})
        state = read_checkpoint(worker, "attempt-1", "hermes-plan")
        state.update(started_at=0, run_id=None, status="admitting")
        write_checkpoint(worker, "attempt-1", "hermes-plan", state)
        with pytest.raises(ExecutorCleanupError):
            await invoke(client, tmp_path)


@pytest.mark.parametrize("approval", [False, True])
async def test_deadline_or_approval_stops_then_confirms_terminal(tmp_path, approval, monkeypatch):
    stopped = False
    admissions = 0
    polls_before_stop = 0
    polls_after_stop = 0
    clock = {"now": 1000.0}
    deadline = 1001.0
    # L'expiration dépend du scénario, jamais du temps de fsync ou de la charge
    # machine entre admission et lecture de l'approbation.
    monkeypatch.setattr("acp_worker.hermes_lifecycle.monotonic", lambda: clock["now"])
    monkeypatch.setattr("acp_worker.hermes_lifecycle._POLL_SECONDS", 0)

    def handler(request):
        nonlocal stopped, admissions, polls_before_stop, polls_after_stop
        if request.url.path.endswith("/stop"):
            stopped = True
            return httpx.Response(200, json={"run_id": "run-test", "status": "stopping"})
        if request.method == "POST":
            admissions += 1
            return httpx.Response(200, json=envelope("running"))
        if stopped:
            polls_after_stop += 1
            return httpx.Response(200, json=envelope("cancelled"))
        polls_before_stop += 1
        if not approval:
            clock["now"] = deadline + 1
        return httpx.Response(200, json=envelope("waiting_for_approval" if approval else "running"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError if approval else TimeoutError,
                           match="approbation indisponible" if approval else "durée globale"):
            await run_operation(client, replace(config(), state_dir=tmp_path), attempt_id="attempt-1",
                operation="plan", payload={"goal": "test"}, headers={"Authorization": "Bearer fixture"},
                deadline=deadline)
    assert admissions == 1 and polls_before_stop == 1
    assert stopped and polls_after_stop == 1
    assert read_checkpoint(replace(config(), state_dir=tmp_path), "attempt-1", "hermes-plan")["status"] == "cancelled"


async def test_unconfirmed_stop_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr("acp_worker.hermes_lifecycle._CLEANUP_SECONDS", 0.05)

    def handler(request):
        return httpx.Response(200, json=envelope("running"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExecutorCleanupError, match="non confirmé"):
            await invoke(client, tmp_path, seconds=0.01)
