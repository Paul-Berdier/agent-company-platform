"""Étape P2 : l'agent n'a AUCUN outil d'exécution (ni terminal, ni fichiers, ni code, ni
navigateur, ni cron, ni délégation). Tests exécutés DANS l'image de test, contre le code de
Hermes à la version épinglée.

Trois couches, prouvées séparément puis ensemble :
1. listes de la managed scope (agent.disabled_toolsets, platform_toolsets) ;
2. épingles de /etc/hermes/.env ;
3. crochet pre_tool_call en liste blanche d'acp-poste (garde_execution.py), seul verrou de
   preview.restart.

Les tours d'agent tournent dans des PROCESSUS NEUFS (hermes/tests/outils/agent_neuf.py,
``python -m tui_gateway.entry``) : aucune fixture n'appelle discover_plugins à la main, c'est
l'AIAgent qui découvre lui-même les greffons (agent/agent_init.py:1060-1065). Chaque test
positif a son témoin négatif : sans la couche testée, l'outil s'exécute vraiment (un fichier
apparaît dans /tmp/acp-temoins). Le test du chemin preview.restart est BLOQUANT : il n'est
jamais marqué ignoré.
"""

from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

import pytest

import garde_execution as ge
from conftest import OUTILS, PYTHON_HERMES, env_processus, executer_python, installer_home_de_test, lancer_outil

OUTILS_INTERDITS = {
    "terminal", "process_manage", "read_file", "write_file", "patch", "search_files", "execute_code",
    "computer_use", "manage_connections", "cronjob_manage", "delegate_task", "manage_catalog",
}
SURFACES = ("api_server", "cli", "cron", "tableau_de_bord_tui", "tableau_de_bord_desktop", "worker_kanban",
            "enfant_delegation")

CONFIG_HOSTILE = """\
toolsets: [hermes-cli, debugging, coding]
platform_toolsets:
  api_server: [web, debugging, hermes-api-server, terminal, file, code_execution]
  cli: [web, debugging, coding, hermes-cli, terminal, file, browser, delegation, cronjob]
  cron: [web, debugging, hermes-cli, terminal]
agent:
  disabled_toolsets: []
  coding_context: focus
cron:
  allow_agent_scheduling: true
"""

ENV_HOSTILE = """\
HERMES_TUI_TOOLSETS=terminal,file,code_execution
HERMES_BIN=/opt/data/faux-hermes
HERMES_ACCEPT_HOOKS=1
HERMES_SAFE_MODE=1
HERMES_YOLO_MODE=1
HERMES_COPILOT_ACP_COMMAND=/opt/data/faux-copilot
HERMES_COPILOT_ACP_ARGS=--intrus
COPILOT_CLI_PATH=/opt/data/faux-copilot
HERMES_ALLOW_PRIVATE_URLS=true
HERMES_DISABLE_LAZY_INSTALLS=0
"""


def _sonder(chemins, valeurs, *, config: str = "", env: str = "", scope: str = "") -> dict:
    """Outils offerts par chaque surface, calculés par Hermes dans un processus neuf."""
    installer_home_de_test(chemins, valeurs, config=config, env=env)
    if scope:
        (chemins.dossier_gere / "config.yaml").write_text(scope, encoding="utf-8")
        (chemins.dossier_gere / ".env").write_text("", encoding="utf-8")
    fichier = chemins.hermes_home.parent / "sonde.json"
    sortie = lancer_outil("sonde_surfaces.py", str(fichier), env=env_processus(chemins))
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    return json.loads(fichier.read_text(encoding="utf-8"))


# ============================================================ 1. listes de la managed scope


@pytest.mark.parametrize("volume", ["vide", "hostile"])
def test_aucune_surface_n_offre_d_outil_d_execution(chemins, valeurs, volume):
    config, env = ("", "") if volume == "vide" else (CONFIG_HOSTILE, ENV_HOSTILE)
    surfaces = _sonder(chemins, valeurs, config=config, env=env)
    print(json.dumps(surfaces, ensure_ascii=False, indent=1))
    assert set(surfaces) == set(SURFACES)
    for surface in SURFACES:
        offerts = set(surfaces[surface]["outils"])
        interdits = sorted(offerts & OUTILS_INTERDITS | {o for o in offerts if o.startswith("browser_")})
        assert interdits == [], f"{surface} offre {interdits}"
        # Aucun jeu n'est « tout » : une liste None rendrait tous les outils.
        assert surfaces[surface]["toolsets"] is not None, surface
    # Contrôle positif : les surfaces offrent bien des outils admis (sinon le test passerait à vide).
    for surface in ("api_server", "cli", "tableau_de_bord_tui", "worker_kanban"):
        assert {"web_search", "skills_list"} <= set(surfaces[surface]["outils"]), surface
    assert {"kanban_complete", "kanban_show"} <= set(surfaces["worker_kanban"]["outils"])
    # Étape P4 (D24) : les outils du greffon sur cli, le tableau de bord et les workers ; jamais sur
    # api_server ni cron (known_plugin_toolsets épinglé), même depuis un volume hostile.
    # Hermes DIFFÈRE les outils de greffon derrière tool_search / tool_call (tools/tool_search.py:150-162) :
    # ils sont dans le catalogue de la surface, pas dans sa liste directe.
    for surface in ("cli", "tableau_de_bord_tui", "tableau_de_bord_desktop", "worker_kanban"):
        assert "acp_poste" in surfaces[surface]["toolsets"] and "projet_etat" in surfaces[surface]["catalogue"], surface
        assert "tool_call" in surfaces[surface]["outils"], surface
    assert {"projet_planifier", "question_repondre"} <= set(surfaces["worker_kanban"]["catalogue"])
    assert "projet_lancer" not in surfaces["worker_kanban"]["catalogue"]
    assert "projet_lancer" in surfaces["cli"]["catalogue"] and "projet_planifier" not in surfaces["cli"]["catalogue"]
    for surface in ("api_server", "cron"):
        assert "acp_poste" not in surfaces[surface]["toolsets"], surface
        assert not set(OUTILS_DU_GREFFON) & set(surfaces[surface]["catalogue"]), surface
    for surface in SURFACES:
        interdits = set(surfaces[surface]["catalogue"]) & OUTILS_INTERDITS
        assert interdits == set(), f"{surface} diffère {interdits}"


