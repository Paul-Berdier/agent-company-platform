"""FAUX ``codex exec`` / ``codex sandbox`` et FAUX ``claude -p`` pilotés par scénario, pour les tests de l'exécution
d'une carte (cahier P6 § 6, § 14.3). Ils ne prouvent que la PLOMBERIE, jamais la qualité d'un modèle.

Jamais lancés par le code de production : les tests les désignent comme exécutables des outils
(``[python, "-I", "faux_agents.py", "<scenario.json>", "codex"|"claude"]``, injectés dans ``Execution.executables``).
Bibliothèque standard seulement, aucun accès réseau.

Scénario (JSON) : ``{"executions": [<exécution>…], "journal": "<fichier>", "compteur": "<fichier>"}`` ; la n-ième
invocation d'agent joue la n-ième exécution (la dernière se répète). Une exécution :

- ``ecrire`` (``{chemin relatif: contenu}``), ``supprimer`` (``[chemins]``), ``lire`` (``[chemins absolus]`` : le
  résultat de chaque lecture, « lu » ou « refusé », va au journal), ``attendre_s``, ``bloquer`` (ne finit jamais),
  ``code`` (code de sortie) ;
- ``sortie`` (objet structuré ; défaut : ``termine``), ``sans_sortie`` ;
- ``session`` ; Claude : ``modele`` (servi, dans ``system/init``), ``outils``, ``limite`` (``rate_limit_info``) ;
  Codex : ``limite`` (vrai : ``turn.failed`` « usage limit »).

``codex sandbox -P <profil> -C <dossier> -- <argv>`` lance simplement ``argv`` (aucune clôture : test seulement).
Chaque invocation est journalisée : outil, argv, entrée standard, noms des variables, présence du jeton.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

SORTIE = {"issue": "termine", "resume": "Travail fait par le faux agent.", "question": None, "verdict": None,
          "corrections": None}


def _journal(scenario: dict, entree: dict) -> None:
    if scenario.get("journal"):
        with open(scenario["journal"], "a", encoding="utf-8") as flux:
            flux.write(json.dumps(entree, ensure_ascii=False) + "\n")


def _rang(scenario: dict) -> int:
    chemin = scenario.get("compteur")
    rang = 0
    if chemin:
        try:
            with open(chemin, encoding="utf-8") as flux:
                rang = int(flux.read().strip() or 0)
        except OSError:
            rang = 0
        with open(chemin, "w", encoding="utf-8") as flux:
            flux.write(str(rang + 1))
    return rang


def _agir(execution: dict, scenario: dict) -> None:
    for chemin, contenu in (execution.get("ecrire") or {}).items():
        dossier = os.path.dirname(chemin)
        if dossier:
            os.makedirs(dossier, exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as flux:
            flux.write(contenu)
    for chemin in execution.get("supprimer") or []:
        os.remove(chemin)
    for chemin in execution.get("lire") or []:
        try:
            with open(chemin, "rb") as flux:
                flux.read(16)
            issue = "lu"
        except OSError:
            issue = "refusé"
        _journal(scenario, {"lecture": chemin, "issue": issue})
    if execution.get("bloquer"):
        while True:
            time.sleep(1)
    time.sleep(float(execution.get("attendre_s", 0)))


def _emettre(objet: dict) -> None:
    # Octets UTF-8, quelle que soit la page de code de la console (Windows) : comme les vraies CLI sous Linux.
    sys.stdout.buffer.write((json.dumps(objet, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def main(argv: list[str]) -> int:
    with open(argv[1], encoding="utf-8") as flux:
        scenario = json.load(flux)
    outil, arguments = argv[2], argv[3:]
    if outil == "codex" and arguments[:1] == ["sandbox"]:
        separateur = arguments.index("--")
        _journal(scenario, {"outil": "codex-sandbox", "argv": arguments, "cwd": os.getcwd()})
        return subprocess.run(arguments[separateur + 1:], check=False).returncode
    entree = sys.stdin.buffer.read().decode("utf-8", "replace")
    rang = _rang(scenario)
    executions = scenario.get("executions") or [{}]
    execution = executions[min(rang, len(executions) - 1)]
    _journal(scenario, {"outil": outil, "rang": rang, "argv": arguments, "stdin": entree, "cwd": os.getcwd(),
                        "noms": sorted(os.environ), "jeton": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
                        "uid": os.getuid() if hasattr(os, "getuid") else None})
    session = execution.get("session", f"session-{outil}-1")
    sortie = None if execution.get("sans_sortie") else execution.get("sortie", SORTIE)
    if outil == "codex":
        _emettre({"type": "thread.started", "thread_id": session})
        _emettre({"type": "turn.started"})
        _agir(execution, scenario)
        if execution.get("limite"):
            _emettre({"type": "turn.failed", "error": {"message": "You've hit your usage limit."}})
            return 1
        if sortie is not None:
            texte = json.dumps(sortie, ensure_ascii=False)
            if "-o" in arguments:
                with open(arguments[arguments.index("-o") + 1], "w", encoding="utf-8") as flux:
                    flux.write(texte)
            _emettre({"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": texte}})
        _emettre({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 200,
                                                      "output_tokens": 50, "reasoning_output_tokens": 0}})
        return int(execution.get("code", 0))
    _emettre({"type": "system", "subtype": "init", "session_id": session,
              "model": execution.get("modele", "claude-sonnet-5"),
              "tools": execution.get("outils", ["Read", "Glob", "Grep", "Edit", "Write"])})
    _agir(execution, scenario)
    if execution.get("limite"):
        _emettre({"type": "rate_limit_event", "rate_limit_info": execution["limite"]})
    resultat = {"type": "result", "subtype": "success", "is_error": False, "session_id": session, "result": "fini",
                "usage": {"input_tokens": 900, "output_tokens": 40, "cache_read_input_tokens": 100,
                          "cache_creation_input_tokens": 0}}
    if sortie is not None:
        resultat["structured_output"] = sortie
    _emettre(resultat)
    return int(execution.get("code", 0))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
