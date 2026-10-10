"""Thème « acp » livré dans l'image (étape P3) : Hermes 0.21.5 le lit sans rien perdre.

Le fichier /opt/acp/theme/acp.yaml est généré depuis design/tokens par scripts/generer_themes.py
(vérifié à jour en CI) ; ici, c'est la normalisation RÉELLE de Hermes qui le lit
(_normalise_theme_definition, hermes_cli/web_server_dashboard.py:317-411) : une clé ignorée en
silence (nom inconnu, valeur non chaîne) ferait échouer ces tests.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

import yaml

THEME = Path("/opt/acp/theme/acp.yaml")


def _brut() -> Dict[str, Any]:
    donnees = yaml.safe_load(THEME.read_text(encoding="utf-8"))
    assert isinstance(donnees, dict)
    return donnees


def _feuilles(donnees: Any, prefixe: str = "") -> Iterator[Tuple[str, Any]]:
    if isinstance(donnees, dict):
        for cle, valeur in donnees.items():
            yield from _feuilles(valeur, f"{prefixe}.{cle}" if prefixe else cle)
    else:
        yield prefixe, donnees


def test_le_fichier_est_genere_root_0644_et_en_lf():
    st = os.lstat(THEME)
    assert stat.S_ISREG(st.st_mode) and st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o644
    octets = THEME.read_bytes()
    assert b"\r" not in octets and not octets.startswith(b"\xef\xbb\xbf")
    assert octets.startswith("# Fichier généré par scripts/generer_themes.py depuis design/tokens".encode("utf-8"))


def test_hermes_garde_toutes_les_cles_du_theme_acp():
    from hermes_cli.web_server_dashboard import _normalise_theme_definition

    brut = _brut()
    normalise = _normalise_theme_definition(brut)
    assert normalise is not None
    print({k: normalise[k] for k in ("name", "label", "layoutVariant")}, sorted(normalise))
    perdues = []
    for chemin, valeur in _feuilles(brut):
        racine = chemin.split(".")[0]
        if racine == "palette":
            cle = chemin.split(".")[1]
            if cle in ("background", "midground"):
                attendu = {"hex": valeur, "alpha": 1.0}
                obtenu = normalise["palette"][cle]
            elif cle == "foreground":
                attendu, obtenu = brut["palette"]["foreground"], normalise["palette"]["foreground"]
                attendu = {"hex": attendu["hex"], "alpha": float(attendu["alpha"])}
            elif cle == "noiseOpacity":
                attendu, obtenu = float(valeur), normalise["palette"]["noiseOpacity"]
            else:
                attendu, obtenu = valeur, normalise["palette"][cle]
        else:
            obtenu: Any = normalise
            for morceau in chemin.split("."):
                obtenu = obtenu.get(morceau) if isinstance(obtenu, dict) else None
            attendu = valeur
        if obtenu != attendu:
            perdues.append((chemin, attendu, obtenu))
    assert perdues == [], perdues
    # Rien d'autre que ce que nous avons écrit, hors valeurs par défaut documentées.
    assert set(normalise["typography"]) - set(brut["typography"]) == set()
    assert normalise["layoutVariant"] == "standard"


def test_aucune_url_externe_et_css_sous_les_plafonds():
    from hermes_cli.web_server_dashboard import _THEME_CUSTOM_CSS_MAX, _normalise_theme_definition

    normalise = _normalise_theme_definition(_brut())
    assert "fontUrl" not in normalise["typography"]
    texte = repr(normalise)
    assert not re.search(r"(?i)https?:|@import|url\s*\(", texte), texte
    css = normalise["customCSS"]
    assert len(css.encode("utf-8")) <= 2048 < _THEME_CUSTOM_CSS_MAX
    assert ":focus-visible" in css and "prefers-reduced-motion: reduce" in css


def test_les_couleurs_d_override_sont_toutes_connues_de_hermes():
    from hermes_cli.web_server_dashboard import _THEME_COMPONENT_BUCKETS, _THEME_OVERRIDE_KEYS

    brut = _brut()
    assert set(brut["colorOverrides"]) <= _THEME_OVERRIDE_KEYS
    assert set(brut["componentStyles"]) <= _THEME_COMPONENT_BUCKETS
    for valeur in brut["colorOverrides"].values():
        assert re.fullmatch(r"#[0-9a-f]{6}", valeur), valeur
