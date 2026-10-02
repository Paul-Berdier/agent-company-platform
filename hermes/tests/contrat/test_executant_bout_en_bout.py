"""Bout en bout LOCAL de l'étape P6 (cahier § 14.3) : l'image Hermes de test + le VRAI exécutant (image
executant/Dockerfile, cible « factice » : Codex et Claude Code remplacés par deux programmes Python pilotés par
scénario), sur un réseau Docker jetable. Rien d'autre n'est simulé : enrôlement par code, jeton machine, long-poll
``reclamer``, worktree, commit local par le superviseur root, vérification sous l'UID ``acp-verif``, contrôles des
fichiers de pilotage et des secrets, file de sortie, routes machine de P6 et routes du propriétaire.

Pile : faux fournisseur d'identité (session OIDC du propriétaire), faux ntfy en HTTPS, modèle factice de Hermes,
bord TLS factice devant le tableau de bord (``https://hermes-acp.test``, comme le bord de Railway), dépôt git distant
factice en HTTPS (``https://git.acp.test/proprietaire/jetable.git``, lecture seule, jamais GitHub). L'exécutant tourne
sous le seccomp Docker par défaut : RÉGIME B mesuré par sa propre sonde (voie Codex fermée, Claude seul), comme sur Railway
si R0 le confirme. Son image de test ajoute seulement l'autorité de test au magasin du système et une politique de
test (origine ``hermes-acp.test``, dépôt factice, vérification admise sans bac à sable).

Scénarios (mot ``[scenario:…]`` dans l'objectif du projet, lu par le faux Claude) :
1. une carte réclamée, exécutée, COMMITTÉE localement (auteur « ACP exécutant », aucun push), vérifiée, terminée ; le
   faux agent tente de lire les secrets du superviseur et ``/proc/1/environ`` : tout est refusé ;
2. une question → réponse du propriétaire → carte resservie, fil repris (``--resume``) → terminée ;
3. un secret dans le diff → branche ``quarantaine/<carte>``, carte bloquée, rien du secret chez Hermes ;
4. un fichier de pilotage (``.github/workflows``) → revue → refus du propriétaire → carte resservie avec le motif →
   corrigée → terminée ;
5. (relecture de P6) planification par le modèle factice de Hermes, implémentation par l'exécutant, puis relecture de
   REPLI par la même voie avec un autre modèle (D91) : le relecteur, sous son UID, lit le diff ET le code relus.
Puis : références du dépôt distant inchangées et aucune requête d'écriture ; aucun jeton dans les journaux (Hermes,
exécutant) ni dans la base du greffon. Les faux CLI ne prouvent que la plomberie, jamais la qualité d'un modèle.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from conftest import ENV_VALIDE, Conteneur, afficher, attendre_modele_factice, docker, lancer

RACINE = Path(__file__).resolve().parents[3]
MODELE = """\
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""
P = "/api/plugins/acp-poste"
PYTHON = "/opt/hermes/.venv/bin/python"
POSTE_SIMULE = "/opt/acp-tests/outils/poste_simule.py"
JOURNAL_NTFY = "/tmp/ntfy-p6-bout.jsonl"
JOURNAL_DEPOT = "/tmp/depot-factice.jsonl"
JOURNAL_FAUX = "/var/tmp/acp-factice/journal-*.jsonl"
JETON_CLAUDE = "jeton-claude-factice-" + "0123456789abcdef" * 2  # factice, jamais un vrai jeton
SECRET_FACTICE = "sk-ant-" + "faux" * 8  # assemblé à l'exécution, comme dans le faux Claude
ENV_P6 = dict(ENV_VALIDE, ACP_NOTIFICATIONS="ntfy", ACP_NTFY_SERVEUR="https://ntfy.acp.test",
              ACP_NTFY_SUJET="acp_sujet_bout_en_bout", ACP_NTFY_JETON="jeton-de-test-bout-en-bout")
NOMS_ENV_CLAUDE = {"HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN",
                   "DISABLE_UPDATES", "DISABLE_AUTOUPDATER", "DISABLE_TELEMETRY"}


def _image_factice() -> str:
    valeur = os.environ.get("ACP_IMAGE_EXECUTANT_FACTICE", "").strip()
    if not valeur:
        pytest.fail("ACP_IMAGE_EXECUTANT_FACTICE n'est pas défini : ce bout en bout exige la cible « factice » de "
                    "executant/Dockerfile (docker build --target factice).", pytrace=False)
    return valeur


