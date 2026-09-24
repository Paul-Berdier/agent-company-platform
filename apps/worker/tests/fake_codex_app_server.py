"""Faux « codex app-server » déterministe pour les tests de la sonde des quotas.

Ce programme n'est jamais lancé par le code de production : les tests
(``apps/worker/tests/test_subscription_quotas.py``) le désignent comme commande
Codex via ``sys.executable -I``. Il n'utilise que la bibliothèque standard et ne
fait aucun accès réseau. Ses réponses reprennent la forme publiée par Codex CLI
0.156.1 ; le test de contrat les valide contre les schémas copiés dans
``fixtures/codex_app_server_0_156_1``.

Invocation : ``python -I fake_codex_app_server.py <mode> [<fichier>] <action>``,
``<action>`` valant ``--version`` ou ``app-server`` (ce que la sonde ajoute).

Modes :

``ok``
    Compte ChatGPT ``prolite`` et deux compteurs dans ``rateLimitsByLimitId`` :
    ``codex`` (limite non atteinte) et ``codex_other`` (limite atteinte).
``single``
    ``rateLimitsByLimitId`` nul : seule la vue historique ``rateLimits`` existe.
``legacy``
    Compteur sans ``rateLimitReachedType`` ni fenêtre secondaire, durée inconnue.
``notifications``
    Comme ``ok``, avec des notifications et une réponse étrangère intercalées.
``not-signed-in`` / ``api-key``
    ``account/read`` sans compte, ou avec un compte par clé d'API.
``old`` / ``garbled-version`` / ``version-hang``
    ``--version`` trop ancien, illisible, ou qui ne se termine jamais.
``malformed`` / ``out-of-range``
    ``usedPercent`` non numérique, ou numérique mais au-delà de 100.
``rpc-error``
    ``account/rateLimits/read`` répond par une erreur JSON-RPC.
``garbage`` / ``crash``
    Ligne non JSON au lieu de la réponse, ou arrêt avant la réponse.
``hang``
    Écrit son PID dans ``<fichier>`` puis ne répond plus jamais.
``env``
    Écrit dans ``<fichier>`` les noms des variables d'environnement reçues et la
    valeur de ``CODEX_HOME``, puis se comporte comme ``ok``.
``record``
    Ajoute chaque message reçu (une ligne JSON) à ``<fichier>``, puis comme ``ok``.
"""

from __future__ import annotations

import json
import os
import sys
import time

VERSION = "codex-cli 0.156.1"
PLAN = "prolite"
EMAIL = "titulaire@example.com"
PRIMARY_RESETS_AT = 1_790_000_000
SECONDARY_RESETS_AT = 1_790_500_000


def initialize_result() -> dict:
    return {
        "codexHome": os.environ.get("CODEX_HOME", os.path.abspath("codex-home")),
        "platformFamily": "windows" if os.name == "nt" else "unix",
        "platformOs": "windows" if os.name == "nt" else "linux",
        "userAgent": "fake_codex_app_server/0.156.1",
    }


def account_result(mode: str) -> dict:
    if mode == "not-signed-in":
        return {"account": None, "requiresOpenaiAuth": True}
    if mode == "api-key":
        return {"account": {"type": "apiKey"}, "requiresOpenaiAuth": True}
    return {
        "account": {"type": "chatgpt", "email": EMAIL, "planType": PLAN},
        "requiresOpenaiAuth": True,
    }


def _window(used, minutes, resets_at) -> dict:
    return {"usedPercent": used, "windowDurationMins": minutes, "resetsAt": resets_at}


def snapshot(
    limit_id: str,
    name: str,
    primary_used,
    secondary_used,
    *,
    reached: str | None = None,
) -> dict:
    return {
        "limitId": limit_id,
        "limitName": name,
        "primary": _window(primary_used, 300, PRIMARY_RESETS_AT),
        "secondary": _window(secondary_used, 10080, SECONDARY_RESETS_AT),
        "credits": {"hasCredits": False, "unlimited": False, "balance": None},
        "planType": PLAN,
        "normalModelSlug": None,
        "individualLimit": None,
        "spendControlReached": None,
        "rateLimitReachedType": reached,
    }