def _sonder_avec(chemins, valeurs, remplacements) -> dict:
    installer_home_de_test(chemins, valeurs, remplacements=remplacements)
    fichier = chemins.hermes_home.parent / "sonde-p4.json"
    sortie = lancer_outil("sonde_surfaces.py", str(fichier), env=env_processus(chemins))
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    return json.loads(fichier.read_text(encoding="utf-8"))


def test_outils_acp_absents_d_api_server_et_cron(chemins, valeurs):
    """Décision D24 : les outils du greffon ne sont offerts ni par l'api_server ni par le cron, grâce aux
    épingles known_plugin_toolsets ; témoin négatif : sans elles, Hermes les active par défaut
    (hermes_cli/tools_config.py:538-545)."""
    avec = _sonder_avec(chemins, valeurs, ())
    assert {"projet_etat", "poste_etat", "poste_catalogue"} <= set(avec["cli"]["catalogue"])
    for surface in ("api_server", "cron"):
        assert not set(OUTILS_DU_GREFFON) & set(avec[surface]["catalogue"]), surface
    sans = _sonder_avec(chemins, valeurs, [("known_plugin_toolsets:\n  api_server: [acp_poste]\n  cron: [acp_poste]\n",
                                            "")])
    print(json.dumps({s: sans[s]["toolsets"] for s in ("api_server", "cron")}, ensure_ascii=False))
    for surface in ("api_server", "cron"):
        assert "projet_etat" in sans[surface]["catalogue"], surface


SCOPE_P1 = """\
agent:
  disabled_toolsets: [browser]
"""


def test_temoin_scope_p1_rend_terminal(chemins, valeurs):
    """Témoin négatif : avec la managed scope de P1 (navigateur seul retiré), les surfaces
    offrent bien terminal et fichiers. Sans ce témoin, le test précédent pourrait réussir pour
    une mauvaise raison (sonde cassée, outils introuvables)."""
    surfaces = _sonder(chemins, valeurs, scope=SCOPE_P1)
    for surface in ("api_server", "cli", "tableau_de_bord_tui", "worker_kanban"):
        assert {"terminal", "write_file"} <= set(surfaces[surface]["outils"]), surface


SCOPE_SANS_PLATFORM_TOOLSETS = """\
agent:
  disabled_toolsets: [browser, terminal, file, code_execution, computer_use, connections, cronjob, delegation, setup]
"""


def test_sans_platform_toolsets_un_composite_rend_terminal(chemins, valeurs):
    """Pourquoi platform_toolsets est épinglé : l'api_server et le tableau de bord ne passent PAS
    agent.disabled_toolsets à l'AIAgent. Un nom de jeu non configurable posé par le volume
    (composite « debugging », qui contient terminal) passe TEL QUEL dans la liste
    (tools_config.py:614-615 et 678-690) et survit à l'élagage de disabled_toolsets, parce que
    ses outils web y survivent (tools_config.py:635-651). Mesuré sur Hermes 0.21.5 : un composite
    seul (hermes-api-server) est, lui, ramené aux jeux configurables puis élagué."""
    surfaces = _sonder(chemins, valeurs, config=CONFIG_HOSTILE, scope=SCOPE_SANS_PLATFORM_TOOLSETS)
    assert "debugging" in surfaces["api_server"]["toolsets"]
    assert "terminal" in surfaces["api_server"]["outils"]
    assert "terminal" in surfaces["tableau_de_bord_tui"]["outils"]
    # Les surfaces qui transmettent disabled_toolsets, elles, le retirent.
    assert "terminal" not in surfaces["cli"]["outils"]


def test_coding_context_focus_neutralise(chemins, valeurs, monkeypatch):
    """« focus » réduirait les outils au jeu de codage (terminal et fichiers) : le volume hostile
    le demande, la managed scope impose « off »."""
    installer_home_de_test(chemins, valeurs, config=CONFIG_HOSTILE)
    code = ("from hermes_cli.config import load_config; from hermes_cli import managed_scope; "
            "c = load_config(); resultat = [c['agent']['coding_context'], "
            "managed_scope.is_key_managed('agent.coding_context'), c['agent']['disabled_toolsets']]")
    contexte, gere, retires = executer_python(code, env=env_processus(chemins))
    assert (contexte, gere) == ("off", True)
    assert {"terminal", "file", "code_execution", "browser"} <= set(retires)


# ============================================================ 2. épingles du .env géré


def test_env_gere_neutralise_le_volume(chemins, valeurs):
    """Les variables d'exécution posées dans /opt/data/.env sont ramenées à leur valeur d'image
    par /etc/hermes/.env, appliqué en dernier (env_loader.py:473 et 503-518)."""
    installer_home_de_test(chemins, valeurs, env=ENV_HOSTILE)
    noms = [ligne.split("=", 1)[0] for ligne in ENV_HOSTILE.splitlines() if ligne]
    code = ("import os; from hermes_cli.env_loader import load_hermes_dotenv; "
            "load_hermes_dotenv(hermes_home=os.environ['HERMES_HOME'], load_external_secrets=False); "
            f"resultat = {{n: os.environ.get(n) for n in {noms!r}}}")
    valeurs_lues = executer_python(code, env=env_processus(chemins))
    attendu = {n: "" for n in noms}
    attendu.update({"HERMES_ALLOW_PRIVATE_URLS": "false", "HERMES_DISABLE_LAZY_INSTALLS": "1"})
    assert valeurs_lues == attendu


# ============================================================ 3. tours d'agent réels


def _tour(chemins, valeurs, modele, mode: str, message: str, *, sans_garde: bool = False, config: str = "") -> dict:
    installer_home_de_test(chemins, valeurs, modele_url=modele.url, sans_garde=sans_garde, config=config)
    fichier = chemins.hermes_home.parent / f"agent-{mode}.json"
    sortie = lancer_outil("agent_neuf.py", mode, modele.url, message, str(fichier), env=env_processus(chemins))
    assert sortie.returncode == 0, sortie.stderr[-4000:]
    return json.loads(fichier.read_text(encoding="utf-8"))


@pytest.mark.parametrize("outil", ["terminal", "write_file", "execute_code", "cronjob_manage", "delegate_task",
                                   "read_file", "browser_navigate"])
