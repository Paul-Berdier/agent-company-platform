"""Contrat du bilan quotidien (étape P7, cahier P7 § 7, § 13.2 ; corrections K1, K3, K15, K22), piloté depuis l'hôte
(voir conftest.py), sur la pile complète : vraie porte d'authentification, cron natif de Hermes, passerelle et émetteur.

Pile : faux fournisseur d'identité (session du propriétaire), faux ntfy en HTTPS, volume jetable.

Ce qui est prouvé ici, sur l'image réellement construite :
- au démarrage, root dépose ``/opt/data/scripts/acp-bilan.py`` (root, 0644, copie de l'image) et le dit ;
- la tâche est créée par la route NATIVE ``POST /api/cron/jobs`` avec la session du propriétaire (``no_agent``,
  ``deliver: local``) : la page Cron de Hermes accepte le script de ce dossier de root (le S du cahier § 17) ; sa
  prochaine exécution tombe à 08:00 HEURE DE PARIS (épingle ``timezone`` de la managed scope : K15) ;
- ``POST /api/cron/jobs/{id}/trigger`` lance le script SANS modèle : le noyau s'importe dans ce sous-processus à
  l'environnement assaini (le S de K22) ; UNE ligne ``bilan:<jour>`` en file, lien relatif ``/`` ; le faux ntfy la
  reçoit avec ``Click`` = URL publique + ``/`` (préfixée à l'envoi : K3) ; une seconde exécution le même jour n'en
  enfile pas d'autre ;
- ``diagnostiquer`` n'en fait pas un constat (seule tâche à script admise) ;
- SECOND DÉMARRAGE sur le même volume (ce que fait un redéploiement Railway) : les gardes admettent le script par son
  empreinte (K1 : sans l'élargissement, tout redémarrage après le dépôt aurait été refusé) ; la tâche survit.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from conftest import ENV_VALIDE, Conteneur, afficher, docker, lancer

PYTHON = "/opt/hermes/.venv/bin/python"
JOURNAL_NTFY = "/tmp/ntfy-bilan.jsonl"
SUJET = "acp_sujet_de_test_bilan"
JETON_NTFY = "jeton-de-test-acp-bilan"
ENV_BILAN = dict(ENV_VALIDE, ACP_NOTIFICATIONS="ntfy", ACP_NTFY_SERVEUR="https://ntfy.acp.test", ACP_NTFY_SUJET=SUJET,
                 ACP_NTFY_JETON=JETON_NTFY)
MODELE = "kanban:\n  dispatch_interval_seconds: 5\n"
TACHE = {"name": "Bilan ACP", "schedule": "0 8 * * *", "prompt": "", "no_agent": True, "script": "acp-bilan.py",
         "deliver": "local"}


@pytest.fixture(scope="module")
def pile(ressources, image_tests):
    reseau = ressources.reseau()
    idp = ressources.nom("idp")
    ressources.conteneurs.append(idp)
    docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
           "--entrypoint", PYTHON, image_tests, "/opt/acp-tests/outils/idp_factice.py", "--emetteur",
           "https://idp.acp.test:8443", "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem",
           "--cle", "/opt/acp-tests/ac/idp.key")
    ntfy = ressources.nom("ntfy")
    ressources.conteneurs.append(ntfy)
    docker("run", "-d", "--name", ntfy, "--network", reseau, "--network-alias", "ntfy.acp.test",
           "--entrypoint", PYTHON, image_tests, "/opt/acp-tests/outils/notif_factice.py", "--port", "443",
           "--certificat", "/opt/acp-tests/ac/ntfy.pem", "--cle", "/opt/acp-tests/ac/ntfy.key",
           "--journal", JOURNAL_NTFY)
    volume = ressources.volume(image_tests, {"config.yaml": MODELE})
    hermes = lancer(ressources, image_tests, ENV_BILAN, volume=volume, reseau=reseau)
    sortie = hermes.executer([PYTHON, "/opt/acp-tests/outils/poste_simule.py", "reglage", "emetteur_intervalle_s", "5"],
                             utilisateur="hermes", delai=120)
    assert sortie.returncode == 0, sortie.stderr[-2000:]
    etat = {"hermes": hermes, "ntfy": ntfy, "volume": volume, "reseau": reseau}
    return etat


def jeton(hermes: Conteneur) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"], verifier=True).stdout
    return json.loads(sortie)["id_token"]


def api(hermes: Conteneur, methode: str, chemin: str, corps: Optional[Any] = None):
    """(code, JSON) d'une route du tableau de bord (native ou du greffon) avec la session du propriétaire."""
    commande = ["curl", "-s", "-o", "/tmp/acp-reponse-bilan", "-w", "%{http_code}", "-X", methode,
                f"http://127.0.0.1:9119{chemin}", "-H", f"Authorization: Bearer {jeton(hermes)}"]
    if corps is not None:
        commande += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(corps, ensure_ascii=False)]
    code = int(hermes.executer(commande, verifier=True, delai=240).stdout.strip())
    contenu = hermes.executer(["cat", "/tmp/acp-reponse-bilan"], verifier=True).stdout
    try:
        return code, json.loads(contenu)
    except ValueError:
        return code, contenu


