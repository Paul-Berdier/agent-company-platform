"""FAUX exécutant Railway, pour les tests de contrat seulement (étape P6, cahier P6 § 14.2) : il parle
``acp-machine/1`` au VRAI tableau de bord de Hermes (bouclage local du conteneur de test), à travers la vraie couture
par jeton, avec le jeton du faux poste (``faux_poste.py enroler`` d'abord). Il n'exécute RIEN : il réclame une carte,
puis rapporte ce que le test lui dicte (battement, terminer, question, bloquer, reprendre, arret). Chaque réponse 200
est validée par les modèles du contrat partagé ; une réponse hors contrat fait échouer la commande (code 5).

Sous-commandes (sortie : un objet JSON sur la dernière ligne de la sortie standard) :

  inventaire [--regime A|B]                publie l'inventaire Linux de l'exemple (daté de maintenant)
  reclamer [--voies v1,v2] [--en-cours tableau:carte:run] [--attente N] [--sans-execution]
                                           une réclamation ; la carte servie est gardée dans /tmp/faux-executant/carte.json
  envoyer <route> [--champs JSON] [--id-envoi U] [--run N]
                                           route de l'exécution sur la DERNIÈRE carte servie ; ``terminer`` reçoit des
                                           métadonnées complètes (branche de la carte, vérification réussie)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/opt/acp-tests/outils")
sys.path.insert(0, "/opt/hermes/plugins/acp-poste/contrat")

import faux_poste as fp  # noqa: E402
from acp_poste_contrat import machine as contrat  # noqa: E402

DOSSIER = Path("/tmp/faux-executant")
CARTE = DOSSIER / "carte.json"


def _maintenant() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def inventaire(regime: str) -> int:
    corps = json.loads((fp.FIXTURES / "inventaire_requete_linux.json").read_text(encoding="utf-8"))
    quand = _maintenant()
    corps["releve_le"] = quand
    corps["isolement_linux"]["sonde_le"] = quand
    for releve in corps["releves"]:
        releve["releve_le"] = quand
        for compteur in releve["compteurs"]:
            compteur["observed_at"] = quand
    fp.mesurer_depots(corps, quand)  # étape P7 : visibilité mesurée de chaque dépôt (cahier P7 § 11.2)
    if regime == "A":
        corps["isolement_linux"].update(regime="A", bwrap="fonctionne", reseau_coupe=True,
                                        ecriture_admise={"codex": True, "claude": True}, raison=None)
    statut, reponse, entetes, duree = fp.poster(contrat.ROUTE_INVENTAIRE, corps, fp._jeton())
    if statut == 200:
        fp._valider(contrat.ReponseInventaire, reponse, "réponse d'inventaire")
    return fp._sortie({"statut": statut, "corps": reponse, "duree": duree})


def reclamer(voies, en_cours, attente: int, peut_executer: bool) -> int:
    carte_en_cours = None
    if en_cours:
        tableau, carte, run = en_cours.split(":")
        carte_en_cours = {"tableau": tableau, "carte": carte, "run_id": int(run)}
    corps = {"protocole": "acp-machine/1", "version_poste": "1.0.0", "peut_executer": peut_executer,
             "ordres_acquittes": [], "attente_max_s": attente, "politique_valide": True,
             "voies_disponibles": list(voies) if peut_executer else [], "carte_en_cours": carte_en_cours,
             "espace_libre_mio": 3120}
    statut, reponse, entetes, duree = fp.poster(contrat.ROUTE_RECLAMER, corps, fp._jeton(), delai=attente + 15)
    if statut == 200:
        valide = fp._valider(contrat.ReponseReclamer, reponse, "réponse de réclamation")
        if valide.carte is not None:
            DOSSIER.mkdir(parents=True, exist_ok=True)
            CARTE.write_text(json.dumps(valide.carte.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
        fp._journaliser("executant_reclamer", carte=valide.carte.carte if valide.carte else None)
    return fp._sortie({"statut": statut, "corps": reponse, "duree": duree})


def _metadonnees(carte: dict) -> dict:
    return {"modele_demande": carte["modele"], "modele_servi": "factice-servi-1" if carte["modele"] else None,
            "effort": carte["effort"], "palier_demande": carte["palier"], "palier_servi": None,
            "jetons": {"entree": 100, "sortie": 20, "cache": 0}, "branche": carte["branche"], "base": "1" * 40,
            "tete": "2" * 40, "diffstat": {"fichiers": 1, "ajouts": 3, "retraits": 0},
            "verification": {"etat": "reussie", "code": 0, "duree_s": 1, "tentatives": 1, "raison": None},
            "pilotage": {"touche": False, "chemins": []}, "regime": "B", "session_locale": True}


def envoyer(route: str, champs: dict, id_envoi, run) -> int:
    carte = json.loads(CARTE.read_text(encoding="utf-8"))
    corps = {"id_envoi": id_envoi or str(uuid.uuid4()), "tableau": carte["tableau"], "carte": carte["carte"],
             "run_id": run or carte["run_id"]}
    if route == "terminer":
        corps.update(issue="termine", resume="Fait.", verdict=None, corrections=None, metadonnees=_metadonnees(carte))
    corps.update(champs)
    chemin = f"{contrat.PREFIXE_ROUTES}/{route}"
    statut, reponse, entetes, duree = fp.poster(chemin, corps, fp._jeton())
    if statut == 200:
        fp._valider(getattr(contrat, contrat.MODELES_P6[chemin][1]), reponse, f"réponse de {route}")
    fp._journaliser("executant_envoi", route=route, statut=statut)
    return fp._sortie({"statut": statut, "corps": reponse, "id_envoi": corps["id_envoi"], "duree": duree})


def main(argv) -> int:
    analyseur = argparse.ArgumentParser()
    sous = analyseur.add_subparsers(dest="commande", required=True)
    a = sous.add_parser("inventaire")
    a.add_argument("--regime", choices=("A", "B"), default="B")
    a = sous.add_parser("reclamer")
    a.add_argument("--voies", default="poste-claude")
    a.add_argument("--en-cours", default=None)
    a.add_argument("--attente", type=int, default=5)
    a.add_argument("--sans-execution", action="store_true")
    a = sous.add_parser("envoyer")
    a.add_argument("route", choices=("battement", "terminer", "question", "bloquer", "reprendre", "arret"))
    a.add_argument("--champs", default="{}")
    a.add_argument("--id-envoi", default=None)
    a.add_argument("--run", type=int, default=None)
    arguments = analyseur.parse_args(argv)
    if arguments.commande == "inventaire":
        return inventaire(arguments.regime)
    if arguments.commande == "reclamer":
        voies = [v for v in arguments.voies.split(",") if v]
        return reclamer(voies, arguments.en_cours, arguments.attente, not arguments.sans_execution)
    return envoyer(arguments.route, json.loads(arguments.champs), arguments.id_envoi, arguments.run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
