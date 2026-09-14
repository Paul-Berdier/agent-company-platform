"""Bibliothèque de livrables : téléversement, téléchargement, liens signés.

Un contenu produit par un test (capture d'un site tiers, rapport HTML, trace) est
traité comme non fiable. Ces tests verrouillent les trois promesses du Lot E :

1. le type servi vient d'une **allowlist serveur**, jamais d'un reniflage du contenu ;
2. le contenu ne s'obtient que par une session valide ou un lien signé, borné,
   révocable, lié à un artefact **et** à un utilisateur ;
3. un plafond dépassé est refusé **pendant** la lecture du flux, sans laisser de
   fichier résiduel.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import io
import json
import struct
import tempfile
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api.artifacts_storage import (
    ArtifactStorageFull,
    ArtifactStorageUnavailable,
    LocalArtifactStorage,
)
from acp_api.deps import get_db
from acp_api.main import app
from acp_api.routers import artifacts as artifacts_router
from acp_api.routers.artifacts import MULTIPART_HEADERS_MAX_BYTES, safe_content_type
from acp_api.routers.workers import _token_hash as worker_token_hash
from acp_api.security import create_user_session, hash_password
from acp_api.signing import sign_artifact_token, token_hash
from acp_database.models import (
    ArtifactLinkModel,
    ArtifactModel,
    AlertModel,
    Base,
    EventModel,
    MembershipModel,
    OrganizationModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    UserModel,
    WorkerLeaseModel,
    WorkerModel,
    WorkspaceModel,
)

PASSWORD = "correct horse battery staple"
WORKER_TOKEN = "jeton-worker-de-test-avec-assez-d-entropie"


# --- Décor ---------------------------------------------------------------------


@dataclass
class Context:
    client: TestClient
    session_factory: sessionmaker
    storage: LocalArtifactStorage
    owner_id: str
    member_id: str
    member_session: str
    member_csrf: str
    stranger_id: str
    stranger_session: str
    stranger_csrf: str
    project_id: str
    other_project_id: str
    run_id: str
    other_run_id: str
    worker_id: str
    worker_token: str


def _user(db: Session, login: str, platform_role: str) -> str:
    user = UserModel(
        login_normalized=f"{login}-{uuid4().hex}",
        display_name=login,
        password_hash=hash_password(PASSWORD),
        platform_role=platform_role,
    )
    db.add(user)
    db.flush()
    return user.id


def _session(db: Session, user_id: str) -> tuple[str, str]:
    _, session_token, csrf_token = create_user_session(db, user_id)
    return session_token, csrf_token


def _project(db: Session, name: str) -> str:
    organization = OrganizationModel(name=f"Org {name}")
    db.add(organization)
    db.flush()
    workspace = WorkspaceModel(organization_id=organization.id, name=f"Ws {name}")
    db.add(workspace)
    db.flush()
    project = ProjectModel(workspace_id=workspace.id, name=f"Projet {name}")
    db.add(project)
    db.flush()
    return project.id


def _run(db: Session, project_id: str) -> tuple[str, str]:
    task = TaskModel(project_id=project_id, title="Tâche")
    db.add(task)
    db.flush()
    run = TaskRunModel(task_id=task.id, status="running", fencing_token=1)
    db.add(run)
    db.flush()
    return run.id, task.id


def _worker(db: Session, token: str) -> str:
    """Worker authentifiable : seul le condensat du jeton est stocké."""

    worker = WorkerModel(
        name=f"worker-{uuid4().hex}",
        token_hash=worker_token_hash(token),
        token_prefix=token[:12],
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        capabilities=["git"],
    )
    db.add(worker)
    db.flush()
    return worker.id


def _lease(db: Session, worker_id: str, task_id: str, run_id: str) -> None:
    db.add(
        WorkerLeaseModel(
            worker_id=worker_id,
            task_id=task_id,
            task_run_id=run_id,
            status="active",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("ACP_ARTIFACT_STORAGE_DIR", str(tmp_path / "blobs"))
    monkeypatch.delenv("ACP_ARTIFACT_SIGNING_KEYS", raising=False)
    monkeypatch.delenv("ACP_ARTIFACT_PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("ACP_API_URL", raising=False)
    monkeypatch.delenv("ACP_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("ACP_ARTIFACT_MAX_BYTES", raising=False)
    monkeypatch.delenv("ACP_ARTIFACT_MAX_BYTES_PER_RUN", raising=False)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with session_factory() as db:
        owner_id = _user(db, "proprietaire", "owner")
        member_id = _user(db, "membre", "member")
        stranger_id = _user(db, "etranger", "member")
        project_id = _project(db, "Alpha")
        other_project_id = _project(db, "Beta")
        db.add(
            MembershipModel(
                user_id=member_id,
                scope_type="project",
                scope_id=project_id,
                role="member",
            )
        )
        db.add(
            MembershipModel(
                user_id=stranger_id,
                scope_type="project",
                scope_id=other_project_id,
                role="member",
            )
        )
        run_id, task_id = _run(db, project_id)
        other_run_id, _ = _run(db, other_project_id)
        worker_id = _worker(db, WORKER_TOKEN)
        _lease(db, worker_id, task_id, run_id)
        member_session, member_csrf = _session(db, member_id)
        stranger_session, stranger_csrf = _session(db, stranger_id)
        db.commit()

    client = TestClient(app)
    client.cookies.set("acp_session", member_session)
    client.headers["X-CSRF-Token"] = member_csrf
    client.headers["X-Attempt-Fencing-Token"] = "1"
    try:
        yield Context(
            client=client,
            session_factory=session_factory,
            storage=LocalArtifactStorage(tmp_path / "blobs"),
            owner_id=owner_id,
            member_id=member_id,
            member_session=member_session,
            member_csrf=member_csrf,
            stranger_id=stranger_id,
            stranger_session=stranger_session,
            stranger_csrf=stranger_csrf,
            project_id=project_id,
            other_project_id=other_project_id,
            run_id=run_id,
            other_run_id=other_run_id,
            worker_id=worker_id,
            worker_token=WORKER_TOKEN,
        )
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _seed_artifact(
    context: Context,
    *,
    payload: bytes | None = b"contenu",
    project_id: str | None = None,
    task_run_id: str | None = None,
    content_type: str = "application/octet-stream",
    original_name: str = "",
    stream_kind: str = "file",
    kind: str = "report",
    created_at: datetime | None = None,
    deleted_at: datetime | None = None,
) -> str:
    """Insère un livrable (et son blob) directement, sans passer par le worker."""

    storage_key = None
    checksum = None
    size = None
    if payload is not None:
        blob = context.storage.write(io.BytesIO(payload), max_bytes=10_000_000)
        storage_key = blob.key
        checksum = blob.sha256
        size = blob.size
    with context.session_factory() as db:
        artifact = ArtifactModel(
            project_id=project_id or context.project_id,
            task_run_id=task_run_id or context.run_id,
            worker_id=context.worker_id,
            kind=kind,
            path=original_name or "sortie/livrable",
            checksum=checksum,
            size_bytes=size,
            metadata_json={},
            storage_key=storage_key,
            content_type=content_type,
            original_name=original_name,
            source="worker",
            stream_kind=stream_kind,
            deleted_at=deleted_at,
        )
        if created_at is not None:
            artifact.created_at = created_at
        db.add(artifact)
        db.commit()
        return artifact.id


# --- Allowlist de types (§7) ----------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "original_name", "expected_type", "expected_inline"),
    [
        ("image/png", "capture.png", "image/png", True),
        ("image/jpeg", "capture.jpg", "image/jpeg", True),
        ("image/webp", "capture.webp", "image/webp", True),
        ("image/gif", "capture.gif", "image/gif", True),
        ("video/webm", "video.webm", "video/webm", True),
        ("video/mp4", "video.mp4", "video/mp4", True),
        ("text/plain", "journal.txt", "text/plain; charset=utf-8", True),
        # Le JSON est servi en texte : jamais interprété par le navigateur.
        ("application/json", "resultat.json", "text/plain; charset=utf-8", True),
        ("model/gltf-binary", "scene.glb", "model/gltf-binary", True),
        # Le JSON glTF et une déclaration GLB incomplète restent des téléchargements.
        ("model/gltf+json", "scene.gltf", "application/octet-stream", False),
        ("application/octet-stream", "scene.glb", "application/octet-stream", False),
        ("model/gltf-binary", "scene.bin", "application/octet-stream", False),
        # Type inconnu de l'allowlist.
        ("application/pdf", "rapport.pdf", "application/octet-stream", False),
        ("", "", "application/octet-stream", False),
        # Paramètres et casse n'élargissent rien.
        ("IMAGE/PNG; charset=utf-8", "capture.png", "image/png", True),
    ],
)
def test_the_served_type_comes_from_the_server_allowlist(
    declared, original_name, expected_type, expected_inline
):
    assert safe_content_type(declared, original_name) == (
        expected_type,
        expected_inline,
    )


@pytest.mark.parametrize(
    ("declared", "original_name"),
    [
        ("text/html", "rapport.html"),
        ("text/html", "rapport.htm"),
        ("image/svg+xml", "schema.svg"),
        ("application/zip", "trace.zip"),
        ("application/xhtml+xml", "page.xhtml"),
        # Un nom d'apparence inoffensive ne réhabilite jamais un type dangereux :
        # la concordance nom/type se juge dans les deux sens (§7).
        ("text/html", "piege.png"),
        ("application/zip", "trace.txt"),
        ("image/svg+xml", "schema.png"),
        ("application/xhtml+xml", "page.json"),
        ("model/gltf+json", "modele.png"),
    ],
)
def test_html_svg_and_archives_are_never_served_inline(declared, original_name):
    assert safe_content_type(declared, original_name) == (
        "application/octet-stream",
        False,
    )


@pytest.mark.parametrize(
    ("declared", "original_name"),
    [
        ("image/png", "piege.html"),
        ("image/png", "piege.svg"),
        ("application/json", "trace.zip"),
        ("video/mp4", "capture.png"),
    ],
)
def test_a_declared_type_contradicting_the_extension_is_downgraded(
    declared, original_name
):
    """Un désaccord nom/type est suspect : le serveur ne tranche jamais en faveur de l'aperçu."""

    assert safe_content_type(declared, original_name) == (
        "application/octet-stream",
        False,
    )


