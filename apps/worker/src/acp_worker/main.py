"""Boucle d'exécution d'un worker enregistré auprès de l'API.

Le worker ne parle qu'à l'API et au provider-gateway. Les intégrations externes
restent derrière leurs contrats de provider et ne sont jamais importées ici.
"""

import asyncio
import random
from typing import Any

import httpx

from .capabilities import missing_capabilities
from .config import WorkerConfig
from .local_log import WorkerLogger
from .state import WorkerCredentials


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
    response = await client.post(f"{config.api_url}/events", json=event)
    response.raise_for_status()


async def gateway_plan(
    client: httpx.AsyncClient, config: WorkerConfig, session: dict, goal: str
) -> dict:
    try:
        response = await client.post(
            f"{config.gateway_url}/v1/providers/{config.provider_id}/plan",
            headers=gateway_headers(config),
            json={"session": session, "goal": goal, "context": {}, "constraints": []},
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"planification indisponible: {exc}") from exc
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
    client: httpx.AsyncClient, config: WorkerConfig, session: dict, summary: str
) -> dict:
    try:
        response = await client.post(
            f"{config.gateway_url}/v1/providers/{config.provider_id}/evaluate",
            headers=gateway_headers(config),
            json={
                "session": session,
                "task_summary": summary,
                "produced_output": {},
                "acceptance_criteria": [],
            },
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"évaluation indisponible: {exc}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("réponse d'évaluation non JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("approved"), bool):
        raise RuntimeError("réponse d'évaluation sans verdict booléen explicite")
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


async def _renew_lease(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    run_id: str,
    stop: asyncio.Event,
    logger: WorkerLogger,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=15.0)
            return
        except TimeoutError:
            pass
        try:
            response = await client.post(
                f"{config.api_url}/workers/{credentials.worker_id}/leases/{run_id}/renew"
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.write("warning", "Renouvellement du lease impossible", run_id=run_id, error=str(exc))


async def process(
    api_client: httpx.AsyncClient,
    gateway_client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    claim: dict,
    logger: WorkerLogger,
) -> None:
    task = claim["task"]
    run = claim["task_run"]
    session = claim["session"]
    agent = claim["agent"]
    task_id, run_id = task["id"], run["id"]
    missing = missing_capabilities(
        claim.get("required_capabilities", []), credentials.capabilities
    )
    if missing:
        raise RuntimeError(f"capacités manquantes après attribution: {', '.join(missing)}")
    if not credentials.simulation:
        raise RuntimeError("aucun exécuteur réel n'est configuré pour ce worker")

    stop_lease = asyncio.Event()
    lease_task = asyncio.create_task(
        _renew_lease(api_client, config, credentials, run_id, stop_lease, logger)
    )
    try:
        plan = await gateway_plan(gateway_client, config, session, task["title"])
        response = await api_client.patch(
            f"{config.api_url}/task-runs/{run_id}",
            json={
                "status": "running",
                "plan": plan,
                "append_logs": [
                    {
                        "level": "info",
                        "message": f"Plan {plan['plan_id']} via {plan.get('provider_id', config.provider_id)}",
                    }
                ],
            },
        )
        response.raise_for_status()
        await emit(
            api_client,
            config,
            "task.plan_ready",
            session,
            task_id=task_id,
            task_run_id=run_id,
            payload={"plan_id": plan["plan_id"], "steps": len(plan["steps"]), "title": task["title"]},
        )
        steps = plan["steps"]
        for index, step in enumerate(steps, start=1):
            await emit(
                api_client,
                config,
                "task.progress",
                session,
                task_id=task_id,
                task_run_id=run_id,
                payload={
                    "step": step.get("title"),
                    "index": index,
                    "total": len(steps),
                    "title": task["title"],
                    "agent": agent["name"],
                },
            )
            await api_client.patch(
                f"{config.api_url}/task-runs/{run_id}",
                json={
                    "workflow_step": step.get("title"),
                    "append_logs": [
                        {"level": "info", "message": f"Étape {index}/{len(steps)}: {step.get('title')}"}
                    ]
                },
            )
            await asyncio.sleep(config.step_seconds * random.uniform(0.6, 1.4))

        if credentials.simulation:
            run_status, _, _ = execution_outcome(None, simulation=True)
            result = {
                "execution_mode": "simulation",
                "technical_validation": "not_executed",
                "user_acceptance": "pending",
                "worker_id": credentials.worker_id,
                "message": "Simulation terminée ; aucune exécution réelle ni preuve technique.",
            }
            response = await api_client.patch(
                f"{config.api_url}/task-runs/{run_id}",
                json={"status": run_status, "result": result},
            )
            response.raise_for_status()
            return

        evaluation = await gateway_evaluate(gateway_client, config, session, task["title"])
        await asyncio.sleep(config.step_seconds * 0.5)
        run_status, _, _ = execution_outcome(evaluation, simulation=False)
        response = await api_client.patch(
            f"{config.api_url}/task-runs/{run_id}",
            json={
                "status": run_status,
                "result": {
                    "evaluation": evaluation,
                    "execution_mode": "real",
                    "technical_validation": "provider_evaluation_only",
                    "user_acceptance": "pending",
                    "worker_id": credentials.worker_id,
                },
            },
        )
        response.raise_for_status()
    except Exception:
        try:
            await api_client.patch(
                f"{config.api_url}/task-runs/{run_id}",
                json={"status": "failed", "append_logs": [{"level": "error", "message": "Échec du worker"}]},
            )
        finally:
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


async def run_forever(
    config: WorkerConfig, credentials: WorkerCredentials, *, once: bool = False
) -> None:
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
    active: set[asyncio.Task] = set()
    async with (
        httpx.AsyncClient(timeout=10.0, headers=headers) as api_client,
        httpx.AsyncClient(timeout=15.0, headers=gateway_headers(config)) as gateway_client,
    ):
        heartbeat = asyncio.create_task(
            _heartbeat_loop(api_client, config, credentials, stop, logger)
        )
        try:
            while True:
                completed = {item for item in active if item.done()}
                for item in completed:
                    try:
                        item.result()
                    except Exception as exc:  # noqa: BLE001
                        logger.write("error", "Échec d'une tâche", error=str(exc))
                active -= completed
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
                await asyncio.gather(*active, return_exceptions=True)
            stop.set()
            await heartbeat


if __name__ == "__main__":
    from .cli import main

    raise SystemExit(main(["start"]))
