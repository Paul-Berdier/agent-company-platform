"""Protocole acp-machine/1, ajouts de l'étape P6 (cahier P6 § 5) : carte servie par ``reclamer``, six routes de
l'exécution, bornes de 8, 32 et 64 Kio, balayage des secrets, refus en français. Les exemples
(hermes/tests/outils/fixtures_machine/*) sont relus par les tests du greffon dans l'image et par le faux exécutant."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from acp_poste_contrat import machine as m

FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "outils" / "fixtures_machine"


def _fixture(nom: str) -> dict:
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


def _carte(**modifs) -> dict:
    carte = copy.deepcopy(_fixture("reclamer_reponse_carte.json")["carte"])
    carte.update(modifs)
    return carte


def _refus(modele, donnees) -> str:
    with pytest.raises(ValueError) as exc:
        m.valider(modele, donnees, quoi="Refusé")
    return str(exc.value)


# ------------------------------------------------------------------ exemples


@pytest.mark.parametrize("fichier, modele", [
    ("reclamer_requete_p6.json", "RequeteReclamer"),
    ("reclamer_reponse_carte.json", "ReponseReclamer"),
    ("battement_requete.json", "RequeteBattement"),
    ("battement_reponse.json", "ReponseBattement"),
    ("terminer_requete.json", "RequeteTerminer"),
    ("terminer_reponse.json", "ReponseTerminer"),
    ("question_requete.json", "RequeteQuestion"),
    ("question_reponse.json", "ReponseQuestion"),
    ("bloquer_requete.json", "RequeteBloquer"),
    ("bloquer_reponse.json", "ReponseBloquer"),
    ("reprendre_requete.json", "RequeteReprendre"),
    ("arret_requete.json", "RequeteArret"),
    ("reprise_reponse.json", "ReponseReprise"),
    ("erreur_reclamation_perdue.json", "ErreurMachine"),
])
def test_exemples_p6_valides(fichier, modele):
    m.valider(getattr(m, modele), _fixture(fichier), quoi="Exemple refusé")


def test_exemples_dans_leurs_bornes():
    for route, (requete, _reponse, borne) in m.MODELES_P6.items():
        nom = route.rsplit("/", 1)[1]
        assert m.taille_json(_fixture(f"{nom}_requete.json")) < borne, route
    assert m.taille_json(_fixture("reclamer_requete_p6.json")) < m.TAILLE_MAX_REQUETE
    assert m.taille_json(_fixture("reclamer_reponse_carte.json")) < m.TAILLE_MAX_REPONSE


def test_bornes_des_corps():
    assert (m.TAILLE_MAX_EVENEMENT, m.TAILLE_MAX_ISSUE, m.TAILLE_MAX_REPONSE) == (8 * 1024, 32 * 1024, 64 * 1024)
    assert m.TAILLE_MAX_CARTE < m.TAILLE_MAX_REPONSE
    assert {r.rsplit("/", 1)[1]: b for r, (_q, _p, b) in m.MODELES_P6.items()} == {
        "battement": 8192, "terminer": 32768, "question": 32768, "bloquer": 8192, "reprendre": 8192, "arret": 8192}


# ------------------------------------------------------------------ reclamer


def test_reclamer_p5_toujours_valide():
    requete = m.RequeteReclamer.model_validate(_fixture("reclamer_requete.json"))
    assert requete.voies_disponibles == [] and requete.carte_en_cours is None and requete.espace_libre_mio is None


def test_reclamer_voies_exigent_peut_executer():
    corps = dict(_fixture("reclamer_requete_p6.json"), peut_executer=False)
    assert "un poste qui ne peut pas exécuter n'annonce aucune voie" in _refus(m.RequeteReclamer, corps)


@pytest.mark.parametrize("voies, motif", [
    (["poste-codex", "poste-codex"], "doublon"),
    (["hermes"], "valeurs admises : poste-codex, poste-claude, poste-integration"),
    (["poste-codex", "poste-claude", "poste-integration", "poste-x"], "au plus 3 voies"),
])
def test_reclamer_voies_refusees(voies, motif):
    assert motif in _refus(m.RequeteReclamer, dict(_fixture("reclamer_requete_p6.json"), voies_disponibles=voies))


def test_reclamer_carte_en_cours():
    corps = dict(_fixture("reclamer_requete_p6.json"),
                 carte_en_cours={"tableau": "acp-x-1a2b", "carte": "t_ab12cd34", "run_id": 3})
    assert m.RequeteReclamer.model_validate(corps).carte_en_cours.run_id == 3
    corps["carte_en_cours"]["carte"] = "carte-libre"
    assert "« carte » : format invalide" in _refus(m.RequeteReclamer, corps)


# ------------------------------------------------------------------ carte servie


def test_carte_tient_dans_64_kio():
    """La borne de la carte est vérifiée par le contrat : une carte qui dépasse 60 Kio (consigne et résumés à tronquer
    par le greffon) est refusée, au lieu d'une réponse de plus de 64 Kio que le poste refuserait sans le dire."""
    grand = "é" * 2000  # 2 octets par caractère en UTF-8
    parents = [{"carte": f"t_{i:08x}", "role": "implementation", "resume": grand, "tronque": True,
                "branche": f"hermes/t_{i:08x}"} for i in range(12)]
    pleine = _carte(consigne="ü" * 16_000, parents=parents)
    message = _refus(m.DemandeCarte, pleine)
    assert "octets : au plus 61440" in message and "à tronquer" in message
    reduite = _carte(consigne="ü" * 16_000, parents=parents[:6])
    carte = m.DemandeCarte.model_validate(reduite)
    reponse = dict(_fixture("reclamer_reponse_carte.json"), carte=carte.model_dump(mode="json"))
    assert m.taille_json(reponse) <= m.TAILLE_MAX_REPONSE


