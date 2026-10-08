"""R4 — Hermes restauré depuis SON PROPRE EXPORT (étape P9, cahier P9 § 3.6), piloté depuis l'hôte.

Chemin de secours quand le volume de Hermes ET ses sauvegardes sont perdus (« Wiping a volume deletes all backups »,
docs Railway). Banc partagé (banc.py) : Hermes de test et vrai exécutant en cible « factice ».

1. banc peuplé (projets A terminé et B en question, routage validé, discussion, bilan quotidien) ; pause générale ;
2. export EXACTEMENT comme la station Qt (apps/desktop/src/viewmodels/SauvegardeViewModel.h) : ``POST /api/ops/backup
   {}`` → ``GET /api/actions/backup/status`` jusqu'à la fin → ``GET /api/ops/backup/download?archive=…`` →
   ``DELETE /api/files`` ; référence API prise à la fin de l'action ;
3. inventaire de l'archive face au manifeste du volume : chaque fichier absent de l'archive est classé par le
   prédicat de Hermes lui-même (``hermes_cli.backup._should_exclude``) en exclusion ATTENDUE ou omission INATTENDUE ;
   le test échoue sur toute omission inattendue ;
4. volume NEUF, VIDE et À ROOT, comme celui que Railway monterait (monté en ``volume-nocopy`` : sinon Docker le garnit
   depuis l'image, à l'UID 10000) ; import sous la forme EXACTE du geste du propriétaire dans une session de
   maintenance (root, sans s6) : ``hermes import --force <archive>`` lancé par root ; l'enveloppe ``hermes`` de l'image
   redescend alors à l'UID hermes. Chaque forme (le geste exact, puis la variante ``chown 10000:10000 /opt/data``) est
   MESURÉE sur son propre volume neuf ; une forme n'est retenue que si l'import est COMPLET d'après la sortie de
   ``hermes import`` (aucun fichier ignoré, tous les fichiers de l'archive restaurés) : son code de sortie seul ne
   prouve rien (premier run 37760142007 : code 0 et « Import complete: 0 files restored ») ;
5. démarrage normal de l'image sur ce volume : les gardes acceptent ou refusent (un refus est un CONSTAT, jamais
   contourné) ; si le seul refus porte sur le script du bilan (importé sous l'UID de l'import, pas root), le geste que
   la garde prescrit elle-même (supprimer le fichier, root le redépose) est appliqué en maintenance, puis le démarrage
   est mesuré à nouveau ;
6. couche 2 : empreintes logiques des bases de l'archive et du volume importé égales ; couche 3 : lectures égales à la
   référence, dont les cartes des projets RELUES PAR L'API (``GET /v1/projets/{id}`` : chaque carte, son rôle et sa
   voie ; rôle, voie et statut de la carte d'exploration) ;
7. l'exécutant, dont le volume n'a pas bougé, continue avec ce Hermes (jeton machine de la base importée) : projet E
   → terminé.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import urllib.parse
from typing import Any, Dict, List

import pytest

from banc import JETON_CLAUDE, PYTHON, Banc, attendre
from conftest import afficher, docker
from volumes import Archives, bases, comparer_bases, manifeste, resume_bases, resume_manifeste

pytestmark = pytest.mark.restauration

SCRIPT_BILAN = "acp-bilan.py"
TACHE_BILAN = {"name": "Bilan ACP", "schedule": "0 8 * * *", "prompt": "", "no_agent": True,
               "script": SCRIPT_BILAN, "deliver": "local"}
OUTIL = "/opt/acp-tests/outils/empreinte_volume.py"
INVENTAIRE = r"""
import json, sys, zipfile
from pathlib import Path
from hermes_cli.backup import _detect_prefix, _should_exclude
entrees = json.load(sys.stdin)
with zipfile.ZipFile('/a/export.zip') as zf:
    prefixe = _detect_prefix(zf) or ''
    noms = {n[len(prefixe):] for n in zf.namelist() if not n.endswith('/')}
attendues, inattendues = [], []
for chemin, e in sorted(entrees.items()):
    if chemin == '.' or e['type'] not in ('f', 'l') or chemin in noms:
        continue
    (attendues if _should_exclude(Path(chemin)) else inattendues).append(chemin)
print(json.dumps({'prefixe': prefixe, 'dans_l_archive': len(noms), 'attendues': attendues,
                  'inattendues': inattendues, 'en_trop': sorted(n for n in noms if n not in entrees)}))
