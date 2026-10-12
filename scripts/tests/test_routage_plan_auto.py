"""Routage Auto réel sur SQLite en mémoire ; seul l'adaptateur Hermes externe est remplacé.

Complète les tests d'image : les validations du contrat, la politique, les quotas, les tables,
les surcharges et la composition du graphe sont celles du code livré. Aucun service ni compte.
"""
from __future__ import annotations

import importlib
import importlib.util
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

NOYAU = Path(__file__).resolve().parents[2] / "hermes/plugins/acp-poste/noyau"
NOM = "_noyau_routage_plan_tests"
spec = importlib.util.spec_from_file_location(NOM, NOYAU / "__init__.py", submodule_search_locations=[str(NOYAU)])
assert spec and spec.loader
paquet = importlib.util.module_from_spec(spec)
sys.modules[NOM] = paquet
spec.loader.exec_module(paquet)
ka = ModuleType(NOM + ".kanban_adapter")
ka.VOIES_POSTE = ("poste-codex", "poste-claude")
ka.VOIE_INTEGRATION = "poste-integration"
ka.VOIES_EXECUTION = (*ka.VOIES_POSTE, ka.VOIE_INTEGRATION)
ka.PREFIXE_CLE = "acp:"
ka.VALID_REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
ka.effort_hermes = lambda valeur: valeur if valeur in ka.VALID_REASONING_EFFORTS else None
ka.masquer = lambda texte: texte
sys.modules[ka.__name__] = ka
r = importlib.import_module(NOM + ".routage")
g = importlib.import_module(NOM + ".graphe")
PROJET = {"id": "p_plan", "titre": "Projet jetable", "depot_alias": "jetable", "tableau": "jetable",
          "profil": "base", "objectif": "Vérifier le routage"}


def releve(voie, quota=None):
    suffixe = voie.removeprefix("poste-")
    return {"voie": voie, "source": "releve_factice", "version_cli": "0.0.0-factice",
            "releve_le": datetime.now(timezone.utc).isoformat(), "depots": [{"alias": "jetable"}],
            "modeles": [{"id": f"factice-{suffixe}-1", "isDefault": True,
                         "supportedReasoningEfforts": ["low", "medium", "high"], "defaultReasoningEffort": "medium"},
                        {"id": f"factice-{suffixe}-2", "isDefault": False,
                         "supportedReasoningEfforts": ["low"], "defaultReasoningEffort": "low"}],
            "quotas": {"pourcentage_utilise": quota} if quota is not None else None}


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.row_factory = sqlite3.Row
    r.base.migrer(db)
    for voie in ka.VOIES_POSTE:
        r.enregistrer_releve(db, releve(voie))
    yield db
    db.close()


def table(conn, classe="implementation", entrees=None):
    if entrees is None:
        entrees = [{"voie": "poste-codex", "modele": "factice-codex-1", "effort": "medium"},
                   {"voie": "poste-claude", "modele": "factice-claude-1", "effort": "low"}]
    r.enregistrer_routage(conn, classe, entrees, source="releve_factice", valide_par="proprietaire:test")


def resoudre(conn, **kw):
    return r.resoudre(conn, classe="implementation", projet=PROJET, preference_plan=True, **kw)


def surcharge(conn, classe="implementation", voie="poste-codex", modele="factice-codex-1", effort="medium"):
    conn.execute("INSERT INTO surcharges (portee, cible, classe, voie, modele, effort, motif, auteur, cree_le) "
                 "VALUES ('projet', ?, ?, ?, ?, ?, 'essai', 'proprietaire:test', 0)",
                 (PROJET["id"], classe, voie, modele, effort))


@pytest.mark.parametrize("hints", [
    {"modele": "modele-invente"}, {"voie": "voie-inventee"}, {"effort": "max"},
    {"voie": "poste-codex", "modele": "factice-codex-2", "effort": "high"},
])
def test_hints_n_ajoutent_pas_de_candidat(conn, hints):
    table(conn, entrees=[{"voie": "poste-claude", "modele": "factice-claude-1", "effort": "low"}])
    resolution = resoudre(conn, **hints)
    assert (resolution.voie, resolution.modele, resolution.effort, resolution.source_routage) == (
        "poste-claude", "factice-claude-1", "low", "table")


def test_hints_departagent_candidats_valides_sans_modifier_table(conn):
    table(conn)
    avant = r.entrees_routage(conn, "implementation")
    assert resoudre(conn).voie == "poste-codex"
    assert resoudre(conn, modele="factice-claude-1").voie == "poste-claude"
    assert r.entrees_routage(conn, "implementation") == avant


def test_quota_exclut_candidat_prefere_et_interdit_repli_hors_table(conn):
    table(conn)
    r.enregistrer_releve(conn, releve("poste-codex", quota=99))
    assert resoudre(conn, voie="poste-codex").voie == "poste-claude"
    table(conn, entrees=[{"voie": "poste-codex", "modele": "factice-codex-1"}])
    with pytest.raises(r.RefusACP, match="quota à 99"):
        resoudre(conn, voie="poste-claude", modele="factice-claude-1")


def test_politique_revalidee_avant_preferences(conn):
    table(conn)
    r.base.poser_reglage(conn, "efforts_interdits", ["medium"], "proprietaire:test")
    assert resoudre(conn, voie="poste-codex", effort="medium").voie == "poste-claude"


