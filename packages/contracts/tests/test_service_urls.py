import pytest

from acp_contracts import ServiceOriginError, normalize_service_origin


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:80/", "http://localhost"),
        ("http://127.0.0.2:8000", "http://127.0.0.2:8000"),
        ("http://[::1]:8000/", "http://[::1]:8000"),
        ("https://SERVICE.Example:443/", "https://service.example"),
        ("https://service.example:8443", "https://service.example:8443"),
    ],
)
def test_normalizes_safe_service_origins(value: str, expected: str):
    assert normalize_service_origin(value, setting="TEST_URL") == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        " http://localhost",
        "http://localhost ",
        "http://service.example",
        "ftp://service.example",
        "https://user:secret@service.example",
        "https://service.example/path",
        "https://service.example?token=secret",
        "https://service.example?",
        "https://service.example#fragment",
        "https://service.example#",
        "https://service.example:0",
        "https://service_example",
        "https:\\service.example",
    ],
)
def test_rejects_ambiguous_or_insecure_service_origins(value: str):
    with pytest.raises(ServiceOriginError):
        normalize_service_origin(value, setting="TEST_URL")


@pytest.mark.parametrize("host", ["event-service", "events.railway.internal", "10.0.0.4"])
def test_internal_http_requires_an_exact_explicit_private_host(host):
    assert normalize_service_origin(
        f"http://{host}:8000", setting="TEST_URL", internal_http_hosts=host
    ) == f"http://{host}:8000"
    with pytest.raises(ServiceOriginError):
        normalize_service_origin(f"http://{host}:8000", setting="TEST_URL")


@pytest.mark.parametrize("host", ["example.com", "8.8.8.8", "*.railway.internal", "http://event-service", "event-service:8000"])
def test_internal_http_allowlist_cannot_enable_public_or_ambiguous_hosts(host):
    with pytest.raises(ServiceOriginError):
        normalize_service_origin(
            "http://event-service:8000", setting="TEST_URL", internal_http_hosts=host
        )
