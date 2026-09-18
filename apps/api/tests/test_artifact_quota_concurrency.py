"""Le quota d'artefacts est arbitré sous vraie concurrence (SQLite fichier ou PostgreSQL)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Barrier, Lock, Thread

from sqlalchemy.orm import Session

from acp_api.routers.artifacts import _lock_artifact_quota, _used_bytes_for_run
from acp_database.models import (
    ArtifactModel,
    OrganizationModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    WorkerModel,
    WorkspaceModel,
)
from acp_database.testing import make_test_engine


def test_two_uploads_cannot_both_spend_the_last_quota_bytes(tmp_path) -> None:
    database = make_test_engine(tmp_path, concurrent=True)
    engine = database.engine
    with Session(engine) as db:
        organization = OrganizationModel(name="Org")
        db.add(organization)
        db.flush()
        workspace = WorkspaceModel(organization_id=organization.id, name="Workspace")
        db.add(workspace)
        db.flush()
        project = ProjectModel(workspace_id=workspace.id, name="Projet")
        worker = WorkerModel(
            name="worker-quota",
            token_hash="a" * 64,
            token_prefix="quota",
            token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add_all([project, worker])
        db.flush()
        task = TaskModel(project_id=project.id, title="Tâche")
        db.add(task)
        db.flush()
        run = TaskRunModel(task_id=task.id, status="running")
        db.add(run)
        db.commit()
        project_id, worker_id, run_id = project.id, worker.id, run.id

    barrier = Barrier(2)
    guard = Lock()
    accepted: list[bool] = []
    failures: list[BaseException] = []

    def reserve(suffix: str) -> None:
        try:
            with Session(engine) as db:
                barrier.wait()
                _lock_artifact_quota(db, run_id)
                remaining = 8 - _used_bytes_for_run(db, run_id)
                if remaining < 8:
                    db.rollback()
                    with guard:
                        accepted.append(False)
                    return
                db.add(
                    ArtifactModel(
                        project_id=project_id,
                        task_run_id=run_id,
                        worker_id=worker_id,
                        kind="file",
                        path="",
                        checksum=suffix * 64,
                        size_bytes=8,
                        storage_key=f"{suffix * 2}/{suffix * 64}",
                    )
                )
                db.commit()
                with guard:
                    accepted.append(True)
        except BaseException as exc:  # pragma: no cover - rendu dans l'assertion
            with guard:
                failures.append(exc)

    threads = [Thread(target=reserve, args=(value,)) for value in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert failures == []
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(accepted) == [False, True]
    with Session(engine) as db:
        assert db.query(ArtifactModel).count() == 1
        assert _used_bytes_for_run(db, run_id) == 8
    database.close()
