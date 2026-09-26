"""Sondes Claude Code du poste (cahier P5 § 10) : version, code de sortie de ``auth status``, alias documentés,
ligne d'état des quotas.

1. ``claude --version``, sans jeton : version ``X.Y.Z`` ; absente ou antérieure à 2.1.248 : relevé ``cli_absente`` ou
   ``cli_hors_version`` ; différente de ``[claude] version_testee`` : ``versions.claude.conforme = false``.
2. ``claude auth status``, avec ``CLAUDE_CODE_OAUTH_TOKEN`` tiré du coffre, **sorties jetées sans lecture**
   (``DEVNULL``), délai 20 s : code 0 → ``jeton_reconnu`` (jamais « valide » : la documentation dit « logged in », pas
   « jeton vérifié auprès d'Anthropic »), 1 → ``refuse``, autre code ou délai dépassé → ``jeton_present_non_verifie`` ;
   jeton absent du coffre → ``jeton_absent`` **sans lancer** la commande. Un ``apiKeyHelper`` venu d'un réglage géré
   passerait avant le jeton et ferait aussi rendre 0 : limite dite, tranchée en P6.
3. Alias et efforts documentés (:mod:`catalogue_claude`) ; quotas : fichier de la ligne d'état de **vos** sessions
   Claude Code (``[claude] ligne_etat``, décision D56).

Environnement de Claude : liste blanche de plateforme, ``CLAUDE_CONFIG_DIR``, ``DISABLE_UPDATES=1``,
``DISABLE_AUTOUPDATER=1``, ``CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`` ; aucune variable ``*_API_KEY`` ni ``ANTHROPIC_*``. Le
jeton n'entre que dans l'environnement de ``claude auth status``, jamais dans l'argv. Aucun fichier de
``CLAUDE_CONFIG_DIR`` n'est lu ; ``.credentials.json`` n'est jamais ouvert.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .app_server import ArretNonConfirme, arreter
from .catalogue_claude import DOCUMENTATION_LUE_LE, PLAGE_MINIMALE, dans_la_plage, modeles_documentes
from .coffre import Coffre, CoffreErreur
from .local_runner import FencedSpawnError, spawn_fenced_process
from .politique import VERSION_CLAUDE_MINIMALE, SectionClaude, version_numerique
from .sondes_codex import lire_version
from .subscription_quotas import _failure, probe_claude_snapshot

DELAI_AUTH_STATUS_S = 20.0
PLATEFORME = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
              "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "APPDATA", "LOCALAPPDATA", "HTTPS_PROXY", "HTTP_PROXY",
              "NO_PROXY")

CLAUDE_ABSENT = "Claude Code introuvable : [claude] executable de poste.toml ne désigne aucun fichier."
VERSION_ILLISIBLE = "Version de Claude Code illisible : relevé refusé."
LIGNE_ETAT_NON_DECLAREE = ("Ligne d'état non déclarée dans poste.toml ([claude] ligne_etat) : quotas Claude "
                           "inconnus.")


def environnement_claude(section: SectionClaude, *, source: Mapping[str, str] | None = None,
                         jeton: str | None = None) -> dict[str, str]:
    """Environnement minimal de Claude Code ; ``jeton`` seulement pour ``auth status``."""
    valeurs = os.environ if source is None else source
    env = {nom: valeurs[nom] for nom in PLATEFORME if nom in valeurs}
    env.update({"CLAUDE_CONFIG_DIR": str(section.config_dir), "DISABLE_UPDATES": "1", "DISABLE_AUTOUPDATER": "1",
                "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"})
    if jeton is not None:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = jeton
    return env


@dataclass
class ResultatClaude:
    releve: dict[str, Any]
    connexion: str
    version: dict[str, Any]
    alertes: list[str] = field(default_factory=list)
    mesures: dict[str, Any] = field(default_factory=dict)


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def code_auth_status(argv: Sequence[str], env: dict[str, str], cwd: str, delai_s: float) -> int | None:
    """Code de sortie de ``claude auth status`` (sorties jetées sans lecture) ; ``None`` si délai dépassé."""
    processus = await spawn_fenced_process([*argv, "auth", "status"], cwd=cwd, env=env,
                                           stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                                           stderr=asyncio.subprocess.DEVNULL)
    code: int | None = None
    try:
        boucle = asyncio.get_running_loop()
        echeance = boucle.time() + delai_s
        while processus.returncode is None and boucle.time() < echeance:
            await asyncio.sleep(0.02)
        code = processus.returncode
    finally:
        arrete = await asyncio.shield(arreter(processus, [], propre=False))
    if not arrete:
        raise ArretNonConfirme
    return code


async def sonder_claude(section: SectionClaude, coffre: Coffre, *, delai_s: float,
                        prefixe: Sequence[str] | None = None, environnement: Mapping[str, str] | None = None,
                        delai_auth_s: float = DELAI_AUTH_STATUS_S) -> ResultatClaude:
    """Relevé de la voie Claude ; ne lève jamais."""

    instant = datetime.now(UTC)
    alertes: list[str] = []
    mesures: dict[str, Any] = {}
    try:
        jeton = coffre.lire("jeton-claude")
        coffre_lisible = True
    except CoffreErreur as exc:
        jeton, coffre_lisible = None, False
        alertes.append(str(exc)[:300])
    connexion = "jeton_absent" if (coffre_lisible and jeton is None) else "inconnu"

    def releve(etat: str, *, version: str | None, detail: str | None, modeles: list | None = None,
               compteurs: list | None = None) -> dict[str, Any]:
        return {"voie": "poste-claude", "source": "poste", "version_cli": version, "releve_le": _iso(instant),
                "modeles": modeles or [], "quotas": None, "compteurs": compteurs or [],
                "origine_liste": "alias_documentes" if modeles else "aucune", "etat": etat, "detail": detail,
                "documentation_lue_le": DOCUMENTATION_LUE_LE.isoformat() if modeles else None,
                "resolutions_observees": []}

    def resultat(r: dict[str, Any], version: str | None) -> ResultatClaude:
        return ResultatClaude(releve=r, connexion=connexion, alertes=alertes, mesures=mesures,
                              version={"lue": version, "testee": section.version_testee,
                                       "conforme": version == section.version_testee})

    argv = list(prefixe) if prefixe else [str(section.executable)]
    if not prefixe and not section.executable.is_file():
        return resultat(releve("cli_absente", version=None, detail=CLAUDE_ABSENT), None)
    env = environnement_claude(section, source=environnement)
    debut = time.monotonic()
    version = None
    try:
        with tempfile.TemporaryDirectory(prefix="acp-sonde-", ignore_cleanup_errors=True) as dossier:
            async with asyncio.timeout(delai_s):
                version = await lire_version(argv, env, dossier)
            if version is None:
                return resultat(releve("indisponible", version=None, detail=VERSION_ILLISIBLE), None)
            numerique = version_numerique(version)
            if numerique < VERSION_CLAUDE_MINIMALE:
                return resultat(releve("cli_hors_version", version=version, detail=(
                    f"Claude Code {version} trop ancien : le poste exige la version 2.1.248 ou plus récente "
                    "(--restricted).")), version)
            if jeton is not None:
                code = await code_auth_status(argv, environnement_claude(section, source=environnement, jeton=jeton),
                                              dossier, delai_auth_s)
                connexion = {0: "jeton_reconnu", 1: "refuse"}.get(code, "jeton_present_non_verifie")
                mesures["auth_status_code"] = code
    except TimeoutError:
        return resultat(releve("indisponible", version=version, detail=(
            f"Claude Code n'a pas répondu dans le délai de {delai_s:g} s : relevé refusé.")), version)
    except FencedSpawnError as exc:
        if exc.reason == "spawn_error":
            return resultat(releve("cli_absente", version=None, detail=CLAUDE_ABSENT), None)
        return resultat(releve("indisponible", version=version, detail=(
            "Isolation du processus Claude Code impossible (Job Object) : sonde non lancée.")), version)
    except ArretNonConfirme:
        return resultat(releve("indisponible", version=version, detail=(
            "Arrêt de Claude Code non confirmé : relevé écarté par prudence.")), version)
    except OSError:
        return resultat(releve("indisponible", version=version, detail=VERSION_ILLISIBLE), version)
    mesures["duree_s"] = round(time.monotonic() - debut, 3)
    if section.ligne_etat is not None:
        compteur = await probe_claude_snapshot(section.ligne_etat)
    else:
        compteur = _failure("claude_code", "unavailable", LIGNE_ETAT_NON_DECLAREE)
    detail = None
    if not dans_la_plage(numerique):
        detail = (f"Claude Code {version} hors de la plage documentée (à partir de "
                  f"{'.'.join(map(str, PLAGE_MINIMALE))}) : alias publiés sans résolution ni efforts (Inconnu).")
    return resultat(releve("ok", version=version, detail=detail, modeles=modeles_documentes(numerique),
                           compteurs=[compteur.model_dump(mode="json")]), version)
