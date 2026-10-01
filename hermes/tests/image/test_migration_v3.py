"""Schéma v3 de la base du greffon (étape P6, cahier P6 § 9.1) : migration v2 → v3 idempotente, y compris entre deux
processus concurrents ; ``demandes`` et ``notifications`` reconstruites UNE fois (contrainte élargie) sans perdre une
ligne ni une clé étrangère ; base neuve et base migrée identiques ; tables ``envois`` et ``attentes``."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from conftest import PYTHON_HERMES, releve_factice

GREFFON = "/opt/hermes/plugins/acp-poste"


def _schema_v2(noyau) -> str:
    """Le schéma v2 de P5 : ``SCHEMA`` (inchangé depuis P5) ; v3 n'y touche pas, il s'ajoute après."""
    return noyau.base.SCHEMA


def _base_v2(noyau, chemin: Path) -> None:
    """Base v2 telle que P5 l'a laissée, avec un projet, un relevé cité par une demande et une notification."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN")
        for instruction in _schema_v2(noyau).split(";"):
            if instruction.strip():
                conn.execute(instruction)
        for table, colonne, genre in noyau.base.COLONNES_V2:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {genre}")
        conn.execute("INSERT INTO meta_schema (cle, valeur) VALUES ('version', '2')")
        conn.execute("INSERT INTO projets (id, tableau, titre, objectif, profil, depot_alias, reponses, etat, tour, "
                     "plafond_tours, plafond_cartes, plafond_corrections, cartes_creees, origine, auteur, cree_le, "
                     "maj_le) VALUES ('p_000000000001', 'acp-v2-0001', 'V2', 'Objectif', 'base', 'jetable', "
                     "'proprietaire', 'actif', 1, 3, 30, 2, 2, 'tableau_de_bord', 'test', 1, 1)")
        conn.execute("INSERT INTO releves (voie, source, version_cli, releve_le, recu_le, contenu) VALUES "
                     "('poste-codex', 'releve_factice', '0.0.0-factice', 1, 1, ?)",
                     (json.dumps(releve_factice("poste-codex")),))
        conn.execute("INSERT INTO demandes (cle, projet_id, tableau, carte, role, classe, voie, tour, source_routage, "
                     "releve_id, consigne, cree_le) VALUES ('acp:p_000000000001:t1:a:implementation', "
                     "'p_000000000001', 'acp-v2-0001', 't_0000aaaa', 'implementation', 'implementation', "
                     "'poste-codex', 1, 'table', 1, 'Consigne v2', 1)")
        conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES "
                     "('termine:p_000000000001', 'termine', 'Projet V2 terminé', 'envoyee', 1)")
        conn.execute("COMMIT")
    finally:
        conn.close()


