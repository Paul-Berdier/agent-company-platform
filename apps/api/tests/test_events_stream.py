"""Journal d'événements durable, lecture par curseur et flux SSE authentifié (Lot E).

Ces tests verrouillent les garanties du §12 de la spécification : séquence monotone
sous concurrence, page par curseur, reprise SSE par ``Last-Event-ID`` sans doublon ni
perte, RBAC inter-projets sur la page comme sur le flux, fermeture après révocation de
session ou perte de membership, refus au-delà de la limite de connexions, et absence de
média embarqué dans un événement.

Deux niveaux de vérification, parce que le ``TestClient`` de Starlette **bufferise** une
réponse en flux (il exécute l'application jusqu'au bout avant de rendre la main) :

- les routes sont vérifiées via ``TestClient`` avec une durée de flux volontairement
  minuscule (en-têtes, RBAC, reprise, rotation, quota) ;
- les comportements réellement « vivants » (livraison pendant la connexion, fermeture
  après révocation, keep-alive périodique) sont vérifiés en consommant directement le
  générateur ``run_event_stream``.

Aucun serveur réel n'est lancé et aucune lecture n'est illimitée : chaque attente est
bornée par un délai explicite.
"""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from acp_api import events_bus
from acp_api.deps import get_db
from acp_api.events_bus import (
    MEDIA_PAYLOAD_KEYS,
    PAYLOAD_MAX_BYTES,
    PAYLOAD_MAX_DEPTH,
    SEQUENCE_ALLOCATION_ATTEMPTS,
    EventHub,
    MediaPayloadRefused,
    SequenceAllocationError,
    allocate_sequence,
    media_reference_payload,
    publish,
    store_event,
)
from acp_api.main import app
from acp_api.security import create_user_session, hash_password, utcnow
from acp_api.streams import (
    project_cursor,
    project_event_stream,
    run_event_stream,
    stream_connections,
    stream_policy,
)
from acp_contracts import Event
from acp_database.models import (
    Base,
    EventModel,
    MembershipModel,
    TaskRunModel,
    UserModel,
    UserSessionModel,
)
from acp_database.testing import make_test_engine

PASSWORD = "correct horse battery staple"
FAST_STREAM_ENVIRON = {
    "ACP_STREAM_POLL_INTERVAL_MS": "20",
    "ACP_STREAM_KEEPALIVE_SECONDS": "30",
    "ACP_STREAM_MAX_SECONDS": "5",
    "ACP_STREAM_MAX_CONNECTIONS_PER_USER": "4",
}


# --- Fixtures ----------------------------------------------------------------


def _create_member(session_factory, project_id: str) -> dict[str, str]:
    """Crée un utilisateur non-owner membre d'un seul projet, avec sa session."""

    with session_factory() as db:
        user = UserModel(
            login_normalized=f"membre-{uuid4().hex}",
            display_name="Membre de projet",
            password_hash=hash_password(PASSWORD),
            platform_role="member",
            password_changed_at=utcnow(),
        )
        db.add(user)
        db.flush()
        db.add(
            MembershipModel(
                user_id=user.id,
                scope_type="project",
                scope_id=project_id,
                role="member",
            )
        )
        _, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
        return {
            "user_id": user.id,
            "session_token": session_token,
            "csrf_token": csrf_token,
        }


