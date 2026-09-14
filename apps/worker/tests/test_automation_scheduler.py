"""Le worker cadence réellement le planificateur sans accéder à la base."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from acp_worker.automation_scheduler import (
    _lease_from_payload,
    automation_scheduler_loop,
)
from acp_worker.config import WorkerConfig
from acp_worker.local_log import WorkerLogger
from acp_worker.state import WorkerCredentials


def _config(tmp_path) -> WorkerConfig:
    return WorkerConfig(
        api_url="https://api.test",
        gateway_url="https://gateway.test",
        gateway_service_token="gateway-token",
        provider_id="mock",
        poll_interval=0.01,
        step_seconds=0,
        state_dir=tmp_path,
        name="scheduler-worker",
        max_concurrency=1,
        simulation=True,
        registration_token=None,
    )


def _credentials() -> WorkerCredentials:
    return WorkerCredentials(
        worker_id="worker-1",
        token="worker-token",
        api_origin="https://api.test",
        name="scheduler-worker",
        capabilities=[],
        max_concurrency=1,
        simulation=True,
        token_expires_at="2030-01-01T00:00:00Z",
        global_access=True,
    )


def test_lease_response_is_bound_to_process_and_worker():
    payload = {
        "worker_id": "worker-1",
        "holder_id": "a" * 32,
        "fencing_token": 7,
        "lease_expires_at": "2030-01-01T00:00:00Z",
    }
    assert (
        _lease_from_payload(payload, worker_id="worker-1", holder_id="a" * 32)
        == 7
    )
    with pytest.raises(ValueError, match="invalide"):
        _lease_from_payload(payload, worker_id="worker-2", holder_id="a" * 32)


async def test_project_scoped_worker_never_contacts_the_global_scheduler(tmp_path):
    requested = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(500)

    stop = asyncio.Event()
    scoped = WorkerCredentials(
        **{
            **_credentials().__dict__,
            "global_access": False,
            "project_id": "project-1",
        }
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await automation_scheduler_loop(
            client,
            _config(tmp_path),
            scoped,
            stop,
            WorkerLogger(tmp_path),
        )

    assert requested is False


async def test_loop_acquires_ticks_with_fence_and_releases(tmp_path):
    stop = asyncio.Event()
    requests: list[tuple[str, str | None]] = []
    holder: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal holder
        body = json.loads(request.content)
        holder = holder or body["holder_id"]
        assert body["holder_id"] == holder
        fence = request.headers.get("x-scheduler-fencing-token")
        requests.append((request.url.path, fence))
        if request.url.path.endswith("/lease"):
            return httpx.Response(
                200,
                json={
                    "worker_id": "worker-1",
                    "holder_id": holder,
                    "fencing_token": 4,
                    "lease_expires_at": (
                        datetime.now(UTC) + timedelta(seconds=45)
                    ).isoformat(),
                    "acquired": True,
                },
            )
        if request.url.path.endswith("/tick"):
            assert body["limit"] == 25
            stop.set()
            return httpx.Response(
                200,
                json={
                    "fencing_token": 4,
                    "reconciled": 0,
                    "disabled_after_failures": 0,
                    "examined": 1,
                    "launched": 1,
                    "replayed": 0,
                    "skipped_concurrency": 0,
                    "skipped_disabled": 0,
                    "catchup_skipped": 0,
                },
            )
        assert request.url.path.endswith("/lease/release")
        return httpx.Response(204)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer worker-token"},
    ) as client:
        await automation_scheduler_loop(
            client,
            _config(tmp_path),
            _credentials(),
            stop,
            WorkerLogger(tmp_path),
        )

    assert [path for path, _ in requests] == [
        "/workers/worker-1/automation-scheduler/lease",
        "/workers/worker-1/automation-scheduler/tick",
        "/workers/worker-1/automation-scheduler/lease/release",
    ]
    assert requests[1][1] == "4"
    assert requests[2][1] == "4"


async def test_stale_tick_drops_fence_and_reacquires(tmp_path):
    stop = asyncio.Event()
    lease_calls = 0
    tick_fences: list[str | None] = []
    holder: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal lease_calls, holder
        body = json.loads(request.content)
        holder = holder or body["holder_id"]
        if request.url.path.endswith("/lease"):
            lease_calls += 1
            fence = lease_calls
            return httpx.Response(
                200,
                json={
                    "worker_id": "worker-1",
                    "holder_id": holder,
                    "fencing_token": fence,
                    "lease_expires_at": "2030-01-01T00:00:00Z",
                    "acquired": True,
                },
            )
        if request.url.path.endswith("/tick"):
            tick_fences.append(request.headers.get("x-scheduler-fencing-token"))
            if len(tick_fences) == 1:
                return httpx.Response(409, json={"detail": "stale"})
            stop.set()
            return httpx.Response(
                200,
                json={
                    "fencing_token": 2,
                    "reconciled": 0,
                    "disabled_after_failures": 0,
                    "examined": 0,
                    "launched": 0,
                    "replayed": 0,
                    "skipped_concurrency": 0,
                    "skipped_disabled": 0,
                    "catchup_skipped": 0,
                },
            )
        return httpx.Response(204)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        await automation_scheduler_loop(
            client,
            _config(tmp_path),
            _credentials(),
            stop,
            WorkerLogger(tmp_path),
        )

    assert lease_calls == 2
    assert tick_fences == ["1", "2"]
