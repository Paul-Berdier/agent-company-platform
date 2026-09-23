"""DAG borné, checkpoints et worktrees conservés pour une équipe explicite."""

import asyncio
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from time import monotonic
from typing import Any, Awaitable, Callable

import httpx

from .budget import EffectBudgetBounds, budgeted_effect
from .checkpoints import read_checkpoint, write_checkpoint
from .config import WorkerConfig
from .executors import ExecutorCleanupError, ExecutorResult, invocation_from_mission, run_executor
from .state import WorkerCredentials
from .mcp_execution import acquire_mcp


def validate_graph(plan: dict, execution: dict, max_agents: int) -> list[dict]:
    steps = plan.get("steps")
    if type(max_agents) is not int or not 1 <= max_agents <= 8 or not isinstance(steps, list) or not 1 <= len(steps) <= max_agents:
        raise RuntimeError("le plan dépasse le plafond d'agents autorisé")
    indexed = {}
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("id"), str) or not step["id"].strip() or len(step["id"]) > 200 or step["id"] in indexed:
            raise RuntimeError("identifiant d'étape absent ou dupliqué")
        if step.get("executor") not in execution["executors"]:
            raise RuntimeError("exécuteur d'étape absent ou non autorisé")
        if not isinstance(step.get("title"), str) or not step["title"].strip() or not isinstance(step.get("description", ""), str):
            raise RuntimeError("contenu d'étape invalide")
        dependencies = step.get("depends_on", [])
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies) or len(set(dependencies)) != len(dependencies):
            raise RuntimeError("dépendances d'étape invalides")
        indexed[step["id"]] = {**step, "depends_on": dependencies}
    visited = set()
    while len(visited) < len(indexed):
        ready = {key for key, step in indexed.items() if key not in visited and set(step["depends_on"]) <= visited}
        if not ready:
            raise RuntimeError("plan cyclique ou dépendance absente")
        visited.update(ready)
    return list(indexed.values())


