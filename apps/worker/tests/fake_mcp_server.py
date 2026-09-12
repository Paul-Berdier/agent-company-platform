"""Serveur MCP stdio déterministe utilisé par les tests de la sonde du worker.

Ce programme n'est jamais lancé par le code de production : il est invoqué par
``apps/worker/tests/test_mcp_probe.py`` via ``sys.executable -I`` afin d'observer
la sonde face à un vrai processus. Il n'utilise que la bibliothèque standard
(``-I`` retire le dossier du script de ``sys.path``) et ne fait aucun accès
réseau.

Modes (premier argument) :

``ok``
    Poignée de main complète puis un seul lot d'outils. ``serverInfo`` contient
    ``environmentNames``, la liste triée des variables d'environnement visibles :
    c'est la preuve que la sonde n'a transmis qu'un environnement minimal.
``paged``
    ``tools/list`` répond en deux pages reliées par ``nextCursor``.
``garbage``
    Écrit une ligne qui n'est pas du JSON avant toute réponse.
``empty-initialize``
    Répond à ``initialize`` avec un ``result`` vide. La spécification MCP
    2025-06-18 impose ``protocolVersion`` et ``serverInfo`` : c'est une réponse
    mal formée, jamais un succès.
``no-protocol-version``
    ``initialize`` sans ``protocolVersion``.
``no-server-info``
    ``initialize`` sans ``serverInfo``.
``echo-env``
    Serveur bavard : renvoie la **valeur** de la variable d'environnement
    nommée en second argument sur stderr, dans ``serverInfo`` et dans la
    description d'un outil. Sert à prouver que la sonde expurge les valeurs
    injectées avant de les retourner à l'API.
``noisy``
    Comme ``ok``, mais écrit d'abord un long flux sur stderr.
``hang``
    Écrit son PID dans le fichier passé en second argument, lit stdin et ne
    répond jamais.
``witness``
    Écrit un témoin dans le fichier passé en second argument puis sort. Sert à
    prouver qu'un exécutable non autorisé n'est jamais lancé.
"""

import json
import os
import sys
import time
from pathlib import Path


PROTOCOL_VERSION = "2025-06-18"
NOISY_STDERR_CHARS = 6000


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _tool(index: int, *, description: str | None = None) -> dict:
    return {
        "name": f"outil-{index}",
        "description": description if description is not None else f"Outil {index}",
        "inputSchema": {
            "type": "object",
            "properties": {"chemin": {"type": "string"}},
            "required": ["chemin"],
        },
    }


def _initialize_result(mode: str, target: str | None) -> dict:
    if mode == "empty-initialize":
        return {}
    server_info: dict = {
        "name": "faux-serveur-mcp",
        "version": "1.0.0",
        "environmentNames": sorted(os.environ),
    }
    if mode == "echo-env" and target:
        server_info["echoedEnvironment"] = {target: os.environ.get(target, "")}
    result: dict = {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": server_info,
    }
    if mode == "no-protocol-version":
        result.pop("protocolVersion")
    if mode == "no-server-info":
        result.pop("serverInfo")
    return result


def _tools_page(mode: str, cursor: str | None, target: str | None = None) -> dict:
    if mode == "echo-env" and target:
        return {
            "tools": [
                _tool(
                    1,
                    description=(
                        "jeton utilisé : " + os.environ.get(target, "")
                    ),
                )
            ]
        }
    if mode == "endless":
        # Ne termine jamais la pagination : la sonde doit refuser plutôt que de
        # présenter une liste tronquée comme complète.
        index = 1 if cursor is None else int(cursor) + 1
        return {"tools": [_tool(index)], "nextCursor": str(index)}
    if mode != "paged":
        return {"tools": [_tool(1), _tool(2, description="é" * 4000)]}
    if cursor is None:
        return {"tools": [_tool(1)], "nextCursor": "page-2"}
    if cursor == "page-2":
        return {"tools": [_tool(2)], "nextCursor": "page-3"}
    return {"tools": [_tool(3)]}


def _serve(mode: str, target: str | None = None) -> int:
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        method = message.get("method")
        identifier = message.get("id")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            _emit(
                {
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "result": _initialize_result(mode, target),
                }
            )
            continue
        if method == "tools/list":
            params = message.get("params") or {}
            cursor = params.get("cursor") if isinstance(params, dict) else None
            _emit(
                {
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "result": _tools_page(mode, cursor, target),
                }
            )
            continue
        _emit(
            {
                "jsonrpc": "2.0",
                "id": identifier,
                "error": {"code": -32601, "message": f"méthode inconnue: {method}"},
            }
        )
    return 0


def main(argv: list[str]) -> int:
    # Le protocole MCP impose UTF-8 sur stdio ; la locale Windows ne l'est pas.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", newline="\n")
    mode = argv[0] if argv else "ok"
    target = Path(argv[1]) if len(argv) > 1 else None
    if mode == "witness":
        if target is not None:
            target.write_text("lancé", encoding="utf-8")
        return 0
    if mode == "hang":
        if target is not None:
            target.write_text(str(os.getpid()), encoding="ascii")
        for _ in sys.stdin:
            pass
        while True:
            time.sleep(1)
    if mode == "garbage":
        sys.stdout.write("ceci n'est pas du JSON\n")
        sys.stdout.flush()
        for _ in sys.stdin:
            pass
        return 0
    echoed = str(target) if target is not None else None
    if mode == "noisy":
        sys.stderr.write("é" * NOISY_STDERR_CHARS + "\n")
        sys.stderr.flush()
    elif mode == "echo-env" and echoed:
        value = os.environ.get(echoed, "")
        sys.stderr.write("connexion établie avec le jeton " + value + "\n")
        sys.stderr.flush()
    else:
        sys.stderr.write("faux serveur prêt\n")
        sys.stderr.flush()
    return _serve(mode, echoed)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
