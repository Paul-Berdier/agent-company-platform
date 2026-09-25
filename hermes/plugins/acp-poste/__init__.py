"""Greffon groupé acp-poste, côté agent.

Hermes importe ce paquet dans chacun de ses processus et appelle :func:`register`
(hermes_cli/plugins.py). Depuis l'étape P2, le greffon :

1. arrête Hermes lancé HORS de la chaîne s6 d'ACP (sentinelle, :func:`_sentinelle_chaine_s6`) ;
2. enregistre la garde d'exécution de l'agent, crochet ``pre_tool_call`` en liste blanche
   (:mod:`garde_execution`).

Il n'enregistre encore ni outil ``poste_*``, ni fournisseur de jeton machine, ni route à
jeton : ils arrivent en P5 ; les annoncer maintenant ferait croire à une délégation qui
n'existe pas.

La partie tableau de bord (``dashboard/plugin_api.py``) est montée indépendamment, sous
``/api/plugins/acp-poste/`` (hermes_cli/web_server_dashboard.py:798-874).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import List, Optional, Sequence

from . import garde_execution

_log = logging.getLogger(__name__)

CODE_HORS_S6 = 78
_HOME_DEPLOYE = "/opt/data"
# Options globales de `hermes` qui prennent une valeur (hermes_cli/main.py) : sautées pour
# trouver la sous-commande.
_OPTIONS_A_VALEUR = {"-p", "--profile", "-m", "--model", "--provider", "-t", "--toolsets", "--skills"}


def _sous_commande(argv: Sequence[str]) -> List[str]:
    """Sous-commande de ``hermes`` (options globales sautées) : ``["gateway", "run"]``,
    ``["dashboard"]``, ``["chat"]``…"""
    positionnels: List[str] = []
    attend_valeur = False
    for argument in list(argv)[1:]:
        if attend_valeur:
            attend_valeur = False
            continue
        if argument in _OPTIONS_A_VALEUR:
            attend_valeur = True
            continue
        if argument.startswith("-"):
            continue
        positionnels.append(argument)
        if positionnels[0] != "gateway" or len(positionnels) == 2:
            break
    return positionnels


def _programme_pid1(cmdline: str = "/proc/1/cmdline") -> Optional[str]:
    """Nom (basename) du premier champ de /proc/1/cmdline ; None s'il est illisible."""
    try:
        with open(cmdline, "rb") as flux:
            brut = flux.read(4096)
    except OSError:
        return None
    premier = brut.split(b"\0", 1)[0].decode("utf-8", errors="replace")
    return os.path.basename(premier) or None


def _sentinelle_chaine_s6(argv: Optional[Sequence[str]] = None, environ: Optional[dict] = None,
                          cmdline: str = "/proc/1/cmdline") -> None:
    """Arrête (code 78) une passerelle ou un tableau de bord de PRODUCTION lancé hors de s6.

    Hors de s6 (``docker run --entrypoint …``, ``--init``, Start Command), ni le crochet
    acp-gardes, ni 05-acp, ni la managed scope régénérée et vérifiée ne s'appliquent. Seuls
    ``hermes gateway run`` et ``hermes dashboard`` avec ``HERMES_HOME=/opt/data`` sont visés :
    les commandes ponctuelles, les workers kanban et les tests ne le sont pas."""
    argv = sys.argv if argv is None else argv
    environ = os.environ if environ is None else environ
    if environ.get("HERMES_HOME") != _HOME_DEPLOYE:
        return
    commande = _sous_commande(argv)
    if commande[:2] != ["gateway", "run"] and commande[:1] != ["dashboard"]:
        return
    programme = _programme_pid1(cmdline)
    if programme == "s6-svscan":
        return
    print(
        f"[acp] REFUS : « hermes {' '.join(commande)} » a été lancé hors de la chaîne s6 d'ACP "
        f"(PID 1 : {programme or 'illisible'}) : ni les gardes de démarrage ni la managed scope "
        "vérifiée ne s'appliqueraient. Arrêt (code 78). Démarrez l'image par son ENTRYPOINT, sans "
        "--init ni commande de démarrage personnalisée.",
        file=sys.stderr, flush=True)
    os._exit(CODE_HORS_S6)


def register(ctx) -> None:
    """Point d'entrée du greffon : sentinelle hors s6, puis garde d'exécution."""
    _sentinelle_chaine_s6()
    ctx.register_hook("pre_tool_call", garde_execution.garde)
    garde_execution.ENREGISTRE_DANS_CE_PROCESSUS = True
    _log.debug("acp-poste : garde d'exécution enregistrée (%d outils admis).", len(garde_execution.OUTILS_ADMIS))
