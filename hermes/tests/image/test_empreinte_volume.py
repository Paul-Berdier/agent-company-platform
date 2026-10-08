"""Empreinte de volume (étape P9, cahier P9 § 3.2) : l'outil des tests de restauration attrape ce qu'il doit attraper.

Dans l'image de test, en root (propriétaires numériques changés pour de vrai) ; tout se passe dans tmp_path :
- manifeste stable d'un relevé à l'autre ; il détecte et NOMME un mode, un propriétaire, un octet (taille égale), une
  cible de lien changés, une entrée absente ou en trop ; une prise Unix est relevée à part et exclue de l'égalité ;
- empreinte logique SQLite : même empreinte d'une base WAL avant et après ``wal_checkpoint`` (octets différents) ;
  une ligne changée est nommée par sa table ; une base tronquée est signalée (``integrity_check`` en échec) ;
- la commande ne modifie jamais la racine qu'elle lit (fichiers, -wal et -shm à l'octet près) ;
- version du schéma du greffon lue dans ``meta_schema`` (pas dans ``user_version``) ;
- montée de données (cahier P9 § 5.6, relevé ``lignes``) : une migration qui élargit une table, en reconstruit une et
  en ajoute une, sans rien perdre, n'a aucun défaut ; chaque défaut est NOMMÉ (ligne d'avant perdue ou modifiée, table
  ou colonne disparue, compteur AUTOINCREMENT revenu en arrière, base disparue) ; une ligne ajoutée n'en est pas un ;
  une table qu'un simple redémarrage change aussi (contrôle) n'en est pas un ; projection lue sur l'entrée standard.
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


# =========================================================================== montée de données (cahier P9 § 5.6)


def _base_avant(chemin: Path) -> sqlite3.Connection:
    """Base « avant » d'une montée : une table que la migration élargit (cartes), une table AUTOINCREMENT qu'elle
    reconstruit (journal, dont la dernière ligne a été supprimée : compteur 5, plus grand identifiant 4), une table
    sans rowid, la version du greffon dans meta_schema."""
    conn = sqlite3.connect(chemin, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE meta_schema (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL)")
    conn.execute("INSERT INTO meta_schema VALUES ('version', '3')")
    conn.execute("CREATE TABLE cartes (id TEXT PRIMARY KEY, statut TEXT, n INTEGER)")
    conn.executemany("INSERT INTO cartes VALUES (?, ?, ?)", [(f"t_{i}", "done", i) for i in range(6)])
    conn.execute("CREATE TABLE journal (id INTEGER PRIMARY KEY AUTOINCREMENT, quoi TEXT NOT NULL "
                 "CHECK (quoi IN ('a', 'b')))")
    conn.executemany("INSERT INTO journal (quoi) VALUES (?)", [("a",), ("b",), ("a",), ("b",), ("a",)])
    conn.execute("DELETE FROM journal WHERE id = 5")
    conn.execute("CREATE TABLE sans_rowid (cle TEXT PRIMARY KEY, valeur TEXT) WITHOUT ROWID")
    conn.executemany("INSERT INTO sans_rowid VALUES (?, ?)", [("a", "1"), ("b", "2")])
    return conn


def _migrer(conn: sqlite3.Connection, *, garder_compteur: bool = True) -> None:
    """Migration du même genre que le schéma 4 du greffon : colonne ajoutée, table reconstruite (contrainte CHECK
    élargie, lignes recopiées colonne par colonne, DROP puis RENAME), table nouvelle, version posée. Sans
    ``garder_compteur``, la reconstruction perd le compteur AUTOINCREMENT au-delà du plus grand identifiant recopié."""
    compteur = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'journal'").fetchone()[0]
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("ALTER TABLE cartes ADD COLUMN neuve TEXT")
    conn.execute("CREATE TABLE journal_v4 (id INTEGER PRIMARY KEY AUTOINCREMENT, quoi TEXT NOT NULL "
                 "CHECK (quoi IN ('a', 'b', 'c')))")
    conn.execute("INSERT INTO journal_v4 (id, quoi) SELECT id, quoi FROM journal")
    conn.execute("DROP TABLE journal")
    conn.execute("ALTER TABLE journal_v4 RENAME TO journal")
    if garder_compteur:
        conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'journal'", (compteur,))
    conn.execute("CREATE TABLE nouvelle (x TEXT)")
    conn.execute("INSERT INTO nouvelle VALUES ('x')")
    conn.execute("UPDATE meta_schema SET valeur = '4' WHERE cle = 'version'")
    conn.execute("COMMIT")


def _releves_de_montee(racine: Path, alterer=None, *, garder_compteur: bool = True):
    conn = _base_avant(racine / "data.db")
    try:
        avant = ev.lignes(str(racine))
        _migrer(conn, garder_compteur=garder_compteur)
        if alterer:
            alterer(conn)
        apres = ev.lignes(str(racine), ev.projection_de(avant))
    finally:
        conn.close()
    return avant, apres, ev.comparer_lignes(avant, apres)


def test_lignes_une_migration_qui_garde_les_donnees_n_a_aucun_defaut(tmp_path):
    racine = tmp_path / "v"
    racine.mkdir()
    avant, apres, montee = _releves_de_montee(racine)
    base_avant, base_apres = avant["bases"]["data.db"], apres["bases"]["data.db"]
    assert base_avant["integrite"] == "ok" and base_avant["meta_schema"] == "3" and base_apres["meta_schema"] == "4"
    assert base_avant["sequences"] == {"journal": 5} and base_apres["sequences"] == {"journal": 5}
    assert base_avant["tables"]["sans_rowid"]["cle"] == "ligne" and base_avant["tables"]["cartes"]["cle"] == "rowid"
    # Lignes élargies comparées sur les colonnes d'avant : identiques ; la colonne nouvelle est dite, vide.
    assert base_apres["tables"]["cartes"]["colonnes"] == ["id", "statut", "n"]
    assert base_apres["tables"]["cartes"]["nouvelles_colonnes"] == {"neuve": 0}
    tables = montee["data.db"]["tables"]
    assert "cartes" not in tables and "journal" not in tables and "sans_rowid" not in tables, tables
    assert tables["meta_schema"]["modifiees"] == 1 and tables["nouvelle"] == {"table": "nouvelle", "ajoutees": 1}
    schemas = ev.comparer_schemas(avant, apres)
    assert schemas["data.db"]["meta_schema"] == ["3", "4"]
    assert schemas["data.db"]["objets_ajoutes"] == ["table:nouvelle"]
    assert schemas["data.db"]["objets_modifies"] == ["table:cartes", "table:journal"]
    assert ev.defauts_de_montee(avant, apres, montee, {}) == []
    assert ev.changements_propres(schemas, {}) == schemas


@pytest.mark.parametrize("alterer, attendu", [
    (lambda c: c.execute("DELETE FROM cartes WHERE id = 't_2'"),
     "data.db : table cartes, 1 ligne(s) d'avant perdue(s) "),
    (lambda c: c.execute("UPDATE cartes SET statut = 'blocked' WHERE id = 't_3'"),
     "data.db : table cartes, 1 ligne(s) d'avant modifiée(s) ['4']"),
    (lambda c: c.execute("INSERT INTO meta_schema VALUES ('autre', 'x')"), None),
    (lambda c: c.execute("UPDATE sans_rowid SET valeur = '9' WHERE cle = 'a'"),
     "data.db : table sans_rowid, 1 ligne(s) d'avant perdue(s) "),
    (lambda c: c.execute("ALTER TABLE cartes DROP COLUMN n"), "data.db : table cartes, colonnes disparues ['n']"),
    (lambda c: c.execute("DROP TABLE sans_rowid"), "data.db : table sans_rowid disparue"),
], ids=["perdue", "modifiee", "ajout_tolere", "sans_rowid", "colonne", "table"])
def test_lignes_chaque_defaut_de_montee_est_nomme(tmp_path, alterer, attendu):
    racine = tmp_path / "v"
    racine.mkdir()
    avant, apres, montee = _releves_de_montee(racine, alterer)
    defauts = ev.defauts_de_montee(avant, apres, montee, {})
    if attendu is None:  # une ligne AJOUTÉE n'est pas un défaut : elle est dite par comparer_lignes
        assert defauts == [] and montee["data.db"]["tables"]["meta_schema"]["ajoutees"] == 1, (defauts, montee)
    else:
        assert any(d.startswith(attendu) for d in defauts), defauts


def test_lignes_compteur_autoincrement_revenu_en_arriere_et_base_disparue(tmp_path):
    racine = tmp_path / "v"
    racine.mkdir()
    avant, apres, montee = _releves_de_montee(racine, garder_compteur=False)
    assert apres["bases"]["data.db"]["sequences"] == {"journal": 4}
    assert ev.defauts_de_montee(avant, apres, montee, {}) == ["data.db : compteur AUTOINCREMENT de journal 5 → 4"]
    vide = {"racine": str(racine), "bases": {}}
    assert ev.comparer_lignes(avant, vide) == {"data.db": {"base": "absente"}}
    assert ev.defauts_de_montee(avant, vide, ev.comparer_lignes(avant, vide), {}) == ["data.db : base disparue"]


def test_lignes_une_table_vivante_au_controle_n_est_pas_un_defaut(tmp_path):
    """Ce qu'un simple redémarrage change aussi (relevé de CONTRÔLE) ne compte pas comme défaut de la montée, et les
    changements « propres » à la montée excluent ceux du contrôle."""
    racine = tmp_path / "v"
    racine.mkdir()
    avant, apres, montee = _releves_de_montee(
        racine, lambda c: c.execute("UPDATE cartes SET statut = 'blocked' WHERE id = 't_3'"))
    controle = {"data.db": {"tables": {"cartes": {"perdues": 0, "modifiees": 1, "ajoutees": 0}}}}
    assert ev.defauts_de_montee(avant, apres, montee, controle) == []
    propres = ev.changements_propres(montee, controle)
    assert "cartes" not in propres["data.db"]["tables"] and "meta_schema" in propres["data.db"]["tables"]
    schemas = ev.comparer_schemas(avant, apres)
    temoin = {"data.db": {"objets_ajoutes": ["table:nouvelle"], "meta_schema": ["3", "4"]}}
    assert ev.changements_propres(schemas, temoin) == {
        "data.db": {"objets_modifies": ["table:cartes", "table:journal"]}}


def test_lignes_ne_modifie_jamais_la_racine_lue(tmp_path):
    racine = tmp_path / "v"
    racine.mkdir()
    conn = _base_avant(racine / "data.db")
    try:
        octets = _empreintes_octets(racine)
        assert (racine / "data.db-wal").stat().st_size > 0
        releve = ev.lignes(str(racine))
        assert _empreintes_octets(racine) == octets, "le relevé a modifié la racine lue"
    finally:
        conn.close()
    assert releve["bases"]["data.db"]["tables"]["cartes"]["nombre"] == 6


def test_lignes_en_ligne_de_commande_avec_projection_sur_l_entree_standard(tmp_path):
    racine = tmp_path / "v"
    racine.mkdir()
    conn = _base_avant(racine / "data.db")
    try:
        avant = _commande("lignes", str(racine))
        conn.execute("ALTER TABLE cartes ADD COLUMN neuve TEXT")
        sortie = subprocess.run([sys.executable, OUTIL, "lignes", str(racine), "-"], capture_output=True, text=True,
                                check=True, input=json.dumps(ev.projection_de(avant)))
        apres = json.loads(sortie.stdout)
    finally:
        conn.close()
    assert ev.comparer_lignes(avant, apres) == {}
    assert apres["bases"]["data.db"]["tables"]["cartes"]["nouvelles_colonnes"] == {"neuve": 0}
    refus = subprocess.run([sys.executable, OUTIL, "lignes", str(racine), "-"], capture_output=True, text=True,
                           input="[1, 2]")
    assert refus.returncode == 2 and "Projection illisible" in refus.stderr