def test_tour_api_server_refuse_terminal_ecriture_code_cron(chemins, valeurs, modele_factice, temoins, outil):
    resultat = _tour(chemins, valeurs, modele_factice, "api_server", f"OUTIL:{outil}")
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"offerts": resultat["outils_offerts"], "resultats": resultats}, ensure_ascii=False))
    assert outil not in resultat["outils_offerts"]
    assert any(f"Tool '{outil}' does not exist" in r for r in resultats), resultats
    assert list(temoins.iterdir()) == []


def test_pont_tool_call_non_resolu_refuse(chemins, valeurs, modele_factice, temoins):
    """Le pont tool_call vers terminal, qui n'est pas différable : Hermes NE PEUT PAS le résoudre
    (tools/tool_search.py:543-571), donc ne le déballe pas (agent/tool_executor.py:390-431) ; la
    garde reçoit « tool_call » lui-même et le refuse (il n'est pas dans la liste blanche). Ce test
    ne prouve que ce chemin d'erreur : le déballage est prouvé par les deux tests suivants."""
    resultat = _tour(chemins, valeurs, modele_factice, "api_server", "OUTIL:tool_call")
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"offerts": resultat["outils_offerts"], "resultats": resultats}, ensure_ascii=False))
    assert "tool_call" in resultat["outils_offerts"]
    assert any("Refusé par ACP : l'outil « tool_call » n'est pas autorisé" in r for r in resultats), resultats
    assert list(temoins.iterdir()) == []


def test_pont_tool_call_vers_un_outil_admis(chemins, valeurs, modele_factice, temoins):
    """Relecture P2 : Hermes déballe le pont AVANT le crochet ; la garde juge l'outil sous-jacent.
    todo_list, différé par défaut (config_defaults.py:1986-1988) donc absent des outils offerts,
    s'exécute à travers le pont sans aucun refus d'ACP."""
    resultat = _tour(chemins, valeurs, modele_factice, "api_server", "OUTIL:tool_call>todo_list")
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"offerts": resultat["outils_offerts"], "resultats": resultats}, ensure_ascii=False))
    assert "tool_call" in resultat["outils_offerts"] and "todo_list" not in resultat["outils_offerts"]
    assert not any("Refusé par ACP" in r for r in resultats), resultats
    assert any("carte de test ACP" in r and '"todos"' in r for r in resultats), resultats
    assert list(temoins.iterdir()) == []


# Volume qui rend terminal DIFFÉRABLE (tools.tool_search.defer remplace la liste par défaut ; un
# nom listé est différable même s'il est « cœur » : tools/tool_search.py:150-162). L'agent caché
# de preview.restart, qui reçoit terminal codé en dur, ne peut alors l'atteindre que par le pont.
CONFIG_TERMINAL_DIFFERE = """\
tools:
  tool_search:
    enabled: "on"
    defer: [terminal]
"""


def test_pont_tool_call_juge_l_outil_sous_jacent(chemins, valeurs, modele_factice, temoins):
    """Relecture P2 : tool_call → terminal RÉSOLU (terminal rendu différable par le volume) : la
    garde reçoit « terminal » (et non « tool_call ») et le refuse ; aucun témoin."""
    resultat = _tour(chemins, valeurs, modele_factice, "cache", "OUTIL:tool_call", config=CONFIG_TERMINAL_DIFFERE)
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"offerts": resultat["outils_offerts"], "resultats": resultats}, ensure_ascii=False))
    assert "tool_call" in resultat["outils_offerts"] and "terminal" not in resultat["outils_offerts"]
    assert any("Refusé par ACP : l'outil « terminal » n'est pas autorisé" in r for r in resultats), resultats
    assert not any("« tool_call »" in r for r in resultats), resultats
    assert list(temoins.iterdir()) == []


def test_pont_tool_call_juge_l_outil_sous_jacent_temoin_negatif(chemins, valeurs, modele_factice, temoins):
    """Témoin négatif : même scénario sans acp-poste → terminal s'exécute à travers le pont."""
    _tour(chemins, valeurs, modele_factice, "cache", "OUTIL:tool_call", sans_garde=True,
          config=CONFIG_TERMINAL_DIFFERE)
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"resultats": resultats}, ensure_ascii=False))
    assert not any("Refusé par ACP" in r for r in resultats)
    assert (temoins / "tool_call").exists(), "le témoin négatif n'a pas pu exécuter terminal par le pont"


def test_garde_dans_un_agent_neuf(chemins, valeurs, modele_factice, temoins):
    """L'agent caché de preview.restart (jeux terminal et fichiers codés en dur), construit dans
    un processus neuf SANS appel manuel à discover_plugins : la garde le refuse."""
    resultat = _tour(chemins, valeurs, modele_factice, "cache", "OUTIL:terminal")
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"offerts": resultat["outils_offerts"], "resultats": resultats}, ensure_ascii=False))
    assert "terminal" in resultat["outils_offerts"]  # seule la garde le ferme
    assert any("Refusé par ACP : l'outil « terminal »" in r for r in resultats), resultats
    assert list(temoins.iterdir()) == []


def test_garde_dans_un_agent_neuf_temoin_negatif(chemins, valeurs, modele_factice, temoins):
    """Témoin négatif : managed scope de test qui désactive acp-poste → l'outil s'exécute."""
    _tour(chemins, valeurs, modele_factice, "cache", "OUTIL:terminal", sans_garde=True)
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"resultats": resultats}, ensure_ascii=False))
    assert not any("Refusé par ACP" in r for r in resultats)
    assert (temoins / "terminal").exists(), "le témoin négatif n'a pas pu exécuter terminal"


# ================================================= 4. preview.restart par tui_gateway (BLOQUANT)


