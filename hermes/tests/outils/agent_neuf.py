"""Tour d'agent de TEST dans un processus NEUF, sans aucun appel manuel à discover_plugins.

Construit un ``AIAgent`` comme le fait une surface réelle de Hermes, puis lance un tour sur
le modèle factice (``OUTIL:<nom>`` dans le message fait demander l'outil) :

- ``cache`` : l'agent caché de preview.restart, jeux ``["terminal", "file"]`` codés en dur,
  sans base de sessions ni mémoire (tui_gateway/agent_callbacks.py:371-374) ;
- ``api_server`` : jeux de _get_platform_tools(cfg, "api_server"), sans disabled_toolsets
  (gateway/platforms/api_server.py:2231-2270).

C'est l'AIAgent qui découvre lui-même les greffons (agent/agent_init.py:1060-1065) : si la
garde d'acp-poste n'est pas chargée par ce chemin, l'outil s'exécute.

Usage : python agent_neuf.py <cache|api_server> <url du modèle factice> "<message>" <fichier de sortie>
Sortie : {"reponse": …, "outils_offerts": […]} en JSON dans le fichier de sortie (Hermes détourne
sys.stdout vers la sortie d'erreur à l'import de certains modules).
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    mode, url, message, fichier_sortie = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    from hermes_cli.env_loader import load_hermes_dotenv

    load_hermes_dotenv(hermes_home=os.environ["HERMES_HOME"], load_external_secrets=False)
    if mode == "cache":
        jeux = ["terminal", "file"]
        plateforme = "tui"
    elif mode == "api_server":
        from hermes_cli.config import load_config
        from hermes_cli.tools_config import _get_platform_tools

        jeux = sorted(_get_platform_tools(load_config(), "api_server"))
        plateforme = "api_server"
    else:
        print(f"mode inconnu : {mode}", file=sys.stderr)
        return 2
    from run_agent import AIAgent

    agent = AIAgent(model="acp-factice", base_url=url, api_key="factice", provider="custom",
                    enabled_toolsets=jeux, quiet_mode=True, verbose_logging=False, max_iterations=6,
                    platform=plateforme, session_db=None, skip_memory=True, session_id=f"acp-test-{mode}")
    resultat = agent.run_conversation(user_message=message, task_id=f"acp-test-{mode}")
    offerts = sorted({d["function"]["name"] for d in (agent.tools or []) if isinstance(d, dict) and "function" in d})
    with open(fichier_sortie, "w", encoding="utf-8") as flux:
        json.dump({"reponse": (resultat or {}).get("final_response"), "outils_offerts": offerts}, flux,
                  ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
