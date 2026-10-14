"""Authentification officielle Claude Code 2.1.283, sur stdio, sans SDK ou endpoint privé.

Le CLI possède son magasin et son rafraîchissement. ACP ne garde l'URL et le code de retour qu'en mémoire.
Une sortie 0 n'est pas une preuve de connexion : SIGINT rend aussi 0 dans le témoin du vrai binaire.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from acp_poste_contrat import comptes as C
from .app_server import ArretNonConfirme, MethodeRefusee, ReponseMalFormee
from .local_runner import spawn_fenced_process, terminate_process_tree

VERSION_CLAUDE = "2.1.283"
SORTIE_MAX = 64 * 1024
_TYPES_AUTH = frozenset({"none", "claude.ai", "oauth_token", "api_key", "api_key_helper", "third_party"})
_ABONNEMENTS = frozenset({"pro", "max", "team", "enterprise"})
_URL = re.compile(r'https://[^\s\x00-\x20<>"\']+(?=[\s\x00-\x20<>"\'])')
_ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


@dataclass(frozen=True)
class EtatClaude:
    reconnu: bool
    type_auth: str
    abonnement: str | None = None


def environnement_officiel(env: Mapping[str, str]) -> dict[str, str]:
    """Refuse une provenance concurrente au lieu de l'injecter ou de la supprimer silencieusement."""
    interdits = {"CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"}
    if any(k in interdits or k.startswith("ANTHROPIC_") for k in env):
        raise ValueError("Environnement d'authentification Claude incompatible.")
    if not env.get("CLAUDE_CONFIG_DIR"):
        raise ValueError("Magasin officiel Claude non configuré.")
    return dict(env, DISABLE_UPDATES="1", DISABLE_AUTOUPDATER="1", DISABLE_TELEMETRY="1")


def _uid_claude(argv: Sequence[str]) -> int | None:
    # Seul le vrai lanceur Linux autorise le balayage global de son UID réservé. Un double Python/Windows,
    # ou une sonde sans identité, doit rester limité à son propre arbre de processus.
    if not argv or argv[0] != "/usr/bin/setpriv" or "--" not in argv:
        return None
    prefixe = argv[:argv.index("--")]
    return 10002 if "--reuid=10002" in prefixe and "--regid=10002" in prefixe else None


async def _arreter(processus, taches, *, uid: int | None = None) -> bool:
    """Groupe et UID dédié, puis clôture ; les erreurs ne deviennent jamais une preuve d'arrêt."""
    confirme = False
    try:
        if processus.stdin is not None:
            processus.stdin.close()
        if uid is not None:
            from .plateforme.linux import arreter_agent
            confirme = await arreter_agent(processus.process, uid, grace_s=.2)
        else:
            confirme = await terminate_process_tree(processus.process, .2)
    except Exception:
        confirme = False
    finally:
        try:
            processus.close_fence()
        except Exception:
            confirme = False
        for t in taches:
            t.cancel()
        await asyncio.gather(*taches, return_exceptions=True)
    return confirme


async def _fermer(processus, taches, *, uid: int | None = None) -> bool:
    fermeture = asyncio.create_task(_arreter(processus, taches, uid=uid))
    annule = False
    while True:
        try:
            resultat = await asyncio.shield(fermeture)
            break
        except asyncio.CancelledError:
            # Même plusieurs annulations ne libèrent pas le verrou avant la fin du balayage.
            annule = True
            if fermeture.done():
                if fermeture.cancelled():
                    raise ArretNonConfirme from None
                resultat = fermeture.result()
                break
    if annule:
        if not resultat:
            raise ArretNonConfirme from None
        raise asyncio.CancelledError
    return resultat


async def _lire_borne(flux, *, garder: bool) -> bytes:
    morceaux, total = [], 0
    while True:
        bloc = await flux.read(8192)
        if not bloc:
            return b"".join(morceaux)
        total += len(bloc)
        if total > SORTIE_MAX:
            raise ValueError("Sortie d'authentification hors limites.")
        if garder:
            morceaux.append(bloc)


def analyser_etat(brut: bytes, code: int, config_dir: str) -> EtatClaude:
    try:
        obj = json.loads(brut)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("État Claude illisible.") from None
    if (not isinstance(obj, dict) or type(obj.get("loggedIn")) is not bool
            or not isinstance(obj.get("authMethod"), str) or obj["authMethod"] not in _TYPES_AUTH or obj.get("configDirectory") != config_dir
            or code not in (0, 1) or (code == 0) != obj["loggedIn"]):
        raise ValueError("État Claude incompatible.")
    if obj["authMethod"] == "none" and obj["loggedIn"]:
        raise ValueError("État Claude contradictoire.")
    reconnu = obj["loggedIn"] and obj["authMethod"] == "claude.ai" and obj.get("apiProvider") == "firstParty"
    abonnement = obj.get("subscriptionType")
    return EtatClaude(reconnu, obj["authMethod"], abonnement if reconnu and isinstance(abonnement, str) and abonnement in _ABONNEMENTS else None)


