import asyncio
import json
import sys
from pathlib import Path
from time import monotonic

import httpx
import pytest
from acp_contracts import EvidenceCreate, TechnicalValidation

from acp_worker.budget import BudgetUnavailable
from acp_worker.cli import main as cli_main
from acp_worker.config import WorkerConfig, WorkerConfigurationError
from acp_worker.executors import (
    ExecutorCleanupError,
    ExecutorConfig,
    ExecutorResult,
    ExecutorSpec,
)
from acp_worker.local_log import WorkerLogger
from acp_worker.local_runner import LocalRunnerConfig, RunnerRequestError
from acp_worker.main import _await_work, _renew_lease, process, run_forever
from acp_worker.state import CredentialStateError, WorkerCredentials


def hermes_transport(handler):
    """Simulation des nouvelles admissions/polls autour des résultats de fixture."""
    admissions = {}
    cancelled = set()

    def dispatch(request):
        path = request.url.path
        if "/operations/" not in path:
            if path.endswith("/stop"):
                run_id = path.split("/")[-2]
                cancelled.add(run_id)
                return httpx.Response(200, json={"run_id": run_id, "status": "cancelled"})
            return handler(request)
        operation = path.split("/operations/")[1].split("/")[0]
        run_id = "fake-" + operation
        envelope = {"provider_id": "hermes", "operation": operation, "run_id": run_id,
                    "status": "started", "result": None, "replayed": False, "error": None}
        if request.method == "POST":
            assert request.headers.get("Idempotency-Key")
            admissions[operation] = request
            return httpx.Response(200, json=envelope)
        if run_id in cancelled:
            return httpx.Response(200, json={**envelope, "status": "cancelled"})
        admitted = admissions[operation]
        legacy_request = httpx.Request("POST", admitted.url.copy_with(path="/v1/providers/hermes/" + operation),
                                       headers=admitted.headers, content=admitted.content)
        response = handler(legacy_request)
        if response.status_code >= 400:
            return httpx.Response(200, json={**envelope, "status": "failed", "error": "Échec simulé"})
        return httpx.Response(200, json={**envelope, "status": "completed", "result": response.json()})

    return httpx.MockTransport(dispatch)


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
        project_id="project-1",
    )


