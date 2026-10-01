"""Commandes imposées aux agents d'une carte (cahier P6 § 6.3) : argv et environnement CALCULÉS, sans shell.

La consigne passe par l'**entrée standard** (``-`` pour Codex, ``-p`` sans invite pour Claude), jamais par l'argv :
``/proc/<pid>/cmdline`` est lisible par tous les UID du conteneur, donc par les autres agents (écart au cahier, qui
plaçait la consigne en dernier argument). La forme ``-`` est documentée par ``codex exec`` et ``codex exec resume``
(``exec/src/cli.rs`` : « If `-` is used, read from stdin »).

**Codex** (UID ``acp-codex``) :
``codex exec --json -C <worktree> -m <modèle> -c model_reasoning_effort="<effort>" -c service_tier="default"
-c cli_auth_credentials_store="file" --ignore-user-config --ignore-rules -c default_permissions="acp_agent|acp_lecture"
-c permissions.<profil>.filesystem={…} -c permissions.<profil>.network.enabled=false
-c sandbox_workspace_write.network_access=false -c web_search="disabled" --disable <fonction>…
--output-schema <schema.json> -o <reponse.json> [resume <session>] -`` ; jamais ``--ephemeral`` (il rendrait la
reprise impossible). Environnement : ``CODEX_HOME``, ``HOME`` de l'agent, ``TMPDIR`` de la tentative, ``PATH``
minimal ; aucune autre variable.

**Profil de permissions imposé** (cahier P6 § 4.2, régime A) : les commandes de Codex tournent sous le même UID que
Codex, propriétaire de ``auth.json`` ; seul le bac à sable peut leur en interdire la lecture. Le profil nommé lit
toute la racine, écrit le worktree et ``$TMPDIR`` (implémentation, correction ; rien pour la relecture et
l'exploration), coupe le réseau et INTERDIT ``/donnees/codex``, ``/donnees/claude``, ``/donnees/acp`` et
``/etc/acp``. **Sans** ``--sandbox`` : avec lui, Codex 0.156.1 ignore ``default_permissions`` et applique son profil
intégré, qui lit toute la racine, ``auth.json`` compris (relecture de P6, reproduit dans l'image avec un faux
fournisseur de modèle : ``executant/tests/test_image.py::test_codex_exec_profil_interdit_les_identifiants``).

**Claude** (UID ``acp-claude``) :
``claude -p --restricted --model <alias|id> --effort <effort> --tools Read,Glob,Grep,Edit,Write
--strict-mcp-config --disallowedTools "mcp__*" --permission-mode acceptEdits --permission-prompts none
--settings /etc/acp/claude-settings.json --add-dir <lecture> --output-format stream-json --verbose
--json-schema '<schéma>' [--resume <session>]`` ; jamais ``--bare`` (il ne lit pas le jeton), jamais
``--fallback-model``. Environnement : ``CLAUDE_CONFIG_DIR``, ``CLAUDE_CODE_OAUTH_TOKEN`` (ce processus seul),
``DISABLE_UPDATES``, ``DISABLE_AUTOUPDATER``, ``DISABLE_TELEMETRY``, ``HOME`` et ``TMPDIR`` propres, **sans**
``CLAUDE_CODE_SKIP_PROMPT_HISTORY`` (une session ainsi lancée ne serait pas reprenable, C4).

Relecture et exploration : Codex sous le profil ``acp_lecture`` (aucune écriture), Claude avec
``--tools Read,Glob,Grep``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

from .evenements import SCHEMA_SORTIE
from .sonde_plateforme import CHEMINS_INTERDITS

FONCTIONS_CODEX_COUPEES = ("apps", "plugins", "hooks", "multi_agent", "browser_use", "computer_use",
                           "image_generation", "worktrees", "workspace_dependencies", "skill_mcp_dependency_install",
                           "goals")
OUTILS_CLAUDE_ECRITURE = "Read,Glob,Grep,Edit,Write"
OUTILS_CLAUDE_LECTURE = "Read,Glob,Grep"
SETTINGS_CLAUDE = "/etc/acp/claude-settings.json"
ROLES_LECTURE = ("relecture", "exploration")
PATH_AGENTS = "/usr/local/bin:/usr/bin:/bin"
PROFIL_AGENT = "acp_agent"
PROFIL_LECTURE = "acp_lecture"


@dataclass(frozen=True)
class CommandeAgent:
    argv: list[str]
    env: dict[str, str]


def schema_json() -> str:
    return json.dumps(SCHEMA_SORTIE, ensure_ascii=False, separators=(",", ":"))


def _base_env(home: PurePosixPath | str, tmpdir: Path) -> dict[str, str]:
    return {"HOME": str(home), "PATH": PATH_AGENTS, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "TMPDIR": Path(tmpdir).as_posix()}


def surcharges_permissions(role: str, interdits: Sequence[str] = CHEMINS_INTERDITS) -> list[str]:
    """Surcharges ``-c`` du profil de permissions de l'agent Codex : lecture de la racine, écriture du worktree et de
    ``$TMPDIR`` (rôles d'écriture seulement), identifiants INTERDITS, réseau coupé (forme éprouvée par le vrai Codex
    0.156.1 dans l'image, témoin du régime A)."""
    lecture = role in ROLES_LECTURE
    nom = PROFIL_LECTURE if lecture else PROFIL_AGENT
    regles = {":root": "read"}
    if not lecture:
        regles.update({":project_roots": "write", ":tmpdir": "write"})
    regles.update({chemin: "deny" for chemin in interdits})
    table = "{" + ", ".join(f'"{chemin}"="{acces}"' for chemin, acces in regles.items()) + "}"
    return ["-c", f'default_permissions="{nom}"', "-c", f"permissions.{nom}.filesystem={table}",
            "-c", f"permissions.{nom}.network.enabled=false"]


def commande_codex(*, prefixe: Sequence[str], executable: str, worktree: Path, modele: str, effort: str | None,
                   role: str, schema: Path, reponse: Path, codex_home: Path, home: PurePosixPath | str,
                   tmpdir: Path, session: str | None = None) -> CommandeAgent:
    argv = [*prefixe, executable, "exec", "--json", "-C", Path(worktree).as_posix(), "-m", modele]
    if effort:
        argv += ["-c", f'model_reasoning_effort="{effort}"']
    argv += ["-c", 'service_tier="default"', "-c", 'cli_auth_credentials_store="file"',
             "--ignore-user-config", "--ignore-rules", *surcharges_permissions(role),
             "-c", "sandbox_workspace_write.network_access=false", "-c", 'web_search="disabled"']
    for fonction in FONCTIONS_CODEX_COUPEES:
        argv += ["--disable", fonction]
    argv += ["--output-schema", Path(schema).as_posix(), "-o", Path(reponse).as_posix()]
    if session:
        argv += ["resume", session]
    argv.append("-")
    env = _base_env(home, tmpdir)
    env["CODEX_HOME"] = Path(codex_home).as_posix()
    return CommandeAgent(argv=argv, env=env)


def commande_claude(*, prefixe: Sequence[str], executable: str, modele: str, effort: str | None, role: str,
                    lecture: Path, config_dir: Path, jeton: str, home: PurePosixPath | str, tmpdir: Path,
                    session: str | None = None, settings: str = SETTINGS_CLAUDE) -> CommandeAgent:
    argv = [*prefixe, executable, "-p", "--restricted", "--model", modele]
    if effort:
        argv += ["--effort", effort]
    argv += ["--tools", OUTILS_CLAUDE_LECTURE if role in ROLES_LECTURE else OUTILS_CLAUDE_ECRITURE,
             "--strict-mcp-config", "--disallowedTools", "mcp__*", "--permission-mode", "acceptEdits",
             "--permission-prompts", "none", "--settings", settings, "--add-dir", Path(lecture).as_posix(),
             "--output-format", "stream-json", "--verbose", "--json-schema", schema_json()]
    if session:
        argv += ["--resume", session]
    env = _base_env(home, tmpdir)
    env.update({"CLAUDE_CONFIG_DIR": Path(config_dir).as_posix(), "CLAUDE_CODE_OAUTH_TOKEN": jeton,
                "DISABLE_UPDATES": "1", "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1"})
    return CommandeAgent(argv=argv, env=env)
