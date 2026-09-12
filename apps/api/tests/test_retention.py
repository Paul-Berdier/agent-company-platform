"""Rétention du journal et des livrables (§5.5).

Deux garde-fous structurent ces tests :

1. **Rien n'est supprimé sans `--apply`.** La commande est une purge à blanc par
   défaut : un opérateur voit d'abord ce qui disparaîtrait.
2. **Le stockage est adressé par contenu**, donc deux livrables peuvent partager un
   blob. Effacer le fichier parce qu'un livrable expire viderait l'autre : le
   comptage de références est obligatoire, pas une optimisation.

Les preuves de mission et les événements terminaux d'une tentative ne sont jamais
purgés : ce sont eux qui rendent une mission auditable après coup.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api.artifacts_storage import LocalArtifactStorage
from acp_api.retention import (
    TERMINAL_RUN_EVENT_TYPES,
    PurgeReport,
    main,
    purge_expired,
)
from acp_database.models import (
    ArtifactModel,
    Base,
    EventModel,
    MissionEvidenceModel,
    OrganizationModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    WorkerModel,
    WorkspaceModel,
)

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


@pytest.fixture
def storage(tmp_path):
    return LocalArtifactStorage(tmp_path / "blobs")


@pytest.fixture
def world(session_factory):
    """Projet, tentative et worker minimaux pour rattacher des livrables."""

    with session_factory() as db:
        organization = OrganizationModel(name="Org")
        db.add(organization)
        db.flush()
        workspace = WorkspaceModel(organization_id=organization.id, name="Ws")
        db.add(workspace)
        db.flush()
        project = ProjectModel(workspace_id=workspace.id, name="Projet")
        db.add(project)
        db.flush()
        task = TaskModel(project_id=project.id, title="Tâche")
        db.add(task)
        db.flush()
        run = TaskRunModel(task_id=task.id, status="succeeded")
        db.add(run)
        worker = WorkerModel(
            name=f"worker-{uuid4().hex}",
            token_hash="x" * 64,
            token_prefix="prefix",
            token_expires_at=NOW,
        )
        db.add(worker)
        db.commit()
        return {"project_id": project.id, "run_id": run.id, "worker_id": worker.id}


def _artifact(
    db: Session,
    world: dict,
    storage: LocalArtifactStorage,
    *,
    payload: bytes,
    age_days: int,
    deleted_at: datetime | None = None,
) -> ArtifactModel:
    blob = storage.write(io.BytesIO(payload), max_bytes=1_000_000)
    artifact = ArtifactModel(
        project_id=world["project_id"],
        task_run_id=world["run_id"],
        worker_id=world["worker_id"],
        kind="report",
        path="",
        checksum=blob.sha256,
        size_bytes=blob.size,
        metadata_json={},
        storage_key=blob.key,
        content_type="application/octet-stream",
        original_name="",
        source="worker",
        stream_kind="file",
        deleted_at=deleted_at,
    )
    artifact.created_at = NOW - timedelta(days=age_days)
    db.add(artifact)
    db.flush()
    return artifact


def _event(db: Session, world: dict, *, type_: str, age_days: int) -> EventModel:
    event = EventModel(
        type=type_,
        occurred_at=NOW - timedelta(days=age_days),
        project_id=world["project_id"],
        task_run_id=world["run_id"],
        payload={},
    )
    event.created_at = NOW - timedelta(days=age_days)
    db.add(event)
    db.flush()
    return event


# --- Purge à blanc --------------------------------------------------------------


def test_a_dry_run_reports_without_deleting_anything(session_factory, storage, world):
    with session_factory() as db:
        artifact = _artifact(db, world, storage, payload=b"vieux", age_days=400)
        _event(db, world, type_="task.progress", age_days=400)
        db.commit()
        artifact_id = artifact.id
        storage_key = artifact.storage_key

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW)

    assert isinstance(report, PurgeReport)
    assert report.applied is False
    assert report.events_deleted == 1
    assert report.artifacts_marked == 1
    assert report.blobs_deleted == 1
    with session_factory() as db:
        assert db.query(EventModel).count() == 1
        assert db.get(ArtifactModel, artifact_id).deleted_at is None
    assert storage.exists(storage_key)


def test_applying_purges_events_and_artifacts(session_factory, storage, world):
    with session_factory() as db:
        artifact = _artifact(db, world, storage, payload=b"vieux", age_days=400)
        _event(db, world, type_="task.progress", age_days=400)
        db.commit()
        artifact_id = artifact.id
        storage_key = artifact.storage_key

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.applied is True
    assert report.events_deleted == 1
    assert report.artifacts_marked == 1
    assert report.blobs_deleted == 1
    with session_factory() as db:
        assert db.query(EventModel).count() == 0
        purged = db.get(ArtifactModel, artifact_id)
        # Les métadonnées restent : l'historique de la tentative n'est pas réécrit.
        assert purged is not None
        assert purged.deleted_at is not None
        assert purged.checksum and purged.size_bytes
    assert not storage.exists(storage_key)


# --- Protections ----------------------------------------------------------------


@pytest.mark.parametrize("event_type", sorted(TERMINAL_RUN_EVENT_TYPES))
def test_terminal_run_events_are_never_purged(
    session_factory, storage, world, event_type
):
    with session_factory() as db:
        _event(db, world, type_=event_type, age_days=4000)
        db.commit()

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.events_deleted == 0
    assert report.events_protected == 1
    with session_factory() as db:
        assert db.query(EventModel).count() == 1


def test_a_recent_event_is_untouched(session_factory, storage, world):
    with session_factory() as db:
        _event(db, world, type_="task.progress", age_days=10)
        db.commit()

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.events_deleted == 0
    with session_factory() as db:
        assert db.query(EventModel).count() == 1


def test_an_unlimited_retention_keeps_every_event(session_factory, storage, world):
    with session_factory() as db:
        _event(db, world, type_="task.progress", age_days=4000)
        db.commit()

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, event_days=0, apply=True)

    assert report.events_deleted == 0
    with session_factory() as db:
        assert db.query(EventModel).count() == 1


def test_a_shared_blob_survives_while_another_artifact_references_it(
    session_factory, storage, world
):
    """Adressage par contenu : un livrable expiré ne vide pas celui qui reste."""

    with session_factory() as db:
        old = _artifact(db, world, storage, payload="partagé".encode(), age_days=400)
        recent = _artifact(db, world, storage, payload="partagé".encode(), age_days=1)
        db.commit()
        shared_key = old.storage_key
        assert recent.storage_key == shared_key
        old_id, recent_id = old.id, recent.id

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.artifacts_marked == 1
    assert report.blobs_deleted == 0
    assert report.blobs_kept == 1
    assert storage.exists(shared_key)
    with session_factory() as db:
        assert db.get(ArtifactModel, old_id).deleted_at is not None
        assert db.get(ArtifactModel, recent_id).deleted_at is None


def test_two_expired_artifacts_sharing_a_blob_delete_it_once(
    session_factory, storage, world
):
    with session_factory() as db:
        _artifact(db, world, storage, payload=b"jumeau", age_days=400)
        second = _artifact(db, world, storage, payload=b"jumeau", age_days=500)
        db.commit()
        shared_key = second.storage_key

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.artifacts_marked == 2
    assert report.blobs_deleted == 1
    assert not storage.exists(shared_key)


@pytest.mark.parametrize("citation", ["data", "uri", "checksum"])
def test_an_artifact_cited_by_a_mission_evidence_is_never_purged(
    session_factory, storage, world, citation
):
    with session_factory() as db:
        artifact = _artifact(db, world, storage, payload=b"preuve", age_days=4000)
        db.flush()
        evidence = MissionEvidenceModel(
            task_run_id=world["run_id"],
            worker_id=world["worker_id"],
            kind="artifact",
            summary="Rapport de recette",
            fingerprint=uuid4().hex,
        )
        if citation == "data":
            evidence.data = {"artifact_id": artifact.id}
        elif citation == "uri":
            evidence.uri = f"acp://artifacts/{artifact.id}/content"
        else:
            evidence.checksum = artifact.checksum
        db.add(evidence)
        db.commit()
        artifact_id = artifact.id
        storage_key = artifact.storage_key

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.artifacts_marked == 0
    assert report.artifacts_protected == 1
    assert storage.exists(storage_key)
    with session_factory() as db:
        assert db.get(ArtifactModel, artifact_id).deleted_at is None


def test_an_already_purged_artifact_is_not_counted_again(
    session_factory, storage, world
):
    with session_factory() as db:
        _artifact(
            db,
            world,
            storage,
            payload="déjà".encode(),
            age_days=400,
            deleted_at=NOW - timedelta(days=10),
        )
        db.commit()

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.artifacts_marked == 0
    assert report.blobs_deleted == 0


def test_a_recent_artifact_is_untouched(session_factory, storage, world):
    with session_factory() as db:
        artifact = _artifact(db, world, storage, payload=b"frais", age_days=3)
        db.commit()
        storage_key = artifact.storage_key

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.artifacts_marked == 0
    assert storage.exists(storage_key)


def test_an_unlimited_artifact_retention_keeps_every_blob(
    session_factory, storage, world
):
    with session_factory() as db:
        artifact = _artifact(db, world, storage, payload="éternel".encode(), age_days=4000)
        db.commit()
        storage_key = artifact.storage_key

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, artifact_days=0, apply=True)

    assert report.artifacts_marked == 0
    assert storage.exists(storage_key)


def test_stale_upload_fragments_are_swept(session_factory, storage, world):
    """Un processus tué pendant un téléversement laisse un ``.part`` : il expire aussi."""

    import os

    temporary = storage.root / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    stale = temporary / "upload-abandonne.part"
    stale.write_bytes(b"fragment")
    old = (NOW - timedelta(days=3)).timestamp()
    os.utime(stale, (old, old))
    fresh = temporary / "upload-en-cours.part"
    fresh.write_bytes(b"fragment")

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW, apply=True)

    assert report.stale_uploads_deleted == 1
    assert not stale.exists()
    assert fresh.exists()


def test_a_dry_run_keeps_upload_fragments(session_factory, storage, world):
    import os

    temporary = storage.root / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    stale = temporary / "upload-abandonne.part"
    stale.write_bytes(b"fragment")
    old = (NOW - timedelta(days=3)).timestamp()
    os.utime(stale, (old, old))

    with session_factory() as db:
        report = purge_expired(db, storage, now=NOW)

    assert report.stale_uploads_deleted == 1
    assert stale.exists()


# --- Commande -------------------------------------------------------------------


def test_the_command_line_defaults_to_a_dry_run(session_factory, storage, world, capsys):
    with session_factory() as db:
        _event(db, world, type_="task.progress", age_days=400)
        db.commit()

    code = main([], session_factory=session_factory, storage=storage)

    assert code == 0
    printed = capsys.readouterr().out
    assert "blanc" in printed.lower() or "aucune suppression" in printed.lower()
    with session_factory() as db:
        assert db.query(EventModel).count() == 1


def test_the_command_line_applies_only_when_asked(
    session_factory, storage, world, capsys
):
    with session_factory() as db:
        _event(db, world, type_="task.progress", age_days=400)
        db.commit()

    code = main(["--apply"], session_factory=session_factory, storage=storage)

    assert code == 0
    assert capsys.readouterr().out
    with session_factory() as db:
        assert db.query(EventModel).count() == 0


def test_the_command_refuses_contradictory_flags(session_factory, storage, world):
    code = main(
        ["--apply", "--dry-run"], session_factory=session_factory, storage=storage
    )

    assert code == 2


def test_the_command_refuses_a_negative_retention(session_factory, storage, world):
    code = main(
        ["--event-days", "-1"], session_factory=session_factory, storage=storage
    )

    assert code == 2
