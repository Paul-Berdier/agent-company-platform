"""Routes machine du greffon (étape P5, cahier P5 § 4.2 à § 4.4, § 14.3) servies par un vrai serveur, derrière la
VRAIE couture par jeton de Hermes : 401 de la couture sans porteur reconnu, contrôles du gestionnaire (fournisseur,
portée, JSON, taille, protocole), usage unique et expiration du code, un seul poste actif, confirmation exigée,
contrat, cadence, et réponses conformes aux modèles partagés."""

from __future__ import annotations

import json

import pytest

from conftest import fixture_machine, inventaire_factice

from acp_poste_contrat import machine as contrat  # noqa: E402

M = "/api/plugins/acp-poste/machine/v1"


def _code(pile) -> str:
    with pile.noyau.base.connexion() as conn:
        return pile.noyau.machines.creer_code(conn, "proprietaire:test")["code"]


def _enroler(pile, code, nom="Poste Windows"):
    return pile.post(f"{M}/enrolement", dict(fixture_machine("enrolement_requete.json"), nom=nom), jeton=code)


def _confirmer(pile, reponse):
    with pile.noyau.base.connexion() as conn:
        pile.noyau.machines.confirmer(conn, reponse["machine_id"], reponse["empreinte"], "proprietaire:test")


def _poste_actif(pile):
    reponse = _enroler(pile, _code(pile)).json()
    _confirmer(pile, reponse)
    return reponse["machine_id"], reponse["jeton"]


def _reclamer(pile, jeton, **modifs):
    corps = dict(fixture_machine("reclamer_requete.json"), ordres_acquittes=[], attente_max_s=5)
    corps.update(modifs)
    return pile.post(f"{M}/reclamer", corps, jeton=jeton)


def test_sans_porteur_401_de_la_couture(pile_machine):
    for route in ("enrolement", "reclamer", "inventaire"):
        reponse = pile_machine.post(f"{M}/{route}", {})
        assert reponse.status_code == 401 and reponse.json() == contrat.CORPS_401_COUTURE
        # Un porteur d'une autre forme (jeton OIDC) n'est pas le nôtre : 401 de la couture, jamais une session.
        reponse = pile_machine.post(f"{M}/{route}", {}, jeton="eyJhbGciOiJSUzI1NiJ9.e30.c2lnbmF0dXJl",
                                    entetes={"x-test-sans-session": "1"})
        assert reponse.status_code == 401 and reponse.json() == contrat.CORPS_401_COUTURE


def test_enrolement_201_puis_reponse_conforme(pile_machine):
    code = _code(pile_machine)
    reponse = _enroler(pile_machine, code)
    assert reponse.status_code == 201 and reponse.headers["cache-control"] == "no-store"
    corps = contrat.ReponseEnrolement.model_validate(reponse.json())
    assert corps.etat == "a_confirmer" and corps.empreinte == contrat.empreinte_courte(
        contrat.empreinte_jeton(corps.jeton))
    assert set(reponse.json()) == set(fixture_machine("enrolement_reponse.json"))


def test_code_usage_unique(pile_machine):
    code = _code(pile_machine)
    assert _enroler(pile_machine, code).status_code == 201
    second = _enroler(pile_machine, code)
    assert second.status_code == 401 and second.json() == contrat.CORPS_401_COUTURE


def test_code_expire(pile_machine):
    code = _code(pile_machine)
    debut = pile_machine.base_routes.maintenant()
    pile_machine.base_routes.fixer_horloge(lambda: debut + 601)
    pile_machine.noyau.base.fixer_horloge(lambda: debut + 601)
    reponse = _enroler(pile_machine, code)
    assert reponse.status_code == 401 and reponse.json() == contrat.CORPS_401_COUTURE


@pytest.mark.parametrize("route, porteur, code_attendu", [
    ("reclamer", "code", "code_enrolement_seulement"),
    ("inventaire", "code", "code_enrolement_seulement"),
    ("enrolement", "jeton", "jeton_machine_ici"),
])
def test_portee_croisee_403(pile_machine, route, porteur, code_attendu):
    machine, jeton = _poste_actif(pile_machine)
    del machine
    code = None
    if porteur == "code":
        with pile_machine.noyau.base.connexion() as conn:
            conn.execute("UPDATE machines SET etat = 'revoque' WHERE etat = 'actif'")
        code = _code(pile_machine)
    corps = {"enrolement": fixture_machine("enrolement_requete.json"), "reclamer": fixture_machine(
        "reclamer_requete.json"), "inventaire": inventaire_factice()}[route]
    reponse = pile_machine.post(f"{M}/{route}", corps, jeton=code if porteur == "code" else jeton)
    assert reponse.status_code == 403 and reponse.json()["detail"]["code"] == code_attendu


