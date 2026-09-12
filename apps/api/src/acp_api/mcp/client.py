"""Client MCP Streamable HTTP minimal (spécification MCP 2025-06-18).

La découverte se limite à ``initialize`` → ``notifications/initialized`` →
``tools/list`` (paginé) → ``DELETE`` de session (au mieux). Chaque requête passe par
le ``PinnedHttpClient`` de la politique de sortie : URL validée, adresse épinglée,
redirections revalidées, corps borné. Les en-têtes résolus (secrets) sont fournis par
l'appelant et ne sont jamais journalisés ici.

Les réponses ``application/json`` (un objet) et ``text/event-stream`` (trames
``data:`` JSON) sont acceptées. Toute réponse mal formée produit une erreur explicite
(``invalid_response``), jamais un succès implicite.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

from acp_contracts import McpDiscoveredTool, McpDiscovery, McpHttpConfig

from ..outbound import PinnedHttpClient

CLIENT_NAME = "agent-company-platform"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26")
INITIALIZE_ID = 1
INPUT_SCHEMA_MAX_CHARS = 50_000
ACCEPTED_NOTIFICATION_STATUSES = frozenset({200, 202, 204})

ERROR_CODES = frozenset(
    {"transport", "protocol", "unsupported_transport", "timeout", "invalid_response"}
)


class McpClientError(RuntimeError):
    """Échec de découverte ; ``code`` est stable, le message est en français."""

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"code d'erreur client MCP inconnu : {code!r}")
        super().__init__(message)
        self.code = code


def _api_version() -> str:
    try:
        return version("acp-api")
    except PackageNotFoundError:  # pragma: no cover - installation en mode non editable
        return "0.0.0"


def _content_type(response: httpx.Response) -> str:
    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _parse_sse_messages(text: str) -> list[Any]:
    """Décode les trames ``data:`` d'un flux SSE (les commentaires ``:`` sont ignorés)."""

    messages: list[Any] = []
    data_lines: list[str] = []

    def flush() -> None:
        if not data_lines:
            return
        payload = "\n".join(data_lines)
        data_lines.clear()
        try:
            messages.append(json.loads(payload))
        except ValueError as exc:
            raise McpClientError(
                "invalid_response", "trame SSE illisible : le champ data n'est pas du JSON."
            ) from exc

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            flush()
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data_lines.append(value)
    flush()
    return messages


def parse_jsonrpc_response(response: httpx.Response, expected_id: int) -> dict[str, Any]:
    """Retourne le ``result`` de la réponse JSON-RPC ``expected_id`` (JSON ou SSE).

    Une erreur JSON-RPC lève ``protocol`` ; un corps illisible, un identifiant absent ou
    un ``result`` manquant lèvent ``invalid_response``.
    """

    content_type = _content_type(response)
    if content_type == "application/json":
        try:
            candidates = [response.json()]
        except ValueError as exc:
            raise McpClientError(
                "invalid_response", "réponse JSON illisible : le corps n'est pas du JSON."
            ) from exc
    elif content_type == "text/event-stream":
        candidates = _parse_sse_messages(response.text)
    else:
        raise McpClientError(
            "invalid_response",
            f"type de contenu inattendu « {content_type or 'absent'} » "
            "(application/json ou text/event-stream attendu).",
        )
    message = next(
        (item for item in candidates if isinstance(item, dict) and item.get("id") == expected_id),
        None,
    )
    if message is None:
        raise McpClientError(
            "invalid_response",
            f"aucune réponse JSON-RPC portant l'identifiant {expected_id} dans le corps.",
        )
    error = message.get("error")
    if error is not None:
        code = error.get("code") if isinstance(error, dict) else None
        detail = error.get("message") if isinstance(error, dict) else str(error)
        raise McpClientError("protocol", f"erreur JSON-RPC {code} : {detail}")
    result = message.get("result")
    if not isinstance(result, dict):
        raise McpClientError(
            "invalid_response", f"réponse JSON-RPC {expected_id} sans objet result."
        )
    return result


def _tool_from(raw: Any) -> McpDiscoveredTool:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"]:
        raise McpClientError(
            "invalid_response", "tools/list : un outil sans nom a été renvoyé par le serveur."
        )
    description = raw.get("description")
    schema = raw.get("inputSchema")
    if not isinstance(schema, dict):
        schema = {}
    serialized = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > INPUT_SCHEMA_MAX_CHARS:
        schema = {"truncated": True}
    return McpDiscoveredTool(
        name=raw["name"],
        description=description if isinstance(description, str) else "",
        input_schema=schema,
    )