def attendre(predicat, delai: float, message: str, pas: float = 2.0):
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:2000]}")


def politique_de_test() -> str:
    """Politique versionnée de l'exécutant, adaptée au banc : origine de test, dépôt factice, attente courte, sonde
    Codex coupée (voie fermée en régime B), vérification admise sans bac à sable (réseau du banc seulement)."""
    texte = (RACINE / "executant" / "politique" / "executant.toml").read_text(encoding="utf-8")
    remplacements = {
        'origine = "https://<libellé-hermes>.up.railway.app"': 'origine = "https://hermes-acp.test"',
        "attente_max_s = 25": "attente_max_s = 5",
        "[sondes]\ncodex = true": "[sondes]\ncodex = false",
        'hotes_admis = ["github.com"]': 'hotes_admis = ["git.acp.test"]',
    }
    for ancien, nouveau in remplacements.items():
        assert texte.count(ancien) == 1, ancien
        texte = texte.replace(ancien, nouveau)
    return texte + """
[depots.jetable]
url = "https://git.acp.test/proprietaire/jetable.git"
branche_base = "main"
acces = "public"
preparation = []
verification = ["/usr/bin/test", "-f", "README.md"]
verification_max_s = 120
reprises_verification = 1
verification_sans_bac_a_sable = true
liens_symboliques = false
pilotage_supplementaire = []
"""


