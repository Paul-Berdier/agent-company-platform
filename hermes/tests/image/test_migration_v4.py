"""Schéma v4 de la base du greffon (étape P7, cahier P7 § 12.1, correction K21) : migration v3 → v4 idempotente, y
compris entre deux processus concurrents ; ``notifications`` reconstruite UNE fois (genre ``bilan``) sans perdre une
ligne ; colonnes de la relance ajoutées à ``demandes`` APRÈS la reconstruction v3 (une base v2 qui passe par v3 les
garde) ; base neuve et base migrée identiques, colonne pour colonne."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from conftest import PYTHON_HERMES, releve_factice

GREFFON = "/opt/hermes/plugins/acp-poste"
COLONNES_P7 = ("consigne_relance", "relancee_le", "consigne_initiale")


def _base_v3(noyau, chemin: Path) -> None:
    """Base v3 telle que P6 l'a laissée (mêmes étapes que la migration de P6, sans celles de P7), avec un projet, une
    demande de l'exécutant (issue, branche) et deux notifications (dont un genre de P6)."""
    b = noyau.base
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN")
        for script in (b.SCHEMA, b.SCHEMA_V3):
            for instruction in script.split(";"):
                if instruction.strip():
                    conn.execute(instruction)
        for table, colonne, genre in b.COLONNES_V2 + b.COLONNES_V3:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {genre}")
        for table, forme, _marqueur, index in b.RECONSTRUCTIONS_V3:
            b.reconstruire_dans(conn, table, forme, index)
        conn.execute("INSERT INTO meta_schema (cle, valeur) VALUES ('version', '3')")
        conn.execute("INSERT INTO projets (id, tableau, titre, objectif, profil, depot_alias, reponses, etat, tour, "
                     "plafond_tours, plafond_cartes, plafond_corrections, cartes_creees, origine, auteur, cree_le, "
                     "maj_le) VALUES ('p_000000000003', 'acp-v3-0003', 'V3', 'Objectif', 'base', 'jetable', "
                     "'hermes_d_abord', 'actif', 1, 3, 30, 2, 2, 'tableau_de_bord', 'test', 1, 1)")
        conn.execute("INSERT INTO releves (voie, source, version_cli, releve_le, recu_le, contenu) VALUES "
                     "('poste-codex', 'releve_factice', '0.0.0-factice', 1, 1, ?)",
                     (json.dumps(releve_factice("poste-codex")),))
        conn.execute("INSERT INTO demandes (cle, projet_id, tableau, carte, role, classe, voie, tour, source_routage, "
                     "releve_id, consigne, cree_le, machine_id, issue, branche) VALUES "
                     "('acp:p_000000000003:t1:a:implementation', 'p_000000000003', 'acp-v3-0003', 't_0000bbbb', "
                     "'implementation', 'implementation', 'poste-codex', 1, 'table', 1, 'Consigne v3', 1, "
                     "'m000000000001', 'question', 'hermes/t_0000bbbb')")
        conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES "
                     "('termine:p_000000000003', 'termine', 'Projet V3 terminé', 'envoyee', 1)")
        conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES "
                     "('isolement:abc', 'isolement', 'Isolement changé', 'en_attente', 2)")
        conn.execute("COMMIT")
    finally:
        conn.close()


def _colonnes(conn, table: str):
    return [l[1] for l in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _sql(conn, table: str) -> str:
    return conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()[0]


def test_v3_vers_v4_idempotente_sans_perte(noyau):
    chemin = noyau.base.chemin_base()
    _base_v3(noyau, chemin)
    noyau.base._initialisees.clear()
    with noyau.base.connexion() as conn:
        assert noyau.base.version_schema(conn) == "4"
        noyau.base.migrer(conn)
        noyau.base.migrer(conn)
        assert conn.execute("SELECT COUNT(*) FROM meta_schema").fetchone()[0] == 1
        ligne = conn.execute("SELECT carte, consigne, issue, branche, consigne_relance, relancee_le, consigne_initiale "
                             "FROM demandes").fetchone()
        assert tuple(ligne) == ("t_0000bbbb", "Consigne v3", "question", "hermes/t_0000bbbb", None, None, None)
        assert [tuple(l) for l in conn.execute("SELECT cle, genre, etat FROM notifications ORDER BY id")] == [
            ("termine:p_000000000003", "termine", "envoyee"), ("isolement:abc", "isolement", "en_attente")]
        assert "'bilan'" in _sql(conn, "notifications") and "'isolement'" in _sql(conn, "notifications")
        assert not [l for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE "
                                            "'%\\_v3' ESCAPE '\\'")]
        index = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert {"demandes_par_projet", "notifications_par_etat", "envois_par_date"} <= index
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        # Le genre « bilan » est admis ; les anciennes contraintes restent.
        with noyau.base.transaction(conn):
            conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES ('bilan:2026-10-02', "
                         "'bilan', 'Bilan du 02/10', 'en_attente', 3)")
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            with noyau.base.transaction(conn):
                conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES ('z', 'inconnu', "
                             "'x', 'en_attente', 1)")
        # La clé UNIQUE survit : deux bilans le même jour n'en font qu'un.
        assert noyau.notifications.enfiler(conn, cle="bilan:2026-10-02", genre="bilan", texte_notif="x") is False


