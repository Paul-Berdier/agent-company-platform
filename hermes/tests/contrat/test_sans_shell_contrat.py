"""Contrat de l'étape P2, piloté depuis l'hôte (voir conftest.py) : l'agent n'a aucun outil
d'exécution, et Hermes ne tourne jamais hors des gardes d'ACP.

Ce qu'ils prouvent, sur l'image réellement construite :
1. démarrage et gardes : refus hors PID 1 (acp-entree), passerelle et tableau de bord lancés
   hors de s6 arrêtés par le greffon (code 78), hooks/ et scripts/ du volume exigés vides puis
   repris par root, règle du volume Railway simulée, aucune installation paresseuse ;
2. outils d'exécution refusés par les VRAIS processus : api_server en HTTP, agent cron, worker
   kanban (la garde est prouvée DANS le processus du worker par le refus de kanban_create et de
   kanban_attach_url), volume piégé après relance ;
3. preview.restart par /api/ws du VRAI tableau de bord, avec un ticket : BLOQUANT, jamais
   ignoré ; témoin négatif (garde retirée → l'outil s'exécute) ;
4. maintenance : Start Command « /bin/sh -c "exec sleep infinity" », avec et sans CMD hérité,
   shell root, ``diagnostiquer`` depuis une session sans environnement.

Un outil d'exécution qui tournerait vraiment laisserait un fichier dans /tmp/acp-temoins du
conteneur (arguments témoins du modèle factice) : aucun ne doit apparaître, sauf dans le
témoin négatif.
"""

from __future__ import annotations

import json
import re
import time
from typing import Dict, List

import pytest

from conftest import (ENV_VALIDE, SANS_CONTEXT7, Conteneur, afficher, attendre_modele_factice,
                      demarrer_jusqu_a_l_arret, docker, lancer, options_env)

SHA = "0123456789abcdef0123456789abcdef01234567"


def _texte(valeur: object) -> str:
    return json.dumps(valeur, ensure_ascii=False, indent=2)


def _lignes_acp(journal: str) -> str:
    return "\n".join(l for l in journal.splitlines() if "[acp]" in l or "rc.init" in l or "hermes]" in l)


def _executer_jusqu_a_l_arret(ressources, image: str, *options: str, commande: List[str] = (),
                              env: Dict[str, str] = ENV_VALIDE, delai: int = 180):
    nom = ressources.nom("arret")
    ressources.conteneurs.append(nom)
    volume = ressources.volume(image)
    resultat = docker("run", "--name", nom, "-v", f"{volume}:/opt/data", *SANS_CONTEXT7, *options_env(env), *options,
                      image, *commande, verifier=False, delai=delai)
    return resultat.returncode, resultat.stdout + resultat.stderr


# =========================================================================== 1. gardes


def test_entree_refuse_hors_pid1(ressources, image):
    """docker run --init : tini est PID 1 ; le repli officiel sans s6 tournerait sans garde
    (entrypoint-dispatch.sh:17-25). acp-entree refuse, code 1, en français."""
    code, journal = _executer_jusqu_a_l_arret(ressources, image, "--init")
    afficher(f"docker run --init : code {code}", _lignes_acp(journal))
    assert code == 1
    assert "[acp] REFUS : l'image n'a pas le PID 1" in journal
    assert "[acp] Démarrage arrêté (échec fermé)" in journal
    assert "Retirez --init" in journal
    assert "[stage2]" not in journal and "not PID 1; skipping s6-overlay" not in journal


def test_entree_refuse_hors_pid1_sur_railway(ressources, image):
    """Relecture P2 : sur Railway (marqueurs présents), ni --init ni Start Command n'ont de sens ;
    le refus renvoie à la procédure du § 10 f de railway.md et interdit tout contournement."""
    env = dict(ENV_VALIDE, RAILWAY_DEPLOYMENT_ID="dep-contrat", RAILWAY_VOLUME_MOUNT_PATH="/opt/data")
    code, journal = _executer_jusqu_a_l_arret(ressources, image, "--init", env=env)
    afficher(f"docker run --init « sur Railway » : code {code}", _lignes_acp(journal))
    assert code == 1
    assert "[acp] REFUS : l'image n'a pas le PID 1" in journal
    assert "Sur Railway, la plateforme n'a pas donné le PID 1 à l'image" in journal
    assert "docs/refonte/railway.md § 10 f" in journal
    assert "Retirez --init" not in journal
    assert "[stage2]" not in journal


@pytest.mark.parametrize("commande", [["gateway", "run"], ["dashboard", "--host", "0.0.0.0", "--port", "9119"]])
def test_passerelle_hors_s6_arretee_par_le_greffon(ressources, image, commande):
    """--entrypoint hermes : ni s6, ni gardes. La sentinelle du greffon arrête la passerelle et
    le tableau de bord de production (HERMES_HOME=/opt/data), code 78."""
    code, journal = _executer_jusqu_a_l_arret(ressources, image, "--entrypoint", "/opt/hermes/.venv/bin/hermes",
                                              commande=commande)
    afficher(f"hermes {' '.join(commande)} hors de s6 : code {code}", _lignes_acp(journal))
    assert code == 78
    attendu = "gateway run" if commande[0] == "gateway" else "dashboard"
    assert f"[acp] REFUS : « hermes {attendu} » a été lancé hors de la chaîne s6 d'ACP" in journal


@pytest.mark.parametrize("fichiers, motif", [
    ({"hooks/intrus/HOOK.yaml": "name: intrus\nevents: [agent:start]\n",
      "hooks/intrus/handler.py": "def handle(*a):\n    pass\n"}, "/opt/data/hooks n'est pas vide (« intrus »)"),
    ({"scripts/tache.py": "print('cron')\n"}, "/opt/data/scripts n'est pas vide (« tache.py »)"),
    # Relecture P2 : un profil secondaire avec un script cron ou un crochet dans SES répertoires.
    # Sans la garde par profil, la passerelle démarrait et le script tournait sous l'uid 10000.
    ({"profiles/intrus/SOUL.md": "Profil secondaire.\n", "profiles/intrus/scripts/tache.py": "print('cron')\n"},
     "/opt/data/profiles/intrus/scripts n'est pas vide (« tache.py »)"),
    ({"profiles/intrus/SOUL.md": "Profil secondaire.\n",
      "profiles/intrus/hooks/intrus/HOOK.yaml": "name: intrus\nevents: [agent:start]\n",
      "profiles/intrus/hooks/intrus/handler.py": "def handle(*a):\n    pass\n"},
     "/opt/data/profiles/intrus/hooks n'est pas vide (« intrus »)"),
], ids=["hooks", "scripts", "profil_scripts", "profil_hooks"])
def test_hooks_scripts_refus(ressources, image, fichiers, motif):
    volume = ressources.volume(image, fichiers)
    code, journal = demarrer_jusqu_a_l_arret(ressources, image, ENV_VALIDE, volume)
    afficher(f"volume avec {sorted(fichiers)} : code {code}", _lignes_acp(journal))
    assert code == 1
    assert f"[acp] REFUS : {motif}" in journal
    assert "fatal: hook /opt/acp/bin/acp-gardes exited 1" in journal
    assert "[stage2]" not in journal


