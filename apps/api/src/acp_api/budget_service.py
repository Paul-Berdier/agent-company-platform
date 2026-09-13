"""Application transactionnelle des budgets de mission et de projet.

Le ledger est l'autorité.  Une réservation autorisée compte jusqu'à ce qu'un
rapport d'usage la rapproche ; le cache par tentative ne contient que l'usage
réellement rapporté.  ``None`` reste une information absente, jamais un zéro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Iterable

from pydantic import ValidationError
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    AutomationMissionBudget,
    BudgetMutationResult,
    BudgetPermitRequest,
    BudgetUsageDelta,
    BudgetVerdict,
    Event,
    ProjectBudgetPolicy,
    ProjectBudgetPolicySummary,
)
from acp_contracts.schedule import resolve_timezone
from acp_database.models import (
    BudgetUsageModel,
    BudgetUsageReportModel,
    ProjectBudgetPolicyModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    WorkerLeaseModel,
    WorkerModel,
)

from .alerts_service import open_or_escalate_alert
from .events_bus import publish

_MONEY_QUANTUM = Decimal("0.000001")
_LIMIT_PRIORITY = ("max_cost", "max_tokens", "max_tool_calls")
_ACTIVE_MISSION_RUN_STATUSES = {
    "pending",
    "queued",
    "preparing",
    "running",
    "waiting_approval",
    "stopping",
}


class BudgetServiceError(RuntimeError):
    """Erreur métier rendue telle quelle par le routeur budget."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class BudgetContext:
    worker: WorkerModel
    lease: WorkerLeaseModel
    run: TaskRunModel
    task: TaskModel
    project: ProjectModel


@dataclass
class _Totals:
    """Sommes et preuve de complétude d'un ensemble de rapports actifs."""

    rows: int = 0
    cost: Decimal = Decimal("0")
    cost_known: bool = True
    currencies: set[str] | None = None
    tokens_input: int = 0
    tokens_input_known: bool = True
    tokens_output: int = 0
    tokens_output_known: bool = True
    tool_calls: int = 0
    tool_calls_known: bool = True
    usage_reported: bool = False
    estimated: bool = False

    def __post_init__(self) -> None:
        if self.currencies is None:
            self.currencies = set()

    def add(self, row: object) -> None:
        self.rows += 1
        cost = getattr(row, "cost", None)
        currency = getattr(row, "currency", None)
        if cost is None:
            self.cost_known = False
        else:
            self.cost += _money(cost)
            assert self.currencies is not None
            self.currencies.add(str(currency).upper())
        tokens_input = getattr(row, "tokens_input", None)
        if tokens_input is None:
            self.tokens_input_known = False
        else:
            self.tokens_input += int(tokens_input)
        tokens_output = getattr(row, "tokens_output", None)
        if tokens_output is None:
            self.tokens_output_known = False
        else:
            self.tokens_output += int(tokens_output)
        tool_calls = getattr(row, "tool_calls", None)
        if tool_calls is None:
            self.tool_calls_known = False
        else:
            self.tool_calls += int(tool_calls)
        self.estimated = self.estimated or bool(getattr(row, "estimated", False))
        self.usage_reported = self.usage_reported or (
            getattr(row, "kind", None) == "usage"
            and getattr(row, "source", None) == "provider"
            and any(
                value is not None
                for value in (cost, tokens_input, tokens_output)
            )
        )


@dataclass(frozen=True)
class _LimitScope:
    name: str
    budget: AutomationMissionBudget
    totals: _Totals


def utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def begin_budget_write(db: Session) -> None:
    """Ferme la lecture d'auth puis sérialise les décisions sous SQLite.

    PostgreSQL s'appuie ensuite sur ``FOR UPDATE``. SQLite ignore ce verrou ;
    ``BEGIN IMMEDIATE`` prend donc son verrou d'écriture *avant* la lecture des
    totaux, ce qui rend la frontière ``nouveau total <= plafond`` atomique.
    """

    if db.in_transaction():
        db.rollback()
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def load_worker_budget_context(
    db: Session,
    *,
    worker: WorkerModel,
    run_id: str,
    fencing_token: int | None,
    now: datetime | None = None,
) -> BudgetContext:
    """Dérive la tâche et le projet depuis un lease actif authentifié."""

    moment = _as_utc(now or utcnow())
    run = (
        db.query(TaskRunModel)
        .filter(TaskRunModel.id == run_id)
        .with_for_update()
        .first()
    )
    if run is None:
        raise BudgetServiceError(404, "Tentative introuvable")
    lease = (
        db.query(WorkerLeaseModel)
        .filter_by(worker_id=worker.id, task_run_id=run.id, status="active")
        .with_for_update()
        .first()
    )
    if lease is None:
        raise BudgetServiceError(409, "Lease actif requis pour le budget")
    if _as_utc(lease.lease_expires_at) <= moment:
        raise BudgetServiceError(409, "Lease expiré ; écriture de budget refusée")
    task = db.get(TaskModel, run.task_id)
    if task is None or lease.task_id != task.id:
        raise BudgetServiceError(409, "Lease incohérent avec la tentative")
    if fencing_token is None or fencing_token != run.fencing_token:
        raise BudgetServiceError(409, "Fencing token requis ou périmé")
    project = db.get(ProjectModel, task.project_id)
    if project is None:
        raise BudgetServiceError(409, "Projet de la tentative introuvable")
    return BudgetContext(worker=worker, lease=lease, run=run, task=task, project=project)


def _policy_payload(policy: ProjectBudgetPolicy) -> dict:
    return policy.model_dump(mode="json", exclude={"timezone"})


def _policy_from_row(row: ProjectBudgetPolicyModel) -> ProjectBudgetPolicy:
    payload = dict(row.policy or {})
    payload["timezone"] = row.timezone
    try:
        return ProjectBudgetPolicy.model_validate(payload)
    except ValidationError as exc:
        raise BudgetServiceError(
            409, "La politique de budget persistée est invalide"
        ) from exc


def default_policy_summary(project: ProjectModel) -> ProjectBudgetPolicySummary:
    policy = ProjectBudgetPolicy()
    return ProjectBudgetPolicySummary(
        project_id=project.id,
        updated_at=_as_utc(project.created_at),
        **policy.model_dump(),
    )


def get_project_policy(
    db: Session, project: ProjectModel
) -> ProjectBudgetPolicySummary:
    row = (
        db.query(ProjectBudgetPolicyModel)
        .filter_by(project_id=project.id)
        .first()
    )
    if row is None:
        return default_policy_summary(project)
    policy = _policy_from_row(row)
    return ProjectBudgetPolicySummary(
        project_id=project.id,
        updated_at=_as_utc(row.updated_at),
        **policy.model_dump(),
    )


def _validate_policy_currencies(policy: ProjectBudgetPolicy) -> None:
    """Refuse une politique qui nécessiterait une conversion implicite."""

    if policy.daily_budget is None or policy.daily_budget.max_cost is None:
        return
    daily_currency = policy.daily_budget.currency
    conflicts = sorted(
        limit.provider
        for limit in policy.provider_budgets
        if limit.budget.max_cost is not None
        and limit.budget.currency != daily_currency
    )
    if conflicts:
        raise BudgetServiceError(
            422,
            "Devise incompatible avec le plafond journalier pour : "
            + ", ".join(conflicts),
        )


def put_project_policy(
    db: Session,
    project: ProjectModel,
    policy: ProjectBudgetPolicy,
) -> ProjectBudgetPolicySummary:
    _validate_policy_currencies(policy)
    row = (
        db.query(ProjectBudgetPolicyModel)
        .filter_by(project_id=project.id)
        .with_for_update()
        .first()
    )
    moment = utcnow()
    if row is None:
        row = ProjectBudgetPolicyModel(
            project_id=project.id,
            timezone=policy.timezone,
            policy=_policy_payload(policy),
            updated_at=moment,
        )
        db.add(row)
    else:
        row.timezone = policy.timezone
        row.policy = _policy_payload(policy)
        row.updated_at = moment
    db.commit()
    db.refresh(row)
    return get_project_policy(db, project)


