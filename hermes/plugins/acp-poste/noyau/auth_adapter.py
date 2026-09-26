"""Adaptateur d'authentification du noyau d'acp-poste (étape P5) : SEUL module du noyau, avec
:mod:`kanban_adapter`, qui importe l'interne de Hermes — et seulement ``hermes_cli.dashboard_auth``.

Chaque nom est importé depuis son MODULE DE DÉFINITION à la version épinglée (0.21.5, commit f97608f) :
``hermes_cli.dashboard_auth.base`` (protocole des fournisseurs), ``.token_auth`` (couture des chemins à jeton) et
``.registry`` (fournisseurs enregistrés, lus par ``/v1/meta``) ; jamais ``hermes_cli.dashboard_auth.middleware``,
qui porte un bloc de pointeurs PLUGIN-COMPAT (middleware.py:232-251). ``test_auth_adapter.py`` compare
``__module__`` à :data:`MODULES_DE_DEFINITION` et le workflow image.yml lance ``hermes plugins compat`` sur tout le
dossier du greffon.

Mécanisme (cahier P5 § 1.1, § 4.2) : un chemin n'accepte un jeton que s'il est enregistré À L'IDENTIQUE par
``register_token_route`` (token_auth.py:27-40) ; sur ce chemin, la couture décide seule (principal attaché, sinon
401, ou 503 si un fournisseur est injoignable), sans jamais retomber sur le cookie (token_auth.py:75-96).
"""

from __future__ import annotations

from hermes_cli.dashboard_auth.base import (
    DashboardAuthProvider,
    ProviderError,
    Session,
    TokenPrincipal,
    assert_protocol_compliance,
)
from hermes_cli.dashboard_auth.registry import list_session_providers, list_token_providers
from hermes_cli.dashboard_auth.token_auth import is_token_route, register_token_route

MODULES_DE_DEFINITION = {
    "DashboardAuthProvider": "hermes_cli.dashboard_auth.base",
    "ProviderError": "hermes_cli.dashboard_auth.base",
    "Session": "hermes_cli.dashboard_auth.base",
    "TokenPrincipal": "hermes_cli.dashboard_auth.base",
    "assert_protocol_compliance": "hermes_cli.dashboard_auth.base",
    "list_session_providers": "hermes_cli.dashboard_auth.registry",
    "list_token_providers": "hermes_cli.dashboard_auth.registry",
    "is_token_route": "hermes_cli.dashboard_auth.token_auth",
    "register_token_route": "hermes_cli.dashboard_auth.token_auth",
}

__all__ = ["MODULES_DE_DEFINITION", *MODULES_DE_DEFINITION]
