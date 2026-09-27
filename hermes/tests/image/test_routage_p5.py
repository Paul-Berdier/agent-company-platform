"""Routage à l'étape P5 (cahier P5 § 12.4, § 12.5, § 14.3) : conditions ajoutées à la résolution de P4 (voie
indisponible, non connectée, liste de secours, version, politique du poste, efforts inconnus), table validée tout ou
rien, suggestion sur les seuls champs lus, table à revalider, interdits de Hermes levés sur confirmation, surcharges
globales, relevé accepté, vue des quotas."""

from __future__ import annotations

import datetime as _dt

import pytest

from conftest import inventaire_factice, poste_confirme, releve_factice

_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
PROJET ={"id": None, "titre": "Outil jetable", "depot_alias": "jetable"}


def _avancer(noyau, secondes: int) -> None:
    instant = noyau.base.maintenant() + secondes
    noyau.base.fixer_horloge(lambda: instant)


def _recevoir(noyau, conn, machine, modifier=None):
    with noyau.base.transaction(conn):
        return noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice(modifier=modifier))


def _poste_et_inventaire(noyau, conn, modifier=None):
    machine, _jeton = poste_confirme(noyau, conn)
    reponse = _recevoir(noyau, conn, machine, modifier)
    return machine, reponse


def _refus(noyau, conn, **choix):
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.valider_choix(conn, classe=choix.pop("classe", "implementation"), projet=PROJET,
                                    palier=choix.pop("palier", None), source="table", **choix)
    return exc.value


def _admis(noyau, conn, **choix):
    return noyau.routage.valider_choix(conn, classe=choix.pop("classe", "implementation"), projet=PROJET,
                                       palier=choix.pop("palier", None), source="table", **choix)


def test_releve_du_compte_admis(noyau, conn):
    _poste_et_inventaire(noyau, conn)
    resolution = _admis(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort="high")
    assert (resolution.voie, resolution.modele, resolution.effort) == ("poste-codex", "factice-codex-1", "high")
    assert resolution.mention is None  # quota connu (41 %) sous le seuil, relevé frais
    resolution = _admis(noyau, conn, voie="poste-claude", modele="opus[1m]", effort="medium")
    assert resolution.modele == "opus[1m]"


def test_liste_de_secours_refusee(noyau, conn):
    def secours(inventaire):
        inventaire["releves"][0]["origine_liste"] = "identique_au_catalogue_embarque"
    machine, reponse = _poste_et_inventaire(noyau, conn, secours)
    refus = _refus(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort=None)
    assert refus.code == "liste_de_secours"
    assert refus.message.startswith("Refusé par ACP : le relevé Codex du ") and (
        "est une liste de secours (identique au catalogue embarqué de Codex 0.156.1), pas celle de votre compte. "
        "Reconnectez Codex, ou acceptez ce relevé depuis la page Routage.") in refus.message
    # Hermes ne prend pas non plus un modèle d'une liste de secours.
    assert _refus(noyau, conn, classe="architecture", voie="hermes", modele="factice-codex-1",
                  effort=None).code == "liste_de_secours"
    vue = noyau.routage.accepter_releve(conn, reponse["releves"]["poste-codex"], "proprietaire:test")
    assert vue["voies"]["poste-codex"]["badge"] == "liste_acceptee"
    assert _admis(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort=None).modele == "factice-codex-1"
    # L'acceptation vaut pour CE relevé seulement : le suivant est de nouveau refusé.
    _avancer(noyau, 120)
    _recevoir(noyau, conn, machine, secours)
    assert _refus(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort=None).code == "liste_de_secours"


def test_catalogue_embarque_sans_compte(noyau, conn):
    def sans_compte(inventaire):
        inventaire["releves"][0]["origine_liste"] = "catalogue_embarque"
        inventaire["connexions"]["codex"] = "non_connecte"
    _poste_et_inventaire(noyau, conn, sans_compte)
    refus = _refus(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort=None)
    assert refus.code == "voie_non_connectee" and refus.message == (
        "Refusé par ACP : Codex n'est pas connecté au compte de l'abonnement sur le poste (non_connecte).")


