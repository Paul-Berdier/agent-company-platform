"""Simulateurs d’inventaire : aucun Docker, processus agent ou compte réel."""
import importlib
import importlib.util
import json
import sqlite3
from contextlib import nullcontext
from types import ModuleType
from pathlib import Path
import sys

import pytest
from acp_poste_contrat.inventaire import InventairePoste

RACINE = Path(__file__).resolve().parents[2]


def _module(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def simulateur(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    fp = _module("_faux_poste_test_distant", RACINE / "hermes/tests/outils/faux_poste.py")
    monkeypatch.setattr(fp, "FIXTURES", RACINE / "hermes/tests/outils/fixtures_machine")
    return fp


def test_inventaire_windows_reste_un_temoin_refuse(simulateur):
    distant = _module("_garde_fixture_distante", RACINE / "hermes/plugins/acp-poste/noyau/distant.py")
    inventaire = simulateur.inventaire_de_l_exemple()
    valide = InventairePoste.model_validate(inventaire)
    assert valide.poste.plateforme == "windows"
    assert distant.raison_inventaire(inventaire) is not None
    assert inventaire["bac_a_sable_codex"] is not None


def test_inventaire_linux_simule_admis_garde_catalogues_historiques(simulateur):
    distant = _module("_garde_fixture_distante", RACINE / "hermes/plugins/acp-poste/noyau/distant.py")
    ancien = simulateur.inventaire_de_l_exemple()
    inventaire = simulateur.inventaire_de_l_exemple(linux_distant=True)
    InventairePoste.model_validate(inventaire)
    assert distant.raison_inventaire(inventaire) is None
    assert (inventaire["poste"]["plateforme"], inventaire["poste"]["hote"]) == ("linux", "railway")
    assert inventaire["bac_a_sable_codex"] is None
    assert inventaire["isolement_linux"]["ecriture_admise"] == {"codex": True, "claude": True}
    assert inventaire["isolement_linux"]["sonde_le"] == inventaire["releve_le"]
    assert set(inventaire["politique"]["conditions"]) == {"codex", "claude"}
    for nouveau, avant in zip(inventaire["releves"], ancien["releves"], strict=True):
        assert nouveau["modeles"] == avant["modeles"]
        assert nouveau["origine_liste"] == avant["origine_liste"]


def test_inventaire_simule_recu_permet_le_projet_du_contrat(simulateur, monkeypatch):
    """Réception, SQLite, gardes et lancement réels ; kanban Hermes seul est doublé.

    Complète le chemin positif du contrat HTTP sans Docker, CLI ni compte personnel.
    """
    nom = "_noyau_fixture_distante"
    dossier = RACINE / "hermes/plugins/acp-poste/noyau"
    spec = importlib.util.spec_from_file_location(
        nom, dossier / "__init__.py", submodule_search_locations=[str(dossier)])
    paquet = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, nom, paquet)
    spec.loader.exec_module(paquet)
    ka = ModuleType(nom + ".kanban_adapter")
    ka.VOIE_INTEGRATION = "poste-integration"
    ka.VOIES_POSTE = ("poste-codex", "poste-claude")
    ka.PROFIL_HERMES = "default"
    ka.CREATEUR = "acp-poste"
    ka.PREFIXE_CLE = "acp:"
    ka.masquer = lambda texte: texte
    ka.get_state = lambda: None
    ka.effort_hermes = lambda effort: effort
    ka.create_board = lambda *args, **kwargs: None
    ka.connexion = lambda tableau: nullcontext(None)
    ka.write_txn = lambda conn: nullcontext(None)
    ka.dernier_evenement = lambda conn: 0
    cartes_creees = []

    def creer_carte(conn, **champs):
        cartes_creees.append(champs)
        return f"c{len(cartes_creees)}"

    ka.create_task = creer_carte
    monkeypatch.setitem(sys.modules, ka.__name__, ka)
    base = importlib.import_module(nom + ".base")
    inventaire = importlib.import_module(nom + ".inventaire")
    ordres = importlib.import_module(nom + ".ordres")
    routage = importlib.import_module(nom + ".routage")
    projets = importlib.import_module(nom + ".projets")
    refus = importlib.import_module(nom + ".textes").RefusACP
    machine = "m" + "1" * 11
    demande = dict(titre="Projet sur le dépôt jetable", objectif="Vérifier le dépôt.", depot="jetable",
                   exploration={"voie": "poste-codex", "modele": "factice-codex-1", "effort": "low"},
                   origine="tableau_de_bord", auteur="proprietaire:test")
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        base.migrer(conn)
        conn.execute("INSERT INTO machines (id,nom,empreinte_jeton,etat,protocole,version_poste,cree_le) "
                     "VALUES (?,?,?,'actif','acp-machine/1','2.0.0',?)",
                     (machine, "Serveur simulé", "1" * 64, base.maintenant()))
        with base.transaction(conn):
            inventaire.recevoir_dans(conn, machine, simulateur.inventaire_de_l_exemple())
        with pytest.raises(refus) as erreur:
            projets.lancer(conn, **demande)
        assert erreur.value.code == "exploration"
        assert "serveur distant Linux" in erreur.value.message
        assert conn.execute("SELECT count(*) FROM projets").fetchone()[0] == 0
        assert not cartes_creees
        assert inventaire.delai_avant_prochain(conn, machine) > 0
        ordre = ordres.creer(conn, machine, "releve", "proprietaire:test")
        with base.transaction(conn):
            ordres.livrer_dans(conn, [ordre])
            assert inventaire.delai_avant_prochain(conn, machine) == 0
            recu = inventaire.recevoir_dans(
                conn, machine, simulateur.inventaire_de_l_exemple(linux_distant=True))
        assert ordres.dus(conn, machine) == []
        assert "poste-codex" not in routage.voies_fermees(conn, depot_alias="jetable")
        releve = conn.execute("SELECT * FROM releves WHERE id = ?", (recu["releves"]["poste-codex"],)).fetchone()
        assert releve["source"] == "poste" and releve["machine_id"] == machine
        contenu = json.loads(releve["contenu"])
        assert contenu["quotas"]["pourcentage_utilise"] < float(base.reglage(conn, "seuil_quota_pct"))
        resultat = projets.lancer(conn, **demande)
        assert resultat["projet"]["etat"] == "actif" and resultat["projet"]["depot"] == "jetable"
        exploration = conn.execute("SELECT * FROM demandes WHERE role = 'exploration'").fetchone()
        assert (exploration["voie"], exploration["modele"], exploration["effort"], exploration["depot_alias"]) == (
            "poste-codex", "factice-codex-1", "low", "jetable")
        assert exploration["releve_id"] == recu["releves"]["poste-codex"]
        assert exploration["source_routage"] == "choix_explicite"
        assert len(cartes_creees) == 2
        assert cartes_creees[0]["model_override"] == "factice-codex-1"
        assert cartes_creees[0]["reasoning_effort"] == "low"
        assert cartes_creees[1]["parents"] == [exploration["carte"]]
    finally:
        conn.close()
        for cle in list(sys.modules):
            if cle.startswith(nom + ".") and cle != ka.__name__:
                sys.modules.pop(cle, None)
