"""Fournisseur du jeton machine du poste (étape P5, cahier P5 § 4.2), sur le modèle du greffon ``drain`` de
Hermes (plugins/dashboard_auth/drain/__init__.py:68-94, 138-157) : un ``DashboardAuthProvider`` à jeton seulement,
enregistré par ``ctx.register_dashboard_auth_provider``, et trois chemins EXACTS enregistrés par
``register_token_route`` (aucun paramètre de chemin : la couture compare le chemin à l'identique).

:meth:`FournisseurJetonMachine.verify_token` :

1. forme : ``acpm_`` + 43 caractères base64url (jeton machine, portée ``machine``) ou ``acpe_`` + 43 (code
   d'enrôlement, portée ``enrolement``) ; sinon ``None`` sans ouvrir la base (un jeton OIDC n'est pas le nôtre) ;
2. SHA-256 du porteur ;
3. lecture SEULE de la base du greffon (connexion ``mode=ro`` dédiée, délai 0,25 s) ; TOUTE exception de
   lecture ou de calcul devient ``ProviderError`` (503) : une exception brute serait avalée par la couture et
   deviendrait un 401 (token_auth.py:66-69), que le poste prendrait pour une révocation ;
4. comparaison par ``hmac.compare_digest`` sur CHAQUE ligne candidate (postes non révoqués, codes utilisables),
   sans sortie anticipée ;
5. ``TokenPrincipal("acp-poste:<machine>", "acp-poste-machine", ("machine",))`` ou
   ``TokenPrincipal("enrolement:<12 hex>", "acp-poste-machine", ("enrolement",))``.

Base absente, ou table absente (schéma v2 pas encore posé) : aucun jeton n'a pu être émis, donc ``None`` (401).
Jamais de jeton ni de code dans un journal : seules les empreintes sont comparées. Ce module n'est importé que par
le paquet du greffon et par ``dashboard/plugin_api.py`` (jamais par un worker kanban).
"""

from __future__ import annotations

import hmac
import logging
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

from . import auth_adapter as aa
from . import base, contrat_partage  # noqa: F401 — contrat_partage met le contrat sur sys.path

from acp_poste_contrat.machine import (  # noqa: E402
    CODE_ENROLEMENT,
    JETON_MACHINE,
    ROUTES,
    empreinte_jeton,
)

_log = logging.getLogger(__name__)

NOM = "acp-poste-machine"
PORTEE_MACHINE = "machine"
PORTEE_ENROLEMENT = "enrolement"
DELAI_LECTURE_S = 0.25