@pytest.mark.parametrize("modifs, motif", [
    ({"role": "integration"}, "poste-integration porte les cartes d'intégration"),
    ({"voie": "poste-integration"}, "poste-integration porte les cartes d'intégration"),
    ({"modele": None}, "porte le modèle résolu par le routage"),
    ({"branche": "hermes/t_00000000"}, "la branche d'une carte est hermes/<carte>"),
    ({"branche": "main"}, "hermes/<carte> ou hermes/projet-<slug> attendu"),
    ({"role": "relecture"}, "« carte_relue » : exigée pour une relecture"),
    ({"carte_relue": "t_9f01aa77"}, "« carte_relue » : exigée pour une relecture"),
    ({"correction_n": 1}, "réservé aux cartes de correction"),
    ({"branches_a_integrer": ["hermes/t_9f01aa77"]}, "réservé aux cartes d'intégration"),
    ({"branche_base": "../main"}, "nom de branche git invalide"),
    ({"branche_base": "main.lock"}, "nom de branche git invalide"),
    ({"duree_max_s": 10}, "« duree_max_s » doit être un entier compris entre 60 et 86400"),
    ({"consigne": " "}, "« consigne » ne peut pas être vide"),
    ({"bonus": 1}, "champ inconnu refusé : « bonus »"),
])
def test_carte_refusee_en_francais(modifs, motif):
    assert motif in _refus(m.DemandeCarte, _carte(**modifs))


def test_carte_d_integration():
    carte = _carte(role="integration", voie="poste-integration", modele=None, effort=None, palier=None,
                   branche="hermes/projet-outil-jetable", branches_a_integrer=["hermes/t_9f01aa77", "hermes/t_ab12cd34"],
                   branche_depart=None, parents=[])
    assert m.DemandeCarte.model_validate(carte).branches_a_integrer[1] == "hermes/t_ab12cd34"
    assert "ni modèle, ni effort, ni palier" in _refus(m.DemandeCarte, dict(carte, modele="sonnet"))
    assert "fusionne au moins une branche" in _refus(m.DemandeCarte, dict(carte, branches_a_integrer=[]))
    assert "écrit hermes/projet-<slug>" in _refus(m.DemandeCarte, dict(carte, branche="hermes/t_ab12cd34"))