def test_an_extension_alone_never_promotes_a_dangerous_type():
    assert safe_content_type("application/octet-stream", "rapport.html") == (
        "application/octet-stream",
        False,
    )
    assert safe_content_type("application/octet-stream", "capture.png") == (
        "image/png",
        True,
    )


# --- Liste et détail (RBAC) -----------------------------------------------------


def test_the_library_lists_only_artifacts_of_accessible_projects(context):
    mine = _seed_artifact(context, payload=b"a")
    foreign = _seed_artifact(
        context,
        payload=b"b",
        project_id=context.other_project_id,
        task_run_id=context.other_run_id,
    )

    response = context.client.get("/artifacts")

    assert response.status_code == 200
    body = response.json()
    identifiers = [item["id"] for item in body["items"]]
    assert mine in identifiers
    assert foreign not in identifiers


def test_a_client_project_filter_never_widens_the_scope(context):
    foreign = _seed_artifact(
        context,
        payload=b"b",
        project_id=context.other_project_id,
        task_run_id=context.other_run_id,
    )

    response = context.client.get(
        "/artifacts", params={"project_id": context.other_project_id}
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert foreign


def test_the_library_pages_with_an_opaque_cursor(context):
    base = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    identifiers = [
        _seed_artifact(
            context,
            payload=f"contenu {index}".encode(),
            created_at=base + timedelta(minutes=index),
        )
        for index in range(3)
    ]

    first = context.client.get("/artifacts", params={"limit": 2})
    assert first.status_code == 200
    first_body = first.json()
    assert [item["id"] for item in first_body["items"]] == [
        identifiers[2],
        identifiers[1],
    ]
    assert first_body["next_cursor"]

    second = context.client.get(
        "/artifacts", params={"limit": 2, "cursor": first_body["next_cursor"]}
    )
    assert second.status_code == 200
    second_body = second.json()
    assert [item["id"] for item in second_body["items"]] == [identifiers[0]]
    assert second_body["next_cursor"] is None


def test_an_unreadable_cursor_is_refused_without_leaking_the_page(context):
    _seed_artifact(context)

    response = context.client.get("/artifacts", params={"cursor": "n'importe quoi"})

    assert response.status_code == 400
    assert "curseur" in response.json()["detail"].lower()


def test_the_summary_never_exposes_the_storage_key(context):
    artifact_id = _seed_artifact(context, original_name="capture.png")

    response = context.client.get(f"/artifacts/{artifact_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["has_content"] is True
    assert "storage_key" not in body
    assert "path" not in body


def test_the_detail_of_a_foreign_artifact_is_not_found(context):
    foreign = _seed_artifact(
        context,
        project_id=context.other_project_id,
        task_run_id=context.other_run_id,
    )

    response = context.client.get(f"/artifacts/{foreign}")

    assert response.status_code == 404


# --- Contenu : en-têtes, aperçu, Range ------------------------------------------


def test_session_content_carries_every_security_header_and_is_an_attachment(context):
    artifact_id = _seed_artifact(
        context, payload=b"journal", content_type="text/plain", original_name="j.txt"
    )

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 200
    assert response.content == b"journal"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"].startswith("attachment")


def test_an_html_artifact_is_forced_to_download(context):
    artifact_id = _seed_artifact(
        context,
        payload=b"<script>alert(1)</script>",
        content_type="text/html",
        original_name="rapport.html",
    )

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment")
    assert "rapport.html" in response.headers["content-disposition"]


def test_an_svg_artifact_is_forced_to_download(context):
    artifact_id = _seed_artifact(
        context,
        payload=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
        content_type="image/svg+xml",
        original_name="schema.svg",
    )

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment")


@pytest.mark.parametrize(
    ("content_type", "original_name", "payload"),
    [
        ("text/html", "piege.png", b"<html><script>alert(1)</script></html>"),
        ("application/zip", "trace.txt", b"PK\x03\x04 archive"),
        ("image/svg+xml", "schema.png", b"<svg onload='alert(1)'></svg>"),
    ],
)
def test_a_dangerous_type_hidden_behind_a_previewable_name_is_forced_to_download(
    context, content_type, original_name, payload
):
    """Le nom d'origine ne réhabilite jamais un type « jamais en ligne » (§7)."""

    artifact_id = _seed_artifact(
        context,
        payload=payload,
        content_type=content_type,
        original_name=original_name,
    )

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment")


def test_a_hostile_file_name_never_reaches_the_disposition_header(context):
    artifact_id = _seed_artifact(
        context,
        payload=b"x",
        original_name='../../etc/passwd"\r\nSet-Cookie: a=b',
    )

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    # Ni injection d'en-tête (CRLF), ni sortie du nom cité, ni trace de chemin.
    assert "\r" not in disposition and "\n" not in disposition
    assert ".." not in disposition
    assert "/" not in disposition and "\\" not in disposition
    assert disposition.count('"') == 2
    assert disposition.startswith("attachment")


def test_a_range_request_returns_the_requested_slice(context):
    artifact_id = _seed_artifact(context, payload=b"0123456789")

    response = context.client.get(
        f"/artifacts/{artifact_id}/content", headers={"Range": "bytes=2-5"}
    )

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-length"] == "4"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_an_open_ended_range_runs_to_the_last_byte(context):
    artifact_id = _seed_artifact(context, payload=b"0123456789")

    response = context.client.get(
        f"/artifacts/{artifact_id}/content", headers={"Range": "bytes=7-"}
    )

    assert response.status_code == 206
    assert response.content == b"789"
    assert response.headers["content-range"] == "bytes 7-9/10"


def test_a_suffix_range_returns_the_tail(context):
    artifact_id = _seed_artifact(context, payload=b"0123456789")

    response = context.client.get(
        f"/artifacts/{artifact_id}/content", headers={"Range": "bytes=-3"}
    )

    assert response.status_code == 206
    assert response.content == b"789"
    assert response.headers["content-range"] == "bytes 7-9/10"


def test_an_unsatisfiable_range_is_refused_with_the_total_size(context):
    artifact_id = _seed_artifact(context, payload=b"0123456789")

    response = context.client.get(
        f"/artifacts/{artifact_id}/content", headers={"Range": "bytes=50-60"}
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"


@pytest.mark.parametrize(
    "header",
    [
        "bytes=0-" + "9" * 4400,
        "bytes=" + "9" * 4400 + "-",
        "bytes=-" + "9" * 4400,
    ],
)
def test_an_absurdly_long_range_is_ignored_instead_of_failing(context, header):
    """Un ``Range`` de plus de 4300 chiffres n'est pas une erreur serveur.

    CPython refuse de convertir un entier aussi long : sans borne sur le motif, la
    conversion levait un ``ValueError`` non intercepté, donc un 500 sur une route
    authentifiée. La RFC 9110 demande d'ignorer un ``Range`` illisible.
    """

    artifact_id = _seed_artifact(context, payload=b"0123456789")

    response = context.client.get(
        f"/artifacts/{artifact_id}/content", headers={"Range": header}
    )

    assert response.status_code == 200
    assert response.content == b"0123456789"


def test_an_unsupported_range_unit_serves_the_whole_content(context):
    artifact_id = _seed_artifact(context, payload=b"0123456789")

    response = context.client.get(
        f"/artifacts/{artifact_id}/content", headers={"Range": "items=0-1"}
    )

    assert response.status_code == 200
    assert response.content == b"0123456789"


def test_the_content_of_a_foreign_artifact_is_not_found(context):
    foreign = _seed_artifact(
        context,
        project_id=context.other_project_id,
        task_run_id=context.other_run_id,
    )

    response = context.client.get(f"/artifacts/{foreign}/content")

    assert response.status_code == 404


def test_an_artifact_without_content_has_no_download(context):
    artifact_id = _seed_artifact(context, payload=None)

    detail = context.client.get(f"/artifacts/{artifact_id}")
    assert detail.status_code == 200
    assert detail.json()["has_content"] is False

    response = context.client.get(f"/artifacts/{artifact_id}/content")
    assert response.status_code == 404


def test_a_purged_artifact_answers_gone_instead_of_a_blank_file(context):
    artifact_id = _seed_artifact(
        context, payload=b"x", deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 410
    assert "rétention" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "storage_key",
    [
        "../../etc/passwd",
        "..\\..\\windows\\win.ini",
        "/etc/shadow",
        "ab/" + "c" * 64,
        "zz/" + "0" * 64,
    ],
)
def test_a_storage_key_outside_the_content_addressing_is_never_opened(
    context, storage_key
):
    """Même une ligne corrompue ne fait pas sortir la lecture de l'arbre des blobs."""

    artifact_id = _seed_artifact(context, payload=b"x")
    with context.session_factory() as db:
        artifact = db.get(ArtifactModel, artifact_id)
        artifact.storage_key = storage_key
        db.commit()

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 404


def test_the_page_size_is_bounded(context):
    assert context.client.get("/artifacts", params={"limit": 500}).status_code == 422
    assert context.client.get("/artifacts", params={"limit": 0}).status_code == 422
    assert context.client.get("/artifacts", params={"limit": 200}).status_code == 200


def test_an_anonymous_download_is_refused(context):
    artifact_id = _seed_artifact(context)
    context.client.cookies.clear()

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 401


# --- Téléversement worker (§6) --------------------------------------------------


def _upload(
    context: Context,
    *,
    payload: bytes = b"rapport",
    file_name: str = "rapport.txt",
    content_type: str = "text/plain",
    kind: str = "report",
    stream_kind: str = "report",
    task_run_id: str | None = None,
    project_id: str | None = None,
    original_name: str | None = None,
    token: str | None = None,
    extra: dict[str, str] | None = None,
):
    data = {
        "kind": kind,
        "stream_kind": stream_kind,
        "task_run_id": task_run_id or context.run_id,
        "project_id": project_id or context.project_id,
    }
    if original_name is not None:
        data["original_name"] = original_name
    if extra:
        data.update(extra)
    return context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={"Authorization": f"Bearer {token or context.worker_token}"},
        files={"file": (file_name, payload, content_type)},
        data=data,
    )


def _glb_from_json(
    raw_json: bytes,
    *,
    version: int = 2,
    binary: bytes | None = None,
    first_chunk_type: bytes = b"JSON",
) -> bytes:
    """Construit un conteneur GLB minimal, y compris avec un JSON volontairement faux."""

    json_chunk = raw_json + (b" " * (-len(raw_json) % 4))
    chunks = [struct.pack("<I4s", len(json_chunk), first_chunk_type), json_chunk]
    if binary is not None:
        binary_chunk = binary + (b"\x00" * (-len(binary) % 4))
        chunks.extend(
            [struct.pack("<I4s", len(binary_chunk), b"BIN\x00"), binary_chunk]
        )
    body = b"".join(chunks)
    return struct.pack("<4sII", b"glTF", version, 12 + len(body)) + body


def _glb(document: dict, *, binary: bytes | None = None) -> bytes:
    return _glb_from_json(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        binary=binary,
    )


def _png(width: int = 1, height: int = 1) -> bytes:
    """Petit PNG RGBA réel ; les grandes dimensions servent aux tests de bombes."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind)
        checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    # Un scanline transparent. Pour les dimensions adversariales, le parseur doit
    # refuser le budget annoncé avant qu'un décodeur tente de gonfler IDAT.
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


ONE_PIXEL_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYI"
    "DAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkF"
    "BQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
    "FBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQF"
    "BgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEI"
    "I0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNk"
    "ZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLD"
    "xMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEB"
    "AQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJB"
    "UQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZH"
    "SElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaan"
    "qKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oA"
    "DAMBAAIRAxEAPwD50ooor8MP9Uz/2Q=="
)
ONE_PIXEL_WEBP = base64.b64decode(
    "UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v89"
)


def _webp(*chunks: tuple[bytes, bytes]) -> bytes:
    body = b"".join(
        kind
        + struct.pack("<I", len(payload))
        + payload
        + (b"\x00" if len(payload) & 1 else b"")
        for kind, payload in chunks
    )
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + body


def _vp8_frame_header(width: int, height: int) -> bytes:
    return (
        b"\x00\x00\x00\x9d\x01\x2a"
        + struct.pack("<H", width)
        + struct.pack("<H", height)
    )


def _upload_glb_document(context: Context, document: dict, *, binary=None):
    return _upload(
        context,
        payload=_glb(document, binary=binary),
        file_name="ressource.glb",
        content_type="model/gltf-binary",
    )


def _blob_files(context: Context) -> list[str]:
    """Tous les fichiers réellement présents sous la racine de stockage."""

    root = context.storage.root
    if not root.exists():
        return []
    return sorted(
        str(path.relative_to(root)).replace("\\", "/")
        for path in root.rglob("*")
        if path.is_file()
    )


def test_a_worker_uploads_content_and_receives_a_summary(context):
    response = _upload(context, payload=b"rapport complet")

    assert response.status_code == 201
    body = response.json()
    assert body["has_content"] is True
    assert body["size_bytes"] == len(b"rapport complet")
    assert body["checksum"] == hashlib.sha256(b"rapport complet").hexdigest()
    assert body["stream_kind"] == "report"
    assert body["content_type"] == "text/plain"
    assert "storage_key" not in body

    download = context.client.get(f"/artifacts/{body['id']}/content")
    assert download.status_code == 200
    assert download.content == b"rapport complet"


def test_a_valid_self_contained_glb_is_previewable_only_on_the_dedicated_origin(
    signed, monkeypatch
):
    monkeypatch.setenv("ACP_API_URL", "https://api.exemple.fr")
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://apercu.exemple.fr")
    png_data_uri = base64.b64encode(_png()).decode("ascii")
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": f"data:image/png;base64,{png_data_uri}"}],
            "buffers": [{"byteLength": 4}],
        },
        binary=b"mesh",
    )

    created = _upload(
        signed,
        payload=payload,
        file_name="scene.glb",
        content_type="model/gltf-binary",
        kind="model_3d",
        stream_kind="model",
    )

    assert created.status_code == 201
    artifact_id = created.json()["id"]

    control_response = signed.client.get(f"/artifacts/{artifact_id}/content")
    assert control_response.status_code == 200
    assert control_response.content == payload
    assert control_response.headers["content-disposition"].startswith("attachment")

    preview_url = _create_link(signed, artifact_id, purpose="preview").json()["url"]
    signed.client.cookies.clear()
    response = signed.client.get(preview_url)
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-type"] == "model/gltf-binary"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["accept-ranges"] == "bytes"

    partial = signed.client.get(preview_url, headers={"Range": "bytes=0-11"})
    assert partial.status_code == 206
    assert partial.content == payload[:12]
    assert partial.headers["content-range"] == f"bytes 0-11/{len(payload)}"
    assert partial.headers["content-length"] == "12"
    assert partial.headers["content-type"] == "model/gltf-binary"
    assert partial.headers["content-disposition"].startswith("inline")
    assert partial.headers["x-content-type-options"] == "nosniff"


def test_a_historical_glb_without_a_validation_seal_stays_a_download(context):
    payload = _glb({"asset": {"version": "2.0"}})
    artifact_id = _seed_artifact(
        context,
        payload=payload,
        content_type="model/gltf-binary",
        original_name="ancien.glb",
    )

    response = context.client.get(f"/artifacts/{artifact_id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment")
    summary = context.client.get(f"/artifacts/{artifact_id}")
    assert summary.status_code == 200
    assert summary.json()["content_type"] == "application/octet-stream"


@pytest.mark.parametrize(
    ("content_type", "file_name", "payload"),
    [
        ("model/gltf-binary", "scene.gltf", _glb({"asset": {"version": "2.0"}})),
        ("model/gltf-binary", "scene.png", _glb({"asset": {"version": "2.0"}})),
        ("application/octet-stream", "scene.glb", b"contenu non verifie"),
        ("application/x-modele", "scene.glb", b"contenu inconnu"),
        ("model/gltf+json", "scene.gltf", b'{"asset":{"version":"2.0"}}'),
    ],
)
def test_a_misleading_or_unsupported_model_declaration_stays_a_download(
    context, content_type, file_name, payload
):
    created = _upload(
        context,
        payload=payload,
        file_name=file_name,
        content_type=content_type,
        kind="model_3d",
    )

    assert created.status_code == 201
    response = context.client.get(f"/artifacts/{created.json()['id']}/content")
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment")


def test_a_glb_declaration_with_another_payload_is_refused_as_unsupported_media(context):
    response = _upload(
        context,
        payload=b"ceci n'est pas un GLB",
        file_name="piege.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 415
    assert "signature" in response.json()["detail"].lower()
    assert _blob_files(context) == []


@pytest.mark.parametrize(
    "payload",
    [
        # Signature présente, mais en-tête tronqué.
        b"glTF\x02\x00",
        # Mauvaise version du conteneur.
        _glb_from_json(b'{"asset":{"version":"2.0"}}', version=1),
        # La longueur totale de l'en-tête ne correspond plus au fichier reçu.
        _glb({"asset": {"version": "2.0"}})[:-1],
        # Le premier chunk n'est pas le JSON obligatoire.
        _glb_from_json(b'{"asset":{"version":"2.0"}}', first_chunk_type=b"BIN\x00"),
        # JSON syntaxiquement invalide puis JSON non UTF-8.
        _glb_from_json(b'{"asset":{"version":"2.0"}'),
        _glb_from_json(b'{"asset":{"version":"2.0"},"x":"\xff"}'),
    ],
)
def test_a_structurally_invalid_glb_is_refused_without_storage(context, payload):
    response = _upload(
        context,
        payload=payload,
        file_name="invalide.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "glb refusé" in response.json()["detail"].lower()
    assert _blob_files(context) == []
    with context.session_factory() as db:
        assert db.query(ArtifactModel).count() == 0


@pytest.mark.parametrize(
    "uri",
    [
        "https://cdn.example/model.bin",
        "//cdn.example/texture.png",
        "textures/albedo.png",
        "file:///etc/passwd",
        "blob:https://example.test/identifier",
    ],
)
def test_a_glb_with_an_external_uri_is_refused(context, uri):
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "extensions": {"VENDOR_nested": {"resource": {"uri": uri}}},
        }
    )

    response = _upload(
        context,
        payload=payload,
        file_name="externe.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "uri externe" in response.json()["detail"].lower()
    assert _blob_files(context) == []


@pytest.mark.parametrize(
    "uri",
    [
        "data:image/svg+xml;base64,PHN2Zy8+",
        "data:text/html;base64,PGgxPnBpZWdlPC9oMT4=",
        "data:image/png,%89PNG",
    ],
)
def test_a_glb_with_an_active_or_non_base64_data_uri_is_refused(context, uri):
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": uri}],
        }
    )

    response = _upload(
        context,
        payload=payload,
        file_name="data-uri.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "data uri" in response.json()["detail"].lower()
    assert _blob_files(context) == []


@pytest.mark.parametrize(
    "payload",
    [
        "%%%%",
        "abc",
    ],
)
def test_a_glb_with_an_invalid_base64_payload_is_refused(context, payload):
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": f"data:application/octet-stream;base64,{payload}"}],
    }

    response = _upload(
        context,
        payload=_glb(document),
        file_name="base64-invalide.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "base64" in response.json()["detail"].lower()
    assert _blob_files(context) == []


@pytest.mark.parametrize(
    ("media_type", "payload"),
    [
        ("image/png", b"not-png"),
        ("image/jpeg", b"not-jpeg"),
        ("image/webp", b"RIFF\x04\x00\x00\x00NOPE"),
    ],
)
def test_a_glb_data_image_must_match_its_declared_magic(
    context, media_type, payload
):
    encoded = base64.b64encode(payload).decode("ascii")
    document = {
        "asset": {"version": "2.0"},
        "images": [{"uri": f"data:{media_type};base64,{encoded}"}],
    }

    response = _upload(
        context,
        payload=_glb(document),
        file_name="image-incoherente.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "signature" in response.json()["detail"].lower()
    assert _blob_files(context) == []


@pytest.mark.parametrize(
    ("media_type", "payload"),
    [
        ("image/png", _png()),
        ("image/jpeg", ONE_PIXEL_JPEG),
        ("image/webp", ONE_PIXEL_WEBP),
    ],
)
def test_a_glb_data_image_with_a_real_one_pixel_header_is_accepted(
    context, media_type, payload
):
    encoded = base64.b64encode(payload).decode("ascii")
    document = {
        "asset": {"version": "2.0"},
        "images": [{"uri": f"data:{media_type};base64,{encoded}"}],
    }

    response = _upload(
        context,
        payload=_glb(document),
        file_name="image-coherente.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 201
    assert response.json()["content_type"] == "model/gltf-binary"


def test_a_tiny_glb_cannot_declare_an_unbounded_zero_initialized_accessor(context):
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "accessors": [
                {"componentType": 5126, "count": 2**31, "type": "VEC4"}
            ],
        }
    )

    response = _upload(
        context,
        payload=payload,
        file_name="allocation-geante.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "budget de décodage" in response.json()["detail"]
    assert _blob_files(context) == []


def test_a_glb_accessor_must_fit_its_buffer_view(context):
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 4}],
            "bufferViews": [{"buffer": 0, "byteLength": 4}],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": 2,
                    "type": "SCALAR",
                }
            ],
        },
        binary=b"data",
    )

    response = _upload(
        context,
        payload=payload,
        file_name="vue-trop-courte.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "dépasse son bufferview" in response.json()["detail"].lower()
    assert _blob_files(context) == []


def test_a_glb_buffer_length_must_match_its_binary_chunk(context):
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 64}],
        },
        binary=b"data",
    )

    response = _upload(
        context,
        payload=payload,
        file_name="buffer-incoherent.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "chunk bin" in response.json()["detail"].lower()
    assert _blob_files(context) == []


def test_a_bounded_accessor_that_fits_its_buffer_is_previewable(context):
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 8}],
            "bufferViews": [{"buffer": 0, "byteLength": 8}],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": 2,
                    "type": "SCALAR",
                }
            ],
        },
        binary=b"12345678",
    )

    response = _upload(
        context,
        payload=payload,
        file_name="accessor-borne.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 201
    assert response.json()["content_type"] == "model/gltf-binary"


def test_overlapping_buffer_views_are_each_charged_to_the_cumulative_budget(
    context, monkeypatch
):
    monkeypatch.setattr(artifacts_router, "GLB_MAX_BUFFER_VIEW_BYTES", 7)
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 4}],
            "bufferViews": [
                {"buffer": 0, "byteLength": 4},
                {"buffer": 0, "byteLength": 4},
            ],
        },
        binary=b"data",
    )

    assert response.status_code == 422
    assert "bufferviews" in response.json()["detail"].lower()
    assert "budget cumulé" in response.json()["detail"].lower()


def test_a_strided_accessor_is_charged_for_its_physical_span(context, monkeypatch):
    monkeypatch.setattr(artifacts_router, "GLB_MAX_PHYSICAL_ACCESSOR_BYTES", 8)
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 12}],
            "bufferViews": [{"buffer": 0, "byteLength": 12, "byteStride": 8}],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": 2,
                    "type": "SCALAR",
                }
            ],
        },
        binary=b"0123456789ab",
    )

    assert response.status_code == 422
    assert "budget physique cumulé" in response.json()["detail"].lower()


def test_overlapping_accessors_cannot_share_the_physical_budget(context, monkeypatch):
    monkeypatch.setattr(artifacts_router, "GLB_MAX_PHYSICAL_ACCESSOR_BYTES", 16)
    accessor = {
        "bufferView": 0,
        "componentType": 5126,
        "count": 2,
        "type": "SCALAR",
    }
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 12}],
            "bufferViews": [{"buffer": 0, "byteLength": 12, "byteStride": 8}],
            "accessors": [accessor, dict(accessor)],
        },
        binary=b"0123456789ab",
    )

    assert response.status_code == 422
    assert "budget physique cumulé" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "image",
    [
        {},
        {
            "uri": "data:image/png;base64,"
            + base64.b64encode(_png()).decode("ascii"),
            "bufferView": 0,
        },
    ],
)
def test_an_image_requires_exactly_one_storage_form(context, image):
    document = {"asset": {"version": "2.0"}, "images": [image]}
    if "bufferView" in image:
        document.update(
            {
                "buffers": [{"byteLength": len(_png())}],
                "bufferViews": [{"buffer": 0, "byteLength": len(_png())}],
            }
        )
    response = _upload_glb_document(
        context,
        document,
        binary=_png() if "bufferView" in image else None,
    )

    assert response.status_code == 422
    assert "exactement uri ou bufferview" in response.json()["detail"].lower()


def test_a_buffer_view_png_is_read_from_the_binary_chunk(context):
    image = _png()
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(image)}],
            "bufferViews": [{"buffer": 0, "byteLength": len(image)}],
            "images": [{"bufferView": 0, "mimeType": "image/png"}],
        },
        binary=image,
    )

    assert response.status_code == 201


def test_a_buffer_view_webp_is_read_from_a_data_buffer(context):
    encoded = base64.b64encode(ONE_PIXEL_WEBP).decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [
                {
                    "byteLength": len(ONE_PIXEL_WEBP),
                    "uri": f"data:application/octet-stream;base64,{encoded}",
                }
            ],
            "bufferViews": [{"buffer": 0, "byteLength": len(ONE_PIXEL_WEBP)}],
            "images": [{"bufferView": 0, "mimeType": "image/webp"}],
        },
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    "image",
    [
        {"bufferView": 0},
        {"bufferView": 0, "mimeType": "image/gif"},
    ],
)
def test_a_buffer_view_image_requires_an_allowed_mime_type(context, image):
    png = _png()
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(png)}],
            "bufferViews": [{"buffer": 0, "byteLength": len(png)}],
            "images": [image],
        },
        binary=png,
    )

    assert response.status_code == 422
    assert "mime" in response.json()["detail"].lower()


def test_an_image_mime_type_must_match_its_data_uri(context):
    encoded = base64.b64encode(_png()).decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "images": [
                {
                    "uri": f"data:image/png;base64,{encoded}",
                    "mimeType": "image/jpeg",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "mime" in response.json()["detail"].lower()
    assert "incohérent" in response.json()["detail"].lower()


def test_a_buffer_data_uri_cannot_use_an_image_media_type(context):
    encoded = base64.b64encode(b"data").decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [
                {
                    "byteLength": 4,
                    "uri": f"data:image/png;base64,{encoded}",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "data uri de buffer" in response.json()["detail"].lower()


def test_an_image_dimension_bomb_is_refused_from_its_png_header(context):
    bomb = _png(artifacts_router.GLB_MAX_IMAGE_DIMENSION + 1, 1)
    encoded = base64.b64encode(bomb).decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": f"data:image/png;base64,{encoded}"}],
        },
    )

    assert response.status_code == 422
    assert "dimensions" in response.json()["detail"].lower()


def test_repeated_images_are_each_charged_to_the_pixel_budget(context, monkeypatch):
    monkeypatch.setattr(artifacts_router, "GLB_MAX_IMAGE_BASE_PIXELS", 1)
    encoded = base64.b64encode(_png()).decode("ascii")
    uri = f"data:image/png;base64,{encoded}"
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": uri}, {"uri": uri}],
        },
    )

    assert response.status_code == 422
    assert "budget cumulé de pixels" in response.json()["detail"].lower()


def test_repeated_images_are_each_charged_with_their_mipmaps(context, monkeypatch):
    monkeypatch.setattr(artifacts_router, "GLB_MAX_IMAGE_RGBA_MIP_BYTES", 4)
    encoded = base64.b64encode(_png()).decode("ascii")
    uri = f"data:image/png;base64,{encoded}"
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": uri}, {"uri": uri}],
        },
    )

    assert response.status_code == 422
    assert "budget rgba avec mipmaps" in response.json()["detail"].lower()


def test_a_jpeg_with_an_out_of_bounds_segment_is_refused(context):
    malformed = b"\xff\xd8\xff\xe0\xff\xff" + b"JFIF" + b"\xff\xd9"
    encoded = base64.b64encode(malformed).decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": f"data:image/jpeg;base64,{encoded}"}],
        },
    )

    assert response.status_code == 422
    assert "segment jpeg" in response.json()["detail"].lower()


def test_a_jpeg_with_multiple_frame_headers_is_refused(context):
    def sof(width: int, height: int) -> bytes:
        payload = bytes([8]) + struct.pack(">HHB", height, width, 1) + b"\x01\x11\x00"
        return b"\xff\xc0" + struct.pack(">H", len(payload) + 2) + payload

    malformed = (
        b"\xff\xd8"
        + sof(artifacts_router.GLB_MAX_IMAGE_DIMENSION + 1, 1)
        + sof(1, 1)
        + b"\xff\xda\x00\x02"
        + b"\xff\xd9"
    )
    encoded = base64.b64encode(malformed).decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": f"data:image/jpeg;base64,{encoded}"}],
        },
    )

    assert response.status_code == 422
    assert "un seul sof" in response.json()["detail"].lower()


def test_a_webp_with_multiple_image_frames_is_refused(context):
    payload = _webp(
        (
            b"VP8L",
            b"\x2f"
            + (((8193 - 1) | ((1 - 1) << 14))).to_bytes(4, "little"),
        ),
        (b"VP8 ", _vp8_frame_header(1, 1)),
    )
    encoded = base64.b64encode(payload).decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": f"data:image/webp;base64,{encoded}"}],
        },
    )

    assert response.status_code == 422
    assert "une seule trame" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "payload",
    [
        _webp(
            (
                b"VP8L",
                b"\x2f"
                + (((8193 - 1) | ((1 - 1) << 14))).to_bytes(4, "little"),
            )
        ),
        _webp(
            (
                b"VP8X",
                b"\x00\x00\x00\x00"
                + (8193 - 1).to_bytes(3, "little")
                + (1 - 1).to_bytes(3, "little"),
            ),
            (b"VP8 ", _vp8_frame_header(8193, 1)),
        ),
    ],
)
def test_webp_variants_expose_dimensions_before_decode(context, payload):
    encoded = base64.b64encode(payload).decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "images": [{"uri": f"data:image/webp;base64,{encoded}"}],
        },
    )

    assert response.status_code == 422
    assert "dimensions" in response.json()["detail"].lower()


def test_accessor_alignment_uses_the_absolute_buffer_offset(context):
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 4}],
            "bufferViews": [{"buffer": 0, "byteOffset": 1, "byteLength": 3}],
            "accessors": [
                {
                    "bufferView": 0,
                    "byteOffset": 1,
                    "componentType": 5123,
                    "count": 1,
                    "type": "SCALAR",
                }
            ],
        },
        binary=b"data",
    )

    assert response.status_code == 201


def test_a_locally_aligned_accessor_with_an_unaligned_absolute_offset_is_refused(
    context,
):
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 4}],
            "bufferViews": [{"buffer": 0, "byteOffset": 1, "byteLength": 2}],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5123,
                    "count": 1,
                    "type": "SCALAR",
                }
            ],
        },
        binary=b"data",
    )

    assert response.status_code == 422
    assert "aligné" in response.json()["detail"].lower()


def test_a_buffer_view_stride_must_be_a_multiple_of_four(context):
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 6}],
            "bufferViews": [{"buffer": 0, "byteLength": 6, "byteStride": 6}],
        },
        binary=b"123456",
    )

    assert response.status_code == 422
    assert "multiple de 4" in response.json()["detail"].lower()


def test_sparse_accessors_are_refused_fail_closed(context):
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "accessors": [
                {
                    "componentType": 5126,
                    "count": 1,
                    "type": "SCALAR",
                    "sparse": {
                        "count": 1,
                        "indices": {"bufferView": 0, "componentType": 5121},
                        "values": {"bufferView": 1},
                    },
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "sparse" in response.json()["detail"].lower()
    assert "pas pris en charge" in response.json()["detail"].lower()


def test_only_buffer_zero_can_map_the_binary_chunk(context):
    encoded = base64.b64encode(b"zero").decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [
                {
                    "byteLength": 4,
                    "uri": f"data:application/octet-stream;base64,{encoded}",
                },
                {"byteLength": 4},
            ],
        },
        binary=b"data",
    )

    assert response.status_code == 422
    assert "seul buffers[0]" in response.json()["detail"].lower()


def test_an_unmapped_binary_chunk_is_refused(context):
    encoded = base64.b64encode(b"data").decode("ascii")
    response = _upload_glb_document(
        context,
        {
            "asset": {"version": "2.0"},
            "buffers": [
                {
                    "byteLength": 4,
                    "uri": f"data:application/octet-stream;base64,{encoded}",
                }
            ],
        },
        binary=b"junk",
    )

    assert response.status_code == 422
    assert "chunk bin" in response.json()["detail"].lower()
    assert "pas référencé" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "extension",
    [
        "KHR_draco_mesh_compression",
        "EXT_meshopt_compression",
        "KHR_texture_basisu",
    ],
)
def test_a_glb_requiring_an_external_decoder_is_refused(context, extension):
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "extensionsUsed": [extension],
            "extensionsRequired": [extension],
            "meshes": [{"extensions": {extension: {}}}],
        }
    )

    response = _upload(
        context,
        payload=payload,
        file_name="decodeur.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert extension in response.json()["detail"]
    assert "décodeur externe" in response.json()["detail"].lower()
    assert _blob_files(context) == []


def test_an_undeclared_external_decoder_block_cannot_bypass_validation(context):
    payload = _glb(
        {
            "asset": {"version": "2.0"},
            "meshes": [
                {"extensions": {"KHR_draco_mesh_compression": {"bufferView": 0}}}
            ],
        },
        binary=b"mesh",
    )

    response = _upload(
        context,
        payload=payload,
        file_name="decodeur-cache.glb",
        content_type="model/gltf-binary",
    )

    assert response.status_code == 422
    assert "KHR_draco_mesh_compression" in response.json()["detail"]
    assert _blob_files(context) == []


def test_re_uploading_the_same_content_on_the_same_run_is_idempotent(context):
    first = _upload(context, payload=b"identique")
    second = _upload(context, payload=b"identique")

    assert first.status_code == 201
    assert second.status_code in (200, 201)
    assert second.json()["id"] == first.json()["id"]

    listing = context.client.get("/artifacts", params={"task_run_id": context.run_id})
    assert len(listing.json()["items"]) == 1
    assert len(_blob_files(context)) == 1


def test_reupload_repairs_a_metadata_only_artifact_instead_of_returning_it_empty(context):
    payload = b"contenu repare"
    checksum = hashlib.sha256(payload).hexdigest()
    with context.session_factory() as db:
        artifact = ArtifactModel(
            project_id=context.project_id,
            task_run_id=context.run_id,
            worker_id=context.worker_id,
            kind="report",
            path="ancien/rapport.txt",
            checksum=checksum,
            size_bytes=len(payload),
            metadata_json={},
            storage_key=None,
            content_type="text/plain",
            original_name="rapport.txt",
            source="worker",
            stream_kind="report",
        )
        db.add(artifact)
        db.commit()
        artifact_id = artifact.id

    response = _upload(context, payload=payload)

    assert response.status_code in (200, 201)
    assert response.json()["id"] == artifact_id
    assert response.json()["has_content"] is True
    download = context.client.get(f"/artifacts/{artifact_id}/content")
    assert download.status_code == 200
    assert download.content == payload


def test_reupload_repairs_a_missing_or_corrupt_blob(context):
    payload = b"contenu adresse"
    first = _upload(context, payload=payload)
    artifact_id = first.json()["id"]
    with context.session_factory() as db:
        artifact = db.get(ArtifactModel, artifact_id)
        assert artifact is not None and artifact.storage_key is not None
        blob_path = context.storage.root / artifact.storage_key
    blob_path.write_bytes(b"corrompu")

    repaired = _upload(context, payload=payload)

    assert repaired.status_code in (200, 201)
    assert repaired.json()["id"] == artifact_id
    assert blob_path.read_bytes() == payload
    assert context.client.get(f"/artifacts/{artifact_id}/content").content == payload


def test_the_same_content_on_another_run_stays_a_distinct_artifact(context):
    with context.session_factory() as db:
        second_run, second_task = _run(db, context.project_id)
        _lease(db, context.worker_id, second_task, second_run)
        db.commit()

    first = _upload(context, payload=b"partage")
    second = _upload(context, payload=b"partage", task_run_id=second_run)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["checksum"] == second.json()["checksum"]
    # Adressage par contenu : un seul blob pour deux livrables.
    assert len(_blob_files(context)) == 1


def test_the_client_never_chooses_the_checksum(context):
    response = _upload(
        context,
        payload="vérité".encode(),
        extra={"sha256": "0" * 64, "checksum": "0" * 64, "size_bytes": "999"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["checksum"] == hashlib.sha256("vérité".encode()).hexdigest()
    assert body["size_bytes"] == len("vérité".encode())


def test_the_original_name_never_reaches_the_storage_path(context):
    response = _upload(
        context,
        payload=b"charge",
        file_name="../../evasion.bin",
        original_name="../../evasion.bin",
    )

    assert response.status_code == 201
    digest = hashlib.sha256(b"charge").hexdigest()
    assert _blob_files(context) == [f"{digest[:2]}/{digest}"]
    assert response.json()["original_name"] == "../../evasion.bin"


def test_a_file_over_the_per_file_cap_is_refused_without_residue(context, monkeypatch):
    monkeypatch.setenv("ACP_ARTIFACT_MAX_BYTES", "16")

    response = _upload(context, payload=b"x" * 4096)

    assert response.status_code == 413
    assert "taille" in response.json()["detail"].lower()
    assert _blob_files(context) == []
    with context.session_factory() as db:
        assert db.query(ArtifactModel).count() == 0


def test_the_run_quota_is_enforced_during_the_stream(context, monkeypatch):
    monkeypatch.setenv("ACP_ARTIFACT_MAX_BYTES_PER_RUN", "24")

    accepted = _upload(context, payload=b"a" * 16)
    refused = _upload(context, payload=b"b" * 16)

    assert accepted.status_code == 201
    assert refused.status_code == 413
    assert "quota" in refused.json()["detail"].lower()
    # Seul le premier livrable existe : le refus n'a laissé ni blob ni ligne.
    assert len(_blob_files(context)) == 1
    with context.session_factory() as db:
        assert db.query(ArtifactModel).count() == 1


def test_an_exhausted_quota_refuses_the_next_upload(context, monkeypatch):
    monkeypatch.setenv("ACP_ARTIFACT_MAX_BYTES_PER_RUN", "8")
    assert _upload(context, payload=b"a" * 8).status_code == 201

    refused = _upload(context, payload=b"b")

    assert refused.status_code == 413
    assert "quota" in refused.json()["detail"].lower()


def test_an_idempotent_reupload_survives_an_exhausted_quota(context, monkeypatch):
    monkeypatch.setenv("ACP_ARTIFACT_MAX_BYTES_PER_RUN", "8")
    first = _upload(context, payload=b"same-8!!")
    replay = _upload(context, payload=b"same-8!!")

    assert first.status_code == 201
    assert replay.status_code in (200, 201)
    assert replay.json()["id"] == first.json()["id"]
    with context.session_factory() as db:
        assert db.query(ArtifactModel).filter_by(task_run_id=context.run_id).count() == 1


@pytest.mark.parametrize(
    "error,status,kind",
    [
        (ArtifactStorageFull("full"), 507, "storage.saturated"),
        (ArtifactStorageUnavailable("offline"), 503, "storage.unavailable"),
    ],
)
def test_a_physical_storage_failure_is_explicit_deduplicated_and_audited(
    context, monkeypatch, error, status, kind
):
    class FailingStorage:
        def write(self, stream, *, max_bytes):
            raise error

    monkeypatch.setattr(
        "acp_api.routers.artifacts.artifact_storage", lambda: FailingStorage()
    )

    first = _upload(context, payload=b"premier")
    second = _upload(context, payload=b"second")

    assert first.status_code == status
    assert second.status_code == status
    assert "full" not in first.text
    assert _blob_files(context) == []
    with context.session_factory() as db:
        alerts = db.query(AlertModel).filter_by(kind=kind).all()
        assert len(alerts) == 1
        assert alerts[0].severity == "critical"
        assert db.query(ArtifactModel).count() == 0
        events = db.query(EventModel).filter_by(type="alert.opened").all()
        assert len(events) == 1
        assert str(context.storage.root) not in str(events[0].payload)


def test_a_full_multipart_spool_returns_507_and_opens_an_alert(context, monkeypatch):
    class FullSpool:
        def __init__(self, *args, **kwargs):
            self._delegate = tempfile.TemporaryFile()

        def write(self, chunk):
            raise OSError(errno.ENOSPC, "temporary volume full")

        def close(self):
            self._delegate.close()

    monkeypatch.setattr(
        "acp_api.routers.artifacts.tempfile.SpooledTemporaryFile", FullSpool
    )

    response = _upload(context, payload=b"x" * 4096)

    assert response.status_code == 507
    with context.session_factory() as db:
        assert db.query(ArtifactModel).count() == 0
        assert db.query(AlertModel).filter_by(kind="storage.saturated").count() == 1


def test_an_upload_without_an_attempt_fence_is_refused_before_storage(context):
    fence = context.client.headers.pop("X-Attempt-Fencing-Token")
    try:
        response = _upload(context)
    finally:
        context.client.headers["X-Attempt-Fencing-Token"] = fence

    assert response.status_code == 409
    assert _blob_files(context) == []
    with context.session_factory() as db:
        assert db.query(ArtifactModel).count() == 0


@pytest.mark.parametrize("fence", ["0", "-1", "abc", "2", "01"])
def test_an_invalid_or_stale_attempt_fence_is_refused_before_storage(context, fence):
    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "X-Attempt-Fencing-Token": fence,
        },
        files={"file": ("rapport.txt", b"rapport", "text/plain")},
        data={
            "kind": "report",
            "task_run_id": context.run_id,
            "project_id": context.project_id,
        },
    )

    assert response.status_code == 409
    assert _blob_files(context) == []
    with context.session_factory() as db:
        assert db.query(ArtifactModel).count() == 0


def test_a_fence_rotated_while_the_body_is_read_is_rechecked_before_storage(
    context, monkeypatch
):
    original_lock = artifacts_router._lock_artifact_quota

    def rotate_fence_after_body(db: Session, run_id: str) -> None:
        original_lock(db, run_id)
        db.query(TaskRunModel).filter_by(id=run_id).update(
            {TaskRunModel.fencing_token: TaskRunModel.fencing_token + 1},
            synchronize_session=False,
        )
        db.flush()

    monkeypatch.setattr(artifacts_router, "_lock_artifact_quota", rotate_fence_after_body)

    response = _upload(context, payload=b"arrive trop tard")

    assert response.status_code == 409
    assert _blob_files(context) == []
    with context.session_factory() as db:
        assert db.query(ArtifactModel).count() == 0


def test_an_upload_without_an_active_lease_is_refused(context):
    response = _upload(context, task_run_id=context.other_run_id)

    assert response.status_code == 409
    assert _blob_files(context) == []


def test_an_upload_declaring_another_project_is_refused(context):
    response = _upload(context, project_id=context.other_project_id)

    assert response.status_code == 400
    assert _blob_files(context) == []


def test_an_upload_without_a_worker_token_is_refused(context):
    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        files={"file": ("x.txt", b"x", "text/plain")},
        data={
            "kind": "report",
            "task_run_id": context.run_id,
            "project_id": context.project_id,
        },
    )

    assert response.status_code == 401
    assert _blob_files(context) == []


def test_a_body_that_is_not_multipart_is_refused(context):
    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "Content-Type": "application/json",
        },
        content=b'{"kind": "report"}',
    )

    assert response.status_code == 415


def test_an_upload_without_a_file_part_is_refused(context):
    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={"Authorization": f"Bearer {context.worker_token}"},
        files={"autre": ("x.txt", b"x", "text/plain")},
        data={
            "kind": "report",
            "task_run_id": context.run_id,
            "project_id": context.project_id,
        },
    )

    assert response.status_code == 422
    assert _blob_files(context) == []


def _raw_multipart(parts: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    """Corps multipart écrit à la main : l'ordre des parties est celui demandé."""

    boundary = "----acp-test-boundary"
    chunks: list[bytes] = []
    for name, file_name, value in parts:
        disposition = f'form-data; name="{name}"'
        if file_name:
            disposition += f'; filename="{file_name}"'
        chunks.append(f"--{boundary}\r\nContent-Disposition: {disposition}\r\n".encode())
        if file_name:
            chunks.append(b"Content-Type: application/octet-stream\r\n")
        chunks.append(b"\r\n")
        chunks.append(value)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def test_a_file_part_sent_before_the_fields_is_still_accepted(context):
    """L'ordre des parties appartient au client : la validation ne doit pas en dépendre."""

    body, content_type = _raw_multipart(
        [
            ("file", "rapport.txt", b"ordre inverse"),
            ("kind", "", b"report"),
            ("stream_kind", "", b"report"),
            ("task_run_id", "", context.run_id.encode()),
            ("project_id", "", context.project_id.encode()),
        ]
    )

    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "Content-Type": content_type,
        },
        content=body,
    )

    assert response.status_code == 201
    assert response.json()["checksum"] == hashlib.sha256(b"ordre inverse").hexdigest()


