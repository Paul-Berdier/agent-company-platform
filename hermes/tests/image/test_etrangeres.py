"""Cartes ``poste-*`` non émises par le greffon (cahier P4 § 12.3, décision D37) : bloquées, jamais archivées."""

from __future__ import annotations

from conftest import carte, lancer_sur_depot

RAISON = ("Refusé par ACP : carte poste-* non émise par le greffon acp-poste ; seul le greffon crée les cartes du "
          "poste.")


def _carte_du_proprietaire(noyau, tableau, assigne="poste-codex", **options):
    with noyau.ka.connexion(tableau) as kc:
        return noyau.ka.create_task(kc, title="Carte à la main", body="Fais ceci sur le poste.", assignee=assigne,
                                    created_by=options.pop("created_by", "proprietaire"), board=tableau, **options)


def _raison_du_blocage(noyau, tableau, identifiant):
    with noyau.ka.connexion(tableau) as kc:
        evenements = [e for e in noyau.ka.list_events(kc, identifiant) if e.kind in ("blocked", "block_loop_detected")]
    return [(e.kind, (e.payload or {}).get("kind"), (e.payload or {}).get("reason")) for e in evenements]


def test_carte_poste_du_proprietaire_bloquee_avec_raison(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    etrangere = _carte_du_proprietaire(noyau, projet["tableau"])
    assert noyau.etrangeres.balayer(conn) == [(projet["tableau"], etrangere)]
    tache = carte(noyau, projet["tableau"], etrangere)
    assert (tache.status, tache.block_kind) == ("blocked", "capability")
    assert _raison_du_blocage(noyau, projet["tableau"], etrangere) == [("blocked", "capability", RAISON)]
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE action = 'carte_etrangere_bloquee'").fetchone()[0] == 1
    # La notification vient de la règle « blocked » de l'émetteur (tableau de projet).
    assert noyau.emetteur.lire_evenements(conn) == {projet["tableau"]: 1}
    assert conn.execute("SELECT genre FROM notifications").fetchone()[0] == "bloquee"
    # Rejouée, la passe ne bloque rien de plus.
    assert noyau.etrangeres.balayer(conn) == []


def test_carte_du_greffon_intacte_meme_avant_rattachement(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    exploration = projet["cartes"]["exploration"]
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET carte = NULL WHERE carte = ?", (exploration,))
    assert noyau.etrangeres.balayer(conn) == []
    assert carte(noyau, projet["tableau"], exploration).status == "ready"


def test_seconde_occurrence_en_triage(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    etrangere = _carte_du_proprietaire(noyau, projet["tableau"])
    noyau.etrangeres.balayer(conn)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.unblock_task(kc, etrangere)  # le propriétaire débloque
    assert carte(noyau, projet["tableau"], etrangere).status == "ready"
    noyau.etrangeres.balayer(conn)
    assert carte(noyau, projet["tableau"], etrangere).status == "triage"
    assert [k for k, _, _ in _raison_du_blocage(noyau, projet["tableau"], etrangere)] == ["blocked",
                                                                                         "block_loop_detected"]


def test_demande_de_la_carte_refuse_une_etrangere(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    cle = f"acp:{projet['id']}:t0:exploration"
    legitime = carte(noyau, projet["tableau"], projet["cartes"]["exploration"])
    assert noyau.etrangeres.demande_de_la_carte(conn, projet["tableau"], legitime)["cle"] == cle
    # Même clé, autre créateur ; même clé sur un autre tableau ; clé inconnue ; autre voie.
    noyau.ka.create_board("acp-autre-tableau", name="Autre")
    copie = _carte_du_proprietaire(noyau, "acp-autre-tableau", assigne="poste-claude", idempotency_key=cle,
                                   created_by="acp-poste")
    assert noyau.etrangeres.demande_de_la_carte(conn, "acp-autre-tableau",
                                                carte(noyau, "acp-autre-tableau", copie)) is None
    for options in ({"created_by": "proprietaire", "idempotency_key": "acp:p_x:t0:x"},
                    {"created_by": "acp-poste", "idempotency_key": "acp:p_inconnu:t1:e1:implementation"},
                    {"created_by": "acp-poste"}):
        forgee = _carte_du_proprietaire(noyau, projet["tableau"], **dict(options))
        assert noyau.etrangeres.demande_de_la_carte(conn, projet["tableau"], carte(noyau, projet["tableau"], forgee)) \
            is None
    changee = carte(noyau, projet["tableau"], projet["cartes"]["exploration"])
    changee.assignee = "poste-codex"
    assert noyau.etrangeres.demande_de_la_carte(conn, projet["tableau"], changee) is None


def test_carte_poste_hors_tableau_de_projet(noyau, conn):
    """Sur le tableau « default » (aucun curseur d'événements), la notification part du balayage."""
    noyau.ka.create_board("default")
    etrangere = _carte_du_proprietaire(noyau, "default", assigne="poste-claude")
    ordinaire = _carte_du_proprietaire(noyau, "default", assigne="default")
    assert noyau.etrangeres.balayer(conn) == [("default", etrangere)]
    assert carte(noyau, "default", ordinaire).status == "ready"  # une carte ordinaire n'est pas visée
    assert [tuple(l) for l in conn.execute("SELECT cle, genre FROM notifications")] == [
        (f"bloquee:default:{etrangere}", "bloquee")]
