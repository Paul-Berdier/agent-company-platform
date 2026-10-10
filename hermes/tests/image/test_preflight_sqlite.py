"""Régressions du prévol SQLite, sur la vraie fonction de l'image construite.

Uniquement des fichiers jetables. Aucune base ni aucun volume de production.
"""
from pathlib import Path
import os
import sqlite3

import pytest
import hermes_state_repair as repair


@pytest.mark.parametrize('suffixe', ['-wal', '-shm'])
def test_sidecar_disparu_entre_detection_et_controle(tmp_path, monkeypatch, suffixe):
    monkeypatch.setattr(repair, 'get_hermes_home', lambda: tmp_path)
    db = tmp_path / 'kanban.db'
    db.touch()
    cible = db.with_name(db.name + suffixe)
    cible.touch()
    access = os.access
    observes = []
    def disparition(chemin, mode):
        if Path(chemin) == cible:
            observes.append(cible.exists())
            cible.unlink(missing_ok=True)
        return access(chemin, mode)
    monkeypatch.setattr(os, 'access', disparition)
    repair.preflight_db_writability(db)
    assert observes and observes[0] is True
    assert not cible.exists()


@pytest.mark.parametrize('suffixe', ['', '-wal', '-shm'])
def test_permission_reellement_refusee_pas_masquee(tmp_path, monkeypatch, suffixe):
    monkeypatch.setattr(repair, 'get_hermes_home', lambda: tmp_path)
    db = tmp_path / 'kanban.db'
    db.touch()
    cible = db.with_name(db.name + suffixe)
    cible.touch()
    access, chmod = os.access, os.chmod
    def refuse_access(chemin, mode):
        return False if Path(chemin) == cible else access(chemin, mode)
    def refuse_chmod(chemin, mode):
        if Path(chemin) == cible:
            raise PermissionError('témoin de propriétaire distinct')
        return chmod(chemin, mode)
    monkeypatch.setattr(os, 'access', refuse_access)
    monkeypatch.setattr(os, 'chmod', refuse_chmod)
    with pytest.raises(sqlite3.OperationalError, match='is read-only'):
        repair.preflight_db_writability(db)
    assert cible.is_file()


def test_erreur_lstat_autre_qu_absence_reste_refusee(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, 'get_hermes_home', lambda: tmp_path)
    db = tmp_path / 'kanban.db'
    db.touch()
    cible = db.with_name(db.name + '-shm')
    cible.touch()
    access, chmod, lstat = os.access, os.chmod, Path.lstat
    def refuse_access(chemin, mode):
        return False if Path(chemin) == cible else access(chemin, mode)
    def refuse_chmod(chemin, mode):
        if Path(chemin) == cible:
            raise PermissionError('témoin chmod')
        return chmod(chemin, mode)
    def refuse_lstat(chemin, *args, **kwargs):
        if chemin == cible:
            raise PermissionError('témoin lstat : ne pas ignorer EACCES')
        return lstat(chemin, *args, **kwargs)
    monkeypatch.setattr(os, 'access', refuse_access)
    monkeypatch.setattr(os, 'chmod', refuse_chmod)
    monkeypatch.setattr(Path, 'lstat', refuse_lstat)
    with pytest.raises(PermissionError, match='témoin lstat'):
        repair.preflight_db_writability(db)


def test_base_principale_disparue_pas_ignoree(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, 'get_hermes_home', lambda: tmp_path)
    db = tmp_path / 'kanban.db'
    db.touch()
    access = os.access
    def disparition(chemin, mode):
        if Path(chemin) == db:
            db.unlink(missing_ok=True)
        return access(chemin, mode)
    monkeypatch.setattr(os, 'access', disparition)
    with pytest.raises(sqlite3.OperationalError):
        repair.preflight_db_writability(db)