"""
EXTRAIRE_ET_EMPREINDRE = (
    "set -eu; mkdir -p /tmp/x; /opt/hermes/.venv/bin/python -c \"import zipfile; "
    "zipfile.ZipFile('/a/export.zip').extractall('/tmp/x')\"; "
    f"/opt/hermes/.venv/bin/python {OUTIL} sqlite /tmp/x")


def _json(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False, indent=1, default=str)


def _lignes(texte: str) -> List[str]:
    """Sortie d'une commande, lignes non vides, 60 dernières au plus (aucun secret : hermes import n'en imprime pas)."""
    return [l for l in texte.splitlines() if l.strip()][-60:]


class Export:
    def __init__(self, banc: Banc, archives: Archives, image: str, image_tests: str) -> None:
        self.banc, self.archives, self.image, self.image_tests = banc, archives, image, image_tests
        self.projets: Dict[str, Dict[str, Any]] = {}
        self.cartes: Dict[str, str] = {}
        self.reference: Dict[str, Any] = {}
        self.session_discussion = ""
        self.tache_bilan = ""
        self.manifeste_avant: Dict[str, Any] = {}
        self.archive: Dict[str, Any] = {}
        self.volume_importe = ""
        self.forme_import = ""
        self.ancien_hermes = ""
        self.remote_avant = ""
        self.question_b: Dict[str, Any] = {}
        self.inventaire: Dict[str, Any] = {}
        self.geste_au_demarrage: List[str] = []
        self.statuts_export: Dict[str, Dict[str, Any]] = {}

    def requete(self, methode: str, chemin: str, corps=None):
        b = self.banc
        commande = ["curl", "-s", "-o", "/tmp/acp-reponse-export", "-w", "%{http_code}", "-X", methode,
                    f"http://127.0.0.1:9119{chemin}", "-H", f"Authorization: Bearer {b.jeton_oidc()}"]
        if corps is not None:
            commande += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(corps, ensure_ascii=False)]
        code = int(b.hermes.executer(commande, verifier=True, delai=240).stdout.strip())
        contenu = b.hermes.executer(["cat", "/tmp/acp-reponse-export"], verifier=True).stdout
        try:
            return code, json.loads(contenu)
        except ValueError:
            return code, contenu

    def cartes_lues(self) -> Dict[str, Any]:
        """Cartes des projets A et B RELUES PAR L'API (``GET /v1/projets/{id}``) : identifiant, rôle et voie de
        chaque carte du projet (aucune perdue, aucune en trop), et statut de la carte d'exploration du poste. Le statut
        des cartes de Hermes lui-même (modèle factice) est seulement imprimé : son répartiteur reprend au démarrage une
        carte qu'un processus disparu tenait."""
        lues: Dict[str, Any] = {}
        for lettre in "AB":
            code, detail = self.banc.api("GET", f"/v1/projets/{self.projets[lettre]['id']}")
            cartes = (((detail or {}).get("projet") or {}).get("cartes") or []) if code == 200 else []
            lues[lettre] = {
                "code": code,
                "cartes": sorted([str(c.get("carte")), str(c.get("role")), str(c.get("voie"))]
                                 for c in cartes if c.get("carte")),
                "exploration": next(({k: c.get(k) for k in ("role", "voie", "statut")} for c in cartes
                                     if c.get("carte") == self.cartes[lettre]), "absente")}
        return lues

    def statuts_des_cartes(self) -> Dict[str, Dict[str, Any]]:
        """Statut de chaque carte des projets A et B (API), pour l'impression seulement."""
        statuts: Dict[str, Dict[str, Any]] = {}
        for lettre in "AB":
            code, detail = self.banc.api("GET", f"/v1/projets/{self.projets[lettre]['id']}")
            statuts[lettre] = {str(c.get("carte")): c.get("statut") for c in
                               (((detail or {}).get("projet") or {}).get("cartes") or [])} if code == 200 else {
                "code": code}
        return statuts

    def releve_reference(self) -> Dict[str, Any]:
        b = self.banc
        _code, projets = b.api("GET", "/v1/projets")
        _code, questions = b.api("GET", "/v1/questions")
        _code, routage = b.api("GET", "/v1/routage")
        _code, poste = b.api("GET", "/v1/poste")
        code_s, sessions = self.requete("GET", "/api/sessions?limit=100&archived=include")
        code_c, taches = self.requete("GET", "/api/cron/jobs")
        taches = taches if isinstance(taches, list) else (taches or {}).get("jobs", [])
        machine = (poste.get("machine") or {}).get("machine") or {}
        discussion = [(s["id"], s.get("message_count")) for s in (sessions or {}).get("sessions", [])
                      if s["id"] == self.session_discussion] if code_s == 200 else f"code {code_s}"
        return {
            "projets": {p["id"]: p["titre"] for p in projets["projets"]},
            "cartes": self.cartes_lues(),
            "pause_generale": projets.get("pause_generale"),
            "questions_ouvertes": sorted((q["id"], q["carte"], q["texte"]) for q in questions["questions"]),
            "machine": {k: machine.get(k) for k in ("id", "etat", "empreinte")},
            "routage_valide": {c: [(e["voie"], e["modele"], e["effort"]) for e in (v.get("entrees") or [])]
                               for c, v in (routage.get("classes") or {}).items() if v.get("etat") == "validee"},
            "session_discussion": discussion,
            "taches_cron": sorted(t["id"] for t in taches) if code_c == 200 else f"code {code_c}",
        }