def test_releve_accepte(noyau, conn):
    _machine, reponse = _poste_et_inventaire(noyau, conn)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.accepter_releve(conn, reponse["releves"]["poste-codex"], "proprietaire:test")
    assert exc.value.code == "releve_non_acceptable"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.accepter_releve(conn, 999999, "proprietaire:test")
    assert exc.value.code == "releve_inconnu"


def test_releve_accepte_plus_le_dernier(noyau, conn):
    def secours(inventaire):
        inventaire["releves"][0]["origine_liste"] = "identique_au_catalogue_embarque"
    machine, premier = _poste_et_inventaire(noyau, conn, secours)
    _avancer(noyau, 120)
    _recevoir(noyau, conn, machine, secours)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.accepter_releve(conn, premier["releves"]["poste-codex"], "proprietaire:test")
    assert exc.value.code == "releve_plus_le_dernier"


def test_interdit_par_le_poste(noyau, conn):
    def politique(inventaire):
        inventaire["politique"]["alias_claude_permis"] = ["opus"]
        inventaire["politique"]["efforts_interdits"] = ["max", "high"]
        inventaire["politique"]["modeles_codex_permis"] = ["factice-codex-2"]
    _poste_et_inventaire(noyau, conn, politique)
    refus = _refus(noyau, conn, voie="poste-claude", modele="opus[1m]", effort=None)
    assert refus.code == "interdit_par_le_poste" and refus.message == (
        "Refusé par ACP : le poste refuse l'alias « opus[1m] » (poste.toml, [politique] alias_claude_permis) ; seule "
        "une modification locale sur le PC peut le lever.")
    assert "l'effort « high »" in _refus(noyau, conn, voie="poste-claude", modele="opus", effort="high").message
    assert "[politique] modeles_codex_permis" in _refus(noyau, conn, voie="poste-codex", modele="factice-codex-1",
                                                        effort=None).message
    # Un interdit du poste ne se lève pas côté Hermes : même avec la phrase de confirmation.
    noyau.routage.poser_politique(conn, efforts_interdits=[], paliers_admis=["default"], motif="essai",
                                  confirmation="J'accepte une dépense hors enveloppe", auteur="proprietaire:test")
    assert _refus(noyau, conn, voie="poste-claude", modele="opus", effort="high").code == "interdit_par_le_poste"


def test_executant_refuse_par_le_poste(noyau, conn):
    _poste_et_inventaire(noyau, conn, lambda i: i["politique"].update(executants=["codex"]))
    refus = _refus(noyau, conn, voie="poste-claude", modele="opus", effort=None)
    assert refus.code == "interdit_par_le_poste" and "l'exécutant Claude Code" in refus.message


def test_cli_hors_version(noyau, conn):
    _poste_et_inventaire(noyau, conn, lambda i: i["versions"].update(
        claude={"lue": "2.1.281", "testee": "2.1.280", "conforme": False}))
    refus = _refus(noyau, conn, voie="poste-claude", modele="opus", effort=None)
    assert refus.code == "cli_hors_version" and refus.message == (
        "Refusé par ACP : Claude Code 2.1.281 n'est pas la version testée par le poste (2.1.280).")


def test_voie_indisponible(noyau, conn):
    """Un relevé en échec REMPLACE le précédent : l'ancien relevé réussi ne reste pas routable."""
    machine, _r = _poste_et_inventaire(noyau, conn)
    assert _admis(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort=None)

    def echec(inventaire):
        codex = inventaire["releves"][0]
        codex.update(etat="cli_absente", origine_liste="aucune", modeles=[], compteurs=[],
                     detail="Codex CLI absent du poste.")
    _avancer(noyau, 120)
    _recevoir(noyau, conn, machine, echec)
    refus = _refus(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort=None)
    assert refus.code == "voie_indisponible" and refus.message.startswith(
        "Refusé par ACP : la voie poste-codex est indisponible sur le poste depuis le ")
    assert refus.message.endswith("(Codex CLI absent du poste.).")


def test_voie_non_connectee(noyau, conn):
    _poste_et_inventaire(noyau, conn, lambda i: i["connexions"].update(codex="cle_api"))
    assert _refus(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort=None).code == "voie_non_connectee"
    _poste = conn.execute("SELECT COUNT(*) FROM inventaires").fetchone()[0]
    assert _poste == 1


