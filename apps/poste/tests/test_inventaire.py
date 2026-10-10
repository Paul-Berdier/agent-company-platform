"""Inventaire du poste (cahier P5 § 11) : conforme au contrat D21 étendu, garde « aucun identifiant » avant l'envoi."""

from __future__ import annotations

import copy

import pytest

from acp_poste.inventaire import InventaireRetenu, construire, relever
from acp_poste.politique import charger
from acp_poste_contrat.inventaire import valider_inventaire

JETON_CLAUDE = "sk-ant-oat01-" + "w" * 40


async def _resultats(poste, depots: bool = False):
    if depots:
        depot = poste.racine / "depots" / "jetable"
        (depot / ".git").mkdir(parents=True)
        poste.ecrire_politique(poste.toml() + f"\n[depots.jetable]\nchemin = '{depot}'\n")
    else:
        poste.ecrire_politique()
    poste.preparer_profil_codex()
    politique = charger(poste.emplacements)
    codex, claude = await relever(politique, emplacements=poste.emplacements, coffre=poste.coffre,
                                  lanceurs=poste.lanceurs())
    return politique, codex, claude


async def test_conforme_au_contrat(poste):
    politique, codex, claude = await _resultats(poste)
    inventaire = construire(politique, codex, claude, windows="10.0.19045", valeurs_exactes=[])
    valide = valider_inventaire(inventaire)
    assert valide.protocole == "acp-machine/1" and valide.version_poste == "1.0.1"
    assert valide.poste.windows == "10.0.19045" and valide.poste.politique_empreinte == politique.empreinte
    assert valide.versions["codex"].conforme is True and valide.versions["claude"].conforme is True
    assert valide.bac_a_sable_codex.ecriture_admise is True
    assert all(r.quotas is None and r.source == "poste" for r in valide.releves)


async def test_depots_recopies(poste):
    politique, codex, claude = await _resultats(poste, depots=True)
    inventaire = construire(politique, codex, claude, windows="10.0.19045", valeurs_exactes=[])
    assert inventaire["depots"] == [{"alias": "jetable"}]
    assert all(r["depots"] == [{"alias": "jetable"}] for r in inventaire["releves"])
    assert "depots" not in codex.releve, "le relevé de la sonde n'est pas modifié"


async def test_visibilite_mesuree_publiee_par_depot(poste):
    """Étape P7 (cahier P7 § 11.2) : un dépôt mesuré porte ``visibilite``, ``lecture`` et ``verifie_le`` (dans
    l'inventaire et dans chaque relevé) ; un dépôt NON mesuré reste ``{"alias"}`` (jamais une mesure inventée) ; une
    mesure d'un alias hors de la politique n'est pas publiée."""
    from datetime import UTC, datetime

    from acp_poste.depots import Visibilite

    politique, codex, claude = await _resultats(poste, depots=True)
    instant = datetime(2026, 10, 2, 12, 30, tzinfo=UTC)
    mesures = {"jetable": Visibilite("prive", "ok", instant, "accès anonyme refusé"),
               "absent": Visibilite("public", "ok", instant, "")}
    inventaire = construire(politique, codex, claude, windows="10.0.19045", valeurs_exactes=[], mesures=mesures)
    attendu = [{"alias": "jetable", "visibilite": "prive", "lecture": "ok", "verifie_le": "2026-10-02T12:30:00Z"}]
    assert inventaire["depots"] == attendu and all(r["depots"] == attendu for r in inventaire["releves"])
    assert "accès anonyme" not in str(inventaire), "la raison reste au journal de l'exécutant"
    valide = valider_inventaire(inventaire)
    assert valide.depots[0].visibilite == "prive" and valide.depots[0].lecture == "ok"
    sans = construire(politique, codex, claude, windows="10.0.19045", valeurs_exactes=[], mesures={})
    assert sans["depots"] == [{"alias": "jetable"}]


@pytest.mark.parametrize("injection, raison", [
    ("titulaire@example.com", "adresse électronique"),
    ("C:\\Users\\Paul\\AppData", "chemin de lecteur"),
    ("D:/depots/prive", "chemin de lecteur"),
    ("voir \\\\serveur\\partage", "chemin réseau"),
    ("/Users/paul/x", "chemin de profil"),
    ("acpm_" + "x" * 43, "jeton machine"),
    ("sk-proj-" + "a" * 30, "secret"),
    (JETON_CLAUDE, "secret"),
])
async def test_aucun_identifiant(poste, injection, raison):
    politique, codex, claude = await _resultats(poste)
    altere = copy.deepcopy(codex)
    altere.releve["detail"] = f"texte avec {injection}"
    with pytest.raises(InventaireRetenu) as exc:
        construire(politique, altere, claude, windows="10.0.19045", valeurs_exactes=[JETON_CLAUDE])
    message = str(exc.value)
    assert raison in message and injection not in message


async def test_valeur_exacte_du_coffre_refusee(poste):
    politique, codex, claude = await _resultats(poste)
    altere = copy.deepcopy(claude)
    altere.releve["detail"] = "jeton-sans-forme-connue-du-coffre"
    with pytest.raises(InventaireRetenu, match="valeur du coffre"):
        construire(politique, codex, altere, windows="10.0.19045",
                   valeurs_exactes=["jeton-sans-forme-connue-du-coffre"])


async def test_bornes(poste):
    politique, codex, claude = await _resultats(poste)
    trop = copy.deepcopy(codex)
    trop.releve["modeles"] = [dict(trop.releve["modeles"][1], id=f"m-{n}") for n in range(201)]
    with pytest.raises(InventaireRetenu, match="au plus 200 modèles"):
        construire(politique, trop, claude, windows="10.0.19045", valeurs_exactes=[])
    with pytest.raises(InventaireRetenu, match="Aucune sonde active"):
        construire(politique, None, None, windows="10.0.19045", valeurs_exactes=[])


async def test_sonde_codex_desactivee_bac_non_sonde(poste):
    politique, codex, claude = await _resultats(poste)
    inventaire = construire(politique, None, claude, windows="10.0.19045", valeurs_exactes=[])
    assert [r["voie"] for r in inventaire["releves"]] == ["poste-claude"]
    assert inventaire["bac_a_sable_codex"]["ecriture_admise"] is False
    assert "désactivée" in inventaire["bac_a_sable_codex"]["raison"]
    assert inventaire["connexions"]["codex"] == "inconnu" and "codex" not in inventaire["versions"]
