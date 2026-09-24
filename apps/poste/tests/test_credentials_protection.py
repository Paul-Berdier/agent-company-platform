"""Protection DPAPI du poste : vrai DPAPI sous Windows, refus explicite ailleurs.

Le module servira au jeton machine en P5 (docs/refonte/plan.md). Ces tests
remplacent ceux que portait ``tests/test_state.py`` du worker (étiquette
archive/acp-0.10.0-avant-hermes), retiré avec l'enrôlement auprès de l'API.
"""

import os

import pytest

from acp_poste import credentials_protection
from acp_poste.credentials_protection import (
    CredentialProtectionError,
    protect_credentials,
    unprotect_credentials,
    uses_windows_protection,
)

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="DPAPI réel propre à Windows")
PAYLOAD = b'{"machine_token": "secret-token-de-test"}'


def test_protection_is_announced_only_on_windows():
    assert uses_windows_protection() is (os.name == "nt")


@pytest.mark.parametrize("operation", [protect_credentials, unprotect_credentials])
def test_without_windows_protection_nothing_is_attempted(monkeypatch, operation):
    # Hors Windows, aucun appel natif : le refus précède tout chargement de crypt32.
    monkeypatch.setattr(credentials_protection, "uses_windows_protection", lambda: False)

    def no_native_call(*_args, **_kwargs):
        pytest.fail("aucun appel natif sans protection Windows")

    monkeypatch.setattr(credentials_protection.ctypes, "WinDLL", no_native_call, raising=False)
    with pytest.raises(CredentialProtectionError, match="exigent DPAPI Windows"):
        operation(PAYLOAD)


@WINDOWS_ONLY
def test_windows_dpapi_round_trip_hides_the_payload():
    protected = protect_credentials(PAYLOAD)
    assert protected != PAYLOAD
    assert b"secret-token-de-test" not in protected
    assert unprotect_credentials(protected) == PAYLOAD


@WINDOWS_ONLY
@pytest.mark.parametrize("position", ["milieu", "fin"])
def test_windows_dpapi_refuses_an_altered_blob(position):
    protected = bytearray(protect_credentials(PAYLOAD))
    index = len(protected) // 2 if position == "milieu" else len(protected) - 1
    protected[index] ^= 0xFF
    with pytest.raises(CredentialProtectionError, match="DPAPI Windows a refusé"):
        unprotect_credentials(bytes(protected))


@WINDOWS_ONLY
def test_windows_dpapi_refuses_a_blob_that_was_never_protected():
    with pytest.raises(CredentialProtectionError, match="DPAPI Windows a refusé"):
        unprotect_credentials(PAYLOAD)


@WINDOWS_ONLY
@pytest.mark.parametrize("operation", [protect_credentials, unprotect_credentials])
@pytest.mark.parametrize("size", [0, 1024 * 1024 + 1], ids=["vide", "plus-de-1-Mio"])
def test_windows_dpapi_refuses_an_empty_or_oversized_payload(operation, size):
    with pytest.raises(CredentialProtectionError, match="Taille des credentials DPAPI invalide"):
        operation(b"x" * size)
