"""Parité des motifs de secrets (étape P5 : la liste vit dans le contrat partagé) : le greffon acp-poste refuse,
dans un objectif, une consigne, une réponse ou un inventaire du poste, exactement ce que le balayage du dépôt
(scripts/balayer_secrets.py) cherche ; le noyau du greffon réexporte la MÊME liste, jamais une copie."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from acp_poste_contrat import motifs_secrets

RACINE = Path(__file__).resolve().parents[5]


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memes_motifs_que_le_balayage_du_depot():
    balayage = _charger("acp_balayer_secrets_parite", RACINE / "scripts/balayer_secrets.py")
    contrat = motifs_secrets.MOTIFS
    assert {nom: m.pattern for nom, m in contrat.items()} == {nom: m.pattern for nom, m in balayage.MOTIFS.items()}
    assert {nom: m.flags for nom, m in contrat.items()} == {nom: m.flags for nom, m in balayage.MOTIFS.items()}


def test_le_noyau_reexporte_le_contrat_sans_copie():
    """Le module du noyau n'a plus de liste propre : il importe celle du contrat (une seule copie)."""
    texte = (RACINE / "hermes/plugins/acp-poste/noyau/motifs_secrets.py").read_text(encoding="utf-8")
    assert "from acp_poste_contrat.motifs_secrets import MOTIFS, motif_trouve" in texte
    assert "re.compile" not in texte


def test_motif_trouve():
    trouve = motifs_secrets.motif_trouve
    # Faux secrets assemblés à l'exécution : le balayage du dépôt ne doit rien trouver dans ce fichier.
    assert trouve("clé " + "sk-" + "ant-" + "a" * 24) == "clé d'API Anthropic"
    assert trouve("x\n  " + "-----BEGIN " + "PRIVATE KEY-----" + "\ny") == "clé privée PEM"
    assert trouve("Authorization: Bearer " + "ac" + "pm_" + "A1b2" * 10 + "c3d") == "jeton machine ACP"
    assert trouve("code " + "ac" + "pe_" + "Z9-_" * 10 + "k2x") == "code d'enrôlement ACP"
    assert trouve("préfixe seul : acpm_ et acpe_, sans jeton") is None
    assert trouve("Écrire un module Python propre.") is None
    assert trouve(None) is None and trouve("") is None
