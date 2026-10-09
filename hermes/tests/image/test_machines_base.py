"""Postes, codes d'enrôlement, ordres et inventaires en base (étape P5, cahier P5 § 4.3, § 4.6, § 5, § 12.2) :
jamais le jeton ni le code en clair, usage unique, un seul poste actif, confirmation par l'empreinte, révocation,
ordres livrés au moins une fois, inventaire tout ou rien avec le résumé des quotas calculé par le greffon."""

from __future__ import annotations

import json

import pytest

from conftest import fixture_machine, inventaire_factice, poste_confirme

from acp_poste_contrat.machine import PROTOCOLE, empreinte_courte, empreinte_jeton  # noqa: E402


def _enroler(noyau, conn, code: str, nom: str = "Poste Windows"):
    with noyau.base.transaction(conn):
        return noyau.machines.enroler_dans(conn, empreinte_jeton(code), nom=nom, version_poste="1.0.0",
                                           protocole=PROTOCOLE)


def _tout_le_texte_de_la_base(conn) -> str:
    morceaux = []
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        for ligne in conn.execute(f"SELECT * FROM {table}").fetchall():
            morceaux.append(json.dumps([str(v) for v in ligne], ensure_ascii=False))
    return "\n".join(morceaux)


def test_code_rendu_une_fois_seul_son_condensat_en_base(noyau, conn):
    cree = noyau.machines.creer_code(conn, "proprietaire:test")
    code = cree["code"]
    assert code.startswith("acpe_") and len(code) == 48 and cree["validite_s"] == 600
    assert conn.execute("SELECT empreinte_code FROM enrolements").fetchone()[0] == empreinte_jeton(code)
    reponse = _enroler(noyau, conn, code)
    jeton = reponse["jeton"]
    assert jeton.startswith("acpm_") and len(jeton) == 48 and reponse["etat"] == "a_confirmer"
    assert reponse["empreinte"] == empreinte_courte(empreinte_jeton(jeton))
    ligne = conn.execute("SELECT * FROM machines WHERE id = ?", (reponse["machine_id"],)).fetchone()
    assert ligne["empreinte_jeton"] == empreinte_jeton(jeton) and ligne["nom"] == "Poste Windows"
    texte = _tout_le_texte_de_la_base(conn)
    assert code not in texte and jeton not in texte and "acpm_" not in texte and "acpe_" not in texte


def test_code_a_usage_unique_et_expire(noyau, conn):
    code = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    _enroler(noyau, conn, code)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        _enroler(noyau, conn, code)
    assert exc.value.code == "non_authentifie" and exc.value.message == (
        "Code d'enrôlement refusé : inconnu, expiré ou déjà utilisé. Générez-en un nouveau depuis la page Poste.")
    debut = noyau.base.maintenant()
    code2 = noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    noyau.base.fixer_horloge(lambda: debut + 601)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        _enroler(noyau, conn, code2)
    assert exc.value.code == "non_authentifie"


