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
