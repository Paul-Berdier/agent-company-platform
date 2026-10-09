"""Client HTTPS du poste (cahier P5 § 4.1, décision D61) et classement des réponses (§ 4.4, § 4.5)."""

from __future__ import annotations

import json
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from acp_poste.client_hermes import ClientHermes, ErreurReseau, OptionsClient, ReponseHTTP
from acp_poste.protocole import (
    CODE_REFUSE,
    JETON_REFUSE,
    HermesIndisponible,
    HorsContrat,
    JetonRefuse,
    PosteRevoque,
    ProtocoleIncompatible,
    Refus,
    TropFrequent,
    classer,
)
from acp_poste_contrat.machine import CORPS_401_COUTURE


class _Scenario(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    reponse = (200, {"ok": True}, {})
    retard = 0.0
    vues: list = []

    def log_message(self, *_a):
        return

    def _servir(self):
        longueur = int(self.headers.get("Content-Length") or 0)
        type(self).vues.append({"chemin": self.path, "entetes": dict(self.headers.items()),
                                "corps": self.rfile.read(longueur)})
        time.sleep(type(self).retard)
        statut, corps, entetes = type(self).reponse
        donnees = corps if isinstance(corps, bytes) else json.dumps(corps).encode()
        self.send_response(statut)
        for cle, valeur in entetes.items():
            self.send_header(cle, valeur)
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    do_GET = do_POST = _servir


@pytest.fixture
def serveur(autorite):
    gestionnaire = type("G", (_Scenario,), {"vues": []})
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), gestionnaire)
    serveur.daemon_threads = True
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexte.load_cert_chain(autorite.fichier_certificat, autorite.fichier_cle)
    serveur.socket = contexte.wrap_socket(serveur.socket, server_side=True)
    fil = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    fil.start()
    serveur.gestionnaire = gestionnaire
    try:
        yield serveur
    finally:
        serveur.shutdown()
        serveur.server_close()


def client(serveur, autorite, **options) -> ClientHermes:
    return ClientHermes(f"https://hermes-acp.test:{serveur.server_address[1]}", delai_connexion_s=3,
                        options=OptionsClient(fichier_autorite=str(autorite.fichier_ac),
                                              resolution={"hermes-acp.test": "127.0.0.1"}), **options)


def test_https_exige_hors_boucle():
    for origine in ("http://hermes.example", "http://127.0.0.1:9119", "ftp://h.test"):
        with pytest.raises(ErreurReseau, match="HTTPS exigé"):
            ClientHermes(origine, delai_connexion_s=2)


def test_en_tetes(serveur, autorite):
    from acp_poste.jeton import Jeton
    from acp_poste.protocole import Protocole

    serveur.gestionnaire.reponse = (200, {"maintenant": "2026-09-26T09:14:02Z", "etat_machine": "actif",
                                          "pause_reclamations": False, "ordres": [], "carte": None,
                                          "remplace": False, "prochaine_attente_s": 0}, {})
    jeton = Jeton("acpm_" + "h" * 43)
    Protocole(client(serveur, autorite)).reclamer(jeton, acquittes=[3], attente_max_s=5, politique_valide=True)
    vue = serveur.gestionnaire.vues[0]
    entetes = {k.lower(): v for k, v in vue["entetes"].items()}
    assert entetes["authorization"] == "Bearer " + "acpm_" + "h" * 43
    assert entetes["content-type"] == "application/json" and entetes["accept"] == "application/json"
    assert entetes["user-agent"] == "acp-poste/1.0.0 (acp-machine/1)"
    assert entetes["x-acp-protocole"] == "acp-machine/1"
    assert "cookie" not in entetes
    assert json.loads(vue["corps"]) == {"protocole": "acp-machine/1", "version_poste": "1.0.0", "peut_executer": False,
                                        "ordres_acquittes": [3], "attente_max_s": 5, "politique_valide": True}


def test_redirection_jamais_suivie(serveur, autorite):
    serveur.gestionnaire.reponse = (302, b"", {"Location": "https://ailleurs.example/"})
    reponse = client(serveur, autorite).echanger("POST", "/x", corps=b"{}", delai_lecture_s=5)
    assert reponse.statut == 302 and len(serveur.gestionnaire.vues) == 1
    with pytest.raises(Refus, match="Redirection refusée"):
        classer(reponse, 200)