def rate_limits_result(mode: str) -> dict:
    codex = snapshot("codex", "Codex", 42, 7)
    if mode == "single":
        return {"rateLimits": codex, "rateLimitsByLimitId": None}
    if mode == "legacy":
        legacy = {
            "limitId": "codex",
            "primary": _window(12, None, None),
            "secondary": None,
            "planType": PLAN,
        }
        return {"rateLimits": legacy}
    if mode == "malformed":
        broken = snapshot("codex", "Codex", 42, 7)
        broken["primary"]["usedPercent"] = "beaucoup"
        return {"rateLimits": broken, "rateLimitsByLimitId": {"codex": broken}}
    if mode == "out-of-range":
        beyond = snapshot("codex", "Codex", 140, 7)
        return {"rateLimits": beyond, "rateLimitsByLimitId": {"codex": beyond}}
    reached = snapshot("codex_other", "GPT-6 Astra", 100, 55, reached="rate_limit_reached")
    return {
        "rateLimits": codex,
        "rateLimitsByLimitId": {"codex": codex, "codex_other": reached},
        "accountId": "compte-fictif",
        "ordinaryUsageAllowed": True,
        "rateLimitResetCredits": {"availableCount": 0, "credits": None},
    }


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _respond(identifier, result: dict) -> None:
    _emit({"id": identifier, "result": result})


def _hang_forever() -> None:
    while True:
        time.sleep(1)


def _version(mode: str) -> int:
    if mode == "version-hang":
        _hang_forever()
    if mode == "old":
        print("codex-cli 0.99.0")
    elif mode == "garbled-version":
        print("codex-cli version inconnue")
    else:
        print(VERSION)
    return 0


def _serve(mode: str, target: str | None) -> int:
    if mode == "hang":
        with open(target, "w", encoding="ascii") as stream:
            stream.write(str(os.getpid()))
        _hang_forever()
    if mode == "env":
        with open(target, "w", encoding="utf-8") as stream:
            json.dump(
                {"names": sorted(os.environ), "codex_home": os.environ.get("CODEX_HOME")},
                stream,
            )
    for line in sys.stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        if mode == "record":
            with open(target, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(message, ensure_ascii=False) + "\n")
        method = message.get("method")
        identifier = message.get("id")
        if method == "initialize":
            _respond(identifier, initialize_result())
        elif method == "initialized":
            continue
        elif method == "account/read":
            if mode == "notifications":
                _emit({"method": "account/rateLimits/updated", "params": {"rateLimits": {}}})
                _emit({"id": 999, "result": {"étranger": True}})
                _emit({"id": identifier, "method": "item/tool/requestUserInput", "params": {}})
            _respond(identifier, account_result(mode))
        elif method == "account/rateLimits/read":
            if mode == "rpc-error":
                _emit({"id": identifier, "error": {"code": -32600, "message": f"refusé pour {EMAIL}"}})
            elif mode == "garbage":
                sys.stdout.write("ceci n'est pas du JSON\n")
                sys.stdout.flush()
            elif mode == "crash":
                return 3
            else:
                _respond(identifier, rate_limits_result(mode))
        elif identifier is not None:
            _emit({"id": identifier, "error": {"code": -32601, "message": "méthode inconnue"}})
    return 0


def main(argv: list[str]) -> int:
    # Le vrai CLI parle UTF-8 sur ses tubes, quel que soit le code de page du poste.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) not in (3, 4):
        print("usage: fake_codex_app_server.py <mode> [<fichier>] <action>", file=sys.stderr)
        return 2
    mode, action = argv[1], argv[-1]
    target = argv[2] if len(argv) == 4 else None
    if action == "--version":
        return _version(mode)
    if action == "app-server":
        return _serve(mode, target)
    print(f"action inconnue : {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
