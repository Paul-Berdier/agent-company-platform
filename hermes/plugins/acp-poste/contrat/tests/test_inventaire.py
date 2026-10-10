"""Contrat du relevé du poste (inventaire), partagé par le poste (P5) et le greffon acp-poste (P4)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest

from acp_poste_contrat.inventaire import ALIAS_DEPOT, Releve, valider_releve

RELEVE = {
    "voie": "poste-codex",
    "source": "releve_factice",
    "version_cli": "0.0.0-factice",
    "releve_le": "2026-09-26T08:00:00+00:00",
    "modeles": [
        {"id": "factice-codex-1", "displayName": "Factice Codex 1", "isDefault": True,
         "supportedReasoningEfforts": ["low", "medium", "high", "xhigh"], "defaultReasoningEffort": "medium",
         "serviceTiers": ["default", "priority"], "defaultServiceTier": "default"},
        {"id": "factice-codex-2", "isDefault": False, "supportedReasoningEfforts": ["low", "ultracode"]},
    ],
    "quotas": {"pourcentage_utilise": 12.5, "remise_a_zero": "2026-09-26T13:00:00+00:00"},
    "depots": [{"alias": "jetable"}],
}


def _releve(**modifs):
    donnees = copy.deepcopy(RELEVE)
    donnees.update(modifs)
    return donnees


def test_un_releve_complet_est_accepte():
    releve = valider_releve(RELEVE)
    assert isinstance(releve, Releve)
    assert releve.releve_le == datetime(2026, 9, 26, 8, tzinfo=UTC)
    assert releve.modele_par_defaut().id == "factice-codex-1"
    assert releve.modele("factice-codex-2").supportedReasoningEfforts == ["low", "ultracode"]
    assert releve.modele("inconnu") is None
    assert [d.alias for d in releve.depots] == ["jetable"]
    assert releve.quotas.pourcentage_utilise == 12.5


def test_quotas_et_depots_facultatifs():
    donnees = _releve()
    del donnees["quotas"], donnees["depots"], donnees["version_cli"]
    releve = valider_releve(donnees)
    assert releve.quotas is None and releve.depots == [] and releve.version_cli is None


@pytest.mark.parametrize("modifs, motif", [
    ({"voie": "poste-windows"}, "« voie » : valeurs admises : poste-codex, poste-claude"),
    ({"source": "inventee"}, "« source » : valeurs admises : poste, releve_factice"),
    ({"releve_le": "2026-09-26T08:00:00"}, "doit porter son fuseau"),
    ({"releve_le": "hier"}, "horodatage ISO 8601 illisible"),
    ({"modeles": []}, "« modeles » doit être une liste non vide"),
    ({"depots": [{"alias": "Mon Dépôt"}]}, "« alias » : format invalide"),
    ({"depots": [{"alias": "jetable"}, {"alias": "jetable"}]}, "alias en double"),
    ({"quotas": {"pourcentage_utilise": 120}}, "entre 0 et 100"),
    ({"intrus": 1}, "champ inconnu refusé : « intrus »"),
])
def test_refus_en_francais(modifs, motif):
    with pytest.raises(ValueError) as exc:
        valider_releve(_releve(**modifs))
    assert str(exc.value).startswith("Relevé refusé : ")
    assert motif in str(exc.value)


def test_refus_des_modeles_incoherents():
    donnees = _releve()
    donnees["modeles"][0]["defaultReasoningEffort"] = "max"
    with pytest.raises(ValueError, match="ne figure pas parmi ses efforts pris en charge"):
        valider_releve(donnees)
    donnees = _releve()
    donnees["modeles"][1]["isDefault"] = True
    with pytest.raises(ValueError, match="un seul modèle peut être le modèle par défaut"):
        valider_releve(donnees)
    donnees = _releve()
    donnees["modeles"][1]["id"] = "factice-codex-1"
    with pytest.raises(ValueError, match="identifiant de modèle en double"):
        valider_releve(donnees)
    donnees = _releve()
    donnees["modeles"][0]["isDefault"] = "oui"
    with pytest.raises(ValueError, match="« isDefault » doit être un booléen"):
        valider_releve(donnees)


def test_champ_obligatoire_absent():
    donnees = _releve()
    del donnees["modeles"]
    with pytest.raises(ValueError, match="champ obligatoire absent : « modeles »"):
        valider_releve(donnees)


def test_aucun_nul_dans_les_textes():
    with pytest.raises(ValueError) as exc:
        valider_releve(_releve(version_cli="1.0\x00"))
    assert "\x00" not in str(exc.value)


def test_alias_de_depot():
    assert ALIAS_DEPOT.fullmatch("jetable") and ALIAS_DEPOT.fullmatch("depot-2")
    assert not ALIAS_DEPOT.fullmatch("-x") and not ALIAS_DEPOT.fullmatch("a" * 33)
    assert not ALIAS_DEPOT.fullmatch("C:/depot")
