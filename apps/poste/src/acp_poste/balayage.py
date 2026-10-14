"""Balayage des secrets de la production d'une carte (cahier P6 § 6.6, point 3), en ÉCHEC FERMÉ.

Sur les lignes ajoutées du diff, le résumé, les notes et la question, AVANT tout envoi :

1. **valeurs exactes**, lues par le superviseur et gardées en mémoire seulement : jeton machine, jeton Claude,
   ``access_token``, ``refresh_token`` et ``id_token`` de ``/donnees/codex/auth.json``,
   ``accessToken`` et ``refreshToken`` du magasin officiel Claude, jeton GitHub de lecture ;
2. puis les motifs du contrat partagé (``acp_poste_contrat.motifs_secrets`` : ``sk-``, ``sk-ant-``, ``ghp_``,
   ``github_pat_``, ``AKIA``, PEM, JWT, ``acpm_``, ``acpe_``…), les mêmes que le greffon et ``balayer_secrets.py``.

Sur détection : aucun envoi du contenu, la branche passe en ``quarantaine/<carte>``, puis ``bloquer(secret)`` avec une
raison FIXE (le greffon l'écrit telle quelle). Le résultat ne porte jamais la valeur, seulement la nature du motif.
Un secret d'une autre forme passerait : barrière de plus, pas une garantie (limite dite).
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Iterable

from acp_poste_contrat.motifs_secrets import motif_trouve

VALEUR_MIN = 12
AUTH_MAX = 256 * 1024
RAISON_SECRET = ("Secret détecté dans la production de l'exécutant : rien n'a été envoyé ; la branche locale est "
                 "gardée pour examen.")


def jetons_de_auth_json(chemin: Path) -> dict[str, str]:
    """Valeurs des clés ``*_token`` et ``*api_key*`` d'``auth.json`` (lu en mémoire par root, jamais recopié)."""
    try:
        if chemin.is_symlink():
            return {}
        fd = os.open(chemin, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as flux:
            if not stat.S_ISREG(os.fstat(flux.fileno()).st_mode):
                return {}
            brut = flux.read(AUTH_MAX + 1)
    except OSError:
        return {}
    if len(brut) > AUTH_MAX:
        return {}
    try:
        document = json.loads(brut.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return {}
    trouves: dict[str, str] = {}
    pile: list[tuple[str, Any]] = [("", document)]
    while pile:
        cle, valeur = pile.pop()
        if isinstance(valeur, dict):
            pile.extend((str(k), v) for k, v in valeur.items())
        elif isinstance(valeur, list):
            pile.extend((cle, v) for v in valeur)
        elif isinstance(valeur, str) and len(valeur) >= VALEUR_MIN:
            nom = cle.lower()
            if nom.endswith("_token") or "api_key" in nom:
                trouves[f"codex:{nom}"] = valeur
    return trouves


def jetons_claude(chemin: Path) -> dict[str, str]:
    """Secrets du magasin officiel, lus en mémoire uniquement pour leur masquage.

    Cette lecture ne décide jamais si le compte est connecté : seul ``auth status``
    le fait. Les autres champs (identité, organisation, plan) sont ignorés.
    """
    try:
        if chemin.is_symlink():
            return {}
        fd = os.open(chemin, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as flux:
            if not stat.S_ISREG(os.fstat(flux.fileno()).st_mode):
                return {}
            brut = flux.read(AUTH_MAX + 1)
        if len(brut) > AUTH_MAX:
            return {}
        document = json.loads(brut.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return {}
    oauth = document.get("claudeAiOauth") if isinstance(document, dict) else None
    if not isinstance(oauth, dict):
        return {}
    return {f"claude:{nom}": oauth[nom] for nom in ("accessToken", "refreshToken")
            if isinstance(oauth.get(nom), str) and len(oauth[nom]) >= VALEUR_MIN}


def valeurs_exactes(coffre: Any, codex_home: Path | None, claude_config: Path | None = None) -> dict[str, str]:
    """Valeurs exactes à chercher : coffre de l'exécutant (jetons machine, Claude, GitHub) et magasins officiels de Codex et Claude."""
    valeurs: dict[str, str] = {}
    for usage in ("jeton-machine", "jeton-claude", "jeton-github"):
        try:
            valeur = coffre.lire(usage)
        except Exception:  # noqa: BLE001 — un coffre illisible n'empêche pas le balayage des motifs
            valeur = None
        if valeur and len(valeur) >= VALEUR_MIN:
            valeurs[usage] = valeur
    if codex_home is not None:
        valeurs.update(jetons_de_auth_json(Path(codex_home) / "auth.json"))
    if claude_config is not None:
        valeurs.update(jetons_claude(Path(claude_config) / ".credentials.json"))
    return valeurs


def secret_dans(textes: Iterable[str | None], valeurs: dict[str, str]) -> str | None:
    """Nature du premier secret trouvé (« valeur exacte : jeton-claude », « clé d'API Anthropic »…), ou ``None``."""
    textes = [t for t in textes if t]
    for usage, valeur in valeurs.items():
        if valeur and any(valeur in texte for texte in textes):
            return f"valeur exacte : {usage}"
    for texte in textes:
        nom = motif_trouve(texte)
        if nom:
            return nom
    return None
