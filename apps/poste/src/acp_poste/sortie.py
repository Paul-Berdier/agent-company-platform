"""File de sortie persistante de l'exécutant (cahier P6 § 5.9).

Toute requête ``terminer``, ``question``, ``bloquer``, ``reprendre`` ou ``arret`` est d'abord écrite de façon atomique
dans ``/donnees/acp/sortie/<horodatage>-<rang>-<id_envoi>.json`` (root, 0600), **puis** envoyée. Chaque requête porte un
``id_envoi`` (UUID v4) : un renvoi après une coupure rend la même réponse (``deja_recu``), sans double effet.

- 2xx : retrait du fichier ;
- 409 ``reclamation_perdue`` : déplacé dans ``sortie/refusees/`` (diagnostic), sans effet dans ACP ;
- refus du contrat CÔTÉ EXÉCUTANT, avant l'envoi (:class:`acp_poste.protocole.RefusAvantEnvoi`) : déplacé dans
  ``sortie/refusees/`` ; la file continue (relecture de P6 : le fichier restait en tête et plus rien n'était
  réclamé) ;
- autre 4xx définitif (contrat, carte inconnue, secret détecté…) : retrait, journalisé par l'appelant ;
- réseau, 5xx, 429, 401 ambigu de la couture : le fichier reste ; le rejeu s'arrête là pour garder l'ORDRE.

Au démarrage, la file est rejouée dans l'ordre, **avant** tout ``reclamer``. Seuls les battements portant des événements publics passent aussi par cette file ;
leur retrait exige un acquittement explicite des identifiants.
"""

from __future__ import annotations

import json
import os
import stat
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .coffre import ecrire_atomiquement
from .protocole import (HermesIndisponible, HorsContrat, JetonRefuse, PosteRevoque, Refus, RefusAvantEnvoi,
                        TropFrequent)

