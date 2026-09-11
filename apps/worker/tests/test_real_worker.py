import asyncio
import json
import sys
from pathlib import Path
from time import monotonic

import httpx
import pytest
from acp_contracts import EvidenceCreate, TechnicalValidation

from acp_worker.cli import main as cli_main
from acp_worker.config import WorkerConfig, WorkerConfigurationError
from acp_worker.local_log import WorkerLogger
from acp_worker.local_runner import LocalRunnerConfig, RunnerRequestError
from acp_worker.main import _renew_lease, process, run_forever
from acp_worker.state import CredentialStateError, WorkerCredentials


def worker_config(tmp_path: Path, runner: LocalRunnerConfig) -> WorkerConfig:
    return WorkerConfig(
        api_url="https://api.test",
        gateway_url="https://gateway.test",
        gateway_service_token="gateway-secret",
        provider_id="hermes",
        poll_interval=0.01,
        step_seconds=0,
        state_dir=tmp_path / "state",
        name="real-test-worker",
        max_concurrency=1,
        simulation=False,
        registration_token=None,
        local_runner=runner,
    )


def credentials() -> WorkerCredentials:
    return WorkerCredentials(
        worker_id="worker-1",
        token="worker-token",
        api_origin="https://api.test",
        name="real-test-worker",
        capabilities=["shell_restricted"],
        max_concurrency=1,
        simulation=False,
        token_expires_at="2030-01-01T00:00:00Z",
    )


async def test_programmatic_worker_start_refuses_mismatched_api_origin(tmp_path: Path):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "raise SystemExit(99)"),
        run_root=tmp_path / "runs",
    )
    config = worker_config(tmp_path, runner)
    mismatched = WorkerCredentials(
        **{**credentials().__dict__, "api_origin": "https://other-api.test"}
    )

    with pytest.raises(CredentialStateError, match="autre origine API"):
        await run_forever(config, mismatched, once=True)

    assert not config.state_dir.exists()


async def test_programmatic_real_worker_refuses_the_mock_evaluator(tmp_path: Path):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "raise SystemExit(99)"),
        run_root=tmp_path / "runs",
    )
    config = WorkerConfig(
        **{**worker_config(tmp_path, runner).__dict__, "provider_id": "mock"}
    )

    with pytest.raises(WorkerConfigurationError, match="mock est interdit"):
        await run_forever(config, credentials(), once=True)

    assert not config.state_dir.exists()


def claim(*, stop_requested: bool = False) -> dict:
    return {
        "task": {
            "id": "task-1",
            "title": "Exécution déterministe",
            "description": "Lancer le programme local configuré",
            "meta": {
                "required_capabilities": ["shell_restricted"],
            },
        },
        "task_run": {"id": "run-1"},
        "attempt_id": "run-1",
        "attempt_number": 2,
        "fencing_token": 9,
        "stop_requested": stop_requested,
        "session": {
            "session_id": "session-1",
            "organization_id": "organization-1",
            "workspace_id": "workspace-1",
            "project_id": "project-1",
            "team_id": None,
            "agent_instance_id": "agent-1",
            "provider_id": "hermes",
        },
        "agent": {"id": "agent-1", "name": "Agent", "role_id": "role-1"},
        "project": {"id": "project-1", "name": "Project", "project_type": "code"},
        "mission": {
            "id": "task-1",
            "objective": "Produire une sortie déterministe",
            "expected_outcome": "Le programme local produit une preuve réelle",
            "acceptance_criteria": ["sortie réelle"],
            "autonomy": {
                "mode": "supervised",
                "allowed_actions": [],
                "forbidden_actions": [],
                "approval_required_actions": [],
            },
            "resources": [],
            "budget": {
                "max_cost": 0,
                "currency": "EUR",
                "max_tokens": None,
                "max_tool_calls": 1,
            },
            "duration_seconds": 60,
        },
        "required_capabilities": ["shell_restricted"],
    }


