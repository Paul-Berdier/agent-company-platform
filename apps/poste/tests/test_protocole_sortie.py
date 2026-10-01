"""Protocole de l'exécution côté poste (cahier P6 § 5) et file de sortie persistante (§ 5.9).

Un faux client HTTP rend des réponses préparées (les exemples du contrat, ``hermes/tests/outils/fixtures_machine``) ;
aucun réseau. Le contrat valide chaque requête AVANT l'envoi : une requête hors contrat n'atteint jamais le client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from acp_poste.client_hermes import ErreurReseau, ReponseHTTP
from acp_poste.jeton import Jeton
from acp_poste.protocole import HermesIndisponible, HorsContrat, JetonRefuse, Protocole, Refus
from acp_poste.sortie import FileSortie, nouvel_id_envoi
from acp_poste_contrat import machine as contrat

EXEMPLES = Path(__file__).resolve().parents[3] / "hermes" / "tests" / "outils" / "fixtures_machine"
JETON = Jeton("acpm_" + "j" * 43)


def exemple(nom: str):
    return json.loads((EXEMPLES / f"{nom}.json").read_text(encoding="utf-8"))


class FauxClient:
    def __init__(self, *reponses) -> None:
        self.reponses = list(reponses)
        self.vus: list[tuple[str, dict]] = []

    def echanger(self, methode, chemin, *, corps=None, entetes=None, delai_lecture_s):
        self.vus.append((chemin, json.loads(corps.decode("utf-8")) if corps else None))
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        statut, document = reponse
        return ReponseHTTP(statut=statut, corps=json.dumps(document).encode("utf-8"), entetes={})

    def interrompre(self):
        pass


# ------------------------------------------------------------------ reclamer


def test_reclamer_sans_execution_garde_le_corps_de_p5():
    client = FauxClient((200, exemple("reclamer_reponse")))
    Protocole(client).reclamer(JETON, acquittes=[], attente_max_s=5, politique_valide=True)
    corps = client.vus[0][1]
    assert set(corps) == {"protocole", "version_poste", "peut_executer", "ordres_acquittes", "attente_max_s",
                          "politique_valide"} and corps["peut_executer"] is False


def test_reclamer_annonce_les_voies_et_recoit_une_carte():
    client = FauxClient((200, exemple("reclamer_reponse_carte")))
    execution = {"peut_executer": True, "voies_disponibles": ["poste-claude", "poste-integration"],
                 "carte_en_cours": None, "espace_libre_mio": 3120}
    reponse = Protocole(client).reclamer(JETON, acquittes=[4], attente_max_s=25, politique_valide=True,
                                         execution=execution)
    assert reponse.carte.carte == "t_ab12cd34" and reponse.carte.voie == "poste-claude"
    corps = client.vus[0][1]
    assert corps["voies_disponibles"] == ["poste-claude", "poste-integration"] and corps["espace_libre_mio"] == 3120


def test_carte_non_demandee_refusee():
    voies_absentes = FauxClient((200, exemple("reclamer_reponse_carte")))
    with pytest.raises(HorsContrat, match="sans avoir été demandée"):
        Protocole(voies_absentes).reclamer(JETON, acquittes=[], attente_max_s=25, politique_valide=True,
                                           execution={"peut_executer": True, "voies_disponibles": ["poste-codex"]})
    sans_execution = FauxClient((200, exemple("reclamer_reponse_carte")))
    with pytest.raises(HorsContrat, match="sans avoir été demandée"):
        Protocole(sans_execution).reclamer(JETON, acquittes=[], attente_max_s=25, politique_valide=True)


def test_reclamer_hors_contrat_jamais_envoye():
    client = FauxClient()
    with pytest.raises(Refus, match="Rien n'a été envoyé"):
        Protocole(client).reclamer(JETON, acquittes=[], attente_max_s=25, politique_valide=True,
                                   execution={"peut_executer": False, "voies_disponibles": ["poste-claude"]})
    assert client.vus == []


# ------------------------------------------------------------------ six routes


@pytest.mark.parametrize(("route", "requete", "reponse"), [
    ("battement", "battement_requete", "battement_reponse"), ("terminer", "terminer_requete", "terminer_reponse"),
    ("question", "question_requete", "question_reponse"), ("bloquer", "bloquer_requete", "bloquer_reponse"),
    ("reprendre", "reprendre_requete", "reprise_reponse"), ("arret", "arret_requete", "reprise_reponse"),
])
def test_six_routes_validees_des_deux_cotes(route, requete, reponse):
    client = FauxClient((200, exemple(reponse)))
    resultat = Protocole(client).envoyer(JETON, route, exemple(requete))
    assert client.vus[0][0] == f"{contrat.PREFIXE_ROUTES}/{route}"
    assert type(resultat).__name__ == contrat.MODELES_P6[client.vus[0][0]][1]


def test_requete_hors_contrat_ou_route_inconnue_jamais_envoyee():
    client = FauxClient()
    mauvais = dict(exemple("battement_requete"), id_envoi="pas-un-uuid")
    with pytest.raises(Refus, match="refusé par le contrat"):
        Protocole(client).envoyer(JETON, "battement", mauvais)
    with pytest.raises(Refus, match="Route machine inconnue"):
        Protocole(client).envoyer(JETON, "pousser", {})
    vide = dict(exemple("terminer_requete"), resume="")
    with pytest.raises(Refus, match="refusé par le contrat"):
        Protocole(client).envoyer(JETON, "terminer", vide)
    assert client.vus == []


def test_classement_des_reponses():
    perdu = FauxClient((409, exemple("erreur_reclamation_perdue")))
    with pytest.raises(Refus) as exc:
        Protocole(perdu).envoyer(JETON, "terminer", exemple("terminer_requete"))
    assert exc.value.code == "reclamation_perdue" and exc.value.statut == 409
    with pytest.raises(JetonRefuse):
        Protocole(FauxClient((401, contrat.CORPS_401_COUTURE))).envoyer(JETON, "battement",
                                                                         exemple("battement_requete"))
    with pytest.raises(HermesIndisponible):
        Protocole(FauxClient((503, {"error": "x"}))).envoyer(JETON, "battement", exemple("battement_requete"))
    with pytest.raises(HermesIndisponible):
        Protocole(FauxClient(ErreurReseau("coupure"))).envoyer(JETON, "battement", exemple("battement_requete"))
    with pytest.raises(HorsContrat):
        Protocole(FauxClient((200, {"etat": "inconnu"}))).envoyer(JETON, "terminer", exemple("terminer_requete"))


# ------------------------------------------------------------------ file de sortie


def _corps(nom: str) -> dict:
    corps = exemple(nom)
    corps["id_envoi"] = nouvel_id_envoi()
    return corps


def test_deposer_atomique_et_ordonne(tmp_path):
    file = FileSortie(tmp_path / "sortie")
    premier = file.deposer("terminer", _corps("terminer_requete"))
    second = file.deposer("arret", _corps("arret_requete"))
    assert file.en_attente() == [premier, second]
    route, corps = FileSortie.lire(premier)
    assert route == "terminer" and corps["resume"].startswith("Commande")
    if os.name == "posix":
        assert (premier.stat().st_mode & 0o777) == 0o600 and ((tmp_path / "sortie").stat().st_mode & 0o777) == 0o700
    with pytest.raises(ValueError, match="hors de la file"):
        file.deposer("battement", _corps("battement_requete"))
    sans_id = exemple("bloquer_requete")
    del sans_id["id_envoi"]
    assert "id_envoi" in FileSortie.lire(file.deposer("bloquer", sans_id))[1]


def test_rejeu_dans_l_ordre_et_issues(tmp_path):
    file = FileSortie(tmp_path / "sortie")
    a = file.deposer("terminer", _corps("terminer_requete"))
    b = file.deposer("question", _corps("question_requete"))
    c = file.deposer("bloquer", _corps("bloquer_requete"))
    d = file.deposer("reprendre", _corps("reprendre_requete"))
    (tmp_path / "sortie" / "00000000-illisible.json").write_text("{", encoding="utf-8")
    client = FauxClient((409, exemple("erreur_reclamation_perdue")),
                        (200, exemple("question_reponse")),
                        (422, {"detail": {"code": "secret_detecte", "message": "Envoi refusé : secret."}}),
                        (503, {"error": "indisponible"}))
    protocole = Protocole(client)
    resultats, arret = file.rejouer(lambda route, corps: protocole.envoyer(JETON, route, corps))
    assert [r.route for r in resultats] == ["terminer", "question", "bloquer"]
    assert resultats[0].deplace and resultats[0].refus.code == "reclamation_perdue"
    assert resultats[1].retire and resultats[1].reponse.etat in ("ouverte", "escaladee")
    assert resultats[2].retire and resultats[2].refus.code == "secret_detecte"
    assert isinstance(arret, HermesIndisponible)
    # Le refus transitoire garde la requête et l'ordre ; l'illisible et le 409 sont rangés pour le diagnostic.
    assert file.en_attente() == [d]
    assert sorted(p.name for p in (tmp_path / "sortie" / "refusees").iterdir()) == sorted(
        ["00000000-illisible.json", a.name])
    assert not b.exists() and not c.exists()
    # Rejeu suivant : la même requête repart, avec le même id_envoi (idempotence côté greffon).
    client.reponses = [(200, exemple("reprise_reponse"))]
    resultats, arret = file.rejouer(lambda route, corps: protocole.envoyer(JETON, route, corps))
    assert arret is None and resultats[0].route == "reprendre" and file.en_attente() == []
    assert client.vus[-1][1]["id_envoi"] == client.vus[-2][1]["id_envoi"]
