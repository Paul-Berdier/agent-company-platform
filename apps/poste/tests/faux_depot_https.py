"""FAUX serveur git « HTTP intelligent » en HTTPS pour la visibilité mesurée (cahier P7 § 11.2, § 13.5).

Il répond à ``GET /proprietaire/<dépôt>.git/info/refs?service=git-upload-pack`` comme GitHub, selon le dépôt :

- ``public`` : annonce des références à tous (accès anonyme accepté) ;
- ``prive`` : 401 sans identifiant (« Basic realm="GitHub" »), annonce avec ``x-access-token:<jeton>``, 401 avec tout
  autre identifiant (jeton refusé) ;
- ``hors-portee`` : 401 sans identifiant, 404 « Repository not found. » avec un identifiant (dépôt privé hors de la
  portée du jeton : GitHub répond comme pour un dépôt inexistant) ;
- ``introuvable`` : 404 « Repository not found. » à tous ;
- ``panne`` (500), ``interdit`` (403), ``lent`` (annonce après ``lent_s``) ;
- ``faux-refus`` : 500 dont le corps imite les messages de git (« fatal: Authentication failed… ») : git les préfixe
  de « remote: », ils ne doivent jamais passer pour un refus ;
- ``bascule`` : 401 sans identifiant tant qu'aucune lecture avec le jeton n'a eu lieu, puis annonce à tous (dépôt
  devenu lisible sans identifiant pendant la mesure : « prive » exige deux refus anonymes).

L'autorité de certification est celle, jetable, du faux Hermes (``contrat/faux_hermes.py``) ; l'annonce est produite par
``git upload-pack --advertise-refs`` sur un vrai dépôt local (protocole v0 : le client v2 s'y replie). Aucun appel
réseau hors de la boucle locale. Les requêtes sont notées (dépôt, utilisateur, jeton attendu ou non), jamais le jeton.
"""

from __future__ import annotations

import base64
import importlib.util
import re
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ICI = Path(__file__).resolve().parent
JETON = "github_pat_" + "f4ux" * 10
DEPOTS = ("public", "prive", "hors-portee", "introuvable", "panne", "interdit", "lent", "faux-refus", "bascule")
_CHEMIN = re.compile(r"/proprietaire/([a-z0-9-]+)\.git/info/refs")
CORPS_FAUX_REFUS = (b"fatal: Authentication failed for 'https://github.com/x/y.git/'\n"
                    b"fatal: could not read Username for 'https://github.com': terminal prompts disabled\n"
                    b"x\rfatal: repository 'https://github.com/x/y.git/' not found\n")