def _demarrer_et_observer(ressources, image: str, volume: str, delai: float = 180):
    """Démarre en arrière-plan et rend (issue, conteneur, journal), l'issue valant « arrêté (code N) »,
    « démarré » (tableau de bord prêt) ou « ni arrêté ni prêt » : un test qui attend un refus décrit ainsi un
    démarrage indu au lieu d'expirer."""
    nom = ressources.nom("secu")
    ressources.conteneurs.append(nom)
    docker("run", "-d", "--name", nom, "-v", f"{volume}:/opt/data", *SANS_CONTEXT7, *options_env(ENV_VALIDE), image)
    conteneur = Conteneur(nom)
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        etat = docker("inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", nom, verifier=False).stdout.split()
        if etat and etat[0] == "false":
            return f"arrêté (code {etat[1]})", conteneur, conteneur.journaux()
        code = conteneur.executer(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                                   "http://127.0.0.1:9119/api/status"]).stdout.strip()
        if code == "200":
            time.sleep(10)  # laisse la passerelle et le tableau de bord charger leur environnement
            return "démarré", conteneur, conteneur.journaux()
        time.sleep(2)
    return "ni arrêté ni prêt", conteneur, conteneur.journaux()


SONDE_PORTEE = ("import json, os; from hermes_cli.env_loader import load_hermes_dotenv; load_hermes_dotenv(); "
                "from hermes_cli import managed_scope; import sys; sys.stderr.write('SONDE ' + json.dumps({"
                "'portee_geree': str(managed_scope.get_managed_dir()), "
                "'HERMES_MANAGED_DIR': os.environ.get('HERMES_MANAGED_DIR'), "
                "'HERMES_TUI_TOOLSETS': os.environ.get('HERMES_TUI_TOOLSETS')}) + '\\n')")


def test_op_env_qui_deplace_la_portee_geree_refuse_le_demarrage(ressources, image):
    """SECU-1 : /opt/data/.op.env est chargé AVANT la portée gérée (env_loader.py:441-443) ; HERMES_MANAGED_DIR
    posée là choisirait le .env géré lu (managed_scope.py:52), et les gardes ne lisaient que .env."""
    volume = ressources.volume(image, {
        ".op.env": "HERMES_MANAGED_DIR=/opt/data/faux\n",
        "faux/.env": "HERMES_TUI_TOOLSETS=terminal,file,code_execution\n",
        "faux/config.yaml": "platform_toolsets:\n  cli: [terminal, file, code_execution]\n"})
    issue, conteneur, journal = _demarrer_et_observer(ressources, image, volume)
    sonde = ""
    if issue == "démarré":
        sonde = conteneur.executer(["/opt/hermes/.venv/bin/python", "-c", SONDE_PORTEE], utilisateur="hermes").stderr
    afficher(f".op.env avec HERMES_MANAGED_DIR : {issue}", _lignes_acp(journal) + ("\n" + sonde if sonde else ""))
    assert issue == "arrêté (code 1)", f"{issue} ; sonde : {sonde}"
    assert "[acp] REFUS : " in journal
    assert "/opt/data/.op.env définit la variable interdite HERMES_MANAGED_DIR" in journal
    assert "[stage2]" not in journal


def test_source_de_secrets_du_volume_refuse_le_demarrage(ressources, image):
    """SECU-2 : ``secrets.command`` du config.yaml du volume, lu SANS la portée gérée (env_loader.py:620-640),
    serait lancé par ``/bin/sh -c`` au chargement de l'environnement de CHAQUE processus de Hermes
    (agent/secret_sources/command.py:61-80), hors des trois couches ; sa sortie KEY=VALUE est appliquée AVANT
    la portée gérée (env_loader.py:471-473) et pourrait même la déplacer."""
    commande = "touch /opt/data/temoin-secrets && echo HERMES_MANAGED_DIR=/opt/data/faux"
    volume = ressources.volume(image, {
        "config.yaml": f"secrets:\n  command:\n    enabled: true\n    command: \"{commande}\"\n",
        "faux/.env": "HERMES_TUI_TOOLSETS=terminal,file,code_execution\n"})
    issue, conteneur, journal = _demarrer_et_observer(ressources, image, volume)
    sonde = ""
    if issue == "démarré":
        sonde = conteneur.executer(["/opt/hermes/.venv/bin/python", "-c", SONDE_PORTEE], utilisateur="hermes").stderr
        sonde += conteneur.sh("ls -ln /opt/data/temoin-secrets 2>&1").stdout
    temoin = docker("run", "--rm", "-v", f"{volume}:/opt/data", "--entrypoint", "sh", image, "-c",
                    "ls -ln /opt/data/temoin-secrets 2>/dev/null || echo absent", verifier=False).stdout.strip()
    afficher(f"secrets.command dans le volume : {issue}",
             _lignes_acp(journal) + f"\ntémoin : {temoin}" + ("\n" + sonde if sonde else ""))
    assert issue == "arrêté (code 1)", f"{issue} ; témoin : {temoin} ; sonde : {sonde}"
    assert "[acp] REFUS : /opt/data/config.yaml active la source externe de secrets « command »" in journal
    assert temoin == "absent", temoin
    assert "[stage2]" not in journal


SONDE_HOME = ("import json, os; from hermes_cli.env_loader import load_hermes_dotenv; load_hermes_dotenv(); "
              "load_hermes_dotenv(); from hermes_constants import get_hermes_home; "
              "from hermes_cli import managed_scope; import sys; sys.stderr.write('SONDE ' + json.dumps({"
              "'home': str(get_hermes_home()), 'portee_geree': str(managed_scope.get_managed_dir()), "
              "'HERMES_TUI_TOOLSETS': os.environ.get('HERMES_TUI_TOOLSETS')}) + '\\n')")


def test_home_du_volume_qui_redirige_hermes_refuse_le_demarrage(ressources, image):
    """Audit défensif, manque 1 : HERMES_HOME posée dans /opt/data/.env est publiée par Hermes puis suivie
    (hermes_constants.py:112-119 et 161-170) ; le chargement suivant lit le .env d'un répertoire qu'aucune garde
    n'inspecte, qui peut à son tour déplacer la portée gérée."""
    volume = ressources.volume(image, {
        ".env": "HERMES_HOME=/opt/data/autre\n",
        "autre/.env": "HERMES_MANAGED_DIR=/opt/data/faux\n",
        "faux/.env": "HERMES_TUI_TOOLSETS=terminal,file,code_execution\n"})
    issue, conteneur, journal = _demarrer_et_observer(ressources, image, volume)
    sonde = ""
    if issue == "démarré":
        sonde = conteneur.executer(["/opt/hermes/.venv/bin/python", "-c", SONDE_HOME], utilisateur="hermes").stderr
    afficher(f".env avec HERMES_HOME : {issue}", _lignes_acp(journal) + ("\n" + sonde if sonde else ""))
    assert issue == "arrêté (code 1)", f"{issue} ; sonde : {sonde}"
    assert "/opt/data/.env définit la variable interdite HERMES_HOME" in journal
    assert "[stage2]" not in journal


def _deposer_octets(image: str, volume: str, chemin: str, octets: bytes) -> None:
    """Dépose un fichier aux octets exacts (UTF-16, NUL) dans le volume, rendu à l'uid hermes."""
    import base64

    cible = f"/opt/data/{chemin}"
    docker("run", "--rm", "-i", "-v", f"{volume}:/opt/data", "--entrypoint", "sh", image, "-c",
           f'base64 -d > "{cible}" && chown 10000:10000 "{cible}"', entree=base64.b64encode(octets).decode("ascii"))


