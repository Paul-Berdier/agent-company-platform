"""Protection DPAPI du poste : vrai DPAPI sous Windows, refus explicite ailleurs.

Étape P5 (cahier P5 § 5.4) : l'entropie complémentaire est propre à chaque usage (``coffre.USAGES``) ; ces tests
exercent la primitive, ``test_coffre.py`` le coffre qui l'emploie.
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
USAGE = b"ACP poste usage de test v1"


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
        operation(PAYLOAD, usage=USAGE)


@WINDOWS_ONLY
def test_windows_dpapi_round_trip_hides_the_payload():
    protected = protect_credentials(PAYLOAD, usage=USAGE)
    assert protected != PAYLOAD
    assert b"secret-token-de-test" not in protected
    assert unprotect_credentials(protected, usage=USAGE) == PAYLOAD


@WINDOWS_ONLY
@pytest.mark.parametrize("position", ["milieu", "fin"])
def test_windows_dpapi_refuses_an_altered_blob(position):
    protected = bytearray(protect_credentials(PAYLOAD, usage=USAGE))
    index = len(protected) // 2 if position == "milieu" else len(protected) - 1
    protected[index] ^= 0xFF
    with pytest.raises(CredentialProtectionError, match="DPAPI Windows a refusé"):
        unprotect_credentials(bytes(protected), usage=USAGE)


@WINDOWS_ONLY
def test_windows_dpapi_refuses_a_blob_that_was_never_protected():
    with pytest.raises(CredentialProtectionError, match="DPAPI Windows a refusé"):
        unprotect_credentials(PAYLOAD, usage=USAGE)


@WINDOWS_ONLY
@pytest.mark.parametrize("operation", [protect_credentials, unprotect_credentials])
@pytest.mark.parametrize("size", [0, 1024 * 1024 + 1], ids=["vide", "plus-de-1-Mio"])
def test_windows_dpapi_refuses_an_empty_or_oversized_payload(operation, size):
    with pytest.raises(CredentialProtectionError, match="Taille des credentials DPAPI invalide"):
        operation(b"x" * size, usage=USAGE)


@WINDOWS_ONLY
def test_windows_dpapi_refuses_another_usage():
    """Un blob protégé pour un usage ne se relit pas avec l'entropie d'un autre (``test_entropie_par_usage``)."""
    protected = protect_credentials(PAYLOAD, usage=USAGE)
    with pytest.raises(CredentialProtectionError, match="DPAPI Windows a refusé"):
        unprotect_credentials(protected, usage=b"ACP poste autre usage v1")


@pytest.mark.parametrize("usage", [b"", b"court", b"x" * 129, "texte"])
def test_an_invalid_usage_is_refused_before_any_native_call(monkeypatch, usage):
    monkeypatch.setattr(credentials_protection, "uses_windows_protection", lambda: True)
    monkeypatch.setattr(credentials_protection.ctypes, "WinDLL",
                        lambda *_a, **_k: pytest.fail("aucun appel natif"), raising=False)
    with pytest.raises(CredentialProtectionError, match="Usage DPAPI invalide"):
        protect_credentials(PAYLOAD, usage=usage)
