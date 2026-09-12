"""Client MCP Streamable HTTP : découverte JSON et SSE, session, pagination, erreurs.

Aucun réseau réel : ``httpx.MockTransport`` simule le serveur MCP et un résolveur DNS
déterministe alimente le ``PinnedHttpClient`` de la fondation.
"""

import json
import socket

import httpx
import pytest

from acp_api.mcp.client import (
    SUPPORTED_PROTOCOL_VERSIONS,
    McpClientError,
    discover_http,
    parse_jsonrpc_response,
)
from acp_api.outbound import OutboundPolicy, OutboundPolicyError, PinnedHttpClient
from acp_contracts import McpHttpConfig

PUBLIC_IP = "93.184.216.34"
SERVER_URL = "https://mcp.example/mcp"


def fake_resolver(table: dict[str, list[str]]):
    def resolve(host, port=None, *args, **kwargs):
        if host not in table:
            raise socket.gaierror(-2, "Name or service not known")
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (address, port or 0),
            )
            for address in table[host]
        ]

    return resolve


def _sse(*messages: dict) -> str:
    return "".join(f"event: message\ndata: {json.dumps(message)}\n\n" for message in messages)


class FakeMcpServer:
    """Serveur MCP Streamable HTTP simulé, paramétrable par scénario."""

    def __init__(
        self,
        *,
        mode: str = "json",
        protocol_version: str = "2025-06-18",
        tools: list[dict] | None = None,
        page_size: int | None = None,
        session_id: str | None = "session-abc",
        initialized_status: int = 202,
        delete_status: int = 200,
        tools_error: dict | None = None,
    ) -> None:
        self.mode = mode
        self.protocol_version = protocol_version
        self.tools = tools if tools is not None else [
            {"name": "search", "description": "Recherche", "inputSchema": {"type": "object"}},
            {"name": "fetch", "description": "Lecture", "inputSchema": {"type": "object"}},
        ]
        self.page_size = page_size
        self.session_id = session_id
        self.initialized_status = initialized_status
        self.delete_status = delete_status
        self.tools_error = tools_error
        self.requests: list[httpx.Request] = []

    def _reply(self, request: httpx.Request, message: dict, *, prefix: list[dict] = ()) -> httpx.Response:
        headers = {}
        if self.session_id and json.loads(request.content).get("method") == "initialize":
            headers["Mcp-Session-Id"] = self.session_id
        if self.mode == "sse":
            headers["Content-Type"] = "text/event-stream"
            return httpx.Response(200, headers=headers, text=_sse(*prefix, message))
        headers["Content-Type"] = "application/json"
        return httpx.Response(200, headers=headers, content=json.dumps(message).encode())

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(self.delete_status)
        if request.method != "POST":
            return httpx.Response(405)
        body = json.loads(request.content)
        method = body.get("method")
        if method == "initialize":
            return self._reply(
                request,
                {
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": self.protocol_version,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "fake-mcp", "version": "1.2.3"},
                    },
                },
                prefix=[{"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info"}}],
            )
        if method == "notifications/initialized":
            assert "id" not in body
            return httpx.Response(self.initialized_status)
        if method == "tools/list":
            if self.session_id:
                assert request.headers.get("mcp-session-id") == self.session_id
            if self.tools_error is not None:
                return self._reply(
                    request, {"jsonrpc": "2.0", "id": body["id"], "error": self.tools_error}
                )
            cursor = int((body.get("params") or {}).get("cursor") or 0)
            if self.page_size is None:
                page, next_cursor = self.tools, None
            else:
                page = self.tools[cursor : cursor + self.page_size]
                next_cursor = cursor + self.page_size
                if next_cursor >= len(self.tools):
                    next_cursor = None
            result = {"tools": page}
            if next_cursor is not None:
                result["nextCursor"] = str(next_cursor)
            return self._reply(request, {"jsonrpc": "2.0", "id": body["id"], "result": result})
        return httpx.Response(400, json={"detail": f"méthode inconnue {method}"})


