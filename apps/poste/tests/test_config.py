"""Origine de service du poste (``normalize_service_origin``, repris de P0).

Étape P5 : ``PosteConfig.from_env`` et les réglages ``ACP_WORKER_*`` ont disparu (``poste.toml``,
``test_politique.py``) ; l'origine de Hermes est de plus exigée en HTTPS partout (``test_origine_boucle_locale_http_refusee``).
"""

import pytest

from acp_poste.config import PosteConfigurationError, normalize_service_origin


def test_origins_are_normalized_and_http_is_limited_to_loopback():
    assert normalize_service_origin("https://API.EXAMPLE:443/", setting="X") == "https://api.example"
    assert normalize_service_origin("http://[::1]:80/", setting="X") == "http://[::1]"
    assert normalize_service_origin("http://127.0.0.1:9119", setting="X") == "http://127.0.0.1:9119"


def test_external_http_origin_is_rejected():
    with pytest.raises(PosteConfigurationError, match="HTTPS"):
        normalize_service_origin("http://service.example", setting="X")


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@api.example",
        "https://api.example?token=secret",
        "https://api.example?",
        "https://api.example#fragment",
        "https://api.example#",
        "https://api.example/v1",
        "https://api.example%2f.evil",
        "https://api_example",
        "https://api.example:0",
    ],
)
def test_origin_rejects_userinfo_query_fragment_and_path(url: str):
    with pytest.raises(PosteConfigurationError):
        normalize_service_origin(url, setting="X")
