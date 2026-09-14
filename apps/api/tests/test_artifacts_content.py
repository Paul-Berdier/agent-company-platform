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

import hashlib
import io
import errno
import tempfile
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
    run = TaskRunModel(task_id=task.id, status="running")
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


def test_the_content_carries_every_security_header(context):
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
    assert response.headers["content-disposition"].startswith("inline")


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
    monkeypatch.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://apercu.exemple.fr")
    artifact_id = _seed_artifact(signed)

    url = _create_link(signed, artifact_id).json()["url"]

    assert url.startswith(f"https://apercu.exemple.fr/artifacts/{artifact_id}/content?")
