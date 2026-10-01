"""Protocole acp-machine/1 (cahier P5 § 4) : modèles partagés par le poste et le greffon, exemples de requêtes et
de réponses (hermes/tests/outils/fixtures_machine, relus aussi par les tests du greffon dans l'image)."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import pytest

from acp_poste_contrat import machine as m
from acp_poste_contrat.inventaire import valider_inventaire

FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "outils" / "fixtures_machine"


def _fixture(nom: str) -> dict:
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


def _jeton(prefixe: str = "acpm_") -> str:
    return prefixe + secrets.token_urlsafe(32)


def test_formes_des_jetons():
    jeton, code = _jeton(), _jeton("acpe_")
    assert len(jeton) == 48 and m.JETON_MACHINE.fullmatch(jeton) and not m.CODE_ENROLEMENT.fullmatch(jeton)
    assert m.CODE_ENROLEMENT.fullmatch(code) and not m.JETON_MACHINE.fullmatch(code)
    assert not m.JETON_MACHINE.fullmatch(jeton[:-1]) and not m.JETON_MACHINE.fullmatch(jeton + "x")
    assert m.MACHINE_ID.fullmatch("m" + secrets.token_hex(6)[:11])


def test_empreintes():
    jeton = _jeton()
    longue = m.empreinte_jeton(jeton)
    assert len(longue) == 64 and longue == longue.lower()
    courte = m.empreinte_courte(longue)
    assert m.EMPREINTE_COURTE.fullmatch(courte) and courte.replace("-", "") == longue[:8].upper()
    for saisie in (courte, courte.lower(), courte.replace("-", ""), " " + courte.lower().replace("-", " ") + " "):
        assert m.empreinte_courte_normalisee(saisie) == courte
    for saisie in ("", "3F9A-0C1", "3F9A-0C1G", None, 12345678):
        assert m.empreinte_courte_normalisee(saisie) is None


def test_protocole_et_majeure():
    assert m.PROTOCOLE == "acp-machine/1" and m.majeure("acp-machine/1") == 1 and m.majeure("acp-machine/2") == 2
    assert m.majeure("acp-poste/1") is None and m.majeure("") is None
    requete = m.valider(m.RequeteEnrolement, dict(_fixture("enrolement_requete.json"), protocole="acp-machine/2"),
                        quoi="Requête refusée")
    assert requete.protocole == "acp-machine/2"  # la majeure est jugée par la route (409), pas par le modèle


def test_routes_exactes():
    assert m.ROUTES == ("/api/plugins/acp-poste/machine/v1/enrolement", "/api/plugins/acp-poste/machine/v1/reclamer",
                        "/api/plugins/acp-poste/machine/v1/inventaire")


def test_exemples_valides():
    m.RequeteEnrolement.model_validate(_fixture("enrolement_requete.json"))
    jeton = _jeton()
    reponse = _fixture("enrolement_reponse.json")
    reponse.update(jeton=jeton, empreinte=m.empreinte_courte(m.empreinte_jeton(jeton)))
    assert m.ReponseEnrolement.model_validate(reponse).etat == "a_confirmer"
    requete = m.RequeteReclamer.model_validate(_fixture("reclamer_requete.json"))
    assert requete.ordres_acquittes == [12, 13] and requete.peut_executer is False
    assert m.ReponseReclamer.model_validate(_fixture("reclamer_reponse.json")).ordres[0].genre == "releve"
    assert m.ReponseReclamer.model_validate(_fixture("reclamer_reponse_a_confirmer.json")).prochaine_attente_s == 15
    assert m.ReponseInventaire.model_validate(_fixture("inventaire_reponse.json")).releves == {
        "poste-codex": 41, "poste-claude": 42}
    assert m.ErreurMachine.model_validate(_fixture("erreur_poste_revoque.json")).detail.code == "poste_revoque"
    assert _fixture("erreur_401_couture.json") == m.CORPS_401_COUTURE
    valider_inventaire(_fixture("inventaire_requete.json"))


def test_empreinte_incoherente_refusee_sans_citer_le_jeton():
    jeton = _jeton()
    reponse = dict(_fixture("enrolement_reponse.json"), jeton=jeton, empreinte="0000-0000")
    with pytest.raises(ValueError) as exc:
        m.valider(m.ReponseEnrolement, reponse, quoi="Réponse d'enrôlement refusée")
    assert "ne correspond pas au jeton reçu" in str(exc.value) and jeton not in str(exc.value)
    with pytest.raises(ValueError) as exc:
        m.valider(m.ReponseEnrolement, dict(reponse, jeton=jeton[:-2]), quoi="Réponse d'enrôlement refusée")
    assert "jeton machine au format invalide" in str(exc.value) and jeton[:-2] not in str(exc.value)


def test_carte_toujours_nulle_en_p5():
    reponse = dict(_fixture("reclamer_reponse.json"), carte={"id": "t_1"})
    with pytest.raises(ValueError, match="aucune carte n'est servie à l'étape P5"):
        m.valider(m.ReponseReclamer, reponse, quoi="Réponse refusée")


@pytest.mark.parametrize("modifs, motif", [
    ({"attente_max_s": 4}, "« attente_max_s » doit être un entier compris entre 5 et 50"),
    ({"attente_max_s": 51}, "« attente_max_s » doit être un entier compris entre 5 et 50"),
    ({"attente_max_s": True}, "« attente_max_s » doit être un entier"),
    ({"ordres_acquittes": list(range(1, 66))}, "au plus 64 identifiants"),
    ({"ordres_acquittes": [0]}, "« ordres_acquittes » doit être un entier"),
    ({"peut_executer": "non"}, "« peut_executer » doit être un booléen"),
    ({"intrus": 1}, "champ inconnu refusé : « intrus »"),
    ({"protocole": "acp machine"}, "« protocole » : format invalide"),
])
def test_requete_reclamer_refusee_en_francais(modifs, motif):
    with pytest.raises(ValueError) as exc:
        m.valider(m.RequeteReclamer, dict(_fixture("reclamer_requete.json"), **modifs), quoi="Requête refusée")
    assert str(exc.value).startswith("Requête refusée : ") and motif in str(exc.value)


def test_reponse_hors_contrat_refusee():
    with pytest.raises(ValueError, match="champ inconnu refusé : « bonus »"):
        m.valider(m.ReponseReclamer, dict(_fixture("reclamer_reponse.json"), bonus=1), quoi="Réponse refusée")
    with pytest.raises(ValueError, match="« code » : valeurs admises"):
        m.valider(m.ErreurMachine, {"detail": {"code": "inconnu", "message": "x"}}, quoi="Erreur refusée")


@pytest.mark.parametrize("nom, raison", [
    ("PC de paul" + "@" + "maison", "adresse électronique (« @ »)"),
    ("Poste C:/bureau", "chemin de lecteur"),
    ("jeton acpm_ collé", "jeton machine ou code d'enrôlement d'ACP"),
])
def test_nom_de_poste_refuse_s_il_ne_peut_pas_etre_publie(nom, raison):
    """Relecture de P5 : un nom que la garde « aucun identifiant » refuse dans l'inventaire était admis à
    l'enrôlement ; le poste s'enrôlait puis ne publiait jamais rien. Refusé dès l'enrôlement, sans citer le nom."""
    with pytest.raises(ValueError) as exc:
        m.valider(m.RequeteEnrolement, dict(_fixture("enrolement_requete.json"), nom=nom), quoi="Requête refusée")
    assert f"« nom » : {raison} refusé dans le nom du poste" in str(exc.value) and nom not in str(exc.value)
    assert m.valider(m.RequeteEnrolement, dict(_fixture("enrolement_requete.json"), nom="PC du bureau : 2e étage"),
                     quoi="Requête refusée").nom == "PC du bureau : 2e étage"


def test_commande_publiee_executable_et_publiable():
    """Relecture de P5 (décision D68) : « acp-poste enroler » n'est reconnu par aucune console (dossier du poste hors
    du PATH). Ce que Hermes et l'inventaire affichent est la forme exécutable de PowerShell, sans lettre de lecteur
    que la garde « aucun identifiant » refuserait."""
    from acp_poste_contrat.inventaire import raison_identifiant

    forme = m.commande_publiee("enroler")
    assert forme == '& "$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd" enroler'
    assert raison_identifiant(forme) is None
    assert raison_identifiant('& "C:\\Program Files\\ACP\\poste\\acp-poste.cmd" enroler') == "chemin de lecteur"