class FournisseurJetonMachine(aa.DashboardAuthProvider):
    """Jeton machine du poste ACP : jamais offert sur la page de connexion (``supports_session = False``)."""

    name = NOM
    display_name = "Poste ACP (jeton machine)"
    supports_password = False
    supports_token = True
    supports_session = False
    _NON_INTERACTIF = "Le jeton machine du poste ACP n'a pas de connexion interactive."

    def __init__(self, chemin_base: Optional[Callable[[], Path]] = None) -> None:
        self._chemin_base = chemin_base or base.chemin_base

    # ---- capacité à jeton : la seule que ce fournisseur implémente

    def verify_token(self, *, token: str) -> Optional[aa.TokenPrincipal]:
        try:
            return self._verifier(token)
        except aa.ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 — 503 et jamais un 401 ambigu (cahier P5 § 4.2, point 3)
            raise aa.ProviderError(f"acp-poste : base du greffon illisible ({type(exc).__name__})") from None

    def _verifier(self, token: str) -> Optional[aa.TokenPrincipal]:
        if not isinstance(token, str):
            return None
        if JETON_MACHINE.fullmatch(token):
            portee = PORTEE_MACHINE
        elif CODE_ENROLEMENT.fullmatch(token):
            portee = PORTEE_ENROLEMENT
        else:
            return None
        calcule = empreinte_jeton(token)
        lignes = self._candidats(portee)
        trouve = None
        for identifiant, empreinte in lignes:
            # Chaque ligne est comparée, sans sortie anticipée.
            if hmac.compare_digest(calcule, str(empreinte)) and trouve is None:
                trouve = identifiant
        if trouve is None:
            return None
        if portee == PORTEE_MACHINE:
            return aa.TokenPrincipal(principal=f"acp-poste:{trouve}", provider=NOM, scopes=(PORTEE_MACHINE,))
        return aa.TokenPrincipal(principal=f"enrolement:{calcule[:12]}", provider=NOM, scopes=(PORTEE_ENROLEMENT,))

    def _candidats(self, portee: str):
        chemin = Path(self._chemin_base())
        if not chemin.is_file():
            return []
        uri = f"file:{urllib.parse.quote(str(chemin))}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=DELAI_LECTURE_S, isolation_level=None)
        try:
            try:
                if portee == PORTEE_MACHINE:
                    return conn.execute("SELECT id, empreinte_jeton FROM machines WHERE etat IN "
                                        "('a_confirmer', 'actif')").fetchall()
                return conn.execute("SELECT empreinte_code, empreinte_code FROM enrolements WHERE utilise_le IS NULL "
                                    "AND expire_le > ?", (base.maintenant(),)).fetchall()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc):
                    return []
                raise
        finally:
            conn.close()

    # ---- méthodes interactives : sans objet (même motif que drain)

    def start_login(self, *, redirect_uri: str):
        raise NotImplementedError(self._NON_INTERACTIF)

    def complete_login(self, *, code: str, state: str, code_verifier: str, redirect_uri: str):
        raise NotImplementedError(self._NON_INTERACTIF)

    def verify_session(self, *, access_token: str) -> Optional[aa.Session]:
        return None

    def refresh_session(self, *, refresh_token: str):
        raise NotImplementedError(self._NON_INTERACTIF)

    def revoke_session(self, *, refresh_token: str) -> None:
        return None


AUCUNE_SESSION = ("acp-poste : aucun fournisseur de session (OIDC) enregistré : le fournisseur du jeton machine "
                  "n'est PAS enregistré. Sans aucun fournisseur, Hermes refuse de servir un tableau de bord public "
                  "(web_server.py:1134-1144) : personne ne pourrait s'y connecter. Vérifiez les variables OIDC et le "
                  "greffon self-hosted (relecture de P5, décision D69).")


def enregistrer(ctx) -> bool:
    """Fournisseur et trois chemins exacts, SEULEMENT si un fournisseur de session (OIDC) est déjà enregistré
    (relecture de P5, décision D69) : la porte de démarrage de Hermes ne refuse de servir que si AUCUN fournisseur
    n'existe, et le nôtre, à jeton seulement, lui aurait suffi. ``plugin.yaml`` déclare ``requires_plugins:
    [self-hosted]`` : le greffon OIDC se charge avant celui-ci (``resolve_plugin_load_order``). Sans fournisseur de
    session, rien n'est enregistré (les routes du poste répondent 401) et Hermes refuse de démarrer, comme avant P5.
    Appelé dans TOUT processus par ``register()`` : idempotent, inerte hors du tableau de bord ; ``/v1/meta``
    vérifie dans le processus du tableau de bord que tout est en place. Rend vrai si le fournisseur est enregistré."""
    if not aa.list_session_providers():
        _log.error(AUCUNE_SESSION)
        return False
    ctx.register_dashboard_auth_provider(FournisseurJetonMachine())
    for chemin in ROUTES:
        aa.register_token_route(chemin)
    return True


def etat_dans_ce_processus() -> dict:
    """Bloc de ``/v1/meta`` : fournisseur enregistré ? chemins à jeton en place ? fournisseurs de session ?"""
    jetons = [p for p in aa.list_token_providers() if getattr(p, "name", None) == NOM]
    chemins = {chemin: bool(aa.is_token_route(chemin)) for chemin in ROUTES}
    sessions = [getattr(p, "name", "?") for p in aa.list_session_providers()]
    return {"fournisseur": "enregistre" if jetons else "absent", "chemins_a_jeton": chemins,
            "fournisseurs_de_session": sessions}