class Banc:
    def __init__(self, ressources, image_tests: str) -> None:
        self.ressources = ressources
        self.image_tests = image_tests
        self.hermes: Optional[Conteneur] = None
        self.image_executant: Optional[str] = None

    # ------------------------------------------------------------------ pile
    def monter(self) -> None:
        r, image = self.ressources, self.image_tests
        reseau = r.reseau()
        for role, alias, commande in (
                ("idp", "idp.acp.test", ["/opt/acp-tests/outils/idp_factice.py", "--emetteur",
                                         "https://idp.acp.test:8443", "--port", "8443", "--certificat",
                                         "/opt/acp-tests/ac/idp.pem", "--cle", "/opt/acp-tests/ac/idp.key"]),
                ("ntfy", "ntfy.acp.test", ["/opt/acp-tests/outils/notif_factice.py", "--port", "443", "--certificat",
                                           "/opt/acp-tests/ac/ntfy.pem", "--cle", "/opt/acp-tests/ac/ntfy.key",
                                           "--journal", JOURNAL_NTFY]),
                ("depot", "git.acp.test", ["/opt/acp-tests/outils/depot_factice.py", "--port", "443", "--certificat",
                                           "/opt/acp-tests/ac/depot.pem", "--cle", "/opt/acp-tests/ac/depot.key",
                                           "--racine", "/tmp/depots", "--journal", JOURNAL_DEPOT])):
            nom = r.nom(role)
            r.conteneurs.append(nom)
            docker("run", "-d", "--name", nom, "--network", reseau, "--network-alias", alias, "--entrypoint", PYTHON,
                   image, "-u", *commande)
            setattr(self, role, nom)
        volume = r.volume(image, {"config.yaml": MODELE})
        self.hermes = lancer(r, image, ENV_P6, volume=volume, reseau=reseau)
        self.hermes.executer(["sh", "-c", "echo '{}' > /tmp/acp-scenarios.json"], utilisateur="hermes", verifier=True)
        docker("exec", "-d", "-u", "hermes", self.hermes.nom, PYTHON, "/opt/acp-tests/outils/modele_factice.py",
               "--port", "18080", "--journal", "/tmp/modele-factice.jsonl", "--scenarios", "/tmp/acp-scenarios.json")
        attendre_modele_factice(self.hermes, "/tmp/modele-factice.jsonl")
        # Émetteur à 5 s ; plafond des projets actifs relevé de 3 à 6 pour le banc (quatre scénarios, chacun son projet,
        # dont la planification par le modèle factice ne se conclut pas) : réglages de test, dits ici.
        for cle, valeur in (("emetteur_intervalle_s", "5"), ("projets_actifs_max", "6")):
            sortie = self.hermes.executer([PYTHON, POSTE_SIMULE, "reglage", cle, valeur], utilisateur="hermes",
                                          delai=120)
            assert sortie.returncode == 0, sortie.stderr[-2000:]
        self.bord = r.nom("bord")
        r.conteneurs.append(self.bord)
        docker("run", "-d", "--name", self.bord, "--network", reseau, "--network-alias", "hermes-acp.test",
               "--entrypoint", PYTHON, image, "-u", "/opt/acp-tests/outils/bord_factice.py", "--port", "443",
               "--certificat", "/opt/acp-tests/ac/bord.pem", "--cle", "/opt/acp-tests/ac/bord.key", "--journal",
               "/tmp/bord.jsonl", "--route", f"hermes-acp.test={self.hermes.nom}:9119")
        for nom, marque in ((self.bord, "[bord-factice] port 443"), (self.depot, "[depot-factice] port 443")):
            attendre(lambda: marque in docker("logs", nom, verifier=False).stdout, 60, f"{nom} non démarré")
        self.reseau = reseau

    def construire_executant(self) -> None:
        """Image de test = cible factice + autorité de test + politique de test (aucun autre changement)."""
        with tempfile.TemporaryDirectory(prefix="acp-exec-bout-") as dossier:
            contexte = Path(dossier)
            ac = docker("run", "--rm", "--entrypoint", "cat", self.image_tests, "/opt/acp-tests/ac/ac.pem").stdout
            (contexte / "ac.pem").write_text(ac, encoding="utf-8", newline="\n")
            (contexte / "executant.toml").write_text(politique_de_test(), encoding="utf-8", newline="\n")
            (contexte / "Dockerfile").write_text(
                "ARG IMAGE\nFROM ${IMAGE}\n"
                "COPY ac.pem /usr/local/share/ca-certificates/acp-test-jetable.crt\n"
                "COPY executant.toml /etc/acp/executant.toml\n"
                "RUN update-ca-certificates && chown root:root /etc/acp/executant.toml "
                "&& chmod 0444 /etc/acp/executant.toml\n", encoding="utf-8", newline="\n")
            self.image_executant = f"{self.ressources.prefixe}-executant:essai"
            docker("build", "-q", "--build-arg", f"IMAGE={_image_factice()}", "-t", self.image_executant,
                   str(contexte), delai=600)

    def demarrer_executant(self) -> None:
        r = self.ressources
        self.volume_executant = r.nom("vol-executant")
        docker("volume", "create", self.volume_executant)
        r.volumes.append(self.volume_executant)
        self.executant = r.nom("executant")
        r.conteneurs.append(self.executant)
        docker("run", "-d", "--name", self.executant, "--network", self.reseau, "-v",
               f"{self.volume_executant}:/donnees", self.image_executant)
        attendre(lambda: "[acp] volume prêt" in docker("logs", self.executant, verifier=False).stdout, 60,
                 "entrée de l'exécutant non passée")

    def nettoyer_image(self) -> None:
        if self.image_executant:
            docker("rmi", "-f", self.image_executant, verifier=False)

    # ------------------------------------------------------------------ gestes
    def jeton_oidc(self) -> str:
        sortie = self.hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                                       "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"],
                                      verifier=True).stdout
        return json.loads(sortie)["id_token"]

    def api(self, methode: str, chemin: str, corps: Optional[Any] = None):
        commande = ["curl", "-s", "-o", "/tmp/acp-reponse-bout", "-w", "%{http_code}", "-X", methode,
                    f"http://127.0.0.1:9119{P}{chemin}", "-H", f"Authorization: Bearer {self.jeton_oidc()}"]
        if corps is not None:
            commande += ["-H", "Content-Type: application/json", "--data-binary",
                         json.dumps(corps, ensure_ascii=False)]
        code = int(self.hermes.executer(commande, verifier=True).stdout.strip())
        contenu = self.hermes.executer(["cat", "/tmp/acp-reponse-bout"], verifier=True).stdout
        try:
            return code, json.loads(contenu)
        except ValueError:
            return code, contenu

    def acp_poste(self, *arguments: str, entree: Optional[str] = None):
        return docker("exec", *(("-i",) if entree is not None else ()), self.executant, "acp-poste", *arguments,
                      entree=entree, verifier=False, delai=180)

    def executant_sh(self, script: str) -> str:
        return docker("exec", self.executant, "sh", "-c", script, verifier=True, delai=120).stdout

    def cartes(self, tableau: str) -> List[Dict[str, Any]]:
        sortie = self.hermes.executer([PYTHON, POSTE_SIMULE, "cartes", tableau], utilisateur="hermes", delai=120)
        assert sortie.returncode == 0, sortie.stderr[-2000:]
        return json.loads(sortie.stdout.strip().splitlines()[-1])["cartes"]

    def carte_exploration(self, tableau: str) -> Dict[str, Any]:
        return attendre(lambda: next((c for c in self.cartes(tableau) if c["assigne"] == "poste-claude"), None), 60,
                        "carte d'exploration absente")

    def statut(self, tableau: str, carte: str) -> str:
        return next(c["statut"] for c in self.cartes(tableau) if c["id"] == carte)

    def attendre_statut(self, tableau: str, carte: str, attendus, delai: float = 120) -> str:
        attendus = (attendus,) if isinstance(attendus, str) else tuple(attendus)
        try:
            return attendre(lambda: (lambda s: s if s in attendus else None)(self.statut(tableau, carte)), delai,
                            f"carte {carte} jamais dans l'état {attendus}")
        except AssertionError as exc:
            _code, liste = self.api("GET", "/v1/questions")
            raisons = [b.get("raison") for b in (liste or {}).get("bloquees", []) if b.get("carte") == carte]
            raise AssertionError(f"{exc} ; raison chez Hermes : {raisons} ; journal : {self.fin_journal()}") from None

    def lancer_projet(self, titre: str, scenario: str) -> Dict[str, Any]:
        code, projet = self.api("POST", "/v1/projets", {
            "titre": titre, "objectif": f"Explorer le dépôt jetable. [scenario:{scenario}]", "depot": "jetable",
            "exploration": {"voie": "poste-claude", "modele": "opus", "effort": "low"}})
        assert code == 201, projet
        return projet["projet"]

    def faux(self) -> List[Dict[str, Any]]:
        brut = docker("exec", self.executant, "sh", "-c", f"cat {JOURNAL_FAUX} 2>/dev/null", verifier=False).stdout
        return [json.loads(l) for l in brut.splitlines() if l.strip()]

    def depot_nu(self, *arguments: str) -> str:
        commande = " ".join(shlex.quote(a) for a in arguments)
        return self.executant_sh(f"git --git-dir=/donnees/depots/jetable.git {commande}")

    def fin_journal(self) -> str:
        return self.acp_poste("journal", "--lignes", "15").stdout[-3000:]

    def notifications(self) -> List[Dict[str, Any]]:
        brut = docker("exec", self.ntfy, "sh", "-c", f"cat {JOURNAL_NTFY} 2>/dev/null", verifier=False).stdout
        return [json.loads(l) for l in brut.splitlines() if l.strip()]