ROUTES_FILE = ("terminer", "question", "bloquer", "reprendre", "arret", "battement")
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
        self._verrou_envoi = threading.RLock()
        self.refusees = Path(refusees) if refusees is not None else self.dossier / "refusees"

    def deposer(self, route: str, corps: dict[str, Any], *, maintenant: datetime | None = None) -> Path:
        """Écrit la requête (atomique, 0600) avant tout envoi ; ``id_envoi`` est ajouté s'il manque."""
        if route not in ROUTES_FILE:
            raise ValueError(f"Route hors de la file de sortie : {route}.")
        if route == "battement":
            if not corps.get("evenements"):
                raise ValueError("Un battement sans événement reste hors de la file de sortie.")
            if len(self.en_attente()) >= FICHIERS_MAX - 5:
                raise ValueError("Journal public distant saturé : exécution interrompue, événements conservés.")
        corps = dict(corps)
        corps.setdefault("id_envoi", nouvel_id_envoi())
        instant = (maintenant or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
        self.dossier.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dossier, 0o700)
        # Clé d'ordre « <instant>-<rang> » strictement croissante : deux dépôts dans la même tranche d'horloge (la
        # résolution de l'horloge varie selon les machines) ou après un recul de l'horloge gardent leur ORDRE.
        cle = f"{instant}-000000"
        existants = [f.name[:len(cle)] for f in self.en_attente()]
        if existants and existants[-1] >= cle:
            precedent, rang = existants[-1].rsplit("-", 1)
            cle = f"{precedent}-{int(rang) + 1:06d}" if rang.isdigit() else cle
        fichier = self.dossier / f"{cle}-{corps['id_envoi']}.json"
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

    def _journal_refuse(self, corps: dict[str, Any]) -> bool:
        """Les lots refusés font foi après redémarrage ; pas de marqueur seulement en RAM."""
        try:
            fichiers = self.refusees.iterdir()
        except FileNotFoundError:
            return False
        try:
            for fichier in fichiers:
                if not fichier.is_file() or fichier.suffix != ".json":
                    continue
                lu = self.lire(fichier)
                if lu is not None and lu[0] == "battement" and all(
                        lu[1].get(cle) == corps.get(cle) for cle in ("tableau", "carte", "run_id")):
                    return True
        except FileNotFoundError:
            return False
        return False

    def envoyer(self, fichier: Path, envoi: Callable[[str, dict[str, Any]], Any]) -> ResultatEnvoi | None:
        # Le long-poll peut rejouer pendant le battement de la carte. Le verrou ne
        # protège QUE l'envoi dans les threads ; deposer/stdout ne l'attendent jamais.
        with self._verrou_envoi:
            if not fichier.exists():
                return None  # déjà traité par l'autre chemin de rejeu
            return self._envoyer(fichier, envoi)

    def _envoyer(self, fichier: Path, envoi: Callable[[str, dict[str, Any]], Any]) -> ResultatEnvoi | None:
        """Envoie UN fichier ; ``None`` s'il est illisible (rangé avec les refusés). Lève les refus TRANSITOIRES
        (réseau, 5xx, 429, 401 ambigu, révocation) : le fichier reste en file."""
        lu = self.lire(fichier)
        if lu is None:
            self._ranger(fichier)
            return None
        route, corps = lu
        if route == "terminer" and self._journal_refuse(corps):
            # Conserver le résultat pour diagnostic, puis remplacer atomiquement l'issue
            # DANS la même file. Même id_envoi : le renvoi de bloquer reste idempotent.
            self.refusees.mkdir(parents=True, exist_ok=True)
            os.chmod(self.refusees, 0o700)
            ecrire_atomiquement(self.refusees / fichier.name,
                                json.dumps({"route": route, "corps": corps}, ensure_ascii=False).encode("utf-8"))
            route = "bloquer"
            corps = {cle: corps[cle] for cle in ("id_envoi", "tableau", "carte", "run_id")}
            corps.update(genre="capacite", raison="Journal public incomplet : un lot a été refusé par Hermes. "
                         "Résultat conservé sur l’exécutant dans sortie/refusees ; carte bloquée.")
            ecrire_atomiquement(fichier, json.dumps({"route": route, "corps": corps},
                                                    ensure_ascii=False).encode("utf-8"))
        try:
            reponse = envoi(route, corps)
        except (HermesIndisponible, TropFrequent, JetonRefuse, PosteRevoque, HorsContrat):
            raise
        except RefusAvantEnvoi as exc:
            # Définitif : jamais envoyable tel quel. Rangé pour le diagnostic ; la file continue.
            self._ranger(fichier)
            return ResultatEnvoi(route, corps, refus=exc, deplace=True)
        except Refus as exc:
            if exc.statut is None or not 400 <= exc.statut < 500:
                raise
            if exc.code == "reclamation_perdue" or route == "battement":
                self._ranger(fichier)
                return ResultatEnvoi(route, corps, refus=exc, deplace=True)
            fichier.unlink(missing_ok=True)
            return ResultatEnvoi(route, corps, refus=exc, retire=True)
        if route == "battement":
            lire = reponse.get if isinstance(reponse, dict) else lambda cle, defaut=None: getattr(reponse, cle, defaut)
            if lire("valide") is False:
                self._ranger(fichier)
                return ResultatEnvoi(route, corps, reponse=reponse, deplace=True)
            attendus = [e["id"] for e in corps.get("evenements", [])]
            recus = lire("evenements_recus", [])
            if len(recus) != len(attendus) or set(recus) != set(attendus):
                raise HorsContrat("Événements publics non acquittés : lot conservé pour le prochain renvoi.")
        fichier.unlink(missing_ok=True)
        return ResultatEnvoi(route, corps, reponse=reponse, retire=True)

    def purger_refusees(self, *, age_s: float, maintenant: float) -> int:
        """Requêtes rangées dans ``refusees/`` (diagnostic) plus anciennes que ``age_s`` : retirées (purge du disque)."""
        retirees = 0
        try:
            fichiers = list(self.refusees.iterdir())
        except OSError:
            return 0
        for fichier in fichiers:
            try:
                etat = os.lstat(fichier)
            except OSError:
                continue
            if stat.S_ISREG(etat.st_mode) and etat.st_mtime < maintenant - age_s:
                fichier.unlink(missing_ok=True)
                retirees += 1
        return retirees

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