def test_v3_vers_v4_garde_le_compteur_autoincrement_de_notifications(noyau, tmp_path):
    """Étape P9 (montée de données, run 37782764948 : compteur de ``notifications`` ramené de 7 à 5 par la
    reconstruction v4) : un numéro déjà consommé ne resert jamais après la migration. Ici consommé par une ligne
    insérée puis retirée (et par un ``INSERT OR IGNORE`` ignoré, qui en consomme un dans SQLite)."""
    chemin = tmp_path / "compteur-v4.db"
    _base_v3(noyau, chemin)
    conn = sqlite3.connect(chemin, isolation_level=None)
    try:
        conn.execute("INSERT OR IGNORE INTO notifications (cle, genre, texte, etat, cree_le) VALUES "
                     "('termine:p_000000000003', 'termine', 'Rejoué', 'envoyee', 3)")
        conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES "
                     "('isolement:retire', 'isolement', 'Retiré', 'envoyee', 4)")
        conn.execute("DELETE FROM notifications WHERE cle = 'isolement:retire'")
        compteur = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'notifications'").fetchone()[0]
        plus_grand = conn.execute("SELECT MAX(id) FROM notifications").fetchone()[0]
        assert compteur > plus_grand == 2, (compteur, plus_grand)
        noyau.base.migrer(conn)
        assert "'bilan'" in _sql(conn, "notifications")
        assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'notifications'").fetchone()[0] == compteur
        conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES "
                     "('bilan:2026-10-08', 'bilan', 'Bilan', 'en_attente', 5)")
        assert conn.execute("SELECT id FROM notifications WHERE cle = 'bilan:2026-10-08'").fetchone()[0] == compteur + 1
        assert [tuple(l) for l in conn.execute("SELECT id, cle FROM notifications WHERE id <= 2 ORDER BY id")] == [
            (1, "termine:p_000000000003"), (2, "isolement:abc")]
        # Seconde migration : rien n'est reconstruit, le compteur suit les insertions.
        noyau.base.migrer(conn)
        seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'notifications'").fetchone()[0]
        assert seq == compteur + 1, (seq, compteur)
    finally:
        conn.close()


def test_base_neuve_et_bases_migrees_v4_ont_le_meme_schema(noyau, tmp_path):
    """K21 : une base v2 (reconstruction v3 de ``demandes`` à sa forme explicite) et une base v3 finissent avec les
    MÊMES colonnes et contraintes qu'une base neuve — colonnes de la relance comprises."""
    from test_migration_v3 import _base_v2

    with noyau.base.connexion() as conn:
        neuve = {t: _colonnes(conn, t) for t in noyau.base.TABLES}
        contraintes = {t: _sql(conn, t) for t in ("demandes", "notifications")}
    assert set(COLONNES_P7) <= set(neuve["demandes"])
    for nom, fabrique in (("v2.db", _base_v2), ("v3.db", _base_v3)):
        ancienne = tmp_path / nom
        fabrique(noyau, ancienne)
        conn = sqlite3.connect(ancienne, isolation_level=None)
        try:
            noyau.base.migrer(conn)
            assert {t: _colonnes(conn, t) for t in noyau.base.TABLES} == neuve, nom
            assert {t: _sql(conn, t) for t in ("demandes", "notifications")} == contraintes, nom
            assert conn.execute("SELECT valeur FROM meta_schema WHERE cle = 'version'").fetchone()[0] == "4"
        finally:
            conn.close()


def test_migration_v4_par_deux_processus_concurrents(noyau, tmp_path):
    """Deux processus migrent une base v3 en même temps : l'un attend l'autre (BEGIN IMMEDIATE) ; une seule
    reconstruction, aucune colonne en double, aucune ligne perdue."""
    chemin = tmp_path / "concurrente-v4.db"
    _base_v3(noyau, chemin)
    code = ("import sqlite3, sys, time\n"
            f"sys.path.insert(0, {GREFFON!r})\n"
            "from noyau import base\n"
            f"conn = sqlite3.connect({str(chemin)!r}, isolation_level=None, timeout=10)\n"
            "conn.execute('PRAGMA busy_timeout=10000')\n"
            "conn.execute('PRAGMA foreign_keys=ON')\n"
            "time.sleep(max(0.0, float(sys.argv[1]) - time.time()))\n"
            "base.migrer(conn)\n"
            "print(conn.execute(\"SELECT valeur FROM meta_schema WHERE cle = 'version'\").fetchone()[0])\n")
    depart = str(time.time() + 1.5)
    env = {"HERMES_HOME": str(tmp_path / "home-concurrent-v4"), "PATH": "/usr/bin:/bin"}
    processus = [subprocess.Popen([PYTHON_HERMES, "-c", code, depart], env=env, cwd="/opt/hermes",
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    sorties = [p.communicate(timeout=120) for p in processus]
    assert [p.returncode for p in processus] == [0, 0], [s[1][-2000:] for s in sorties]
    assert [s[0].strip().splitlines()[-1] for s in sorties] == ["4", "4"]
    conn = sqlite3.connect(chemin)
    try:
        colonnes = _colonnes(conn, "demandes")
        assert all(colonnes.count(c) == 1 for c in COLONNES_P7) and len(colonnes) == len(set(colonnes))
        assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 2
    finally:
        conn.close()
