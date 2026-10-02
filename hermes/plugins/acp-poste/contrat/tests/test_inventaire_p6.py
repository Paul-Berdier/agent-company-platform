"""Inventaire, variante Linux de l'exécutant Railway (cahier P6 § 7.3) : compatible avec P5 (un inventaire Windows de
P5 reste valide sans changement), un seul bloc d'isolement par plateforme, verdict de la sonde cohérent, conditions
d'usage et bornes d'exécution dans la politique."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from acp_poste_contrat.inventaire import identifiant_trouve, valider_inventaire

FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "outils" / "fixtures_machine"


def _fixture(nom: str) -> dict:
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


def _linux(**modifs_isolement) -> dict:
    inventaire = copy.deepcopy(_fixture("inventaire_requete_linux.json"))
    inventaire["isolement_linux"].update(modifs_isolement)
    return inventaire


def _refus(donnees) -> str:
    with pytest.raises(ValueError) as exc:
        valider_inventaire(donnees)
    return str(exc.value)


def test_inventaire_windows_p5_toujours_valide():
    """Un inventaire publié par un poste P5 (sans aucune clé de P6) reste valide sans changement ; l'exemple partagé
    porte « isolement_linux »: null, forme sérialisée par le poste depuis P6."""
    p5 = _fixture("inventaire_requete.json")
    assert p5.pop("isolement_linux") is None
    inventaire = valider_inventaire(p5)
    assert inventaire.poste.plateforme == "windows" and inventaire.poste.hote == "pc"
    assert inventaire.isolement_linux is None and inventaire.bac_a_sable_codex is not None
    assert inventaire.politique.conditions == {} and inventaire.politique.cartes_par_jour is None


def test_inventaire_linux_accepte():
    inventaire = valider_inventaire(_fixture("inventaire_requete_linux.json"))
    assert inventaire.poste.plateforme == "linux" and inventaire.poste.compte == "uid_dedie"
    assert inventaire.isolement_linux.regime == "B" and inventaire.isolement_linux.ecriture_admise == {
        "codex": False, "claude": True}
    assert str(inventaire.politique.conditions["claude"]) == "2026-10-01"
    assert (inventaire.politique.cartes_par_jour, inventaire.politique.concurrence) == (20, 1)
    # Aucun identifiant dans l'exemple : la garde de la réception passe.
    assert identifiant_trouve(_fixture("inventaire_requete_linux.json")) is None


def test_un_seul_isolement_par_plateforme():
    linux = _fixture("inventaire_requete_linux.json")
    windows = _fixture("inventaire_requete.json")
    assert "un exécutant Linux publie « isolement_linux », et lui seul" in _refus(
        dict(linux, bac_a_sable_codex=windows["bac_a_sable_codex"]))
    assert "un exécutant Linux publie « isolement_linux », et lui seul" in _refus(dict(linux, isolement_linux=None))
    assert "un poste Windows publie « bac_a_sable_codex », et lui seul" in _refus(
        dict(windows, isolement_linux=linux["isolement_linux"]))


@pytest.mark.parametrize("poste, motif", [
    ({"compte": "dedie"}, "sous Linux, seul « uid_dedie » est admis"),
    ({"windows": "10.0.19045"}, "« windows » : sans objet sous Linux"),
    ({"hote": "nuage"}, "valeurs admises : pc, railway"),
    ({"noyau": "six"}, "« noyau » : format invalide"),
])
def test_infos_linux_refusees(poste, motif):
    inventaire = _fixture("inventaire_requete_linux.json")
    inventaire["poste"].update(poste)
    assert motif in _refus(inventaire)


def test_uid_dedie_refuse_sous_windows():
    inventaire = _fixture("inventaire_requete.json")
    inventaire["poste"]["compte"] = "uid_dedie"
    assert "réservés à Linux" in _refus(inventaire)
    inventaire = _fixture("inventaire_requete.json")
    del inventaire["poste"]["windows"]
    assert "version de Windows exigée pour un poste Windows" in _refus(inventaire)


@pytest.mark.parametrize("modifs, motif", [
    ({"regime": "A"}, "régime « A » : exige bubblewrap fonctionnel"),
    ({"uid_separes": False}, "aucune écriture sans identifiants séparés"),
    ({"uid_separes": None}, "aucune écriture sans identifiants séparés"),
    ({"ecriture_admise": {"codex": True, "claude": True}}, "refusée en régime B tant que D79 vaut « refuse »"),
    ({"raison": None}, "une écriture refusée doit dire pourquoi"),
    ({"ecriture_admise": {"claude": True}}, "un booléen pour « codex » et un pour « claude »"),
    ({"regime": "C"}, "valeurs admises : A, B, inconnu"),
    ({"codex_sans_bac_a_sable": "toujours"}, "valeurs admises : refuse, edition_seule, acces_complet"),
])
def test_matrice_de_l_isolement(modifs, motif):
    assert motif in _refus(_linux(**modifs))


def test_regime_a_et_inconnu():
    a = valider_inventaire(_linux(regime="A", bwrap="fonctionne", reseau_coupe=True, proc_neuf=False,
                                  ecriture_admise={"codex": True, "claude": True}, raison=None))
    assert a.isolement_linux.regime == "A"
    inconnu = valider_inventaire(_linux(regime="inconnu", bwrap="inconnu", reseau_coupe=None, uid_separes=None,
                                        proc_neuf=None, ecriture_admise={"codex": False, "claude": False},
                                        raison="Sonde de plateforme pas encore faite : écriture refusée."))
    assert not any(inconnu.isolement_linux.ecriture_admise.values())
    # D79 option (b) ou (a) : Codex admis en régime B si le propriétaire l'a décidé dans la politique.
    edition = valider_inventaire(_linux(codex_sans_bac_a_sable="edition_seule",
                                        ecriture_admise={"codex": True, "claude": True}, raison=None))
    assert edition.isolement_linux.ecriture_admise["codex"] is True


@pytest.mark.parametrize("politique, motif", [
    ({"conditions": {"gemini": "2026-10-01"}}, "« conditions » : clé inconnue refusée"),
    ({"conditions": {"codex": "01/10/2026"}}, "date ISO 8601 (AAAA-MM-JJ) illisible"),
    ({"conditions": {"codex": 20261001}}, "date ISO 8601 (AAAA-MM-JJ) ou null attendue"),
    ({"cartes_par_jour": 0}, "« cartes_par_jour » doit être un entier compris entre 1 et 1000"),
    ({"duree_max_carte_s": 30}, "« duree_max_carte_s » doit être un entier compris entre 60 et 86400"),
    ({"concurrence": True}, "« concurrence » doit être un entier"),
])
def test_politique_p6_refusee(politique, motif):
    inventaire = _fixture("inventaire_requete_linux.json")
    inventaire["politique"].update(politique)
    assert motif in _refus(inventaire)


def test_conditions_non_decidees():
    inventaire = _fixture("inventaire_requete_linux.json")
    inventaire["politique"]["conditions"] = {"codex": None, "claude": "2026-10-01"}
    assert valider_inventaire(inventaire).politique.conditions["codex"] is None



def test_echeance_du_jeton_claude_facultative():
    """Relecture de P6 : date d'expiration ESTIMÉE du jeton Claude de l'exécutant, facultative (un inventaire antérieur
    reste valide), jamais autre chose qu'une date."""
    inventaire = _fixture("inventaire_requete_linux.json")
    assert valider_inventaire(inventaire).connexions.claude_echeance is None
    inventaire["connexions"]["claude_echeance"] = "2027-09-30"
    assert valider_inventaire(inventaire).connexions.claude_echeance.isoformat() == "2027-09-30"
    for valeur, motif in (("30/09/2027", "illisible"), ("2027-09-30T00:00:00Z", "illisible"), (20270930, "attendue"),
                          ("1999-01-01", "hors bornes")):
        inventaire["connexions"]["claude_echeance"] = valeur
        assert motif in _refus(inventaire), valeur