@pytest.mark.parametrize("forme", ["utf16", "nul"])
def test_managed_dir_que_seul_hermes_decode_refuse_le_demarrage(ressources, image, forme):
    """Audit défensif, manque 2 : la garde lisait les .env en UTF-8 avec python-dotenv seul ; Hermes réécrit un
    .env UTF-16 en UTF-8 et retire les octets NUL avant de le charger (env_loader.py:347-370), puis publie
    HERMES_MANAGED_DIR, qui choisit le .env géré lu."""
    ligne = "HERMES_MANAGED_DIR=/opt/data/faux\n"
    octets = ligne.encode("utf-16") if forme == "utf16" else ligne.replace("_DIR", "\x00_DIR").encode("utf-8")
    volume = ressources.volume(image, {"faux/.env": "HERMES_TUI_TOOLSETS=terminal,file,code_execution\n"})
    _deposer_octets(image, volume, ".env", octets)
    issue, conteneur, journal = _demarrer_et_observer(ressources, image, volume)
    sonde = ""
    if issue == "démarré":
        sonde = conteneur.executer(["/opt/hermes/.venv/bin/python", "-c", SONDE_PORTEE], utilisateur="hermes").stderr
    afficher(f".env {forme} avec HERMES_MANAGED_DIR : {issue}", _lignes_acp(journal) + ("\n" + sonde if sonde else ""))
    assert issue == "arrêté (code 1)", f"{issue} ; sonde : {sonde}"
    assert "/opt/data/.env définit la variable interdite HERMES_MANAGED_DIR" in journal
    assert "[stage2]" not in journal


@pytest.fixture(scope="module")
def hermes_railway(ressources, image) -> Conteneur:
    """Conteneur « comme sur Railway » : marqueurs, volume déclaré, commit déployé."""
    env = dict(ENV_VALIDE, RAILWAY_ENVIRONMENT_ID="env-contrat", RAILWAY_SERVICE_ID="svc-contrat",
               RAILWAY_DEPLOYMENT_ID="dep-contrat", RAILWAY_VOLUME_MOUNT_PATH="/opt/data",
               RAILWAY_GIT_COMMIT_SHA=SHA, RAILWAY_RUN_UID="0")
    # Un profil secondaire SAIN (relecture P2) : ses hooks/ et scripts/ doivent être repris par root.
    volume = ressources.volume(image, {"profiles/coder/SOUL.md": "Profil de contrat.\n"})
    return lancer(ressources, image, env, volume=volume)


def test_hooks_scripts_root_et_refus(hermes_railway):
    repertoires = ("/opt/data/hooks /opt/data/scripts /opt/data/profiles/coder/hooks "
                   "/opt/data/profiles/coder/scripts")
    etat = hermes_railway.sh(f"stat -c '%U:%G %a %n' {repertoires}", verifier=True).stdout
    afficher("hooks/ et scripts/ au démarrage (racine et profil coder)", etat)
    assert len(etat.strip().splitlines()) == 4
    for ligne in etat.strip().splitlines():
        assert ligne.startswith("root:root 755 "), ligne
    for chemin in ("/opt/data/hooks/intrus", "/opt/data/scripts/intrus.py", "/opt/data/profiles/coder/hooks/intrus",
                   "/opt/data/profiles/coder/scripts/intrus.py"):
        assert hermes_railway.sh(f"mkdir -p {chemin}", utilisateur="hermes").returncode != 0, chemin
    assert hermes_railway.sh("touch /opt/data/controle /opt/data/profiles/coder/controle",
                             utilisateur="hermes").returncode == 0
    journal = hermes_railway.journaux()
    assert "ainsi que hooks/ et scripts/ de 1 profil(s) (coder)." in journal
    etat_demarrage = json.loads(hermes_railway.sh("cat /run/acp/etat-demarrage.json", verifier=True).stdout)
    assert etat_demarrage["repertoires_executes"]["profils"] == ["coder"]


def test_diagnostiquer_sous_s6_sur_un_conteneur_sain(hermes_railway):
    """Relecture P2 : sous s6, /run/s6/container_environment termine chaque valeur par un saut de
    ligne ; `diagnostiquer` le lisait tel quel et rendait 29 faux constats (code 1) sur un
    conteneur sain. Exigé : aucun constat, code 0, depuis une session sans environnement."""
    resultat = hermes_railway.executer(["env", "-i", "/opt/hermes/.venv/bin/python", "-I", "-B",
                                        "/opt/acp/bin/acp_demarrage.py", "diagnostiquer"])
    afficher(f"diagnostiquer sous s6, conteneur sain : code {resultat.returncode}", resultat.stdout + resultat.stderr)
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert "source de l'environnement de référence : /run/s6/container_environment (PID 1 : " in resultat.stdout
    assert f"commit déployé : {SHA}." in resultat.stdout
    assert "managed scope installée : déploiement." in resultat.stdout
    assert "aucun constat ; code 0." in resultat.stdout


def test_volume_railway_simule(ressources, image, hermes_railway):
    journal = hermes_railway.journaux()
    afficher("démarrage « Railway » (marqueurs, volume, commit)", _lignes_acp(journal))
    assert f"[acp] commit déployé : {SHA}" in journal
    assert "info: hook /opt/acp/bin/acp-gardes exited 0" in journal
    etat = json.loads(hermes_railway.sh("cat /run/acp/etat-demarrage.json", verifier=True).stdout)
    # Schéma 2 en P2 ; 3 depuis P3 (bloc catalogue ajouté, rien de retiré) ; 4 depuis P7 (script du bilan).
    assert etat["deploiement"] == {"commit": SHA} and etat["schema"] == 4
    base = dict(ENV_VALIDE, RAILWAY_ENVIRONMENT_ID="env-contrat", RAILWAY_SERVICE_ID="svc-contrat")
    cas = {
        "sans_volume": (base, "le volume du service doit être monté sur /opt/data (reçu « aucun volume »)"),
        "autre_chemin": (dict(base, RAILWAY_VOLUME_MOUNT_PATH="/data"), "(reçu « /data »)"),
        "uid": (dict(base, RAILWAY_VOLUME_MOUNT_PATH="/opt/data", RAILWAY_RUN_UID="1000"),
                "la variable RAILWAY_RUN_UID vaut « 1000 »"),
    }
    for libelle, (env, motif) in cas.items():
        code, journal = demarrer_jusqu_a_l_arret(ressources, image, env)
        afficher(f"Railway simulé « {libelle} » : code {code}", _lignes_acp(journal))
        assert code == 1 and f"[acp] REFUS : " in journal and motif in journal, libelle


# =========================================================================== 2. pile de test