def test_claude_jeton_present_non_verifie_admis(noyau, conn):
    _poste_et_inventaire(noyau, conn, lambda i: i["connexions"].update(claude="jeton_present_non_verifie"))
    assert _admis(noyau, conn, voie="poste-claude", modele="opus", effort=None).voie == "poste-claude"


def test_efforts_inconnus_sans_typeerror(noyau, conn):
    def hors_plage(inventaire):
        for modele in inventaire["releves"][1]["modeles"]:
            modele.update(supportedReasoningEfforts=None, defaultReasoningEffort=None)
    _poste_et_inventaire(noyau, conn, hors_plage)
    for effort in (None, "high"):
        refus = _refus(noyau, conn, voie="poste-claude", modele="opus", effort=effort)
        assert refus.code == "efforts_inconnus" and refus.message == (
            "Refusé par ACP : efforts de « opus » inconnus pour Claude Code 2.1.280 (documentation relevée le "
            "26/09/2026).")


def test_validation_tout_ou_rien(noyau, conn):
    _poste_et_inventaire(noyau, conn)
    vue = noyau.routage.vue_routage(conn)
    releves = vue["releves"]
    classes = {"implementation": [{"voie": "poste-codex", "modele": "factice-codex-1", "effort": "medium"}],
               "relecture": [{"voie": "poste-claude", "modele": "opus", "effort": "max"}]}  # max : interdit (Hermes)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.valider_table(conn, releves=releves, classes=classes, auteur="proprietaire:test")
    assert exc.value.code == "table_refusee" and exc.value.refus == [{
        "classe": "relecture", "rang": 0, "code": "effort_interdit",
        "message": "Refusé par ACP : l'effort « max » est interdit par défaut ; seul le propriétaire peut le lever "
                   "(page Routage)."}]
    assert conn.execute("SELECT COUNT(*) FROM routage").fetchone()[0] == 0  # rien d'enregistré
    classes["relecture"][0]["effort"] = "high"
    vue = noyau.routage.valider_table(conn, releves=releves, classes=classes, auteur="proprietaire:test")
    assert vue["classes"]["implementation"]["etat"] == "validee" and vue["classes"]["relecture"]["etat"] == "validee"
    assert conn.execute("SELECT source, valide_par FROM routage WHERE classe = 'implementation'").fetchone()[:] == (
        "proprietaire", "proprietaire:test")
    projet = dict(PROJET, id="p_x")
    resolution = noyau.routage.resoudre(conn, classe="implementation", projet=projet)
    assert (resolution.modele, resolution.effort, resolution.source_routage) == ("factice-codex-1", "medium", "table")


def test_releve_change_409(noyau, conn):
    machine, _r = _poste_et_inventaire(noyau, conn)
    releves = noyau.routage.vue_routage(conn)["releves"]
    _avancer(noyau, 120)
    _recevoir(noyau, conn, machine)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.valider_table(conn, releves=releves, classes={"implementation": [
            {"voie": "poste-codex", "modele": "factice-codex-1"}]}, auteur="proprietaire:test")
    assert exc.value.code == "releve_change" and exc.value.message == (
        "Le relevé a changé depuis l'ouverture de la page : rechargez.")


def test_suggestion_sur_champs_lus(noyau, conn):
    _poste_et_inventaire(noyau, conn)
    suggestion = noyau.routage.suggestion(conn, "implementation")
    assert suggestion["entrees"] == [{"voie": "poste-codex", "modele": "factice-codex-1", "effort": "medium",
                                      "palier": "default"}]
    assert suggestion["remarques"] == ["Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."]
    assert suggestion["libelle"].startswith("Suggestion calculée depuis le relevé du ")
    assert noyau.routage.suggestion(conn, "planification")["entrees"] == [
        {"voie": "hermes", "modele": None, "effort": None, "palier": "default"}]


