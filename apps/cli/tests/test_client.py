from __future__ import annotations

from typing import Any

import httpx

from acp_cli.client import ACPClient
from acp_cli.config import Settings


def test_http_client_ignores_environment_proxy_configuration(monkeypatch):
    constructed_with: dict[str, Any] = {}

    class RecordingClient:
        def __init__(self, **kwargs: Any) -> None:
            constructed_with.update(kwargs)

        def __enter__(self) -> "RecordingClient":
            return self

        def __exit__(self, *_exception: object) -> bool:
            return False

        def request(self, _method: str, _path: str, **_kwargs: Any) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx, "Client", RecordingClient)

    result = ACPClient(
        Settings(
            api_url="https://api.example.test",
            web_url="https://app.example.test",
        )
    ).request("GET", "/health", authenticated=False)

    assert result == {"status": "ok"}
    assert constructed_with["trust_env"] is False