async def lire_etat_claude(argv: Sequence[str], env: Mapping[str, str], cwd: Path | str,
                           delai_s: float = 20) -> EtatClaude:
    """JSON du CLI seulement ; pas de lecture de .credentials.json, identité ou token dans le résultat."""
    environnement = environnement_officiel(env)
    p = await spawn_fenced_process([*argv, "auth", "status"], cwd=cwd, env=environnement,
                                  stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                  stderr=asyncio.subprocess.PIPE, limit=SORTIE_MAX)
    taches = [asyncio.create_task(_lire_borne(p.stdout, garder=True)),
              asyncio.create_task(_lire_borne(p.stderr, garder=False)),
              asyncio.create_task(p.process.wait())]
    try:
        sortie, _, code = await asyncio.wait_for(asyncio.gather(*taches), timeout=delai_s)
        resultat = analyser_etat(sortie, code, environnement["CLAUDE_CONFIG_DIR"])
    finally:
        if not await _fermer(p, taches, uid=_uid_claude(argv)):
            raise ArretNonConfirme from None
    return resultat


class SessionCompteClaude:
    """Un seul login en attente, un seul code écrit ; les retransmissions identiques sont acquittées sans réécrire."""
    def __init__(self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path | str):
        self.argv, self.env, self.cwd = list(argv), environnement_officiel(env), cwd
        self.arret_confirme = None
        self.code_transmis = False
        self._p = None
        self._taches = []
        self._url = None
        self._invite = False
        self._soumission = None
        self._empreinte = None
        self._verrou_code = asyncio.Lock()

    async def __aenter__(self):
        boucle = asyncio.get_running_loop()
        self.defi = boucle.create_future()
        self.terminee = boucle.create_future()
        self._p = await spawn_fenced_process([*self.argv, "auth", "login", "--claudeai"], cwd=self.cwd,
            env=self.env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=SORTIE_MAX)
        lecteurs = [asyncio.create_task(self._lire(self._p.stdout)), asyncio.create_task(self._lire(self._p.stderr))]
        self._taches = [*lecteurs, asyncio.create_task(self._fin(lecteurs))]
        return self

    async def __aexit__(self, *args):
        try:
            if self._p is not None:
                self.arret_confirme = await _fermer(self._p, self._taches, uid=_uid_claude(self.argv))
        finally:
            self._p = None
            self._url = None
            for f in (self.defi, self.terminee):
                if f.done() and not f.cancelled():
                    f.exception()
                elif not f.done():
                    f.cancel()
        if self.arret_confirme is False:
            raise ArretNonConfirme from None

    def _echouer(self):
        for f in (self.defi, self.terminee):
            if not f.done():
                f.set_exception(ReponseMalFormee("Dialogue Claude incompatible."))

    def _observer(self, brut: bytes, *, fin=False):
        texte = _ANSI.sub("", brut.decode("utf-8", "replace")) + ("\n" if fin else "")
        self._invite |= "paste code" in texte.lower()
        for valeur in _URL.findall(texte):
            if C.url_claude_valide(valeur):
                if self._url is not None and valeur != self._url:
                    raise ReponseMalFormee("Défi Claude changé pendant la connexion.")
                self._url = valeur
        if self._url is not None and self._invite and not self.defi.done():
            self.defi.set_result(self._url)

    async def _lire(self, flux):
        tampon = bytearray()
        try:
            while True:
                bloc = await flux.read(8192)
                if not bloc:
                    self._observer(bytes(tampon), fin=True)
                    return
                tampon.extend(bloc)
                if len(tampon) > SORTIE_MAX:
                    raise ReponseMalFormee("Dialogue Claude hors limites.")
                self._observer(bytes(tampon))
        except Exception:
            self._echouer()
        finally:
            tampon.clear()

    async def _fin(self, lecteurs):
        try:
            code = await self._p.process.wait()
            await asyncio.gather(*lecteurs)
            if not self.defi.done():
                self.defi.set_exception(ReponseMalFormee("Défi Claude absent."))
            # Le processus peut sortir dès la lecture de stdin, avant le retour de drain().
            # Le verdict attend l’issue de cette unique transmission, sans la rejouer.
            async with self._verrou_code:
                if not self.terminee.done():
                    self.terminee.set_result(code)
        except Exception:
            self._echouer()

    async def fournir_code(self, soumission_id: str, code: str) -> bool:
        C.identifiant(soumission_id)
        if not C.code_retour_valide(code):
            raise MethodeRefusee("Code temporaire invalide.")
        empreinte = hashlib.sha256(code.encode("utf-8")).digest()
        async with self._verrou_code:
            if self._soumission is not None:
                if soumission_id != self._soumission or empreinte != self._empreinte:
                    raise MethodeRefusee("Une soumission différente existe déjà.")
                return self.code_transmis
            if (self._p is None or self._p.returncode is not None or not self.defi.done()
                    or self.defi.cancelled() or self.defi.exception() is not None):
                raise MethodeRefusee("Aucun défi Claude en attente.")
            # Marqué avant write : un échec partiel ne doit jamais permettre un second envoi ambigu.
            self._soumission, self._empreinte = soumission_id, empreinte
            try:
                self._p.stdin.write(code.encode("utf-8") + b"\n")
                await asyncio.wait_for(self._p.stdin.drain(), timeout=3)
                self.code_transmis = True
                return True
            except (OSError, RuntimeError, TimeoutError):
                self._echouer()
                raise ReponseMalFormee("Transmission du code interrompue.") from None
