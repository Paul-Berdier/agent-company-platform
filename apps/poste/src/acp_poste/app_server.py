"""Session JSON-RPC avec ``codex app-server``, à liste blanche de méthodes (cahier P5 § 9.2 et § 9.3).

Le poste ne demande à l'app-server **que** des lectures :

- ``initialize`` (puis la notification ``initialized``), ``account/read``, ``config/read``,
  ``windowsSandbox/readiness``, ``model/list``, ``account/rateLimits/read`` ;
- ``windowsSandbox/setupStart`` seulement dans une session **interactive** (``Session(interactive=True)``),
  construite par ``acp-poste connexion bac-a-sable`` et nulle part ailleurs.

Toute autre méthode est refusée **avant l'envoi** (:class:`MethodeRefusee`) : jamais ``account/login/*``,
``account/logout``, ``account/rateLimitResetCredit/consume`` (consomme un crédit), ``account/sendAddCreditsNudgeEmail``
(envoie un e-mail), ``config/value/write``, ``config/batchWrite`` ni ``skills/config/write`` (écrivent la
configuration). Une **requête du serveur** (``id`` et ``method``, dont ``account/chatgptAuthTokens/refresh``) reçoit
l'erreur ``-32601`` : le poste ne rend jamais de jeton. Les notifications sont ignorées sans être journalisées.

Le processus est lancé sans shell dans la clôture du runner local (Job Object sous Windows, créé suspendu) ; son
arbre est arrêté à la fermeture et l'arrêt doit être **prouvé**, sinon :class:`ArretNonConfirme` (le relevé est
écarté par l'appelant). Rien de ce que dit l'app-server n'est journalisé.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .local_runner import FencedProcess, spawn_fenced_process, terminate_process_tree

METHODES_ADMISES = frozenset({
    "initialize", "account/read", "config/read", "windowsSandbox/readiness", "model/list", "account/rateLimits/read",
})
METHODES_INTERACTIVES = frozenset({"windowsSandbox/setupStart"})
NOTIFICATIONS_ADMISES = frozenset({"initialized"})
LIGNE_MAX = 1024 * 1024
ARRET_GRACE_S = 0.2
SORTIE_PROPRE_S = 2.0
CLIENT = {"name": "acp_poste", "title": "Agent Company Platform — poste", "version": "1.0"}
ERREUR_NON_PRISE_EN_CHARGE = {"code": -32601, "message": "non pris en charge par le poste"}


class MethodeRefusee(RuntimeError):
    """Méthode hors de la liste blanche : rien n'a été envoyé."""


class SessionFermee(Exception):
    """L'app-server a fermé sa sortie avant la réponse attendue."""


class ReponseMalFormee(Exception):
    """Ligne non JSON, trop longue, ou réponse hors de la forme attendue."""


class ErreurRpc(Exception):
    def __init__(self, methode: str, code: Any) -> None:
        super().__init__(methode)
        self.methode = methode
        self.code = code if type(code) is int else "inconnu"


class ArretNonConfirme(Exception):
    """L'arrêt complet de l'arbre de l'app-server n'a pas pu être prouvé."""


async def _vider(flux: asyncio.StreamReader | None) -> None:
    """Vide un flux sans rien garder : la sortie d'erreur du CLI n'est jamais lue ni journalisée."""
    if flux is None:
        return
    while True:
        try:
            morceau = await flux.read(64 * 1024)
        except (OSError, ValueError):
            return
        if not morceau:
            return


async def arreter(processus: FencedProcess, taches: list[asyncio.Task], *, propre: bool) -> bool:
    """Ferme l'entrée, laisse une courte grâce si ``propre``, arrête l'arbre et le confirme ; ne lève jamais."""

    arrete = False
    try:
        entree = processus.stdin
        if entree is not None:
            try:
                entree.close()
                await asyncio.wait_for(entree.wait_closed(), timeout=1.0)
            except (OSError, RuntimeError, TimeoutError, ConnectionResetError):
                pass
        if propre:
            boucle = asyncio.get_running_loop()
            echeance = boucle.time() + SORTIE_PROPRE_S
            while processus.returncode is None and boucle.time() < echeance:
                await asyncio.sleep(0.01)
        arrete = await terminate_process_tree(processus.process, ARRET_GRACE_S)
    except Exception:  # noqa: BLE001 - un arrêt non prouvé reste un échec, jamais une exception
        arrete = False
    finally:
        try:
            processus.close_fence()
        except Exception:  # noqa: BLE001
            arrete = False
        if taches:
            await asyncio.wait(taches, timeout=1.0)
            for tache in taches:
                tache.cancel()
            await asyncio.gather(*taches, return_exceptions=True)
    return arrete


