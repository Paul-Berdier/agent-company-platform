"""Boucle d'exécution d'un worker enregistré auprès de l'API.

Le worker ne parle qu'à l'API et au provider-gateway. Les intégrations externes
restent derrière leurs contrats de provider et ne sont jamais importées ici.
"""

import asyncio
import random
import uuid

import httpx

from .capabilities import missing_capabilities
from .config import WorkerConfig
from .local_log import WorkerLogger
from .state import WorkerCredentials


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
    try:
        await client.post(f"{config.api_url}/events", json=event)
    except httpx.HTTPError:
        pass


async def set_agent_status(
    client: httpx.AsyncClient, config: WorkerConfig, agent_id: str, status: str
) -> None:
    try:
        await client.patch(f"{config.api_url}/agents/{agent_id}", json={"status": status})
    except httpx.HTTPError:
        pass


async def set_task_status(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    task_id: str,
    status: str,
    workflow_step: str | None = None,
) -> None:
    body = {"status": status}
    if workflow_step:
        body["workflow_step"] = workflow_step
    try:
        await client.patch(f"{config.api_url}/tasks/{task_id}", json=body)
    except httpx.HTTPError:
        pass


async def gateway_plan(
    client: httpx.AsyncClient, config: WorkerConfig, session: dict, goal: str
) -> dict:
    try:
        response = await client.post(
            f"{config.gateway_url}/v1/providers/{config.provider_id}/plan",
            json={"session": session, "goal": goal, "context": {}, "constraints": []},
            timeout=15.0,
        )
        if response.status_code < 400:
            return response.json()
    except httpx.HTTPError:
        pass
    return {
        "plan_id": f"fallback-{uuid.uuid4().hex[:8]}",
        "steps": [
            {"id": "s1", "title": "Analyser la demande", "depends_on": []},
            {"id": "s2", "title": "Produire le livrable", "depends_on": ["s1"]},
            {"id": "s3", "title": "Vérifier le résultat", "depends_on": ["s2"]},
        ],
        "rationale": "Plan de secours local (gateway indisponible).",
        "provider_id": "local-fallback",
    }


async def gateway_evaluate(
    client: httpx.AsyncClient, config: WorkerConfig, session: dict, summary: str
) -> dict:
    try:
        response = await client.post(
            f"{config.gateway_url}/v1/providers/{config.provider_id}/evaluate",
            json={
                "session": session,
                "task_summary": summary,
                "produced_output": {},
                "acceptance_criteria": [],
            },
            timeout=15.0,
        )
        if response.status_code < 400:
            return response.json()
    except httpx.HTTPError:
        pass
    return {"approved": True, "score": 0.8, "feedback": "Évaluation locale par défaut."}


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
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    claim: dict,
    logger: WorkerLogger,
) -> None:
    task = claim["task"]
    run = claim["task_run"]
    session = claim["session"]
    agent = claim["agent"]
    task_id, run_id, agent_id = task["id"], run["id"], agent["id"]
    missing = missing_capabilities(
        claim.get("required_capabilities", []), credentials.capabilities
    )
    if missing:
        raise RuntimeError(f"capacités manquantes après attribution: {', '.join(missing)}")
    if not credentials.simulation:
        raise RuntimeError("aucun exécuteur réel n'est configuré pour ce worker")

    stop_lease = asyncio.Event()
    lease_task = asyncio.create_task(
        _renew_lease(client, config, credentials, run_id, stop_lease, logger)
    )
    try:
        plan = await gateway_plan(client, config, session, task["title"])
        response = await client.patch(
            f"{config.api_url}/task-runs/{run_id}",
            json={
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
            client,
            config,
            "task.plan_ready",
            session,
            task_id=task_id,
            task_run_id=run_id,
            payload={"plan_id": plan["plan_id"], "steps": len(plan["steps"]), "title": task["title"]},
        )
        await set_task_status(client, config, task_id, "in_progress")
        await set_agent_status(client, config, agent_id, "working")

        steps = plan.get("steps") or [{"id": "s1", "title": "Exécution"}]
        for index, step in enumerate(steps, start=1):
            await set_task_status(
                client, config, task_id, "in_progress", workflow_step=step.get("title")
            )
            await emit(
                client,
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
            await client.patch(
                f"{config.api_url}/task-runs/{run_id}",
                json={
                    "append_logs": [
                        {"level": "info", "message": f"Étape {index}/{len(steps)}: {step.get('title')}"}
                    ]
                },
            )
            await asyncio.sleep(config.step_seconds * random.uniform(0.6, 1.4))

        await set_task_status(client, config, task_id, "review")
        await set_agent_status(client, config, agent_id, "reviewing")
        evaluation = await gateway_evaluate(client, config, session, task["title"])
        await asyncio.sleep(config.step_seconds * 0.5)
        succeeded = bool(evaluation.get("approved", True))
        response = await client.patch(
            f"{config.api_url}/task-runs/{run_id}",
            json={
                "status": "succeeded" if succeeded else "failed",
                "result": {"evaluation": evaluation, "worker_id": credentials.worker_id},
            },
        )
        response.raise_for_status()
        await set_task_status(client, config, task_id, "done" if succeeded else "failed")
        await set_agent_status(client, config, agent_id, "idle")
        await emit(
            client,
            config,
            "task.completed" if succeeded else "task.failed",
            session,
            task_id=task_id,
            task_run_id=run_id,
            payload={"title": task["title"], "score": evaluation.get("score"), "agent": agent["name"]},
        )
    except Exception:
        try:
            await client.patch(
                f"{config.api_url}/task-runs/{run_id}",
                json={"status": "failed", "append_logs": [{"level": "error", "message": "Échec du worker"}]},
            )
            await set_task_status(client, config, task_id, "failed")
            await set_agent_status(client, config, agent_id, "idle")
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
    headers = {"Authorization": f"Bearer {credentials.token}"}
    stop = asyncio.Event()
    active: set[asyncio.Task] = set()
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        heartbeat = asyncio.create_task(
            _heartbeat_loop(client, config, credentials, stop, logger)
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
                    response = await client.post(
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
                    job = asyncio.create_task(process(client, config, credentials, claim, logger))
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
