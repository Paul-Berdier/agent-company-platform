"""Montée de DONNÉES d'une image à la suivante (étape P9, cahier P9 § 5.6), pilotée depuis l'hôte.

Le risque réel d'une montée sur Railway est le VOLUME QUI RESTE : l'image change, les bases restent. Ce test peuple les
volumes de Hermes (/opt/data) et de l'exécutant (/donnees) avec les images « AVANT » (ACP_IMAGE_TESTS_AVANT,
ACP_IMAGE_EXECUTANT_FACTICE_AVANT, construites par le job « montee » d'image.yml depuis son entrée ``ref_avant``), puis
redémarre LES MÊMES VOLUMES avec les images « APRÈS » (ACP_IMAGE_TESTS, ACP_IMAGE_EXECUTANT_FACTICE : celles du commit).

1. peuplement AVANT par les routes communes aux deux versions (celles de P6 : projets, cartes, exécutant, questions),
   gestes de R1 (test_restauration.py) réduits aux scénarios « simple » et « question », présents dans les deux cibles
   factices (« attente » n'existe pas avant P9) : routage validé, projet A terminé, projet B arrêté sur une question
   ouverte, réglage changé, notification envoyée ; puis REPOS (la question de B escaladée par le filet de
   l'émetteur, plus aucune notification en attente, deux passes de l'émetteur) ; référence lue par les API ;
2. arrêt propre (exécutant, puis Hermes) ; relevés AVANT : manifestes, et pour chaque base SQLite son schéma
   (``PRAGMA user_version``, version du greffon dans ``meta_schema``, objets de ``sqlite_master``), ses compteurs
   ``AUTOINCREMENT`` et l'empreinte de CHAQUE ligne (outils/empreinte_volume.py ``lignes``) ;
3. CONTRÔLE : l'image AVANT redémarrée sur une COPIE du volume de Hermes, deux passes de l'émetteur, mêmes lectures,
   même relevé à chaud : ce qu'un simple redémarrage change (tables « vivantes ») est MESURÉ, jamais supposé ;
4. MONTÉE : Hermes APRÈS sur le même volume : gardes acceptées, migration du greffon faite (moment relevé), mêmes
   deux passes, relevé APRÈS à chaud (``docker pause``), projeté sur les colonnes d'avant ; schémas imprimés avant et
   après et « migration de schéma : oui/non » (changements absents du contrôle) ; DÉFAUTS : base, table ou colonne
   d'avant disparue, ligne d'avant perdue ou modifiée dans une table que le contrôle ne change pas (hors ligne de
   version de ``meta_schema``), compteur ``AUTOINCREMENT`` revenu en arrière, intégrité perdue ; lectures égales à la
   référence ;
5. exécutant APRÈS sur son même volume : prêt, enrôlé, en ligne ; jeton, empreinte et références git égales ;
6. le travail REPREND : réponse à B → fil repris (``--resume`` d'une session ouverte par l'exécutant AVANT) →
   terminée ; nouveau projet E → terminé, un commit d'exploration ; aucun jeton dans les journaux, aucun push.

Autorité de test : chaque image de test génère la sienne à sa construction. Le banc (faux IdP, faux ntfy, dépôt
factice, bords) tourne avec celle de l'image AVANT ; l'image de test APRÈS est donc dérivée ici avec la MÊME autorité
(seul ``/opt/acp-tests/ac`` et le magasin du système changent ; le code d'ACP et de Hermes est celui de l'image après).

Résultat pour le job (``ACP_MONTEE_DOSSIER``, facultatif) : ``resultat.json`` et ``resume.md``, dont la ligne
« migration de schéma : oui » ou « non ». Rien n'est jamais imprimé d'un contenu de base ni d'un jeton : des
décomptes, des empreintes courtes, des noms, des statuts et le SQL du schéma.

Ce que ce test NE prouve PAS (cahier § 5.8) : la montée d'un volume réel de Railway (seulement des volumes peuplés ici,
sans données du propriétaire), le déploiement réel, Rollback face au volume.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from banc import JETON_CLAUDE, JOURNAL_DEPOT, PYTHON, POSTE_SIMULE, RACINE, SECRET_FACTICE, Banc, attendre, \
    politique_de_test
from conftest import afficher, docker
from volumes import Archives, a_chaud, changements_propres, comparer_lignes, comparer_manifestes, comparer_schemas, \
    defauts_de_montee, lignes, manifeste, projection_de, resume_manifeste

pytestmark = pytest.mark.montee

BASE_GREFFON = "plugin-data/acp-poste/data.db"
SOURCE_SCHEMA_GREFFON = "/opt/hermes/plugins/acp-poste/noyau/base.py"
SEUIL_AVANT = 85  # réglage « seuil_quota_pct » changé avant la montée (défaut : 90)
REGLAGES_LUS = ("seuil_quota_pct", "emetteur_intervalle_s", "projets_actifs_max")
CLES_EXECUTANT = ("jeton_executant", "refs")  # lues seulement quand l'exécutant tourne


def _json(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False, indent=1, default=str)


def _image(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        pytest.fail(f"{nom} n'est pas défini : la montée de données exige les images « avant » et « après » "
                    "(job « montee » d'image.yml, entrée ref_avant).", pytrace=False)
    return valeur


def _racine_avant() -> Path:
    """Arbre du commit « avant » (sa politique d'exécutant) ; sans ACP_RACINE_AVANT, l'arbre courant (dit)."""
    valeur = os.environ.get("ACP_RACINE_AVANT", "").strip()
    if not valeur:
        afficher("Montée — politique de l'exécutant avant",
                 "ACP_RACINE_AVANT non défini : politique de l'arbre courant.")
        return RACINE
    racine = Path(valeur)
    if not (racine / "executant" / "politique" / "executant.toml").is_file():
        pytest.fail(f"ACP_RACINE_AVANT={valeur} ne contient pas executant/politique/executant.toml.", pytrace=False)
    return racine


def schema_de_l_image(image: str) -> Optional[str]:
    """Version de schéma que le greffon de l'image pose (``VERSION_SCHEMA`` de noyau/base.py, lu dans l'image)."""
    texte = docker("run", "--rm", "--entrypoint", "cat", image, SOURCE_SCHEMA_GREFFON).stdout
    trouve = re.search(r'^VERSION_SCHEMA = "([^"]+)"$', texte, flags=re.M)
    return trouve.group(1) if trouve else None


def image_apres_meme_autorite(ressources, image_apres: str, image_avant: str) -> str:
    """Image de test APRÈS portant l'autorité de test de l'image AVANT (fichiers de ``/opt/acp-tests/ac`` recopiés,
    magasin du système reconstruit) : le banc monté avec l'image avant reste ainsi de confiance pour Hermes après, et
    l'exécutant après fait confiance aux deux bords. Aucun autre changement."""
    brut = docker("run", "--rm", "--entrypoint", "sh", image_avant, "-c",
                  "tar -C /opt/acp-tests -cf - ac | base64 -w 0").stdout
    image = f"{ressources.prefixe}-tests:apres-ac-avant"
    with tempfile.TemporaryDirectory(prefix="acp-montee-ac-") as dossier:
        contexte = Path(dossier)
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(brut))) as archive:
            archive.extractall(contexte, filter="data")
        assert (contexte / "ac" / "ac.pem").is_file(), sorted(p.name for p in (contexte / "ac").iterdir())
        (contexte / "Dockerfile").write_text(
            "ARG IMAGE\nFROM ${IMAGE}\n"
            "RUN rm -rf /opt/acp-tests/ac\n"
            "COPY ac/ /opt/acp-tests/ac/\n"
            "RUN set -eu; chown -R root:root /opt/acp-tests/ac; chmod 0755 /opt/acp-tests/ac; "
            "chmod 0644 /opt/acp-tests/ac/*; "
            "cp /opt/acp-tests/ac/ac.pem /usr/local/share/ca-certificates/acp-test-jetable.crt; "
            "update-ca-certificates --fresh\n", encoding="utf-8", newline="\n")
        docker("build", "-q", "--build-arg", f"IMAGE={image_apres}", "-t", image, str(contexte), delai=600)
    return image


