"""Ingestion et lecture des exécutions de tests structurées (Lot E, §5.4).

Un succès provient d'assertions et d'un code de sortie réels. Les statuts Playwright
(``passed``, ``failed``, ``timedOut``, ``skipped``, ``interrupted``) et le caractère
``flaky`` sont conservés distinctement : rien n'est réduit à « vert / rouge ».

Trois garanties structurent ce module :

1. **Idempotence.** Une réémission du même rapport ne crée ni une seconde exécution
   (``UniqueConstraint(task_run_id, runner)``), ni un cas en double
   (``UniqueConstraint(test_run_id, test_id, attempt)``), ni un second jeu
   d'événements : chaque événement n'est publié qu'au moment où une ligne apparaît
   ou change d'état.
2. **Aucun média dans le journal.** Le ``payload`` d'un événement ne porte qu'une
   référence d'artefact (identifiant, type MIME, taille, empreinte) — jamais un
   contenu.
3. **Aucun succès forcé.** La validation technique dérivée est écrite dans la même
   transaction que l'exécution de tests, mais elle ne touche ni ``TaskRunModel.status``
   ni ``user_acceptance`` : l'acceptation utilisateur et l'évaluateur du Lot C restent
   les seuls à conclure une tentative.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    ArtifactSummary,
    Event,
    ReporterEvent,
    TestCaseResult,
    TestIngestRequest,
    TestRunDetail,
    TestRunSummary,
    TestTotals,
)
from acp_database.models import (
    ArtifactModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    TestCaseModel,
    TestRunModel,
    WorkerLeaseModel,
    WorkerModel,
    WorkspaceModel,
)

from . import events_bus
from .routers.workers import _as_utc, expire_task_leases, utcnow

__test__ = False  # module de service : pytest ne collecte pas ses symboles « test_ »

EVENT_RUN_STARTED = "test.run.started"
EVENT_CASE_FINISHED = "test.case.finished"
EVENT_RUN_FINISHED = "test.run.finished"

EVENT_EXECUTOR = "playwright"
"""L'exécuteur réel des assertions ; le worker n'est que le transporteur."""

EVENT_EMITTED_BY = "worker"
"""Le reporter n'a aucun credential : l'émetteur authentifié est le worker."""

EVENT_ERROR_EXCERPT_MAX_CHARS = 500
"""Extrait d'erreur porté par un événement ; le message complet reste en base."""

REPORTER_ERRORS_MAX = 20
"""Nombre d'erreurs de reporter conservées dans ``config['reporter_errors']``."""

NO_ASSERTION_REASON = "aucune assertion exécutée"
"""Motif exact d'un rapport vide : zéro cas n'est jamais un succès."""

_TERMINAL_TEST_RUN_STATUSES = frozenset(
    {"completed", "failed", "interrupted", "timed_out"}
)


# --- Dérivation de la validation technique ------------------------------------


def _counted(value: int, singular: str) -> str:
    return f"{value} {singular}{'s' if value > 1 else ''}"


def _exit_code_text(exit_code: int | None) -> str:
    return "absent" if exit_code is None else str(exit_code)


def _counters_sentence(totals: TestTotals, exit_code: int | None, case_count: int) -> str:
    """Phrase de compteurs : les six catégories restent visibles, même à zéro."""

    return (
        f"{_counted(case_count, 'cas exécuté')} : "
        f"{_counted(totals.expected, 'attendu')}, "
        f"{_counted(totals.unexpected, 'inattendu')}, "
        f"{_counted(totals.flaky, 'instable')}, "
        f"{_counted(totals.skipped, 'ignoré')}, "
        f"{_counted(totals.interrupted, 'interrompu')}, "
        f"{totals.timedOut} en dépassement de délai ; "
        f"code de sortie {_exit_code_text(exit_code)}."
    )