MODELE = """\
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""

JOURNAL_FACTICE = "/tmp/modele-factice.jsonl"
SCENARIOS = "/tmp/acp-scenarios.json"


@pytest.fixture(scope="module")
def pile(ressources, image_tests):
    """Faux fournisseur d'identité, cible « attache.acp.test » qui consigne toute requête, et
    Hermes (image de test) avec le modèle factice, sur un réseau privé jetable."""
    reseau = ressources.reseau()
    idp = ressources.nom("idp")
    ressources.conteneurs.append(idp)
    docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
           "--entrypoint", "/opt/hermes/.venv/bin/python", image_tests,
           "/opt/acp-tests/outils/idp_factice.py", "--emetteur", "https://idp.acp.test:8443",
           "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem", "--cle", "/opt/acp-tests/ac/idp.key")
    attache = ressources.nom("attache")
    ressources.conteneurs.append(attache)
    docker("run", "-d", "--name", attache, "--network", reseau, "--network-alias", "attache.acp.test",
           "--entrypoint", "/opt/hermes/.venv/bin/python", image_tests, "-u", "-m", "http.server", "80")
    volume = ressources.volume(image_tests, {"config.yaml": MODELE})
    hermes = lancer(ressources, image_tests, ENV_VALIDE, volume=volume, reseau=reseau)
    hermes.sh("mkdir -p /tmp/acp-temoins && chmod 1777 /tmp/acp-temoins", verifier=True)
    hermes.executer(["sh", "-c", f"echo '{{}}' > {SCENARIOS}"], utilisateur="hermes", verifier=True)
    docker("exec", "-d", "-u", "hermes", hermes.nom, "/opt/hermes/.venv/bin/python",
           "/opt/acp-tests/outils/modele_factice.py", "--port", "18080", "--journal", JOURNAL_FACTICE,
           "--scenarios", SCENARIOS)
    attendre_modele_factice(hermes, JOURNAL_FACTICE)
    hermes.attache = attache  # type: ignore[attr-defined]
    return hermes


def jeton(hermes: Conteneur) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"],
                             verifier=True).stdout
    return json.loads(sortie)["id_token"]


def vider_journal(hermes: Conteneur) -> None:
    hermes.executer(["sh", "-c", f": > {JOURNAL_FACTICE}"], utilisateur="hermes", verifier=True)


def requetes(hermes: Conteneur) -> list:
    brut = hermes.sh(f"cat {JOURNAL_FACTICE} 2>/dev/null", verifier=True).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def resultats_outils(hermes: Conteneur) -> List[str]:
    vus: List[str] = []
    for requete in requetes(hermes):
        for resultat in requete.get("resultats_outils") or []:
            if resultat["contenu"] not in vus:
                vus.append(resultat["contenu"])
    return vus


def temoins(hermes: Conteneur) -> List[str]:
    return hermes.sh("ls -A /tmp/acp-temoins", verifier=True).stdout.split()


def attendre_resultat(hermes: Conteneur, motif: str, delai: float = 150) -> List[str]:
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        vus = resultats_outils(hermes)
        if any(motif in v for v in vus):
            return vus
        time.sleep(2)
    raise AssertionError(f"« {motif} » absent des résultats d'outils reçus par le modèle : {resultats_outils(hermes)}")


# ============================================================ 3. outils d'exécution refusés


CAS_API_SERVER = {
    "terminal": "Tool 'terminal' does not exist",
    "write_file": "Tool 'write_file' does not exist",
    "read_file": "Tool 'read_file' does not exist",
    "execute_code": "Tool 'execute_code' does not exist",
    "cronjob_manage": "Tool 'cronjob_manage' does not exist",
    "delegate_task": "Tool 'delegate_task' does not exist",
    "browser_navigate": "Tool 'browser_navigate' does not exist",
    # Pont NON RÉSOLU (terminal n'est pas différable, tools/tool_search.py:543-571) : Hermes ne le
    # déballe pas, la garde reçoit « tool_call » et le refuse.
    "tool_call": "Refusé par ACP : l'outil « tool_call » n'est pas autorisé",
    # Pont RÉSOLU vers un outil admis (relecture P2) : Hermes le déballe AVANT le crochet
    # (agent/tool_executor.py:390-431) ; la garde juge todo_list, qui s'exécute.
    "tool_call>todo_list": "carte de test ACP",
}


def test_api_server_http_refuse_les_outils_d_execution(pile):
    """Vrai tour d'agent de la passerelle par l'api_server HTTP (127.0.0.1:8642), qui construit
    l'AIAgent SANS agent.disabled_toolsets (api_server.py:2231-2270)."""
    rapport = []
    for outil, attendu in CAS_API_SERVER.items():
        vider_journal(pile)
        corps = json.dumps({"model": "hermes-agent", "messages": [{"role": "user", "content": f"OUTIL:{outil}"}]})
        reponse = pile.sh("K=$(grep '^API_SERVER_KEY=' /opt/data/.env | cut -d= -f2-); "
                          "curl -s -m 150 http://127.0.0.1:8642/v1/chat/completions -H \"Authorization: Bearer $K\" "
                          "-H 'Content-Type: application/json' --data-binary @-", entree=corps, verifier=True).stdout
        offerts = next((r["outils_offerts"] for r in requetes(pile) if r.get("outil_demande") == outil), None)
        vus = resultats_outils(pile)
        rapport.append(f"{outil} : offerts={offerts} ; résultat={vus[:1]} ; réponse={reponse[:120]}")
        assert offerts is not None, f"le modèle n'a pas été interrogé pour {outil}"
        # tool_call (pont des outils différés) est offert ; il n'est refusé que non résolu.
        assert outil == "tool_call" or outil not in offerts
        assert any(attendu in v for v in vus), (outil, vus)
        if outil == "tool_call>todo_list":
            assert "tool_call" in offerts and not any("Refusé par ACP" in v for v in vus), vus
    afficher("api_server HTTP : outils d'exécution demandés par le modèle", "\n".join(rapport))
    assert temoins(pile) == []


def _creer_tache_cron(pile: Conteneur, message: str, nom: str) -> str:
    sortie = pile.executer(["sh", "-c", f"cd /opt/data && hermes cron create 1h '{message}' --name {nom}"],
                           utilisateur="hermes", verifier=True).stdout
    trouve = re.search(r"Created job: ([0-9a-f]{6,})", sortie)
    assert trouve, sortie
    return trouve.group(1)


@pytest.mark.parametrize("outil, attendu", [
    ("terminal", "Tool 'terminal' does not exist"),
    ("tool_call", "Refusé par ACP : l'outil « tool_call » n'est pas autorisé"),
])
def test_agent_cron_refuse_terminal(pile, outil, attendu):
    """Une tâche cron créée par le propriétaire, dont le prompt fait demander un outil
    d'exécution : l'agent cron ne l'a pas (jeu cron, retraits). Le pont tool_call vers terminal,
    offert mais NON RÉSOLU (terminal n'est pas différable), arrive à la garde sous son propre nom :
    son refus « Refusé par ACP » prouve la garde DANS le processus qui exécute la tâche. (Un pont
    résolu serait jugé sur l'outil sous-jacent : test_pont_tool_call_juge_l_outil_sous_jacent.)"""
    vider_journal(pile)
    tache = _creer_tache_cron(pile, f"OUTIL:{outil}", f"acp-contrat-{outil.replace('_', '-')}")
    try:
        pile.executer(["sh", "-c", f"cd /opt/data && hermes cron run {tache} && timeout 200 hermes cron tick"],
                      utilisateur="hermes", verifier=True, delai=260)
        vus = attendre_resultat(pile, attendu)
        offerts = next((r["outils_offerts"] for r in requetes(pile) if r.get("outil_demande") == outil), [])
        afficher(f"agent cron : {outil}", f"offerts : {offerts}\nrésultats : {_texte(vus)}")
        assert outil == "tool_call" or outil not in offerts
        assert temoins(pile) == []
    finally:
        pile.executer(["sh", "-c", f"cd /opt/data && hermes cron remove {tache}"], utilisateur="hermes")


