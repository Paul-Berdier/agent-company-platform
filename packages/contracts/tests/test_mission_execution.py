"""Une équipe ne contourne pas les préconditions d'une mission CLI."""

import copy

import pytest
from pydantic import ValidationError

from acp_contracts import MissionCreate


def payload():
    return {
        "project_id": "project-1", "title": "Équipe", "objective": "Comparer le code",
        "expected_outcome": "Deux réponses", "acceptance_criteria": ["Preuves lisibles"],
        "autonomy": {"mode": "supervised"},
        "resources": [{"kind": "project_workspace", "identifier": "project-1", "access": "read"}],
        "budget": {"max_tool_calls": 10}, "duration_seconds": 600,
        "required_capabilities": ["agent_team", "codex_cli", "claude_code"],
        "execution": {"mode": "multi_agent", "executors": ["codex_cli", "claude_code"], "max_concurrency": 2},
    }


def test_team_contract_round_trip_retains_executor_constraints():
    body = payload()
    parsed = MissionCreate.model_validate(body)
    assert parsed.execution.model_dump() == body["execution"]
    assert parsed.budget.max_cost is None
    assert MissionCreate.model_validate(parsed.model_dump()).execution == parsed.execution


@pytest.mark.parametrize("field,value", [
    ("resources", []),
    ("resources", [{"kind": "project_workspace", "identifier": "another-project"}]),
    ("autonomy", {"mode": "autonomous"}),
    ("autonomy", {"mode": "supervised", "allowed_actions": ["shell"]}),
    ("required_capabilities", ["codex_cli", "claude_code"]),
    ("execution", {"executors": ["codex_cli", "codex_cli"]}),
    ("execution", {"executors": ["unknown"]}),
    ("execution", {"executors": ["codex_cli"], "max_concurrency": 3}),
])
def test_invalid_team_is_refused_before_admission(field, value):
    body = copy.deepcopy(payload())
    body[field] = value
    with pytest.raises(ValidationError):
        MissionCreate.model_validate(body)


def test_read_only_claude_team_cannot_acquire_write_access():
    body = payload()
    body["execution"]["executors"] = ["claude_code"]
    body["resources"][0]["access"] = "write"
    with pytest.raises(ValidationError, match="seul Codex"):
        MissionCreate.model_validate(body)
