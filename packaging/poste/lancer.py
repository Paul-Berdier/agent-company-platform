"""Lanceur installé du poste Windows d'ACP (étape P5, décision D53 : installation SANS venv).

Copié par ``Installer-PosteAcp.ps1`` sous ``C:\\Program Files\\ACP\\poste\\lancer.py`` et lancé par l'interpréteur
python.org « tous utilisateurs » en mode isolé : ``"<python.exe>" -I lancer.py <commande>``. ``-I`` retire
``PYTHONPATH``, le site utilisateur et le dossier courant de ``sys.path`` : seul ``lib`` (à côté de ce fichier,
non modifiable par le compte du poste) s'y ajoute. Aucun lanceur de venv ne s'interpose entre la tâche planifiée et
l'interpréteur réel (celui d'un venv laisse vivre l'interpréteur hors du Job Object).
"""

import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))

from acp_poste.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
