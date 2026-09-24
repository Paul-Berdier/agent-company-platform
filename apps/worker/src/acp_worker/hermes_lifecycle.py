"""Admission durable et suivi borné des opérations Hermes, sans rejouer un run."""

import asyncio
import hashlib
import json
import math
from time import monotonic, time
from typing import Any
from urllib.parse import quote

import httpx

from .checkpoints import read_checkpoint, write_checkpoint
from .config import WorkerConfig
from .executors import ExecutorCleanupError

_ACTIVE = {"started", "queued", "running", "waiting_for_approval", "stopping"}
_TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
_POLL_SECONDS = 0.2
_CLEANUP_SECONDS = 5.0
_RETENTION_SECONDS = 86400


def _body(response: httpx.Response, operation: str, run_id: str | None = None) -> dict:
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise RuntimeError("réponse Hermes trop volumineuse")
    data = response.json()
    if not isinstance(data, dict) or data.get("provider_id") != "hermes" or data.get("operation") != operation or data.get("status") not in _ACTIVE | _TERMINAL:
        raise RuntimeError("réponse d'opération Hermes invalide")
    returned_id = data.get("run_id")
    if not isinstance(returned_id, str) or not returned_id or len(returned_id) > 256 or (run_id is not None and returned_id != run_id):
        raise RuntimeError("identifiant de run Hermes incohérent")
    return data


async def run_operation(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    *,
    attempt_id: str,
    operation: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    deadline: float | None,
) -> dict:
    if operation not in {"plan", "evaluate"}:
        raise ValueError("opération Hermes inconnue")
    phase = f"hermes-{operation}"
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    state = read_checkpoint(config, attempt_id, phase)
    if state is None:
        state = {"gateway_url": config.gateway_url, "payload_sha256": digest,
                 "idempotency_key": "worker-hermes-" + hashlib.sha256(f"{config.api_url}\0{attempt_id}\0{operation}".encode()).hexdigest(),
                 "started_at": time(), "run_id": None, "status": "admitting"}
        write_checkpoint(config, attempt_id, phase, state)
    if state.get("gateway_url") != config.gateway_url or state.get("payload_sha256") != digest:
        raise RuntimeError("opération Hermes de reprise hors contexte; nouvel effet refusé")
    started_at = state.get("started_at")
    if not isinstance(started_at, (int, float)) or isinstance(started_at, bool) or not math.isfinite(started_at) or not isinstance(state.get("idempotency_key"), str):
        raise RuntimeError("point de reprise Hermes invalide")
    stored_id = state.get("run_id")
    if stored_id is not None and (not isinstance(stored_id, str) or not stored_id or len(stored_id) > 256):
        raise RuntimeError("identifiant de reprise Hermes invalide")
    base = f"{config.gateway_url}/v1/providers/hermes/operations/{operation}"

    def timeout() -> float:
        remaining = 15.0 if deadline is None else deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("durée globale de l'opération Hermes dépassée")
        return min(15.0, remaining)

    async def admit() -> None:
        if state.get("run_id"):
            return
        if time() < started_at or time() - started_at >= _RETENTION_SECONDS:
            raise RuntimeError("rétention d'idempotence Hermes expirée; reprise ambiguë refusée")
        for index in range(3):
            try:
                response = await client.post(base, headers={**headers, "Idempotency-Key": state["idempotency_key"]}, json=payload, timeout=timeout())
                if response.status_code in {408, 429, 500, 502, 503, 504} and index < 2:
                    await asyncio.sleep(_POLL_SECONDS)
                    continue
                data = _body(response, operation)
            except httpx.TransportError:
                if index == 2:
                    raise
                await asyncio.sleep(_POLL_SECONDS)
                continue
            state.update(run_id=data["run_id"], status=data["status"])
            write_checkpoint(config, attempt_id, phase, state)
            return

    async def poll() -> dict:
        response = await client.get(f"{base}/{quote(state['run_id'], safe='')}", headers=headers, timeout=timeout())
        data = _body(response, operation, state["run_id"])
        state["status"] = data["status"]
        write_checkpoint(config, attempt_id, phase, state)
        return data

    async def stop_and_confirm() -> None:
        nonlocal deadline
        deadline = monotonic() + _CLEANUP_SECONDS
        try:
            async with asyncio.timeout(_CLEANUP_SECONDS):
                await admit()
                response = await client.post(f"{config.gateway_url}/v1/providers/hermes/runs/{quote(state['run_id'], safe='')}/stop", headers=headers, timeout=timeout())
                response.raise_for_status()
                while True:
                    data = await poll()
                    if data["status"] in _TERMINAL:
                        return
                    await asyncio.sleep(_POLL_SECONDS)
        except (Exception, asyncio.CancelledError) as exc:
            raise ExecutorCleanupError("arrêt Hermes non confirmé; intervention requise avant reprise") from exc

    try:
        await admit()
        # Même une admission terminale ne porte pas nécessairement son résultat.
        # Toujours lire le run identifié, sans nouvelle admission ni nouvelle clé.
        while True:
            data = await poll()
            if data["status"] == "completed":
                result = data.get("result")
                if not isinstance(result, dict):
                    raise RuntimeError("opération Hermes terminée sans résultat vérifiable")
                return result
            if data["status"] in _TERMINAL:
                raise RuntimeError(f"opération Hermes terminée avec le statut {data['status']}")
            if data["status"] == "waiting_for_approval":
                await stop_and_confirm()
                raise RuntimeError("Hermes demande une approbation indisponible; opération arrêtée")
            await asyncio.sleep(_POLL_SECONDS)
    except (asyncio.CancelledError, TimeoutError):
        await stop_and_confirm()
        raise
    except (httpx.HTTPError, ValueError, RuntimeError):
        # Une rupture du suivi n'autorise pas à oublier un run distant actif.
        if state.get("status") not in _TERMINAL:
            await stop_and_confirm()
        raise
