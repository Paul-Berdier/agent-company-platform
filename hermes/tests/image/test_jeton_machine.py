"""Fournisseur du jeton machine (étape P5, cahier P5 § 4.2, § 14.3) contre le protocole de Hermes 0.21.5 : forme,
condensat seul en base, comparaison à temps constant sur chaque ligne, lecture seule d'une base WAL, toute panne en
503 (jamais un 401 ambigu), rapidité, jamais journalisé ; enregistrement par register() et chemins exacts."""

from __future__ import annotations

import logging
import os
import sqlite3
import time

import pytest

from conftest import env_processus, executer_python, installer_home_de_test, poste_confirme

from acp_poste_contrat.machine import PROTOCOLE, ROUTES, empreinte_jeton  # noqa: E402


@pytest.fixture
def jm(noyau):
    from noyau import jeton_machine

    return jeton_machine


def _fournisseur(jm):
    return jm.FournisseurJetonMachine()


def test_conformite_du_protocole(jm):
    from hermes_cli.dashboard_auth.base import DashboardAuthProvider, assert_protocol_compliance

    assert_protocol_compliance(jm.FournisseurJetonMachine)
    fournisseur = _fournisseur(jm)
    assert isinstance(fournisseur, DashboardAuthProvider)
    assert (fournisseur.name, fournisseur.supports_token, fournisseur.supports_session,
            fournisseur.supports_password) == ("acp-poste-machine", True, False, False)
    assert fournisseur.verify_session(access_token="x") is None and fournisseur.revoke_session(refresh_token="x") is None
    for methode, arguments in (("start_login", {"redirect_uri": "x"}), ("refresh_session", {"refresh_token": "x"}),
                               ("complete_login", {"code": "c", "state": "s", "code_verifier": "v",
                                                   "redirect_uri": "x"})):
        with pytest.raises(NotImplementedError):
            getattr(fournisseur, methode)(**arguments)


def test_bon_jeton_principal_machine(jm, noyau, conn):
    machine, jeton = poste_confirme(noyau, conn)
    principal = _fournisseur(jm).verify_token(token=jeton)
    assert (principal.principal, principal.provider, principal.scopes) == (
        f"acp-poste:{machine}", "acp-poste-machine", ("machine",))


def test_poste_a_confirmer_reconnu(jm, noyau, conn):
    code = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    with noyau.base.transaction(conn):
        reponse = noyau.machines.enroler_dans(conn, empreinte_jeton(code), nom="P", version_poste="0.11.0",
                                              protocole=PROTOCOLE)
    principal = _fournisseur(jm).verify_token(token=reponse["jeton"])
    assert principal.principal == f"acp-poste:{reponse['machine_id']}" and principal.scopes == ("machine",)


def test_code_principal_enrolement(jm, noyau, conn):
    code = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    principal = _fournisseur(jm).verify_token(token=code)
    assert principal.principal == f"enrolement:{empreinte_jeton(code)[:12]}" and principal.scopes == ("enrolement",)
    with noyau.base.transaction(conn):
        noyau.machines.enroler_dans(conn, empreinte_jeton(code), nom="P", version_poste="0.11.0", protocole=PROTOCOLE)
    assert _fournisseur(jm).verify_token(token=code) is None  # usage unique
    code2 = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    debut = noyau.base.maintenant()
    noyau.base.fixer_horloge(lambda: debut + 601)
    assert _fournisseur(jm).verify_token(token=code2) is None  # expiré


def test_jeton_revoque_none(jm, noyau, conn):
    machine, jeton = poste_confirme(noyau, conn)
    noyau.machines.revoquer(conn, machine, "essai", "proprietaire:test")
    assert _fournisseur(jm).verify_token(token=jeton) is None


def test_forme_invalide_none_sans_base(jm, noyau, conn, monkeypatch):
    ouvertures = []
    monkeypatch.setattr(jm.sqlite3, "connect", lambda *a, **k: ouvertures.append(a) or (_ for _ in ()).throw(
        AssertionError("base ouverte")))
    fournisseur = _fournisseur(jm)
    for porteur in ("", "abc", "acpm_court", "acpm_" + "x" * 44, "eyJhbGciOiJSUzI1NiJ9.e30.c2ln", "Bearer acpm_",
                    None, 12):
        assert fournisseur.verify_token(token=porteur) is None
    assert ouvertures == []