def bilans(hermes: Conteneur) -> List[Dict[str, Any]]:
    code = ("import json, sqlite3\n"
            "c = sqlite3.connect('file:/opt/data/plugin-data/acp-poste/data.db?mode=ro', uri=True)\n"
            "c.row_factory = sqlite3.Row\n"
            "print(json.dumps([dict(l) for l in c.execute(\"SELECT cle, genre, texte, lien, etat FROM notifications "
            "WHERE genre = 'bilan' ORDER BY id\")], ensure_ascii=False))\n")
    return json.loads(hermes.executer([PYTHON, "-c", code], utilisateur="hermes", verifier=True).stdout)


def recues(ntfy: str) -> List[Dict[str, Any]]:
    brut = docker("exec", ntfy, "sh", "-c", f"cat {JOURNAL_NTFY} 2>/dev/null", verifier=False).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def attendre(predicat, delai: float, message: str, pas: float = 1.0):
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


def a_paris(hermes: Conteneur, instant: Optional[str] = None) -> Dict[str, str]:
    """Heure de Paris d'un instant ISO (ou de maintenant), calculée DANS le conteneur (base des fuseaux de l'image ;
    l'hôte Windows n'en a pas forcément) : ``{jour, jj_mm, heure}``."""
    code = ("import json, sys\n"
            "from datetime import datetime, timezone\n"
            "from zoneinfo import ZoneInfo\n"
            "brut = sys.argv[1]\n"
            "t = datetime.fromisoformat(brut) if brut else datetime.now(timezone.utc)\n"
            "p = t.astimezone(ZoneInfo('Europe/Paris'))\n"
            "print(json.dumps({'jour': p.strftime('%Y-%m-%d'), 'jj_mm': p.strftime('%d/%m'), "
            "'heure': p.strftime('%H:%M')}))\n")
    return json.loads(hermes.executer([PYTHON, "-c", code, instant or ""], verifier=True).stdout)


def _taches(hermes: Conteneur) -> List[Dict[str, Any]]:
    code, liste = api(hermes, "GET", "/api/cron/jobs")
    assert code == 200, liste
    return liste if isinstance(liste, list) else liste.get("jobs", [])


def test_script_depose_par_root_au_demarrage(pile):
    hermes = pile["hermes"]
    etat = hermes.sh("stat -c '%U:%G %a %F' /opt/data/scripts/acp-bilan.py && ls -A /opt/data/scripts && "
                     "cmp /opt/data/scripts/acp-bilan.py /opt/acp/scripts/acp-bilan.py && echo identique",
                     verifier=True).stdout
    afficher("script du bilan au premier démarrage", etat)
    assert etat.splitlines() == ["root:root 644 regular file", "acp-bilan.py", "identique"]
    journal = hermes.journaux()
    assert "[acp] script du bilan quotidien déposé : /opt/data/scripts/acp-bilan.py (root 0644" in journal
    assert hermes.sh("echo x >> /opt/data/scripts/acp-bilan.py", utilisateur="hermes").returncode != 0
    demarrage = json.loads(hermes.sh("cat /run/acp/etat-demarrage.json", verifier=True).stdout)
    empreinte = hermes.sh("sha256sum /opt/acp/scripts/acp-bilan.py", verifier=True).stdout.split()[0]
    assert demarrage["schema"] == 4 and demarrage["bilan_depose"] == empreinte


