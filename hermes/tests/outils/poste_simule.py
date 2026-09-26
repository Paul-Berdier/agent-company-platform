"""Poste SIMULÉ, pour les tests seulement (étape P4) : il joue le rôle du poste Windows par l'API kanban
de Hermes et les fonctions de bibliothèque du greffon acp-poste — jamais par un raccourci SQL.

Exécuté dans le conteneur de test (``docker exec -u hermes … python poste_simule.py …``) ou par les tests
de l'image, avec le ``HERMES_HOME`` du processus. Les routes machine du vrai poste (``/machine/v1/*``,
jeton, réclamation par long-poll) sont l'objet de P5-P6 ; ce script en appelle les MÊMES fonctions du
noyau (relevé, présence, questions, corrections) ou l'API kanban publique (réclamation, clôture).

Sous-commandes (sortie : un objet JSON sur la sortie standard, code 0 ; refus : code 3) :

  releve-factice <json|@fichier>          relevé d'une voie (source « releve_factice »)
  routage-factice <json|@fichier>         {classe: [{voie, modele, effort?, palier?}]}
  presence <machine>                      présence du poste (source « simule »)
  reclamer <tableau> <carte>              claim_task, réclamant « acp-poste:simule », TTL 2 700 s
  terminer <tableau> <carte> <résumé>     complete_task(expected_run_id = run courant)
  question <tableau> <carte> <texte>      questions.poser (run courant)
  corriger <tableau> <relecture> <consigne>  graphe.inserer_correction (run courant de la relecture)
  reglage <clé> <valeur JSON>             réglage du greffon
  cartes <tableau>                        cartes du tableau (lecture : statut, assigné, effort…)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/opt/hermes/plugins/acp-poste")

RECLAMANT = "acp-poste:simule"
TTL = 2700


def _json_argument(valeur: str):
    if valeur.startswith("@"):
        with open(valeur[1:], encoding="utf-8") as flux:
            return json.load(flux)
    return json.loads(valeur)


def _sortie(objet, code: int = 0) -> int:
    os.write(1, (json.dumps(objet, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
    return code


def main(argv) -> int:
    from noyau import base, graphe, presence, questions, routage
    from noyau import kanban_adapter as ka
    from noyau.textes import RefusACP

    if not argv:
        return _sortie({"erreur": "sous-commande attendue"}, 2)
    commande, arguments = argv[0], argv[1:]
    try:
        with base.connexion() as conn:
            if commande == "releve-factice":
                donnees = _json_argument(arguments[0])
                if donnees.get("source") != "releve_factice":
                    return _sortie({"erreur": "le poste simulé ne dépose que des relevés factices"}, 2)
                return _sortie({"releve": routage.enregistrer_releve(conn, donnees)})
            if commande == "routage-factice":
                for classe, entrees in _json_argument(arguments[0]).items():
                    routage.enregistrer_routage(conn, classe, entrees, source="releve_factice", valide_par="poste-simule")
                return _sortie({"ok": True})
            if commande == "presence":
                return _sortie({"presence": presence.enregistrer(conn, arguments[0], "simule")})
            if commande == "reglage":
                base.poser_reglage(conn, arguments[0], json.loads(arguments[1]), "poste-simule")
                return _sortie({"ok": True})
            tableau = arguments[0]
            if commande == "cartes":
                with ka.connexion(tableau) as kc:
                    return _sortie({"cartes": [{
                        "id": t.id, "titre": t.title, "statut": t.status, "assigne": t.assignee,
                        "cree_par": t.created_by, "cle": t.idempotency_key, "modele": t.model_override,
                        "effort": t.reasoning_effort, "competences": t.skills, "priorite": t.priority,
                        "reclamation": t.claim_lock, "run": t.current_run_id, "parents": ka.parent_ids(kc, t.id),
                        "cree_le": t.created_at, "debut": t.started_at, "fini_le": t.completed_at}
                        for t in ka.list_tasks(kc, include_archived=True)]})
            carte = arguments[1]
            if commande == "reclamer":
                with ka.connexion(tableau) as kc:
                    tache = ka.claim_task(kc, carte, ttl_seconds=TTL, claimer=RECLAMANT)
                if tache is None:
                    return _sortie({"reclamee": False}, 3)
                return _sortie({"reclamee": True, "run": tache.current_run_id})
            with ka.connexion(tableau) as kc:
                run = ka.get_task(kc, carte).current_run_id
            if commande == "terminer":
                with ka.connexion(tableau) as kc:
                    fini = ka.complete_task(kc, carte, summary=arguments[2], expected_run_id=run)
                return _sortie({"terminee": fini}, 0 if fini else 3)
            if commande == "question":
                return _sortie(questions.poser(conn, tableau=tableau, carte=carte, run_id=run, texte=arguments[2]))
            if commande == "corriger":
                return _sortie(graphe.inserer_correction(conn, tableau=tableau, carte_relecture=carte,
                                                         run_id_relecture=run, consigne=arguments[2]))
    except RefusACP as exc:
        return _sortie({"code": exc.code, "message": exc.message}, 3)
    return _sortie({"erreur": f"sous-commande inconnue : {commande}"}, 2)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
