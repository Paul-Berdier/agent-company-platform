import hashlib

import httpx
import pytest

from acp_worker.config import WorkerConfig
from acp_worker.extensions import load_extensions
from acp_worker.executors import invocation_from_mission


@pytest.mark.parametrize("invalid", [None, "hash", "revision", "missing", "large"])
async def test_only_complete_pinned_skill_content_reaches_agent_prompt(tmp_path, invalid):
    config = WorkerConfig(api_url="https://api.test", gateway_url="https://gateway.test", provider_id="hermes",
        gateway_service_token="fixture", state_dir=tmp_path, poll_interval=.1, step_seconds=0,
        name="fixture", max_concurrency=1, simulation=False, registration_token=None)
    content = "Règle métier approuvée." if invalid != "large" else "x"*24001
    skill = {"skill_id": "skill-1", "revision_number": 2, "name": "Règle", "content": content,
             "sha256": hashlib.sha256(content.encode()).hexdigest()}
    if invalid == "hash": skill["sha256"] = "0"*64
    if invalid == "revision": skill["revision_number"] = 3

    def handler(request):
        assert request.headers["X-Attempt-Fencing-Token"] == "9"
        return httpx.Response(200, json={"skills": [] if invalid == "missing" else [skill], "mcp": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        if invalid:
            with pytest.raises(RuntimeError):
                await load_extensions(client, config, "worker", "run", 9, {"skills": [{"skill_id":"skill-1", "revision_number":2}]})
            return
        result = await load_extensions(client, config, "worker", "run", 9, {"skills": [{"skill_id":"skill-1", "revision_number":2}]})
    mission = {"objective":"Objectif", "expected_outcome":"Résultat", "acceptance_criteria":["preuve"],
        "autonomy":{"mode":"supervised", "allowed_actions":[], "forbidden_actions":[], "approval_required_actions":[]},
        "resources":[{"kind":"project_workspace","identifier":"project-1","access":"read"}]}
    invocation = invocation_from_mission("codex_cli", "project-1", mission, {"steps":[], "_skills":result["skills"]})
    assert content in invocation.prompt and '"revision_number": 2' in invocation.prompt
    assert "ne peuvent accorder" in invocation.prompt
