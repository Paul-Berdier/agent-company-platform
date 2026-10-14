"""Applications réelles du catalogue : sélection, intégrité, bornes et consignes du graphe."""
from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
import sqlite3
from contextlib import nullcontext
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

RACINE = Path(__file__).resolve().parents[2]
NOYAU = RACINE / "hermes/plugins/acp-poste/noyau"
NOM = "_noyau_competences_poste_tests"
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
cp = importlib.import_module(NOM + ".competences_poste")
g = importlib.import_module(NOM + ".graphe")
RefusACP = importlib.import_module(NOM + ".textes").RefusACP


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    shutil.copytree(RACINE / "hermes/skills", tmp_path / "skills")
    shutil.copy2(RACINE / "hermes/catalogue/catalogue.lock.json", tmp_path / "catalogue.lock.json")
    monkeypatch.setattr(cp, "VERROU", tmp_path / "catalogue.lock.json")
    monkeypatch.setattr(cp, "SKILLS", tmp_path / "skills")
    return tmp_path


def appel(texte="Corriger le comportement demandé.", **options):
    args = dict(profil="web", classe="implementation", role="implementation", voie="poste-codex")
    args.update(options)
    return cp.appliquer(texte, **args)


def modifier(catalogue, changement):
    p = catalogue / "catalogue.lock.json"
    v = json.loads(p.read_text(encoding="utf-8"))
    changement(v)
    p.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("voie", ["poste-codex", "poste-claude"])
def test_web_recoit_les_applications_sources_reelles(catalogue, voie):
    texte = appel(voie=voie)
    assert texte.startswith("Corriger le comportement demandé.\n")
    for nom in ("incremental-implementation", "addy-test-driven-development", "frontend-ui-engineering", "ponytail"):
        assert f"## Compétence {nom}\n" in texte
    assert "a06bc63b3f8b829c14b0bbf53d99fefc39d58092" in texte
    assert "9b58c1ffb790c075ca32e70a89cf1d80588f4abf" in texte
    assert "## Compétence ponytail-review\n" not in texte
    assert len(texte) < 8000


def test_profil_et_role_selectionnent_sans_tout_injecter(catalogue):
    assert "frontend-ui-engineering" not in appel(profil="donnees")
    assert appel(profil="recherche") == "Corriger le comportement demandé."
    revue = appel(classe="relecture", role="relecture")
    for nom in ("code-review-and-quality", "ponytail-review", "ponytail-audit"):
        assert f"## Compétence {nom}\n" in revue
    assert "Ne modifiez aucun fichier" in revue
    correction = appel(classe="debogage_tests", role="correction")
    assert "debugging-and-error-recovery" in correction
    assert "frontend-ui-engineering" not in correction


@pytest.mark.parametrize("options", [{"profil": "base"}, {"voie": "hermes"}, {"voie": "poste-integration"}])
def test_aucune_application_implicite_hors_poste(options, monkeypatch, tmp_path):
    monkeypatch.setattr(cp, "VERROU", tmp_path / "absent.json")
    assert appel(**options) == "Corriger le comportement demandé."


def test_catalogue_absent_refuse_ferme(monkeypatch, tmp_path):
    monkeypatch.setattr(cp, "VERROU", tmp_path / "absent.json")
    with pytest.raises(RefusACP, match="Compétences du poste indisponibles"):
        appel()


@pytest.mark.parametrize("alteration", ["absent", "modifie"])
def test_application_absente_ou_modifiee_refuse(catalogue, alteration):
    p = catalogue / "skills/ponytail/ponytail/POSTE.md"
    if alteration == "absent":
        p.unlink()
    else:
        p.write_bytes(p.read_bytes() + b"modification")
    with pytest.raises(RefusACP, match="configuration absente, invalide ou modifiée"):
        appel()


def test_chemin_manipule_ne_lit_pas_hors_catalogue(catalogue):
    modifier(catalogue, lambda v: next(s for s in v["skills"] if s["nom"] == "ponytail").update(chemin="../secret"))
    with pytest.raises(RefusACP):
        appel()


def test_application_desactivee_dans_profil_ne_sapplique_pas(catalogue):
    modifier(catalogue, lambda v: v["profils"]["web"].update(skills_poste=[]))
    assert appel() == "Corriger le comportement demandé."


def test_debordement_refuse_sans_tronquer(catalogue):
    with pytest.raises(RefusACP, match="dépassent la limite"):
        appel("consigne " * 1770)


def test_graphe_et_corrections_partagent_la_consigne_visible(catalogue):
    demandes = [dict(role=role, classe=classe, voie=voie, consigne="Consigne exacte.", corps="Carte initiale.")
                for role, classe, voie in [("implementation", "implementation", "poste-codex"),
                                          ("correction", "debogage_tests", "poste-claude"),
                                          ("relecture", "relecture", "poste-claude"),
                                          ("hermes", "documentation", "hermes"),
                                          ("integration", "integration", "poste-integration")]]
    g._appliquer_competences_poste({"profil": "web"}, demandes)
    for d in demandes[:3]:
        assert "# Applications ACP du profil web" in d["consigne"]
        assert d["corps"] == "Carte initiale." + d["consigne"][len("Consigne exacte."):]
    assert all(d["consigne"] == "Consigne exacte." for d in demandes[3:])


