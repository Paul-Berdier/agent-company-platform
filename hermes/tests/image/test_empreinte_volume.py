"""Empreinte de volume (étape P9, cahier P9 § 3.2) : l'outil des tests de restauration attrape ce qu'il doit attraper.

Dans l'image de test, en root (propriétaires numériques changés pour de vrai) ; tout se passe dans tmp_path :
- manifeste stable d'un relevé à l'autre ; il détecte et NOMME un mode, un propriétaire, un octet (taille égale), une
  cible de lien changés, une entrée absente ou en trop ; une prise Unix est relevée à part et exclue de l'égalité ;
- empreinte logique SQLite : même empreinte d'une base WAL avant et après ``wal_checkpoint`` (octets différents) ;
  une ligne changée est nommée par sa table ; une base tronquée est signalée (``integrity_check`` en échec) ;
- la commande ne modifie jamais la racine qu'elle lit (fichiers, -wal et -shm à l'octet près) ;
- version du schéma du greffon lue dans ``meta_schema`` (pas dans ``user_version``).
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/opt/acp-tests/outils")

import empreinte_volume as ev  # noqa: E402

OUTIL = "/opt/acp-tests/outils/empreinte_volume.py"


def _arbre(racine: Path) -> Path:
    (racine / "acp" / "secrets").mkdir(parents=True)
    (racine / "acp" / "secrets" / "jeton").write_bytes(b"jeton-factice-0123456789")
    os.chmod(racine / "acp" / "secrets", 0o700)
    os.chmod(racine / "acp" / "secrets" / "jeton", 0o600)
    (racine / "notes.txt").write_text("contenu\n", encoding="utf-8")
    os.chown(racine / "notes.txt", 10000, 10000)
    os.symlink("notes.txt", racine / "lien")
    return racine


def _commande(*arguments: str) -> dict:
    sortie = subprocess.run([sys.executable, OUTIL, *arguments], capture_output=True, text=True, check=True)
    return json.loads(sortie.stdout)


def _empreintes_octets(racine: Path) -> dict:
    return {str(p.relative_to(racine)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(racine.rglob("*")) if p.is_file() and not p.is_symlink()}


def test_manifeste_stable_et_complet(tmp_path):
    racine = _arbre(tmp_path / "v")
    premier, second = _commande("manifeste", str(racine)), _commande("manifeste", str(racine))
    assert ev.comparer_manifestes(premier, second) == []
    entrees = premier["entrees"]
    assert set(entrees) == {".", "acp", "acp/secrets", "acp/secrets/jeton", "notes.txt", "lien"}
    assert entrees["acp/secrets/jeton"]["mode"] == "0600" and entrees["acp/secrets"]["mode"] == "0700"
    assert (entrees["notes.txt"]["uid"], entrees["notes.txt"]["gid"]) == (10000, 10000)
    assert entrees["notes.txt"]["sha256"] == hashlib.sha256(b"contenu\n").hexdigest()
    assert entrees["lien"] == {"type": "l", "mode": entrees["lien"]["mode"], "uid": 0, "gid": 0, "cible": "notes.txt"}
    assert premier["decompte"] == {"d": 3, "f": 2, "l": 1} and premier["prises"] == []


@pytest.mark.parametrize("mutation, attendu", [
    (lambda r: os.chmod(r / "notes.txt", 0o600), "notes.txt : mode '0644' → '0600'"),
    (lambda r: os.chown(r / "acp/secrets/jeton", 10001, 0), "acp/secrets/jeton : uid 0 → 10001"),
    (lambda r: os.chown(r / "notes.txt", 10000, 10002), "notes.txt : gid 10000 → 10002"),
    (lambda r: (r / "notes.txt").write_text("contenX\n", encoding="utf-8"), "notes.txt : sha256 "),
    (lambda r: (os.remove(r / "lien"), os.symlink("acp", r / "lien")), "lien : cible 'notes.txt' → 'acp'"),
    (lambda r: os.remove(r / "acp/secrets/jeton"), "absent : acp/secrets/jeton"),
    (lambda r: (r / "acp/en-trop").write_bytes(b""), "en trop : acp/en-trop"),
    (lambda r: os.chmod(r, 0o700), ". : mode '0755' → '0700'"),
], ids=["mode", "proprietaire", "groupe", "octet", "cible", "absent", "en_trop", "racine"])
def test_manifeste_detecte_et_nomme_chaque_ecart(tmp_path, mutation, attendu):
    racine = _arbre(tmp_path / "v")
    os.chmod(racine, 0o755)
    os.chmod(racine / "notes.txt", 0o644)
    avant = ev.manifeste(str(racine))
    mutation(racine)
    ecarts = ev.comparer_manifestes(avant, ev.manifeste(str(racine)))
    assert ecarts and any(e.startswith(attendu) for e in ecarts), ecarts


def test_prise_unix_relevee_a_part_et_exclue_de_l_egalite(tmp_path):
    racine = _arbre(tmp_path / "v")
    sans = ev.manifeste(str(racine))
    prise = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        prise.bind(str(racine / "gateway.sock"))
        avec = ev.manifeste(str(racine))
    finally:
        prise.close()
    assert avec["prises"] == ["gateway.sock"] and avec["entrees"]["gateway.sock"]["type"] == "s"
    assert ev.comparer_manifestes(avec, sans) == [] and ev.comparer_manifestes(sans, avec) == []


def _base_wal(chemin: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(chemin, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE cartes (id TEXT PRIMARY KEY, statut TEXT, n INTEGER, poids REAL, b BLOB, libre)")
    conn.execute("CREATE TABLE sans_rowid (cle TEXT PRIMARY KEY, valeur TEXT) WITHOUT ROWID")
    conn.execute("CREATE TABLE meta_schema (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL)")
    conn.execute("INSERT INTO meta_schema VALUES ('version', '4')")
    conn.execute("PRAGMA user_version = 7")
    conn.executemany("INSERT INTO cartes VALUES (?, ?, ?, ?, ?, ?)",
                     [(f"t_{i}", "done", i, i / 3, bytes([i]), i) for i in range(50)])
    conn.executemany("INSERT INTO sans_rowid VALUES (?, ?)", [("b", "2"), ("a", "1")])
    return conn


def test_empreinte_logique_identique_avant_et_apres_checkpoint(tmp_path):
    racine = tmp_path / "v"
    racine.mkdir()
    conn = _base_wal(racine / "data.db")
    try:
        octets_avant = _empreintes_octets(racine)
        assert (racine / "data.db-wal").stat().st_size > 0, "le journal WAL doit porter les écritures"
        avant = _commande("sqlite", str(racine))
        assert _empreintes_octets(racine) == octets_avant, "la commande a modifié la racine lue"
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        assert _empreintes_octets(racine) != octets_avant
        apres = _commande("sqlite", str(racine))
    finally:
        conn.close()
    [base] = avant["bases"]
    assert base == "data.db" and avant["bases"][base]["integrite"] == "ok"
    assert avant["bases"][base]["annexes"]["-wal"] > 0
    assert ev.comparer_bases(avant, apres) == []
    tables = avant["bases"][base]["tables"]
    assert tables["cartes"]["lignes"] == 50 and tables["sans_rowid"]["lignes"] == 2
    assert avant["bases"][base]["user_version"] == 7 and avant["bases"][base]["meta_schema"] == "4"


def test_une_ligne_changee_est_nommee_par_sa_table(tmp_path):
    racine = tmp_path / "v"
    racine.mkdir()
    conn = _base_wal(racine / "data.db")
    try:
        avant = ev.bases(str(racine))
        conn.execute("UPDATE cartes SET statut = 'blocked' WHERE id = 't_3'")
        apres = ev.bases(str(racine))
        conn.execute("UPDATE cartes SET statut = 'done' WHERE id = 't_3'")
        retour = ev.bases(str(racine))
        # Même valeur, autre type (colonne sans affinité : le texte « 3 » n'y redevient pas l'entier 3).
        conn.execute("UPDATE cartes SET libre = '3' WHERE id = 't_3'")
        type_change = ev.bases(str(racine))
    finally:
        conn.close()
    ecarts = ev.comparer_bases(avant, apres)
    assert len(ecarts) == 1 and ecarts[0].startswith("data.db : table cartes "), ecarts
    assert ev.comparer_bases(avant, retour) == []
    assert any(e.startswith("data.db : table cartes ") for e in ev.comparer_bases(avant, type_change))


def test_base_tronquee_signalee(tmp_path):
    racine = tmp_path / "v"
    racine.mkdir()
    conn = sqlite3.connect(racine / "data.db", isolation_level=None)
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.executemany("INSERT INTO t VALUES (?)", [("x" * 500,) for _ in range(400)])
    conn.close()
    taille = (racine / "data.db").stat().st_size
    with open(racine / "data.db", "r+b") as flux:
        flux.truncate(taille // 2)
    releve = _commande("sqlite", str(racine))
    integrite = releve["bases"]["data.db"]["integrite"]
    assert integrite != "ok" and isinstance(integrite, list) and integrite, integrite


def test_integrite_en_echec_signalee_meme_quand_les_tables_se_lisent(tmp_path):
    """Une base lisible mais incohérente (contrainte CHECK violée en écrivant avec ignore_check_constraints) :
    ``integrity_check`` la signale et l'outil le rapporte tel quel, sans s'arrêter aux lectures qui réussissent."""
    racine = tmp_path / "v"
    racine.mkdir()
    conn = sqlite3.connect(racine / "data.db", isolation_level=None)
    conn.execute("CREATE TABLE t (x INTEGER NOT NULL CHECK (x > 0))")
    conn.execute("PRAGMA ignore_check_constraints = 1")
    conn.execute("INSERT INTO t VALUES (-1)")
    conn.close()
    base = ev.bases(str(racine))["bases"]["data.db"]
    assert base["integrite"] == ["CHECK constraint failed in t"], base["integrite"]
    assert base["tables"]["t"]["lignes"] == 1


def test_fichier_non_sqlite_ignore_et_racine_absente_refusee(tmp_path):
    racine = _arbre(tmp_path / "v")
    assert ev.bases(str(racine))["bases"] == {}
    refus = subprocess.run([sys.executable, OUTIL, "manifeste", str(tmp_path / "absente")], capture_output=True,
                           text=True)
    assert refus.returncode == 2 and "Racine illisible" in refus.stderr
