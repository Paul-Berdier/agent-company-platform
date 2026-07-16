import os

import httpx

from acp_contracts import Event


class EventClient:
    """Émet des événements métier vers l'API (qui journalise et diffuse).

    Résilient : une panne du bus d'événements ne doit jamais faire échouer
    l'opération métier qui l'émet.
    """

    def __init__(self, api_url: str | None = None) -> None:
        self._api_url = (api_url or os.environ.get("ACP_API_URL", "http://localhost:8000")).rstrip("/")

    async def emit(self, event: Event) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self._api_url}/events", json=event.model_dump(mode="json")
                )
                return resp.status_code < 400
        except httpx.HTTPError:
            return False

    async def emit_type(self, event_type: str, **fields) -> bool:
        payload = fields.pop("payload", {})
        return await self.emit(Event(type=event_type, payload=payload, **fields))