def test_a_file_sent_before_the_fields_still_obeys_the_run_quota(context, monkeypatch):
    monkeypatch.setenv("ACP_ARTIFACT_MAX_BYTES_PER_RUN", "8")
    assert _upload(context, payload=b"a" * 8).status_code == 201

    body, content_type = _raw_multipart(
        [
            ("file", "rapport.txt", b"trop tard"),
            ("kind", "", b"report"),
            ("task_run_id", "", context.run_id.encode()),
            ("project_id", "", context.project_id.encode()),
        ]
    )
    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "Content-Type": content_type,
        },
        content=body,
    )

    assert response.status_code == 413
    assert "quota" in response.json()["detail"].lower()
    assert len(_blob_files(context)) == 1


def test_a_file_sent_before_the_fields_still_needs_an_active_lease(context):
    body, content_type = _raw_multipart(
        [
            ("file", "rapport.txt", b"sans lease"),
            ("kind", "", b"report"),
            ("task_run_id", "", context.other_run_id.encode()),
            ("project_id", "", context.other_project_id.encode()),
        ]
    )

    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "Content-Type": content_type,
        },
        content=body,
    )

    assert response.status_code == 409
    assert _blob_files(context) == []


def test_a_semicolon_in_a_filename_never_rebinds_the_field_name(context):
    """Un « ; » cité appartient au nom de fichier : il ne renomme pas la partie."""

    body, content_type = _raw_multipart(
        [
            ("autre", "x;name=file", b"pas la piece"),
            ("kind", "", b"report"),
            ("task_run_id", "", context.run_id.encode()),
            ("project_id", "", context.project_id.encode()),
        ]
    )

    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "Content-Type": content_type,
        },
        content=body,
    )

    assert response.status_code == 422
    assert "file" in response.json()["detail"]
    assert _blob_files(context) == []