def _resume_releve(releve: Dict[str, Any]) -> Dict[str, Any]:
    """Ce que le journal imprime d'un relevé ``lignes`` : intégrité, versions, nombre de tables et de lignes."""
    return {base: {"integrite": e.get("integrite"), "user_version": e.get("user_version"),
                   "meta_schema": e.get("meta_schema"), "tables": len(e.get("tables") or {}),
                   "lignes": sum(t.get("nombre", 0) for t in (e.get("tables") or {}).values())}
            for base, e in sorted(releve["bases"].items())}


def _difference_sql(avant: str, apres: str, contexte: int = 80) -> Dict[str, str]:
    """Le SQL de schéma d'un objet avant et après, à partir de peu avant leur première différence (le reste est
    commun)."""
    commun = 0
    while commun < min(len(avant), len(apres)) and avant[commun] == apres[commun]:
        commun += 1
    debut = max(0, commun - contexte)
    prefixe = "…" if debut else ""
    return {"avant": prefixe + avant[debut:debut + 900], "apres": prefixe + apres[debut:debut + 900]}


def _sans_exemples(ecarts: Dict[str, Any]) -> Dict[str, Any]:
    """Écarts de ``comparer_lignes`` réduits aux décomptes, par « base : table »."""
    resume: Dict[str, Any] = {}
    for base, e in ecarts.items():
        if "base" in e:
            resume[base] = e
            continue
        for table, ecart in e["tables"].items():
            resume[f"{base} : {table}"] = {k: v for k, v in ecart.items() if k != "exemples" and v not in ([], 0)}
    return resume