def _cartes(pile: Conteneur) -> List[dict]:
    sortie = pile.executer(["sh", "-c", "cd /opt/data && hermes kanban list --archived --json"],
                           utilisateur="hermes", verifier=True).stdout
    return json.loads(sortie)


def test_worker_kanban_refuse_les_outils_d_execution(pile):
    """Trois cartes créées par le PROPRIÉTAIRE ; leurs vrais workers (python -m hermes_cli.main -p
    default --cli --accept-hooks --toolsets … chat -q) reçoivent du modèle une demande de
    terminal, de kanban_create (skills, modèle, fournisseur, workspace_path /opt/data) et de
    kanban_attach_url. Le refus « Refusé par ACP » de kanban_create et de kanban_attach_url, qui
    sont OFFERTS au worker, prouve la garde DANS le processus du worker."""
    vider_journal(pile)
    identifiants: Dict[str, str] = {}
    for outil in ("terminal", "kanban_create", "kanban_attach_url"):
        sortie = pile.executer(["sh", "-c", f"cd /opt/data && hermes kanban create 'Carte contrat {outil}' "
                                            f"--assignee default --body 'Scénario {outil}' --initial-status blocked "
                                            "--max-retries 1 --json"], utilisateur="hermes", verifier=True).stdout
        identifiants[outil] = json.loads(sortie)["id"]
    avant = {c["id"] for c in _cartes(pile)}
    scenarios = {f"work kanban task {tid}": outil for outil, tid in identifiants.items()}
    pile.executer(["sh", "-c", f"cat > {SCENARIOS}"], utilisateur="hermes", entree=json.dumps(scenarios),
                  verifier=True)
    pile.executer(["sh", "-c", "cd /opt/data && hermes kanban unblock " + " ".join(identifiants.values())],
                  utilisateur="hermes", verifier=True)
    vus = attendre_resultat(pile, "Refusé par ACP : l'agent ne crée pas de carte kanban lui-même", 240)
    vus = attendre_resultat(pile, "Refusé par ACP : ce téléchargement ne résiste pas au rebinding DNS", 240)
    vus = attendre_resultat(pile, "Tool 'terminal' does not exist", 240)
    workers = [r for r in requetes(pile) if "kanban_create" in (r.get("outils_offerts") or [])]
    time.sleep(10)  # laisse les workers finir (kanban_complete) avant de compter les cartes
    apres = _cartes(pile)
    nouvelles = [c for c in apres if c["id"] not in avant]
    requetes_attache = docker("logs", pile.attache, verifier=False)  # type: ignore[attr-defined]
    afficher("workers kanban", f"cartes : {_texte(identifiants)}\n"
                               f"outils offerts au worker : {workers[0]['outils_offerts'] if workers else None}\n"
                               f"résultats : {_texte(vus)}\nnouvelles cartes : {nouvelles}\n"
                               f"journal d'attache.acp.test : {(requetes_attache.stdout + requetes_attache.stderr)!r}")
    assert workers, "aucun worker n'a interrogé le modèle avec kanban_create offert"
    assert "kanban_attach_url" in workers[0]["outils_offerts"]
    assert "terminal" not in workers[0]["outils_offerts"]
    assert nouvelles == []
    assert "GET" not in requetes_attache.stdout + requetes_attache.stderr
    assert temoins(pile) == []


# ============================================================ 4. preview.restart (BLOQUANT)


def _client_ws(pile: Conteneur, mode: str) -> dict:
    sortie = pile.executer(["/opt/hermes/.venv/bin/python", "/opt/acp-tests/outils/client_ws.py", mode, jeton(pile),
                            "/tmp/acp-client-ws.json"], delai=300)
    assert sortie.returncode == 0, sortie.stdout[-2000:] + sortie.stderr[-4000:]
    return json.loads(pile.sh("cat /tmp/acp-client-ws.json", verifier=True).stdout)


def test_preview_restart_par_api_ws(pile):
    """BLOQUANT, non ignorable (correction R1-3). Ticket POST /api/auth/ws-ticket avec le jeton du
    faux fournisseur, puis session.create et preview.restart sur /api/ws du VRAI tableau de bord :
    l'agent caché (terminal et fichiers codés en dur) tourne DANS le processus du tableau de
    bord ; le modèle demande terminal ; la garde le refuse, aucun témoin. S'il ne peut pas être
    piloté, ce test échoue : il n'est jamais marqué ignoré."""
    vider_journal(pile)
    resultat = _client_ws(pile, "preview-restart")
    requetes_modele = [r for r in requetes(pile) if r.get("outils_offerts")]
    vus = resultats_outils(pile)
    afficher("preview.restart par /api/ws", f"événements : {_texte(resultat['evenements'])}\n"
                                           f"résultats d'outils : {_texte(vus)}")
    assert "result" in resultat["reponse"], resultat["reponse"]
    assert any("terminal" in r["outils_offerts"] and r.get("outil_demande") == "terminal" for r in requetes_modele)
    assert any("Refusé par ACP : l'outil « terminal »" in v for v in vus), vus
    assert temoins(pile) == []


def test_session_du_tableau_de_bord_sans_outil_d_execution(pile):
    resultat = _client_ws(pile, "session")
    outils = sorted({o for liste in (resultat["outils_session"] or {}).values() for o in liste})
    afficher("outils d'une session du tableau de bord (/api/ws)", _texte(resultat["outils_session"]))
    assert outils and "web_search" in outils
    assert not {"terminal", "read_file", "write_file", "execute_code", "delegate_task", "cronjob_manage"} & set(outils)
    assert not [o for o in outils if o.startswith("browser_")]


def test_meta_garde_execution_dans_le_tableau_de_bord(pile):
    code, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile))
    afficher("meta : garde d'exécution, réseau, déploiement",
             _texte({k: meta.get(k) for k in ("garde_execution", "reseau", "deploiement", "alertes")}))
    assert code == 200
    garde = meta["garde_execution"]
    assert garde["processus"] == "processus du tableau de bord (sert /api/ws)"
    assert (garde["decouverte"], garde["presente_dans_le_gestionnaire"], garde["enregistree"]) == ("reussie", True, True)
    assert garde["alerte"] is None
    assert meta["deploiement"] == {"commit": None}
    assert meta["reseau"]["schema_vu"] == "http" and meta["reseau"]["pair"] == "127.0.0.1"


def test_aucune_installation_paresseuse(pile):
    journaux = pile.journaux() + pile.sh("cat /opt/data/logs/*.log /opt/data/logs/gateways/*/current 2>/dev/null",
                                         verifier=True).stdout
    paresseux = pile.sh("ls -A /opt/data/lazy-packages 2>/dev/null", verifier=True).stdout.split()
    afficher("installations paresseuses", f"lazy-packages : {paresseux}\n"
                                          f"« uv pip install » dans les journaux : {'uv pip install' in journaux}")
    assert "uv pip install" not in journaux
    assert [p for p in paresseux if p not in (".lock", ".python-abi")] == []


