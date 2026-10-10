"""Journal local du poste, masqué avant écriture (cahier P5 § 6.4, décision D64).

``%LOCALAPPDATA%\\ACP\\journal\\poste.jsonl``, rotation (``[journal]`` de ``poste.toml`` : 5 fichiers de 1 Mio par
défaut). Une ligne : ``{"quand", "niveau", "evenement", "message", "details"}``. Rien n'est envoyé à Hermes.

Masquage, **avant** écriture, de chaque texte (message et détails) :

1. valeurs exactes enregistrées (jeton machine, jeton Claude, code d'enrôlement le temps de l'enrôlement) →
   ``«masqué:<nom>»`` ;
2. motifs de ``acp_poste_contrat.motifs_secrets`` (les mêmes que ``scripts/balayer_secrets.py``, jetons ``acpm_`` et
   codes ``acpe_`` compris) → ``«masqué:<motif>»`` ;
3. chemins sous un profil (``C:\\Users\\<nom>``) → ``<profil>`` ; adresses électroniques → ``<adresse>``.

Jamais journalisé : corps et en-têtes HTTP, valeurs d'environnement, sorties des CLI (seulement tailles et codes
de sortie), listes de modèles (seulement leur nombre), contenu de ``config.toml``. Les ``details`` n'admettent que
des scalaires et des listes de chaînes courtes (200 caractères au plus).
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from acp_poste_contrat.motifs_secrets import MOTIFS

from .verrou import Verrou, VerrouOccupe

NOM = "poste.jsonl"
NIVEAUX = ("detail", "info", "avertissement", "erreur")
DETAIL_MAX = 200
LISTE_MAX = 20
MESSAGE_MAX = 600

_PROFIL = re.compile(r"(?i)(?:\b[A-Z]:)?[\\/]+(?:Users|home)[\\/]+[^\\/\s\"'<>|:]+")
_ADRESSE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def masquer(texte: str, valeurs: dict[str, str] | None = None) -> str:
    """Texte masqué (valeurs exactes, motifs de secrets, profils, adresses) ; jamais la valeur d'origine."""

    if not isinstance(texte, str) or not texte:
        return texte
    for nom, valeur in (valeurs or {}).items():
        if valeur:
            texte = texte.replace(valeur, f"«masqué:{nom}»")
    for nom, motif in MOTIFS.items():
        if motif.pattern.startswith("^"):
            texte = "\n".join(f"«masqué:{nom}»" if motif.search(ligne) else ligne for ligne in texte.split("\n"))
        else:
            texte = motif.sub(f"«masqué:{nom}»", texte)
    texte = _ADRESSE.sub("<adresse>", texte)
    return _PROFIL.sub("<profil>", texte)


def _detail(valeur: Any, valeurs: dict[str, str]) -> Any:
    if valeur is None or isinstance(valeur, (bool, int, float)):
        return valeur
    if isinstance(valeur, str):
        return masquer(valeur, valeurs)[:DETAIL_MAX]
    if isinstance(valeur, (list, tuple)) and len(valeur) <= LISTE_MAX and all(isinstance(v, str) for v in valeur):
        return [masquer(v, valeurs)[:DETAIL_MAX] for v in valeur]
    return "«refusé : type non journalisable»"


class Journal:
    """Écrivain du journal ; sûr entre processus du même compte (verrou d'écriture court)."""

    def __init__(self, dossier: Path, *, taille_max_octets: int = 1024 * 1024, fichiers: int = 5,
                 niveau: str = "info") -> None:
        self.dossier = Path(dossier)
        self.taille_max_octets = int(taille_max_octets)
        self.fichiers = max(1, int(fichiers))
        self.niveau = niveau if niveau in ("info", "detail") else "info"
        self._valeurs: dict[str, str] = {}
        self._limites: dict[str, float] = {}

    @property
    def chemin(self) -> Path:
        return self.dossier / NOM

    def masquer_valeur(self, nom: str, valeur: str | None) -> None:
        """Enregistre une valeur exacte à masquer partout (jeton, code) ; ``None`` l'oublie."""
        if valeur:
            self._valeurs[nom] = valeur
        else:
            self._valeurs.pop(nom, None)

    def valeurs_masquees(self) -> list[str]:
        return list(self._valeurs.values())

    def masquer(self, texte: str) -> str:
        return masquer(texte, self._valeurs)

    def ecrire(self, niveau: str, evenement: str, message: str, **details: Any) -> None:
        """Ajoute une ligne ; ne lève jamais (un journal plein ou verrouillé ne fait pas tomber le service)."""
        if niveau not in NIVEAUX or (niveau == "detail" and self.niveau != "detail"):
            return
        ligne = {
            "quand": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "niveau": niveau,
            "evenement": re.sub(r"[^a-z0-9_]", "_", str(evenement).lower())[:60],
            "message": masquer(str(message), self._valeurs)[:MESSAGE_MAX],
            "details": {str(k)[:40]: _detail(v, self._valeurs) for k, v in list(details.items())[:20]},
        }
        donnees = (json.dumps(ligne, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self.dossier.mkdir(parents=True, exist_ok=True)
            with Verrou(self.dossier / f"{NOM}.verrou").prendre(attendre_s=1.0):
                self._tourner_si_besoin(len(donnees))
                with self.chemin.open("ab") as flux:
                    flux.write(donnees)
        except (OSError, VerrouOccupe):
            pass

    def ecrire_au_plus(self, cle: str, periode_s: float, niveau: str, evenement: str, message: str,
                       **details: Any) -> bool:
        """Comme :meth:`ecrire`, au plus une fois par ``periode_s`` pour ``cle`` (erreurs réseau répétées)."""
        maintenant = time.monotonic()
        derniere = self._limites.get(cle)
        if derniere is not None and maintenant - derniere < periode_s:
            return False
        self._limites[cle] = maintenant
        self.ecrire(niveau, evenement, message, **details)
        return True

    def _tourner_si_besoin(self, supplement: int) -> None:
        try:
            taille = self.chemin.stat().st_size
        except FileNotFoundError:
            return
        if taille + supplement <= self.taille_max_octets:
            return
        if self.fichiers == 1:
            self.chemin.unlink()
            return
        plus_ancien = self.dossier / f"{NOM}.{self.fichiers - 1}"
        if plus_ancien.exists():
            plus_ancien.unlink()
        for rang in range(self.fichiers - 2, 0, -1):
            source = self.dossier / f"{NOM}.{rang}"
            if source.exists():
                source.replace(self.dossier / f"{NOM}.{rang + 1}")
        self.chemin.replace(self.dossier / f"{NOM}.1")


def lire_fin(dossier: Path, lignes: int) -> list[str] | None:
    """Les ``lignes`` dernières lignes du journal courant, ou ``None`` s'il n'existe pas."""
    chemin = Path(dossier) / NOM
    try:
        contenu = chemin.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    return contenu.splitlines()[-max(1, lignes):]