def _pinned(handler, *, timeout: float = 5.0) -> PinnedHttpClient:
    return PinnedHttpClient(
        OutboundPolicy(),
        fake_resolver({"mcp.example": [PUBLIC_IP]}),
        transport=httpx.MockTransport(handler),
        timeout=timeout,
    )


def _config(**overrides) -> McpHttpConfig:
    values = {"url": SERVER_URL, "headers": {"X-Client": "acp"}, "timeout_seconds": 5}
    values.update(overrides)
    return McpHttpConfig(**values)


# --- parcours nominal ----------------------------------------------------------------


@pytest.mark.parametrize("mode", ["json", "sse"])
async def test_discovery_over_json_and_sse(mode):
    server = FakeMcpServer(mode=mode)
    discovery = await discover_http(
        _config(),
        {"Authorization": "Bearer resolved-token"},
        pinned=_pinned(server.handle),
    )

    assert discovery.protocol_version == "2025-06-18"
    assert discovery.server_info == {"name": "fake-mcp", "version": "1.2.3"}
    assert discovery.capabilities == {"tools": {"listChanged": False}}
    assert [tool.name for tool in discovery.tools] == ["search", "fetch"]
    assert discovery.tools[0].description == "Recherche"
    assert discovery.tools[0].input_schema == {"type": "object"}
    assert discovery.truncated is False

    methods = [
        json.loads(request.content).get("method") if request.method == "POST" else request.method
        for request in server.requests
    ]
    assert methods == ["initialize", "notifications/initialized", "tools/list", "DELETE"]

    initialize = server.requests[0]
    assert initialize.url.host == PUBLIC_IP
    assert initialize.headers["host"] == "mcp.example"
    assert initialize.extensions["sni_hostname"] == "mcp.example"
    assert initialize.headers["accept"] == "application/json, text/event-stream"
    assert initialize.headers["content-type"] == "application/json"
    assert initialize.headers["authorization"] == "Bearer resolved-token"
    assert initialize.headers["x-client"] == "acp"
    body = json.loads(initialize.content)
    assert body["jsonrpc"] == "2.0" and body["id"] == 1
    assert body["params"]["protocolVersion"] == "2025-06-18"
    assert body["params"]["capabilities"] == {}
    assert body["params"]["clientInfo"]["name"] == "agent-company-platform"
    assert body["params"]["clientInfo"]["version"]

    for later in server.requests[1:]:
        assert later.headers["mcp-session-id"] == "session-abc"
        assert later.headers["mcp-protocol-version"] == "2025-06-18"
        assert later.headers["authorization"] == "Bearer resolved-token"
    assert server.requests[-1].method == "DELETE"


async def test_older_supported_protocol_version_is_negotiated():
    server = FakeMcpServer(protocol_version="2025-03-26")
    discovery = await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert discovery.protocol_version == "2025-03-26"
    assert server.requests[2].headers["mcp-protocol-version"] == "2025-03-26"
    assert "2025-03-26" in SUPPORTED_PROTOCOL_VERSIONS


async def test_server_without_session_id_is_accepted():
    server = FakeMcpServer(session_id=None)
    discovery = await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert [tool.name for tool in discovery.tools] == ["search", "fetch"]
    assert "mcp-session-id" not in server.requests[2].headers
    # Sans session, aucune fermeture DELETE n'est nécessaire.
    assert [request.method for request in server.requests] == ["POST", "POST", "POST"]


async def test_delete_failure_does_not_fail_discovery():
    server = FakeMcpServer(delete_status=405)
    discovery = await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert len(discovery.tools) == 2


# --- pagination et bornes -----------------------------------------------------------------


def _many_tools(count: int) -> list[dict]:
    return [{"name": f"tool-{index}", "description": "", "inputSchema": {}} for index in range(count)]


