"""Client HTTP minimal pour l'API officielle Hermes Agent."""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from acp_contracts import ServiceOriginError, normalize_service_origin
from acp_provider_sdk import ProviderUnavailableError


class HermesHTTPError(ProviderUnavailableError):
    """Refus HTTP Hermes sans recopier un corps potentiellement sensible."""

    def __init__(self, method: str, path: str, status_code: int) -> None:
        self.method = method
        self.path = path
        self.status_code = status_code
        super().__init__(f"Hermes a refusé {method} {path} (HTTP {status_code})")


class HermesTimeoutError(ProviderUnavailableError):
    """Délai réseau épuisé après les tentatives configurées."""


class HermesTransportError(ProviderUnavailableError):
    """Échec de transport non HTTP après les tentatives configurées."""


class HermesInvalidResponseError(ProviderUnavailableError):
    """Réponse HTTP réussie mais non conforme au format JSON minimal."""


@dataclass(repr=False)
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
    _base_url_invalid: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            self.base_url = ""
            return
        try:
            self.base_url = normalize_service_origin(
                self.base_url, setting="HERMES_BASE_URL"
            )
        except ServiceOriginError:
            self.base_url = ""
            self._base_url_invalid = True

    @property
    def configured(self) -> bool:
        # L'API Server Hermes exige son API_SERVER_KEY même sur loopback. Le
        # gateway stocke la valeur cliente dans HERMES_API_KEY (avec
        # HERMES_SERVICE_TOKEN conservé comme alias de migration).
        return bool(self.base_url.strip() and self.service_token.strip())

    @property
    def base_url_invalid(self) -> bool:
        return self._base_url_invalid


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
            trust_env=False,
        )

    async def get_json(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def get_collection(self, path: str, *, key: str) -> list[Any]:
        """Lit une liste native Hermes sans rien y écrire.

        Les routes de consultation d'Hermes 0.21.1 renvoient soit un tableau
        JSON nu, soit un objet enveloppant ce tableau sous sa clé (`skills`,
        `toolsets`). Toute autre forme est une réponse invalide : elle est
        refusée plutôt que réinterprétée.
        """

        data, _ = await self._request_any("GET", path)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get(key), list):
            return data[key]
        raise HermesInvalidResponseError(f"Réponse Hermes non listable sur {path}")

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
        data, response_headers = await self._request_any(
            method, path, payload, headers=headers
        )
        if not isinstance(data, dict):
            raise HermesInvalidResponseError(f"Réponse Hermes non objet sur {path}")
        if method == "POST" and path == "/v1/runs":
            replayed_header = response_headers.get("Idempotency-Replayed")
            if replayed_header is not None:
                normalized = replayed_header.strip().lower()
                if normalized not in {"true", "false"}:
                    raise HermesInvalidResponseError(
                        "En-tête Idempotency-Replayed Hermes invalide"
                    )
                data = {**data, "replayed": normalized == "true"}
        return data

    async def _request_any(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, httpx.Headers]:
        """Exécute la requête et rend le JSON brut avec les en-têtes réponse."""

        if not self.settings.base_url.strip():
            detail = "invalide" if self.settings.base_url_invalid else "non configurée"
            raise ProviderUnavailableError(f"HERMES_BASE_URL {detail}")
        if not self.settings.service_token.strip():
            raise ProviderUnavailableError(
                "HERMES_API_KEY non configurée (HERMES_SERVICE_TOKEN accepté en migration)"
            )

        last_error = "erreur inconnue"
        error_type: type[ProviderUnavailableError] = HermesTransportError
        for attempt in range(max(0, self.settings.max_retries) + 1):
            try:
                async with self._client() as client:
                    response = await client.request(method, path, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                error_type = HermesTimeoutError
                last_error = type(exc).__name__
            except httpx.RequestError as exc:
                error_type = HermesTransportError
                last_error = type(exc).__name__
            else:
                if 200 <= response.status_code < 300:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise HermesInvalidResponseError(
                            f"Réponse JSON Hermes invalide sur {path}"
                        ) from exc
                    return data, response.headers

                # Les 3xx/4xx sont laissées au contrôle de l'appelant. En
                # particulier, aucun redirect susceptible d'exposer le Bearer
                # et aucun retry 429 implicite n'est suivi ici.
                if response.status_code < 500:
                    raise HermesHTTPError(method, path, response.status_code)
                error_type = HermesTransportError
                last_error = f"HTTP {response.status_code}"

            if attempt < max(0, self.settings.max_retries):
                await asyncio.sleep(0.2 * (attempt + 1))

        raise error_type(f"Hermes injoignable ({method} {path}): {last_error}")