def test_base_absente_ou_sans_tables_none(jm, tmp_path):
    fournisseur = jm.FournisseurJetonMachine(chemin_base=lambda: tmp_path / "absente.db")
    jeton = "acpm_" + "A" * 43
    assert fournisseur.verify_token(token=jeton) is None
    vide = tmp_path / "vide.db"
    sqlite3.connect(vide).close()
    assert jm.FournisseurJetonMachine(chemin_base=lambda: vide).verify_token(token=jeton) is None


def test_comparaison_a_temps_constant(jm, noyau, conn, monkeypatch):
    """Autant d'appels à compare_digest que de lignes candidates, même quand la première correspond."""
    machine, jeton = poste_confirme(noyau, conn)
    # Deux postes à confirmer de plus (lignes candidates), écrits directement.
    with noyau.base.transaction(conn):
        for i in (1, 2):
            conn.execute("INSERT INTO machines (id, nom, empreinte_jeton, etat, protocole, version_poste, cree_le) "
                         "VALUES (?, 'x', ?, 'a_confirmer', 'acp-machine/1', '0.11.0', 0)",
                         (f"m0000000000{i}", str(i) * 64))
    appels = []

    class Espion:
        @staticmethod
        def compare_digest(a, b):
            appels.append(b)
            import hmac

            return hmac.compare_digest(a, b)
    monkeypatch.setattr(jm, "hmac", Espion)
    candidats = conn.execute("SELECT COUNT(*) FROM machines WHERE etat IN ('a_confirmer', 'actif')").fetchone()[0]
    assert candidats == 3
    assert _fournisseur(jm).verify_token(token=jeton).principal == f"acp-poste:{machine}"
    assert len(appels) == candidats
    appels.clear()
    assert _fournisseur(jm).verify_token(token="acpm_" + "Z" * 43) is None
    assert len(appels) == candidats


def test_base_illisible_provider_error(jm, tmp_path):
    from hermes_cli.dashboard_auth.base import ProviderError

    corrompue = tmp_path / "corrompue.db"
    corrompue.write_bytes(b"ceci n'est pas une base SQLite" * 100)
    with pytest.raises(ProviderError, match="base du greffon illisible"):
        jm.FournisseurJetonMachine(chemin_base=lambda: corrompue).verify_token(token="acpm_" + "A" * 43)


def test_exception_interne_devient_provider_error(jm, noyau, conn, monkeypatch):
    """Toute exception brute deviendrait un 401 dans la couture (token_auth.py:66-69) : elle devient un 503."""
    from hermes_cli.dashboard_auth.base import ProviderError
    from hermes_cli.dashboard_auth import token_auth

    poste_confirme(noyau, conn)
    monkeypatch.setattr(jm.FournisseurJetonMachine, "_candidats", lambda self, portee: 1 / 0)
    fournisseur = _fournisseur(jm)
    with pytest.raises(ProviderError):
        fournisseur.verify_token(token="acpm_" + "A" * 43)
    # Dans la couture réelle : « injoignable » (503), jamais « non reconnu » (401).
    monkeypatch.setattr(token_auth, "list_token_providers", lambda: [fournisseur])

    class Requete:
        headers = {"authorization": "Bearer acpm_" + "A" * 43}
        cookies = {}
    principal, injoignable = token_auth.authenticate_token(Requete())
    assert principal is None and injoignable == "acp-poste-machine"


def test_verify_token_base_wal_lecture_seule(jm, noyau, conn):
    """Lecture seule d'une base en WAL pendant qu'un écrivain tient une transaction ouverte (SQLite ≥ 3.22)."""
    machine, jeton = poste_confirme(noyau, conn)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    autre = sqlite3.connect(noyau.base.chemin_base(), isolation_level=None)
    try:
        autre.execute("BEGIN IMMEDIATE")
        autre.execute("INSERT INTO journal (quand, acteur, action) VALUES (0, 't', 'ecrivain')")
        debut = time.monotonic()
        assert _fournisseur(jm).verify_token(token=jeton).principal == f"acp-poste:{machine}"
        assert time.monotonic() - debut < 0.25  # un lecteur n'attend pas l'écrivain
        autre.execute("ROLLBACK")
    finally:
        autre.close()
    assert sqlite3.sqlite_version_info >= (3, 22, 0)