def test_boucle_chef_chargee_aux_deux_roles_hermes():
    assert "acp-boucle-chef" in g.projets.COMPETENCES_PLANIFICATION
    assert "acp-boucle-chef" in g.projets.COMPETENCES_SYNTHESE
    v = json.loads((RACINE / "hermes/catalogue/catalogue.lock.json").read_text(encoding="utf-8"))
    chef = next(s for s in v["skills"] if s["nom"] == "acp-boucle-chef")
    assert chef["execution"] == "aucune"
    assert (RACINE / "hermes/skills" / chef["chemin"] / "SKILL.md").is_file()


def test_composition_reelle_du_graphe_injecte_avant_reservation(catalogue, monkeypatch):
    def route(voie):
        return SimpleNamespace(voie=voie, modele="modele-test", effort="medium", palier="default",
                               effort_carte="medium", source_routage="test", releve_id=None, mention=None)
    monkeypatch.setattr(g.routage, "resoudre", lambda *a, **kw: route("poste-codex"))
    monkeypatch.setattr(g.routage, "resoudre_relecture", lambda *a, **kw: route("poste-claude"))
    fiche = dict(id="p-test", tableau="test", titre="Test", depot_alias="jetable", profil="web", objectif="Test")
    plan = g.valider_plan("Un comportement vérifié", [], [dict(ref="fix", titre="Corriger", classe="implementation",
                                                              consigne="Corriger le défaut reproduit.")], maximum=12)
    demandes = g.composer(None, fiche, 1, plan)
    assert [d["role"] for d in demandes] == ["implementation", "relecture", "synthese"]
    assert "## Compétence incremental-implementation" in demandes[0]["consigne"]
    assert "## Compétence code-review-and-quality" in demandes[1]["consigne"]
    assert demandes[2]["consigne"] == "Un comportement vérifié"
    (catalogue / "skills/ponytail/ponytail/POSTE.md").unlink()
    with pytest.raises(RefusACP):
        g.composer(None, fiche, 1, plan)


def test_reprise_correction_reservee_ne_relit_pas_le_catalogue(catalogue, monkeypatch):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.row_factory = sqlite3.Row
    g.base.migrer(db)
    db.execute("INSERT INTO projets (id, tableau, titre, objectif, profil, depot_alias, reponses, etat, tour, "
               "plafond_tours, plafond_cartes, plafond_corrections, cartes_creees, origine, auteur, cree_le, maj_le) "
               "VALUES ('p-reprise', 'jetable', 'Reprise', 'Tester la reprise', 'web', 'depot', 'proprietaire', "
               "'actif', 1, 3, 30, 2, 3, 'tableau_de_bord', 'test', 0, 0)")
    commun = dict(projet_id="p-reprise", tableau="jetable", tour=1, ref="fix", depot_alias="depot",
                  source_routage="table", consigne="Consigne initiale.", corps="Carte initiale.",
                  modele="modele-test", effort="medium", palier="default")
    g.cartes.reserver(db, [dict(commun, cle="impl", role="implementation", classe="implementation", voie="poste-codex"),
                          dict(commun, cle="rel", role="relecture", classe="relecture", voie="poste-claude"),
                          dict(commun, cle="synth", role="synthese", classe="synthese", voie="hermes")])
    db.execute("UPDATE demandes SET carte = cle")
    # Première tentative : réservation réelle, puis coupure avant de créer les cartes kanban.
    def couper(*args, **kwargs):
        raise RuntimeError("coupure après réservation")
    monkeypatch.setattr(g.cartes, "creer", couper)
    with pytest.raises(RuntimeError, match="coupure après réservation"):
        g.inserer_correction(db, tableau="jetable", carte_relecture="rel", run_id_relecture=5,
                            consigne="Corriger le défaut prouvé.")
    avant = [(r["cle"], r["consigne"], r["corps"]) for r in db.execute(
        "SELECT * FROM demandes WHERE correction_n = 1 OR carte_relue LIKE 'acp:%'")]
    assert len(avant) == 2 and all("# Applications ACP du profil web" in r[1] for r in avant)
    (catalogue / "catalogue.lock.json").unlink()
    def creer(conn, fiche, demandes):
        ids = {}
        for d in demandes:
            ids[d["cle"]] = "carte-" + d["role"]
            conn.execute("UPDATE demandes SET carte = ? WHERE cle = ?", (ids[d["cle"]], d["cle"]))
        return ids
    liens, fins = [], []
    monkeypatch.setattr(g.cartes, "creer", creer)
    monkeypatch.setattr(ka, "connexion", lambda tableau: nullcontext(None), raising=False)
    monkeypatch.setattr(ka, "link_tasks", lambda kc, enfant, parent: liens.append((enfant, parent)), raising=False)
    def finir(kc, carte, **kw):
        fins.append((carte, kw)); return True
    monkeypatch.setattr(ka, "complete_task", finir, raising=False)
    resultat = g.inserer_correction(db, tableau="jetable", carte_relecture="rel", run_id_relecture=5,
                                   consigne="Corriger le défaut prouvé.")
    apres = [(r["cle"], r["consigne"], r["corps"]) for r in db.execute(
        "SELECT * FROM demandes WHERE correction_n = 1 OR carte_relue LIKE 'acp:%'")]
    assert avant == apres
    assert resultat["relecture_terminee"] is True
    assert liens == [("carte-correction", "synth"), ("carte-relecture", "synth")]
    assert fins[0][0] == "rel" and fins[0][1]["expected_run_id"] == 5
    assert db.execute("SELECT count(*) FROM demandes").fetchone()[0] == 5
    db.close()
