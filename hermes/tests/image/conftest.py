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

# Étape P5 : le contrat partagé (acp_poste_contrat) est importé par son chemin, comme le fait le noyau.
for chemin in (BIN_ACP, GREFFON, GREFFON / "contrat"):
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
    from noyau import (base, cartes, emetteur, etrangeres, graphe, inventaire, invite, machines, notifications, ordres,
                       outils, presence, projets, questions, quotas, routage, textes)
    from noyau import kanban_adapter as ka

    base.fixer_horloge(None)
    emetteur.configurer(notifications.Configuration(), passerelle=False, transport=notifications.transport_urllib)
    yield SimpleNamespace(home=home, base=base, cartes=cartes, emetteur=emetteur, etrangeres=etrangeres,
                          graphe=graphe, invite=invite, notifications=notifications, outils=outils,
                          presence=presence, projets=projets, questions=questions, routage=routage, textes=textes,
                          ka=ka, machines=machines, ordres=ordres, inventaire=inventaire, quotas=quotas)
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


# ------------------------------------------------------------------ poste connecté (étape P5)

FIXTURES_MACHINE = OUTILS / "fixtures_machine"


def fixture_machine(nom: str) -> dict:
    """Exemple de requête ou de réponse du protocole acp-machine/1 (hermes/tests/outils/fixtures_machine), le même
    que lisent les tests du contrat et le faux Hermes des tests du poste."""
    return json.loads((FIXTURES_MACHINE / nom).read_text(encoding="utf-8"))


def inventaire_factice(*, releve_le=None, depots=("jetable",), modifier=None) -> dict:
    """Inventaire de l'exemple, daté de maintenant (ou de ``releve_le``), dépôts remplacés ; ``modifier(inv)``
    ajuste le reste."""
    import datetime as _dt

    inventaire = fixture_machine("inventaire_requete.json")
    quand = (releve_le or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)).strftime("%Y-%m-%dT%H:%M:%SZ")
    inventaire["releve_le"] = quand
    inventaire["depots"] = [{"alias": d} for d in depots]
    for releve in inventaire["releves"]:
        releve["releve_le"] = quand
        releve["depots"] = [{"alias": d} for d in depots]
        for compteur in releve["compteurs"]:
            compteur["observed_at"] = quand
    inventaire["bac_a_sable_codex"]["lu_le"] = quand
    if modifier is not None:
        modifier(inventaire)
    return inventaire


def poste_confirme(noyau, conn, *, nom: str = "Poste Windows"):
    """Enrôle ET confirme un poste par les fonctions du noyau ; rend (machine_id, jeton)."""
    from acp_poste_contrat.machine import PROTOCOLE, empreinte_jeton

    code = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    with noyau.base.transaction(conn):
        reponse = noyau.machines.enroler_dans(conn, empreinte_jeton(code), nom=nom, version_poste="0.11.0",
                                              protocole=PROTOCOLE)
    noyau.machines.confirmer(conn, reponse["machine_id"], reponse["empreinte"], "proprietaire:test")
    return reponse["machine_id"], reponse["jeton"]


class PileMachine:
    """Routes du greffon servies par un VRAI serveur uvicorn (fil de test), derrière la VRAIE couture
    d'authentification par jeton de Hermes (token_auth_middleware) où le fournisseur du greffon est enregistré,
    plus une session factice pour les routes du propriétaire (la porte OIDC réelle est prouvée au contrat)."""

    def __init__(self, noyau, module, url: str, serveur, fil, fournisseurs) -> None:
        self.noyau, self.module, self.url, self._serveur, self._fil = noyau, module, url, serveur, fil
        self._fournisseurs = fournisseurs
        import meta

        self.base_routes = meta.sous_module_noyau("base")  # copie du noyau servie par les routes

    def post(self, chemin: str, corps=None, *, jeton=None, entetes=None, brut=None, delai: float = 70):
        import httpx

        envoyes = {"Content-Type": "application/json"}
        if jeton:
            envoyes["Authorization"] = f"Bearer {jeton}"
        envoyes.update(entetes or {})
        contenu = brut if brut is not None else json.dumps(corps if corps is not None else {}).encode("utf-8")
        return httpx.post(self.url + chemin, content=contenu, headers=envoyes, timeout=delai)

    def get(self, chemin: str, *, delai: float = 30):
        import httpx

        return httpx.get(self.url + chemin, timeout=delai)

    def arreter(self) -> None:
        from hermes_cli.dashboard_auth.registry import unregister_global_provider

        self._serveur.should_exit = True
        self._fil.join(15)
        for fournisseur in self._fournisseurs:
            unregister_global_provider(fournisseur.name, fournisseur)


@pytest.fixture
def pile_machine(noyau, monkeypatch):
    import importlib.util
    import threading

    import uvicorn
    from fastapi import FastAPI, Request
    from hermes_cli.dashboard_auth.registry import register_global_provider
    from hermes_cli.dashboard_auth.token_auth import register_token_route, token_auth_middleware

    monkeypatch.setenv("HERMES_DASHBOARD_PUBLIC_URL", "https://hermes.acp.test")
    spec = importlib.util.spec_from_file_location("acp_poste_plugin_api_p5", GREFFON / "dashboard" / "plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import meta

    jeton_machine = meta.sous_module_noyau("jeton_machine")
    fournisseur = jeton_machine.FournisseurJetonMachine()
    register_global_provider(fournisseur)
    from acp_poste_contrat.machine import ROUTES

    for chemin in ROUTES:
        register_token_route(chemin)
    application = FastAPI()

    @application.middleware("http")
    async def session_factice(request: Request, suivant):
        if request.headers.get("x-test-sans-session") is None and not request.url.path.startswith(
                "/api/plugins/acp-poste/machine/"):
            request.state.session = SimpleNamespace(user_id="proprietaire-test")
        return await suivant(request)

    @application.middleware("http")
    async def couture(request: Request, suivant):
        return await token_auth_middleware(request, suivant)

    @application.get("/test/fils-occupes")
    async def fils_occupes():
        import anyio

        return {"occupes": anyio.to_thread.current_default_thread_limiter().borrowed_tokens}

    application.include_router(module.router, prefix="/api/plugins/acp-poste")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    serveur = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning",
                                           lifespan="off"))
    fil = threading.Thread(target=serveur.run, name="uvicorn-test-p5", daemon=True)
    fil.start()
    limite = time.monotonic() + 20
    while not serveur.started:
        if time.monotonic() > limite or not fil.is_alive():
            raise RuntimeError("le serveur de test des routes machine n'a pas démarré")
        time.sleep(0.05)
    pile = PileMachine(noyau, module, f"http://127.0.0.1:{port}", serveur, fil, [fournisseur])
    try:
        yield pile
    finally:
        pile.arreter()
        pile.base_routes.fixer_horloge(None)
