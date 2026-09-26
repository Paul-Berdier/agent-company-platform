"""Base propre du greffon acp-poste (étape P4) : schéma, migrations, WAL, transactions, deux copies du noyau."""

from __future__ import annotations

import sqlite3

import pytest

import meta
from conftest import lancer_sans_depot


def test_schema_cree_et_version(noyau, conn):
    tables = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(noyau.base.TABLES) <= tables
    assert noyau.base.version_schema(conn) == "1"
    colonnes = {l[1] for l in conn.execute("PRAGMA table_info(demandes)")}
    # Les cinq tables du plan, et ce qu'il faut pour recréer une carte à l'identique.
    assert {"cle", "carte", "role", "voie", "modele", "effort", "effort_carte", "palier", "source_routage",
            "parents", "competences", "corps"} <= colonnes


def test_migration_idempotente(noyau, conn):
    noyau.base.migrer(conn)
    noyau.base.migrer(conn)
    assert conn.execute("SELECT COUNT(*) FROM meta_schema").fetchone()[0] == 1
    assert noyau.base.version_schema(conn) == "1"


def test_base_sous_hermes_home_en_wal(noyau, conn):
    chemin = noyau.base.chemin_base()
    assert chemin == noyau.home / "plugin-data" / "acp-poste" / "data.db"
    assert chemin.is_file()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_transaction_immediate_serialise(noyau, conn):
    autre = sqlite3.connect(noyau.base.chemin_base(), timeout=0.2, isolation_level=None)
    try:
        with noyau.base.transaction(conn):
            conn.execute("INSERT INTO reglages (cle, valeur, maj_le, auteur) VALUES ('plafond_tours', '5', 0, 't')")
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                autre.execute("BEGIN IMMEDIATE")
        # Témoin : la transaction validée libère l'écrivain.
        autre.execute("BEGIN IMMEDIATE")
        autre.execute("ROLLBACK")
    finally:
        autre.close()
    assert noyau.base.reglage(conn, "plafond_tours") == 5


def test_transaction_annulee_sur_exception(noyau, conn):
    with pytest.raises(RuntimeError):
        with noyau.base.transaction(conn):
            noyau.base.journaliser(conn, "test", "essai")
            raise RuntimeError("panne")
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE action = 'essai'").fetchone()[0] == 0


def test_reglages_par_defaut_et_pose(noyau, conn):
    assert noyau.base.reglage(conn, "plafond_cartes") == 30
    assert noyau.base.reglage(conn, "efforts_interdits") == ["max", "ultra", "ultracode"]
    assert noyau.base.reglage(conn, "paliers_admis") == ["default"]
    noyau.base.poser_reglage(conn, "seuil_hors_ligne_s", 10, "test")
    assert noyau.base.reglage(conn, "seuil_hors_ligne_s") == 10
    with pytest.raises(ValueError, match="réglage inconnu"):
        noyau.base.poser_reglage(conn, "inconnu", 1, "test")


def test_deux_copies_du_noyau_partagent_la_base(noyau, conn):
    """Le tableau de bord charge le noyau DEUX fois (paquet du greffon pour la discussion, chemin pour les
    routes) : aucun état en mémoire, tout passe par la base."""
    copie = meta.sous_module_noyau("projets")
    assert copie.__name__ == "acp_poste_noyau.projets" and copie is not noyau.projets
    base_copie = meta.sous_module_noyau("base")
    with base_copie.connexion() as autre:
        projet = copie.lancer(autre, titre="Deux copies", objectif="Même base.", origine="tableau_de_bord",
                              auteur="proprietaire:test")["projet"]
    assert noyau.projets.projet(conn, projet["id"])["titre"] == "Deux copies"
    lance = lancer_sans_depot(noyau, conn, "Depuis la première copie")
    with base_copie.connexion() as autre:
        assert copie.projet(autre, lance["tableau"])["id"] == lance["id"]
