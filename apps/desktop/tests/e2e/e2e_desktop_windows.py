"""Bout en bout LOCAL de la station Qt (apps/desktop) contre la pile de test (cahier P8 § 10). Jamais en CI.

Pile : vrai Authelia (image ACP_IMAGE_IDENTITE), Hermes de test (ACP_IMAGE_TESTS) avec le modèle factice, bord
TLS factice publié sur 127.0.0.1:<port> (hermes/tests/contrat/pile_identite.py). Station : le pilote
``acp_desktop_e2e`` (la VRAIE station : Application, services, ViewModels et pages QML), lancé avec un coffre
``AcpDesktopE2E-<uuid>``, une portée de préférences ``ACP E2E <uuid>``, l'autorité de test du bord et un
MANDATAIRE CONNECT local de ce script, qui ne mène qu'aux deux noms de la pile (tout autre nom est refusé et
compté). Navigateur : Chromium (Playwright) avec un authentificateur WebAuthn virtuel, à la place du navigateur
du système.

Parcours :
 1. connexion native RFC 8252 : la station émet l'URL d'autorisation ; Chromium s'y rend (mot de passe,
    passkey, consentement) ; la redirection atteint l'écouteur 127.0.0.1 de la station ; échange, identité,
    jeton de rafraîchissement au coffre de test ;
 2. deux rafraîchissements : rotation constatée par empreintes (jamais les valeurs) ;
 3. JSON-RPC : ticket, /api/ws par le bord, session.create, prompt.submit → réponse du modèle factice ;
 4. projet lancé par la page Projets (sur dépôt, « Moi » répond) ; veille du kanban : un événement de carte
    déclenche une relecture du détail (délai mesuré) ; le poste simulé pose une question ; la station la voit
    dans Questions et y RÉPOND ; relecture par l'API : question fermée, carte reprise ; captures avant/après ;
 5. sauvegarde : lancée, suivie, téléchargée et chiffrée (DPAPI), déchiffrée et comparée (SHA-256), suppression
    de l'archive du volume tentée et son résultat consigné ;
 6. redémarrage de la station : la session revient du coffre SANS navigateur (rotation au démarrage) ;
 7. déconnexion : POST /auth/logout avec le cookie, puis rejeu de l'ancien jeton : statut consigné tel quel ;
 8. hygiène : préférences et journal de la station sans jeton, entrée du coffre absente (cmdkey), export du
    registre de la portée balayé, journal du bord balayé ; portée de test supprimée.

Rapport JSON sans jeton ni URL d'autorisation ; captures PNG avec empreintes. Code ≠ 0 au moindre écart.

Lancement : scripts/e2e-desktop-windows.ps1 (voir docs/desktop-build.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

RACINE = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RACINE / "hermes" / "tests" / "contrat"))

from pile_identite import (EMETTEUR, HOTE_HERMES, HOTE_IDENTITE, MOT_DE_PASSE, NOM, URL_HERMES, UTILISATEUR,  # noqa: E402
                           Pile, docker, empreinte_argon2, lignes_du_bord, monter_pile, spki_du_bord)

PYTHON = "/opt/hermes/.venv/bin/python"
SCENARIOS = "/tmp/acp-scenarios.json"
JOURNAL_FACTICE = "/tmp/modele-factice.jsonl"
MODELE = """\
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""
TITRE = "Outil station"
QUESTION = "Quelle version de Python viser ?"
REPONSE = "Python 3.12, sans dépendance externe."
REPONSE_FACTICE = "Réponse du modèle factice ACP."
PLAN = {"resume": "Une recherche, puis la synthèse.", "decisions": ["Sources de moins d'un an"],
        "etapes": [{"ref": "e1", "titre": "Chercher les modèles", "classe": "recherche_web",
                    "consigne": "Recenser les modèles publiés ce mois."}]}
# Formes de secrets cherchées dans tout ce que la station et la pile écrivent.
FORMES_DE_SECRET = re.compile(
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|authelia_[a-z]{2}_[A-Za-z0-9._~-]{6,}|Bearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|hermes_session_(?:rt|at)=[^;\s\[]{6,}|hermes-gateway-ticket\.[A-Za-z0-9._~-]{6,}|acp[em]_[A-Za-z0-9_-]{20,}"
    r"|[?&](?:code|state|ticket|code_verifier)=[^&\s\[]{6,}")


# ----------------------------------------------------------------------------------------- outils


def afficher(texte: str) -> None:
    print(texte, flush=True)


def attendre(predicat: Callable[[], Any], delai: float, message: str, pas: float = 2.0) -> Any:
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:800]}")