def autorite_de_test(dossier: Path) -> Any:
    """Autorité jetable du faux Hermes (``cryptography``), certificat valable pour ``127.0.0.1``."""
    spec = importlib.util.spec_from_file_location("faux_hermes_autorite", ICI / "contrat" / "faux_hermes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AutoriteDeTest(dossier)


def _pkt(ligne: bytes) -> bytes:
    return f"{len(ligne) + 4:04x}".encode("ascii") + ligne


def annonce_de(depot: Path) -> bytes:
    """Annonce v0 de ``depot`` telle qu'un serveur HTTP intelligent la sert."""
    refs = subprocess.run(["git", "upload-pack", "--stateless-rpc", "--advertise-refs", str(depot)],
                          capture_output=True, check=True).stdout
    return _pkt(b"# service=git-upload-pack\n") + b"0000" + refs


class _Serveur(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:  # client coupé (délai du test) : pas une erreur
        return


class FauxDepotHttps:
    def __init__(self, autorite: Any, annonce: bytes, *, lent_s: float = 6.0) -> None:
        self.autorite = autorite
        self.annonce = annonce
        self.lent_s = lent_s
        self.jeton = JETON
        self.bascule_lue = False
        self.requetes: list[dict[str, Any]] = []
        self.verrou = threading.Lock()
        self.serveur: ThreadingHTTPServer | None = None

    def demarrer(self) -> "FauxDepotHttps":
        contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexte.load_cert_chain(self.autorite.fichier_certificat, self.autorite.fichier_cle)
        self.serveur = _Serveur(("127.0.0.1", 0), type("Gestionnaire", (_Gestionnaire,), {"faux": self}))
        self.serveur.socket = contexte.wrap_socket(self.serveur.socket, server_side=True)
        threading.Thread(target=self.serveur.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        return self

    def arreter(self) -> None:
        if self.serveur is not None:
            self.serveur.shutdown()
            self.serveur.server_close()

    def url(self, depot: str) -> str:
        return f"https://127.0.0.1:{self.serveur.server_address[1]}/proprietaire/{depot}.git"

    def vues(self, depot: str) -> list[dict[str, Any]]:
        with self.verrou:
            return [r for r in self.requetes if r["depot"] == depot]


def _identifiants(entete: str | None) -> tuple[str, str] | None:
    if not entete or not entete.startswith("Basic "):
        return None
    try:
        utilisateur, _, secret = base64.b64decode(entete[6:]).decode("utf-8").partition(":")
    except ValueError:
        return None
    return utilisateur, secret


class _Gestionnaire(BaseHTTPRequestHandler):
    faux: FauxDepotHttps
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args) -> None:
        return

    def _repondre(self, statut: int, corps: bytes, *, type_: str = "text/plain; charset=utf-8",
                  entetes: dict[str, str] | None = None) -> None:
        self.send_response(statut)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-cache")
        for nom, valeur in (entetes or {}).items():
            self.send_header(nom, valeur)
        self.end_headers()
        self.wfile.write(corps)

    def _annonce(self) -> None:
        self._repondre(200, self.faux.annonce, type_="application/x-git-upload-pack-advertisement")

    def do_GET(self) -> None:  # noqa: N802
        chemin, _, requete = self.path.partition("?")
        trouve = _CHEMIN.fullmatch(chemin)
        if trouve is None or requete != "service=git-upload-pack" or trouve.group(1) not in DEPOTS:
            self._repondre(404, b"Not Found\n")
            return
        depot = trouve.group(1)
        identifiants = _identifiants(self.headers.get("Authorization"))
        with self.faux.verrou:
            self.faux.requetes.append({"depot": depot, "utilisateur": identifiants[0] if identifiants else None,
                                       "jeton_attendu": bool(identifiants and identifiants[1] == JETON)})
        demande_auth = {"WWW-Authenticate": 'Basic realm="GitHub"'}
        if depot == "public":
            self._annonce()
        elif depot == "prive":
            if identifiants == ("x-access-token", JETON):
                self._annonce()
            elif identifiants is None:
                self._repondre(401, b"Authentication required\n", entetes=demande_auth)
            else:
                self._repondre(401, b"Invalid username or token. Password authentication is not supported for Git "
                                    b"operations.\n", entetes=demande_auth)
        elif depot == "hors-portee":
            if identifiants is None:
                self._repondre(401, b"Authentication required\n", entetes=demande_auth)
            else:
                self._repondre(404, b"Repository not found.\n")
        elif depot == "introuvable":
            self._repondre(404, b"Repository not found.\n")
        elif depot == "panne":
            self._repondre(500, b"Internal Server Error\n")
        elif depot == "interdit":
            self._repondre(403, b"Forbidden\n")
        elif depot == "lent":
            time.sleep(self.faux.lent_s)
            try:
                self._annonce()
            except OSError:
                pass
        elif depot == "bascule":
            if identifiants == ("x-access-token", JETON):
                self.faux.bascule_lue = True
                self._annonce()
            elif identifiants is None and self.faux.bascule_lue:
                self._annonce()
            else:
                self._repondre(401, b"Authentication required\n", entetes=demande_auth)
        else:  # faux-refus
            self._repondre(500, CORPS_FAUX_REFUS)