def _binaire(*arguments: str, entree: bytes = b"") -> bytes:
    resultat = subprocess.run(["docker", *arguments], input=entree, capture_output=True, timeout=600)
    if resultat.returncode != 0:
        raise AssertionError(f"docker {' '.join(arguments[:3])}… : {resultat.stderr[-2000:]!r}")
    return resultat.stdout


@pytest.fixture(scope="module")
def export(ressources, image, image_tests):
    banc = Banc(ressources, image_tests)
    try:
        banc.monter()
        banc.construire_executant()
        banc.demarrer_executant()
        yield Export(banc, Archives(ressources, image_tests), image, image_tests)
    finally:
        banc.nettoyer_image()


def test_r4_peuplement_pause_et_export_comme_le_desktop(export):
    e, b = export, export.banc
    e.remote_avant = b.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
    b.mettre_en_service()
    _code, routage = b.api("GET", "/v1/routage")
    entrees = ((routage["classes"].get("exploration") or {}).get("suggestion") or {}).get("entrees") or [
        {"voie": "poste-claude", "modele": "opus", "effort": "low"}]
    code, valide = b.api("POST", "/v1/routage", {"releves": routage["releves"], "classes": {"exploration": entrees}})
    assert code == 200, valide
    e.projets["A"] = b.lancer_projet("Export — A", "simple")
    e.cartes["A"] = b.carte_exploration(e.projets["A"]["tableau"])["id"]
    b.attendre_statut(e.projets["A"]["tableau"], e.cartes["A"], "done")
    e.projets["B"] = b.lancer_projet("Export — B", "question")
    e.cartes["B"] = b.carte_exploration(e.projets["B"]["tableau"])["id"]

    def question():
        code, liste = b.api("GET", "/v1/questions")
        return next((q for q in liste["questions"] if q["carte"] == e.cartes["B"]), None) if code == 200 else None

    e.question_b = attendre(question, 240, f"question de B jamais posée ({b.fin_journal()})")
    fichier = "/tmp/acp-ws-export.json"
    sortie = b.hermes.executer([PYTHON, "/opt/acp-tests/outils/client_ws.py", "prompt", b.jeton_oidc(), fichier,
                                "Discussion d'essai avant l'export."], delai=420)
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    tour = json.loads(b.hermes.executer(["cat", fichier], verifier=True).stdout)
    # Clé STOCKÉE de la session (celle de /api/sessions), pas l'identifiant de la connexion /api/ws.
    assert tour.get("cle"), tour.get("session_id")
    e.session_discussion = tour["cle"]
    code, tache = e.requete("POST", "/api/cron/jobs", TACHE_BILAN)
    assert code == 200, tache
    e.tache_bilan = tache["id"]
    # Pause générale, puis plus aucune carte en main de l'exécutant (procédure, cahier § 4.3 point 4).
    code, pause = b.api("POST", "/v1/pause", {"generale": True, "raison": "export de restauration"})
    assert code == 200 and pause["pause_generale"], pause
    attendre(lambda: not (json.loads(docker("exec", b.executant, "sh", "-c",
                                             "cat /donnees/acp/etat/carte.json 2>/dev/null || echo '{}'").stdout or "{}")
                          .get("etape") in ("agent", "verification", "preparation_dependances")) or None,
             120, "l'exécutant tient encore une carte")
    e.manifeste_avant = manifeste(e.image_tests, b.volume_hermes)
    # 2. Export comme la station Qt.
    debut = time.monotonic()
    code, lance = e.requete("POST", "/api/ops/backup", {})
    assert code == 200 and lance.get("archive"), lance
    chemin = lance["archive"]

    def fini():
        code, etat = e.requete("GET", "/api/actions/backup/status?lines=40")
        return etat if code == 200 and etat.get("running") is False else None

    etat = attendre(fini, 600, "la sauvegarde de Hermes ne se termine pas", pas=2.0)
    assert etat.get("exit_code") == 0, etat
    e.reference = e.releve_reference()
    e.statuts_export = e.statuts_des_cartes()
    telecharge = b.hermes.executer(["curl", "-s", "-o", "/tmp/acp-export.zip", "-w", "%{http_code}",
                                    "http://127.0.0.1:9119/api/ops/backup/download?archive=" +
                                    urllib.parse.quote(chemin, safe=""),
                                    "-H", f"Authorization: Bearer {b.jeton_oidc()}"], verifier=True).stdout.strip()
    assert telecharge == "200", telecharge
    code, supprime = e.requete("DELETE", "/api/files", {"path": chemin})
    assert code == 200, supprime
    reste = b.hermes.executer(["test", "-e", chemin]).returncode
    contenu = _binaire("exec", b.hermes.nom, "cat", "/tmp/acp-export.zip")
    b.hermes.executer(["rm", "-f", "/tmp/acp-export.zip"], verifier=True)
    _binaire("run", "--rm", "-i", "--network", "none", "-v", f"{e.archives.volume}:/a", "--entrypoint", "sh",
             e.image_tests, "-c", "cat > /a/export.zip", entree=contenu)
    e.archive = {"octets": len(contenu), "sha256": hashlib.sha256(contenu).hexdigest()[:16],
                 "duree_s": round(time.monotonic() - debut, 1), "archive_restee_sur_le_volume": reste == 0}
    afficher("R4 — export comme la station Qt", _json({
        "archive": e.archive, "journal_de_la_sauvegarde": (etat.get("lines") or [])[-12:],
        "reference": e.reference, "statuts_des_cartes": e.statuts_export,
        "volume": resume_manifeste(e.manifeste_avant)}))
    assert reste != 0, "l'archive en clair est restée sur le volume de Hermes"
    assert e.reference["session_discussion"] and e.reference["taches_cron"] == [e.tache_bilan]
    # Relecture des cartes non vide : chaque projet lu (200), sa carte d'exploration présente, celle de A terminée.
    cartes = e.reference["cartes"]
    assert {x: cartes[x]["code"] for x in "AB"} == {"A": 200, "B": 200}, cartes
    assert cartes["A"]["exploration"] == {"role": "exploration", "voie": "poste-claude", "statut": "done"}, cartes
    assert cartes["B"]["exploration"] != "absente", cartes


