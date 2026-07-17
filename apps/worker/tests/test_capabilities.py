from acp_worker.capabilities import missing_capabilities


def test_missing_capabilities_is_deterministic():
    assert missing_capabilities(["git", "blender", "git"], ["git"]) == ["blender"]
