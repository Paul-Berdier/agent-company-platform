"""Autorisations MCP synthétiques : refus de secrets argv et d'origine différente."""

import json
import tomllib
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from acp_worker.config import WorkerConfig
from acp_worker.executors import codex_command, claude_command, _count_json_events
from acp_worker.mcp_execution import acquire_mcp


@pytest.mark.parametrize("invalid", [None, "origin", "revision", "expired", "missing", "tools"])
async def test_grants_are_scoped_validated_and_never_exposed_in_commands(tmp_path, invalid):
    config = WorkerConfig(api_url="https://api.test", gateway_url="https://gateway.test", provider_id="hermes",
        state_dir=tmp_path, gateway_service_token="fixture", poll_interval=.1, step_seconds=0, name="fixture", max_concurrency=1, simulation=False, registration_token=None)
    token = "fixture-mcp-secret-never-in-argv"
    server = {"server_id": "server-1", "revision_number": 2, "token": token,
              "url_path": "/mcp/execution/grant-1", "name": "fixture", "allowed_tools": ["echo"],
              "expires_at": (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}
    if invalid == "origin": server["url_path"] = "https://external.test/steal"
    if invalid == "revision": server["revision_number"] = 3
    if invalid == "expired": server["expires_at"] = "2000-01-01T00:00:00Z"
    if invalid == "tools": server["allowed_tools"] = ["echo,*"]

    def handler(request):
        assert request.headers["X-Attempt-Fencing-Token"] == "4"
        assert json.loads(request.content) == {"step_id": "step-stable", "ttl_seconds": 70}
        return httpx.Response(200, json={"servers": [] if invalid == "missing" else [server]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        if invalid:
            with pytest.raises(RuntimeError):
                await acquire_mcp(client, config, worker_id="worker-1", attempt_id="attempt-1", fencing_token=4,
                    step_id="step-stable", snapshot=[{"server_id":"server-1","revision_number":2}], timeout_seconds=60)
            return
        context = await acquire_mcp(client, config, worker_id="worker-1", attempt_id="attempt-1", fencing_token=4,
            step_id="step-stable", snapshot=[{"server_id":"server-1","revision_number":2}], timeout_seconds=60)
    codex = codex_command(tmp_path, "fixture", mcp=context)
    claude = claude_command(tmp_path, "fixture", mcp=context)
    assert token not in repr(context) and token not in " ".join(codex+claude)
    assert context.environment == {"ACP_MCP_GRANT_0": token}
    value = tomllib.loads(next(item for item in codex if item.startswith("mcp_servers=")))
    assert value["mcp_servers"]["acp_0"]["enabled_tools"] == ["echo"]
    assert value["mcp_servers"]["acp_0"]["bearer_token_env_var"] == "ACP_MCP_GRANT_0"
    assert "--safe-mode" not in claude and "--restricted" in claude
    assert "mcp__acp_0__echo" in claude[claude.index("--allowedTools")+1]
    value = json.loads(claude[claude.index("--mcp-config")+1])
    assert value["mcpServers"]["acp_0"]["headers"]["Authorization"] == "Bearer ${ACP_MCP_GRANT_0}"
    raw = (json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"x"*15990+token}})
           + '\n{"type":"turn.completed"}\n').encode()
    _, output, _ = _count_json_events("codex_cli", raw, require_terminal_success=True, redactions=(token,))
    assert "fixture" not in output["text"]


async def test_no_mcp_binding_never_requests_grants(tmp_path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail("unexpected I/O"))) as client:
        assert await acquire_mcp(client, None, worker_id="worker", attempt_id="run", fencing_token=1,
                                 step_id="step", snapshot=[], timeout_seconds=60) is None
