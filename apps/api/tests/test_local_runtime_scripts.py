"""Le profil tiers ne remplace ni l'écoute loopback ni les secrets du lanceur."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("hermes_profile_guard", ROOT / "scripts/check_hermes_profile.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.mark.parametrize("key", ["API_SERVER_HOST", "api_server_key", "HERMES_HOME", "HERMES_LAZY_INSTALL_TARGET"])
def test_profile_cannot_replace_launch_boundaries(tmp_path, key):
    source, profile = tmp_path / "source", tmp_path / "profile"
    profile.mkdir()
    (profile / ".env").write_text(f'{key}="private-value-not-for-errors"\n', encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        guard.check_profile(source, profile)
    assert "private-value-not-for-errors" not in str(caught.value)


def test_checkout_dotenv_is_refused_even_with_fresh_profile(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=unexpected\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checkout"):
        guard.check_profile(tmp_path, tmp_path / "new-profile")


def test_provider_credentials_remain_in_profile_without_loading_parent_env(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=synthetic\n", encoding="utf-8")
    guard.check_profile(tmp_path / "source", tmp_path)
    assert "OPENAI_API_KEY" not in guard.os.environ


def test_managed_environment_cannot_override_bind_address(tmp_path):
    managed = tmp_path / "managed"
    managed.mkdir()
    (managed / ".env").write_text("API_SERVER_HOST=0.0.0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="API_SERVER_HOST"):
        guard.check_profile(tmp_path / "source", tmp_path / "profile", managed=managed)


@pytest.mark.parametrize("filename", [".env", ".op.env"])
def test_loader_cannot_turn_nul_obfuscated_key_into_reserved_setting(tmp_path, filename):
    (tmp_path / filename).write_bytes(b"API_\x00SERVER_HOST=0.0.0.0\n")
    with pytest.raises(ValueError, match="NUL"):
        guard.check_profile(tmp_path / "source", tmp_path)


def test_external_secret_injection_requires_separate_configuration(tmp_path):
    (tmp_path / "config.yaml").write_text("secrets:\n  sources: [external]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="externes"):
        guard.check_profile(tmp_path / "source", tmp_path)
