"""Greffon groupé acp-poste, côté agent.

Hermes importe ce paquet dans chacun de ses processus et appelle :func:`register`
(hermes_cli/plugins.py). Depuis l'étape P2, le greffon :

1. arrête Hermes lancé HORS de la chaîne s6 d'ACP (sentinelle, :func:`_sentinelle_chaine_s6`) ;
2. enregistre la garde d'exécution de l'agent, crochet ``pre_tool_call`` en liste blanche
   (:mod:`garde_execution`).

Il n'enregistre encore aucun outil : les outils ``projet_*``, ``poste_*`` et ``question_*``
arrivent en P4, le jeton machine et les routes du poste en P5 (plan d'autonomie,
docs/refonte/autonomie.md § 8) ; les annoncer maintenant ferait croire à une délégation qui
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
# Options globales de `hermes` qui prennent une valeur, sautées avec leur valeur pour trouver la
# sous-commande. Relevées dans l'analyseur réel de Hermes 0.21.5 (hermes_cli/_parser.py:22-26 et
# 129-197 : valeur obligatoire ; « -c/--continue » à valeur facultative, qu'argparse consomme dès
# que le mot suivant n'est pas une option) et « -p/--profile », consommée avant argparse
# (hermes_cli/_parser.py:13-16). test_options_a_valeur_couvrent_l_analyseur_de_hermes compare cette
# liste à hermes_cli._parser.top_level_value_flag_sets() de l'image épinglée.
_OPTIONS_A_VALEUR = frozenset({
    "-p", "--profile", "-z", "--oneshot", "--usage-file", "-m", "--model", "--provider", "--reasoning",
    "-t", "--toolsets", "-r", "--resume", "--in", "-s", "--skills", "-c", "--continue",
})
# Sous-commandes qui lancent le serveur du tableau de bord : « dashboard » et « serve », même
# serveur sans navigateur (hermes_cli/subcommands/dashboard.py:79-101).
_COMMANDES_TABLEAU_DE_BORD = frozenset({"dashboard", "serve"})


def _sous_commande(argv: Sequence[str]) -> List[str]:
    """Sous-commande de ``hermes`` (options globales sautées avec leur valeur, comme
    ``_first_positional_argv`` de hermes_cli/main.py:2825-2845) : ``["gateway", "run"]``,
    ``["gateway"]``, ``["dashboard"]``, ``["chat"]``…"""
    positionnels: List[str] = []
    arguments = list(argv)[1:]
    i = 0
    while i < len(arguments):
        argument = arguments[i]
        if argument == "--":  # tout ce qui suit est positionnel
            positionnels.extend(arguments[i + 1:])
            break
        if argument.startswith("-"):
            # « --option=valeur » est un seul mot ; une option à valeur consomme le mot suivant.
            i += 2 if ("=" not in argument and argument in _OPTIONS_A_VALEUR) else 1
            continue
        positionnels.append(argument)
        i += 1
        if positionnels[0] != "gateway" or len(positionnels) == 2:
            break
    return positionnels[:2] if positionnels[:1] == ["gateway"] else positionnels[:1]


def _home_de_production(home: Optional[str]) -> bool:
    """Vrai si ``home`` désigne le volume de production ou l'un de ses sous-répertoires (un profil
    ``/opt/data/profiles/<nom>`` y compris), après normalisation (``/opt/data/``,
    ``/opt//data``, ``/opt/data/../data``) et résolution des liens."""
    if not home:
        return False
    for forme in (os.path.normpath(home), os.path.realpath(home)):
        if forme == _HOME_DEPLOYE or forme.startswith(_HOME_DEPLOYE + "/"):
            return True
    return False


def _lance_un_serveur(commande: Sequence[str]) -> bool:
    """« gateway » nu ou « gateway run » (hermes_cli/gateway.py:5108-5112 : la sous-commande absente
    lance aussi la passerelle), « dashboard » ou « serve »."""
    if commande[:1] == ["gateway"]:
        return len(commande) == 1 or commande[1] == "run"
    return bool(commande) and commande[0] in _COMMANDES_TABLEAU_DE_BORD


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
    ``hermes gateway [run]``, ``hermes dashboard`` et ``hermes serve`` avec un ``HERMES_HOME``
    dans ``/opt/data`` sont visés : les commandes ponctuelles, les workers kanban et les tests ne
    le sont pas. Défense en profondeur : elle suppose que la commande passe par l'analyse de
    ``sys.argv`` ; ``acp-entree`` reste la garde principale."""
    argv = sys.argv if argv is None else argv
    environ = os.environ if environ is None else environ
    if not _home_de_production(environ.get("HERMES_HOME")):
        return
    commande = _sous_commande(argv)
    if not _lance_un_serveur(commande):
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