class PasserelleStdio:
    """``python -m tui_gateway.entry`` : JSON-RPC ligne par ligne sur stdin/stdout, comme le
    client Ink (tui_gateway/entry.py). Rien n'est simulé : c'est le vrai répartiteur."""

    def __init__(self, env: dict) -> None:
        self.processus = subprocess.Popen(
            [PYTHON_HERMES, "-m", "tui_gateway.entry"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd="/opt/hermes", env=env, text=True, bufsize=1)
        self.messages: "queue.Queue[dict]" = queue.Queue()
        self.recus: list = []
        self.erreurs: list = []
        threading.Thread(target=self._lire, daemon=True).start()
        threading.Thread(target=self._lire_erreurs, daemon=True).start()

    def _lire(self) -> None:
        for ligne in self.processus.stdout:
            try:
                self.messages.put(json.loads(ligne))
            except ValueError:
                continue

    def _lire_erreurs(self) -> None:
        for ligne in self.processus.stderr:
            self.erreurs.append(ligne)

    def envoyer(self, identifiant: int, methode: str, params: dict) -> None:
        self.processus.stdin.write(json.dumps({"jsonrpc": "2.0", "id": identifiant, "method": methode,
                                               "params": params}) + "\n")
        self.processus.stdin.flush()

    def attendre(self, predicat, delai: float = 180) -> dict:
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            try:
                message = self.messages.get(timeout=1)
            except queue.Empty:
                if self.processus.poll() is not None:
                    break
                continue
            self.recus.append(message)
            if predicat(message):
                return message
        raise AssertionError("réponse JSON-RPC attendue non reçue ; stderr :\n" + "".join(self.erreurs)[-4000:])

    def fermer(self) -> None:
        self.processus.terminate()
        try:
            self.processus.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.processus.kill()


def _evenement(type_: str):
    return lambda m: m.get("method") == "event" and (m.get("params") or {}).get("type") == type_


def _preview_restart_stdio(chemins, valeurs, modele, *, sans_garde: bool = False) -> list:
    installer_home_de_test(chemins, valeurs, modele_url=modele.url, sans_garde=sans_garde)
    passerelle = PasserelleStdio(env_processus(chemins))
    try:
        passerelle.attendre(_evenement("gateway.ready"), 90)
        passerelle.envoyer(1, "session.create", {})
        session = passerelle.attendre(lambda m: m.get("id") == 1)["result"]["session_id"]
        passerelle.envoyer(2, "preview.restart", {"session_id": session, "url": "http://127.0.0.1:1",
                                                  "cwd": "/tmp", "context": "OUTIL:terminal"})
        reponse = passerelle.attendre(lambda m: m.get("id") == 2)
        assert "result" in reponse, reponse
        fin = passerelle.attendre(_evenement("preview.restart.complete"))
        return [m for m in passerelle.recus if m.get("method") == "event"] + [fin]
    finally:
        passerelle.fermer()


def test_preview_restart_par_tui_gateway(chemins, valeurs, modele_factice, temoins):
    """BLOQUANT (correction R1-3). Le vrai chemin session.create puis preview.restart
    (tui_gateway/methods_prompt.py:1075-1133) : l'agent caché reçoit terminal et fichiers
    codés en dur ; le modèle demande terminal ; la garde le refuse, aucun témoin."""
    evenements = _preview_restart_stdio(chemins, valeurs, modele_factice)
    requetes = [r for r in modele_factice.requetes() if r.get("outils_offerts")]
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"evenements": [e["params"] for e in evenements], "resultats": resultats},
                     ensure_ascii=False)[:6000])
    assert any("terminal" in r["outils_offerts"] and r.get("outil_demande") == "terminal" for r in requetes), \
        "le modèle factice n'a pas reçu la demande de l'agent caché avec terminal offert"
    assert any("Refusé par ACP : l'outil « terminal »" in r for r in resultats), resultats
    assert list(temoins.iterdir()) == []


def test_preview_restart_par_tui_gateway_temoin_negatif(chemins, valeurs, modele_factice, temoins):
    """Témoin négatif du test bloquant : sans acp-poste, preview.restart exécute terminal."""
    _preview_restart_stdio(chemins, valeurs, modele_factice, sans_garde=True)
    assert not any("Refusé par ACP" in r for r in modele_factice.resultats_outils())
    assert (temoins / "terminal").exists(), "sans la garde, preview.restart aurait dû exécuter terminal"


# ============================================================ 5. la garde elle-même


OUTILS_DU_GREFFON = ("projet_lancer", "projet_planifier", "projet_etat", "poste_etat", "poste_catalogue",
                     "question_repondre", "question_escalader", "routage_surcharger")


def test_garde_liste_blanche():
    # 26 en P2-P3, plus les huit outils du greffon (étape P4).
    assert len(ge.OUTILS_ADMIS) == 34
    for nom in ge.OUTILS_ADMIS:
        assert ge.garde(tool_name=nom, args={}) is None, nom
    for nom, motif in (("kanban_create", "les projets passent par les outils du greffon acp-poste (projet_lancer, "
                                         "projet_planifier)"),
                       ("kanban_attach_url", "ne résiste pas au rebinding DNS")):
        bloc = ge.garde(tool_name=nom, args={"skills": ["x"], "workspace_path": "/opt/data"})
        assert bloc["action"] == "block" and bloc["message"].startswith("Refusé par ACP : ") and motif in bloc["message"]
    for nom in ("terminal", "process_manage", "read_file", "write_file", "patch", "search_files", "execute_code",
                "tool_call", "desktop_project", "browser_navigate", "browser_click", "computer_use",
                "manage_connections", "cronjob_manage", "delegate_task", "manage_catalog", "inconnu", "",
                "WEB_SEARCH", "web_search ", "poste_executer"):
        bloc = ge.garde(tool_name=nom, args={})
        assert bloc["action"] == "block", nom
        assert bloc["message"].startswith("Refusé par ACP : l'outil « "), nom
        assert "L'exécution passe par le poste Windows du propriétaire." in bloc["message"]


def test_memoire_refusee_dans_un_worker_kanban(monkeypatch):
    """Étape P4 : dans un worker kanban (HERMES_KANBAN_TASK posée par le répartiteur), memory est refusé
    tout de suite, au lieu d'une invite d'approbation qui attendrait 300 s ; en discussion, il reste admis."""
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    assert ge.garde(tool_name="memory", args={"action": "add"}) is None
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_abc")
    bloc = ge.garde(tool_name="memory", args={"action": "add"})
    assert bloc["action"] == "block" and bloc["message"].startswith("Refusé par ACP : une carte kanban n'écrit pas en "
                                                                    "mémoire")
    assert ge.garde(tool_name="projet_etat", args={}) is None and ge.garde(tool_name="kanban_show", args={}) is None
    monkeypatch.setenv("HERMES_KANBAN_TASK", " ")
    assert ge.garde(tool_name="memory", args={}) is None


