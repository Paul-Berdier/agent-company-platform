"""Bridge testé sans réseau personnel : réponses au contrat et coffre en mémoire."""
import json
import time
from uuid import uuid4

import pytest

from acp_poste.cli import main
from acp_poste.client_hermes import ClientHermes, ErreurReseau, ReponseHTTP
from acp_poste.obsidian_bridge import BridgeCoffre, ProtocoleCoffre, RefusBridge, origine_valide
from acp_poste_contrat import coffre as contrat

TOKEN = "acpct_" + "a" * 43
CODE = "acpce_" + "b" * 43

class Client:
    def __init__(self):
        self.calls = []
        self.responses = []

    def echanger(self, method, route, **kw):
        self.calls.append((method, route, kw))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        status, data = response
        return ReponseHTTP(status, json.dumps(data).encode(), {})

@pytest.fixture
def bridge(poste, tmp_path):
    c = Client()
    b = BridgeCoffre(poste.contexte(), fabrique_client=lambda *a, **kw: c)
    b.creer(tmp_path / "Notes ACP")
    return b, c


def association(b, c):
    notes = b.charger()
    c.responses.append((201, {"protocole": contrat.PROTOCOLE, "coffre_id": notes.coffre_id,
                            "jeton": TOKEN, "empreinte": "ABCD-0123", "etat": "a_confirmer"}))
    assert b.associer("https://hermes.test", CODE) == "ABCD-0123"
    return notes


def test_association_distincte_lie_origine_et_identite(bridge, poste):
    b, c = bridge
    poste.coffre.ecrire("jeton-machine", "INCHANGE")
    notes = association(b, c)
    assert poste.coffre.lire("jeton-machine") == "INCHANGE"
    protected = json.loads(poste.coffre.lire("jeton-coffre"))
    assert protected["origine"] == "https://hermes.test"
    assert protected["coffre_id"] == notes.coffre_id
    assert TOKEN not in b.configuration.read_text(encoding="utf-8")
    assert CODE not in b.configuration.read_text(encoding="utf-8")
    assert c.calls[0][1] == contrat.ROUTE_ENROLEMENT
    assert c.calls[0][2]["entetes"]["Authorization"] == "Bearer " + CODE
    assert "racine" not in c.calls[0][2]["corps"].decode()
    with pytest.raises(RefusBridge):
        b.associer("https://autre.test", CODE)


@pytest.mark.parametrize("url", ["http://hermes.test", "https://a:b@hermes.test", "https://hermes.test/x",
                                 "https://hermes.test?secret=x", "https://hermes.test/#x", "https://hermes.test:0"])
def test_origines_refusees(url):
    with pytest.raises(RefusBridge):
        origine_valide(url)


def test_confirmation_et_identite_operation_exigees(bridge):
    b, c = bridge
    notes = association(b, c)
    op = {"id_operation": str(uuid4()), "coffre_id": notes.coffre_id, "action": "creer",
          "parametres": {"chemin": "Interdit.md", "contenu": "non"}, "expire_le": int(time.time()) + 600}
    c.responses.append((200, {"protocole": contrat.PROTOCOLE, "etat": "a_confirmer", "operation": op}))
    with pytest.raises(RefusBridge):
        b.cycle(ProtocoleCoffre(c), notes, TOKEN, attente=0)
    assert not (notes.racine / "Interdit.md").exists()
    op["coffre_id"] = str(uuid4())
    c.responses.append((200, {"protocole": contrat.PROTOCOLE, "etat": "actif", "operation": op}))
    with pytest.raises(RefusBridge):
        b.cycle(ProtocoleCoffre(c), notes, TOKEN, attente=0)
    assert not (notes.racine / "Interdit.md").exists()


def test_coupure_resultat_repris_sans_reexecution(bridge):
    b, c = bridge
    notes = association(b, c)
    op = {"id_operation": str(uuid4()), "coffre_id": notes.coffre_id, "action": "creer",
          "parametres": {"chemin": "Preuve.md", "contenu": "une fois"}, "expire_le": int(time.time()) + 600}
    c.responses.extend([(200, {"protocole": contrat.PROTOCOLE, "etat": "actif", "operation": op}), ErreurReseau("test")])
    with pytest.raises(RefusBridge, match="conservé"):
        b.cycle(ProtocoleCoffre(c), notes, TOKEN, attente=0)
    assert (notes.racine / "Preuve.md").read_text(encoding="utf-8") == "une fois"
    pending = b.sortie.read_bytes()
    # Un redémarrage reprend d'abord le résultat, même après une édition locale ultérieure.
    (notes.racine / "Preuve.md").write_text("édition locale", encoding="utf-8")
    restarted = BridgeCoffre(b.contexte, fabrique_client=b.fabrique_client)
    c.responses.append((200, {"ok": True, "id_operation": op["id_operation"], "deja": True}))
    assert restarted.cycle(ProtocoleCoffre(c), notes, TOKEN, attente=0) == "resultat_transmis"
    assert c.calls[-1][1] == contrat.ROUTE_RESULTAT
    assert json.loads(c.calls[-1][2]["corps"]) == json.loads(pending)
    assert not b.sortie.exists()
    assert (notes.racine / "Preuve.md").read_text(encoding="utf-8") == "édition locale"


def test_mauvais_accuse_conserve_resultat(bridge):
    b, c = bridge
    notes = association(b, c)
    result = {"protocole": contrat.PROTOCOLE, "coffre_id": notes.coffre_id, "id_operation": str(uuid4()),
              "etat": "refusee", "resultat": None, "erreur": {"code": "absent", "message": "Absent."}}
    b._sauver(b.sortie, result)
    c.responses.append((200, {"ok": True, "id_operation": str(uuid4()), "deja": False}))
    with pytest.raises(RefusBridge):
        b.cycle(ProtocoleCoffre(c), notes, TOKEN, attente=0)
    assert b.sortie.exists()


@pytest.mark.parametrize("code,efface", [("coffre_revoque", True), ("inconnu", False)])
def test_revocation_distincte_et_401_ambigu(bridge, poste, code, efface):
    b, c = bridge
    association(b, c)
    poste.coffre.ecrire("jeton-machine", "intact")
    c.responses.append((401, {"detail": {"code": code, "message": "refus"}}))
    with pytest.raises(RefusBridge):
        b.servir(une_fois=True)
    assert poste.coffre.present("jeton-coffre") is not efface
    assert poste.coffre.lire("jeton-machine") == "intact"


def test_cli_coffre_ne_demande_pas_politique(poste, tmp_path, capsys):
    context = poste.contexte()
    assert not context.emplacements.politique.exists()
    assert main(["obsidian", "creer", "--dossier", str(tmp_path / "Coffre CLI")], contexte=context) == 0
    assert main(["obsidian", "diagnostic"], contexte=context) == 0
    assert "identité locale absente" in capsys.readouterr().out
    poste.coffre.ecrire("jeton-machine", "ne pas effacer")
    poste.coffre.ecrire("jeton-coffre", "en mémoire")
    assert main(["obsidian", "oublier"], contexte=context) == 0
    assert poste.coffre.lire("jeton-machine") == "ne pas effacer"
    assert not poste.coffre.present("jeton-coffre")


def test_borne_https_defaut_conservee():
    assert ClientHermes("https://hermes.test", delai_connexion_s=1).limite_reponse == 64 * 1024
    assert ClientHermes("https://hermes.test", delai_connexion_s=1, limite_reponse=192 * 1024).limite_reponse == 192 * 1024
    with pytest.raises(ErreurReseau):
        ClientHermes("https://hermes.test", delai_connexion_s=1, limite_reponse=192 * 1024 + 1)
