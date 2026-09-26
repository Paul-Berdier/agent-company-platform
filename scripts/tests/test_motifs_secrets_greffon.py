"""Parité des motifs de secrets : le greffon acp-poste refuse, dans un objectif, une consigne ou une réponse,
exactement ce que le balayage du dépôt (scripts/balayer_secrets.py) cherche (étape P4)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memes_motifs_que_le_balayage_du_depot():
    greffon = _charger("acp_motifs_secrets_greffon", RACINE / "hermes/plugins/acp-poste/noyau/motifs_secrets.py")
    balayage = _charger("acp_balayer_secrets_parite", RACINE / "scripts/balayer_secrets.py")
    assert {nom: m.pattern for nom, m in greffon.MOTIFS.items()} == {nom: m.pattern for nom, m in balayage.MOTIFS.items()}
    assert {nom: m.flags for nom, m in greffon.MOTIFS.items()} == {nom: m.flags for nom, m in balayage.MOTIFS.items()}


def test_motif_trouve():
    greffon = _charger("acp_motifs_secrets_greffon_2", RACINE / "hermes/plugins/acp-poste/noyau/motifs_secrets.py")
    # Faux secrets assemblés à l'exécution : le balayage du dépôt ne doit rien trouver dans ce fichier.
    assert greffon.motif_trouve("clé " + "sk-" + "ant-" + "a" * 24) == "clé d'API Anthropic"
    assert greffon.motif_trouve("x\n  " + "-----BEGIN " + "PRIVATE KEY-----" + "\ny") == "clé privée PEM"
    assert greffon.motif_trouve("Écrire un module Python propre.") is None
    assert greffon.motif_trouve(None) is None and greffon.motif_trouve("") is None