CONFIG_PIEGEE = """\
toolsets: [hermes-cli, debugging, coding]
platform_toolsets:
  api_server: [web, debugging, hermes-api-server, terminal, file, code_execution]
  cli: [web, debugging, coding, hermes-cli, terminal, file, browser, delegation]
  cron: [web, debugging, terminal]
agent:
  disabled_toolsets: []
  coding_context: focus
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""

ENV_PIEGE = """
HERMES_TUI_TOOLSETS=terminal,file,code_execution
HERMES_BIN=/opt/data/faux-hermes
HERMES_ACCEPT_HOOKS=1
HERMES_SAFE_MODE=1
HERMES_YOLO_MODE=1
HERMES_ALLOW_PRIVATE_URLS=true
HERMES_DISABLE_LAZY_INSTALLS=0
"""


def test_volume_piege_apres_relance(pile):
    """L'agent (uid hermes) aurait piégé /opt/data/config.yaml et /opt/data/.env avant P2, puis
    relancé la passerelle et le tableau de bord : aucune surface ne rend d'outil d'exécution, ni
    après relance, ni après redémarrage du conteneur, et la configuration gérée est intacte."""
    empreintes = "sha256sum /etc/hermes/config.yaml /etc/hermes/.env"
    avant = pile.sh(empreintes, verifier=True).stdout
    pile.executer(["sh", "-c", "cat > /opt/data/config.yaml"], utilisateur="hermes", entree=CONFIG_PIEGEE,
                  verifier=True)
    pile.executer(["sh", "-c", "cat >> /opt/data/.env"], utilisateur="hermes", entree=ENV_PIEGE, verifier=True)
    for service in ("dashboard", "gateway-default"):
        assert pile.executer(["/command/s6-svc", "-r", f"/run/service/{service}"],
                             utilisateur="hermes").returncode == 0
    time.sleep(4)
    pile.attendre_pret()
    pile.attendre_passerelle()
    for contexte in ("relance par l'agent", "redémarrage du conteneur"):
        if contexte == "redémarrage du conteneur":
            docker("restart", pile.nom, delai=240)
            pile.attendre_pret()
            pile.attendre_passerelle()
            pile.sh("mkdir -p /tmp/acp-temoins && chmod 1777 /tmp/acp-temoins", verifier=True)
            docker("exec", "-d", "-u", "hermes", pile.nom, "/opt/hermes/.venv/bin/python",
                   "/opt/acp-tests/outils/modele_factice.py", "--port", "18080", "--journal", JOURNAL_FACTICE,
                   "--scenarios", SCENARIOS)
            attendre_modele_factice(pile, JOURNAL_FACTICE)
        vider_journal(pile)
        corps = json.dumps({"model": "hermes-agent", "messages": [{"role": "user", "content": "OUTIL:terminal"}]})
        pile.sh("K=$(grep '^API_SERVER_KEY=' /opt/data/.env | cut -d= -f2-); "
                "curl -s -m 150 http://127.0.0.1:8642/v1/chat/completions -H \"Authorization: Bearer $K\" "
                "-H 'Content-Type: application/json' --data-binary @-", entree=corps, verifier=True)
        vus = resultats_outils(pile)
        session = _client_ws(pile, "session")
        outils_session = sorted({o for l in (session["outils_session"] or {}).values() for o in l})
        afficher(f"volume piégé, {contexte}", f"api_server : {vus}\nsession du tableau de bord : {outils_session}")
        assert any("Tool 'terminal' does not exist" in v for v in vus), vus
        assert "terminal" not in outils_session and "write_file" not in outils_session
        assert temoins(pile) == []
    assert pile.sh(empreintes, verifier=True).stdout == avant
    # Les variables piégées restent neutralisées pour les processus de Hermes.
    valeurs = pile.executer(["/opt/hermes/.venv/bin/python", "-c",
                             "import os; from hermes_cli.env_loader import load_hermes_dotenv; "
                             "load_hermes_dotenv(hermes_home='/opt/data', load_external_secrets=False); "
                             "import sys; sys.stderr.write(repr([os.environ.get(n) for n in ("
                             "'HERMES_TUI_TOOLSETS', 'HERMES_SAFE_MODE', 'HERMES_ALLOW_PRIVATE_URLS', "
                             "'HERMES_DISABLE_LAZY_INSTALLS')]))"], utilisateur="hermes", verifier=True).stderr
    assert "['', '', 'false', '1']" in valeurs, valeurs


# ------------------------------------------------- SECU-1 : fenêtre de publication du .env du volume

# Pièges posés dans /opt/data/.op.env (chargé AVANT la portée gérée, override=False : env_loader.py:441-443).
OP_ENV_PIEGE = """\
HERMES_TUI_TOOLSETS=terminal,file,code_execution
HERMES_SAFE_MODE=1
HERMES_ALLOW_PRIVATE_URLS=true
HERMES_DASHBOARD_OIDC_ISSUER=https://intrus.example
"""

# Sonde lancée DANS le conteneur, sous l'uid hermes, avec la vraie portée gérée /etc/hermes. Elle relit les
# épingles de /etc/hermes/.env puis mesure, dans le code de Hermes à la version épinglée :
#  1. os.environ au point fixe où la portée gérée va être appliquée (env_loader.py:473) : toute valeur d'une
#     clé épinglée qui n'est pas la valeur gérée vient du volume ; et les outils qu'une session du tableau de
#     bord recevrait à cet instant (tui_gateway/server.py:1907-1946) ;
#  2. la course réelle : un fil recharge le .env comme la découverte MCP, le fil principal résout les outils
#     d'une session, pendant 4 s ;
#  3. reload.env (hermes_cli/config.py:2733-2747), que /api/ws sert sans filtre.
SONDE_SECU = r'''
import json, os, threading, time
from dotenv import dotenv_values
GERE = {k: (v or "") for k, v in dotenv_values("/etc/hermes/.env", interpolate=False).items()}
def ecarts():
    return sorted(k for k, v in GERE.items() if os.environ.get(k) is not None and os.environ.get(k) != v)
from hermes_cli import env_loader
from tui_gateway import server as tui
fenetre = {}
appliquer = env_loader._apply_managed_env
def sonde(*a, **k):
    if not fenetre:
        fenetre["ecarts"] = ecarts()
        fenetre["outils"] = tui._load_enabled_toolsets("tui")
    return appliquer(*a, **k)
env_loader._apply_managed_env = sonde
env_loader.load_hermes_dotenv()
env_loader._apply_managed_env = appliquer
arret = threading.Event()
compte = {"rechargements": 0, "lectures": 0, "avec_terminal": 0}
def recharger():
    while not arret.is_set():
        env_loader.load_hermes_dotenv()
        compte["rechargements"] += 1
fil = threading.Thread(target=recharger, daemon=True)
fil.start()
fin = time.monotonic() + 4.0
while time.monotonic() < fin:
    choisis = tui._load_enabled_toolsets("tui")
    compte["lectures"] += 1
    if choisis is None or "terminal" in choisis:
        compte["avec_terminal"] += 1
arret.set()
fil.join(10)
env_loader.load_hermes_dotenv()
from hermes_cli import config
config.reload_env()
apres_reload = {"ecarts": ecarts(), "supprimees": sorted(k for k in GERE if os.environ.get(k) is None)}
with open("/tmp/acp-sonde-secu.json", "w", encoding="utf-8") as flux:
    json.dump({"fenetre": fenetre, "concurrence": compte, "reload_env": apres_reload, "epingles": sorted(GERE)},
              flux, ensure_ascii=False)
'''


def _cles_epinglees_dans_le_volume(pile: Conteneur) -> str:
    """Lignes des .env du volume qui assignent une clé épinglée par /etc/hermes/.env (noms seulement)."""
    return pile.sh("for f in /opt/data/.env /opt/data/.op.env; do [ -f \"$f\" ] || continue; "
                   "for c in $(sed -n 's/^\\([A-Za-z_][A-Za-z0-9_]*\\)=.*/\\1/p' /etc/hermes/.env); do "
                   "grep -Eq \"^(export[[:space:]]+)?$c[[:space:]]*=\" \"$f\" && echo \"$f : $c\"; done; done; true",
                   verifier=True).stdout


def test_volume_piege_aucune_valeur_publiee_apres_relance(pile):
    """SECU-1. Cause racine du run 37784838264 (tentative 1), mesurée sans course : après une relance des
    services par l'agent, AUCUN processus de Hermes ne voit la valeur du volume d'une clé épinglée, ni au point
    où la portée gérée va être appliquée, ni pendant une course réelle, ni après reload.env."""
    pile.executer(["sh", "-c", "cat >> /opt/data/.env"], utilisateur="hermes", entree=ENV_PIEGE, verifier=True)
    pile.executer(["sh", "-c", "cat > /opt/data/.op.env"], utilisateur="hermes", entree=OP_ENV_PIEGE, verifier=True)
    avant = _cles_epinglees_dans_le_volume(pile)
    for service in ("dashboard", "gateway-default"):
        assert pile.executer(["/command/s6-svc", "-r", f"/run/service/{service}"],
                             utilisateur="hermes").returncode == 0
    time.sleep(4)
    pile.attendre_pret()
    pile.attendre_passerelle()
    apres = _cles_epinglees_dans_le_volume(pile)
    pile.executer(["/opt/hermes/.venv/bin/python", "-c", SONDE_SECU], utilisateur="hermes", verifier=True, delai=240)
    mesure = json.loads(pile.sh("cat /tmp/acp-sonde-secu.json", verifier=True).stdout)
    journal = "\n".join(l for l in pile.journaux().splitlines() if "SECU-1" in l)
    afficher("SECU-1 : volume piégé, relance par l'agent",
             f"clés épinglées dans le volume avant la relance :\n{avant}\naprès la relance :\n{apres or '(aucune)'}\n"
             f"journal SECU-1 :\n{journal or '(aucune ligne)'}\nmesure : {_texte(mesure)}")
    assert mesure["fenetre"]["ecarts"] == [], (
        "valeurs du volume publiées avant la portée gérée : " + ", ".join(mesure["fenetre"]["ecarts"]))
    outils = mesure["fenetre"]["outils"]
    assert isinstance(outils, list) and not {"terminal", "file", "code_execution"} & set(outils), outils
    assert mesure["concurrence"]["lectures"] > 20 and mesure["concurrence"]["rechargements"] > 20
    assert mesure["concurrence"]["avec_terminal"] == 0, mesure["concurrence"]
    assert mesure["reload_env"]["ecarts"] == [], mesure["reload_env"]
    assert apres == "", apres
    assert temoins(pile) == []


def _prompt_ws(pile: Conteneur, texte: str) -> dict:
    sortie = pile.executer(["/opt/hermes/.venv/bin/python", "/opt/acp-tests/outils/client_ws.py", "prompt", jeton(pile),
                            "/tmp/acp-client-ws.json", texte], delai=420)
    assert sortie.returncode == 0, sortie.stdout[-2000:] + sortie.stderr[-4000:]
    return json.loads(pile.sh("cat /tmp/acp-client-ws.json", verifier=True).stdout)


def test_couche_3_refuse_terminal_a_une_session_qui_l_a_recu(pile):
    """SECU-1, question 3 : la session fautive du run 37784838264 avait reçu terminal, file et code_execution.
    On reproduit EXACTEMENT ce résultat sans course (HERMES_TUI_TOOLSETS posé en root dans /etc/hermes/.env,
    volume toujours piégé, dont HERMES_SAFE_MODE=1), puis le modèle demande terminal dans une vraie session
    /api/ws du tableau de bord : la garde pre_tool_call d'acp-poste doit le refuser, sans témoin."""
    pile.sh("cp /etc/hermes/.env /tmp/acp-env-gere-sauve && "
            "sed -i 's#^HERMES_TUI_TOOLSETS=$#HERMES_TUI_TOOLSETS=terminal,file,code_execution#' /etc/hermes/.env && "
            "grep -q '^HERMES_TUI_TOOLSETS=terminal,file,code_execution$' /etc/hermes/.env", verifier=True)
    try:
        assert pile.executer(["/command/s6-svc", "-r", "/run/service/dashboard"]).returncode == 0
        time.sleep(4)
        pile.attendre_pret()
        code, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile))
        vider_journal(pile)
        resultat = _prompt_ws(pile, "OUTIL:terminal")
        demande = [r for r in requetes(pile) if r.get("outil_demande") == "terminal"]
        vus = resultats_outils(pile)
        afficher("SECU-1 : couche 3 face à une session qui a reçu terminal",
                 f"garde : {_texte(meta.get('garde_execution') if isinstance(meta, dict) else meta)}\n"
                 f"outils de la session : {_texte(resultat.get('outils_session'))}\n"
                 f"outils offerts au modèle : {demande[0]['outils_offerts'] if demande else None}\n"
                 f"résultats : {_texte(vus)}\ntémoins : {temoins(pile)}")
        assert code == 200
        garde = meta["garde_execution"]
        assert (garde["decouverte"], garde["presente_dans_le_gestionnaire"], garde["enregistree"]) == (
            "reussie", True, True)
        # Contrôle : la situation fautive est bien reproduite (sinon le test passerait à vide).
        assert demande and "terminal" in demande[0]["outils_offerts"], demande
        assert any("Refusé par ACP : l'outil « terminal »" in v for v in vus), vus
        assert temoins(pile) == []
    finally:
        pile.sh("cp /tmp/acp-env-gere-sauve /etc/hermes/.env && rm -f /tmp/acp-temoins/*", verifier=True)
        pile.executer(["/command/s6-svc", "-r", "/run/service/dashboard"])
        time.sleep(4)
        pile.attendre_pret()