def test_garde_admet_exactement_les_outils_du_greffon():
    """Les noms ajoutés en P4 sont EXACTEMENT les outils que le greffon enregistre (noyau/outils.py)."""
    from noyau.outils import SCHEMAS

    ajoutes = set(ge.OUTILS_ADMIS) - OUTILS_P3
    assert ajoutes == set(SCHEMAS) == set(OUTILS_DU_GREFFON)


def test_un_outil_du_greffon_retire_de_la_liste_est_refuse(tmp_path):
    """Témoin : une copie de la garde privée d'un nom du greffon refuse cet outil ; la liste blanche est
    bien la seule porte (aucune exception par préfixe ou par jeu d'outils)."""
    import importlib.util

    copie = tmp_path / "garde_copie.py"
    source = (Path(ge.__file__)).read_text(encoding="utf-8")
    assert source.count('"projet_planifier", ') == 1
    copie.write_text(source.replace('"projet_planifier", ', "", 1), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("garde_copie_p4", copie)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.OUTILS_ADMIS) == 33
    bloc = module.garde(tool_name="projet_planifier", args={})
    assert bloc["action"] == "block" and "« projet_planifier » n'est pas autorisé" in bloc["message"]
    assert module.garde(tool_name="projet_etat", args={}) is None


# Les 26 outils de P2-P3 (context7 compris), pour isoler l'ajout de P4.
OUTILS_P3 = frozenset({
    "mcp__context7__resolve_library_id", "mcp__context7__query_docs", "web_search", "web_extract", "vision_analyze",
    "skills_list", "skill_view", "skill_manage", "todo_list", "memory", "session_search", "clarify", "tool_search",
    "tool_describe", "kanban_show", "kanban_list", "kanban_complete", "kanban_block", "kanban_request_review",
    "kanban_request_changes", "kanban_heartbeat", "kanban_comment", "kanban_link", "kanban_unblock", "kanban_attach",
    "kanban_attachments"})


class _ChaineHostile(str):
    def __hash__(self):  # noqa: D105
        raise RuntimeError("hachage piégé")

    def __eq__(self, autre):  # noqa: D105
        raise RuntimeError("comparaison piégée")


@pytest.mark.parametrize("nom, args", [
    (None, None), (42, "x"), (["terminal"], {}), ("\x1b[31mterminal\x1b[0m" + "x" * 500, {"a": object()}),
    (_ChaineHostile("web_search"), {}), ("web_search", object()),
])
def test_garde_arguments_aberrants_sans_exception(nom, args):
    bloc = ge.garde(tool_name=nom, args=args, task_id=object(), inconnu=1)
    if type(nom) is str and nom == "web_search":
        assert bloc is None  # les arguments ne changent rien au verdict en P2
        return
    assert bloc["action"] == "block" and bloc["message"].startswith("Refusé par ACP")
    assert "\x1b" not in bloc["message"] and len(bloc["message"]) < 400


def test_un_rappel_qui_leve_est_bloque_par_hermes():
    """Hermes traite un rappel pre_tool_call qui lève comme un blocage (plugins_dispatch.py:229-241).
    La garde ne lève jamais ; ce test fixe le comportement de Hermes dont elle dépend."""
    from hermes_cli.plugins import PluginManager

    gestionnaire = PluginManager()

    def rappel_qui_leve(tool_name="", args=None, **_):
        raise RuntimeError("panne")

    gestionnaire._hooks["pre_tool_call"] = [rappel_qui_leve]
    resultats = gestionnaire.invoke_hook("pre_tool_call", tool_name="terminal", args={})
    assert any(isinstance(r, dict) and r.get("action") == "block" for r in resultats), resultats
    gestionnaire._hooks["pre_tool_call"] = [ge.garde]
    assert gestionnaire.invoke_hook("pre_tool_call", tool_name="terminal", args={})[0]["action"] == "block"
    assert gestionnaire.invoke_hook("pre_tool_call", tool_name="web_search", args={}) == []


# ============================================================ 6. recensements


RACINE_HERMES = Path("/opt/hermes")
_EXCLUS = ("tests/", "tests-js/", "website/", "node_modules/", ".venv/", "ui-tui/", "web/", "apps/", "evals/",
           "optional-", "skills/", "plugin-catalog/", "scripts/", "native/", "nix/")

# Relevé sur Hermes 0.21.5 (f97608f) le 25/09/2026. Toute construction d'AIAgent NOUVELLE ou
# DÉPLACÉE doit être relue : ses jeux d'outils passent-ils par la managed scope, et la garde
# d'acp-poste (seule couche garantie partout) y est-elle chargée ? (« class AIAgent( » et les
# exemples de docstring comptent aussi dans run_agent.py.)
CONSTRUCTIONS_AIAGENT = {
    "acp_adapter/session.py": 1, "agent/background_review.py": 1, "agent/curator.py": 2, "batch_runner.py": 1,
    "cli.py": 1, "cron/scheduler.py": 2, "gateway/platforms/api_server.py": 1,
    "gateway/platforms/api_server_memory_sessions.py": 1, "gateway/run_turn.py": 2,
    "gateway/run_turn_runner.py": 1, "gateway/slash_commands_session.py": 1,
    "hermes_cli/cli_agent_setup_mixin.py": 1, "hermes_cli/cli_commands_mixin.py": 1, "hermes_cli/oneshot.py": 1,
    "hermes_cli/prompt_size.py": 1, "plugins/platforms/feishu/feishu_comment.py": 1, "run_agent.py": 3,
    "tools/delegate_tool.py": 1, "tui_gateway/methods_prompt.py": 2, "tui_gateway/server.py": 1,
}
# Jeux d'outils écrits en dur (hors configuration). ["terminal", "file"] de preview.restart n'est
# fermé que par la garde.
JEUX_EN_DUR = {
    'agent/curator.py: enabled_toolsets=["skills"],',
    "agent/inline_tool_executors.py: agent.enabled_toolsets = [*enabled, *added]",
    'gateway/run_turn.py: skip_memory=not _hyg_checkpoint_required, enabled_toolsets=["memory"],',
    'gateway/slash_commands_session.py: skip_memory=not _checkpoint_required, enabled_toolsets=["memory"],',
    'plugins/platforms/feishu/feishu_comment.py: quiet_mode=True, skip_context_files=True, skip_memory=True, '
    'max_iterations=15, enabled_toolsets=["feishu_doc", "feishu_drive"])',
    "tools/blueprints.py: enabled_toolsets=[str(t) for t in toolsets] if toolsets else None,",
    "tools/connectors/mcp.py: agent.enabled_toolsets = [*enabled, *(n for n in adopted if n not in enabled)]",
    'tui_gateway/agent_callbacks.py: "enabled_toolsets": ["terminal", "file"], "session_db": None, "skip_memory": True}',
}


