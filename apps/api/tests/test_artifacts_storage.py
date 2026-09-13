"""Stockage local de livrables adressé par contenu.

Le client ne choisit jamais le chemin : la clé est ``<sha256[0:2]>/<sha256>``. Le
refus de taille intervient **pendant** la lecture du flux, jamais après avoir écrit
le fichier entier, et aucun fragment ne survit à un refus.
"""

import io
import os
import stat
from pathlib import Path

import pytest

from acp_api.artifacts_storage import (
    DEFAULT_ARTIFACT_MAX_BYTES,
    DEFAULT_ARTIFACT_MAX_BYTES_PER_RUN,
    DEFAULT_ARTIFACT_STORAGE_DIR,
    ArtifactKeyInvalid,
    ArtifactNotFound,
    ArtifactStorage,
    ArtifactStorageError,
    ArtifactTooLarge,
    LocalArtifactStorage,
    artifact_max_bytes,
    artifact_max_bytes_per_run,
    content_key,
    local_artifact_storage,
    storage_directory,
)

CONTENT = b"capture PNG factice \x89PNG\r\n" * 50


@pytest.fixture
def storage(tmp_path) -> LocalArtifactStorage:
    return LocalArtifactStorage(tmp_path / "artifacts")


def _files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


class _CountingStream:
    """Flux qui refuse de servir plus que sa garde : prouve un refus anticipé."""

    def __init__(self, chunk: bytes, guard_bytes: int) -> None:
        self._chunk = chunk
        self._guard = guard_bytes
        self.served = 0

    def read(self, size: int = -1) -> bytes:
        if self.served >= self._guard:
            raise AssertionError(
                "le flux a été lu au-delà de la borne : le refus est arrivé trop tard"
            )
        piece = self._chunk if size < 0 or size >= len(self._chunk) else self._chunk[:size]
        self.served += len(piece)
        return piece


# --- clé et adressage par contenu ---------------------------------------------


def test_write_returns_a_content_addressed_key(storage):
    import hashlib

    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    expected = hashlib.sha256(CONTENT).hexdigest()
    assert blob.sha256 == expected
    assert blob.size == len(CONTENT)
    assert blob.key == f"{expected[:2]}/{expected}"


def test_key_never_contains_a_client_supplied_name(storage):
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    assert set(blob.key) <= set("0123456789abcdef/")
    stored = next(iter(_files(storage.root)))
    assert stored.name == blob.sha256
    assert stored.parent.name == blob.sha256[:2]


def test_content_key_matches_the_written_key(storage):
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    assert content_key(blob.sha256) == blob.key


def test_identical_content_is_stored_once(storage):
    first = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    second = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    assert first.key == second.key
    assert first.sha256 == second.sha256
    assert len(_files(storage.root)) == 1


def test_different_contents_are_stored_separately(storage):
    first = storage.write(io.BytesIO(b"alpha"), max_bytes=1_000_000)
    second = storage.write(io.BytesIO(b"beta"), max_bytes=1_000_000)
    assert first.key != second.key
    assert len(_files(storage.root)) == 2


def test_an_empty_stream_is_stored_as_an_empty_blob(storage):
    blob = storage.write(io.BytesIO(b""), max_bytes=1_000_000)
    assert blob.size == 0
    with storage.open(blob.key) as handle:
        assert handle.read() == b""


def test_a_successful_write_leaves_no_temporary_file(storage):
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    assert [path.name for path in _files(storage.root)] == [blob.sha256]


def test_a_concurrent_write_of_the_same_content_succeeds(storage, monkeypatch):
    """Deux écritures simultanées du même contenu : le blob cible est déjà bon.

    Sous Windows, remplacer un fichier ouvert en lecture échoue. L'adressage par
    contenu garantit que la cible porte déjà les mêmes octets : le téléversement
    identique ne doit pas être refusé pour autant.
    """

    reference = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)

    def refuse(source, destination):
        raise PermissionError("fichier verrouillé par un lecteur")

    monkeypatch.setattr(Path, "exists", lambda self: False)
    monkeypatch.setattr(os, "replace", refuse)
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    assert blob.key == reference.key
    monkeypatch.undo()
    assert len(_files(storage.root)) == 1


def test_a_failed_replace_without_a_target_is_reported(storage, monkeypatch):
    def refuse(source, destination):
        raise PermissionError("volume en lecture seule")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError):
        storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    monkeypatch.undo()
    assert _files(storage.root) == []


# --- borne de taille ----------------------------------------------------------


def test_writing_more_than_max_bytes_is_refused(storage):
    with pytest.raises(ArtifactTooLarge):
        storage.write(io.BytesIO(CONTENT), max_bytes=len(CONTENT) - 1)


def test_a_refused_write_leaves_no_residual_file(storage):
    with pytest.raises(ArtifactTooLarge):
        storage.write(io.BytesIO(CONTENT), max_bytes=10)
    assert _files(storage.root) == []


def test_exactly_max_bytes_is_accepted(storage):
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=len(CONTENT))
    assert blob.size == len(CONTENT)


