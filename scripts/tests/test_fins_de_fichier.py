"""Hygiène des fichiers suivis (règle du dépôt : ``git diff --check`` propre avant chaque commit).

Relecture indépendante de P4 : deux commits avaient ajouté une ligne vide en fin de fichier
(``apps/interface/src/projets/NouveauProjet.tsx``, ``hermes/tests/image/test_kanban_adapter.py``), que
``git diff --check`` signale (« new blank line at EOF »), alors que la documentation le disait propre. Ce
test le vérifie sur tout l'arbre suivi, sans dépendre d'une plage de commits."""

from __future__ import annotations

import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
BINAIRES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".woff", ".woff2", ".ttf", ".otf", ".zip",
            ".gz", ".exe", ".dll", ".pdf", ".wasm", ".bin"}


def _fichiers_texte_suivis():
    sortie = subprocess.run(["git", "ls-files", "-z"], cwd=RACINE, capture_output=True, check=True).stdout
    for nom in sortie.decode("utf-8").split("\0"):
        chemin = RACINE / nom
        if not nom or chemin.suffix.lower() in BINAIRES or not chemin.is_file():
            continue
        contenu = chemin.read_bytes()
        if b"\0" in contenu[:8192]:
            continue
        yield nom, contenu


def test_aucun_fichier_suivi_ne_finit_par_une_ligne_vide():
    fautifs = [nom for nom, contenu in _fichiers_texte_suivis()
               if contenu.endswith(b"\n\n") or contenu.endswith(b"\r\n\r\n")]
    assert fautifs == [], "ligne vide en fin de fichier (git diff --check : new blank line at EOF) : " + ", ".join(fautifs)
