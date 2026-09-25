"""Sonde de TEST : outils que chaque surface de Hermes offrirait à l'agent, calculés par le code
de Hermes lui-même (version épinglée), dans un processus neuf.

L'appelant fixe HERMES_HOME (volume jetable) et, en test, HERMES_MANAGED_DIR (managed scope
jetable). La sonde charge les .env comme Hermes (load_hermes_dotenv : volume puis managed
scope), puis, pour chaque surface, reprend exactement la résolution de la surface :

- api_server : _get_platform_tools(cfg, "api_server"), SANS disabled_toolsets
  (gateway/platforms/api_server.py:2231-2270) ;
- cli (CLI, ``hermes -z``) : _get_platform_tools(cfg, "cli") et agent.disabled_toolsets ;
- cron : _get_platform_tools(cfg, "cron") et _resolve_cron_disabled_toolsets ;
- tableau de bord (discussion et /api/ws) : tui_gateway.server._load_enabled_toolsets, SANS
  disabled_toolsets (tui_gateway/server.py:2451-2468), pour les sources « tui » et « desktop » ;
- worker kanban : _resolve_worker_cli_toolsets, agent.disabled_toolsets, HERMES_KANBAN_TASK ;
- enfant de délégation : _resolve_child_toolsets d'un parent « cli », qui demande terminal,
  fichiers et code.

Sortie : un objet JSON {surface: {"toolsets": [...], "outils": [...], "mcp": [...]}} écrit dans le
fichier donné en argument (Hermes détourne sys.stdout vers la sortie d'erreur à l'import de certains
modules).

Étape P3 : avec ``--mcp``, la sonde découvre d'abord les serveurs MCP configurés
(discover_mcp_tools, comme la passerelle au démarrage) ; ``mcp`` donne, par surface, les outils MCP
que ses jeux résolvent (Hermes les DIFFÈRE : l'agent les trouve par tool_search et les appelle par
le pont tool_call), et ``_processus`` les processus enfants de la sonde après la découverte (un
serveur stdio en serait un).

Usage : python sonde_surfaces.py <fichier de sortie> [--mcp]
"""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace


def main() -> int:
    home = os.environ["HERMES_HOME"]
    from hermes_cli.env_loader import load_hermes_dotenv

    load_hermes_dotenv(hermes_home=home, load_external_secrets=False)

    from agent.skill_utils import parse_config_string_list
    from hermes_cli.config import load_config
    from hermes_cli.tools_config import _get_platform_tools
    import model_tools

    decouverts = None
    if "--mcp" in sys.argv[2:]:
        from tools.mcp_tool_discovery import discover_mcp_tools

        decouverts = sorted(discover_mcp_tools())

    cfg = load_config()
    desactives = [n.strip() for n in parse_config_string_list((cfg.get("agent") or {}).get("disabled_toolsets"))
                  if str(n).strip()]

    from toolsets import resolve_toolset

    def outils(actives, retires):
        definitions = model_tools.get_tool_definitions(
            enabled_toolsets=list(actives) if actives is not None else None,
            disabled_toolsets=list(retires) if retires else None, quiet_mode=True)
        return sorted({d["function"]["name"] for d in definitions if isinstance(d, dict) and "function" in d})

    def mcp(actives):
        return sorted({o for jeu in (actives or []) for o in resolve_toolset(jeu) if o.startswith("mcp__")})

    resultat = {}
    api = sorted(_get_platform_tools(cfg, "api_server"))
    resultat["api_server"] = {"toolsets": api, "outils": outils(api, None)}
    cli = sorted(_get_platform_tools(cfg, "cli"))
    resultat["cli"] = {"toolsets": cli, "outils": outils(cli, desactives)}

    from cron.scheduler import _resolve_cron_disabled_toolsets

    cron = sorted(_get_platform_tools(cfg, "cron"))
    resultat["cron"] = {"toolsets": cron, "outils": outils(cron, _resolve_cron_disabled_toolsets(cfg))}

    from tui_gateway.server import _load_enabled_toolsets

    for source in ("tui", "desktop"):
        choisis = _load_enabled_toolsets(source)
        resultat[f"tableau_de_bord_{source}"] = {
            "toolsets": sorted(choisis) if choisis is not None else None, "outils": outils(choisis, None)}

    from hermes_cli.kanban_db_dispatch import _resolve_worker_cli_toolsets

    os.environ["HERMES_KANBAN_TASK"] = "t_sonde"
    worker = _resolve_worker_cli_toolsets(home)
    resultat["worker_kanban"] = {"toolsets": worker, "outils": outils(worker, desactives)}
    os.environ.pop("HERMES_KANBAN_TASK", None)

    from tools.delegate_tool_toolsets import _resolve_child_toolsets

    parent = SimpleNamespace(enabled_toolsets=cli, disabled_toolsets=desactives)
    enfant, enfant_retires = _resolve_child_toolsets(parent, ["terminal", "file", "code_execution", "web"], "leaf")
    resultat["enfant_delegation"] = {"toolsets": enfant, "outils": outils(enfant, enfant_retires)}

    for surface in resultat.values():
        surface["mcp"] = mcp(surface["toolsets"])
    if decouverts is not None:
        from agent_neuf import processus_enfants

        resultat["_decouverte"] = {"outils": decouverts, "processus": processus_enfants()}

    with open(sys.argv[1], "w", encoding="utf-8") as flux:
        json.dump(resultat, flux, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
