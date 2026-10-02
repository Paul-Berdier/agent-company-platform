"""Inventaire de l'étape P7 (cahier P7 § 11.2, décision D83) : visibilité MESURÉE de chaque dépôt (``visibilite``,
``lecture``, ``verifie_le``), trois champs FACULTATIFS. Un inventaire de P5 ou de P6 reste valide sans changement ; un
dépôt non mesuré se sérialise toujours ``{"alias": …}`` (un greffon de P6 refuse tout champ inconnu : la forme envoyée
par un poste qui ne mesure rien ne change pas) ; une mesure est complète et datée ; les valeurs hors liste sont
refusées en français."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from acp_poste_contrat.inventaire import Depot, Releve, valider_inventaire

FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "outils" / "fixtures_machine"
QUAND = "2026-10-01T09:00:00Z"


def _fixture(nom: str) -> dict:
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


def _mesure(inventaire: dict, **mesure) -> dict:
    inventaire = copy.deepcopy(inventaire)
    for liste in [inventaire["depots"]] + [r["depots"] for r in inventaire["releves"]]:
        for depot in liste:
            depot.update(mesure)
    return inventaire


@pytest.mark.parametrize("nom", ["inventaire_requete.json", "inventaire_requete_linux.json"])
def test_inventaires_p5_et_p6_toujours_valides_et_serialises_a_l_identique(nom):
    brut = _fixture(nom)
    inventaire = valider_inventaire(brut)
    assert [d.visibilite for d in inventaire.depots] == [None]
    dump = inventaire.model_dump(mode="json")
    assert dump["depots"] == brut["depots"] == [{"alias": "jetable"}]
    assert all(r["depots"] == [{"alias": "jetable"}] for r in dump["releves"])


def test_inventaire_mesure_valide_et_relu():
    inventaire = valider_inventaire(_mesure(_fixture("inventaire_requete_linux.json"), visibilite="prive",
                                            lecture="ok", verifie_le=QUAND))
    [depot] = inventaire.depots
    assert (depot.alias, depot.visibilite, depot.lecture) == ("jetable", "prive", "ok")
    assert inventaire.model_dump(mode="json")["depots"] == [
        {"alias": "jetable", "visibilite": "prive", "lecture": "ok", "verifie_le": QUAND}]


@pytest.mark.parametrize("champs, attendu", [
    ({"visibilite": "ouvert", "lecture": "ok", "verifie_le": QUAND},
     "« visibilite » : valeurs admises : public, prive, inconnue"),
    ({"visibilite": "prive", "lecture": "peut-etre", "verifie_le": QUAND},
     "« lecture » : valeurs admises : ok, refusee, inconnue"),
    ({"visibilite": "prive", "lecture": "ok"}, "une visibilité ou une lecture mesurée porte sa date"),
    ({"visibilite": "prive", "verifie_le": QUAND}, "une mesure donne la visibilité ET la lecture"),
    ({"verifie_le": QUAND}, "une mesure donne la visibilité ET la lecture"),
    ({"visibilite": "prive", "lecture": "ok", "verifie_le": "2026-10-01T09:00:00"}, "doit porter son fuseau"),
    ({"visibilite": "prive", "lecture": "ok", "verifie_le": QUAND, "proprietaire": "x"}, "champ inconnu refusé"),
])
def test_mesures_invalides_refusees_en_francais(champs, attendu):
    with pytest.raises(ValueError) as exc:
        valider_inventaire(_mesure(_fixture("inventaire_requete_linux.json"), **champs))
    assert attendu in str(exc.value)


def test_depot_seul_et_releve_gardent_la_forme_de_p5():
    assert Depot.model_validate({"alias": "jetable"}).model_dump() == {"alias": "jetable"}
    releve = _fixture("inventaire_requete.json")["releves"][0]
    assert Releve.model_validate(releve).model_dump(mode="json")["depots"] == [{"alias": "jetable"}]
