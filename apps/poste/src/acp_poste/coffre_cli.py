"""Entrée autonome des notes facultatives, sans worker ni moteur local."""
from __future__ import annotations

import argparse
import sys
from types import SimpleNamespace

from . import __version__
from .chemins import EmplacementsIndisponibles, emplacements_du_compte
from .client_hermes import OptionsClient
from .coffre import CoffreDPAPI, CoffreErreur
from .obsidian_bridge import ajouter_commandes, executer_cli


class Parseur(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "Commande du coffre refusée. Consultez --help pour les options disponibles.\n")


def main(argv=None, *, contexte=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = Parseur(prog="acp-coffre", description="Copie locale facultative des notes ACP ; aucun moteur d’agent.")
    parser.add_argument("--version", action="version", version=f"acp-coffre {__version__}")
    ajouter_commandes(parser.add_subparsers(dest="commande", required=True))
    args = parser.parse_args(argv)
    if contexte is None:
        if sys.platform != "win32":
            print("Le coffre local nécessite Windows et la protection DPAPI du compte propriétaire.", file=sys.stderr)
            return 2
        try:
            emplacements = emplacements_du_compte()
            contexte = SimpleNamespace(
                plateforme="windows", emplacements=emplacements,
                coffre=CoffreDPAPI(emplacements.secrets), options_client=OptionsClient())
        except (EmplacementsIndisponibles, CoffreErreur, OSError):
            print("Les dossiers ou la protection du compte Windows sont indisponibles.", file=sys.stderr)
            return 2
    return executer_cli(args, contexte)


if __name__ == "__main__":
    raise SystemExit(main())