def test_r4_inventaire_de_l_archive(export):
    e = export
    sortie = docker("run", "--rm", "-i", "--network", "none", "-v", f"{e.archives.volume}:/a:ro", "--entrypoint",
                    PYTHON, e.image_tests, "-c", INVENTAIRE, entree=json.dumps(e.manifeste_avant["entrees"]))
    inventaire = json.loads(sortie.stdout)
    e.inventaire = inventaire
    afficher("R4 — inventaire de l'archive face au volume (exclusions classées par hermes_cli.backup)", _json(
        dict(inventaire, attendues=inventaire["attendues"][:60])))
    assert inventaire["dans_l_archive"] > 0
    assert inventaire["inattendues"] == [], inventaire["inattendues"]


def _bilan_import(code: int, sortie: str, dans_l_archive: int) -> Dict[str, Any]:
    """Ce que ``hermes import`` dit avoir fait, relevé dans sa sortie. Son code de sortie et son « Import complete »
    ne suffisent PAS : le premier run (37760142007) a mesuré, pour la forme exacte du geste, le code 0, « Import
    complete: 0 files restored », « Warnings (400 files skipped) » (Permission denied) et « Done. Your Hermes
    configuration has been restored. ». Complet : aucun fichier ignoré, et restaurés + fichiers d'exécution gardés
    (ceux de la machine cible, jamais remplacés : hermes_cli/backup.py, _IMPORT_SKIP_NAMES) = fichiers de l'archive."""
    restaures = re.search(r"Import complete: (\d+) files? restored", sortie)
    ignores = re.search(r"Warnings \((\d+) files? skipped\)", sortie)
    gardes = re.search(r"Preserved (\d+) runtime state file", sortie)
    bilan: Dict[str, Any] = {"code": code, "restaures": int(restaures.group(1)) if restaures else None,
                             "ignores": int(ignores.group(1)) if ignores else 0,
                             "etat_d_execution_garde": int(gardes.group(1)) if gardes else 0,
                             "dans_l_archive": dans_l_archive}
    bilan["complet"] = (code == 0 and bool(bilan["restaures"]) and bilan["ignores"] == 0
                        and bilan["restaures"] + bilan["etat_d_execution_garde"] == dans_l_archive)
    return bilan