class Montee:
    """État partagé des étapes (le test est une suite ordonnée, comme R1)."""

    def __init__(self, banc: Banc, archives: Archives, images: Dict[str, str]) -> None:
        self.banc, self.archives, self.images = banc, archives, images
        self.outils = images["tests_apres"]  # empreinte_volume.py de CE commit, pour tous les relevés
        self.projets: Dict[str, Dict[str, Any]] = {}
        self.cartes: Dict[str, str] = {}
        self.question_b: Dict[str, Any] = {}
        self.reference: Dict[str, Any] = {}
        self.remote_avant = ""
        self.volumes: Dict[str, str] = {}
        self.versions: Dict[str, Optional[str]] = {}
        self.avant: Dict[str, Any] = {}
        self.projection: Dict[str, Any] = {}
        self.controle: Dict[str, Any] = {}
        self.apres: Dict[str, Any] = {}
        self.conteneurs: Dict[str, List[str]] = {"hermes": [], "executant": []}
        self.resultat: Dict[str, Any] = {"migration_de_schema": "inconnue", "travail_repris": "non mesuré"}

    # ------------------------------------------------------------------ lectures
    def sql(self, requete: str, *parametres: str) -> List[Dict[str, Any]]:
        """Lecture SEULE de la base du greffon (``mode=ro`` : n'ouvre jamais le noyau, donc ne migre rien)."""
        code = ("import json, sqlite3, sys\n"
                "c = sqlite3.connect('file:/opt/data/plugin-data/acp-poste/data.db?mode=ro', uri=True)\n"
                "c.row_factory = sqlite3.Row\n"
                "print(json.dumps([dict(l) for l in c.execute(sys.argv[1], sys.argv[2:])], ensure_ascii=False, "
                "default=str))\n")
        sortie = self.banc.hermes.executer([PYTHON, "-c", code, requete, *parametres], utilisateur="hermes",
                                           verifier=True)
        return json.loads(sortie.stdout)

    def reglage(self, cle: str) -> Any:
        lignes_ = self.sql("SELECT valeur FROM reglages WHERE cle = ?", cle)
        return json.loads(lignes_[0]["valeur"]) if lignes_ else None

    def poser_reglage(self, cle: str, valeur: Any) -> None:
        sortie = self.banc.hermes.executer([PYTHON, POSTE_SIMULE, "reglage", cle, json.dumps(valeur)],
                                           utilisateur="hermes", delai=120)
        assert sortie.returncode == 0, sortie.stderr[-2000:]

    def derniere_passe(self) -> int:
        """Fin de la dernière passe COMPLÈTE de l'émetteur (``emetteur.derniere_passe``, écrite en fin de passe), en
        secondes depuis l'époque ; 0 si aucune ou illisible."""
        try:
            lignes_ = self.sql("SELECT valeur FROM emetteur WHERE cle = 'derniere_passe'")
            return int(json.loads(lignes_[0]["valeur"])) if lignes_ else 0
        except (AssertionError, ValueError, TypeError):
            return 0

    def attendre_deux_passes(self, depuis: float) -> Dict[str, Any]:
        """Deux passes complètes de l'émetteur terminées après ``depuis`` : ce qu'un redémarrage déclenche (événements
        en retard, filets) est fait, au même point pour le contrôle et pour la montée. Rend les instants relevés."""
        premiere = attendre(lambda: (lambda p: p if p > int(depuis) else None)(self.derniere_passe()), 180,
                            "aucune passe complète de l'émetteur après le redémarrage")
        seconde = attendre(lambda: (lambda p: p if p > premiere else None)(self.derniere_passe()), 120,
                           "pas de seconde passe complète de l'émetteur")
        return {"premiere_passe_s": premiere - int(depuis), "seconde_passe_s": seconde - int(depuis)}

    def attendre_le_repos(self) -> str:
        """T au REPOS avant l'arrêt (run 37780726989 : sans cette attente, le contrôle et la montée relevaient, chacun
        à son heure, un travail encore en cours à T) : la carte « répondre » de Hermes (modèle factice) finit sans
        réponse et le filet de l'émetteur escalade la question de B (notification « question ») ; plus aucune
        notification en attente ; deux passes complètes de l'émetteur ensuite (curseurs à jour). Mesuré : une attente
        dépassée est dite, sans arrêter le test (la montée relèvera alors ce qui restait)."""
        debut, constats = time.monotonic(), []

        def escaladee():
            questions = self.lire("/v1/questions")["questions"]
            return next((q for q in questions if q["id"] == self.question_b["id"] and q.get("etat") == "escaladee"),
                        None)

        for nom, predicat, delai in (
                ("question de B escaladée", escaladee, 480),
                ("aucune notification en attente",
                 lambda: not self.sql("SELECT 1 FROM notifications WHERE etat = 'en_attente'"), 180)):
            try:
                attendre(predicat, delai, nom)
                constats.append(f"{nom} ({time.monotonic() - debut:.0f} s)")
            except AssertionError as exc:
                constats.append(f"NON : {exc}"[:300])
        try:
            self.attendre_deux_passes(time.time())
            constats.append(f"deux passes de l'émetteur ensuite ({time.monotonic() - debut:.0f} s)")
        except AssertionError as exc:
            constats.append(f"NON : {exc}"[:300])
        return " ; ".join(constats)

    def version_en_base(self) -> Optional[str]:
        """Version du greffon lue en base (lecture seule) ; ``None`` si elle est illisible à cet instant (dit)."""
        try:
            lignes_ = self.sql("SELECT valeur FROM meta_schema WHERE cle = 'version'")
        except AssertionError:
            return None
        return lignes_[0]["valeur"] if lignes_ else None

    def lire(self, chemin: str) -> Dict[str, Any]:
        code, corps = self.banc.api("GET", chemin)
        assert code == 200 and isinstance(corps, dict), (chemin, code, str(corps)[:2000])
        return corps

    def statuts(self) -> Dict[str, str]:
        resultat = {}
        for lettre, projet in self.projets.items():
            cartes = {c["id"]: c["statut"] for c in self.banc.cartes(projet["tableau"])}
            resultat[lettre] = cartes.get(self.cartes[lettre], "absente")
        return resultat

    def refs(self) -> Dict[str, str]:
        sortie = self.banc.depot_nu("for-each-ref", "--format=%(refname) %(objectname:short=12)")
        return dict(l.split(" ", 1) for l in sortie.splitlines() if l.strip())

    def releve(self, *, executant: bool) -> Dict[str, Any]:
        """Champs STABLES lus par les routes communes aux deux versions ; jamais un contenu de fichier ni un jeton."""
        projets = self.lire("/v1/projets")
        questions = self.lire("/v1/questions")
        poste = self.lire("/v1/poste")
        routage = self.lire("/v1/routage")
        machine = (poste.get("machine") or {}).get("machine") or {}
        lu: Dict[str, Any] = {
            "projets": {p["id"]: {"titre": p["titre"]} for p in projets["projets"]},
            "questions_ouvertes": sorted((q["id"], q["carte"], q["texte"]) for q in questions["questions"]),
            "machine": {k: machine.get(k) for k in ("id", "etat", "empreinte")},
            "routage_valide": {c: [(e["voie"], e["modele"], e["effort"]) for e in (v.get("entrees") or [])]
                               for c, v in (routage.get("classes") or {}).items() if v.get("etat") == "validee"},
            "reglages": {c: self.reglage(c) for c in REGLAGES_LUS},
            "statuts": self.statuts(),
        }
        if executant:
            diagnostic = json.loads(self.banc.acp_poste("diagnostic").stdout or "{}")
            jeton = diagnostic.get("jeton") or {}
            lu["jeton_executant"] = {k: jeton.get(k) for k in ("present", "machine_id", "empreinte")}
            lu["refs"] = self.refs()
        return lu

    def notifications(self) -> Dict[str, int]:
        return {f"{l['genre']}:{l['etat']}": l["n"] for l in self.sql(
            "SELECT genre, etat, COUNT(*) AS n FROM notifications GROUP BY genre, etat")}

    def meta(self) -> Dict[str, Any]:
        """Versions vues par /v1/meta (greffon, Hermes, schéma du greffon) et nombre d'alertes : imprimées seulement."""
        code, meta = self.banc.api("GET", "/v1/meta")
        if code != 200 or not isinstance(meta, dict):
            return {"code": code, "corps": str(meta)[:500]}
        hermes = meta.get("hermes") or {}
        return {"greffon": (meta.get("greffon") or {}).get("version"), "hermes": hermes.get("version"),
                "etiquette": hermes.get("etiquette"), "conforme": hermes.get("conforme"),
                "schema_greffon": (meta.get("projets") or {}).get("schema"), "alertes": len(meta.get("alertes") or [])}

    def ecarts(self, lu: Dict[str, Any]) -> Dict[str, Any]:
        return {k: {"reference": self.reference[k], "lu": lu[k]} for k in lu if lu[k] != self.reference.get(k)}

    def ecrire_resultat(self) -> None:
        """``resultat.json`` et ``resume.md`` pour le résumé du job (ACP_MONTEE_DOSSIER) ; rien sans cette variable."""
        dossier = os.environ.get("ACP_MONTEE_DOSSIER", "").strip()
        if not dossier:
            return
        Path(dossier).mkdir(parents=True, exist_ok=True)
        r = self.resultat
        (Path(dossier) / "resultat.json").write_text(_json(r) + "\n", encoding="utf-8")
        propres = r.get("changements_de_schema") or {}
        lignes_resume = [
            "## Montée de données (test_montee_de_donnees.py)", "",
            f"migration de schéma : {r['migration_de_schema']}", "",
            f"- schéma du greffon posé par les images : avant {r.get('schema_greffon_images', {}).get('avant')}, "
            f"après {r.get('schema_greffon_images', {}).get('apres')}",
            f"- repos à T, avant l'arrêt : {r.get('repos_a_t', 'non mesuré')}",
            f"- migration du greffon faite : {r.get('migration_faite', 'non mesuré')}",
            "- changements de schéma propres à la montée (absents du contrôle) : "
            + ("; ".join(f"{b} : {_json(e)}".replace("\n", "") for b, e in propres.items()) or "aucun"),
            f"- bases nouvelles : {', '.join(r.get('bases_nouvelles') or []) or 'aucune'}",
            f"- défauts (données d'avant perdues ou altérées) : {'; '.join(r.get('defauts') or []) or 'aucun'}"
            if "defauts" in r else "- défauts : non mesurés",
            "- tables vivantes au contrôle (même image redémarrée) : "
            f"{len(r.get('tables_vivantes_au_controle') or [])}",
            f"- lectures après la montée face à la référence : {r.get('lectures', 'non mesuré')}",
            f"- exécutant après : {r.get('executant', 'non mesuré')}",
            f"- travail repris : {r['travail_repris']}",
        ]
        (Path(dossier) / "resume.md").write_text("\n".join(lignes_resume) + "\n", encoding="utf-8")

    def aucun_jeton_ni_push(self) -> Dict[str, Any]:
        b = self.banc
        remote = b.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
        assert remote == self.remote_avant, "références du dépôt distant changées"
        requetes = [json.loads(l) for l in docker("exec", b.depot, "cat", JOURNAL_DEPOT).stdout.splitlines() if l]
        assert requetes and {r["methode"] for r in requetes} <= {"GET", "HEAD"}
        assert not any("receive-pack" in r["chemin"] for r in requetes)
        jeton_machine = b.executant_sh("cat /donnees/acp/secrets/jeton-machine").strip()
        assert jeton_machine.startswith("acpm_")
        textes: Dict[str, str] = {}
        for role, noms in self.conteneurs.items():
            for nom in noms:
                journal = docker("logs", nom, verifier=False)
                textes[f"docker logs {role} {nom}"] = journal.stdout + journal.stderr
        textes["journal de l'exécutant"] = b.executant_sh("cat /donnees/acp/journal/* 2>/dev/null || true")
        textes["file de sortie"] = b.executant_sh("cat /donnees/acp/sortie/* /donnees/acp/sortie/refusees/* "
                                                  "2>/dev/null || true")
        for nom, texte in textes.items():
            for valeur in (jeton_machine, JETON_CLAUDE, SECRET_FACTICE):
                assert valeur not in texte, nom
            assert "acpe_" not in texte, nom
        return {"requetes_depot": len(requetes), "journaux_controles": len(textes)}