def test_a_revalider(noyau, conn):
    machine, _r = _poste_et_inventaire(noyau, conn)
    releves = noyau.routage.vue_routage(conn)["releves"]
    noyau.routage.valider_table(conn, releves=releves, classes={"implementation": [
        {"voie": "poste-codex", "modele": "factice-codex-2", "effort": "low"},
        {"voie": "poste-codex", "modele": "factice-codex-1", "effort": "medium"}]}, auteur="proprietaire:test")

    def sans_modele_2(inventaire):
        inventaire["releves"][0]["modeles"] = inventaire["releves"][0]["modeles"][:1]
    _avancer(noyau, 120)
    _recevoir(noyau, conn, machine, sans_modele_2)
    etat = noyau.routage.etat_de_la_table(conn, "implementation")
    assert etat["etat"] == "a_revalider"
    assert [e["admise"] for e in etat["entrees"]] == [False, True] and etat["entrees"][0]["code"] == "modele_absent"
    # La résolution saute l'entrée refusée (jamais remplacée en silence) et prend la suivante, validée.
    resolution = noyau.routage.resoudre(conn, classe="implementation", projet=dict(PROJET, id="p_x"))
    assert resolution.modele == "factice-codex-1"


def test_levee_d_interdit_exige_confirmation(noyau, conn):
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.poser_politique(conn, efforts_interdits=["ultra", "ultracode"], paliers_admis=["default"],
                                      motif="gros travail", confirmation=None, auteur="proprietaire:test")
    assert exc.value.code == "confirmation_requise" and "effort « max » levé" in exc.value.message
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.poser_politique(conn, efforts_interdits=["max", "ultra", "ultracode"],
                                      paliers_admis=["default", "priority"], motif="vite", confirmation="oui",
                                      auteur="proprietaire:test")
    assert "palier « priority » admis" in exc.value.message
    assert noyau.base.reglage(conn, "efforts_interdits") == ["max", "ultra", "ultracode"]  # rien n'a changé
    vue = noyau.routage.poser_politique(conn, efforts_interdits=["ultra", "ultracode"], paliers_admis=["default"],
                                        motif="gros travail", confirmation="J'accepte une dépense hors enveloppe",
                                        auteur="proprietaire:test")
    assert vue["politique_hermes"]["efforts_interdits"] == ["ultra", "ultracode"]
    # Reposer un interdit ne demande aucune confirmation.
    noyau.routage.poser_politique(conn, efforts_interdits=["max", "ultra", "ultracode"], paliers_admis=["default"],
                                  motif="retour", confirmation=None, auteur="proprietaire:test")
    assert noyau.base.reglage(conn, "efforts_interdits") == ["max", "ultra", "ultracode"]


def test_surcharge_globale(noyau, conn):
    _poste_et_inventaire(noyau, conn)
    creee = noyau.routage.creer_surcharge_globale(conn, classe="implementation", voie="poste-codex",
                                                  modele="factice-codex-2", effort="low", motif="essai",
                                                  auteur="proprietaire:test")
    resolution = noyau.routage.resoudre(conn, classe="implementation", projet=dict(PROJET, id="p_x"))
    assert (resolution.modele, resolution.source_routage) == ("factice-codex-2", "surcharge_globale")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.creer_surcharge_globale(conn, classe="implementation", voie="poste-codex", modele="inexistant",
                                              motif="essai", auteur="proprietaire:test")
    assert exc.value.code == "modele_absent"
    assert [s["id"] for s in noyau.routage.desactiver_surcharge(conn, creee["surcharge"],
                                                                "proprietaire:test")["surcharges"]] == []
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.routage.desactiver_surcharge(conn, creee["surcharge"], "proprietaire:test")
    assert exc.value.code == "surcharge_inconnue"


def test_releves_factices_de_p4_gardent_leur_routage(noyau, conn):
    """Sans inventaire (relevé factice de P4) : ni connexion, ni version, ni politique du poste à vérifier."""
    noyau.routage.enregistrer_releve(conn, releve_factice("poste-codex"))
    assert _admis(noyau, conn, voie="poste-codex", modele="factice-codex-1", effort="extreme").effort == "extreme"
    assert noyau.routage.badge(conn, "poste-codex") == "releve_factice"


