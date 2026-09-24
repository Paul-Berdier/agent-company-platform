"""Outillage des tests de contrat de l'image : ils pilotent Docker depuis l'hôte.

Lancement (le workflow image.yml le fait après la construction des deux images) :

  ACP_IMAGE=acp-hermes:ci ACP_IMAGE_TESTS=acp-hermes-tests:ci \
      python -m pytest -p no:cacheprovider -s -v hermes/tests/contrat

Chaque conteneur démarre sur un volume nommé JETABLE, jamais sur un volume qui contient des
données ; tout ce qui est créé (conteneurs, volumes, réseau) porte le préfixe
``acp-contrat-<aléa>`` et est supprimé à la fin, même en cas d'échec.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pytest

RACINE_HERMES = Path(__file__).resolve().parents[2]

ENV_VALIDE: Dict[str, str] = {
    "HERMES_DASHBOARD_PUBLIC_URL": "https://hermes.acp.test",
    "HERMES_DASHBOARD_OIDC_ISSUER": "https://idp.acp.test:8443",
    "HERMES_DASHBOARD_OIDC_CLIENT_ID": "acp-tableau",
}


def _image(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        pytest.fail(f"{nom} n'est pas défini : ces tests exigent l'image construite (voir conftest.py).",
                    pytrace=False)
    return valeur


@pytest.fixture(scope="session")
def image() -> str:
    return _image("ACP_IMAGE")


@pytest.fixture(scope="session")
def image_tests() -> str:
    return _image("ACP_IMAGE_TESTS")


def docker(*arguments: str, entree: Optional[str] = None, delai: int = 300,
           verifier: bool = True) -> subprocess.CompletedProcess:
    resultat = subprocess.run(
        ["docker", *arguments], input=entree, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=delai)
    if verifier and resultat.returncode != 0:
        raise AssertionError(
            f"docker {' '.join(arguments[:4])}… a échoué ({resultat.returncode}) :\n"
            f"{resultat.stdout[-3000:]}\n{resultat.stderr[-3000:]}")
    return resultat


def afficher(titre: str, texte: str) -> None:
    """Preuve lisible dans le journal de CI (pytest -s)."""
    print(f"\n===== {titre} =====\n{texte.rstrip()}\n", flush=True)


class Ressources:
    """Conteneurs, volumes et réseaux créés par les tests ; tout est supprimé à la fin."""

    def __init__(self) -> None:
        self.prefixe = f"acp-contrat-{uuid.uuid4().hex[:8]}"
        self.conteneurs: List[str] = []
        self.volumes: List[str] = []
        self.reseaux: List[str] = []
        self._n = 0

    def nom(self, role: str) -> str:
        self._n += 1
        return f"{self.prefixe}-{role}-{self._n}"

    def volume(self, image: str, fichiers: Optional[Dict[str, str]] = None,
               liens: Optional[Dict[str, str]] = None) -> str:
        """Volume nommé neuf, éventuellement garni (fichiers et liens symboliques), rendu à
        l'uid hermes comme le ferait 01-hermes-setup sur un volume déjà utilisé."""
        nom = self.nom("vol")
        docker("volume", "create", nom)
        self.volumes.append(nom)
        for chemin, contenu in (fichiers or {}).items():
            cible = f"/opt/data/{chemin}"
            docker("run", "--rm", "-i", "-v", f"{nom}:/opt/data", "--entrypoint", "sh", image, "-c",
                   f'mkdir -p "$(dirname "{cible}")" && cat > "{cible}"', entree=contenu)
        for chemin, vers in (liens or {}).items():
            cible = f"/opt/data/{chemin}"
            docker("run", "--rm", "-v", f"{nom}:/opt/data", "--entrypoint", "sh", image, "-c",
                   f'mkdir -p "$(dirname "{cible}")" && ln -s "{vers}" "{cible}"')
        docker("run", "--rm", "-v", f"{nom}:/opt/data", "--entrypoint", "sh", image, "-c",
               "chown -hR 10000:10000 /opt/data")
        return nom

    def reseau(self) -> str:
        nom = self.nom("net")
        docker("network", "create", nom)
        self.reseaux.append(nom)
        return nom

    def nettoyer(self) -> None:
        for nom in reversed(self.conteneurs):
            docker("rm", "-f", "-v", nom, verifier=False, delai=120)
        for nom in self.volumes:
            docker("volume", "rm", "-f", nom, verifier=False, delai=120)
        for nom in self.reseaux:
            docker("network", "rm", nom, verifier=False, delai=120)


@pytest.fixture(scope="session")
def ressources():
    res = Ressources()
    yield res
    res.nettoyer()


def options_env(env: Dict[str, str]) -> List[str]:
    options: List[str] = []
    for cle, valeur in env.items():
        options += ["-e", f"{cle}={valeur}"]
    return options


