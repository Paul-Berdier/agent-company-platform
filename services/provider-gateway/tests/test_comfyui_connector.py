"""Tests de frontière du connecteur image ComfyUI."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import acp_provider_gateway.main as gateway_main
from acp_provider_gateway.providers.comfyui import (
    ComfyUIBusyError,
    ComfyUIConfigurationError,
    ComfyUIConnector,
    ComfyUIHTTPError,
    ComfyUIIdempotencyConflict,
    ComfyUIImage,
    ComfyUIImageRequest,
    ComfyUISettings,
    ComfyUITimeoutError,
    ComfyUIUpstreamError,
)


GATEWAY_TOKEN = "gateway-internal-secret"
UPSTREAM_TOKEN = "comfyui-upstream-secret"
PROMPT_ID = "prompt_0123456789abcdef"
PNG = b"\x89PNG\r\n\x1a\n" + b"safe-png"
JPEG = b"\xff\xd8\xff\xe0" + b"safe-jpeg"
WEBP = b"RIFF\x08\x00\x00\x00WEBP" + b"safe-webp"


@pytest.fixture(autouse=True)
def _gateway_auth(monkeypatch):
    monkeypatch.setenv("ACP_GATEWAY_SERVICE_TOKEN", GATEWAY_TOKEN)


def _authorization(*, key: str | None = "image-request-1") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {GATEWAY_TOKEN}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _workflow_file(tmp_path: Path) -> Path:
    path = tmp_path / "operator-workflow.json"
    path.write_text(
        json.dumps(
            {
                "3": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "text": "operator placeholder",
                        "clip": ["1", 0],
                    },
                },
                "9": {
                    "class_type": "SaveImage",
                    "inputs": {
                        "images": ["8", 0],
                        "filename_prefix": "ACP",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _settings(
    workflow_path: Path,
    *,
    origin: str = "https://comfy.test",
    max_polls: int = 2,
    max_image_bytes: int = 1024,
    cache_entries: int = 8,
    cache_max_bytes: int = 8 * 1024,
    max_inflight: int = 4,
    max_waiters: int = 16,
    api_token: str = UPSTREAM_TOKEN,
) -> ComfyUISettings:
    return ComfyUISettings(
        enabled=True,
        origin=origin,
        workflow_path=str(workflow_path),
        prompt_node_id="3",
        prompt_input="text",
        output_node_id="9",
        api_token=api_token,
        timeout_seconds=1,
        poll_interval_seconds=0,
        max_polls=max_polls,
        max_image_bytes=max_image_bytes,
        max_inflight_generations=max_inflight,
        max_inflight_waiters=max_waiters,
        idempotency_max_entries=cache_entries,
        idempotency_max_bytes=cache_max_bytes,
        idempotency_ttl_seconds=60,
    )


def _history(
    *,
    filename: str = "ACP_00001_.png",
    subfolder: str = "",
    output_type: str = "output",
    extra: dict | None = None,
) -> dict:
    metadata = {
        "filename": filename,
        "subfolder": subfolder,
        "type": output_type,
    }
    if extra:
        metadata.update(extra)
    return {
        PROMPT_ID: {
            "outputs": {
                "9": {
                    "images": [metadata],
                }
            }
        }
    }


def _success_handler(
    requests: list[httpx.Request],
    *,
    content: bytes = PNG,
    media_type: str = "image/png",
    filename: str = "ACP_00001_.png",
):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"ok": True}})
        if request.url.path == "/prompt" and request.method == "POST":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID, "number": 1})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json=_history(filename=filename))
        if request.url.path == "/view":
            return httpx.Response(200, content=content, headers={"Content-Type": media_type})
        return httpx.Response(404)

    return handler


def test_disabled_is_fail_closed_and_never_calls_upstream(monkeypatch):
    calls: list[httpx.Request] = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    connector = ComfyUIConnector(
        ComfyUISettings(enabled=False), transport=httpx.MockTransport(unexpected)
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)
    with TestClient(gateway_main.app) as client:
        diagnostic = client.get(
            "/v1/providers/comfyui/diagnostic", headers=_authorization(key=None)
        )
        generation = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "un phare"},
            headers=_authorization(),
        )

    assert diagnostic.status_code == 200
    assert diagnostic.json() == {
        "provider_id": "comfyui",
        "status": "not_configured",
        "configured": False,
        "ready": False,
        "detail": "Connecteur ComfyUI non activé",
        "idempotency_scope": "bounded_process_memory",
        "idempotency_durable": False,
        "worker_integration": False,
    }
    assert generation.status_code == 503
    assert calls == []


@pytest.mark.parametrize(
    "origin",
    [
        "http://comfy.example",
        "https://user:password@comfy.example",
        "https://comfy.example/api",
        "https://comfy.example?token=secret",
        "comfy.example",
    ],
)
def test_invalid_origin_is_reported_without_upstream_call(
    monkeypatch, tmp_path, origin
):
    calls: list[httpx.Request] = []
    workflow_path = _workflow_file(tmp_path)
    monkeypatch.setenv("ACP_COMFYUI_ENABLED", "1")
    monkeypatch.setenv("ACP_COMFYUI_ORIGIN", origin)
    monkeypatch.delenv("ACP_COMFYUI_BASE_URL", raising=False)
    monkeypatch.setenv("ACP_COMFYUI_WORKFLOW_PATH", str(workflow_path))
    monkeypatch.setenv("ACP_COMFYUI_PROMPT_NODE_ID", "3")
    monkeypatch.setenv("ACP_COMFYUI_PROMPT_INPUT", "text")
    monkeypatch.setenv("ACP_COMFYUI_OUTPUT_NODE_ID", "9")

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(transport=httpx.MockTransport(unexpected)),
    )
    with TestClient(gateway_main.app) as client:
        diagnostic = client.get(
            "/v1/providers/comfyui/diagnostic", headers=_authorization(key=None)
        )
        generation = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "un phare"},
            headers=_authorization(),
        )

    assert diagnostic.status_code == 200
    assert diagnostic.json()["status"] == "invalid_configuration"
    assert generation.status_code == 503
    assert "secret" not in diagnostic.text
    assert calls == []


def test_http_loopback_origin_is_allowed(tmp_path):
    settings = _settings(_workflow_file(tmp_path), origin="http://127.0.0.1:8188")
    assert settings.origin == "http://127.0.0.1:8188"


def test_environment_activation_is_strict_and_partial_configuration_fails_closed(
    monkeypatch,
):
    monkeypatch.setenv("ACP_COMFYUI_ENABLED", "true")
    with pytest.raises(ComfyUIConfigurationError, match="uniquement 0 ou 1"):
        ComfyUISettings.from_environment()

    monkeypatch.setenv("ACP_COMFYUI_ENABLED", "0")
    monkeypatch.setenv("ACP_COMFYUI_ORIGIN", "https://comfy.example")
    with pytest.raises(ComfyUIConfigurationError, match="ENABLED=1"):
        ComfyUISettings.from_environment()

    monkeypatch.delenv("ACP_COMFYUI_ORIGIN")
    monkeypatch.setenv("ACP_COMFYUI_MAX_INFLIGHT_GENERATIONS", "2")
    with pytest.raises(ComfyUIConfigurationError, match="ENABLED=1"):
        ComfyUISettings.from_environment()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"max_image_bytes": 1024, "cache_max_bytes": 1023},
            "au moins une image",
        ),
        (
            {
                "max_image_bytes": 100 * 1024 * 1024,
                "cache_max_bytes": 100 * 1024 * 1024,
                "max_inflight": 2,
            },
            "produit concurrence/taille",
        ),
        ({"max_inflight": 33}, "Concurrence"),
        ({"max_waiters": 65}, "Attentes"),
        ({"cache_max_bytes": 257 * 1024 * 1024}, "Budget mémoire"),
    ],
)
def test_memory_and_concurrency_limits_fail_closed(tmp_path, overrides, message):
    with pytest.raises(ComfyUIConfigurationError, match=message):
        _settings(_workflow_file(tmp_path), **overrides)


def test_api_token_cannot_inject_headers(tmp_path):
    with pytest.raises(ComfyUIConfigurationError, match="Jeton"):
        _settings(_workflow_file(tmp_path), api_token="secret\r\nX-Injected: yes")


def test_gateway_bearer_protects_diagnostic_and_generation(monkeypatch):
    calls: list[httpx.Request] = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(
            ComfyUISettings(enabled=False), transport=httpx.MockTransport(unexpected)
        ),
    )
    with TestClient(gateway_main.app) as client:
        assert client.get("/v1/providers/comfyui/diagnostic").status_code == 401
        assert (
            client.post(
                "/v1/providers/comfyui/images",
                json={"prompt": "x"},
                headers={"Idempotency-Key": "key"},
            ).status_code
            == 401
        )
        monkeypatch.delenv("ACP_GATEWAY_SERVICE_TOKEN")
        assert (
            client.get(
                "/v1/providers/comfyui/diagnostic",
                headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            ).status_code
            == 503
        )
    assert calls == []


def test_diagnostic_calls_only_system_stats_and_redacts_configuration(
    monkeypatch, tmp_path
):
    requests: list[httpx.Request] = []
    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path)),
        transport=httpx.MockTransport(_success_handler(requests)),
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)

    with TestClient(gateway_main.app) as client:
        response = client.get(
            "/v1/providers/comfyui/diagnostic", headers=_authorization(key=None)
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["worker_integration"] is False
    assert [request.url.path for request in requests] == ["/system_stats"]
    assert requests[0].headers["Authorization"] == f"Bearer {UPSTREAM_TOKEN}"
    assert UPSTREAM_TOKEN not in response.text
    assert "comfy.test" not in response.text
    assert "operator-workflow" not in response.text


def test_generation_structurally_injects_prompt_and_sets_download_headers(
    monkeypatch, tmp_path
):
    requests: list[httpx.Request] = []
    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path)),
        transport=httpx.MockTransport(_success_handler(requests)),
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)
    prompt = 'portrait avec {{"workflow":"hostile"}} et $variables'

    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": prompt},
            headers=_authorization(),
        )

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == 'attachment; filename="ACP_00001_.png"'
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["idempotency-replayed"] == "false"
    assert response.headers["x-acp-idempotency-scope"] == "bounded-process-memory"

    assert [request.url.path for request in requests] == [
        "/prompt",
        f"/history/{PROMPT_ID}",
        "/view",
    ]
    submitted = json.loads(requests[0].content)
    assert set(submitted) == {"prompt"}
    assert submitted["prompt"]["3"]["inputs"]["text"] == prompt
    assert submitted["prompt"]["3"]["inputs"]["clip"] == ["1", 0]
    assert submitted["prompt"]["9"]["inputs"]["filename_prefix"] == "ACP"
    assert all(
        request.headers["Authorization"] == f"Bearer {UPSTREAM_TOKEN}"
        for request in requests
    )
    assert dict(requests[2].url.params) == {
        "filename": "ACP_00001_.png",
        "subfolder": "",
        "type": "output",
    }


@pytest.mark.parametrize(
    "body",
    [
        {"prompt": "x", "workflow": {"hostile": True}},
        {"prompt": "x", "output_url": "https://attacker.example/file"},
        {"prompt": "x", "view": {"filename": "../../secret"}},
    ],
)
def test_request_cannot_supply_workflow_or_output_location(
    monkeypatch, tmp_path, body
):
    calls: list[httpx.Request] = []
    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path)),
        transport=httpx.MockTransport(lambda request: calls.append(request)),
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json=body,
            headers=_authorization(),
        )
    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize("key", [None, "", "contains space", "x" * 256])
def test_generation_validates_idempotency_key_before_upstream(
    monkeypatch, tmp_path, key
):
    calls: list[httpx.Request] = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(
            _settings(_workflow_file(tmp_path)),
            transport=httpx.MockTransport(unexpected),
        ),
    )
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "x"},
            headers=_authorization(key=key),
        )
    assert response.status_code == 422
    assert calls == []


def test_idempotency_replays_same_request_and_conflicts_on_changed_prompt(
    monkeypatch, tmp_path
):
    requests: list[httpx.Request] = []
    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path)),
        transport=httpx.MockTransport(_success_handler(requests)),
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)
    with TestClient(gateway_main.app) as client:
        first = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "un phare"},
            headers=_authorization(),
        )
        replay = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "un phare"},
            headers=_authorization(),
        )
        conflict = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "une forêt"},
            headers=_authorization(),
        )

    assert first.status_code == 200
    assert first.headers["idempotency-replayed"] == "false"
    assert replay.status_code == 200
    assert replay.headers["idempotency-replayed"] == "true"
    assert conflict.status_code == 409
    assert [request.url.path for request in requests] == [
        "/prompt",
        f"/history/{PROMPT_ID}",
        "/view",
    ]


def test_idempotency_cache_evicts_oldest_entry_at_configured_bound(
    monkeypatch, tmp_path
):
    requests: list[httpx.Request] = []
    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path), cache_entries=1),
        transport=httpx.MockTransport(_success_handler(requests)),
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)
    with TestClient(gateway_main.app) as client:
        for key, prompt in (("key-1", "one"), ("key-2", "two"), ("key-1", "one")):
            response = client.post(
                "/v1/providers/comfyui/images",
                json={"prompt": prompt},
                headers=_authorization(key=key),
            )
            assert response.status_code == 200
            assert response.headers["idempotency-replayed"] == "false"
    assert [request.url.path for request in requests].count("/prompt") == 3


async def test_image_cache_evicts_by_aggregate_payload_bytes(tmp_path):
    requests: list[httpx.Request] = []
    image_bytes = len(PNG)
    connector = ComfyUIConnector(
        _settings(
            _workflow_file(tmp_path),
            max_image_bytes=image_bytes,
            cache_entries=8,
            cache_max_bytes=image_bytes * 2,
            max_inflight=1,
        ),
        transport=httpx.MockTransport(_success_handler(requests)),
    )

    for key, prompt in (("key-1", "one"), ("key-2", "two"), ("key-3", "three")):
        image = await connector.generate(
            ComfyUIImageRequest(prompt=prompt), idempotency_key=key
        )
        assert image.replayed is False

    newest = await connector.generate(
        ComfyUIImageRequest(prompt="three"), idempotency_key="key-3"
    )
    evicted = await connector.generate(
        ComfyUIImageRequest(prompt="one"), idempotency_key="key-1"
    )

    assert newest.replayed is True
    assert evicted.replayed is False
    assert [request.url.path for request in requests].count("/prompt") == 4
    assert connector._cache_image_bytes <= image_bytes * 2


async def test_inflight_limit_rejects_only_new_keys_before_upstream(tmp_path):
    upstream_requests: list[httpx.Request] = []
    prompt_started = asyncio.Event()
    release_prompt = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        upstream_requests.append(request)
        if request.url.path == "/prompt":
            prompt_started.set()
            await release_prompt.wait()
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json=_history())
        if request.url.path == "/view":
            return httpx.Response(
                200, content=PNG, headers={"Content-Type": "image/png"}
            )
        return httpx.Response(404)

    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path), cache_entries=1, max_inflight=1),
        transport=httpx.MockTransport(handler),
    )
    first = asyncio.create_task(
        connector.generate(
            ComfyUIImageRequest(prompt="un phare"), idempotency_key="key-1"
        )
    )
    await prompt_started.wait()

    replay = asyncio.create_task(
        connector.generate(
            ComfyUIImageRequest(prompt="un phare"), idempotency_key="key-1"
        )
    )
    await asyncio.sleep(0)
    assert replay.done() is False

    with pytest.raises(ComfyUIBusyError, match="Capacité"):
        await connector.generate(
            ComfyUIImageRequest(prompt="une forêt"), idempotency_key="key-2"
        )
    assert [request.url.path for request in upstream_requests] == ["/prompt"]

    release_prompt.set()
    first_image, replayed_image = await asyncio.gather(first, replay)
    assert isinstance(first_image, ComfyUIImage)
    assert first_image.replayed is False
    assert replayed_image.replayed is True
    assert [request.url.path for request in upstream_requests] == [
        "/prompt",
        f"/history/{PROMPT_ID}",
        "/view",
    ]


async def test_inflight_limit_maps_to_429_without_second_upstream_effect(
    monkeypatch, tmp_path
):
    upstream_requests: list[httpx.Request] = []
    prompt_started = asyncio.Event()
    release_prompt = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        upstream_requests.append(request)
        if request.url.path == "/prompt":
            prompt_started.set()
            await release_prompt.wait()
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json=_history())
        if request.url.path == "/view":
            return httpx.Response(
                200, content=PNG, headers={"Content-Type": "image/png"}
            )
        return httpx.Response(404)

    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path), cache_entries=1, max_inflight=1),
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)
    transport = httpx.ASGITransport(app=gateway_main.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://gateway.test"
    ) as client:
        first = asyncio.create_task(
            client.post(
                "/v1/providers/comfyui/images",
                json={"prompt": "un phare"},
                headers=_authorization(key="key-1"),
            )
        )
        await prompt_started.wait()
        refused = await client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "une forêt"},
            headers=_authorization(key="key-2"),
        )
        assert refused.status_code == 429
        assert refused.headers["retry-after"] == "1"
        assert refused.json() == {
            "detail": "Trop de générations ComfyUI simultanées"
        }
        assert [request.url.path for request in upstream_requests] == ["/prompt"]

        release_prompt.set()
        completed = await first

    assert completed.status_code == 200


def test_polling_is_bounded_and_never_uses_global_interrupt(monkeypatch, tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json={})
        return httpx.Response(500)

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(
            _settings(_workflow_file(tmp_path), max_polls=2),
            transport=httpx.MockTransport(handler),
        ),
    )
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "lent"},
            headers=_authorization(),
        )

    assert response.status_code == 504
    assert [request.url.path for request in requests] == [
        "/prompt",
        f"/history/{PROMPT_ID}",
        f"/history/{PROMPT_ID}",
    ]
    assert all(request.url.path != "/interrupt" for request in requests)


async def test_poll_timeout_leaves_a_tombstone_and_retry_never_resubmits(tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json={})
        return httpx.Response(500)

    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path), max_polls=1),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ComfyUITimeoutError):
        await connector.generate(
            ComfyUIImageRequest(prompt="lent"), idempotency_key="timeout-key"
        )
    with pytest.raises(ComfyUIIdempotencyConflict):
        await connector.generate(
            ComfyUIImageRequest(prompt="autre"), idempotency_key="timeout-key"
        )
    with pytest.raises(ComfyUITimeoutError):
        await connector.generate(
            ComfyUIImageRequest(prompt="lent"), idempotency_key="timeout-key"
        )

    assert [request.url.path for request in requests] == [
        "/prompt",
        f"/history/{PROMPT_ID}",
    ]


async def test_prompt_request_timeout_leaves_a_tombstone(tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("ambiguous", request=request)

    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path)),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ComfyUITimeoutError):
        await connector.generate(
            ComfyUIImageRequest(prompt="lent"), idempotency_key="prompt-timeout"
        )
    with pytest.raises(ComfyUITimeoutError):
        await connector.generate(
            ComfyUIImageRequest(prompt="lent"), idempotency_key="prompt-timeout"
        )
    assert [request.url.path for request in requests] == ["/prompt"]


async def test_post_submit_failure_leaves_a_safe_tombstone(tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json=_history())
        if request.url.path == "/view":
            return httpx.Response(500, text=UPSTREAM_TOKEN)
        return httpx.Response(404)

    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path)),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ComfyUIHTTPError):
        await connector.generate(
            ComfyUIImageRequest(prompt="cassé"), idempotency_key="failed-key"
        )
    with pytest.raises(ComfyUIUpstreamError, match="indéterminé") as replayed:
        await connector.generate(
            ComfyUIImageRequest(prompt="cassé"), idempotency_key="failed-key"
        )

    assert UPSTREAM_TOKEN not in str(replayed.value)
    assert [request.url.path for request in requests] == [
        "/prompt",
        f"/history/{PROMPT_ID}",
        "/view",
    ]


async def test_cancellation_after_submit_leaves_a_safe_tombstone(tmp_path):
    requests: list[httpx.Request] = []
    polling_started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            polling_started.set()
            await asyncio.Event().wait()
        return httpx.Response(404)

    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path)),
        transport=httpx.MockTransport(handler),
    )
    owner = asyncio.create_task(
        connector.generate(
            ComfyUIImageRequest(prompt="annulé"), idempotency_key="cancelled-key"
        )
    )
    await polling_started.wait()
    waiter = asyncio.create_task(
        connector.generate(
            ComfyUIImageRequest(prompt="annulé"), idempotency_key="cancelled-key"
        )
    )
    await asyncio.sleep(0)
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    with pytest.raises(ComfyUIUpstreamError, match="indéterminé"):
        await waiter

    with pytest.raises(ComfyUIUpstreamError, match="indéterminé"):
        await connector.generate(
            ComfyUIImageRequest(prompt="annulé"), idempotency_key="cancelled-key"
        )
    assert [request.url.path for request in requests].count("/prompt") == 1


async def test_cancelling_one_waiter_does_not_cancel_shared_generation(tmp_path):
    requests: list[httpx.Request] = []
    prompt_started = asyncio.Event()
    release_prompt = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            prompt_started.set()
            await release_prompt.wait()
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json=_history())
        if request.url.path == "/view":
            return httpx.Response(
                200, content=PNG, headers={"Content-Type": "image/png"}
            )
        return httpx.Response(404)

    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path), max_inflight=1),
        transport=httpx.MockTransport(handler),
    )
    owner = asyncio.create_task(
        connector.generate(ComfyUIImageRequest(prompt="x"), idempotency_key="key")
    )
    await prompt_started.wait()
    cancelled_waiter = asyncio.create_task(
        connector.generate(ComfyUIImageRequest(prompt="x"), idempotency_key="key")
    )
    surviving_waiter = asyncio.create_task(
        connector.generate(ComfyUIImageRequest(prompt="x"), idempotency_key="key")
    )
    await asyncio.sleep(0)
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter

    release_prompt.set()
    owner_image, replayed_image = await asyncio.gather(owner, surviving_waiter)
    assert owner_image.replayed is False
    assert replayed_image.replayed is True
    assert [request.url.path for request in requests].count("/prompt") == 1


async def test_same_key_waiters_are_bounded_and_cancellation_releases_capacity(
    tmp_path,
):
    requests: list[httpx.Request] = []
    prompt_started = asyncio.Event()
    release_prompt = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            prompt_started.set()
            await release_prompt.wait()
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json=_history())
        if request.url.path == "/view":
            return httpx.Response(
                200, content=PNG, headers={"Content-Type": "image/png"}
            )
        return httpx.Response(404)

    connector = ComfyUIConnector(
        _settings(
            _workflow_file(tmp_path), max_inflight=1, max_waiters=1
        ),
        transport=httpx.MockTransport(handler),
    )
    owner = asyncio.create_task(
        connector.generate(ComfyUIImageRequest(prompt="x"), idempotency_key="key")
    )
    await prompt_started.wait()
    first_waiter = asyncio.create_task(
        connector.generate(ComfyUIImageRequest(prompt="x"), idempotency_key="key")
    )
    await asyncio.sleep(0)

    with pytest.raises(ComfyUIBusyError, match="attentes"):
        await connector.generate(
            ComfyUIImageRequest(prompt="x"), idempotency_key="key"
        )

    first_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_waiter
    replacement_waiter = asyncio.create_task(
        connector.generate(ComfyUIImageRequest(prompt="x"), idempotency_key="key")
    )
    await asyncio.sleep(0)
    release_prompt.set()
    owner_image, replayed_image = await asyncio.gather(owner, replacement_waiter)

    assert owner_image.replayed is False
    assert replayed_image.replayed is True
    assert connector._inflight_waiters == 0
    assert [request.url.path for request in requests].count("/prompt") == 1


async def test_unexpired_failure_tombstone_is_never_evicted_for_image_bytes(tmp_path):
    requests: list[httpx.Request] = []
    image_bytes = len(PNG)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        submitted_prompts = [
            json.loads(item.content)["prompt"]["3"]["inputs"]["text"]
            for item in requests
            if item.url.path == "/prompt"
        ]
        current_prompt = submitted_prompts[-1] if submitted_prompts else ""
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            if current_prompt == "failure":
                return httpx.Response(200, json={})
            return httpx.Response(200, json=_history())
        if request.url.path == "/view":
            return httpx.Response(
                200, content=PNG, headers={"Content-Type": "image/png"}
            )
        return httpx.Response(404)

    connector = ComfyUIConnector(
        _settings(
            _workflow_file(tmp_path),
            max_polls=1,
            max_image_bytes=image_bytes,
            cache_entries=4,
            cache_max_bytes=image_bytes,
            max_inflight=1,
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ComfyUITimeoutError):
        await connector.generate(
            ComfyUIImageRequest(prompt="failure"), idempotency_key="failed-key"
        )
    for key in ("image-1", "image-2"):
        await connector.generate(
            ComfyUIImageRequest(prompt=key), idempotency_key=key
        )
    with pytest.raises(ComfyUITimeoutError):
        await connector.generate(
            ComfyUIImageRequest(prompt="failure"), idempotency_key="failed-key"
        )

    submitted = [request for request in requests if request.url.path == "/prompt"]
    assert len(submitted) == 3


async def test_tombstone_capacity_is_reserved_before_a_new_prompt(tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json={})
        return httpx.Response(404)

    connector = ComfyUIConnector(
        _settings(
            _workflow_file(tmp_path),
            max_polls=1,
            cache_entries=1,
            max_inflight=1,
        ),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ComfyUITimeoutError):
        await connector.generate(
            ComfyUIImageRequest(prompt="first"), idempotency_key="first-key"
        )
    with pytest.raises(ComfyUIBusyError, match="idempotence"):
        await connector.generate(
            ComfyUIImageRequest(prompt="second"), idempotency_key="second-key"
        )
    assert [request.url.path for request in requests].count("/prompt") == 1


@pytest.mark.parametrize("failure", ["http", "timeout"])
def test_upstream_failures_are_redacted(monkeypatch, tmp_path, failure):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(UPSTREAM_TOKEN, request=request)
        return httpx.Response(
            500,
            json={
                "error": UPSTREAM_TOKEN,
                "workflow": {"private": True},
                "url": "https://private-comfy.example",
            },
        )

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(
            _settings(_workflow_file(tmp_path)),
            transport=httpx.MockTransport(handler),
        ),
    )
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "x"},
            headers=_authorization(),
        )

    assert response.status_code == (504 if failure == "timeout" else 502)
    assert UPSTREAM_TOKEN not in response.text
    assert "private-comfy" not in response.text
    assert "workflow" not in response.text


@pytest.mark.parametrize(
    "history",
    [
        {"other_prompt": {"outputs": {}}},
        {PROMPT_ID: []},
        {PROMPT_ID: {"outputs": []}},
        {PROMPT_ID: {"outputs": {"other_node": {"images": []}}}},
        {PROMPT_ID: {"outputs": {"9": {"images": "not-a-list"}}}},
    ],
)
def test_malformed_history_fails_closed_without_view(
    monkeypatch, tmp_path, history
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(200, json=history)
        return httpx.Response(500)

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(
            _settings(_workflow_file(tmp_path)),
            transport=httpx.MockTransport(handler),
        ),
    )
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "x"},
            headers=_authorization(),
        )
    assert response.status_code == 502
    assert all(request.url.path != "/view" for request in requests)


@pytest.mark.parametrize(
    "metadata",
    [
        {"filename": "../../secret.png", "subfolder": "", "type": "output"},
        {"filename": "safe.png", "subfolder": "../private", "type": "output"},
        {"filename": "safe.png", "subfolder": "", "type": "input"},
        {
            "filename": "safe.png",
            "subfolder": "",
            "type": "output",
            "url": "https://attacker.example/secret.png",
        },
    ],
)
def test_hostile_output_metadata_never_reaches_view(
    monkeypatch, tmp_path, metadata
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": PROMPT_ID})
        if request.url.path == f"/history/{PROMPT_ID}":
            return httpx.Response(
                200,
                json={
                    PROMPT_ID: {
                        "outputs": {"9": {"images": [metadata]}},
                    }
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(
            _settings(_workflow_file(tmp_path)),
            transport=httpx.MockTransport(handler),
        ),
    )
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "x"},
            headers=_authorization(),
        )
    assert response.status_code == 502
    assert all(request.url.path != "/view" for request in requests)


@pytest.mark.parametrize(
    ("content", "media_type", "filename"),
    [
        (PNG, "image/png", "safe.png"),
        (JPEG, "image/jpeg", "safe.jpeg"),
        (WEBP, "image/webp", "safe.webp"),
    ],
)
def test_allowed_image_types_require_matching_magic_and_extension(
    monkeypatch, tmp_path, content, media_type, filename
):
    requests: list[httpx.Request] = []
    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path)),
        transport=httpx.MockTransport(
            _success_handler(
                requests,
                content=content,
                media_type=media_type,
                filename=filename,
            )
        ),
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "x"},
            headers=_authorization(),
        )
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == media_type


@pytest.mark.parametrize(
    ("content", "media_type", "filename", "limit"),
    [
        (PNG, "text/html", "safe.png", 1024),
        (JPEG, "image/png", "safe.png", 1024),
        (PNG, "image/png", "safe.jpg", 1024),
        (PNG + b"too-large", "image/png", "safe.png", len(PNG)),
    ],
)
def test_image_type_magic_extension_and_size_fail_closed(
    monkeypatch, tmp_path, content, media_type, filename, limit
):
    requests: list[httpx.Request] = []
    connector = ComfyUIConnector(
        _settings(_workflow_file(tmp_path), max_image_bytes=limit),
        transport=httpx.MockTransport(
            _success_handler(
                requests,
                content=content,
                media_type=media_type,
                filename=filename,
            )
        ),
    )
    monkeypatch.setattr(gateway_main, "comfyui_connector", connector)
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "x"},
            headers=_authorization(),
        )
    assert response.status_code == 502


def test_prompt_id_is_validated_before_building_history_path(monkeypatch, tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"prompt_id": "../../private"})

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(
            _settings(_workflow_file(tmp_path)),
            transport=httpx.MockTransport(handler),
        ),
    )
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "x"},
            headers=_authorization(),
        )
    assert response.status_code == 502
    assert [request.url.path for request in requests] == ["/prompt"]


def test_oversized_operator_workflow_is_rejected_before_upstream(
    monkeypatch, tmp_path
):
    workflow_path = tmp_path / "oversized.json"
    workflow_path.write_bytes(b"{" + b" " * (2 * 1024 * 1024) + b"}")
    calls: list[httpx.Request] = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(
        gateway_main,
        "comfyui_connector",
        ComfyUIConnector(
            _settings(workflow_path), transport=httpx.MockTransport(unexpected)
        ),
    )
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/comfyui/images",
            json={"prompt": "x"},
            headers=_authorization(),
        )
    assert response.status_code == 503
    assert calls == []
