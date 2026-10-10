"""Contrat de la discussion réduite (étape P7, part D ; cahier P7 § 9.4, § 13.2 ; correction K14), piloté depuis l'hôte
(voir conftest.py), sur la pile complète : vraie porte d'authentification (ticket WebSocket à usage unique), JSON-RPC
natif du tableau de bord (/api/ws), modèle factice qui appelle l'outil ``clarify``.

Le client de test (outils/client_ws.py, modes ``clarify-*``) n'emploie QUE les méthodes de la liste blanche d'ACP
(apps/interface/src/jsonrpc/canal.ts) : client.capabilities, session.create {}, session.resume, session.active_list,
prompt.submit, session.interrupt.

Ce qui est prouvé ici, sur l'image réellement construite :
- une ``clarify`` posée dans une session /api/ws SURVIT à la déconnexion de son client (le téléphone se ferme) : la
  session reste vivante dans le processus du tableau de bord (close_on_disconnect jamais envoyé, valeur par défaut) ;
- un SECOND client la voit ``waiting`` dans ``session.active_list`` (lecture seule, sans capacités : ce que lit la
  file Questions), sous la clé STOCKÉE rendue par session.create (``stored_session_id`` = ``session_key`` : c'est le
  lien « Ouvrir la discussion ») ;
- ``session.resume`` de cette clé rejoue la MÊME requête (même identifiant) dans ``open_requests`` ; la réponse
  ``{answers}`` est acceptée, le tour reprend et se termine (``message.complete``), et l'outil rend au modèle la
  réponse du propriétaire ;
- ``session.interrupt`` pendant une question la retire (``request.cancel``) et clôt le tour (``interrupted``).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from conftest import ENV_VALIDE, Conteneur, afficher, attendre_modele_factice, docker, lancer

PYTHON = "/opt/hermes/.venv/bin/python"
CLIENT = "/opt/acp-tests/outils/client_ws.py"
JOURNAL_FACTICE = "/tmp/modele-factice.jsonl"
MODELE = """\
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""
QUESTION = "Quel nom donner au module ?"
REPONSE = "outil.py"


@pytest.fixture(scope="module")
def pile(ressources, image_tests):
    reseau = ressources.reseau()
    idp = ressources.nom("idp")
    ressources.conteneurs.append(idp)
    docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
           "--entrypoint", PYTHON, image_tests, "/opt/acp-tests/outils/idp_factice.py", "--emetteur",
           "https://idp.acp.test:8443", "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem",
           "--cle", "/opt/acp-tests/ac/idp.key")
    volume = ressources.volume(image_tests, {"config.yaml": MODELE})
    hermes = lancer(ressources, image_tests, ENV_VALIDE, volume=volume, reseau=reseau)
    docker("exec", "-d", "-u", "hermes", hermes.nom, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port",
           "18080", "--journal", JOURNAL_FACTICE)
    attendre_modele_factice(hermes, JOURNAL_FACTICE)
    return hermes


def jeton(hermes: Conteneur) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"], verifier=True).stdout
    return json.loads(sortie)["id_token"]


def client(hermes: Conteneur, mode: str, *arguments: str) -> Dict[str, Any]:
    sortie_json = f"/tmp/acp-ws-{mode}.json"
    sortie = hermes.executer([PYTHON, CLIENT, mode, jeton(hermes), sortie_json, *arguments], delai=420)
    assert sortie.returncode == 0, (mode, sortie.stdout[-2000:], sortie.stderr[-4000:])
    return json.loads(hermes.executer(["cat", sortie_json], verifier=True).stdout)


def requetes_du_modele(hermes: Conteneur) -> List[Dict[str, Any]]:
    brut = hermes.executer(["cat", JOURNAL_FACTICE], verifier=True).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def test_clarify_survit_a_la_deconnexion_et_se_reprend_depuis_un_second_client(pile):
    posee = client(pile, "clarify-poser", "OUTIL:clarify")
    afficher("téléphone : question posée, puis déconnexion", json.dumps(posee, ensure_ascii=False, indent=1))
    assert "clarify" in posee["capacites"]["server_requests"]
    assert posee["envoi"]["status"] == "streaming"
    requete = posee["requete"]
    assert requete["method"] == "clarify" and requete["id"].startswith("srq-")
    [question] = requete["params"]["questions"]
    assert question["question"] == QUESTION and question["qid"] == "q0"
    # Hermes marque le premier choix « (Recommended) » (la page d'ACP le dit en français).
    assert question["choices"] == ["outil.py (Recommended)", "module.py"]
    cle = posee["cle"]
    assert cle

    reprise = client(pile, "clarify-reprendre", cle, REPONSE)
    afficher("bureau : liste, reprise, réponse, fin du tour", json.dumps(reprise, ensure_ascii=False, indent=1))
    # Lecture seule (file Questions) : la session est « waiting » sous la clé stockée rendue par session.create.
    assert reprise["attente"] == [{"status": "waiting", "session_key": cle, "id": posee["session_id"]}]
    # Même requête rejouée par session.resume (aucune nouvelle question posée).
    assert [(r["id"], r["method"]) for r in reprise["open_requests"]] == [(requete["id"], "clarify")]
    assert reprise["open_requests"][0]["params"]["questions"] == requete["params"]["questions"]
    assert reprise["reponse_envoyee"] == {"answers": {"q0": REPONSE}}
    assert reprise["fin"]["status"] == "complete" and reprise["fin"]["text"] == "fin"
    assert "message.complete" in reprise["evenements"]
    # L'outil a rendu au modèle la réponse du propriétaire (résultat de l'outil, reçu par le modèle factice ; un message
    # d'outil au format OpenAI ne porte pas toujours le nom de l'outil : il est reconnu à sa forme).
    resultats = [r["contenu"] for e in requetes_du_modele(pile) for r in e.get("resultats_outils") or []
                 if '"user_response"' in (r.get("contenu") or "")]
    afficher("résultat de l'outil clarify reçu par le modèle factice", json.dumps(resultats, ensure_ascii=False, indent=1))
    assert any(f'"user_response": "{REPONSE}"' in r and QUESTION in r for r in resultats), resultats


def test_interrompre_pendant_une_question_la_retire_et_clot_le_tour(pile):
    interrompue = client(pile, "clarify-interrompre", "OUTIL:clarify")
    afficher("interruption pendant une question", json.dumps(interrompue, ensure_ascii=False, indent=1))
    assert interrompue["interruption"]["status"] == "interrupted"
    assert interrompue["annulation"]["id"] == interrompue["requete"]["id"]
    assert interrompue["annulation"]["method"] == "clarify"
    assert interrompue["fin"]["status"] == "interrupted"
