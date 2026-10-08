"""Restauration LOCALE des trois volumes nommés (étape P9, cahier P9 § 3.3 et § 3.4), pilotée depuis l'hôte.

Banc partagé (banc.py : Hermes de test, VRAI exécutant en cible « factice », faux IdP, faux ntfy, dépôt git factice,
bord TLS) + vraie identité (Authelia) sur son volume. Trois volumes : ``hermes`` (/opt/data), ``executant``
(/donnees), ``identite`` (/config).

R1 — trois volumes restaurés au MÊME instant :
1. peuplement à T : projet A terminé, projet B arrêté sur une question ouverte, ``reclamation_ttl_s`` abaissé à 300 s
   AVANT la réclamation de C (l'échéance d'une réclamation est écrite en base), projet C dont la carte est EN MAIN de
   l'exécutant (scénario « attente »), routage validé, réglage changé, notification envoyée, discussion, bilan
   quotidien (tâche cron et script de root), deux premiers facteurs sur l'identité (un réussi, un refusé) ;
2. référence à T (champs stables), puis instantané À CHAUD (``docker pause`` des trois services) : manifestes,
   empreintes SQLite, archives ;
3. marqueurs APRÈS T (réponse à B, projet D, réglage remis, nouveau premier facteur, C libérée et terminée), puis
   instantané FROID T+1 (arrêt propre exécutant, Hermes, identité) ;
4. restauration de T dans trois volumes NEUFS : couche 1 (manifestes égaux, entrée par entrée), couche 2
   (``integrity_check`` = ok, empreintes logiques égales) ;
5. redémarrage, mêmes images et variables : gardes acceptées, identité « générés : aucun », exécutant prêt et enrôlé ;
   couche 3 : lectures égales à la référence de T, marqueurs postérieurs ABSENTS ;
6. le travail REPREND : B → terminée, C reprise → terminée avec UN commit d'exploration, nouveau projet E → terminé.
   Mécanismes RELEVÉS et imprimés, jamais supposés : compteur ``oom`` de la carte C (un volume pris à chaud se relit
   comme un arrêt brutal), réclamation restaurée encore valide ou rendue (échéance passée), échecs comptés.
   Comme une restauration réelle a lieu des heures après la sauvegarde, le redémarrage attend que l'échéance de la
   réclamation restaurée de C soit PASSÉE (au plus T + 300 s) : c'est le chemin de la sauvegarde quotidienne.
   Notification témoin : le faux ntfy est coupé du réseau juste avant T et une notification est enfilée ; elle est EN
   ATTENTE à T, délivrée après T (faux ntfy rebranché), puis on MESURE si l'émetteur restauré la renvoie.

R2 — volumes restaurés à des instants DIFFÉRENTS (les sauvegardes de Railway ne sont pas synchronisées) :
- R2a : Hermes ← T+1, exécutant ← T (exécutant plus ancien) ;
- R2b : Hermes ← T, exécutant ← T+1 (exécutant plus récent) : comportement non connu, MESURÉ ; seuls les invariants
  sont affirmés (aucun push, aucun secret, cartes finies ou en revue, historique des branches sans perte). La règle
  d'ordre de la procédure (décision P9-6) suit cette mesure.

Partout : aucun jeton dans les journaux, aucun push sur le dépôt factice. Aucun contenu de fichier ni jeton n'est
imprimé : seulement des décomptes, des empreintes courtes, des identifiants et des statuts.

Ce que ce test local NE prouve PAS (cahier § 3.8, dit) : l'atomicité réelle d'une sauvegarde Railway entre les
fichiers d'un même volume (``docker pause`` en est seulement l'analogue local le plus proche) ; la mise en attente du
``Restore`` et le renommage des volumes ; le comportement des jetons réels (openai-codex de Hermes, Codex de
l'exécutant, Claude, GitHub : ici des jetons factices) ; une vraie passkey de téléphone ; le vrai bord de Railway.
C'est l'objet de la répétition de restauration sur Railway (docs/refonte/railway.md, § 4.11 bis).
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

import pytest

from banc import JETON_CLAUDE, JOURNAL_DEPOT, PYTHON, POSTE_SIMULE, SECRET_FACTICE, Banc, attendre
from conftest import afficher, docker
from pile_identite import MOT_DE_PASSE, UTILISATEUR
from volumes import Archives, a_chaud, bases, comparer_bases, comparer_manifestes, manifeste, resume_bases, \
    resume_manifeste

pytestmark = pytest.mark.restauration

LIBERER = "/var/tmp/acp-factice/liberer"
TTL_RESTAURATION_S = 300
TEMOIN_CLE = "restauration:temoin-T"
TEMOIN_TEXTE = "Témoin de la restauration (P9) : notification en attente à l'instant T."
TACHE_BILAN = {"name": "Bilan ACP", "schedule": "0 8 * * *", "prompt": "", "no_agent": True,
               "script": "acp-bilan.py", "deliver": "local"}
SEUIL_A_T, SEUIL_APRES_T = 85, 90  # réglage « seuil_quota_pct » : changé avant T, remis après T
VOLUMES = ("hermes", "executant", "identite")


def _json(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False, indent=1, default=str)


class Scene:
    """État partagé des étapes (le test est une suite ordonnée, comme le bout en bout de P6)."""

    def __init__(self, banc: Banc, archives: Archives, image_tests: str, image_identite: str, empreinte: str) -> None:
        self.banc, self.archives = banc, archives
        self.image_tests, self.image_identite, self.empreinte = image_tests, image_identite, empreinte
        self.projets: Dict[str, Dict[str, Any]] = {}
        self.cartes: Dict[str, str] = {}
        self.instants: Dict[str, Dict[str, Any]] = {}
        self.reference: Dict[str, Any] = {}
        self.remote_avant = ""
        self.question_b: Dict[str, Any] = {}
        self.tache_bilan = ""
        self.session_discussion = ""
        self.refs_t1: Dict[str, str] = {}
        self.sujets_c_t1: List[str] = []
        self.restaures: Dict[str, str] = {}
        self.statuts_t: Dict[str, str] = {}
        self.redemarrage_r1 = 0.0
        self.temoin_avant_restauration = 0

    # ------------------------------------------------------------------ lectures
    def requete(self, methode: str, chemin: str, corps: Optional[Any] = None):
        """Route native du tableau de bord (``/api/…``) avec la session du propriétaire (faux IdP du banc)."""
        b = self.banc
        commande = ["curl", "-s", "-o", "/tmp/acp-reponse-restauration", "-w", "%{http_code}", "-X", methode,
                    f"http://127.0.0.1:9119{chemin}", "-H", f"Authorization: Bearer {b.jeton_oidc()}"]
        if corps is not None:
            commande += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(corps, ensure_ascii=False)]
        code = int(b.hermes.executer(commande, verifier=True, delai=240).stdout.strip())
        contenu = b.hermes.executer(["cat", "/tmp/acp-reponse-restauration"], verifier=True).stdout
        try:
            return code, json.loads(contenu)
        except ValueError:
            return code, contenu

    def sql(self, requete: str, *parametres: str) -> List[Dict[str, Any]]:
        """Lecture SEULE de la base du greffon (lignes en dictionnaires)."""
        code = ("import json, sqlite3, sys\n"
                "c = sqlite3.connect('file:/opt/data/plugin-data/acp-poste/data.db?mode=ro', uri=True)\n"
                "c.row_factory = sqlite3.Row\n"
                "print(json.dumps([dict(l) for l in c.execute(sys.argv[1], sys.argv[2:])], ensure_ascii=False, "
                "default=str))\n")
        sortie = self.banc.hermes.executer([PYTHON, "-c", code, requete, *parametres], utilisateur="hermes",
                                           verifier=True)
        return json.loads(sortie.stdout)

    def reglage(self, cle: str) -> Any:
        lignes = self.sql("SELECT valeur FROM reglages WHERE cle = ?", cle)
        return json.loads(lignes[0]["valeur"]) if lignes else None

    def poser_reglage(self, cle: str, valeur: Any) -> None:
        sortie = self.banc.hermes.executer([PYTHON, POSTE_SIMULE, "reglage", cle, json.dumps(valeur)],
                                           utilisateur="hermes", delai=120)
        assert sortie.returncode == 0, sortie.stderr[-2000:]

    def tache_kanban(self, tableau: str, carte: str) -> Dict[str, Any]:
        """Statut, réclamation, échéance et échecs consécutifs d'une carte (base kanban de Hermes, lecture)."""
        code = ("import json, sys, time\n"
                "sys.path.insert(0, '/opt/hermes/plugins/acp-poste')\n"
                "from noyau import kanban_adapter as ka\n"
                "with ka.connexion(sys.argv[1]) as kc:\n"
                "    l = kc.execute('SELECT status, claim_lock, claim_expires, consecutive_failures, "
                "last_failure_error FROM tasks WHERE id = ?', (sys.argv[2],)).fetchone()\n"
                "print(json.dumps({'statut': l[0], 'reclamee': l[1] is not None, 'echeance_dans_s': "
                "(l[2] - int(time.time())) if l[2] else None, 'echecs': l[3], "
                "'dernier_echec': (l[4] or '')[:160]}))\n")
        sortie = self.banc.hermes.executer([PYTHON, "-c", code, tableau, carte], utilisateur="hermes", verifier=True)
        return json.loads(sortie.stdout)

    def historique(self, lettre: str) -> Dict[str, Any]:
        """Chemin suivi par la carte dans le kanban de Hermes, RELEVÉ : tentatives (``task_runs`` : identifiant, statut,
        issue), genres des événements (``task_events``, dans l'ordre), statut et échecs consécutifs. Lecture seule."""
        code = ("import json, sys\n"
                "sys.path.insert(0, '/opt/hermes/plugins/acp-poste')\n"
                "from noyau import kanban_adapter as ka\n"
                "with ka.connexion(sys.argv[1]) as kc:\n"
                "    runs = [[l[0], l[1], l[2]] for l in kc.execute('SELECT id, status, outcome FROM task_runs "
                "WHERE task_id = ? ORDER BY id', (sys.argv[2],))]\n"
                "    evts = [l[0] for l in kc.execute('SELECT kind FROM task_events WHERE task_id = ? ORDER BY id', "
                "(sys.argv[2],))]\n"
                "    t = kc.execute('SELECT status, consecutive_failures FROM tasks WHERE id = ?', "
                "(sys.argv[2],)).fetchone()\n"
                "print(json.dumps({'tentatives': runs, 'evenements': evts, 'statut': t[0], 'echecs': t[1]}))\n")
        sortie = self.banc.hermes.executer([PYTHON, "-c", code, self.projets[lettre]["tableau"], self.cartes[lettre]],
                                           utilisateur="hermes", verifier=True)
        return json.loads(sortie.stdout)

    def envois(self, lettre: str, depuis: float = 0.0) -> List[Dict[str, Any]]:
        """Issues de l'exécutant ACCEPTÉES par Hermes pour cette carte (table ``envois`` du greffon, réponses 2xx
        gardées : route, statut, état rendu), reçues depuis ``depuis`` (secondes depuis l'époque)."""
        lignes = self.sql("SELECT route, statut, reponse, recu_le FROM envois WHERE carte = ? AND recu_le >= ? "
                          "ORDER BY recu_le, rowid", self.cartes[lettre], str(int(depuis)))
        resultat = []
        for l in lignes:
            try:
                reponse = json.loads(l["reponse"])
            except ValueError:
                reponse = {}
            resultat.append({"route": l["route"], "statut": l["statut"],
                             "etat": reponse.get("etat") if isinstance(reponse, dict) else None,
                             "recu_apres_s": int(l["recu_le"] - depuis) if depuis else None})
        return resultat

    def appels_agent(self) -> Dict[str, List[str]]:
        """Invocations du faux Claude dans le conteneur COURANT de l'exécutant (son journal vit hors du volume), par
        scénario : phases dans l'ordre. Chaque projet du test a son propre scénario."""
        appels: Dict[str, List[str]] = {}
        for f in self.banc.faux():
            if f.get("scenario") and f.get("phase"):
                appels.setdefault(str(f["scenario"]), []).append(str(f["phase"]))
        return appels

    def temoins_recus(self) -> int:
        return sum(1 for n in self.banc.notifications() if n.get("corps") == TEMOIN_TEXTE)

    def notification_temoin(self) -> Dict[str, Any]:
        lignes = self.sql("SELECT etat, tentatives FROM notifications WHERE cle = ?", TEMOIN_CLE)
        return lignes[0] if lignes else {}

    def couper_ntfy(self) -> None:
        """Faux ntfy retiré du réseau du banc (son journal reste lisible par ``docker exec``) : tout envoi échoue."""
        docker("network", "disconnect", self.banc.reseau, self.banc.ntfy)

    def rebrancher_ntfy(self) -> None:
        """Faux ntfy rendu au réseau sous son alias (sans effet s'il y est déjà : étape précédente en échec)."""
        relie = docker("inspect", "-f", "{{json .NetworkSettings.Networks}}", self.banc.ntfy).stdout
        if self.banc.reseau not in relie:
            docker("network", "connect", "--alias", "ntfy.acp.test", self.banc.reseau, self.banc.ntfy)

    def enfiler_temoin(self) -> None:
        """Notification témoin enfilée par la fonction du greffon (genre « test »), comme le ferait l'émetteur."""
        code = ("import sys\n"
                "sys.path.insert(0, '/opt/hermes/plugins/acp-poste')\n"
                "from noyau import base, notifications\n"
                "with base.connexion() as conn:\n"
                "    print(notifications.enfiler(conn, cle=sys.argv[1], genre='test', texte_notif=sys.argv[2]))\n")
        sortie = self.banc.hermes.executer([PYTHON, "-c", code, TEMOIN_CLE, TEMOIN_TEXTE], utilisateur="hermes",
                                           verifier=True)
        assert sortie.stdout.strip() == "True", sortie.stdout

    def statuts_poste(self, lettres: str = "ABC") -> Dict[str, str]:
        """Statut des cartes d'exploration (voie poste-claude) des projets donnés, par lettre de projet. Seulement des
        projets connus de ce Hermes : lire le tableau d'un projet absent en créerait la base."""
        resultat = {}
        for lettre in lettres:
            cartes = {c["id"]: c for c in self.banc.cartes(self.projets[lettre]["tableau"])}
            carte = self.cartes.get(lettre)
            resultat[lettre] = cartes[carte]["statut"] if carte in cartes else "absente"
        return resultat

    def contient(self, ancetre: str, ref: str) -> bool:
        resultat = docker("exec", self.banc.executant, "git", "--git-dir=/donnees/depots/jetable.git", "merge-base",
                          "--is-ancestor", ancetre, ref, verifier=False)
        return resultat.returncode == 0

    def refs_executant(self) -> Dict[str, str]:
        sortie = self.banc.depot_nu("for-each-ref", "--format=%(refname) %(objectname:short=12)")
        return dict(l.split(" ", 1) for l in sortie.splitlines() if l.strip())

    def sujets(self, lettre: str) -> List[str]:
        return self.banc.depot_nu("log", "--format=%s", f"hermes/{self.cartes[lettre]}").splitlines()

    def en_main(self) -> Dict[str, Any]:
        brut = docker("exec", self.banc.executant, "sh", "-c", "cat /donnees/acp/etat/carte.json 2>/dev/null",
                      verifier=False).stdout.strip()
        etat = json.loads(brut) if brut else {}
        return {k: etat.get(k) for k in ("carte", "etape")}

    def oom(self, lettre: str) -> Any:
        brut = docker("exec", self.banc.executant, "sh", "-c",
                      f"cat /donnees/acp/etat/sessions/{self.cartes[lettre]}.json 2>/dev/null", verifier=False).stdout
        return (json.loads(brut) if brut.strip() else {}).get("oom", 0)

    def bord_identite(self) -> str:
        assert self.banc.bord_identite, "identité non lancée"
        return self.banc.bord_identite

    def identite_publique(self) -> Dict[str, Any]:
        """JWKS (kid, empreinte courte du module) et document de découverte, lus par le bord de l'identité."""
        lus = {}
        for cle, chemin in (("jwks", "/jwks.json"), ("decouverte", "/.well-known/openid-configuration")):
            sortie = docker("exec", self.bord_identite(), "curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                            f"https://identite-acp.test{chemin}").stdout
            lus[cle] = json.loads(sortie)
        cles = [{"kid": k["kid"], "n": hashlib.sha256(k["n"].encode()).hexdigest()[:16]} for k in lus["jwks"]["keys"]]
        decouverte = {k: lus["decouverte"].get(k) for k in ("issuer", "authorization_endpoint", "token_endpoint",
                                                              "jwks_uri")}
        return {"cles": cles, "decouverte": decouverte}

    def premier_facteur(self, mot_de_passe: str) -> Dict[str, Any]:
        sortie = docker("exec", self.bord_identite(), PYTHON, "/opt/acp-tests/outils/client_identite.py",
                        "autoriser", "--utilisateur", UTILISATEUR, "--mot-de-passe", mot_de_passe).stdout
        resultat = json.loads(sortie)
        return {"statut": resultat["premier_facteur"]["statut"],
                "corps": (resultat["premier_facteur"]["corps"] or {}).get("status")}

    def releve_reference(self) -> Dict[str, Any]:
        """Champs STABLES lus par les API (cahier § 3.3 point 3) ; jamais un contenu de fichier ni un jeton."""
        b = self.banc
        _code, projets = b.api("GET", "/v1/projets")
        _code, questions = b.api("GET", "/v1/questions")
        _code, poste = b.api("GET", "/v1/poste")
        _code, routage = b.api("GET", "/v1/routage")
        code_s, sessions = self.requete("GET", "/api/sessions?limit=100&archived=include")
        code_c, taches = self.requete("GET", "/api/cron/jobs")
        taches = taches if isinstance(taches, list) else (taches or {}).get("jobs", [])
        machine = (poste.get("machine") or {}).get("machine") or {}
        diagnostic = json.loads(b.acp_poste("diagnostic").stdout or "{}")
        return {
            "projets": {p["id"]: {"titre": p["titre"]} for p in projets["projets"]},
            "questions_ouvertes": sorted((q["id"], q["carte"], q["texte"]) for q in questions["questions"]),
            "machine": {k: machine.get(k) for k in ("id", "etat", "empreinte")},
            "routage_valide": {c: [(e["voie"], e["modele"], e["effort"]) for e in (v.get("entrees") or [])]
                               for c, v in (routage.get("classes") or {}).items() if v.get("etat") == "validee"},
            "reglages": {c: self.reglage(c) for c in ("seuil_quota_pct", "reclamation_ttl_s", "emetteur_intervalle_s")},
            "notifications": {f"{l['genre']}:{l['etat']}": l["n"] for l in self.sql(
                "SELECT genre, etat, COUNT(*) AS n FROM notifications GROUP BY genre, etat")},
            "sessions": {s["id"]: s.get("message_count") for s in (sessions or {}).get("sessions", [])}
            if code_s == 200 else f"code {code_s}",
            "taches_cron": sorted(t["id"] for t in taches) if code_c == 200 else f"code {code_c}",
            "jeton_executant": {"present": (diagnostic.get("jeton") or {}).get("present"),
                                "machine_id": (diagnostic.get("jeton") or {}).get("machine_id"),
                                "empreinte": (diagnostic.get("jeton") or {}).get("empreinte")},
            "refs": self.refs_executant(),
            "identite": self.identite_publique(),
        }

    def releve_volumes(self) -> Dict[str, Dict[str, Any]]:
        b = self.banc
        volumes = {"hermes": b.volume_hermes, "executant": b.volume_executant, "identite": b.volume_identite}
        return {role: {"manifeste": manifeste(self.image_tests, v), "bases": bases(self.image_tests, v)}
                for role, v in volumes.items()}

    def archiver(self, instant: str) -> Dict[str, Any]:
        b = self.banc
        volumes = {"hermes": b.volume_hermes, "executant": b.volume_executant, "identite": b.volume_identite}
        return {role: self.archives.instantane(v, f"{instant}-{role}") for role, v in volumes.items()}

    def restaurer(self, instants: Dict[str, str]) -> Dict[str, str]:
        """Volumes NEUFS garnis des archives demandées ({rôle: instant})."""
        return {role: self.archives.volume_restaure(f"{instant}-{role}", f"{role}-{instant}")
                for role, instant in instants.items()}

    def aucun_jeton_ni_push(self, etiquette: str) -> Dict[str, Any]:
        b = self.banc
        remote = b.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
        assert remote == self.remote_avant, f"{etiquette} : références du dépôt distant changées"
        requetes = [json.loads(l) for l in docker("exec", b.depot, "cat", JOURNAL_DEPOT).stdout.splitlines() if l]
        assert requetes and {r["methode"] for r in requetes} <= {"GET", "HEAD"}
        assert not any("receive-pack" in r["chemin"] for r in requetes)
        jeton_machine = b.executant_sh("cat /donnees/acp/secrets/jeton-machine").strip()
        assert jeton_machine.startswith("acpm_")
        executant = docker("logs", b.executant, verifier=False)
        textes = {"docker logs hermes": b.hermes.journaux(),
                  "docker logs executant": executant.stdout + executant.stderr,
                  "journal de l'exécutant": b.executant_sh("cat /donnees/acp/journal/* 2>/dev/null || true"),
                  "file de sortie": b.executant_sh("cat /donnees/acp/sortie/* /donnees/acp/sortie/refusees/* "
                                                   "2>/dev/null || true")}
        for nom, texte in textes.items():
            for valeur in (jeton_machine, JETON_CLAUDE, SECRET_FACTICE):
                assert valeur not in texte, f"{etiquette} : {nom}"
            assert "acpe_" not in texte, f"{etiquette} : {nom}"
        return {"requetes_depot": len(requetes), "tailles": {n: len(t) for n, t in textes.items()}}

    def carte_en_main_de(self, lettre: str, delai: float = 240) -> Dict[str, Any]:
        def en_agent():
            etat = self.en_main()
            return etat if etat.get("carte") == self.cartes[lettre] and etat.get("etape") == "agent" else None
        return attendre(en_agent, delai, f"carte {lettre} jamais en main à l'étape agent ({self.banc.fin_journal()})")


@pytest.fixture(scope="module")
def scene(ressources, image_tests, image_identite, empreinte_argon2):
    banc = Banc(ressources, image_tests)
    try:
        banc.monter()
        banc.construire_executant()
        banc.demarrer_executant()
        banc.lancer_identite(image_identite, empreinte_argon2)
        yield Scene(banc, Archives(ressources, image_tests), image_tests, image_identite, empreinte_argon2)
    finally:
        banc.nettoyer_image()


# =========================================================================== R1. peuplement et instantané à chaud T


def test_r1_peuplement_a_t(scene):
    b = scene.banc
    scene.remote_avant = b.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
    b.mettre_en_service()
    # Routage validé par le propriétaire (classe exploration, suggestion calculée sur le relevé de l'exécutant).
    _code, routage = b.api("GET", "/v1/routage")
    entrees = ((routage["classes"].get("exploration") or {}).get("suggestion") or {}).get("entrees") or [
        {"voie": "poste-claude", "modele": "opus", "effort": "low"}]
    code, valide = b.api("POST", "/v1/routage", {"releves": routage["releves"], "classes": {"exploration": entrees}})
    assert code == 200, valide
    # A : menée à son terme.
    scene.projets["A"] = b.lancer_projet("Restauration — A", "simple")
    scene.cartes["A"] = b.carte_exploration(scene.projets["A"]["tableau"])["id"]
    b.attendre_statut(scene.projets["A"]["tableau"], scene.cartes["A"], "done")
    # Échéance des réclamations abaissée AVANT la réclamation de C (elle est écrite en base à la réclamation).
    scene.poser_reglage("reclamation_ttl_s", TTL_RESTAURATION_S)
    # B : arrêtée sur une question ouverte.
    scene.projets["B"] = b.lancer_projet("Restauration — B", "question")
    scene.cartes["B"] = b.carte_exploration(scene.projets["B"]["tableau"])["id"]

    def question():
        code, liste = b.api("GET", "/v1/questions")
        return next((q for q in liste["questions"] if q["carte"] == scene.cartes["B"]), None) if code == 200 else None

    scene.question_b = attendre(question, 240, f"question de B jamais posée ({b.fin_journal()})")
    # C : carte EN MAIN de l'exécutant (scénario « attente »).
    scene.projets["C"] = b.lancer_projet("Restauration — C", "attente")
    scene.cartes["C"] = b.carte_exploration(scene.projets["C"]["tableau"])["id"]
    scene.carte_en_main_de("C")
    b.attendre_statut(scene.projets["C"]["tableau"], scene.cartes["C"], "running")
    scene.poser_reglage("seuil_quota_pct", SEUIL_A_T)
    # Notification envoyée (curseur de l'émetteur avancé) : la question de B part vers le faux ntfy.
    attendre(lambda: b.notifications(), 90, "aucune notification reçue par le faux ntfy")
    # Discussion : un tour complet par /api/ws (modèle factice).
    fichier = "/tmp/acp-ws-restauration.json"
    sortie = b.hermes.executer([PYTHON, "/opt/acp-tests/outils/client_ws.py", "prompt", b.jeton_oidc(), fichier,
                                "Discussion d'essai avant la restauration."], delai=420)
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    tour = json.loads(b.hermes.executer(["cat", fichier], verifier=True).stdout)
    assert (tour.get("fin") or {}).get("params", {}).get("type") == "message.complete", tour
    # Clé STOCKÉE de la session (celle de /api/sessions), pas l'identifiant de la connexion /api/ws.
    assert tour.get("cle"), tour.get("session_id")
    scene.session_discussion = tour["cle"]
    # Bilan quotidien de P7 : tâche cron native du propriétaire (script de root admis par son empreinte).
    code, tache = scene.requete("POST", "/api/cron/jobs", TACHE_BILAN)
    assert code == 200, tache
    scene.tache_bilan = tache["id"]
    # Identité : base, secrets et clé RS256 générés au premier démarrage ; deux premiers facteurs.
    reussi, refuse = scene.premier_facteur(MOT_DE_PASSE), scene.premier_facteur("mauvais-mot-de-passe-de-test")
    assert reussi["statut"] == 200 and refuse["statut"] != 200, (reussi, refuse)
    # Notification témoin EN ATTENTE à T : faux ntfy coupé du réseau, puis notification enfilée.
    scene.couper_ntfy()
    scene.enfiler_temoin()
    scene.reference = scene.releve_reference()
    scene.statuts_t = scene.statuts_poste()
    afficher("R1 — référence à T (champs stables)", _json({
        **{k: v for k, v in scene.reference.items() if k != "refs"}, "refs": len(scene.reference["refs"]),
        "statuts": scene.statuts_t, "en_main": scene.en_main(),
        "reclamation_C": scene.tache_kanban(scene.projets["C"]["tableau"], scene.cartes["C"]),
        "historique_C": scene.historique("C"), "notification_temoin": scene.notification_temoin(),
        "premiers_facteurs": {"reussi": reussi, "refuse": refuse}}))
    assert scene.notification_temoin().get("etat") == "en_attente"
    assert set(scene.reference["projets"]) == {scene.projets[x]["id"] for x in "ABC"}
    assert [q[1] for q in scene.reference["questions_ouvertes"]] == [scene.cartes["B"]]
    assert scene.reference["reglages"]["seuil_quota_pct"] == SEUIL_A_T
    assert scene.reference["jeton_executant"]["present"] is True
    assert scene.session_discussion in scene.reference["sessions"]
    assert scene.reference["taches_cron"] == [scene.tache_bilan]


def test_r1_instantane_a_chaud_t(scene):
    b = scene.banc
    debut = time.monotonic()
    with a_chaud([b.executant, b.hermes.nom, b.identite]):
        releves = scene.releve_volumes()
        archives = scene.archiver("T")
    scene.instants["T"] = dict(releves, quand=time.time(), archives=archives)
    afficher(f"R1 — instantané à chaud T (pause de {time.monotonic() - debut:.1f} s)", _json({
        role: {"manifeste": resume_manifeste(r["manifeste"]), "bases": resume_bases(r["bases"]),
               "archive": archives[role]} for role, r in releves.items()}))
    for role, r in releves.items():
        # L'exécutant garde son état en fichiers JSON et en dépôts git : aucune base n'y est exigée.
        assert role == "executant" or r["bases"]["bases"], f"aucune base SQLite relevée sur le volume {role}"
        for base, e in r["bases"]["bases"].items():
            assert e["integrite"] == "ok", (role, base, e["integrite"])
    assert "plugin-data/acp-poste/data.db" in releves["hermes"]["bases"]["bases"]
    assert "db.sqlite3" in releves["identite"]["bases"]["bases"]


def test_r1_marqueurs_apres_t_puis_instantane_froid(scene):
    b = scene.banc
    scene.rebrancher_ntfy()
    code, repondue = b.api("POST", f"/v1/questions/{scene.question_b['id']}/reponse", {"reponse": "Oui, garde-la."})
    assert code == 200 and repondue["carte_debloquee"] is True, repondue
    scene.projets["D"] = b.lancer_projet("Restauration — D", "simple")
    scene.cartes["D"] = b.carte_exploration(scene.projets["D"]["tableau"])["id"]
    scene.poser_reglage("seuil_quota_pct", SEUIL_APRES_T)
    assert scene.premier_facteur(MOT_DE_PASSE)["statut"] == 200
    b.executant_sh(f"touch {LIBERER}")
    for lettre in ("C", "B", "D"):
        b.attendre_statut(scene.projets[lettre]["tableau"], scene.cartes[lettre], "done", delai=300)
    scene.refs_t1 = scene.refs_executant()
    scene.sujets_c_t1 = scene.sujets("C")
    # Témoin : délivré APRÈS T (reprise de l'émetteur à 30 s × 2ⁿ), avant T+1. Mesuré, non exigé ici.
    try:
        attendre(lambda: scene.temoins_recus() > 0, 300, "notification témoin jamais délivrée après T")
    except AssertionError as exc:
        afficher("R1 — témoin non délivré avant T+1", str(exc))
    scene.temoin_avant_restauration = scene.temoins_recus()
    temoin_t1 = scene.notification_temoin()
    arrets = b.arreter()
    releves = scene.releve_volumes()
    archives = scene.archiver("T1")
    scene.instants["T1"] = dict(releves, quand=time.time(), archives=archives)
    afficher("R1 — marqueurs après T et instantané froid T+1", _json({
        "arrets": arrets, "statuts": {k: "done" for k in "BCD"}, "sujets_C": scene.sujets_c_t1,
        "temoin": {"recu_par_le_faux_ntfy": scene.temoin_avant_restauration, "etat_a_t1": temoin_t1},
        "refs": len(scene.refs_t1), "codes_de_sortie_info": "relevés, non affirmés",
        "volumes": {role: {"manifeste": resume_manifeste(r["manifeste"]), "archive": archives[role]}
                    for role, r in releves.items()}}))
    for role, r in releves.items():
        for base, e in r["bases"]["bases"].items():
            assert e["integrite"] == "ok", (role, base, e["integrite"])


# =========================================================================== R1. restauration de T, couches 1 à 3


def test_r1_restauration_couches_1_et_2(scene):
    scene.restaures = scene.restaurer({role: "T" for role in VOLUMES})
    t = scene.instants["T"]
    resultats = {}
    for role, volume in scene.restaures.items():
        m, bs = manifeste(scene.image_tests, volume), bases(scene.image_tests, volume)
        resultats[role] = {"manifeste": resume_manifeste(m),
                           "ecarts_octets": comparer_manifestes(t[role]["manifeste"], m),
                           "bases": {base: e["integrite"] for base, e in bs["bases"].items()},
                           "ecarts_sqlite": comparer_bases(t[role]["bases"], bs), "releve": {"bases": bs}}
    # Tout est relevé et imprimé AVANT d'affirmer : un écart d'une couche ne masque jamais celui de l'autre.
    afficher("R1 — couches 1 (octets) et 2 (SQLite) des volumes restaurés à T", _json(
        {role: {k: (v[:20] if k.startswith("ecarts") else v) for k, v in r.items() if k != "releve"}
         for role, r in resultats.items()}))

    # Marqueurs postérieurs absents dès la couche 2 : premiers facteurs de l'identité (journal d'Authelia) et
    # projets du greffon comptés à T, à T+1 et dans le volume restauré.
    def lignes(releves, role, base, table):
        return ((releves[role]["bases"]["bases"].get(base) or {}).get("tables") or {}).get(table, {}).get("lignes")

    restaures = {role: r["releve"] for role, r in resultats.items()}
    marqueurs = {}
    for role, base, table in (("identite", "db.sqlite3", "authentication_logs"),
                              ("hermes", "plugin-data/acp-poste/data.db", "projets")):
        marqueurs[f"{table} ({role})"] = {"T": lignes(t, role, base, table),
                                          "T+1": lignes(scene.instants["T1"], role, base, table),
                                          "restauré": lignes(restaures, role, base, table)}
    afficher("R1 — lignes comptées à T, à T+1 et dans les volumes restaurés", _json(marqueurs))
    for role, r in resultats.items():
        assert r["ecarts_octets"] == [], (role, "couche 1", r["ecarts_octets"][:20], "couche 2",
                                          r["ecarts_sqlite"][:20])
        assert r["ecarts_sqlite"] == [], (role, "couche 2", r["ecarts_sqlite"][:20])
        assert all(i == "ok" for i in r["bases"].values()), (role, r["bases"])
    for nom, n in marqueurs.items():
        assert n["T"] is not None and n["T+1"] is not None and n["T+1"] > n["T"] == n["restauré"], (nom, n)


def test_r1_redemarrage_et_couche_3(scene):
    b = scene.banc
    # Cas réel d'une sauvegarde quotidienne : la restauration a lieu après l'échéance de la réclamation restaurée de C
    # (écrite en base au plus T + 300 s). Le redémarrage attend donc cette échéance (le premier run, sans cette
    # attente, a relevé l'autre chemin : réclamation encore valide, rendue par l'exécutant lui-même).
    attente = scene.instants["T"]["quand"] + TTL_RESTAURATION_S + 20 - time.time()
    afficher("R1 — attente de l'échéance de la réclamation restaurée de C", f"{max(attente, 0):.0f} s")
    if attente > 0:
        time.sleep(attente)
    scene.redemarrage_r1 = time.time()
    b.relancer(scene.restaures["hermes"], scene.restaures["executant"], volume_identite=scene.restaures["identite"],
               image_identite=scene.image_identite, empreinte=scene.empreinte)
    journal_hermes = b.hermes.journaux()
    journal_identite = docker("logs", b.identite, verifier=False)
    journal_identite = journal_identite.stdout + journal_identite.stderr
    journal_executant = docker("logs", b.executant, verifier=False)
    journal_executant = journal_executant.stdout + journal_executant.stderr
    afficher("R1 — redémarrage sur les volumes restaurés (extraits)", "\n".join(
        [l for l in journal_hermes.splitlines() if "[acp]" in l or "05-acp" in l][:40]
        + [l for l in journal_identite.splitlines() if "[acp-identite]" in l]
        + [l for l in journal_executant.splitlines() if "[acp]" in l][:20]))
    assert "cont-init: info: /etc/cont-init.d/05-acp exited 0" in journal_hermes
    assert "[acp] REFUS" not in journal_hermes
    assert "(hors acp-bilan.py, admis par son empreinte)" in journal_hermes
    assert "secrets de /config/secrets : générés : aucun ;" in journal_identite
    assert "[acp] volume prêt" in journal_executant and "non enrôlé" not in journal_executant
    # Couche 3 : AVANT toute reprise du travail (C attend son drapeau, B sa réponse).
    lu = scene.releve_reference()
    ref = scene.reference
    # Notifications : MESURÉES, non affirmées (l'émetteur restauré peut renvoyer ce qui partait à T) ; sessions :
    # comparées à part (Hermes peut en ouvrir de nouvelles pour ses propres cartes).
    ecarts = {k: {"T": ref[k], "restauré": lu[k]} for k in ref
              if k not in ("sessions", "notifications") and lu[k] != ref[k]}
    sessions_perdues = sorted(set(ref["sessions"]) - set(lu["sessions"]) if isinstance(lu["sessions"], dict) else [])
    afficher("R1 — couche 3 : lectures après redémarrage face à la référence de T", _json({
        "ecarts": ecarts, "sessions_perdues": sessions_perdues,
        "sessions_nouvelles": sorted(set(lu["sessions"]) - set(ref["sessions"])) if isinstance(lu["sessions"], dict)
        else lu["sessions"],
        "notifications": {"T": ref["notifications"], "restauré": lu["notifications"]},
        "statuts": {"T": scene.statuts_t, "restauré": scene.statuts_poste()}, "en_main": scene.en_main(),
        "reclamation_C": scene.tache_kanban(scene.projets["C"]["tableau"], scene.cartes["C"]),
        "historique_C": scene.historique("C"), "envois_C_depuis_redemarrage": scene.envois("C", scene.redemarrage_r1),
        "oom_C": scene.oom("C")}))
    assert ecarts == {}, ecarts
    assert sessions_perdues == [] and lu["sessions"][scene.session_discussion] == ref["sessions"][
        scene.session_discussion]
    assert scene.projets["D"]["id"] not in lu["projets"]
    assert lu["reglages"]["seuil_quota_pct"] == SEUIL_A_T
    # A terminée et B arrêtée sur sa question (statut « scheduled » de Hermes) : comme à T. C : mesurée ci-dessus.
    statuts = scene.statuts_poste()
    assert {k: statuts[k] for k in "AB"} == {k: scene.statuts_t[k] for k in "AB"}, (scene.statuts_t, statuts)


def test_r1_le_travail_reprend(scene):
    b = scene.banc
    # Notifications : le faux ntfy n'est PAS restauré ; ce que l'émetteur restauré renvoie est relevé, non affirmé.
    recues_avant = len(b.notifications())
    # B : la question restaurée est de nouveau ouverte ; la réponse débloque la carte, le fil reprend.
    code, repondue = b.api("POST", f"/v1/questions/{scene.question_b['id']}/reponse", {"reponse": "Oui, garde-la."})
    assert code == 200 and repondue["carte_debloquee"] is True, repondue
    # C : un volume d'exécutant pris à chaud se relit comme un arrêt brutal (compteur oom) ; relevé, puis reprise.
    mecanismes = {"oom_C": scene.oom("C"), "reclamation_C": scene.tache_kanban(scene.projets["C"]["tableau"],
                                                                               scene.cartes["C"]),
                  "refusees": b.executant_sh("ls /donnees/acp/sortie/refusees 2>/dev/null | wc -l").strip()}
    b.executant_sh(f"touch {LIBERER}")
    for lettre in ("B", "C"):
        b.attendre_statut(scene.projets[lettre]["tableau"], scene.cartes[lettre], "done", delai=420)
    scene.projets["E"] = b.lancer_projet("Restauration — E (R1)", "simple")
    scene.cartes["E"] = b.carte_exploration(scene.projets["E"]["tableau"])["id"]
    b.attendre_statut(scene.projets["E"]["tableau"], scene.cartes["E"], "done", delai=300)
    sujets_c = scene.sujets("C")
    explorations = [s for s in sujets_c if s.startswith(f"exploration({scene.cartes['C']}):")]
    # Témoin : l'émetteur restauré le renvoie-t-il ? (il était en attente à T ; le faux ntfy, non restauré, l'a
    # déjà reçu après T). Délai : la reprise de l'émetteur restauré est échue depuis longtemps ; 60 s suffisent.
    try:
        attendre(lambda: scene.temoins_recus() > scene.temoin_avant_restauration, 60, "témoin non renvoyé")
    except AssertionError:
        pass
    mecanismes.update({"apres": scene.tache_kanban(scene.projets["C"]["tableau"], scene.cartes["C"]),
                       "historique_C": scene.historique("C"),
                       "envois_C_depuis_redemarrage": scene.envois("C", scene.redemarrage_r1),
                       "sujets_C": sujets_c, "notifications_recues_apres_redemarrage":
                       len(b.notifications()) - recues_avant,
                       "temoin": {"recu_avant_restauration": scene.temoin_avant_restauration,
                                  "recu_au_total": scene.temoins_recus(),
                                  "etat_apres_redemarrage": scene.notification_temoin()},
                       "appels_agent_depuis_redemarrage": scene.appels_agent()})
    afficher("R1 — le travail reprend : mécanismes relevés", _json(mecanismes))
    assert len(explorations) == 1, sujets_c
    afficher("R1 — aucun jeton, aucun push", _json(scene.aucun_jeton_ni_push("R1")))


# =========================================================================== R2. instants différents


def _r2(scene, instants: Dict[str, str], titre: str) -> Dict[str, Any]:
    b = scene.banc
    b.arreter()
    volumes = scene.restaurer(instants)
    debut = time.time()
    b.relancer(volumes["hermes"], volumes["executant"])
    b.executant_sh(f"touch {LIBERER}")  # le drapeau vit hors du volume : toute attente se libère tout de suite
    return {"titre": titre, "volumes": volumes, "debut": debut}


def _journal_executant(scene, contenant: str, lignes: int = 300) -> List[List[Any]]:
    """Événements du journal local de l'exécutant qui citent ``contenant`` (une carte) : instant, événement, message
    (aucun jeton : le même journal est contrôlé par aucun_jeton_ni_push)."""
    retenus: List[List[Any]] = []
    for ligne in scene.banc.acp_poste("journal", "--lignes", str(lignes)).stdout.splitlines():
        if contenant not in ligne:
            continue
        try:
            e = json.loads(ligne)
            retenus.append([e.get("quand"), e.get("evenement"), str(e.get("message"))[:200]])
        except ValueError:
            retenus.append([ligne[:200]])
    return retenus[-15:]


def _cartes_finies(scene, lettres, delai: float = 420) -> Dict[str, str]:
    b = scene.banc
    fins = {}
    for lettre in lettres:
        fins[lettre] = b.attendre_statut(scene.projets[lettre]["tableau"], scene.cartes[lettre], ("done", "review"),
                                         delai=delai)
    return fins


def test_r2a_executant_plus_ancien_que_hermes(scene):
    """Hermes ← T+1 (C terminée), exécutant ← T (il croit tenir C à l'étape agent)."""
    b = scene.banc
    r2 = _r2(scene, {"hermes": "T1", "executant": "T"}, "R2a")

    # Au démarrage, l'exécutant restauré croit tenir C (étape agent) : il envoie reprendre(redemarrage). On attend que
    # Hermes l'ait reçu (table envois) et que l'exécutant ait lâché C ; l'issue est RELEVÉE (le premier run a mesuré
    # « deja_libre », réponse 2xx, et non un 409 reclamation_perdue rangé dans sortie/refusees).
    def lachee():
        return scene.en_main().get("carte") != scene.cartes["C"] and scene.envois("C", r2["debut"])

    try:
        attendre(lachee, 120, "l'exécutant restauré tient encore C, ou Hermes n'a reçu aucune issue de C")
    except AssertionError as exc:
        afficher("R2a — C non lâchée en 120 s", str(exc))
    refusees = b.executant_sh("ls /donnees/acp/sortie/refusees 2>/dev/null || true").split()
    scene.projets["E2a"] = b.lancer_projet("Restauration — E (R2a)", "simple")
    scene.cartes["E2a"] = b.carte_exploration(scene.projets["E2a"]["tableau"])["id"]
    b.attendre_statut(scene.projets["E2a"]["tableau"], scene.cartes["E2a"], "done", delai=300)
    mesure = {"envois_C_depuis_redemarrage": scene.envois("C", r2["debut"]), "sortie_refusees": refusees,
              "oom_C": scene.oom("C"), "en_main": scene.en_main(),
              "statut_C_chez_hermes": scene.tache_kanban(scene.projets["C"]["tableau"], scene.cartes["C"]),
              "historique_C": scene.historique("C"), "appels_agent_depuis_redemarrage": scene.appels_agent(),
              "branche_C_gardee": f"refs/heads/hermes/{scene.cartes['C']}" in scene.refs_executant(),
              "worktrees": b.executant_sh("ls /donnees/espaces/jetable 2>/dev/null || true").split(),
              "journal_executant_C": _journal_executant(scene, scene.cartes["C"])}
    afficher("R2a — exécutant plus ancien que Hermes : mesure", _json(mesure))
    assert mesure["statut_C_chez_hermes"]["statut"] == "done"
    assert mesure["branche_C_gardee"], "branche de C perdue"
    assert mesure["en_main"].get("carte") != scene.cartes["C"] or mesure["en_main"].get("etape") in (
        "arretee", "rendue"), mesure["en_main"]
    afficher("R2a — aucun jeton, aucun push", _json(scene.aucun_jeton_ni_push("R2a")))


def test_r2b_executant_plus_recent_que_hermes(scene):
    """Hermes ← T (C en main, B en question), exécutant ← T+1 (rien en main, C et B terminées de son côté)."""
    b = scene.banc
    r2 = _r2(scene, {"hermes": "T", "executant": "T1"}, "R2b")
    reclamation_au_redemarrage = scene.tache_kanban(scene.projets["C"]["tableau"], scene.cartes["C"])
    code, repondue = b.api("POST", f"/v1/questions/{scene.question_b['id']}/reponse", {"reponse": "Oui, garde-la."})
    assert code == 200, repondue
    fins = _cartes_finies(scene, ("C", "B"), delai=600)
    scene.projets["E2b"] = b.lancer_projet("Restauration — E (R2b)", "simple")
    scene.cartes["E2b"] = b.carte_exploration(scene.projets["E2b"]["tableau"])["id"]
    b.attendre_statut(scene.projets["E2b"]["tableau"], scene.cartes["E2b"], "done", delai=300)
    refs = scene.refs_executant()
    sujets_c, sujets_b = scene.sujets("C"), scene.sujets("B")
    appels = scene.appels_agent()
    mesure = {"reclamation_C_au_redemarrage": reclamation_au_redemarrage, "fins": fins,
              "apres": {x: scene.tache_kanban(scene.projets[x]["tableau"], scene.cartes[x]) for x in ("B", "C")},
              "historique": {x: scene.historique(x) for x in ("B", "C")},
              "envois_depuis_redemarrage": {x: scene.envois(x, r2["debut"]) for x in ("B", "C")},
              "sujets_C": sujets_c, "sujets_B": sujets_b,
              "commits_exploration_C": len([s for s in sujets_c if s.startswith(f"exploration({scene.cartes['C']}):")]),
              "commits_exploration_B": len([s for s in sujets_b if s.startswith(f"exploration({scene.cartes['B']}):")]),
              # Chaque projet a son scénario : « attente » = C, « question » = B (agent relancé = travail refait).
              "agent_relance_sur_C": appels.get("attente", []), "agent_relance_sur_B": appels.get("question", []),
              "appels_agent_depuis_redemarrage": appels,
              "journal_executant_C": _journal_executant(scene, scene.cartes["C"])}
    afficher("R2b — exécutant plus récent que Hermes : MESURE (comportement non connu avant ce test)", _json(mesure))
    # Invariants seulement : historique des branches sans perte (tout commit de T+1 encore atteignable).
    for lettre, sujets_t1 in (("C", scene.sujets_c_t1),):
        assert all(s in sujets_c for s in sujets_t1), (lettre, sujets_t1, sujets_c)
    for ref, objet in scene.refs_t1.items():
        if ref.startswith("refs/heads/hermes/"):
            assert ref in refs and scene.contient(objet, ref), f"branche {ref} perdue ou réécrite"
    afficher("R2b — aucun jeton, aucun push", _json(scene.aucun_jeton_ni_push("R2b")))
