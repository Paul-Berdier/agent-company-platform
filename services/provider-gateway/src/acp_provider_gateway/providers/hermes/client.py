"""Client HTTP minimal pour l'API officielle Hermes Agent."""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from acp_provider_sdk import ProviderUnavailableError


@dataclass
class HermesSettings:
    base_url: str = field(default_factory=lambda: os.environ.get("HERMES_BASE_URL", ""))
    service_token: str = field(
        default_factory=lambda: (
            os.environ.get("HERMES_API_KEY")
            or os.environ.get("HERMES_SERVICE_TOKEN", "")
        )
    )
    timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("HERMES_TIMEOUT_SECONDS", "30"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get("HERMES_MAX_RETRIES", "2"))
    )
    run_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("HERMES_RUN_TIMEOUT_SECONDS", "120"))
    )
    poll_interval_seconds: float = field(
        default_factory=lambda: float(os.environ.get("HERMES_POLL_INTERVAL_SECONDS", "0.5"))
    )

    @property
    def configured(self) -> bool:
        # L'API Server Hermes exige son API_SERVER_KEY même sur loopback. Le
        # gateway stocke la valeur cliente dans HERMES_API_KEY (avec
        # HERMES_SERVICE_TOKEN conservé comme alias de migration).
        return bool(self.base_url.strip() and self.service_token.strip())


class HermesClient:
    def __init__(
        self,
        settings: HermesSettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or HermesSettings()
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.settings.service_token}"},
            timeout=self.settings.timeout_seconds,
            transport=self._transport,
        )

    async def get_json(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return await self._request("POST", path, payload, headers=headers)

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.base_url.strip():
            raise ProviderUnavailableError("HERMES_BASE_URL non configurée")
        if not self.settings.service_token.strip():
            raise ProviderUnavailableError(
                "HERMES_API_KEY non configurée (HERMES_SERVICE_TOKEN accepté en migration)"
            )

        last_error = "erreur inconnue"
        for attempt in range(max(0, self.settings.max_retries) + 1):
            try:
                async with self._client() as client:
                    response = await client.request(method, path, json=payload, headers=headers)
            except httpx.RequestError as exc:
                last_error = type(exc).__name__
            else:
                if 200 <= response.status_code < 300:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise ProviderUnavailableError(
                            f"Réponse JSON Hermes invalide sur {path}"
                        ) from exc
                    if not isinstance(data, dict):
                        raise ProviderUnavailableError(
                            f"Réponse Hermes non objet sur {path}"
                        )
                    return data

                # Les 3xx/4xx sont laissées au contrôle de l'appelant. En
                # particulier, aucun redirect susceptible d'exposer le Bearer
                # et aucun retry 429 implicite n'est suivi ici.
                if response.status_code < 500:
                    raise ProviderUnavailableError(
                        f"Hermes a refusé {method} {path} (HTTP {response.status_code})"
                    )
                last_error = f"HTTP {response.status_code}"

            if attempt < max(0, self.settings.max_retries):
                await asyncio.sleep(0.2 * (attempt + 1))

        raise ProviderUnavailableError(
            f"Hermes injoignable ({method} {path}): {last_error}"
        )
