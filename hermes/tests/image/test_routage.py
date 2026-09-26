"""Routage déterministe et catalogue relevé du poste (cahier P4 § 7)."""

from __future__ import annotations

import datetime as dt

import pytest

from conftest import (carte, en_discussion, en_worker, lancer_sans_depot, lancer_sur_depot, outil, reclamer,
                      releve_factice, terminer)

PROJET_DEPOT = {"id": "p_essai", "titre": "Essai", "depot_alias": "jetable"}
PROJET_SANS_DEPOT = {"id": "p_essai", "titre": "Essai", "depot_alias": None}


def test_ordre_de_resolution(noyau, conn):
    r = noyau.routage
    r.enregistrer_releve(conn, releve_factice("poste-codex"))
    r.enregistrer_releve(conn, releve_factice("poste-claude"))
    r.enregistrer_routage(conn, "implementation", [{"voie": "poste-claude", "modele": "factice-claude-2",
                                                    "effort": "low"}], source="releve_factice", valide_par="test")
    # 3. Table.
    res = r.resoudre(conn, classe="implementation", projet=PROJET_DEPOT)
    assert (res.voie, res.modele, res.effort, res.source_routage) == ("poste-claude", "factice-claude-2", "low", "table")
    # 2. Choix explicite, avant la table.
    res = r.resoudre(conn, classe="implementation", projet=PROJET_DEPOT, voie="poste-codex", effort="high")
    assert (res.voie, res.modele, res.effort, res.source_routage) == ("poste-codex", "factice-codex-1", "high",
                                                                       "choix_explicite")
    # Modèle seul : la voie est celle dont le relevé le contient.
    assert r.resoudre(conn, classe="implementation", projet=PROJET_DEPOT, modele="factice-claude-1").voie == "poste-claude"
    # 1. Surcharge du propriétaire (projet), avant tout ; puis carte, plus précise.
    with noyau.base.transaction(conn):
        conn.execute("INSERT INTO surcharges (portee, cible, classe, voie, modele, effort, motif, auteur, cree_le) "
                     "VALUES ('projet', 'p_essai', 'implementation', 'poste-codex', 'factice-codex-2', 'low', 'm', 'p', 0)")
        conn.execute("INSERT INTO surcharges (portee, cible, classe, voie, modele, effort, motif, auteur, cree_le) "
                     "VALUES ('carte', 't_x', 'implementation', 'poste-claude', 'factice-claude-1', 'high', 'm', 'p', 0)")
    res = r.resoudre(conn, classe="implementation", projet=PROJET_DEPOT, voie="poste-claude")
    assert (res.voie, res.modele, res.source_routage) == ("poste-codex", "factice-codex-2", "surcharge_projet")
    res = r.resoudre(conn, classe="implementation", projet=PROJET_DEPOT, carte="t_x")
    assert (res.voie, res.modele, res.source_routage) == ("poste-claude", "factice-claude-1", "surcharge_carte")


def test_classes_hermes_et_projet_sans_depot(noyau, conn):
    r = noyau.routage
    for classe in ("planification", "synthese", "repondre", "recherche_web"):
        res = r.resoudre(conn, classe=classe, projet=PROJET_DEPOT)
        assert (res.voie, res.modele, res.effort_carte, res.source_routage) == ("hermes", None, None, "profil")
    # Conception et rédaction sans dépôt : Hermes.
    for classe in ("architecture", "documentation"):
        assert r.resoudre(conn, classe=classe, projet=PROJET_SANS_DEPOT).voie == "hermes"
    assert r.resoudre(conn, classe="recherche_web", projet=PROJET_DEPOT, effort="high").effort_carte == "high"


def test_aucun_modele_sans_releve(noyau, conn):
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.resoudre(conn, classe="implementation", projet=PROJET_DEPOT)
    assert (exc.value.code, exc.value.message) == ("aucun_modele", "Aucun modèle disponible pour la classe "
                                                   "« implementation » : catalogue du poste inconnu (aucun relevé).")
    en_catalogue = noyau.routage.catalogue(conn)
    assert en_catalogue["etat"] == "inconnu" and en_catalogue["message"] == (
        "Catalogue du poste inconnu : aucun relevé (le poste publie son inventaire à l'étape P5).")
    assert noyau.routage.depots_autorises(conn) is None


def test_releve_perime_signale(noyau, conn):
    ancien = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)
    noyau.routage.enregistrer_releve(conn, releve_factice("poste-codex", releve_le=ancien))
    voie = noyau.routage.catalogue(conn)["voies"]["poste-codex"]
    assert voie["etat"] == "perime" and voie["perime"] is True and voie["age_s"] >= 3 * 3600
    res = noyau.routage.resoudre(conn, classe="implementation", projet=PROJET_DEPOT, voie="poste-codex")
    assert res.mention == "quota inconnu, relevé périmé"


def test_quota_connu_au_dela_du_seuil_refuse(noyau, conn):
    noyau.routage.enregistrer_releve(conn, releve_factice("poste-codex", quota=95))
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.resoudre(conn, classe="implementation", projet=PROJET_DEPOT, voie="poste-codex")
    assert exc.value.message == "Aucun modèle disponible pour la classe « implementation » : quota à 95 %."
    noyau.routage.enregistrer_releve(conn, releve_factice("poste-codex", quota=40))
    res = noyau.routage.resoudre(conn, classe="implementation", projet=PROJET_DEPOT, voie="poste-codex")
    assert res.mention is None  # quota connu et sous le seuil