async def test_real_worker_only_succeeds_after_process_proof_and_evaluation(
    tmp_path: Path,
):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "print('real-output')"),
        run_root=tmp_path / "runs",
        timeout_seconds=2,
        max_output_bytes=1024,
    )
    config = worker_config(tmp_path, runner)
    api_requests: list[tuple[str, dict]] = []
    gateway_requests: list[tuple[str, dict]] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH" or request.url.path == "/events":
            assert request.headers["x-attempt-fencing-token"] == "9"
        body = json.loads(request.content) if request.content else {}
        api_requests.append((f"{request.method} {request.url.path}", body))
        return httpx.Response(200, json={})

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer gateway-secret"
        body = json.loads(request.content)
        gateway_requests.append((request.url.path, body))
        if request.url.path.endswith("/plan"):
            assert body["goal"] == "Produire une sortie déterministe"
            return httpx.Response(
                200,
                json={
                    "plan_id": "plan-1",
                    "provider_id": "hermes",
                    "steps": [{"id": "step-1", "title": "Run"}],
                },
            )
        assert body["task_summary"] == "Le programme local produit une preuve réelle"
        assert body["produced_output"]["execution_evidence"]["exit_code"] == 0
        assert body["produced_output"]["execution_evidence"]["data"]["stdout"][
            "text"
        ].splitlines() == ["real-output"]
        assert body["acceptance_criteria"] == ["sortie réelle"]
        return httpx.Response(
            200,
            json={"approved": True, "score": 1, "provider_id": "hermes"},
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(gateway_handler)) as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            credentials(),
            claim(),
            WorkerLogger(config.state_dir),
        )

    patches = [body for method, body in api_requests if method.startswith("PATCH ")]
    assert patches[-1]["status"] == "succeeded"
    assert patches[-1]["technical_validation"]["status"] == "passed"
    assert len(patches[-1]["evidence"]) == 1
    assert patches[-1]["evidence"][0]["kind"] == "local_process"
    assert patches[-1]["evidence"][0]["data"]["status"] == "succeeded"
    assert patches[-1]["result"]["execution_mode"] == "real_local_process"
    TechnicalValidation.model_validate(patches[-1]["technical_validation"])
    EvidenceCreate.model_validate(patches[-1]["evidence"][0])
    assert [path.rsplit("/", 1)[-1] for path, _ in gateway_requests] == [
        "plan",
        "evaluate",
    ]


async def test_terminal_patch_conflict_reconciles_interrupted_with_same_evidence(
    tmp_path: Path,
):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "print('durable-proof')"),
        run_root=tmp_path / "runs",
        timeout_seconds=2,
        max_output_bytes=1024,
    )
    config = worker_config(tmp_path, runner)
    patches: list[dict] = []
    terminal_conflicted = False

    def api_handler(request: httpx.Request) -> httpx.Response:
        nonlocal terminal_conflicted
        if request.method == "PATCH":
            body = json.loads(request.content)
            patches.append(body)
            if body.get("status") == "succeeded" and not terminal_conflicted:
                terminal_conflicted = True
                return httpx.Response(409, json={"detail": "run stopping"})
        return httpx.Response(200, json={})

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/plan"):
            return httpx.Response(
                200,
                json={"plan_id": "plan-1", "steps": [{"id": "one", "title": "Run"}]},
            )
        return httpx.Response(
            200, json={"approved": True, "provider_id": "hermes"}
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(gateway_handler)) as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            credentials(),
            claim(),
            WorkerLogger(config.state_dir),
        )

    conflicted = next(body for body in patches if body.get("status") == "succeeded")
    reconciled = patches[-1]
    assert reconciled["status"] == "interrupted"
    assert reconciled["technical_validation"]["status"] == "passed"
    assert reconciled["evidence"] == conflicted["evidence"]
    assert reconciled["result"]["evidence"] == conflicted["evidence"]
    persisted = json.loads(
        (tmp_path / "runs" / "run-1--run-1" / "evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted == reconciled["evidence"][0]["data"]


async def test_provider_evaluation_failure_keeps_real_process_proof(tmp_path: Path):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "print('proof-before-evaluation')"),
        run_root=tmp_path / "runs",
        timeout_seconds=2,
        max_output_bytes=1024,
    )
    config = worker_config(tmp_path, runner)
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/evaluate"):
            return httpx.Response(503, json={"detail": "provider unavailable"})
        return httpx.Response(
            200,
            json={
                "plan_id": "plan-1",
                "steps": [{"id": "step-1", "title": "Run"}],
            },
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(gateway_handler)) as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            credentials(),
            claim(),
            WorkerLogger(config.state_dir),
        )

    terminal = patches[-1]
    assert terminal["status"] == "blocked"
    assert terminal["technical_validation"]["status"] == "passed"
    assert terminal["evidence"][0]["exit_code"] == 0
    assert terminal["evidence"][0]["data"]["status"] == "succeeded"
    assert terminal["result"]["evaluation"] == {
        "status": "unavailable",
        "error_type": "RuntimeError",
    }
    TechnicalValidation.model_validate(terminal["technical_validation"])
    EvidenceCreate.model_validate(terminal["evidence"][0])
    assert all(item.get("status") != "succeeded" for item in patches)


