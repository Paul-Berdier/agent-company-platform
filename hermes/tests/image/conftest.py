"""Tests exécutés DANS l'image de test (``hermes/tests/Dockerfile``), en root, avec
l'interpréteur de Hermes :

  docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e PYTHONPATH=/opt/acp-tests/site \
      acp-hermes-tests:ci -m pytest -p no:cacheprovider /opt/acp-tests/image

Ils ne tournent nulle part ailleurs : ils importent le code de Hermes à la version
épinglée et les fichiers de l'image (/opt/acp, /opt/hermes/plugins/acp-poste). Chaque test
travaille dans un HERMES_HOME et une managed scope jetables (tmp_path), jamais dans
/opt/data ni /etc/hermes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

import pytest

BIN_ACP = Path("/opt/acp/bin")
GREFFON = Path("/opt/hermes/plugins/acp-poste")
OUTILS = Path("/opt/acp-tests/outils")

if not (BIN_ACP / "acp_demarrage.py").is_file() or not GREFFON.is_dir():
    raise RuntimeError(
        "Ces tests s'exécutent dans l'image de test ACP (hermes/tests/Dockerfile), pas ailleurs.")

for chemin in (BIN_ACP, GREFFON):
    if str(chemin) not in sys.path:
        sys.path.insert(0, str(chemin))

import acp_demarrage as ad  # noqa: E402

ENV_VALIDE = {
    "HERMES_HOME": "/opt/data",
    "HERMES_WEB_DIST": "/opt/hermes/hermes_cli/web_dist",
    "HERMES_DASHBOARD": "1",
    "HERMES_DASHBOARD_HOST": "0.0.0.0",
    "HERMES_DASHBOARD_PORT": "9119",
    "S6_BEHAVIOUR_IF_STAGE2_FAILS": "2",
    "S6_STAGE2_HOOK": "/opt/acp/bin/acp-gardes",
    # Valeurs imposées depuis P2 (ENV de l'image officielle).
    "HERMES_WRITE_SAFE_ROOT": "/opt/data",
    "HERMES_DISABLE_LAZY_INSTALLS": "1",
    "HERMES_LAZY_INSTALL_TARGET": "/opt/data/lazy-packages",
    "HERMES_TUI_DIR": "/opt/hermes/ui-tui",
    "XDG_RUNTIME_DIR": "/tmp/hermes-runtime",
    "HERMES_DASHBOARD_PUBLIC_URL": "https://hermes.acp.test",
    "HERMES_DASHBOARD_OIDC_ISSUER": "https://idp.acp.test:8443",
    "HERMES_DASHBOARD_OIDC_CLIENT_ID": "acp-tableau",
    "PATH": "/usr/bin:/bin",
    "HOSTNAME": "conteneur",
}


@pytest.fixture
def env_valide() -> dict:
    return dict(ENV_VALIDE)


@pytest.fixture
def valeurs() -> "ad.ValeursDeploiement":
    return ad.verifier_environnement(ENV_VALIDE)


@pytest.fixture
def chemins(tmp_path: Path) -> "ad.Chemins":
    """Arborescence jetable : managed scope, HERMES_HOME, état ; modèle, thème et SOUL de l'image.

    Les parents de tmp_path sont rendus traversables (0755) : sans cela, un test « l'uid
    hermes ne peut pas écrire » réussirait pour une mauvaise raison (répertoire parent
    fermé), ce que les contrôles positifs des tests vérifient."""
    for parent in (tmp_path, tmp_path.parent, tmp_path.parent.parent):
        os.chmod(parent, 0o755)
    gere = tmp_path / "etc-hermes"
    gere.mkdir(mode=0o755)
    os.chmod(gere, 0o755)
    home = tmp_path / "opt-data"
    home.mkdir()
    os.chown(home, 10000, 10000)
    return ad.Chemins(
        modele_gere=Path("/opt/acp/gere/config.yaml"),
        dossier_gere=gere,
        hermes_home=home,
        theme_livre=Path("/opt/acp/theme"),
        soul_livre=Path("/opt/acp/persona/SOUL.md"),
        soul_amont=Path("/opt/hermes/docker/SOUL.md"),
        dossier_etat=tmp_path / "run-acp",
    )


# ------------------------------------------------------------------ processus neufs (étape P2)

import json  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402

PYTHON_HERMES = "/opt/hermes/.venv/bin/python"
TEMOINS = Path("/tmp/acp-temoins")

# Variables jamais transmises à un processus neuf de test : elles désigneraient le vrai volume ou
# changeraient le comportement mesuré.
_VARIABLES_ECARTEES = ("HERMES_HOME", "HERMES_MANAGED_DIR", "HERMES_KANBAN_TASK", "HERMES_TUI_TOOLSETS",
                       "HERMES_SAFE_MODE", "HERMES_BIN", "PYTHONPATH")


class ModeleFactice:
    """Modèle factice (hermes/tests/outils/modele_factice.py) dans un sous-processus."""

    def __init__(self, dossier: Path) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.journal = dossier / "modele-factice.jsonl"
        self.scenarios = dossier / "scenarios.json"
        self.processus = subprocess.Popen(
            [PYTHON_HERMES, str(OUTILS / "modele_factice.py"), "--port", str(self.port),
             "--journal", str(self.journal), "--scenarios", str(self.scenarios)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        limite = time.monotonic() + 30
        while time.monotonic() < limite:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("le modèle factice n'a pas démarré")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def requetes(self) -> list:
        if not self.journal.exists():
            return []
        return [json.loads(l) for l in self.journal.read_text(encoding="utf-8").splitlines() if l.strip()]

    def resultats_outils(self) -> list:
        """Contenus des résultats d'outils reçus par le modèle, dans l'ordre."""
        vus = []
        for requete in self.requetes():
            for resultat in requete.get("resultats_outils") or []:
                if resultat["contenu"] not in vus:
                    vus.append(resultat["contenu"])
        return vus

    def arreter(self) -> None:
        self.processus.terminate()
        try:
            self.processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.processus.kill()


@pytest.fixture
def modele_factice(tmp_path: Path):
    dossier = tmp_path / "factice"
    dossier.mkdir()
    modele = ModeleFactice(dossier)
    yield modele
    modele.arreter()


@pytest.fixture
def temoins():
    """Répertoire des témoins, vidé avant et après le test : un fichier qui y apparaît prouve
    qu'un outil d'exécution a réellement tourné."""
    shutil.rmtree(TEMOINS, ignore_errors=True)
    TEMOINS.mkdir(mode=0o777)
    os.chmod(TEMOINS, 0o1777)
    yield TEMOINS
    shutil.rmtree(TEMOINS, ignore_errors=True)


def installer_home_de_test(chemins: "ad.Chemins", valeurs: "ad.ValeursDeploiement", *, modele_url: Optional[str] = None,
                           config: str = "", env: str = "", sans_garde: bool = False,
                           remplacements: Sequence[Tuple[str, str]] = ()) -> None:
    """Managed scope jetable (celle de l'image, régénérée) et volume jetable garni.

    ``sans_garde`` : témoin négatif, la managed scope de test désactive acp-poste.
    ``remplacements`` : témoins négatifs de P3, (texte, remplacement) appliqués à la managed scope
    installée (chaque texte doit s'y trouver)."""
    ad.installer_scope_geree(chemins, valeurs)
    fichier = chemins.dossier_gere / "config.yaml"
    if sans_garde:
        texte = fichier.read_text(encoding="utf-8")
        assert "    - dashboard_auth/drain\n" in texte
        fichier.write_text(texte.replace("    - dashboard_auth/drain\n",
                                         "    - dashboard_auth/drain\n    - acp-poste\n"), encoding="utf-8")
    for motif, remplacement in remplacements:
        texte = fichier.read_text(encoding="utf-8")
        assert motif in texte, motif
        fichier.write_text(texte.replace(motif, remplacement, 1), encoding="utf-8")
    contenu = config
    if modele_url:
        contenu = (f"model:\n  provider: custom\n  base_url: {modele_url}\n  default: acp-factice\n"
                   f"  api_key: factice\n") + contenu
    if contenu:
        (chemins.hermes_home / "config.yaml").write_text(contenu, encoding="utf-8")
    if env:
        (chemins.hermes_home / ".env").write_text(env, encoding="utf-8")


def env_processus(chemins: "ad.Chemins", **supplement: str) -> dict:
    """Environnement d'un processus neuf : HERMES_HOME et managed scope jetables."""
    env = {k: v for k, v in os.environ.items() if k not in _VARIABLES_ECARTEES}
    env["HERMES_HOME"] = str(chemins.hermes_home)
    env["HERMES_MANAGED_DIR"] = str(chemins.dossier_gere)
    env["HOME"] = str(chemins.hermes_home)
    env.update(supplement)
    return env


def lancer_outil(script: str, *arguments: str, env: dict, delai: int = 240) -> subprocess.CompletedProcess:
    """Lance un outil de hermes/tests/outils dans un processus Python NEUF (interpréteur de Hermes)."""
    return subprocess.run([PYTHON_HERMES, str(OUTILS / script), *arguments], env=env, cwd="/opt/hermes",
                          capture_output=True, text=True, timeout=delai)


def executer_python(code: str, *, env: Optional[dict] = None, delai: int = 180, dossier: Optional[Path] = None):
    """Exécute ``code`` dans un processus Python NEUF (interpréteur de Hermes) ; le code range son
    résultat dans la variable ``resultat``, relue en JSON par un fichier : Hermes détourne
    sys.stdout vers la sortie d'erreur à l'import de certains modules."""
    import tempfile

    fd, chemin = tempfile.mkstemp(prefix="acp-resultat-", suffix=".json", dir=str(dossier) if dossier else None)
    os.close(fd)
    os.chmod(chemin, 0o666)
    enveloppe = (code + "\nimport json as _acp_json\nwith open(" + repr(chemin)
                 + ", 'w', encoding='utf-8') as _acp_f:\n    _acp_json.dump(resultat, _acp_f, ensure_ascii=False)\n")
    try:
        sortie = subprocess.run([PYTHON_HERMES, "-c", enveloppe], env=env, cwd="/opt/hermes", capture_output=True,
                                text=True, timeout=delai)
        assert sortie.returncode == 0, f"code {sortie.returncode}\n{sortie.stderr[-4000:]}"
        with open(chemin, encoding="utf-8") as flux:
            return json.load(flux)
    finally:
        os.unlink(chemin)


# ------------------------------------------------------------------ faux context7 (étape P3)

HOTE_CONTEXT7 = "mcp.context7.com"


@pytest.fixture(scope="session", autouse=True)
def context7_sans_reseau():
    """Pendant TOUTE la session de tests de l'image, mcp.context7.com (épinglé par la managed scope)
    désigne le bouclage local : aucun processus de test ne joint le vrai serveur ; sans faux serveur,
    la connexion est refusée (état « hors ligne »)."""
    hotes = Path("/etc/hosts")
    avant = hotes.read_text(encoding="utf-8")
    hotes.write_text(avant.rstrip("\n") + f"\n127.0.0.1 {HOTE_CONTEXT7}\n", encoding="utf-8")
    yield
    hotes.write_text(avant, encoding="utf-8")


class FauxContext7:
    """Faux serveur context7 (hermes/tests/outils/mcp_factice.py) en TLS sur 127.0.0.1:443."""

    def __init__(self, dossier: Path) -> None:
        self.journal = dossier / "mcp-factice.jsonl"
        self.processus = subprocess.Popen(
            [PYTHON_HERMES, str(OUTILS / "mcp_factice.py"), "--port", "443", "--certificat",
             "/opt/acp-tests/ac/mcp.pem", "--cle", "/opt/acp-tests/ac/mcp.key", "--journal", str(self.journal)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        limite = time.monotonic() + 60
        while time.monotonic() < limite:
            try:
                with socket.create_connection(("127.0.0.1", 443), timeout=1):
                    return
            except OSError:
                if self.processus.poll() is not None:
                    raise RuntimeError("le faux serveur context7 s'est arrêté")
                time.sleep(0.3)
        raise RuntimeError("le faux serveur context7 n'a pas démarré")

    def evenements(self) -> list:
        if not self.journal.exists():
            return []
        return [json.loads(l) for l in self.journal.read_text(encoding="utf-8").splitlines() if l.strip()]

    def appels(self) -> list:
        return [e["outil"] for e in self.evenements() if e.get("evenement") == "appel"]

    def arreter(self) -> None:
        self.processus.terminate()
        try:
            self.processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.processus.kill()


@pytest.fixture
def faux_context7(tmp_path: Path):
    dossier = tmp_path / "context7"
    dossier.mkdir()
    serveur = FauxContext7(dossier)
    yield serveur
    serveur.arreter()


# ------------------------------------------------------------------ noyau des projets (étape P4)

from types import SimpleNamespace  # noqa: E402

_VARIABLES_KANBAN = ("HERMES_KANBAN_HOME", "HERMES_KANBAN_DB", "HERMES_KANBAN_BOARD", "HERMES_KANBAN_TASK",
                     "HERMES_KANBAN_RUN_ID", "HERMES_KANBAN_CLAIM_LOCK", "HERMES_KANBAN_WORKSPACE",
                     "HERMES_DELEGATED_CHILD_CONTEXT")


def releve_factice(voie: str = "poste-codex", *, depots=("jetable",), quota=None, releve_le=None, modeles=None) -> dict:
    """Relevé FACTICE (identifiants manifestement factices), comme outils/releve_factice.json."""
    import datetime as _dt

    suffixe = "codex" if voie == "poste-codex" else "claude"
    quand = releve_le or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    return {
        "voie": voie, "source": "releve_factice", "version_cli": "0.0.0-factice",
        "releve_le": quand.isoformat(),
        "modeles": modeles or [
            {"id": f"factice-{suffixe}-1", "displayName": f"Factice {suffixe} 1", "isDefault": True,
             "supportedReasoningEfforts": ["low", "medium", "high", "xhigh", "max", "extreme"],
             "defaultReasoningEffort": "medium", "serviceTiers": ["default", "priority"],
             "defaultServiceTier": "default"},
            {"id": f"factice-{suffixe}-2", "isDefault": False, "supportedReasoningEfforts": ["low"]},
        ],
        "quotas": {"pourcentage_utilise": quota} if quota is not None else None,
        "depots": [{"alias": d} for d in depots],
    }


@pytest.fixture
def noyau(tmp_path, monkeypatch):
    """Noyau du greffon acp-poste sur un HERMES_HOME jetable (base du greffon et tableaux kanban sous
    tmp_path, jamais /opt/data), horloge réelle, émetteur hors passerelle."""
    home = tmp_path / "home-p4"
    home.mkdir()
    for nom in _VARIABLES_KANBAN + ("HERMES_DASHBOARD_PUBLIC_URL",):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.setenv("HERMES_HOME", str(home))
    from noyau import (base, cartes, emetteur, etrangeres, graphe, invite, notifications, outils, presence,
                       projets, questions, routage, textes)
    from noyau import kanban_adapter as ka

    base.fixer_horloge(None)
    emetteur.configurer(notifications.Configuration(), passerelle=False, transport=notifications.transport_urllib)
    yield SimpleNamespace(home=home, base=base, cartes=cartes, emetteur=emetteur, etrangeres=etrangeres,
                          graphe=graphe, invite=invite, notifications=notifications, outils=outils,
                          presence=presence, projets=projets, questions=questions, routage=routage, textes=textes,
                          ka=ka)
    base.fixer_horloge(None)
    emetteur.configurer(notifications.Configuration(), passerelle=False, transport=notifications.transport_urllib)


@pytest.fixture
def conn(noyau):
    with noyau.base.connexion() as connexion:
        yield connexion


def en_worker(monkeypatch, tableau: str, carte: str) -> None:
    """Contexte d'un worker kanban, tel que le répartiteur le pose (kanban_db_dispatch.py:2821-2862)."""
    monkeypatch.setenv("HERMES_KANBAN_TASK", carte)
    monkeypatch.setenv("HERMES_KANBAN_BOARD", tableau)


def en_discussion(monkeypatch) -> None:
    for nom in ("HERMES_KANBAN_TASK", "HERMES_KANBAN_BOARD"):
        monkeypatch.delenv(nom, raising=False)


def outil(noyau, nom: str, args, session: str = "session-test") -> dict:
    """Appelle un outil du greffon comme Hermes (gestionnaire enregistré) et rend son JSON."""
    return json.loads(noyau.outils.GESTIONNAIRES[nom](args, session_id=session, task_id="x", inconnu=1))


def carte(noyau, tableau: str, identifiant: str):
    with noyau.ka.connexion(tableau) as kc:
        return noyau.ka.get_task(kc, identifiant)


def cartes_du_tableau(noyau, tableau: str):
    with noyau.ka.connexion(tableau) as kc:
        return {t.id: t for t in noyau.ka.list_tasks(kc, include_archived=True)}


def reclamer(noyau, tableau: str, identifiant: str):
    """Réclamation par le poste SIMULÉ (claimer distant, comme le poste réel en P6)."""
    with noyau.ka.connexion(tableau) as kc:
        tache = noyau.ka.claim_task(kc, identifiant, ttl_seconds=2700, claimer="acp-poste:simule")
    assert tache is not None, f"réclamation de {identifiant} refusée"
    return tache.current_run_id


def terminer(noyau, tableau: str, identifiant: str, resume: str = "fait") -> bool:
    with noyau.ka.connexion(tableau) as kc:
        run = noyau.ka.get_task(kc, identifiant).current_run_id
        return noyau.ka.complete_task(kc, identifiant, summary=resume, expected_run_id=run)


def lancer_sans_depot(noyau, conn, titre: str = "Veille LLM", **options):
    resultat = noyau.projets.lancer(conn, titre=titre, objectif="Recenser les modèles récents.", profil="recherche",
                                    origine="tableau_de_bord", auteur="proprietaire:test", **options)
    return resultat["projet"]


def lancer_sur_depot(noyau, conn, titre: str = "Outil jetable", *, voies=("poste-codex", "poste-claude"), **options):
    for voie in voies:
        noyau.routage.enregistrer_releve(conn, releve_factice(voie))
    options.setdefault("exploration", {"voie": "poste-claude", "modele": "factice-claude-1", "effort": "low"})
    resultat = noyau.projets.lancer(conn, titre=titre, objectif="Écrire un outil dans le dépôt jetable.",
                                    profil="base", depot="jetable", origine="tableau_de_bord",
                                    auteur="proprietaire:test", **options)
    return resultat["projet"]