def sha256_fichier(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def appel(nom: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"outil": "tool_call", "arguments": {"calls": [{"name": nom, "arguments": arguments or {}}]}}


def scenarios() -> Dict[str, Any]:
    """Même forme que hermes/tests/e2e/test_projets.py : planification, étape Hermes et synthèse jouées."""
    def scenario(etapes: List[Dict[str, Any]], resume: str) -> Dict[str, Any]:
        return {"dans": "systeme", "etapes": etapes, "resume_final": resume}

    return {
        f"rôle « planification » — projet « {TITRE} »": scenario(
            [{"outil": "kanban_show", "arguments": {}}, appel("projet_planifier", PLAN)], "Plan posé : une recherche."),
        f"rôle « hermes » — projet « {TITRE} »": scenario([{"outil": "kanban_show", "arguments": {}}],
                                                          "Recherche faite (témoin)."),
        f"rôle « synthese » — projet « {TITRE} »": scenario([appel("projet_etat")], "Conclusion : la recherche est faite."),
    }


def simule(hermes: str, *arguments: str) -> Dict[str, Any]:
    sortie = docker("exec", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/poste_simule.py", *arguments,
                    verifier=False, delai=120)
    assert sortie.returncode == 0, (arguments, sortie.stdout[-2000:], sortie.stderr[-3000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def demarrer_modele_factice(hermes: str) -> None:
    docker("exec", "-i", "-u", "hermes", hermes, "sh", "-c", f"cat > {SCENARIOS}",
           entree=json.dumps(scenarios(), ensure_ascii=False))
    docker("exec", "-d", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port", "18080",
           "--journal", JOURNAL_FACTICE, "--scenarios", SCENARIOS)
    attendre(lambda: docker("exec", hermes, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "http://127.0.0.1:18080/v1/models", verifier=False).stdout.strip() == "200",
             60, "le modèle factice ne répond pas", pas=0.5)


def attendre_passerelle(hermes: str) -> None:
    def branchee() -> bool:
        sortie = docker("exec", hermes, "curl", "-s", "http://127.0.0.1:9119/api/status", verifier=False).stdout
        try:
            statut = json.loads(sortie)
        except ValueError:
            return False
        serveur = (statut.get("gateway_platforms") or {}).get("api_server") or {}
        return bool(statut.get("gateway_running")) and serveur.get("state") == "connected"

    attendre(branchee, 180, "la passerelle de Hermes n'est pas branchée")


# ----------------------------------------------------------------------- mandataire CONNECT local


class Mandataire:
    """Mandataire HTTP CONNECT sur 127.0.0.1 : seuls hermes-acp.test:443 et identite-acp.test:443 mènent au
    bord publié ; toute autre cible est refusée (403) et comptée. Aucun octet n'est lu ni consigné."""

    def __init__(self, port_bord: int) -> None:
        self.port_bord = port_bord
        self.ecoute = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ecoute.bind(("127.0.0.1", 0))
        self.ecoute.listen(64)
        self.port = self.ecoute.getsockname()[1]
        self.tunnels: Dict[str, int] = {}
        self.refus: List[str] = []
        self.arret = threading.Event()
        threading.Thread(target=self._boucle, daemon=True).start()

    def _boucle(self) -> None:
        while not self.arret.is_set():
            try:
                client, _ = self.ecoute.accept()
            except OSError:
                return
            threading.Thread(target=self._servir, args=(client,), daemon=True).start()

    def _servir(self, client: socket.socket) -> None:
        try:
            tete = b""
            while b"\r\n\r\n" not in tete and len(tete) < 8192:
                morceau = client.recv(4096)
                if not morceau:
                    return
                tete += morceau
            premiere = tete.split(b"\r\n", 1)[0].decode("latin-1")
            parties = premiere.split()
            cible = parties[1] if len(parties) == 3 and parties[0] == "CONNECT" else premiere[:80]
            if cible not in (f"{HOTE_HERMES}:443", f"{HOTE_IDENTITE}:443"):
                self.refus.append(cible)
                client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            self.tunnels[cible] = self.tunnels.get(cible, 0) + 1
            amont = socket.create_connection(("127.0.0.1", self.port_bord), timeout=30)
            amont.settimeout(None)
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            reste = tete.split(b"\r\n\r\n", 1)[1]
            if reste:
                amont.sendall(reste)
            self._relayer(client, amont)
        except OSError:
            pass
        finally:
            try:
                client.close()
            except OSError:
                pass

    @staticmethod
    def _relayer(a: socket.socket, b: socket.socket) -> None:
        def sens(source: socket.socket, cible: socket.socket) -> None:
            try:
                while True:
                    donnees = source.recv(65536)
                    if not donnees:
                        break
                    cible.sendall(donnees)
            except OSError:
                pass
            finally:
                for s in (source, cible):
                    try:
                        s.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        fil = threading.Thread(target=sens, args=(b, a), daemon=True)
        fil.start()
        sens(a, b)
        fil.join(timeout=5)
        b.close()

    def fermer(self) -> None:
        self.arret.set()
        self.ecoute.close()


# --------------------------------------------------------------------------------- pilote station


class Station:
    """Le pilote acp_desktop_e2e : une commande JSON par ligne, des lignes « ACPE2E {json} » en retour."""

    def __init__(self, executable: Path, coffre: str, portee: str, mandataire: int, autorite: Path,
                 captures: Path, journal: Path, qt_bin: Optional[Path]) -> None:
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        # Polices du système pour les captures hors écran (sans elles, des carrés).
        env["QT_QPA_FONTDIR"] = str(Path(os.environ.get("WINDIR", os.environ.get("SystemRoot", ""))) / "Fonts")
        if qt_bin:
            env["PATH"] = f"{qt_bin}{os.pathsep}{env.get('PATH', '')}"
        self.journal = open(journal, "a", encoding="utf-8", errors="replace")
        self.processus = subprocess.Popen(
            [str(executable), "--coffre", coffre, "--portee", portee, "--mandataire", f"127.0.0.1:{mandataire}",
             "--autorite", str(autorite), "--captures", str(captures)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.journal, env=env)
        self.lignes: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        threading.Thread(target=self._lire, daemon=True).start()
        self.pret = self.attendre_evenement("pret", 60)

    def _lire(self) -> None:
        assert self.processus.stdout is not None
        for brut in self.processus.stdout:
            texte = brut.decode("utf-8", errors="replace").rstrip("\r\n")
            if texte.startswith("ACPE2E "):
                self.lignes.put(json.loads(texte[len("ACPE2E "):]))
        self.lignes.put({"evenement": "fin", "code": self.processus.wait()})

    def _suivant(self, delai: float) -> Dict[str, Any]:
        try:
            return self.lignes.get(timeout=delai)
        except queue.Empty:
            raise AssertionError(f"la station n'a rien émis en {delai:.0f} s") from None

    def attendre_evenement(self, nom: str, delai: float) -> Dict[str, Any]:
        limite = time.monotonic() + delai
        while True:
            ligne = self._suivant(max(1.0, limite - time.monotonic()))
            if ligne.get("evenement") == "fin":
                raise AssertionError(f"la station s'est arrêtée (code {ligne.get('code')}) avant « {nom} »")
            if ligne.get("evenement") == nom:
                return ligne
            if time.monotonic() > limite:
                raise AssertionError(f"événement « {nom} » jamais reçu")

    def envoyer(self, commande: str, **arguments: Any) -> None:
        assert self.processus.stdin is not None
        self.processus.stdin.write((json.dumps({"commande": commande, **arguments}, ensure_ascii=False) + "\n").encode())
        self.processus.stdin.flush()

    def reponse(self, commande: str, delai: float = 300) -> Dict[str, Any]:
        limite = time.monotonic() + delai
        while True:
            ligne = self._suivant(max(1.0, limite - time.monotonic()))
            if ligne.get("evenement") == "fin":
                raise AssertionError(f"la station s'est arrêtée (code {ligne.get('code')}) pendant « {commande} »")
            if ligne.get("commande") == commande:
                return ligne
            if time.monotonic() > limite:
                raise AssertionError(f"réponse à « {commande} » jamais reçue")

    def commande(self, commande: str, delai: float = 300, **arguments: Any) -> Dict[str, Any]:
        self.envoyer(commande, **arguments)
        return self.reponse(commande, delai)

    def quitter(self) -> int:
        try:
            self.commande("quitter", 30)
        finally:
            code = self.processus.wait(timeout=60)
            self.journal.close()
        return code


# -------------------------------------------------------------------------------------- navigateur


def connexion_navigateur(playwright, port: int, spki: str, identite: str, url: str,
                         captures: Path) -> Dict[str, Any]:
    """Étapes du propriétaire dans le navigateur (même parcours que hermes/tests/e2e/parcours.se_connecter, mais
    parti de l'URL d'autorisation NATIVE de la station) ; finit sur la page de l'écouteur 127.0.0.1."""
    navigateur = playwright.chromium.launch(headless=True, args=[
        f"--host-resolver-rules=MAP {HOTE_HERMES} 127.0.0.1:{port}, MAP {HOTE_IDENTITE} 127.0.0.1:{port}",
        f"--ignore-certificate-errors-spki-list={spki}"])
    try:
        contexte = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris",
                                          viewport={"width": 1280, "height": 860})
        page = contexte.new_page()
        page.set_default_timeout(60_000)
        cdp = contexte.new_cdp_session(page)
        cdp.send("WebAuthn.enable")
        authentificateur = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
            "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
            "isUserVerified": True, "automaticPresenceSimulation": True}})["authenticatorId"]
        page.goto(url)
        page.wait_for_url(re.compile(rf"^{re.escape(EMETTEUR)}/\?flow=openid_connect&flow_id="))
        page.wait_for_selector("#username-textfield")
        page.fill("#username-textfield", UTILISATEUR)
        page.fill("#password-textfield", MOT_DE_PASSE)
        page.click("#sign-in-button")
        page.wait_for_url(re.compile(r"/2fa/webauthn\?flow=openid_connect"))
        url_second_facteur = page.url
        page.wait_for_selector("#register-link")
        page.click("#register-link")
        page.click("#webauthn-credential-add")
        page.wait_for_selector("#one-time-code")
        page.fill("#one-time-code", code_a_usage_unique(identite))
        page.click("#dialog-verify")
        page.fill("#webauthn-credential-description", "authentificateur virtuel de test")
        page.click("#dialog-next")
        page.wait_for_selector("#webauthn-credential-0-information")
        page.goto(url_second_facteur)
        page.wait_for_url(re.compile(r"/consent/openid/decision\?flow=openid_connect"))
        page.wait_for_selector("#openid-consent-accept")
        [credential] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": authentificateur})["credentials"]
        page.click("#openid-consent-accept")
        page.wait_for_url(re.compile(r"^http://127\.0\.0\.1:\d+/rappel\?"))
        page.wait_for_load_state()
        texte = page.inner_text("body")
        captures.mkdir(parents=True, exist_ok=True)
        capture = captures / "00-navigateur-rappel.png"
        page.screenshot(path=str(capture))
        return {"rp_id": credential["rpId"], "compteur_passkey": credential["signCount"],
                "page_de_rappel": texte.strip()[:300], "capture": capture.name}
    finally:
        navigateur.close()


