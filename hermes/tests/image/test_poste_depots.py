"""Carte « Dépôts » de la page Poste et grisage de Codex dans « Nouveau projet » (étape P7, partie E, cahier P7 § 11.2) :
``GET /v1/poste`` porte, dans le bloc ``executant``, chaque dépôt du dernier inventaire avec sa visibilité MESURÉE (telle
que publiée par l'exécutant, jamais devinée) et les voies du poste fermées POUR LUI (calcul du routage,
``routage.voies_fermees(…, depot_alias)``).

La réponse a la forme ET les valeurs de la fixture partagée ``hermes/tests/outils/fixtures_poste/depots.json``, lue
aussi par Vitest (``apps/interface/tests/depots-p7.test.tsx``) : l'interface est éprouvée sur la forme réelle. Pour la
régénérer après un changement VOULU : lancer ce fichier dans l'image de test avec
``ACP_ECRIRE_FIXTURE_DEPOTS=<chemin monté>``, relire et recopier le fichier écrit (jamais en CI)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import inventaire_factice, poste_confirme
from test_routes_projets import P, client  # noqa: F401 — fixture des routes (session factice)

FIXTURE = Path("/opt/acp-tests/outils/fixtures_poste/depots.json")


def _demo_public(inventaire: dict) -> None:
    """« demo » mesuré public (lu sans identifiant) ; « jetable » reste privé et lu avec le jeton."""
    for depots in [inventaire["depots"], *(r["depots"] for r in inventaire["releves"])]:
        for depot in depots:
            if depot["alias"] == "demo":
                depot["visibilite"] = "public"


def _sans_date(depots: list) -> list:
    return [{k: v for k, v in d.items() if k != "verifie_le"} for d in depots]


def test_page_poste_depots_mesures_et_voies(client, noyau):  # noqa: F811
    with noyau.base.connexion() as conn:
        machine, _jeton = poste_confirme(noyau, conn)
        with noyau.base.transaction(conn):
            noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice(depots=("demo", "jetable"),
                                                                             modifier=_demo_public))
    reponse = client.get(f"{P}/v1/poste")
    assert reponse.status_code == 200, reponse.text
    depots = reponse.json()["executant"]["depots"]
    if os.environ.get("ACP_ECRIRE_FIXTURE_DEPOTS"):  # régénération de la fixture partagée (documentée), jamais en CI
        Path(os.environ["ACP_ECRIRE_FIXTURE_DEPOTS"]).write_text(
            json.dumps(depots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    attendu = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert _sans_date(depots) == _sans_date(attendu)
    assert all(d["verifie_le"].endswith("Z") for d in depots)
    demo, jetable = depots
    assert (demo["alias"], demo["visibilite"], demo["lecture"]) == ("demo", "public", "ok")
    assert list(demo["voies_fermees"]) == ["poste-codex"] and "non prouvé privé" in demo["voies_fermees"]["poste-codex"]
    assert (jetable["alias"], jetable["visibilite"], jetable["lecture"], jetable["voies_fermees"]) == (
        "jetable", "prive", "ok", {})


def test_page_poste_sans_inventaire_aucun_depot_invente(client, noyau):  # noqa: F811
    reponse = client.get(f"{P}/v1/poste")
    assert reponse.status_code == 200 and reponse.json()["executant"] == {"connu": False}
