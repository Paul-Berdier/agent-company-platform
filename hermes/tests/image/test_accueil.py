"""Accueil agrégé (étape P7, cahier P7 § 8.2, décision P7-7 ; correction K18) : ``GET /v1/accueil`` a la FORME de la
fixture partagée (``hermes/tests/outils/fixtures_accueil/accueil.json``, lue aussi par les tests de l'interface et,
s'il le veut, par le desktop P8) sur un état construit ; ses blocs viennent des fonctions existantes (mêmes valeurs que
``/v1/questions``, ``/v1/quotas``, ``/v1/poste``) ; un bloc illisible vaut ``null`` avec sa raison, jamais une valeur
par défaut ; rien n'est inventé sans exécutant.

La fixture est la réponse réelle de cet état construit ; pour la régénérer après un changement VOULU de la forme :
lancer ce fichier dans l'image de test avec ``ACP_ECRIRE_FIXTURE_ACCUEIL=<chemin monté>``, puis relire et recopier le
fichier écrit (jamais en CI)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import inventaire_linux, poste_confirme
from test_routes_projets import P, client  # noqa: F401 — fixture des routes (session factice)

FIXTURE = Path("/opt/acp-tests/outils/fixtures_accueil/accueil.json")


def forme(valeur):
    """Forme d'une réponse : clés des objets (récursivement), forme du premier élément des listes, type des
    feuilles (``None`` à part : une valeur absente reste dite)."""
    if isinstance(valeur, dict):
        return {cle: forme(v) for cle, v in sorted(valeur.items())}
    if isinstance(valeur, list):
        return [forme(valeur[0])] if valeur else []
    if valeur is None:
        return None
    return {bool: "booleen", int: "nombre", float: "nombre", str: "texte"}[type(valeur)]


def construire_etat(noyau, conn) -> dict:
    """Exécutant Railway en ligne (inventaire Linux, régime B : relevés, quotas et voies du poste), un projet sur dépôt
    dont l'exploration (voie Claude) est en main de l'exécutant et pose une question adressée au propriétaire, un
    canal ntfy publié par la passerelle."""
    machine, _jeton = poste_confirme(noyau, conn, nom="Exécutant Railway")
    with noyau.base.transaction(conn):
        noyau.inventaire.recevoir_dans(conn, machine, inventaire_linux())
        noyau.presence.enregistrer_dans(conn, machine, "longpoll")
        noyau.base.ecrire_emetteur(conn, "canal", {"canal": "ntfy", "configure": True,
                                                   "serveur": "https://ntfy.acp.test"})
    projet = noyau.projets.lancer(conn, titre="Outil jetable", objectif="Écrire un outil dans le dépôt jetable.",
                                  profil="base", depot="jetable", reponses="proprietaire", origine="tableau_de_bord",
                                  auteur="proprietaire:test",
                                  exploration={"voie": "poste-claude", "modele": "opus", "effort": "low"})["projet"]
    exploration = projet["cartes"]["exploration"]
    with noyau.ka.connexion(projet["tableau"]) as kc:
        tache = noyau.ka.claim_task(kc, exploration, ttl_seconds=2700, claimer=noyau.execution.claimer(machine))
    en_main = {"tableau": projet["tableau"], "carte": exploration, "run_id": tache.current_run_id}
    with noyau.base.transaction(conn):  # ce que noter_reclamation et _reclamer_une écrivent pour l'exécutant
        conn.execute("UPDATE demandes SET machine_id = ?, reclamee_le = ? WHERE carte = ?",
                     (machine, noyau.base.maintenant(), exploration))
        conn.execute("UPDATE machines SET peut_executer = 1, voies_disponibles = ?, carte_en_cours = ?, "
                     "espace_libre_mio = 3120 WHERE id = ?", (json.dumps(["poste-claude"]), json.dumps(en_main),
                                                             machine))
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=exploration, run_id=tache.current_run_id,
                              texte="Faut-il garder Python 3.11 ?")
    return {"projet": projet, "question": q["question"], "machine": machine}


def test_route_a_la_forme_de_la_fixture_partagee(client, noyau):  # noqa: F811
    with noyau.base.connexion() as conn:
        etat = construire_etat(noyau, conn)
    reponse = client.get(f"{P}/v1/accueil")
    assert reponse.status_code == 200, reponse.text
    accueil = reponse.json()
    if os.environ.get("ACP_ECRIRE_FIXTURE_ACCUEIL"):  # régénération de la fixture partagée (documentée), jamais en CI
        Path(os.environ["ACP_ECRIRE_FIXTURE_ACCUEIL"]).write_text(
            json.dumps(accueil, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    attendu = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert forme(accueil) == forme(attendu)
    # Valeurs : celles des routes existantes, jamais recalculées autrement.
    questions = client.get(f"{P}/v1/questions").json()
    assert accueil["a_traiter"]["total"] == questions["compteurs"]["a_traiter"] == 1
    assert accueil["a_traiter"]["premieres"] == [{
        "genre": "question", "projet": etat["projet"]["id"], "projet_titre": "Outil jetable",
        "titre": "Exploration du dépôt « jetable »", "cible": f"/projets?vue=questions&q={etat['question']}"}]
    assert accueil["chez_hermes"] == 0 and accueil["discussions"] == questions["discussions"]
    assert accueil["quotas"] == client.get(f"{P}/v1/quotas").json()
    assert accueil["executant"]["etat"] == "en_ligne" and accueil["executant"]["nom"] == "Exécutant Railway"
    assert accueil["executant"]["plateforme"] == "linux" and "poste-codex" in accueil["executant"]["voies_fermees"]
    assert accueil["executant"]["carte_en_cours"] == {
        "titre": "Exploration du dépôt « jetable »", "projet": etat["projet"]["id"], "projet_titre": "Outil jetable",
        "statut": "scheduled", "voie": "poste-claude", "connue": True}
    assert accueil["quotas"]["poste-codex"]["source_releve"] == "poste"  # relevé de l'inventaire, jamais estimé
    assert accueil["notifications"] == {"canal": "ntfy", "configure": True, "connu": True, "message": None}
    [p] = accueil["projets"]["liste"]
    assert (p["id"], p["etat"], p["questions_ouvertes"], p["depot"], p["branche_prete"]) == (
        etat["projet"]["id"], "actif", 1, "jetable", None)
    assert (accueil["projets"]["en_cours"], accueil["projets"]["en_pause"], accueil["projets"]["termines_7j"]) == (
        1, 0, 0)
    assert accueil["pause_generale"] is None and accueil["illisibles"] == {}


def test_sans_executant_rien_n_est_invente(client, noyau):  # noqa: F811
    accueil = client.get(f"{P}/v1/accueil").json()
    assert accueil["executant"]["etat"] == "non_configure" and accueil["executant"]["nom"] is None
    assert accueil["executant"]["plateforme"] is None and accueil["executant"]["carte_en_cours"] is None
    assert accueil["executant"]["voies_fermees"] == {}
    assert accueil["notifications"]["connu"] is False and accueil["notifications"]["message"] == (
        "État du canal de notification inconnu : la passerelle ne l'a pas encore publié.")
    assert accueil["a_traiter"]["total"] == 0 and accueil["projets"]["liste"] == []
    assert accueil["quotas"]["poste-codex"]["etat"] == "inconnu"


def test_bloc_illisible_vaut_null_avec_sa_raison(client, noyau, monkeypatch):  # noqa: F811
    import meta

    presence = meta.sous_module_noyau("presence")  # la copie du noyau servie par les routes

    def en_panne(_conn):
        raise RuntimeError("base du poste illisible")
    monkeypatch.setattr(presence, "etat_poste", en_panne)
    accueil = client.get(f"{P}/v1/accueil").json()
    assert accueil["executant"] is None
    assert accueil["illisibles"] == {"executant": "Bloc illisible (RuntimeError) : rechargez la page ; si l'erreur "
                                                  "reste, consultez /v1/meta."}
    assert accueil["projets"] is not None and accueil["a_traiter"] is not None  # les autres blocs restent lus