def code_a_usage_unique(identite: str, delai: float = 60) -> str:
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        texte = docker("exec", identite, "cat", "/config/notification.txt", verifier=False).stdout
        codes = re.findall(r"^\s*([A-Z0-9]{8})\s*$", texte, re.M)
        if codes:
            return codes[-1]
        time.sleep(1)
    raise AssertionError("aucun code à usage unique dans /config/notification.txt")


# ----------------------------------------------------------------------------------------- parcours


def verifier(condition: bool, message: str, ecarts: List[str]) -> None:
    if not condition:
        ecarts.append(message)
        afficher(f"  ÉCART : {message}")


def parcours(options: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    ecarts: List[str] = []
    preuves: Dict[str, Any] = {"date": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "images": {
        "tests": options.image_tests, "identite": options.image_identite}, "etapes": {}}
    etapes = preuves["etapes"]
    jeton_essai = uuid.uuid4().hex[:12]
    coffre = f"AcpDesktopE2E-{jeton_essai}"
    portee = f"ACP E2E {jeton_essai}"
    captures = Path(options.captures)
    captures.mkdir(parents=True, exist_ok=True)
    travail = Path(tempfile.mkdtemp(prefix="acp-e2e-desktop-"))
    journal_station = travail / "station-stderr.log"
    journal_expurge = travail / "station-journal.log"
    pile = Pile()
    mandataire: Optional[Mandataire] = None
    station: Optional[Station] = None
    try:
        # ---------------------------------------------------------------- pile
        afficher("Pile : identité, bord publié, Hermes de test, modèle factice…")
        noms = monter_pile(pile, options.image_identite, options.image_tests, empreinte_argon2(options.image_identite),
                           publier=True, fichiers={"config.yaml": MODELE})
        identite, hermes, bord, port = noms["identite"], noms["hermes"], noms["bord"], noms["port"]
        attendre_passerelle(hermes)
        demarrer_modele_factice(hermes)
        for cle, valeur in (("emetteur_intervalle_s", "5"), ("seuil_hors_ligne_s", "3600"),
                            ("projets_actifs_max", "10")):
            simule(hermes, "reglage", cle, valeur)
        spki = spki_du_bord(options.image_tests)
        autorite = travail / "ac.pem"
        autorite.write_text(docker("run", "--rm", "--entrypoint", "cat", options.image_tests,
                                   "/opt/acp-tests/ac/ac.pem").stdout, encoding="ascii")
        mandataire = Mandataire(port)
        preuves["bord_publie"] = f"127.0.0.1:{port}"

        def lancer_station() -> Station:
            return Station(Path(options.executable), coffre, portee, mandataire.port, autorite, captures,
                           journal_station, Path(options.qt_bin) if options.qt_bin else None)

        # ---------------------------------------------------------------- 1. connexion native
        afficher("1. Connexion native…")
        station = lancer_station()
        etapes["station"] = {"coffre": station.pret.get("coffre"), "preferences": "portée de test (registre)"}
        configuration = station.commande("configurer", serveur=URL_HERMES, memoriser=True)
        verifier(configuration.get("ok") is True, f"adresse refusée : {configuration}", ecarts)
        station.envoyer("connecter")
        autorisation = station.attendre_evenement("autorisation", 60)["url"]
        morceaux = urlsplit(autorisation)
        parametres = {cle: valeurs[0] for cle, valeurs in parse_qs(morceaux.query).items()}
        redirection = urlsplit(parametres.get("redirect_uri", ""))
        controles_url = {
            "origine": f"{morceaux.scheme}://{morceaux.netloc}{morceaux.path}",
            "provider": parametres.get("provider"),
            "code_challenge_method": parametres.get("code_challenge_method"),
            "longueur_code_challenge": len(parametres.get("code_challenge", "")),
            "longueur_state": len(parametres.get("state", "")),
            "redirect_uri_hote": redirection.hostname,
            "redirect_uri_chemin": redirection.path,
            "code_verifier_absent": "code_verifier" not in parametres,
        }
        etapes["autorisation"] = controles_url
        verifier(controles_url["origine"] == f"{URL_HERMES}/auth/native/authorize", "origine de l'autorisation", ecarts)
        verifier(controles_url["code_challenge_method"] == "S256", "PKCE S256 exigé", ecarts)
        verifier(controles_url["redirect_uri_hote"] == "127.0.0.1", "redirection vers 127.0.0.1 seulement", ecarts)
        verifier(controles_url["code_verifier_absent"], "le vérificateur PKCE ne doit jamais voyager", ecarts)
        with sync_playwright() as playwright:
            etapes["navigateur"] = connexion_navigateur(playwright, port, spki, identite, autorisation, captures)
        verifier("Connexion transmise" in etapes["navigateur"]["page_de_rappel"], "page de l'écouteur", ecarts)
        connexion = station.reponse("connecter", 120)
        etapes["connexion"] = connexion
        verifier(connexion.get("ok") is True, f"connexion : {connexion.get('etat')} {connexion.get('erreur')}", ecarts)
        # /api/auth/me rend le `sub` d'Authelia (identifiant opaque) et le nom affiché du propriétaire de test.
        verifier(connexion.get("nom") == NOM and connexion.get("identite") not in ("", "Inconnu", None),
                 f"identité lue par /api/auth/me : {connexion.get('nom')!r}", ecarts)
        verifier(connexion.get("entree_au_coffre") is True and bool(connexion.get("empreinte_rt")),
                 "jeton de rafraîchissement au coffre de test", ecarts)

        # ---------------------------------------------------------------- 2. rotation
        afficher("2. Deux rafraîchissements…")
        empreintes = [connexion.get("empreinte_rt")]
        for rang in (1, 2):
            rotation = station.commande("rafraichir", 120)
            etapes[f"rafraichissement_{rang}"] = rotation
            verifier(rotation.get("ok") is True and rotation.get("tourne") is True, f"rotation {rang}", ecarts)
            empreintes.append(rotation.get("empreinte_rt"))
        verifier(len(set(empreintes)) == 3, f"trois jetons distincts attendus : {empreintes}", ecarts)

        # ---------------------------------------------------------------- 3. JSON-RPC
        afficher("3. Discussion JSON-RPC…")
        discussion = station.commande("discussion", 240, texte="Bonjour Hermes, réponds en une phrase.")
        etapes["discussion"] = discussion
        verifier(discussion.get("ok") is True and discussion.get("reponse") == REPONSE_FACTICE,
                 f"réponse du modèle factice : {discussion.get('reponse')!r} {discussion.get('erreur')!r}", ecarts)

        # ---------------------------------------------------------------- 4. projet, veille, question
        afficher("4. Projet, veille du kanban, question…")
        releve = {"voie": "poste-claude", "source": "releve_factice", "version_cli": "0.0.0-factice",
                  "releve_le": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                  "modeles": [{"id": "factice-claude-1", "isDefault": True,
                               "supportedReasoningEfforts": ["low", "medium"], "defaultReasoningEffort": "medium",
                               "serviceTiers": ["default"]}],
                  "depots": [{"alias": "jetable"}]}
        simule(hermes, "releve-factice", json.dumps(releve))
        simule(hermes, "presence", "poste-simule")
        projet = station.commande("projet", 180, titre=TITRE, objectif="Écrire outil.py dans le dépôt jetable.",
                                  profil="base", depot="jetable", voie="poste-claude", reponses="proprietaire")
        etapes["projet"] = projet
        verifier(projet.get("ok") is True and bool(projet.get("exploration")), f"lancement : {projet}", ecarts)
        verifier(projet.get("origine") == "tableau_de_bord" or bool(projet.get("origine")), "origine du projet", ecarts)
        if projet.get("exploration"):
            marque = station.commande("marquer_veille", 60)
            reclame = simule(hermes, "reclamer", projet["tableau"], projet["exploration"])
            veille = station.commande("attendre_veille", 30, delai_ms=10000)
            etapes["veille"] = {"marque": marque, "reclamee": reclame.get("reclamee"), **veille}
            verifier(veille.get("ok") is True and 0 <= veille.get("relecture_apres_attente_ms", -1) < 3000,
                     f"relecture du détail sur événement de carte en moins de 3 s : {veille}", ecarts)
            posee = simule(hermes, "question", projet["tableau"], projet["exploration"], QUESTION)
            etapes["question_posee"] = {"etat": posee.get("etat")}
            verifier(posee.get("etat") == "escaladee", f"question escaladée au propriétaire : {posee}", ecarts)
            vue = station.commande("questions_attendre", 120, question=posee.get("question"))
            etapes["question_vue"] = {"ok": vue.get("ok"), "texte": vue.get("question", {}).get("texte")
                                      or vue.get("question", {}).get("question"), "capture": Path(vue.get("capture") or "-").name}
            verifier(vue.get("ok") is True, "question visible dans la page Questions", ecarts)
            reponse = station.commande("repondre", 120, question=posee.get("question"), reponse=REPONSE)
            etapes["question_repondue"] = {k: v for k, v in reponse.items() if k != "capture"}
            etapes["question_repondue"]["capture"] = Path(reponse.get("capture") or "-").name
            verifier(reponse.get("ok") is True and reponse.get("encore_ouverte") is False,
                     f"question fermée après la réponse : {reponse}", ecarts)
            verifier(reponse.get("exploration_statut") == "ready", f"carte reprise : {reponse.get('exploration_statut')}",
                     ecarts)

        # ---------------------------------------------------------------- 5. sauvegarde
        afficher("5. Sauvegarde chiffrée…")
        sauvegarde = station.commande("sauvegarde", 900, destination=str(travail / "hermes.acpb"),
                                      archive=str(travail / "hermes-dechiffree.zip"))
        etapes["sauvegarde"] = {k: v for k, v in sauvegarde.items() if k not in ("capture",)}
        etapes["sauvegarde"]["capture"] = Path(sauvegarde.get("capture") or "-").name
        verifier(sauvegarde.get("ok") is True, f"sauvegarde exportée et déchiffrée à l'identique : {sauvegarde}", ecarts)
        verifier(sauvegarde.get("zip_commence_par_PK") is True, "archive déchiffrée = zip", ecarts)
        acpb = travail / "hermes.acpb"
        if acpb.is_file():
            contenu = acpb.read_bytes()
            etapes["sauvegarde"]["fichier_chiffre_sha256"] = hashlib.sha256(contenu).hexdigest()
            etapes["sauvegarde"]["fichier_chiffre_commence_par_ACPB1"] = contenu.startswith(b"ACPB1\x01")
            verifier(not contenu[:4096].startswith(b"PK"), "le fichier sur disque n'est pas l'archive en clair", ecarts)
        verifier(not (travail / "hermes-dechiffree.zip").exists(), "archive en clair supprimée après comparaison", ecarts)

        # ---------------------------------------------------------------- 6. redémarrage
        afficher("6. Redémarrage : session reprise du coffre, sans navigateur…")
        etapes["capture_accueil"] = station.commande("capture", 60, page="HomePage", nom="accueil")
        etapes["capture_diagnostics"] = station.commande("capture", 60, page="DiagnosticsPage", nom="diagnostics")
        code = station.quitter()
        verifier(code == 0, f"code de sortie de la station : {code}", ecarts)
        station = lancer_station()
        reprise = station.commande("attendre_session", 120, delai_ms=90000)
        etapes["reprise"] = reprise
        verifier(reprise.get("ok") is True, f"session reprise du coffre : {reprise}", ecarts)
        verifier(bool(reprise.get("empreinte_rt")) and reprise.get("empreinte_rt") not in empreintes,
                 "le démarrage fait tourner le jeton mémorisé", ecarts)

        # ---------------------------------------------------------------- 7. déconnexion
        afficher("7. Déconnexion et rejeu de l'ancien jeton…")
        deconnexion = station.commande("deconnecter", 120)
        etapes["deconnexion"] = deconnexion
        verifier(deconnexion.get("ok") is True and deconnexion.get("entree_au_coffre_apres") is False,
                 f"déconnexion et coffre vidé : {deconnexion}", ecarts)
        verifier(deconnexion.get("rejeu_apres_deconnexion_statut") not in (200, 0, None),
                 f"l'ancien jeton refusé après la déconnexion : {deconnexion.get('rejeu_apres_deconnexion_statut')}",
                 ecarts)

        # ---------------------------------------------------------------- 8. hygiène
        afficher("8. Hygiène…")
        hygiene = station.commande("hygiene", 60, journal=str(journal_expurge))
        etapes["hygiene_station"] = hygiene
        verifier(hygiene.get("ok") is True, f"préférences et journal de la station sans jeton : {hygiene}", ecarts)
        code = station.quitter()
        station = None
        verifier(code == 0, f"code de sortie de la station : {code}", ecarts)

        externe: Dict[str, Any] = {}
        texte_journal = (journal_expurge.read_text(encoding="utf-8", errors="replace") if journal_expurge.exists() else "")
        texte_journal += journal_station.read_text(encoding="utf-8", errors="replace") if journal_station.exists() else ""
        externe["formes_de_secret_journal_station"] = len(FORMES_DE_SECRET.findall(texte_journal))
        export = travail / "portee.reg"
        sortie = subprocess.run(["reg", "export", f"HKCU\\Software\\{portee}", str(export), "/y"],
                                capture_output=True, text=True)
        texte_registre = export.read_text(encoding="utf-16", errors="replace") if export.exists() else ""
        externe["registre_exporte"] = sortie.returncode == 0
        externe["cles_registre"] = len(re.findall(r'^"[^"]+"=', texte_registre, re.M))
        externe["formes_de_secret_registre"] = len(FORMES_DE_SECRET.findall(texte_registre))
        cmdkey = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, errors="replace").stdout
        externe["entrees_coffre_de_test_restantes"] = cmdkey.count(coffre)
        lignes = lignes_du_bord(bord)
        texte_bord = json.dumps(lignes, ensure_ascii=False)
        externe["requetes_du_bord"] = len(lignes)
        externe["tunnels_websocket"] = sorted({l["chemin"] for l in lignes if l.get("tunnel") == "websocket"})
        externe["hotes_websocket"] = sorted({l.get("hote") for l in lignes if l.get("tunnel") == "websocket"})
        externe["formes_de_secret_bord"] = len(FORMES_DE_SECRET.findall(texte_bord))
        externe["mandataire"] = {"tunnels": mandataire.tunnels, "refus": mandataire.refus}
        journal_hermes = docker("logs", hermes, verifier=False)
        externe["formes_de_secret_hermes"] = len(FORMES_DE_SECRET.findall(journal_hermes.stdout + journal_hermes.stderr))
        etapes["hygiene_externe"] = externe
        verifier(externe["formes_de_secret_journal_station"] == 0, "journal de la station sans forme de secret", ecarts)
        verifier(externe["registre_exporte"] and externe["formes_de_secret_registre"] == 0,
                 "registre de la portée de test sans forme de secret", ecarts)
        verifier(externe["entrees_coffre_de_test_restantes"] == 0, "entrée du coffre de test absente (cmdkey)", ecarts)
        verifier(externe["formes_de_secret_bord"] == 0, "journal du bord sans forme de secret", ecarts)
        verifier(not mandataire.refus, f"aucune sortie hors de la pile : {mandataire.refus}", ecarts)
        # La station ne parle jamais au fournisseur d'identité : seul le navigateur le fait.
        verifier(f"{HOTE_IDENTITE}:443" not in mandataire.tunnels, "aucune connexion de la station à Authelia", ecarts)
        verifier("/api/ws" in externe["tunnels_websocket"], "passerelle JSON-RPC passée par le bord", ecarts)
        verifier(externe["hotes_websocket"] == [HOTE_HERMES], "WebSockets sous l'hôte public de Hermes", ecarts)
    except Exception as exc:  # noqa: BLE001 — tout échec est consigné et rend un code non nul
        ecarts.append(f"interruption : {type(exc).__name__}: {str(exc)[:1500]}")
        afficher(f"  INTERRUPTION : {exc}")
    finally:
        if station is not None:
            try:
                station.processus.kill()
            except OSError:
                pass
        if mandataire is not None:
            mandataire.fermer()
        subprocess.run(["reg", "delete", f"HKCU\\Software\\{portee}", "/f"], capture_output=True)
        # Filet : l'entrée de test du coffre ne doit pas survivre, même à un échec.
        for cible in re.findall(rf"target=({re.escape(coffre)}\S*)",
                                subprocess.run(["cmdkey", "/list"], capture_output=True, text=True,
                                               errors="replace").stdout):
            subprocess.run(["cmdkey", f"/delete:{cible}"], capture_output=True)
        if not options.garder:
            pile.nettoyer()
            # Sauvegarde chiffrée de la pile de test, export du registre, journaux : rien ne reste.
            shutil.rmtree(travail, ignore_errors=True)
        else:
            for fichier in travail.glob("*.zip"):
                fichier.unlink(missing_ok=True)

    preuves["captures"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(captures.glob("*.png"))}
    preuves["ecarts"] = ecarts
    preuves["resultat"] = "réussi" if not ecarts else "échoué"
    rapport = json.dumps(preuves, ensure_ascii=False, indent=2)
    if FORMES_DE_SECRET.search(rapport):
        ecarts.append("le rapport lui-même contient une forme de secret : il n'est pas écrit")
        afficher("ÉCART : forme de secret dans le rapport ; rapport non écrit")
        return 1
    Path(options.preuves).write_text(rapport, encoding="utf-8")
    afficher(f"Rapport : {options.preuves} — {preuves['resultat']} ({len(ecarts)} écart(s))")
    return 0 if not ecarts else 1


def main() -> int:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("--image-tests", required=True)
    arguments.add_argument("--image-identite", required=True)
    arguments.add_argument("--executable", required=True, help="acp_desktop_e2e.exe compilé")
    arguments.add_argument("--qt-bin", default="", help="répertoire bin de Qt (DLL)")
    arguments.add_argument("--preuves", required=True)
    arguments.add_argument("--captures", required=True)
    arguments.add_argument("--garder", action="store_true", help="garder la pile après le parcours")
    return parcours(arguments.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