def _fichiers_hermes():
    for chemin in sorted(RACINE_HERMES.rglob("*.py")):
        relatif = chemin.relative_to(RACINE_HERMES).as_posix()
        if not any(relatif.startswith(e) for e in _EXCLUS):
            yield relatif, chemin


def test_recensement_des_constructions_aiagent():
    motif_agent = re.compile(r"\bAIAgent\(")
    motif_jeux = re.compile(r"""enabled_toolsets["']?\s*[:=]\s*\[""")
    constructions, jeux = {}, set()
    for relatif, chemin in _fichiers_hermes():
        try:
            lignes = chemin.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        utiles = [l for l in lignes if not l.lstrip().startswith("#")]
        compte = sum(1 for l in utiles if motif_agent.search(l))
        if compte:
            constructions[relatif] = compte
        jeux.update(f"{relatif}: {l.strip()[:140]}" for l in utiles if motif_jeux.search(l))
    ajoutees = {k: v for k, v in constructions.items() if CONSTRUCTIONS_AIAGENT.get(k) != v}
    retirees = {k: v for k, v in CONSTRUCTIONS_AIAGENT.items() if constructions.get(k) != v}
    assert not ajoutees and not retirees, (
        f"constructions d'AIAgent changées (à relire avant toute montée de Hermes) : nouvelles ou "
        f"déplacées {ajoutees}, disparues {retirees}")
    assert jeux == JEUX_EN_DUR, (
        f"jeux d'outils écrits en dur changés : nouveaux {sorted(jeux - JEUX_EN_DUR)}, "
        f"disparus {sorted(JEUX_EN_DUR - jeux)}")


# Appels HTTP directs dans les modules des outils admis et de leurs fournisseurs, relevés sur
# Hermes 0.21.5 le 25/09/2026 (fichier:ligne: texte). Aucun ne télécharge une URL choisie par
# l'agent depuis le conteneur, sauf kanban_tools.py:943 (kanban_attach_url, RETIRÉ par la garde :
# httpx.stream ordinaire, sans protection contre le rebinding DNS). Les autres parlent aux API
# des fournisseurs (web, mémoire) ou au hub de skills par un client sûr (skills_hub.py:100-117).
# Tout site nouveau ou déplacé fait échouer le test : il faut vérifier qu'il passe par
# tools.url_safety.create_ssrf_safe_[async_]client avant de l'admettre (correction R1-1).
APPELS_HTTP_CONNUS = {
    "tools/vision_tools.py:154: bypass the pre-flight check). Async because httpx.AsyncClient awaits hooks.\"\"\"",
    "tools/skills_hub.py:117: return httpx.get(url, **kwargs)",
    "tools/skills_hub_github.py:147: resp = httpx.post(",
    "tools/skills_sync_client_wire.py:215: self._session = requests.Session()",
    'tools/kanban_tools.py:943: with httpx.stream("GET", current_url, headers={"User-Agent": "hermes-kanban/attach"},',
    "plugins/web/_common.py:147: resp = httpx.get(url, params=params, headers=headers, timeout=timeout)",
    'plugins/web/firecrawl/provider.py:112: response = httpx.post(f"{self.api_url}{path}", json=payload, '
    'headers={"Content-Type": "application/json"}, timeout=60.0)',
    "plugins/web/keenable/provider.py:46: response = requests.post(",
    'plugins/web/keenable/provider.py:70: response = requests.get(f"{_KEENABLE_API_URL}/v1/fetch", '
    'params={"url": url}, headers=_keenable_headers(api_key), timeout=30)',
    "plugins/web/keyless_mcp.py:178: response = requests.post(url, json=payload, headers=headers, timeout=timeout)",
    "plugins/web/perplexity/provider.py:10: Both are sync — the underlying call is ``httpx.post(...)``.",
    "plugins/web/perplexity/provider.py:88: response = httpx.post(",
    "plugins/web/perplexity/provider.py:213: Sync — the underlying call is httpx.post(...). Per-URL failures",
    "plugins/web/tavily/provider.py:47: response = httpx.post(url, json=payload, timeout=60, "
    "headers=_tavily_headers(api_key))",
    'plugins/web/xai/provider.py:141: resp = httpx.post(f"{base_url}/responses", headers=headers, json=payload, '
    "timeout=timeout)",
    "plugins/memory/honcho/oauth.py:214: resp = httpx.request(method, url, data=data, timeout=timeout)",
    'plugins/memory/mem0/_backend.py:73: self._client = httpx.Client(base_url=host.rstrip("/"), headers=headers, '
    "timeout=30.0, transport=transport or httpx.HTTPTransport(retries=2))",
    "plugins/memory/mem0/_setup.py:49: return urllib.request.urlopen(urllib.request.Request("
    "f\"{url.rstrip('/')}{path}\", method=\"GET\"), timeout=timeout)",
    'plugins/memory/retaindb/__init__.py:108: return requests.request(method, f"{self.base_url}{path}", '
    "headers=self._headers(path, json_body), timeout=timeout, **kwargs)",
}
MODULES_DES_OUTILS_ADMIS = (
    "tools/web_tools*.py", "tools/vision_tools.py", "tools/skills_*.py", "tools/skill_manager_tool.py",
    "tools/todo_tool.py", "tools/memory_tool.py", "tools/session_search_tool.py", "tools/clarify_tool.py",
    "tools/tool_search*.py", "tools/kanban_tools.py", "plugins/web/**/*.py", "plugins/memory/**/*.py",
)