def _colonnes(conn, table: str):
    return [l[1] for l in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _sql(conn, table: str) -> str:
    return conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()[0]


def test_v2_vers_v3_idempotente_sans_perte(noyau):
    chemin = noyau.base.chemin_base()
    _base_v2(noyau, chemin)
    noyau.base._initialisees.clear()
    with noyau.base.connexion() as conn:
        assert noyau.base.version_schema(conn) == "3"
        noyau.base.migrer(conn)
        noyau.base.migrer(conn)
        assert conn.execute("SELECT COUNT(*) FROM meta_schema").fetchone()[0] == 1
        ligne = conn.execute("SELECT carte, consigne, releve_id, machine_id, issue FROM demandes").fetchone()
        assert tuple(ligne) == ("t_0000aaaa", "Consigne v2", 1, None, None)
        assert tuple(conn.execute("SELECT genre, etat FROM notifications").fetchone()) == ("termine", "envoyee")
        assert "'integration'" in _sql(conn, "demandes") and "'poste-integration'" in _sql(conn, "demandes")
        assert "'isolement'" in _sql(conn, "notifications")
        assert not {"demandes_v3", "notifications_v3"} & {
            l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        index = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert {"demandes_par_projet", "notifications_par_etat", "envois_par_date"} <= index
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        # La clé étrangère demandes.releve_id survit à la reconstruction.
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            with noyau.base.transaction(conn):
                conn.execute("DELETE FROM releves WHERE id = 1")
        # Les valeurs nouvelles sont admises, les anciennes contraintes restent.
        with noyau.base.transaction(conn):
            conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES ('r', 'revue', 'x', "
                         "'en_attente', 1)")
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            with noyau.base.transaction(conn):
                conn.execute("INSERT INTO notifications (cle, genre, texte, etat, cree_le) VALUES ('z', 'inconnu', "
                             "'x', 'en_attente', 1)")


def test_base_neuve_et_base_migree_v3_ont_le_meme_schema(noyau, tmp_path):
    with noyau.base.connexion() as conn:
        neuve = {t: _colonnes(conn, t) for t in noyau.base.TABLES}
        contraintes = {t: _sql(conn, t) for t in ("demandes", "notifications")}
    ancienne = tmp_path / "v2.db"
    _base_v2(noyau, ancienne)
    conn = sqlite3.connect(ancienne, isolation_level=None)
    try:
        noyau.base.migrer(conn)
        assert {t: _colonnes(conn, t) for t in noyau.base.TABLES} == neuve
        assert {t: _sql(conn, t) for t in ("demandes", "notifications")} == contraintes
    finally:
        conn.close()


def test_migration_v3_par_deux_processus_concurrents(noyau, tmp_path):
    """Deux processus migrent une base v2 en même temps : l'un attend l'autre (BEGIN IMMEDIATE) ; une seule
    reconstruction, aucune table « _v3 » laissée, aucune colonne en double."""
    chemin = tmp_path / "concurrente-v3.db"
    _base_v2(noyau, chemin)
    code = ("import sqlite3, sys, time\n"
            f"sys.path.insert(0, {GREFFON!r})\n"
            "from noyau import base\n"
            f"conn = sqlite3.connect({str(chemin)!r}, isolation_level=None, timeout=10)\n"
            "conn.execute('PRAGMA busy_timeout=10000')\n"
            "conn.execute('PRAGMA foreign_keys=ON')\n"
            "time.sleep(max(0.0, float(sys.argv[1]) - time.time()))\n"
            "base.migrer(conn)\n"
            "print(conn.execute(\"SELECT valeur FROM meta_schema WHERE cle = 'version'\").fetchone()[0])\n")
    import time

    depart = str(time.time() + 1.5)
    env = {"HERMES_HOME": str(tmp_path / "home-concurrent-v3"), "PATH": "/usr/bin:/bin"}
    processus = [subprocess.Popen([PYTHON_HERMES, "-c", code, depart], env=env, cwd="/opt/hermes",
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    sorties = [p.communicate(timeout=120) for p in processus]
    assert [p.returncode for p in processus] == [0, 0], [s[1][-2000:] for s in sorties]
    assert [s[0].strip().splitlines()[-1] for s in sorties] == ["3", "3"]
    conn = sqlite3.connect(chemin)
    try:
        colonnes = _colonnes(conn, "demandes")
        assert colonnes.count("machine_id") == 1 and len(colonnes) == len(set(colonnes))
        assert conn.execute("SELECT COUNT(*) FROM demandes").fetchone()[0] == 1
        assert not [l for l in conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%_v3'")]
    finally:
        conn.close()


def test_reglages_p6_par_defaut(noyau, conn):
    assert [noyau.base.reglage(conn, c) for c in ("reclamation_ttl_s", "envois_conservation_s",
                                                   "grace_arret_propre_s", "voie_fermee_delai_s",
                                                   "relecture_repli_meme_voie")] == [2700, 604800, 600, 1800, True]


def test_envois_et_attentes_bornes(noyau, conn):
    with noyau.base.transaction(conn):
        conn.execute("INSERT INTO envois (id_envoi, machine_id, route, tableau, carte, run_id, empreinte, statut, "
                     "reponse, recu_le) VALUES (?, 'm000000000001', 'terminer', 'acp-x', 't_0001', 1, ?, 200, '{}', 1)",
                     ("3f2a8c1e-5b6d-4e7f-8a9b-0c1d2e3f4a5b", "0" * 64))
        conn.execute("INSERT INTO attentes (tableau, carte, motif, reprise_le, cree_le) VALUES ('acp-x', 't_0001', "
                     "'quota', 2, 1)")
    for sql in ("INSERT INTO envois (id_envoi, machine_id, route, tableau, carte, run_id, empreinte, statut, reponse, "
                "recu_le) VALUES ('court', 'm', 'terminer', 't', 'c', 1, '" + "0" * 64 + "', 200, '{}', 1)",
                "INSERT INTO envois (id_envoi, machine_id, route, tableau, carte, run_id, empreinte, statut, reponse, "
                "recu_le) VALUES ('3f2a8c1e-5b6d-4e7f-8a9b-0c1d2e3f4a5c', 'm', 'inventaire', 't', 'c', 1, '"
                + "0" * 64 + "', 200, '{}', 1)",
                "INSERT INTO attentes (tableau, carte, motif, reprise_le, cree_le) VALUES ('t', 'c', 'autre', 1, 1)"):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            with noyau.base.transaction(conn):
                conn.execute(sql)
