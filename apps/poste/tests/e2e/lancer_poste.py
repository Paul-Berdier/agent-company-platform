"""Lanceur du VRAI poste pour le bout en bout local sous Windows (cahier P5 § 14.5) : jamais une installation.

    python -I lancer_poste.py --racine <dossier temporaire> --autorite <ac.pem> [--hote hermes-acp.test] -- <commande>

Il construit le contexte du poste sur une racine JETABLE (équivalents de ``ProgramData``, ``LOCALAPPDATA`` et
``Program Files`` sous ``--racine``), avec le coffre DPAPI RÉEL (compte courant), une autorité de test et la
résolution de l'hôte de test vers ``127.0.0.1`` (paramètres du client HTTPS, absents de ``poste.toml``), puis appelle
``acp_poste.cli.main``. Il REFUSE de démarrer si une des racines tombe hors du dossier temporaire du système : jamais
le vrai ``C:\\ProgramData\\ACP``, ni le coffre, le verrou, le journal ou le profil Codex ou Claude d'une installation.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve()
RACINE_DEPOT = ICI.parents[4]
sys.path[:0] = [str(RACINE_DEPOT / "apps" / "poste" / "src"), str(RACINE_DEPOT / "hermes" / "plugins" / "acp-poste" /
                                                                    "contrat")]

from acp_poste.chemins import Emplacements  # noqa: E402
from acp_poste.cli import main  # noqa: E402
from acp_poste.client_hermes import OptionsClient  # noqa: E402
from acp_poste.coffre import CoffreDPAPI  # noqa: E402
from acp_poste.contexte import Contexte  # noqa: E402


def lancer(argv: list[str]) -> int:
    analyseur = argparse.ArgumentParser(prog="lancer_poste")
    analyseur.add_argument("--racine", required=True, type=Path)
    analyseur.add_argument("--autorite", required=True, type=Path)
    analyseur.add_argument("--hote", default="hermes-acp.test")
    analyseur.add_argument("commande", nargs=argparse.REMAINDER)
    options = analyseur.parse_args(argv)
    commande = options.commande[1:] if options.commande[:1] == ["--"] else options.commande
    emplacements = Emplacements.de_test(options.racine)
    temporaire = Path(tempfile.gettempdir())
    if not emplacements.sous(temporaire) or Path(options.racine).resolve() == temporaire.resolve():
        print("lancer_poste : racine refusée (hors du dossier temporaire du système) : aucune installation réelle ne "
              "doit être touchée.", file=sys.stderr)
        return 2
    contexte = Contexte(emplacements=emplacements, coffre=CoffreDPAPI(emplacements.secrets),
                        options_client=OptionsClient(fichier_autorite=str(options.autorite),
                                                     resolution={options.hote: "127.0.0.1"}))
    return main(commande, contexte=contexte)


if __name__ == "__main__":
    raise SystemExit(lancer(sys.argv[1:]))