def test_verify_token_rapide(jm, noyau, conn):
    machine, jeton = poste_confirme(noyau, conn)
    fournisseur = _fournisseur(jm)
    durees = []
    for i in range(1000):
        debut = time.perf_counter()
        fournisseur.verify_token(token=jeton if i % 2 else "acpm_" + "B" * 43)
        durees.append(time.perf_counter() - debut)
    durees.sort()
    p99 = durees[989]
    print(f"\nverify_token : p50 {durees[500] * 1000:.3f} ms, p99 {p99 * 1000:.3f} ms sur 1 000 appels")
    assert p99 < 0.020


def test_jamais_journalise(jm, noyau, conn, caplog):
    machine, jeton = poste_confirme(noyau, conn)
    caplog.set_level(logging.DEBUG)
    fournisseur = _fournisseur(jm)
    fournisseur.verify_token(token=jeton)
    fournisseur.verify_token(token="acpm_" + "C" * 43)
    assert jeton not in caplog.text and "acpm_" not in caplog.text
    journal = " ".join(str(l[0]) for l in conn.execute("SELECT detail FROM journal"))
    assert "acpm_" not in journal and "acpe_" not in journal


_CODE_REGISTER = r"""
import importlib.util, logging, os, sys
AVEC_SESSION = __AVEC_SESSION__
messages = []
class Collecteur(logging.Handler):
    def emit(self, record): messages.append([record.levelname, record.getMessage()])
if AVEC_SESSION:
    # Fournisseur de session factice, comme celui du greffon self-hosted quand il se charge avant (cas d'école :
    # en vrai, acp-poste se charge AVANT lui, voir test_decouverte_reelle_charge_acp_poste_avant_l_oidc).
    from hermes_cli.dashboard_auth.base import DashboardAuthProvider
    from hermes_cli.dashboard_auth.registry import register_global_provider
    class Session(DashboardAuthProvider):
        name = "session-test"
        display_name = "Session de test"
        def start_login(self, *, redirect_uri): raise NotImplementedError
        def complete_login(self, *, code, state, code_verifier, redirect_uri): raise NotImplementedError
        def verify_session(self, *, access_token): return None
        def refresh_session(self, *, refresh_token): raise NotImplementedError
        def revoke_session(self, *, refresh_token): return None
    register_global_provider(Session())
spec = importlib.util.spec_from_file_location("acp_test_p5", "/opt/hermes/plugins/acp-poste/__init__.py",
                                              submodule_search_locations=["/opt/hermes/plugins/acp-poste"])
module = importlib.util.module_from_spec(spec)
sys.modules["acp_test_p5"] = module
spec.loader.exec_module(module)
class Contexte:
    def __init__(self): self.fournisseurs = []
    def register_hook(self, *a): pass
    def register_tool(self, **k): pass
    def register_system_prompt_section(self, *a, **k): pass
    def register_dashboard_auth_provider(self, fournisseur): self.fournisseurs.append(fournisseur)
ctx = Contexte()
# Journal du greffon (loggers « acp_test_p5.* ») relevé juste avant register(), après tout réglage de Hermes.
journal = logging.getLogger("acp_test_p5")
journal.disabled = False
journal.setLevel(logging.WARNING)
journal.addHandler(Collecteur(level=logging.WARNING))
module.register(ctx)
from hermes_cli.dashboard_auth.token_auth import is_token_route
chemins = ["/api/plugins/acp-poste/machine/v1/enrolement", "/api/plugins/acp-poste/machine/v1/reclamer",
           "/api/plugins/acp-poste/machine/v1/inventaire"]
resultat = [[(f.name, f.supports_token, f.supports_session) for f in ctx.fournisseurs],
            [is_token_route(c) for c in chemins],
            [is_token_route(c + "/") for c in chemins] + [is_token_route("/api/plugins/acp-poste/machine/v1/battement"),
             is_token_route("/api/plugins/acp-poste/v1/poste")],
            messages]
"""