async def test_global_mission_deadline_covers_plan_process_and_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runner = LocalRunnerConfig(
        argv=(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(0.2); print('deadline-proof')",
        ),
        run_root=tmp_path / "runs",
        timeout_seconds=10,
        max_output_bytes=1024,
    )
    config = worker_config(tmp_path, runner)
    mission_claim = claim()
    mission_claim["mission"]["duration_seconds"] = 1
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    async def delayed_plan(*args, **kwargs) -> dict:
        await asyncio.sleep(0.2)
        return {
            "plan_id": "plan-deadline",
            "steps": [{"id": "step-1", "title": "Run"}],
        }

    async def evaluation_beyond_deadline(*args, **kwargs) -> dict:
        await asyncio.sleep(5)
        return {"approved": True}

    monkeypatch.setattr("acp_worker.main.gateway_plan", delayed_plan)
    monkeypatch.setattr("acp_worker.main.gateway_evaluate", evaluation_beyond_deadline)

    started = monotonic()
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
        as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            credentials(),
            mission_claim,
            WorkerLogger(config.state_dir),
        )
    elapsed = monotonic() - started

    terminal = patches[-1]
    assert elapsed < 1.7
    assert terminal["status"] == "blocked"
    assert terminal["technical_validation"]["status"] == "passed"
    assert terminal["evidence"][0]["data"]["status"] == "succeeded"
    assert terminal["evidence"][0]["data"]["limits"]["timeout_seconds"] < 1
    assert terminal["result"]["evaluation"]["error_type"] == "MissionDeadlineExceeded"
    assert all(item.get("status") != "succeeded" for item in patches)


async def test_unsafe_mission_policy_is_rejected_before_spawn(tmp_path: Path):
    marker = tmp_path / "must-not-run"
    runner = LocalRunnerConfig(
        argv=(
            sys.executable,
            "-I",
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')",
            str(marker),
        ),
        run_root=tmp_path / "runs",
        timeout_seconds=2,
        max_output_bytes=128,
    )
    config = worker_config(tmp_path, runner)
    unsafe_claim = claim()
    unsafe_claim["mission"]["resources"] = [
        {
            "kind": "filesystem",
            "identifier": "project-1",
            "access": "write",
            "description": "write access is not isolated",
        }
    ]
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    def unexpected_gateway(_: httpx.Request) -> httpx.Response:
        raise AssertionError("la politique doit être refusée avant la planification")

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(unexpected_gateway)) as gateway_client,
    ):
        with pytest.raises(RunnerRequestError, match="ressources en écriture"):
            await process(
                api_client,
                gateway_client,
                config,
                credentials(),
                unsafe_claim,
                WorkerLogger(config.state_dir),
            )

    assert not marker.exists()
    assert patches[-1]["status"] == "failed"


