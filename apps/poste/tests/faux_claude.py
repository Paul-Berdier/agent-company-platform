"""FAUX Claude Code (``--version`` et ``auth status``) piloté par un scénario JSON, pour les tests du poste (étape P5).

Jamais lancé par le code de production (lanceur injecté par les tests). Invocation :
``python -I faux_claude.py <scenario.json> (--version | auth status)``.

Clés du scénario : ``version`` (sortie de ``--version``), ``code_auth`` (code de sortie d'``auth status``),
``auth_bloque`` (ne se termine jamais), ``enregistrer`` (fichier : argv, noms des variables reçues, présence et
empreinte de ``CLAUDE_CODE_OAUTH_TOKEN``). ``auth status`` écrit toujours une adresse électronique sur sa sortie :
le poste doit la jeter sans la lire.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time


def main(argv: list[str]) -> int:
    with open(argv[1], encoding="utf-8") as flux:
        scenario = json.load(flux)
    arguments = argv[2:]
    jeton = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if scenario.get("enregistrer"):
        with open(scenario["enregistrer"], "a", encoding="utf-8") as flux:
            flux.write(json.dumps({
                "argv": arguments, "noms": sorted(os.environ),
                "jeton": hashlib.sha256(jeton.encode("utf-8")).hexdigest()[:12] if jeton else None,
                "config_dir": os.environ.get("CLAUDE_CONFIG_DIR"),
                "disable_updates": os.environ.get("DISABLE_UPDATES"),
            }, ensure_ascii=False) + "\n")
    if arguments == ["--version"]:
        print(scenario.get("version", "2.1.280 (Claude Code)"))
        return 0
    if arguments == ["auth", "status"]:
        print(json.dumps({"loggedIn": True, "email": "titulaire@example.com"}))
        print("secret-de-sortie-jamais-lu", file=sys.stderr)
        sys.stdout.flush()
        if scenario.get("auth_bloque"):
            while True:
                time.sleep(1)
        return int(scenario.get("code_auth", 0))
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
