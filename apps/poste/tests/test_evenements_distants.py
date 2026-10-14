"""Projection et reprise sans CLI : flux synthétiques et transport fonctionnel explicites.

Le journal SQLite, la file atomique et leurs réouvertures sont réels. Seule l'horloge
Hermes est remplacée ; l'auth HTTP et la réclamation sont éprouvées dans l'image.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sqlite3
import sys
import types
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from acp_poste.evenements import ProjectionPublique
from acp_poste.execution import Execution
from acp_poste.journal import Journal, masquer
from acp_poste.protocole import HermesIndisponible, HorsContrat, Refus
from acp_poste.sortie import FileSortie
from acp_poste_contrat.machine import EvenementExecution, RequeteBattement, ReponseBattement

RACINE = Path(__file__).resolve().parents[3]
NOYAU = RACINE / "hermes/plugins/acp-poste/noyau"
MAINTENANT = datetime(2026, 10, 14, 12, tzinfo=UTC)


def evenement(**changements):
    return dict(dict(id=str(uuid.uuid4()), tentative_id=str(uuid.uuid4()), ordre=1,
                     quand=MAINTENANT.isoformat(), moteur="codex", genre="message", texte="Message public."),
                **changements)


def battement(*evenements):
    return dict(id_envoi=str(uuid.uuid4()), tableau="acp-jetable", carte="t_ab12cd34", run_id=1,
                note="Événements publics du moteur.", evenements=list(evenements))


def projection(moteur="codex", valeurs=None):
    return ProjectionPublique(moteur, lambda t: masquer(t, valeurs), lambda: MAINTENANT)


def recevoir(p, **document):
    return p.recevoir(json.dumps(document))


@pytest.fixture
def noyau(monkeypatch):
    paquet = types.ModuleType("_test_journal_execution")
    paquet.__path__ = [str(NOYAU)]
    monkeypatch.setitem(sys.modules, paquet.__name__, paquet)
    base = types.ModuleType(paquet.__name__ + ".base")
    base.maintenant = lambda: int(MAINTENANT.timestamp())
    monkeypatch.setitem(sys.modules, base.__name__, base)
    for nom in ("textes", "journal_execution"):
        nom_complet = paquet.__name__ + "." + nom
        spec = importlib.util.spec_from_file_location(nom_complet, NOYAU / (nom + ".py"))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, nom_complet, module)
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def base_journal(tmp_path):
    chemin = tmp_path / "hermes.db"
    conn = sqlite3.connect(chemin)
    arbre = ast.parse((NOYAU / "base.py").read_text(encoding="utf-8"))
    schema = next(ast.literal_eval(n.value) for n in arbre.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "SCHEMA" for t in n.targets))
    conn.executescript(schema)
    conn.close()
    return chemin


def stocker(noyau, chemin, corps, *, projet="p_jetable", machine="m_test", voie="poste-codex"):
    demande = dict(projet_id=projet, role="implementation", voie=voie, modele="demande-non-observe")
    with sqlite3.connect(chemin) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return noyau.enregistrer(conn, machine, demande, RequeteBattement.model_validate(corps), parents=["t_12345678"])


def lecture(noyau, chemin, projet="p_jetable", **options):
    with sqlite3.connect(chemin) as conn:
        return noyau.lire(conn, projet, **options)


def test_projection_codex_liste_blanche_et_identifiants():
    p = projection()
    session = recevoir(p, type="thread.started", thread_id="native-thread")[0]
    assert session["session_native"] == "native-thread" and session["modele_servi"] is None
    assert recevoir(p, type="item.completed", item={"type": "reasoning", "text": "PRIVE"}) == []
    outil = recevoir(p, type="item.completed", item={"type": "command_execution", "id": "item-1",
                    "command": "SECRET-ARGUMENT", "aggregated_output": "SORTIE-PRIVEE"})[0]
    assert outil["outil"] == "shell" and outil["item_natif"] == "item-1"
    assert "PRIVE" not in json.dumps(outil) and "ARGUMENT" not in json.dumps(outil)
    assert recevoir(p, type="item.completed", item={"type": "file_change", "changes": None}) == []
    assert recevoir(p, type="turn.completed")[0]["ordre"] == 3


def test_projection_claude_modele_rapporte_parent_et_thinking_exclu():
    p = projection("claude")
    recevoir(p, type="system", subtype="init", session_id="claude-session", model="claude-reported")
    faits = recevoir(p, type="assistant", parent_tool_use_id="parent-tool", message={"id": "msg1",
        "content": [{"type": "thinking", "thinking": "PRIVE"}, {"type": "text", "text": "Bonjour"},
                    {"type": "tool_use", "id": "tool1", "name": "Read", "input": {"secret": "PRIVE"}}]})
    assert [e["genre"] for e in faits] == ["message", "outil"]
    assert all(e["modele_servi"] == "claude-reported" and e["parent_natif"] == "parent-tool" for e in faits)
    assert "PRIVE" not in json.dumps(faits)
    assert recevoir(p, type="user", message={"content": [{"type": "tool_result", "tool_use_id": "tool1",
                       "content": "PRIVE"}]})[0]["item_natif"] == "tool1"


def test_secret_chevauchant_deux_fragments_masque_avant_decoupage():
    secret = "un-jeton-opaque-de-test-123456789"
    p = projection(valeurs={"machine": secret})
    texte = "a" * 491 + secret + "b" * 700
    faits = recevoir(p, type="item.completed", item={"type": "agent_message", "text": texte})
    assert len(faits) == 3 and all(len(e["texte"]) <= 500 for e in faits)
    total = "".join(e["texte"] for e in faits)
    assert secret not in total and "«masqué:machine»" in total
    assert p._identifiant(secret) is None


def test_contrat_borne_les_lots_et_refuse_raisonnement():
    e = evenement()
    with pytest.raises(ValidationError):
        EvenementExecution.model_validate(dict(e, genre="reasoning"))
    with pytest.raises(ValidationError):
        EvenementExecution.model_validate(dict(e, texte="a" * 501))
    with pytest.raises(ValidationError):
        RequeteBattement.model_validate(battement(*[evenement() for _ in range(5)]))
    RequeteBattement.model_validate(battement(EvenementExecution.model_validate(e)))


def test_deduplication_reelle_apres_reouverture_et_pagination(noyau, base_journal):
    e1, e2 = evenement(), evenement()
    corps = battement(e1, e2)
    assert stocker(noyau, base_journal, corps) == [e1["id"], e2["id"]]
    assert stocker(noyau, base_journal, corps) == [e1["id"], e2["id"]]
    premiere = lecture(noyau, base_journal, limite=1)
    assert premiere["encore"] is True and len(premiere["evenements"]) == 1
    evenement_lu = premiere["evenements"][0]
    assert evenement_lu["parents"] == ["t_12345678"] and evenement_lu["modele_demande"] == "demande-non-observe"
    assert evenement_lu["modele_servi"] is None
    suite = lecture(noyau, base_journal, apres=premiere["prochain_curseur"], limite=1)
    assert suite["encore"] is False and suite["evenements"][0]["id"] == e2["id"]
    vide = lecture(noyau, base_journal, apres=suite["prochain_curseur"])
    assert vide["evenements"] == [] and vide["prochain_curseur"] == suite["prochain_curseur"]
    assert lecture(noyau, base_journal, "p_autre")["evenements"] == []


def test_conflit_identifiant_et_rang_annule_tout_le_lot(noyau, base_journal):
    e = evenement()
    stocker(noyau, base_journal, battement(e))
    with pytest.raises(noyau.RefusACP, match="autre contenu"):
        stocker(noyau, base_journal, battement(evenement(), dict(e, texte="modifié")))
    assert len(lecture(noyau, base_journal)["evenements"]) == 1
    with pytest.raises(noyau.RefusACP, match="rang"):
        stocker(noyau, base_journal, battement(dict(e, id=str(uuid.uuid4()))))
    with pytest.raises(noyau.RefusACP, match="moteur"):
        stocker(noyau, base_journal, battement(evenement(moteur="claude")))
    with pytest.raises(noyau.RefusACP, match="secret"):
        stocker(noyau, base_journal, battement(evenement(texte="sk-ant-api03-" + "x" * 80)))


def test_reponse_perdue_renvoi_apres_redemarrage_sans_doublon(noyau, base_journal, tmp_path):
    file = FileSortie(tmp_path / "sortie")
    corps = battement(evenement())
    chemin = file.deposer("battement", corps)
    def perdu(_route, document):
        stocker(noyau, base_journal, document)
        raise HermesIndisponible("Réponse perdue, transport de test.")
    with pytest.raises(HermesIndisponible):
        file.envoyer(chemin, perdu)
    assert chemin.exists()
    # Nouveau superviseur et nouvelle connexion SQLite : ni état dédupliqué en RAM, ni relance d'agent.
    file = FileSortie(tmp_path / "sortie")
    def reponse(_route, document):
        ids = stocker(noyau, base_journal, document)
        return ReponseBattement(valide=True, pause=False, annuler=False, evenements_recus=ids)
    resultats, refus = file.rejouer(reponse)
    assert refus is None and resultats[0].retire and file.en_attente() == []
    assert len(lecture(noyau, base_journal)["evenements"]) == 1


def test_absence_acquittement_garde_fichier_et_refus_le_preserve(tmp_path):
    file = FileSortie(tmp_path / "sortie")
    fichier = file.deposer("battement", battement(evenement()))
    with pytest.raises(HorsContrat, match="non acquittés"):
        file.envoyer(fichier, lambda *_: ReponseBattement(valide=True, pause=False, annuler=False))
    assert fichier.exists()
    def refus(*_):
        raise Refus("Conflit factice.", statut=422, code="requete_refusee")
    assert file.envoyer(fichier, refus).deplace
    assert (file.refusees / fichier.name).exists()


def test_evenements_transmis_avant_issue_et_coupure_ne_la_devance_pas(tmp_path):
    execution = object.__new__(Execution)
    execution.sortie = FileSortie(tmp_path / "sortie")
    execution.journal = Journal(tmp_path / "journal")
    execution.sortie.deposer("battement", battement(evenement()))
    vus = []
    def envoi(route, corps):
        vus.append(route)
        if route == "battement":
            raise HermesIndisponible("Coupure factice.")
    execution.envoyer = envoi
    issue = execution.emettre("terminer", {"id_envoi": str(uuid.uuid4()), "carte": "t_ab12cd34"})
    assert not issue.envoyee and vus == ["battement"]
    assert [execution.sortie.lire(f)[0] for f in execution.sortie.en_attente()] == ["battement", "terminer"]
    def reprise(route, corps):
        vus.append(route)
        return ReponseBattement(valide=True, pause=False, annuler=False,
                                evenements_recus=[e["id"] for e in corps.get("evenements", [])])
    execution.sortie.rejouer(reprise)
    assert vus == ["battement", "battement", "terminer"]


def test_saturation_explicite_garde_la_place_pour_issue(tmp_path, monkeypatch):
    import acp_poste.sortie as module
    monkeypatch.setattr(module, "FICHIERS_MAX", 6)
    file = FileSortie(tmp_path / "sortie")
    file.deposer("battement", battement(evenement()))
    with pytest.raises(ValueError, match="saturé"):
        file.deposer("battement", battement(evenement()))
    file.deposer("bloquer", {"id_envoi": str(uuid.uuid4())})
    assert len(file.en_attente()) == 2


@pytest.mark.parametrize("redemarrage", [False, True])
def test_lot_refuse_empeche_resultat_reussi_meme_apres_redemarrage(tmp_path, redemarrage):
    file = FileSortie(tmp_path / "sortie")
    original = battement(evenement())
    fichier = file.deposer("battement", original)
    def refus(*_):
        raise Refus("Conflit factice.", statut=422, code="requete_refusee")
    assert file.envoyer(fichier, refus).deplace
    if redemarrage:
        file = FileSortie(tmp_path / "sortie")
    corps = {cle: original[cle] for cle in ("tableau", "carte", "run_id")}
    corps.update(id_envoi=str(uuid.uuid4()), resume="Résultat synthétique à conserver.")
    fichier_issue = file.deposer("terminer", corps)
    envois = []
    def recevoir(route, document):
        envois.append((route, document))
        return {"etat": "bloquee"}
    resultat = file.envoyer(fichier_issue, recevoir)
    assert resultat.route == "bloquer" and resultat.retire
    assert [r for r, _ in envois] == ["bloquer"]
    assert envois[0][1]["id_envoi"] == corps["id_envoi"]
    assert "Journal public incomplet" in envois[0][1]["raison"]
    assert file.lire(file.refusees / fichier_issue.name)[1]["resume"] == corps["resume"]


def test_blocage_journal_reste_durable_apres_panne_durant_son_envoi(tmp_path):
    file = FileSortie(tmp_path / "sortie")
    corps = battement(evenement())
    fichier = file.deposer("battement", corps)
    file.envoyer(fichier, lambda *_: ReponseBattement(valide=False, pause=False, annuler=False))
    issue = file.deposer("terminer", {cle: corps[cle] for cle in ("id_envoi", "tableau", "carte", "run_id")})
    def perdu(*_):
        raise HermesIndisponible("Coupure factice.")
    with pytest.raises(HermesIndisponible):
        file.envoyer(issue, perdu)
    assert FileSortie(tmp_path / "sortie").lire(issue)[0] == "bloquer"


@pytest.mark.asyncio
async def test_saturation_du_lecteur_arrete_le_processus_et_bloque(tmp_path, monkeypatch):
    """Processus entièrement en mémoire : aucune CLI lancée, arrêt piloté par le vrai superviseur."""
    import asyncio
    import acp_poste.execution as moteur
    import acp_poste.sortie as sortie
    from types import SimpleNamespace

    class Entree:
        def write(self, _): pass
        async def drain(self): pass
        def close(self): pass

    class Processus:
        def __init__(self):
            self.stdin, self.stdout, self.stderr = Entree(), asyncio.StreamReader(), asyncio.StreamReader()
            self.returncode, self.process, self.ferme, self.arrets = None, self, False, 0
            self.stdout.feed_data(b'{"type":"thread.started","thread_id":"native"}\n')
            self.stdout.feed_data(b'{"type":"item.completed","item":{"type":"agent_message","text":"Public"}}\n')
        def close_fence(self): self.ferme = True

    processus = Processus()
    async def lancer(*_, **__): return processus
    async def arreter(*_):
        processus.arrets += 1
        processus.returncode = -15
        processus.stdout.feed_eof()
        processus.stderr.feed_eof()
        return True
    monkeypatch.setattr(moteur, "spawn_fenced_process", lancer)
    monkeypatch.setattr(sortie, "FICHIERS_MAX", 6)
    execution = object.__new__(Execution)
    execution.politique = SimpleNamespace(politique=SimpleNamespace(duree_max_carte_s=10), codex=None, claude=None)
    execution._secrets_connus = {}  # object.__new__ ne passe pas par les valeurs par défaut de la dataclass.
    execution.coffre = SimpleNamespace(lire=lambda _: None)
    execution.sortie, execution.journal = FileSortie(tmp_path / "sortie"), Journal(tmp_path / "journal")
    execution.horloge = lambda: MAINTENANT
    execution.intervalle_battement_s, execution.grace_s = 60, 0
    execution.lanceur = SimpleNamespace(arreter=arreter)
    execution.envoyer = lambda *_: ReponseBattement(valide=True, pause=False, annuler=False)
    demande = SimpleNamespace(duree_max_s=10, tableau="acp-jetable", carte="t_ab12cd34", run_id=1,
                              role="implementation")
    with pytest.raises(moteur.CarteRefusee, match="Journal public impossible") as refuse:
        await execution._processus(demande, "codex", "acp-codex", SimpleNamespace(argv=[], env={}), tmp_path,
                                   "Consigne factice", asyncio.Event(), None)
    assert refuse.value.genre == "capacite" and processus.arrets == 1 and processus.ferme
    assert len(execution.sortie.en_attente()) == 1


def test_deux_envois_concurrents_ne_rangent_pas_un_fichier_deja_retire(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    file = FileSortie(tmp_path / "sortie")
    fichier = file.deposer("battement", battement(evenement()))
    entre, liberer = threading.Event(), threading.Event()
    appels = []
    def transport(_route, corps):
        appels.append(corps["id_envoi"])
        entre.set()
        assert liberer.wait(3)
        return ReponseBattement(valide=True, pause=False, annuler=False,
                                evenements_recus=[e["id"] for e in corps["evenements"]])
    with ThreadPoolExecutor(max_workers=2) as pool:
        premier = pool.submit(file.envoyer, fichier, transport)
        assert entre.wait(3)
        second = pool.submit(file.envoyer, fichier, transport)
        # Le lecteur stdout peut toujours déposer pendant que le réseau attend.
        suivant = file.deposer("battement", battement(evenement()))
        assert suivant.exists()
        liberer.set()
        assert premier.result(timeout=3).retire
        assert second.result(timeout=3) is None
    assert len(appels) == 1 and file.en_attente() == [suivant]