def _reporter_utc(value: datetime) -> datetime:
    """Normalise un instant du reporter en UTC avant de l'écrire en base.

    Le reporter Playwright horodate en UTC ; un instant reçu sans fuseau est donc
    réputé UTC (``replace(tzinfo=UTC)``), jamais interprété dans le fuseau local
    du serveur ni de la base ; un instant porteur d'un autre décalage est converti.
    Sans cette règle, SQLite (qui ne stocke pas le fuseau) relirait un mur d'heure
    local là où PostgreSQL relit l'instant en UTC, et la durée calculée entre un
    instant naïf et un instant conscient différerait selon le dialecte.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def derive_technical_validation(test_run: TestRunSummary) -> tuple[str, str]:
    """Dérive ``(statut, résumé)`` de la validation technique d'une exécution.

    ``passed`` exige un code de sortie nul, zéro cas ``unexpected``, ``interrupted``
    et ``timedOut``, **et** au moins un cas réellement exécuté. ``flaky`` et
    ``skipped`` n'empêchent pas ``passed`` mais figurent toujours dans le résumé.
    La valeur retournée n'est jamais ``succeeded`` : conclure une tentative
    n'appartient pas à ce module.
    """

    totals = test_run.totals
    exit_code = test_run.exit_code
    case_count = test_run.case_count
    counters = _counters_sentence(totals, exit_code, case_count)

    reasons: list[str] = []
    if case_count == 0:
        reasons.append(NO_ASSERTION_REASON)
    if exit_code is None:
        reasons.append("code de sortie absent")
    elif exit_code != 0:
        reasons.append(f"code de sortie {exit_code} non nul")
    if totals.unexpected:
        reasons.append(f"{_counted(totals.unexpected, 'cas inattendu')}")
    if totals.interrupted:
        reasons.append(f"{_counted(totals.interrupted, 'cas interrompu')}")
    if totals.timedOut:
        reasons.append(f"{totals.timedOut} cas en dépassement de délai")

    if reasons:
        return "failed", f"Validation technique refusée — {', '.join(reasons)}. {counters}"
    return "passed", f"Validation technique réussie — {counters}"


# --- Lectures ------------------------------------------------------------------


def _artifact_summary(artifact: ArtifactModel) -> ArtifactSummary:
    """Expose un artefact sans jamais publier sa clé de stockage ni son chemin."""

    return ArtifactSummary(
        id=artifact.id,
        project_id=artifact.project_id,
        task_run_id=artifact.task_run_id,
        kind=artifact.kind,
        stream_kind=artifact.stream_kind or "",
        original_name=artifact.original_name or "",
        content_type=artifact.content_type or "application/octet-stream",
        size_bytes=artifact.size_bytes,
        checksum=artifact.checksum,
        source=artifact.source or "worker",
        has_content=artifact.storage_key is not None,
        created_at=artifact.created_at,
    )


def _artifacts_by_id(db: Session, artifact_ids: set[str]) -> dict[str, ArtifactModel]:
    if not artifact_ids:
        return {}
    rows = (
        db.query(ArtifactModel)
        .filter(
            ArtifactModel.id.in_(artifact_ids),
            ArtifactModel.deleted_at.is_(None),
        )
        .all()
    )
    return {row.id: row for row in rows}


def _case_contract(
    case: TestCaseModel, artifacts: dict[str, ArtifactModel]
) -> TestCaseResult:
    attachments = [
        _artifact_summary(artifacts[artifact_id])
        for artifact_id in (case.attachment_artifact_ids or [])
        if artifact_id in artifacts
    ]
    return TestCaseResult(
        id=case.id,
        test_run_id=case.test_run_id,
        suite_path=list(case.suite_path or []),
        title=case.title,
        test_id=case.test_id,
        location=dict(case.location or {}),
        project_name=case.project_name or "",
        attempt=case.attempt,
        expected_status=case.expected_status,
        status=case.status,
        outcome=case.outcome,
        duration_ms=case.duration_ms or 0,
        error_message=case.error_message or "",
        error_snippet=case.error_snippet or "",
        steps=list(case.steps or []),
        annotations=list(case.annotations or []),
        attachments=attachments,
    )


def _ordered_cases(db: Session, test_run_id: str) -> list[TestCaseModel]:
    return (
        db.query(TestCaseModel)
        .filter_by(test_run_id=test_run_id)
        .order_by(TestCaseModel.created_at, TestCaseModel.id)
        .all()
    )


def test_run_detail(db: Session, test_run: TestRunModel) -> TestRunDetail:
    """Rend une exécution complète : totaux, cas et rapport éventuel."""

    cases = _ordered_cases(db, test_run.id)
    referenced: set[str] = set()
    for case in cases:
        referenced.update(case.attachment_artifact_ids or [])
    if test_run.report_artifact_id:
        referenced.add(test_run.report_artifact_id)
    artifacts = _artifacts_by_id(db, referenced)
    report = artifacts.get(test_run.report_artifact_id or "")
    return TestRunDetail(
        id=test_run.id,
        task_run_id=test_run.task_run_id,
        project_id=test_run.project_id,
        worker_id=test_run.worker_id,
        runner=test_run.runner,
        runner_version=test_run.runner_version or "",
        status=test_run.status,
        # Servis avec un décalage explicite quel que soit le dialecte : SQLite relit
        # naïf ce que PostgreSQL relit en UTC.
        started_at=_as_utc(test_run.started_at),
        finished_at=(
            _as_utc(test_run.finished_at) if test_run.finished_at is not None else None
        ),
        duration_ms=test_run.duration_ms,
        totals=TestTotals.model_validate(test_run.totals or {}),
        exit_code=test_run.exit_code,
        config=dict(test_run.config or {}),
        case_count=len(cases),
        cases=[_case_contract(case, artifacts) for case in cases],
        report_artifact=_artifact_summary(report) if report is not None else None,
    )


def test_run_for_attempt(
    db: Session, task_run_id: str, *, runner: str | None = None
) -> TestRunModel | None:
    """Exécution de tests rattachée à une tentative (la plus récente par runner)."""

    query = db.query(TestRunModel).filter_by(task_run_id=task_run_id)
    if runner is not None:
        query = query.filter_by(runner=runner)
    return query.order_by(TestRunModel.created_at.desc()).first()


# Ces deux fonctions commencent par « test_ » : sans ce marqueur, pytest tenterait de
# les collecter comme des tests dès qu'un module de test les importe.
test_run_detail.__test__ = False
test_run_for_attempt.__test__ = False


# --- Événements ----------------------------------------------------------------


def _event_scope(db: Session, task: TaskModel) -> dict[str, Any]:
    project = db.get(ProjectModel, task.project_id)
    workspace = (
        db.get(WorkspaceModel, project.workspace_id) if project is not None else None
    )
    return {
        "organization_id": workspace.organization_id if workspace else None,
        "workspace_id": project.workspace_id if project else None,
        "department_id": project.department_id if project else None,
        "project_id": task.project_id,
        "team_id": task.team_id,
        "agent_instance_id": task.agent_instance_id,
        "task_id": task.id,
    }


def _publish(
    db: Session,
    *,
    scope: dict[str, Any],
    task_run_id: str,
    event_type: str,
    payload: dict[str, Any],
    background: BackgroundTasks | None,
) -> None:
    """Publie un événement séquencé **dans la transaction courante**.

    Délègue à ``events_bus.publish`` (agent E1) : numéros attribués au ``commit()`` de
    l'appelant (0.9.1), réveil des flux SSE du run et du projet et relais « best
    effort » vers le service temps réel reportés à ce même commit.
    ``commit=False`` est essentiel : la validation technique de la tentative et les
    cas de test doivent être validés dans la même transaction que ces événements.
    """

    events_bus.publish(
        db,
        Event(type=event_type, **scope, task_run_id=task_run_id, payload=payload),
        commit=False,
        background=background,
        executor=EVENT_EXECUTOR,
        emitted_by=EVENT_EMITTED_BY,
    )


def _attachment_references(
    artifact_ids: list[str], artifacts: dict[str, ArtifactModel]
) -> list[dict[str, Any]]:
    """Références d'artefacts pour un événement : jamais d'octets, jamais de chemin."""

    references = []
    for artifact_id in artifact_ids:
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            continue
        references.append(
            events_bus.media_reference_payload(
                artifact_id=artifact.id,
                content_type=artifact.content_type or "application/octet-stream",
                size_bytes=artifact.size_bytes or 0,
                sha256=artifact.checksum or "",
                stream_kind=artifact.stream_kind or "",
            )
        )
    return references


# --- Ingestion -----------------------------------------------------------------


def _require_active_run_lease(
    db: Session, worker_id: str, task_run_id: str
) -> WorkerLeaseModel:
    expire_task_leases(db)
    lease = (
        db.query(WorkerLeaseModel)
        .filter_by(worker_id=worker_id, task_run_id=task_run_id, status="active")
        .first()
    )
    if lease is None or _as_utc(lease.lease_expires_at) <= utcnow():
        raise HTTPException(
            status_code=409, detail="Le worker ne possède pas ce run actif"
        )
    return lease


def _deciding_cases(cases: list[TestCaseModel]) -> list[TestCaseModel]:
    """Ne garde qu'une ligne par test : celle de la dernière tentative.

    Playwright émet un ``test_end`` par tentative. Compter chaque ligne ferait d'un
    test instable — rouge puis vert — un échec inattendu. Seule la tentative la plus
    élevée décide, exactement comme le rapport Playwright.
    """

    latest: dict[str, TestCaseModel] = {}
    for case in cases:
        previous = latest.get(case.test_id)
        if previous is None or (case.attempt or 1) > (previous.attempt or 1):
            latest[case.test_id] = case
    return list(latest.values())


def _observed_totals(cases: list[TestCaseModel]) -> TestTotals:
    """Compteurs réellement observés, une seule fois par test."""

    deciding = _deciding_cases(cases)
    return TestTotals(
        expected=sum(1 for case in deciding if case.outcome == "expected"),
        unexpected=sum(1 for case in deciding if case.outcome == "unexpected"),
        flaky=sum(1 for case in deciding if case.outcome == "flaky"),
        skipped=sum(1 for case in deciding if case.outcome == "skipped"),
        interrupted=sum(1 for case in deciding if case.status == "interrupted"),
        timedOut=sum(1 for case in deciding if case.status == "timedOut"),
    )


def _accepts_exit_code(
    current: int | None, reported: int, *, was_finished: bool
) -> bool:
    """Dit si un code de sortie annoncé peut remplacer celui déjà enregistré.

    Tant que l'exécution n'est pas terminale, le dernier code annoncé fait foi. Une
    fois terminale, un second rapport peut encore **signaler** un échec (``0`` puis
    non nul) mais jamais l'**effacer** : sans cette règle, un ``run_end`` tardif
    annonçant ``exit_code=0`` repeindrait en vert une validation technique déjà
    refusée, y compris lorsque l'échec ne tenait qu'au code de sortie (teardown
    global, erreur de configuration, plantage après les assertions) et qu'aucune
    ligne rouge ne protège le verdict.
    """

    if not was_finished:
        return True
    if reported != 0:
        return True
    return (current or 0) == 0


def _merged_exit_code(measured: int | None, reported: int) -> int:
    """Fusionne le code mesuré par le worker et celui que le rapport s'attribue.

    Le worker mesure le code de sortie réel du processus ; le rapport, lui, est du
    contenu non fiable — le processus de test reçoit ``ACP_REPORT_FILE`` et peut
    donc ajouter la ligne ``run_end`` de son choix. La règle est la même que pour
    ``_merged_totals`` : le rapport peut **signaler** un échec, jamais en effacer un.

    Concrètement, un ``run_end`` annonçant ``0`` ne remplace jamais un code mesuré
    non nul ; un ``run_end`` annonçant un échec est en revanche toujours retenu
    quand le worker n'a mesuré aucun échec.
    """

    if measured is None:
        return reported
    if measured == 0 and reported != 0:
        return reported
    return measured


def _resolved_run_status(reported: str | None, exit_code: int | None) -> str:
    """Statut d'une exécution qui vient de recevoir son ``run_end``.

    Un ``run_end`` **termine** l'exécution : le statut annoncé ne peut pas la
    laisser ouverte. ``TestRunStatus`` admet pourtant ``running``, et recopier cette
    valeur priverait la tentative de toute validation technique et de son
    ``test.run.finished`` — un reporter modifié étoufferait ainsi un échec au lieu
    de le déclarer. Un ``completed`` annoncé sur un code de sortie non nul est
    refusé pour la même raison.
    """

    derived = "completed" if exit_code == 0 else "failed"
    if reported not in _TERMINAL_TEST_RUN_STATUSES:
        return derived
    if reported == "completed" and exit_code != 0:
        return derived
    return reported


def _merged_totals(reported: TestTotals | None, observed: TestTotals) -> TestTotals:
    """Conserve les totaux du rapport, sans jamais laisser sous-déclarer un échec.

    ``expected``, ``flaky`` et ``skipped`` viennent du rapport (Playwright seul sait
    qu'une reprise a rendu un test instable). Les trois compteurs bloquants sont en
    revanche relevés au niveau réellement observé : un reporter modifié ne peut pas
    transformer un échec enregistré en succès.
    """

    if reported is None:
        return observed
    return TestTotals(
        expected=reported.expected,
        unexpected=max(reported.unexpected, observed.unexpected),
        flaky=reported.flaky,
        skipped=reported.skipped,
        interrupted=max(reported.interrupted, observed.interrupted),
        timedOut=max(reported.timedOut, observed.timedOut),
    )


def _resolve_attachment_ids(
    db: Session, *, task_run_id: str, project_id: str, event: ReporterEvent
) -> list[str]:
    """Rattache les pièces jointes déjà téléversées par leur ``sha256``.

    Une empreinte inconnue est ignorée : le cas de test reste enregistré même si le
    téléversement du média a échoué — un test rouge ne doit jamais disparaître parce
    qu'une capture manque.
    """

    digests = [
        attachment.sha256 for attachment in event.attachments if attachment.sha256
    ]
    if not digests:
        return []
    rows = (
        db.query(ArtifactModel)
        .filter(
            ArtifactModel.task_run_id == task_run_id,
            ArtifactModel.project_id == project_id,
            ArtifactModel.deleted_at.is_(None),
            ArtifactModel.checksum.in_(set(digests)),
        )
        .order_by(ArtifactModel.created_at)
        .all()
    )
    by_digest: dict[str, str] = {}
    for row in rows:
        by_digest.setdefault(row.checksum, row.id)
    resolved: list[str] = []
    for digest in digests:
        artifact_id = by_digest.get(digest)
        if artifact_id is not None and artifact_id not in resolved:
            resolved.append(artifact_id)
    return resolved


def _resolve_report_artifact_id(
    db: Session, *, task_run_id: str, report_path: str | None
) -> str | None:
    """Retrouve le rapport HTML téléversé pour cette tentative.

    Le rapport est identifié par ``stream_kind='report'`` et par ``original_name``
    égal au chemin annoncé par le reporter (ou à son seul nom de fichier).
    """

    candidates = (
        db.query(ArtifactModel)
        .filter(
            ArtifactModel.task_run_id == task_run_id,
            ArtifactModel.deleted_at.is_(None),
            ArtifactModel.stream_kind == "report",
        )
        .order_by(ArtifactModel.created_at.desc())
        .all()
    )
    if not candidates:
        return None
    if report_path:
        normalized = report_path.replace("\\", "/")
        basename = normalized.rsplit("/", 1)[-1]
        for artifact in candidates:
            name = (artifact.original_name or "").replace("\\", "/")
            if name == normalized or (basename and name.rsplit("/", 1)[-1] == basename):
                return artifact.id
    return candidates[0].id if len(candidates) == 1 else None


def _get_or_create_test_run(
    db: Session,
    *,
    task_run_id: str,
    project_id: str,
    worker_id: str,
    request: TestIngestRequest,
) -> tuple[TestRunModel, bool]:
    existing = (
        db.query(TestRunModel)
        .filter_by(task_run_id=task_run_id, runner=request.runner)
        .with_for_update()
        .first()
    )
    if existing is not None:
        return existing, False
    created = TestRunModel(
        task_run_id=task_run_id,
        project_id=project_id,
        worker_id=worker_id,
        runner=request.runner,
        runner_version=request.runner_version,
        status="running",
        started_at=utcnow(),
        totals=TestTotals().model_dump(),
        exit_code=None,
        config=dict(request.config),
    )
    try:
        with db.begin_nested():
            db.add(created)
            db.flush()
    except IntegrityError:
        # Une ingestion concurrente a gagné la course : l'unicité
        # (task_run_id, runner) rend la seconde requête idempotente.
        if created in db:
            db.expunge(created)
        concurrent = (
            db.query(TestRunModel)
            .filter_by(task_run_id=task_run_id, runner=request.runner)
            .first()
        )
        if concurrent is None:  # pragma: no cover - défense
            raise
        return concurrent, False
    return created, True


def ingest_test_run(
    db: Session,
    worker: WorkerModel,
    request: TestIngestRequest,
    *,
    background: BackgroundTasks | None = None,
) -> TestRunDetail:
    """Ingère un rapport de tests transmis par un worker authentifié.

    Vérifie l'identité du worker (lease actif sur la tentative) et le
    ``fencing_token`` avant toute écriture, puis crée ou complète l'exécution de
    tests de façon idempotente et met à jour la validation technique de la tentative
    dans la même transaction.
    """

    _require_active_run_lease(db, worker.id, request.task_run_id)
    attempt = (
        db.query(TaskRunModel)
        .filter_by(id=request.task_run_id)
        .with_for_update()
        .first()
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Tentative introuvable")
    task = db.get(TaskModel, attempt.task_id)
    if task is None:
        raise HTTPException(status_code=409, detail="Tentative sans tâche rattachée")
    if request.fencing_token != (attempt.fencing_token or 0):
        raise HTTPException(status_code=409, detail="Fencing token requis ou périmé")

    test_run, created = _get_or_create_test_run(
        db,
        task_run_id=attempt.id,
        project_id=task.project_id,
        worker_id=worker.id,
        request=request,
    )
    was_finished = test_run.status in _TERMINAL_TEST_RUN_STATUSES
    scope = _event_scope(db, task)

    if created:
        _publish(
            db,
            scope=scope,
            task_run_id=attempt.id,
            event_type=EVENT_RUN_STARTED,
            payload={
                "test_run_id": test_run.id,
                "runner": test_run.runner,
                "runner_version": test_run.runner_version,
                "attempt_number": attempt.attempt_number,
            },
            background=background,
        )

    known_keys = {
        (case.test_id, case.attempt) for case in _ordered_cases(db, test_run.id)
    }
    reported_totals: TestTotals | None = None
    reporter_errors: list[str] = []
    run_end_seen = False
    finished_at: datetime | None = None
    run_status: str | None = None
    exit_code: int | None = request.exit_code
    report_path: str | None = None

    for event in request.events:
        if event.kind == "run_begin":
            if created:
                if event.started_at is not None:
                    test_run.started_at = _reporter_utc(event.started_at)
                if event.runner_version:
                    test_run.runner_version = event.runner_version
                if event.config:
                    merged = dict(test_run.config or {})
                    merged.update(event.config)
                    test_run.config = merged
            continue
        if event.kind == "error":
            if len(reporter_errors) < REPORTER_ERRORS_MAX:
                reporter_errors.append(event.message)
            continue
        if event.kind == "run_end":
            run_end_seen = True
            reported_totals = event.totals
            finished_at = (
                _reporter_utc(event.finished_at)
                if event.finished_at is not None
                else utcnow()
            )
            run_status = event.run_status
            if event.exit_code is not None:
                # Le code mesuré par le worker fait foi ; celui du rapport ne peut
                # que déclarer un échec de plus (``_merged_exit_code``).
                exit_code = _merged_exit_code(request.exit_code, event.exit_code)
            report_path = event.report_path
            continue

        key = (event.test_id, event.attempt)
        if key in known_keys:
            continue
        known_keys.add(key)
        attachment_ids = _resolve_attachment_ids(
            db,
            task_run_id=attempt.id,
            project_id=task.project_id,
            event=event,
        )
        case = TestCaseModel(
            test_run_id=test_run.id,
            suite_path=list(event.suite_path),
            title=event.title,
            test_id=event.test_id,
            location=dict(event.location),
            project_name=event.project_name,
            attempt=event.attempt,
            expected_status=event.expected_status,
            status=event.status,
            outcome=event.outcome,
            duration_ms=event.duration_ms,
            error_message=event.error_message,
            error_snippet=event.error_snippet,
            steps=[step.model_dump() for step in event.steps],
            annotations=[dict(annotation) for annotation in event.annotations],
            attachment_artifact_ids=attachment_ids,
        )
        db.add(case)
        db.flush()
        artifacts = _artifacts_by_id(db, set(attachment_ids))
        _publish(
            db,
            scope=scope,
            task_run_id=attempt.id,
            event_type=EVENT_CASE_FINISHED,
            payload={
                "test_run_id": test_run.id,
                "test_case_id": case.id,
                "test_id": case.test_id,
                "title": case.title,
                "suite_path": list(case.suite_path or []),
                "project_name": case.project_name,
                "attempt": case.attempt,
                "expected_status": case.expected_status,
                "status": case.status,
                "outcome": case.outcome,
                "duration_ms": case.duration_ms,
                "has_error": bool(case.error_message or case.error_snippet),
                "error_excerpt": (case.error_message or "")[
                    :EVENT_ERROR_EXCERPT_MAX_CHARS
                ],
                "attachments": _attachment_references(attachment_ids, artifacts),
            },
            background=background,
        )

    stored_cases = _ordered_cases(db, test_run.id)
    baseline_totals = reported_totals
    if baseline_totals is None and was_finished:
        # Lot de rattrapage sans ``run_end`` : les totaux déjà annoncés par le
        # rapport restent la référence. Les recalculer à partir des seules lignes
        # enregistrées perdrait ``flaky``, que Playwright seul connaît.
        baseline_totals = TestTotals.model_validate(dict(test_run.totals or {}))
    test_run.totals = _merged_totals(
        baseline_totals, _observed_totals(stored_cases)
    ).model_dump()
    if exit_code is not None and _accepts_exit_code(
        test_run.exit_code, exit_code, was_finished=was_finished
    ):
        test_run.exit_code = exit_code
    if reporter_errors:
        config = dict(test_run.config or {})
        config["reporter_errors"] = reporter_errors
        test_run.config = config

    if run_end_seen:
        test_run.finished_at = finished_at
        test_run.status = _resolved_run_status(run_status, test_run.exit_code)
        if test_run.started_at is not None and finished_at is not None:
            elapsed = _as_utc(finished_at) - _as_utc(test_run.started_at)
            test_run.duration_ms = max(0, int(elapsed.total_seconds() * 1000))
        resolved_report = _resolve_report_artifact_id(
            db, task_run_id=attempt.id, report_path=report_path
        )
        if resolved_report is not None:
            test_run.report_artifact_id = resolved_report
    db.flush()

    detail = test_run_detail(db, test_run)
    if test_run.status in _TERMINAL_TEST_RUN_STATUSES:
        status, summary = derive_technical_validation(detail)
        previous_status = (attempt.technical_validation or {}).get("status")
        # Jamais ``succeeded`` : la tentative n'est pas conclue ici. L'état du run,
        # l'acceptation utilisateur et l'évaluateur du Lot C restent intacts.
        attempt.technical_validation = {
            "status": status,
            "summary": summary,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        # Republié dès que le verdict change : le journal ne doit jamais
        # contredire ``TaskRunModel.technical_validation``.
        if not was_finished or status != previous_status:
            _publish(
                db,
                scope=scope,
                task_run_id=attempt.id,
                event_type=EVENT_RUN_FINISHED,
                payload={
                    "test_run_id": test_run.id,
                    "status": test_run.status,
                    "exit_code": test_run.exit_code,
                    "totals": dict(test_run.totals or {}),
                    "case_count": detail.case_count,
                    "duration_ms": test_run.duration_ms,
                    "technical_validation": status,
                    "summary": summary,
                    "report_artifact_id": test_run.report_artifact_id,
                    "errors": reporter_errors,
                },
                background=background,
            )

    db.commit()
    db.refresh(test_run)
    return test_run_detail(db, test_run)
