"""Lot E — événements, tests structurés et artefacts côté CLI.

Aucun réseau réel : chaque appel passe par ``httpx.MockTransport``.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import httpx
import pytest

from acp_cli.cli import ExitCode, main
from acp_cli.config import Settings, save_settings


class Capture(io.StringIO):
    """Flux de sortie injectable, avec ``buffer`` et ``isatty`` contrôlables."""

    def __init__(self, *, tty: bool = False) -> None:
        super().__init__()
        self.buffer = io.BytesIO()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def authenticated_config(path: Path) -> None:
    settings = Settings(
        api_url="http://127.0.0.1:8000",
        web_url="http://127.0.0.1:5173",
    ).with_session("session-secret", "csrf-secret", principal_id="u-1")
    save_settings(path, settings)


def invoke(
    tmp_path: Path,
    args: list[str],
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    stdin: str = "",
    sleep=lambda _seconds: None,
    browser_open=lambda _url: True,
    stdout: Capture | None = None,
    stderr: Capture | None = None,
    anonymous: bool = False,
):
    out = stdout or Capture()
    err = stderr or Capture()
    config = tmp_path / "config.json"
    if not anonymous:
        authenticated_config(config)
    code = main(
        [*args, "--config", str(config)],
        transport=httpx.MockTransport(handler),
        stdout=out,
        stderr=err,
        stdin=io.StringIO(stdin),
        environ={},
        sleep=sleep,
        browser_open=browser_open,
    )
    return code, out.getvalue(), err.getvalue(), out


class ChunkStream(httpx.SyncByteStream):
    """Corps de réponse émis morceau par morceau, éventuellement interrompu."""

    def __init__(self, chunks: Iterable[bytes], *, error: BaseException | None = None) -> None:
        self._chunks = list(chunks)
        self._error = error

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._chunks:
            yield chunk
        if self._error is not None:
            raise self._error


def sse(*frames: str) -> bytes:
    return "".join(frames).encode("utf-8")


def frame(sequence: int | None, event: dict[str, Any]) -> str:
    head = f"id: {sequence}\n" if sequence is not None else ""
    return f"{head}event: {event['type']}\ndata: {json.dumps(event, sort_keys=True)}\n\n"


def event(sequence: int | None, event_type: str = "run.progress", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "id": extra.pop("id", f"e-{sequence}"),
        "sequence": sequence,
        "type": event_type,
        "occurred_at": "2026-09-12T10:00:00+00:00",
        "task_run_id": "r-1",
        "payload": {},
    }
    body.update(extra)
    return body


def page(events: list[dict[str, Any]], *, next_cursor: int | None = None, has_more: bool = False) -> dict[str, Any]:
    return {
        "events": events,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "retention_days": 30,
    }


def ndjson(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --------------------------------------------------------------------------
# acp runs events
# --------------------------------------------------------------------------


def test_runs_events_reads_exactly_one_page_with_the_expected_request(tmp_path):
    seen: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=page([event(4), event(5)]))

    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "events", "r-1", "--after-seq", "3", "--limit", "2", "--json"],
        handler,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert seen == [("GET", "/runs/r-1/events", {"after_seq": "3", "limit": "2"})]
    assert [item["sequence"] for item in ndjson(out)] == [4, 5]


def test_runs_events_without_json_prints_one_readable_line_per_event(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "events", "r-1"],
        lambda _request: httpx.Response(200, json=page([event(1, "run.started")])),
    )

    assert code == ExitCode.OK
    assert err == ""
    line = out.strip()
    assert line.startswith("1 ")
    assert "run.started" in line
    assert "e-1" in line


def test_runs_events_reports_a_truncated_page_on_stderr_only(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "events", "r-1", "--limit", "1", "--json"],
        lambda _request: httpx.Response(200, json=page([event(7)], next_cursor=7, has_more=True)),
    )

    assert code == ExitCode.OK
    assert [item["sequence"] for item in ndjson(out)] == [7]
    notice = json.loads(err)["notice"]
    assert notice["code"] == "events_truncated"
    assert notice["next_cursor"] == 7


@pytest.mark.parametrize("bad", [["--limit", "0"], ["--limit", "501"], ["--after-seq", "-1"]])
def test_runs_events_refuses_out_of_range_bounds_without_calling_the_api(tmp_path, bad):
    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "events", "r-1", "--json", *bad],
        lambda _request: pytest.fail("une borne invalide ne doit pas appeler l'API"),
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "usage"


def test_runs_events_resolves_a_mission_identifier_after_a_404(tmp_path):
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/runs/m-1/events":
            return httpx.Response(404, json={"detail": "run introuvable"})
        if request.url.path == "/missions/m-1":
            return httpx.Response(200, json={"current_run": {"id": "r-9"}})
        return httpx.Response(200, json=page([event(1)]))

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "m-1", "--json"], handler)

    assert code == ExitCode.OK
    assert err == ""
    assert paths == ["/runs/m-1/events", "/missions/m-1", "/runs/r-9/events"]
    assert [item["sequence"] for item in ndjson(out)] == [1]


def test_runs_events_keeps_a_404_when_the_identifier_is_not_a_mission(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "run introuvable"})

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "x-1", "--json"], handler)

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["status"] == 404


def test_runs_events_maps_a_forbidden_project_to_the_auth_exit_code(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "events", "r-1", "--json"],
        lambda _request: httpx.Response(403, json={"detail": "projet interdit"}),
    )

    assert code == ExitCode.AUTH
    assert out == ""
    assert json.loads(err)["error"]["status"] == 403


# --------------------------------------------------------------------------
# acp runs events --follow
# --------------------------------------------------------------------------


def test_follow_drains_the_durable_log_then_streams_without_duplicates(tmp_path):
    seen: list[tuple[str, dict[str, str], str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (request.url.path, dict(request.url.params), request.headers.get("last-event-id"))
        )
        if request.url.path == "/runs/r-1/events":
            after = int(request.url.params.get("after_seq", "0"))
            if after == 0:
                return httpx.Response(200, json=page([event(1), event(2)]))
            return httpx.Response(200, json=page([]))
        return httpx.Response(
            200,
            stream=ChunkStream([sse(frame(2, event(2)), frame(3, event(3)), frame(4, event(4)))]),
            headers={"content-type": "text/event-stream"},
        )

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.OK
    assert [item["sequence"] for item in ndjson(out)] == [1, 2, 3, 4]
    assert seen[0] == ("/runs/r-1/events", {}, None)
    assert seen[1] == ("/streams/runs/r-1", {"after_seq": "2"}, "2")
    assert seen[2] == ("/runs/r-1/events", {"after_seq": "4"}, None)
    assert json.loads(err)["notice"]["code"] == "follow_ended"


def test_follow_falls_back_to_cursor_polling_when_the_stream_breaks(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.url.path}?{request.url.params}")
        if request.url.path == "/runs/r-1/events":
            after = int(request.url.params.get("after_seq", "0"))
            if after == 0:
                return httpx.Response(200, json=page([]))
            if after == 3:
                return httpx.Response(200, json=page([event(4), event(5)], next_cursor=5, has_more=True))
            return httpx.Response(200, json=page([]))
        return httpx.Response(
            200,
            stream=ChunkStream(
                [sse(frame(3, event(3)))], error=httpx.ReadError("flux coupé")
            ),
            headers={"content-type": "text/event-stream"},
        )

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.OK
    assert [item["sequence"] for item in ndjson(out)] == [3, 4, 5]
    codes = [json.loads(line)["notice"]["code"] for line in err.splitlines() if line.strip()]
    assert codes == ["stream_degraded", "follow_ended"]
    assert calls[-1] == "/runs/r-1/events?after_seq=5"


def test_follow_degrades_when_the_stream_carries_unreadable_data(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs/r-1/events":
            return httpx.Response(200, json=page([]))
        return httpx.Response(
            200,
            stream=ChunkStream([b"event: run.progress\ndata: {ceci n'est pas du JSON}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.OK
    assert out == ""
    codes = [json.loads(line)["notice"]["code"] for line in err.splitlines() if line.strip()]
    assert codes == ["stream_degraded", "follow_ended"]


def test_follow_deduplicates_events_that_carry_no_sequence(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs/r-1/events":
            return httpx.Response(200, json=page([event(None, id="e-a")]))
        return httpx.Response(
            200,
            stream=ChunkStream(
                [sse(frame(None, event(None, id="e-a")), frame(None, event(None, id="e-b")))]
            ),
            headers={"content-type": "text/event-stream"},
        )

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.OK
    assert [item["id"] for item in ndjson(out)] == ["e-a", "e-b"]


def test_follow_ignores_stream_heartbeats(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs/r-1/events":
            return httpx.Response(200, json=page([]))
        return httpx.Response(
            200,
            stream=ChunkStream([b": ping\n\n" + frame(1, event(1)).encode("utf-8") + b": ping\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

    code, out, _err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.OK
    assert [item["sequence"] for item in ndjson(out)] == [1]


def test_follow_interrupted_never_asks_for_a_cancellation(tmp_path):
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(f"{request.method} {request.url.path}")
        if request.url.path == "/runs/r-1/events":
            return httpx.Response(200, json=page([event(1)]))
        return httpx.Response(
            200,
            stream=ChunkStream([sse(frame(2, event(2)))], error=KeyboardInterrupt()),
            headers={"content-type": "text/event-stream"},
        )

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.INTERRUPTED
    assert [item["sequence"] for item in ndjson(out)] == [1, 2]
    assert all(entry.startswith("GET ") for entry in methods)
    lines = [json.loads(line) for line in err.splitlines() if line.strip()]
    assert lines[0]["notice"]["code"] == "follow_interrupted"
    assert lines[0]["notice"]["next_cursor"] == 2
    assert "n'est pas arrêtée" in lines[0]["notice"]["message"]
    assert lines[1]["error"]["code"] == "interrupted"


def test_follow_degrades_when_the_stream_route_is_unavailable(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs/r-1/events":
            after = int(request.url.params.get("after_seq", "0"))
            return httpx.Response(200, json=page([event(1)] if after == 0 else []))
        return httpx.Response(503, json={"detail": "flux indisponible"})

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.OK
    assert [item["sequence"] for item in ndjson(out)] == [1]
    codes = [json.loads(line)["notice"]["code"] for line in err.splitlines() if line.strip()]
    assert codes == ["stream_degraded", "follow_ended"]


def test_follow_surfaces_a_forbidden_stream_instead_of_polling_around_it(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/runs/r-1/events":
            return httpx.Response(200, json=page([]))
        return httpx.Response(403, json={"detail": "projet interdit"})

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.AUTH
    assert out == ""
    assert calls == ["/runs/r-1/events", "/streams/runs/r-1"]
    assert json.loads(err)["error"]["status"] == 403


def test_follow_without_json_still_writes_ndjson(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs/r-1/events":
            return httpx.Response(200, json=page([]))
        return httpx.Response(
            200,
            stream=ChunkStream([sse(frame(1, event(1)))]),
            headers={"content-type": "text/event-stream"},
        )

    code, out, _err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow"], handler)

    assert code == ExitCode.OK
    assert ndjson(out) == [event(1)]


def test_follow_opens_the_stream_at_the_requested_cursor_when_the_log_is_empty(tmp_path):
    seen: list[tuple[str, dict[str, str], str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (request.url.path, dict(request.url.params), request.headers.get("last-event-id"))
        )
        if request.url.path == "/runs/r-1/events":
            return httpx.Response(200, json=page([]))
        return httpx.Response(
            200,
            stream=ChunkStream([b""]),
            headers={"content-type": "text/event-stream"},
        )

    code, out, _err, _ = invoke(
        tmp_path, ["runs", "events", "r-1", "--follow", "--after-seq", "7", "--json"], handler
    )

    assert code == ExitCode.OK
    assert out == ""
    assert seen[0] == ("/runs/r-1/events", {"after_seq": "7"}, None)
    assert seen[1] == ("/streams/runs/r-1", {"after_seq": "7"}, "7")


def test_runs_events_refuses_a_page_without_events(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "events", "r-1", "--json"],
        lambda _request: httpx.Response(200, json={"has_more": False}),
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "client"


def test_follow_refuses_a_cursor_that_does_not_advance(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs/r-1/events":
            return httpx.Response(200, json=page([event(1)], next_cursor=1, has_more=True))
        return httpx.Response(200, json=page([]))

    code, out, err, _ = invoke(tmp_path, ["runs", "events", "r-1", "--follow", "--json"], handler)

    assert code == ExitCode.REMOTE
    assert [item["sequence"] for item in ndjson(out)] == [1]
    assert json.loads(err)["error"]["code"] == "client"


# --------------------------------------------------------------------------
# acp runs tests
# --------------------------------------------------------------------------


def run_detail(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "tr-1",
        "task_run_id": "r-1",
        "project_id": "p-1",
        "runner": "playwright",
        "runner_version": "1.44.0",
        "status": "completed",
        "started_at": "2026-09-12T10:00:00+00:00",
        "finished_at": "2026-09-12T10:01:00+00:00",
        "duration_ms": 60000,
        "exit_code": 0,
        "case_count": 4,
        "totals": {
            "expected": 3,
            "unexpected": 0,
            "flaky": 1,
            "skipped": 0,
            "interrupted": 0,
            "timedOut": 0,
        },
        "cases": [],
        "report_artifact": {"id": "a-report"},
    }
    body.update(overrides)
    return body


def test_runs_tests_exits_zero_and_keeps_every_status_distinct(tmp_path):
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json=run_detail())

    code, out, err, _ = invoke(tmp_path, ["runs", "tests", "r-1", "--json"], handler)

    assert code == ExitCode.OK
    assert err == ""
    assert seen == [("GET", "/runs/r-1/test-run")]
    payload = json.loads(out)
    assert payload["validation"] == "passed"
    assert payload["totals"] == {
        "expected": 3,
        "unexpected": 0,
        "flaky": 1,
        "skipped": 0,
        "interrupted": 0,
        "timedOut": 0,
    }
    assert payload["report_artifact_id"] == "a-report"
    assert payload["reasons"] == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"totals": {"expected": 1, "unexpected": 1, "flaky": 0, "skipped": 0, "interrupted": 0, "timedOut": 0}}, "unexpected"),
        ({"totals": {"expected": 1, "unexpected": 0, "flaky": 0, "skipped": 0, "interrupted": 0, "timedOut": 1}}, "timedOut"),
        ({"totals": {"expected": 1, "unexpected": 0, "flaky": 0, "skipped": 0, "interrupted": 1, "timedOut": 0}}, "interrupted"),
        ({"case_count": 0}, "case_count"),
        ({"status": "failed"}, "status"),
        ({"exit_code": 1}, "exit_code"),
    ],
)
def test_runs_tests_exits_four_and_names_the_reason(tmp_path, overrides, reason):
    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "tests", "r-1", "--json"],
        lambda _request: httpx.Response(200, json=run_detail(**overrides)),
    )

    assert code == ExitCode.REMOTE
    payload = json.loads(out)
    assert payload["validation"] == "failed"
    assert reason in payload["reasons"]
    assert json.loads(err)["error"]["code"] == "tests_failed"


def test_runs_tests_human_summary_names_each_status(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["runs", "tests", "r-1"],
        lambda _request: httpx.Response(200, json=run_detail()),
    )

    assert code == ExitCode.OK
    assert err == ""
    for label in ("attendus", "inattendus", "instables", "ignorés", "expirés", "interrompus"):
        assert label in out


def test_runs_tests_reports_a_missing_test_run_as_a_remote_error(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/missions/r-1":
            return httpx.Response(404, json={"detail": "mission introuvable"})
        return httpx.Response(404, json={"detail": "aucune exécution de tests pour ce run"})

    code, out, err, _ = invoke(tmp_path, ["runs", "tests", "r-1", "--json"], handler)

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["status"] == 404


# --------------------------------------------------------------------------
# acp artifacts list
# --------------------------------------------------------------------------


def artifact(identifier: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": identifier,
        "project_id": "p-1",
        "task_run_id": "r-1",
        "kind": "screenshot",
        "stream_kind": "test",
        "original_name": f"{identifier}.png",
        "content_type": "image/png",
        "size_bytes": 12,
        "checksum": "0" * 64,
        "source": "worker",
        "has_content": True,
        "created_at": "2026-09-12T10:00:00+00:00",
    }
    body.update(overrides)
    return body


def test_artifacts_list_filters_kind_and_content_type_locally(tmp_path):
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "items": [
                    artifact("a-1"),
                    artifact("a-2", kind="trace", content_type="application/zip"),
                    artifact("a-3", content_type="image/webp"),
                    artifact("a-4", task_run_id="r-2"),
                ],
                "next_cursor": None,
            },
        )

    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "list", "--run", "r-1", "--kind", "screenshot", "--type", "IMAGE/PNG", "--json"],
        handler,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert seen == [{"task_run_id": "r-1"}]
    assert [item["id"] for item in json.loads(out)] == ["a-1"]


def test_artifacts_list_follows_the_server_cursor(tmp_path):
    cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        cursors.append(cursor)
        if cursor is None:
            return httpx.Response(200, json={"items": [artifact("a-1")], "next_cursor": "c-2"})
        return httpx.Response(200, json={"items": [artifact("a-2")], "next_cursor": None})

    code, out, err, _ = invoke(tmp_path, ["artifacts", "list", "--run", "r-1", "--json"], handler)

    assert code == ExitCode.OK
    assert err == ""
    assert cursors == [None, "c-2"]
    assert [item["id"] for item in json.loads(out)] == ["a-1", "a-2"]


def test_artifacts_list_refuses_a_cursor_that_never_advances(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "list", "--run", "r-1", "--json"],
        lambda _request: httpx.Response(200, json={"items": [artifact("a-1")], "next_cursor": "c-1"}),
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "client"


# --------------------------------------------------------------------------
# acp artifacts get
# --------------------------------------------------------------------------

PAYLOAD = b"contenu d'artefact\n"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def content_handler(
    body: bytes = PAYLOAD,
    *,
    checksum: str | None = None,
    summary_overrides: dict[str, Any] | None = None,
    seen: list[str] | None = None,
):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/content"):
            return httpx.Response(
                200,
                stream=ChunkStream([body[index : index + 4] for index in range(0, len(body), 4)]),
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        overrides = {
            "checksum": checksum if checksum is not None else DIGEST,
            "size_bytes": len(body),
            "content_type": "text/plain",
            "original_name": "rapport.txt",
        }
        overrides.update(summary_overrides or {})
        return httpx.Response(200, json=artifact("a-1", **overrides))

    return handler


def test_artifacts_get_writes_the_file_and_checks_the_digest(tmp_path):
    seen: list[str] = []
    target = tmp_path / "sortie.txt"

    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(target), "--json"],
        content_handler(seen=seen),
    )

    assert code == ExitCode.OK
    assert err == ""
    assert seen == ["GET /artifacts/a-1", "GET /artifacts/a-1/content"]
    assert target.read_bytes() == PAYLOAD
    payload = json.loads(out)
    assert payload["path"] == str(target)
    assert payload["checksum"] == DIGEST
    assert payload["size_bytes"] == len(PAYLOAD)


def test_artifacts_get_uses_the_declared_name_stripped_of_any_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    code, _out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--json"],
        content_handler(summary_overrides={"original_name": "../../../etc/passwd"}),
    )

    assert code == ExitCode.OK
    assert err == ""
    assert (tmp_path / "passwd").read_bytes() == PAYLOAD
    assert not (tmp_path.parent / "passwd").exists()


def test_artifacts_get_falls_back_to_the_identifier_for_an_unusable_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    code, _out, _err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--json"],
        content_handler(summary_overrides={"original_name": "../.."}),
    )

    assert code == ExitCode.OK
    assert (tmp_path / "a-1").read_bytes() == PAYLOAD


def test_artifacts_get_refuses_to_overwrite_an_existing_file(tmp_path):
    target = tmp_path / "sortie.txt"
    target.write_bytes(b"precieux")

    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(target), "--json"],
        content_handler(),
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "file_exists"
    assert target.read_bytes() == b"precieux"


def test_artifacts_get_overwrites_only_with_force(tmp_path):
    target = tmp_path / "sortie.txt"
    target.write_bytes(b"precieux")

    code, _out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(target), "--force", "--json"],
        content_handler(),
    )

    assert code == ExitCode.OK
    assert err == ""
    assert target.read_bytes() == PAYLOAD


def test_artifacts_get_keeps_the_previous_file_when_a_forced_download_fails(tmp_path):
    target = tmp_path / "sortie.txt"
    target.write_bytes(b"precieux")

    code, _out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(target), "--force", "--json"],
        content_handler(checksum="1" * 64),
    )

    assert code == ExitCode.REMOTE
    assert json.loads(err)["error"]["code"] == "checksum_mismatch"
    assert target.read_bytes() == b"precieux"
    assert list(tmp_path.glob("*.part*")) == []


def test_artifacts_get_leaves_no_file_when_the_digest_differs(tmp_path):
    target = tmp_path / "sortie.txt"

    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(target), "--json"],
        content_handler(checksum="1" * 64),
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "checksum_mismatch"
    assert not target.exists()


def test_artifacts_get_refuses_a_body_larger_than_the_declared_size(tmp_path):
    target = tmp_path / "sortie.txt"

    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(target), "--json"],
        content_handler(summary_overrides={"size_bytes": 4}),
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "artifact_too_large"
    assert not target.exists()


def test_artifacts_get_writes_into_an_existing_directory(tmp_path):
    directory = tmp_path / "telechargements"
    directory.mkdir()

    code, _out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(directory), "--json"],
        content_handler(),
    )

    assert code == ExitCode.OK
    assert err == ""
    assert (directory / "rapport.txt").read_bytes() == PAYLOAD


def test_artifacts_get_streams_text_to_stdout(tmp_path):
    captured = Capture()

    code, out, err, stream = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--stdout"],
        content_handler(),
        stdout=captured,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert stream.buffer.getvalue() == PAYLOAD
    assert out == ""


def test_artifacts_get_refuses_binary_content_on_an_interactive_terminal(tmp_path):
    captured = Capture(tty=True)

    code, _out, err, stream = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--stdout", "--json"],
        content_handler(summary_overrides={"content_type": "image/png"}),
        stdout=captured,
    )

    assert code == ExitCode.USAGE
    assert stream.buffer.getvalue() == b""
    assert json.loads(err)["error"]["code"] == "binary_stdout"


def test_artifacts_get_writes_binary_to_an_interactive_terminal_with_force(tmp_path):
    captured = Capture(tty=True)

    code, _out, err, stream = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--stdout", "--force"],
        content_handler(summary_overrides={"content_type": "image/png"}),
        stdout=captured,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert stream.buffer.getvalue() == PAYLOAD


def test_artifacts_get_accepts_binary_on_a_redirected_stdout(tmp_path):
    captured = Capture(tty=False)

    code, _out, err, stream = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--stdout"],
        content_handler(summary_overrides={"content_type": "image/png"}),
        stdout=captured,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert stream.buffer.getvalue() == PAYLOAD


def test_artifacts_get_keeps_json_metadata_off_the_content_stream(tmp_path):
    captured = Capture()

    code, out, err, stream = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--stdout", "--json"],
        content_handler(),
        stdout=captured,
    )

    assert code == ExitCode.OK
    assert out == ""
    assert stream.buffer.getvalue() == PAYLOAD
    payload = json.loads(err)
    assert payload["path"] is None
    assert payload["checksum"] == DIGEST
    assert payload["verified"] is True


def test_artifacts_get_says_when_the_api_declares_no_checksum(tmp_path):
    target = tmp_path / "sortie.txt"

    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(target), "--json"],
        content_handler(checksum=""),
    )

    assert code == ExitCode.OK
    assert target.read_bytes() == PAYLOAD
    assert json.loads(out)["verified"] is False
    assert json.loads(err)["notice"]["code"] == "checksum_absent"


def test_artifacts_get_reports_a_digest_mismatch_even_on_stdout(tmp_path):
    captured = Capture()

    code, _out, err, stream = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--stdout", "--json"],
        content_handler(checksum="1" * 64),
        stdout=captured,
    )

    assert code == ExitCode.REMOTE
    # Le contenu est déjà parti sur la sortie standard : le CLI le dit au lieu
    # de laisser croire qu'il a été vérifié.
    assert stream.buffer.getvalue() == PAYLOAD
    assert json.loads(err)["error"]["code"] == "checksum_mismatch"


class BrokenBuffer(io.BytesIO):
    def write(self, _data):  # type: ignore[override]
        raise OSError(32, "tube cassé")


def test_artifacts_get_reports_a_broken_output_pipe_without_a_traceback(tmp_path):
    captured = Capture()
    captured.buffer = BrokenBuffer()

    code, _out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--stdout", "--json"],
        content_handler(),
        stdout=captured,
    )

    assert code == ExitCode.REMOTE
    payload = json.loads(err)["error"]
    assert payload["code"] == "write_failed"
    assert "tube cassé" in payload["message"]


def test_artifacts_get_refuses_a_download_into_a_missing_directory(tmp_path):
    code, _out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(tmp_path / "absent" / "x.txt"), "--json"],
        content_handler(),
    )

    assert code == ExitCode.REMOTE
    assert json.loads(err)["error"]["code"] == "write_failed"


def test_artifacts_get_refuses_an_empty_output_path(tmp_path):
    code, _out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", "  ", "--json"],
        content_handler(),
    )

    assert code == ExitCode.USAGE
    assert json.loads(err)["error"]["code"] == "usage"


def test_artifacts_get_refuses_output_and_stdout_together(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--stdout", "--output", str(tmp_path / "x"), "--json"],
        lambda _request: pytest.fail("une commande contradictoire ne doit pas appeler l'API"),
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "usage"


def test_artifacts_get_refuses_an_artifact_without_content(tmp_path):
    code, _out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(tmp_path / "x"), "--json"],
        content_handler(summary_overrides={"has_content": False}),
    )

    assert code == ExitCode.REMOTE
    assert json.loads(err)["error"]["code"] == "no_content"


def test_artifacts_get_maps_an_unauthenticated_answer_to_auth(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "get", "a-1", "--output", str(tmp_path / "x"), "--json"],
        lambda _request: httpx.Response(401, json={"detail": "session expirée"}),
    )

    assert code == ExitCode.AUTH
    assert out == ""
    assert json.loads(err)["error"]["status"] == 401


@pytest.mark.parametrize(
    ("status", "expected"),
    [(403, ExitCode.AUTH), (404, ExitCode.REMOTE), (500, ExitCode.REMOTE)],
)
def test_artifacts_get_reports_a_refused_content_stream(tmp_path, status, expected):
    """Le refus doit survivre au flux : ``APIError`` est un dataclass gelé."""

    target = tmp_path / "sortie.txt"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/content"):
            return httpx.Response(status, json={"detail": "contenu refusé"})
        return httpx.Response(200, json=artifact("a-1", checksum=DIGEST, size_bytes=len(PAYLOAD)))

    code, out, err, _ = invoke(
        tmp_path, ["artifacts", "get", "a-1", "--output", str(target), "--json"], handler
    )

    assert code == expected
    assert out == ""
    payload = json.loads(err)["error"]
    assert payload["status"] == status
    assert payload["message"] == "contenu refusé"
    assert not target.exists()


def test_artifacts_get_maps_a_stream_failure_to_the_network_exit_code(tmp_path):
    target = tmp_path / "sortie.txt"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/content"):
            return httpx.Response(
                200,
                stream=ChunkStream([b"abc"], error=httpx.ReadError("coupure")),
                headers={"content-type": "text/plain"},
            )
        return httpx.Response(200, json=artifact("a-1", checksum=DIGEST, size_bytes=len(PAYLOAD)))

    code, _out, err, _ = invoke(
        tmp_path, ["artifacts", "get", "a-1", "--output", str(target), "--json"], handler
    )

    assert code == ExitCode.NETWORK
    assert json.loads(err)["error"]["code"] == "network"
    assert not target.exists()


# --------------------------------------------------------------------------
# acp artifacts link
# --------------------------------------------------------------------------


def test_artifacts_link_posts_the_ttl_and_prints_the_url(tmp_path):
    seen: list[tuple[str, str, dict[str, str], str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.url.path,
                dict(request.url.params),
                request.headers.get("x-csrf-token"),
            )
        )
        return httpx.Response(
            200,
            json={
                "artifact_id": "a-1",
                "url": "http://127.0.0.1:8000/artifacts/a-1/content?token=v1.a-1.1789.sig",
                "expires_at": "2026-09-12T10:05:00+00:00",
            },
        )

    code, out, err, _ = invoke(tmp_path, ["artifacts", "link", "a-1", "--ttl", "120"], handler)

    assert code == ExitCode.OK
    assert seen == [("POST", "/artifacts/a-1/link", {"ttl_seconds": "120"}, "csrf-secret")]
    assert out.strip().endswith("token=v1.a-1.1789.sig")
    assert "2026-09-12T10:05:00+00:00" in err


def test_artifacts_link_uses_the_documented_default_ttl(tmp_path):
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={"artifact_id": "a-1", "url": "http://x/y", "expires_at": "2026-09-12T10:05:00+00:00"},
        )

    code, out, _err, _ = invoke(tmp_path, ["artifacts", "link", "a-1", "--json"], handler)

    assert code == ExitCode.OK
    assert seen == [{"ttl_seconds": "300"}]
    assert json.loads(out)["expires_at"] == "2026-09-12T10:05:00+00:00"


@pytest.mark.parametrize("ttl", ["0", "901", "-1"])
def test_artifacts_link_refuses_a_ttl_outside_the_allowed_window(tmp_path, ttl):
    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "link", "a-1", "--ttl", ttl, "--json"],
        lambda _request: pytest.fail("un TTL hors borne ne doit pas appeler l'API"),
    )

    assert code == ExitCode.USAGE
    assert out == ""
    assert json.loads(err)["error"]["code"] == "usage"


def test_artifacts_link_reports_a_missing_signing_key(tmp_path):
    code, out, err, _ = invoke(
        tmp_path,
        ["artifacts", "link", "a-1", "--json"],
        lambda _request: httpx.Response(503, json={"detail": "signature des liens non configurée"}),
    )

    assert code == ExitCode.REMOTE
    assert out == ""
    assert json.loads(err)["error"]["status"] == 503


# --------------------------------------------------------------------------
# acp open --studio
# --------------------------------------------------------------------------


def test_open_studio_prints_the_studio_url_without_opening_a_browser(tmp_path):
    opened: list[str] = []

    code, out, err, _ = invoke(
        tmp_path,
        ["open", "--run", "r-1", "--studio"],
        lambda _request: pytest.fail("open ne doit pas appeler l'API"),
        browser_open=lambda url: opened.append(url) or True,
    )

    assert code == ExitCode.OK
    assert err == ""
    assert out.strip() == "http://127.0.0.1:5173/missions?run=r-1&view=studio"
    assert opened == []


def test_open_studio_reports_the_view_in_json(tmp_path):
    code, out, _err, _ = invoke(
        tmp_path,
        ["open", "--run", "r-1", "--studio", "--json"],
        lambda _request: pytest.fail("open ne doit pas appeler l'API"),
    )

    assert code == ExitCode.OK
    payload = json.loads(out)
    assert payload["view"] == "studio"
    assert payload["url"].endswith("view=studio")


def test_open_studio_can_open_the_browser_on_demand(tmp_path):
    opened: list[str] = []

    code, _out, _err, _ = invoke(
        tmp_path,
        ["open", "--run", "r-1", "--studio", "--browser"],
        lambda _request: pytest.fail("open ne doit pas appeler l'API"),
        browser_open=lambda url: opened.append(url) or True,
    )

    assert code == ExitCode.OK
    assert opened == ["http://127.0.0.1:5173/missions?run=r-1&view=studio"]


def test_open_without_studio_keeps_the_mission_url(tmp_path):
    code, out, _err, _ = invoke(
        tmp_path,
        ["open", "--run", "r-1"],
        lambda _request: pytest.fail("open ne doit pas appeler l'API"),
    )

    assert code == ExitCode.OK
    assert out.strip() == "http://127.0.0.1:5173/missions?run=r-1"


# --------------------------------------------------------------------------
# complétion
# --------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["events", "tests", "get", "link"])
def test_completion_offers_the_new_subcommands(tmp_path, word):
    code, out, _err, _ = invoke(
        tmp_path,
        ["completion", "bash"],
        lambda _request: pytest.fail("completion ne doit pas appeler l'API"),
    )

    assert code == ExitCode.OK
    assert f" {word} " in out or f" {word}\"" in out
