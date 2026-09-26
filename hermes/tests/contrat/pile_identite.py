"""Pile de test du fournisseur d'identité, partagée par test_identite.py (contrat) et par le test
navigateur (hermes/tests/e2e). Autonome : n'importe pas conftest.py.

Sur un réseau Docker JETABLE :
- ``identite`` : l'image identite/ (Authelia épinglé + garde root), alias ``identite-interne``
  (l'équivalent du domaine privé *.railway.internal), volume nommé jetable sur /config ;
- ``hermes`` : l'image de TEST de Hermes (elle fait confiance à l'AC jetable), alias
  ``hermes-interne``, émetteur OIDC https://identite-acp.test, client public hermes-acp ;
- ``bord`` : bord TLS factice (outils/bord_factice.py), alias hermes-acp.test et identite-acp.test,
  qui imite le bord de Railway ; éventuellement publié sur 127.0.0.1 (port choisi par Docker) pour
  un navigateur de l'hôte.

hermes-acp.test et identite-acp.test ont des domaines enregistrables DISTINCTS, comme deux
sous-domaines de up.railway.app (suffixe public) : le navigateur les traite en sites différents.
Tout ce qui est créé porte le préfixe ``acp-contrat-<aléa>`` et est supprimé par ``nettoyer()``.
Le mot de passe ci-dessous n'existe que pour ces tests.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

RACINE_DEPOT = Path(__file__).resolve().parents[3]

HOTE_HERMES = "hermes-acp.test"
HOTE_IDENTITE = "identite-acp.test"
URL_HERMES = f"https://{HOTE_HERMES}"
EMETTEUR = f"https://{HOTE_IDENTITE}"
CLIENT = "hermes-acp"
PORTEES = "openid profile email offline_access"
UTILISATEUR = "proprietaire"
NOM = "Propriétaire d'ACP"
EMAIL = "proprietaire@acp.test"
MOT_DE_PASSE = "Mot-de-passe-de-TEST-acp-2026"
AC = "/opt/acp-tests/ac/ac.pem"
JOURNAL_BORD = "/tmp/bord.jsonl"


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


def journal(nom: str) -> str:
    resultat = docker("logs", nom, verifier=False)
    return resultat.stdout + resultat.stderr


def env_identite(empreinte: str, **modifications: Optional[str]) -> Dict[str, str]:
    """Variables du service identite ; une valeur None retire la variable."""
    env = {
        "ACP_IDP_DOMAINE": HOTE_IDENTITE,
        "ACP_HERMES_URL": URL_HERMES,
        "ACP_IDP_UTILISATEUR": UTILISATEUR,
        "ACP_IDP_NOM": NOM,
        "ACP_IDP_EMAIL": EMAIL,
        "ACP_IDP_MOT_DE_PASSE_ARGON2": empreinte,
    }
    for cle, valeur in modifications.items():
        if valeur is None:
            env.pop(cle, None)
        else:
            env[cle] = valeur
    return env


def options_env(env: Dict[str, str]) -> List[str]:
    options: List[str] = []
    for cle, valeur in env.items():
        options += ["-e", f"{cle}={valeur}"]
    return options


ENV_HERMES = {
    "HERMES_DASHBOARD_PUBLIC_URL": URL_HERMES,
    "HERMES_DASHBOARD_OIDC_ISSUER": EMETTEUR,
    "HERMES_DASHBOARD_OIDC_CLIENT_ID": CLIENT,
    "HERMES_DASHBOARD_OIDC_SCOPES": PORTEES,
}


def empreinte_argon2(image_identite: str, mot_de_passe: str = MOT_DE_PASSE) -> str:
    """Empreinte argon2id calculée par l'image elle-même, paramètres par défaut (m=65536, t=3,
    p=4), exactement comme le propriétaire la calcule sur son poste."""
    sortie = docker("run", "--rm", "--entrypoint", "/app/authelia", image_identite, "crypto", "hash", "generate",
                    "argon2", "--password", mot_de_passe).stdout
    for ligne in sortie.splitlines():
        if ligne.startswith("Digest: "):
            return ligne[len("Digest: "):].strip()
    raise AssertionError(f"empreinte introuvable dans : {sortie!r}")


class Pile:
    """Conteneurs, volumes et réseaux créés ; tout est supprimé par nettoyer()."""

    def __init__(self) -> None:
        self.prefixe = f"acp-contrat-{uuid.uuid4().hex[:8]}"
        self.conteneurs: List[str] = []
        self.volumes: List[str] = []
        self.reseaux: List[str] = []
        self._n = 0

    def nom(self, role: str) -> str:
        self._n += 1
        return f"{self.prefixe}-{role}-{self._n}"

    def volume(self) -> str:
        nom = self.nom("vol")
        docker("volume", "create", nom)
        self.volumes.append(nom)
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

    # ------------------------------------------------------------------ identite

    def lancer_identite(self, image: str, env: Dict[str, str], *, reseau: Optional[str] = None,
                        alias: str = "identite-interne", volume: Optional[str] = None,
                        options: Tuple[str, ...] = ()) -> str:
        nom = self.nom("identite")
        self.conteneurs.append(nom)
        volume = volume or self.volume()
        commande = ["run", "-d", "--name", nom, "-v", f"{volume}:/config", *options]
        if reseau:
            commande += ["--network", reseau, "--network-alias", alias]
        docker(*commande, *options_env(env), image)
        attendre_identite(nom)
        return nom

    # ------------------------------------------------------------------ bord

    def lancer_bord(self, image_tests: str, reseau: str, *, publier: bool = False,
                    routes: Optional[Dict[str, str]] = None) -> Tuple[str, Optional[int]]:
        nom = self.nom("bord")
        self.conteneurs.append(nom)
        routes = routes or {HOTE_HERMES: "hermes-interne:9119", HOTE_IDENTITE: "identite-interne:9091"}
        commande = ["run", "-d", "--name", nom, "--network", reseau]
        for hote in routes:
            commande += ["--network-alias", hote]
        if publier:
            commande += ["-p", "127.0.0.1::443"]
        commande += ["--entrypoint", "/opt/hermes/.venv/bin/python", image_tests, "-u",
                     "/opt/acp-tests/outils/bord_factice.py", "--port", "443",
                     "--certificat", "/opt/acp-tests/ac/bord.pem", "--cle", "/opt/acp-tests/ac/bord.key",
                     "--journal", JOURNAL_BORD]
        for hote, amont in routes.items():
            commande += ["--route", f"{hote}={amont}"]
        docker(*commande)
        port = None
        limite = time.monotonic() + 60
        while time.monotonic() < limite:
            if "[bord-factice] port 443" in journal(nom):
                break
            time.sleep(0.5)
        else:
            raise AssertionError(f"bord factice non démarré :\n{journal(nom)[-3000:]}")
        if publier:
            sortie = docker("port", nom, "443/tcp").stdout.strip().splitlines()[0]
            port = int(sortie.rsplit(":", 1)[1])
        return nom, port

    # ------------------------------------------------------------------ hermes

    def lancer_hermes(self, image_tests: str, reseau: str, env: Optional[Dict[str, str]] = None,
                      fichiers: Optional[Dict[str, str]] = None) -> str:
        """``fichiers`` : fichiers déposés dans le volume jetable AVANT le démarrage (étape P4 : le
        config.yaml du modèle factice), rendus à l'uid hermes comme sur un volume déjà utilisé."""
        nom = self.nom("hermes")
        self.conteneurs.append(nom)
        volume = self.volume()
        for chemin, contenu in (fichiers or {}).items():
            cible = f"/opt/data/{chemin}"
            docker("run", "--rm", "-i", "-v", f"{volume}:/opt/data", "--entrypoint", "sh", image_tests, "-c",
                   f'mkdir -p "$(dirname "{cible}")" && cat > "{cible}"', entree=contenu)
        if fichiers:
            docker("run", "--rm", "-v", f"{volume}:/opt/data", "--entrypoint", "sh", image_tests, "-c",
                   "chown -hR 10000:10000 /opt/data")
        # Étape P3 : context7 (épinglé par la managed scope) résolu vers le bouclage local : aucun appel
        # au vrai serveur pendant les tests.
        docker("run", "-d", "--name", nom, "--network", reseau, "--network-alias", "hermes-interne",
               "--add-host", "mcp.context7.com:127.0.0.1",
               "-v", f"{volume}:/opt/data", *options_env(env or ENV_HERMES), image_tests)
        limite = time.monotonic() + 300
        while time.monotonic() < limite:
            etat = docker("inspect", "-f", "{{.State.Running}}", nom, verifier=False).stdout.strip()
            if etat == "false":
                raise AssertionError(f"Hermes s'est arrêté :\n{journal(nom)[-4000:]}")
            code = docker("exec", nom, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                          "http://127.0.0.1:9119/api/status", verifier=False).stdout.strip()
            if code == "200":
                return nom
            time.sleep(2)
        raise AssertionError(f"tableau de bord de Hermes injoignable :\n{journal(nom)[-4000:]}")