FORMES_IMPORT = (
    # Forme EXACTE du geste du propriétaire (railway ssh, root, maintenance sans s6), d'abord.
    ("hermes import --force (root, enveloppe officielle)", "hermes import --force /import/export.zip"),
    # Variante : racine du volume neuf rendue à l'UID hermes (l'enveloppe y redescend), puis le même import.
    ("chown 10000:10000 /opt/data, puis hermes import --force (root)",
     "chown 10000:10000 /opt/data && hermes import --force /import/export.zip"),
)


def test_r4_import_dans_un_volume_neuf_vide_a_root(export):
    e = export
    mesures: List[Dict[str, Any]] = []
    racines: List[str] = []
    retenue = None
    # Chaque forme est MESURÉE sur son propre volume neuf, vide et à root (un essai raté a pu écrire à moitié).
    for forme, commande in FORMES_IMPORT:
        volume = e.archives.ressources.nom("vol-import")
        docker("volume", "create", volume)
        e.archives.ressources.volumes.append(volume)
        monte = f"type=volume,src={volume},dst=/opt/data,volume-nocopy"
        racines.append(docker("run", "--rm", "-u", "0", "--network", "none", "--mount", monte, "--entrypoint",
                              "stat", e.image, "-c", "%u:%g %a", "/opt/data").stdout.strip())
        geste = docker("run", "--rm", "-u", "0", "--network", "none", "-e", "HERMES_HOME=/opt/data", "--mount", monte,
                       "-v", f"{e.archives.volume}:/import:ro", "--entrypoint", "/bin/sh", e.image, "-c", commande,
                       verifier=False, delai=600)
        sortie = geste.stdout + geste.stderr
        bilan = _bilan_import(geste.returncode, sortie, int(e.inventaire.get("dans_l_archive") or -1))
        proprietaires = docker("run", "--rm", "-u", "0", "--network", "none", "--mount", monte, "--entrypoint", "sh",
                               e.image, "-c", "stat -c '%u:%g %a %n' /opt/data /opt/data/.env /opt/data/auth.json "
                               "/opt/data/state.db /opt/data/plugin-data/acp-poste/data.db "
                               "/opt/data/scripts/acp-bilan.py 2>&1 || true").stdout
        mesures.append({"forme": forme, "bilan": bilan, "proprietaires_apres_import": proprietaires.splitlines(),
                        "sortie": [l for l in _lignes(sortie) if not l.strip().endswith("files ...")]})
        if bilan["complet"] and retenue is None:
            retenue = (forme, volume)
    afficher("R4 — import dans un volume neuf, vide et à root (volume-nocopy) : formes mesurées", _json({
        "racines_des_volumes_neufs": racines, "mesures": mesures, "forme_retenue": retenue[0] if retenue else None}))
    assert racines and all(r == "0:0 755" for r in racines), racines
    assert retenue is not None, "aucune forme d'import complète"
    e.forme_import, e.volume_importe = retenue
    assert "hermes update" not in e.forme_import


def test_r4_couche_2_archive_et_volume_importe(export):
    e = export
    sortie = docker("run", "--rm", "--network", "none", "-v", f"{e.archives.volume}:/a:ro", "--entrypoint", "sh",
                    e.image_tests, "-c", EXTRAIRE_ET_EMPREINDRE, delai=600)
    de_l_archive = json.loads(sortie.stdout)
    importe = bases(e.image_tests, e.volume_importe)
    ecarts = comparer_bases(de_l_archive, importe)
    afficher("R4 — couche 2 : bases de l'archive et du volume importé", _json({
        "archive": resume_bases(de_l_archive), "ecarts": ecarts[:20]}))
    assert de_l_archive["bases"] and ecarts == [], ecarts[:20]
    assert all(b["integrite"] == "ok" for b in importe["bases"].values())