PUT_EPINGLEES = {"HERMES_TUI_TOOLSETS": "terminal,file,code_execution", "HERMES_BIN": "/opt/data/faux-hermes",
                 "HERMES_SAFE_MODE": "1"}


def test_put_api_env_n_ecrit_aucune_cle_epinglee(pile):
    """SECU-1, faille 8 de la contre-vérification : une écriture du .env du volume EN COURS DE VIE rouvrirait la
    fenêtre jusqu'à la relance suivante, et « PUT /api/env » était cité comme moyen. Toute écriture du .env par
    Hermes passe par save_env_value (hermes_cli/config.py:2641-2646), qui refuse une clé que la portée gérée
    épingle (_env_write_blocked, config.py:2619-2632 ; managed_scope.is_env_managed) : la même fonction sert
    PUT /api/env (web_routers/config_env.py:292-307, credential_lifecycle.py:163-182) et la saisie d'un secret
    demandé par une skill (tui_gateway/agent_callbacks.py:207). Mesuré ici avec le propriétaire authentifié.
    Contrôle positif : une clé NON épinglée est bien écrite puis retirée par la même route (sinon le test
    réussirait à vide)."""
    cle = jeton(pile)
    avant = _cles_epinglees_dans_le_volume(pile)
    reponses = {nom: pile.json("/api/env", jeton=cle, methode="PUT", corps=json.dumps({"key": nom, "value": valeur}))
                for nom, valeur in PUT_EPINGLEES.items()}
    apres = _cles_epinglees_dans_le_volume(pile)
    valeurs_ecrites = pile.sh("grep -c -e 'terminal,file,code_execution' -e 'faux-hermes' /opt/data/.env || true",
                              verifier=True).stdout.strip()
    temoin = pile.json("/api/env", jeton=cle, methode="PUT", corps=json.dumps({"key": "ACP_TEMOIN_SECU", "value": "1"}))
    ecrit = pile.sh("grep -c '^ACP_TEMOIN_SECU=1$' /opt/data/.env || true", verifier=True).stdout.strip()
    retrait = pile.json("/api/env", jeton=cle, methode="DELETE", corps=json.dumps({"key": "ACP_TEMOIN_SECU"}))
    restant = pile.sh("grep -c '^ACP_TEMOIN_SECU=' /opt/data/.env || true", verifier=True).stdout.strip()
    refus = "\n".join(l for l in pile.journaux().splitlines() if "managed by your administrator" in l)
    afficher("SECU-1 : PUT /api/env de clés épinglées par le propriétaire authentifié",
             f"réponses : {_texte(reponses)}\nclés épinglées dans le volume avant :\n{avant or '(aucune)'}\n"
             f"après :\n{apres or '(aucune)'}\nvaleurs pièges dans /opt/data/.env : {valeurs_ecrites}\n"
             f"contrôle positif : PUT {temoin}, lignes écrites {ecrit}, DELETE {retrait}, lignes restantes {restant}\n"
             f"refus journalisés par Hermes :\n{refus or '(aucune ligne dans le journal du conteneur)'}")
    assert temoin[0] == 200 and ecrit == "1", ("la route n'écrit pas une clé ordinaire : test à vide", temoin, ecrit)
    assert retrait[0] == 200 and restant == "0", (retrait, restant)
    assert apres == avant == "", (avant, apres)
    assert valeurs_ecrites == "0", valeurs_ecrites