def test_reponses_livrees():
    question = {"genre": "question", "question": "q_0a1b2c3d4e5f", "texte": "Oui, garde 3.10.",
                "repondu_par": "hermes", "le": "2026-10-02T09:00:00Z"}
    refus = {"genre": "refus_revue", "question": None, "texte": "Ne touche pas au workflow de CI.",
             "repondu_par": "proprietaire", "le": "2026-10-02T09:00:00Z"}
    carte = m.DemandeCarte.model_validate(_carte(reponses=[question, refus], reprise=True))
    assert [r.genre for r in carte.reponses] == ["question", "refus_revue"] and carte.reprise
    assert "exigée pour une réponse à une question" in _refus(m.ReponseQuestionLivree, dict(question, question=None))
    assert "seul le propriétaire refuse une revue" in _refus(m.ReponseQuestionLivree, dict(refus, repondu_par="hermes"))


# ------------------------------------------------------------------ routes de l'exécution


def test_id_envoi_uuid_v4():
    corps = _fixture("battement_requete.json")
    for faux in ("3f2a8c1e-5b6d-1e7f-8a9b-0c1d2e3f4a5b", "pas-un-uuid", "3F2A8C1E-5B6D-4E7F-8A9B-0C1D2E3F4A5B"):
        assert "« id_envoi » : format invalide" in _refus(m.RequeteBattement, dict(corps, id_envoi=faux))
    assert "champ obligatoire absent : « id_envoi »" in _refus(
        m.RequeteBattement, {k: v for k, v in corps.items() if k != "id_envoi"})


def test_battement_note_bornee():
    corps = _fixture("battement_requete.json")
    assert "au maximum 500 caractères" in _refus(m.RequeteBattement, dict(corps, note="x" * 501))
    assert m.RequeteBattement.model_validate(dict(corps, note="x" * 500)).note


def test_terminer_resume_vide_refuse():
    """``complete_task`` lèverait ``EmptyCompletionError`` depuis ``running`` : le contrat refuse avant."""
    corps = _fixture("terminer_requete.json")
    assert "« resume » ne peut pas être vide" in _refus(m.RequeteTerminer, dict(corps, resume="   "))
    assert "au maximum 4000 caractères" in _refus(m.RequeteTerminer, dict(corps, resume="x" * 4001))


def test_terminer_verdict_et_corrections():
    corps = _fixture("terminer_requete.json")
    assert m.RequeteTerminer.model_validate(dict(corps, verdict="accepte")).verdict == "accepte"
    assert m.RequeteTerminer.model_validate(dict(corps, verdict="corrections", corrections="Ajoute un test.")).corrections
    for modifs in ({"verdict": "corrections"}, {"corrections": "x"}, {"verdict": "accepte", "corrections": "x"}):
        assert "exigée avec le verdict « corrections »" in _refus(m.RequeteTerminer, dict(corps, **modifs))
    assert "valeurs admises : accepte, corrections" in _refus(m.RequeteTerminer, dict(corps, verdict="peut-etre"))
    assert "valeurs admises : termine" in _refus(m.RequeteTerminer, dict(corps, issue="question"))


def test_terminer_metadonnees_fermees():
    """Champs fermés : jamais ``artifacts`` ni ``published_pr``, que ``complete_task`` traiterait (copie de fichiers,
    acceptation de PR)."""
    corps = _fixture("terminer_requete.json")
    for intrus in ("artifacts", "published_pr"):
        donnees = copy.deepcopy(corps)
        donnees["metadonnees"][intrus] = ["/etc/passwd"]
        assert f"champ inconnu refusé : « {intrus} »" in _refus(m.RequeteTerminer, donnees)
    donnees = copy.deepcopy(corps)
    donnees["metadonnees"]["branche"] = "hermes/t_00000000"
    assert "la branche d'une carte est hermes/<carte>" in _refus(m.RequeteTerminer, donnees)
    donnees = copy.deepcopy(corps)
    donnees["metadonnees"]["branche"] = "hermes/projet-outil-jetable"
    assert m.RequeteTerminer.model_validate(donnees).metadonnees.branche == "hermes/projet-outil-jetable"


