"""Boucle d'exécution d'un worker enregistré auprès de l'API.

Le worker ne parle qu'à l'API et au provider-gateway. Les intégrations externes
restent derrière leurs contrats de provider et ne sont jamais importées ici.
"""

import asyncio
import random
import math
from collections.abc import Awaitable, Callable
from dataclasses import replace
from time import monotonic, time
from typing import Any, TypeVar

import httpx
from acp_contracts import WorkerCapability

from .automation_scheduler import automation_scheduler_loop
from .budget import (
    EffectBudgetBounds,
    budgeted_effect,
    gateway_effect_bounds,
    non_consuming_effect_bounds,
)
from .capabilities import missing_capabilities
from .checkpoints import read_checkpoint, write_checkpoint
from .config import WorkerConfig
from .executors import (
    ExecutorCleanupError,
    invocation_from_mission,
    requested_executor,
    run_executor,
)
from .hermes_lifecycle import run_operation as hermes_operation
from .extensions import load_extensions
from .multi_agent import run_team
from .mcp_execution import acquire_mcp
from .local_runner import (
    LocalRunnerResult,
    LocalRunRequest,
    request_from_claim,
    run_local_program,
    validate_claim_for_local_runner,
    validate_safe_local_policy,
)
from .local_log import WorkerLogger
from .mcp_probe import run_stdio_probe
from .state import CredentialStateError, WorkerCredentials
from .subscription_quotas import subscription_quota_loop
from .web_tests import (
    WebTestLease,
    WorkerTestApi,
    mission_requests_web_tests,
    run_web_tests,
    web_tests_available,
)


_T = TypeVar("_T")


class MissionDeadlineExceeded(TimeoutError):
    """La durée globale de travail accordée par le claim est épuisée."""


class ExecutionStopped(RuntimeError):
    """Le lease a demandé l'arrêt d'une opération en cours."""


