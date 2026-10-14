"""Gardes remote-only : anciennes données conservées, inventaire courant exigé."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("acp_distant_test", RACINE / "hermes/plugins/acp-poste/noyau/distant.py")
distant = importlib.util.module_from_spec(spec)
spec.loader.exec_module(distant)


@pytest.fixture
def conn(tmp_path):
    connexion = sqlite3.connect(tmp_path / "ancien.sqlite")
    connexion.row_factory = sqlite3.Row
    connexion.executescript("""
        CREATE TABLE machines(id TEXT PRIMARY KEY, etat TEXT);
        CREATE TABLE inventaires(id INTEGER PRIMARY KEY, machine_id TEXT, contenu TEXT);
        INSERT INTO machines VALUES ('serveur', 'actif');
    """)
    yield connexion
    connexion.close()


def publier(conn, plateforme, hote):
    conn.execute("INSERT INTO inventaires(machine_id, contenu) VALUES ('serveur', ?)",
                 (json.dumps({"poste": {"plateforme": plateforme, "hote": hote}}),))
    conn.commit()


def test_ancien_pc_conserve_mais_inutilisable(conn):
    publier(conn, "windows", "pc")
    avant = list(conn.iterdump())
    assert distant.raison_refus(conn, "serveur") == distant.EXECUTION_LOCALE_REFUSEE
    assert list(conn.iterdump()) == avant


def test_identite_distante_admise_sans_affirmer_les_capacites(conn):
    publier(conn, "linux", "railway")
    assert distant.raison_refus(conn, "serveur") is None


def test_linux_local_et_plateforme_inconnue_refuses(conn):
    publier(conn, "linux", "pc")
    assert distant.raison_refus(conn, "serveur") == distant.EXECUTION_LOCALE_REFUSEE
    publier(conn, None, "railway")
    assert distant.raison_refus(conn, "serveur") == distant.EXECUTION_LOCALE_REFUSEE


def test_dernier_inventaire_remplace_un_ancien_verdict_admis(conn):
    publier(conn, "linux", "railway")
    assert distant.raison_refus(conn, "serveur") is None
    publier(conn, "windows", "pc")
    assert distant.raison_refus(conn, "serveur") == distant.EXECUTION_LOCALE_REFUSEE


def test_absence_corruption_et_revocation_refusees(conn):
    assert distant.raison_refus(conn, "serveur") == distant.INVENTAIRE_ABSENT
    conn.execute("INSERT INTO inventaires(machine_id, contenu) VALUES ('serveur', '{')")
    assert distant.raison_refus(conn, "serveur") == distant.INVENTAIRE_ABSENT
    publier(conn, "linux", "railway")
    conn.execute("UPDATE machines SET etat = 'revoque'")
    assert distant.raison_refus(conn, "serveur") == distant.SERVEUR_ABSENT
    assert distant.raison_refus(conn, "inconnu") == distant.SERVEUR_ABSENT


@pytest.mark.parametrize("hote", ["pc", "vps", None])
def test_hebergement_non_pris_en_charge_refuse(conn, hote):
    # Un libellé inventé ne rend pas le produit compatible VPS.
    publier(conn, "linux", hote)
    assert distant.raison_refus(conn, "serveur") == distant.EXECUTION_LOCALE_REFUSEE
