"""Exécutions de tests structurées (ingestion worker et lectures membres).

Un succès provient d'assertions et d'un code de sortie réels ; les statuts
Playwright restent distincts et ne sont jamais réduits à « vert / rouge ».

Le routeur est déclaré sans préfixe : chaque route porte son chemin complet
(``/workers/{worker_id}/test-runs``, ``/runs/{run_id}/test-run``, ``/test-runs/{id}``).

Le projet d'une lecture est toujours résolu **côté serveur** depuis la tentative :
aucun identifiant fourni par le client n'élargit la portée.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from acp_contracts import TestIngestRequest, TestRunDetail
from acp_database.models import TaskModel, TaskRunModel, TestRunModel

from ..deps import ensure_access, get_db, get_principal
from ..testing_service import ingest_test_run, test_run_detail, test_run_for_attempt
from .workers import authenticate_worker

router = APIRouter(tags=["testing"])


def _readable_test_run(
    db: Session, principal: str | None, test_run: TestRunModel
) -> TestRunDetail:
    """Autorise la lecture par le projet de la tentative, jamais par le corps reçu."""

    attempt = db.get(TaskRunModel, test_run.task_run_id)
    task = db.get(TaskModel, attempt.task_id) if attempt is not None else None
    if attempt is None or task is None:
        raise HTTPException(status_code=404, detail="Exécution de tests introuvable")
    ensure_access(db, principal, project_id=task.project_id, minimum_role="viewer")
    return test_run_detail(db, test_run)


@router.post("/workers/{worker_id}/test-runs", response_model=TestRunDetail)
def ingest_worker_test_run(
    worker_id: str,
    body: TestIngestRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    header_worker_id: str | None = Header(default=None, alias="X-Worker-Id"),
):
    """Ingère le rapport normalisé d'un runner pour la tentative tenue par ce worker."""

    if not header_worker_id or header_worker_id != worker_id:
        raise HTTPException(status_code=401, detail="X-Worker-Id requis")
    worker = authenticate_worker(db, worker_id, authorization)
    return ingest_test_run(db, worker, body, background=background)


@router.get("/runs/{run_id}/test-run", response_model=TestRunDetail)
def read_test_run_of_attempt(
    run_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Exécution de tests d'une tentative ; 404 explicite s'il n'y en a aucune."""

    attempt = db.get(TaskRunModel, run_id)
    task = db.get(TaskModel, attempt.task_id) if attempt is not None else None
    if attempt is None or task is None:
        raise HTTPException(status_code=404, detail="Tentative introuvable")
    ensure_access(db, principal, project_id=task.project_id, minimum_role="viewer")
    test_run = test_run_for_attempt(db, run_id)
    if test_run is None:
        raise HTTPException(
            status_code=404,
            detail="Aucune exécution de tests pour cette tentative",
        )
    return test_run_detail(db, test_run)


@router.get("/test-runs/{test_run_id}", response_model=TestRunDetail)
def read_test_run(
    test_run_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    test_run = db.get(TestRunModel, test_run_id)
    if test_run is None:
        raise HTTPException(status_code=404, detail="Exécution de tests introuvable")
    return _readable_test_run(db, principal, test_run)