def _remaining_work_seconds(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise MissionDeadlineExceeded("durée globale de la mission dépassée")
    return remaining


async def _await_work(
    factory: Callable[[], Awaitable[_T]],
    *,
    deadline: float | None,
    stop_event: asyncio.Event,
) -> _T:
    """Attend une opération sans dépasser le budget restant ni ignorer un stop."""

    if stop_event.is_set():
        raise ExecutionStopped("arrêt du lease reçu")
    remaining = _remaining_work_seconds(deadline)
    operation = asyncio.ensure_future(factory())
    stop_waiter = asyncio.create_task(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            {operation, stop_waiter},
            timeout=remaining,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_waiter in done:
            operation.cancel()
            raise ExecutionStopped("arrêt du lease reçu")
        if operation in done:
            return await operation
        operation.cancel()
        raise MissionDeadlineExceeded("durée globale de la mission dépassée")
    finally:
        if not operation.done():
            operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        stop_waiter.cancel()
        await asyncio.gather(stop_waiter, return_exceptions=True)
        if not operation.cancelled():
            operation_error = operation.exception()
            if isinstance(operation_error, ExecutorCleanupError):
                raise operation_error


def _stopped_status(stop_context: dict[str, str | None]) -> str:
    return "cancelled" if stop_context["reason"] == "stop_requested" else "interrupted"


def gateway_headers(config: WorkerConfig) -> dict[str, str]:
    token = config.gateway_service_token
    if token is None or not token.strip():
        raise RuntimeError("ACP_GATEWAY_SERVICE_TOKEN doit être configuré pour le worker")
    return {"Authorization": f"Bearer {token}"}


async def emit(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    event_type: str,
    session: dict,
    *,
    fencing_token: int,
    **extra,
) -> None:
    event = {
        "type": event_type,
        "organization_id": session.get("organization_id"),
        "workspace_id": session.get("workspace_id"),
        "project_id": session.get("project_id"),
        "team_id": session.get("team_id"),
        "agent_instance_id": session.get("agent_instance_id"),
        **extra,
    }
    response = await client.post(
        f"{config.api_url}/events",
        headers=_fencing_headers(fencing_token),
        json=event,
    )
    response.raise_for_status()


def _fencing_headers(fencing_token: int) -> dict[str, str]:
    if (
        not isinstance(fencing_token, int)
        or isinstance(fencing_token, bool)
        or fencing_token < 1
    ):
        raise RuntimeError("fencing_token positif requis")
    return {"X-Attempt-Fencing-Token": str(fencing_token)}


async def patch_run(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    attempt_id: str,
    fencing_token: int,
    body: dict[str, Any],
) -> httpx.Response:
    response = await client.patch(
        f"{config.api_url}/task-runs/{attempt_id}",
        headers=_fencing_headers(fencing_token),
        json=body,
    )
    response.raise_for_status()
    return response


async def gateway_plan(
    client: httpx.AsyncClient, config: WorkerConfig, session: dict, goal: str,
    *, attempt_id: str | None = None, deadline: float | None = None,
    context: dict[str, Any] | None = None,
) -> dict:
    payload = {"session": session, "goal": goal, "context": context or {}, "constraints": []}
    if config.provider_id == "hermes" and attempt_id is not None:
        data = await hermes_operation(client, config, attempt_id=attempt_id, operation="plan",
                                      payload=payload, headers=gateway_headers(config), deadline=deadline)
    else:
        try:
            response = await client.post(
                f"{config.gateway_url}/v1/providers/{config.provider_id}/plan",
                headers=gateway_headers(config), json=payload, timeout=15.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("planification indisponible") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("réponse de planification non JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("réponse de planification invalide")
    if not isinstance(data.get("plan_id"), str) or not data["plan_id"].strip():
        raise RuntimeError("réponse de planification sans plan_id")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RuntimeError("réponse de planification sans étape vérifiable")
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("id"), str) or not isinstance(
            step.get("title"), str
        ):
            raise RuntimeError("étape de planification invalide")
    return data


async def gateway_evaluate(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    session: dict,
    summary: str,
    *,
    produced_output: dict[str, Any] | None = None,
    acceptance_criteria: list[Any] | None = None,
    attempt_id: str | None = None,
    deadline: float | None = None,
) -> dict:
    payload = {"session": session, "task_summary": summary,
               "produced_output": produced_output or {}, "acceptance_criteria": acceptance_criteria or []}
    if config.provider_id == "hermes" and attempt_id is not None:
        data = await hermes_operation(client, config, attempt_id=attempt_id, operation="evaluate",
                                      payload=payload, headers=gateway_headers(config), deadline=deadline)
    else:
        try:
            response = await client.post(
                f"{config.gateway_url}/v1/providers/{config.provider_id}/evaluate",
                headers=gateway_headers(config), json=payload, timeout=15.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("évaluation indisponible") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("réponse d'évaluation non JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("approved"), bool):
        raise RuntimeError("réponse d'évaluation sans verdict booléen explicite")
    reported_provider = data.get("provider_id")
    if reported_provider != config.provider_id or reported_provider == "mock":
        raise RuntimeError("réponse d'évaluation issue d'un provider inattendu ou simulé")
    return data


def execution_outcome(
    evaluation: dict[str, Any] | None, *, simulation: bool
) -> tuple[str, str, str]:
    """Retourne (run, tâche, événement) sans jamais promouvoir une simulation.

    Un verdict absent ou mal typé est une erreur de protocole. Cette vérification
    reste locale même si la passerelle a déjà validé sa réponse : la terminaison
    d'un run est la dernière frontière avant un événement de succès.
    """

    if simulation:
        return "blocked", "blocked", "task.blocked"
    if not isinstance(evaluation, dict) or not isinstance(evaluation.get("approved"), bool):
        raise RuntimeError("verdict d'évaluation explicite requis")
    if evaluation["approved"] is True:
        return "succeeded", "done", "task.completed"
    return "failed", "failed", "task.failed"


def technical_validation_payload(status: str, summary: str) -> dict[str, str]:
    if status not in {"pending", "passed", "failed"}:
        raise ValueError("statut de validation technique invalide")
    return {"status": status, "summary": summary[:10_000]}


def platform_evidence(
    execution: LocalRunnerResult, request: LocalRunRequest
) -> dict[str, Any]:
    details = execution.evidence(request)
    exit_label = "absent" if execution.exit_code is None else str(execution.exit_code)
    return {
        "kind": "local_process",
        "summary": (
            f"Processus local {execution.status}; code de sortie {exit_label}; "
            f"stdout {execution.stdout.total_bytes} octets; "
            f"stderr {execution.stderr.total_bytes} octets."
        ),
        "data": details,
        "exit_code": execution.exit_code,
    }


async def _renew_lease(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    attempt_id: str,
    fencing_token: int,
    stop: asyncio.Event,
    execution_stop: asyncio.Event,
    stop_context: dict[str, str | None],
    logger: WorkerLogger,
    *,
    renew_interval_seconds: float = 15.0,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=renew_interval_seconds)
            return
        except TimeoutError:
            pass
        try:
            response = await client.post(
                f"{config.api_url}/workers/{credentials.worker_id}/leases/{attempt_id}/renew",
                headers=_fencing_headers(fencing_token),
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError("réponse de renouvellement invalide")
            renewed_token = data.get("fencing_token")
            if renewed_token != fencing_token:
                stop_context["reason"] = "fencing_token_mismatch"
                execution_stop.set()
                logger.write(
                    "error",
                    "Fencing token discordant; arrêt de la tentative",
                    attempt_id=attempt_id,
                )
                return
            if (
                data.get("worker_id") != credentials.worker_id
                or data.get("task_run_id") != attempt_id
            ):
                raise RuntimeError("réponse de renouvellement hors tentative")
            if data.get("stop_requested") is True or data.get("status") == "stopping":
                stop_context["reason"] = "stop_requested"
                execution_stop.set()
                logger.write(
                    "info", "Arrêt demandé par la plateforme", attempt_id=attempt_id
                )
                return
            if data.get("stop_requested") is not False:
                raise RuntimeError("réponse de renouvellement sans stop_requested booléen")
            if data.get("status") not in {"preparing", "running", "waiting_approval"}:
                raise RuntimeError("la tentative renouvelée n'est plus active")
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            stop_context["reason"] = "lease_lost"
            execution_stop.set()
            logger.write(
                "error",
                "Lease perdu; arrêt de la tentative",
                attempt_id=attempt_id,
                error=str(exc),
            )
            return


async def process(
    api_client: httpx.AsyncClient,
    gateway_client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    claim: dict,
    logger: WorkerLogger,
) -> None:
    claimed_clock = monotonic()
    task = claim["task"]
    run = claim["task_run"]
    session = claim["session"]
    agent = claim["agent"]
    task_id, run_id = task["id"], run["id"]
    attempt_id = claim.get("attempt_id")
    attempt_number = claim.get("attempt_number")
    fencing_token = claim.get("fencing_token")
    stop_requested = claim.get("stop_requested")
    if not isinstance(attempt_id, str) or attempt_id != run_id:
        raise RuntimeError("claim sans attempt_id cohérent")
    if (
        not isinstance(attempt_number, int)
        or isinstance(attempt_number, bool)
        or attempt_number < 1
    ):
        raise RuntimeError("claim sans attempt_number positif")
    _fencing_headers(fencing_token)
    if not isinstance(stop_requested, bool):
        raise RuntimeError("claim sans stop_requested booléen")

    stop_lease = asyncio.Event()
    execution_stop = asyncio.Event()
    stop_context: dict[str, str | None] = {"reason": None}
    mission_deadline: float | None = None
    evidence: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    technical_status: str | None = None
    execution_label = "Exécution"
    execution_status = "unknown"
    execution_succeeded = False
    execution_cancelled = False

    def capture_completed() -> None:
        assert result is not None
        result["accounting"] = {"status": "unconfirmed", "reservation_reconciled": False}
        write_checkpoint(config, attempt_id, "execution", {"status": "completed", "result": result})

    def capture_reported(reconciled: bool) -> None:
        assert result is not None
        result["accounting"] = {
            "status": "reported" if reconciled else "reservation_retained",
            "reservation_reconciled": reconciled,
        }
        write_checkpoint(config, attempt_id, "execution", {"status": "completed", "result": result})
    lease_task = asyncio.create_task(
        _renew_lease(
            api_client,
            config,
            credentials,
            attempt_id,
            fencing_token,
            stop_lease,
            execution_stop,
            stop_context,
            logger,
        )
    )
    try:
        previous = read_checkpoint(config, attempt_id, "execution")
        if previous is not None:
            previous_result = previous.get("result")
            if not isinstance(previous_result, dict):
                raise RuntimeError("preuve de reprise invalide; réexécution refusée")
            result = previous_result
            evidence = result.get("evidence", [])
            technical_status = result.get("technical_validation", "pending")
            await patch_run(api_client, config, attempt_id, fencing_token, {
                "status": "blocked",
                "technical_validation": technical_validation_payload(technical_status, "Effet déjà exécuté; réexécution automatique refusée."),
                "evidence": evidence,
                "result": result,
            })
            return
        required_capabilities = claim.get("required_capabilities", [])
        missing = missing_capabilities(required_capabilities, credentials.capabilities)
        if missing:
            raise RuntimeError(
                f"capacités manquantes après attribution: {', '.join(missing)}"
            )
        mission = validate_claim_for_local_runner(claim)
        team_execution = mission.get("execution") if mission is not None else None
        agent_executor = None if team_execution else requested_executor(required_capabilities)
        if (
            not credentials.simulation
            and agent_executor is None
            and team_execution is None
            and config.local_runner is None
        ):
            raise RuntimeError(
                "aucun runner local n'est configuré pour cette mission"
            )

        if stop_requested:
            await patch_run(
                api_client,
                config,
                attempt_id,
                fencing_token,
                {
                    "status": "cancelled",
                    "technical_validation": technical_validation_payload(
                        "pending", "Processus local non démarré: arrêt déjà demandé."
                    ),
                    "evidence": [],
                    "result": {
                        "execution_mode": "not_started",
                        "technical_validation": "not_executed",
                        "evidence": [],
                        "worker_id": credentials.worker_id,
                        "message": "Arrêt demandé avant le lancement du processus local.",
                    },
                },
            )
            return

        if mission is None and not credentials.simulation:
            raise RuntimeError(
                "un worker réel exige une enveloppe mission complète et bornée"
            )
        agent_invocation = None
        if team_execution is not None:
            for executor_id in team_execution["executors"]:
                config.executors.spec_for(executor_id)
            config.executors.project_path(session.get("project_id"))
        elif agent_executor is None:
            validate_safe_local_policy(mission)
        else:
            if mission is None:
                raise RuntimeError(
                    "un exécuteur d'agent exige une enveloppe mission complète"
                )
            project_id = session.get("project_id")
            agent_invocation = invocation_from_mission(
                agent_executor,
                project_id,
                mission,
                {"steps": []},
            )
            # Vérifie exécutable, authentification et racine avant même l'appel de
            # planification : une configuration locale incomplète ne consomme rien.
            config.executors.spec_for(agent_executor)
            config.executors.project_path(agent_invocation.project_id)
        if mission is not None:
            remembered = read_checkpoint(config, attempt_id, "mission-deadline")
            if remembered is None:
                epoch = time() + max(0, claimed_clock + mission["duration_seconds"] - monotonic())
                write_checkpoint(config, attempt_id, "mission-deadline", {"deadline_epoch": epoch})
            else:
                epoch = remembered.get("deadline_epoch")
                if type(epoch) not in {int, float} or not math.isfinite(epoch):
                    raise RuntimeError("deadline de reprise invalide")
            mission_deadline = min(claimed_clock + mission["duration_seconds"], monotonic() + epoch - time())
        mission_budget = mission["budget"] if mission is not None else None
        budget_currency = (
            mission_budget["currency"] if mission_budget is not None else "EUR"
        )
        orchestrator_bounds = gateway_effect_bounds(
            config.provider_id, budget_currency
        )
        local_bounds = non_consuming_effect_bounds(budget_currency)
        extensions = await _await_work(
            lambda: load_extensions(api_client, config, credentials.worker_id, attempt_id,
                                    fencing_token, (task.get("meta") or {}).get("extensions") or {}),
            deadline=mission_deadline, stop_event=execution_stop)
        if extensions["mcp"] and agent_executor is None and team_execution is None:
            raise RuntimeError("les MCP d'exécution exigent un CLI d'agent configuré")
        planning_context = {"extensions": extensions}
        if team_execution is not None:
            limits = claim.get("execution_limits")
            if not isinstance(limits, dict) or type(limits.get("max_agents")) is not int or not 1 <= limits["max_agents"] <= 8:
                raise RuntimeError("plafond d'agents de la mission absent ou invalide")
            planning_context.update(execution=team_execution, execution_limits=limits)
        goal = mission["objective"] if mission is not None else task["title"]
        plan = await _await_work(
            lambda: budgeted_effect(
                api_client,
                config,
                credentials,
                attempt_id=attempt_id,
                fencing_token=fencing_token,
                effect_key="gateway-plan",
                provider=config.provider_id,
                phase="planning",
                budget=mission_budget,
                bounds=orchestrator_bounds,
                operation=lambda: gateway_plan(
                    gateway_client, config, session, goal,
                    attempt_id=attempt_id, deadline=mission_deadline, context=planning_context,
                ),
            ),
            deadline=mission_deadline,
            stop_event=execution_stop,
        )
        plan["_skills"] = extensions["skills"]
        plan["_mcp"] = extensions["mcp"]
        await _await_work(
            lambda: patch_run(
                api_client,
                config,
                attempt_id,
                fencing_token,
                {
                    "status": "running",
                    "plan": plan,
                    "append_logs": [
                        {
                            "level": "info",
                            "message": (
                                f"Plan {plan['plan_id']} via "
                                f"{plan.get('provider_id', config.provider_id)}"
                            ),
                        }
                    ],
                },
            ),
            deadline=mission_deadline,
            stop_event=execution_stop,
        )
        await _await_work(
            lambda: emit(
                api_client,
                config,
                "task.plan_ready",
                session,
                fencing_token=fencing_token,
                task_id=task_id,
                task_run_id=attempt_id,
                payload={
                    "plan_id": plan["plan_id"],
                    "steps": len(plan["steps"]),
                    "title": task["title"],
                },
            ),
            deadline=mission_deadline,
            stop_event=execution_stop,
        )
        steps = plan["steps"]
        for index, step in enumerate(steps, start=1):
            if execution_stop.is_set():
                raise RuntimeError("arrêt reçu pendant la préparation")
            await _await_work(
                lambda: emit(
                    api_client,
                    config,
                    "task.progress",
                    session,
                    fencing_token=fencing_token,
                    task_id=task_id,
                    task_run_id=attempt_id,
                    payload={
                        "step": step.get("title"),
                        "index": index,
                        "total": len(steps),
                        "title": task["title"],
                        "agent": agent["name"],
                    },
                ),
                deadline=mission_deadline,
                stop_event=execution_stop,
            )
            await _await_work(
                lambda: patch_run(
                    api_client,
                    config,
                    attempt_id,
                    fencing_token,
                    {
                        "workflow_step": step.get("title"),
                        "append_logs": [
                            {
                                "level": "info",
                                "message": (
                                    f"Étape {index}/{len(steps)}: {step.get('title')}"
                                ),
                            }
                        ],
                    },
                ),
                deadline=mission_deadline,
                stop_event=execution_stop,
            )
            if credentials.simulation:
                delay = config.step_seconds * random.uniform(0.6, 1.4)
                await _await_work(
                    lambda: asyncio.sleep(delay),
                    deadline=mission_deadline,
                    stop_event=execution_stop,
                )

        if execution_stop.is_set():
            stopped_status = _stopped_status(stop_context)
            await patch_run(
                api_client,
                config,
                attempt_id,
                fencing_token,
                {
                    "status": stopped_status,
                    "technical_validation": technical_validation_payload(
                        "pending", "Processus local non démarré après arrêt du lease."
                    ),
                    "evidence": [],
                    "result": {
                        "execution_mode": "not_started",
                        "technical_validation": "not_executed",
                        "evidence": [],
                        "stop_reason": stop_context["reason"],
                        "worker_id": credentials.worker_id,
                    },
                },
            )
            return

        if credentials.simulation:
            run_status, _, _ = execution_outcome(None, simulation=True)
            result = {
                "execution_mode": "simulation",
                "technical_validation": "not_executed",
                "user_acceptance": "pending",
                "worker_id": credentials.worker_id,
                "message": "Simulation terminée ; aucune exécution réelle ni preuve technique.",
            }
            await patch_run(
                api_client,
                config,
                attempt_id,
                fencing_token,
                {
                    "status": run_status,
                    "technical_validation": technical_validation_payload(
                        "pending", "Simulation: aucune validation technique exécutée."
                    ),
                    "evidence": [],
                    "result": result,
                },
            )
            return

        if team_execution is not None:
            assert mission is not None and mission_deadline is not None
            execution_label = "Équipe d'agents"

            def team_progress(value: dict) -> None:
                nonlocal result, evidence, technical_status
                result = value
                evidence = value["evidence"]
                technical_status = value["technical_validation"]

            async def team_publish(value: dict) -> None:
                await patch_run(api_client, config, attempt_id, fencing_token, {
                    "result": value, "evidence": value["evidence"],
                    "technical_validation": technical_validation_payload(value["technical_validation"], "Progression de l'équipe persistée par étape.")})

            result = await _await_work(
                lambda: run_team(api_client, config, credentials, attempt_id=attempt_id,
                    fencing_token=fencing_token, project_id=session["project_id"], mission=mission,
                    plan=plan, max_agents=limits["max_agents"], deadline=mission_deadline,
                    on_progress=team_progress, publish=team_publish),
                deadline=mission_deadline, stop_event=execution_stop)
            evidence = result["evidence"]
            technical_status = result["technical_validation"]
            execution_status = result["runner_status"]
            execution_succeeded = execution_status == "succeeded"
            execution_cancelled = False
        elif agent_executor is not None:
            assert mission is not None
            agent_invocation = invocation_from_mission(
                agent_executor,
                session.get("project_id"),
                mission,
                plan,
            )
            async def execute_agent():
                remaining = _remaining_work_seconds(mission_deadline)
                mcp = await acquire_mcp(api_client, config, worker_id=credentials.worker_id,
                    attempt_id=attempt_id, fencing_token=fencing_token, step_id="single-" + agent_executor,
                    snapshot=extensions["mcp"], timeout_seconds=min(config.executors.timeout_seconds, remaining or config.executors.timeout_seconds))
                return await run_executor(agent_invocation.executor, agent_invocation.project_id,
                    agent_invocation.requested_path, agent_invocation.prompt, config=config.executors,
                    timeout_seconds=_remaining_work_seconds(mission_deadline), allow_writes=agent_invocation.allow_writes, mcp=mcp)

            def capture_agent(execution) -> None:
                nonlocal evidence, result, technical_status
                nonlocal execution_label, execution_status, execution_succeeded, execution_cancelled
                execution_label = (
                    "Codex CLI" if agent_executor == "codex_cli" else "Claude Code"
                )
                execution_status = "succeeded" if execution.exit_code == 0 else "failed"
                execution_succeeded = execution.exit_code == 0
                execution_cancelled = False
                evidence = [
                    {
                        "kind": "agent_executor",
                        "summary": (
                            f"{execution_label} terminé avec le code {execution.exit_code}; "
                            "flux bruts conservés uniquement sous forme d'empreintes."
                        ),
                        "data": {
                            "executor": agent_executor,
                            "status": execution_status,
                            "project_id": agent_invocation.project_id,
                            "workspace_write": agent_invocation.allow_writes,
                            "spawned_agents": 1,
                            "spawned_agents_scope": "worker_managed_top_level_cli_only",
                            "stdout": {
                                "sha256": execution.stdout_sha256,
                                "total_bytes": execution.stdout_bytes,
                                "event_count": execution.event_count,
                            },
                            "stderr": {
                                "sha256": execution.stderr_sha256,
                                "total_bytes": execution.stderr_bytes,
                            },
                        },
                        "exit_code": execution.exit_code,
                    }
                ]
                technical_status = "passed" if execution_succeeded else "failed"
                result = {
                    "execution_mode": agent_executor,
                    "technical_validation": technical_status,
                    "evidence": evidence,
                    "runner_status": execution_status,
                    "exit_code": execution.exit_code,
                    "spawned_agents": 1,
                    "spawned_agents_scope": "worker_managed_top_level_cli_only",
                    "user_acceptance": "pending",
                    "worker_id": credentials.worker_id,
                }
                if execution.output is not None:
                    result["output"] = execution.output
                result["usage"] = {"cost": None, "currency": None, "tokens_input": None, "tokens_output": None, **(execution.usage or {})}
                capture_completed()

            execution = await _await_work(
                lambda: budgeted_effect(
                    api_client,
                    config,
                    credentials,
                    attempt_id=attempt_id,
                    fencing_token=fencing_token,
                    effect_key=f"agent-executor-{agent_executor}",
                    provider=agent_executor,
                    phase="execution",
                    on_completed=capture_agent,
                    on_reported=capture_reported,
                    budget=mission_budget,
                    # Les CLIs ne publient pas de plafond fiable de coût ou de
                    # jetons. Toute politique qui en exige un refuse donc le permis
                    # avant spawn ; seul l'appel d'outil est borné ici.
                    bounds=EffectBudgetBounds(tool_calls=1),
                    operation=execute_agent,
                ),
                deadline=mission_deadline,
                stop_event=execution_stop,
            )
        elif web_tests_available(
            config.web_tests,
            credentials.capabilities,
            simulation=credentials.simulation,
        ) and mission_requests_web_tests(mission):
            # Mission de tests web : l'exécution passe par la suite Playwright de
            # l'opérateur. Tout le reste de la boucle (arrêt, évaluation,
            # terminaison) est strictement celui du Lot C.
            web_lease = WebTestLease(
                worker_id=credentials.worker_id,
                task_run_id=attempt_id,
                attempt_number=attempt_number,
                fencing_token=fencing_token,
                project_id=session.get("project_id") or "",
                output_root=config.local_runner.run_root,
            )
            def capture_web(outcome) -> None:
                nonlocal evidence, result, technical_status
                nonlocal execution_label, execution_status, execution_succeeded, execution_cancelled
                execution_label = "Suite de tests web"
                execution_status = outcome.status
                execution_succeeded = outcome.succeeded
                execution_cancelled = outcome.error == "stopped"
                evidence = [outcome.evidence()]
                technical_status = "passed" if execution_succeeded else "failed"
                result = {
                    "execution_mode": "web_tests",
                    "technical_validation": technical_status,
                    "evidence": evidence,
                    "runner_status": outcome.status,
                    "exit_code": outcome.exit_code,
                    "test_run_id": outcome.test_run_id,
                    "user_acceptance": "pending",
                    "worker_id": credentials.worker_id,
                }
                capture_completed()

            outcome = await _await_work(
                lambda: budgeted_effect(
                    api_client,
                    config,
                    credentials,
                    attempt_id=attempt_id,
                    fencing_token=fencing_token,
                    effect_key="web-test-suite",
                    provider="playwright",
                    phase="execution",
                    on_completed=capture_web,
                    on_reported=capture_reported,
                    budget=mission_budget,
                    bounds=local_bounds,
                    operation=lambda: run_web_tests(
                        mission,
                        config.web_tests,
                        api=WorkerTestApi(
                            api_client, config.api_url, credentials.worker_id
                        ),
                        lease=web_lease,
                        stop_event=execution_stop,
                        # La deadline globale borne aussi le processus de test.
                        remaining_seconds=_remaining_work_seconds(
                            mission_deadline
                        ),
                    ),
                ),
                deadline=mission_deadline,
                stop_event=execution_stop,
            )
        else:
            assert config.local_runner is not None
            runner_request = request_from_claim(claim, plan)
            remaining = _remaining_work_seconds(mission_deadline)
            if remaining is not None:
                request_timeout = runner_request.timeout_seconds
                runner_request = replace(
                    runner_request,
                    timeout_seconds=(
                        remaining
                        if request_timeout is None
                        else min(request_timeout, remaining)
                    ),
                )
            def capture_local(execution) -> None:
                nonlocal evidence, result, technical_status
                nonlocal execution_label, execution_status, execution_succeeded, execution_cancelled
                execution_label = "Programme local"
                execution_status = execution.status
                execution_succeeded = execution.succeeded
                execution_cancelled = execution.status == "cancelled"
                evidence = [platform_evidence(execution, runner_request)]
                technical_status = "passed" if execution_succeeded else "failed"
                result = {
                    "execution_mode": "real_local_process",
                    "technical_validation": technical_status,
                    "evidence": evidence,
                    "runner_status": execution.status,
                    "exit_code": execution.exit_code,
                    "user_acceptance": "pending",
                    "worker_id": credentials.worker_id,
                }
                capture_completed()

            execution = await _await_work(
                lambda: budgeted_effect(
                    api_client,
                    config,
                    credentials,
                    attempt_id=attempt_id,
                    fencing_token=fencing_token,
                    effect_key="local-program",
                    provider="local-runner",
                    phase="execution",
                    on_completed=capture_local,
                    on_reported=capture_reported,
                    budget=mission_budget,
                    bounds=local_bounds,
                    operation=lambda: run_local_program(
                        config.local_runner,
                        runner_request,
                        stop_event=execution_stop,
                    ),
                ),
                deadline=mission_deadline,
                stop_event=execution_stop,
            )

        if execution_cancelled:
            stopped_status = _stopped_status(stop_context)
            result["stop_reason"] = stop_context["reason"] or "local_stop"
            await patch_run(
                api_client,
                config,
                attempt_id,
                fencing_token,
                {
                    "status": stopped_status,
                    "technical_validation": technical_validation_payload(
                        "failed", f"{execution_label} interrompu avant validation."
                    ),
                    "evidence": evidence,
                    "result": result,
                },
            )
            return

        if not execution_succeeded:
            stopped = execution_stop.is_set()
            terminal_status = _stopped_status(stop_context) if stopped else ("blocked" if execution_status == "blocked" else "failed")
            if stopped:
                result["stop_reason"] = stop_context["reason"]
            await patch_run(
                api_client,
                config,
                attempt_id,
                fencing_token,
                {
                    "status": terminal_status,
                    "technical_validation": technical_validation_payload(
                        technical_status or "failed",
                        f"{execution_label} terminé avec le statut {execution_status}.",
                    ),
                    "evidence": evidence,
                    "result": result,
                },
            )
            return

        if execution_stop.is_set():
            stopped_status = _stopped_status(stop_context)
            result["stop_reason"] = stop_context["reason"]
            await patch_run(
                api_client,
                config,
                attempt_id,
                fencing_token,
                {
                    "status": stopped_status,
                    "technical_validation": technical_validation_payload(
                        "passed", f"{execution_label} terminé avant la demande d'arrêt."
                    ),
                    "evidence": evidence,
                    "result": result,
                },
            )
            return

        acceptance_criteria = (
            mission["acceptance_criteria"] if mission is not None else []
        )
        evaluation_summary = (
            mission["expected_outcome"] if mission is not None else task["title"]
        )
        try:
            evaluation = await _await_work(
                lambda: budgeted_effect(
                    api_client,
                    config,
                    credentials,
                    attempt_id=attempt_id,
                    fencing_token=fencing_token,
                    effect_key="gateway-evaluate",
                    provider=config.provider_id,
                    phase="evaluation",
                    budget=mission_budget,
                    bounds=orchestrator_bounds,
                    operation=lambda: gateway_evaluate(
                        gateway_client,
                        config,
                        session,
                        evaluation_summary,
                        produced_output={"execution_evidence": evidence[0], "execution_evidence_all": evidence, "output": result.get("output")},
                        acceptance_criteria=acceptance_criteria,
                        attempt_id=attempt_id, deadline=mission_deadline,
                    ),
                ),
                deadline=mission_deadline,
                stop_event=execution_stop,
            )
        except ExecutorCleanupError:
            raise
        except Exception as exc:
            if execution_stop.is_set():
                result["evaluation"] = {"status": "interrupted"}
                result["stop_reason"] = stop_context["reason"]
                await patch_run(
                    api_client,
                    config,
                    attempt_id,
                    fencing_token,
                    {
                        "status": _stopped_status(stop_context),
                        "technical_validation": technical_validation_payload(
                            "passed",
                            f"{execution_label} terminé; évaluation interrompue par l'arrêt.",
                        ),
                        "evidence": evidence,
                        "result": result,
                    },
                )
                return

            # Le processus et sa preuve restent vrais même si le verdict du
            # provider devient indisponible. Sans verdict explicite, le run ne
            # peut toutefois jamais être promu en succès.
            result["evaluation"] = {
                "status": "unavailable",
                "error_type": type(exc).__name__,
            }
            result["user_acceptance"] = "unavailable"
            await patch_run(
                api_client,
                config,
                attempt_id,
                fencing_token,
                {
                    "status": "blocked",
                    "technical_validation": technical_validation_payload(
                        "passed",
                        f"{execution_label} terminé; verdict du provider indisponible.",
                    ),
                    "evidence": evidence,
                    "result": result,
                    "append_logs": [
                        {
                            "level": "error",
                            "message": "Évaluation provider indisponible; succès refusé.",
                        }
                    ],
                },
            )
            return

        run_status, _, _ = execution_outcome(evaluation, simulation=False)
        result["evaluation"] = evaluation
        if execution_stop.is_set():
            run_status = _stopped_status(stop_context)
            result["stop_reason"] = stop_context["reason"]
        await patch_run(
            api_client,
            config,
            attempt_id,
            fencing_token,
            {
                "status": run_status,
                "technical_validation": technical_validation_payload(
                    "passed", f"{execution_label} terminé avec un verdict technique réussi."
                ),
                "evidence": evidence,
                "result": result,
            },
        )
    except ExecutorCleanupError as exc:
        # Un arbre dont l'arrêt n'est pas prouvé ne doit jamais être converti en
        # résultat métier terminal : le renouvellement du lease cesse et le worker
        # remonte l'erreur pour cesser de réclamer du travail. Le lease distant
        # expire ou est réconcilié côté API ; il n'est pas déclaré libéré ici.
        logger.write(
            "critical",
            "Nettoyage de l'exécuteur non confirmé; arrêt de sécurité du worker",
            attempt_id=attempt_id,
            error=str(exc),
        )
        raise
    except Exception as exc:
        # A terminal PATCH can race with the API's transition to STOPPING before
        # the renew loop observes it. Reconcile that conflict as interrupted,
        # never as failed, and preserve any evidence already persisted locally.
        api_conflict = (
            isinstance(exc, httpx.HTTPStatusError)
            and exc.response.status_code == 409
        )
        if api_conflict and not execution_stop.is_set():
            stop_context["reason"] = "api_state_conflict"
            execution_stop.set()
        stopped = execution_stop.is_set()
        accounting_pending = result is not None and result.get("accounting", {}).get("status") == "unconfirmed"
        terminal_status = _stopped_status(stop_context) if stopped else ("blocked" if accounting_pending else "failed")
        if evidence:
            validation_status = technical_status or "failed"
            validation_summary = (
                "Tentative interrompue après production d'une preuve locale durable."
                if stopped
                else "Le worker a échoué après production d'une preuve locale durable."
            )
        else:
            validation_status = "pending" if stopped else "failed"
            validation_summary = (
                "Tentative arrêtée avant la production d'une preuve exploitable."
                if stopped
                else "Le worker a échoué avant de produire une preuve exploitable."
            )
        failure_body: dict[str, Any] = {
            "status": terminal_status,
            "technical_validation": technical_validation_payload(
                validation_status, validation_summary
            ),
            "evidence": evidence,
            "append_logs": [
                {
                    "level": "warning" if stopped else "error",
                    "message": "Tentative arrêtée" if stopped else "Échec du worker",
                }
            ],
        }
        if result is not None:
            if stopped:
                result["stop_reason"] = stop_context["reason"]
            failure_body["result"] = result
        await patch_run(
            api_client,
            config,
            attempt_id,
            fencing_token,
            failure_body,
        )
        if stopped or accounting_pending:
            return
        raise
    finally:
        stop_lease.set()
        await lease_task


async def _heartbeat_loop(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    stop: asyncio.Event,
    logger: WorkerLogger,
) -> None:
    while not stop.is_set():
        try:
            response = await client.post(
                f"{config.api_url}/workers/{credentials.worker_id}/heartbeat",
                json={
                    "capabilities": credentials.capabilities,
                    "max_concurrency": credentials.max_concurrency,
                    "simulation": credentials.simulation,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.write("warning", "Heartbeat impossible", error=str(exc))
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=credentials.heartbeat_interval_seconds
            )
        except TimeoutError:
            pass


async def _wait_or_stop(stop: asyncio.Event, delay: float) -> None:
    """Attend ``delay`` secondes ou l'ordre d'arrêt, selon ce qui vient en premier."""

    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
    except TimeoutError:
        pass


def probe_loop_enabled(config: WorkerConfig, credentials: WorkerCredentials) -> bool:
    """La boucle de sonde n'existe que si la capacité est réellement annoncée.

    Trois conditions cumulatives : capacité déclarée à l'API, worker réel (pas de
    simulation) et configuration locale valide. Une seule manquante ⇒ pas de
    boucle, donc aucun claim de sonde.
    """

    return (
        not credentials.simulation
        and WorkerCapability.MCP_STDIO_PROBE.value in credentials.capabilities
        and config.mcp_probe.enabled
        and bool(config.mcp_probe.allowed_executables)
    )


async def _probe_loop(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    stop: asyncio.Event,
    logger: WorkerLogger,
) -> None:
    """Réclame et exécute les sondes MCP stdio approuvées par la plateforme.

    Cette boucle est indépendante de la boucle mission : elle ne la ralentit pas
    et ne l'interrompt jamais. Aucune valeur d'environnement n'est journalisée.
    """

    if not probe_loop_enabled(config, credentials):
        # Défense en profondeur : même appelée directement, la boucle ne réclame
        # rien tant que la capacité n'est pas réellement annoncée et configurée.
        return
    while not stop.is_set():
        probe: dict[str, Any] | None = None
        try:
            response = await client.post(
                f"{config.api_url}/mcp/worker/probes/claim", json={}
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.write("warning", "Claim de sonde MCP impossible", error=str(exc))
            payload = None
        if isinstance(payload, dict):
            candidate = payload.get("probe")
            if isinstance(candidate, dict):
                probe = candidate
        if probe is None or not isinstance(probe.get("id"), str):
            await _wait_or_stop(stop, config.poll_interval)
            continue

        probe_id = probe["id"]
        logger.write("info", "Sonde MCP prise en charge", probe_id=probe_id)
        try:
            result = await run_stdio_probe(probe, config.mcp_probe)
        except Exception as exc:  # noqa: BLE001
            # La sonde est censée être fermée sur ses échecs ; un défaut
            # inattendu ne doit ni tuer la boucle ni laisser la sonde en attente.
            # Seul le type est journalisé : un message d'exception pourrait
            # contenir une valeur d'environnement injectée par l'API.
            logger.write(
                "error",
                "Sonde MCP interrompue",
                probe_id=probe_id,
                error_type=type(exc).__name__,
            )
            result = {
                "status": "failed",
                "protocol_version": None,
                "server_info": None,
                "tools": [],
                "exit_code": None,
                "stderr_tail": "",
                "duration_ms": 0,
                "error": "worker_error",
            }
        try:
            response = await client.post(
                f"{config.api_url}/mcp/worker/probes/{probe_id}/result",
                json=result,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.write(
                "warning",
                "Résultat de sonde MCP non transmis",
                probe_id=probe_id,
                error=str(exc),
            )
        else:
            logger.write(
                "info",
                "Sonde MCP terminée",
                probe_id=probe_id,
                status=str(result.get("status")),
            )


def _reap_completed_jobs(
    active: set[asyncio.Task[Any]], logger: WorkerLogger
) -> None:
    """Retire les jobs finis et propage toute clôture non confirmée."""

    completed = {item for item in active if item.done()}
    cleanup_error: ExecutorCleanupError | None = None
    for item in completed:
        try:
            item.result()
        except ExecutorCleanupError as exc:
            cleanup_error = cleanup_error or exc
            logger.write(
                "critical",
                "Arrêt de sécurité du worker après un nettoyage non confirmé",
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            logger.write("error", "Échec d'une tâche", error=str(exc))
    active.difference_update(completed)
    if cleanup_error is not None:
        raise cleanup_error


async def run_forever(
    config: WorkerConfig, credentials: WorkerCredentials, *, once: bool = False
) -> None:
    if credentials.api_origin != config.api_url:
        raise CredentialStateError(
            "Credentials liés à une autre origine API; réenregistrement requis"
        )
    config.validate_advertised_capabilities(
        credentials.capabilities,
        simulation=credentials.simulation,
        project_id=credentials.project_id,
        global_access=credentials.global_access,
    )
    logger = WorkerLogger(config.state_dir)
    logger.write(
        "info",
        "Worker démarré",
        worker_id=credentials.worker_id,
        api=config.api_url,
        provider=config.provider_id,
        concurrency=credentials.max_concurrency,
    )
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "X-Worker-Id": credentials.worker_id,
    }
    stop = asyncio.Event()
    active: set[asyncio.Task[Any]] = set()
    async with (
        httpx.AsyncClient(timeout=10.0, headers=headers, trust_env=False) as api_client,
        httpx.AsyncClient(
            timeout=15.0,
            headers=gateway_headers(config),
            trust_env=False,
        ) as gateway_client,
    ):
        heartbeat = asyncio.create_task(
            _heartbeat_loop(api_client, config, credentials, stop, logger)
        )
        scheduler_task: asyncio.Task | None = None
        if not once and credentials.global_access:
            scheduler_task = asyncio.create_task(
                automation_scheduler_loop(
                    api_client, config, credentials, stop, logger
                )
            )
        probe_task: asyncio.Task | None = None
        if probe_loop_enabled(config, credentials):
            logger.write("info", "Sonde MCP stdio activée")
            probe_task = asyncio.create_task(
                _probe_loop(api_client, config, credentials, stop, logger)
            )
        quota_task: asyncio.Task | None = None
        if not once and config.subscription_quotas.enabled:
            logger.write("info", "Relevé des quotas d'abonnement activé")
            quota_task = asyncio.create_task(
                subscription_quota_loop(api_client, config, credentials, stop, logger)
            )
        try:
            while True:
                _reap_completed_jobs(active, logger)
                if len(active) >= credentials.max_concurrency:
                    await asyncio.sleep(config.poll_interval)
                    continue
                try:
                    response = await api_client.post(
                        f"{config.api_url}/workers/{credentials.worker_id}/claim",
                        json={"provider_id": config.provider_id},
                    )
                    response.raise_for_status()
                    claim = response.json()
                except httpx.HTTPError as exc:
                    logger.write("warning", "Claim impossible", error=str(exc))
                    claim = {"task": None}
                # Un autre job peut avoir échoué pendant la requête HTTP. Ne
                # démarre jamais le claim reçu après une clôture non confirmée.
                _reap_completed_jobs(active, logger)
                if claim.get("task"):
                    title = claim["task"]["title"]
                    logger.write("info", "Tâche prise en charge", title=title)
                    job = asyncio.create_task(
                        process(api_client, gateway_client, config, credentials, claim, logger)
                    )
                    active.add(job)
                    if once:
                        await job
                        return
                else:
                    if once:
                        return
                    await asyncio.sleep(config.poll_interval)
        finally:
            if active:
                for job in active:
                    job.cancel()
                await asyncio.gather(*active, return_exceptions=True)
            stop.set()
            await heartbeat
            if scheduler_task is not None:
                await asyncio.wait({scheduler_task}, timeout=30)
                if not scheduler_task.done():
                    scheduler_task.cancel()
                await asyncio.gather(scheduler_task, return_exceptions=True)
            if probe_task is not None:
                await asyncio.wait({probe_task}, timeout=30)
                if not probe_task.done():
                    probe_task.cancel()
                await asyncio.gather(probe_task, return_exceptions=True)
            if quota_task is not None:
                # Une sonde en cours arrête elle-même l'arbre du CLI, même annulée.
                await asyncio.wait({quota_task}, timeout=30)
                if not quota_task.done():
                    quota_task.cancel()
                await asyncio.gather(quota_task, return_exceptions=True)


if __name__ == "__main__":
    from .cli import main

    raise SystemExit(main(["start"]))
