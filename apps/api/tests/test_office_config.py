"""Tests de la sélection des templates de salles (office-config)."""

import os
import tempfile

os.environ["ACP_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["ACP_PLUGINS_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "..", "plugins")

from fastapi.testclient import TestClient  # noqa: E402

from acp_agent_sdk import RoomTemplate, select_room_template  # noqa: E402
from acp_api.main import app  # noqa: E402


def _templates():
    return [
        RoomTemplate(id="small", department_type="x", capacity=6),
        RoomTemplate(id="large", department_type="x", capacity=18),
        RoomTemplate(id="other", department_type="y", capacity=4),
    ]


def test_select_smallest_sufficient():
    assert select_room_template(_templates(), "x", 4).id == "small"
    assert select_room_template(_templates(), "x", 6).id == "small"
    assert select_room_template(_templates(), "x", 7).id == "large"


def test_select_largest_when_overflow():
    assert select_room_template(_templates(), "x", 99).id == "large"


def test_select_none_for_unknown_type():
    assert select_room_template(_templates(), "z", 1) is None


def test_office_config_returns_template():
    with TestClient(app) as client:
        org = client.post("/organizations", json={"name": "T"}).json()
        ws = client.post("/workspaces", json={"organization_id": org["id"], "name": "W"}).json()
        dept = client.post("/departments", json={
            "workspace_id": ws["id"], "name": "Dev",
            "department_type": "software-engineering",
        }).json()

        small = client.get(f"/departments/{dept['id']}/office-config?capacity=3").json()
        assert small["template_id"] == "software-office-small-v1"
        assert small["width"] == 12 and small["height"] == 9
        assert small["office_theme"] == "dev-floor"
        assert any(s["kind"] == "coffee-machine" for s in small["stations"])
        assert small["doors"] == [{"x": 6, "y": 9}]

        large = client.get(f"/departments/{dept['id']}/office-config?capacity=15").json()
        assert large["template_id"] == "software-office-large-v1"
        assert large["width"] == 14

        # secteur sans template : repli sur les stations historiques du module
        generic = client.post("/departments", json={
            "workspace_id": ws["id"], "name": "Ops", "department_type": "general",
        }).json()
        fallback = client.get(f"/departments/{generic['id']}/office-config").json()
        assert "template_id" not in fallback
        assert len(fallback["stations"]) > 0
