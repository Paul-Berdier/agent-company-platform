from __future__ import annotations

import json
import multiprocessing
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from acp_cli.config import (
    ConfigError,
    PendingOperation,
    Settings,
    load_settings,
    mutate_settings,
    normalized_api_endpoint,
    normalized_origin,
    pending_dispatch_lock,
    save_settings,
)


def _increment_config_in_process(path_value: str, start_event, iterations: int) -> None:
    path = Path(path_value)
    start_event.wait(10)
    for _ in range(iterations):
        def increment(current: Settings):
            next_value = int(current.principal_id or "0") + 1
            time.sleep(0.003)
            return replace(current, principal_id=str(next_value)), None

        mutate_settings(path, increment, environ={})


def _hold_pending_dispatch_lock(path_value: str, held_event, release_event) -> None:
    with pending_dispatch_lock(Path(path_value)):
        held_event.set()
        if not release_event.wait(10):
            raise RuntimeError("dispatch-lock test timed out")


def test_settings_round_trip_and_no_secret_repr(tmp_path):
    path = tmp_path / "nested" / "config.json"
    settings = Settings(
        api_url="https://api.example.test",
        web_url="https://app.example.test",
    ).with_session("very-secret-cookie", "very-secret-csrf")

    save_settings(path, settings)

    assert load_settings(path, environ={}) == settings
    assert "very-secret" not in repr(settings)
    assert not list(path.parent.glob("*.tmp"))
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_pending_operation_round_trip_contains_only_fingerprints(tmp_path):
    path = tmp_path / "config.json"
    pending = PendingOperation(
        operation="mission-create",
        api_endpoint="https://api.example.test/v1",
        principal_session_fingerprint="a" * 64,
        payload_fingerprint="b" * 64,
        idempotency_key="acp-cli:mission-create:recoverable",
    )
    settings = Settings(
        api_url="https://api.example.test/v1",
        web_url="https://app.example.test",
        pending_operation=pending,
    ).with_session("cookie-secret", "csrf-secret", principal_id="user-1")

    save_settings(path, settings)

    assert load_settings(path, environ={}) == settings
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["pending_operation"]["version"] == 2
    assert stored["pending_operation"]["dispatch_count"] == 1
    assert "cookie-secret" not in json.dumps(stored["pending_operation"])
    assert "csrf-secret" not in json.dumps(stored["pending_operation"])
    assert "user-1" not in json.dumps(stored["pending_operation"])


def test_invalid_pending_operation_is_rejected(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "api_url": "https://api.example.test",
                "web_url": "https://app.example.test",
                "pending_operation": {
                    "version": 2,
                    "operation": "mission-create",
                    "api_endpoint": "https://api.example.test",
                    "principal_session_fingerprint": "not-a-digest",
                    "payload_fingerprint": "b" * 64,
                    "idempotency_key": "valid-key",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="empreinte"):
        load_settings(path, environ={})


@pytest.mark.parametrize(
    "missing_field",
    [
        "operation",
        "api_endpoint",
        "principal_session_fingerprint",
        "payload_fingerprint",
        "idempotency_key",
    ],
)
def test_incomplete_pending_operation_is_a_safe_config_error(
    tmp_path,
    missing_field,
):
    path = tmp_path / "config.json"
    pending = {
        "version": 2,
        "operation": "mission-create",
        "api_endpoint": "https://api.example.test",
        "principal_session_fingerprint": "a" * 64,
        "payload_fingerprint": "b" * 64,
        "idempotency_key": "valid-key",
    }
    pending.pop(missing_field)
    path.write_text(
        json.dumps(
            {
                "api_url": "https://api.example.test",
                "web_url": "https://app.example.test",
                "pending_operation": pending,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="pending incomplète"):
        load_settings(path, environ={})


def test_version_one_pending_is_safely_bound_to_its_stored_api_path(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "api_url": "https://api.example.test/v1",
                "web_url": "https://app.example.test",
                "pending_operation": {
                    "version": 1,
                    "operation": "mission-create",
                    "api_origin": "https://api.example.test",
                    "principal_session_fingerprint": "a" * 64,
                    "payload_fingerprint": "b" * 64,
                    "idempotency_key": "legacy-key",
                },
            }
        ),
        encoding="utf-8",
    )

    pending = load_settings(
        path,
        environ={},
        api_url="https://api.example.test/v2",
    ).pending_operation
    assert pending is not None
    assert pending.api_endpoint == "https://api.example.test/v1"


def test_version_one_pending_is_safely_bound_to_its_stored_api_path(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "api_url": "https://api.example.test/v1",
                "web_url": "https://app.example.test",
                "pending_operation": {
                    "version": 1,
                    "operation": "mission-create",
                    "api_origin": "https://api.example.test",
                    "principal_session_fingerprint": "a" * 64,
                    "payload_fingerprint": "b" * 64,
                    "idempotency_key": "legacy-key",
                },
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(path, environ={}, api_url="https://api.example.test/v2")
    assert settings.pending_operation is not None
    assert settings.pending_operation.api_endpoint == "https://api.example.test/v1"


def test_environment_and_cli_urls_override_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "api_url": "https://file-api.example.test",
                "web_url": "https://file-web.example.test",
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(
        path,
        environ={
            "ACP_API_URL": "https://env-api.example.test/",
            "ACP_WEB_URL": "https://env-web.example.test/",
        },
        api_url="https://cli-api.example.test/",
    )

    assert settings.api_url == "https://cli-api.example.test"
    assert settings.web_url == "https://env-web.example.test"


@pytest.mark.parametrize(
    "url",
    ["ftp://example.test", "example.test", "https://user:secret@example.test", "https://example.test/#fragment"],
)
def test_invalid_or_secret_bearing_urls_are_rejected(tmp_path, url):
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "missing.json", environ={}, api_url=url)


@pytest.mark.parametrize("field", ["api_url", "web_url"])
def test_plain_http_is_refused_outside_loopback(tmp_path, field):
    kwargs = {field: "http://api.example.test"}
    with pytest.raises(ConfigError, match="HTTPS hors loopback"):
        load_settings(tmp_path / "missing.json", environ={}, **kwargs)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://LOCALHOST.:8000/api",
        "http://127.42.3.9:8000",
        "http://[::1]:8000",
    ],
)
def test_plain_http_is_allowed_for_loopback(tmp_path, url):
    settings = load_settings(
        tmp_path / "missing.json",
        environ={},
        api_url=url,
        web_url=url,
    )
    assert settings.api_url == url.rstrip("/")