def _lock_policy(db: Session, project_id: str) -> tuple[ProjectBudgetPolicyModel, ProjectBudgetPolicy]:
    row = (
        db.query(ProjectBudgetPolicyModel)
        .filter_by(project_id=project_id)
        .with_for_update()
        .first()
    )
    if row is None:
        default = ProjectBudgetPolicy()
        candidate = ProjectBudgetPolicyModel(
            project_id=project_id,
            timezone=default.timezone,
            policy=_policy_payload(default),
            updated_at=utcnow(),
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            row = (
                db.query(ProjectBudgetPolicyModel)
                .filter_by(project_id=project_id)
                .with_for_update()
                .one()
            )
        else:
            row = candidate
    # Un UPDATE sans changement est le verrou de décision portable. Il complète
    # FOR UPDATE et est décisif sur SQLite lorsque le service est appelé sans le
    # routeur (tests ou intégration interne).
    db.query(ProjectBudgetPolicyModel).filter_by(id=row.id).update(
        {ProjectBudgetPolicyModel.updated_at: ProjectBudgetPolicyModel.updated_at},
        synchronize_session=False,
    )
    db.flush()
    db.refresh(row)
    return row, _policy_from_row(row)


def enforce_project_mission_capacity(
    db: Session, project_id: str
) -> ProjectBudgetPolicy:
    """Verrouille la policy puis refuse une mission transversale de trop.

    L'appelant conserve la transaction ouverte et doit créer la mission avant son
    commit. Cette discipline rend la vérification et la matérialisation atomiques
    dès lors que tous les producteurs de missions passent par ce point.
    """

    _, policy = _lock_policy(db, project_id)
    active = (
        db.query(TaskRunModel.id)
        .join(TaskModel, TaskModel.id == TaskRunModel.task_id)
        .filter(
            TaskModel.project_id == project_id,
            TaskModel.is_mission == 1,
            TaskRunModel.status.in_(_ACTIVE_MISSION_RUN_STATUSES),
        )
        .count()
    )
    if active >= policy.max_concurrent_missions:
        raise BudgetServiceError(
            409,
            "Plafond de missions concurrentes atteint pour ce projet",
        )
    return policy


def enforce_mission_retry_limit(
    db: Session, task: TaskModel
) -> ProjectBudgetPolicy:
    """Refuse une relance au-delà du nombre de retries configuré.

    ``attempt_counter`` inclut la tentative initiale ; la policy compte seulement
    les tentatives supplémentaires. L'appel se fait avant l'incrément atomique du
    routeur mission et conserve sa transaction ouverte.
    """

    _, policy = _lock_policy(db, task.project_id)
    retries_used = max(int(task.attempt_counter or 0) - 1, 0)
    if retries_used >= policy.max_retries_per_mission:
        raise BudgetServiceError(
            409,
            "Plafond de relances atteint pour cette mission",
        )
    return policy


def _mission_budget(task: TaskModel) -> AutomationMissionBudget | None:
    payload = dict(task.budget or {})
    if not payload:
        return None
    try:
        return AutomationMissionBudget.model_validate(payload)
    except ValidationError as exc:
        raise BudgetServiceError(
            409, "Le budget de la mission persistée est invalide"
        ) from exc


def _day_bounds(moment: datetime, timezone_name: str) -> tuple[datetime, datetime]:
    zone = resolve_timezone(timezone_name)
    local = _as_utc(moment).astimezone(zone)
    start_local = datetime.combine(local.date(), datetime.min.time(), tzinfo=zone)
    next_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), next_local.astimezone(UTC)


def _active_reports_query(db: Session):
    return db.query(BudgetUsageReportModel).filter(
        BudgetUsageReportModel.allowed == 1,
        or_(
            BudgetUsageReportModel.kind == "usage",
            and_(
                BudgetUsageReportModel.kind == "reservation",
                BudgetUsageReportModel.reconciled_at.is_(None),
            ),
        ),
    )


def _totals(rows: Iterable[BudgetUsageReportModel]) -> _Totals:
    result = _Totals()
    for row in rows:
        result.add(row)
    return result


def _scope_totals(
    db: Session,
    context: BudgetContext,
    policy: ProjectBudgetPolicy,
    provider: str,
    moment: datetime,
) -> tuple[_Totals, _Totals, _Totals]:
    start, end = _day_bounds(moment, policy.timezone)
    base = _active_reports_query(db)
    run_totals = _totals(
        base.filter(BudgetUsageReportModel.task_run_id == context.run.id).all()
    )
    daily_totals = _totals(
        _active_reports_query(db)
        .filter(
            BudgetUsageReportModel.project_id == context.project.id,
            BudgetUsageReportModel.occurred_at >= start,
            BudgetUsageReportModel.occurred_at < end,
        )
        .all()
    )
    provider_totals = _totals(
        _active_reports_query(db)
        .filter(
            BudgetUsageReportModel.project_id == context.project.id,
            BudgetUsageReportModel.occurred_at >= start,
            BudgetUsageReportModel.occurred_at < end,
            func.lower(BudgetUsageReportModel.provider) == provider.casefold(),
        )
        .all()
    )
    return run_totals, daily_totals, provider_totals


