"""CLI locale du poste : diagnostic et relevé des quotas.

Refonte « Hermes au centre » : l'enrôlement auprès de l'API ACP et la boucle de
claims ont disparu avec cette API. La réclamation des travaux sur Hermes (voie
kanban du tableau ``poste``) arrive en P5 : aucune commande ne la simule ici.
Aucune commande ``journal`` non plus : aucun composant du poste n'écrit encore de
journal ; la lecture reviendra en P5 avec un écrivain réel.
Aucune commande n'ouvre de connexion réseau.
"""

import argparse
import asyncio
import json
import sys

from .config import PosteConfig, PosteConfigurationError
from .local_runner import RunnerConfigurationError
from .subscription_quotas import SubscriptionQuotaConfigurationError, collect_reports

EPILOGUE = (
    "La délégation de travaux par Hermes (réclamation, battements, résultats) "
    "arrive en P5 ; voir docs/refonte/plan.md."
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acp-poste", epilog=EPILOGUE)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "diagnostic",
        help="Afficher la configuration locale reconnue (sans chemin ni secret)",
    )
    commands.add_parser(
        "quotas",
        help="Relever maintenant les quotas Codex et Claude Code de ce poste",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = PosteConfig.from_env()
    except (PosteConfigurationError, RunnerConfigurationError) as exc:
        print(f"Configuration du poste refusée : {exc}", file=sys.stderr)
        return 2
    if args.command == "diagnostic":
        print(json.dumps(config.diagnostic(), ensure_ascii=False, indent=2))
        return 0
    try:
        reports = asyncio.run(collect_reports(config.subscription_quotas))
    except SubscriptionQuotaConfigurationError as exc:
        print(f"Relevé des quotas refusé : {exc}.", file=sys.stderr)
        return 2
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