def test_reponse_bornee(serveur, autorite):
    serveur.gestionnaire.reponse = (200, b"x" * (64 * 1024 + 1), {})
    with pytest.raises(ErreurReseau, match="trop volumineuse"):
        client(serveur, autorite).echanger("GET", "/", delai_lecture_s=5)


def test_delais(serveur, autorite):
    serveur.gestionnaire.retard = 2.5
    debut = time.monotonic()
    with pytest.raises(ErreurReseau, match="n'a pas répondu"):
        client(serveur, autorite).echanger("GET", "/", delai_lecture_s=1)
    assert time.monotonic() - debut < 2.4


def test_mandataire_d_environnement_ignore(serveur, autorite, monkeypatch):
    for nom in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "HTTP_PROXY"):
        monkeypatch.setenv(nom, "http://127.0.0.1:9")
    reponse = client(serveur, autorite).echanger("GET", "/api/health", delai_lecture_s=5)
    assert reponse.statut == 200 and serveur.gestionnaire.vues[0]["chemin"] == "/api/health"


def test_tls_invalide_refus_francais(serveur):
    """Sans l'autorité de test, le certificat du faux Hermes n'est pas reconnu : refus français, rien d'échangé."""
    inconnu = ClientHermes(f"https://hermes-acp.test:{serveur.server_address[1]}", delai_connexion_s=3,
                           options=OptionsClient(resolution={"hermes-acp.test": "127.0.0.1"}))
    with pytest.raises(ErreurReseau) as exc:
        inconnu.echanger("GET", "/api/health", delai_lecture_s=5)
    assert str(exc.value).startswith("Certificat de Hermes refusé (autorité de certification inconnue")
    assert "diagnostic --reseau" in str(exc.value)
    assert serveur.gestionnaire.vues == []


def test_nom_d_hote_verifie(serveur, autorite):
    autre = ClientHermes(f"https://autre-hote.test:{serveur.server_address[1]}", delai_connexion_s=3,
                         options=OptionsClient(fichier_autorite=str(autorite.fichier_ac),
                                               resolution={"autre-hote.test": "127.0.0.1"}))
    with pytest.raises(ErreurReseau, match="ne correspond pas au nom d'hôte"):
        autre.echanger("GET", "/", delai_lecture_s=5)


# ------------------------------------------------------------------ classement des réponses


def _r(statut: int, corps, entetes=None) -> ReponseHTTP:
    return ReponseHTTP(statut=statut, corps=json.dumps(corps).encode() if not isinstance(corps, bytes) else corps,
                       entetes=entetes or {})


def test_401_poste_revoque_efface_le_jeton():
    corps = {"detail": {"code": "poste_revoque", "message": "Poste révoqué par le propriétaire le 26/09/2026 11:14 : "
                                                            "jeton local effacé."}}
    with pytest.raises(PosteRevoque) as exc:
        classer(_r(401, corps), 200)
    assert exc.value.message.startswith("Poste révoqué par le propriétaire")


def test_401_couture_garde_le_jeton_code_4():
    with pytest.raises(JetonRefuse) as exc:
        classer(_r(401, dict(CORPS_401_COUTURE)), 200)
    assert exc.value.message == JETON_REFUSE and "gardé" in exc.value.message
    with pytest.raises(JetonRefuse) as exc:
        classer(_r(401, dict(CORPS_401_COUTURE)), 201, enrolement=True)
    assert exc.value.message == CODE_REFUSE
    with pytest.raises(JetonRefuse):  # tout autre 401 reste ambigu : jeton gardé
        classer(_r(401, {"detail": {"code": "non_authentifie", "message": "Jeton absent."}}), 200)


def test_429_retry_after():
    corps = {"detail": {"code": "trop_frequent", "message": "Inventaire trop fréquent : prochain envoi possible dans "
                                                            "42 s."}}
    with pytest.raises(TropFrequent) as exc:
        classer(_r(429, corps, {"retry-after": "42"}), 200)
    assert exc.value.retry_after == 42
    with pytest.raises(TropFrequent) as exc:
        classer(_r(429, b"", {}), 200)
    assert exc.value.retry_after == 60


def test_409_protocole_arret():
    corps = {"detail": {"code": "protocole_incompatible", "message": "Protocole du poste incompatible."}}
    with pytest.raises(ProtocoleIncompatible):
        classer(_r(409, corps), 200)


def test_503_et_reponse_illisible():
    with pytest.raises(HermesIndisponible, match="base du greffon illisible"):
        classer(_r(503, {"error": "x"}), 200)
    with pytest.raises(HorsContrat):
        classer(_r(200, b"<html>"), 200)