@pytest.fixture(scope="module")
def montee(ressources):
    images = {"tests_avant": _image("ACP_IMAGE_TESTS_AVANT"),
              "factice_avant": _image("ACP_IMAGE_EXECUTANT_FACTICE_AVANT"),
              "tests_apres_d_origine": _image("ACP_IMAGE_TESTS"),
              "factice_apres": _image("ACP_IMAGE_EXECUTANT_FACTICE")}
    banc = Banc(ressources, images["tests_avant"])
    try:
        banc.monter()
        images["tests_apres"] = image_apres_meme_autorite(ressources, images["tests_apres_d_origine"],
                                                          images["tests_avant"])
        banc.images_construites.append(images["tests_apres"])
        images["executant_apres"] = banc.construire_executant(images["factice_apres"], "apres")
        images["executant_avant"] = banc.construire_executant(images["factice_avant"], "avant",
                                                              politique_de_test(_racine_avant()))
        banc.demarrer_executant()
        scene = Montee(banc, Archives(ressources, images["tests_avant"]), images)
        scene.conteneurs["hermes"].append(banc.hermes.nom)
        scene.conteneurs["executant"].append(banc.executant)
        afficher("Montée — images", _json(images))
        yield scene
    finally:
        banc.nettoyer_image()


# =========================================================================== 1. peuplement avec les images AVANT


