"""Comportement de ``docker/entrypoint.sh`` face au répertoire de données.

L'image crée ``/data`` elle-même : sans volume, le répertoire existe et reste
inscriptible, et tout ce qui y est écrit disparaît au redéploiement pendant que la
base le référence encore. L'entrypoint exige donc un volume monté, sauf dérogation
explicite ``ACP_DATA_DIR_EPHEMERAL=1``.

Ces tests exécutent le vrai script avec ``sh`` (ignorés, avec leur raison, sur un poste
qui n'en a pas) sur un répertoire temporaire, qui n'est pas un volume.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT = ROOT / "docker" / "entrypoint.sh"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="sh absent : entrypoint non exécutable ici")


def _under_a_mount(path: Path) -> bool:
    current = os.path.realpath(path)
    while os.path.dirname(current) != current:
        if os.path.ismount(current):
            return True
        current = os.path.dirname(current)
    return False


def _run(data_dir: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ACP_ARTIFACT_STORAGE_DIR", "ACP_SKILLS_STORAGE_DIR", "ACP_DATA_DIR_EPHEMERAL"}
    }
    # Le script appelle « python » : celui de la suite, pas un alias du système.
    environment["PATH"] = os.path.dirname(sys.executable) + os.pathsep + environment.get("PATH", "")
    environment["ACP_DATA_DIR"] = data_dir.as_posix()
    environment.update(extra)
    return subprocess.run(
        [SH, ENTRYPOINT.as_posix(), "check-data"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def test_a_data_directory_outside_any_volume_is_refused(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    if _under_a_mount(data_dir):
        pytest.skip("le répertoire temporaire de ce poste est lui-même sur un montage")

    completed = _run(data_dir)

    assert completed.returncode == 3, completed.stdout + completed.stderr
    assert "aucun volume monté" in completed.stderr
    assert "ACP_DATA_DIR_EPHEMERAL=1" in completed.stderr


def test_the_explicit_ephemeral_waiver_is_accepted_and_announced(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    completed = _run(data_dir, ACP_DATA_DIR_EPHEMERAL="1")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "ne survivront pas au redéploiement" in completed.stderr
    assert "Répertoire de données conforme" in completed.stdout


def test_a_missing_data_directory_is_still_refused_first(tmp_path):
    completed = _run(tmp_path / "absent", ACP_DATA_DIR_EPHEMERAL="1")

    assert completed.returncode == 3
    assert "n'existe pas" in completed.stderr