class _McpSession:
    """Une session Streamable HTTP : en-têtes de négociation, ``Mcp-Session-Id``, envoi épinglé."""

    def __init__(
        self,
        pinned: PinnedHttpClient,
        url: str,
        base_headers: Mapping[str, str],
        protocol_version: str,
    ) -> None:
        self.pinned = pinned
        self.url = url
        self.base_headers = dict(base_headers)
        self.requested_protocol_version = protocol_version
        self.negotiated_protocol_version: str | None = None
        self.session_id: str | None = None

    def _headers(self) -> dict[str, str]:
        headers = {
            **self.base_headers,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.negotiated_protocol_version is not None:
            headers["MCP-Protocol-Version"] = self.negotiated_protocol_version
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _send_sync(
        self, method: str, headers: Mapping[str, str], content: bytes | None
    ) -> httpx.Response:
        try:
            return self.pinned.request(method, self.url, headers=headers, content=content)
        except httpx.TimeoutException as exc:
            raise McpClientError(
                "timeout", f"délai dépassé pendant l'appel MCP ({type(exc).__name__})."
            ) from exc
        except httpx.TransportError as exc:
            raise McpClientError(
                "transport", f"échec de transport pendant l'appel MCP : {exc}"
            ) from exc

    async def send(
        self, method: str, headers: Mapping[str, str], content: bytes | None = None
    ) -> httpx.Response:
        # ``PinnedHttpClient.request`` est synchrone (spécification) : appel court hors boucle.
        return await asyncio.to_thread(self._send_sync, method, headers, content)

    async def post(self, message: dict[str, Any]) -> httpx.Response:
        content = json.dumps(message, ensure_ascii=False).encode("utf-8")
        return await self.send("POST", self._headers(), content)

    async def call(self, rpc_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self.post(
            {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
        )
        if response.status_code >= 500:
            raise McpClientError(
                "transport", f"réponse HTTP {response.status_code} du serveur MCP à {method}."
            )
        if response.status_code >= 400:
            if method == "initialize" and await self._looks_like_legacy_sse():
                raise McpClientError(
                    "unsupported_transport",
                    "transport HTTP+SSE 2024-11-05 non supporté : le serveur expose un "
                    "endpoint SSE ancien ; utilisez un serveur Streamable HTTP (2025-03-26 "
                    "ou 2025-06-18).",
                )
            raise McpClientError(
                "transport", f"réponse HTTP {response.status_code} du serveur MCP à {method}."
            )
        if method == "initialize":
            session_id = response.headers.get("mcp-session-id")
            if session_id:
                self.session_id = session_id
        return parse_jsonrpc_response(response, rpc_id)

    async def notify(self, method: str) -> None:
        response = await self.post({"jsonrpc": "2.0", "method": method})
        if response.status_code not in ACCEPTED_NOTIFICATION_STATUSES:
            raise McpClientError(
                "protocol",
                f"le serveur a refusé la notification {method} "
                f"(HTTP {response.status_code} ; 202 attendu).",
            )

    async def _looks_like_legacy_sse(self) -> bool:
        """Détection au mieux de l'ancien transport (GET → flux ``event: endpoint``)."""

        headers = {**self.base_headers, "Accept": "text/event-stream"}
        try:
            response = await self.send("GET", headers)
        except Exception:  # noqa: BLE001 - détection au mieux, l'erreur d'origine prime
            return False
        return (
            response.status_code == 200
            and _content_type(response) == "text/event-stream"
            and "event: endpoint" in response.text
        )

    async def close(self) -> None:
        """Termine la session (``DELETE``) sans jamais faire échouer la découverte."""

        if not self.session_id:
            return
        try:
            await self.send("DELETE", self._headers())
        except Exception:  # noqa: BLE001 - 405 ou erreur réseau tolérés à la fermeture
            return


async def discover_http(
    config: McpHttpConfig,
    resolved_headers: Mapping[str, str],
    *,
    pinned: PinnedHttpClient,
    protocol_version: str = DEFAULT_PROTOCOL_VERSION,
    max_tools: int = 500,
    max_pages: int = 10,
) -> McpDiscovery:
    """Découvre les outils d'un serveur Streamable HTTP ; lève ``McpClientError`` ou ``OutboundPolicyError``."""

    if max_tools < 1 or max_pages < 1:
        raise ValueError("max_tools et max_pages doivent être strictement positifs")
    session = _McpSession(
        pinned,
        config.url,
        {**config.headers, **resolved_headers},
        protocol_version,
    )
    init_result = await session.call(
        INITIALIZE_ID,
        "initialize",
        {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": _api_version()},
        },
    )
    negotiated = init_result.get("protocolVersion")
    if negotiated not in SUPPORTED_PROTOCOL_VERSIONS:
        raise McpClientError(
            "protocol",
            f"version de protocole MCP « {negotiated} » non supportée "
            f"(acceptées : {', '.join(SUPPORTED_PROTOCOL_VERSIONS)}).",
        )
    session.negotiated_protocol_version = negotiated
    await session.notify("notifications/initialized")

    tools: list[McpDiscoveredTool] = []
    truncated = False
    cursor: str | None = None
    rpc_id = INITIALIZE_ID + 1
    for _page in range(max_pages):
        params: dict[str, Any] = {"cursor": cursor} if cursor else {}
        result = await session.call(rpc_id, "tools/list", params)
        rpc_id += 1
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            raise McpClientError("invalid_response", "tools/list : liste d'outils absente.")
        for raw in raw_tools:
            if len(tools) >= max_tools:
                truncated = True
                break
            tools.append(_tool_from(raw))
        next_cursor = result.get("nextCursor")
        if truncated or not next_cursor:
            break
        cursor = str(next_cursor)
    else:
        truncated = True
    await session.close()
    return McpDiscovery(
        protocol_version=negotiated,
        server_info=init_result.get("serverInfo") if isinstance(init_result.get("serverInfo"), dict) else {},
        tools=tools,
        capabilities=init_result.get("capabilities") if isinstance(init_result.get("capabilities"), dict) else {},
        truncated=truncated,
    )