def _demarrer(e: Export) -> Dict[str, Any]:
    """Démarrage NORMAL de l'image sur le volume importé. Un refus des gardes arrête le conteneur : son journal est
    relevé tel quel (le refus est un constat, jamais contourné)."""
    b, ressources = e.banc, e.archives.ressources
    avant = set(ressources.conteneurs)
    try:
        b.relancer_hermes(e.volume_importe)
        return {"accepte": True, "journal": b.hermes.journaux()}
    except AssertionError as exc:
        nouveaux = [n for n in ressources.conteneurs if n not in avant and "-hermes-" in n]
        if not nouveaux:
            raise
        journal = docker("logs", nouveaux[-1], verifier=False)
        return {"accepte": False, "journal": journal.stdout + journal.stderr, "erreur": str(exc)[:300]}


def test_r4_demarrage_normal_couche_3_et_reprise(export):
    e, b = export, export.banc
    e.ancien_hermes = b.hermes.nom
    docker("stop", "-t", "90", b.hermes.nom, delai=200)
    essais = []
    demarrage = _demarrer(e)
    refus = [l.split("REFUS : ", 1)[1] for l in demarrage["journal"].splitlines() if "[acp] REFUS : " in l]
    essais.append({"geste_prealable": None, "accepte": demarrage["accepte"], "refus": refus})
    if not demarrage["accepte"] and refus and all(SCRIPT_BILAN in r for r in refus):
        # Constat : le script du bilan importé appartient à l'utilisateur de l'import, pas à root ; la garde le refuse
        # et dit elle-même le geste (« supprimez ce fichier, root le redéposera au démarrage »). Geste appliqué EN
        # MAINTENANCE (root, sans s6), puis nouveau démarrage normal : mesuré à son tour.
        geste = f"rm -f /opt/data/scripts/{SCRIPT_BILAN}"
        docker("run", "--rm", "-u", "0", "--network", "none", "-v", f"{e.volume_importe}:/opt/data", "--entrypoint",
               "/bin/sh", e.image, "-c", geste)
        e.geste_au_demarrage.append(geste)
        demarrage = _demarrer(e)
        refus = [l.split("REFUS : ", 1)[1] for l in demarrage["journal"].splitlines() if "[acp] REFUS : " in l]
        essais.append({"geste_prealable": geste, "accepte": demarrage["accepte"], "refus": refus})
    journal = demarrage["journal"]
    afficher("R4 — démarrage normal sur le volume importé : essais et extraits", _json({
        "forme_d_import": e.forme_import, "essais": essais,
        "extraits": [l for l in journal.splitlines() if "[acp]" in l or "05-acp" in l][-40:]}))
    assert demarrage["accepte"], essais
    assert "cont-init: info: /etc/cont-init.d/05-acp exited 0" in journal
    assert "[acp] REFUS" not in journal
    lu = e.releve_reference()
    ecarts = {k: {"export": e.reference[k], "importé": lu[k]} for k in e.reference if lu[k] != e.reference[k]}
    afficher("R4 — couche 3 : lectures après import face à la référence de l'export", _json({
        "ecarts": ecarts or "aucun écart", "cartes_relues": lu["cartes"],
        # Statut de CHAQUE carte, relevé et imprimé, non comparé : seules les cartes d'exploration le sont (ci-dessus).
        "statuts_des_cartes": {"export": e.statuts_export, "importé": e.statuts_des_cartes()}}))
    assert ecarts == {}, ecarts
    # Pause levée ; l'exécutant (volume inchangé) continue avec ce Hermes : jeton machine de la base importée.
    code, reprise = b.api("POST", "/v1/pause", {"generale": False})
    assert code == 200 and not reprise["pause_generale"], reprise
    e.projets["E"] = b.lancer_projet("Export — E", "simple")
    e.cartes["E"] = b.carte_exploration(e.projets["E"]["tableau"])["id"]
    b.attendre_statut(e.projets["E"]["tableau"], e.cartes["E"], "done", delai=300)
    remote = b.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
    assert remote == e.remote_avant
    jeton_machine = b.executant_sh("cat /donnees/acp/secrets/jeton-machine").strip()
    executant = docker("logs", b.executant, verifier=False)
    for nom, texte in {"docker logs hermes": journal + b.hermes.journaux(),
                       "docker logs executant": executant.stdout + executant.stderr}.items():
        assert jeton_machine not in texte and JETON_CLAUDE not in texte and "acpe_" not in texte, nom