@pytest.fixture(scope="module")
def banc(ressources, image_tests):
    b = Banc(ressources, image_tests)
    try:
        b.monter()
        b.construire_executant()
        b.demarrer_executant()
        yield b
    finally:
        b.nettoyer_image()


# =========================================================================== 0. mise en service


def test_mise_en_service_jetons_enrolement_regime_b(banc):
    remote_avant = banc.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
    banc.remote_avant = remote_avant
    depose = banc.acp_poste("connexion", "claude", "--stdin", entree=JETON_CLAUDE + "\n")
    assert depose.returncode == 0 and "déposé sur le volume (root, 0600)" in depose.stdout, depose.stderr
    assert JETON_CLAUDE not in depose.stdout + depose.stderr
    code, cree = banc.api("POST", "/v1/poste/enrolement", {})
    assert code == 201, cree
    enrole = banc.acp_poste("enroler", "--code-stdin", entree=cree["code"] + "\n")
    trouve = re.search(r"Poste enrôlé \(([^)]+)\)\. Empreinte : ([A-Z0-9]{4}-[A-Z0-9]{4})", enrole.stdout)
    assert enrole.returncode == 0 and trouve, (enrole.stdout, enrole.stderr)
    assert cree["code"] not in enrole.stdout + enrole.stderr
    code, confirme = banc.api("POST", "/v1/poste/confirmation", {"machine_id": trouve.group(1),
                                                                  "empreinte": trouve.group(2)})
    assert code == 200 and confirme["machine"]["etat"] == "actif", confirme

    def en_ligne():
        code, vue = banc.api("GET", "/v1/poste")
        executant = (vue or {}).get("executant") if code == 200 else None
        if executant and (executant.get("isolement") or {}).get("regime") in ("A", "B") and \
                "poste-claude" in (executant.get("voies_disponibles") or []):
            return vue
        return None

    vue = attendre(en_ligne, 180, f"exécutant jamais en ligne avec la voie poste-claude ({banc.fin_journal()})")
    executant = vue["executant"]
    afficher("exécutant réel vu par /v1/poste", json.dumps(executant, ensure_ascii=False, indent=1)[:4000])
    assert executant["plateforme"] == "linux" and executant["isolement"]["regime"] == "B"
    assert executant["isolement"]["uid_separes"] is True
    assert "poste-codex" in executant["voies_fermees"]


