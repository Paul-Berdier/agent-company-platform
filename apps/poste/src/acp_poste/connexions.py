"""Connexions manuelles du compte du poste (cahier P5 § 6.3 et § 8.3) : gestes du **propriétaire**, jamais d'un agent.

- ``acp-poste connexion codex`` : écrit le ``config.toml`` du profil dédié s'il manque (jamais par-dessus une
  version modifiée), puis lance ``codex -c cli_auth_credentials_store="keyring" login --device-auth`` avec
  ``CODEX_HOME`` imposé, **en héritant de la console** : le poste ne lit ni n'enregistre rien de ce dialogue.
- ``acp-poste connexion claude`` : lit le jeton de ``claude setup-token`` par saisie masquée, vérifie sa forme
  minimale (non vide, sans espace, 512 caractères au plus) et le range au coffre DPAPI ; n'affiche que « Jeton Claude
  enregistré (DPAPI). ».
- ``acp-poste connexion bac-a-sable`` : console interactive seulement ; app-server lancé dans un dossier vide dédié,
  puis ``windowsSandbox/setupStart {mode: "elevated"}`` **sans ``cwd``** (aucune racine de travail ne reçoit d'ACL
  d'écriture) ; l'UAC s'affiche ; attente de ``windowsSandbox/setupCompleted`` (10 min au plus) ; relecture des droits
  de ``poste.toml`` et des exécutables.

Chacune tient le verrou des sondes : elle ne croise jamais une sonde du service sur le même ``CODEX_HOME``.
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from typing import Callable

from .app_server import ArretNonConfirme, ErreurRpc, ReponseMalFormee, SessionFermee
from .coffre import CoffreErreur
from .contexte import Contexte
from .local_runner import FencedSpawnError, spawn_fenced_process, terminate_process_tree
from .politique import Politique, PolitiqueRefusee, verifier_droits
from .sondes_codex import SURCHARGES, ecrire_config_toml, installer_bac_a_sable
from .subscription_quotas import codex_environment
from .verrou import Verrou, VerrouOccupe

SONDE_EN_COURS = "Une sonde est en cours dans le service : réessayez dans une minute."
BAC_DELAI_S = 600.0
JETON_CLAUDE_MAX = 512


def _verrou_sondes(contexte: Contexte) -> Verrou | None:
    try:
        return Verrou(contexte.emplacements.verrou_sondes).prendre()
    except VerrouOccupe:
        print(SONDE_EN_COURS, file=sys.stderr)
        return None


def connexion_codex(contexte: Contexte, politique: Politique) -> int:
    if politique.codex is None:
        print("Section [codex] absente de poste.toml : connexion Codex impossible.", file=sys.stderr)
        return 2
    verrou = _verrou_sondes(contexte)
    if verrou is None:
        return 2
    try:
        try:
            etat = ecrire_config_toml(politique.codex.home)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print("config.toml du profil Codex " + ("écrit par le poste." if etat == "cree" else "déjà conforme."))
        argv = [*(contexte.lanceurs.get("codex") or [str(politique.codex.executable)]),
                "-c", 'cli_auth_credentials_store="keyring"', "login", "--device-auth"]
        env = codex_environment(politique.codex.home, source=contexte.environnement)
        return asyncio.run(_console(argv, env, str(contexte.emplacements.acp_local)))
    finally:
        verrou.rendre()


async def _console(argv: list[str], env: dict[str, str], dossier: str) -> int:
    """Lance ``argv`` en héritant de la console (rien n'est lu ni capturé), sous clôture d'arbre."""
    try:
        processus = await spawn_fenced_process(argv, cwd=dossier, env=env, stdin=None, stdout=None, stderr=None)
    except FencedSpawnError:
        print("Codex CLI introuvable ou impossible à isoler : connexion non lancée.", file=sys.stderr)
        return 2
    try:
        while processus.returncode is None:
            await asyncio.sleep(0.1)
        return int(processus.returncode)
    finally:
        await terminate_process_tree(processus.process, 0.2)
        processus.close_fence()


def forme_jeton_claude(valeur: str) -> bool:
    return bool(valeur) and len(valeur) <= JETON_CLAUDE_MAX and not any(c.isspace() for c in valeur)


def connexion_claude(contexte: Contexte, *, lire: Callable[[str], str] | None = None) -> int:
    valeur = (lire or getpass.getpass)("Jeton de « claude setup-token » (collé, saisie masquée) : ").strip()
    if not forme_jeton_claude(valeur):
        print("Jeton Claude refusé : non vide, sans espace, 512 caractères au plus.", file=sys.stderr)
        return 2
    try:
        contexte.coffre.ecrire("jeton-claude", valeur)
    except CoffreErreur as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("Jeton Claude enregistré (DPAPI).")
    print("Effacez maintenant le terminal où « claude setup-token » l'a affiché (cls) et le presse-papiers ; si "
          "l'historique du presse-papiers de Windows (Win+V) est actif, supprimez-y l'entrée.")
    return 0


def connexion_bac_a_sable(contexte: Contexte, politique: Politique, *, interactif: bool | None = None,
                          delai_s: float = BAC_DELAI_S) -> int:
    if interactif is None:
        interactif = sys.stdin.isatty() and sys.stdout.isatty()
    if not interactif:
        print("Installation élevée du bac à sable refusée hors d'une console interactive (l'UAC doit s'afficher "
              "devant vous).", file=sys.stderr)
        return 2
    if politique.codex is None:
        print("Section [codex] absente de poste.toml : bac à sable Codex impossible.", file=sys.stderr)
        return 2
    verrou = _verrou_sondes(contexte)
    if verrou is None:
        return 2
    try:
        dossier = contexte.emplacements.bac_a_sable
        dossier.mkdir(parents=True, exist_ok=True)
        argv = [*(contexte.lanceurs.get("codex") or [str(politique.codex.executable)]), *SURCHARGES, "app-server"]
        env = codex_environment(politique.codex.home, source=contexte.environnement)
        try:
            issue = asyncio.run(installer_bac_a_sable(argv, env, str(dossier), delai_s))
        except (TimeoutError, FencedSpawnError, ErreurRpc, ArretNonConfirme, SessionFermee, ReponseMalFormee) as exc:
            print(f"Installation élevée du bac à sable non menée à terme ({type(exc).__name__}) : relancez la "
                  "commande ; rien n'est déduit.", file=sys.stderr)
            return 1
        if not issue.get("success"):
            erreur = issue.get("error")
            print("Installation élevée du bac à sable en échec" + (f" (message de Codex, en anglais : "
                  f"« {str(erreur)[:300]} »)" if erreur else "") + ".", file=sys.stderr)
            return 1
        print("Installation élevée du bac à sable terminée ; le prochain relevé lira le mode (config/read).")
    finally:
        verrou.rendre()
    try:
        verifier_droits(politique)
        print("Droits relus : poste.toml et les binaires des CLI restent hors d'atteinte du compte du poste.")
    except PolitiqueRefusee as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0