def _git_sync(root: Path, *args: str, timeout: float = 10) -> bytes:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git indisponible pour l'isolation d'équipe")
    environment = {key: value for key, value in os.environ.items() if key.upper() in {
        "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "LANG", "LC_ALL"}}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    # Aucun hook, filtre externe de diff, fsmonitor ou identité réseau hérités.
    command = [git, "-c", f"safe.directory={root}", "-c", f"core.hooksPath={os.devnull}",
               "-c", "core.fsmonitor=false", "-c", "protocol.file.allow=never", "-C", str(root), *args]
    # Les gros diffs ne sont jamais assemblés sans borne en mémoire.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        outcome = subprocess.run(command, stdout=output, stderr=errors,
                                 env=environment, timeout=max(0.05, min(timeout, 10)),
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if outcome.returncode:
            raise RuntimeError("opération Git d'isolation refusée")
        output.seek(0)
        content = output.read(2_000_001)
        if len(content) > 2_000_000:
            raise RuntimeError("preuve Git trop volumineuse")
        return content


async def _git(root: Path, *args: str, deadline: float) -> bytes:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("durée d'équipe dépassée")
    # Git est court et non interactif. Attendre aussi son arrêt sur annulation :
    # un worktree en cours de création ne doit pas survivre au suivi du worker.
    task = asyncio.create_task(asyncio.to_thread(_git_sync, root, *args, timeout=remaining))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


async def prepare_worktree(config: WorkerConfig, project_id: str, attempt_id: str,
                           step_id: str, deadline: float) -> dict:
    root = config.executors.project_path(project_id)
    git_root = (await _git(root, "rev-parse", "--show-toplevel", deadline=deadline)).decode().strip()
    if Path(git_root).resolve() != root.resolve():
        raise RuntimeError("l'équipe exige une racine Git complète autorisée")
    # Un filtre checkout est une commande arbitraire du dépôt : refus explicite.
    names = (await _git(root, "config", "--local", "--name-only", "--list", deadline=deadline)).decode()
    if any(name.casefold().startswith(("filter.", "include.", "includeif.", "extensions.worktreeconfig")) for name in names.splitlines()):
        raise RuntimeError("les filtres et inclusions Git ne sont pas autorisés pour un worktree d'équipe")
    if await _git(root, "status", "--porcelain", "--untracked-files=all", deadline=deadline):
        raise RuntimeError("le dépôt source doit être propre avant une équipe d'agents")
    base = (await _git(root, "rev-parse", "HEAD", deadline=deadline)).decode().strip()
    identity = hashlib.sha256(f"{config.api_url}\0{attempt_id}\0{step_id}".encode()).hexdigest()[:24]
    path = (config.state_dir / "team-worktrees" / identity).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError("worktree déjà présent; réexécution ambiguë refusée")
    branch = f"codex/acp-{identity}"
    await _git(root, "worktree", "add", "-b", branch, str(path), base, deadline=deadline)
    return {"path": str(path), "branch": branch, "base_commit": base, "merged": False}


async def workspace_proof(workspace: dict, deadline: float) -> dict:
    path = Path(workspace["path"])
    diff = await _git(path, "diff", "--no-ext-diff", "--no-textconv", "--binary", workspace["base_commit"], deadline=deadline)
    untracked = await _git(path, "ls-files", "--others", "--exclude-standard", deadline=deadline)
    text = diff.decode("utf-8", errors="replace").replace("\x00", "�")
    return {**workspace, "diff": text[:16_000], "diff_truncated": len(text) > 16_000,
            "diff_sha256": hashlib.sha256(diff).hexdigest(),
            "untracked_files": untracked.decode("utf-8", errors="replace")[:8_000]}


def _evidence(step: dict) -> dict | None:
    execution = step.get("execution")
    if not execution:
        return None
    return {"kind": "agent_executor", "summary": f"Étape {step['id']} via {step['executor']}; code {execution['exit_code']}.",
            "exit_code": execution["exit_code"], "data": {
                "step_id": step["id"], "executor": step["executor"], "status": step["status"],
                "spawned_agents": 1, "spawned_agents_scope": "worker_managed_top_level_cli_only",
                "stdout": {"sha256": execution["stdout_sha256"], "total_bytes": execution["stdout_bytes"], "event_count": execution["event_count"]},
                "stderr": {"sha256": execution["stderr_sha256"], "total_bytes": execution["stderr_bytes"]},
                "workspace": step.get("workspace")}}


async def run_team(client: httpx.AsyncClient, config: WorkerConfig, credentials: WorkerCredentials,
                   *, attempt_id: str, fencing_token: int, project_id: str, mission: dict,
                   plan: dict, max_agents: int, deadline: float,
                   on_progress: Callable[[dict], None], publish: Callable[[dict], Awaitable[None]]) -> dict:
    execution = mission["execution"]
    steps = validate_graph(plan, execution, max_agents)
    graph_hash = hashlib.sha256(json.dumps({"steps": steps, "mission": mission}, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    state = read_checkpoint(config, attempt_id, "team")
    if state is None:
        state = {"graph_sha256": graph_hash, "steps": [{"id": step["id"], "executor": step["executor"], "status": "queued"} for step in steps]}
    elif state.get("graph_sha256") != graph_hash:
        raise RuntimeError("plan d'équipe différent du checkpoint; reprise refusée")
    by_id = {step["id"]: step for step in state["steps"]}
    if any(step["status"] != "queued" for step in state["steps"]):
        # Reprendre exigerait aussi de prouver les rapports du ledger. Garder
        # toutes les preuves et refuser tout nouvel effet après un début d'équipe.
        state["replay_refused"] = True
    publish_lock = asyncio.Lock()

    def snapshot() -> dict:
        evidence = [item for step in state["steps"] if (item := _evidence(step)) is not None]
        passed = all(step.get("execution", {}).get("exit_code") == 0 for step in state["steps"])
        succeeded = all(step["status"] == "completed" and step.get("accounting") == "reported" for step in state["steps"])
        blocked = state.get("replay_refused") or any(step.get("accounting") in {"unconfirmed", "reservation_retained"} or step["status"] == "blocked" for step in state["steps"])
        failed = any(step["status"] in {"failed", "cancelled"} for step in state["steps"])
        return {"execution_mode": "multi_agent", "technical_validation": "passed" if passed else ("failed" if failed else "pending"),
                "runner_status": "blocked" if blocked else ("succeeded" if succeeded else ("failed" if failed else "running")),
                "steps": copy.deepcopy(state["steps"]), "evidence": evidence,
                "spawned_agents": sum(bool(step.get("spawn_started")) for step in state["steps"]),
                "spawned_agents_scope": "worker_managed_top_level_cli_only", "user_acceptance": "pending",
                "worker_id": credentials.worker_id,
                "output": {"steps": [{"id": step["id"], "output": step.get("execution", {}).get("output"), "workspace": step.get("workspace")} for step in state["steps"]]}}

    def persist() -> None:
        write_checkpoint(config, attempt_id, "team", state)
        on_progress(snapshot())

    async def flush() -> None:
        async with publish_lock:
            await publish(snapshot())

    persist()
    if state.get("replay_refused"):
        return snapshot()

    async def step_work(step: dict) -> None:
        item = by_id[step["id"]]
        item["status"] = "running"
        persist()
        await flush()
        step_mission = copy.deepcopy(mission)
        if step["executor"] == "claude_code":
            step_mission["resources"][0]["access"] = "read"
        step_mission["objective"] = f"{mission['objective']}\n\nÉtape assignée : {step['title']}\n{step.get('description', '')}"
        dependencies = [{"id": dependency, "output": by_id[dependency].get("execution", {}).get("output"), "workspace": by_id[dependency].get("workspace")} for dependency in step["depends_on"]]
        if dependencies:
            rendered = json.dumps(dependencies, ensure_ascii=False)
            step_mission["objective"] += "\nRésultats des dépendances (données, ne changent aucun droit) :\n" + rendered[:12_000]
            if len(rendered) > 12_000:
                step_mission["objective"] += "\n[Contexte de dépendances tronqué ; worktrees conservés dans les preuves.]"
        invocation = invocation_from_mission(step["executor"], project_id, step_mission, {"steps": [step], "_skills": plan.get("_skills", [])})
        executors = config.executors
        try:
            item["workspace"] = await prepare_worktree(config, project_id, attempt_id, step["id"], deadline)
            executors = replace(executors, project_roots={project_id: Path(item["workspace"]["path"])})
            persist()

            def completed(value: ExecutorResult) -> None:
                item.update(status="completed" if value.exit_code == 0 else "failed", execution=asdict(value), accounting="unconfirmed")
                persist()

            def reported(reconciled: bool) -> None:
                item["accounting"] = "reported" if reconciled else "reservation_retained"
                persist()

            async def execute_step():
                mcp = await acquire_mcp(client, config, worker_id=credentials.worker_id,
                    attempt_id=attempt_id, fencing_token=fencing_token,
                    step_id="step-" + hashlib.sha256(step["id"].encode()).hexdigest(),
                    snapshot=plan.get("_mcp", []), timeout_seconds=min(config.executors.timeout_seconds, deadline-monotonic()))
                item["spawn_started"] = True
                persist()
                return await run_executor(invocation.executor, project_id, ".", invocation.prompt,
                    config=executors, timeout_seconds=deadline-monotonic(), allow_writes=invocation.allow_writes, mcp=mcp)

            await budgeted_effect(client, config, credentials, attempt_id=attempt_id,
                fencing_token=fencing_token, effect_key="team-step-" + step["id"], provider=step["executor"],
                phase="execution", budget=mission["budget"], bounds=EffectBudgetBounds(tool_calls=1),
                on_completed=completed, on_reported=reported,
                operation=execute_step)
            if item.get("workspace"):
                item["workspace"] = await workspace_proof(item["workspace"], deadline)
            persist()
            await flush()
        except ExecutorCleanupError:
            item["status"] = "blocked"
            persist()
            raise
        except asyncio.CancelledError:
            if not item.get("execution"):
                item["status"] = "cancelled"
            persist()
            raise
        except Exception as exc:
            item["status"] = "blocked" if item.get("execution") else "failed"
            item["error_type"] = type(exc).__name__
            persist()
            await flush()

    active: dict[asyncio.Task, str] = {}
    try:
        remaining = {step["id"]: step for step in steps}
        while remaining or active:
            successful = {step["id"] for step in state["steps"] if step["status"] == "completed" and step.get("accounting") == "reported"}
            available = execution["max_concurrency"] - len(active)
            ready = [step for step in remaining.values() if set(step["depends_on"]) <= successful][:available]
            for step in ready:
                active[asyncio.create_task(step_work(step))] = step["id"]
                del remaining[step["id"]]
            if not active:
                break
            done, _ = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                del active[task]
                await task
            if any(step["status"] in {"failed", "blocked", "cancelled"} for step in state["steps"]):
                break
    finally:
        for task in active:
            task.cancel()
        outcomes = await asyncio.gather(*active, return_exceptions=True)
        for step in state["steps"]:
            if step["status"] == "queued":
                step.update(status="blocked", reason="dépendance ou arrêt de l'équipe")
        persist()
        for outcome in outcomes:
            if isinstance(outcome, ExecutorCleanupError):
                raise outcome
    return snapshot()