@pytest.fixture
def stream_context(monkeypatch, tmp_path):
    bootstrap_token = f"bootstrap-{uuid4().hex}"
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", bootstrap_token)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("ACP_STREAM_POLL_INTERVAL_MS", "20")
    monkeypatch.setenv("ACP_STREAM_KEEPALIVE_SECONDS", "30")
    monkeypatch.setenv("ACP_STREAM_MAX_SECONDS", "0.3")
    monkeypatch.setenv("ACP_STREAM_MAX_CONNECTIONS_PER_USER", "4")
    monkeypatch.delenv("ACP_STREAM_BATCH", raising=False)
    monkeypatch.delenv("ACP_EVENT_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("ACP_EVENT_RETENTION_DAYS", raising=False)

    database = make_test_engine(tmp_path, concurrent=True, create_schema=False)
    engine = database.engine
    if engine.dialect.name == "sqlite":
        # Test uniquement : supprimer les ``fsync`` divise par six le coût du schéma.
        # ``synchronous=OFF`` ne touche pas au verrouillage (journal de reprise
        # conservé, pas de WAL) : la concurrence réelle vérifiée plus bas reste
        # représentative. Le moteur mémoire n'a rien à synchroniser ; le fichier
        # ``concurrent`` ci-dessous en profite.
        @sqlalchemy_event.listens_for(engine, "connect")
        def _unsynchronized_sqlite(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.close()

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    events_bus.event_hub.reset()
    stream_connections.reset()
    try:
        with TestClient(app) as client:
            bootstrap = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": bootstrap_token},
                json={
                    "login": f"owner-{uuid4().hex}",
                    "display_name": "Propriétaire du flux",
                    "password": PASSWORD,
                },
            )
            assert bootstrap.status_code == 201
            client.headers["X-CSRF-Token"] = bootstrap.json()["csrf_token"]
            organization = client.post("/organizations", json={"name": "Org flux"}).json()
            workspace = client.post(
                "/workspaces",
                json={"organization_id": organization["id"], "name": "Ws flux"},
            ).json()
            project_a = client.post(
                "/projects", json={"workspace_id": workspace["id"], "name": "Projet A"}
            ).json()
            project_b = client.post(
                "/projects", json={"workspace_id": workspace["id"], "name": "Projet B"}
            ).json()
            agent = client.post(
                "/agents",
                json={
                    "workspace_id": workspace["id"],
                    "name": "Agent flux",
                    "role_id": "developer",
                },
            ).json()
            task_a = client.post(
                "/tasks",
                json={
                    "project_id": project_a["id"],
                    "agent_instance_id": agent["id"],
                    "title": "Tâche A",
                },
            ).json()
            task_b = client.post(
                "/tasks",
                json={
                    "project_id": project_b["id"],
                    "agent_instance_id": agent["id"],
                    "title": "Tâche B",
                },
            ).json()
            with session_factory() as db:
                run_a = TaskRunModel(
                    task_id=task_a["id"],
                    agent_instance_id=agent["id"],
                    status="running",
                    attempt_number=1,
                    fencing_token=1,
                )
                sibling_a = TaskRunModel(
                    task_id=task_a["id"],
                    agent_instance_id=agent["id"],
                    status="running",
                    attempt_number=2,
                    fencing_token=2,
                )
                run_b = TaskRunModel(
                    task_id=task_b["id"],
                    agent_instance_id=agent["id"],
                    status="running",
                    attempt_number=1,
                    fencing_token=1,
                )
                db.add_all([run_a, sibling_a, run_b])
                db.commit()
                run_a_id, sibling_a_id, run_b_id = run_a.id, sibling_a.id, run_b.id
                owner_id = (
                    db.query(UserModel.id).filter_by(platform_role="owner").first()[0]
                )

            context = {
                "client": client,
                "session_factory": session_factory,
                "owner_id": owner_id,
                "project_a": project_a["id"],
                "project_b": project_b["id"],
                "task_a": task_a["id"],
                "task_b": task_b["id"],
                "run_a": run_a_id,
                "sibling_a": sibling_a_id,
                "run_b": run_b_id,
                "alice": _create_member(session_factory, project_a["id"]),
                "mallory": _create_member(session_factory, project_b["id"]),
            }
            yield context
    finally:
        app.dependency_overrides.pop(get_db, None)
        events_bus.event_hub.reset()
        stream_connections.reset()
        database.close()


def _authenticate(client: TestClient, member: dict[str, str]) -> None:
    client.cookies.clear()
    client.cookies.set("acp_session", member["session_token"])
    client.headers["X-CSRF-Token"] = member["csrf_token"]


def _publish(
    context,
    *,
    run_id: str | None,
    project_id: str,
    event_type: str = "task.progress",
    payload: dict | None = None,
) -> int | None:
    with context["session_factory"]() as db:
        return publish(
            db,
            Event(
                type=event_type,
                project_id=project_id,
                task_run_id=run_id,
                payload=payload or {},
            ),
            executor="platform",
            emitted_by="api",
        )


def _publish_burst(
    context,
    *,
    run_id: str,
    project_id: str,
    count: int,
    event_type: str = "task.progress",
) -> list[str]:
    """Publie une rafale dans **une seule** transaction et rend les identifiants écrits.

    C'est la forme que produit ``testing_service`` : plusieurs événements écrits d'un
    coup, donc plusieurs lignes qui partagent la même microseconde d'écriture sur une
    horloge à faible granularité (Windows : ~1,5 ms).
    """

    identifiers: list[str] = []
    with context["session_factory"]() as db:
        for index in range(count):
            event = Event(
                type=event_type,
                project_id=project_id,
                task_run_id=run_id,
                payload={"index": index},
            )
            publish(db, event, commit=False, forward=False, emitted_by="api")
            identifiers.append(event.id)
        db.commit()
    return identifiers


def _collapse_created_at(context, event_ids: list[str]) -> None:
    """Fait partager une **seule** microseconde à ces lignes, de façon déterministe.

    Une rafale réelle produit le même groupe d'égalité, mais seulement quand l'horloge
    le veut bien : ce forçage retire l'aléa du test sans changer la forme des données.
    """

    with context["session_factory"]() as db:
        rows = db.query(EventModel).filter(EventModel.id.in_(event_ids)).all()
        moment = max(row.created_at for row in rows)
        db.query(EventModel).filter(EventModel.id.in_(event_ids)).update(
            {EventModel.created_at: moment}, synchronize_session=False
        )
        db.commit()


def _journal_cursor(context, event_id: str) -> int:
    """Curseur de portée projet d'une ligne, lu en base plutôt que deviné."""

    with context["session_factory"]() as db:
        row = db.get(EventModel, event_id)
        assert row is not None and row.journal_seq is not None
        return int(row.journal_seq)


def _seed_run_events(
    context, *, run_id: str, project_id: str, count: int
) -> tuple[int, int]:
    """Constitue un retard de lecture directement en base, sans passer par ``publish``.

    Le test qui s'en sert porte sur la borne de durée du flux, pas sur l'allocation de
    séquence — déjà verrouillée par ailleurs. Rend ``(première séquence, nombre)``.
    """

    with context["session_factory"]() as db:
        start = allocate_sequence(db, run_id)
        db.add_all(
            [
                EventModel(
                    type="task.progress",
                    occurred_at=utcnow(),
                    project_id=project_id,
                    task_run_id=run_id,
                    payload={"index": index},
                    sequence=start + index,
                )
                for index in range(count)
            ]
        )
        db.commit()
    return start, count


def _project_event_ids(context, project_id: str, *, after: int) -> list[str]:
    """Identifiants écrits pour ce projet, dans l'ordre du journal, lus directement."""

    with context["session_factory"]() as db:
        rows = (
            db.query(EventModel.id)
            .filter(
                EventModel.project_id == project_id,
                EventModel.journal_seq.is_not(None),
                EventModel.journal_seq > after,
            )
            .order_by(EventModel.journal_seq.asc())
            .all()
        )
    return [row[0] for row in rows]


def _drain_project_pages(
    client: TestClient,
    project_id: str,
    *,
    cursor: int,
    limit: int,
    max_pages: int = 400,
) -> tuple[list[str], dict]:
    """Parcourt la page projet jusqu'à épuisement, sans jamais boucler indéfiniment."""

    delivered: list[str] = []
    page: dict = {}
    for _ in range(max_pages):
        page = client.get(
            f"/projects/{project_id}/events",
            params={"after_seq": cursor, "limit": limit},
        ).json()
        delivered.extend(event["id"] for event in page["events"])
        if not page["has_more"]:
            return delivered, page
        assert page["next_cursor"] is not None
        assert page["next_cursor"] > cursor, "curseur immobile : pagination bloquée"
        cursor = page["next_cursor"]
    raise AssertionError("pagination non convergente : trop de pages")


def _parse_sse(payload: str) -> tuple[list[dict[str, str]], list[str]]:
    """Découpe un flux SSE en trames et commentaires, sans rien supposer d'autre."""

    frames: list[dict[str, str]] = []
    comments: list[str] = []
    current: dict[str, str] = {}
    for raw in payload.split("\n"):
        line = raw.rstrip("\r")
        if line == "":
            if current:
                frames.append(current)
                current = {}
            continue
        if line.startswith(":"):
            comments.append(line[1:].strip())
            continue
        field, _, value = line.partition(":")
        current[field] = value[1:] if value.startswith(" ") else value
    if current:
        frames.append(current)
    return frames, comments


def _sequences(frames) -> list[int]:
    return [
        json.loads(frame["data"])["sequence"]
        for frame in frames
        if frame.get("event") == "acp.event"
    ]


def _page_sequences(page) -> list[int]:
    return [event["sequence"] for event in page["events"]]


class _StreamReader:
    """Consomme un générateur SSE avec une attente **toujours** bornée."""

    def __init__(self, stream) -> None:
        self._stream = stream
        self._payload = ""
        self.frames: list[dict[str, str]] = []
        self.comments: list[str] = []
        self.exhausted = False

    async def until(
        self, *, frames: int = 0, comments: int = 0, timeout: float = 5.0
    ) -> None:
        deadline = monotonic() + timeout
        while len(self.frames) < frames or len(self.comments) < comments:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return
            try:
                chunk = await asyncio.wait_for(
                    self._stream.__anext__(), timeout=remaining
                )
            except StopAsyncIteration:
                self.exhausted = True
                return
            except TimeoutError:
                return
            self._payload += chunk.decode("utf-8")
            self.frames, self.comments = _parse_sse(self._payload)

    async def drain(self, *, timeout: float = 5.0) -> None:
        """Consomme jusqu'à la fin du générateur, sans jamais dépasser ``timeout``."""

        deadline = monotonic() + timeout
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return
            try:
                chunk = await asyncio.wait_for(
                    self._stream.__anext__(), timeout=remaining
                )
            except StopAsyncIteration:
                self.exhausted = True
                return
            except TimeoutError:
                return
            self._payload += chunk.decode("utf-8")
            self.frames, self.comments = _parse_sse(self._payload)

    async def aclose(self) -> None:
        await self._stream.aclose()


def _member_policy(context, member_key: str, *, run_id: str | None, project_id: str, **overrides):
    member = context[member_key]
    environ = dict(FAST_STREAM_ENVIRON)
    environ.update(overrides)
    return stream_policy(
        user_id=member["user_id"],
        session_token=member["session_token"],
        project_id=project_id,
        run_id=run_id,
        environ=environ,
    )


# --- 1. Séquence allouée dans la transaction métier --------------------------


def test_a_run_sequence_starts_at_one_and_stays_contiguous(stream_context):
    """La première séquence d'une tentative vaut 1 puis progresse de 1 en 1."""

    run_id = stream_context["run_a"]
    sequences = [
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
        for _ in range(4)
    ]

    assert sequences == [1, 2, 3, 4]


def test_two_runs_have_independent_sequences(stream_context):
    """Une séquence est propre à la tentative : deux runs repartent de 1."""

    first = _publish(
        stream_context,
        run_id=stream_context["run_a"],
        project_id=stream_context["project_a"],
    )
    second = _publish(
        stream_context,
        run_id=stream_context["sibling_a"],
        project_id=stream_context["project_a"],
    )

    assert (first, second) == (1, 1)


def test_concurrent_publishers_on_one_run_get_distinct_contiguous_sequences(
    stream_context,
):
    """Douze fils publiant sur la même tentative produisent 1..12, sans trou ni doublon."""

    run_id = stream_context["run_a"]
    project_id = stream_context["project_a"]
    threads = 12
    barrier = threading.Barrier(threads)

    def publish_one(index: int) -> int:
        barrier.wait(timeout=10)
        with stream_context["session_factory"]() as db:
            return publish(
                db,
                Event(
                    type="task.progress",
                    project_id=project_id,
                    task_run_id=run_id,
                    payload={"index": index},
                ),
            )

    with ThreadPoolExecutor(max_workers=threads) as pool:
        allocated = sorted(pool.map(publish_one, range(threads)))

    assert allocated == list(range(1, threads + 1))
    with stream_context["session_factory"]() as db:
        stored = sorted(
            sequence
            for (sequence,) in db.query(EventModel.sequence)
            .filter_by(task_run_id=run_id)
            .all()
        )
    assert stored == list(range(1, threads + 1))


def test_an_event_without_a_run_is_stored_without_a_sequence(stream_context):
    """Un événement hors tentative reste accepté : l'unicité de séquence est partielle."""

    sequence = _publish(
        stream_context, run_id=None, project_id=stream_context["project_a"]
    )

    assert sequence is None
    with stream_context["session_factory"]() as db:
        rows = db.query(EventModel).filter_by(task_run_id=None, type="task.progress").all()
    assert [row.sequence for row in rows] == [None]


def test_sequence_allocation_gives_up_after_five_attempts(stream_context, monkeypatch):
    """Une collision permanente s'arrête après cinq essais, sans boucle infinie."""

    run_id = stream_context["run_a"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    attempts: list[int] = []

    def always_one(db, task_run_id):
        attempts.append(1)
        return 1

    monkeypatch.setattr(events_bus, "allocate_sequence", always_one)

    with stream_context["session_factory"]() as db:
        with pytest.raises(SequenceAllocationError):
            publish(
                db,
                Event(
                    type="task.progress",
                    project_id=stream_context["project_a"],
                    task_run_id=run_id,
                ),
            )

    assert len(attempts) == SEQUENCE_ALLOCATION_ATTEMPTS == 5


def test_a_sequence_collision_is_replayed_until_it_succeeds(stream_context, monkeypatch):
    """Une allocation périmée n'est pas perdue : elle est rejouée et aboutit."""

    run_id = stream_context["run_a"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    genuine = events_bus.allocate_sequence
    calls: list[int] = []

    def stale_then_genuine(db, task_run_id):
        calls.append(1)
        if len(calls) == 1:
            return 1  # numéro déjà pris par une autre transaction
        return genuine(db, task_run_id)

    monkeypatch.setattr(events_bus, "allocate_sequence", stale_then_genuine)

    with stream_context["session_factory"]() as db:
        sequence = publish(
            db,
            Event(
                type="task.progress",
                project_id=stream_context["project_a"],
                task_run_id=run_id,
            ),
        )

    assert (sequence, len(calls)) == (2, 2)
    with stream_context["session_factory"]() as db:
        stored = sorted(
            value
            for (value,) in db.query(EventModel.sequence).filter_by(task_run_id=run_id).all()
        )
    assert stored == [1, 2]


def test_allocate_sequence_reads_the_next_free_number(stream_context):
    """``allocate_sequence`` ne consomme rien : elle rend le prochain numéro libre."""

    run_id = stream_context["run_a"]
    with stream_context["session_factory"]() as db:
        assert allocate_sequence(db, run_id) == 1
        assert allocate_sequence(db, run_id) == 1
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    with stream_context["session_factory"]() as db:
        assert allocate_sequence(db, run_id) == 2


def test_a_foreign_integrity_error_is_reported_as_is(stream_context):
    """Seule une collision de séquence est rejouée : une autre violation remonte telle quelle."""

    run_id = stream_context["run_a"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    with stream_context["session_factory"]() as db:
        existing_id = db.query(EventModel).filter_by(task_run_id=run_id).one().id

    with stream_context["session_factory"]() as db:
        with pytest.raises(IntegrityError):
            publish(
                db,
                Event(
                    id=existing_id,
                    type="task.progress",
                    project_id=stream_context["project_a"],
                    task_run_id=run_id,
                ),
            )


def test_the_integrity_error_of_a_duplicate_sequence_is_the_retry_signal(stream_context):
    """Le doublon de séquence remonte en ``IntegrityError`` : c'est le signal de réessai."""

    run_id = stream_context["run_a"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    with stream_context["session_factory"]() as db:
        db.add(EventModel(type="task.progress", task_run_id=run_id, sequence=1))
        with pytest.raises(IntegrityError):
            db.commit()


# --- 2. Transaction de l'appelant --------------------------------------------


def test_store_event_commits_by_default_for_existing_callers(stream_context):
    """Les appelants du Lot C n'ont rien changé : ``store_event`` valide la transaction."""

    with stream_context["session_factory"]() as db:
        store_event(
            db, Event(type="journal.direct", project_id=stream_context["project_a"])
        )
    with stream_context["session_factory"]() as db:
        assert db.query(EventModel).filter_by(type="journal.direct").count() == 1


def test_an_event_written_without_publish_still_enters_the_project_cursor(stream_context):
    """Un appelant direct de ``store_event`` reste lisible dans la portée projet.

    Les routeurs du Lot C écrivent sans passer par ``publish`` : sans numéro de
    journal, leurs événements sortiraient purement et simplement de la page projet.
    """

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    event = Event(type="agent.status_changed", project_id=project_id)
    with stream_context["session_factory"]() as db:
        store_event(db, event)

    page = client.get(
        f"/projects/{project_id}/events", params={"after_seq": cursor}
    ).json()
    assert [rendered["id"] for rendered in page["events"]] == [event.id]
    assert _journal_cursor(stream_context, event.id) > cursor


def test_an_event_written_without_publish_still_enters_the_run_cursor(stream_context):
    """Un événement terminal du Lot C reste lisible dans la portée tentative.

    ``routers/work.py`` et ``routers/missions.py`` écrivent leurs événements de cycle
    de vie par ``store_event``. Sans séquence de tentative, ``task.completed`` et ses
    pairs sortiraient de ``GET /runs/{id}/events`` **et** du flux : le Studio
    n'apprendrait jamais qu'une mission est terminée.
    """

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    event = Event(
        type="task.completed",
        project_id=stream_context["project_a"],
        task_id=stream_context["task_a"],
        task_run_id=run_id,
    )
    with stream_context["session_factory"]() as db:
        store_event(db, event)

    page = client.get(f"/runs/{run_id}/events").json()
    assert [rendered["id"] for rendered in page["events"]] == [event.id]
    assert page["events"][0]["sequence"] == 1
    assert page["has_more"] is False
    assert page["next_cursor"] == 1


def test_a_terminal_event_of_lot_c_is_delivered_by_the_run_stream(stream_context):
    """Le même événement doit traverser le flux SSE de la tentative, pas seulement la page."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    event = Event(
        type="task.failed",
        project_id=stream_context["project_a"],
        task_id=stream_context["task_a"],
        task_run_id=run_id,
    )
    with stream_context["session_factory"]() as db:
        store_event(db, event)

    response = client.get(f"/streams/runs/{run_id}")
    frames, _ = _parse_sse(response.text)
    served = [
        json.loads(frame["data"])
        for frame in frames
        if frame.get("event") == "acp.event"
    ]

    assert [rendered["id"] for rendered in served] == [event.id]
    assert [rendered["type"] for rendered in served] == ["task.failed"]


def test_a_run_sequence_provided_by_the_caller_is_never_reallocated(stream_context):
    """``publish`` alloue déjà ses deux numéros : ``store_event`` ne les recalcule pas."""

    run_id = stream_context["run_a"]
    with stream_context["session_factory"]() as db:
        publish(
            db,
            Event(
                type="task.progress",
                project_id=stream_context["project_a"],
                task_run_id=run_id,
            ),
        )
    event = Event(
        type="task.progress",
        project_id=stream_context["project_a"],
        task_run_id=run_id,
    )
    with stream_context["session_factory"]() as db:
        stored = store_event(db, event, sequence=7)
        assert stored.sequence == 7

    with stream_context["session_factory"]() as db:
        rows = (
            db.query(EventModel.sequence)
            .filter(EventModel.task_run_id == run_id)
            .order_by(EventModel.sequence.asc())
            .all()
        )
    assert [row[0] for row in rows] == [1, 7]


def test_an_event_without_a_run_takes_part_in_the_project_cursor(stream_context):
    """Sans tentative, donc sans séquence, un événement garde son rang dans le journal."""

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    with_run = Event(
        type="task.progress", project_id=project_id, task_run_id=stream_context["run_a"]
    )
    without_run = Event(type="project.updated", project_id=project_id)
    for event in (with_run, without_run):
        with stream_context["session_factory"]() as db:
            assert publish(db, event) is (None if event is without_run else 1)

    page = client.get(
        f"/projects/{project_id}/events", params={"after_seq": cursor}
    ).json()
    assert [rendered["id"] for rendered in page["events"]] == [
        with_run.id,
        without_run.id,
    ]
    assert [rendered["sequence"] for rendered in page["events"]] == [1, None]


def test_the_project_cursor_is_the_journal_counter_not_the_clock():
    """``project_cursor`` rend ``journal_seq``, et ``None`` pour une ligne non numérotée."""

    numbered = EventModel(type="task.progress", occurred_at=utcnow(), journal_seq=42)
    unnumbered = EventModel(type="task.progress", occurred_at=utcnow())

    assert project_cursor(numbered) == 42
    assert project_cursor(unnumbered) is None


def test_an_unnumbered_row_is_left_out_of_the_project_page_without_failing(stream_context):
    """Une ligne sans numéro de journal est exclue, jamais une exception.

    Cas d'une base dont la migration n'a pas encore tourné : la lecture doit rester
    définie plutôt que de refuser la page entière.
    """

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    numbered = _publish(
        stream_context, run_id=stream_context["run_a"], project_id=project_id
    )
    assert numbered == 1
    with stream_context["session_factory"]() as db:
        db.add(
            EventModel(
                id="sans-numero",
                type="task.progress",
                occurred_at=utcnow(),
                project_id=project_id,
                payload={},
            )
        )
        db.commit()

    page = client.get(
        f"/projects/{project_id}/events", params={"after_seq": cursor}
    ).json()

    assert "sans-numero" not in [rendered["id"] for rendered in page["events"]]
    assert len(page["events"]) == 1


def test_store_event_leaves_the_transaction_to_its_caller(stream_context):
    """``commit=False`` n'écrit rien tant que l'appelant n'a pas validé sa transaction."""

    with stream_context["session_factory"]() as db:
        store_event(
            db,
            Event(type="test.run.started", project_id=stream_context["project_a"]),
            commit=False,
        )
        with stream_context["session_factory"]() as observer:
            assert observer.query(EventModel).filter_by(type="test.run.started").count() == 0
        db.commit()
    with stream_context["session_factory"]() as db:
        assert db.query(EventModel).filter_by(type="test.run.started").count() == 1


def test_a_rolled_back_transaction_publishes_nothing(stream_context):
    """Un ``rollback`` de l'appelant retire aussi l'événement : pas de journal fantôme."""

    run_id = stream_context["run_a"]
    with stream_context["session_factory"]() as db:
        publish(
            db,
            Event(
                type="task.progress",
                project_id=stream_context["project_a"],
                task_run_id=run_id,
            ),
            commit=False,
        )
        db.rollback()
    with stream_context["session_factory"]() as db:
        assert db.query(EventModel).filter_by(task_run_id=run_id).count() == 0


def test_a_deferred_publication_is_visible_only_after_the_caller_commits(stream_context):
    """``publish(commit=False)`` s'insère dans la transaction de son appelant.

    Depuis 0.9.1, ses numéros n'existent qu'au commit : ``publish`` ne peut donc pas
    rendre de séquence, et la ligne n'en porte pas avant le commit.
    """

    run_id = stream_context["run_a"]
    with stream_context["session_factory"]() as db:
        sequence = publish(
            db,
            Event(
                type="test.case.finished",
                project_id=stream_context["project_a"],
                task_run_id=run_id,
            ),
            commit=False,
        )
        assert sequence is None
        with stream_context["session_factory"]() as observer:
            assert observer.query(EventModel).filter_by(task_run_id=run_id).count() == 0
        db.commit()
    with stream_context["session_factory"]() as db:
        row = db.query(EventModel).filter_by(task_run_id=run_id).one()
        assert row.sequence == 1 and row.journal_seq is not None


# --- 3. Aucun média dans le journal ------------------------------------------


def test_a_media_payload_carries_only_an_artifact_reference():
    """Le payload d'un événement de média ne porte qu'une référence d'artefact."""

    payload = media_reference_payload(
        artifact_id="11111111-1111-4111-8111-111111111111",
        content_type="image/png",
        size_bytes=2048,
        sha256="a" * 64,
        stream_kind="screenshot",
    )

    assert set(payload) == set(MEDIA_PAYLOAD_KEYS)
    assert payload["artifact_id"] == "11111111-1111-4111-8111-111111111111"
    assert payload["stream_kind"] == "screenshot"


@pytest.mark.parametrize(
    "payload",
    [
        {"body_base64": "iVBORw0KGgo="},
        {"image_base64": "iVBORw0KGgo="},
        {"data_url": "data:image/png;base64,iVBORw0KGgo="},
        {"attachment": {"content_base64": "iVBORw0KGgo="}},
        {"attachments": [{"blob": "iVBORw0KGgo="}]},
    ],
)
def test_an_event_carrying_inline_media_is_refused(stream_context, payload):
    """Une image en base64 n'entre jamais dans le journal : le refus est explicite."""

    with stream_context["session_factory"]() as db:
        with pytest.raises(MediaPayloadRefused):
            store_event(
                db,
                Event(
                    type="artifact.created",
                    project_id=stream_context["project_a"],
                    payload=payload,
                ),
            )
    with stream_context["session_factory"]() as db:
        assert db.query(EventModel).filter_by(type="artifact.created").count() == 0


def test_a_media_event_is_served_as_a_reference_only(stream_context):
    """Sur la page, l'événement de média ne porte que sa référence d'artefact."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    _publish(
        stream_context,
        run_id=run_id,
        project_id=stream_context["project_a"],
        event_type="artifact.created",
        payload=media_reference_payload(
            artifact_id="22222222-2222-4222-8222-222222222222",
            content_type="video/webm",
            size_bytes=98_304,
            sha256="b" * 64,
            stream_kind="video",
        ),
    )

    response = client.get(f"/runs/{run_id}/events")
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 1
    assert set(events[0]["payload"]) == set(MEDIA_PAYLOAD_KEYS)
    assert "base64" not in json.dumps(events[0])


def _nested(leaf: dict, levels: int) -> dict:
    payload = leaf
    for _ in range(levels):
        payload = {"nested": payload}
    return payload


def _refused(context, payload: dict) -> None:
    """Le refus est explicite **et** rien n'est écrit : les deux font la garantie."""

    with context["session_factory"]() as db:
        with pytest.raises(MediaPayloadRefused):
            store_event(
                db,
                Event(
                    type="artifact.created",
                    project_id=context["project_a"],
                    payload=payload,
                ),
            )
    with context["session_factory"]() as db:
        assert db.query(EventModel).filter_by(type="artifact.created").count() == 0


def test_a_payload_nested_deeper_than_the_inspection_depth_is_refused(stream_context):
    """Au-delà de la profondeur inspectée, la charge utile est refusée, jamais ignorée.

    La charge utile n'emploie **aucune** clé listée : c'est bien la profondeur non
    inspectable qui est refusée, pas un nom reconnu au passage.
    """

    _refused(stream_context, _nested({"detail": "hors de portée"}, PAYLOAD_MAX_DEPTH + 1))


def test_a_payload_within_the_inspection_depth_is_still_accepted(stream_context):
    """La borne de profondeur reste une borne : juste en deçà, l'écriture passe."""

    with stream_context["session_factory"]() as db:
        store_event(
            db,
            Event(
                type="task.progress",
                project_id=stream_context["project_a"],
                payload=_nested({"detail": "ok"}, PAYLOAD_MAX_DEPTH - 1),
            ),
        )
    with stream_context["session_factory"]() as db:
        assert db.query(EventModel).filter_by(type="task.progress").count() == 1


def test_an_oversized_payload_is_refused_whatever_its_key_is_called(stream_context):
    """La garantie ne repose pas sur une liste de noms : la taille est bornée aussi."""

    _refused(stream_context, {"screenshot": "A" * (PAYLOAD_MAX_BYTES + 1)})


def test_a_payload_just_under_the_size_bound_is_accepted(stream_context):
    """La borne de taille ne rétrécit pas les événements métier légitimes."""

    with stream_context["session_factory"]() as db:
        store_event(
            db,
            Event(
                type="task.progress",
                project_id=stream_context["project_a"],
                payload={"error_snippet": "b" * (PAYLOAD_MAX_BYTES // 2)},
            ),
        )
    with stream_context["session_factory"]() as db:
        assert db.query(EventModel).filter_by(type="task.progress").count() == 1


def test_an_artifact_reference_refuses_any_foreign_key(stream_context):
    """Une référence d'artefact ne porte que ses cinq clés : rien ne voyage à côté."""

    reference = media_reference_payload(
        artifact_id="33333333-3333-4333-8333-333333333333",
        content_type="image/png",
        size_bytes=2048,
        sha256="c" * 64,
        stream_kind="screenshot",
    )

    _refused(stream_context, {**reference, "png": "iVBORw0KGgo="})
    _refused(stream_context, {"attachments": [{**reference, "thumbnail": "iVBORw0"}]})


# --- 4. Lecture par curseur ---------------------------------------------------


def test_the_run_page_paginates_by_cursor(stream_context):
    """La page rend ``next_cursor`` et ``has_more`` et reprend exactement après."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    for _ in range(5):
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    first = client.get(f"/runs/{run_id}/events", params={"limit": 2}).json()
    assert _page_sequences(first) == [1, 2]
    assert (first["next_cursor"], first["has_more"]) == (2, True)

    second = client.get(
        f"/runs/{run_id}/events",
        params={"limit": 2, "after_seq": first["next_cursor"]},
    ).json()
    assert _page_sequences(second) == [3, 4]
    assert (second["next_cursor"], second["has_more"]) == (4, True)

    third = client.get(
        f"/runs/{run_id}/events",
        params={"limit": 2, "after_seq": second["next_cursor"]},
    ).json()
    assert _page_sequences(third) == [5]
    assert (third["next_cursor"], third["has_more"]) == (5, False)


def test_an_exhausted_cursor_returns_an_empty_page_without_moving(stream_context):
    """Une page vide conserve le curseur du client : il n'y a rien à réconcilier."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    for _ in range(2):
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    page = client.get(f"/runs/{run_id}/events", params={"after_seq": 2}).json()

    assert page["events"] == []
    assert (page["next_cursor"], page["has_more"]) == (2, False)


def test_the_run_page_never_returns_another_run(stream_context):
    """La portée d'une page est la tentative demandée, jamais sa voisine."""

    client = stream_context["client"]
    _publish(
        stream_context,
        run_id=stream_context["run_a"],
        project_id=stream_context["project_a"],
        event_type="task.progress",
    )
    _publish(
        stream_context,
        run_id=stream_context["sibling_a"],
        project_id=stream_context["project_a"],
        event_type="task.blocked",
    )

    page = client.get(f"/runs/{stream_context['run_a']}/events").json()

    assert [event["type"] for event in page["events"]] == ["task.progress"]


def test_the_page_exposes_the_event_metadata_of_lot_e(stream_context):
    """La page rend les colonnes du Lot E, exploitables par le Studio."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    event = client.get(f"/runs/{run_id}/events").json()["events"][0]

    assert event["schema_version"] == "1.0"
    assert event["executor"] == "platform"
    assert event["emitted_by"] == "api"
    assert event["task_run_id"] == run_id
    assert event["sequence"] == 1


def test_the_run_page_exposes_the_retention_window(stream_context, monkeypatch):
    """La page annonce la fenêtre de rétention pour que l'interface l'affiche."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    assert client.get(f"/runs/{run_id}/events").json()["retention_days"] == 90

    monkeypatch.setenv("ACP_EVENT_RETENTION_DAYS", "0")
    assert client.get(f"/runs/{run_id}/events").json()["retention_days"] == 0


def test_the_project_page_paginates_over_every_run_of_the_project(stream_context):
    """La page projet agrège les tentatives du projet et reprend après son curseur."""

    client = stream_context["client"]
    baseline = client.get(f"/projects/{stream_context['project_a']}/events").json()
    cursor = baseline["next_cursor"] or 0

    markers = []
    for run_key in ("run_a", "sibling_a", "run_a"):
        markers.append(
            _publish(
                stream_context,
                run_id=stream_context[run_key],
                project_id=stream_context["project_a"],
                event_type="task.progress",
            )
        )
    assert markers == [1, 1, 2]

    page = client.get(
        f"/projects/{stream_context['project_a']}/events",
        params={"after_seq": cursor},
    ).json()

    assert [event["type"] for event in page["events"]] == ["task.progress"] * 3
    assert page["has_more"] is False
    assert page["next_cursor"] > cursor

    resumed = client.get(
        f"/projects/{stream_context['project_a']}/events",
        params={"after_seq": page["next_cursor"]},
    ).json()
    assert resumed["events"] == []


def test_the_project_page_ignores_the_events_of_another_project(stream_context):
    """Un événement du projet B n'apparaît jamais dans la page du projet A."""

    client = stream_context["client"]
    baseline = client.get(f"/projects/{stream_context['project_a']}/events").json()
    cursor = baseline["next_cursor"] or 0
    _publish(
        stream_context,
        run_id=stream_context["run_b"],
        project_id=stream_context["project_b"],
        event_type="task.progress",
    )

    page = client.get(
        f"/projects/{stream_context['project_a']}/events",
        params={"after_seq": cursor},
    ).json()

    assert page["events"] == []


def test_the_project_page_never_drops_a_row_sharing_a_timestamp(stream_context):
    """Des lignes écrites à la même microseconde sortent toutes, une seule fois chacune.

    Le curseur ne lit plus l'horloge : l'égalité d'horodatage n'a plus d'effet sur la
    pagination, et une page ne peut plus avancer ``next_cursor`` au-delà de lignes
    jamais rendues.
    """

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    identifiers = _publish_burst(
        stream_context, run_id=stream_context["run_a"], project_id=project_id, count=3
    )
    _collapse_created_at(stream_context, identifiers)

    for limit in (1, 2, 3):
        delivered, last_page = _drain_project_pages(
            client, project_id, cursor=cursor, limit=limit
        )
        assert delivered == identifiers
        assert len(delivered) == len(set(delivered))
        assert last_page["has_more"] is False


def test_the_project_page_announces_has_more_and_resumes_without_a_gap(
    stream_context,
):
    """``has_more`` et ``next_cursor`` reprennent exactement après la dernière ligne rendue."""

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    tied = _publish_burst(
        stream_context, run_id=stream_context["run_a"], project_id=project_id, count=2
    )
    _collapse_created_at(stream_context, tied)
    later = _publish_burst(
        stream_context,
        run_id=stream_context["sibling_a"],
        project_id=project_id,
        count=1,
    )

    first = client.get(
        f"/projects/{project_id}/events",
        params={"after_seq": cursor, "limit": 2},
    ).json()
    assert [event["id"] for event in first["events"]] == tied
    assert first["has_more"] is True

    second = client.get(
        f"/projects/{project_id}/events",
        params={"after_seq": first["next_cursor"], "limit": 2},
    ).json()
    assert [event["id"] for event in second["events"]] == later
    assert second["has_more"] is False


def test_a_project_burst_in_one_transaction_is_paged_without_loss(stream_context):
    """Rafale réaliste (une transaction) : page par page, rien ne manque, rien ne double."""

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    identifiers = _publish_burst(
        stream_context, run_id=stream_context["run_a"], project_id=project_id, count=120
    )

    for limit in (1, 2):
        delivered, _ = _drain_project_pages(
            client, project_id, cursor=cursor, limit=limit
        )
        assert delivered == identifiers
        assert len(delivered) == len(set(delivered))


def test_three_hundred_unspaced_publications_are_paged_exactly_once(stream_context):
    """300 publications d'affilée, page par page (``limit=1``) : 300 rendus, une fois chacun.

    Aucune pause entre les écritures : sur une horloge à faible granularité
    (Windows : ~1,5 ms) des dizaines de lignes partagent la même microseconde. Un
    curseur dérivé de l'horodatage en perdait donc silencieusement, en annonçant
    ``has_more: false``. Le compteur de journal donne un ordre total : rien ne saute.
    """

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    published = [
        _publish(
            stream_context,
            run_id=stream_context["run_a"],
            project_id=project_id,
            payload={"index": index},
        )
        for index in range(300)
    ]
    assert published == list(range(1, 301))
    written = _project_event_ids(stream_context, project_id, after=cursor)
    assert len(written) == 300

    delivered, last_page = _drain_project_pages(
        client, project_id, cursor=cursor, limit=1
    )

    assert delivered == written, "événements perdus, dupliqués ou désordonnés"
    assert last_page["has_more"] is False


def test_two_concurrent_publications_get_distinct_journal_sequences(stream_context):
    """Deux publications simultanées ne peuvent jamais obtenir le même numéro de journal."""

    project_id = stream_context["project_a"]
    threads = 12
    barrier = threading.Barrier(threads)

    def publish_one(index: int) -> str:
        event = Event(
            type="task.progress",
            project_id=project_id,
            task_run_id=stream_context["run_a"] if index % 2 else None,
            payload={"index": index},
        )
        barrier.wait(timeout=10)
        with stream_context["session_factory"]() as db:
            publish(db, event)
        return event.id

    with ThreadPoolExecutor(max_workers=threads) as pool:
        identifiers = list(pool.map(publish_one, range(threads)))

    numbers = [_journal_cursor(stream_context, event_id) for event_id in identifiers]
    assert len(set(numbers)) == threads


def test_the_project_page_never_exceeds_its_limit_on_a_shared_timestamp(stream_context):
    """Une page reste bornée par ``limit`` même si toutes les lignes partagent l'horodatage.

    L'ancien contournement élargissait la page à tout le groupe d'égalité, sans borne :
    le curseur ne dépendant plus de l'horloge, la borne redevient celle demandée.
    """

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    identifiers = _publish_burst(
        stream_context, run_id=stream_context["run_a"], project_id=project_id, count=25
    )
    _collapse_created_at(stream_context, identifiers)

    page = client.get(
        f"/projects/{project_id}/events",
        params={"after_seq": cursor, "limit": 2},
    ).json()
    assert len(page["events"]) == 2
    assert page["has_more"] is True

    for limit in (1, 3):
        delivered, last_page = _drain_project_pages(
            client, project_id, cursor=cursor, limit=limit
        )
        assert delivered == identifiers
        assert last_page["has_more"] is False


def test_the_project_stream_resumes_after_last_event_id_without_loss(stream_context):
    """Reprise du flux projet par ``Last-Event-ID``, sur des publications non espacées."""

    client = stream_context["client"]
    project_id = stream_context["project_a"]
    identifiers = [
        Event(
            type="task.progress",
            project_id=project_id,
            task_run_id=stream_context["run_a"],
            payload={"index": index},
        )
        for index in range(6)
    ]
    for event in identifiers:
        with stream_context["session_factory"]() as db:
            publish(db, event)
    written = [event.id for event in identifiers]
    resume_from = _journal_cursor(stream_context, written[2])

    response = client.get(
        f"/streams/projects/{project_id}",
        headers={"Last-Event-ID": str(resume_from)},
    )
    frames, _ = _parse_sse(response.text)
    served = [
        json.loads(frame["data"])["id"]
        for frame in frames
        if frame.get("event") == "acp.event"
    ]

    assert served == written[3:]


def test_the_page_limit_is_bounded(stream_context):
    """Une limite hors bornes est refusée plutôt que silencieusement réinterprétée."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]

    assert client.get(f"/runs/{run_id}/events", params={"limit": 501}).status_code == 422
    assert client.get(f"/runs/{run_id}/events", params={"limit": 0}).status_code == 422
    assert client.get(f"/runs/{run_id}/events", params={"limit": 500}).status_code == 200
    assert client.get(f"/runs/{run_id}/events", params={"after_seq": -1}).status_code == 422


def test_an_unknown_run_is_not_found(stream_context):
    client = stream_context["client"]

    assert client.get(f"/runs/{uuid4()}/events").status_code == 404
    assert client.get(f"/streams/runs/{uuid4()}").status_code == 404


def test_the_journal_is_closed_without_a_server_session(stream_context):
    client = stream_context["client"]
    run_id = stream_context["run_a"]
    client.cookies.clear()

    assert client.get(f"/runs/{run_id}/events").status_code == 401
    assert client.get(f"/projects/{stream_context['project_a']}/events").status_code == 401
    assert client.get(f"/streams/runs/{run_id}").status_code == 401
    assert client.get(f"/streams/projects/{stream_context['project_a']}").status_code == 401


# --- 5. RBAC inter-projets ----------------------------------------------------


def test_a_member_of_another_project_is_refused_on_the_run_page(stream_context):
    """Le projet du run est résolu côté serveur : un étranger reçoit 403."""

    client = stream_context["client"]
    _authenticate(client, stream_context["mallory"])

    response = client.get(f"/runs/{stream_context['run_a']}/events")

    assert response.status_code == 403


def test_a_client_supplied_project_id_never_widens_the_run_page_scope(stream_context):
    """Un ``project_id`` fourni par le client n'élargit jamais la portée du run."""

    client = stream_context["client"]
    _authenticate(client, stream_context["mallory"])

    page = client.get(
        f"/runs/{stream_context['run_a']}/events",
        params={"project_id": stream_context["project_b"]},
    )
    stream = client.get(
        f"/streams/runs/{stream_context['run_a']}",
        params={"project_id": stream_context["project_b"]},
    )

    assert (page.status_code, stream.status_code) == (403, 403)


def test_a_member_of_another_project_is_refused_on_the_project_page(stream_context):
    client = stream_context["client"]
    _authenticate(client, stream_context["mallory"])

    response = client.get(f"/projects/{stream_context['project_a']}/events")

    assert response.status_code == 403


def test_a_member_of_the_project_reads_its_own_journal(stream_context):
    """Le membre légitime lit bien la page : le refus ci-dessus vient du RBAC."""

    client = stream_context["client"]
    _publish(
        stream_context,
        run_id=stream_context["run_a"],
        project_id=stream_context["project_a"],
    )
    _authenticate(client, stream_context["alice"])

    response = client.get(f"/runs/{stream_context['run_a']}/events")

    assert response.status_code == 200
    assert _page_sequences(response.json()) == [1]


def test_a_member_of_another_project_is_refused_on_the_stream(stream_context):
    """Le flux applique le même RBAC que la page, avant toute émission."""

    client = stream_context["client"]
    _authenticate(client, stream_context["mallory"])

    response = client.get(f"/streams/runs/{stream_context['run_a']}")

    assert response.status_code == 403
    assert stream_connections.count(stream_context["mallory"]["user_id"]) == 0


def test_a_member_of_another_project_is_refused_on_the_project_stream(stream_context):
    client = stream_context["client"]
    _authenticate(client, stream_context["mallory"])

    response = client.get(f"/streams/projects/{stream_context['project_a']}")

    assert response.status_code == 403


# --- 6. Routes de flux (réponse bufferisée par le TestClient) -----------------


def test_the_stream_announces_no_store_and_no_buffering(stream_context):
    """Les en-têtes SSE interdisent le cache et la mise en tampon d'un proxy."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    response = client.get(f"/streams/runs/{run_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    # Le middleware de l'API renforce en « private, no-store » pour une réponse
    # authentifiée : la directive exigée reste présente.
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-accel-buffering"] == "no"


def test_the_stream_resumes_after_last_event_id_without_duplicate_or_loss(stream_context):
    """``Last-Event-ID`` reprend exactement après le dernier événement reçu."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    for _ in range(5):
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    response = client.get(
        f"/streams/runs/{run_id}", headers={"Last-Event-ID": "2"}
    )
    frames, _ = _parse_sse(response.text)

    assert _sequences(frames) == [3, 4, 5]
    assert [frame["id"] for frame in frames if frame.get("event") == "acp.event"] == [
        "3",
        "4",
        "5",
    ]


def test_last_event_id_takes_precedence_over_after_seq(stream_context):
    """L'en-tête prime sur le paramètre : la reprise du navigateur fait autorité."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    for _ in range(3):
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    response = client.get(
        f"/streams/runs/{run_id}",
        params={"after_seq": 0},
        headers={"Last-Event-ID": "2"},
    )
    frames, _ = _parse_sse(response.text)

    assert _sequences(frames) == [3]


def test_an_unreadable_last_event_id_falls_back_to_after_seq(stream_context):
    """Un en-tête illisible ne casse pas la reprise : le paramètre reprend la main."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    for _ in range(3):
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    response = client.get(
        f"/streams/runs/{run_id}",
        params={"after_seq": 2},
        headers={"Last-Event-ID": "pas-un-nombre"},
    )
    frames, _ = _parse_sse(response.text)

    assert _sequences(frames) == [3]


def test_the_stream_rotates_with_its_cursor_after_the_maximum_duration(stream_context):
    """Au bout de ``ACP_STREAM_MAX_SECONDS`` le serveur ferme en donnant le curseur."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    for _ in range(2):
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])

    response = client.get(f"/streams/runs/{run_id}")
    frames, comments = _parse_sse(response.text)

    rotate = [frame for frame in frames if frame.get("event") == "acp.stream.rotate"]
    assert len(rotate) == 1
    assert json.loads(rotate[0]["data"]) == {"cursor": 2, "reason": "max_seconds"}
    assert rotate[0]["id"] == "2"
    assert comments[0] == "ping"


def test_an_empty_stream_rotates_without_a_cursor(stream_context):
    """Sans aucun événement, la rotation ne fabrique pas de curseur imaginaire."""

    client = stream_context["client"]

    response = client.get(f"/streams/runs/{stream_context['run_a']}")
    frames, _ = _parse_sse(response.text)

    assert len(frames) == 1
    assert frames[0]["event"] == "acp.stream.rotate"
    assert json.loads(frames[0]["data"])["cursor"] == 0
    assert "id" not in frames[0]


def test_the_project_stream_serves_the_events_of_the_project(stream_context):
    """Le flux projet agrège les tentatives du projet et ignore les autres."""

    client = stream_context["client"]
    baseline = client.get(f"/projects/{stream_context['project_a']}/events").json()
    cursor = baseline["next_cursor"] or 0
    _publish(
        stream_context,
        run_id=stream_context["run_b"],
        project_id=stream_context["project_b"],
        event_type="task.blocked",
    )
    _publish(
        stream_context,
        run_id=stream_context["sibling_a"],
        project_id=stream_context["project_a"],
        event_type="task.progress",
    )

    response = client.get(
        f"/streams/projects/{stream_context['project_a']}",
        params={"after_seq": cursor},
    )
    frames, _ = _parse_sse(response.text)

    payloads = [
        json.loads(frame["data"])
        for frame in frames
        if frame.get("event") == "acp.event"
    ]
    assert [payload["type"] for payload in payloads] == ["task.progress"]
    assert payloads[0]["project_id"] == stream_context["project_a"]


# --- 7. Limite de connexions --------------------------------------------------


def test_the_stream_is_refused_beyond_the_connection_limit(stream_context, monkeypatch):
    """Au-delà de ``ACP_STREAM_MAX_CONNECTIONS_PER_USER`` la connexion est refusée."""

    monkeypatch.setenv("ACP_STREAM_MAX_CONNECTIONS_PER_USER", "2")
    client = stream_context["client"]
    run_id = stream_context["run_a"]
    owner_id = stream_context["owner_id"]

    assert stream_connections.acquire(owner_id, 2) is True
    assert client.get(f"/streams/runs/{run_id}").status_code == 200

    assert stream_connections.acquire(owner_id, 2) is True
    refused = client.get(f"/streams/runs/{run_id}")

    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "5"
    assert "flux" in refused.json()["detail"].lower()


def test_a_finished_stream_frees_its_slot(stream_context):
    """Le compteur revient à zéro quand le flux se termine : pas de fuite de quota."""

    client = stream_context["client"]
    run_id = stream_context["run_a"]
    owner_id = stream_context["owner_id"]

    for _ in range(3):
        assert client.get(f"/streams/runs/{run_id}").status_code == 200
        assert stream_connections.count(owner_id) == 0


def test_the_connection_limit_is_counted_per_user():
    """Le quota d'un utilisateur n'est jamais consommé par un autre."""

    stream_connections.reset()
    assert stream_connections.acquire("user-a", 1) is True
    assert stream_connections.acquire("user-a", 1) is False
    assert stream_connections.acquire("user-b", 1) is True
    stream_connections.release("user-a")
    assert stream_connections.count("user-a") == 0
    assert stream_connections.acquire("user-a", 1) is True
    stream_connections.reset()
    assert stream_connections.count("user-b") == 0


def test_releasing_an_unknown_slot_is_harmless():
    """Une libération en double ne rend jamais le compteur négatif."""

    stream_connections.reset()
    stream_connections.release("inconnu")
    stream_connections.release("inconnu")

    assert stream_connections.count("inconnu") == 0


# --- 8. Comportements vivants du générateur -----------------------------------


@pytest.mark.asyncio
async def test_the_stream_delivers_events_published_after_the_connection(stream_context):
    """Le flux suit la base : un événement publié pendant la connexion arrive ensuite."""

    run_id = stream_context["run_a"]
    for _ in range(2):
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    policy = _member_policy(
        stream_context, "alice", run_id=run_id, project_id=stream_context["project_a"]
    )

    reader = _StreamReader(
        run_event_stream(stream_context["session_factory"], run_id, 0, policy)
    )
    try:
        await reader.until(frames=2)
        assert _sequences(reader.frames) == [1, 2]
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
        await reader.until(frames=3)
        assert _sequences(reader.frames) == [1, 2, 3]
    finally:
        await reader.aclose()


@pytest.mark.asyncio
async def test_the_stream_resumes_exactly_after_its_cursor(stream_context):
    """Reprise par curseur : ni doublon, ni saut, y compris à chaud."""

    run_id = stream_context["run_a"]
    for _ in range(4):
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    policy = _member_policy(
        stream_context, "alice", run_id=run_id, project_id=stream_context["project_a"]
    )

    reader = _StreamReader(
        run_event_stream(stream_context["session_factory"], run_id, 2, policy)
    )
    try:
        await reader.until(frames=2)
        assert _sequences(reader.frames) == [3, 4]
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
        await reader.until(frames=3)
        assert _sequences(reader.frames) == [3, 4, 5]
    finally:
        await reader.aclose()


@pytest.mark.asyncio
async def test_the_project_stream_follows_every_run_of_the_project(stream_context):
    """Le flux projet suit plusieurs tentatives et refuse celles des autres projets."""

    project_a = stream_context["project_a"]
    policy = _member_policy(stream_context, "alice", run_id=None, project_id=project_a)
    baseline = stream_context["client"].get(f"/projects/{project_a}/events").json()
    cursor = baseline["next_cursor"] or 0

    reader = _StreamReader(
        project_event_stream(stream_context["session_factory"], project_a, cursor, policy)
    )
    try:
        _publish(
            stream_context,
            run_id=stream_context["run_b"],
            project_id=stream_context["project_b"],
            event_type="task.blocked",
        )
        _publish(
            stream_context,
            run_id=stream_context["run_a"],
            project_id=project_a,
            event_type="task.progress",
        )
        _publish(
            stream_context,
            run_id=stream_context["sibling_a"],
            project_id=project_a,
            event_type="task.completed",
        )
        await reader.until(frames=2)
        payloads = [
            json.loads(frame["data"])
            for frame in reader.frames
            if frame.get("event") == "acp.event"
        ]
        assert [payload["type"] for payload in payloads] == [
            "task.progress",
            "task.completed",
        ]
        assert {payload["project_id"] for payload in payloads} == {project_a}
    finally:
        await reader.aclose()


@pytest.mark.asyncio
async def test_the_stream_closes_after_the_session_is_revoked(stream_context):
    """Une session révoquée ferme le flux au plus tard à la page suivante."""

    run_id = stream_context["run_a"]
    alice = stream_context["alice"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    policy = _member_policy(
        stream_context, "alice", run_id=run_id, project_id=stream_context["project_a"]
    )

    reader = _StreamReader(
        run_event_stream(stream_context["session_factory"], run_id, 0, policy)
    )
    try:
        await reader.until(frames=1)
        assert _sequences(reader.frames) == [1]
        with stream_context["session_factory"]() as db:
            session = db.query(UserSessionModel).filter_by(user_id=alice["user_id"]).one()
            session.revoked_at = utcnow()
            db.commit()
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
        await reader.until(frames=2)
    finally:
        await reader.aclose()

    assert [frame.get("event") for frame in reader.frames] == [
        "acp.event",
        "acp.stream.closed",
    ]
    assert json.loads(reader.frames[1]["data"])["reason"] == "unauthorized"


@pytest.mark.asyncio
async def test_the_stream_closes_after_the_membership_is_lost(stream_context):
    """Perdre son membership ferme le flux comme une révocation de session."""

    run_id = stream_context["run_a"]
    alice = stream_context["alice"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    policy = _member_policy(
        stream_context, "alice", run_id=run_id, project_id=stream_context["project_a"]
    )

    reader = _StreamReader(
        run_event_stream(stream_context["session_factory"], run_id, 0, policy)
    )
    try:
        await reader.until(frames=1)
        assert _sequences(reader.frames) == [1]
        with stream_context["session_factory"]() as db:
            db.query(MembershipModel).filter_by(user_id=alice["user_id"]).delete()
            db.commit()
        _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
        await reader.until(frames=2)
    finally:
        await reader.aclose()

    assert reader.frames[-1]["event"] == "acp.stream.closed"


@pytest.mark.asyncio
async def test_the_stream_sends_periodic_keepalive_comments(stream_context):
    """Un commentaire ``: ping`` périodique garde la connexion ouverte à vide."""

    run_id = stream_context["run_a"]
    policy = _member_policy(
        stream_context,
        "alice",
        run_id=run_id,
        project_id=stream_context["project_a"],
        ACP_STREAM_KEEPALIVE_SECONDS="0.05",
        ACP_STREAM_MAX_SECONDS="5",
    )

    reader = _StreamReader(
        run_event_stream(stream_context["session_factory"], run_id, 0, policy)
    )
    try:
        await reader.until(comments=3, timeout=3)
    finally:
        await reader.aclose()

    assert reader.frames == []
    assert len(reader.comments) >= 3
    assert set(reader.comments) == {"ping"}


@pytest.mark.asyncio
async def test_the_stream_ends_after_the_maximum_duration(stream_context):
    """Le générateur s'arrête de lui-même : une connexion ne vit pas indéfiniment."""

    run_id = stream_context["run_a"]
    _publish(stream_context, run_id=run_id, project_id=stream_context["project_a"])
    policy = _member_policy(
        stream_context,
        "alice",
        run_id=run_id,
        project_id=stream_context["project_a"],
        ACP_STREAM_MAX_SECONDS="0.2",
    )

    reader = _StreamReader(
        run_event_stream(stream_context["session_factory"], run_id, 0, policy)
    )
    await reader.drain(timeout=3)

    assert reader.exhausted is True
    assert reader.frames[-1]["event"] == "acp.stream.rotate"
    assert json.loads(reader.frames[-1]["data"])["cursor"] == 1


@pytest.mark.asyncio
async def test_the_stream_rotates_even_while_it_is_catching_up(stream_context):
    """La borne de durée s'applique aussi au rattrapage, pas seulement à l'attente.

    Sans cela, un flux qui trouve toujours des lignes ne tourne jamais : il dépasse
    ``ACP_STREAM_MAX_SECONDS`` sans limite et garde son jeton de connexion.
    """

    run_id = stream_context["run_a"]
    start, backlog = _seed_run_events(
        stream_context,
        run_id=run_id,
        project_id=stream_context["project_a"],
        count=1500,
    )
    policy = _member_policy(
        stream_context,
        "alice",
        run_id=run_id,
        project_id=stream_context["project_a"],
        ACP_STREAM_MAX_SECONDS="0.1",
        ACP_STREAM_BATCH="1",
    )

    reader = _StreamReader(
        run_event_stream(stream_context["session_factory"], run_id, 0, policy)
    )
    await reader.drain(timeout=30)

    delivered = _sequences(reader.frames)
    assert reader.exhausted is True
    assert reader.frames[-1]["event"] == "acp.stream.rotate"
    # Rattrapage interrompu net : le curseur de rotation reprend exactement là.
    assert delivered == list(range(start, start + len(delivered)))
    assert 0 < len(delivered) < backlog
    assert json.loads(reader.frames[-1]["data"])["cursor"] == delivered[-1]


@pytest.mark.asyncio
async def test_a_closed_stream_unsubscribes_from_the_hub(stream_context):
    """Fermer un flux libère son abonnement : pas de fuite de file de réveil."""

    run_id = stream_context["run_a"]
    channel = events_bus.run_channel(run_id)
    policy = _member_policy(
        stream_context, "alice", run_id=run_id, project_id=stream_context["project_a"]
    )

    reader = _StreamReader(
        run_event_stream(stream_context["session_factory"], run_id, 0, policy)
    )
    await reader.until(comments=1, timeout=3)
    assert events_bus.event_hub.subscriber_count(channel) == 1
    await reader.aclose()

    assert events_bus.event_hub.subscriber_count(channel) == 0


# --- 9. Hub local : uniquement des numéros de séquence ------------------------


@pytest.mark.asyncio
async def test_the_hub_only_carries_sequence_numbers():
    """Le hub réveille les flux ; la lecture reste faite en base."""

    hub = EventHub()
    queue = hub.subscribe("run:1")
    hub.notify("run:1", 7)

    assert await queue.get() == 7
    assert hub.subscriber_count("run:1") == 1
    hub.unsubscribe("run:1", queue)
    assert hub.subscriber_count("run:1") == 0
    hub.notify("run:1", 8)
    assert queue.empty()


@pytest.mark.asyncio
async def test_the_hub_never_blocks_a_publisher():
    """Une file saturée perd le réveil, jamais la publication : la base fait foi."""

    hub = EventHub()
    queue = hub.subscribe("run:2")
    for sequence in range(1, 200):
        hub.notify("run:2", sequence)

    assert queue.qsize() == hub.queue_maxsize


def test_a_publisher_outside_an_event_loop_still_notifies():
    """``publish`` est appelé depuis une route synchrone : la notification ne plante pas."""

    hub = EventHub()
    queue = hub.subscribe("run:3")
    hub.notify("run:3", 1)

    assert queue.get_nowait() == 1


def test_publish_notifies_the_run_and_project_channels(stream_context):
    """Une publication réveille le flux du run et celui du projet."""

    run_channel = events_bus.run_channel(stream_context["run_a"])
    project_channel = events_bus.project_channel(stream_context["project_a"])
    run_queue = events_bus.event_hub.subscribe(run_channel)
    project_queue = events_bus.event_hub.subscribe(project_channel)
    try:
        sequence = _publish(
            stream_context,
            run_id=stream_context["run_a"],
            project_id=stream_context["project_a"],
        )
        assert run_queue.get_nowait() == sequence
        assert project_queue.get_nowait() == sequence
    finally:
        events_bus.event_hub.unsubscribe(run_channel, run_queue)
        events_bus.event_hub.unsubscribe(project_channel, project_queue)


def test_no_module_writes_an_event_row_outside_the_journal_writer():
    """``events_bus`` est le seul module autorisé à construire un ``EventModel``.

    Un ``db.add(EventModel(...))` direct écrit une ligne sans numéro : invisible du
    journal projet jusqu'au prochain redémarrage, puis remontée hors d'ordre par le
    rattrapage de démarrage. Le garde-fou est structurel parce que la faute ne se
    voit pas à l'exécution — l'écriture réussit, c'est la lecture qui perd la ligne.
    """

    import acp_api

    source_root = Path(acp_api.__file__).resolve().parent
    offenders = sorted(
        module.relative_to(source_root).as_posix()
        for module in source_root.rglob("*.py")
        if module.name != "events_bus.py" and "EventModel(" in module.read_text(encoding="utf-8")
    )

    assert offenders == [], (
        "ces modules écrivent une ligne d'événement sans passer par "
        f"events_bus.store_event : {', '.join(offenders)}"
    )


# --- Frontière de transaction (0.9.1) --------------------------------------------


@pytest.mark.parametrize("scope", ["run", "project"])
def test_a_stream_keeps_no_request_transaction_while_it_runs(stream_context, monkeypatch, scope):
    """La session de la requête ne garde ni transaction ni connexion pendant le flux.

    Avec FastAPI, une dépendance ``get_db`` reste ouverte jusqu'à la fin d'une réponse
    en flux : sans libération explicite, chaque flux retenait une connexion du pool
    jusqu'à ACP_STREAM_MAX_SECONDS, et PostgreSQL la tuait au bout de 60 s.
    """

    import acp_api.streams as streams_module

    recorded = []
    base = app.dependency_overrides[get_db]

    def recording():
        for db in base():
            recorded.append(db)
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, recording)
    observed: list[bool] = []
    real_read = streams_module._read_rows

    def watching(*args, **kwargs):
        observed.append(any(db.in_transaction() for db in recorded))
        return real_read(*args, **kwargs)

    monkeypatch.setattr(streams_module, "_read_rows", watching)
    path = (
        f"/streams/runs/{stream_context['run_a']}"
        if scope == "run"
        else f"/streams/projects/{stream_context['project_a']}"
    )

    response = stream_context["client"].get(path)

    assert response.status_code == 200
    assert recorded, "la session de la requête doit avoir été enregistrée"
    assert observed, "le flux doit avoir lu au moins une page"
    assert not any(observed), "la session de la requête gardait une transaction"