def test_tache_creee_par_le_proprietaire_a_8_h_de_paris(pile):
    hermes = pile["hermes"]
    code, tache = api(hermes, "POST", "/api/cron/jobs", TACHE)
    afficher("POST /api/cron/jobs (session du propriétaire)", json.dumps(tache, ensure_ascii=False, indent=1)[:3000])
    assert code == 200, tache
    assert (tache["script"], tache["no_agent"], tache["name"]) == ("acp-bilan.py", True, "Bilan ACP")
    prochaine = datetime.fromisoformat(tache["next_run_at"])
    assert prochaine.tzinfo is not None
    assert a_paris(hermes, tache["next_run_at"])["heure"] == "08:00", tache["next_run_at"]
    maintenant = datetime.now(timezone.utc)
    assert maintenant < prochaine <= maintenant + timedelta(days=1, minutes=1)
    pile["tache"] = tache["id"]
    assert [t["id"] for t in _taches(hermes)] == [tache["id"]]


def test_execution_sans_modele_une_ligne_et_livraison(pile):
    hermes, ntfy = pile["hermes"], pile["ntfy"]
    avant = len(recues(ntfy))
    code, apres = api(hermes, "POST", f"/api/cron/jobs/{pile['tache']}/trigger")
    afficher("trigger de la tâche du bilan", json.dumps(apres, ensure_ascii=False, indent=1)[:3000])
    assert code == 200, apres
    [ligne] = attendre(lambda: bilans(hermes), 30, "aucune ligne « bilan » en file")
    paris = a_paris(hermes)
    assert (ligne["cle"], ligne["lien"]) == (f"bilan:{paris['jour']}", "/")
    assert ligne["texte"].startswith(f"ACP — Bilan du {paris['jj_mm']} : ")
    assert len(ligne["texte"]) <= 300
    nouvelles = attendre(lambda: [n for n in recues(ntfy)[avant:] if n["corps"].startswith("ACP — Bilan du ")], 60,
                         "le faux ntfy n'a pas reçu le bilan")
    afficher("bilan reçu par le faux ntfy", json.dumps(nouvelles, ensure_ascii=False, indent=1))
    assert [n["corps"] for n in nouvelles] == [ligne["texte"]]
    assert nouvelles[0]["click"] == "https://hermes.acp.test/" and nouvelles[0]["autorisation_presente"]
    # Seconde exécution le même jour : rien de plus en file.
    code, _ = api(hermes, "POST", f"/api/cron/jobs/{pile['tache']}/trigger")
    assert code == 200
    time.sleep(8)
    assert len(bilans(hermes)) == 1
    assert len([n for n in recues(ntfy)[avant:] if n["corps"].startswith("ACP — Bilan du ")]) == 1


def test_diagnostiquer_admet_la_seule_tache_du_bilan(pile):
    hermes = pile["hermes"]
    resultat = hermes.executer(["env", "-i", PYTHON, "-I", "-B", "/opt/acp/bin/acp_demarrage.py", "diagnostiquer"])
    afficher(f"diagnostiquer avec la tâche du bilan : code {resultat.returncode}", resultat.stdout + resultat.stderr)
    constats = [l for l in resultat.stdout.splitlines() if l.startswith("[acp] DIAGNOSTIC : ")]
    assert not any("tâche cron" in l or "/scripts n'est pas vide" in l or "acp-bilan" in l for l in constats), constats
    # Relecture finale de P7 (constat tests-5) : un diagnostic qui échouerait AVANT d'avoir lu les tâches (exception,
    # refus de _exiger_root, interpréteur absent) n'écrirait aucune ligne DIAGNOSTIC et passait ce test à vide.
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert "[acp] diagnostic : aucun constat ; code 0." in resultat.stdout.splitlines(), resultat.stdout


def test_second_demarrage_sur_le_meme_volume(pile, ressources, image_tests):
    """K1 : le volume porte le script déposé au premier démarrage ; le second démarrage (redéploiement) passe les
    gardes, qui l'admettent par son empreinte ; la tâche du propriétaire survit."""
    ancien = pile["hermes"]
    docker("rm", "-f", ancien.nom, delai=180)
    nouveau = lancer(ressources, image_tests, ENV_BILAN, volume=pile["volume"], reseau=pile["reseau"])
    pile["hermes"] = nouveau
    journal = nouveau.journaux()
    lignes = [l for l in journal.splitlines() if "[acp]" in l and ("scripts" in l or "bilan" in l)]
    afficher("second démarrage sur le même volume", "\n".join(lignes))
    assert "/opt/data/hooks et /opt/data/scripts inspectés : vides (hors acp-bilan.py, admis par son empreinte)" in journal
    assert "[acp] REFUS" not in journal
    assert [t["id"] for t in _taches(nouveau)] == [pile["tache"]]
    assert len(bilans(nouveau)) == 1  # aucune ligne de plus au redémarrage