def test_mauvais_fournisseur_403(pile_machine):
    """Un principal d'un AUTRE fournisseur à jeton sur un chemin machine : le gestionnaire le refuse (403)."""
    from hermes_cli.dashboard_auth.base import DashboardAuthProvider, TokenPrincipal
    from hermes_cli.dashboard_auth.registry import register_global_provider, unregister_global_provider

    class Autre(DashboardAuthProvider):
        name, display_name, supports_token, supports_session = "autre-jeton", "Autre", True, False

        def verify_token(self, *, token):
            return TokenPrincipal("service", self.name, ("machine",)) if token == "autre-jeton-de-test" else None

        def start_login(self, **k): raise NotImplementedError

        def complete_login(self, **k): raise NotImplementedError

        def verify_session(self, **k): return None

        def refresh_session(self, **k): raise NotImplementedError

        def revoke_session(self, **k): return None
    autre = Autre()
    register_global_provider(autre)
    try:
        for route in ("enrolement", "reclamer", "inventaire"):
            reponse = pile_machine.post(f"{M}/{route}", {}, jeton="autre-jeton-de-test")
            assert reponse.status_code == 403, route
            assert reponse.json()["detail"] == {"code": "mauvais_fournisseur", "message": (
                "Jeton refusé : ce chemin n'accepte que le jeton machine d'acp-poste.")}
    finally:
        unregister_global_provider(autre.name, autre)


def test_un_seul_poste_actif(pile_machine):
    code_a, code_b = _code(pile_machine), _code(pile_machine)
    premier = _enroler(pile_machine, code_a).json()
    _confirmer(pile_machine, premier)
    reponse = _enroler(pile_machine, code_b, nom="Second")
    assert reponse.status_code == 409 and reponse.json()["detail"] == {"code": "poste_deja_enrole", "message": (
        "Un poste est déjà enrôlé (« Poste Windows ») : révoquez-le depuis la page Poste avant d'en enrôler un "
        "autre.")}


def test_a_confirmer_remplace(pile_machine):
    premier = _enroler(pile_machine, _code(pile_machine)).json()
    second = _enroler(pile_machine, _code(pile_machine)).json()
    assert _reclamer(pile_machine, premier["jeton"]).status_code == 401  # remplacé : jeton inconnu de la couture
    reponse = _reclamer(pile_machine, second["jeton"])
    assert reponse.status_code == 200 and reponse.json()["etat_machine"] == "a_confirmer"
    assert reponse.json()["prochaine_attente_s"] == 15 and reponse.json()["ordres"] == []
    with pile_machine.noyau.base.connexion() as conn:
        assert conn.execute("SELECT COUNT(*) FROM presence").fetchone()[0] == 0  # à confirmer : jamais présent


def test_inventaire_avant_confirmation_403(pile_machine):
    reponse = _enroler(pile_machine, _code(pile_machine)).json()
    inventaire = pile_machine.post(f"{M}/inventaire", inventaire_factice(), jeton=reponse["jeton"])
    assert inventaire.status_code == 403 and inventaire.json()["detail"] == {"code": "poste_a_confirmer", "message": (
        f"Poste en attente de confirmation : confirmez l'empreinte {reponse['empreinte']} sur la page Poste.")}
    with pile_machine.noyau.base.connexion() as conn:
        assert conn.execute("SELECT COUNT(*) FROM releves").fetchone()[0] == 0


def test_inventaire_200_conforme(pile_machine):
    machine, jeton = _poste_actif(pile_machine)
    reponse = pile_machine.post(f"{M}/inventaire", inventaire_factice(), jeton=jeton)
    assert reponse.status_code == 200 and reponse.headers["cache-control"] == "no-store"
    corps = contrat.ReponseInventaire.model_validate(reponse.json())
    assert set(corps.releves) == {"poste-codex", "poste-claude"}
    with pile_machine.noyau.base.connexion() as conn:
        assert {l[0] for l in conn.execute("SELECT machine_id FROM releves")} == {machine}


def test_inventaire_hors_contrat_422(pile_machine):
    _machine, jeton = _poste_actif(pile_machine)
    reponse = pile_machine.post(f"{M}/inventaire", inventaire_factice(modifier=lambda i: i.pop("politique")),
                                jeton=jeton)
    assert reponse.status_code == 422 and reponse.json()["detail"]["code"] == "requete_refusee"
    message = reponse.json()["detail"]["message"]
    assert message.startswith("Requête du poste refusée par le contrat : ") and "« politique »" in message
    assert message.endswith("Rien n'a été enregistré.")