async def test_real_worker_rejects_legacy_task_without_mission_policy(tmp_path: Path):
    marker = tmp_path / "legacy-must-not-run"
    runner = LocalRunnerConfig(
        argv=(
            sys.executable,
            "-I",
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')",
            str(marker),
        ),
        run_root=tmp_path / "runs",
        timeout_seconds=2,
        max_output_bytes=128,
    )
    config = worker_config(tmp_path, runner)
    legacy_claim = claim()
    legacy_claim.pop("mission")
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    def unexpected_gateway(_: httpx.Request) -> httpx.Response:
        raise AssertionError("une tâche sans politique ne doit pas atteindre le gateway")

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(unexpected_gateway)) as gateway_client,
    ):
        with pytest.raises(RuntimeError, match="enveloppe mission complète"):
            await process(
                api_client,
                gateway_client,
                config,
                credentials(),
                legacy_claim,
                WorkerLogger(config.state_dir),
            )

    assert not marker.exists()
    assert patches[-1]["status"] == "failed"
    assert patches[-1]["evidence"] == []


async def test_claim_stop_prevents_process_spawn(tmp_path: Path):
    marker = tmp_path / "must-not-run"
    runner = LocalRunnerConfig(
        argv=(
            sys.executable,
            "-I",
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')",
            str(marker),
        ),
        run_root=tmp_path / "runs",
        timeout_seconds=2,
        max_output_bytes=128,
    )
    config = worker_config(tmp_path, runner)
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-attempt-fencing-token"] == "9"
        patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    def unexpected_gateway(_: httpx.Request) -> httpx.Response:
        raise AssertionError("le gateway ne doit pas être appelé après un stop au claim")

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(unexpected_gateway)) as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            credentials(),
            claim(stop_requested=True),
            WorkerLogger(config.state_dir),
        )

    assert not marker.exists()
    assert patches == [
        {
            "status": "cancelled",
            "technical_validation": {
                "status": "pending",
                "summary": "Processus local non démarré: arrêt déjà demandé.",
            },
            "evidence": [],
            "result": {
                "execution_mode": "not_started",
                "technical_validation": "not_executed",
                "evidence": [],
                "worker_id": "worker-1",
                "message": "Arrêt demandé avant le lancement du processus local.",
            },
        }
    ]


async def test_stop_during_planning_finishes_cancelled_without_failed_repatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    marker = tmp_path / "must-not-run"
    runner = LocalRunnerConfig(
        argv=(
            sys.executable,
            "-I",
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')",
            str(marker),
        ),
        run_root=tmp_path / "runs",
        timeout_seconds=2,
        max_output_bytes=128,
    )
    config = worker_config(tmp_path, runner)
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    async def delayed_plan(*args, **kwargs) -> dict:
        await asyncio.sleep(5)
        return {
            "plan_id": "too-late",
            "steps": [{"id": "step-1", "title": "Run"}],
        }

    async def request_stop(
        client,
        worker_config,
        worker_credentials,
        attempt_id,
        fencing_token,
        stop,
        execution_stop,
        stop_context,
        logger,
        **kwargs,
    ) -> None:
        await asyncio.sleep(0.01)
        stop_context["reason"] = "stop_requested"
        execution_stop.set()
        await stop.wait()

    monkeypatch.setattr("acp_worker.main.gateway_plan", delayed_plan)
    monkeypatch.setattr("acp_worker.main._renew_lease", request_stop)

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
        as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            credentials(),
            claim(),
            WorkerLogger(config.state_dir),
        )

    assert not marker.exists()
    assert patches[-1]["status"] == "cancelled"
    assert all(item.get("status") != "failed" for item in patches)


