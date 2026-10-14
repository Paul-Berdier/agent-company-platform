"""Un ancien PC ne reçoit aucune carte, même s'il se déclare prêt.

Vrais noyau, base et kanban Hermes jetables ; inventaires et compte simulés.
Ces tests ne prouvent pas l'emplacement physique ni une inférence fournisseur.
"""

import pytest

from conftest import inventaire_factice, inventaire_linux, lancer_sur_depot, poste_confirme
from acp_poste_contrat.machine import RequeteReclamer


def requete():
    return RequeteReclamer.model_validate({
        "protocole": "acp-machine/1", "version_poste": "2.0.0",
        "peut_executer": True, "politique_valide": True, "ordres_acquittes": [],
        "attente_max_s": 5, "voies_disponibles": ["poste-claude"], "carte_en_cours": None,
        "espace_libre_mio": 4096,
    })


def publier(noyau, conn, machine, inventaire):
    with noyau.base.transaction(conn):
        noyau.inventaire.recevoir_dans(conn, machine, inventaire)


@pytest.mark.parametrize("ancien", [False, True], ids=["inventaire-absent", "ancien-windows"])
def test_aucune_attribution_sans_serveur_distant(noyau, conn, ancien):
    projet = lancer_sur_depot(noyau, conn)
    machine, _ = poste_confirme(noyau, conn)
    if ancien:
        publier(noyau, conn, machine, inventaire_factice())
    assert noyau.execution.servir(machine, requete()) is None
    assert noyau.machines.machine(conn, machine)["etat"] == "actif"
    with noyau.ka.connexion(projet["tableau"]) as kc:
        tache = noyau.ka.get_task(kc, projet["cartes"]["exploration"])
        assert tache.status == "ready"
        assert tache.claim_lock is None


@pytest.mark.parametrize("hote", ["railway", "vps"])
def test_serveur_linux_recoit_la_carte_et_client_absent_sans_effet(noyau, conn, hote):
    machine, _ = poste_confirme(noyau, conn, nom="Serveur de test")
    inventaire = inventaire_linux()
    inventaire["poste"].update(hote=hote, execution_distante_declaree=hote == "vps")
    publier(noyau, conn, machine, inventaire)
    # Le label VPS ne débloque jamais Codex en régime B ; source quotas Linux conservée.
    assert "poste-codex" in noyau.routage.voies_fermees(conn)
    assert noyau.quotas.vue(conn)["poste-claude"]["source"] == "claude_code_rate_limit_event"
    # Le catalogue Linux simulé expose « opus », pas le modèle factice-claude-1 de P4.
    # Créer la carte contre ce catalogue : aucun relevé factice tardif ne le remplace.
    projet = noyau.projets.lancer(
        conn, titre="Mission distante simulée", objectif="Explorer le dépôt jetable.",
        profil="base", depot="jetable", origine="tableau_de_bord", auteur="proprietaire:test",
        exploration={"voie": "poste-claude", "modele": "opus", "effort": "low"})["projet"]
    carte = noyau.execution.servir(machine, requete())
    assert carte is not None and carte["tableau"] == projet["tableau"]
    assert carte["modele"] == "opus"
    # Il n'y a aucun client desktop dans cet essai. La carte est portée par
    # l'identité distante et sa réclamation reste dans le kanban du serveur.
    with noyau.ka.connexion(projet["tableau"]) as kc:
        tache = noyau.ka.get_task(kc, carte["carte"])
        assert tache.status == "running"
        assert tache.claim_lock == noyau.execution.claimer(machine)
    assert noyau.execution.vue_executant(conn)["refus_distant"] is None


def test_un_inventaire_windows_plus_recent_ferme_les_deux_moteurs(noyau, conn):
    machine, _ = poste_confirme(noyau, conn)
    publier(noyau, conn, machine, inventaire_linux())
    publier(noyau, conn, machine, inventaire_factice())
    fermees = noyau.routage.voies_fermees(conn)
    assert set(fermees) == {"poste-codex", "poste-claude"}
    assert all("uniquement sur un serveur distant" in raison for raison in fermees.values())
    assert noyau.execution.vue_executant(conn)["refus_distant"] is not None