def test_un_seul_poste_actif(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.machines.creer_code(conn, "proprietaire:test")
    assert exc.value.code == "poste_deja_enrole" and "« Poste Windows »" in exc.value.message
    # L'index unique partiel refuse un second actif même écrit à la main.
    with pytest.raises(Exception, match="UNIQUE"):
        with noyau.base.transaction(conn):
            conn.execute("INSERT INTO machines (id, nom, empreinte_jeton, etat, protocole, version_poste, cree_le) "
                         "VALUES ('m00000000001', 'x', ?, 'actif', 'acp-machine/1', '1.0.0', 0)", ("0" * 64,))
    assert conn.execute("SELECT COUNT(*) FROM machines WHERE etat = 'actif'").fetchone()[0] == 1
    assert noyau.machines.machine_active(conn)["id"] == machine


def test_un_enrolement_remplace_le_poste_a_confirmer(noyau, conn):
    premier = _enroler(noyau, conn, noyau.machines.creer_code(conn, "proprietaire:test")["code"])
    second = _enroler(noyau, conn, noyau.machines.creer_code(conn, "proprietaire:test")["code"], nom="Second")
    etats = dict(conn.execute("SELECT id, etat FROM machines").fetchall())
    assert etats == {premier["machine_id"]: "revoque", second["machine_id"]: "a_confirmer"}
    motif = conn.execute("SELECT motif_revocation FROM machines WHERE id = ?", (premier["machine_id"],)).fetchone()[0]
    assert motif == "remplacé par un nouvel enrôlement"


def test_confirmation_par_l_empreinte(noyau, conn):
    reponse = _enroler(noyau, conn, noyau.machines.creer_code(conn, "proprietaire:test")["code"])
    machine = reponse["machine_id"]
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.machines.confirmer(conn, machine, "0000-0000", "proprietaire:test")
    assert exc.value.code == "empreinte_differente" and exc.value.message == (
        "L'empreinte saisie ne correspond pas à celle du poste enrôlé : n'activez pas ce poste ; révoquez-le et "
        "recommencez.")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.machines.confirmer(conn, machine, "pas une empreinte", "proprietaire:test")
    assert exc.value.code == "empreinte_illisible"
    assert noyau.machines.machine(conn, machine)["etat"] == "a_confirmer"
    etat = noyau.machines.confirmer(conn, machine, reponse["empreinte"].lower().replace("-", ""), "proprietaire:test")
    assert etat["machine"]["etat"] == "actif" and etat["machine"]["empreinte"] == reponse["empreinte"]
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.machines.confirmer(conn, machine, reponse["empreinte"], "proprietaire:test")
    assert exc.value.code == "pas_a_confirmer"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.machines.confirmer(conn, "m00000000000", reponse["empreinte"], "proprietaire:test")
    assert exc.value.code == "machine_inconnue"


def test_revocation_supprime_la_presence_et_abandonne_les_ordres(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)
    noyau.presence.enregistrer(conn, machine, "longpoll")
    noyau.ordres.creer(conn, machine, "releve", "proprietaire:test")
    etat = noyau.machines.revoquer(conn, machine, "PC perdu", "proprietaire:test")
    assert etat["machine"]["etat"] == "revoque" and etat["machine"]["motif_revocation"] == "PC perdu"
    assert conn.execute("SELECT COUNT(*) FROM presence WHERE machine_id = ?", (machine,)).fetchone()[0] == 0
    assert noyau.ordres.dus(conn, machine) == []
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.machines.revoquer(conn, machine, "encore", "proprietaire:test")
    assert exc.value.code == "deja_revoque"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.machines.revoquer(conn, machine, "", "proprietaire:test")
    assert exc.value.code == "motif"
    # Après révocation, un nouvel enrôlement est possible.
    assert noyau.machines.creer_code(conn, "proprietaire:test")["code"].startswith("acpe_")


def test_ordres_livres_au_moins_une_fois_puis_expires(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)
    premier = noyau.ordres.creer(conn, machine, "releve", "proprietaire:test")
    second = noyau.ordres.creer(conn, machine, "pause", "proprietaire:test")
    assert [o["id"] for o in noyau.ordres.dus(conn, machine)] == [premier, second]
    with noyau.base.transaction(conn):
        noyau.ordres.livrer_dans(conn, [premier, second])
    # Livré mais non acquitté : encore dû (au moins une fois).
    assert [o["id"] for o in noyau.ordres.dus(conn, machine)] == [premier, second]
    with noyau.base.transaction(conn):
        assert noyau.ordres.acquitter_dans(conn, machine, [second, 999999]) == 1
        assert noyau.ordres.acquitter_dans(conn, "m00000000000", [premier]) == 0  # ordre d'une autre machine
    assert [o["id"] for o in noyau.ordres.dus(conn, machine)] == [premier]
    assert noyau.ordres.releve_en_attente(conn, machine) is True
    debut = noyau.base.maintenant()
    noyau.base.fixer_horloge(lambda: debut + 3601)
    assert noyau.ordres.expirer(conn) == [premier]
    assert noyau.ordres.dus(conn, machine) == [] and noyau.ordres.releve_en_attente(conn, machine) is False


def test_inventaire_recu_tout_ou_rien_quotas_calcules(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)
    ordre = noyau.ordres.creer(conn, machine, "releve", "proprietaire:test")
    with noyau.base.transaction(conn):
        noyau.ordres.livrer_dans(conn, [ordre])
        reponse = noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice())
    assert set(reponse["releves"]) == {"poste-codex", "poste-claude"}
    ligne = conn.execute("SELECT source, machine_id, contenu FROM releves WHERE id = ?",
                         (reponse["releves"]["poste-codex"],)).fetchone()
    assert (ligne["source"], ligne["machine_id"]) == ("poste", machine)
    # Résumé calculé par le greffon : la plus grande part utilisée des fenêtres relevées (41 %), jamais estimé.
    assert json.loads(ligne["contenu"])["quotas"]["pourcentage_utilise"] == 41.0
    claude = noyau.routage.dernier_releve(conn, "poste-claude")[1]
    assert claude.quotas is None and claude.modele("opus[1m]").nature == "alias_documente"
    assert noyau.ordres.dus(conn, machine) == []  # l'ordre « releve » livré est servi
    dernier = noyau.inventaire.dernier(conn, machine)
    assert dernier["contenu"]["poste"]["nom"] == "Poste Windows" and "releves" in dernier["contenu"]
    assert dernier["alertes"] == []
    assert noyau.routage.depots_autorises(conn) == ["jetable"]
    # Hors contrat : rien n'est écrit.
    avant = conn.execute("SELECT COUNT(*) FROM releves").fetchone()[0]
    with pytest.raises(noyau.textes.RefusACP) as exc:
        with noyau.base.transaction(conn):
            noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice(modifier=lambda i: i.update(intrus=1)))
    assert exc.value.code == "requete_refusee"
    assert exc.value.message.startswith("Requête du poste refusée par le contrat : ")
    assert exc.value.message.endswith("Rien n'a été enregistré.") and "« intrus »" in exc.value.message
    assert conn.execute("SELECT COUNT(*) FROM releves").fetchone()[0] == avant


