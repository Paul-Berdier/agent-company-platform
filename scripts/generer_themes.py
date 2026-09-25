#!/usr/bin/env python3
"""Génère le thème « acp » du tableau de bord de Hermes depuis ``design/tokens/*.json``.

Une seule source pour les deux clients : les jetons de ``design/tokens`` produisent déjà les
singletons QML du client desktop (``apps/desktop/cmake/generate_design_tokens.py``) ; ce script
en tire le thème YAML que Hermes lit dans ``/opt/data/dashboard-themes`` (déposé par ``05-acp``
depuis ``/opt/acp/theme``). Les jetons sont chargés par le MÊME module que le générateur du
desktop (``load_tokens``, ``public_tokens``) : même validation, aucun second chargeur.

Format de sortie : celui que normalise ``_normalise_theme_definition`` de Hermes 0.21.5
(``hermes_cli/web_server_dashboard.py:317-411``) : ``palette``, ``typography``, ``layout``,
``layoutVariant``, ``colorOverrides``, ``componentStyles``, ``customCSS`` (32 Kio au plus).

Refus explicites (code 1, message en français, rien n'est écrit) :
- un jeton manquant ou hors contrat ;
- une URL externe (``fontUrl``, ``url(http…)``, ``@import``) : aucune police n'est téléchargée
  (``design/tokens/typography.json``) ;
- un ``customCSS`` au-delà de 32 Kio (plafond de Hermes) ou du budget d'ACP (2 Kio) ;
- un contraste texte/fond inférieur à 4,5:1 ou bordure interactive/fond inférieur à 3:1,
  recalculé ici (WCAG 2.1).

Usage :
    python scripts/generer_themes.py            # écrit hermes/theme/acp.yaml
    python scripts/generer_themes.py --check    # échoue si acp.yaml ou le QML du desktop est périmé

Bibliothèque standard seulement. Le YAML est écrit à la main (chaînes entre guillemets doubles
au format JSON, valides en YAML) : la sortie est déterministe, octet pour octet, sous Windows
comme sous Linux.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Tuple

RACINE = Path(__file__).resolve().parents[1]
JETONS = RACINE / "design" / "tokens"
SORTIE = RACINE / "hermes" / "theme" / "acp.yaml"
GENERATEUR_DESKTOP = RACINE / "apps" / "desktop" / "cmake" / "generate_design_tokens.py"
QML_GENERE = RACINE / "apps" / "desktop" / "qml" / "theme" / "generated"

THEME = "dark"  # $defaultTheme des jetons ; le thème clair est reporté (décision D18).
PLAFOND_CSS_HERMES = 32 * 1024  # _THEME_CUSTOM_CSS_MAX (web_server_dashboard.py)
BUDGET_CSS_ACP = 2 * 1024
CONTRASTE_TEXTE = 4.5
CONTRASTE_BORDURE = 3.0

# Fichiers de jetons lus (tous passent par le chargeur du desktop).
FICHIERS = ("colors", "semantic-status", "typography", "radius", "spacing", "motion")

_URL_EXTERNE = re.compile(r"(?i)(https?:|//[a-z0-9]|@import|url\s*\()")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class Refus(RuntimeError):
    """Refus explicite : rien n'est écrit."""


# ------------------------------------------------------------------------------ chargement


