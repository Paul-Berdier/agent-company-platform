import os

import httpx

from acp_contracts import Event


class EventClient:
    """Émet des événements worker vers l'API (qui journalise et diffuse).

    L'identité doit être fournie explicitement. Le SDK retourne ``False`` sans
    effectuer de requête lorsque les deux éléments d'authentification manquent ;
    il n'invente jamais qu'un événement a été accepté.
    """

    def __init__(
        self,
        api_url: str | None = None,
        *,
        worker_id: str | None = None,
        worker_token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = (api_url or os.environ.get("ACP_API_URL", "http://localhost:8000")).rstrip("/")
        self._worker_id = worker_id
        self._worker_token = worker_token
        self._transport = transport

    async def emit(self, event: Event) -> bool:
        if not self._worker_id or not self._worker_token:
            return False
        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                transport=self._transport,
                headers={
                    "Authorization": f"Bearer {self._worker_token}",
                    "X-Worker-Id": self._worker_id,
                },
            ) as client:
                resp = await client.post(
                    f"{self._api_url}/events", json=event.model_dump(mode="json")
                )
                return 200 <= resp.status_code < 300
        except httpx.HTTPError:
            return False

    async def emit_type(self, event_type: str, **fields) -> bool:
        payload = fields.pop("payload", {})
        return await self.emit(Event(type=event_type, payload=payload, **fields))
