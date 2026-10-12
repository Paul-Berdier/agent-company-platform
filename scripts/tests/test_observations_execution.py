"""Projection d'exécution pure : contrat partagé réel, sans serveur ni base Hermes de production."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_NOYAU = Path(__file__).resolve().parents[2] / "hermes/plugins/acp-poste/noyau"
_PAQUET = importlib.util.spec_from_file_location("_noyau_observations_tests", _NOYAU / "__init__.py",
                                               submodule_search_locations=[str(_NOYAU)])
assert _PAQUET is not None and _PAQUET.loader is not None
_paquet = importlib.util.module_from_spec(_PAQUET)
sys.modules[_PAQUET.name] = _paquet
_PAQUET.loader.exec_module(_paquet)
_SPEC = importlib.util.spec_from_file_location(_PAQUET.name + ".observations", _NOYAU / "observations.py")
assert _SPEC is not None and _SPEC.loader is not None
observation = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(observation)

DEMANDE = {"carte": "t_abcd", "cle": "acp:p_test:t0:e1", "voie": "poste-codex", "role": "implementation"}


def tache(**kw):
    return SimpleNamespace(**dict({"id": "t_abcd", "created_by": "acp-poste", "idempotency_key": DEMANDE["cle"],
                                  "current_run_id": None, "status": "done", "claim_lock": None}, **kw))


def run(**kw):
    return SimpleNamespace(**dict({"id": 1, "task_id": "t_abcd", "profile": "poste-codex", "status": "done",
                                  "claim_lock": "acp-poste:m0123456789a", "started_at": 100, "ended_at": 105,
                                  "outcome": "completed", "metadata": {"branche": "hermes/t_abcd", "tete": "2" * 40,
                                  "verification": {"etat": "reussie", "code": 0, "tentatives": 1},
                                  "diffstat": {"fichiers": 1, "ajouts": 2, "retraits": 0},
                                  "jetons": {"entree": 0, "sortie": 12, "cache": None}}}, **kw))


def lire(t=None, runs=None, demande=None, masque=lambda s: s):
    return observation.construire(demande or DEMANDE, t or tache(), [run()] if runs is None else runs, masque)


def test_run_ferme_conserve_provenance_et_vrais_zeros():
    v = lire()
    assert (v["etat"], v["portee"], v["provenance"], v["run_id"], v["machine_id"]) == (
        "observe", "derniere", "hermes.task_runs", 1, "m0123456789a")
    assert v["metadonnees"]["verification"] == {"etat": "reussie", "code": 0, "tentatives": 1}
    assert v["metadonnees"]["jetons"] == {"entree": 0, "sortie": 12, "cache": None}
    assert "modele_servi" not in v["metadonnees"] and "session_locale" not in v["metadonnees"]


def test_nouvelle_tentative_ne_reprend_ni_resultat_ni_machine_ancienne():
    active = run(id=2, started_at=110, ended_at=None, status="running", outcome=None,
                 claim_lock="acp-poste:m11111111111", metadata=None)
    v = lire(tache(current_run_id=2, status="running", claim_lock=active.claim_lock), [run(), active],
             demande=dict(DEMANDE, machine_id="m0123456789a", tete="2" * 40, verification='{"etat":"reussie"}'))
    assert v["run_id"] == 2 and v["portee"] == "courante" and v["machine_id"] == "m11111111111"
    assert v["metadonnees"] is None and v["motif_metadonnees"] == "absentes"


def test_derniere_tentative_sans_resultat_ne_reprend_pas_precedente():
    v = lire(runs=[run(), run(id=2, started_at=110, ended_at=120, status="reclaimed", outcome="reclaimed", metadata=None)])
    assert v["run_id"] == 2 and v["metadonnees"] is None


@pytest.mark.parametrize("t,rs", [
    (tache(current_run_id=2), [run()]),
    (tache(current_run_id=1), [run()]),
    (tache(current_run_id=1, status="running", claim_lock="autre"), [run(ended_at=None)]),
    (tache(), [run(ended_at=None)]),
    (tache(), [run(task_id="t_dcba")]),
    (tache(), [run(claim_lock="hermes:123")]),
    (tache(), [run(profile="poste-claude")]),
    (tache(), [run(ended_at=99)]),
    (tache(), [run(id=True)]),
    (tache(created_by="autre"), [run()]),
    (tache(idempotency_key="autre"), [run()]),
])
def test_rattachement_incoherent_ne_fuit_aucun_resultat(t, rs):
    v = lire(t, rs)
    assert v == observation.vide()


def test_absence_et_voie_non_prise_en_charge_sont_distinguees():
    assert lire(runs=[])["etat"] == "aucune"
    assert lire(demande=dict(DEMANDE, voie="hermes"))["etat"] == "non_pris_en_charge"


@pytest.mark.parametrize("meta", ["secret", {"branche": "hermes/t_dcba"}, {"branche": "hermes/t_abcd", "jetons": {"entree": -1}},
                                  {"branche": "hermes/t_abcd", "verification": {"etat": "reussie", "code": True}},
                                  {"branche": "hermes/t_abcd", "verification": {"etat": "invente"}}])
def test_metadata_invalide_n_est_pas_restituee(meta):
    v = lire(runs=[run(metadata=meta)])
    assert v["etat"] == "observe" and v["metadonnees"] is None and v["motif_metadonnees"] == "invalides"


def test_allowlist_et_masquage_recursif():
    meta = dict(run().metadata, raw_stdout="secret", artifacts=[{"content": "secret"}],
                verification={"etat": "echouee", "raison": "secret"},
                pilotage={"touche": True, "chemins": ["secret"]})
    v = lire(runs=[run(metadata=meta)], masque=lambda s: s.replace("secret", "[masqué]"))
    assert "secret" not in json.dumps(v, ensure_ascii=False)
    assert "raw_stdout" not in v["metadonnees"] and "artifacts" not in v["metadonnees"]
    assert v["metadonnees"]["pilotage"]["chemins"] == ["[masqué]"]


def test_panne_masquage_ferme_la_projection():
    def panne(_):
        raise RuntimeError("indisponible")
    assert lire(masque=panne)["metadonnees"] is None


def test_integration_accepte_sa_branche_projet_sans_inventer_modele():
    v = lire(demande=dict(DEMANDE, voie="poste-integration", role="integration"),
             runs=[run(profile="poste-integration", metadata={"branche": "hermes/projet-demo"})])
    assert v["metadonnees"] == {"branche": "hermes/projet-demo"}


def test_attente_planifiee_conserve_le_statut_reel_sans_resultat_reussi():
    v = lire(t=tache(status="scheduled"),
             runs=[run(status="scheduled", outcome="scheduled", metadata=None)])
    assert (v["etat"], v["portee"], v["statut"], v["issue"]) == ("observe", "derniere", "scheduled", "scheduled")
    assert v["metadonnees"] is None and v["fin"] == 105


@pytest.fixture
def lecture_projet(monkeypatch):
    # Vrai module projets et vraie projection ; seul l'adaptateur externe Hermes est remplacé.
    import importlib
    from types import ModuleType

    ka = ModuleType(_PAQUET.name + ".kanban_adapter")
    ka.VOIES_POSTE = ("poste-codex", "poste-claude")
    ka.VOIE_INTEGRATION = "poste-integration"
    ka.VOIES_EXECUTION = (*ka.VOIES_POSTE, ka.VOIE_INTEGRATION)
    ka.masquer = lambda texte: texte
    monkeypatch.setitem(sys.modules, ka.__name__, ka)
    projets = importlib.import_module(_PAQUET.name + ".projets")
    monkeypatch.setattr(projets, "ka", ka)
    return projets, ka


@pytest.mark.parametrize("active", [False, True])
def test_lecture_projet_selectionne_une_seule_tentative(lecture_projet, active):
    projets, ka = lecture_projet
    appels = []
    selection = run(id=500, started_at=200, ended_at=None if active else 205,
                    status="running" if active else "done", metadata=None)
    carte = tache(current_run_id=500 if active else None, status=selection.status,
                  claim_lock=selection.claim_lock if active else None)
    ka.get_run = lambda conn, identifiant: appels.append(("courante", identifiant)) or selection
    ka.latest_run = lambda conn, identifiant: appels.append(("derniere", identifiant)) or selection
    # Pas de list_runs sur cet adaptateur : une lecture de tout l'historique échouerait.
    v = projets._execution(object(), DEMANDE, carte)
    assert v["run_id"] == 500
    assert appels == [("courante", 500) if active else ("derniere", "t_abcd")]


@pytest.mark.parametrize("selection", [None, run(id=2), run(task_id="t_dcba")])
def test_pointeur_courant_incoherent_ne_se_replie_pas(lecture_projet, selection):
    projets, ka = lecture_projet
    appels = []
    ka.get_run = lambda conn, identifiant: appels.append(("courante", identifiant)) or selection
    ka.latest_run = lambda conn, identifiant: appels.append(("interdit", identifiant)) or run()
    v = projets._execution(object(), DEMANDE, tache(current_run_id=1, status="running",
                                                   claim_lock="acp-poste:m0123456789a"))
    assert v == observation.vide()
    assert appels == [("courante", 1)]


def test_lecture_projet_sans_tentative_distingue_absence_et_panne(lecture_projet):
    projets, ka = lecture_projet
    ka.latest_run = lambda conn, identifiant: None
    assert projets._execution(object(), DEMANDE, tache())["etat"] == "aucune"

    def panne(*args):
        raise RuntimeError("lecture impossible")
    ka.latest_run = panne
    assert projets._execution(object(), DEMANDE, tache())["etat"] == "indisponible"