def budget_success_response(request: httpx.Request) -> httpx.Response | None:
    if "/budget/" not in request.url.path:
        return None
    assert request.headers["x-attempt-fencing-token"] == "9"
    return httpx.Response(
        200,
        json={
            "accepted": True,
            "idempotent": False,
            "permit_allowed": True,
            "verdict": {
                "state": "ok",
                "measured": True,
                "limit_reached": None,
                "cost": None,
                "currency": "EUR",
                "tokens_input": None,
                "tokens_output": None,
                "tool_calls": 1,
                "usage_reported": False,
                "estimated": False,
            },
        },
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


async def test_programmatic_worker_refuses_persisted_agent_capability_without_backend(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    binary = tmp_path / "bin" / "claude.exe"
    auth = tmp_path / "auth"
    workspace.mkdir()
    binary.parent.mkdir()
    binary.write_bytes(b"test")
    auth.mkdir()
    claude_only = ExecutorConfig(
        claude=ExecutorSpec(executable=binary, auth_directory=auth),
        project_roots={"project-1": workspace},
    )
    base = worker_config(
        tmp_path,
        LocalRunnerConfig(
            argv=(sys.executable, "-I", "-c", "raise SystemExit(99)"),
            run_root=tmp_path / "unused-runs",
        ),
    )
    config = WorkerConfig(
        **{**base.__dict__, "local_runner": None, "executors": claude_only}
    )
    stale = WorkerCredentials(
        **{**credentials().__dict__, "capabilities": ["codex_cli"]}
    )

    with pytest.raises(WorkerConfigurationError, match="codex_cli"):
        await run_forever(config, stale, once=True)

    assert not config.state_dir.exists()


async def test_programmatic_worker_refuses_agent_project_without_local_root(
    tmp_path: Path,
):
    allowed_workspace = tmp_path / "allowed-workspace"
    binary = tmp_path / "bin" / "codex.exe"
    auth = tmp_path / "auth"
    allowed_workspace.mkdir()
    binary.parent.mkdir()
    binary.write_bytes(b"test")
    auth.mkdir()
    executors = ExecutorConfig(
        codex=ExecutorSpec(executable=binary, auth_directory=auth),
        project_roots={"project-1": allowed_workspace},
    )
    base = worker_config(
        tmp_path,
        LocalRunnerConfig(
            argv=(sys.executable, "-I", "-c", "raise SystemExit(99)"),
            run_root=tmp_path / "unused-runs",
        ),
    )
    config = WorkerConfig(
        **{**base.__dict__, "local_runner": None, "executors": executors}
    )
    stale = WorkerCredentials(
        **{
            **credentials().__dict__,
            "capabilities": ["codex_cli"],
            "project_id": "project-2",
        }
    )

    with pytest.raises(WorkerConfigurationError, match="project-2"):
        await run_forever(config, stale, once=True)

    assert not config.state_dir.exists()


async def test_worker_http_clients_ignore_environment_proxies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "raise SystemExit(99)"),
        run_root=tmp_path / "runs",
    )
    config = worker_config(tmp_path, runner)
    real_async_client = httpx.AsyncClient
    client_options: list[dict[str, object]] = []

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        client_options.append(dict(kwargs))
        is_api_client = len(client_options) == 1
        handler = lambda _request: httpx.Response(
            200 if is_api_client else 500,
            json={"task": None} if is_api_client else {},
        )
        return real_async_client(
            **kwargs,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr("acp_worker.main.httpx.AsyncClient", client_factory)

    await run_forever(config, credentials(), once=True)

    assert len(client_options) == 2
    assert all(options.get("trust_env") is False for options in client_options)


async def test_await_work_propagates_cleanup_failure_after_stop():
    started = asyncio.Event()
    stop = asyncio.Event()

    async def operation() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise ExecutorCleanupError("nettoyage non confirmé") from None

    waiter = asyncio.create_task(
        _await_work(operation, deadline=None, stop_event=stop)
    )
    await started.wait()
    stop.set()

    with pytest.raises(ExecutorCleanupError, match="nettoyage non confirmé"):
        await waiter


async def test_await_work_propagates_cleanup_failure_after_deadline():
    async def operation() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise ExecutorCleanupError("nettoyage après délai non confirmé") from None

    with pytest.raises(ExecutorCleanupError, match="après délai"):
        await _await_work(
            operation,
            deadline=monotonic() + 0.02,
            stop_event=asyncio.Event(),
        )


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
                "max_cost": None,
                "currency": "EUR",
                "max_tokens": None,
                "max_tool_calls": 3,
            },
            "duration_seconds": 60,
        },
        "required_capabilities": ["shell_restricted"],
    }


async def test_process_never_converts_cleanup_failure_to_a_terminal_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "raise SystemExit(99)"),
        run_root=tmp_path / "runs",
    )
    config = worker_config(tmp_path, runner)
    api_requests: list[str] = []

    async def fail_closed_await(
        _factory,
        *,
        deadline: float | None,
        stop_event: asyncio.Event,
    ) -> None:
        stop_event.set()
        raise ExecutorCleanupError("arbre non confirmé")

    monkeypatch.setattr("acp_worker.main._await_work", fail_closed_await)

    def api_handler(request: httpx.Request) -> httpx.Response:
        api_requests.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={}))
        ) as gateway_client,
    ):
        with pytest.raises(ExecutorCleanupError, match="arbre non confirmé"):
            await process(
                api_client,
                gateway_client,
                config,
                credentials(),
                claim(),
                WorkerLogger(config.state_dir),
            )

    assert not any(request.startswith("PATCH ") for request in api_requests)