def test_inventaire_trop_frequent_429(pile_machine):
    _machine, jeton = _poste_actif(pile_machine)
    assert pile_machine.post(f"{M}/inventaire", inventaire_factice(), jeton=jeton).status_code == 200
    reponse = pile_machine.post(f"{M}/inventaire", inventaire_factice(), jeton=jeton)
    assert reponse.status_code == 429 and reponse.json()["detail"]["code"] == "trop_frequent"
    attente = int(reponse.headers["retry-after"])
    assert 55 <= attente <= 60 and f"prochain envoi possible dans {attente} s" in reponse.json()["detail"]["message"]


def test_corps_borne_413(pile_machine):
    _machine, jeton = _poste_actif(pile_machine)
    gros = json.dumps(dict(fixture_machine("reclamer_requete.json"), bourrage="x" * 5000)).encode()
    reponse = pile_machine.post(f"{M}/reclamer", brut=gros, jeton=jeton)
    assert reponse.status_code == 413 and reponse.json()["detail"] == {
        "code": "trop_volumineux", "message": "Requête du poste refusée : corps de plus de 4 Kio."}
    tres_gros = json.dumps({"bourrage": "x" * (257 * 1024)}).encode()
    reponse = pile_machine.post(f"{M}/inventaire", brut=tres_gros, jeton=jeton)
    assert reponse.status_code == 413 and "256 Kio" in reponse.json()["detail"]["message"]


def test_json_exige_415(pile_machine):
    _machine, jeton = _poste_actif(pile_machine)
    reponse = pile_machine.post(f"{M}/reclamer", brut=b"protocole=acp-machine/1", jeton=jeton,
                                entetes={"Content-Type": "application/x-www-form-urlencoded"})
    assert reponse.status_code == 415 and reponse.json()["detail"]["code"] == "json_attendu"
    reponse = pile_machine.post(f"{M}/reclamer", brut=b"{pas du json", jeton=jeton)
    assert reponse.status_code == 422 and "corps JSON illisible" in reponse.json()["detail"]["message"]


def test_protocole_409(pile_machine):
    _machine, jeton = _poste_actif(pile_machine)
    reponse = _reclamer(pile_machine, jeton, protocole="acp-machine/2")
    assert reponse.status_code == 409 and reponse.json()["detail"] == {"code": "protocole_incompatible", "message": (
        "Protocole du poste « acp-machine/2 » incompatible avec le greffon (acp-machine/1 attendu) : mettez le poste "
        "à jour.")}


def test_reclamer_hors_contrat_422(pile_machine):
    _machine, jeton = _poste_actif(pile_machine)
    reponse = _reclamer(pile_machine, jeton, attente_max_s=99)
    assert reponse.status_code == 422
    assert "« attente_max_s » doit être un entier compris entre 5 et 50" in reponse.json()["detail"]["message"]


@pytest.mark.parametrize("route, brut", [
    # Relecture de P5 : 20 000 niveaux faisaient lever RecursionError au décodeur (500 en texte brut, en anglais).
    ("inventaire", b"[" * 20_000 + b"]" * 20_000),
    ("inventaire", b'{"a":' * 20_000 + b"1" + b"}" * 20_000),
    # Décodable, mais plus imbriqué que la borne : refusé AVANT le balayage récursif et le contrat.
    ("reclamer", b'{"a":' * (contrat.PROFONDEUR_MAX_CORPS + 1) + b"1" + b"}" * (contrat.PROFONDEUR_MAX_CORPS + 1)),
])
def test_corps_trop_imbrique_422(pile_machine, route, brut):
    _machine, jeton = _poste_actif(pile_machine)
    reponse = pile_machine.post(f"{M}/{route}", brut=brut, jeton=jeton)
    assert reponse.status_code == 422 and reponse.headers["cache-control"] == "no-store"
    assert reponse.headers["content-type"].startswith("application/json")
    assert reponse.json()["detail"] == {"code": "requete_refusee", "message": (
        f"Requête du poste refusée par le contrat : corps JSON trop imbriqué (plus de {contrat.PROFONDEUR_MAX_CORPS} "
        "niveaux). Rien n'a été enregistré.")}
    with pile_machine.noyau.base.connexion() as conn:
        assert conn.execute("SELECT COUNT(*) FROM releves").fetchone()[0] == 0


def test_inventaire_imbrique_sous_la_borne_passe_le_balayage(pile_machine):
    """Un champ inconnu imbriqué sous la borne n'atteint plus un balayage récursif : refus du contrat, en 422."""
    _machine, jeton = _poste_actif(pile_machine)
    profond: object = "rien"
    for _ in range(contrat.PROFONDEUR_MAX_CORPS - 2):
        profond = [profond]
    reponse = pile_machine.post(f"{M}/inventaire", inventaire_factice(modifier=lambda i: i.update(bonus=profond)),
                                jeton=jeton)
    assert reponse.status_code == 422 and reponse.json()["detail"]["code"] == "requete_refusee"
    assert "trop imbriqué" not in reponse.json()["detail"]["message"]
