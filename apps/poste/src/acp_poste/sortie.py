"""File de sortie persistante de l'exécutant (cahier P6 § 5.9).

Toute requête ``terminer``, ``question``, ``bloquer``, ``reprendre`` ou ``arret`` est d'abord écrite de façon atomique
dans ``/donnees/acp/sortie/<horodatage>-<id_envoi>.json`` (root, 0600), **puis** envoyée. Chaque requête porte un
``id_envoi`` (UUID v4) : un renvoi après une coupure rend la même réponse (``deja_recu``), sans double effet.

- 2xx : retrait du fichier ;
- 409 ``reclamation_perdue`` : déplacé dans ``sortie/refusees/`` (diagnostic), sans effet dans ACP ;
- autre 4xx définitif (contrat, carte inconnue, secret détecté…) : retrait, journalisé par l'appelant ;
- réseau, 5xx, 429, 401 ambigu de la couture : le fichier reste ; le rejeu s'arrête là pour garder l'ORDRE.

Au démarrage, la file est rejouée dans l'ordre, **avant** tout ``reclamer``. Le ``battement`` n'y passe pas : il n'a
de sens qu'en direct.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .coffre import ecrire_atomiquement
from .protocole import HermesIndisponible, HorsContrat, JetonRefuse, PosteRevoque, Refus, TropFrequent

ROUTES_FILE = ("terminer", "question", "bloquer", "reprendre", "arret")
FICHIERS_MAX = 1000


def nouvel_id_envoi() -> str:
    return str(uuid.uuid4())


@dataclass
class ResultatEnvoi:
    route: str
    corps: dict[str, Any]
    reponse: Any = None
    refus: Refus | None = None
    retire: bool = False
    deplace: bool = False


class FileSortie:
    def __init__(self, dossier: Path, refusees: Path | None = None) -> None:
        self.dossier = Path(dossier)
        self.refusees = Path(refusees) if refusees is not None else self.dossier / "refusees"

    def deposer(self, route: str, corps: dict[str, Any], *, maintenant: datetime | None = None) -> Path:
        """Écrit la requête (atomique, 0600) avant tout envoi ; ``id_envoi`` est ajouté s'il manque."""
        if route not in ROUTES_FILE:
            raise ValueError(f"Route hors de la file de sortie : {route}.")
        corps = dict(corps)
        corps.setdefault("id_envoi", nouvel_id_envoi())
        instant = (maintenant or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
        self.dossier.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dossier, 0o700)
        fichier = self.dossier / f"{instant}-{corps['id_envoi']}.json"
        ecrire_atomiquement(fichier, json.dumps({"route": route, "corps": corps}, ensure_ascii=False).encode("utf-8"))
        return fichier

    def en_attente(self) -> list[Path]:
        try:
            fichiers = sorted(f for f in self.dossier.iterdir() if f.is_file() and f.suffix == ".json"
                              and not f.name.startswith("."))
        except FileNotFoundError:
            return []
        return fichiers[:FICHIERS_MAX]

    @staticmethod
    def lire(fichier: Path) -> tuple[str, dict[str, Any]] | None:
        try:
            donnees = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(donnees, dict) or donnees.get("route") not in ROUTES_FILE or not isinstance(
                donnees.get("corps"), dict):
            return None
        return donnees["route"], donnees["corps"]

    def _ranger(self, fichier: Path) -> None:
        self.refusees.mkdir(parents=True, exist_ok=True)
        os.chmod(self.refusees, 0o700)
        os.replace(fichier, self.refusees / fichier.name)

    def envoyer(self, fichier: Path, envoi: Callable[[str, dict[str, Any]], Any]) -> ResultatEnvoi | None:
        """Envoie UN fichier ; ``None`` s'il est illisible (rangé avec les refusés). Lève les refus TRANSITOIRES
        (réseau, 5xx, 429, 401 ambigu, révocation) : le fichier reste en file."""
        lu = self.lire(fichier)
        if lu is None:
            self._ranger(fichier)
            return None
        route, corps = lu
        try:
            reponse = envoi(route, corps)
        except (HermesIndisponible, TropFrequent, JetonRefuse, PosteRevoque, HorsContrat):
            raise
        except Refus as exc:
            if exc.statut is None or not 400 <= exc.statut < 500:
                raise
            if exc.code == "reclamation_perdue":
                self._ranger(fichier)
                return ResultatEnvoi(route, corps, refus=exc, deplace=True)
            fichier.unlink(missing_ok=True)
            return ResultatEnvoi(route, corps, refus=exc, retire=True)
        fichier.unlink(missing_ok=True)
        return ResultatEnvoi(route, corps, reponse=reponse, retire=True)

    def rejouer(self, envoi: Callable[[str, dict[str, Any]], Any]) -> tuple[list[ResultatEnvoi], Refus | None]:
        """Rejoue la file dans l'ordre ; s'arrête au premier refus transitoire (rendu)."""
        resultats: list[ResultatEnvoi] = []
        for fichier in self.en_attente():
            try:
                resultat = self.envoyer(fichier, envoi)
            except Refus as exc:
                return resultats, exc
            if resultat is not None:
                resultats.append(resultat)
        return resultats, None
