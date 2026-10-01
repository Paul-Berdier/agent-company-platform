"""Adaptateur d'authentification du noyau (étape P5, cahier P5 § 14.3) : chaque nom vient de son module de
définition de Hermes 0.21.5 (jamais du pointeur PLUGIN-COMPAT de middleware.py), et seuls les deux adaptateurs du
noyau importent Hermes."""

from __future__ import annotations

import ast
from pathlib import Path

GREFFON = Path("/opt/hermes/plugins/acp-poste")


def test_chaque_nom_vient_de_son_module_de_definition(noyau):
    from noyau import auth_adapter as aa

    for nom, attendu in aa.MODULES_DE_DEFINITION.items():
        assert getattr(aa, nom).__module__ == attendu, (nom, getattr(aa, nom).__module__)
    assert {m for m in aa.MODULES_DE_DEFINITION.values()} == {
        "hermes_cli.dashboard_auth.base", "hermes_cli.dashboard_auth.token_auth", "hermes_cli.dashboard_auth.registry"}


def test_l_adaptateur_n_importe_que_dashboard_auth():
    arbre = ast.parse((GREFFON / "noyau" / "auth_adapter.py").read_text(encoding="utf-8"))
    modules = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            modules.add(noeud.module)
        elif isinstance(noeud, ast.Import):
            modules.update(a.name for a in noeud.names)
    assert modules == {"__future__", "hermes_cli.dashboard_auth.base", "hermes_cli.dashboard_auth.registry",
                       "hermes_cli.dashboard_auth.token_auth"}
    assert "middleware" not in (GREFFON / "noyau" / "auth_adapter.py").read_text(encoding="utf-8").split('"""')[2]


def test_scan_de_compatibilite_vide():
    from hermes_cli.plugin_compat import scan_plugin

    constats = scan_plugin(GREFFON)
    assert not constats, constats