def _request_row(body: BudgetPermitRequest) -> object:
    class Candidate:
        kind = "reservation"
        source = "provider"
        estimated = False

    candidate = Candidate()
    for name in (
        "cost",
        "currency",
        "tokens_input",
        "tokens_output",
        "tool_calls",
    ):
        setattr(candidate, name, getattr(body, name))
    return candidate


def _provider_budget(
    policy: ProjectBudgetPolicy, provider: str
) -> AutomationMissionBudget | None:
    folded = provider.casefold()
    for item in policy.provider_budgets:
        if item.provider.casefold() == folded:
            return item.budget
    return None


def _limit_scopes(
    *,
    task: TaskModel,
    policy: ProjectBudgetPolicy,
    provider: str,
    totals: tuple[_Totals, _Totals, _Totals],
) -> list[_LimitScope]:
    run_totals, daily_totals, provider_totals = totals
    result: list[_LimitScope] = []
    mission = _mission_budget(task)
    if mission is not None:
        result.append(_LimitScope("mission", mission, run_totals))
    if policy.daily_budget is not None:
        result.append(_LimitScope("daily", policy.daily_budget, daily_totals))
    provider_limit = _provider_budget(policy, provider)
    if provider_limit is not None:
        result.append(_LimitScope("provider", provider_limit, provider_totals))
    return result


def _metric(scope: _LimitScope, name: str) -> tuple[Decimal | int | None, Decimal | int | None]:
    budget = scope.budget
    totals = scope.totals
    if name == "max_cost":
        if budget.max_cost is None:
            return None, None
        currencies = totals.currencies or set()
        if not totals.cost_known or any(
            currency != budget.currency for currency in currencies
        ):
            return None, _money(budget.max_cost)
        return totals.cost, _money(budget.max_cost)
    if name == "max_tokens":
        if budget.max_tokens is None:
            return None, None
        if not totals.tokens_input_known or not totals.tokens_output_known:
            return None, int(budget.max_tokens)
        return totals.tokens_input + totals.tokens_output, int(budget.max_tokens)
    if budget.max_tool_calls is None:
        return None, None
    if not totals.tool_calls_known:
        return None, int(budget.max_tool_calls)
    return totals.tool_calls, int(budget.max_tool_calls)


def _pick_limit(
    scopes: list[_LimitScope], predicate
) -> tuple[str, _LimitScope] | None:
    for name in _LIMIT_PRIORITY:
        for scope in scopes:
            value, limit = _metric(scope, name)
            if limit is not None and predicate(value, limit):
                return name, scope
    return None


def _visible_totals(scopes: list[_LimitScope], fallback: _Totals) -> tuple:
    """Valeurs de réponse : max des portées comparées, ou portée run sans policy."""

    considered = scopes or [
        _LimitScope(
            "run",
            AutomationMissionBudget(max_tool_calls=2**31 - 1),
            fallback,
        )
    ]
    cost_scopes = [scope for scope in considered if scope.budget.max_cost is not None]
    token_scopes = [scope for scope in considered if scope.budget.max_tokens is not None]
    tool_scopes = [scope for scope in considered if scope.budget.max_tool_calls is not None]
    if not scopes:
        cost_scopes = token_scopes = tool_scopes = list(considered)

    cost: Decimal | None = None
    currency = "EUR"
    if cost_scopes:
        expected = cost_scopes[0].budget.currency
        if all(
            scope.totals.cost_known
            and not any(c != scope.budget.currency for c in (scope.totals.currencies or set()))
            for scope in cost_scopes
        ):
            cost = max(scope.totals.cost for scope in cost_scopes)
        currency = expected

    token_pair: tuple[int, int] | None = None
    complete_tokens = [
        scope.totals
        for scope in token_scopes
        if scope.totals.tokens_input_known and scope.totals.tokens_output_known
    ]
    if token_scopes and len(complete_tokens) == len(token_scopes):
        picked = max(complete_tokens, key=lambda t: t.tokens_input + t.tokens_output)
        token_pair = (picked.tokens_input, picked.tokens_output)

    tools: int | None = None
    if tool_scopes and all(scope.totals.tool_calls_known for scope in tool_scopes):
        tools = max(scope.totals.tool_calls for scope in tool_scopes)
    return cost, currency, token_pair, tools