@pytest.mark.parametrize("verification, motif", [
    ({"etat": "reussie", "code": 1, "tentatives": 1}, "réussie exige le code 0"),
    ({"etat": "echouee", "code": 0, "tentatives": 3}, "un échec porte un code non nul"),
    ({"etat": "non_executee", "code": None, "tentatives": 0}, "non exécutée dit pourquoi"),
])
def test_verification_coherente(verification, motif):
    corps = copy.deepcopy(_fixture("terminer_requete.json"))
    corps["metadonnees"]["verification"] = verification
    assert motif in _refus(m.RequeteTerminer, corps)


def test_pilotage_coherent():
    corps = copy.deepcopy(_fixture("terminer_requete.json"))
    corps["metadonnees"]["pilotage"] = {"touche": True, "chemins": []}
    assert "« touche » vaut vrai exactement quand des chemins sont cités" in _refus(m.RequeteTerminer, corps)
    corps["metadonnees"]["pilotage"] = {"touche": True, "chemins": [".github/workflows/ci.yml", "CLAUDE.md"]}
    assert m.RequeteTerminer.model_validate(corps).metadonnees.pilotage.chemins[1] == "CLAUDE.md"


def test_question_32_kio_admise():
    """Texte et contexte de 4 000 caractères chacun, jusqu'à 4 octets par caractère : 32 000 octets, que la borne de
    8 Kio de la première version aurait refusés."""
    corps = dict(_fixture("question_requete.json"), texte="𝄞" * 4000, contexte="𝄞" * 4000)
    assert m.taille_json(corps) > m.TAILLE_MAX_EVENEMENT and m.taille_json(corps) <= m.TAILLE_MAX_ISSUE
    assert len(m.RequeteQuestion.model_validate(corps).texte) == 4000
    assert "au maximum 4000 caractères" in _refus(m.RequeteQuestion, dict(corps, texte="x" * 4001))


def test_bloquer_genres_et_reprise():
    corps = _fixture("bloquer_requete.json")
    for genre in m.GENRES_BLOCAGE:
        donnees = dict(corps, genre=genre, reprise_le=corps["reprise_le"] if genre == "quota" else None)
        assert m.RequeteBloquer.model_validate(donnees).genre == genre
    assert "réservé au genre « quota »" in _refus(m.RequeteBloquer, dict(corps, genre="capacite"))
    assert "au maximum 500 caractères" in _refus(m.RequeteBloquer, dict(corps, raison="x" * 501))
    assert "valeurs admises : capacite" in _refus(m.RequeteBloquer, dict(corps, genre="autre"))


def test_reprendre_et_arret_motifs():
    assert "valeurs admises : redemarrage, reclamation_perdue" in _refus(
        m.RequeteReprendre, dict(_fixture("reprendre_requete.json"), motif="sigterm"))
    assert "valeurs admises : sigterm, pause_locale, annulee" in _refus(
        m.RequeteArret, dict(_fixture("arret_requete.json"), motif="redemarrage"))
    assert "valeurs admises : rendue, deja_libre" in _refus(m.ReponseReprise, {"etat": "liberee"})


def test_codes_d_erreur_p6():
    for code in ("reclamation_perdue", "projet_en_pause", "carte_inconnue", "carte_non_emise", "secret_detecte",
                 "issue_invalide"):
        assert m.ErreurMachine.model_validate({"detail": {"code": code, "message": "x"}}).detail.code == code


def test_secret_trouve_sans_citer_la_valeur():
    corps = copy.deepcopy(_fixture("terminer_requete.json"))
    assert m.secret_trouve(corps) is None
    faux = "sk-ant-" + "a" * 30
    corps["metadonnees"]["pilotage"] = {"touche": True, "chemins": [f"docs/{faux}.md"]}
    assert m.secret_trouve(corps) == "clé d'API Anthropic"
    assert m.secret_trouve({"cle-" + "ghp_" + "b" * 36: 1}) == "jeton GitHub"
    profond: object = "acpm_" + "c" * 43
    for _ in range(5000):
        profond = [profond]
    assert m.secret_trouve(profond) == "jeton machine ACP"  # itératif : aucune RecursionError