# =========================================================================== 1. carte exécutée, committée, terminée


def test_carte_executee_committee_verifiee_terminee(banc):
    projet = banc.lancer_projet("Bout en bout — simple", "simple")
    carte = banc.carte_exploration(projet["tableau"])
    banc.attendre_statut(projet["tableau"], carte["id"], "done")
    branche = f"hermes/{carte['id']}"
    journal = banc.depot_nu("log", "-1", "--format=%an%x09%ae%x09%s", branche)
    fichiers = banc.depot_nu("show", "--name-only", "--format=", branche)
    afficher("commit local de l'exécutant", journal + fichiers)
    auteur, courriel, sujet = journal.strip().split("\t")
    assert (auteur, courriel) == ("ACP exécutant", "executant@acp.invalid")
    assert sujet.startswith(f"exploration({carte['id']}):") and "Co-Authored-By" not in journal
    assert "NOTES-acp.md" in fichiers.split()
    appel = next(f for f in banc.faux() if f.get("scenario") == "simple")
    afficher("faux Claude : identité, environnement, lectures interdites",
             json.dumps({k: appel[k] for k in ("uid", "noms", "jeton", "lectures")}, ensure_ascii=False, indent=1))
    assert appel["uid"] == 10002 and appel["jeton"] is True
    assert set(appel["noms"]) <= NOMS_ENV_CLAUDE, set(appel["noms"]) - NOMS_ENV_CLAUDE
    assert appel["lectures"] and all(issue.startswith("refusé") for issue in appel["lectures"].values())
    assert "--restricted" in appel["argv"] and "--bare" not in appel["argv"]
    assert appel["cwd"] == f"/donnees/espaces/jetable/{carte['id']}"


# =========================================================================== 2. question, réponse, reprise


def test_question_reponse_puis_reprise_du_fil(banc):
    projet = banc.lancer_projet("Bout en bout — question", "question")
    carte = banc.carte_exploration(projet["tableau"])

    def question():
        code, liste = banc.api("GET", "/v1/questions")
        return next((q for q in liste["questions"] if q["carte"] == carte["id"]), None) if code == 200 else None

    posee = attendre(question, 240, f"question jamais posée ({banc.fin_journal()})")
    assert posee["texte"] == "Faut-il garder la compatibilité avec Python 3.10 ?"
    code, repondue = banc.api("POST", f"/v1/questions/{posee['id']}/reponse", {"reponse": "Oui, garde-la."})
    assert code == 200 and repondue["carte_debloquee"] is True, repondue
    banc.attendre_statut(projet["tableau"], carte["id"], "done")
    appels = [f for f in banc.faux() if f.get("scenario") == "question"]
    assert [a["phase"] for a in appels] == ["premiere", "reprise"]
    assert "--resume" in appels[1]["argv"] and appels[1]["argv"][appels[1]["argv"].index("--resume") + 1].startswith(
        "factice-question-")
    # La question n'avait rien écrit : aucun commit « wip » (rien à committer) ; la reprise committe le travail final.
    sujets = banc.depot_nu("log", "--format=%s", f"hermes/{carte['id']}").splitlines()
    assert sujets[0].startswith(f"exploration({carte['id']}):") and sujets[-1] == "initial"
    notes = banc.depot_nu("show", f"hermes/{carte['id']}:NOTES-acp.md")
    assert "Compatibilité Python 3.10 gardée" in notes


# =========================================================================== 3. secret : quarantaine et blocage