async def test_pagination_follows_next_cursor():
    server = FakeMcpServer(tools=_many_tools(5), page_size=2)
    discovery = await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert [tool.name for tool in discovery.tools] == [f"tool-{index}" for index in range(5)]
    assert discovery.truncated is False
    list_calls = [
        json.loads(request.content)
        for request in server.requests
        if request.method == "POST" and json.loads(request.content).get("method") == "tools/list"
    ]
    assert [call.get("params", {}).get("cursor") for call in list_calls] == [None, "2", "4"]
    assert [call["id"] for call in list_calls] == [2, 3, 4]


async def test_max_pages_and_max_tools_mark_truncation():
    server = FakeMcpServer(tools=_many_tools(5), page_size=2)
    limited_pages = await discover_http(
        _config(), {}, pinned=_pinned(server.handle), max_pages=1
    )
    assert [tool.name for tool in limited_pages.tools] == ["tool-0", "tool-1"]
    assert limited_pages.truncated is True

    server = FakeMcpServer(tools=_many_tools(5), page_size=2)
    limited_tools = await discover_http(
        _config(), {}, pinned=_pinned(server.handle), max_tools=3
    )
    assert [tool.name for tool in limited_tools.tools] == ["tool-0", "tool-1", "tool-2"]
    assert limited_tools.truncated is True


async def test_tool_description_and_schema_are_bounded():
    huge_schema = {"type": "object", "properties": {f"p{i}": {"type": "string"} for i in range(4000)}}
    server = FakeMcpServer(
        tools=[
            {"name": "verbose", "description": "x" * 5000, "inputSchema": huge_schema},
            {"name": "bare"},
        ]
    )
    discovery = await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert len(discovery.tools[0].description) == 2000
    assert discovery.tools[0].input_schema == {"truncated": True}
    assert discovery.tools[1].description == "" and discovery.tools[1].input_schema == {}


async def test_tool_without_name_is_an_invalid_response():
    server = FakeMcpServer(tools=[{"description": "sans nom"}])
    with pytest.raises(McpClientError) as excinfo:
        await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert excinfo.value.code == "invalid_response"


# --- refus et erreurs -----------------------------------------------------------------------


async def test_unknown_protocol_version_is_refused():
    server = FakeMcpServer(protocol_version="2099-01-01")
    with pytest.raises(McpClientError) as excinfo:
        await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert excinfo.value.code == "protocol"
    assert "2099-01-01" in str(excinfo.value)
    # Rien n'est envoyé après le refus.
    assert len(server.requests) == 1


async def test_legacy_http_sse_transport_is_unsupported():
    seen: list[httpx.Request] = []

    def legacy(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and "text/event-stream" in request.headers.get("accept", ""):
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text="event: endpoint\ndata: /messages?sessionId=42\n\n",
            )
        return httpx.Response(405, text="Method Not Allowed")

    with pytest.raises(McpClientError) as excinfo:
        await discover_http(_config(url="https://mcp.example/sse"), {}, pinned=_pinned(legacy))
    assert excinfo.value.code == "unsupported_transport"
    assert "2024-11-05" in str(excinfo.value)
    assert [request.method for request in seen] == ["POST", "GET"]


async def test_plain_4xx_without_legacy_endpoint_is_a_transport_error():
    def denied(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(McpClientError) as excinfo:
        await discover_http(_config(), {}, pinned=_pinned(denied))
    assert excinfo.value.code == "transport"
    assert "401" in str(excinfo.value)


async def test_jsonrpc_error_fails_discovery():
    server = FakeMcpServer(tools_error={"code": -32601, "message": "Method not found"})
    with pytest.raises(McpClientError) as excinfo:
        await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert excinfo.value.code == "protocol"
    assert "Method not found" in str(excinfo.value)


async def test_rejected_initialized_notification_is_a_protocol_error():
    server = FakeMcpServer(initialized_status=400)
    with pytest.raises(McpClientError) as excinfo:
        await discover_http(_config(), {}, pinned=_pinned(server.handle))
    assert excinfo.value.code == "protocol"


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx.ReadTimeout("lent"), "timeout"),
        (httpx.ConnectTimeout("lent"), "timeout"),
        (httpx.ConnectError("refusé"), "transport"),
        (httpx.RemoteProtocolError("coupé"), "transport"),
    ],
)
async def test_httpx_transport_exceptions_are_mapped(exception, code):
    def failing(request: httpx.Request) -> httpx.Response:
        raise exception

    with pytest.raises(McpClientError) as excinfo:
        await discover_http(_config(), {}, pinned=_pinned(failing))
    assert excinfo.value.code == code


