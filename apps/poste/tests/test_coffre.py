"""Coffre DPAPI du poste (cahier P5 § 5.4) : un fichier ``ACPD1`` + blob par usage, écriture atomique, refus
français d'un blob illisible. Vrai DPAPI sous Windows ; refus explicite ailleurs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from acp_poste import coffre as module
from acp_poste.coffre import COFFRE_ILLISIBLE, ENTETE, CoffreDPAPI, CoffreErreur, ecrire_atomiquement

WINDOWS_SEULEMENT = pytest.mark.skipif(os.name != "nt", reason="DPAPI réel propre à Windows")
JETON = "acpm_" + "A" * 43
JETON_CLAUDE = "sk-ant-oat01-" + "b" * 40


@WINDOWS_SEULEMENT
def test_aller_retour_dpapi(tmp_path: Path):
    coffre = CoffreDPAPI(tmp_path / "secrets")
    assert coffre.lire("jeton-machine") is None and not coffre.present("jeton-machine")
    coffre.ecrire("jeton-machine", JETON)
    brut = (tmp_path / "secrets" / "jeton-machine.dpapi").read_bytes()
    assert brut.startswith(ENTETE) and JETON.encode() not in brut
    assert coffre.present("jeton-machine") and coffre.lire("jeton-machine") == JETON
    assert coffre.effacer("jeton-machine") is True and coffre.effacer("jeton-machine") is False


@WINDOWS_SEULEMENT
def test_entropie_par_usage(tmp_path: Path):
    """Un blob du jeton machine recopié à la place du jeton Claude ne se relit pas (autre entropie)."""
    coffre = CoffreDPAPI(tmp_path / "secrets")
    coffre.ecrire("jeton-machine", JETON)
    coffre.ecrire("jeton-claude", JETON_CLAUDE)
    dossier = tmp_path / "secrets"
    (dossier / "claude-oauth.dpapi").write_bytes((dossier / "jeton-machine.dpapi").read_bytes())
    with pytest.raises(CoffreErreur) as exc:
        coffre.lire("jeton-claude")
    assert str(exc.value) == COFFRE_ILLISIBLE
    assert coffre.lire("jeton-machine") == JETON


@WINDOWS_SEULEMENT
@pytest.mark.parametrize("alteration", ["blob", "entete"])
def test_blob_corrompu_refus_francais(tmp_path: Path, alteration: str):
    coffre = CoffreDPAPI(tmp_path / "secrets")
    coffre.ecrire("jeton-machine", JETON)
    fichier = tmp_path / "secrets" / "jeton-machine.dpapi"
    contenu = bytearray(fichier.read_bytes())
    if alteration == "blob":
        contenu[len(contenu) // 2] ^= 0xFF
        attendu = COFFRE_ILLISIBLE
    else:
        contenu[:5] = b"XXXXX"
        attendu = "au format inconnu"
    fichier.write_bytes(bytes(contenu))
    with pytest.raises(CoffreErreur, match=attendu) as exc:
        coffre.lire("jeton-machine")
    assert JETON not in str(exc.value)


def test_ecriture_atomique(tmp_path: Path, monkeypatch):
    """Écriture par fichier temporaire du même dossier puis ``os.replace`` : une panne laisse l'ancien contenu et
    aucun fichier temporaire."""
    cible = tmp_path / "d" / "f.bin"
    ecrire_atomiquement(cible, b"ancien")

    def panne(*_a):
        raise OSError("disque plein")

    monkeypatch.setattr(module.os, "replace", panne)
    with pytest.raises(OSError):
        ecrire_atomiquement(cible, b"nouveau")
    assert cible.read_bytes() == b"ancien"
    assert sorted(p.name for p in cible.parent.iterdir()) == ["f.bin"]


def test_coffre_avec_protection_injectee(tmp_path: Path):
    """Le format du fichier (en-tête, blob) et l'usage transmis à la primitive, sans DPAPI (toutes plateformes)."""
    vus = []

    def proteger(donnees, *, usage):
        vus.append(usage)
        return donnees[::-1]

    def deproteger(donnees, *, usage):
        vus.append(usage)
        return donnees[::-1]

    coffre = CoffreDPAPI(tmp_path, proteger=proteger, deproteger=deproteger)
    coffre.ecrire("jeton-claude", JETON_CLAUDE)
    assert (tmp_path / "claude-oauth.dpapi").read_bytes() == ENTETE + JETON_CLAUDE.encode()[::-1]
    assert coffre.lire("jeton-claude") == JETON_CLAUDE
    assert vus == [module.USAGES["jeton-claude"][1]] * 2
    with pytest.raises(CoffreErreur, match="Usage du coffre inconnu"):
        coffre.lire("autre")
    with pytest.raises(CoffreErreur, match="Secret vide"):
        coffre.ecrire("jeton-machine", "")


@pytest.mark.skipif(os.name == "nt", reason="refus hors Windows")
def test_hors_windows_refuse(tmp_path: Path):
    coffre = CoffreDPAPI(tmp_path)
    with pytest.raises(CoffreErreur, match="exige DPAPI Windows"):
        coffre.ecrire("jeton-machine", JETON)
    assert list(tmp_path.iterdir()) == []