def _verdict(
    scopes: list[_LimitScope], *, run_totals: _Totals
) -> tuple[BudgetVerdict, bool]:
    exceeded = _pick_limit(
        scopes, lambda value, limit: value is not None and value > limit
    )
    unknown = _pick_limit(scopes, lambda value, limit: value is None)
    warning = _pick_limit(
        scopes,
        lambda value, limit: (
            value is not None
            and limit > 0
            and value * 10 >= limit * 8
        ),
    )

    if exceeded is not None:
        state = "exceeded"
        limit_reached = exceeded[0]
    elif unknown is not None:
        state = "unknown"
        limit_reached = None
    elif warning is not None:
        state = "warning"
        limit_reached = warning[0]
    else:
        state = "ok"
        limit_reached = None

    cost, currency, token_pair, tools = _visible_totals(scopes, run_totals)
    tokens_input = token_pair[0] if token_pair is not None else None
    tokens_output = token_pair[1] if token_pair is not None else None
    has_measure = any(
        value is not None for value in (cost, tokens_input, tokens_output, tools)
    )
    estimated = any(scope.totals.estimated for scope in scopes) or run_totals.estimated
    measured = has_measure
    # Une somme partiellement estimée ne prouve pas un dépassement. Elle reste une
    # alerte, mais pas un constat ``exceeded`` au sens du contrat.
    if state == "exceeded" and estimated:
        state = "warning"
    verdict = BudgetVerdict(
        state=state,
        measured=measured,
        limit_reached=limit_reached,
        cost=float(cost) if cost is not None else None,
        currency=currency,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tool_calls=tools,
        usage_reported=run_totals.usage_reported,
        estimated=estimated,
    )
    permit_allowed = exceeded is None and unknown is None
    return verdict, permit_allowed


def _evaluate(
    db: Session,
    context: BudgetContext,
    policy: ProjectBudgetPolicy,
    provider: str,
    moment: datetime,
    *,
    candidate: BudgetPermitRequest | None = None,
) -> tuple[BudgetVerdict, bool]:
    totals = _scope_totals(db, context, policy, provider, moment)
    if candidate is not None:
        row = _request_row(candidate)
        for item in totals:
            item.add(row)
    scopes = _limit_scopes(
        task=context.task,
        policy=policy,
        provider=provider,
        totals=totals,
    )
    return _verdict(scopes, run_totals=totals[0])


def _normalised_provider(value: str) -> str:
    return value.strip().casefold()


def _same_number(stored: object, supplied: object) -> bool:
    if stored is None or supplied is None:
        return stored is None and supplied is None
    return Decimal(str(stored)) == Decimal(str(supplied))


def _same_permit(row: BudgetUsageReportModel, body: BudgetPermitRequest) -> bool:
    return (
        row.kind == "reservation"
        and row.provider == _normalised_provider(body.provider)
        and row.phase == body.phase
        and _same_number(row.cost, body.cost)
        and (row.currency or None) == (body.currency or None)
        and _same_number(row.tokens_input, body.tokens_input)
        and _same_number(row.tokens_output, body.tokens_output)
        and _same_number(row.tool_calls, body.tool_calls)
    )


def _same_usage(row: BudgetUsageReportModel, body: BudgetUsageDelta) -> bool:
    return (
        row.kind == "usage"
        and row.permit_id == body.permit_id
        and row.provider == _normalised_provider(body.provider)
        and row.phase == body.phase
        and row.source == body.source
        and _same_number(row.cost, body.cost)
        and (row.currency or None) == (body.currency or None)
        and _same_number(row.tokens_input, body.tokens_input)
        and _same_number(row.tokens_output, body.tokens_output)
        and _same_number(row.tool_calls, body.tool_calls)
        and bool(row.estimated) == body.estimated
    )


def _emit_budget_event(
    db: Session,
    context: BudgetContext,
    *,
    event_type: str,
    provider: str,
    phase: str,
    source: str,
    verdict: BudgetVerdict,
    permit_allowed: bool,
) -> None:
    """Journal expurgé : décision et dimensions, jamais montant ni jetons."""

    publish(
        db,
        Event(
            type=event_type,
            project_id=context.project.id,
            task_id=context.task.id,
            task_run_id=context.run.id,
            payload={
                "provider": provider,
                "phase": phase,
                "source": source,
                "state": verdict.state,
                "limit_reached": verdict.limit_reached,
                "permit_allowed": permit_allowed,
            },
        ),
        commit=False,
        forward=False,
        emitted_by="budget-service",
    )


