"""Jetons MCP éphémères : mémoire/env enfant, jamais argv, preuve ou checkpoint."""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import WorkerConfig

_TOOL = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_PATH = re.compile(r"/mcp/execution/[A-Za-z0-9-]{1,64}\Z")


@dataclass(frozen=True)
class McpExecution:
    servers: tuple[dict[str, Any], ...]
    environment: dict[str, str] = field(repr=False)
    expires_at: datetime

    def remaining_seconds(self) -> float:
        remaining = (self.expires_at - datetime.now(timezone.utc)).total_seconds() - 5
        if remaining <= 0:
            raise RuntimeError("autorisation MCP expirée avant l'exécution")
        return remaining


async def acquire_mcp(client: httpx.AsyncClient, config: WorkerConfig, *, worker_id: str,
                      attempt_id: str, fencing_token: int, step_id: str, snapshot: list,
                      timeout_seconds: float) -> McpExecution | None:
    if not snapshot:
        return None
    response = await client.post(f"{config.api_url}/work/workers/{worker_id}/runs/{attempt_id}/mcp/grants",
        headers={"X-Attempt-Fencing-Token": str(fencing_token)},
        json={"step_id": step_id, "ttl_seconds": max(30, min(3600, math.ceil(timeout_seconds) + 10))})
    response.raise_for_status()
    if len(response.content) > 200_000:
        raise RuntimeError("autorisations MCP trop volumineuses")
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
        raise RuntimeError("réponse d'autorisation MCP invalide")
    expected = {(item["server_id"], item["revision_number"]) for item in snapshot}
    actual = set()
    environment = {}
    servers = []
    expiries = []
    for index, item in enumerate(data["servers"]):
        if not isinstance(item, dict):
            raise RuntimeError("autorisation de serveur MCP invalide")
        key = (item.get("server_id"), item.get("revision_number"))
        token, path, tools = item.get("token"), item.get("url_path"), item.get("allowed_tools")
        if key not in expected or key in actual or not isinstance(token, str) or not 16 <= len(token) <= 4096 or any(char.isspace() for char in token):
            raise RuntimeError("autorisation MCP hors révision ou jeton invalide")
        if not isinstance(path, str) or not _PATH.fullmatch(path) or not isinstance(tools, list) or not tools or any(not isinstance(tool, str) or not _TOOL.fullmatch(tool) for tool in tools):
            raise RuntimeError("URL de proxy ou outils MCP invalides")
        try:
            expiry = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise ValueError()
        except (KeyError, AttributeError, TypeError, ValueError):
            raise RuntimeError("expiration d'autorisation MCP invalide") from None
        variable = f"ACP_MCP_GRANT_{index}"
        environment[variable] = token
        servers.append({"name": f"acp_{index}", "url": config.api_url + path,
                        "token_variable": variable, "tools": tools})
        expiries.append(expiry)
        actual.add(key)
    if actual != expected or not servers:
        raise RuntimeError("une liaison MCP épinglée manque à l'exécution")
    result = McpExecution(tuple(servers), environment, min(expiries))
    result.remaining_seconds()
    return result
