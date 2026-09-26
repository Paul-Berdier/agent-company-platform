"""Présence du poste à l'étape P5 (cahier P5 § 4.7) : seuls les postes ``actif`` comptent, grâce de redémarrage de
Hermes (tableau de bord ET passerelle), aucune notification « hors ligne » après une révocation, états du poste."""

from __future__ import annotations

import time

from conftest import poste_confirme

from acp_poste_contrat.machine import PROTOCOLE, empreinte_jeton  # noqa: E402


def _notifs(conn):
    return [tuple(l) for l in conn.execute("SELECT cle, genre FROM notifications ORDER BY id")]


def _horloge(noyau, instant):
    noyau.base.fixer_horloge(lambda: instant)


def test_attente_enregistre_la_presence(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)
    etat = noyau.presence.etat_poste(conn)
    assert etat["etat"] == "hors_ligne" and etat["derniere_vue"] is None
    assert etat["message"] == "Poste confirmé mais jamais vu depuis : démarrez son service (tâche planifiée)."
    with noyau.base.transaction(conn):
        noyau.presence.enregistrer_dans(conn, machine, "longpoll")
    etat = noyau.presence.etat_poste(conn)
    assert etat["etat"] == "en_ligne" and etat["machine"] == machine and etat["source"] == "longpoll"
    assert etat["poste"]["nom"] == "Poste Windows" and etat["poste"]["etat"] == "actif"


def test_a_confirmer_ne_compte_pas(noyau, conn):
    noyau.base.poser_reglage(conn, "seuil_hors_ligne_s", 10, "test")
    debut = time.time() + 1000
    _horloge(noyau, debut)
    code = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    with noyau.base.transaction(conn):
        reponse = noyau.machines.enroler_dans(conn, empreinte_jeton(code), nom="Poste", version_poste="0.11.0",
                                              protocole=PROTOCOLE)
        # Présence posée à la main (la route n'en écrit jamais pour un poste à confirmer) : elle ne compte pas.
        noyau.presence.enregistrer_dans(conn, reponse["machine_id"], "longpoll")
    etat = noyau.presence.etat_poste(conn)
    assert etat["etat"] == "a_confirmer" and reponse["empreinte"] in etat["message"]
    _horloge(noyau, debut + 60)
    assert noyau.presence.evaluer(conn) == [] and _notifs(conn) == []


def test_revocation_sans_notification_hors_ligne(noyau, conn):
    noyau.base.poser_reglage(conn, "seuil_hors_ligne_s", 10, "test")
    debut = time.time() + 1000
    _horloge(noyau, debut)
    machine, _jeton = poste_confirme(noyau, conn)
    noyau.presence.enregistrer(conn, machine, "longpoll")
    noyau.machines.revoquer(conn, machine, "essai", "proprietaire:test")
    _horloge(noyau, debut + 600)
    assert noyau.presence.evaluer(conn) == [] and _notifs(conn) == []
    etat = noyau.presence.etat_poste(conn)
    assert etat["etat"] == "revoque" and etat["message"].startswith("Poste révoqué le ")
    assert "(essai)" in etat["message"]


def test_redemarrage_de_hermes_sans_notification(noyau, conn, monkeypatch):
    noyau.base.poser_reglage(conn, "seuil_hors_ligne_s", 180, "test")
    debut = time.time() + 10_000
    _horloge(noyau, debut)
    machine, _jeton = poste_confirme(noyau, conn)
    noyau.presence.enregistrer(conn, machine, "longpoll")
    # Le tableau de bord redémarre 100 s plus tard (redéploiement) : les attentes sont coupées.
    _horloge(noyau, debut + 100)
    noyau.presence.ecrire_demarrage_tableau_de_bord(conn)
    _horloge(noyau, debut + 200)
    assert noyau.presence.evaluer(conn) == []  # 200 s sans vue, mais seulement 100 s depuis le redémarrage
    _horloge(noyau, debut + 281)
    assert noyau.presence.evaluer(conn) == [machine]
    assert _notifs(conn) == [(f"hors_ligne:{machine}:1", "hors_ligne")]


def test_passerelle_relancee_avant_le_tableau_de_bord(noyau, conn, monkeypatch):
    """La passerelle (qui évalue) repart avant que le tableau de bord réécrive sa date : elle se fie à SON démarrage."""
    noyau.base.poser_reglage(conn, "seuil_hors_ligne_s", 180, "test")
    debut = time.time() + 20_000
    _horloge(noyau, debut)
    machine, _jeton = poste_confirme(noyau, conn)
    noyau.presence.enregistrer(conn, machine, "longpoll")
    _horloge(noyau, debut + 50)
    noyau.presence.ecrire_demarrage_tableau_de_bord(conn)  # ancien démarrage du tableau de bord
    monkeypatch.setattr(noyau.presence, "DEMARRAGE_DU_PROCESSUS", int(debut + 150))
    _horloge(noyau, debut + 250)
    assert noyau.presence.evaluer(conn) == []
    _horloge(noyau, debut + 331)
    assert noyau.presence.evaluer(conn) == [machine]


def test_presence_simulee_de_p4_inchangee(noyau, conn):
    """Sans poste enrôlé, la présence simulée des tests de P4 garde son sens (en ligne, hors ligne, notifiée)."""
    noyau.base.poser_reglage(conn, "seuil_hors_ligne_s", 10, "test")
    debut = time.time() + 1000
    _horloge(noyau, debut)
    noyau.presence.enregistrer(conn, "poste-simule", "simule")
    assert noyau.presence.etat_poste(conn)["etat"] == "en_ligne"
    _horloge(noyau, debut + 11)
    assert noyau.presence.evaluer(conn) == ["poste-simule"]


def test_etats_du_poste(noyau, conn):
    assert noyau.presence.etat_poste(conn)["etat"] == "non_configure"
    code = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    with noyau.base.transaction(conn):
        reponse = noyau.machines.enroler_dans(conn, empreinte_jeton(code), nom="Poste", version_poste="0.11.0",
                                              protocole=PROTOCOLE)
    assert noyau.presence.etat_poste(conn)["etat"] == "a_confirmer"
    noyau.machines.confirmer(conn, reponse["machine_id"], reponse["empreinte"], "proprietaire:test")
    assert noyau.presence.etat_poste(conn)["etat"] == "hors_ligne"
    noyau.presence.enregistrer(conn, reponse["machine_id"], "longpoll")
    assert noyau.presence.etat_poste(conn)["etat"] == "en_ligne"
    conn.execute("UPDATE machines SET politique_valide = 0 WHERE id = ?", (reponse["machine_id"],))
    assert noyau.presence.etat_poste(conn)["message"] == (
        "Politique locale invalide : le poste reste joignable mais ne publie plus rien.")
    noyau.machines.revoquer(conn, reponse["machine_id"], "fin", "proprietaire:test")
    assert noyau.presence.etat_poste(conn)["etat"] == "revoque"