def test_surcharge_owner_non_repliable_et_appel_manuel_intact(conn):
    table(conn)
    # Le propriétaire conserve son choix explicite, même hors table.
    assert r.resoudre(conn, classe="implementation", projet=PROJET, modele="factice-codex-2").modele == "factice-codex-2"
    surcharge(conn)
    assert resoudre(conn, voie="poste-claude").source_routage == "surcharge_projet"
    r.enregistrer_releve(conn, releve("poste-codex", quota=100))
    with pytest.raises(r.RefusACP, match="quota à 100"):
        resoudre(conn, voie="poste-claude")


def test_table_absente_non_remplacee_par_releve_ou_plan(conn):
    with pytest.raises(r.RefusACP, match="aucune entrée autorisée"):
        resoudre(conn, voie="poste-codex", modele="factice-codex-1")


def relire(conn, **kw):
    return r.resoudre_relecture(conn, projet=PROJET, voie_relue="poste-codex", modele_relu="factice-codex-1",
                                ref="e1", preference_plan=True, **kw)


def test_relecture_croisee_sans_defaut_hors_table(conn):
    table(conn, "relecture", [{"voie": "poste-codex", "modele": "factice-codex-2"}])
    with pytest.raises(r.RefusACP, match="aucune entrée autorisée"):
        relire(conn, modele="factice-claude-1")
    table(conn, "relecture", [{"voie": "poste-claude", "modele": "factice-claude-1", "effort": "low"}])
    assert relire(conn, modele="invente").voie == "poste-claude"
    surcharge(conn, classe="relecture", voie="poste-codex", modele="factice-codex-2", effort="low")
    with pytest.raises(r.RefusACP, match="surcharge du propriétaire"):
        relire(conn)


def test_relecture_quota_ne_permet_pas_meme_voie(conn):
    table(conn, "relecture")
    r.enregistrer_releve(conn, releve("poste-claude", quota=100))
    with pytest.raises(r.RefusACP, match="quota à 100"):
        relire(conn)


def test_repli_d91_modele_different_apres_resolution_et_owner_verrouille(conn, monkeypatch):
    monkeypatch.setattr(r, "voies_fermees", lambda *a, **kw: {"poste-claude": "fermée par politique"})
    table(conn, "relecture", [{"voie": "poste-codex", "modele": None},
                              {"voie": "poste-codex", "modele": "factice-codex-2", "effort": "low"}])
    resolution = relire(conn, modele="factice-codex-1")
    assert resolution.modele == "factice-codex-2" and "D91" in resolution.mention
    surcharge(conn, classe="relecture")
    with pytest.raises(r.RefusACP, match="celui de l'implémentation"):
        relire(conn, modele="factice-codex-2")


def test_graphe_utilise_preferences_et_garde_synthese(conn):
    table(conn)
    table(conn, "relecture", [{"voie": "poste-claude", "modele": "factice-claude-1", "effort": "low"}])
    plan = g.valider_plan("Essai", [], [{"ref": "e1", "titre": "Coder", "classe": "implementation",
                                       "consigne": "Modifier le dépôt", "modele": "invente",
                                       "relecture_modele": "autre-invente"}], maximum=10)
    demandes = g.composer(conn, PROJET, 1, plan)
    assert [(d["role"], d["voie"], d["source_routage"]) for d in demandes] == [
        ("implementation", "poste-codex", "table"), ("relecture", "poste-claude", "table"),
        ("synthese", "hermes", "profil")]
    assert demandes[1]["parents"] == [demandes[0]["cle"]]
    assert demandes[2]["parents"] == [d["cle"] for d in demandes[:2]]


def test_surcharge_inconnue_ou_fermee_n_est_pas_une_preference(conn, monkeypatch):
    table(conn)
    surcharge(conn, modele="invente")
    with pytest.raises(r.RefusACP, match="ne figure pas"):
        resoudre(conn, modele="factice-claude-1")
    conn.execute("UPDATE surcharges SET modele = 'factice-codex-1'")
    monkeypatch.setattr(r, "voies_fermees", lambda *a, **kw: {"poste-codex": "fermée"})
    with pytest.raises(r.RefusACP, match="fermée"):
        resoudre(conn, voie="poste-claude")


def test_repli_d91_desactive_ne_peut_pas_etre_reactive_par_plan(conn, monkeypatch):
    table(conn, "relecture", [{"voie": "poste-codex", "modele": "factice-codex-2"},
                              {"voie": "poste-claude", "modele": "factice-claude-1"}])
    monkeypatch.setattr(r, "voies_fermees", lambda *a, **kw: {"poste-claude": "fermée"})
    r.base.poser_reglage(conn, "relecture_repli_meme_voie", False, "proprietaire:test")
    with pytest.raises(r.RefusACP, match="fermée"):
        relire(conn, modele="factice-codex-2")


def test_hints_hermes_ne_changent_pas_son_profil(conn):
    resolution = r.resoudre(conn, classe="recherche_web", projet=PROJET, preference_plan=True,
                            voie="poste-codex", modele="modele-invente", effort="max")
    assert (resolution.voie, resolution.modele, resolution.effort, resolution.source_routage) == (
        "hermes", None, None, "profil")
