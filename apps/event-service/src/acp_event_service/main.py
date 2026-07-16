"""Service de diffusion temps réel.

L'API pousse chaque événement sur `POST /internal/events` ; les clients web
sont connectés en WebSocket sur `/ws` avec des filtres optionnels par
workspace / projet / département.
"""

import asyncio
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from acp_contracts import Event

app = FastAPI(title="Agent Company Platform — Event Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ACP_CORS_ORIGINS", "*").split(","),
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


@app.get("/health")
def health():
    return {"status": "ok", "service": "event-service"}


@app.post("/internal/events")
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
