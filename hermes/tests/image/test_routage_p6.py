"""Routage de l'étape P6 (cahier P6 § 4.3, § 6.7, § 7.3) : inventaire Linux de l'exécutant reçu ; voies fermées
d'après le dernier inventaire (isolement, conditions d'usage) ; repli de la relecture par la même voie avec un AUTRE
modèle (D91, appliqué) et D27 tant que le réglage est levé ; classe ``integration`` ouverte ; changement d'isolement
notifié ; vue de l'exécutant et bloc de /v1/meta."""

from __future__ import annotations

import pytest

from conftest import inventaire_factice, inventaire_linux, lancer_sur_depot, poste_confirme

PROJET = {"id": None, "titre": "Outil jetable", "depot_alias": "jetable"}


def _recevoir(noyau, conn, machine, inventaire):
    with noyau.base.transaction(conn):
        return noyau.inventaire.recevoir_dans(conn, machine, inventaire)


def _executant(noyau, conn, modifier=None):
    machine, _jeton = poste_confirme(noyau, conn, nom="Exécutant Railway")
    reponse = _recevoir(noyau, conn, machine, inventaire_linux(modifier=modifier))
    return machine, reponse


def _permettre_haiku(inventaire):
    inventaire["politique"]["alias_claude_permis"] = ["opus", "opus[1m]", "haiku"]


def test_inventaire_linux_recu(noyau, conn):
    machine, reponse = _executant(noyau, conn)
    assert set(reponse["releves"]) == {"poste-codex", "poste-claude"}
    assert reponse["alertes"] == ["Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la "
                                  "plateforme (régime B) : voie Codex fermée en écriture."]
    ligne = conn.execute("SELECT plateforme, hote FROM machines WHERE id = ?", (machine,)).fetchone()
    assert tuple(ligne) == ("linux", "railway")


def test_voies_fermees_d_apres_l_inventaire(noyau, conn):
    _executant(noyau, conn)
    fermees = noyau.routage.voies_fermees(conn)
    assert list(fermees) == ["poste-codex"] and "régime B" in fermees["poste-codex"]
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.valider_choix(conn, classe="implementation", projet=PROJET, voie="poste-codex",
                                    modele="factice-codex-1", effort="medium", palier=None, source="table")
    assert exc.value.code == "voie_fermee" and exc.value.message.startswith(
        "Refusé par ACP : la voie poste-codex est fermée sur l'exécutant : isolement de l'exécutant (régime B)")
    admis = noyau.routage.valider_choix(conn, classe="implementation", projet=PROJET, voie="poste-claude",
                                        modele="opus", effort="medium", palier=None, source="table")
    assert (admis.voie, admis.modele) == ("poste-claude", "opus")


def test_conditions_non_decidees_ferment_la_voie(noyau, conn):
    def sans_decision(inventaire):
        inventaire["politique"]["conditions"] = {"codex": "2026-10-01", "claude": None}
        inventaire["isolement_linux"].update(regime="A", bwrap="fonctionne", reseau_coupe=True,
                                             ecriture_admise={"codex": True, "claude": True}, raison=None)
    machine, reponse = _executant(noyau, conn, sans_decision)
    assert noyau.routage.voies_fermees(conn) == {"poste-claude": "conditions d'usage de Claude Code non décidées par le "
                                                                 "propriétaire (politique de l'exécutant)"}
    assert ("Conditions d'usage de Claude Code non décidées dans la politique de l'exécutant : voie fermée."
            in reponse["alertes"])


def test_inventaire_windows_p5_ne_ferme_rien(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)
    _recevoir(noyau, conn, machine, inventaire_factice())
    assert noyau.routage.voies_fermees(conn) == {}


def test_relecture_repli_meme_voie_autre_modele(noyau, conn):
    _executant(noyau, conn, _permettre_haiku)
    noyau.routage.enregistrer_routage(conn, "relecture", [{"voie": "poste-claude", "modele": "opus"},
                                                          {"voie": "poste-claude", "modele": "haiku"}],
                                      source="releve_factice", valide_par="test")
    resolution = noyau.routage.resoudre_relecture(conn, projet=PROJET, voie_relue="poste-claude", ref="e1",
                                                  modele_relu="opus")
    assert (resolution.voie, resolution.modele) == ("poste-claude", "haiku")  # jamais le modèle de l'implémentation
    assert "relecture de repli par la même voie, autre modèle (D91)" in resolution.mention


def test_relecture_repli_sans_autre_modele_refusee(noyau, conn):
    _executant(noyau, conn, _permettre_haiku)
    noyau.routage.enregistrer_routage(conn, "relecture", [{"voie": "poste-claude", "modele": "opus"}],
                                      source="releve_factice", valide_par="test")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.resoudre_relecture(conn, projet=PROJET, voie_relue="poste-claude", ref="e1", modele_relu="opus")
    assert exc.value.code == "relecture_impossible"
    assert "le modèle « opus » est celui de l'implémentation" in exc.value.message


def test_relecture_repli_refusee_sans_d88(noyau, conn):
    """D27 s'applique tant que le repli (D91) n'est pas admis : le réglage levé, la relecture est refusée."""
    _executant(noyau, conn, _permettre_haiku)
    noyau.routage.enregistrer_routage(conn, "relecture", [{"voie": "poste-claude", "modele": "haiku"}],
                                      source="releve_factice", valide_par="test")
    noyau.base.poser_reglage(conn, "relecture_repli_meme_voie", False, "test")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.resoudre_relecture(conn, projet=PROJET, voie_relue="poste-claude", ref="e1", modele_relu="opus")
    assert exc.value.code == "relecture_impossible" and "exige l'autre exécutant" in exc.value.message