class Session:
    """Une session JSON-RPC (JSONL sur stdio, sans en-tête ``jsonrpc``) avec un app-server lancé par le poste."""

    def __init__(self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path | str,
                 interactive: bool = False) -> None:
        self.argv = list(argv)
        self.env = dict(env)
        self.cwd = cwd
        self.interactive = interactive
        self.methodes_envoyees: list[str] = []
        self.requetes_du_serveur = 0
        self._processus: FencedProcess | None = None
        self._taches: list[asyncio.Task] = []
        self._attentes: dict[int, tuple[str, asyncio.Future]] = {}
        self._notifications: dict[str, asyncio.Future] = {}
        self._compteur = itertools.count(1)
        self._erreur: BaseException | None = None
        self.arret_confirme: bool | None = None

    # ------------------------------------------------------------------ cycle de vie
    async def __aenter__(self) -> "Session":
        self._processus = await spawn_fenced_process(
            self.argv, cwd=self.cwd, env=self.env, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=LIGNE_MAX)
        self._taches = [asyncio.create_task(self._lire()), asyncio.create_task(_vider(self._processus.stderr))]
        return self

    async def __aexit__(self, type_exc, exc, trace) -> None:
        processus, self._processus = self._processus, None
        if processus is None:
            return
        # Protégé contre l'annulation : l'arbre est arrêté même après un délai dépassé.
        self.arret_confirme = await asyncio.shield(arreter(processus, self._taches, propre=type_exc is None))
        if not self.arret_confirme and type_exc is None:
            raise ArretNonConfirme

    # ------------------------------------------------------------------ échanges
    def _admise(self, methode: str) -> bool:
        return methode in METHODES_ADMISES or (self.interactive and methode in METHODES_INTERACTIVES)

    async def _envoyer(self, message: dict[str, Any]) -> None:
        processus = self._processus
        if processus is None or processus.stdin is None:
            raise SessionFermee
        processus.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            await processus.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise SessionFermee from exc

    async def appeler(self, methode: str, params: Any = None, *, avec_params: bool = True) -> dict[str, Any]:
        """Envoie ``methode`` (refusée avant l'envoi si elle n'est pas admise) et rend son résultat (objet)."""

        if not self._admise(methode):
            raise MethodeRefusee(methode)
        if self._erreur is not None:
            raise self._erreur
        identifiant = next(self._compteur)
        attente: asyncio.Future = asyncio.get_running_loop().create_future()
        self._attentes[identifiant] = (methode, attente)
        message: dict[str, Any] = {"id": identifiant, "method": methode}
        if avec_params:
            message["params"] = {} if params is None else params
        self.methodes_envoyees.append(methode)
        await self._envoyer(message)
        return await attente

    async def notifier(self, methode: str = "initialized") -> None:
        if methode not in NOTIFICATIONS_ADMISES:
            raise MethodeRefusee(methode)
        self.methodes_envoyees.append(methode)
        await self._envoyer({"method": methode})

    async def attendre_notification(self, methode: str) -> dict[str, Any]:
        """Paramètres de la prochaine notification ``methode`` (ex. ``windowsSandbox/setupCompleted``)."""
        attente = self._notifications.get(methode)
        if attente is None or attente.done():
            attente = asyncio.get_running_loop().create_future()
            self._notifications[methode] = attente
        return await attente

    async def initialiser(self) -> dict[str, Any]:
        resultat = await self.appeler("initialize", {"clientInfo": dict(CLIENT)})
        await self.notifier("initialized")
        return resultat

    # ------------------------------------------------------------------ lecture
    def _echouer(self, erreur: BaseException) -> None:
        self._erreur = erreur
        for _methode, attente in self._attentes.values():
            if not attente.done():
                attente.set_exception(erreur)
        self._attentes.clear()
        for attente in self._notifications.values():
            if not attente.done():
                attente.set_exception(erreur)

    async def _lire(self) -> None:
        processus = self._processus
        flux = processus.stdout if processus is not None else None
        if flux is None:
            self._echouer(SessionFermee())
            return
        while True:
            try:
                ligne = await flux.readline()
            except (ValueError, asyncio.LimitOverrunError):
                self._echouer(ReponseMalFormee())
                return
            except (OSError, asyncio.CancelledError):
                self._echouer(SessionFermee())
                return
            if not ligne:
                self._echouer(SessionFermee())
                return
            if not ligne.strip():
                continue
            try:
                message = json.loads(ligne.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                self._echouer(ReponseMalFormee())
                return
            if not isinstance(message, dict):
                self._echouer(ReponseMalFormee())
                return
            if "method" in message and "id" in message:
                # Requête du serveur (dont account/chatgptAuthTokens/refresh) : jamais servie.
                self.requetes_du_serveur += 1
                try:
                    await self._envoyer({"id": message["id"], "error": dict(ERREUR_NON_PRISE_EN_CHARGE)})
                except SessionFermee:
                    pass
                continue
            if "method" in message:
                attente = self._notifications.get(str(message["method"]))
                if attente is not None and not attente.done():
                    params = message.get("params")
                    attente.set_result(params if isinstance(params, dict) else {})
                continue
            identifiant = message.get("id")
            if type(identifiant) is not int or identifiant not in self._attentes:
                continue
            methode, attente = self._attentes.pop(identifiant)
            if attente.done():
                continue
            if "error" in message:
                erreur = message["error"]
                attente.set_exception(ErreurRpc(methode, erreur.get("code") if isinstance(erreur, dict) else None))
                continue
            resultat = message.get("result")
            if not isinstance(resultat, dict):
                attente.set_exception(ReponseMalFormee())
                continue
            attente.set_result(resultat)
