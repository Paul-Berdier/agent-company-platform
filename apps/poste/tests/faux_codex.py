"""FAUX Codex CLI (``--version`` et ``app-server``) piloté par un scénario JSON, pour les tests du poste (étape P5).

Jamais lancé par le code de production : les tests le désignent comme lanceur de Codex
(``[sys.executable, "-I", "faux_codex.py", "<scenario.json>"]``, injecté par le contexte, jamais par ``poste.toml``).
Bibliothèque standard seulement, aucun accès réseau. Ses réponses suivent les schémas publiés par Codex CLI 0.156.1
(``fixtures/codex_app_server_0_156_1``) : ``test_sondes_codex.py`` les valide.

Invocation : ``python -I faux_codex.py <scenario.json> [-c …]… (--version | app-server)``. Si l'argv porte
``cli_auth_credentials_store="ephemeral"`` (second app-server du catalogue embarqué), le sous-scénario ``embarque``
remplace le scénario principal (compte nul par défaut).

Clés du scénario (toutes facultatives) :

- ``version`` (sortie de ``--version`` ; ``null`` : sortie illisible), ``version_bloquee`` ;
- ``compte`` (objet ``account`` rendu par ``account/read``, ``null`` : aucun compte), ``config``, ``origines``,
  ``readiness``, ``modeles``, ``page`` (taille de page de ``model/list``), ``limites`` (résultat de
  ``account/rateLimits/read``, ou ``"erreur"``) ;
- ``requete_serveur`` : émet la requête serveur ``account/chatgptAuthTokens/refresh`` avant de répondre à
  ``account/read`` ; ``notifications`` : intercale des notifications et une réponse étrangère ;
- ``bloquer`` (méthode après laquelle le faux ne répond plus ; son PID est écrit dans ``pid``), ``planter``
  (méthode avant la réponse de laquelle il s'arrête), ``ligne_invalide`` (méthode à laquelle il répond par du
  texte non JSON) ;
- ``enregistrer`` (fichier : argv puis chaque message reçu, une ligne JSON par entrée), ``env`` (fichier : noms des
  variables reçues, ``CODEX_HOME``) ;
- ``bac`` : notification ``windowsSandbox/setupCompleted`` envoyée après ``windowsSandbox/setupStart``.
"""

from __future__ import annotations

import json
import os
import sys
import time

EMAIL = "titulaire@example.com"
MODELES = [
    {
        "id": "factice-codex-1", "model": "factice-codex-1", "displayName": "Factice 1",
        "description": "Modèle manifestement factice (description jetée par le poste).",
        "hidden": False, "isDefault": True, "defaultReasoningEffort": "medium",
        "supportedReasoningEfforts": [{"reasoningEffort": "low", "description": "d"},
                                      {"reasoningEffort": "medium", "description": "d"},
                                      {"reasoningEffort": "high", "description": "d"}],
        "serviceTiers": [{"id": "default", "name": "Standard", "description": "d"},
                         {"id": "priority", "name": "Rapide", "description": "d"}],
        "defaultServiceTier": "default", "upgrade": None,
        "upgradeInfo": {"model": "factice-codex-2", "retirementAt": 1790000000},
        "availabilityNux": {"message": "texte promotionnel jeté"}, "inputModalities": ["text"],
    },
    {
        "id": "factice-codex-2", "model": "factice-codex-2", "displayName": "Factice 2",
        "description": "Second modèle factice.", "hidden": False, "isDefault": False,
        "defaultReasoningEffort": "low",
        "supportedReasoningEfforts": [{"reasoningEffort": "low", "description": "d"}],
        "serviceTiers": [], "defaultServiceTier": None, "upgrade": None, "upgradeInfo": None,
    },
]
CONFIG = {"windows": {"sandbox": "elevated"}, "service_tier": "default", "cli_auth_credentials_store": "keyring",
          "model": None, "workspaceRouting": "valeur jetée"}
ORIGINES = {"windows.sandbox": {"name": {"type": "sessionFlags"}, "version": "1"},
            "service_tier": {"name": {"type": "sessionFlags"}, "version": "1"},
            "cli_auth_credentials_store": {"name": {"type": "sessionFlags"}, "version": "1"}}


def limites_par_defaut() -> dict:
    def fenetre(utilise, minutes, remise):
        return {"usedPercent": utilise, "windowDurationMins": minutes, "resetsAt": remise}
    instantane = {"limitId": "codex", "limitName": "Codex", "primary": fenetre(41, 300, 1790000000),
                  "secondary": fenetre(12, 10080, 1790500000),
                  "credits": {"hasCredits": False, "unlimited": False, "balance": None}, "planType": "prolite",
                  "rateLimitReachedType": None}
    return {"rateLimits": instantane, "rateLimitsByLimitId": {"codex": instantane}}


