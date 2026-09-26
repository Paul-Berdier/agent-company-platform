"""Contrat du catalogue d'ACP (étape P3) sur le conteneur complet démarré par s6, avec une session
OIDC réelle émise par le faux fournisseur d'identité de l'image de test :

- GET /api/skills du VRAI tableau de bord liste exactement les skills livrées visibles et celles du
  catalogue, drapeaux « enabled » conformes au verrou ;
- 05-acp a écrit skills.external_dirs et skills.disabled dans /opt/data/config.yaml (et rien
  d'autre) ; un basculement depuis le tableau de bord ne les retire pas ; un écart est signalé par
  /v1/meta et /v1/catalogue puis corrigé au démarrage suivant ;
- la discussion du tableau de bord (/api/ws, surface cli) appelle context7 — ici un faux serveur en
  TLS, dans son propre conteneur, joint sous le nom épinglé mcp.context7.com — derrière le pont des
  outils différés ; échantillonnage et élicitation refusés ; aucun processus lancé ;
- un serveur MCP stdio ou hors catalogue dans le volume refuse le démarrage (décision D8), et la
  relance du tableau de bord aussi.
"""

from __future__ import annotations

import json
import time

import pytest

from conftest import ENV_VALIDE, RACINE_HERMES, afficher, attendre_modele_factice, demarrer_jusqu_a_l_arret, docker, lancer

VERROU = json.loads((RACINE_HERMES / "catalogue" / "catalogue.lock.json").read_text(encoding="utf-8"))
NOMS_ACP = sorted(s["nom"] for s in VERROU["skills"] if s["cible"] == "hermes")
DESACTIVEES = sorted(e["nom"] for e in VERROU["livrees"]["desactivees_par_acp"])
MACOS = set(VERROU["livrees"]["macos_seulement"])
# Frontmatter « environments: [kanban] » : offerte seulement dans un worker kanban
# (agent/skill_utils.py:201-208), y compris par GET /api/skills.
CACHEES_HORS_KANBAN = {"sdlc-review"}