def test_register_enregistre_le_fournisseur_et_les_chemins_exacts(noyau):
    code = _CODE_REGISTER.replace("__AVEC_SESSION__", "True")
    fournisseurs, exacts, autres, messages = executer_python(code, env=dict(os.environ, HERMES_HOME=str(noyau.home)))
    assert fournisseurs == [["acp-poste-machine", True, False]]
    assert exacts == [True, True, True]
    assert autres == [False] * 5  # chemin exact seulement ; routes P6 et routes du propriétaire jamais à jeton
    assert list(ROUTES) == ["/api/plugins/acp-poste/machine/v1/enrolement", "/api/plugins/acp-poste/machine/v1/reclamer",
                            "/api/plugins/acp-poste/machine/v1/inventaire"]
    assert [m for m in messages if m[0] == "ERROR"] == []


def test_register_sans_fournisseur_de_session_enregistre_quand_meme(noyau):
    """Relecture de P5 (décision D69, révisée) : à l'appel de register(), le fournisseur OIDC n'est JAMAIS encore là
    (acp-poste se charge avant lui, test suivant). Subordonner l'enregistrement à sa présence retirait le jeton
    machine de tout déploiement réel : le fournisseur et ses trois chemins s'enregistrent donc sans condition, sans
    erreur au journal."""
    code = _CODE_REGISTER.replace("__AVEC_SESSION__", "False")
    fournisseurs, exacts, autres, messages = executer_python(code, env=dict(os.environ, HERMES_HOME=str(noyau.home)))
    assert fournisseurs == [["acp-poste-machine", True, False]]
    assert exacts == [True, True, True] and autres == [False] * 5
    assert [m for m in messages if m[0] == "ERROR"] == []


def test_decouverte_reelle_charge_acp_poste_avant_l_oidc(chemins, valeurs):
    """Pourquoi aucun contrôle « fournisseur de session présent » n'est possible dans register() : Hermes charge les
    greffons groupés de type backend dès leur tri (gate_manifest → load_now), dans l'ordre alphabétique des dossiers,
    sans passer par resolve_plugin_load_order (requires_plugins n'y change rien). Vraie découverte, managed scope
    d'ACP avec l'OIDC configuré : les deux fournisseurs sont là au bout du compte, acp-poste-machine enregistré le
    premier, et les chemins du poste sont à jeton."""
    installer_home_de_test(chemins, valeurs)
    code = r"""
import sys
from pathlib import Path
from hermes_cli.plugins import discover_plugins
from hermes_cli.plugins_discovery import gate_manifest
from hermes_cli.plugins_manifest import parse_manifest_file
discover_plugins()
from hermes_cli.dashboard_auth.registry import list_providers
from hermes_cli.dashboard_auth.token_auth import is_token_route
greffon = Path("/opt/hermes/plugins/acp-poste")
oidc = Path("/opt/hermes/plugins/dashboard_auth/self_hosted")
manifestes = [parse_manifest_file(greffon / "plugin.yaml", greffon, "bundled", ""),
              parse_manifest_file(oidc / "plugin.yaml", oidc, "bundled", "dashboard_auth")]
resultat = [[[p.name, bool(getattr(p, "supports_session", True))] for p in list_providers()],
            [is_token_route(c) for c in ("/api/plugins/acp-poste/machine/v1/enrolement",
                                         "/api/plugins/acp-poste/machine/v1/reclamer",
                                         "/api/plugins/acp-poste/machine/v1/inventaire")],
            [gate_manifest(m, set(), None).action for m in manifestes],
            [m.requires_plugins for m in manifestes]]
"""
    fournisseurs, chemins_a_jeton, actions, dependances = executer_python(code, env=env_processus(chemins))
    noms = [nom for nom, _ in fournisseurs]
    sessions = [nom for nom, session in fournisseurs if session]
    assert "acp-poste-machine" in noms and sessions == ["self-hosted"], fournisseurs
    assert noms.index("acp-poste-machine") < noms.index("self-hosted")
    assert chemins_a_jeton == [True, True, True]
    assert actions == ["load_now", "load_now"]
    assert not dependances[0]  # requires_plugins retiré : il n'ordonnait rien pour un greffon groupé
