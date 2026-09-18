import pytest
from fastapi import HTTPException, Request, Response

from acp_api.preview import configured_preview_cors_origins, create_preview_app
from acp_api.routers import artifacts as artifacts_router


def test_preview_app_exposes_only_health_and_signed_content():
    app = create_preview_app(
        {"ACP_CORS_ORIGINS": "https://app.example.test,http://127.0.0.1:5173"}
    )

    flattened = []
    for route in app.routes:
        nested = getattr(route, "original_router", None)
        flattened.extend(nested.routes if nested is not None else [route])
    routes = {
        (route.path, frozenset(route.methods or set()))
        for route in flattened
        if getattr(route, "path", None)
    }
    assert routes == {
        ("/health", frozenset({"GET"})),
        ("/ready", frozenset({"GET"})),
        ("/artifacts/{artifact_id}/content", frozenset({"GET"})),
    }
    paths = {path for path, _methods in routes}
    assert "/auth/session" not in paths
    assert "/missions" not in paths
    assert "/openapi.json" not in paths


def test_preview_cors_allowlist_is_exact_deduplicated_and_has_no_wildcard():
    assert configured_preview_cors_origins(
        {
            "ACP_CORS_ORIGINS": (
                "https://app.example.test,https://app.example.test,"
                "http://localhost:5173"
            )
        }
    ) == ["https://app.example.test", "http://localhost:5173"]

    with pytest.raises(ValueError, match="générique"):
        configured_preview_cors_origins({"ACP_CORS_ORIGINS": "*"})
    with pytest.raises(ValueError, match="origine vide"):
        configured_preview_cors_origins(
            {"ACP_CORS_ORIGINS": "https://app.example.test,"}
        )
    with pytest.raises(ValueError, match="invalide"):
        configured_preview_cors_origins(
            {"ACP_CORS_ORIGINS": "https://app.example.test/path"}
        )


def test_preview_cors_middleware_never_allows_credentials():
    app = create_preview_app({"ACP_CORS_ORIGINS": "https://app.example.test"})
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )
    assert cors.kwargs["allow_origins"] == ["https://app.example.test"]
    assert cors.kwargs["allow_credentials"] is False
    assert cors.kwargs["allow_methods"] == ["GET", "HEAD", "OPTIONS"]
    assert cors.kwargs["allow_headers"] == ["Range"]


def _preview_request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/artifacts/artifact-1/content",
            "raw_path": b"/artifacts/artifact-1/content",
            "query_string": b"token=signed",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("preview.example.test", 443),
        }
    )


def test_preview_route_uses_only_a_preview_token_and_serves_inline(monkeypatch):
    artifact = object()
    storage = object()
    recorded: list[str] = []
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        artifacts_router,
        "_link_principal",
        lambda *args, **kwargs: ("user-1", "preview", "link-1"),
    )
    monkeypatch.setattr(
        artifacts_router,
        "_readable_artifact",
        lambda *args, **kwargs: artifact,
    )
    monkeypatch.setattr(artifacts_router, "artifact_storage", lambda: storage)
    monkeypatch.setattr(
        artifacts_router,
        "_record_link_use",
        lambda _db, link_id: recorded.append(link_id),
    )

    def content_response(**kwargs):
        observed.update(kwargs)
        kwargs["on_prepared"]()
        return Response(b"preview", media_type="image/png")

    monkeypatch.setattr(artifacts_router, "_content_response", content_response)

    response = artifacts_router.preview_artifact_content(
        "artifact-1", _preview_request(), token="signed", db=object()
    )

    assert response.body == b"preview"
    assert observed["artifact"] is artifact
    assert observed["storage"] is storage
    assert observed["force_download"] is False
    assert recorded == ["link-1"]


def test_preview_route_rejects_a_download_token(monkeypatch):
    monkeypatch.setattr(
        artifacts_router,
        "_link_principal",
        lambda *args, **kwargs: ("user-1", "download", "link-1"),
    )

    with pytest.raises(HTTPException) as error:
        artifacts_router.preview_artifact_content(
            "artifact-1", _preview_request(), token="signed", db=object()
        )

    assert error.value.status_code == 403
