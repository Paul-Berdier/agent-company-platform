"""Service de diffusion temps réel.

L'API pousse chaque événement sur `POST /internal/events` ; les clients web
sont connectés en WebSocket sur `/ws` avec des filtres optionnels par
workspace / projet / département.

Lot H3 : l'ingestion est idempotente par ``event.id``. Le relais d'outbox livre
au-moins-une-fois et renvoie un événement dont le commit de livraison a échoué ;
un identifiant déjà vu répond ``{"ok": true, "duplicate": true}`` sans diffusion, et
un identifiant en cours de diffusion n'est jamais diffusé une seconde fois (0.9.1).
Le registre (``DeliveryLedger``) vit en mémoire : après un redémarrage, un lot
renvoyé peut être rediffusé au plus une fois. Les en-têtes ``X-ACP-*`` du relais
sont facultatifs : le relais direct historique, qui n'en pose aucun, reste accepté.
"""

import asyncio
import os
import secrets
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware

from acp_contracts import Event

from .dedupe import DeliveryLedger, dedupe_size, inflight_wait_seconds

app = FastAPI(title="Agent Company Platform — Event Service", version="0.10.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "ACP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, dict[str, str | None]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, filters: dict[str, str | None]) -> None:
        await ws.accept()
        async with self._lock:
            self._clients[ws] = filters

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(ws, None)

    @staticmethod
    def _matches(event: Event, filters: dict[str, str | None]) -> bool:
        for field, wanted in filters.items():
            if wanted and getattr(event, field, None) != wanted:
                return False
        return True

    async def broadcast(self, event: Event) -> None:
        payload = event.model_dump(mode="json")
        async with self._lock:
            clients = list(self._clients.items())
        for ws, filters in clients:
            if not self._matches(event, filters):
                continue
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 — client déconnecté
                await self.disconnect(ws)


manager = ConnectionManager()

ledger = DeliveryLedger(max_ids=dedupe_size())
"""Registre des livraisons du processus : borné, en mémoire, partagé par les routes."""

inflight_wait = inflight_wait_seconds()
"""Attente d'un renvoi pendant que l'original est diffusé (lue au démarrage)."""


def _require_internal_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Authentifie l'appel de service sans exposer le secret dans l'URL."""
    token = os.environ.get("ACP_EVENT_SERVICE_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="L'authentification interne du service d'événements n'est pas configurée.",
        )

    supplied = authorization or ""
    if not secrets.compare_digest(
        supplied.encode("utf-8"), f"Bearer {token}".encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification interne invalide.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _unsafe_anonymous_websocket_enabled() -> bool:
    return os.environ.get(
        "ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET", ""
    ).strip().lower() in {"1", "true", "yes", "on"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "event-service"}


@app.post("/internal/events", dependencies=[Depends(_require_internal_token)])
async def ingest(event: Event):
    """Diffuse un événement une seule fois par identifiant, dans la fenêtre du registre.

    Le doublon est **acquitté** (2xx) et non refusé : pour le relais, un événement
    déjà diffusé est une livraison réussie, et un refus le ferait renvoyer sans fin.
    La mémorisation suit la diffusion : un événement que personne n'a reçu n'est
    jamais marqué comme vu.

    Un renvoi qui arrive **pendant** la diffusion de l'original (relais qui a dépassé
    son délai HTTP) attend la fin de celle-ci, au plus ``inflight_wait`` secondes :
    réussie, il est acquitté comme doublon ; échouée, il reprend la diffusion ;
    toujours en cours, il reçoit un 503 réessayable (``Retry-After: 1``).
    """

    loop = asyncio.get_running_loop()
    deadline = loop.time() + inflight_wait
    while True:
        state, waiter = ledger.reserve(event.id)
        if state == "seen":
            return {"ok": True, "duplicate": True}
        if state == "reserved":
            break
        # Une autre livraison diffuse cet identifiant : on attend sa fin au lieu de
        # le rediffuser. Réussie, l'identifiant sera « vu » ; échouée, la réservation
        # est libérée et ce renvoi reprend la diffusion lui-même.
        remaining = deadline - loop.time()
        if waiter is None or remaining <= 0:
            raise _still_broadcasting()
        try:
            await asyncio.wait_for(waiter.wait(), remaining)
        except TimeoutError:
            raise _still_broadcasting() from None
    try:
        await manager.broadcast(event)
    except BaseException:
        ledger.release(event.id)
        raise
    ledger.confirm(event.id)
    return {"ok": True}


def _still_broadcasting() -> HTTPException:
    """503 réessayable : l'original est encore en cours de diffusion."""

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Événement en cours de diffusion par une livraison précédente : réessayer.",
        headers={"Retry-After": "1"},
    )


@app.websocket("/ws")
async def ws_endpoint(
    ws: WebSocket,
    workspace_id: str | None = None,
    project_id: str | None = None,
    department_id: str | None = None,
):
    if not _unsafe_anonymous_websocket_enabled():
        await ws.accept()
        await ws.send_json(
            {
                "type": "error",
                "code": "anonymous_websocket_disabled",
                "message": (
                    "Le flux WebSocket anonyme est désactivé. "
                    "Utilisez un canal utilisateur authentifié."
                ),
            }
        )
        await ws.close(
            code=4403,
            reason="Le flux WebSocket anonyme est désactivé.",
        )
        return

    filters = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "department_id": department_id,
    }
    await manager.connect(ws, filters)
    try:
        while True:
            await ws.receive_text()  # keep-alive ; les clients n'envoient rien d'utile
    except WebSocketDisconnect:
        await manager.disconnect(ws)