def test_secret_quarantaine_et_carte_bloquee(banc):
    projet = banc.lancer_projet("Bout en bout — secret", "secret")
    carte = banc.carte_exploration(projet["tableau"])
    banc.attendre_statut(projet["tableau"], carte["id"], "blocked")
    references = banc.depot_nu("for-each-ref", "--format=%(refname)", "refs/heads/")
    assert f"refs/heads/quarantaine/{carte['id']}" in references.split()
    assert f"refs/heads/hermes/{carte['id']}" not in references.split()
    code, liste = banc.api("GET", "/v1/questions")
    bloquee = next(b for b in liste["bloquees"] if b["carte"] == carte["id"])
    afficher("carte bloquée pour secret", json.dumps(bloquee, ensure_ascii=False, indent=1))
    assert SECRET_FACTICE not in json.dumps(liste)
    attendre(lambda: any("secret détecté" in n.get("corps", "") for n in banc.notifications()), 90,
             "notification « secret » jamais reçue")


# =========================================================================== 4. revue refusée, puis corrigée


def test_revue_de_pilotage_refusee_puis_corrigee(banc):
    projet = banc.lancer_projet("Bout en bout — pilotage", "pilotage")
    carte = banc.carte_exploration(projet["tableau"])
    banc.attendre_statut(projet["tableau"], carte["id"], "review")
    code, liste = banc.api("GET", "/v1/questions")
    revue = next(r for r in liste["revues"] if r["carte"] == carte["id"])
    assert revue["chemins"] == [".github/workflows/acp.yml"]
    code, refus = banc.api("POST", f"/v1/revues/{projet['tableau']}/{carte['id']}/refuser",
                           {"motif": "Ne touche pas aux workflows de CI."})
    assert code == 200, refus
    banc.attendre_statut(projet["tableau"], carte["id"], "done")
    appels = [f for f in banc.faux() if f.get("scenario") == "pilotage"]
    assert [a["phase"] for a in appels] == ["premiere", "reprise"]
    fichiers = banc.depot_nu("ls-tree", "-r", "--name-only", f"hermes/{carte['id']}").split()
    assert ".github/workflows/acp.yml" not in fichiers and "NOTES-acp.md" in fichiers


# =========================================================================== 4 bis. relecture (relecture de P6)


def test_relecture_lit_le_code_relu_et_son_diff(banc):
    """Haute (relecture de P6) : le greffon sert une relecture SANS branche de départ ; son worktree partait de la
    branche de base, et son diff, écrit root:root 0640, était illisible par l'agent : relecture à l'aveugle. Ici, de
    bout en bout : planification par le modèle factice de Hermes, implémentation par l'exécutant (voie Claude, régime
    B), puis relecture de REPLI par la même voie avec un autre modèle (D91) ; le faux Claude relecteur, sous l'UID
    10002, lit le diff et le code relus."""
    titre = "Bout en bout — relecture"
    # Modèles choisis par le plan (implémentation « sonnet », relecture « opus ») : la voie Codex étant fermée (régime
    # B), la relecture va à la même voie avec cet autre modèle (repli D91).
    plan = {"resume": "Écrire un fichier, puis le relire.", "decisions": ["Fichier texte"], "etapes": [
        {"ref": "e1", "titre": "Écrire relu.txt", "classe": "implementation", "voie": "poste-claude",
         "modele": "sonnet", "relecture_modele": "opus", "consigne": "Écrire le fichier relu.txt. [scenario:relu]",
         "effort": "low"}]}
    appel_plan = {"outil": "tool_call", "arguments": {"calls": [{"name": "projet_planifier", "arguments": plan}]}}
    appel_etat = {"outil": "tool_call", "arguments": {"calls": [{"name": "projet_etat", "arguments": {}}]}}
    scenarios = json.loads(banc.hermes.executer(["cat", "/tmp/acp-scenarios.json"], verifier=True).stdout or "{}")
    scenarios.update({
        f"rôle « planification » — projet « {titre} »": {"dans": "systeme", "etapes": [appel_plan],
                                                           "resume_final": "Plan posé."},
        f"rôle « synthese » — projet « {titre} »": {"dans": "systeme", "etapes": [appel_etat],
                                                      "resume_final": "Conclusion."}})
    banc.hermes.executer(["sh", "-c", "cat > /tmp/acp-scenarios.json"], utilisateur="hermes",
                         entree=json.dumps(scenarios, ensure_ascii=False), verifier=True)
    projet = banc.lancer_projet(titre, "relu-explo")

    def relecture():
        code, detail = banc.api("GET", f"/v1/projets/{projet['id']}")
        cartes = (detail or {}).get("projet", {}).get("cartes", []) if code == 200 else []
        return next((c for c in cartes if c.get("role") == "relecture"), None)

    try:
        carte = attendre(relecture, 300, "relecture jamais planifiée")
    except AssertionError as exc:
        _code, detail = banc.api("GET", f"/v1/projets/{projet['id']}")
        brut = banc.hermes.executer(["cat", "/tmp/modele-factice.jsonl"], verifier=False).stdout
        resultats = [r.get("resultats_outils") for r in (json.loads(l) for l in brut.splitlines() if l.strip())
                     if f"projet « {titre} »" in (r.get("section_acp") or "")]
        raise AssertionError(f"{exc} ; outils de la planification : {json.dumps(resultats, ensure_ascii=False)[:3000]}"
                             f" ; projet : {json.dumps(detail, ensure_ascii=False)[:1500]} ; journal : "
                             f"{banc.fin_journal()}") from None
    afficher("carte de relecture planifiée", json.dumps(carte, ensure_ascii=False, indent=1))
    banc.attendre_statut(projet["tableau"], carte["carte"], "done", delai=300)
    appel = next(f for f in banc.faux() if f.get("scenario") == "relecteur")
    afficher("faux Claude relecteur : identité, outils, textes lus",
             json.dumps({k: appel[k] for k in ("uid", "textes")}, ensure_ascii=False, indent=1))
    assert appel["uid"] == 10002 and "--add-dir" in appel["argv"]
    assert appel["argv"][appel["argv"].index("--tools") + 1] == "Read,Glob,Grep"
    assert appel["argv"][appel["argv"].index("--model") + 1] == "opus"  # repli D91 : autre modèle que « sonnet »
    assert "+contenu relu ACP-RELU-7C2B" in appel["textes"]["{add_dir}/diff.patch"], appel["textes"]
    assert appel["textes"]["relu.txt"] == "contenu relu ACP-RELU-7C2B\n", appel["textes"]


