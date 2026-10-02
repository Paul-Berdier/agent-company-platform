"""Outillage des tests de l'image de l'exécutant (cahier P6 § 14.1), importé par conftest.py et les tests.

Les tests d'image sont pilotés depuis l'hôte par la CLI ``docker`` contre une image DÉJÀ construite :

    ACP_IMAGE_EXECUTANT=acp-executant:ci                      (cible finale, celle de Railway)
    ACP_IMAGE_EXECUTANT_FACTICE=acp-executant:factice          (cible factice : CLI de test)

Sans ces variables, ils sont IGNORÉS avec leur raison (suite du dépôt sous Windows ou Linux sans Docker) ; avec
``ACP_EXECUTANT_OBLIGATOIRE=1`` (CI de l'exécutant), une image ou un outil absent fait ÉCHOUER au lieu d'ignorer.
Chaque conteneur est nommé ``acp-contrat-exec-<pid>-<n>`` et supprimé, avec ses volumes, à la fin du test.
"""

from __future__ import annotations

import itertools
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
EXECUTANT = RACINE / "executant"
OBLIGATOIRE = os.environ.get("ACP_EXECUTANT_OBLIGATOIRE") == "1"
_COMPTEUR = itertools.count(1)


def exiger(variable: str) -> str:
    valeur = os.environ.get(variable)
    if valeur and shutil.which("docker"):
        return valeur
    raison = f"{variable} absente ou docker introuvable : image de l'exécutant non testée ici"
    if OBLIGATOIRE:
        pytest.fail(f"{raison} (ACP_EXECUTANT_OBLIGATOIRE=1).")
    pytest.skip(raison)


def docker(*arguments: str, entree: bytes | None = None, delai: float = 300,
           verifier: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    resultat = subprocess.run(["docker", *arguments], input=entree, capture_output=True, timeout=delai, env=env,
                              check=False)
    resultat.stdout = resultat.stdout.decode("utf-8", "replace")  # type: ignore[assignment]
    resultat.stderr = resultat.stderr.decode("utf-8", "replace")  # type: ignore[assignment]
    if verifier and resultat.returncode != 0:
        raise AssertionError(f"docker {' '.join(arguments[:6])} … : code {resultat.returncode}\n"
                             f"{resultat.stdout[-3000:]}\n{resultat.stderr[-3000:]}")
    return resultat


class Ressources:
    """Conteneurs, volumes et images dérivées d'un test, toujours supprimés à la fin."""

    def __init__(self) -> None:
        self.conteneurs: list[str] = []
        self.volumes: list[str] = []
        self.images: list[str] = []

    def nom(self, genre: str = "c") -> str:
        return f"acp-contrat-exec-{os.getpid()}-{genre}{next(_COMPTEUR)}"

    def volume(self) -> str:
        nom = self.nom("v")
        docker("volume", "create", nom, verifier=True)
        self.volumes.append(nom)
        return nom

    def nettoyer(self) -> None:
        for nom in self.conteneurs:
            docker("rm", "-f", "-v", nom)
        for nom in self.volumes:
            docker("volume", "rm", "-f", nom)
        for nom in self.images:
            docker("rmi", "-f", nom)

    def image_politique_de_test(self, image: str) -> str:
        """Image dérivée JETABLE : la même image, avec la politique versionnée dont l'origine de Hermes ne vaut plus
        le gabarit (le superviseur démarre alors et attend l'enrôlement, sans aucune requête). Rien d'autre."""
        texte = (EXECUTANT / "politique" / "executant.toml").read_text(encoding="utf-8")
        gabarit = 'origine = "https://<libellé-hermes>.up.railway.app"'
        assert texte.count(gabarit) == 1
        texte = texte.replace(gabarit, 'origine = "https://hermes-acp-test.up.railway.app"')
        nom = f"acp-contrat-exec-{os.getpid()}-politique{next(_COMPTEUR)}"
        with tempfile.TemporaryDirectory(prefix="acp-exec-politique-") as dossier:
            contexte = Path(dossier)
            (contexte / "executant.toml").write_text(texte, encoding="utf-8", newline="\n")
            (contexte / "Dockerfile").write_text(
                "ARG IMAGE\nFROM ${IMAGE}\nCOPY executant.toml /etc/acp/executant.toml\n"
                "RUN chown root:root /etc/acp/executant.toml && chmod 0444 /etc/acp/executant.toml\n",
                encoding="utf-8", newline="\n")
            docker("build", "-q", "--build-arg", f"IMAGE={image}", "-t", nom, str(contexte), delai=600,
                   verifier=True)
        self.images.append(nom)
        return nom


def lancer(image: str, *commande: str, entree: bytes | None = None, options: tuple[str, ...] = (),
           point_d_entree: str = "sh", delai: float = 300) -> subprocess.CompletedProcess:
    """Conteneur jetable (``--rm``) avec un point d'entrée remplacé ; ``options`` : options de ``docker run``."""
    interactif = ("-i",) if entree is not None else ()
    return docker("run", "--rm", *interactif, *options, "--entrypoint", point_d_entree, image, *commande,
                  entree=entree, delai=delai)


def afficher(titre: str, texte: str) -> None:
    print(f"\n===== {titre} =====\n{texte}")
