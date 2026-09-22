"""Verrous de la politique budgétaire sous PostgreSQL (0.9.1, constat N2-6).

La politique budgétaire d'un projet est sérialisée en verrouillant la ligne du projet.
Jusqu'en 0.9.0, ce verrou était un ``FOR UPDATE`` : il bloquait aussi le ``KEY SHARE``
que PostgreSQL pose sur la ligne parente à chaque insertion d'une ligne fille (tâche,
alerte, artefact, conversation…). Un permis budgétaire suspendait donc toutes les
écritures rattachées au projet, et fermait un cycle d'interblocage avec le
planificateur tant que le verrou du journal était pris en milieu de transaction.

``FOR NO KEY UPDATE`` suffit à sérialiser les décisions de politique (deux verrous de
ce mode s'excluent) sans bloquer les clés étrangères des lignes filles.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy.orm import sessionmaker

from acp_api import budget_service
from acp_contracts import ProjectBudgetPolicy
from acp_database.models import (
    OrganizationModel,
    ProjectModel,
    TaskModel,
    WorkspaceModel,
)
from acp_database.testing import make_test_engine, skip_or_fail_without_postgresql

pytestmark = [pytest.mark.postgres, pytest.mark.concurrency]


@pytest.fixture
def session_factory(tmp_path):
    skip_or_fail_without_postgresql()
    database = make_test_engine(tmp_path, concurrent=True)
    assert database.backend == "postgresql"
    try:
        yield sessionmaker(bind=database.engine, expire_on_commit=False)
    finally:
        database.close()


@pytest.fixture
def project_id(session_factory) -> str:
    with session_factory() as db:
        organization = OrganizationModel(name="Org budget")
        db.add(organization)
        db.flush()
        workspace = WorkspaceModel(organization_id=organization.id, name="Espace budget")
        db.add(workspace)
        db.flush()
        project = ProjectModel(workspace_id=workspace.id, name="Projet budget")
        db.add(project)
        db.commit()
        return project.id


def _insert_task_concurrently(session_factory, project_id: str) -> tuple[threading.Thread, list]:
    outcome: list = []

    def insert() -> None:
        try:
            with session_factory() as db:
                db.add(TaskModel(project_id=project_id, title="Tâche pendant un permis"))
                db.commit()
            outcome.append("committed")
        except BaseException as exc:  # pragma: no cover - diagnostic
            outcome.append(exc)

    thread = threading.Thread(target=insert)
    thread.start()
    return thread, outcome


@pytest.mark.parametrize("operation", ["decision", "policy"])
def test_a_budget_decision_does_not_block_child_rows_of_its_project(
    session_factory, project_id, monkeypatch, operation
):
    budget = session_factory()
    thread = None
    try:
        if operation == "policy":
            # Conserver la transaction ouverte pour observer le verrou du PUT.
            monkeypatch.setattr(budget, "commit", budget.flush)
            budget_service.put_project_policy(
                budget, budget.get(ProjectModel, project_id), ProjectBudgetPolicy()
            )
        else:
            budget_service._lock_policy(budget, project_id)
        thread, outcome = _insert_task_concurrently(session_factory, project_id)
        thread.join(3)
        assert not thread.is_alive(), (
            "l'insertion d'une tâche du projet attend la fin de la décision budgétaire"
        )
        assert outcome == ["committed"]
    finally:
        budget.rollback()
        budget.close()
        if thread is not None:
            thread.join(15)
            assert not thread.is_alive()


def test_two_budget_decisions_on_one_project_are_still_serialized(
    session_factory, project_id
):
    first = session_factory()
    second_done = threading.Event()
    second_started = threading.Event()
    failures = []
    thread = None
    try:
        budget_service._lock_policy(first, project_id)
        first.commit()
        budget_service._lock_policy(first, project_id)

        def second_decision() -> None:
            try:
                with session_factory() as second:
                    second_started.set()
                    budget_service._lock_policy(second, project_id)
                    second_done.set()
                    second.rollback()
            except BaseException as exc:  # pragma: no cover - diagnostic
                failures.append(exc)

        thread = threading.Thread(target=second_decision)
        thread.start()
        assert second_started.wait(5)
        thread.join(1.5)
        assert thread.is_alive() and not second_done.is_set(), (
            "une seconde décision sur le même projet doit attendre la première"
        )
        first.rollback()
        thread.join(30)
        assert second_done.is_set() and not failures, failures
    finally:
        first.close()
        if thread is not None:
            thread.join(15)
            assert not thread.is_alive()
