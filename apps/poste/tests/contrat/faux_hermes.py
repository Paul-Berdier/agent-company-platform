"""FAUX Hermes pour les tests de contrat du poste (cahier P5 § 14.2) : serveur HTTPS de la bibliothèque standard, derrière
une autorité de certification de TEST générée par ``cryptography`` (jamais committée, détruite avec le test).

Il implémente les trois routes machine ``acp-machine/1`` avec les **modèles du contrat partagé**
(``acp_poste_contrat.machine`` et ``inventaire``) et les règles du § 4 : code d'enrôlement à usage unique, jeton
haché (SHA-256, jamais gardé en clair), poste « à confirmer » puis actif, attente longue avec réveil (ordre,
révocation, remplacement), ordres au moins une fois, inventaire validé et balayé (« aucun identifiant »), 422, 429 avec
``Retry-After``. Ses réponses partent des **exemples partagés** avec le vrai greffon
(``hermes/tests/outils/fixtures_machine/``) et sont validées par le contrat avant l'envoi : une divergence entre le
faux et le vrai greffon fait échouer l'un des deux jeux de tests.

Les refus de la couture d'authentification de Hermes (401 anglais et ambigu, 503) sont reproduits à l'identique
(``CORPS_401_COUTURE``). Des pannes s'injectent par :meth:`FauxHermes.injecter`.
"""

from __future__ import annotations

import datetime as dt
import hmac
import ipaddress
import json
import secrets
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from acp_poste_contrat import machine as contrat
from acp_poste_contrat.inventaire import identifiant_trouve, valider_inventaire

RACINE = Path(__file__).resolve().parents[4]
EXEMPLES = RACINE / "hermes" / "tests" / "outils" / "fixtures_machine"
HOTE = "hermes-acp.test"


def exemple(nom: str) -> Any:
    return json.loads((EXEMPLES / f"{nom}.json").read_text(encoding="utf-8"))


def _iso(instant: float | None = None) -> str:
    return dt.datetime.fromtimestamp(int(instant if instant is not None else time.time()),
                                     tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AutoriteDeTest:
    """Autorité de test et certificat du serveur ``hermes-acp.test`` (et ``127.0.0.1``), valables deux jours."""

    def __init__(self, dossier: Path) -> None:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

        dossier.mkdir(parents=True, exist_ok=True)
        maintenant = dt.datetime.now(dt.timezone.utc)
        cle_ac = ec.generate_private_key(ec.SECP256R1())
        nom_ac = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Autorite de test ACP (jetable)")])
        ac = (x509.CertificateBuilder().subject_name(nom_ac).issuer_name(nom_ac).public_key(cle_ac.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(maintenant - dt.timedelta(hours=1))
              .not_valid_after(maintenant + dt.timedelta(days=2))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                           content_commitment=False, key_encipherment=False, data_encipherment=False,
                                           key_agreement=False, encipher_only=False, decipher_only=False),
                             critical=True)
              .sign(cle_ac, hashes.SHA256()))
        cle = ec.generate_private_key(ec.SECP256R1())
        serveur = (x509.CertificateBuilder()
                   .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOTE)])).issuer_name(nom_ac)
                   .public_key(cle.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(maintenant - dt.timedelta(hours=1))
                   .not_valid_after(maintenant + dt.timedelta(days=2))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName(HOTE),
                                                               x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                                  critical=False)
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .sign(cle_ac, hashes.SHA256()))
        self.fichier_ac = dossier / "autorite-de-test.pem"
        self.fichier_certificat = dossier / "serveur.pem"
        self.fichier_cle = dossier / "serveur.key"
        self.fichier_ac.write_bytes(ac.public_bytes(serialization.Encoding.PEM))
        self.fichier_certificat.write_bytes(serveur.public_bytes(serialization.Encoding.PEM))
        self.fichier_cle.write_bytes(cle.private_bytes(serialization.Encoding.PEM,
                                                       serialization.PrivateFormat.PKCS8,
                                                       serialization.NoEncryption()))


