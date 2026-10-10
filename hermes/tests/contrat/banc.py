"""Banc LOCAL partagé (étape P9, cahier P9 § 3.2) : l'image Hermes de test + le VRAI exécutant (image
executant/Dockerfile, cible « factice »), sur un réseau Docker jetable. Extrait SANS changement de comportement du bout
en bout de l'étape P6 (test_executant_bout_en_bout.py, qui l'emploie tel quel) pour servir aussi aux tests de
restauration de P9.

Pile : faux fournisseur d'identité (session OIDC du propriétaire), faux ntfy en HTTPS, modèle factice de Hermes, bord
TLS factice devant le tableau de bord (``https://hermes-acp.test``, comme le bord de Railway), dépôt git distant
factice en HTTPS (``https://git.acp.test/proprietaire/jetable.git``, lecture seule, jamais GitHub). L'image de test de
l'exécutant ajoute seulement l'autorité de test au magasin du système et une politique de test (origine
``hermes-acp.test``, dépôt factice, vérification admise sans bac à sable).

Tout ce qui est créé porte le préfixe des ``Ressources`` de conftest.py et est supprimé à la fin, même en échec.
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

from conftest import ENV_VALIDE, Conteneur, attendre_modele_factice, docker, lancer

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


def image_factice() -> str:
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


def politique_de_test(racine: Path = RACINE) -> str:
    """Politique versionnée de l'exécutant, adaptée au banc : origine de test, dépôt factice, attente courte, sonde
    Codex coupée (voie fermée en régime B), vérification admise sans bac à sable (réseau du banc seulement).
    ``racine`` : l'arbre dont la politique est lue (étape P9, montée de données : celui du commit « avant »)."""
    texte = (racine / "executant" / "politique" / "executant.toml").read_text(encoding="utf-8")
    import re
    texte, nombre = re.subn(r'(?m)^origine = "[^"\n]*"$', 'origine = "https://hermes-acp.test"', texte)
    assert nombre == 1, "une seule origine attendue dans la politique du banc"
    remplacements = {
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
        self.image_executant: Optional[str] = None
        # Images construites par le banc (exécutant de test ; étape P9 : une par version) : nettoyer_image() les retire.
        self.images_construites: List[str] = []
        # Posés par monter() et demarrer_executant() (déclarations seules : aucun changement de comportement).
        self.hermes: Conteneur
        self.idp: str
        self.ntfy: str
        self.depot: str
        self.bord: str
        self.reseau: str
        self.executant: str
        self.volume_executant: str
        self.volume_hermes: str
        # Étape P9 : vraie identité (Authelia) à côté du banc, sur son volume, non branchée sur l'OIDC du banc.
        self.identite: Optional[str] = None
        self.volume_identite: Optional[str] = None
        self.bord_identite: Optional[str] = None

    # ------------------------------------------------------------------ pile
    def monter(self) -> None:
        r, image = self.ressources, self.image_tests
        reseau = r.reseau()
        self.reseau = reseau
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
        self.volume_hermes = volume
        self.hermes = lancer(r, image, ENV_P6, volume=volume, reseau=reseau)
        self._demarrer_modele_factice()
        # Émetteur à 5 s ; plafond des projets actifs relevé de 3 à 6 pour le banc (quatre scénarios, chacun son projet,
        # dont la planification par le modèle factice ne se conclut pas) : réglages de test, dits ici.
        for cle, valeur in (("emetteur_intervalle_s", "5"), ("projets_actifs_max", "6")):
            sortie = self.hermes.executer([PYTHON, POSTE_SIMULE, "reglage", cle, valeur], utilisateur="hermes",
                                          delai=120)
            assert sortie.returncode == 0, sortie.stderr[-2000:]
        self._lancer_bord()
        for nom, marque in ((self.bord, "[bord-factice] port 443"), (self.depot, "[depot-factice] port 443")):
            attendre(lambda: marque in docker("logs", nom, verifier=False).stdout, 60, f"{nom} non démarré")

    def _demarrer_modele_factice(self) -> None:
        """Modèle factice de Hermes, lancé dans son conteneur (hors du volume : à relancer avec le conteneur)."""
        self.hermes.executer(["sh", "-c", "echo '{}' > /tmp/acp-scenarios.json"], utilisateur="hermes", verifier=True)
        docker("exec", "-d", "-u", "hermes", self.hermes.nom, PYTHON, "/opt/acp-tests/outils/modele_factice.py",
               "--port", "18080", "--journal", "/tmp/modele-factice.jsonl", "--scenarios", "/tmp/acp-scenarios.json")
        attendre_modele_factice(self.hermes, "/tmp/modele-factice.jsonl")

    def _lancer_bord(self) -> None:
        """Bord TLS factice ``hermes-acp.test`` devant le tableau de bord du conteneur Hermes courant."""
        self.bord = self.ressources.nom("bord")
        self.ressources.conteneurs.append(self.bord)
        docker("run", "-d", "--name", self.bord, "--network", self.reseau, "--network-alias", "hermes-acp.test",
               "--entrypoint", PYTHON, self.image_tests, "-u", "/opt/acp-tests/outils/bord_factice.py", "--port", "443",
               "--certificat", "/opt/acp-tests/ac/bord.pem", "--cle", "/opt/acp-tests/ac/bord.key", "--journal",
               "/tmp/bord.jsonl", "--route", f"hermes-acp.test={self.hermes.nom}:9119")

    def construire_executant(self, image_base: Optional[str] = None, etiquette: str = "essai",
                             politique: Optional[str] = None) -> str:
        """Image de test = cible factice + autorité de test + politique de test (aucun autre changement). Étape P9
        (montée de données) : ``image_base`` (défaut : ACP_IMAGE_EXECUTANT_FACTICE), ``politique`` (défaut :
        :func:`politique_de_test`) et ``etiquette`` distinguent l'image « avant » de l'image « après ». L'autorité est
        celle de ``self.image_tests``. Rend le nom de l'image, que :meth:`demarrer_executant` lance ensuite."""
        with tempfile.TemporaryDirectory(prefix="acp-exec-bout-") as dossier:
            contexte = Path(dossier)
            ac = docker("run", "--rm", "--entrypoint", "cat", self.image_tests, "/opt/acp-tests/ac/ac.pem").stdout
            (contexte / "ac.pem").write_text(ac, encoding="utf-8", newline="\n")
            (contexte / "executant.toml").write_text(politique if politique is not None else politique_de_test(),
                                                     encoding="utf-8", newline="\n")
            (contexte / "Dockerfile").write_text(
                "ARG IMAGE\nFROM ${IMAGE}\n"
                "COPY ac.pem /usr/local/share/ca-certificates/acp-test-jetable.crt\n"
                "COPY executant.toml /etc/acp/executant.toml\n"
                "RUN update-ca-certificates && chown root:root /etc/acp/executant.toml "
                "&& chmod 0444 /etc/acp/executant.toml\n", encoding="utf-8", newline="\n")
            image = f"{self.ressources.prefixe}-executant:{etiquette}"
            self.images_construites.append(image)
            self.image_executant = image
            docker("build", "-q", "--build-arg", f"IMAGE={image_base or image_factice()}", "-t", image,
                   str(contexte), delai=600)
        return image

    def demarrer_executant(self, volume: Optional[str] = None) -> None:
        """Conteneur de l'exécutant sur un volume neuf, ou sur ``volume`` (étape P9 : volume restauré)."""
        r = self.ressources
        self.volume_executant = volume if volume is not None else self._volume_neuf("vol-executant")
        self.executant = r.nom("executant")
        r.conteneurs.append(self.executant)
        assert self.image_executant, "construire_executant() d'abord"
        docker("run", "-d", "--name", self.executant, "--network", self.reseau, "-v",
               f"{self.volume_executant}:/donnees", self.image_executant)
        attendre(lambda: "[acp] volume prêt" in docker("logs", self.executant, verifier=False).stdout, 60,
                 "entrée de l'exécutant non passée")

    def _volume_neuf(self, role: str) -> str:
        nom: str = self.ressources.nom(role)
        docker("volume", "create", nom)
        self.ressources.volumes.append(nom)
        return nom

    def nettoyer_image(self) -> None:
        for image in self.images_construites:
            docker("rmi", "-f", image, verifier=False)

    # ------------------------------------------------------------------ étape P9 : identité, arrêt, relance
    def lancer_identite(self, image_identite: str, empreinte: str, volume: Optional[str] = None) -> str:
        """Vraie identité (image identite/, Authelia) sur le réseau du banc, alias ``identite-interne``, sur un volume
        neuf ou donné (même forme que ``Pile.lancer_identite`` de pile_identite.py), et son bord TLS factice
        ``identite-acp.test`` (lancé une fois). Elle n'est PAS branchée sur l'OIDC du banc, qui garde son faux IdP."""
        from pile_identite import HOTE_IDENTITE, attendre_identite, env_identite, options_env

        r = self.ressources
        volume = volume if volume is not None else self._volume_neuf("vol-identite")
        nom: str = r.nom("identite")
        r.conteneurs.append(nom)
        docker("run", "-d", "--name", nom, "-v", f"{volume}:/config", "--network", self.reseau, "--network-alias",
               "identite-interne", *options_env(env_identite(empreinte)), image_identite)
        attendre_identite(nom)
        self.identite, self.volume_identite = nom, volume
        if self.bord_identite is None:
            bord: str = r.nom("bord-identite")
            self.bord_identite = bord
            r.conteneurs.append(bord)
            docker("run", "-d", "--name", bord, "--network", self.reseau, "--network-alias", HOTE_IDENTITE,
                   "--entrypoint", PYTHON, self.image_tests, "-u", "/opt/acp-tests/outils/bord_factice.py", "--port",
                   "443", "--certificat", "/opt/acp-tests/ac/bord.pem", "--cle", "/opt/acp-tests/ac/bord.key",
                   "--journal", "/tmp/bord.jsonl", "--route", f"{HOTE_IDENTITE}=identite-interne:9091")
            attendre(lambda: "[bord-factice] port 443" in docker("logs", bord, verifier=False).stdout, 60,
                     f"{bord} non démarré")
        return nom

    def arreter(self, delai: int = 90) -> List[Dict[str, Any]]:
        """Arrêt propre dans l'ordre exécutant, Hermes, identité (cahier P9 § 3.3 point 6 : l'exécutant envoie son
        ``arret`` à un Hermes encore en marche). Rend le code de sortie de chacun ; un conteneur déjà arrêté le reste."""
        etats = []
        for nom in [self.executant, self.hermes.nom] + ([self.identite] if self.identite else []):
            docker("stop", "-t", str(delai), nom, delai=delai + 60)
            code = docker("inspect", "-f", "{{.State.ExitCode}}", nom).stdout.strip()
            etats.append({"conteneur": nom, "code": int(code)})
        return etats

    def relancer_hermes(self, volume_hermes: str) -> None:
        """Hermes seul, mêmes image et variables, dans un NOUVEAU conteneur sur ``volume_hermes`` (modèle factice et
        nouveau bord vers lui ; l'ancien bord est retiré). Le conteneur Hermes précédent doit être arrêté."""
        docker("rm", "-f", self.bord, verifier=False, delai=120)
        self.volume_hermes = volume_hermes
        self.hermes = lancer(self.ressources, self.image_tests, ENV_P6, volume=volume_hermes, reseau=self.reseau)
        self._demarrer_modele_factice()
        self._lancer_bord()
        bord = self.bord
        attendre(lambda: "[bord-factice] port 443" in docker("logs", bord, verifier=False).stdout, 60,
                 f"{bord} non démarré")

    def relancer(self, volume_hermes: str, volume_executant: str, *, volume_identite: Optional[str] = None,
                 image_identite: Optional[str] = None, empreinte: Optional[str] = None) -> None:
        """Mêmes images et mêmes variables sur les volumes donnés (restaurés), dans de NOUVEAUX conteneurs : Hermes
        (et son modèle factice), un nouveau bord ``hermes-acp.test`` vers lui (l'ancien est retiré : un seul alias),
        l'identité si son volume est donné, puis l'exécutant. Les conteneurs précédents doivent être arrêtés."""
        self.relancer_hermes(volume_hermes)
        if volume_identite is not None:
            assert image_identite and empreinte, "image et empreinte de l'identité exigées"
            self.lancer_identite(image_identite, empreinte, volume=volume_identite)
        self.demarrer_executant(volume=volume_executant)

    # ------------------------------------------------------------------ mise en service
    def mettre_en_service(self) -> Dict[str, Any]:
        """Jeton Claude factice déposé, enrôlement par code, empreinte confirmée, puis attente de l'exécutant en ligne
        avec la voie poste-claude (régime A ou B). Rend la vue ``/v1/poste``."""
        depose = self.acp_poste("connexion", "claude", "--stdin", entree=JETON_CLAUDE + "\n")
        assert depose.returncode == 0 and "déposé sur le volume (root, 0600)" in depose.stdout, depose.stderr
        assert JETON_CLAUDE not in depose.stdout + depose.stderr
        code, cree = self.api("POST", "/v1/poste/enrolement", {})
        assert code == 201, cree
        enrole = self.acp_poste("enroler", "--code-stdin", entree=cree["code"] + "\n")
        trouve = re.search(r"Poste enrôlé \(([^)]+)\)\. Empreinte : ([A-Z0-9]{4}-[A-Z0-9]{4})", enrole.stdout)
        assert enrole.returncode == 0 and trouve, (enrole.stdout, enrole.stderr)
        assert cree["code"] not in enrole.stdout + enrole.stderr
        code, confirme = self.api("POST", "/v1/poste/confirmation", {"machine_id": trouve.group(1),
                                                                      "empreinte": trouve.group(2)})
        assert code == 200 and confirme["machine"]["etat"] == "actif", confirme

        def en_ligne():
            code, vue = self.api("GET", "/v1/poste")
            executant = (vue or {}).get("executant") if code == 200 else None
            if executant and (executant.get("isolement") or {}).get("regime") in ("A", "B") and \
                    "poste-claude" in (executant.get("voies_disponibles") or []):
                return vue
            return None

        return attendre(en_ligne, 180, f"exécutant jamais en ligne avec la voie poste-claude ({self.fin_journal()})")

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


__all__ = ["Banc", "ENV_P6", "JETON_CLAUDE", "JOURNAL_DEPOT", "JOURNAL_FAUX", "JOURNAL_NTFY", "MODELE", "P", "PYTHON",
           "POSTE_SIMULE", "RACINE", "SECRET_FACTICE", "attendre", "image_factice", "politique_de_test"]