async def test_run_forever_stops_claiming_after_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "raise SystemExit(99)"),
        run_root=tmp_path / "runs",
    )
    config = worker_config(tmp_path, runner)
    claim_count = 0
    process_count = 0

    async def fail_closed_process(*_args, **_kwargs) -> None:
        nonlocal process_count
        process_count += 1
        raise ExecutorCleanupError("arbre non confirmé")

    def api_handler(request: httpx.Request) -> httpx.Response:
        nonlocal claim_count
        if request.url.path.endswith("/claim"):
            claim_count += 1
            return httpx.Response(200, json=claim())
        return httpx.Response(200, json={})

    real_async_client = httpx.AsyncClient
    client_count = 0

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        nonlocal client_count
        client_count += 1
        handler = (
            api_handler
            if client_count == 1
            else lambda _request: httpx.Response(200, json={})
        )
        return real_async_client(
            **kwargs,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr("acp_worker.main.process", fail_closed_process)
    monkeypatch.setattr("acp_worker.main.httpx.AsyncClient", client_factory)

    with pytest.raises(ExecutorCleanupError, match="arbre non confirmé"):
        await asyncio.wait_for(run_forever(config, credentials()), timeout=1.0)

    assert process_count == 1
    assert claim_count == 1


async def test_real_worker_only_succeeds_after_process_proof_and_evaluation(
    tmp_path: Path,
):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "print('real-output')"),
        run_root=tmp_path / "runs",
        timeout_seconds=15,
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
        budget_response = budget_success_response(request)
        if budget_response is not None:
            return budget_response
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
        httpx.AsyncClient(transport=hermes_transport(gateway_handler)) as gateway_client,
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
    budget_requests = [
        (method.rsplit("/", 1)[-1], body)
        for method, body in api_requests
        if "/budget/" in method
    ]
    assert [kind for kind, _ in budget_requests] == [
        "permit",
        "usage",
        "permit",
        "permit",
        "usage",
    ]
    assert [body["phase"] for _, body in budget_requests] == [
        "planning",
        "planning",
        "execution",
        "evaluation",
        "evaluation",
    ]
    assert all(body["tool_calls"] == 1 for _, body in budget_requests)
    # Les appels Hermes ne revendiquent aucune borne coût/jetons que son API
    # n'impose pas. L'effet local réserve au contraire ses zéros vérifiables et
    # reste en attente faute de faux rapport provider.
    assert "cost" not in budget_requests[0][1]
    assert budget_requests[2][1]["cost"] == 0
    assert budget_requests[2][1]["tokens_input"] == 0
    assert budget_requests[2][1]["tokens_output"] == 0
    assert "cost" not in budget_requests[-1][1]