def test_credentials_are_ignored_after_api_origin_change(tmp_path):
    path = tmp_path / "config.json"
    original = Settings(
        api_url="https://api.example.test/v1",
        web_url="https://app.example.test",
    ).with_session("bound-cookie", "bound-csrf")
    save_settings(path, original)

    changed = load_settings(
        path,
        environ={},
        api_url="https://other.example.test/v1",
    )

    assert changed.session_cookie is None
    assert changed.csrf_token is None
    assert changed.session_origin is None
    assert not changed.authenticated

    changed_from_environment = load_settings(
        path,
        environ={"ACP_API_URL": "https://environment.example.test/v1"},
    )
    assert changed_from_environment.session_cookie is None
    assert changed_from_environment.csrf_token is None
    assert not changed_from_environment.authenticated


def test_same_normalized_origin_keeps_credentials(tmp_path):
    path = tmp_path / "config.json"
    original = Settings(
        api_url="https://API.Example.Test:443/v1/",
        web_url="https://app.example.test",
    ).with_session("bound-cookie", "bound-csrf")
    save_settings(path, original)

    same_origin = load_settings(
        path,
        environ={},
        api_url="https://api.example.test/v2",
    )

    assert normalized_origin(same_origin.api_url) == "https://api.example.test"
    assert same_origin.session_cookie == "bound-cookie"
    assert same_origin.csrf_token == "bound-csrf"
    assert same_origin.authenticated


def test_api_endpoint_keeps_path_separate_from_credential_origin():
    assert normalized_origin("https://API.example.test:443/v1/") == (
        "https://api.example.test"
    )
    assert normalized_api_endpoint("https://API.example.test:443/v1/") == (
        "https://api.example.test/v1"
    )
    assert normalized_api_endpoint("https://api.example.test/v2") != (
        "https://api.example.test/v1"
    )


def test_mutate_settings_serializes_competing_process_style_updates(tmp_path):
    path = tmp_path / "config.json"
    save_settings(
        path,
        Settings().with_session("cookie", "csrf", principal_id="0"),
    )

    def increment_many() -> None:
        for _ in range(12):
            def increment(current: Settings):
                next_value = int(current.principal_id or "0") + 1
                # Élargit volontairement la fenêtre qui perdrait une mise à jour
                # si la relecture et l'écriture n'étaient pas sous le même verrou.
                time.sleep(0.002)
                return replace(current, principal_id=str(next_value)), None

            mutate_settings(path, increment, environ={})

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(increment_many) for _ in range(4)]
        for future in futures:
            future.result()

    assert load_settings(path, environ={}).principal_id == "48"


def test_mutate_settings_serializes_real_spawned_processes(tmp_path):
    path = tmp_path / "config.json"
    save_settings(
        path,
        Settings().with_session("cookie", "csrf", principal_id="0"),
    )
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    processes = [
        context.Process(
            target=_increment_config_in_process,
            args=(str(path), start_event, 8),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(20)
    try:
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)

    assert load_settings(path, environ={}).principal_id == "16"


def test_pending_dispatch_lock_excludes_another_process(tmp_path):
    path = tmp_path / "config.json"
    context = multiprocessing.get_context("spawn")
    held_event = context.Event()
    release_event = context.Event()
    process = context.Process(
        target=_hold_pending_dispatch_lock,
        args=(str(path), held_event, release_event),
    )
    process.start()
    try:
        assert held_event.wait(10)
        with pytest.raises(ConfigError, match="déjà en cours"):
            with pending_dispatch_lock(path):
                pytest.fail("the second process acquired the dispatch lock")
    finally:
        release_event.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(5)

    assert process.exitcode == 0