def test_the_limit_is_enforced_while_reading_the_stream(storage):
    max_bytes = 64 * 1024
    stream = _CountingStream(b"x" * 8192, guard_bytes=max_bytes * 4)
    with pytest.raises(ArtifactTooLarge):
        storage.write(stream, max_bytes=max_bytes)
    assert stream.served <= max_bytes * 4
    assert _files(storage.root) == []


def test_a_non_positive_limit_is_refused(storage):
    for limit in (0, -1):
        with pytest.raises(ValueError):
            storage.write(io.BytesIO(CONTENT), max_bytes=limit)


def test_a_text_stream_is_refused(storage):
    with pytest.raises(ArtifactStorageError):
        storage.write(io.StringIO("du texte"), max_bytes=1_000_000)


# --- lecture, existence, suppression ------------------------------------------


def test_content_is_read_back_as_a_stream(storage):
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    chunks = []
    with storage.open(blob.key) as handle:
        while True:
            chunk = handle.read(64)
            if not chunk:
                break
            chunks.append(chunk)
    assert b"".join(chunks) == CONTENT


def test_exists_and_delete_follow_the_blob(storage):
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    assert storage.exists(blob.key) is True
    storage.delete(blob.key)
    assert storage.exists(blob.key) is False
    assert _files(storage.root) == []


def test_deleting_an_absent_blob_is_idempotent(storage):
    missing = content_key("a" * 64)
    storage.delete(missing)
    storage.delete(missing)
    assert storage.exists(missing) is False


def test_opening_an_absent_blob_raises_an_explicit_error(storage):
    with pytest.raises(ArtifactNotFound):
        storage.open(content_key("b" * 64))


@pytest.mark.parametrize(
    "key",
    [
        "",
        "..",
        "../../etc/passwd",
        "aa/../../secrets.env",
        "aa/" + "a" * 63,
        "aa/" + "A" * 64,
        "zz/" + "a" * 64,
        "ab/" + "a" * 64,
        "C:/windows/system32",
        "aa/" + "a" * 64 + "/extra",
    ],
)
def test_an_invalid_key_never_reaches_the_filesystem(storage, key: str):
    for operation in (storage.open, storage.exists, storage.delete):
        with pytest.raises(ArtifactKeyInvalid):
            operation(key)


def test_local_storage_satisfies_the_protocol(storage):
    assert isinstance(storage, ArtifactStorage)


@pytest.mark.skipif(os.name == "nt", reason="permissions POSIX non applicables")
def test_the_blob_is_private_to_the_service(storage):
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    mode = stat.S_IMODE((storage.root / blob.key).stat().st_mode)
    assert mode == 0o600


def test_a_system_without_permissions_still_stores_the_blob(storage, monkeypatch):
    """Windows ignore ``chmod`` : le téléversement ne doit pas en dépendre."""

    def refuse(self, mode):
        raise OSError("chmod non supporté")

    monkeypatch.setattr(Path, "chmod", refuse)
    blob = storage.write(io.BytesIO(CONTENT), max_bytes=1_000_000)
    with storage.open(blob.key) as handle:
        assert handle.read() == CONTENT


# --- configuration ------------------------------------------------------------


def test_storage_directory_defaults_to_the_local_data_dir():
    assert storage_directory({}) == Path(DEFAULT_ARTIFACT_STORAGE_DIR)
    assert DEFAULT_ARTIFACT_STORAGE_DIR == "./acp-data/artifacts"


def test_storage_directory_reads_the_environment(tmp_path):
    environ = {"ACP_ARTIFACT_STORAGE_DIR": str(tmp_path / "blobs")}
    assert storage_directory(environ) == tmp_path / "blobs"
    assert local_artifact_storage(environ).root == tmp_path / "blobs"


def test_artifact_limits_have_documented_defaults():
    assert DEFAULT_ARTIFACT_MAX_BYTES == 200 * 1024 * 1024
    assert DEFAULT_ARTIFACT_MAX_BYTES_PER_RUN == 1024 * 1024 * 1024
    assert artifact_max_bytes({}) == DEFAULT_ARTIFACT_MAX_BYTES
    assert artifact_max_bytes_per_run({}) == DEFAULT_ARTIFACT_MAX_BYTES_PER_RUN
    assert artifact_max_bytes({"ACP_ARTIFACT_MAX_BYTES": "1024"}) == 1024
    assert artifact_max_bytes_per_run({"ACP_ARTIFACT_MAX_BYTES_PER_RUN": "2048"}) == 2048


@pytest.mark.parametrize("raw", ["0", "-1", "abc", "1.5"])
def test_an_unusable_limit_is_refused_rather_than_silently_relaxed(raw: str):
    with pytest.raises(ValueError):
        artifact_max_bytes({"ACP_ARTIFACT_MAX_BYTES": raw})
    with pytest.raises(ValueError):
        artifact_max_bytes_per_run({"ACP_ARTIFACT_MAX_BYTES_PER_RUN": raw})