@pytest.mark.parametrize("usage_failures", [0, 1, 3])
async def test_real_worker_spawns_one_explicit_codex_executor_without_leaking_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    usage_failures: int,
):
    workspace = tmp_path / "workspace"
    binary = tmp_path / "bin" / "codex.exe"
    auth = tmp_path / "auth"
    workspace.mkdir()
    binary.parent.mkdir()
    binary.write_bytes(b"test")
    auth.mkdir()
    executor_config = ExecutorConfig(
        codex=ExecutorSpec(executable=binary, auth_directory=auth),
        project_roots={"project-1": workspace},
    )
    config = WorkerConfig(
        **{
            **worker_config(
                tmp_path,
                LocalRunnerConfig(
                    argv=(sys.executable, "-I", "-c", "raise SystemExit(99)"),
                    run_root=tmp_path / "unused-runs",
                ),
            ).__dict__,
            "local_runner": None,
            "executors": executor_config,
        }
    )
    worker_credentials = WorkerCredentials(
        **{
            **credentials().__dict__,
            "capabilities": ["codex_cli"],
        }
    )
    executor_claim = claim()
    executor_claim["task"]["meta"]["required_capabilities"] = ["codex_cli"]
    executor_claim["required_capabilities"] = ["codex_cli"]
    executor_claim["mission"]["resources"] = [
        {
            "kind": "project_workspace",
            "identifier": "project-1",
            "access": "write",
            "description": "workspace approuvé",
        }
    ]
    invocations: list[dict[str, object]] = []

    async def fake_run_executor(
        executor: str,
        project_id: str,
        requested_path: str,
        prompt: str,
        **kwargs: object,
    ) -> ExecutorResult:
        invocations.append(
            {
                "executor": executor,
                "project_id": project_id,
                "requested_path": requested_path,
                "prompt": prompt,
                **kwargs,
            }
        )
        return ExecutorResult(
            executor="codex_cli",
            exit_code=0,
            event_count=1,
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            stdout_bytes=123,
            stderr_bytes=17,
            output={"text": "Réponse métier vérifiable", "truncated": False, "complete": True},
        )

    monkeypatch.setattr("acp_worker.main.run_executor", fake_run_executor)
    api_requests: list[tuple[str, dict]] = []

    execution_reports: list[dict] = []
    evaluations: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        api_requests.append((f"{request.method} {request.url.path}", body))
        if request.url.path.endswith("/budget/usage") and body.get("phase") == "execution":
            execution_reports.append(body)
            if len(execution_reports) <= usage_failures:
                # Simule une réponse perdue après un éventuel commit côté API.
                raise httpx.ReadError("réponse perdue", request=request)
        budget_response = budget_success_response(request)
        return budget_response or httpx.Response(200, json={})

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/plan"):
            return httpx.Response(
                200,
                json={
                    "plan_id": "plan-agent-1",
                    "provider_id": "hermes",
                    "steps": [{"id": "step-1", "title": "Modifier le projet"}],
                },
            )
        evaluations.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"approved": True, "score": 1, "provider_id": "hermes"},
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=hermes_transport(gateway_handler)) as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            worker_credentials,
            executor_claim,
            WorkerLogger(config.state_dir),
        )
        if usage_failures == 3:
            # Même tentative après redémarrage : preuve relue, aucun second effet.
            await process(api_client, gateway_client, config, worker_credentials,
                          executor_claim, WorkerLogger(config.state_dir))

    assert len(invocations) == 1
    assert invocations[0]["executor"] == "codex_cli"
    assert invocations[0]["project_id"] == "project-1"
    assert invocations[0]["requested_path"] == "."
    assert invocations[0]["allow_writes"] is True
    assert "Produire une sortie déterministe" in str(invocations[0]["prompt"])
    patches = [body for method, body in api_requests if method.startswith("PATCH ")]
    assert patches[-1]["status"] == ("blocked" if usage_failures == 3 else "succeeded")
    assert patches[-1]["technical_validation"]["status"] == "passed"
    assert patches[-1]["result"]["output"]["text"] == "Réponse métier vérifiable"
    assert len(execution_reports) == min(usage_failures + 1, 3)
    assert all(item == execution_reports[0] for item in execution_reports)
    if usage_failures == 3:
        assert patches[-1]["result"]["accounting"]["status"] == "unconfirmed"
        assert evaluations == []
    else:
        assert evaluations[0]["produced_output"]["output"]["text"] == "Réponse métier vérifiable"
    assert patches[-1]["result"]["execution_mode"] == "codex_cli"
    assert patches[-1]["result"]["spawned_agents"] == 1
    assert (
        patches[-1]["result"]["spawned_agents_scope"]
        == "worker_managed_top_level_cli_only"
    )
    assert (
        patches[-1]["evidence"][0]["data"]["spawned_agents_scope"]
        == "worker_managed_top_level_cli_only"
    )
    assert patches[-1]["evidence"][0]["data"]["stdout"]["sha256"] == "a" * 64
    persisted = json.dumps(patches, ensure_ascii=False)
    assert "SORTIE-SENSIBLE" not in persisted
    assert "ERREUR-SENSIBLE" not in persisted
    budget_requests = [
        (method.rsplit("/", 1)[-1], body)
        for method, body in api_requests
        if "/budget/" in method
    ]
    if usage_failures:
        return
    assert [kind for kind, _ in budget_requests] == [
        "permit",
        "usage",
        "permit",
        "usage",
        "permit",
        "usage",
    ]
    assert [body["phase"] for _, body in budget_requests] == [
        "planning",
        "planning",
        "execution",
        "execution",
        "evaluation",
        "evaluation",
    ]
    assert all(body["tool_calls"] == 1 for _, body in budget_requests)
    assert "cost" not in budget_requests[0][1]
    assert budget_requests[2][1]["provider"] == "codex_cli"
    assert "cost" not in budget_requests[2][1]
    assert "tokens_input" not in budget_requests[2][1]
    assert "tokens_output" not in budget_requests[2][1]
    assert "cost" not in budget_requests[-1][1]


