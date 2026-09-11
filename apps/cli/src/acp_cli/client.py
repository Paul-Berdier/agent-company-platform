"""Transport HTTP strict du CLI ACP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from . import __version__
from .config import Settings


SESSION_COOKIE_NAME = "acp_session"
USER_AGENT = f"acp-cli/{__version__}"


class ClientError(RuntimeError):
    """Erreur sûre à présenter à l'utilisateur."""


@dataclass(frozen=True)
class APIError(ClientError):
    status_code: int
    detail: str

    def __str__(self) -> str:
        return f"API {self.status_code}: {self.detail}"


class NetworkError(ClientError):
    pass


class ProtocolError(ClientError):
    pass


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return "réponse d'erreur non JSON"
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail[:500]
        if isinstance(detail, list):
            # Les erreurs de validation FastAPI ne contiennent pas de secrets si
            # l'on ne reproduit pas le champ ``input``.
            messages = [
                item.get("msg", "validation invalide")
                for item in detail
                if isinstance(item, dict)
            ]
            if messages:
                return "; ".join(str(message) for message in messages)[:500]
    return "requête refusée"


class ACPClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.timeout = timeout

    def request_response(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Mapping[str, Any] | None = None,
        authenticated: bool = True,
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        cookies: dict[str, str] = {}
        session_allowed = authenticated and self.settings.authenticated
        if session_allowed and self.settings.session_cookie:
            cookies[SESSION_COOKIE_NAME] = self.settings.session_cookie
        if (
            session_allowed
            and method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            and self.settings.csrf_token
        ):
            headers["X-CSRF-Token"] = self.settings.csrf_token
        if idempotency_key is not None:
            if (
                not idempotency_key
                or len(idempotency_key) > 200
                or any(
                    ord(character) < 33 or ord(character) > 126
                    for character in idempotency_key
                )
            ):
                raise ProtocolError("clé d'idempotence invalide")
            headers["Idempotency-Key"] = idempotency_key
        try:
            with httpx.Client(
                base_url=f"{self.settings.api_url}/",
                headers=headers,
                cookies=cookies,
                timeout=self.timeout,
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.request(
                    method,
                    path.lstrip("/"),
                    json=json_body,
                    params=params,
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise NetworkError("API ACP injoignable") from exc
        except httpx.HTTPError as exc:
            raise NetworkError("échec du transport HTTP") from exc
        if response.is_redirect:
            raise ProtocolError("redirection HTTP inattendue")
        if response.status_code >= 400:
            raise APIError(response.status_code, _error_detail(response))
        return response

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Mapping[str, Any] | None = None,
        authenticated: bool = True,
        idempotency_key: str | None = None,
    ) -> Any:
        response = self.request_response(
            method,
            path,
            json_body=json_body,
            params=params,
            authenticated=authenticated,
            idempotency_key=idempotency_key,
        )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ProtocolError("l'API a retourné une réponse non JSON") from exc