def test_m1_peuplement_avant(montee: Montee):
    m, b = montee, montee.banc
    m.remote_avant = b.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
    vue = b.mettre_en_service()
    executant = vue.get("executant") or {}
    routage = m.lire("/v1/routage")
    entrees = ((routage["classes"].get("exploration") or {}).get("suggestion") or {}).get("entrees") or [
        {"voie": "poste-claude", "modele": "opus", "effort": "low"}]
    code, valide = b.api("POST", "/v1/routage", {"releves": routage["releves"], "classes": {"exploration": entrees}})
    assert code == 200, valide
    m.projets["A"] = b.lancer_projet("Montée — A", "simple")
    m.cartes["A"] = b.carte_exploration(m.projets["A"]["tableau"])["id"]
    b.attendre_statut(m.projets["A"]["tableau"], m.cartes["A"], "done", delai=300)
    m.projets["B"] = b.lancer_projet("Montée — B", "question")
    m.cartes["B"] = b.carte_exploration(m.projets["B"]["tableau"])["id"]

    def question():
        code, liste = b.api("GET", "/v1/questions")
        return next((q for q in liste["questions"] if q["carte"] == m.cartes["B"]), None) if code == 200 else None

    m.question_b = attendre(question, 240, f"question de B jamais posée ({b.fin_journal()})")
    # La carte de B quitte « running » quand l'exécutant a rendu sa question (R1 : « scheduled » chez Hermes).
    attendre(lambda: (lambda s: s if s != "running" else None)(b.statut(m.projets["B"]["tableau"], m.cartes["B"])),
             120, "carte de B encore « running » après sa question")
    m.poser_reglage("seuil_quota_pct", SEUIL_AVANT)
    attendre(lambda: b.notifications(), 90, "aucune notification reçue par le faux ntfy")
    m.resultat["repos_a_t"] = m.attendre_le_repos()
    m.reference = m.releve(executant=True)
    m.resultat["avant"] = {"meta": m.meta(), "notifications": m.notifications(),
                           "executant": {k: executant.get(k) for k in ("plateforme", "version", "voies_disponibles")}}
    afficher("Montée 1 — référence AVANT (champs stables)", _json({
        **{k: v for k, v in m.reference.items() if k != "refs"}, "refs": len(m.reference["refs"]),
        "avant": m.resultat["avant"], "repos_a_t": m.resultat["repos_a_t"],
        "notifications_recues_par_le_faux_ntfy": len(b.notifications())}))
    assert set(m.reference["projets"]) == {m.projets[x]["id"] for x in "AB"}
    assert [q[1] for q in m.reference["questions_ouvertes"]] == [m.cartes["B"]]
    assert m.reference["reglages"]["seuil_quota_pct"] == SEUIL_AVANT
    assert m.reference["jeton_executant"]["present"] is True and m.reference["statuts"]["A"] == "done"