async def test_hermes_cost_or_token_budget_is_refused_before_provider_effect(
    tmp_path: Path,
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
        max_output_bytes=1024,
    )
    config = worker_config(tmp_path, runner)
    bounded_claim = claim()
    bounded_claim["mission"]["budget"] = {
        "max_cost": 1,
        "currency": "EUR",
        "max_tokens": 100,
        "max_tool_calls": 3,
    }
    api_paths: list[str] = []
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        api_paths.append(request.url.path)
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
            return httpx.Response(200, json={})
        raise AssertionError("aucun permis ne doit précéder une borne indisponible")

    def unexpected_gateway(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Hermes ne doit recevoir aucun effet non bornable")

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)) as api_client,
        httpx.AsyncClient(transport=httpx.MockTransport(unexpected_gateway))
        as gateway_client,
    ):
        with pytest.raises(
            BudgetUnavailable,
            match="estimation conservatrice indisponible.*coût.*jetons",
        ):
            await process(
                api_client,
                gateway_client,
                config,
                credentials(),
                bounded_claim,
                WorkerLogger(config.state_dir),
            )

    assert marker.exists() is False
    assert all("/budget/" not in path for path in api_paths)
    assert patches[-1]["status"] == "failed"


async def test_terminal_patch_conflict_reconciles_interrupted_with_same_evidence(
    tmp_path: Path,
):
    runner = LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", "print('durable-proof')"),
        run_root=tmp_path / "runs",
        timeout_seconds=15,
        max_output_bytes=1024,
    )
    config = worker_config(tmp_path, runner)
    patches: list[dict] = []
    terminal_conflicted = False

    def api_handler(request: httpx.Request) -> httpx.Response:
        nonlocal terminal_conflicted
        budget_response = budget_success_response(request)
        if budget_response is not None:
            return budget_response
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
        httpx.AsyncClient(transport=hermes_transport(gateway_handler)) as gateway_client,
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
        timeout_seconds=15,
        max_output_bytes=1024,
    )
    config = worker_config(tmp_path, runner)
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        budget_response = budget_success_response(request)
        if budget_response is not None:
            return budget_response
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
        httpx.AsyncClient(transport=hermes_transport(gateway_handler)) as gateway_client,
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
    assert terminal["status"] == "blocked", terminal
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
            "import time; time.sleep(0.1); print('deadline-proof')",
        ),
        run_root=tmp_path / "runs",
        timeout_seconds=10,
        max_output_bytes=1024,
    )
    config = worker_config(tmp_path, runner)
    mission_claim = claim()
    # Garde une marge aux créations de processus Windows/antivirus tout en
    # prouvant qu'une évaluation longue reste bornée par la deadline globale.
    mission_claim["mission"]["duration_seconds"] = 3
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        budget_response = budget_success_response(request)
        if budget_response is not None:
            return budget_response
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
        return httpx.Response(200, json={})

    async def delayed_plan(*args, **kwargs) -> dict:
        await asyncio.sleep(0.1)
        return {
            "plan_id": "plan-deadline",
            "steps": [{"id": "step-1", "title": "Run"}],
        }

    async def evaluation_beyond_deadline(*args, **kwargs) -> dict:
        await asyncio.sleep(10)
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
    assert elapsed < 4.2
    assert terminal["status"] == "blocked"
    assert terminal["technical_validation"]["status"] == "passed"
    assert terminal["evidence"][0]["data"]["status"] == "succeeded"
    assert terminal["evidence"][0]["data"]["limits"]["timeout_seconds"] < 3
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
        budget_response = budget_success_response(request)
        if budget_response is not None:
            return budget_response
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
        budget_response = budget_success_response(request)
        if budget_response is not None:
            return budget_response
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
        budget_response = budget_success_response(request)
        if budget_response is not None:
            return budget_response
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
        timeout_seconds=15,
        max_output_bytes=128,
    )
    config = worker_config(tmp_path, runner)
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        budget_response = budget_success_response(request)
        if budget_response is not None:
            return budget_response
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
        httpx.AsyncClient(transport=hermes_transport(gateway_handler)) as gateway_client,
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
