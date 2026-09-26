"""Schéma v2 de la base du greffon (étape P5, cahier P5 § 12.1) : migration v1 → v2 idempotente, y compris entre
deux processus concurrents ; relevés de P4 lisibles après la migration ; purge qui épargne les relevés cités ou
acceptés (``foreign_keys=ON``) ; aucune fonction ``…_dans`` n'ouvre de transaction imbriquée."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from conftest import PYTHON_HERMES, inventaire_factice, lancer_sur_depot, poste_confirme, releve_factice

GREFFON = "/opt/hermes/plugins/acp-poste"


def _schema_v1(noyau) -> str:
    """Le schéma v1 de P4 : la partie du schéma courant qui précède les tables de P5 (inchangée depuis P4)."""
    return noyau.base.SCHEMA.split("CREATE TABLE IF NOT EXISTS machines")[0]


def _base_v1(noyau, chemin: Path, *, avec_releve: bool = True) -> None:
    """Base v1 telle que P4 l'a laissée : tables, version '1', un relevé factice et une demande qui le cite."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN")
        for instruction in _schema_v1(noyau).split(";"):
            if instruction.strip():
                conn.execute(instruction)
        conn.execute("INSERT INTO meta_schema (cle, valeur) VALUES ('version', '1')")
        if avec_releve:
            contenu = releve_factice("poste-codex")
            conn.execute("INSERT INTO releves (voie, source, version_cli, releve_le, recu_le, contenu) "
                         "VALUES ('poste-codex', 'releve_factice', '0.0.0-factice', 1, 1, ?)", (json.dumps(contenu),))
        conn.execute("COMMIT")
    finally:
        conn.close()


def _colonnes(conn, table: str):
    return [l[1] for l in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def test_v1_vers_v2_idempotente(noyau):
    chemin = noyau.base.chemin_base()
    _base_v1(noyau, chemin)
    noyau.base._initialisees.clear()
    with noyau.base.connexion() as conn:
        assert noyau.base.version_schema(conn) == "2"
        noyau.base.migrer(conn)
        noyau.base.migrer(conn)
        assert conn.execute("SELECT COUNT(*) FROM meta_schema").fetchone()[0] == 1
        assert noyau.base.version_schema(conn) == "2"
        colonnes = _colonnes(conn, "releves")
        assert colonnes[-3:] == ["machine_id", "accepte_le", "accepte_par"] and len(colonnes) == len(set(colonnes))
        tables = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"machines", "enrolements", "ordres", "inventaires"} <= tables
        index = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert {"un_seul_poste_actif", "releves_par_voie"} <= index


def test_base_neuve_et_base_migree_ont_le_meme_schema(noyau, tmp_path):
    with noyau.base.connexion() as conn:
        neuve = {t: _colonnes(conn, t) for t in noyau.base.TABLES}
    ancienne = tmp_path / "v1.db"
    _base_v1(noyau, ancienne, avec_releve=False)
    conn = sqlite3.connect(ancienne, isolation_level=None)
    try:
        noyau.base.migrer(conn)
        assert {t: _colonnes(conn, t) for t in noyau.base.TABLES} == neuve
    finally:
        conn.close()


