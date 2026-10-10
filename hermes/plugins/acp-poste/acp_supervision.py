"""Preuve locale du superviseur s6 sous un init externe (ACP 1.0.1).

Aucune variable ne vaut autorisation. L'attestation est écrite par le bootstrap root
APRÈS les gardes, dans /run (jamais sur le volume). Elle lie le PID à son instant de
création Linux, au démarrage du noyau et à la commande exacte de s6. Un serveur doit
en outre descendre de ce superviseur ; une session ``docker exec`` n'en descend pas.
Ce module, sans dépendance, est aussi copié dans hermes_cli et /opt/acp/bin.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

UID_ATTENDU = 0
ATTESTATION = Path('/run/acp-supervision/etat.json')
COMMANDE_S6 = ('/command/s6-svscan', '/run/service')


def lire_stat(pid: int, proc: Path = Path('/proc')) -> tuple[int, int, int]:
    """PPID, groupe et starttime ; le nom entre parenthèses peut contenir des espaces."""
    brut = (proc / str(pid) / 'stat').read_text()
    champs = brut[brut.rindex(')') + 2:].split()
    return int(champs[1]), int(champs[2]), int(champs[19])


def _chemin_root(chemin: Path, *, repertoire: bool) -> bool:
    """Refuse liens et écritures non-root, sur CHAQUE composant du chemin absolu."""
    if not chemin.is_absolute():
        return False
    for parent in (*reversed(chemin.parents), chemin):
        st = parent.lstat()
        attendu_dir = parent != chemin or repertoire
        if st.st_uid != UID_ATTENDU or st.st_mode & 0o022:
            return False
        if attendu_dir and not stat.S_ISDIR(st.st_mode):
            return False
        if not attendu_dir and not stat.S_ISREG(st.st_mode):
            return False
    return True


def superviseur_actif(*, attestation: Path = ATTESTATION, proc: Path = Path('/proc')) -> int | None:
    """Rend un PID root attesté et vivant ; tout écart rend None, jamais une exception."""
    try:
        if not _chemin_root(attestation, repertoire=False):
            return None
        fd = os.open(attestation, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as flux:
            st = os.fstat(flux.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != UID_ATTENDU or st.st_mode & 0o022:
                return None
            contenu = flux.read(4097)
        if len(contenu) > 4096:
            return None
        preuve = json.loads(contenu)
        if not isinstance(preuve, dict) or set(preuve) != {'version', 'pid', 'debut', 'boot_id'}:
            return None
        pid, debut = preuve['pid'], preuve['debut']
        if preuve['version'] != 1 or type(pid) is not int or pid <= 1 or type(debut) is not int:
            return None
        if (proc / str(pid)).stat().st_uid != UID_ATTENDU:
            return None
        if preuve['boot_id'] != (proc / 'sys/kernel/random/boot_id').read_text().strip():
            return None
        if lire_stat(pid, proc)[2] != debut:
            return None
        commande = tuple(p.decode('utf-8') for p in (proc / str(pid) / 'cmdline').read_bytes().split(b'\0') if p)
        if commande != COMMANDE_S6:
            return None
        return pid
    except (OSError, ValueError, TypeError, KeyError, IndexError, UnicodeError):
        return None


def dans_la_chaine(*, pid: int | None = None, attestation: Path = ATTESTATION,
                   proc: Path = Path('/proc')) -> bool:
    """Pas de simple marqueur d'environnement : vérifier l'ascendance Linux effective."""
    superviseur = superviseur_actif(attestation=attestation, proc=proc)
    if superviseur is None:
        return False
    courant = os.getpid() if pid is None else pid
    vus: set[int] = set()
    try:
        for _ in range(128):
            if courant == superviseur:
                # Le PID a pu mourir pendant la marche : revérifier son identité.
                return superviseur_actif(attestation=attestation, proc=proc) == superviseur
            if courant <= 1 or courant in vus:
                return False
            vus.add(courant)
            courant = lire_stat(courant, proc)[0]
    except (OSError, ValueError, IndexError):
        return False
    return False
