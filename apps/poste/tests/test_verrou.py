"""Verrous par fichier du poste (cahier P5 § 6.1 et § 6.2) : ``LockFileEx`` sous Windows, ``flock`` ailleurs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from acp_poste.verrou import Verrou, VerrouOccupe, est_tenu

PYTHON = str(Path(sys.executable).resolve())


def test_second_verrou_refuse_dans_le_meme_processus(tmp_path: Path):
    chemin = tmp_path / "etat" / "poste.verrou"
    premier = Verrou(chemin).prendre()
    assert premier.tenu and est_tenu(chemin)
    with pytest.raises(VerrouOccupe):
        Verrou(chemin).prendre()
    premier.rendre()
    assert not est_tenu(chemin)
    with Verrou(chemin) as second:
        assert second.tenu


def test_verrou_tenu_par_un_autre_processus_puis_libere_a_sa_mort(tmp_path: Path):
    """Un autre processus tient le verrou : refus ; à sa mort, le système le libère (aucun fichier à nettoyer)."""
    chemin = tmp_path / "poste.verrou"
    script = ("import sys, time\nsys.path[:0] = sys.argv[2:]\nfrom acp_poste.verrou import Verrou\n"
              "v = Verrou(__import__('pathlib').Path(sys.argv[1])).prendre()\nprint('tenu', flush=True)\n"
              "time.sleep(60)\n")
    import acp_poste

    source = str(Path(acp_poste.__file__).resolve().parents[1])
    import acp_poste_contrat

    contrat = str(Path(acp_poste_contrat.__file__).resolve().parents[1])
    enfant = subprocess.Popen([PYTHON, "-c", script, str(chemin), source, contrat], stdout=subprocess.PIPE, text=True)
    try:
        assert enfant.stdout.readline().strip() == "tenu"
        with pytest.raises(VerrouOccupe):
            Verrou(chemin).prendre()
        assert est_tenu(chemin)
    finally:
        enfant.kill()
        enfant.wait(10)
    Verrou(chemin).prendre(attendre_s=5).rendre()


def test_attente_bornee(tmp_path: Path):
    chemin = tmp_path / "sondes.verrou"
    with Verrou(chemin):
        import time

        debut = time.monotonic()
        with pytest.raises(VerrouOccupe):
            Verrou(chemin).prendre(attendre_s=0.3)
        assert 0.25 <= time.monotonic() - debut < 3
