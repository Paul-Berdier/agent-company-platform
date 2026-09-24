"""Table des derniers relevés de quotas d'abonnement, sur le dialecte de test courant.

Sans ``ACP_TEST_DATABASE_URL`` ces tests tournent sous SQLite ; avec, dans un schéma
PostgreSQL éphémère. Les mêmes garanties doivent tenir sur les deux dialectes :
un seul relevé par (worker, fournisseur, compteur), des énumérations fermées et
l'effacement des relevés avec leur worker.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from acp_database.models import SubscriptionQuotaSnapshotModel, WorkerModel

UTC = timezone.utc


def _worker(name: str) -> WorkerModel:
    return WorkerModel(
        name=name,
        token_hash="a" * 64,
        token_prefix="prefix",
        token_expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        capabilities=[],
        simulation=1,
        global_access=1,
    )


def _snapshot(worker_id: str, **overrides) -> SubscriptionQuotaSnapshotModel:
    observed = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)
    values = {
        "worker_id": worker_id,
        "provider": "codex",
        "limit_id": "codex",
        "status": "ok",
        "source": "codex_app_server",
        "plan": "prolite",
        "windows": [
            {
                "key": "primary",
                "used_percent": 42,
                "window_minutes": 300,
                "resets_at": "2026-09-24T12:00:00Z",
            }
        ],
        "credits": {"has_credits": False, "unlimited": False, "balance": None},
        "limit_reached": 0,
        "reached_type": None,
        "detail": None,
        "observed_at": observed,
        "received_at": observed + timedelta(seconds=2),
    }
    values.update(overrides)
    return SubscriptionQuotaSnapshotModel(**values)


def test_snapshot_table_declares_its_constraints(test_engine):
    inspector = inspect(test_engine)
    columns = {column["name"]: column for column in inspector.get_columns("subscription_quota_snapshots")}
    assert {
        "id",
        "created_at",
        "worker_id",
        "provider",
        "limit_id",
        "status",
        "source",
        "plan",
        "windows",
        "credits",
        "limit_reached",
        "reached_type",
        "detail",
        "observed_at",
        "received_at",
    } == set(columns)
    for nullable in ("plan", "credits", "limit_reached", "reached_type", "detail"):
        assert columns[nullable]["nullable"] is True
    for required in ("worker_id", "provider", "limit_id", "status", "source", "windows", "observed_at", "received_at"):
        assert columns[required]["nullable"] is False
    uniques = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("subscription_quota_snapshots")
    }
    assert ("worker_id", "provider", "limit_id") in uniques
    foreign_keys = inspector.get_foreign_keys("subscription_quota_snapshots")
    assert [
        (fk["referred_table"], fk["constrained_columns"], (fk.get("options") or {}).get("ondelete"))
        for fk in foreign_keys
    ] == [("workers", ["worker_id"], "CASCADE")]
    checks = {check["name"] for check in inspector.get_check_constraints("subscription_quota_snapshots")}
    assert {
        "ck_subscription_quota_provider",
        "ck_subscription_quota_status",
        "ck_subscription_quota_source",
        "ck_subscription_quota_limit_reached",
    } <= checks


def test_one_snapshot_per_worker_provider_and_counter(test_engine):
    with Session(test_engine) as db:
        worker = _worker("quota-unique")
        db.add(worker)
        db.flush()
        db.add(_snapshot(worker.id))
        db.add(_snapshot(worker.id, limit_id="codex_other"))
        db.add(_snapshot(worker.id, provider="claude_code", source="claude_code_statusline", limit_id="codex"))
        db.commit()

        db.add(_snapshot(worker.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(SubscriptionQuotaSnapshotModel.id).limit(1)) is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider": "chatgpt"},
        {"status": "estimated"},
        {"source": "codex_session_log"},
        {"limit_reached": 2},
    ],
)
def test_closed_values_are_enforced_by_the_database(test_engine, overrides):
    with Session(test_engine) as db:
        worker = _worker(f"quota-check-{next(iter(overrides))}")
        db.add(worker)
        db.flush()
        db.add(_snapshot(worker.id, **overrides))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_snapshots_are_erased_with_their_worker(test_engine):
    with Session(test_engine) as db:
        kept = _worker("quota-kept")
        erased = _worker("quota-erased")
        db.add_all([kept, erased])
        db.flush()
        db.add_all([_snapshot(kept.id), _snapshot(erased.id), _snapshot(erased.id, limit_id="other")])
        db.commit()
        erased_id = erased.id
        kept_id = kept.id

    with Session(test_engine) as db:
        db.execute(delete(WorkerModel).where(WorkerModel.id == erased_id))
        db.commit()
        remaining = db.scalars(select(SubscriptionQuotaSnapshotModel.worker_id)).all()
    assert remaining == [kept_id]


def test_snapshot_instants_round_trip_in_utc_and_naive_ones_are_refused(test_engine):
    paris = timezone(timedelta(hours=2))
    with Session(test_engine) as db:
        worker = _worker("quota-utc")
        db.add(worker)
        db.flush()
        observed = datetime(2026, 9, 24, 10, 0, tzinfo=paris)
        db.add(_snapshot(worker.id, observed_at=observed, received_at=observed))
        db.commit()
        db.expire_all()
        stored = db.scalars(select(SubscriptionQuotaSnapshotModel)).one()
        assert stored.observed_at == observed
        assert stored.observed_at.utcoffset() == timedelta(0)

        db.add(_snapshot(worker.id, limit_id="naive", observed_at=datetime(2026, 9, 24, 8, 0)))
        with pytest.raises(StatementError, match="fuseau"):
            db.commit()
        db.rollback()
