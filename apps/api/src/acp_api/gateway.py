"""Client interne strict de l'API vers le provider-gateway."""

import os
from typing import Any, Literal

import httpx
from acp_contracts import (
    HermesNativeListing,
    ServiceOriginError,
    normalize_service_origin,
)
from pydantic import BaseModel, ConfigDict, ValidationError


class GatewayUnavailableError(RuntimeError):
    """Le gateway n'a pas fourni une réponse exploitable."""


class GatewayDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["hermes"]
    status: Literal[
        "not_configured",
        "ready",
        "unauthorized",
        "timeout",
        "incompatible_version",
        "invalid_response",
        "unavailable",
    ]
    configured: bool
    ready: bool
    expected_version: str
    detected_version: str | None = None
    model: str | None = None
    latency_ms: float | None = None
    detail: str


class GatewayRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    status: Literal[
        "started",
        "queued",
        "running",
        "waiting_for_approval",
        "stopping",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ]
    replayed: bool = False
    session_id: str | None = None
    model: str | None = None
    output: str | None = None
    error: str | None = None
    usage: dict[str, Any] | None = None


class GatewayClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_token: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        raw_base_url = (
            base_url
            if base_url is not None
            else os.environ.get("ACP_PROVIDER_GATEWAY_URL", "http://localhost:8002")
        )
        try:
            self.base_url: str | None = normalize_service_origin(
                raw_base_url, setting="ACP_PROVIDER_GATEWAY_URL",
                internal_http_hosts=os.environ.get("ACP_INTERNAL_HTTP_HOSTS", ""),
            )
        except ServiceOriginError:
            self.base_url = None
        self.service_token = (
            service_token
            if service_token is not None
            else os.environ.get("ACP_GATEWAY_SERVICE_TOKEN", "")
        )
        raw_timeout = os.environ.get("ACP_GATEWAY_TIMEOUT_SECONDS", "10")
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else float(raw_timeout)
        )
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        if self.base_url is None:
            raise GatewayUnavailableError(
                "L'origine du provider-gateway est invalide ou non sécurisée"
            )
        if not self.service_token.strip():
            raise GatewayUnavailableError(
                "Le jeton de service du provider-gateway n'est pas configuré"
            )
        return {"Authorization": f"Bearer {self.service_token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        request_headers = self._headers()
        assert self.base_url is not None
        request_headers.update(kwargs.pop("headers", {}))
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    headers=request_headers,
                    **kwargs,
                )
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GatewayUnavailableError(
                "Le provider-gateway ne répond pas avec un contrat valide"
            ) from exc

    async def diagnose_hermes(self) -> GatewayDiagnostic:
        data = await self._request("GET", "/v1/providers/hermes/diagnostic")
        try:
            return GatewayDiagnostic.model_validate(data)
        except ValidationError as exc:
            raise GatewayUnavailableError(
                "Le diagnostic Hermes ne respecte pas le contrat attendu"
            ) from exc

    async def hermes_native_listing(self) -> HermesNativeListing:
        """Lit, via le gateway, les skills et toolsets annoncés par Hermes.

        Lecture seule : l'API ne réécrit jamais la configuration native
        d'Hermes, qui reste la source de vérité de ses skills et toolsets.
        """

        data = await self._request("GET", "/v1/providers/hermes/native-listing")
        try:
            return HermesNativeListing.model_validate(data)
        except ValidationError as exc:
            raise GatewayUnavailableError(
                "La lecture des skills et toolsets natifs ne respecte pas le "
                "contrat attendu"
            ) from exc

    async def submit_hermes_run(
        self,
        *,
        prompt: str,
        session_id: str,
        idempotency_key: str,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GatewayRun:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "session_id": session_id,
            "metadata": metadata or {},
        }
        if model is not None:
            payload["model"] = model
        data = await self._request(
            "POST",
            "/v1/providers/hermes/runs",
            json=payload,
            headers={
                **self._headers(),
                "Idempotency-Key": idempotency_key,
            },
        )
        try:
            return GatewayRun.model_validate(data)
        except ValidationError as exc:
            raise GatewayUnavailableError(
                "L'admission du run Hermes ne respecte pas le contrat attendu"
            ) from exc

    async def get_hermes_run(self, run_id: str) -> GatewayRun:
        data = await self._request("GET", f"/v1/providers/hermes/runs/{run_id}")
        try:
            return GatewayRun.model_validate(data)
        except ValidationError as exc:
            raise GatewayUnavailableError(
                "Le statut du run Hermes ne respecte pas le contrat attendu"
            ) from exc


def get_gateway_client() -> GatewayClient:
    return GatewayClient()