def test_classe_integration_ouverte(noyau, conn):
    resolution = noyau.routage.resoudre(conn, classe="integration", projet=PROJET, ref="int")
    assert (resolution.voie, resolution.modele, resolution.effort, resolution.source_routage) == (
        "poste-integration", None, None, "sans_objet")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.resoudre(conn, classe="integration", projet=dict(PROJET, depot_alias=None), ref="int")
    assert exc.value.code == "sans_depot"
    assert "integration" not in noyau.routage.CLASSES_TABLE  # rien à valider dans la table


def test_isolement_change_notifie(noyau, conn):
    machine, _reponse = _executant(noyau, conn)

    def regime_a(inventaire):
        inventaire["isolement_linux"].update(regime="A", bwrap="fonctionne", reseau_coupe=True,
                                             ecriture_admise={"codex": True, "claude": True}, raison=None)
    _recevoir(noyau, conn, machine, inventaire_linux(modifier=regime_a))
    _recevoir(noyau, conn, machine, inventaire_linux(modifier=regime_a))  # inchangé : aucune autre notification
    notes = [tuple(l) for l in conn.execute("SELECT genre, texte FROM notifications WHERE genre = 'isolement'")]
    assert len(notes) == 1 and notes[0][1].startswith("ACP — Isolement de l'exécutant changé (régime A)")


def test_vue_executant(noyau, conn):
    assert noyau.execution.vue_executant(conn) == {"connu": False}
    machine, _reponse = _executant(noyau, conn)
    vue = noyau.execution.vue_executant(conn)
    assert (vue["plateforme"], vue["hote"], vue["noyau"]) == ("linux", "railway", "6.12.10")
    assert vue["isolement"]["regime"] == "B" and vue["bac_a_sable_codex"] is None
    assert vue["conditions"] == {"codex": "2026-10-01", "claude": "2026-10-01"}
    assert vue["bornes"] == {"cartes_par_jour": 20, "duree_max_carte_s": 3600, "concurrence": 1}
    assert vue["peut_executer"] is None and vue["voies_disponibles"] is None  # aucune réclamation encore : inconnu
    assert list(vue["voies_fermees"]) == ["poste-codex"]
    assert vue["carte_en_cours"] is None and vue["branches_pretes"] == [] and vue["revues"] == 0


def test_carte_voie_fermee_apres_composition_signalee(noyau, conn, monkeypatch):
    """Voie fermée APRÈS la composition (régime A → B au redémarrage) : la carte n'est jamais réassignée en silence ;
    notée en attente (page Poste), puis bloquée avec la raison au-delà de 30 min."""
    from conftest import en_worker, outil, reclamer, terminer

    projet = lancer_sur_depot(noyau, conn)
    reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    terminer(noyau, projet["tableau"], projet["cartes"]["exploration"], "Carte du dépôt.")
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    plan = {"resume": "Une étape.", "etapes": [{"ref": "e1", "titre": "Écrire", "classe": "implementation",
                                                "consigne": "Écrire.", "voie": "poste-codex", "relecture": False}]}
    tour = outil(noyau, "projet_planifier", plan)
    assert tour["ok"], tour
    impl = next(c["carte"] for c in tour["cartes"] if c["role"] == "implementation")
    _executant(noyau, conn)  # l'exécutant publie maintenant le régime B : Codex fermé
    assert noyau.execution.signaler_voies_fermees(conn) == []
    attente = noyau.execution.cartes_en_attente_de_voie(conn)
    assert [(a["carte"], a["voie"]) for a in attente] == [(impl, "poste-codex")] and "régime B" in attente[0]["raison"]
    debut = noyau.base.maintenant()
    noyau.base.fixer_horloge(lambda: debut + 1801)
    try:
        assert noyau.execution.signaler_voies_fermees(conn) == [impl]
    finally:
        noyau.base.fixer_horloge(None)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        tache = noyau.ka.get_task(kc, impl)
        raison = [e.payload for e in noyau.ka.list_events(kc, impl) if e.kind == "blocked"][-1]["reason"]
    assert tache.status == "blocked" and raison.startswith("Voie poste-codex fermée depuis plus de 30 min")
    assert noyau.execution.cartes_en_attente_de_voie(conn) == []



def test_alerte_a_trente_jours_de_l_echeance_du_jeton_claude(noyau, conn):
    """Relecture de P6 : l'exécutant publie la date d'expiration estimée de son jeton Claude ; la page Poste l'annonce
    à 30 jours (alerte de l'inventaire), sans jamais rien du jeton."""
    from datetime import date

    inventaire = noyau.inventaire.valider_corps(inventaire_linux(
        modifier=lambda i: i["connexions"].update(claude_echeance="2027-09-30")))
    loin = noyau.inventaire.alertes_de(inventaire, aujourdhui=date(2027, 8, 30))
    proche = noyau.inventaire.alertes_de(inventaire, aujourdhui=date(2027, 9, 1))
    assert not any("Jeton Claude" in a for a in loin)
    assert ("Jeton Claude de l'exécutant : expiration estimée le 2027-09-30 (setup-token valable un an) ; renouvelez-le"
            in " ".join(proche))
    machine, _reponse = _executant(noyau, conn, modifier=lambda i: i["connexions"].update(claude_echeance="2026-10-15"))
    assert any("expiration estimée le 2026-10-15" in a for a in noyau.inventaire.dernier(conn, machine)["alertes"])