# =========================================================================== 2. arrêt propre et relevés AVANT


def test_m2_arret_et_releves_avant(montee: Montee):
    m, b = montee, montee.banc
    arrets = b.arreter()
    m.volumes = {"hermes": b.volume_hermes, "executant": b.volume_executant}
    m.avant = {role: {"manifeste": manifeste(m.outils, v), "lignes": lignes(m.outils, v)}
               for role, v in m.volumes.items()}
    m.projection = projection_de(m.avant["hermes"]["lignes"])
    archive = m.archives.instantane(m.volumes["hermes"], "avant-hermes")
    m.versions = {"avant": schema_de_l_image(m.images["tests_avant"]),
                  "apres": schema_de_l_image(m.images["tests_apres"])}
    m.resultat["schema_greffon_images"] = m.versions
    afficher("Montée 2 — arrêt propre et relevés AVANT", _json({
        "arrets": arrets, "schema_greffon_images": m.versions, "archive_pour_le_controle": archive,
        "manifestes": {role: resume_manifeste(r["manifeste"]) for role, r in m.avant.items()},
        "bases": {role: _resume_releve(r["lignes"]) for role, r in m.avant.items()}}))
    bases_hermes = m.avant["hermes"]["lignes"]["bases"]
    assert BASE_GREFFON in bases_hermes, sorted(bases_hermes)
    for role, r in m.avant.items():
        for base, e in r["lignes"]["bases"].items():
            assert e.get("integrite") == "ok", (role, base, e.get("integrite"))
    assert bases_hermes[BASE_GREFFON]["meta_schema"] == m.versions["avant"], (
        bases_hermes[BASE_GREFFON]["meta_schema"], m.versions)


# =========================================================================== 3. contrôle : même image AVANT, redémarrée


def test_m3_controle_redemarrage_avec_l_image_avant(montee: Montee):
    """Ce qu'un simple redémarrage change, mesuré sur une COPIE du volume de Hermes (l'original reste celui d'avant)."""
    m, b = montee, montee.banc
    volume = m.archives.volume_restaure("avant-hermes", "hermes-controle")
    b.image_tests = m.images["tests_avant"]
    debut, depuis = time.monotonic(), time.time()
    b.relancer_hermes(volume)
    m.conteneurs["hermes"].append(b.hermes.nom)
    passes = m.attendre_deux_passes(depuis)
    lu = m.releve(executant=False)
    with a_chaud([b.hermes.nom]):
        releve = lignes(m.outils, volume, m.projection)
    duree = time.monotonic() - debut
    docker("stop", "-t", "90", b.hermes.nom, delai=150)
    avant = m.avant["hermes"]["lignes"]
    m.controle = {"lignes": releve, "ecarts": comparer_lignes(avant, releve),
                  "schemas": comparer_schemas(avant, releve)}
    ecarts_lectures = m.ecarts(lu)
    m.resultat["tables_vivantes_au_controle"] = sorted(_sans_exemples(m.controle["ecarts"]))
    afficher(f"Montée 3 — CONTRÔLE : image avant redémarrée sur une copie ({duree:.0f} s jusqu'au relevé)", _json({
        "passes_de_l_emetteur": passes, "lectures_face_a_la_reference": ecarts_lectures or "égales",
        "tables_vivantes": _sans_exemples(m.controle["ecarts"]),
        "schemas": m.controle["schemas"] or "inchangés", "bases": _resume_releve(releve)}))
    assert ecarts_lectures == {}, ecarts_lectures


