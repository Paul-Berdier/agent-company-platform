import json
import os
import stat
from pathlib import Path
from uuid import uuid4

import pytest

import acp_worker.state as worker_state
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
        project_id="project-1",
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
        assert list(test_dir.glob(".worker.json.*.tmp")) == []
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


def test_legacy_credentials_without_scope_load_into_quarantine(tmp_path: Path):
    data = dict(credentials().__dict__)
    data.pop("project_id")
    data.pop("global_access")
    (tmp_path / "worker.json").write_text(json.dumps(data), encoding="utf-8")

    loaded = load_credentials(tmp_path, "https://api.example")

    assert loaded is not None
    assert loaded.project_id is None
    assert loaded.global_access is False


def test_credentials_reject_simultaneous_project_and_global_scope():
    with pytest.raises(CredentialStateError, match="incompatibles"):
        WorkerCredentials(
            **{
                **credentials().__dict__,
                "project_id": "project-1",
                "global_access": True,
            }
        )


def test_worker_credentials_repr_never_contains_the_bearer():
    rendered = repr(credentials())

    assert "secret-token" not in rendered


def test_credentials_file_is_private_before_the_first_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    real_chmod = worker_state.os.chmod
    observations: list[tuple[int, int]] = []

    def record_chmod(path: str | os.PathLike[str], mode: int) -> None:
        candidate = Path(path)
        observations.append((mode, candidate.stat().st_size))
        real_chmod(path, mode)

    monkeypatch.setattr(worker_state.os, "chmod", record_chmod)

    path = save_credentials(tmp_path, credentials())

    assert observations[0] == (0o600, 0)
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_predictable_legacy_symlink_is_never_followed(tmp_path: Path):
    victim = tmp_path / "victim.txt"
    victim.write_text("intact", encoding="utf-8")
    legacy_temporary = tmp_path / "worker.tmp"
    symbolic = True
    try:
        legacy_temporary.symlink_to(victim)
    except OSError:
        # Windows peut refuser les symlinks sans mode développeur. Un hard link
        # reproduit le risque de l'ancien `write_text(worker.tmp)` sans skip.
        symbolic = False
        os.link(victim, legacy_temporary)

    path = save_credentials(tmp_path, credentials())

    assert path == tmp_path / "worker.json"
    assert victim.read_text(encoding="utf-8") == "intact"
    assert legacy_temporary.is_symlink() is symbolic
    assert list(tmp_path.glob(".worker.json.*.tmp")) == []


def test_failed_atomic_replace_preserves_state_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = save_credentials(tmp_path, credentials())
    original = path.read_bytes()

    def fail_replace(_source: os.PathLike[str], _destination: os.PathLike[str]) -> None:
        raise OSError("replace refused")

    monkeypatch.setattr(worker_state.os, "replace", fail_replace)

    with pytest.raises(CredentialStateError, match="façon sûre"):
        save_credentials(tmp_path, credentials("https://other-api.example"))

    assert path.read_bytes() == original
    assert list(tmp_path.glob(".worker.json.*.tmp")) == []