class _Serveur(ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        """Un poste qui coupe sa connexion (arrêt, attente remplacée) n'est pas une erreur du faux."""
        import sys

        if isinstance(sys.exc_info()[1], (ssl.SSLError, ConnectionError, OSError)):
            return
        super().handle_error(request, client_address)


class FauxHermes:
    """État du faux greffon et contrôles du test (codes, confirmation, révocation, ordres, pannes)."""

    def __init__(self, autorite: AutoriteDeTest, *, attente_a_confirmer_s: int = 1,
                 intervalle_inventaire_s: int = 60) -> None:
        self.autorite = autorite
        self.attente_a_confirmer_s = attente_a_confirmer_s
        self.intervalle_inventaire_s = intervalle_inventaire_s
        self.condition = threading.Condition()
        self.codes: dict[str, dict[str, Any]] = {}
        self.machines: dict[str, dict[str, Any]] = {}
        self.ordres: list[dict[str, Any]] = []
        self.inventaires: list[dict[str, Any]] = []
        self.requetes: list[dict[str, Any]] = []
        self.presence: dict[str, float] = {}
        self.generations: dict[str, int] = {}
        self.en_attente: dict[str, int] = {}
        self.pannes: list[str] = []
        self.serveur: ThreadingHTTPServer | None = None
        self._fil: threading.Thread | None = None

    # ------------------------------------------------------------------ cycle de vie
    def demarrer(self) -> "FauxHermes":
        contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexte.load_cert_chain(self.autorite.fichier_certificat, self.autorite.fichier_cle)
        gestionnaire = type("Gestionnaire", (_Gestionnaire,), {"hermes": self})
        self.serveur = _Serveur(("127.0.0.1", 0), gestionnaire)
        self.serveur.daemon_threads = True
        self.serveur.socket = contexte.wrap_socket(self.serveur.socket, server_side=True)
        self._fil = threading.Thread(target=self.serveur.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._fil.start()
        return self

    def arreter(self) -> None:
        if self.serveur is not None:
            with self.condition:
                self.pannes.clear()
                self.condition.notify_all()
            self.serveur.shutdown()
            self.serveur.server_close()

    @property
    def port(self) -> int:
        return self.serveur.server_address[1]

    @property
    def origine(self) -> str:
        return f"https://{HOTE}:{self.port}"

    def options_client(self):
        from acp_poste.client_hermes import OptionsClient

        return OptionsClient(fichier_autorite=str(self.autorite.fichier_ac), resolution={HOTE: "127.0.0.1"})

    # ------------------------------------------------------------------ contrôles
    def creer_code(self, *, validite_s: int = 600) -> str:
        code = "acpe_" + secrets.token_urlsafe(32)
        with self.condition:
            self.codes[contrat.empreinte_jeton(code)] = {"expire": time.time() + validite_s, "utilise": False}
        return code

    def machine(self) -> tuple[str, dict[str, Any]] | None:
        with self.condition:
            for identifiant, ligne in self.machines.items():
                if ligne["etat"] != "revoque":
                    return identifiant, ligne
        return None

    def confirmer(self, machine_id: str) -> None:
        with self.condition:
            self.machines[machine_id]["etat"] = "actif"
            self.condition.notify_all()

    def revoquer_pendant_l_attente(self, machine_id: str, delai_s: float = 30) -> bool:
        """Révoque dès que le poste est dans une attente longue (il doit alors recevoir ``poste_revoque``)."""
        with self.condition:
            if not self.attendre(lambda: self.en_attente.get(machine_id, 0) > 0, delai_s):
                return False
            self.revoquer(machine_id)
            return True

    def revoquer(self, machine_id: str) -> None:
        with self.condition:
            self.machines[machine_id]["etat"] = "revoque"
            self.machines[machine_id]["revoque_le"] = time.time()
            self.presence.pop(machine_id, None)
            self.condition.notify_all()

    def ordonner(self, machine_id: str, genre: str = "releve") -> int:
        with self.condition:
            identifiant = len(self.ordres) + 1
            self.ordres.append({"id": identifiant, "machine": machine_id, "genre": genre, "cree_le": time.time(),
                                "livre": False, "acquitte": False})
            self.condition.notify_all()
            return identifiant

    def injecter(self, nature: str, fois: int = 1) -> None:
        """``503``, ``401_couture``, ``409_protocole``, ``hors_contrat`` (réponse de ``reclamer`` avec un champ
        inconnu), ``coupure``."""
        with self.condition:
            self.pannes.extend([nature] * fois)

    def attendre(self, predicat, delai_s: float) -> bool:
        echeance = time.monotonic() + delai_s
        with self.condition:
            while not predicat():
                reste = echeance - time.monotonic()
                if reste <= 0:
                    return False
                self.condition.wait(min(reste, 0.1))
        return True

    # ------------------------------------------------------------------ logique des routes
    def _machine_du_porteur(self, porteur: str) -> tuple[str, dict[str, Any]] | None:
        if not contrat.JETON_MACHINE.fullmatch(porteur or ""):
            return None
        calcule = contrat.empreinte_jeton(porteur)
        trouve = None
        for identifiant, ligne in self.machines.items():  # toutes les lignes, sans sortie anticipée
            if hmac.compare_digest(calcule, ligne["empreinte_jeton"]) and ligne["etat"] != "revoque":
                trouve = (identifiant, ligne)
        return trouve

    def _dus(self, machine_id: str) -> list[dict[str, Any]]:
        return [o for o in self.ordres if o["machine"] == machine_id and not o["acquitte"]]


def _erreur(code: str, message: str) -> tuple[int, dict[str, Any]]:
    corps = {"detail": {"code": code, "message": message}}
    contrat.valider(contrat.ErreurMachine, corps, quoi="erreur du faux")
    statuts = {"poste_revoque": 401, "poste_a_confirmer": 403, "poste_deja_enrole": 409,
               "protocole_incompatible": 409, "requete_refusee": 422, "trop_frequent": 429}
    return statuts[code], corps


class _Gestionnaire(BaseHTTPRequestHandler):
    hermes: FauxHermes
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args) -> None:  # aucun journal (et donc aucun jeton) sur la console des tests
        return

    def _repondre(self, statut: int, corps: Any, entetes: dict[str, str] | None = None) -> None:
        donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
        self.send_response(statut)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(donnees)))
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            self._repondre(200, {"status": "ok"})
        else:
            self._repondre(404, {"detail": "Not Found"})

    def do_POST(self) -> None:  # noqa: N802
        hermes = self.hermes
        longueur = int(self.headers.get("Content-Length") or 0)
        brut = self.rfile.read(min(longueur, contrat.TAILLE_MAX_INVENTAIRE + 1))
        porteur = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        with hermes.condition:
            hermes.requetes.append({"chemin": self.path, "entetes": dict(self.headers.items()), "corps": brut})
            panne = hermes.pannes.pop(0) if hermes.pannes and self.path in contrat.ROUTES else None
        if panne == "coupure":
            self.close_connection = True
            self.connection.shutdown(2)
            return
        if panne == "503":
            self._repondre(503, {"error": "provider_unavailable", "detail": "Authentication provider unavailable"})
            return
        if panne == "401_couture":
            self._repondre(401, dict(contrat.CORPS_401_COUTURE))
            return
        if panne == "409_protocole":
            self._repondre(*_erreur("protocole_incompatible", "Protocole du poste « acp-machine/9 » incompatible "
                                    "avec le greffon (acp-machine/1 attendu) : mettez le poste à jour."))
            return
        try:
            corps = json.loads(brut.decode("utf-8"))
        except ValueError:
            self._repondre(*_erreur("requete_refusee", "Requête du poste refusée : corps JSON illisible."))
            return
        if self.path == contrat.ROUTE_ENROLEMENT:
            self._enrolement(porteur, corps)
        elif self.path == contrat.ROUTE_RECLAMER:
            self._reclamer(porteur, corps, hors_contrat=panne == "hors_contrat")
        elif self.path == contrat.ROUTE_INVENTAIRE:
            self._inventaire(porteur, corps)
        else:
            self._repondre(401, dict(contrat.CORPS_401_COUTURE))

    def _enrolement(self, porteur: str, corps: dict[str, Any]) -> None:
        hermes = self.hermes
        with hermes.condition:
            code = hermes.codes.get(contrat.empreinte_jeton(porteur)) if contrat.CODE_ENROLEMENT.fullmatch(porteur) \
                else None
            if code is None or code["utilise"] or code["expire"] < time.time():
                self._repondre(401, dict(contrat.CORPS_401_COUTURE))
                return
            try:
                requete = contrat.valider(contrat.RequeteEnrolement, corps, quoi="Requête refusée")
            except ValueError as exc:
                self._repondre(*_erreur("requete_refusee", str(exc)[:500]))
                return
            if any(l["etat"] == "actif" for l in hermes.machines.values()):
                self._repondre(*_erreur("poste_deja_enrole", "Un poste est déjà enrôlé : révoquez-le d'abord."))
                return
            for ligne in hermes.machines.values():
                if ligne["etat"] == "a_confirmer":
                    ligne["etat"] = "revoque"
            code["utilise"] = True
            jeton = "acpm_" + secrets.token_urlsafe(32)
            machine_id = "m" + secrets.token_hex(6)[:11]
            hermes.machines[machine_id] = {"empreinte_jeton": contrat.empreinte_jeton(jeton), "etat": "a_confirmer",
                                           "nom": requete.nom, "empreinte": contrat.empreinte_courte(
                                               contrat.empreinte_jeton(jeton))}
            reponse = dict(exemple("enrolement_reponse"), machine_id=machine_id, jeton=jeton,
                           empreinte=hermes.machines[machine_id]["empreinte"])
            contrat.valider(contrat.ReponseEnrolement, reponse, quoi="réponse du faux")
            hermes.condition.notify_all()
        self._repondre(201, reponse)

    def _reponse_reclamer(self, etat: str, ordres: list, *, remplace: bool = False, prochaine: int = 0,
                          hors_contrat: bool = False) -> None:
        reponse = dict(exemple("reclamer_reponse"), maintenant=_iso(), etat_machine=etat, pause_reclamations=False,
                       ordres=[{"id": o["id"], "genre": o["genre"], "cree_le": _iso(o["cree_le"])} for o in ordres],
                       carte=None, remplace=remplace, prochaine_attente_s=prochaine)
        contrat.valider(contrat.ReponseReclamer, reponse, quoi="réponse du faux")
        if hors_contrat:
            reponse["champ_inconnu_du_contrat"] = True
        self._repondre(200, reponse)

    def _reclamer(self, porteur: str, corps: dict[str, Any], *, hors_contrat: bool) -> None:
        hermes = self.hermes
        with hermes.condition:
            trouve = hermes._machine_du_porteur(porteur)
            if trouve is None:
                self._repondre(401, dict(contrat.CORPS_401_COUTURE))
                return
            machine_id, ligne = trouve
            try:
                requete = contrat.valider(contrat.RequeteReclamer, corps, quoi="Requête refusée")
            except ValueError as exc:
                self._repondre(*_erreur("requete_refusee", str(exc)[:500]))
                return
            for ordre in hermes.ordres:
                if ordre["machine"] == machine_id and ordre["id"] in requete.ordres_acquittes:
                    ordre["acquitte"] = True
            ligne["politique_valide"] = requete.politique_valide
            if ligne["etat"] == "a_confirmer":
                self._reponse_reclamer("a_confirmer", [], prochaine=hermes.attente_a_confirmer_s,
                                       hors_contrat=hors_contrat)
                return
            hermes.presence[machine_id] = time.time()
            generation = hermes.generations.get(machine_id, 0) + 1
            hermes.generations[machine_id] = generation
            hermes.condition.notify_all()
            echeance = time.monotonic() + requete.attente_max_s
            hermes.en_attente[machine_id] = hermes.en_attente.get(machine_id, 0) + 1
            try:
                self._attendre(hermes, machine_id, ligne, generation, echeance, hors_contrat)
            finally:
                hermes.en_attente[machine_id] -= 1

    def _attendre(self, hermes, machine_id, ligne, generation, echeance, hors_contrat) -> None:
        while True:
            if ligne["etat"] == "revoque":
                self._repondre(*_erreur("poste_revoque", "Poste révoqué par le propriétaire le "
                                        f"{dt.datetime.now().strftime('%d/%m/%Y %H:%M')} : jeton local effacé."))
                return
            if hermes.generations.get(machine_id) != generation:
                self._reponse_reclamer("actif", [], remplace=True, hors_contrat=hors_contrat)
                return
            dus = hermes._dus(machine_id)
            if dus:
                for ordre in dus:
                    ordre["livre"] = True
                self._reponse_reclamer("actif", dus, hors_contrat=hors_contrat)
                return
            reste = echeance - time.monotonic()
            if reste <= 0:
                self._reponse_reclamer("actif", [], hors_contrat=hors_contrat)
                return
            hermes.condition.wait(min(reste, 0.2))

    def _inventaire(self, porteur: str, corps: dict[str, Any]) -> None:
        hermes = self.hermes
        with hermes.condition:
            trouve = hermes._machine_du_porteur(porteur)
            if trouve is None:
                self._repondre(401, dict(contrat.CORPS_401_COUTURE))
                return
            machine_id, ligne = trouve
            if ligne["etat"] == "a_confirmer":
                self._repondre(*_erreur("poste_a_confirmer", f"Poste en attente de confirmation : confirmez "
                                        f"l'empreinte {ligne['empreinte']} sur la page Poste."))
                return
            trouve_id = identifiant_trouve(corps)
            if trouve_id:
                self._repondre(*_erreur("requete_refusee", f"Requête du poste refusée : {trouve_id[:300]}."))
                return
            try:
                inventaire = valider_inventaire(corps)
            except ValueError as exc:
                self._repondre(*_erreur("requete_refusee", str(exc)[:500]))
                return
            releve_du = any(o["machine"] == machine_id and o["genre"] == "releve" and o["livre"] and not o["acquitte"]
                            for o in hermes.ordres)
            derniers = [i["recu"] for i in hermes.inventaires if i["machine"] == machine_id]
            if derniers and not releve_du and time.time() - derniers[-1] < hermes.intervalle_inventaire_s:
                attente = int(hermes.intervalle_inventaire_s - (time.time() - derniers[-1])) + 1
                statut, erreur = _erreur("trop_frequent", f"Inventaire trop fréquent : prochain envoi possible dans "
                                         f"{attente} s.")
                self._repondre(statut, erreur, {"Retry-After": str(attente)})
                return
            for ordre in hermes.ordres:
                if ordre["machine"] == machine_id and ordre["genre"] == "releve" and ordre["livre"]:
                    ordre["acquitte"] = True
            numero = len(hermes.inventaires) + 1
            hermes.inventaires.append({"machine": machine_id, "recu": time.time(), "corps": corps,
                                       "inventaire": inventaire})
            releves = {r.voie: numero * 10 + rang for rang, r in enumerate(inventaire.releves, 1)}
            alertes = [f"Relevé Codex : liste de secours (catalogue embarqué de Codex {r.version_cli})."
                       for r in inventaire.releves if r.origine_liste == "catalogue_embarque"]
            reponse = dict(exemple("inventaire_reponse"), recu_le=_iso(), releves=releves, alertes=alertes)
            contrat.valider(contrat.ReponseInventaire, reponse, quoi="réponse du faux")
            hermes.condition.notify_all()
        self._repondre(200, reponse)