def test_preview_restart_par_api_ws_temoin_negatif(pile):
    """Témoin négatif du test bloquant, EN DERNIER (il modifie le conteneur) : la managed scope est
    altérée en root pour désactiver acp-poste, puis le tableau de bord est relancé. preview.restart
    exécute alors vraiment terminal : le test bloquant sait donc voir un échec."""
    pile.sh("cp /etc/hermes/config.yaml /tmp/acp-config-sauve.yaml && "
            "sed -i 's#    - dashboard_auth/drain#    - dashboard_auth/drain\\n    - acp-poste#' /etc/hermes/config.yaml",
            verifier=True)
    try:
        assert pile.executer(["/command/s6-svc", "-r", "/run/service/dashboard"]).returncode == 0
        time.sleep(4)
        pile.attendre_pret()
        vider_journal(pile)
        _client_ws(pile, "preview-restart")
        vus = resultats_outils(pile)
        afficher("témoin négatif : preview.restart sans acp-poste", f"résultats : {_texte(vus)}\n"
                                                                    f"témoins : {temoins(pile)}")
        assert not any("Refusé par ACP" in v for v in vus)
        assert "terminal" in temoins(pile)
    finally:
        pile.sh("cp /tmp/acp-config-sauve.yaml /etc/hermes/config.yaml && rm -f /tmp/acp-temoins/*", verifier=True)
        pile.executer(["/command/s6-svc", "-r", "/run/service/dashboard"])


# ============================================================ 5. maintenance


@pytest.mark.parametrize("cmd_herite", [True, False], ids=["cmd_herite_garde", "cmd_herite_retire"])
def test_maintenance_sleep_infinity(ressources, image, cmd_herite):
    """Start Command de maintenance « /bin/sh -c "exec sleep infinity" » (R2-2) : elle remplace
    l'ENTRYPOINT ; que Railway garde ou non le CMD hérité (« gateway run »), les arguments en trop
    deviennent $0 et $1 du shell et sont ignorés. Le conteneur tient, docker exec donne un shell
    root, et `diagnostiquer` lit /proc/1/environ depuis une session SANS environnement (R2-7)."""
    nom = ressources.nom("maintenance")
    ressources.conteneurs.append(nom)
    volume = ressources.volume(image, {".env": "HERMES_MANAGED_DIR=/opt/data/faux\n",
                                       "config.yaml": "mcp_servers:\n  x:\n    command: /opt/data/x\n"})
    env = dict(ENV_VALIDE, RAILWAY_ENVIRONMENT_ID="env-contrat", RAILWAY_VOLUME_MOUNT_PATH="/opt/data")
    supplement = ["gateway", "run"] if cmd_herite else []
    docker("run", "-d", "--name", nom, "-v", f"{volume}:/opt/data", *SANS_CONTEXT7, *options_env(env), "--entrypoint",
           "/bin/sh", image, "-c", "exec sleep infinity", *supplement)
    time.sleep(20)
    etat = docker("inspect", "-f", "{{.State.Running}} {{.RestartCount}}", nom, verifier=True).stdout.strip()
    conteneur = Conteneur(nom)
    pid1 = conteneur.executer(["cat", "/proc/1/cmdline"], verifier=True).stdout.replace("\x00", " ").strip()
    qui = conteneur.executer(["id", "-u"], verifier=True).stdout.strip()
    diagnostic = conteneur.executer(["env", "-i", "/opt/hermes/.venv/bin/python", "-I", "-B",
                                     "/opt/acp/bin/acp_demarrage.py", "diagnostiquer"])
    afficher(f"maintenance (CMD hérité {'gardé' if cmd_herite else 'retiré'}) : {etat} ; PID 1 : {pid1} ; uid {qui}",
             f"diagnostiquer (code {diagnostic.returncode}) :\n{diagnostic.stdout}{diagnostic.stderr}")
    assert etat.startswith("true")
    assert pid1 == "sleep infinity"
    assert qui == "0"
    assert diagnostic.returncode == 1
    sortie = diagnostic.stdout
    assert "source de l'environnement de référence : /proc/1/environ (PID 1 hors de s6 : sleep infinity)" in sortie
    assert "[acp] DIAGNOSTIC : /opt/data/.env définit la variable interdite HERMES_MANAGED_DIR" in sortie
    assert "mcp_servers.x.command = « /opt/data/x »" in sortie
    # Aucun faux refus lié à la session vide (env -i) : l'environnement Railway valide est relu.
    assert "est obligatoire et absente" not in sortie and "PATH" not in sortie
    assert "managed scope installée : construction (valeurs de déploiement vides)." in sortie
    # Nettoyage du volume puis nouveau diagnostic : sain, code 0.
    conteneur.sh("rm -f /opt/data/.env /opt/data/config.yaml", verifier=True)
    sain = conteneur.executer(["env", "-i", "/opt/hermes/.venv/bin/python", "-I", "-B",
                               "/opt/acp/bin/acp_demarrage.py", "diagnostiquer"])
    assert sain.returncode == 0, sain.stdout + sain.stderr
    assert "aucun constat ; code 0." in sain.stdout