def _emettre(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _enregistrer(scenario: dict, entree: dict) -> None:
    cible = scenario.get("enregistrer")
    if cible:
        with open(cible, "a", encoding="utf-8") as flux:
            flux.write(json.dumps(entree, ensure_ascii=False) + "\n")


def _bloquer(scenario: dict) -> None:
    if scenario.get("pid"):
        with open(scenario["pid"], "w", encoding="ascii") as flux:
            flux.write(str(os.getpid()))
    while True:
        time.sleep(1)


def _servir(scenario: dict) -> int:
    if scenario.get("env"):
        with open(scenario["env"], "w", encoding="utf-8") as flux:
            json.dump({"noms": sorted(os.environ), "codex_home": os.environ.get("CODEX_HOME")}, flux)
    modeles = scenario.get("modeles", MODELES)
    page = int(scenario.get("page", 50))
    for ligne in sys.stdin:
        if not ligne.strip():
            continue
        message = json.loads(ligne)
        _enregistrer(scenario, message)
        methode, identifiant = message.get("method"), message.get("id")
        if methode is None:
            continue  # réponse du poste à une requête du serveur (enregistrée ci-dessus)
        if methode == scenario.get("planter"):
            return 3
        if methode == scenario.get("ligne_invalide"):
            sys.stdout.write("ceci n'est pas du JSON\n")
            sys.stdout.flush()
            continue
        if methode == "initialize":
            _emettre({"id": identifiant, "result": {"codexHome": os.environ.get("CODEX_HOME", "absent"),
                                                    "platformFamily": "windows" if os.name == "nt" else "unix",
                                                    "platformOs": "windows" if os.name == "nt" else "linux",
                                                    "userAgent": "faux_codex/0.156.1"}})
        elif methode == "initialized":
            continue
        elif methode == "account/read":
            if scenario.get("requete_serveur"):
                _emettre({"id": 900, "method": "account/chatgptAuthTokens/refresh",
                          "params": {"reason": "unauthorized", "previousAccountId": None}})
            if scenario.get("notifications"):
                _emettre({"method": "account/rateLimits/updated", "params": {"rateLimits": {}}})
                _emettre({"id": 999, "result": {"étranger": True}})
            compte = scenario.get("compte", {"type": "chatgpt", "email": EMAIL, "planType": "prolite"})
            _emettre({"id": identifiant, "result": {"account": compte, "requiresOpenaiAuth": True}})
        elif methode == "config/read":
            _emettre({"id": identifiant, "result": {"config": scenario.get("config", CONFIG),
                                                    "origins": scenario.get("origines", ORIGINES)}})
        elif methode == "windowsSandbox/readiness":
            _emettre({"id": identifiant, "result": {"status": scenario.get("readiness", "ready")}})
        elif methode == "model/list":
            params = message.get("params") or {}
            debut = int(params.get("cursor") or 0)
            tranche = modeles[debut:debut + page]
            suite = str(debut + page) if debut + page < len(modeles) else None
            _emettre({"id": identifiant, "result": {"data": tranche, "nextCursor": suite}})
        elif methode == "account/rateLimits/read":
            limites = scenario.get("limites", "defaut")
            if limites == "erreur":
                _emettre({"id": identifiant, "error": {"code": -32600, "message": f"refusé pour {EMAIL}"}})
            else:
                _emettre({"id": identifiant, "result": limites_par_defaut() if limites == "defaut" else limites})
        elif methode == "windowsSandbox/setupStart":
            _emettre({"id": identifiant, "result": {"started": True}})
            fin = scenario.get("bac", {"mode": "elevated", "success": True, "error": None})
            _emettre({"method": "windowsSandbox/setupCompleted", "params": fin})
        elif identifiant is not None:
            _emettre({"id": identifiant, "error": {"code": -32601, "message": "méthode inconnue du faux"}})
        if methode == scenario.get("bloquer"):
            _bloquer(scenario)
    return 0


def main(argv: list[str]) -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    with open(argv[1], encoding="utf-8") as flux:
        scenario = json.load(flux)
    arguments = argv[2:]
    if 'cli_auth_credentials_store="ephemeral"' in arguments:
        # Par défaut, le catalogue embarqué diffère de la liste du compte (un seul modèle) : origine « compte ».
        scenario = dict({"compte": None, "modeles": MODELES[1:]}, **scenario.get("embarque", {}),
                        enregistrer=scenario.get("enregistrer"))
    _enregistrer(scenario, {"argv": arguments})
    if "--version" in arguments:
        if scenario.get("version_bloquee"):
            _bloquer(scenario)
        version = scenario.get("version", "codex-cli 0.156.1")
        print(version if version is not None else "codex-cli version inconnue")
        return 0
    if "app-server" in arguments:
        return _servir(scenario)
    if "login" in arguments:
        return int(scenario.get("code_login", 0))
    print("action inconnue du faux", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