async def test_nonzero_process_cannot_reach_provider_approval(tmp_path: Path):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "raise SystemExit(6)"),
        run_root=tmp_path / "runs",
        timeout_seconds=2,
        max_output_bytes=128,
    )
    config = worker_config(tmp_path, runner)
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/evaluate"):
            raise AssertionError("un code non nul ne doit jamais être évalué comme succès")
        return httpx.Response(
            200,
            json={
                "plan_id": "plan-1",
                "steps": [{"id": "step-1", "title": "Run"}],
            },
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(gateway_handler)) as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            credentials(),
            claim(),
            WorkerLogger(config.state_dir),
        )

    assert patches[-1]["status"] == "failed"
    assert patches[-1]["technical_validation"]["status"] == "failed"
    assert patches[-1]["evidence"][0]["exit_code"] == 6
    assert patches[-1]["evidence"][0]["data"]["status"] == "failed"


async def test_renew_stop_requested_sets_execution_stop(tmp_path: Path):
    config = worker_config(
        tmp_path,
        LocalRunnerConfig(
            argv=(sys.executable, "-V"),
            run_root=tmp_path / "runs",
        ),
    )
    stop_lease = asyncio.Event()
    execution_stop = asyncio.Event()
    stop_context: dict[str, str | None] = {"reason": None}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/leases/run-1/renew")
        assert request.headers["x-attempt-fencing-token"] == "9"
        return httpx.Response(
            200,
            json={
                "worker_id": "worker-1",
                "task_run_id": "run-1",
                "lease_expires_at": "2030-01-01T00:00:00Z",
                "status": "stopping",
                "stop_requested": True,
                "fencing_token": 9,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await _renew_lease(
            client,
            config,
            credentials(),
            "run-1",
            9,
            stop_lease,
            execution_stop,
            stop_context,
            WorkerLogger(config.state_dir),
            renew_interval_seconds=0.001,
        )

    assert execution_stop.is_set()
    assert stop_context["reason"] == "stop_requested"


async def test_renew_failure_or_stale_fence_stops_execution(tmp_path: Path):
    config = worker_config(
        tmp_path,
        LocalRunnerConfig(
            argv=(sys.executable, "-V"),
            run_root=tmp_path / "runs",
        ),
    )

    for response, reason in (
        (httpx.Response(409, json={"detail": "lease lost"}), "lease_lost"),
        (
            httpx.Response(
                200,
                json={"status": "active", "stop_requested": False, "fencing_token": 10},
            ),
            "fencing_token_mismatch",
        ),
    ):
        stop_lease = asyncio.Event()
        execution_stop = asyncio.Event()
        stop_context: dict[str, str | None] = {"reason": None}
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: response)
        ) as client:
            await _renew_lease(
                client,
                config,
                credentials(),
                "run-1",
                9,
                stop_lease,
                execution_stop,
                stop_context,
                WorkerLogger(config.state_dir),
                renew_interval_seconds=0.001,
            )
        assert execution_stop.is_set()
        assert stop_context["reason"] == reason


def test_cli_refuses_real_worker_without_local_runner(
    tmp_path: Path, monkeypatch, capsys
):
    config = worker_config(
        tmp_path,
        LocalRunnerConfig(
            argv=(sys.executable, "-V"),
            run_root=tmp_path / "unused-runs",
        ),
    )
    config = WorkerConfig(
        **{
            **config.__dict__,
            "local_runner": None,
        }
    )
    monkeypatch.setattr(
        "acp_worker.cli.WorkerConfig.from_env", classmethod(lambda cls: config)
    )
    monkeypatch.setattr(
        "acp_worker.cli.load_credentials", lambda _state_dir, _origin: credentials()
    )

    assert cli_main(["start"]) == 2
    assert "Aucun exécuteur réel sécurisé" in capsys.readouterr().err
