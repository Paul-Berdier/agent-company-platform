"""Surface Streamable HTTP locale au proxy, sans secret MCP amont côté CLI."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from acp_contracts.limits import DatabaseModel

from ..deps import get_db
from ..mcp import execution
from ..mcp.client import DEFAULT_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS
from .mcp import _policy, get_dns_resolver, get_http_transport

router = APIRouter(tags=["mcp-execution"])
_PRIVATE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class GrantRequest(DatabaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    ttl_seconds: int = Field(default=900, ge=30, le=3600, strict=True)


@router.post("/work/workers/{worker_id}/runs/{run_id}/mcp/grants")
def create_grants(
    worker_id: str, run_id: str, body: GrantRequest,
    db: Session = Depends(get_db), authorization: str | None = Header(default=None),
    fencing_token: Annotated[int | None, Header(alias="X-Attempt-Fencing-Token", gt=0, le=2**31 - 1)] = None,
):
    result = execution.issue_grants(
        db, worker_id=worker_id, run_id=run_id, authorization=authorization,
        fence=fencing_token, step_id=body.step_id, ttl_seconds=body.ttl_seconds,
    )
    return JSONResponse(result, headers=_PRIVATE)


def _pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Clé JSON dupliquée")
        result[key] = value
    return result


def _refuse_constant(_value):
    raise ValueError("Nombre JSON non fini")


async def _read_rpc(request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > execution.MAX_BODY_BYTES:
            raise HTTPException(413, "Requête MCP trop volumineuse.")
    try:
        message = json.loads(data, object_pairs_hook=_pairs_unique, parse_constant=_refuse_constant)
        execution.canonical(message)
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(400, "Requête MCP JSON invalide.") from None
    if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
            or set(message) - {"jsonrpc", "id", "method", "params"}
            or not isinstance(message.get("method"), str)
            or not isinstance(message.get("params", {}), dict)):
        raise HTTPException(400, "Objet JSON-RPC MCP attendu.")
    identifier = message.get("id")
    if identifier is not None and (
        type(identifier) not in {str, int}
        or (isinstance(identifier, str) and (not identifier or len(identifier) > 128))
        or (type(identifier) is int and not -(2**63) <= identifier < 2**63)
    ):
        raise HTTPException(400, "Identifiant RPC MCP invalide.")
    return message


def _rpc_result(identifier, result):
    return JSONResponse({"jsonrpc": "2.0", "id": identifier, "result": result}, headers=_PRIVATE)


def _authorized_tools(db, grant_id, authorization):
    # L'autorisation acquiert les verrous run/lease. Elle doit quitter la boucle
    # ASGI et libérer sa transaction avant la lecture asynchrone du corps HTTP.
    try:
        _, _, _, _, _, tools = execution.authorize_grant(db, grant_id, authorization)
        db.commit()
        return tools
    except Exception:
        db.rollback()
        raise


@router.post("/mcp/execution/{grant_id}")
async def proxy_rpc(
    grant_id: str, request: Request, db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    resolver=Depends(get_dns_resolver), transport=Depends(get_http_transport),
):
    # Cette délégation est réservée aux processus CLI ; aucun navigateur ne doit
    # pouvoir l'utiliser par rebinding ou emporter un jeton dans une page web.
    if request.headers.get("origin"):
        raise HTTPException(403, "Les appels MCP de navigateur ne sont pas autorisés.")
    tools = await run_in_threadpool(_authorized_tools, db, grant_id, authorization)
    message = await _read_rpc(request)
    method, identifier, params = message["method"], message.get("id"), message.get("params", {})
    if method == "notifications/initialized" and "id" not in message:
        return Response(status_code=202, headers=_PRIVATE)
    if identifier is None:
        raise HTTPException(400, "Un identifiant RPC est requis pour cette méthode.")
    if method == "initialize":
        version = params.get("protocolVersion")
        version = version if version in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
        return _rpc_result(identifier, {"protocolVersion": version, "capabilities": {"tools": {}},
                                       "serverInfo": {"name": "acp-mission-mcp", "version": "1"}})
    if method == "ping":
        return _rpc_result(identifier, {})
    if method == "tools/list":
        if params.get("cursor"):
            raise HTTPException(400, "Le proxy MCP ne fournit pas de page supplémentaire.")
        result = [{"name": tool["name"], "description": tool.get("description", ""),
                   "inputSchema": tool.get("input_schema", {})} for tool in tools]
        return _rpc_result(identifier, {"tools": result})
    if method != "tools/call":
        return JSONResponse({"jsonrpc": "2.0", "id": identifier,
                             "error": {"code": -32601, "message": "Méthode MCP non prise en charge."}},
                            headers=_PRIVATE)
    name, arguments = params.get("name"), params.get("arguments", {})
    if (not isinstance(name, str) or not 1 <= len(name) <= 200 or not isinstance(arguments, dict)
            or set(params) - {"name", "arguments", "_meta"}):
        raise HTTPException(400, "Arguments tools/call invalides.")
    result = await run_in_threadpool(execution.call_tool_sync,
        db, grant_id=grant_id, authorization=authorization, rpc_id=identifier, name=name,
        arguments=arguments, policy=_policy(), resolver=resolver, transport=transport,
    )
    return _rpc_result(identifier, result)


@router.delete("/mcp/execution/{grant_id}", status_code=204)
def close_grant(grant_id: str, db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    grant, *_ = execution.authorize_grant(db, grant_id, authorization)
    grant.revoked_at = execution.utcnow()
    db.commit()
    return Response(status_code=204, headers=_PRIVATE)
