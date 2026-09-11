import json
from pathlib import Path
from uuid import uuid4

import pytest

from acp_worker.state import (
    CredentialStateError,
    WorkerCredentials,
    load_credentials,
    save_credentials,
)


def credentials(api_origin: str = "https://api.example") -> WorkerCredentials:
    return WorkerCredentials(
        worker_id="worker-1",
        token="secret-token",
        api_origin=api_origin,
        name="test-worker",
        capabilities=["git"],
        max_concurrency=1,
        simulation=True,
        token_expires_at="2030-01-01T00:00:00Z",
    )


def test_credentials_round_trip_without_temporary_file():
    test_dir = Path.cwd() / ".pytest-tmp" / uuid4().hex
    worker_credentials = credentials("https://API.EXAMPLE:443/")
    try:
        path = save_credentials(test_dir, worker_credentials)
        assert load_credentials(test_dir, "https://api.example") == worker_credentials
        assert "secret-token" in path.read_text(encoding="utf-8")
        assert worker_credentials.api_origin == "https://api.example"
        assert not path.with_suffix(".tmp").exists()
    finally:
        for child in test_dir.glob("*"):
            child.unlink()
        test_dir.rmdir()
        test_dir.parent.rmdir()


def test_credentials_are_rejected_after_api_origin_changes(tmp_path: Path):
    save_credentials(tmp_path, credentials("https://api-a.example"))

    with pytest.raises(CredentialStateError, match="autre origine API"):
        load_credentials(tmp_path, "https://api-b.example")


def test_legacy_credentials_without_origin_fail_closed(tmp_path: Path):
    data = {
        key: value
        for key, value in credentials().__dict__.items()
        if key != "api_origin"
    }
    state_file = tmp_path / "worker.json"
    state_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CredentialStateError, match="réenregistrement requis"):
        load_credentials(tmp_path, "https://api.example")
