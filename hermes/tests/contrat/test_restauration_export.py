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
   redescend alors à l'UID hermes. Forme MESURÉE ; si elle échoue, la variante retenue est mesurée à son tour et seule
   une forme mesurée est dite ;
5. démarrage normal de l'image sur ce volume : les gardes acceptent ou refusent (un refus est un CONSTAT, jamais
   contourné) ;
6. couche 2 : empreintes logiques des bases de l'archive et du volume importé égales ; couche 3 : lectures égales à la
   référence ;
7. l'exécutant, dont le volume n'a pas bougé, continue avec ce Hermes (jeton machine de la base importée) : projet E
   → terminé.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.parse
from typing import Any, Dict, List

import pytest

from banc import JETON_CLAUDE, PYTHON, Banc, attendre
from conftest import afficher, docker
from volumes import Archives, bases, comparer_bases, manifeste, resume_bases, resume_manifeste

pytestmark = pytest.mark.restauration

TACHE_BILAN = {"name": "Bilan ACP", "schedule": "0 8 * * *", "prompt": "", "no_agent": True,
               "script": "acp-bilan.py", "deliver": "local"}
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
    e.session_discussion = json.loads(b.hermes.executer(["cat", fichier], verifier=True).stdout)["session_id"]
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
        "reference": e.reference, "volume": resume_manifeste(e.manifeste_avant)}))
    assert reste != 0, "l'archive en clair est restée sur le volume de Hermes"
    assert e.reference["session_discussion"] and e.reference["taches_cron"] == [e.tache_bilan]


def test_r4_inventaire_de_l_archive(export):
    e = export
    sortie = docker("run", "--rm", "-i", "--network", "none", "-v", f"{e.archives.volume}:/a:ro", "--entrypoint",
                    PYTHON, e.image_tests, "-c", INVENTAIRE, entree=json.dumps(e.manifeste_avant["entrees"]))
    inventaire = json.loads(sortie.stdout)
    afficher("R4 — inventaire de l'archive face au volume (exclusions classées par hermes_cli.backup)", _json(
        dict(inventaire, attendues=inventaire["attendues"][:60])))
    assert inventaire["dans_l_archive"] > 0
    assert inventaire["inattendues"] == [], inventaire["inattendues"]


def test_r4_import_dans_un_volume_neuf_vide_a_root(export):
    e = export
    volume = e.archives.ressources.nom("vol-import")
    docker("volume", "create", volume)
    e.archives.ressources.volumes.append(volume)
    monte = f"type=volume,src={volume},dst=/opt/data,volume-nocopy"
    racine = docker("run", "--rm", "-u", "0", "--network", "none", "--mount", monte, "--entrypoint", "stat",
                    e.image, "-c", "%u:%g %a", "/opt/data").stdout.strip()
    # Forme exacte du geste du propriétaire (railway ssh, root, maintenance sans s6).
    geste = docker("run", "--rm", "-u", "0", "--network", "none", "-e", "HERMES_HOME=/opt/data", "--mount", monte,
                   "-v", f"{e.archives.volume}:/import:ro", "--entrypoint", "/bin/sh", e.image, "-c",
                   "hermes import --force /import/export.zip", verifier=False, delai=600)
    mesures: List[Dict[str, Any]] = [{"forme": "hermes import --force (root, enveloppe officielle)",
                                      "code": geste.returncode, "sortie": _lignes(geste.stdout + geste.stderr)}]
    reussi = geste.returncode == 0 and "Import complete" in geste.stdout
    if not reussi:
        # Variante mesurée : rendre la racine du volume neuf à l'UID hermes (ce que l'image ferait de son propre
        # /opt/data), puis le même import, sur un AUTRE volume neuf (l'essai raté a pu écrire à moitié).
        volume = e.archives.ressources.nom("vol-import")
        docker("volume", "create", volume)
        e.archives.ressources.volumes.append(volume)
        monte = f"type=volume,src={volume},dst=/opt/data,volume-nocopy"
        variante = docker("run", "--rm", "-u", "0", "--network", "none", "-e", "HERMES_HOME=/opt/data", "--mount",
                          monte, "-v", f"{e.archives.volume}:/import:ro", "--entrypoint", "/bin/sh", e.image, "-c",
                          "chown 10000:10000 /opt/data && hermes import --force /import/export.zip", verifier=False,
                          delai=600)
        mesures.append({"forme": "chown 10000:10000 /opt/data, puis hermes import --force (root)",
                        "code": variante.returncode, "sortie": _lignes(variante.stdout + variante.stderr)})
        reussi = variante.returncode == 0 and "Import complete" in variante.stdout
    e.volume_importe = volume
    e.forme_import = mesures[-1]["forme"]
    proprietaires = docker("run", "--rm", "-u", "0", "--network", "none", "--mount", monte, "--entrypoint", "sh",
                           e.image, "-c", "stat -c '%u:%g %a %n' /opt/data /opt/data/.env /opt/data/auth.json "
                           "/opt/data/state.db /opt/data/plugin-data/acp-poste/data.db 2>&1 || true").stdout
    afficher("R4 — import dans un volume neuf, vide et à root (volume-nocopy)", _json({
        "racine_du_volume_neuf": racine, "mesures": mesures, "forme_retenue": e.forme_import if reussi else None,
        "proprietaires_apres_import": proprietaires.splitlines()}))
    assert racine == "0:0 755", racine
    assert reussi, mesures
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


def test_r4_demarrage_normal_couche_3_et_reprise(export):
    e, b = export, export.banc
    e.ancien_hermes = b.hermes.nom
    docker("stop", "-t", "90", b.hermes.nom, delai=200)
    b.relancer_hermes(e.volume_importe)
    journal = b.hermes.journaux()
    afficher("R4 — démarrage normal sur le volume importé (extraits)", "\n".join(
        l for l in journal.splitlines() if "[acp]" in l or "05-acp" in l)[-6000:])
    assert "cont-init: info: /etc/cont-init.d/05-acp exited 0" in journal
    assert "[acp] REFUS" not in journal
    lu = e.releve_reference()
    ecarts = {k: {"export": e.reference[k], "importé": lu[k]} for k in e.reference if lu[k] != e.reference[k]}
    afficher("R4 — couche 3 : lectures après import face à la référence de l'export", _json(ecarts or "aucun écart"))
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
