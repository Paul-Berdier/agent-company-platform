"""Présence du poste (cahier P4 § 12.4) : jamais vu, hors ligne une fois par passage, retour en ligne."""

from __future__ import annotations

import time

import pytest

from conftest import en_discussion, outil


def _notifs(conn):
    return [tuple(l) for l in conn.execute("SELECT cle, genre FROM notifications ORDER BY id")]


def test_jamais_vu_non_configure_sans_notification(noyau, conn, monkeypatch):
    en_discussion(monkeypatch)
    etat = outil(noyau, "poste_etat", {})["poste"]
    assert etat["etat"] == "non_configure" and etat["derniere_vue"] is None
    assert etat["message"] == "Le poste n'a jamais été vu (connexion prévue à l'étape P5)."
    assert noyau.presence.evaluer(conn) == [] and _notifs(conn) == []


def test_hors_ligne_une_notification_par_passage(noyau, conn):
    noyau.base.poser_reglage(conn, "seuil_hors_ligne_s", 10, "test")
    debut = time.time()
    noyau.base.fixer_horloge(lambda: debut)
    noyau.presence.enregistrer(conn, "poste-paul", "simule")
    assert noyau.presence.etat_poste(conn)["etat"] == "en_ligne"
    noyau.base.fixer_horloge(lambda: debut + 5)
    assert noyau.presence.evaluer(conn) == []
    noyau.base.fixer_horloge(lambda: debut + 11)
    assert noyau.presence.evaluer(conn) == ["poste-paul"]
    assert noyau.presence.evaluer(conn) == []  # une seule notification par passage
    assert _notifs(conn) == [("hors_ligne:poste-paul:1", "hors_ligne")]
    texte = conn.execute("SELECT texte FROM notifications").fetchone()[0]
    assert texte.startswith("ACP — Poste hors ligne depuis ") and "(Europe/Paris), 0 carte en attente." in texte
    etat = noyau.presence.etat_poste(conn)
    assert etat["etat"] == "hors_ligne" and etat["hors_ligne_depuis"] == int(debut)


def test_retour_en_ligne_nouveau_passage(noyau, conn):
    noyau.base.poser_reglage(conn, "seuil_hors_ligne_s", 10, "test")
    debut = time.time()
    noyau.base.fixer_horloge(lambda: debut)
    noyau.presence.enregistrer(conn, "poste-paul", "simule")
    noyau.base.fixer_horloge(lambda: debut + 11)
    noyau.presence.evaluer(conn)
    noyau.base.fixer_horloge(lambda: debut + 12)
    ligne = noyau.presence.enregistrer(conn, "poste-paul", "simule")
    assert ligne["passage"] == 2 and ligne["hors_ligne_depuis"] is None
    assert noyau.presence.etat_poste(conn)["etat"] == "en_ligne"
    noyau.base.fixer_horloge(lambda: debut + 30)
    assert noyau.presence.evaluer(conn) == ["poste-paul"]
    assert _notifs(conn) == [("hors_ligne:poste-paul:1", "hors_ligne"), ("hors_ligne:poste-paul:2", "hors_ligne")]


@pytest.mark.parametrize("machine, source", [("", "simule"), ("a b", "simule"), ("poste", "radio")])
def test_enregistrer_refuse_une_entree_invalide(noyau, conn, machine, source):
    with pytest.raises(ValueError):
        noyau.presence.enregistrer(conn, machine, source)


def test_accord_du_nombre_de_cartes(noyau):
    """Textes des notifications : singulier sous 2 (« 0 carte », « 1 carte faite »), pluriel ensuite."""
    cartes = noyau.textes.cartes
    assert [cartes(0), cartes(1), cartes(2)] == ["0 carte", "1 carte", "2 cartes"]
    assert [cartes(1, "faite"), cartes(4, "faite")] == ["1 carte faite", "4 cartes faites"]