def test_a_filename_containing_a_semicolon_is_preserved(context):
    """Une capture Playwright nommée « a;b.png » garde son nom entier."""

    body, content_type = _raw_multipart(
        [
            ("kind", "", b"report"),
            ("stream_kind", "", b"report"),
            ("task_run_id", "", context.run_id.encode()),
            ("project_id", "", context.project_id.encode()),
            ("file", "a;b.png", b"capture"),
        ]
    )

    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "Content-Type": content_type,
        },
        content=body,
    )

    assert response.status_code == 201
    assert response.json()["original_name"] == "a;b.png"


def test_a_disposition_with_an_unbalanced_quote_is_refused(context):
    """Un en-tête de partie non analysable est rejeté, jamais deviné."""

    boundary = "----acp-test-boundary"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file; filename="x.txt"\r\n',
            b"Content-Type: application/octet-stream\r\n\r\n",
            b"contenu",
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )

    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        content=body,
    )

    assert response.status_code == 422
    # Le refus vient de l'en-tête illisible, pas d'un champ manquant deviné après coup.
    assert "guillemet" in response.json()["detail"]
    assert _blob_files(context) == []


@pytest.mark.parametrize(
    ("padding", "expected_status"),
    [
        # Le plafond porte sur tout le bloc d'en-têtes, délimiteur exclu : sa
        # valeur exacte est acceptée, le premier octet de trop est refusé.
        (0, 201),
        (1, 422),
    ],
)
def test_multipart_header_limit_applies_when_the_whole_body_is_one_chunk(
    context, padding, expected_status
):
    boundary = "----acp-test-boundary"
    prefix = b'Content-Disposition: form-data; name="file"; filename="x.txt"\r\nX: '
    # ``read_until(b"\r\n\r\n")`` exclut le séparateur entier : le CRLF qui
    # termine le dernier en-tête appartient donc au séparateur, pas au bloc
    # ``raw_headers`` dont on mesure ici exactement la taille.
    fill_size = MULTIPART_HEADERS_MAX_BYTES - len(prefix) + padding
    raw_headers = prefix + (b"a" * fill_size)
    assert len(raw_headers) == MULTIPART_HEADERS_MAX_BYTES + padding
    run_part = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="task_run_id"\r\n\r\n'
        f"{context.run_id}\r\n"
    ).encode()
    project_part = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="project_id"\r\n\r\n'
        f"{context.project_id}\r\n"
    ).encode()
    body = b"".join(
        [
            run_part,
            project_part,
            f"--{boundary}\r\n".encode(),
            raw_headers,
            b"\r\n\r\nx",
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )

    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={
            "Authorization": f"Bearer {context.worker_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        content=body,
    )

    assert response.status_code == expected_status
    if padding:
        assert "hors bornes" in response.json()["detail"]


def test_an_upload_without_a_run_is_refused(context):
    response = context.client.post(
        f"/workers/{context.worker_id}/artifacts/content",
        headers={"Authorization": f"Bearer {context.worker_token}"},
        files={"file": ("x.txt", b"x", "text/plain")},
        data={"kind": "report", "project_id": context.project_id},
    )

    assert response.status_code == 422


# --- Liens signés (§5.3, §6) ----------------------------------------------------

SIGNING_KEY = "cle-de-signature-de-test-avec-assez-d-entropie"
OTHER_KEY = "autre-cle-de-signature-de-test-avec-entropie"


@pytest.fixture
def signed(context, monkeypatch):
    monkeypatch.setenv("ACP_ARTIFACT_SIGNING_KEYS", SIGNING_KEY)
    return context


def _create_link(context: Context, artifact_id: str, **params):
    return context.client.post(f"/artifacts/{artifact_id}/link", params=params)


def test_a_link_is_unavailable_without_a_signing_key(context):
    artifact_id = _seed_artifact(context)

    response = _create_link(context, artifact_id)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "ACP_ARTIFACT_SIGNING_KEYS" in detail
    assert "generate-key" in detail
    # Le téléchargement par session reste possible : la fonctionnalité dégradée
    # n'est que le partage.
    assert context.client.get(f"/artifacts/{artifact_id}/content").status_code == 200


def test_a_signed_link_downloads_without_a_session(signed):
    artifact_id = _seed_artifact(
        signed, payload=b"capture", content_type="image/png", original_name="c.png"
    )
    created = _create_link(signed, artifact_id)
    assert created.status_code == 201
    body = created.json()
    assert body["artifact_id"] == artifact_id
    assert f"/artifacts/{artifact_id}/content" in body["url"]

    token = body["url"].split("token=")[1]
    signed.client.cookies.clear()
    response = signed.client.get(
        f"/artifacts/{artifact_id}/content", params={"token": token}
    )

    assert response.status_code == 200
    assert response.content == b"capture"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["content-disposition"].startswith("attachment")


def test_a_link_never_opens_anything_but_its_artifact(signed):
    artifact_id = _seed_artifact(signed, payload=b"un")
    other_id = _seed_artifact(signed, payload=b"deux")
    token = _create_link(signed, artifact_id).json()["url"].split("token=")[1]
    signed.client.cookies.clear()

    assert (
        signed.client.get(
            f"/artifacts/{other_id}/content", params={"token": token}
        ).status_code
        == 403
    )
    # Le jeton n'ouvre ni la bibliothèque ni les métadonnées.
    assert signed.client.get("/artifacts", params={"token": token}).status_code == 401
    assert (
        signed.client.get(
            f"/artifacts/{artifact_id}", params={"token": token}
        ).status_code
        == 401
    )


def test_an_expired_link_is_refused(signed):
    artifact_id = _seed_artifact(signed)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    token = sign_artifact_token(artifact_id, signed.member_id, past, SIGNING_KEY)
    with signed.session_factory() as db:
        db.add(
            ArtifactLinkModel(
                artifact_id=artifact_id,
                user_id=signed.member_id,
                token_hash=token_hash(token),
                expires_at=past,
            )
        )
        db.commit()
    signed.client.cookies.clear()

    response = signed.client.get(
        f"/artifacts/{artifact_id}/content", params={"token": token}
    )

    assert response.status_code == 403
    assert "expir" in response.json()["detail"].lower()


def test_a_revoked_link_is_refused(signed):
    artifact_id = _seed_artifact(signed)
    created = _create_link(signed, artifact_id).json()
    token = created["url"].split("token=")[1]

    revoked = signed.client.delete(f"/artifacts/links/{created['id']}")
    assert revoked.status_code == 204

    signed.client.cookies.clear()
    response = signed.client.get(
        f"/artifacts/{artifact_id}/content", params={"token": token}
    )

    assert response.status_code == 403
    assert "révoqu" in response.json()["detail"].lower()


def test_a_link_signed_for_another_user_never_verifies(signed):
    """Le jeton ne porte pas l'utilisateur : le serveur le retrouve par la ligne."""

    artifact_id = _seed_artifact(signed)
    token = sign_artifact_token(
        artifact_id,
        signed.stranger_id,
        datetime.now(timezone.utc) + timedelta(minutes=5),
        SIGNING_KEY,
    )
    with signed.session_factory() as db:
        db.add(
            ArtifactLinkModel(
                artifact_id=artifact_id,
                user_id=signed.member_id,
                token_hash=token_hash(token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        db.commit()
    signed.client.cookies.clear()

    response = signed.client.get(
        f"/artifacts/{artifact_id}/content", params={"token": token}
    )

    assert response.status_code == 403


def test_a_link_dies_with_its_holder_access(signed):
    artifact_id = _seed_artifact(signed)
    token = _create_link(signed, artifact_id).json()["url"].split("token=")[1]
    with signed.session_factory() as db:
        db.query(MembershipModel).filter_by(user_id=signed.member_id).delete()
        db.commit()
    signed.client.cookies.clear()

    response = signed.client.get(
        f"/artifacts/{artifact_id}/content", params={"token": token}
    )

    assert response.status_code == 403


def test_a_link_dies_with_its_holder_account(signed):
    artifact_id = _seed_artifact(signed)
    token = _create_link(signed, artifact_id).json()["url"].split("token=")[1]
    with signed.session_factory() as db:
        db.get(UserModel, signed.member_id).is_active = 0
        db.commit()
    signed.client.cookies.clear()

    response = signed.client.get(
        f"/artifacts/{artifact_id}/content", params={"token": token}
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "token",
    [
        "",
        "n'importe quoi",
        "v1.inconnu.1789200000.AAAA",
        "v2.a.1.b",
        "éàü",
    ],
)
def test_a_forged_token_is_refused_without_a_crash(signed, token):
    artifact_id = _seed_artifact(signed)
    signed.client.cookies.clear()

    response = signed.client.get(
        f"/artifacts/{artifact_id}/content", params={"token": token}
    )

    assert response.status_code in (401, 403)


def test_a_token_signed_with_a_retired_key_is_refused(signed):
    artifact_id = _seed_artifact(signed)
    token = sign_artifact_token(
        artifact_id,
        signed.member_id,
        datetime.now(timezone.utc) + timedelta(minutes=5),
        OTHER_KEY,
    )
    with signed.session_factory() as db:
        db.add(
            ArtifactLinkModel(
                artifact_id=artifact_id,
                user_id=signed.member_id,
                token_hash=token_hash(token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        db.commit()
    signed.client.cookies.clear()

    response = signed.client.get(
        f"/artifacts/{artifact_id}/content", params={"token": token}
    )

    assert response.status_code == 403


def test_the_link_lifetime_is_bounded_and_defaults_to_five_minutes(signed):
    artifact_id = _seed_artifact(signed)

    default = _create_link(signed, artifact_id)
    assert default.status_code == 201
    expires_at = datetime.fromisoformat(default.json()["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    assert 240 < remaining <= 300

    assert _create_link(signed, artifact_id, ttl_seconds=901).status_code == 422
    assert _create_link(signed, artifact_id, ttl_seconds=0).status_code == 422
    assert _create_link(signed, artifact_id, ttl_seconds=900).status_code == 201


def test_a_link_counts_its_uses(signed):
    artifact_id = _seed_artifact(signed)
    created = _create_link(signed, artifact_id).json()
    token = created["url"].split("token=")[1]
    signed.client.cookies.clear()

    for _ in range(2):
        assert (
            signed.client.get(
                f"/artifacts/{artifact_id}/content", params={"token": token}
            ).status_code
            == 200
        )

    with signed.session_factory() as db:
        link = db.get(ArtifactLinkModel, created["id"])
        assert link.used_count == 2


def test_a_link_counts_only_a_content_response_that_was_prepared(signed):
    artifact_id = _seed_artifact(signed, payload=b"0123456789")
    created = _create_link(signed, artifact_id).json()
    token = created["url"].split("token=", 1)[1]
    signed.client.cookies.clear()

    refused = signed.client.get(
        f"/artifacts/{artifact_id}/content",
        params={"token": token},
        headers={"Range": "bytes=99-100"},
    )

    assert refused.status_code == 416
    with signed.session_factory() as db:
        assert db.get(ArtifactLinkModel, created["id"]).used_count == 0


def test_a_link_cannot_be_created_for_a_foreign_artifact(signed):
    foreign = _seed_artifact(
        signed,
        project_id=signed.other_project_id,
        task_run_id=signed.other_run_id,
    )

    assert _create_link(signed, foreign).status_code == 404


def test_a_link_cannot_be_created_without_content(signed):
    artifact_id = _seed_artifact(signed, payload=None)

    assert _create_link(signed, artifact_id).status_code == 404


def test_creating_a_link_requires_the_csrf_token(signed):
    artifact_id = _seed_artifact(signed)
    signed.client.headers.pop("X-CSRF-Token", None)

    assert _create_link(signed, artifact_id).status_code == 403


def test_a_stranger_cannot_revoke_a_link(signed):
    artifact_id = _seed_artifact(signed)
    created = _create_link(signed, artifact_id).json()
    signed.client.cookies.set("acp_session", signed.stranger_session)
    signed.client.headers["X-CSRF-Token"] = signed.stranger_csrf

    response = signed.client.delete(f"/artifacts/links/{created['id']}")

    assert response.status_code == 404


def test_revocation_is_idempotent(signed):
    artifact_id = _seed_artifact(signed)
    created = _create_link(signed, artifact_id).json()

    assert signed.client.delete(f"/artifacts/links/{created['id']}").status_code == 204
    assert signed.client.delete(f"/artifacts/links/{created['id']}").status_code == 204


def test_the_preview_origin_is_used_when_configured(signed, monkeypatch):
    monkeypatch.setenv("ACP_API_URL", "https://api.exemple.fr")
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://apercu.exemple.fr")
    artifact_id = _seed_artifact(signed)

    url = _create_link(signed, artifact_id, purpose="preview").json()["url"]

    assert url.startswith(f"https://apercu.exemple.fr/artifacts/{artifact_id}/content?")


def test_preview_and_download_links_created_in_the_same_second_never_collide(
    signed, monkeypatch
):
    monkeypatch.setenv("ACP_API_URL", "https://api.exemple.fr")
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://apercu.exemple.fr")
    artifact_id = _seed_artifact(signed)

    preview = _create_link(signed, artifact_id, purpose="preview")
    download = _create_link(signed, artifact_id, purpose="download")

    assert preview.status_code == download.status_code == 201
    assert preview.json()["id"] != download.json()["id"]
    assert preview.json()["url"] != download.json()["url"]
    with signed.session_factory() as db:
        assert db.query(ArtifactLinkModel).count() == 2


def test_a_preview_token_is_inline_only_on_its_configured_origin(signed, monkeypatch):
    monkeypatch.setenv("ACP_API_URL", "https://api.exemple.fr")
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://apercu.exemple.fr")
    artifact_id = _seed_artifact(
        signed, payload=b"capture", content_type="image/png", original_name="c.png"
    )
    created = _create_link(signed, artifact_id, purpose="preview").json()
    token = created["url"].split("token=", 1)[1]
    signed.client.cookies.clear()

    refused = signed.client.get(
        f"https://api.exemple.fr/artifacts/{artifact_id}/content",
        params={"token": token},
    )
    accepted = signed.client.get(created["url"])

    assert refused.status_code == 403
    assert accepted.status_code == 200
    assert accepted.content == b"capture"
    assert accepted.headers["content-disposition"].startswith("inline")
    with signed.session_factory() as db:
        assert db.get(ArtifactLinkModel, created["id"]).used_count == 1


def test_a_download_token_stays_an_attachment_on_the_preview_origin(
    signed, monkeypatch
):
    monkeypatch.setenv("ACP_API_URL", "https://api.exemple.fr")
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://apercu.exemple.fr")
    artifact_id = _seed_artifact(
        signed, payload=b"capture", content_type="image/png", original_name="c.png"
    )
    created = _create_link(signed, artifact_id, purpose="download").json()
    token = created["url"].split("token=", 1)[1]
    signed.client.cookies.clear()

    response = signed.client.get(
        f"https://apercu.exemple.fr/artifacts/{artifact_id}/content",
        params={"token": token},
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")


def test_a_download_link_stays_on_the_api_when_preview_origin_is_configured(
    signed, monkeypatch
):
    monkeypatch.setenv("ACP_API_URL", "https://api.exemple.fr")
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://apercu.exemple.fr")
    artifact_id = _seed_artifact(signed)

    url = _create_link(signed, artifact_id, purpose="download").json()["url"]

    assert url.startswith(f"https://api.exemple.fr/artifacts/{artifact_id}/content?")
    assert "apercu.exemple.fr" not in url


def test_a_preview_link_checks_its_origin_before_keys_and_persists_nothing(context):
    artifact_id = _seed_artifact(context)

    response = _create_link(context, artifact_id, purpose="preview")

    assert response.status_code == 424
    assert "ACP_ARTIFACT_PUBLIC_ORIGIN" in response.json()["detail"]
    with context.session_factory() as db:
        assert db.query(ArtifactLinkModel).count() == 0


def test_a_preview_link_requires_an_explicit_api_origin_before_signing(
    signed, monkeypatch
):
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://apercu.exemple.fr")
    artifact_id = _seed_artifact(signed)

    response = _create_link(signed, artifact_id, purpose="preview")

    assert response.status_code == 424
    assert "ACP_API_URL" in response.json()["detail"]
    with signed.session_factory() as db:
        assert db.query(ArtifactLinkModel).count() == 0


def test_an_invalid_download_origin_fails_before_signing_or_persistence(
    signed, monkeypatch
):
    monkeypatch.setenv("ACP_API_URL", "https://api.example.test/subpath")
    artifact_id = _seed_artifact(signed)

    response = _create_link(signed, artifact_id, purpose="download")

    assert response.status_code == 424
    assert "ACP_API_URL" in response.json()["detail"]
    with signed.session_factory() as db:
        assert db.query(ArtifactLinkModel).count() == 0


@pytest.mark.parametrize(
    "origin",
    [
        "http://preview.example.test",
        "https://user:secret@preview.example.test",
        "https://preview.example.test/subpath",
        "javascript:alert(1)",
    ],
)
def test_an_unsafe_preview_origin_fails_closed(signed, monkeypatch, origin):
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", origin)
    artifact_id = _seed_artifact(signed)

    response = _create_link(signed, artifact_id, purpose="preview")

    assert response.status_code == 424
    assert origin not in response.text


def test_the_preview_origin_must_differ_from_the_control_api(signed, monkeypatch):
    monkeypatch.setenv("ACP_API_URL", "https://api.example.test")
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://api.example.test/")
    artifact_id = _seed_artifact(signed)

    response = _create_link(signed, artifact_id, purpose="preview")

    assert response.status_code == 424
    assert "distincte" in response.json()["detail"]


def test_the_preview_origin_must_differ_from_the_browser_origin(signed, monkeypatch):
    monkeypatch.setenv("ACP_API_URL", "https://api.example.test")
    monkeypatch.setenv("ACP_CORS_ORIGINS", "https://app.example.test")
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://app.example.test/")
    artifact_id = _seed_artifact(signed)

    response = _create_link(signed, artifact_id, purpose="preview")

    assert response.status_code == 424
    assert "application" in response.json()["detail"]