def test_recensement_http_des_outils_admis():
    appel = re.compile(r"\bhttpx\.(get|post|put|patch|delete|head|request|stream|Client|AsyncClient)\b"
                       r"|\brequests\.(get|post|put|patch|delete|head|request|Session)\b"
                       r"|\burlopen\(|\burllib\.request\.(urlopen|Request)\b|\baiohttp\.ClientSession\b")
    trouves = set()
    for motif in MODULES_DES_OUTILS_ADMIS:
        fichiers = sorted(RACINE_HERMES.glob(motif))
        assert fichiers, f"aucun fichier pour {motif} : le recensement ne verrait plus rien"
        for fichier in fichiers:
            relatif = fichier.relative_to(RACINE_HERMES).as_posix()
            for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
                texte = ligne.strip()
                if not texte.startswith("#") and appel.search(ligne):
                    trouves.add(f"{relatif}:{numero}: {texte[:150]}")
    assert trouves == APPELS_HTTP_CONNUS, (
        "appels HTTP directs changés dans les outils admis : nouveaux ou déplacés "
        f"{sorted(trouves - APPELS_HTTP_CONNUS)} ; disparus {sorted(APPELS_HTTP_CONNUS - trouves)}")
    # Les outils admis qui téléchargent une URL de l'agent passent par le client sûr.
    assert "create_ssrf_safe_async_client" in (RACINE_HERMES / "tools/vision_tools.py").read_text(encoding="utf-8")
    assert "async_is_safe_url" in (RACINE_HERMES / "tools/web_tools.py").read_text(encoding="utf-8")


def test_decouverte_des_greffons_reussit(chemins, valeurs):
    """Garde contre l'échec ouvert d'agent_init.py:1066-1067 : sur l'image épinglée, la
    découverte des greffons ne lève pas, acp-poste se charge sans erreur et le crochet est
    enregistré (processus neuf, managed scope d'ACP)."""
    installer_home_de_test(chemins, valeurs)
    code = r"""
import json, logging, sys
journal = []
class Recueil(logging.Handler):
    def emit(self, r):
        if r.levelno >= logging.WARNING:
            journal.append(f"{r.name}: {r.getMessage()}")
logging.getLogger().addHandler(Recueil())
logging.getLogger().setLevel(logging.WARNING)
sys.path.insert(0, "/opt/hermes/plugins/acp-poste")
from hermes_cli.plugins import discover_plugins, get_plugin_manager
discover_plugins()
import garde_execution
g = get_plugin_manager()
charge = g._plugins.get("acp-poste")
resultat = {"journal": journal, "erreur": getattr(charge, "error", "absent") if charge else "absent",
            "etat": garde_execution.etat()}
"""
    resultat = executer_python(code, env=env_processus(chemins))
    print(json.dumps(resultat, ensure_ascii=False))
    assert resultat["erreur"] is None
    assert not [l for l in resultat["journal"] if "discovery failed" in l.lower() or "acp-poste" in l.lower()]
    assert resultat["etat"]["presente_dans_le_gestionnaire"] is True
    assert resultat["etat"]["enregistree"] is True


# ============================================================ 7. sentinelle hors s6


SENTINELLE = r"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location("acp_sentinelle", "/opt/hermes/plugins/acp-poste/__init__.py",
                                              submodule_search_locations=["/opt/hermes/plugins/acp-poste"])
module = importlib.util.module_from_spec(spec)
sys.modules["acp_sentinelle"] = module
spec.loader.exec_module(module)
argv = sys.argv[3:]
module._sentinelle_chaine_s6(argv=["/opt/hermes/.venv/bin/hermes", *argv], environ={"HERMES_HOME": sys.argv[1]},
                             cmdline=sys.argv[2])
print("passe")
"""


@pytest.mark.parametrize("pid1, home, argv, arret", [
    ("/opt/hermes/.venv/bin/python3", "/opt/data", ["gateway", "run", "--replace"], True),
    ("/sbin/docker-init", "/opt/data", ["dashboard", "--host", "0.0.0.0"], True),
    ("tini", "/opt/data", ["--profile", "default", "gateway", "run"], True),
    ("/package/admin/s6/command/s6-svscan", "/opt/data", ["gateway", "run", "--replace"], False),
    ("/package/admin/s6/command/s6-svscan", "/opt/data", ["dashboard"], False),
    ("/opt/hermes/.venv/bin/python3", "/opt/data", ["chat", "-q", "bonjour"], False),
    ("/opt/hermes/.venv/bin/python3", "/opt/data", ["-p", "default", "--cli", "chat", "-q", "work kanban task t"],
     False),
    ("/opt/hermes/.venv/bin/python3", "/tmp/autre", ["gateway", "run"], False),
    (None, "/opt/data", ["gateway", "run"], True),
    # Relecture P2 : options globales à valeur oubliées, HERMES_HOME non normalisé, profil,
    # « gateway » nu (hermes_cli/gateway.py:5108-5112) et « serve » (même serveur que dashboard).
    ("/sbin/docker-init", "/opt/data", ["--reasoning", "high", "gateway", "run"], True),
    ("/sbin/docker-init", "/opt/data", ["--in", "/tmp", "dashboard"], True),
    ("/sbin/docker-init", "/opt/data", ["--resume", "s1", "-r", "s2", "dashboard"], True),
    ("/sbin/docker-init", "/opt/data", ["-z", "x", "--usage-file", "/tmp/u", "gateway", "run"], True),
    ("/sbin/docker-init", "/opt/data", ["-s", "une", "--skills", "deux", "-c", "nom", "gateway", "run"], True),
    ("/sbin/docker-init", "/opt/data", ["--reasoning=high", "gateway", "run"], True),
    ("/sbin/docker-init", "/opt/data", ["--", "gateway", "run"], True),
    ("/sbin/docker-init", "/opt/data/", ["gateway", "run"], True),
    ("/sbin/docker-init", "/opt//data", ["gateway", "run"], True),
    ("/sbin/docker-init", "/opt/data/../data", ["dashboard"], True),
    ("/sbin/docker-init", "/opt/data/profiles/coder", ["gateway", "run"], True),
    ("/sbin/docker-init", "/opt/data", ["gateway"], True),
    ("/sbin/docker-init", "/opt/data", ["serve", "--port", "9119"], True),
    ("/sbin/docker-init", "/opt/data", ["gateway", "status"], False),
    ("/sbin/docker-init", "/opt/database", ["gateway", "run"], False),
    ("/sbin/docker-init", "/opt/data", ["--continue", "gateway", "run"], False),  # argparse : « gateway » = SESSION_NAME
])
def test_sentinelle_hors_s6(tmp_path, pid1, home, argv, arret):
    cmdline = tmp_path / "cmdline"
    if pid1 is not None:
        cmdline.write_bytes(pid1.encode() + b"\0--\0/run/service\0")
    sortie = subprocess.run([PYTHON_HERMES, "-c", SENTINELLE, home, str(cmdline), *argv],
                            capture_output=True, text=True, timeout=60)
    if arret:
        assert sortie.returncode == 78, (sortie.returncode, sortie.stdout, sortie.stderr)
        assert "[acp] REFUS : « hermes " in sortie.stderr and "hors de la chaîne s6 d'ACP" in sortie.stderr
        assert "passe" not in sortie.stdout
    else:
        assert sortie.returncode == 0, sortie.stderr
        assert sortie.stdout.strip() == "passe"


def test_sentinelle_suit_un_lien_vers_le_volume(tmp_path):
    """Un HERMES_HOME qui est un lien vers /opt/data désigne le volume de production."""
    lien = tmp_path / "lien"
    lien.symlink_to("/opt/data")
    cmdline = tmp_path / "cmdline"
    cmdline.write_bytes(b"/sbin/docker-init\0--\0")
    sortie = subprocess.run([PYTHON_HERMES, "-c", SENTINELLE, str(lien), str(cmdline), "gateway", "run"],
                            capture_output=True, text=True, timeout=60)
    assert sortie.returncode == 78, (sortie.returncode, sortie.stdout, sortie.stderr)


def test_options_a_valeur_couvrent_l_analyseur_de_hermes():
    """Recensement : toute option globale de `hermes` qui prend une valeur, d'après l'analyseur
    RÉEL de l'image épinglée (hermes_cli._parser.top_level_value_flag_sets, dérivé de
    build_top_level_parser), est connue de la sentinelle. Une montée de version qui en ajoute une
    fait échouer ce test au lieu d'ouvrir un contournement."""
    code = r"""
import importlib.util, sys
from hermes_cli import _parser
obligatoires, facultatives = _parser.top_level_value_flag_sets()
spec = importlib.util.spec_from_file_location("acp_recensement", "/opt/hermes/plugins/acp-poste/__init__.py",
                                              submodule_search_locations=["/opt/hermes/plugins/acp-poste"])
module = importlib.util.module_from_spec(spec)
sys.modules["acp_recensement"] = module
spec.loader.exec_module(module)
connues = set(module._OPTIONS_A_VALEUR)
resultat = {"hermes": sorted(obligatoires | facultatives), "secours": sorted(_parser._VALUE_FLAGS_FALLBACK
            | _parser._OPTIONAL_VALUE_FLAGS_FALLBACK), "avant_argparse": [n for n, _ in _parser.PRE_ARGPARSE_INHERITED_FLAGS],
            "manquantes": sorted((obligatoires | facultatives | _parser._VALUE_FLAGS_FALLBACK
                                  | _parser._OPTIONAL_VALUE_FLAGS_FALLBACK
                                  | {n for n, _ in _parser.PRE_ARGPARSE_INHERITED_FLAGS}) - connues)}
"""
    resultat = executer_python(code)
    print(json.dumps(resultat, ensure_ascii=False))
    assert len(resultat["hermes"]) >= 14  # analyseur réel lu (sinon le test passerait à vide)
    assert resultat["manquantes"] == []


