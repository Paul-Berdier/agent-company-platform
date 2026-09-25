"""Générateur du thème « acp » (scripts/generer_themes.py) : correspondance avec les jetons,
refus explicites et mode --check, sans PyYAML (bibliothèque standard seulement, comme le script).

La lecture du YAML par Hermes lui-même est vérifiée dans l'image (hermes/tests/image/test_theme.py)."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("generer_themes", RACINE / "scripts" / "generer_themes.py")
assert _SPEC is not None and _SPEC.loader is not None
gt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gt)


def _jetons(fichier: str) -> dict:
    return json.loads((RACINE / "design" / "tokens" / f"{fichier}.json").read_text(encoding="utf-8"))["tokens"]


@pytest.fixture
def jetons_copies(tmp_path: Path) -> Path:
    dossier = tmp_path / "tokens"
    shutil.copytree(RACINE / "design" / "tokens", dossier)
    return dossier


def _modifier(dossier: Path, fichier: str, modification) -> None:
    chemin = dossier / f"{fichier}.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    modification(donnees)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")


def test_la_correspondance_suit_les_jetons_du_theme_sombre():
    couleurs, statuts = _jetons("colors"), _jetons("semantic-status")
    theme, _ = gt.construire(gt.charger_jetons())
    sombre = lambda t: t["dark"]  # noqa: E731
    assert theme["name"] == "acp" and theme["label"] == "ACP"
    assert theme["palette"]["background"] == sombre(couleurs["surface.canvas"])
    assert theme["palette"]["midground"] == sombre(couleurs["text.primary"])
    assert theme["palette"]["foreground"] == {"hex": "#ffffff", "alpha": 0}
    assert theme["palette"]["warmGlow"] == "rgba(0, 0, 0, 0)" and theme["palette"]["noiseOpacity"] == 0
    o = theme["colorOverrides"]
    attendu = {
        "card": couleurs["surface.panel"], "cardForeground": couleurs["text.primary"],
        "popover": couleurs["surface.overlay"], "popoverForeground": couleurs["text.primary"],
        "primary": couleurs["accent.primary"], "primaryForeground": couleurs["text.onAccent"],
        "secondary": couleurs["surface.panelRaised"], "muted": couleurs["surface.panelRaised"],
        "mutedForeground": couleurs["text.muted"], "accent": couleurs["accent.muted"],
        "accentForeground": couleurs["text.primary"], "destructive": statuts["status.failed.foreground"],
        "success": statuts["status.succeeded.foreground"], "warning": statuts["status.degraded.foreground"],
        "border": couleurs["border.default"], "input": couleurs["border.interactive"],
        "ring": couleurs["border.focus"],
    }
    for cle, jeton in attendu.items():
        assert o[cle] == sombre(jeton), cle
    # Chaque clé de colorOverrides est connue de Hermes (_THEME_OVERRIDE_KEYS).
    assert set(o) <= {"card", "cardForeground", "popover", "popoverForeground", "primary", "primaryForeground",
                      "secondary", "secondaryForeground", "muted", "mutedForeground", "accent", "accentForeground",
                      "destructive", "destructiveForeground", "success", "warning", "border", "input", "ring"}
    typo = theme["typography"]
    assert typo["fontSans"].startswith("Inter, \"Inter Variable\"") and typo["fontSans"].endswith(", sans-serif")
    assert typo["fontMono"].startswith("\"Cascadia Code\"") and typo["fontMono"].endswith(", monospace")
    assert (typo["baseSize"], typo["lineHeight"], typo["letterSpacing"]) == ("14px", "1.43", "0")
    assert "fontUrl" not in typo
    assert theme["layout"] == {"radius": "8px", "density": "comfortable"}
    assert theme["layoutVariant"] == "standard"
    assert theme["componentStyles"]["card"] == {"boxShadow": "none"}
    assert theme["componentStyles"]["header"]["background"] == sombre(couleurs["surface.sidebar"])
    assert sombre(couleurs["border.focus"]) in theme["customCSS"]
    assert "prefers-reduced-motion: reduce" in theme["customCSS"]


def test_contrastes_calcules_et_tous_au_dessus_des_seuils():
    assert round(gt.contraste("#ffffff", "#000000"), 2) == 21.0
    assert round(gt.contraste("#777777", "#ffffff"), 2) == 4.48
    _, controles = gt.construire(gt.charger_jetons())
    assert len(controles) >= 20
    for libelle, _, _, mesure, seuil in controles:
        assert mesure >= seuil, libelle


def test_la_sortie_versionnee_est_a_jour_et_deterministe():
    texte = gt.generer()
    assert texte == gt.generer()
    assert (RACINE / "hermes" / "theme" / "acp.yaml").read_text(encoding="utf-8") == texte
    assert texte.startswith("# Fichier généré par scripts/generer_themes.py depuis design/tokens")
    assert "\r" not in texte and "\t" not in texte


def test_le_yaml_rendu_n_emploie_que_des_scalaires_json_et_un_bloc_css():
    texte = gt.generer()
    corps = [l for l in texte.splitlines() if l and not l.startswith("#")]
    dans_css = False
    for ligne in corps:
        if ligne == "customCSS: |":
            dans_css = True
            continue
        if dans_css:
            assert ligne.startswith("  "), ligne
            continue
        cle, _, valeur = ligne.strip().partition(":")
        assert cle and cle.replace("_", "").isalnum(), ligne
        valeur = valeur.strip()
        if valeur:
            json.loads(valeur)  # chaîne entre guillemets doubles ou nombre : du JSON, donc du YAML


def test_empreinte_independante_des_fins_de_ligne(jetons_copies):
    brut = (jetons_copies / "colors.json").read_bytes()
    (jetons_copies / "colors.json").write_bytes(brut.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert gt.generer(jetons_copies) == gt.generer()


def test_un_jeton_manquant_est_refuse(jetons_copies):
    _modifier(jetons_copies, "colors", lambda d: d["tokens"].pop("surface.canvas"))
    with pytest.raises(gt.Refus, match="jeton manquant : colors.surface.canvas"):
        gt.generer(jetons_copies)


def test_un_contraste_insuffisant_est_refuse(jetons_copies):
    _modifier(jetons_copies, "colors", lambda d: d["tokens"]["text.muted"].update(dark="#3a453c"))
    with pytest.raises(gt.Refus, match="contraste insuffisant pour « texte atténué"):
        gt.generer(jetons_copies)


def test_une_bordure_interactive_trop_faible_est_refusee(jetons_copies):
    _modifier(jetons_copies, "colors", lambda d: d["tokens"]["border.interactive"].update(dark="#2b332d"))
    with pytest.raises(gt.Refus, match="bordure interactive"):
        gt.generer(jetons_copies)


@pytest.mark.parametrize("pile", [
    ["https://fonts.example/inter.css"],
    ["Inter", "url(//fonts.example/x)"],
])
def test_une_url_externe_est_refusee(jetons_copies, pile):
    _modifier(jetons_copies, "typography", lambda d: d["tokens"]["family.interface"].update({"$value": pile}))
    with pytest.raises(gt.Refus, match="URL ou un import externe"):
        gt.generer(jetons_copies)


def test_font_url_et_css_trop_lourd_sont_refuses():
    theme, controles = gt.construire(gt.charger_jetons())
    theme["typography"]["fontUrl"] = "/polices.css"
    with pytest.raises(gt.Refus, match="fontUrl est interdit"):
        gt.valider(theme, controles)
    theme, controles = gt.construire(gt.charger_jetons())
    theme["customCSS"] = "a{}" * 700
    with pytest.raises(gt.Refus, match="budget d'ACP"):
        gt.valider(theme, controles)
    theme["customCSS"] = "a{}" * 11000
    with pytest.raises(gt.Refus, match="plafond de Hermes"):
        gt.valider(theme, controles)


def test_check_rouge_sur_une_sortie_retouchee(tmp_path, capsys):
    sortie = tmp_path / "acp.yaml"
    sortie.write_text(gt.generer().replace("#65c6ae", "#ff00ff"), encoding="utf-8")
    assert gt.main(["--check", "--sortie", str(sortie)]) == 1
    assert "ne correspond plus aux jetons" in capsys.readouterr().err
    sortie.write_text(gt.generer(), encoding="utf-8")
    assert gt.main(["--check", "--sortie", str(sortie)]) == 0


def test_check_rouge_sur_un_jeton_modifie(jetons_copies, capsys):
    _modifier(jetons_copies, "colors", lambda d: d["tokens"]["accent.primary"].update(dark="#66c6ae"))
    # La sortie versionnée ET le QML du desktop deviennent périmés : les deux sont signalés.
    assert gt.main(["--check", "--jetons", str(jetons_copies)]) == 1
    erreur = capsys.readouterr().err
    assert "ne correspond plus aux jetons de design" in erreur
    assert "Colors.qml : contenu périmé" in erreur


def test_check_rouge_sur_un_qml_perime(tmp_path, capsys):
    qml = tmp_path / "generated"
    shutil.copytree(RACINE / "apps" / "desktop" / "qml" / "theme" / "generated", qml)
    (qml / "Colors.qml").write_text("// retouché à la main\n", encoding="utf-8")
    assert gt.main(["--check", "--qml", str(qml)]) == 1
    assert "Colors.qml : contenu périmé" in capsys.readouterr().err


def test_ecriture_en_lf(tmp_path):
    sortie = tmp_path / "acp.yaml"
    assert gt.main(["--sortie", str(sortie)]) == 0
    assert b"\r" not in sortie.read_bytes()
    assert sortie.read_text(encoding="utf-8") == gt.generer()
