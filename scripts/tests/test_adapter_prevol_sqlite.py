"""Course WAL/SHM déterministe et témoins négatifs du correctif amont borné."""
from __future__ import annotations

import contextlib
import importlib.util
import logging
import os
from pathlib import Path
import sqlite3
import stat
from typing import Optional

import pytest

RACINE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('adapter_amont', RACINE / 'hermes/image/adapter_amont.py')
assert SPEC is not None and SPEC.loader is not None
ADAPTATEUR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTATEUR)
ORIGINAL = (Path(__file__).parent / 'fixtures/preflight_db_writability.py.txt').read_text(encoding='utf-8')


def prevol(texte, home):
    espace = {'Path': Path, 'Optional': Optional, 'contextlib': contextlib, 'os': os,
              'stat': stat, 'sqlite3': sqlite3, 'logger': logging.getLogger(__name__),
              'get_hermes_home': lambda: home}
    exec(compile(texte, '<prevol-amont>', 'exec'), espace)
    return espace['preflight_db_writability']


@pytest.mark.parametrize('suffixe', ['-wal', '-shm'])
@pytest.mark.parametrize('corrige', [False, True])
def test_disparition_apres_is_file(tmp_path, monkeypatch, suffixe, corrige):
    db = tmp_path / 'kanban.db'
    db.touch()
    sidecar = db.with_name(db.name + suffixe)
    sidecar.touch()
    access = os.access
    def disparition(chemin, mode):
        if Path(chemin) == sidecar:
            sidecar.unlink(missing_ok=True)
        return access(chemin, mode)
    monkeypatch.setattr(os, 'access', disparition)
    fonction = prevol(ADAPTATEUR.adapter_prevol_sqlite(ORIGINAL) if corrige else ORIGINAL, tmp_path)
    if corrige:
        fonction(db)
    else:
        with pytest.raises(sqlite3.OperationalError, match='is read-only'):
            fonction(db)
    assert not sidecar.exists()


@pytest.mark.parametrize('suffixe', ['', '-wal', '-shm'])
def test_vrai_refus_de_permission_conserve(tmp_path, monkeypatch, suffixe):
    db = tmp_path / 'kanban.db'
    db.touch()
    cible = db.with_name(db.name + suffixe)
    cible.touch()
    avant = cible.stat().st_mode
    access = os.access
    chmod = os.chmod
    def refuse_access(chemin, mode):
        return False if Path(chemin) == cible else access(chemin, mode)
    def refuse_chmod(chemin, mode):
        if Path(chemin) == cible:
            raise PermissionError('témoin : autre propriétaire')
        return chmod(chemin, mode)
    monkeypatch.setattr(os, 'access', refuse_access)
    monkeypatch.setattr(os, 'chmod', refuse_chmod)
    with pytest.raises(sqlite3.OperationalError, match='is read-only'):
        prevol(ADAPTATEUR.adapter_prevol_sqlite(ORIGINAL), tmp_path)(db)
    assert cible.exists() and cible.stat().st_mode == avant


def test_disparition_base_principale_reste_refusee(tmp_path, monkeypatch):
    db = tmp_path / 'kanban.db'
    db.touch()
    access = os.access
    def disparition(chemin, mode):
        if Path(chemin) == db:
            db.unlink(missing_ok=True)
        return access(chemin, mode)
    monkeypatch.setattr(os, 'access', disparition)
    with pytest.raises(sqlite3.OperationalError):
        prevol(ADAPTATEUR.adapter_prevol_sqlite(ORIGINAL), tmp_path)(db)


def test_reste_du_module_inchange_et_seconde_application_refusee():
    source = 'AVANT = 1\n\n' + ORIGINAL + '\nAPRES = 2\n'
    resultat = ADAPTATEUR.adapter_prevol_sqlite(source)
    assert resultat.replace(ADAPTATEUR.CORRECTION_PREVOL, '', 1) == source
    with pytest.raises(ValueError, match='amont modifiée'):
        ADAPTATEUR.adapter_prevol_sqlite(resultat)


@pytest.mark.parametrize('source', [ORIGINAL.replace('if in_scope and', 'if True and'), '', ORIGINAL + ORIGINAL])
def test_source_non_reconnue_refusee(source):
    with pytest.raises(ValueError):
        ADAPTATEUR.adapter_prevol_sqlite(source)