def demarrer_jusqu_a_l_arret(ressources: Ressources, image: str, env: Dict[str, str],
                             volume: Optional[str] = None) -> Tuple[int, str]:
    """Lance un conteneur au premier plan et rend (code de sortie, journal complet)."""
    nom = ressources.nom("refus")
    ressources.conteneurs.append(nom)
    volume = volume or ressources.volume(image)
    resultat = docker("run", "--name", nom, "-v", f"{volume}:/opt/data", *options_env(env), image,
                      verifier=False, delai=240)
    return resultat.returncode, resultat.stdout + resultat.stderr


class Conteneur:
    def __init__(self, nom: str) -> None:
        self.nom = nom

    def executer(self, commande: Iterable[str], *, utilisateur: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None, entree: Optional[str] = None,
                 verifier: bool = False, delai: int = 180) -> subprocess.CompletedProcess:
        options: List[str] = ["exec", "-i"] if entree is not None else ["exec"]
        if utilisateur:
            options += ["-u", utilisateur]
        for cle, valeur in (env or {}).items():
            options += ["-e", f"{cle}={valeur}"]
        return docker(*options, self.nom, *commande, entree=entree, verifier=verifier, delai=delai)

    def sh(self, script: str, **options) -> subprocess.CompletedProcess:
        return self.executer(["sh", "-c", script], **options)

    def python(self, code: str, **options) -> subprocess.CompletedProcess:
        return self.executer(["/opt/hermes/.venv/bin/python", "-c", code], **options)

    def http(self, chemin: str, *, jeton: Optional[str] = None, methode: str = "GET",
             corps: Optional[str] = None) -> Tuple[int, str, str]:
        """(code, corps, en-tête Location) d'une requête au tableau de bord, en bouclage local."""
        commande = ["curl", "-s", "-o", "/tmp/acp-reponse", "-w", "%{http_code} %{redirect_url}",
                    "-X", methode, f"http://127.0.0.1:9119{chemin}"]
        if jeton:
            commande += ["-H", f"Authorization: Bearer {jeton}"]
        if corps is not None:
            commande += ["-H", "Content-Type: application/json", "--data", corps]
        sortie = self.executer(commande, verifier=True).stdout.strip()
        code, _, redirection = sortie.partition(" ")
        contenu = self.executer(["cat", "/tmp/acp-reponse"], verifier=True).stdout
        return int(code), contenu, redirection

    def json(self, chemin: str, **options) -> Tuple[int, object]:
        code, contenu, _ = self.http(chemin, **options)
        try:
            return code, json.loads(contenu)
        except ValueError:
            return code, contenu

    def journaux(self) -> str:
        resultat = docker("logs", self.nom, verifier=False)
        return resultat.stdout + resultat.stderr

    def attendre_pret(self, delai: float = 240) -> None:
        """Attend que le tableau de bord réponde (``/api/status`` public, 200)."""
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            etat = docker("inspect", "-f", "{{.State.Running}}", self.nom, verifier=False).stdout.strip()
            if etat == "false":
                raise AssertionError(f"le conteneur {self.nom} s'est arrêté :\n{self.journaux()[-4000:]}")
            code = self.executer(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                                  "http://127.0.0.1:9119/api/status"]).stdout.strip()
            if code == "200":
                return
            time.sleep(2)
        raise AssertionError(f"tableau de bord injoignable après {delai} s :\n{self.journaux()[-4000:]}")

    def attendre_passerelle(self, delai: float = 180) -> None:
        """Attend que la passerelle ait branché son api_server : le tableau de bord répond
        parfois avant (constaté sur un poste chargé)."""
        limite = time.monotonic() + delai
        dernier: object = None
        while time.monotonic() < limite:
            code, statut = self.json("/api/status")
            dernier = statut
            if code == 200 and isinstance(statut, dict):
                serveur = (statut.get("gateway_platforms") or {}).get("api_server") or {}
                if statut.get("gateway_running") and serveur.get("state") == "connected":
                    return
            time.sleep(2)
        raise AssertionError(f"api_server de la passerelle non branché après {delai} s : {dernier}")


def lancer(ressources: Ressources, image: str, env: Dict[str, str], *, volume: Optional[str] = None,
           reseau: Optional[str] = None) -> Conteneur:
    nom = ressources.nom("hermes")
    ressources.conteneurs.append(nom)
    volume = volume or ressources.volume(image)
    options = ["run", "-d", "--name", nom, "-v", f"{volume}:/opt/data"]
    if reseau:
        options += ["--network", reseau]
    docker(*options, *options_env(env), image)
    conteneur = Conteneur(nom)
    conteneur.attendre_pret()
    conteneur.attendre_passerelle()
    return conteneur


def lire_version_epinglee() -> Dict[str, str]:
    valeurs: Dict[str, str] = {}
    for ligne in (RACINE_HERMES / "contrat" / "HERMES_VERSION").read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            cle, _, valeur = ligne.partition("=")
            valeurs[cle] = valeur
    return valeurs
