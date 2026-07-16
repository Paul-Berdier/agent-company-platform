"""Client HTTP Hermes : configuration par variables d'environnement, retries.

Migrer Hermes (Railway, serveur personnel...) = changer HERMES_BASE_URL.
"""

import asyncio
import os
from dataclasses import dataclass, field

import httpx

from acp_provider_sdk import ProviderUnavailableError


@dataclass
class HermesSettings:
    base_url: str = field(default_factory=lambda: os.environ.get("HERMES_BASE_URL", ""))
    service_token: str = field(default_factory=lambda: os.environ.get("HERMES_SERVICE_TOKEN", ""))
    timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("HERMES_TIMEOUT_SECONDS", "30"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get("HERMES_MAX_RETRIES", "2"))
    )

    @property
    def configured(self) -> bool:
        return bool(self.base_url)


class HermesClient:
    def __init__(
        self,
        settings: HermesSettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or HermesSettings()
        self._transport = transport  # injectable pour les tests d'intégration simulés

    def _client(self) -> httpx.AsyncClient:
        headers = {}
        if self.settings.service_token:
            headers["Authorization"] = f"Bearer {self.settings.service_token}"
        return httpx.AsyncClient(
            base_url=self.settings.base_url.rstrip("/"),
            headers=headers,
            timeout=self.settings.timeout_seconds,
            transport=self._transport,
        )

    async def get_json(self, path: str) -> dict:
        return await self._request("GET", path)

    async def post_json(self, path: str, payload: dict) -> dict:
        return await self._request("POST", path, payload)

    async def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not self.settings.configured:
            raise ProviderUnavailableError("HERMES_BASE_URL non configurée")
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                async with self._client() as client:
                    resp = await client.request(method, path, json=payload)
                    if resp.status_code >= 500:
                        raise ProviderUnavailableError(f"Hermes {resp.status_code} sur {path}")
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.HTTPError, ProviderUnavailableError) as exc:
                last_error = exc
                if attempt < self.settings.max_retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
        raise ProviderUnavailableError(f"Hermes injoignable ({path}): {last_error}")