def _maybe_alert(
    db: Session,
    context: BudgetContext,
    *,
    provider: str,
    verdict: BudgetVerdict,
) -> None:
    if verdict.state == "ok":
        return
    if verdict.state == "exceeded":
        kind, severity, title = (
            "budget.exceeded",
            "critical",
            "Plafond de budget dépassé",
        )
    elif verdict.state == "unknown":
        kind, severity, title = (
            "budget.unknown",
            "warning",
            "Mesure de budget indisponible",
        )
    else:
        kind, severity, title = (
            "budget.warning",
            "warning",
            "Budget proche de sa limite",
        )
    open_or_escalate_alert(
        db,
        project_id=context.project.id,
        kind=kind,
        severity=severity,
        title=title,
        detail=(
            "La tentative requiert une vérification de budget. "
            "Aucune donnée de consommation sensible n'est copiée dans l'alerte."
        ),
        task_id=context.task.id,
        dimensions={
            "task_id": context.task.id,
            "provider": provider,
            "limit": verdict.limit_reached or "unknown",
        },
    )


def reserve_budget(
    db: Session,
    context: BudgetContext,
    body: BudgetPermitRequest,
    *,
    now: datetime | None = None,
) -> BudgetMutationResult:
    moment = _as_utc(now or utcnow())
    _, policy = _lock_policy(db, context.project.id)
    provider = _normalised_provider(body.provider)
    existing = (
        db.query(BudgetUsageReportModel)
        .filter_by(task_run_id=context.run.id, report_id=body.permit_id)
        .with_for_update()
        .first()
    )
    if existing is not None:
        if not _same_permit(existing, body):
            raise BudgetServiceError(
                409, "Ce permit_id désigne déjà une réservation différente"
            )
        verdict, _ = _evaluate(
            db,
            context,
            policy,
            provider,
            moment,
            candidate=None if existing.allowed else body,
        )
        return BudgetMutationResult(
            accepted=True,
            idempotent=True,
            permit_allowed=bool(existing.allowed),
            verdict=verdict,
        )

    verdict, allowed = _evaluate(
        db, context, policy, provider, moment, candidate=body
    )
    row = BudgetUsageReportModel(
        task_run_id=context.run.id,
        report_id=body.permit_id,
        permit_id=body.permit_id,
        project_id=context.project.id,
        provider=provider,
        kind="reservation",
        source="provider",
        phase=body.phase,
        cost=_money(body.cost) if body.cost is not None else None,
        currency=body.currency,
        tokens_input=body.tokens_input,
        tokens_output=body.tokens_output,
        tool_calls=body.tool_calls,
        estimated=0,
        allowed=int(allowed),
        occurred_at=moment,
    )
    db.add(row)
    db.flush()
    _maybe_alert(db, context, provider=provider, verdict=verdict)
    _emit_budget_event(
        db,
        context,
        event_type="budget.permit_allowed" if allowed else "budget.permit_denied",
        provider=provider,
        phase=body.phase,
        source="provider",
        verdict=verdict,
        permit_allowed=allowed,
    )
    db.commit()
    return BudgetMutationResult(
        accepted=True,
        idempotent=False,
        permit_allowed=allowed,
        verdict=verdict,
    )


def _require_matching_permit(
    db: Session, context: BudgetContext, body: BudgetUsageDelta
) -> BudgetUsageReportModel:
    if body.permit_id is None:
        raise BudgetServiceError(409, "permit_id requis avant tout effet")
    reservation = (
        db.query(BudgetUsageReportModel)
        .filter_by(
            task_run_id=context.run.id,
            report_id=body.permit_id,
            kind="reservation",
        )
        .with_for_update()
        .first()
    )
    if reservation is None:
        raise BudgetServiceError(409, "Permis de budget introuvable")
    if not reservation.allowed:
        raise BudgetServiceError(409, "Ce permis de budget a été refusé")
    if reservation.provider != _normalised_provider(body.provider):
        raise BudgetServiceError(409, "Le fournisseur diffère du permis")
    if reservation.phase != body.phase:
        raise BudgetServiceError(409, "La phase diffère du permis")
    for name in ("cost", "tokens_input", "tokens_output", "tool_calls"):
        if getattr(reservation, name) is not None and getattr(body, name) is None:
            raise BudgetServiceError(
                409, f"Le rapport omet la mesure réservée « {name} »"
            )
    if reservation.cost is not None and reservation.currency != body.currency:
        raise BudgetServiceError(409, "La devise diffère du permis")
    return reservation


