"""Coffre de secrets : configuration, chiffrement, rotation et génération de clé."""

import subprocess
import sys

import pytest
from cryptography.fernet import Fernet

from acp_api import secrets_vault
from acp_api.secrets_vault import (
    SecretsVault,
    VaultDecryptionFailed,
    VaultNotConfigured,
    generate_key,
    get_vault,
    key_id,
    load_keys,
    vault_status,
)


def test_missing_keys_raise_and_status_is_actionable():
    with pytest.raises(VaultNotConfigured) as excinfo:
        get_vault({})
    assert "ACP_SECRETS_KEYS" in str(excinfo.value)
    status = vault_status({})
    assert status.configured is False
    assert status.primary_key_id is None and status.key_count == 0
    assert "ACP_SECRETS_KEYS" in status.message and "generate-key" in status.message


def test_blank_value_counts_as_missing():
    with pytest.raises(VaultNotConfigured):
        load_keys({"ACP_SECRETS_KEYS": " , "})


def test_invalid_key_raises_an_explicit_error():
    with pytest.raises(VaultNotConfigured) as excinfo:
        load_keys({"ACP_SECRETS_KEYS": "not-a-fernet-key"})
    assert "invalide" in str(excinfo.value)
    with pytest.raises(VaultNotConfigured) as excinfo:
        load_keys({"ACP_SECRETS_KEYS": f"{generate_key()},bad"})
    assert "2" in str(excinfo.value)
    status = vault_status({"ACP_SECRETS_KEYS": "bad"})
    assert status.configured is False and "invalide" in status.message


def test_encrypt_and_decrypt_round_trip():
    key = generate_key()
    vault = get_vault({"ACP_SECRETS_KEYS": key})
    kid, token = vault.encrypt("hunter2-value")
    assert kid == vault.primary_key_id == key_id(key.encode("ascii"))
    assert len(kid) == 12 and int(kid, 16) >= 0
    assert "hunter2" not in token
    assert vault.decrypt(token) == "hunter2-value"
    status = vault.status()
    assert status.configured is True and status.key_count == 1
    assert status.primary_key_id == kid and status.message


def test_rotation_keeps_old_tokens_readable_and_changes_key_id():
    old_key, new_key = generate_key(), generate_key()
    old_vault = get_vault({"ACP_SECRETS_KEYS": old_key})
    old_kid, old_token = old_vault.encrypt("v1")
    rotated = get_vault({"ACP_SECRETS_KEYS": f"{new_key}, {old_key}"})
    assert rotated.decrypt(old_token) == "v1"
    assert rotated.primary_key_id != old_kid
    new_kid, new_token = rotated.encrypt("v1")
    assert new_kid == rotated.primary_key_id
    assert new_token != old_token
    assert rotated.status().key_count == 2
    with pytest.raises(VaultDecryptionFailed):
        old_vault.decrypt(new_token)


def test_tampered_token_is_refused():
    vault = get_vault({"ACP_SECRETS_KEYS": generate_key()})
    _, token = vault.encrypt("x")
    with pytest.raises(VaultDecryptionFailed):
        vault.decrypt("garbage")
    with pytest.raises(VaultDecryptionFailed):
        vault.decrypt(token[:-8] + "AAAAAAAA")


def test_generate_key_is_accepted_by_load_keys():
    key = generate_key()
    assert load_keys({"ACP_SECRETS_KEYS": key}) == [key.encode("ascii")]
    Fernet(key.encode("ascii"))
    assert generate_key() != key


def test_default_environ_is_the_process_environment(monkeypatch):
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    assert vault_status().configured is True
    assert isinstance(get_vault(), SecretsVault)
    monkeypatch.delenv("ACP_SECRETS_KEYS")
    assert vault_status().configured is False
    with pytest.raises(VaultNotConfigured):
        get_vault()


def test_vault_repr_never_contains_key_material():
    key = generate_key()
    vault = get_vault({"ACP_SECRETS_KEYS": key})
    assert key not in repr(vault) and key not in str(vault)
    assert key[:10] not in repr(vault)


def test_cli_generate_key_prints_a_valid_key():
    result = subprocess.run(
        [sys.executable, "-m", "acp_api.secrets_vault", "generate-key"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    key = result.stdout.strip()
    Fernet(key.encode("ascii"))
    assert load_keys({"ACP_SECRETS_KEYS": key})


def test_cli_rejects_unknown_command(capsys):
    assert secrets_vault.main(["frobnicate"]) == 2
    assert "generate-key" in capsys.readouterr().err
    assert secrets_vault.main([]) == 2
