"""Instantanés et restaurations de volumes nommés, côté hôte (étape P9, cahier P9 § 3.2).

- ``manifeste`` et ``bases`` : outils/empreinte_volume.py lancé dans l'image de test, SOUS ROOT (``-u 0`` : des
  secrets sont en 0600), le volume monté EN LECTURE SEULE, ``--entrypoint`` explicite (l'entrée ``acp-entree`` refuse
  hors PID 1). Couche 1 (octets) et couche 2 (contenu SQLite) du cahier § 3.1. L'image d'Authelia n'a pas de Python :
  son volume ``/config`` est lu par le même conteneur d'outils.
- ``Archives`` : un volume nommé jetable qui reçoit les archives tar (``--numeric-owner``, propriétaires et modes
  gardés), puis ``volume_restaure`` les extrait (``--same-owner -p``) dans un volume NEUF. Écart au cahier, dit : un
  volume plutôt qu'un dossier de l'hôte monté en ``/sortie``, pour que la même suite tourne sous Windows (chemins de
  l'hôte) et sous Linux sans conversion ; l'archive ne quitte jamais Docker.
- ``a_chaud`` : ``docker pause`` de TOUS les conteneurs donnés pendant la copie (état des fichiers à un instant
  unique, l'analogue local le plus proche d'un instantané copie-sur-écriture de Railway, décision P9-5), puis
  ``unpause`` en ``finally`` ; ``a_froid`` : ``docker stop -t 90`` dans l'ordre donné (arrêt propre).

Tout volume créé ici est enregistré dans les ``Ressources`` (préfixe ``acp-contrat-``) et supprimé à la fin.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence

from conftest import docker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outils"))

from empreinte_volume import comparer_bases, comparer_manifestes  # noqa: E402

PYTHON = "/opt/hermes/.venv/bin/python"
OUTIL = "/opt/acp-tests/outils/empreinte_volume.py"


def _releve(image_tests: str, volume: str, commande: str) -> Dict[str, Any]:
    sortie = docker("run", "--rm", "-u", "0", "--network", "none", "-v", f"{volume}:/v:ro", "--entrypoint", PYTHON,
                    image_tests, OUTIL, commande, "/v", delai=600)
    return json.loads(sortie.stdout)


def manifeste(image_tests: str, volume: str) -> Dict[str, Any]:
    """Couche 1 : manifeste du volume (chemins, types, modes, uid, gid, tailles, SHA-256, cibles de liens)."""
    return _releve(image_tests, volume, "manifeste")


def bases(image_tests: str, volume: str) -> Dict[str, Any]:
    """Couche 2 : empreinte logique de chaque base SQLite du volume, lue sur une copie."""
    return _releve(image_tests, volume, "sqlite")


def resume_manifeste(m: Dict[str, Any]) -> str:
    return f"{len(m['entrees'])} entrées {m['decompte']}, prises exclues : {m['prises'] or 'aucune'}"


def resume_bases(b: Dict[str, Any]) -> Dict[str, Any]:
    """Ce que le journal du test imprime d'une couche 2 : jamais un contenu, seulement des décomptes et empreintes."""
    return {base: {"integrite": e.get("integrite"), "user_version": e.get("user_version"),
                   "meta_schema": e.get("meta_schema"), "schema": (e.get("schema") or "")[:12],
                   "annexes": e.get("annexes"),
                   "tables": {t: (v.get("lignes") if not v.get("virtuelle") else "virtuelle")
                              for t, v in (e.get("tables") or {}).items()}}
            for base, e in sorted(b["bases"].items())}


class Archives:
    """Archives tar de volumes, rangées dans un volume nommé jetable."""

    def __init__(self, ressources, image_tests: str) -> None:
        self.ressources = ressources
        self.image_tests = image_tests
        self.volume = ressources.nom("vol-archives")
        docker("volume", "create", self.volume)
        ressources.volumes.append(self.volume)

    def instantane(self, volume: str, nom: str) -> Dict[str, Any]:
        """Archive ``<nom>.tar`` du volume (propriétaires numériques, modes) ; rend la taille et les avertissements de
        tar (les prises Unix sont ignorées par GNU tar : « socket ignored », attendu, voir empreinte_volume.py)."""
        resultat = docker("run", "--rm", "-u", "0", "--network", "none", "-v", f"{volume}:/v:ro",
                          "-v", f"{self.volume}:/archives", "--entrypoint", "tar", self.image_tests,
                          "--numeric-owner", "-cpf", f"/archives/{nom}.tar", "-C", "/v", ".", verifier=False, delai=900)
        avertissements = [l for l in resultat.stderr.splitlines() if l.strip()]
        inattendus = [l for l in avertissements if not l.endswith(": socket ignored")]
        if resultat.returncode != 0 or inattendus:
            raise AssertionError(f"archive {nom} de {volume} : tar code {resultat.returncode}, {inattendus}")
        taille = docker("run", "--rm", "-v", f"{self.volume}:/archives:ro", "--entrypoint", "stat",
                        self.image_tests, "-c", "%s", f"/archives/{nom}.tar").stdout.strip()
        return {"archive": f"{nom}.tar", "octets": int(taille), "tar": avertissements}

    def restaurer(self, nom: str, volume: str) -> None:
        resultat = docker("run", "--rm", "-u", "0", "--network", "none", "-v", f"{self.volume}:/archives:ro",
                          "-v", f"{volume}:/v", "--entrypoint", "tar", self.image_tests, "--numeric-owner",
                          "--same-owner", "-xpf", f"/archives/{nom}.tar", "-C", "/v", verifier=False, delai=900)
        if resultat.returncode != 0 or resultat.stderr.strip():
            raise AssertionError(f"restauration de {nom} : tar code {resultat.returncode}, {resultat.stderr[-2000:]}")

    def volume_restaure(self, nom: str, role: str) -> str:
        """Volume NEUF (jamais un volume existant) garni de l'archive ``<nom>.tar``."""
        volume = self.ressources.nom(f"vol-{role}")
        docker("volume", "create", volume)
        self.ressources.volumes.append(volume)
        self.restaurer(nom, volume)
        return volume


@contextmanager
def a_chaud(conteneurs: Sequence[str]) -> Iterator[None]:
    """Tous les conteneurs gelés ensemble (``docker pause``) pendant le bloc, dégelés même en échec."""
    docker("pause", *conteneurs)
    try:
        yield
    finally:
        docker("unpause", *conteneurs, verifier=False)


def a_froid(conteneurs: Sequence[str], delai: int = 90) -> List[Dict[str, Any]]:
    """Arrêt propre, un conteneur après l'autre dans l'ordre donné ; rend le code de sortie de chacun."""
    etats = []
    for nom in conteneurs:
        docker("stop", "-t", str(delai), nom, delai=delai + 60)
        code = docker("inspect", "-f", "{{.State.ExitCode}}", nom).stdout.strip()
        etats.append({"conteneur": nom, "code": int(code)})
    return etats


__all__ = ["Archives", "a_chaud", "a_froid", "bases", "comparer_bases", "comparer_manifestes", "manifeste",
           "resume_bases", "resume_manifeste"]