def attendre_identite(nom: str, delai: float = 120) -> None:
    """Attend /api/health (200) ; échoue tout de suite si le conteneur s'arrête."""
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        etat = docker("inspect", "-f", "{{.State.Running}}", nom, verifier=False).stdout.strip()
        if etat == "false":
            raise AssertionError(f"le conteneur identite {nom} s'est arrêté :\n{journal(nom)[-4000:]}")
        sortie = docker("exec", nom, "wget", "-q", "-O", "-", "http://127.0.0.1:9091/api/health",
                        verifier=False)
        if sortie.returncode == 0 and '"OK"' in sortie.stdout:
            return
        time.sleep(1)
    raise AssertionError(f"identite {nom} injoignable après {delai} s :\n{journal(nom)[-4000:]}")


def monter_pile(pile: Pile, image_identite: str, image_tests: str, empreinte: str, *,
                publier: bool = False, fichiers: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    """identite + bord + Hermes sur un réseau jetable ; rend les noms et le port publié."""
    reseau = pile.reseau()
    identite = pile.lancer_identite(image_identite, env_identite(empreinte), reseau=reseau)
    bord, port = pile.lancer_bord(image_tests, reseau, publier=publier)
    hermes = pile.lancer_hermes(image_tests, reseau, fichiers=fichiers)
    return {"reseau": reseau, "identite": identite, "bord": bord, "hermes": hermes, "port": port}


def lignes_du_bord(bord: str) -> List[dict]:
    brut = docker("exec", bord, "cat", JOURNAL_BORD, verifier=False).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def spki_du_bord(image_tests: str) -> str:
    """Empreinte SPKI (base64 du SHA-256) du certificat du bord, pour
    --ignore-certificate-errors-spki-list de Chromium : le navigateur de l'hôte fait alors
    confiance à CE certificat seulement, sans toucher au magasin du système."""
    code = ("import base64, hashlib\n"
            "from cryptography import x509\n"
            "from cryptography.hazmat.primitives import serialization\n"
            "c = x509.load_pem_x509_certificate(open('/opt/acp-tests/ac/bord.pem', 'rb').read())\n"
            "d = c.public_key().public_bytes(serialization.Encoding.DER, "
            "serialization.PublicFormat.SubjectPublicKeyInfo)\n"
            "print(base64.b64encode(hashlib.sha256(d).digest()).decode())\n")
    return docker("run", "--rm", "--entrypoint", "/opt/hermes/.venv/bin/python", image_tests, "-c", code).stdout.strip()