# =========================================================================== 4. montée : Hermes APRÈS, même volume


def test_m4_montee_hermes_apres_sur_le_meme_volume(montee: Montee):
    m, b = montee, montee.banc
    volume = m.volumes["hermes"]
    b.image_tests = m.images["tests_apres"]
    debut, depuis = time.monotonic(), time.time()
    b.relancer_hermes(volume)
    m.conteneurs["hermes"].append(b.hermes.nom)
    pret = time.monotonic() - debut
    journal = b.hermes.journaux()
    # La migration du greffon se fait à la première ouverture de sa base : au démarrage (passerelle, tableau de bord)
    # ou à la première lecture par une route. Mesuré (lecture SEULE de la base, qui ne migre rien).
    try:
        attendre(lambda: m.version_en_base() == m.versions["apres"], 60, "version du greffon inchangée", pas=2)
        m.resultat["migration_faite"] = f"au démarrage, sans requête (version lue {time.monotonic() - debut:.0f} s " \
                                        "après le lancement)"
    except AssertionError:
        m.resultat["migration_faite"] = (f"pas dans les 60 s qui suivent le démarrage (version en base : "
                                         f"{m.version_en_base()!r}) : à la première lecture par une route")
    # Mêmes passes de l'émetteur que le contrôle avant les lectures et le relevé (comparaison au même point).
    passes = m.attendre_deux_passes(depuis)
    lu = m.releve(executant=False)
    meta = m.meta()
    with a_chaud([b.hermes.nom]):
        m.apres = {"manifeste": manifeste(m.outils, volume), "lignes": lignes(m.outils, volume, m.projection)}
    avant, apres = m.avant["hermes"]["lignes"], m.apres["lignes"]
    # Sans contrôle (étape 3 en échec), rien n'est retranché : la comparaison est plus stricte, et le test échoue à la
    # fin (dit), après avoir tout imprimé.
    controle = m.controle or {"ecarts": {}, "schemas": {}}
    schemas = comparer_schemas(avant, apres)
    propres = changements_propres(schemas, controle["schemas"])
    montee_lignes = comparer_lignes(avant, apres)
    defauts = defauts_de_montee(avant, apres, montee_lignes, controle["ecarts"])
    ecarts_lectures = m.ecarts(lu)
    migration = any(e.get("base") != "nouvelle" for e in propres.values())
    m.resultat.update({
        "migration_de_schema": "oui" if migration else "non",
        "changements_de_schema": {base: e for base, e in propres.items() if e.get("base") != "nouvelle"},
        "bases_nouvelles": sorted(base for base, e in propres.items() if e.get("base") == "nouvelle"),
        "defauts": defauts, "lectures": "égales" if not ecarts_lectures else ecarts_lectures,
        "apres": {"meta": meta}, "lignes_changees_hors_controle": _sans_exemples(
            changements_propres(montee_lignes, controle["ecarts"]))})
    m.ecrire_resultat()
    # Tout est imprimé AVANT d'affirmer.
    sql_change = {}
    for base, e in propres.items():
        objets_avant = (avant["bases"].get(base) or {}).get("objets") or {}
        objets_apres = (apres["bases"].get(base) or {}).get("objets") or {}
        objets = [o for cle in ("objets_modifies", "objets_ajoutes", "objets_retires") for o in (e.get(cle) or [])]
        for objet in objets:
            sql_change[f"{base} : {objet}"] = _difference_sql(objets_avant.get(objet, "(absent)"),
                                                              objets_apres.get(objet, "(absent)"))
    afficher(f"Montée 4 — Hermes APRÈS sur le volume d'avant (prêt en {pret:.0f} s) : journal", "\n".join(
        [l for l in journal.splitlines() if "[acp]" in l or "05-acp" in l][:60]))
    afficher("Montée 4 — schémas AVANT et APRÈS", _json({
        "migration de schéma": m.resultat["migration_de_schema"], "migration_faite": m.resultat["migration_faite"],
        "passes_de_l_emetteur": passes,
        "schema_greffon_images": m.versions, "avant": _resume_releve(avant), "apres": _resume_releve(apres),
        "changements_de_schema": schemas, "dont_propres_a_la_montee": propres, "sql_avant_apres": sql_change}))
    afficher("Montée 4 — lignes d'avant après la montée (projetées sur les colonnes d'avant)", _json({
        "defauts": defauts or "aucun", "changees_par_la_montee": _sans_exemples(montee_lignes),
        "nouvelles_colonnes": {f"{base} : {t}": e["nouvelles_colonnes"] for base, eb in apres["bases"].items()
                               for t, e in (eb.get("tables") or {}).items() if e.get("nouvelles_colonnes")},
        "fichiers_du_volume_changes": [e[:160] for e in comparer_manifestes(m.avant["hermes"]["manifeste"],
                                                                           m.apres["manifeste"])][:60]}))
    afficher("Montée 4 — lectures et /v1/meta après la montée", _json({
        "lectures_face_a_la_reference": ecarts_lectures or "égales", "meta_avant": m.resultat["avant"]["meta"],
        "meta_apres": meta, "notifications": {"avant": m.resultat["avant"]["notifications"],
                                              "apres": m.notifications()}}))
    assert "cont-init: info: /etc/cont-init.d/05-acp exited 0" in journal
    assert "[acp] REFUS" not in journal
    assert (apres["bases"].get(BASE_GREFFON) or {}).get("meta_schema") == m.versions["apres"], m.versions
    assert defauts == [], defauts
    assert ecarts_lectures == {}, ecarts_lectures
    assert m.controle, "contrôle non mesuré (étape 3 en échec) : rien n'a pu être retranché de la comparaison"


