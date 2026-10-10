"""Verrous par fichier du poste (cahier P5 § 6.1 et § 6.2).

- **Verrou d'instance** ``%LOCALAPPDATA%\\ACP\\etat\\poste.verrou`` : pris par ``acp-poste servir`` et tenu toute la
  vie du processus ; une seconde instance dans le même compte s'arrête (code 3). Le système le libère à la mort
  du processus. Préféré à un mutex nommé : la tâche planifiée (session 0) et une console ``runas`` (session
  interactive) partagent ce fichier puisqu'elles tournent sous le même compte, sans dépendre des espaces de noms
  ``Global\\``/``Local\\``.
- **Verrou des sondes** ``…\\etat\\sondes.verrou`` : tenu par chaque cycle de sondes du service et par les
  commandes de console qui lancent Codex (``connexion codex``, ``connexion bac-a-sable``, ``releve``,
  ``preuve model-list``) : deux ``codex app-server`` ne se croisent jamais sur le même ``CODEX_HOME``.

Windows : ``LockFileEx`` exclusif et non bloquant sur un octet. Ailleurs (tests) : ``flock``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import BinaryIO


class VerrouOccupe(RuntimeError):
    """Le verrou est tenu par un autre processus (ou une autre poignée)."""


def _verrouiller(flux: BinaryIO) -> bool:
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        class _OVERLAPPED(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                        ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                        wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
        kernel32.LockFileEx.restype = wintypes.BOOL
        recouvrement = _OVERLAPPED()
        poignee = msvcrt.get_osfhandle(flux.fileno())
        # LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, un octet à l'offset 0.
        return bool(kernel32.LockFileEx(poignee, 0x2 | 0x1, 0, 1, 0, ctypes.byref(recouvrement)))
    import fcntl

    try:
        fcntl.flock(flux.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _deverrouiller(flux: BinaryIO) -> None:
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        class _OVERLAPPED(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                        ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                          ctypes.POINTER(_OVERLAPPED)]
        kernel32.UnlockFileEx.restype = wintypes.BOOL
        kernel32.UnlockFileEx(msvcrt.get_osfhandle(flux.fileno()), 0, 1, 0, ctypes.byref(_OVERLAPPED()))
        return
    import fcntl

    fcntl.flock(flux.fileno(), fcntl.LOCK_UN)


class Verrou:
    """Verrou exclusif sur ``chemin`` ; ``prendre`` lève :class:`VerrouOccupe` s'il est tenu ailleurs."""

    def __init__(self, chemin: Path) -> None:
        self.chemin = Path(chemin)
        self._flux: BinaryIO | None = None

    @property
    def tenu(self) -> bool:
        return self._flux is not None

    def prendre(self, *, attendre_s: float = 0.0) -> "Verrou":
        if self._flux is not None:
            return self
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        flux = self.chemin.open("a+b")
        try:
            flux.seek(0, os.SEEK_END)
            if flux.tell() == 0:
                flux.write(b"\0")
                flux.flush()
            flux.seek(0)
            echeance = time.monotonic() + max(0.0, attendre_s)
            while not _verrouiller(flux):
                if time.monotonic() >= echeance:
                    raise VerrouOccupe(str(self.chemin.name))
                time.sleep(0.05)
        except BaseException:
            flux.close()
            raise
        self._flux = flux
        return self

    def rendre(self) -> None:
        flux, self._flux = self._flux, None
        if flux is None:
            return
        try:
            _deverrouiller(flux)
        finally:
            flux.close()

    def __enter__(self) -> "Verrou":
        return self.prendre()

    def __exit__(self, *_exc) -> None:
        self.rendre()


def est_tenu(chemin: Path) -> bool:
    """Le verrou est-il tenu par quelqu'un d'autre ? (lecture pour le diagnostic : pris puis rendu aussitôt)."""
    if not Path(chemin).exists():
        return False
    essai = Verrou(chemin)
    try:
        essai.prendre()
    except VerrouOccupe:
        return True
    essai.rendre()
    return False
