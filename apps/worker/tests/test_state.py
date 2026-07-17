from pathlib import Path
from uuid import uuid4

from acp_worker.state import WorkerCredentials, load_credentials, save_credentials


def test_credentials_round_trip_without_temporary_file():
    test_dir = Path.cwd() / ".pytest-tmp" / uuid4().hex
    credentials = WorkerCredentials(
        worker_id="worker-1",
        token="secret-token",
        name="test-worker",
        capabilities=["git"],
        max_concurrency=1,
        simulation=True,
        token_expires_at="2030-01-01T00:00:00Z",
    )
    try:
        path = save_credentials(test_dir, credentials)
        assert load_credentials(test_dir) == credentials
        assert "secret-token" in path.read_text(encoding="utf-8")
        assert not path.with_suffix(".tmp").exists()
    finally:
        for child in test_dir.glob("*"):
            child.unlink()
        test_dir.rmdir()
        test_dir.parent.rmdir()