# =========================================================================== 5. exécutant APRÈS sur son même volume


def test_m5_executant_apres_sur_le_meme_volume(montee: Montee):
    m, b = montee, montee.banc
    b.image_executant = m.images["executant_apres"]
    b.demarrer_executant(volume=m.volumes["executant"])
    m.conteneurs["executant"].append(b.executant)
    journal = docker("logs", b.executant, verifier=False)
    journal_executant = journal.stdout + journal.stderr

    def en_ligne():
        code, vue = b.api("GET", "/v1/poste")
        executant = (vue or {}).get("executant") if code == 200 else None
        return executant if executant and "poste-claude" in (executant.get("voies_disponibles") or []) else None

    vue = attendre(en_ligne, 180, f"exécutant après jamais en ligne avec la voie poste-claude ({b.fin_journal()})")
    lu = m.releve(executant=True)
    ecarts = m.ecarts(lu)
    m.resultat["executant"] = ("prêt, enrôlé, en ligne ; jeton, empreinte et références égaux" if not ecarts
                               else f"écarts : {sorted(ecarts)}")
    m.ecrire_resultat()
    afficher("Montée 5 — exécutant APRÈS sur le volume d'avant", _json({
        "journal": [l for l in journal_executant.splitlines() if "[acp]" in l][:20],
        "vue": {k: vue.get(k) for k in ("plateforme", "version", "voies_disponibles", "isolement")},
        "lectures_face_a_la_reference": ecarts or "égales"}))
    assert "[acp] volume prêt" in journal_executant and "non enrôlé" not in journal_executant
    assert ecarts == {}, ecarts


# =========================================================================== 6. le travail reprend


def test_m6_le_travail_reprend(montee: Montee):
    m, b = montee, montee.banc
    code, repondue = b.api("POST", f"/v1/questions/{m.question_b['id']}/reponse", {"reponse": "Oui, garde-la."})
    assert code == 200 and repondue["carte_debloquee"] is True, repondue
    try:
        b.attendre_statut(m.projets["B"]["tableau"], m.cartes["B"], "done", delai=420)
    except AssertionError:
        # Sans --resume, le faux Claude repose la question (phase « premiere ») : la carte ne finit jamais. Dit.
        afficher("Montée 6 — B non terminée : appels du faux Claude", _json(
            [{"scenario": a.get("scenario"), "phase": a.get("phase"), "argv": a.get("argv")} for a in b.faux()]))
        raise
    m.projets["E"] = b.lancer_projet("Montée — E", "simple")
    m.cartes["E"] = b.carte_exploration(m.projets["E"]["tableau"])["id"]
    b.attendre_statut(m.projets["E"]["tableau"], m.cartes["E"], "done", delai=300)
    appels_b = [f for f in b.faux() if f.get("scenario") == "question"]
    sujets = {x: b.depot_nu("log", "--format=%s", f"hermes/{m.cartes[x]}").splitlines() for x in "BE"}
    explorations = {x: len([s for s in sujets[x] if s.startswith(f"exploration({m.cartes[x]}):")]) for x in "BE"}
    with a_chaud([b.executant]):
        fichiers_executant = comparer_manifestes(m.avant["executant"]["manifeste"],
                                                 manifeste(m.outils, m.volumes["executant"]))
    afficher("Montée 6 — le travail reprend", _json({
        "appels_du_faux_claude_pour_B": [{"phase": a.get("phase"), "argv": a.get("argv")} for a in appels_b],
        "sujets": sujets, "commits_d_exploration": explorations, "statuts": m.statuts(),
        "fichiers_du_volume_de_l_executant_changes": len(fichiers_executant)}))
    assert [a.get("phase") for a in appels_b] == ["reprise"], appels_b
    argv = appels_b[0]["argv"]
    assert "--resume" in argv and argv[argv.index("--resume") + 1].startswith("factice-question-"), argv
    assert explorations == {"B": 1, "E": 1}, (explorations, sujets)
    afficher("Montée 6 — aucun jeton, aucun push", _json(m.aucun_jeton_ni_push()))
    m.resultat["travail_repris"] = ("oui : B reprise par l'exécutant après (--resume de la session ouverte avant), "
                                    "terminée ; E terminée ; un commit d'exploration chacune ; aucun jeton, aucun push")
    m.ecrire_resultat()
