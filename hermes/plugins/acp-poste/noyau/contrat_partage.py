"""Met le contrat partagé avec le poste (``hermes/plugins/acp-poste/contrat``, décision D21) sur ``sys.path`` :
dans l'image, il est importé par son chemin, rien n'est installé dans l'environnement de Hermes. Chaque module du
noyau qui importe ``acp_poste_contrat`` importe d'abord celui-ci."""

from __future__ import annotations

import sys
from pathlib import Path

CHEMIN = Path(__file__).resolve().parent.parent / "contrat"
if CHEMIN.is_dir() and str(CHEMIN) not in sys.path:
    sys.path.insert(0, str(CHEMIN))
