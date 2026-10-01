"""Routes du propriétaire de l'étape P5 (cahier P5 § 12.3) sur un vrai serveur, avec une session factice (la porte
OIDC réelle est prouvée au contrat) : enrôlement, confirmation, révocation, « Relever maintenant », routage (vue,
validation tout ou rien, politique, surcharges, relevé accepté), quotas ; règles d'écriture de P4 sur chaque route."""

from __future__ import annotations

import pytest

from conftest import fixture_machine, inventaire_factice

P = "/api/plugins/acp-poste"
M = f"{P}/machine/v1"
ECRITURES = ("/v1/poste/enrolement", "/v1/poste/confirmation", "/v1/poste/revocation", "/v1/poste/releve",
             "/v1/routage", "/v1/routage/politique", "/v1/routage/surcharges", "/v1/routage/surcharges/1/desactiver",
             "/v1/routage/releve-accepte")


def _code(pile):
    reponse = pile.post(f"{P}/v1/poste/enrolement", {})
    assert reponse.status_code == 201, reponse.text
    return reponse


def _poste_actif(pile):
    code = _code(pile).json()["code"]
    enrole = pile.post(f"{M}/enrolement", fixture_machine("enrolement_requete.json"), jeton=code).json()
    confirme = pile.post(f"{P}/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                         "empreinte": enrole["empreinte"]})
    assert confirme.status_code == 200, confirme.text
    return enrole["machine_id"], enrole["jeton"]


def test_regles_d_ecriture_sur_chaque_route(pile_machine):
    for chemin in ECRITURES:
        sans_session = pile_machine.post(P + chemin, {}, entetes={"x-test-sans-session": "1"})
        assert sans_session.status_code == 401, chemin
        assert pile_machine.post(P + chemin, brut=b"{}", entetes={"Content-Type": "text/plain"}).status_code == 415
        assert pile_machine.post(P + chemin, {}, entetes={"Origin": "https://intrus.example"}).status_code == 403
    assert pile_machine.post(f"{P}/v1/poste/enrolement", {"intrus": 1}).status_code == 400


def test_poste_non_configure_puis_code_rendu_une_fois(pile_machine):
    vue = pile_machine.get(f"{P}/v1/poste").json()
    assert vue["poste"]["etat"] == "non_configure" and vue["machine"]["machine"] is None
    assert vue["inventaire"] is None and vue["alertes"] == [] and vue["ordres"] == []
    reponse = _code(pile_machine)
    corps = reponse.json()
    assert reponse.headers["cache-control"] == "no-store"
    assert corps["code"].startswith("acpe_") and len(corps["code"]) == 48 and corps["validite_s"] == 600
    # Forme exécutable dans la console du compte, sans lettre de lecteur (relecture de P5, décision D68).
    assert corps["commande"] == '& "$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd" enroler' and corps["protocole"] == "acp-machine/1"
    # Le code n'est plus jamais rendu : la vue du poste n'en montre que le nombre.
    vue = pile_machine.get(f"{P}/v1/poste").json()
    assert corps["code"] not in str(vue) and vue["machine"]["codes_utilisables"] == 1


def test_confirmation_et_etats(pile_machine):
    code = _code(pile_machine).json()["code"]
    enrole = pile_machine.post(f"{M}/enrolement", fixture_machine("enrolement_requete.json"), jeton=code).json()
    vue = pile_machine.get(f"{P}/v1/poste").json()
    assert vue["poste"]["etat"] == "a_confirmer" and vue["machine"]["machine"]["empreinte"] == enrole["empreinte"]
    faux = pile_machine.post(f"{P}/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                             "empreinte": "0000-0000"})
    assert faux.status_code == 409 and faux.json()["detail"]["code"] == "empreinte_differente"
    inconnu = pile_machine.post(f"{P}/v1/poste/confirmation", {"machine_id": "m00000000000", "empreinte": "0000-0000"})
    assert inconnu.status_code == 404
    bon = pile_machine.post(f"{P}/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                            "empreinte": enrole["empreinte"].lower()})
    assert bon.status_code == 200 and bon.json()["machine"]["etat"] == "actif"
    assert pile_machine.post(f"{P}/v1/poste/enrolement", {}).status_code == 409  # un seul poste actif (D50)


def test_releve_maintenant(pile_machine):
    absent = pile_machine.post(f"{P}/v1/poste/releve", {})
    assert absent.status_code == 409 and absent.json()["detail"]["code"] == "aucun_poste_actif"
    machine, jeton = _poste_actif(pile_machine)
    reponse = pile_machine.post(f"{P}/v1/poste/releve", {})
    assert reponse.status_code == 202 and reponse.json()["en_attente_du_poste"] is True
    assert reponse.json()["message"] == ("Ordre de relevé mis en file : le poste est hors ligne ; il le recevra à son "
                                         "retour (abandonné après 60 min).")
    ordres = pile_machine.get(f"{P}/v1/poste").json()["ordres"]
    assert [(o["genre"], o["livre"]) for o in ordres] == [("releve", False)]
    corps = pile_machine.post(f"{M}/reclamer", dict(fixture_machine("reclamer_requete.json"), ordres_acquittes=[],
                                                    attente_max_s=5), jeton=jeton).json()
    assert [o["genre"] for o in corps["ordres"]] == ["releve"]
    # L'inventaire qui suit sert l'ordre livré, même dans la minute (ordre « releve » en attente).
    assert pile_machine.post(f"{M}/inventaire", inventaire_factice(), jeton=jeton).status_code == 200
    vue = pile_machine.get(f"{P}/v1/poste").json()
    assert vue["ordres"] == [] and vue["inventaire"]["contenu"]["poste"]["nom"] == "Poste Windows"
    assert vue["poste"]["etat"] == "en_ligne"
    del machine


def test_revocation(pile_machine):
    machine, jeton = _poste_actif(pile_machine)
    reponse = pile_machine.post(f"{P}/v1/poste/revocation", {"machine_id": machine, "motif": "PC perdu"})
    assert reponse.status_code == 200 and reponse.json()["machine"]["etat"] == "revoque"
    assert pile_machine.post(f"{M}/reclamer", fixture_machine("reclamer_requete.json"), jeton=jeton).status_code == 401
    assert pile_machine.post(f"{P}/v1/poste/revocation", {"machine_id": machine, "motif": "x"}).status_code == 409
    assert pile_machine.post(f"{P}/v1/poste/revocation", {"machine_id": "m00000000000",
                                                          "motif": "x"}).status_code == 404
    assert pile_machine.get(f"{P}/v1/poste").json()["poste"]["etat"] == "revoque"


def test_routage_vue_validation_et_refus(pile_machine):
    _machine, jeton = _poste_actif(pile_machine)
    assert pile_machine.post(f"{M}/inventaire", inventaire_factice(), jeton=jeton).status_code == 200
    vue = pile_machine.get(f"{P}/v1/routage").json()
    assert vue["voies"]["poste-codex"]["badge"] == "releve_du_compte"
    assert vue["voies"]["poste-claude"]["badge"] == "alias_documentes"
    assert vue["classes"]["implementation"]["etat"] == "non_validee"
    assert vue["politique_poste"]["alias_claude_permis"] == ["opus", "opus[1m]", "sonnet", "haiku"]
    refus = pile_machine.post(f"{P}/v1/routage", {"releves": vue["releves"], "classes": {
        "implementation": [{"voie": "poste-codex", "modele": "inexistant"}]}})
    assert refus.status_code == 422 and refus.json()["detail"]["code"] == "table_refusee"
    assert refus.json()["detail"]["refus"][0]["code"] == "modele_absent"
    change = pile_machine.post(f"{P}/v1/routage", {"releves": {"poste-codex": 1, "poste-claude": None},
                                                    "classes": {"implementation": [{"voie": "poste-codex"}]}})
    assert change.status_code == 409 and change.json()["detail"]["code"] == "releve_change"
    bon = pile_machine.post(f"{P}/v1/routage", {"releves": vue["releves"], "classes": {
        "implementation": [{"voie": "poste-codex", "modele": "factice-codex-1", "effort": "medium"}]}})
    assert bon.status_code == 200 and bon.json()["classes"]["implementation"]["etat"] == "validee"


def test_politique_surcharges_releve_accepte(pile_machine):
    _machine, jeton = _poste_actif(pile_machine)
    assert pile_machine.post(f"{M}/inventaire", inventaire_factice(), jeton=jeton).status_code == 200
    sans = pile_machine.post(f"{P}/v1/routage/politique", {"efforts_interdits": [], "paliers_admis": ["default"],
                                                           "motif": "essai"})
    assert sans.status_code == 422 and sans.json()["detail"]["code"] == "confirmation_requise"
    avec = pile_machine.post(f"{P}/v1/routage/politique", {
        "efforts_interdits": ["ultra"], "paliers_admis": ["default"], "motif": "essai",
        "confirmation": "J'accepte une dépense hors enveloppe"})
    assert avec.status_code == 200 and avec.json()["politique_hermes"]["efforts_interdits"] == ["ultra"]
    refusee = pile_machine.post(f"{P}/v1/routage/surcharges", {"classe": "implementation", "voie": "poste-codex",
                                                               "modele": "inexistant", "motif": "essai"})
    assert refusee.status_code == 422 and refusee.json()["detail"]["code"] == "modele_absent"
    creee = pile_machine.post(f"{P}/v1/routage/surcharges", {"classe": "implementation", "voie": "poste-codex",
                                                             "modele": "factice-codex-2", "motif": "essai"})
    assert creee.status_code == 201
    identifiant = creee.json()["surcharge"]
    assert [s["id"] for s in pile_machine.get(f"{P}/v1/routage").json()["surcharges"]] == [identifiant]
    assert pile_machine.post(f"{P}/v1/routage/surcharges/{identifiant}/desactiver", {}).status_code == 200
    assert pile_machine.post(f"{P}/v1/routage/surcharges/{identifiant}/desactiver", {}).status_code == 404
    releve = pile_machine.get(f"{P}/v1/routage").json()["releves"]["poste-codex"]
    non = pile_machine.post(f"{P}/v1/routage/releve-accepte", {"releve_id": releve})
    assert non.status_code == 409 and non.json()["detail"]["code"] == "releve_non_acceptable"


@pytest.mark.parametrize("chemin", ["/v1/quotas", "/v1/routage", "/v1/poste"])
def test_lectures_sans_poste(pile_machine, chemin):
    reponse = pile_machine.get(P + chemin)
    assert reponse.status_code == 200


def test_quotas_apres_inventaire(pile_machine):
    assert pile_machine.get(f"{P}/v1/quotas").json()["poste-codex"]["etat"] == "inconnu"
    _machine, jeton = _poste_actif(pile_machine)
    assert pile_machine.post(f"{M}/inventaire", inventaire_factice(), jeton=jeton).status_code == 200
    quotas = pile_machine.get(f"{P}/v1/quotas").json()
    assert quotas["poste-codex"]["etat"] == "releve" and quotas["poste-codex"]["compteurs"][0]["plan"] == "prolite"


def test_pause_generale_ordonne_au_poste(pile_machine):
    machine, _jeton = _poste_actif(pile_machine)
    reponse = pile_machine.post(f"{P}/v1/pause", {"generale": True})
    assert reponse.status_code == 200, reponse.text
    try:
        ordres = pile_machine.get(f"{P}/v1/poste").json()["ordres"]
        assert [o["genre"] for o in ordres] == ["pause"]
    finally:
        assert pile_machine.post(f"{P}/v1/pause", {"generale": False}).status_code == 200
    assert [o["genre"] for o in pile_machine.get(f"{P}/v1/poste").json()["ordres"]] == ["pause", "reprise"]
    del machine


@pytest.mark.parametrize("brut", [b"[" * 20_000 + b"]" * 20_000, b'{"a":' * 40 + b"1" + b"}" * 40])
def test_ecriture_trop_imbriquee_400(pile_machine, brut):
    """Relecture de P5 : même garde sur les routes d'écriture du propriétaire (400 en français, jamais un 500)."""
    reponse = pile_machine.post(f"{P}/v1/routage/politique", brut=brut)
    assert reponse.status_code == 400
    assert reponse.json()["detail"]["message"] == "Requête refusée : corps JSON trop imbriqué (plus de 32 niveaux)."