def test_la_garde_est_enregistree_par_register():
    """register() enregistre exactement la garde sur pre_tool_call (hors /opt/data : pas de sentinelle)."""
    code = r"""
import importlib.util, json, os, sys
os.environ["HERMES_HOME"] = "/tmp/acp-hors-volume"
spec = importlib.util.spec_from_file_location("acp_test_greffon", "/opt/hermes/plugins/acp-poste/__init__.py",
                                              submodule_search_locations=["/opt/hermes/plugins/acp-poste"])
module = importlib.util.module_from_spec(spec)
sys.modules["acp_test_greffon"] = module
spec.loader.exec_module(module)
class Contexte:
    def __init__(self): self.crochets = []
    def register_hook(self, nom, rappel): self.crochets.append((nom, rappel.__name__, rappel.__module__))
    def register_tool(self, **k): pass
    def register_system_prompt_section(self, *a, **k): pass
ctx = Contexte()
module.register(ctx)
resultat = [ctx.crochets, module.garde_execution.ENREGISTRE_DANS_CE_PROCESSUS]
"""
    crochets, enregistre = executer_python(code)
    # La garde d'abord ; depuis P4, le crochet de tick de l'émetteur ensuite (test_outils_greffon.py).
    assert crochets[0] == ["pre_tool_call", "garde", "acp_test_greffon.garde_execution"]
    assert [c[0] for c in crochets] == ["pre_tool_call", "on_kanban_dispatch_tick"]
    assert enregistre is True


def test_register_appelle_la_sentinelle():
    """register() lance bien la sentinelle AVANT d'enregistrer la garde : une passerelle de
    production (HERMES_HOME=/opt/data, « gateway run ») hors de s6 s'arrête en code 78."""
    code = r"""
import importlib.util, os, sys
os.environ["HERMES_HOME"] = "/opt/data"
sys.argv = ["/opt/hermes/.venv/bin/hermes", "gateway", "run", "--replace"]
spec = importlib.util.spec_from_file_location("acp_test_sentinelle", "/opt/hermes/plugins/acp-poste/__init__.py",
                                              submodule_search_locations=["/opt/hermes/plugins/acp-poste"])
module = importlib.util.module_from_spec(spec)
sys.modules["acp_test_sentinelle"] = module
spec.loader.exec_module(module)
module._programme_pid1 = lambda *a, **k: "python3"   # PID 1 hors de s6
class Contexte:
    def register_hook(self, nom, rappel):
        print("crochet enregistré", flush=True)
module.register(Contexte())
print("passe", flush=True)
"""
    sortie = subprocess.run([PYTHON_HERMES, "-c", code], capture_output=True, text=True, timeout=60)
    assert sortie.returncode == 78, (sortie.returncode, sortie.stdout, sortie.stderr)
    assert "hors de la chaîne s6 d'ACP" in sortie.stderr
    assert "passe" not in sortie.stdout and "crochet enregistré" not in sortie.stdout


def test_modules_outils_de_test_presents():
    """Les outils de test utilisés ci-dessus sont bien dans l'image de test (sinon échec, jamais
    d'ignorance silencieuse)."""
    for nom in ("modele_factice.py", "sonde_surfaces.py", "agent_neuf.py"):
        assert (OUTILS / nom).is_file(), nom
    assert (Path("/opt/hermes/tui_gateway") / "entry.py").is_file()
