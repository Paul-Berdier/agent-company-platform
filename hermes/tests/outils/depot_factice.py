"""Dépôt git distant FACTICE, pour les tests seulement (étape P6) : jamais GitHub, jamais déployé.

Crée un dépôt nu ``<racine>/proprietaire/jetable.git`` (une petite arborescence Python, branche ``main``), puis le
sert en HTTPS par le protocole git « bête » (fichiers statiques après ``git update-server-info``) : ``git clone`` et
``git fetch``
fonctionnent, **aucune écriture n'est possible** (seuls GET et HEAD sont servis ; toute autre méthode rend 405 et est
consignée). Chaque requête est journalisée (méthode, chemin sans la requête, statut) en JSONL : le bout en bout prouve
ainsi qu'aucun push n'a été tenté et que les références distantes sont inchangées.

Usage : python depot_factice.py --port 443 --certificat depot.pem --cle depot.key --racine /tmp/depots \\
            --journal /tmp/depot.jsonl
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import ssl
import subprocess
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FICHIERS = {
    "README.md": "# Dépôt jetable\n\nDépôt de preuve du bout en bout de l'exécutant (factice).\n",
    "src/app.py": "def bonjour() -> str:\n    return 'bonjour'\n",
    "tests/test_app.py": "from src.app import bonjour\n\n\ndef test_bonjour():\n    assert bonjour() == 'bonjour'\n",
}
_VERROU = threading.Lock()


def creer_depot(racine: Path) -> Path:
    nu = racine / "proprietaire" / "jetable.git"
    if nu.exists():
        return nu
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME=str(racine), GIT_AUTHOR_NAME="Propriétaire",
               GIT_AUTHOR_EMAIL="proprietaire@acp.invalid", GIT_COMMITTER_NAME="Propriétaire",
               GIT_COMMITTER_EMAIL="proprietaire@acp.invalid")
    with tempfile.TemporaryDirectory() as dossier:
        travail = Path(dossier) / "travail"
        subprocess.run(["git", "init", "-q", "-b", "main", str(travail)], check=True, env=env)
        for chemin, contenu in FICHIERS.items():
            fichier = travail / chemin
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_text(contenu, encoding="utf-8")
        subprocess.run(["git", "-C", str(travail), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(travail), "commit", "-q", "-m", "initial"], check=True, env=env)
        nu.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--bare", str(travail), str(nu)], check=True, env=env)
    subprocess.run(["git", "--git-dir", str(nu), "update-server-info"], check=True, env=env)
    return nu


class Gestionnaire(SimpleHTTPRequestHandler):
    journal: Path

    def _consigner(self, statut: int) -> None:
        entree = {"methode": self.command, "chemin": self.path.split("?", 1)[0], "statut": statut}
        with _VERROU, open(self.journal, "a", encoding="utf-8") as flux:
            flux.write(json.dumps(entree, ensure_ascii=False) + "\n")

    def send_response(self, code, message=None):  # noqa: D401 — consigne chaque réponse
        self._consigner(code)
        super().send_response(code, message)

    def _refuser(self) -> None:
        self.send_error(405, "Dépôt factice en lecture seule")

    do_POST = do_PUT = do_DELETE = do_PATCH = _refuser

    def log_message(self, format, *args):  # noqa: A002
        return


def main() -> int:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--port", type=int, default=443)
    analyseur.add_argument("--certificat", required=True)
    analyseur.add_argument("--cle", required=True)
    analyseur.add_argument("--racine", required=True, type=Path)
    analyseur.add_argument("--journal", required=True, type=Path)
    options = analyseur.parse_args()
    creer_depot(options.racine)
    Gestionnaire.journal = options.journal
    serveur = ThreadingHTTPServer(("0.0.0.0", options.port),
                                  functools.partial(Gestionnaire, directory=str(options.racine)))
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexte.minimum_version = ssl.TLSVersion.TLSv1_2
    contexte.load_cert_chain(options.certificat, options.cle)
    serveur.socket = contexte.wrap_socket(serveur.socket, server_side=True)
    print(f"[depot-factice] port {options.port}, dépôt {options.racine / 'proprietaire' / 'jetable.git'}", flush=True)
    serveur.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
