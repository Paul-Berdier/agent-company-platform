"""Garde « dépôt privé » côté greffon (étape P7, cahier P7 § 11.2, décision D83 ; correction K24) : la voie Codex n'est
prêtée qu'à un dépôt dont le dernier inventaire dit la visibilité MESURÉE ``prive`` ET la lecture ``ok`` ; non mesuré,
public, inconnu, lecture refusée ou dépôt absent → ``poste-codex`` fermée pour CE dépôt, en échec fermé. La voie Claude
n'est pas touchée ; ``resoudre`` passe à l'entrée suivante de la table (Hermes gère, aucune question au propriétaire) ;
la relecture croisée d'une implémentation Claude prend le repli de D91. Sans dépôt nommé, rien ne change."""

from __future__ import annotations

import pytest

from conftest import inventaire_factice, poste_confirme

PROJET = {"id": None, "titre": "Outil jetable", "depot_alias": "jetable"}


def _poste_windows(noyau, conn, mesure):
    """Poste de l'exemple (bac à sable Codex admis : la voie Codex n'est fermée que par la garde du dépôt)."""
    machine, _jeton = poste_confirme(noyau, conn)
    with noyau.base.transaction(conn):
        noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice(mesure=mesure))
    return machine


def _codex(noyau, conn, projet=PROJET):
    return noyau.routage.valider_choix(conn, classe="implementation", projet=projet, voie="poste-codex",
                                       modele="factice-codex-1", effort="medium", palier=None, source="table")


def test_depot_prive_mesure_ouvre_codex(noyau, conn):
    _poste_windows(noyau, conn, mesure=True)
    assert noyau.routage.voies_fermees(conn, depot_alias="jetable") == {}
    assert _codex(noyau, conn).voie == "poste-codex"


@pytest.mark.parametrize("mesure, raison", [
    (None, "visibilité non mesurée par l'exécutant"),
    (("public", "ok"), "visibilité mesurée : public"),
    (("inconnue", "inconnue"), "visibilité mesurée : inconnue"),
    (("prive", "refusee"), "lecture avec le jeton : refusee"),
    (("prive", "inconnue"), "lecture avec le jeton : inconnue"),
])
def test_codex_ferme_si_le_depot_n_est_pas_prouve_prive(noyau, conn, mesure, raison):
    _poste_windows(noyau, conn, mesure=mesure)
    fermees = noyau.routage.voies_fermees(conn, depot_alias="jetable")
    assert fermees == {"poste-codex": f"dépôt « jetable » non prouvé privé ({raison}) : Codex n'y travaille que sur un "
                                      "dépôt privé lu avec le jeton de lecture (D83)"}
    with pytest.raises(noyau.textes.RefusACP) as exc:
        _codex(noyau, conn)
    assert exc.value.code == "voie_fermee" and raison in exc.value.message
    # La voie Claude n'est pas touchée ; sans dépôt nommé, les voies fermées du poste sont inchangées.
    admis = noyau.routage.valider_choix(conn, classe="implementation", projet=PROJET, voie="poste-claude",
                                        modele="opus", effort="medium", palier=None, source="table")
    assert admis.voie == "poste-claude"
    assert noyau.routage.voies_fermees(conn) == {}


def test_depot_absent_de_l_inventaire(noyau, conn):
    _poste_windows(noyau, conn, mesure=True)
    raison = noyau.routage.voies_fermees(conn, depot_alias="autre")["poste-codex"]
    assert "absent du dernier inventaire de l'exécutant" in raison


def test_resoudre_passe_a_l_entree_suivante_de_la_table(noyau, conn):
    """Hermes gère : la table met Codex d'abord ; dépôt non mesuré → la résolution prend l'entrée suivante (Claude),
    sans question au propriétaire. S'il n'en reste aucune, le refus de routage existant s'applique."""
    _poste_windows(noyau, conn, mesure=None)
    noyau.routage.enregistrer_routage(conn, "implementation", [
        {"voie": "poste-codex", "modele": "factice-codex-1", "effort": "medium"},
        {"voie": "poste-claude", "modele": "opus", "effort": "medium"}], source="releve_factice", valide_par="test")
    resolution = noyau.routage.resoudre(conn, classe="implementation", projet=PROJET, ref="e1")
    assert (resolution.voie, resolution.modele) == ("poste-claude", "opus")
    noyau.routage.enregistrer_routage(conn, "implementation", [
        {"voie": "poste-codex", "modele": "factice-codex-1", "effort": "medium"}], source="releve_factice",
        valide_par="test")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.resoudre(conn, classe="implementation", projet=PROJET, ref="e1")
    assert exc.value.code == "voie_fermee" and "non prouvé privé" in exc.value.message


def test_relecture_croisee_vers_codex_prend_le_repli(noyau, conn):
    """Une implémentation Claude se relit par Codex ; Codex fermé pour ce dépôt → repli de D91 (même voie, autre
    modèle), dit dans la mention, jamais silencieux."""
    def haiku(inventaire):
        inventaire["politique"]["alias_claude_permis"] = ["opus", "opus[1m]", "sonnet", "haiku"]
    machine, _jeton = poste_confirme(noyau, conn)
    with noyau.base.transaction(conn):
        noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice(mesure=("public", "ok"), modifier=haiku))
    noyau.routage.enregistrer_routage(conn, "relecture", [{"voie": "poste-claude", "modele": "haiku"}],
                                      source="releve_factice", valide_par="test")
    resolution = noyau.routage.resoudre_relecture(conn, projet=PROJET, voie_relue="poste-claude", ref="e1",
                                                  modele_relu="opus")
    assert (resolution.voie, resolution.modele) == ("poste-claude", "haiku")
    assert "non prouvé privé" in resolution.mention


def test_lancement_avec_exploration_codex_refusee_sur_depot_public(noyau, conn):
    _poste_windows(noyau, conn, mesure=("public", "ok"))
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.projets.lancer(conn, titre="Public", objectif="o", depot="jetable", origine="tableau_de_bord",
                             auteur="proprietaire:test",
                             exploration={"voie": "poste-codex", "modele": "factice-codex-1", "effort": "low"})
    assert exc.value.code == "exploration" and "non prouvé privé" in exc.value.message
    assert conn.execute("SELECT COUNT(*) FROM projets").fetchone()[0] == 0  # aucune écriture avant les contrôles


def test_table_de_routage_validee_pour_tout_depot(noyau, conn):
    """Une entrée de table vaut pour TOUT dépôt : sa validation (page Routage) n'est jamais jugée sur un dépôt fictif ;
    la garde s'applique à la résolution, pour le dépôt réel du projet."""
    _poste_windows(noyau, conn, mesure=None)
    entree = {"voie": "poste-codex", "modele": "factice-codex-1", "effort": "medium"}
    assert noyau.routage.admission(conn, "implementation", entree)["admise"] is True
    noyau.routage.enregistrer_routage(conn, "implementation", [entree], source="releve_factice", valide_par="test")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.resoudre(conn, classe="implementation", projet=PROJET, ref="e1")
    assert exc.value.code == "voie_fermee"