def test_vue_des_quotas(noyau, conn):
    vue = noyau.quotas.vue(conn)
    assert vue["poste-codex"]["etat"] == "inconnu" and vue["hermes"] == {"etat": "inconnu", "libelle": "Inconnu"}
    machine, _r = _poste_et_inventaire(noyau, conn, lambda i: i["poste"].update(hermes_meme_enveloppe_que_codex=True))
    vue = noyau.quotas.vue(conn)
    codex = vue["poste-codex"]
    assert codex["etat"] == "releve" and codex["seuil_pct"] == 90 and codex["resume"]["pourcentage_utilise"] == 41.0
    [compteur] = codex["compteurs"]
    assert compteur["worker_id"] == machine and compteur["worker_name"] == "Poste Windows"
    assert [f["remaining_percent"] for f in compteur["windows"]] == [59, 88] and compteur["stale"] is False
    assert vue["poste-claude"]["compteurs"] == [] and vue["poste-claude"]["source_libelle"].startswith("Ligne d'état")
    assert vue["hermes"]["etat"] == "meme_enveloppe_que_codex"
    _avancer(noyau, 7201)
    vue = noyau.quotas.vue(conn)
    assert vue["poste-codex"]["etat"] == "perime" and vue["poste-codex"]["compteurs"][0]["stale"] is True


def _compteur_claude(observe, *, utilise=95):
    return {"provider": "claude_code", "status": "ok", "source": "claude_code_statusline", "plan": None,
            "limit_id": "default", "windows": [{"key": "five_hour", "used_percent": utilise, "window_minutes": 300,
                                                "resets_at": (observe + _dt.timedelta(hours=3)).strftime(_FORMAT)}],
            "credits": None, "limit_reached": False, "reached_type": None, "observed_at": observe.strftime(_FORMAT),
            "detail": None}


def test_ligne_d_etat_claude_ancienne_dans_un_releve_frais_est_perimee(noyau, conn):
    """Relecture de P5 : un relevé FRAIS du poste peut recopier une ligne d'état Claude Code vieille de deux jours
    (les sessions du propriétaire n'ont pas tourné). L'état et ``stale`` se calculaient sur la date du relevé : la
    page montrait « Relevé », 95 % utilisés et une remise à zéro passée comme actuels. ``stale`` suit désormais
    ``observed_at`` de chaque compteur (contrat SubscriptionQuotaView) ; la voie est « perime » quand tous ses
    compteurs le sont."""
    maintenant = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    ancien = maintenant - _dt.timedelta(days=2)

    def claude_ancien(inventaire):
        [releve] = [r for r in inventaire["releves"] if r["voie"] == "poste-claude"]
        releve["compteurs"] = [_compteur_claude(ancien)]

    _poste_et_inventaire(noyau, conn, claude_ancien)
    vue = noyau.quotas.vue(conn)
    claude, codex = vue["poste-claude"], vue["poste-codex"]
    assert maintenant.timestamp() - claude["releve_le"] < 120  # le relevé lui-même est frais
    assert claude["etat"] == "perime" and [c["stale"] for c in claude["compteurs"]] == [True]
    assert claude["compteurs"][0]["windows"][0]["used_percent"] == 95  # la valeur reste lisible, datée
    assert codex["etat"] == "releve" and [c["stale"] for c in codex["compteurs"]] == [False]


def test_compteurs_de_fraicheurs_differentes(noyau, conn):
    """Un compteur périmé et un compteur frais dans le même relevé : chacun garde sa fraîcheur ; la voie reste
    « releve » tant qu'un compteur est frais."""
    maintenant = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)

    def deux_compteurs(inventaire):
        [releve] = [r for r in inventaire["releves"] if r["voie"] == "poste-claude"]
        releve["compteurs"] = [_compteur_claude(maintenant - _dt.timedelta(hours=3)),
                               dict(_compteur_claude(maintenant - _dt.timedelta(minutes=5), utilise=10),
                                    limit_id="autre")]

    _poste_et_inventaire(noyau, conn, deux_compteurs)
    claude = noyau.quotas.vue(conn)["poste-claude"]
    assert claude["etat"] == "releve" and [c["stale"] for c in claude["compteurs"]] == [True, False]
