"""Worker simulé : `python -m acp_worker.main`.

Boucle : claim d'une tâche `queued` auprès de l'API → plan via le
provider-gateway (orchestrateur configurable, mock par défaut) → simulation
des étapes avec événements de progression → évaluation → clôture.

Le worker ne parle qu'à l'API et au gateway : jamais à Hermes directement.
"""

import asyncio
import os
import random
import uuid

import httpx

API_URL = os.environ.get("ACP_API_URL", "http://localhost:8000").rstrip("/")
GATEWAY_URL = os.environ.get("ACP_PROVIDER_GATEWAY_URL", "http://localhost:8002").rstrip("/")
PROVIDER_ID = os.environ.get("ACP_ORCHESTRATOR_PROVIDER", "mock")
POLL_INTERVAL = float(os.environ.get("ACP_WORKER_POLL_INTERVAL", "2.0"))
STEP_SECONDS = float(os.environ.get("ACP_WORKER_STEP_SECONDS", "3.0"))
WORKER_ID = os.environ.get("ACP_WORKER_ID", f"worker-{uuid.uuid4().hex[:6]}")


async def emit(client: httpx.AsyncClient, event_type: str, session: dict, **extra) -> None:
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
        await client.post(f"{API_URL}/events", json=event)
    except httpx.HTTPError:
        pass


async def set_agent_status(client: httpx.AsyncClient, agent_id: str, status: str) -> None:
    try:
        await client.patch(f"{API_URL}/agents/{agent_id}", json={"status": status})
    except httpx.HTTPError:
        pass


async def set_task_status(client: httpx.AsyncClient, task_id: str, status: str,
                          workflow_step: str | None = None) -> None:
    body = {"status": status}
    if workflow_step:
        body["workflow_step"] = workflow_step
    try:
        await client.patch(f"{API_URL}/tasks/{task_id}", json=body)
    except httpx.HTTPError:
        pass


async def gateway_plan(client: httpx.AsyncClient, session: dict, goal: str) -> dict:
    """Demande un plan à l'orchestrateur ; plan de secours local si indisponible."""
    try:
        resp = await client.post(
            f"{GATEWAY_URL}/v1/providers/{PROVIDER_ID}/plan",
            json={"session": session, "goal": goal, "context": {}, "constraints": []},
            timeout=15.0,
        )
        if resp.status_code < 400:
            return resp.json()
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


async def gateway_evaluate(client: httpx.AsyncClient, session: dict, summary: str) -> dict:
    try:
        resp = await client.post(
            f"{GATEWAY_URL}/v1/providers/{PROVIDER_ID}/evaluate",
            json={"session": session, "task_summary": summary,
                  "produced_output": {}, "acceptance_criteria": []},
            timeout=15.0,
        )
        if resp.status_code < 400:
            return resp.json()
    except httpx.HTTPError:
        pass
    return {"approved": True, "score": 0.8, "feedback": "Évaluation locale par défaut."}


async def process(client: httpx.AsyncClient, claim: dict) -> None:
    task = claim["task"]
    run = claim["task_run"]
    session = claim["session"]
    agent = claim["agent"]
    task_id, run_id, agent_id = task["id"], run["id"], agent["id"]

    plan = await gateway_plan(client, session, task["title"])
    await client.patch(f"{API_URL}/task-runs/{run_id}", json={
        "plan": plan,
        "append_logs": [{"level": "info", "message": f"Plan {plan['plan_id']} via {plan.get('provider_id', PROVIDER_ID)}"}],
    })
    await emit(client, "task.plan_ready", session, task_id=task_id, task_run_id=run_id,
               payload={"plan_id": plan["plan_id"], "steps": len(plan["steps"]), "title": task["title"]})

    await set_task_status(client, task_id, "in_progress")
    await set_agent_status(client, agent_id, "working")

    steps = plan.get("steps") or [{"id": "s1", "title": "Exécution"}]
    for index, step in enumerate(steps, start=1):
        await set_task_status(client, task_id, "in_progress", workflow_step=step.get("title"))
        await emit(client, "task.progress", session, task_id=task_id, task_run_id=run_id,
                   payload={"step": step.get("title"), "index": index, "total": len(steps),
                            "title": task["title"], "agent": agent["name"]})
        await client.patch(f"{API_URL}/task-runs/{run_id}", json={
            "append_logs": [{"level": "info", "message": f"Étape {index}/{len(steps)}: {step.get('title')}"}],
        })
        await asyncio.sleep(STEP_SECONDS * random.uniform(0.6, 1.4))

    await set_task_status(client, task_id, "review")
    await set_agent_status(client, agent_id, "reviewing")
    evaluation = await gateway_evaluate(client, session, task["title"])
    await asyncio.sleep(STEP_SECONDS * 0.5)

    succeeded = bool(evaluation.get("approved", True))
    await client.patch(f"{API_URL}/task-runs/{run_id}", json={
        "status": "succeeded" if succeeded else "failed",
        "result": {"evaluation": evaluation, "worker_id": WORKER_ID},
    })
    await set_task_status(client, task_id, "done" if succeeded else "failed")
    await set_agent_status(client, agent_id, "idle")
    await emit(client, "task.completed" if succeeded else "task.failed", session,
               task_id=task_id, task_run_id=run_id,
               payload={"title": task["title"], "score": evaluation.get("score"),
                        "agent": agent["name"]})


async def run_forever() -> None:
    print(f"[{WORKER_ID}] démarrage — api={API_URL} gateway={GATEWAY_URL} provider={PROVIDER_ID}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                resp = await client.post(f"{API_URL}/worker/claim",
                                         json={"worker_id": WORKER_ID, "provider_id": PROVIDER_ID})
                claim = resp.json() if resp.status_code < 400 else {"task": None}
            except httpx.HTTPError:
                claim = {"task": None}
            if claim.get("task"):
                title = claim["task"]["title"]
                print(f"[{WORKER_ID}] tâche prise en charge : {title}")
                try:
                    await process(client, claim)
                    print(f"[{WORKER_ID}] tâche terminée : {title}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[{WORKER_ID}] échec : {exc}")
            else:
                await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_forever())