def charger_generateur_desktop() -> ModuleType:
    """Module du générateur QML du desktop, chargé par son chemin (il n'est pas un paquet)."""
    spec = importlib.util.spec_from_file_location("acp_generate_design_tokens", GENERATEUR_DESKTOP)
    if spec is None or spec.loader is None:
        raise Refus(f"générateur du desktop introuvable : {GENERATEUR_DESKTOP}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def charger_jetons(dossier: Path = JETONS) -> Dict[str, dict]:
    """Documents de jetons validés par le chargeur du desktop, indexés par nom de fichier."""
    desktop = charger_generateur_desktop()
    documents: Dict[str, dict] = {}
    for nom in FICHIERS:
        try:
            documents[nom] = desktop.load_tokens(dossier, nom)
        except desktop.GenerationError as erreur:
            raise Refus(str(erreur)) from erreur
    return documents


def empreinte_jetons(documents: Dict[str, dict]) -> str:
    """Empreinte des jetons LUS (JSON canonique), indépendante des fins de ligne de l'arbre de
    travail : un poste Windows (core.autocrlf) et la CI Linux obtiennent la même valeur."""
    canonique = json.dumps(documents, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()


class Jetons:
    """Accès typé aux jetons publics ; tout jeton absent est un refus."""

    def __init__(self, documents: Dict[str, dict]) -> None:
        self.documents = documents

    def _brut(self, fichier: str, nom: str) -> Any:
        tokens = self.documents[fichier]["tokens"]
        if nom not in tokens or nom.startswith("$"):
            raise Refus(f"jeton manquant : {fichier}.{nom}")
        return tokens[nom]

    def couleur(self, fichier: str, nom: str) -> str:
        valeur = self._brut(fichier, nom).get(THEME)
        if not isinstance(valeur, str) or not _HEX.match(valeur):
            raise Refus(f"{fichier}.{nom} : couleur hexadécimale opaque attendue pour le thème {THEME}, "
                        f"reçu {valeur!r}")
        return valeur.lower()

    def valeur(self, fichier: str, nom: str) -> Any:
        return self._brut(fichier, nom).get("$value")

    def nombre(self, fichier: str, nom: str) -> float:
        valeur = self.valeur(fichier, nom)
        if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
            raise Refus(f"{fichier}.{nom} : nombre attendu, reçu {valeur!r}")
        return valeur

    def pile(self, nom: str) -> List[str]:
        valeur = self.valeur("typography", nom)
        if not isinstance(valeur, list) or not valeur or not all(isinstance(v, str) and v for v in valeur):
            raise Refus(f"typography.{nom} : pile de polices attendue, reçu {valeur!r}")
        return valeur


# ------------------------------------------------------------------------------ contrastes


def _luminance(hexa: str) -> float:
    def canal(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(a: str, b: str) -> float:
    """Rapport de contraste WCAG 2.1 entre deux couleurs opaques."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ------------------------------------------------------------------------------ construction


def _pile_css(familles: List[str], generique: str) -> str:
    noms = [f'"{f}"' if re.search(r"[^A-Za-z0-9-]", f) else f for f in familles]
    return ", ".join([*noms, generique])


def _px(valeur: float) -> str:
    return f"{int(valeur)}px" if float(valeur).is_integer() else f"{valeur}px"


def construire(documents: Dict[str, dict]) -> Tuple[Dict[str, Any], List[Tuple[str, str, str, float, float]]]:
    """(thème, contrôles de contraste) : le thème suit la table de correspondance du cahier P3
    (docs/refonte/interface.md § 2) ; chaque contrôle est (libellé, avant-plan, fond, mesuré, seuil)."""
    j = Jetons(documents)
    c = lambda nom: j.couleur("colors", nom)  # noqa: E731
    s = lambda nom: j.couleur("semantic-status", nom)  # noqa: E731

    taille = j.nombre("typography", "size.body")
    interligne = j.nombre("typography", "lineHeight.body")
    espacement = j.nombre("typography", "letterSpacing.normal")
    focus = c("border.focus")
    anneau = j.nombre("spacing", "layout.focusRingWidth")
    decalage = j.nombre("spacing", "layout.focusRingOffset")
    if j.nombre("motion", "duration.instant") != 0:
        raise Refus("motion.duration.instant doit valoir 0 : le profil réduit s'appuie dessus.")

    custom_css = "\n".join([
        "/* Généré depuis design/tokens (spacing.layout.focusRing*, colors.border.focus, motion). */",
        ":focus-visible {",
        f"  outline: {_px(anneau)} solid {focus};",
        f"  outline-offset: {_px(decalage)};",
        "}",
        "/* Profil « mouvement réduit » de motion.json : aucun déplacement, aucune boucle. */",
        "@media (prefers-reduced-motion: reduce) {",
        "  *, *::before, *::after {",
        "    animation-duration: 0.01ms !important;",
        "    animation-iteration-count: 1 !important;",
        "    transition-duration: 0.01ms !important;",
        "    scroll-behavior: auto !important;",
        "  }",
        "}",
    ]) + "\n"

    theme: Dict[str, Any] = {
        "name": "acp",
        "label": "ACP",
        "description": "Identité ACP : graphite végétal, ivoire et sarcelle (thème sombre des jetons de design).",
        "palette": {
            "background": c("surface.canvas"),
            "midground": c("text.primary"),
            # Couche d'avant-plan invisible, comme le thème par défaut de Hermes.
            "foreground": {"hex": "#ffffff", "alpha": 0},
            # Aucun halo ni grain décoratif (règles d'elevation.json).
            "warmGlow": "rgba(0, 0, 0, 0)",
            "noiseOpacity": 0,
        },
        "typography": {
            "fontSans": _pile_css(j.pile("family.interface"), "sans-serif"),
            "fontMono": _pile_css(j.pile("family.mono"), "monospace"),
            "baseSize": _px(taille),
            "lineHeight": f"{interligne / taille:.2f}",
            "letterSpacing": "0" if espacement == 0 else _px(espacement),
        },
        "layout": {
            "radius": _px(j.nombre("radius", "radius.md")),
            # Cibles tactiles confortables : le tableau de bord sert aussi au téléphone.
            "density": "comfortable",
        },
        "layoutVariant": "standard",
        "colorOverrides": {
            "card": c("surface.panel"),
            "cardForeground": c("text.primary"),
            "popover": c("surface.overlay"),
            "popoverForeground": c("text.primary"),
            "primary": c("accent.primary"),
            "primaryForeground": c("text.onAccent"),
            "secondary": c("surface.panelRaised"),
            "secondaryForeground": c("text.primary"),
            "muted": c("surface.panelRaised"),
            "mutedForeground": c("text.muted"),
            "accent": c("accent.muted"),
            "accentForeground": c("text.primary"),
            "destructive": s("status.failed.foreground"),
            # Encre sombre sur le corail d'échec : le blanc par défaut de Hermes n'y atteint pas 4,5:1.
            "destructiveForeground": c("surface.canvas"),
            "success": s("status.succeeded.foreground"),
            "warning": s("status.degraded.foreground"),
            "border": c("border.default"),
            "input": c("border.interactive"),
            "ring": focus,
        },
        "componentStyles": {
            # La profondeur vient du trait, jamais de l'ombre (elevation.json).
            "card": {"boxShadow": "none"},
            "header": {"background": c("surface.sidebar")},
            "sidebar": {"background": c("surface.sidebar")},
        },
        "customCSS": custom_css,
    }

    o = theme["colorOverrides"]
    fond = theme["palette"]["background"]
    controles: List[Tuple[str, str, str, float, float]] = []

    def exiger(libelle: str, avant: str, arriere: str, seuil: float) -> None:
        controles.append((libelle, avant, arriere, round(contraste(avant, arriere), 2), seuil))

    exiger("texte principal sur le canevas", theme["palette"]["midground"], fond, CONTRASTE_TEXTE)
    exiger("texte sur une carte", o["cardForeground"], o["card"], CONTRASTE_TEXTE)
    exiger("texte sur une surface flottante", o["popoverForeground"], o["popover"], CONTRASTE_TEXTE)
    exiger("encre sur l'accent principal", o["primaryForeground"], o["primary"], CONTRASTE_TEXTE)
    exiger("texte sur la surface secondaire", o["secondaryForeground"], o["secondary"], CONTRASTE_TEXTE)
    exiger("texte atténué sur la surface atténuée", o["mutedForeground"], o["muted"], CONTRASTE_TEXTE)
    exiger("texte atténué sur le canevas", o["mutedForeground"], fond, CONTRASTE_TEXTE)
    exiger("texte atténué sur une carte", o["mutedForeground"], o["card"], CONTRASTE_TEXTE)
    exiger("texte sur l'accent atténué", o["accentForeground"], o["accent"], CONTRASTE_TEXTE)
    exiger("encre sur l'échec", o["destructiveForeground"], o["destructive"], CONTRASTE_TEXTE)
    for cle in ("primary", "destructive", "success", "warning"):
        exiger(f"{cle} employé comme texte sur le canevas", o[cle], fond, CONTRASTE_TEXTE)
        exiger(f"{cle} employé comme texte sur une carte", o[cle], o["card"], CONTRASTE_TEXTE)
    exiger("bordure interactive sur le canevas", o["input"], fond, CONTRASTE_BORDURE)
    exiger("bordure interactive sur une carte", o["input"], o["card"], CONTRASTE_BORDURE)
    exiger("anneau de focus sur le canevas", o["ring"], fond, CONTRASTE_BORDURE)
    exiger("anneau de focus sur une carte", o["ring"], o["card"], CONTRASTE_BORDURE)
    return theme, controles


def valider(theme: Dict[str, Any], controles: List[Tuple[str, str, str, float, float]]) -> None:
    """Refuse une URL externe, un CSS trop lourd ou un contraste insuffisant."""
    erreurs: List[str] = []
    if "fontUrl" in theme.get("typography", {}):
        erreurs.append("typography.fontUrl est interdit : aucune police n'est téléchargée.")
    for chemin, valeur in _feuilles(theme):
        if isinstance(valeur, str) and _URL_EXTERNE.search(valeur):
            erreurs.append(f"{chemin} contient une URL ou un import externe : « {valeur[:80]} ».")
    css = theme.get("customCSS", "")
    taille = len(css.encode("utf-8"))
    if taille > PLAFOND_CSS_HERMES:
        erreurs.append(f"customCSS pèse {taille} octets, au-delà du plafond de Hermes ({PLAFOND_CSS_HERMES}).")
    if taille > BUDGET_CSS_ACP:
        erreurs.append(f"customCSS pèse {taille} octets, au-delà du budget d'ACP ({BUDGET_CSS_ACP}).")
    for libelle, avant, arriere, mesure, seuil in controles:
        if mesure < seuil:
            erreurs.append(f"contraste insuffisant pour « {libelle} » : {avant} sur {arriere} = {mesure}:1 "
                           f"(minimum {seuil}:1).")
    if erreurs:
        raise Refus("\n".join(erreurs))


def _feuilles(donnees: Any, prefixe: str = "") -> List[Tuple[str, Any]]:
    if isinstance(donnees, dict):
        resultat: List[Tuple[str, Any]] = []
        for cle, valeur in donnees.items():
            resultat.extend(_feuilles(valeur, f"{prefixe}.{cle}" if prefixe else cle))
        return resultat
    return [(prefixe, donnees)]


# ------------------------------------------------------------------------------ YAML


def _scalaire(valeur: Any) -> str:
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, (int, float)):
        return json.dumps(valeur)
    return json.dumps(str(valeur), ensure_ascii=False)


def _yaml(donnees: Dict[str, Any], retrait: int = 0) -> List[str]:
    lignes: List[str] = []
    marge = "  " * retrait
    for cle, valeur in donnees.items():
        if isinstance(valeur, dict):
            lignes.append(f"{marge}{cle}:")
            lignes.extend(_yaml(valeur, retrait + 1))
        elif isinstance(valeur, str) and "\n" in valeur:
            lignes.append(f"{marge}{cle}: |")
            lignes.extend(f"{marge}  {ligne}" if ligne else "" for ligne in valeur.rstrip("\n").split("\n"))
        else:
            lignes.append(f"{marge}{cle}: {_scalaire(valeur)}")
    return lignes


def rendre(theme: Dict[str, Any], documents: Dict[str, dict],
           controles: List[Tuple[str, str, str, float, float]]) -> str:
    versions = ", ".join(f"{nom} {documents[nom].get('$version', 'inconnue')}" for nom in FICHIERS)
    entete = [
        "# Fichier généré par scripts/generer_themes.py depuis design/tokens ; ne pas modifier à la main.",
        "# Toute correction se fait dans les jetons, puis : python scripts/generer_themes.py",
        f"# Jetons : {versions} (thème {THEME}).",
        f"# Empreinte des jetons lus (JSON canonique) : sha256:{empreinte_jetons(documents)}",
        "# Même source que le QML du desktop (apps/desktop/qml/theme/generated), vérifié par --check.",
        "# Format : _normalise_theme_definition de Hermes (hermes_cli/web_server_dashboard.py:317-411).",
        "# Contrastes recalculés (WCAG 2.1) :",
    ]
    for libelle, avant, arriere, mesure, seuil in controles:
        entete.append(f"#   {mesure:>5.2f}:1 (min {seuil}) {libelle} ({avant} sur {arriere})")
    return "\n".join(entete + _yaml(theme)) + "\n"


def generer(dossier: Path = JETONS) -> str:
    documents = charger_jetons(dossier)
    theme, controles = construire(documents)
    valider(theme, controles)
    return rendre(theme, documents, controles)


# ------------------------------------------------------------------------------ entrée


def verifier_qml(dossier_jetons: Path = JETONS, sortie_qml: Path = QML_GENERE) -> int:
    """Le QML du desktop est-il à jour ? Délègue au générateur du desktop, en mode --check."""
    desktop = charger_generateur_desktop()
    return desktop.main(["--tokens", str(dossier_jetons), "--out", str(sortie_qml), "--check"])


def main(argv: List[str]) -> int:
    parseur = argparse.ArgumentParser(description="Génère le thème acp du tableau de bord depuis design/tokens.")
    parseur.add_argument("--check", action="store_true",
                         help="ne rien écrire ; échouer si acp.yaml ou le QML du desktop est périmé")
    parseur.add_argument("--jetons", type=Path, default=JETONS, help=argparse.SUPPRESS)
    parseur.add_argument("--sortie", type=Path, default=SORTIE, help=argparse.SUPPRESS)
    parseur.add_argument("--qml", type=Path, default=QML_GENERE, help=argparse.SUPPRESS)
    arguments = parseur.parse_args(argv)
    try:
        texte = generer(arguments.jetons)
    except Refus as refus:
        for ligne in str(refus).splitlines():
            print(f"REFUS : {ligne}", file=sys.stderr)
        return 1
    if arguments.check:
        try:
            actuel = arguments.sortie.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            actuel = None
        code = 0
        if actuel != texte:
            print(f"REFUS : {arguments.sortie} ne correspond plus aux jetons de design.", file=sys.stderr)
            print("  Régénérez avec : python scripts/generer_themes.py", file=sys.stderr)
            code = 1
        else:
            print(f"Thème à jour : {arguments.sortie}.")
        if verifier_qml(arguments.jetons, arguments.qml) != 0:
            code = 1
        return code
    arguments.sortie.parent.mkdir(parents=True, exist_ok=True)
    arguments.sortie.write_text(texte, encoding="utf-8", newline="\n")
    print(f"Thème écrit : {arguments.sortie}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
