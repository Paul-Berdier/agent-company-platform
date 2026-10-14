"""Accès confinés au coffre de notes ; aucune ouverture de lien ou de fichier partagé.

Windows : dossiers épinglés sans partage DELETE, fichiers sans partage WRITE/DELETE.
Le contrôle de version conserve son handle ; la nouvelle note est préparée séparément
puis publiée sans écraser un fichier apparu entre-temps. Elles ne prétendent pas être atomiques en cas de panne du système.
POSIX : parcours par dir_fd/O_NOFOLLOW ; les verrous de fichiers restent consultatifs.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import stat


class RefusFichier(RuntimeError):
    pass


def _regulier(st):
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or getattr(st, "st_file_attributes", 0) & 0x400:
        raise RefusFichier("Un fichier ordinaire sans lien est requis.")


def _win_ouvrir(path, *, dossier=False, ecriture=False, creer=False, deplacer=False):
    import ctypes
    import msvcrt
    from ctypes import wintypes as w
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    k.CreateFileW.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    class INFO(ctypes.Structure):
        _fields_ = [("attributes", w.DWORD), ("creation", w.FILETIME), ("access", w.FILETIME),
                    ("write", w.FILETIME), ("volume", w.DWORD), ("high", w.DWORD),
                    ("low", w.DWORD), ("links", w.DWORD), ("index_high", w.DWORD), ("index_low", w.DWORD)]
    k.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.POINTER(INFO)]
    k.GetFileInformationByHandle.restype = w.BOOL
    rights = 0x80000000 if dossier else 0x80000000 | (0x40000000 if ecriture else 0) | (0x10000 if deplacer else 0)
    share = 3 if dossier else 1  # Pas de remplacement du dossier ; pas d'écriture concurrente du fichier.
    h = k.CreateFileW(str(path), rights, share, None, 1 if creer else 3,
                     0x00200000 | (0x02000000 if dossier else 0), None)
    if h in (None, w.HANDLE(-1).value):
        code = ctypes.get_last_error()
        if code in (2, 3):
            raise FileNotFoundError()
        if code in (80, 183):
            raise FileExistsError()
        raise RefusFichier("Fichier occupé ou accès refusé.")
    info = INFO()
    if not k.GetFileInformationByHandle(h, ctypes.byref(info)) or info.attributes & 0x400 or bool(info.attributes & 0x10) != dossier or (not dossier and info.links != 1):
        k.CloseHandle(h)
        raise RefusFichier("Lien, jonction ou type de fichier refusé.")
    if dossier:
        return h
    try:
        return msvcrt.open_osfhandle(h, os.O_BINARY | (os.O_RDWR if ecriture else os.O_RDONLY))
    except BaseException:
        k.CloseHandle(h)
        raise


@contextlib.contextmanager
def dossier_epingle(path: Path):
    """Tient tous les ancêtres ; rend le fd du dossier sous POSIX, None sous Windows."""
    if not path.is_absolute():
        raise RefusFichier("Le coffre exige un chemin local absolu.")
    handles = []
    try:
        if os.name == "nt":
            if str(path).startswith("\\"):
                raise RefusFichier("Les chemins réseau sont refusés.")
            current = Path(path.anchor)
            handles.append(_win_ouvrir(current, dossier=True))
            for component in path.parts[1:]:
                if component in (".", ".."):
                    raise RefusFichier("Chemin ambigu refusé.")
                current /= component
                handles.append(_win_ouvrir(current, dossier=True))
            yield None
        else:
            fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.append(fd)
            for component in path.parts[1:]:
                if component in (".", ".."):
                    raise RefusFichier("Chemin ambigu refusé.")
                fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                handles.append(fd)
            yield fd
    finally:
        for h in reversed(handles):
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                k = ctypes.WinDLL("kernel32", use_last_error=True)
                k.CloseHandle.argtypes = [wintypes.HANDLE]
                k.CloseHandle(h)
            else:
                os.close(h)


@contextlib.contextmanager
def fichier_epingle(path: Path, *, ecriture=False, creer=False, deplacer=False):
    with dossier_epingle(path.parent) as parent:
        if os.name == "nt":
            fd = _win_ouvrir(path, ecriture=ecriture, creer=creer, deplacer=deplacer)
        else:
            flags = (os.O_RDWR if ecriture else os.O_RDONLY) | os.O_NOFOLLOW
            if creer:
                flags |= os.O_CREAT | os.O_EXCL
            fd = os.open(path.name, flags, 0o600, dir_fd=parent)
        try:
            _regulier(os.fstat(fd))
            if os.name != "nt":
                import fcntl
                fcntl.flock(fd, (fcntl.LOCK_EX if ecriture or deplacer else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            with os.fdopen(fd, "r+b" if ecriture else "rb", closefd=False) as stream:
                yield stream, parent
        finally:
            os.close(fd)


def renommer_handle(stream, source: Path, destination: Path, parent_source):
    """Déplace le handle exact sans remplacer une destination existante."""
    with dossier_epingle(destination.parent) as parent_dest:
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes as w
            name = str(destination)
            class RENAME(ctypes.Structure):
                _fields_ = [("replace", w.BOOL), ("root", w.HANDLE), ("length", w.DWORD),
                            ("name", w.WCHAR * (len(name.encode("utf-16-le")) // 2 + 1))]
            data = RENAME(False, None, len(name.encode("utf-16-le")), name)
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.SetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
            k.SetFileInformationByHandle.restype = w.BOOL
            if not k.SetFileInformationByHandle(msvcrt.get_osfhandle(stream.fileno()), 3, ctypes.byref(data), ctypes.sizeof(data)):
                if ctypes.get_last_error() in (80, 183):
                    raise FileExistsError()
                raise RefusFichier("Déplacement refusé ; le fichier reste conservé.")
        else:
            # link/unlink refuse l'écrasement ; la source reste ouverte et contrôlée.
            original = os.fstat(stream.fileno())
            actuel = os.stat(source.name, dir_fd=parent_source, follow_symlinks=False)
            if (original.st_dev, original.st_ino) != (actuel.st_dev, actuel.st_ino):
                raise RefusFichier("La note a changé pendant le déplacement.")
            os.link(source.name, destination.name, src_dir_fd=parent_source, dst_dir_fd=parent_dest, follow_symlinks=False)
            os.unlink(source.name, dir_fd=parent_source)
