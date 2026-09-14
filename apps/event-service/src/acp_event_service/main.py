"""Service de diffusion temps réel.

L'API pousse chaque événement sur `POST /internal/events` ; les clients web
sont connectés en WebSocket sur `/ws` avec des filtres optionnels par
workspace / projet / département.
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

app = FastAPI(title="Agent Company Platform — Event Service", version="0.8.0")

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
    await manager.broadcast(event)
    return {"ok": True}


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