MODELE = """\
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""


@pytest.fixture(scope="module")
def pile(ressources, image_tests):
    """Faux fournisseur d'identité, faux context7 (alias réseau mcp.context7.com) et Hermes (image de
    test, avec son modèle factice) sur un réseau privé jetable."""
    reseau = ressources.reseau()
    idp = ressources.nom("idp")
    ressources.conteneurs.append(idp)
    docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
           "--entrypoint", "/opt/hermes/.venv/bin/python", image_tests,
           "/opt/acp-tests/outils/idp_factice.py", "--emetteur", "https://idp.acp.test:8443",
           "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem", "--cle", "/opt/acp-tests/ac/idp.key")
    context7 = ressources.nom("context7")
    ressources.conteneurs.append(context7)
    docker("run", "-d", "--name", context7, "--network", reseau, "--network-alias", "mcp.context7.com",
           "--entrypoint", "/opt/hermes/.venv/bin/python", image_tests, "/opt/acp-tests/outils/mcp_factice.py",
           "--hote", "0.0.0.0", "--port", "443", "--certificat", "/opt/acp-tests/ac/mcp.pem",
           "--cle", "/opt/acp-tests/ac/mcp.key", "--journal", "/tmp/mcp-factice.jsonl")
    volume = ressources.volume(image_tests, {"config.yaml": MODELE})
    # hotes=[] : mcp.context7.com est résolu par le DNS du réseau, vers le faux serveur.
    hermes = lancer(ressources, image_tests, ENV_VALIDE, volume=volume, reseau=reseau, hotes=[])
    docker("exec", "-d", "-u", "hermes", hermes.nom, "/opt/hermes/.venv/bin/python",
           "/opt/acp-tests/outils/modele_factice.py", "--port", "18080", "--journal", "/tmp/modele-factice.jsonl")
    attendre_modele_factice(hermes, "/tmp/modele-factice.jsonl")
    hermes.context7 = context7
    return hermes


def jeton(hermes) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"],
                             verifier=True).stdout
    return json.loads(sortie)["id_token"]


def journal_context7(pile) -> list:
    brut = docker("exec", pile.context7, "cat", "/tmp/mcp-factice.jsonl", verifier=False).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def config_du_volume(pile) -> dict:
    code = "import json, yaml; print(json.dumps(yaml.safe_load(open('/opt/data/config.yaml', encoding='utf-8'))))"
    return json.loads(pile.python(code, verifier=True).stdout)


def test_05_acp_a_ecrit_les_reglages_de_skills(pile):
    config = config_du_volume(pile)
    etat = json.loads(pile.executer(["cat", "/run/acp/etat-demarrage.json"], verifier=True).stdout)
    afficher("skills du config.yaml du volume et état du démarrage",
             json.dumps({"skills": config.get("skills"), "catalogue": etat.get("catalogue")}, ensure_ascii=False,
                        indent=1))
    assert config["skills"]["external_dirs"] == ["/opt/acp/skills"]
    assert config["skills"]["disabled"] == DESACTIVEES
    # Entrée vide : le tableau de bord ne lance sa découverte MCP que si la config brute du volume
    # déclare un serveur ; la managed scope en fournit tout le contenu.
    assert config["mcp_servers"] == {"context7": {}}
    # Le reste vient du volume (modèle factice) et de la graine de l'image : rien d'autre n'est imposé.
    assert config["model"]["base_url"] == "http://127.0.0.1:18080/v1"
    assert etat["schema"] == 3 and etat["catalogue"]["reglages_skills"]["etat"] in ("applique", "cree")
    assert etat["catalogue"]["serveurs_mcp_admis"] == ["context7"]
    proprietaire = pile.sh("stat -c '%U:%G %a' /opt/data/config.yaml", verifier=True).stdout.strip()
    assert proprietaire == "hermes:hermes 640"


def test_get_api_skills_liste_exactement_le_catalogue(pile):
    code, skills = pile.json("/api/skills", jeton=jeton(pile))
    assert code == 200
    vu = {s["name"]: s["enabled"] for s in skills}
    afficher("GET /api/skills (tableau de bord réel, session OIDC)",
             f"{len(vu)} skills, {sum(vu.values())} activées, {len(vu) - sum(vu.values())} désactivées\n"
             + json.dumps(dict(sorted(vu.items())), ensure_ascii=False))
    attendues = (set(VERROU["livrees"]["noms"]) - MACOS - CACHEES_HORS_KANBAN) | set(NOMS_ACP)
    assert set(vu) == attendues
    assert {n for n, actif in vu.items() if not actif} == set(DESACTIVEES) - CACHEES_HORS_KANBAN
    assert all(vu[n] for n in NOMS_ACP)


def test_la_route_catalogue_exige_une_session_et_decrit_le_catalogue(pile):
    code, _ = pile.json("/api/plugins/acp-poste/v1/catalogue")
    assert code == 401
    code, catalogue = pile.json("/api/plugins/acp-poste/v1/catalogue", jeton=jeton(pile))
    afficher("GET /api/plugins/acp-poste/v1/catalogue", json.dumps(
        {k: v for k, v in catalogue.items() if k not in ("profils", "exclus", "livrees", "sources")},
        ensure_ascii=False, indent=1)[:6000])
    assert code == 200
    assert {s["nom"]: s["etat"] for s in catalogue["skills"] if s["cible"] == "hermes"} == {n: "active" for n in NOMS_ACP}
    assert catalogue["external_dirs_conforme"] is True and catalogue["desactivations_conformes"] is True
    assert catalogue["collisions"] == [] and catalogue["alertes"] == []
    code, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile))
    assert meta["catalogue"]["skills_actives"] == meta["catalogue"]["skills_attendues"] == len(NOMS_ACP)
    assert meta["interface"] == {"greffons": {"acp-interface": "0.11.0", "acp-catalogue": "0.11.0"}, "sdk_attendu": "1.x"}


def test_discussion_du_tableau_de_bord_appelle_context7(pile):
    """Tour complet par /api/ws (surface cli du tableau de bord) : le modèle factice appelle
    query_docs par le pont des outils différés ; le faux context7, dans un AUTRE conteneur, répond ;
    échantillonnage et élicitation refusés ; aucun processus lancé dans le conteneur de Hermes."""
    avant = set(pile.sh("ps -eo pid=", verifier=True).stdout.split())
    sortie = pile.executer(["/opt/hermes/.venv/bin/python", "/opt/acp-tests/outils/client_ws.py", "prompt",
                            jeton(pile), "/tmp/acp-ws-context7.json", "OUTIL:tool_call>mcp__context7__query_docs"],
                           delai=400)
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    resultat = json.loads(pile.executer(["cat", "/tmp/acp-ws-context7.json"], verifier=True).stdout)
    requetes = [json.loads(l) for l in pile.executer(["cat", "/tmp/modele-factice.jsonl"], verifier=True).stdout.splitlines()
                if l.strip()]
    resultats = [r["contenu"] for q in requetes for r in q.get("resultats_outils") or []]
    serveur = journal_context7(pile)
    apres = pile.sh("ps -eo pid=,args=", verifier=True).stdout
    afficher("discussion /api/ws → context7", json.dumps({"fin": resultat.get("fin"), "resultats": resultats,
                                                          "serveur": serveur}, ensure_ascii=False, indent=1)[:6000])
    assert any("Documentation factice ACP" in r for r in resultats), resultats
    assert not any("Refusé par ACP" in r for r in resultats)
    assert [e["outil"] for e in serveur if e.get("evenement") == "appel"] == ["query-docs"]
    [echantillon] = [e for e in serveur if e.get("evenement") == "echantillonnage"]
    [elicitation] = [e for e in serveur if e.get("evenement") == "elicitation"]
    assert echantillon["issue"] == "refuse" and elicitation["issue"] == "refusee"
    nouveaux = [l for l in apres.splitlines() if l.split(None, 1)[0] not in avant]
    assert not any(motif in l for l in nouveaux for motif in ("npx", "uvx", "node ", "mcp")), nouveaux
    # Le tableau de bord a découvert context7 : la route le dit connecté.
    _, catalogue = pile.json("/api/plugins/acp-poste/v1/catalogue", jeton=jeton(pile))
    [c7] = [m for m in catalogue["mcp"] if m["nom"] == "context7"]
    assert c7["connexion"] == "connecte" and c7["outils_exposes"] == 2


def test_un_basculement_depuis_le_tableau_de_bord_garde_les_reglages(pile):
    """PUT /api/skills/toggle réécrit config.yaml (save_config) : skills.external_dirs reste (il n'est
    pas dans la managed scope, qui l'aurait retiré). Réactiver « codex » est un écart signalé, corrigé
    au démarrage suivant."""
    cle = jeton(pile)
    code, _ = pile.json("/api/skills/toggle", jeton=cle, methode="PUT", corps='{"name": "arxiv", "enabled": false}')
    assert code == 200
    config = config_du_volume(pile)
    assert config["skills"]["external_dirs"] == ["/opt/acp/skills"] and "arxiv" in config["skills"]["disabled"]
    code, _ = pile.json("/api/skills/toggle", jeton=cle, methode="PUT", corps='{"name": "codex", "enabled": true}')
    assert code == 200
    _, catalogue = pile.json("/api/plugins/acp-poste/v1/catalogue", jeton=cle)
    _, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=cle)
    afficher("après basculement de codex", json.dumps({"ecarts": catalogue["desactivations_non_appliquees"],
                                                       "alertes": meta["alertes"]}, ensure_ascii=False, indent=1))
    assert catalogue["desactivations_non_appliquees"] == ["codex"]
    assert any("codex" in a for a in meta["alertes"])
    assert all(s["etat"] == "active" for s in catalogue["skills"] if s["cible"] == "hermes")
    docker("restart", pile.nom, delai=240)
    pile.attendre_pret()
    config = config_du_volume(pile)
    assert "codex" in config["skills"]["disabled"] and "arxiv" in config["skills"]["disabled"]
    _, catalogue = pile.json("/api/plugins/acp-poste/v1/catalogue", jeton=jeton(pile))
    assert catalogue["desactivations_non_appliquees"] == []


def test_external_dirs_retire_puis_retabli_au_demarrage(pile):
    code = ("import yaml; p = '/opt/data/config.yaml'; d = yaml.safe_load(open(p, encoding='utf-8')); "
            "d['skills'].pop('external_dirs'); open(p, 'w', encoding='utf-8').write(yaml.safe_dump(d))")
    pile.executer(["/opt/hermes/.venv/bin/python", "-c", code], utilisateur="hermes", verifier=True)
    _, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile))
    afficher("external_dirs retiré", json.dumps({"catalogue": meta["catalogue"], "alertes": meta["alertes"]},
                                                ensure_ascii=False, indent=1))
    assert meta["catalogue"]["external_dirs_conforme"] is False and meta["catalogue"]["skills_actives"] == 0
    assert any("skills.external_dirs ne contient pas /opt/acp/skills" in a for a in meta["alertes"])
    docker("restart", pile.nom, delai=240)
    pile.attendre_pret()
    assert config_du_volume(pile)["skills"]["external_dirs"] == ["/opt/acp/skills"]
    _, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile))
    assert meta["catalogue"]["external_dirs_conforme"] is True
    assert meta["catalogue"]["skills_actives"] == len(NOMS_ACP)


def test_deux_demarrages_successifs_n_ecrivent_rien(pile):
    """Volume déjà conforme : un redémarrage ne réécrit pas config.yaml (même empreinte, même date)
    et l'état du démarrage dit « conforme »."""
    empreinte = "sha256sum /opt/data/config.yaml && stat -c '%Y %U:%G %a' /opt/data/config.yaml"
    avant = pile.sh(empreinte, verifier=True).stdout
    docker("restart", pile.nom, delai=240)
    pile.attendre_pret()
    apres = pile.sh(empreinte, verifier=True).stdout
    etat = json.loads(pile.executer(["cat", "/run/acp/etat-demarrage.json"], verifier=True).stdout)
    afficher("config.yaml avant et après redémarrage", f"{avant}\n{apres}\n{etat['catalogue']['reglages_skills']}")
    assert avant == apres
    assert etat["catalogue"]["reglages_skills"]["etat"] == "conforme"


def test_d8_relance_du_tableau_de_bord_refusee_sur_un_serveur_stdio(pile):
    """Le propriétaire (ou une ancienne injection) ajoute un serveur stdio dans le volume, puis le
    tableau de bord est relancé : la garde de relance refuse (tableau de bord hors service, visible),
    et aucun témoin n'est créé. Retiré, le tableau de bord repart."""
    code = ("import yaml; p = '/opt/data/config.yaml'; d = yaml.safe_load(open(p, encoding='utf-8')); "
            "d['mcp_servers'] = {'outil': {'command': '/bin/sh', 'args': ['-c', 'touch /tmp/acp-temoin-mcp']}}; "
            "open(p, 'w', encoding='utf-8').write(yaml.safe_dump(d))")
    pile.executer(["/opt/hermes/.venv/bin/python", "-c", code], utilisateur="hermes", verifier=True)
    relance = pile.executer(["/command/s6-svc", "-r", "/run/service/dashboard"], utilisateur="hermes")
    assert relance.returncode == 0, relance.stderr
    time.sleep(12)
    statut = pile.executer(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "http://127.0.0.1:9119/api/status"]).stdout.strip()
    journal = pile.journaux()
    afficher("relance du tableau de bord avec un serveur MCP stdio dans le volume",
             f"statut : {statut}\n" + "\n".join(l for l in journal.splitlines() if "[acp]" in l)[-3000:])
    assert statut != "200"
    assert "avec un « command »" in journal
    assert pile.sh("test -e /tmp/acp-temoin-mcp").returncode != 0
    retrait = ("import yaml; p = '/opt/data/config.yaml'; d = yaml.safe_load(open(p, encoding='utf-8')); "
               "d.pop('mcp_servers'); open(p, 'w', encoding='utf-8').write(yaml.safe_dump(d))")
    pile.executer(["/opt/hermes/.venv/bin/python", "-c", retrait], utilisateur="hermes", verifier=True)
    pile.attendre_pret()


@pytest.mark.parametrize("config, motif", [
    ("mcp_servers:\n  outil:\n    command: /bin/sh\n", "avec un « command »"),
    ("mcp_servers:\n  deepwiki:\n    url: https://mcp.deepwiki.com/mcp\n", "absent du catalogue"),
])
def test_d8_demarrage_refuse(ressources, image, config, motif):
    volume = ressources.volume(image, {"config.yaml": config})
    code, journal = demarrer_jusqu_a_l_arret(ressources, image, ENV_VALIDE, volume=volume)
    afficher(f"démarrage avec {config.splitlines()[1].strip()} : code {code}",
             "\n".join(l for l in journal.splitlines() if "[acp]" in l))
    assert code == 1
    assert motif in journal and "[acp] REFUS : " in journal
    assert "Retirez ces serveurs de mcp_servers" in journal
