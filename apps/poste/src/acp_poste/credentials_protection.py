"""Protection DPAPI liée au compte Windows courant, sans interface interactive.

Étape P5 (cahier P5 § 5.4) : l'entropie complémentaire est propre à chaque **usage** (jeton machine, jeton Claude) ;
un blob d'un usage ne se déchiffre pas avec l'autre. Portée utilisateur (jamais ``CRYPTPROTECT_LOCAL_MACHINE``),
``CRYPTPROTECT_UI_FORBIDDEN``.
"""

import ctypes
import os
from ctypes import wintypes

ENTROPIE_MIN = 8
ENTROPIE_MAX = 128


class CredentialProtectionError(RuntimeError):
    """Le système n'a pas pu protéger ou relire les credentials."""


def uses_windows_protection() -> bool:
    return os.name == "nt"


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _transform(payload: bytes, *, decrypt: bool, usage: bytes) -> bytes:
    if not uses_windows_protection():
        raise CredentialProtectionError("Ces credentials exigent DPAPI Windows.")
    if not isinstance(usage, bytes) or not ENTROPIE_MIN <= len(usage) <= ENTROPIE_MAX:
        raise CredentialProtectionError("Usage DPAPI invalide : une entropie de 8 à 128 octets est exigée.")
    if not payload or len(payload) > 1024 * 1024:
        raise CredentialProtectionError("Taille des credentials DPAPI invalide.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    operation.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
    source = _Blob(len(payload), buffer)
    entropy_buffer = (ctypes.c_ubyte * len(usage)).from_buffer_copy(usage)
    entropy = _Blob(len(usage), entropy_buffer)
    destination = _Blob()
    try:
        # CRYPTPROTECT_UI_FORBIDDEN ; pas de portée machine, donc compte courant.
        if not operation(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                         0x1, ctypes.byref(destination)):
            raise CredentialProtectionError("DPAPI Windows a refusé les credentials.")
        return ctypes.string_at(destination.data, destination.size)
    finally:
        ctypes.memset(buffer, 0, len(payload))
        if destination.data:
            ctypes.memset(destination.data, 0, destination.size)
            kernel32.LocalFree(destination.data)


def protect_credentials(payload: bytes, *, usage: bytes) -> bytes:
    return _transform(payload, decrypt=False, usage=usage)


def unprotect_credentials(payload: bytes, *, usage: bytes) -> bytes:
    return _transform(payload, decrypt=True, usage=usage)