def test_migration_par_deux_processus_concurrents(noyau, tmp_path):
    """Passerelle et tableau de bord peuvent migrer en même temps : l'un attend l'autre (BEGIN IMMEDIATE), les
    colonnes ne sont ajoutées qu'une fois, aucun « duplicate column name »."""
    chemin = tmp_path / "concurrente.db"
    _base_v1(noyau, chemin)
    code = ("import sqlite3, sys, time\n"
            f"sys.path.insert(0, {GREFFON!r})\n"
            "from noyau import base\n"
            f"conn = sqlite3.connect({str(chemin)!r}, isolation_level=None, timeout=10)\n"
            "conn.execute('PRAGMA busy_timeout=10000')\n"
            "time.sleep(max(0.0, float(sys.argv[1]) - time.time()))\n"
            "base.migrer(conn)\n"
            "print(conn.execute(\"SELECT valeur FROM meta_schema WHERE cle = 'version'\").fetchone()[0])\n")
    import time

    depart = str(time.time() + 1.5)
    env = {"HERMES_HOME": str(tmp_path / "home-concurrent"), "PATH": "/usr/bin:/bin"}
    processus = [subprocess.Popen([PYTHON_HERMES, "-c", code, depart], env=env, cwd="/opt/hermes",
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    sorties = [p.communicate(timeout=120) for p in processus]
    assert [p.returncode for p in processus] == [0, 0], [s[1][-2000:] for s in sorties]
    assert [s[0].strip().splitlines()[-1] for s in sorties] == ["2", "2"]
    conn = sqlite3.connect(chemin)
    try:
        assert _colonnes(conn, "releves").count("machine_id") == 1
    finally:
        conn.close()


def test_releves_p4_en_base_restent_lisibles(noyau):
    chemin = noyau.base.chemin_base()
    _base_v1(noyau, chemin)
    noyau.base._initialisees.clear()
    with noyau.base.connexion() as conn:
        dernier = noyau.routage.dernier_releve(conn, "poste-codex")
        assert dernier is not None and dernier[1].source == "releve_factice"
        assert dernier[1].modele_par_defaut().id == "factice-codex-1"
        assert noyau.routage.depots_autorises(conn) == ["jetable"]


def test_releves_factices_gardent_machine_id_nul(noyau, conn):
    identifiant = noyau.routage.enregistrer_releve(conn, releve_factice("poste-claude"))
    ligne = conn.execute("SELECT machine_id, accepte_le FROM releves WHERE id = ?", (identifiant,)).fetchone()
    assert tuple(ligne) == (None, None)


def test_purge_epargne_les_releves_cites(noyau, conn):
    """La base a foreign_keys=ON : un relevé cité par demandes.releve_id ne peut pas être supprimé ; la purge
    l'épargne (sans quoi la réception de l'inventaire échouerait tout entière), comme un relevé accepté."""
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    projet = lancer_sur_depot(noyau, conn)
    cite = conn.execute("SELECT releve_id FROM demandes WHERE projet_id = ? AND releve_id IS NOT NULL",
                        (projet["id"],)).fetchone()[0]
    voie = conn.execute("SELECT voie FROM releves WHERE id = ?", (cite,)).fetchone()[0]
    accepte = noyau.routage.enregistrer_releve(conn, releve_factice(voie))
    conn.execute("UPDATE releves SET accepte_le = 1, accepte_par = 'test' WHERE id = ?", (accepte,))
    for _ in range(noyau.routage.RELEVES_GARDES_PAR_VOIE + 5):
        noyau.routage.enregistrer_releve(conn, releve_factice(voie))
    with noyau.base.transaction(conn):
        supprimes = noyau.routage.purger_releves_dans(conn, voie)
    assert supprimes >= 1
    restants = {l[0] for l in conn.execute("SELECT id FROM releves WHERE voie = ?", (voie,))}
    assert cite in restants and accepte in restants
    assert len(restants) == noyau.routage.RELEVES_GARDES_PAR_VOIE + 2
    # Témoin : sans l'exclusion des relevés cités, SQLite refuse la suppression.
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        with noyau.base.transaction(conn):
            conn.execute("DELETE FROM releves WHERE id = ?", (cite,))


class _SansTransactionImbriquee:
    """Connexion qui LÈVE si un BEGIN est exécuté alors qu'une transaction est déjà ouverte."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql, *args):
        if sql.strip().upper().startswith("BEGIN") and self._conn.in_transaction:
            raise AssertionError(f"transaction imbriquée : {sql}")
        return self._conn.execute(sql, *args)

    def __getattr__(self, nom):
        return getattr(self._conn, nom)


def test_aucune_transaction_imbriquee(noyau, conn):
    """Chaque fonction appelée sous la transaction d'une route machine (…_dans) n'en ouvre aucune autre."""
    from acp_poste_contrat.machine import PROTOCOLE, empreinte_jeton

    code = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    espion = _SansTransactionImbriquee(conn)
    with noyau.base.transaction(espion):
        reponse = noyau.machines.enroler_dans(espion, empreinte_jeton(code), nom="Poste", version_poste="0.11.0",
                                              protocole=PROTOCOLE)
    noyau.machines.confirmer(conn, reponse["machine_id"], reponse["empreinte"], "proprietaire:test")
    machine = reponse["machine_id"]
    with noyau.base.transaction(espion):
        noyau.presence.enregistrer_dans(espion, machine, "longpoll")
        ordre = noyau.ordres.creer_dans(espion, machine, "releve", "proprietaire:test")
        noyau.ordres.livrer_dans(espion, [ordre])
        noyau.inventaire.recevoir_dans(espion, machine, inventaire_factice())
        noyau.ordres.acquitter_dans(espion, machine, [ordre])
        noyau.routage.enregistrer_releve_dans(espion, releve_factice("poste-codex"))
    # Témoin : l'espion détecte bien une fonction qui ouvre sa propre transaction.
    with pytest.raises(AssertionError, match="transaction imbriquée"):
        with noyau.base.transaction(espion):
            noyau.routage.enregistrer_releve(espion, releve_factice("poste-codex"))


def test_reglages_p5_par_defaut(noyau, conn):
    assert [noyau.base.reglage(conn, c) for c in ("longpoll_attente_s", "enrolement_validite_s",
                                                   "inventaire_intervalle_min_s", "ordre_expiration_s")] == [
        25, 600, 60, 3600]
    noyau.base.poser_reglage(conn, "longpoll_attente_s", 5, "test")
    assert noyau.base.reglage(conn, "longpoll_attente_s") == 5
    machine, _jeton = poste_confirme(noyau, conn)
    assert conn.execute("SELECT etat FROM machines WHERE id = ?", (machine,)).fetchone()[0] == "actif"
