"""Boucle légère qui élit un worker comme planificateur via l'API.

Le worker ne lit jamais la base. Il ne conserve que son identifiant de processus
et le dernier fence reçu; toute décision et toute matérialisation restent côté API.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import httpx

from .config import WorkerConfig
from .local_log import WorkerLogger
from .state import WorkerCredentials


def _lease_from_payload(
    payload: Any, *, worker_id: str, holder_id: str
) -> int:
    if not isinstance(payload, dict):
        raise ValueError("réponse de bail invalide")
    token = payload.get("fencing_token")
    if (
        payload.get("worker_id") != worker_id
        or payload.get("holder_id") != holder_id
        or not isinstance(token, int)
        or isinstance(token, bool)
        or token < 1
        or not isinstance(payload.get("lease_expires_at"), str)
    ):
        raise ValueError("réponse de bail invalide")
    return token


async def _wait_or_stop(stop: asyncio.Event, delay: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
    except TimeoutError:
        pass


async def automation_scheduler_loop(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    stop: asyncio.Event,
    logger: WorkerLogger,
) -> None:
    """Concourt au bail et cadence les ticks jusqu'à l'arrêt du worker."""

    # Défense en profondeur : la boucle n'émet même pas de requête avec des
    # credentials limités à un projet. L'API réapplique la même frontière.
    if not credentials.global_access:
        return

    holder_id = uuid4().hex
    fence: int | None = None
    base = (
        f"{config.api_url}/workers/{credentials.worker_id}/automation-scheduler"
    )
    try:
        while not stop.is_set():
            try:
                response = await client.post(
                    f"{base}/lease", json={"holder_id": holder_id}
                )
                if response.status_code == 409:
                    fence = None
                    await _wait_or_stop(stop, config.poll_interval)
                    continue
                response.raise_for_status()
                fence = _lease_from_payload(
                    response.json(),
                    worker_id=credentials.worker_id,
                    holder_id=holder_id,
                )

                response = await client.post(
                    f"{base}/tick",
                    headers={"X-Scheduler-Fencing-Token": str(fence)},
                    json={"holder_id": holder_id, "limit": 25},
                )
                if response.status_code == 409:
                    fence = None
                    await _wait_or_stop(stop, config.poll_interval)
                    continue
                response.raise_for_status()
                payload = response.json()
                if (
                    not isinstance(payload, dict)
                    or payload.get("fencing_token") != fence
                ):
                    raise ValueError("réponse de tick invalide")
                activity = sum(
                    int(payload.get(name, 0))
                    for name in (
                        "reconciled",
                        "examined",
                        "disabled_after_failures",
                    )
                    if isinstance(payload.get(name, 0), int)
                )
                if activity:
                    logger.write(
                        "info",
                        "Tick du planificateur terminé",
                        examined=int(payload.get("examined", 0)),
                        launched=int(payload.get("launched", 0)),
                        reconciled=int(payload.get("reconciled", 0)),
                    )
            except (httpx.HTTPError, ValueError):
                # Ni corps de réponse ni exception distante dans les logs : ils
                # peuvent provenir d'un proxy et ne sont pas une donnée fiable.
                logger.write("warning", "Planificateur API momentanément indisponible")
            await _wait_or_stop(stop, config.poll_interval)
    finally:
        if fence is not None:

            async def release() -> None:
                try:
                    response = await client.post(
                        f"{base}/lease/release",
                        headers={"X-Scheduler-Fencing-Token": str(fence)},
                        json={"holder_id": holder_id},
                    )
                    if response.status_code not in {204, 409}:
                        response.raise_for_status()
                except httpx.HTTPError:
                    # L'expiration serveur garantit la reprise même si la
                    # libération gracieuse se perd avec la connexion.
                    pass

            await asyncio.shield(release())