async def test_non_json_body_is_an_invalid_response():
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<html>")

    with pytest.raises(McpClientError) as excinfo:
        await discover_http(_config(), {}, pinned=_pinned(html))
    assert excinfo.value.code == "invalid_response"


async def test_outbound_policy_errors_propagate_unchanged():
    server = FakeMcpServer()
    pinned = PinnedHttpClient(
        OutboundPolicy(),
        fake_resolver({"mcp.example": ["10.0.0.5"]}),
        transport=httpx.MockTransport(server.handle),
    )
    with pytest.raises(OutboundPolicyError) as excinfo:
        await discover_http(_config(), {}, pinned=pinned)
    assert excinfo.value.code == "host_blocked"
    assert server.requests == []


def test_invalid_client_error_code_is_rejected():
    with pytest.raises(ValueError):
        McpClientError("nope", "message")


# --- parse_jsonrpc_response ---------------------------------------------------------------


def test_parse_json_response_returns_result():
    response = httpx.Response(
        200,
        headers={"Content-Type": "application/json; charset=utf-8"},
        json={"jsonrpc": "2.0", "id": 7, "result": {"ok": True}},
    )
    assert parse_jsonrpc_response(response, 7) == {"ok": True}


def test_parse_sse_response_picks_the_matching_id_and_ignores_comments():
    stream = (
        ": keep-alive\n\n"
        'data: {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}\n\n'
        "event: message\n"
        'data: {"jsonrpc": "2.0", "id": 3, "result": {"tools": []}}\n\n'
    )
    response = httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=stream)
    assert parse_jsonrpc_response(response, 3) == {"tools": []}


def test_parse_rejects_mismatched_id_missing_result_and_bad_json():
    mismatched = httpx.Response(
        200, headers={"Content-Type": "application/json"}, json={"jsonrpc": "2.0", "id": 2, "result": {}}
    )
    with pytest.raises(McpClientError) as excinfo:
        parse_jsonrpc_response(mismatched, 1)
    assert excinfo.value.code == "invalid_response"

    no_result = httpx.Response(
        200, headers={"Content-Type": "application/json"}, json={"jsonrpc": "2.0", "id": 1}
    )
    with pytest.raises(McpClientError) as excinfo:
        parse_jsonrpc_response(no_result, 1)
    assert excinfo.value.code == "invalid_response"

    broken = httpx.Response(200, headers={"Content-Type": "application/json"}, text="{not json")
    with pytest.raises(McpClientError) as excinfo:
        parse_jsonrpc_response(broken, 1)
    assert excinfo.value.code == "invalid_response"

    broken_sse = httpx.Response(
        200, headers={"Content-Type": "text/event-stream"}, text="data: {oops\n\n"
    )
    with pytest.raises(McpClientError) as excinfo:
        parse_jsonrpc_response(broken_sse, 1)
    assert excinfo.value.code == "invalid_response"

    error = httpx.Response(
        200,
        headers={"Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "Invalid Request"}},
    )
    with pytest.raises(McpClientError) as excinfo:
        parse_jsonrpc_response(error, 1)
    assert excinfo.value.code == "protocol"
    assert "-32600" in str(excinfo.value) and "Invalid Request" in str(excinfo.value)