def _update_usage_cache(
    db: Session, context: BudgetContext, body: BudgetUsageDelta, moment: datetime
) -> None:
    cache = (
        db.query(BudgetUsageModel)
        .filter_by(task_run_id=context.run.id)
        .with_for_update()
        .first()
    )
    if cache is None:
        cache = BudgetUsageModel(task_run_id=context.run.id, updated_at=moment)
        db.add(cache)
        db.flush()
    if body.cost is not None:
        if cache.cost_reported and cache.currency != body.currency:
            raise BudgetServiceError(
                409, "Devise incompatible avec l'usage déjà rapporté"
            )
        if not cache.cost_reported:
            cache.currency = body.currency or "EUR"
    values: dict = {BudgetUsageModel.updated_at: moment}
    if body.cost is not None:
        values[BudgetUsageModel.cost] = BudgetUsageModel.cost + _money(body.cost)
        values[BudgetUsageModel.cost_reported] = 1
    if body.tokens_input is not None:
        values[BudgetUsageModel.tokens_input] = (
            BudgetUsageModel.tokens_input + body.tokens_input
        )
        values[BudgetUsageModel.tokens_input_reported] = 1
    if body.tokens_output is not None:
        values[BudgetUsageModel.tokens_output] = (
            BudgetUsageModel.tokens_output + body.tokens_output
        )
        values[BudgetUsageModel.tokens_output_reported] = 1
    if body.tool_calls is not None:
        values[BudgetUsageModel.tool_calls] = (
            BudgetUsageModel.tool_calls + body.tool_calls
        )
        values[BudgetUsageModel.tool_calls_reported] = 1
    if body.source == "provider" and any(
        value is not None
        for value in (body.cost, body.tokens_input, body.tokens_output)
    ):
        values[BudgetUsageModel.usage_reported] = 1
    db.query(BudgetUsageModel).filter_by(task_run_id=context.run.id).update(
        values, synchronize_session=False
    )
    db.flush()


def record_usage(
    db: Session,
    context: BudgetContext,
    body: BudgetUsageDelta,
    *,
    now: datetime | None = None,
) -> BudgetMutationResult:
    moment = _as_utc(now or utcnow())
    _, policy = _lock_policy(db, context.project.id)
    provider = _normalised_provider(body.provider)
    existing = (
        db.query(BudgetUsageReportModel)
        .filter_by(task_run_id=context.run.id, report_id=body.report_id)
        .with_for_update()
        .first()
    )
    if existing is not None:
        if not _same_usage(existing, body):
            raise BudgetServiceError(
                409, "Ce report_id désigne déjà un rapport différent"
            )
        verdict, _ = _evaluate(db, context, policy, provider, moment)
        return BudgetMutationResult(
            accepted=True,
            idempotent=True,
            permit_allowed=True,
            verdict=verdict,
        )

    reservation = _require_matching_permit(db, context, body)
    if reservation.reconciled_at is not None:
        raise BudgetServiceError(409, "Ce permis a déjà été rapproché")
    row = BudgetUsageReportModel(
        task_run_id=context.run.id,
        report_id=body.report_id,
        permit_id=body.permit_id,
        project_id=context.project.id,
        provider=provider,
        kind="usage",
        source=body.source,
        phase=body.phase,
        cost=_money(body.cost) if body.cost is not None else None,
        currency=body.currency,
        tokens_input=body.tokens_input,
        tokens_output=body.tokens_output,
        tool_calls=body.tool_calls,
        estimated=int(body.estimated),
        allowed=1,
        occurred_at=moment,
    )
    db.add(row)
    reservation.reconciled_at = moment
    db.flush()
    _update_usage_cache(db, context, body, moment)
    verdict, _ = _evaluate(db, context, policy, provider, moment)
    _maybe_alert(db, context, provider=provider, verdict=verdict)
    _emit_budget_event(
        db,
        context,
        event_type="budget.usage_recorded",
        provider=provider,
        phase=body.phase,
        source=body.source,
        verdict=verdict,
        permit_allowed=True,
    )
    db.commit()
    return BudgetMutationResult(
        accepted=True,
        idempotent=False,
        permit_allowed=True,
        verdict=verdict,
    )
