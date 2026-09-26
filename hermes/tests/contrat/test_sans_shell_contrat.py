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
    # Schéma 2 en P2 ; 3 depuis P3 (bloc catalogue ajouté, rien de retiré).
    assert etat["deploiement"] == {"commit": SHA} and etat["schema"] == 3
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