# =========================================================================== 5. aucun push, aucun jeton


def test_aucun_push_et_aucun_jeton_dans_les_journaux(banc):
    remote_apres = banc.executant_sh("git ls-remote https://git.acp.test/proprietaire/jetable.git")
    assert remote_apres == banc.remote_avant
    requetes = [json.loads(l) for l in docker("exec", banc.depot, "cat", JOURNAL_DEPOT).stdout.splitlines() if l]
    assert requetes and {r["methode"] for r in requetes} <= {"GET", "HEAD"}
    assert not any("receive-pack" in r["chemin"] for r in requetes)
    jeton_machine = banc.executant_sh("cat /donnees/acp/secrets/jeton-machine").strip()
    assert jeton_machine.startswith("acpm_")
    journaux_executant = docker("logs", banc.executant, verifier=False)
    textes = {
        "docker logs hermes": banc.hermes.journaux(),
        "base du greffon": banc.hermes.executer([PYTHON, "-c", (
            "import sqlite3, json\n"
            "c = sqlite3.connect('file:/opt/data/plugin-data/acp-poste/data.db?mode=ro', uri=True)\n"
            "t = [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]\n"
            "print(json.dumps({x: [list(map(str, l)) for l in c.execute(f'SELECT * FROM {x}')] for x in t}))\n")],
            utilisateur="hermes", verifier=True).stdout,
        "docker logs executant": journaux_executant.stdout + journaux_executant.stderr,
        "journal de l'exécutant": banc.executant_sh("cat /donnees/acp/journal/* 2>/dev/null || true"),
        "file de sortie": banc.executant_sh("cat /donnees/acp/sortie/* 2>/dev/null || true"),
    }
    for nom, texte in textes.items():
        for valeur in (jeton_machine, JETON_CLAUDE, SECRET_FACTICE):
            assert valeur not in texte, nom
        assert "acpe_" not in texte, nom
    etat = banc.acp_poste("cartes")
    afficher("état local de l'exécutant à la fin", etat.stdout[-2000:])
    afficher("bilan", json.dumps({"requetes_depot": len(requetes), "references_distantes": remote_apres.strip(),
                                  "tailles": {n: len(t) for n, t in textes.items()}}, ensure_ascii=False, indent=1))
