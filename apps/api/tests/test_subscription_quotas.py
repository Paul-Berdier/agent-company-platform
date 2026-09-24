"""Quotas réels d'abonnement : dépôt par un worker authentifié, lecture par le propriétaire.

Le module tourne sous SQLite par défaut et, avec ``ACP_TEST_DATABASE_URL``, dans le
schéma PostgreSQL éphémère de la session (voir ``conftest.py``). Les relevés sont
monotones : un relevé plus ancien que celui stocké n'écrase jamais un relevé plus
récent. L'usage d'un abonnement étant personnel à son titulaire, seule la personne
qui possède la plateforme lit ces valeurs.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from acp_api.main import app
from acp_api.security import create_user_session
from acp_api.routers.subscriptions import _begin_worker_write
from acp_api.subscription_quotas import ingest_reports
from acp_contracts import SubscriptionQuotaBatch, SubscriptionQuotaList
from acp_database import get_session_factory
from acp_database.models import SubscriptionQuotaSnapshotModel, UserModel, WorkerModel

REGISTRATION_TOKEN = "jeton-d-enrolement-des-quotas"
FIXTURES = Path(__file__).resolve().parents[3] / "apps" / "desktop" / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def _registration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", REGISTRATION_TOKEN)
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_GLOBAL_ACCESS", "1")
    monkeypatch.delenv("ACP_WORKER_REGISTRATION_PROJECT_ID", raising=False)
    monkeypatch.delenv("ACP_SUBSCRIPTION_QUOTA_STALE_SECONDS", raising=False)


def _register(client: TestClient, name: str | None = None) -> tuple[str, str, str]:
    name = name or f"poste-{uuid4().hex[:10]}"
    response = client.post(
        "/workers/register",
        headers={"X-Worker-Registration-Token": REGISTRATION_TOKEN},
        json={
            "name": name,
            "capabilities": [],
            "max_concurrency": 1,
            "simulation": True,
            "project_id": None,
            "global_access": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["worker_id"], body["token"], name


def _session(client: TestClient, role: str = "owner") -> None:
    with get_session_factory()() as db:
        user = UserModel(
            login_normalized=f"quotas-{role}-{uuid4().hex}",
            display_name=f"Quotas {role}",
            password_hash="non-utilisé-par-ce-test",
            platform_role=role,
        )
        db.add(user)
        db.flush()
        _, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token


def _instant(offset_seconds: int = 0) -> str:
    moment = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=offset_seconds)
    return moment.isoformat()


def _codex(observed_at: str, *, limit_id: str = "codex", used: int = 42, **overrides) -> dict:
    report = {
        "provider": "codex",
        "status": "ok",
        "source": "codex_app_server",
        "plan": "prolite",
        "limit_id": limit_id,
        "windows": [
            {
                "key": "primary",
                "used_percent": used,
                "window_minutes": 300,
                "resets_at": "2026-09-24T12:00:00Z",
            },
            {
                "key": "secondary",
                "used_percent": 7,
                "window_minutes": 10080,
                "resets_at": "2026-09-29T00:00:00Z",
            },
        ],
        "credits": {"has_credits": False, "unlimited": False, "balance": None},
        "limit_reached": False,
        "reached_type": None,
        "observed_at": observed_at,
        "detail": None,
    }
    report.update(overrides)
    return report


def _claude(observed_at: str) -> dict:
    return {
        "provider": "claude_code",
        "status": "ok",
        "source": "claude_code_statusline",
        "plan": None,
        "limit_id": "default",
        "windows": [
            {"key": "five_hour", "used_percent": 12.5, "window_minutes": 300, "resets_at": None},
            {"key": "seven_day", "used_percent": None, "window_minutes": 10080, "resets_at": None},
        ],
        "credits": None,
        "limit_reached": None,
        "reached_type": None,
        "observed_at": observed_at,
        "detail": None,
    }


def _not_signed_in(observed_at: str) -> dict:
    return {
        "provider": "codex",
        "status": "not_signed_in",
        "source": "codex_app_server",
        "limit_id": "probe",
        "observed_at": observed_at,
        "detail": "Profil Codex dédié non connecté : exécutez « codex login » avec ce profil.",
    }


def _claude_failure(observed_at: str) -> dict:
    return {
        "provider": "claude_code",
        "status": "unavailable",
        "source": "claude_code_statusline",
        "limit_id": "probe",
        "observed_at": observed_at,
        "detail": "Relevé de la ligne d'état Claude Code mal formé : quotas non relevés.",
    }


def _post(client: TestClient, worker_id: str, token: str, *reports: dict):
    return client.post(
        f"/work/workers/{worker_id}/subscription-quotas",
        headers={"Authorization": f"Bearer {token}"},
        json={"reports": list(reports)},
    )


def _owner_items(worker_id: str | None = None) -> list[dict]:
    with TestClient(app) as reader:
        _session(reader, "owner")
        response = reader.get("/subscription-quotas")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    return [item for item in items if worker_id is None or item["worker_id"] == worker_id]


# --- Dépôt par le worker ----------------------------------------------------------


def test_worker_posts_quotas_and_the_owner_reads_the_remaining_share():
    with TestClient(app) as client:
        worker_id, token, name = _register(client)
        observed = _instant(-30)
        response = _post(client, worker_id, token, _codex(observed), _claude(observed))
        assert response.status_code == 200, response.text
        assert response.json() == {"stored": 2, "ignored_older": 0, "removed": 0}

        _session(client, "owner")
        listing = client.get("/subscription-quotas")
    assert listing.status_code == 200, listing.text
    assert listing.headers["cache-control"] == "private, no-store"
    body = listing.json()
    SubscriptionQuotaList.model_validate(body)
    assert body["stale_after_seconds"] == 1800
    items = [item for item in body["items"] if item["worker_id"] == worker_id]
    assert [(item["provider"], item["limit_id"]) for item in items] == [
        ("claude_code", "default"),
        ("codex", "codex"),
    ]
    claude, codex = items
    assert codex["worker_name"] == name
    assert codex["plan"] == "prolite"
    assert codex["stale"] is False
    assert codex["observed_at"] == observed.replace("+00:00", "Z")
    assert [window["remaining_percent"] for window in codex["windows"]] == [58, 93]
    assert codex["credits"] == {"has_credits": False, "unlimited": False, "balance": None}
    assert [window["remaining_percent"] for window in claude["windows"]] == [87.5, None]
    assert claude["windows"][1]["used_percent"] is None
    assert claude["limit_reached"] is None


def test_post_requires_the_worker_own_bearer_token():
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        other_id, other_token, _ = _register(client)
        batch = {"reports": [_codex(_instant())]}
        url = f"/work/workers/{worker_id}/subscription-quotas"

        missing = client.post(url, json=batch)
        assert missing.status_code == 401
        assert missing.json()["detail"] == "Jeton worker manquant"
        wrong = client.post(url, json=batch, headers={"Authorization": f"Bearer {other_token}"})
        assert wrong.status_code == 401
        unknown = client.post(
            f"/work/workers/{uuid4()}/subscription-quotas",
            json=batch,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert unknown.status_code == 404

        with get_session_factory()() as db:
            db.get(WorkerModel, other_id).status = "revoked"
            db.commit()
        revoked = _post(client, other_id, other_token, _codex(_instant()))
        assert revoked.status_code == 403

    with get_session_factory()() as db:
        stored = db.query(SubscriptionQuotaSnapshotModel).filter(
            SubscriptionQuotaSnapshotModel.worker_id.in_([worker_id, other_id])
        ).count()
    assert stored == 0


def test_an_older_reading_never_replaces_a_newer_one_and_is_counted():
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        assert _post(client, worker_id, token, _codex(_instant(-60), used=40)).json() == {
            "stored": 1,
            "ignored_older": 0,
            "removed": 0,
        }
        older = _post(client, worker_id, token, _codex(_instant(-120), used=90))
        assert older.status_code == 200
        assert older.json() == {"stored": 0, "ignored_older": 1, "removed": 0}
        assert _owner_items(worker_id)[0]["windows"][0]["used_percent"] == 40

        newer = _post(client, worker_id, token, _codex(_instant(-10), used=55))
        assert newer.json() == {"stored": 1, "ignored_older": 0, "removed": 0}
    items = _owner_items(worker_id)
    assert len(items) == 1
    assert items[0]["windows"][0]["used_percent"] == 55
    assert items[0]["windows"][0]["remaining_percent"] == 45


def test_replaying_the_same_reading_is_idempotent():
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        report = _codex(_instant(-60))
        assert _post(client, worker_id, token, report).json()["stored"] == 1
        assert _post(client, worker_id, token, report).json() == {
            "stored": 1,
            "ignored_older": 0,
            "removed": 0,
        }
    assert len(_owner_items(worker_id)) == 1


def test_a_newer_probe_retires_the_counters_it_no_longer_reports():
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        assert _post(client, worker_id, token, _not_signed_in(_instant(-300))).json()["stored"] == 1
        signed_in = _post(
            client,
            worker_id,
            token,
            _codex(_instant(-60), limit_id="codex"),
            _codex(_instant(-60), limit_id="codex_other"),
        )
        assert signed_in.json() == {"stored": 2, "ignored_older": 0, "removed": 1}
        assert [item["limit_id"] for item in _owner_items(worker_id)] == ["codex", "codex_other"]

        # Un relevé en retard ne retire pas des compteurs plus récents que lui.
        late = _post(client, worker_id, token, _not_signed_in(_instant(-200)))
        assert late.json() == {"stored": 1, "ignored_older": 0, "removed": 0}
        assert [item["limit_id"] for item in _owner_items(worker_id)] == [
            "codex",
            "codex_other",
            "probe",
        ]
        # Une lecture Claude Code ne retire aucun compteur Codex.
        claude = _post(client, worker_id, token, _claude(_instant(-5)))
        assert claude.json() == {"stored": 1, "ignored_older": 0, "removed": 0}
    providers = sorted({item["provider"] for item in _owner_items(worker_id)})
    assert providers == ["claude_code", "codex"]


def test_a_failed_reading_never_retires_the_last_successful_counters():
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        ok = _post(client, worker_id, token, _codex(_instant(-120)), _codex(_instant(-120), limit_id="codex_other"))
        assert ok.json() == {"stored": 2, "ignored_older": 0, "removed": 0}
        failed = {
            "provider": "codex",
            "status": "unavailable",
            "source": "codex_app_server",
            "limit_id": "probe",
            "observed_at": _instant(-5),
            "detail": "L'app-server Codex n'a pas répondu dans le délai de 20 s : quotas non relevés.",
        }
        assert _post(client, worker_id, token, failed).json() == {
            "stored": 1,
            "ignored_older": 0,
            "removed": 0,
        }
    items = _owner_items(worker_id)
    assert [(item["limit_id"], item["status"]) for item in items] == [
        ("codex", "ok"),
        ("codex_other", "ok"),
        ("probe", "unavailable"),
    ]
    assert items[0]["windows"][0]["used_percent"] == 42


def test_a_failed_claude_reading_never_hides_the_last_status_line_snapshot():
    """Le fichier de la ligne d'état est daté de son écriture, avant l'échec d'une lecture.

    Scénario de la relecture indépendante : relevé réussi, lecture ratée (fichier en
    cours de réécriture), puis le même fichier relu. Le reste Claude ne disparaît
    jamais, et l'échec est retiré par la lecture réussie qui le suit.
    """

    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        written = _instant(-600)
        assert _post(client, worker_id, token, _claude(written)).json() == {
            "stored": 1,
            "ignored_older": 0,
            "removed": 0,
        }
        assert _post(client, worker_id, token, _claude_failure(_instant(-1))).json() == {
            "stored": 1,
            "ignored_older": 0,
            "removed": 0,
        }
        during = _owner_items(worker_id)
        assert [(item["limit_id"], item["status"]) for item in during] == [
            ("default", "ok"),
            ("probe", "unavailable"),
        ]
        assert during[0]["windows"][0]["remaining_percent"] == 87.5

        reread = _post(client, worker_id, token, _claude(written))
        assert reread.json() == {"stored": 1, "ignored_older": 0, "removed": 1}
    after = _owner_items(worker_id)
    assert [(item["limit_id"], item["status"]) for item in after] == [("default", "ok")]
    assert after[0]["windows"][0]["remaining_percent"] == 87.5


def test_a_failed_reading_never_replaces_the_single_codex_counter():
    """Vue historique sans ``limitId`` : le compteur « default » survit à un échec."""

    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        assert _post(client, worker_id, token, _codex(_instant(-120), limit_id="default")).json()[
            "stored"
        ] == 1
        assert _post(client, worker_id, token, _not_signed_in(_instant(-60))).json()["stored"] == 1
        items = _owner_items(worker_id)
        assert [(item["limit_id"], item["status"]) for item in items] == [
            ("default", "ok"),
            ("probe", "not_signed_in"),
        ]
        assert items[0]["windows"][0]["used_percent"] == 42

        # Une lecture en échec qui prendrait l'identité d'un compteur est refusée.
        disguised = {**_not_signed_in(_instant(-30)), "limit_id": "default"}
        refused = _post(client, worker_id, token, disguised)
        assert refused.status_code == 422
        assert "identifiant réservé « probe »" in refused.text
    assert [item["status"] for item in _owner_items(worker_id)] == ["ok", "not_signed_in"]


def test_an_old_observation_is_marked_stale_against_the_configured_threshold(
    monkeypatch: pytest.MonkeyPatch,
):
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        assert _post(client, worker_id, token, _codex(_instant(-7200))).status_code == 200
        assert _owner_items(worker_id)[0]["stale"] is True

        monkeypatch.setenv("ACP_SUBSCRIPTION_QUOTA_STALE_SECONDS", "86400")
        _session(client, "owner")
        listing = client.get("/subscription-quotas").json()
    assert listing["stale_after_seconds"] == 86400
    assert [item["stale"] for item in listing["items"] if item["worker_id"] == worker_id] == [False]


@pytest.mark.parametrize("value", ["abc", "10", "604801", "1800.5", " "])
def test_an_invalid_freshness_setting_fails_closed(monkeypatch: pytest.MonkeyPatch, value: str):
    monkeypatch.setenv("ACP_SUBSCRIPTION_QUOTA_STALE_SECONDS", value)
    with TestClient(app) as client:
        _session(client, "owner")
        response = client.get("/subscription-quotas")
    assert response.status_code == 503
    assert "ACP_SUBSCRIPTION_QUOTA_STALE_SECONDS" in response.json()["detail"]


@pytest.mark.concurrency
def test_concurrent_batches_of_one_worker_are_serialised_and_the_newest_wins():
    """Lots simultanés d'un même worker : aucun doublon, aucune erreur, le plus récent reste.

    Chaque fil ouvre sa propre session et passe par la même frontière que la route
    (authentification puis verrou d'écriture du worker).
    """

    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
    offsets = [-50, -10, -40, -20, -30, -60]
    barrier = threading.Barrier(len(offsets))
    outcomes: list[object] = []

    def send(offset: int) -> None:
        batch = SubscriptionQuotaBatch.model_validate(
            {"reports": [_codex(_instant(offset), used=abs(offset))]}
        )
        try:
            barrier.wait(10)
            with get_session_factory()() as db:
                worker = _begin_worker_write(db, worker_id, f"Bearer {token}")
                outcomes.append(ingest_reports(db, worker, batch, now=datetime.now(UTC)))
        except BaseException as exc:  # pragma: no cover - diagnostic
            outcomes.append(exc)

    threads = [threading.Thread(target=send, args=(offset,)) for offset in offsets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)

    assert all(not isinstance(outcome, BaseException) for outcome in outcomes), outcomes
    assert len(outcomes) == len(offsets)
    assert sum(outcome.stored + outcome.ignored_older for outcome in outcomes) == len(offsets)
    items = _owner_items(worker_id)
    assert len(items) == 1
    assert items[0]["windows"][0]["used_percent"] == 10


# --- Lecture réservée au propriétaire ---------------------------------------------


def test_only_the_platform_owner_reads_subscription_quotas():
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        assert _post(client, worker_id, token, _codex(_instant(-5))).status_code == 200
        anonymous = client.get("/subscription-quotas")
        assert anonymous.status_code == 401
        worker_bearer = client.get(
            "/subscription-quotas", headers={"Authorization": f"Bearer {token}"}
        )
        assert worker_bearer.status_code == 401

    for role in ("operator", "member", "viewer"):
        with TestClient(app) as client:
            _session(client, role)
            refused = client.get("/subscription-quotas")
        assert refused.status_code == 403, role
        detail = refused.json()["detail"]
        assert "propriétaire de la plateforme" in detail
        assert "personnel" in detail


# --- Refus du contrat ----------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda report: report["windows"][0].update(used_percent=150), "entre 0 et 100"),
        (lambda report: report.update(email="titulaire@example.com"), "champ inconnu refusé"),
        (
            lambda report: report.update(
                observed_at=(datetime.now(UTC) + timedelta(minutes=10)).isoformat()
            ),
            "futur",
        ),
        (lambda report: report.update(source="claude_code_statusline"), "source"),
    ],
)
def test_an_invalid_batch_is_refused_in_french_and_nothing_is_stored(mutate, expected):
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        report = _codex(_instant(-5))
        mutate(report)
        response = _post(client, worker_id, token, report, _claude(_instant(-5)))
    assert response.status_code == 422
    messages = " | ".join(error["msg"] for error in response.json()["detail"])
    assert expected in messages
    with get_session_factory()() as db:
        assert db.query(SubscriptionQuotaSnapshotModel).filter_by(worker_id=worker_id).count() == 0


def test_an_empty_or_oversized_batch_is_refused():
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        empty = client.post(
            f"/work/workers/{worker_id}/subscription-quotas",
            headers={"Authorization": f"Bearer {token}"},
            json={"reports": []},
        )
        assert empty.status_code == 422
        assert "au moins un relevé" in empty.text
        many = [_codex(_instant(-5), limit_id=f"b{index}") for index in range(17)]
        oversized = _post(client, worker_id, token, *many)
        assert oversized.status_code == 422
        assert "au maximum 16" in oversized.text


# --- Ordre et forme servie au desktop -------------------------------------------------


def test_quotas_of_every_worker_come_in_a_stable_order():
    with TestClient(app) as client:
        prefix = uuid4().hex[:8]
        second_id, second_token, _ = _register(client, f"{prefix}-b-poste")
        first_id, first_token, _ = _register(client, f"{prefix}-a-poste")
        observed = _instant(-5)
        assert _post(client, second_id, second_token, _codex(observed), _claude(observed)).status_code == 200
        assert _post(client, first_id, first_token, _codex(observed)).status_code == 200
    ours = {first_id, second_id}
    first_read = [
        (item["provider"], item["limit_id"], item["worker_name"])
        for item in _owner_items()
        if item["worker_id"] in ours
    ]
    assert first_read == [
        ("claude_code", "default", f"{prefix}-b-poste"),
        ("codex", "codex", f"{prefix}-a-poste"),
        ("codex", "codex", f"{prefix}-b-poste"),
    ]
    second_read = [
        (item["provider"], item["limit_id"], item["worker_name"])
        for item in _owner_items()
        if item["worker_id"] in ours
    ]
    assert second_read == first_read


def _shape(value):
    if isinstance(value, dict):
        return {key: _shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_shape(child) for child in value]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


def test_desktop_fixture_has_exactly_the_shape_served_by_the_api():
    """Forme de référence pour le client natif, figée contre la réponse réelle."""

    fixture = json.loads((FIXTURES / "subscription-quotas.json").read_text(encoding="utf-8"))
    SubscriptionQuotaList.model_validate(fixture)
    with TestClient(app) as client:
        worker_id, token, _ = _register(client)
        observed = _instant(-5)
        assert _post(client, worker_id, token, _claude(observed), _codex(observed)).status_code == 200
        # Un échec n'est jamais dans le même lot que les compteurs de son fournisseur.
        assert _post(client, worker_id, token, _not_signed_in(observed)).status_code == 200
        _session(client, "owner")
        served = client.get("/subscription-quotas").json()
    served["items"] = [item for item in served["items"] if item["worker_id"] == worker_id]
    assert _shape(fixture) == _shape(served)