def test_quota_inconnu_admis_et_mentionne(noyau, conn):
    noyau.routage.enregistrer_releve(conn, releve_factice("poste-codex"))
    res = noyau.routage.resoudre(conn, classe="implementation", projet=PROJET_DEPOT, voie="poste-codex")
    assert res.mention == "quota inconnu" and res.releve_id is not None


def test_relecture_modele_par_defaut_du_releve(noyau, conn):
    noyau.routage.enregistrer_releve(conn, releve_factice("poste-claude"))
    res = noyau.routage.resoudre_relecture(conn, projet=PROJET_DEPOT, voie_relue="poste-codex", ref="e1")
    assert (res.voie, res.modele, res.effort) == ("poste-claude", "factice-claude-1", "medium")
    res = noyau.routage.resoudre_relecture(conn, projet=PROJET_DEPOT, voie_relue="poste-codex", ref="e1",
                                           modele="factice-claude-2")
    assert (res.modele, res.source_routage) == ("factice-claude-2", "choix_explicite")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.resoudre_relecture(conn, projet=PROJET_DEPOT, voie_relue="poste-claude", ref="e1")
    assert exc.value.code == "relecture_impossible"


def test_releve_factice_etiquete(noyau, conn):
    identifiant = noyau.routage.enregistrer_releve(conn, releve_factice("poste-claude", depots=("jetable", "b")))
    assert identifiant > 0
    catalogue = noyau.routage.catalogue(conn)
    assert catalogue["etat"] == "connu" and catalogue["releve_factice"] is True
    assert catalogue["voies"]["poste-claude"]["source"] == "releve_factice"
    assert [m["id"] for m in catalogue["voies"]["poste-claude"]["modeles"]] == ["factice-claude-1", "factice-claude-2"]
    assert catalogue["politique"]["efforts_interdits"] == ["max", "ultra", "ultracode"]
    assert catalogue["politique"]["voies_par_classe"]["integration"] == []
    assert noyau.routage.depots_autorises(conn) == ["b", "jetable"]
    with pytest.raises(ValueError, match="Relevé refusé"):
        noyau.routage.enregistrer_releve(conn, dict(releve_factice(), voie="poste-windows"))


def test_surcharge_depuis_la_discussion(noyau, conn, monkeypatch):
    en_discussion(monkeypatch)
    projet = lancer_sur_depot(noyau, conn)
    base = {"portee": "projet", "cible": projet["id"], "classe": "implementation", "voie": "poste-codex",
            "motif": "Codex connaît mieux ce dépôt."}
    reponse = outil(noyau, "routage_surcharger", dict(base, modele="factice-codex-2", effort="low"), "s-9")
    assert reponse["ok"] and reponse["resolution"]["source_routage"] == "surcharge_projet"
    ligne = conn.execute("SELECT * FROM surcharges").fetchone()
    assert (ligne["auteur"], ligne["cible"], ligne["modele"]) == ("discussion:s-9", projet["id"], "factice-codex-2")
    # Une surcharge ne lève jamais un interdit, et la portée globale revient au propriétaire (P5).
    assert outil(noyau, "routage_surcharger", dict(base, effort="max"))["code"] == "effort_interdit"
    assert outil(noyau, "routage_surcharger", dict(base, portee="globale"))["message"] == (
        "Refusé par ACP : une surcharge globale se fait depuis la page Routage (étape P5).")
    # Portée « carte » : refusée en P4, même sur une carte inconnue (test suivant pour une carte existante).
    assert outil(noyau, "routage_surcharger", dict(base, portee="carte", cible="t_inconnue"))["code"] == (
        "surcharge_carte")
    sans_depot = lancer_sans_depot(noyau, conn, "Sans dépôt")
    assert outil(noyau, "routage_surcharger", dict(base, cible=sans_depot["id"]))["code"] == "sans_depot"


def test_surcharge_d_une_carte_refusee_tant_qu_elle_ne_s_applique_pas(noyau, conn, monkeypatch):
    """Relecture de P4 : routage_surcharger(portée « carte ») répondait « ok » et une résolution, alors qu'aucune
    carte ne relit cette surcharge (ni la carte visée, ni sa correction). Refus explicite, rien d'écrit."""
    projet = lancer_sur_depot(noyau, conn)
    reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    terminer(noyau, projet["tableau"], projet["cartes"]["exploration"], "Carte du dépôt.")
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(noyau, "projet_planifier", {"resume": "r", "etapes": [
        {"ref": "e1", "titre": "t", "classe": "implementation", "consigne": "c", "voie": "poste-codex"}]})
    impl = next(c["carte"] for c in tour["cartes"] if c["role"] == "implementation")
    en_discussion(monkeypatch)
    reponse = outil(noyau, "routage_surcharger", {
        "portee": "carte", "cible": impl, "classe": "implementation", "voie": "poste-claude",
        "modele": "factice-claude-1", "effort": "low", "motif": "Le propriétaire veut Claude pour cette carte."})
    assert reponse == {"ok": False, "code": "surcharge_carte", "message": (
        "Refusé par ACP : une carte existante garde son exécutant et son modèle : la surcharge d'une carte est "
        "prévue à l'étape P6 ; surchargez le projet (portée « projet »), ce qui vaut pour ses prochaines cartes.")}
    assert conn.execute("SELECT COUNT(*) FROM surcharges").fetchone()[0] == 0
    assert carte(noyau, projet["tableau"], impl).assignee == "poste-codex"
    assert noyau.outils.SCHEMAS["routage_surcharger"]["parameters"]["properties"]["portee"]["enum"] == ["projet"]