def test_inventaire_avec_un_identifiant_refuse(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)

    def fuite(inventaire):
        inventaire["releves"][0]["detail"] = "profil C:\\Users\\proprietaire"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        with noyau.base.transaction(conn):
            noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice(modifier=fuite))
    assert "releves[0].detail : chemin de lecteur" in exc.value.message
    assert conn.execute("SELECT COUNT(*) FROM releves").fetchone()[0] == 0


def test_alertes_de_l_inventaire(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)

    def secours(inventaire):
        inventaire["releves"][0]["origine_liste"] = "identique_au_catalogue_embarque"
        inventaire["versions"]["claude"] = {"lue": "2.1.281", "testee": "2.1.280", "conforme": False}
        inventaire["bac_a_sable_codex"].update(ecriture_admise=False, mode_lu="unelevated",
                                               raison="Bac à sable Codex non élevé (unelevated) : l'écriture est "
                                                      "refusée.")
    with noyau.base.transaction(conn):
        reponse = noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice(modifier=secours))
    assert reponse["alertes"] == [
        "Relevé Codex identique au catalogue embarqué de Codex 0.156.1 : liste de secours probable.",
        "Claude Code 2.1.281 n'est pas la version testée par le poste (2.1.280).",
        "Écriture Codex non admise (étape P6) : Bac à sable Codex non élevé (unelevated) : l'écriture est refusée."]


def test_cadence_des_inventaires(noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)
    assert noyau.inventaire.delai_avant_prochain(conn, machine) == 0
    with noyau.base.transaction(conn):
        noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice())
    assert 55 <= noyau.inventaire.delai_avant_prochain(conn, machine) <= 60
    noyau.ordres.creer(conn, machine, "releve", "proprietaire:test")
    assert noyau.inventaire.delai_avant_prochain(conn, machine) == 0  # un ordre « releve » en attente l'autorise


def test_exemple_de_reponse_conforme(noyau, conn):
    """La réponse du greffon a la forme de l'exemple partagé avec le poste (fixtures_machine)."""
    from acp_poste_contrat.machine import ReponseInventaire

    machine, _jeton = poste_confirme(noyau, conn)
    with noyau.base.transaction(conn):
        reponse = noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice())
    ReponseInventaire.model_validate(reponse)
    assert set(reponse) == set(fixture_machine("inventaire_reponse.json"))
