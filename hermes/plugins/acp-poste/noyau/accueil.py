"""Accueil agrégé (étape P7, cahier P7 § 8.2, décision P7-7) : route ``GET /v1/accueil``.

UNE lecture pour la page d'accueil, la même au téléphone, dans le navigateur du PC et, s'il le veut, pour le desktop
(P8) : ce qui attend le propriétaire, les projets en cours, l'exécutant, les quotas, le canal de notification, la pause
générale et les discussions en attente (compteur en lecture seule).

Composée UNIQUEMENT de fonctions existantes du noyau (correction K18) : ``questions.file_questions`` (compteurs de la
file), ``projets.lister``, ``presence.etat_poste``, ``execution.vue_executant`` et ``execution.branches_pretes``
(lecture seule), ``quotas.vue`` (la forme de ``GET /v1/quotas``), ``notifications.etat_public`` et
``projets.pause_generale``. Chaque bloc illisible vaut ``null`` et sa raison est rangée dans ``illisibles`` : jamais une
valeur par défaut, jamais un zéro inventé. Le nom de l'exécutant vient de ``machines.nom``, jamais d'un libellé écrit
en dur.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from . import base, notifications, presence, projets, questions, quotas
from . import textes as T

PREMIERES = 3
SEPT_JOURS_S = 7 * 24 * 3600
ETATS_EN_COURS = ("creation", "actif")
CHEMIN_QUESTIONS = "/projets?vue=questions"


def _cible_question(q: Dict[str, Any]) -> str:
    return f"{CHEMIN_QUESTIONS}&q={q['id']}"


def _cible_carte(entree: Dict[str, Any]) -> str:
    return f"{CHEMIN_QUESTIONS}&carte={entree['tableau']}/{entree['carte']}"


def _a_traiter(file: Dict[str, Any]) -> Dict[str, Any]:
    """Compteurs de la file Questions et les trois premières demandes, dans l'ordre de la page Questions."""
    compteurs = file["compteurs"]
    premieres: List[Dict[str, Any]] = []
    for q in file["questions"]:
        if q["chez"] == "proprietaire":
            premieres.append({"genre": "question", "projet": q["projet"], "projet_titre": q["projet_titre"],
                              "titre": q["carte_titre"] or q["texte"][:120], "cible": _cible_question(q)})
    for genre, section in (("decision", "triage"), ("revue", "revues"), ("arretee", "bloquees")):
        for entree in file.get(section) or []:
            premieres.append({"genre": genre, "projet": entree["projet"], "projet_titre": entree["projet_titre"],
                              "titre": entree["titre"], "cible": _cible_carte(entree)})
    return {"total": compteurs["a_traiter"], "questions": compteurs["questions"], "decisions": compteurs["decisions"],
            "revues": compteurs["revues"], "arretees": compteurs["arretees"], "premieres": premieres[:PREMIERES],
            "tableaux_illisibles": list(file.get("tableaux_illisibles") or [])}


def _projets(conn) -> Dict[str, Any]:
    from . import execution  # import différé : execution importe projets et questions

    liste = projets.lister(conn)
    limite = base.maintenant() - SEPT_JOURS_S
    termines_7j = conn.execute("SELECT COUNT(*) FROM projets WHERE etat = 'termine' AND termine_le >= ?",
                               (limite,)).fetchone()[0]
    pretes = {}
    for branche in execution.branches_pretes(conn):
        pretes.setdefault(branche["projet"], branche["branche"])
    ouverts = [p for p in liste if p["etat"] in projets.ETATS_OUVERTS]
    return {
        "en_cours": sum(1 for p in liste if p["etat"] in ETATS_EN_COURS),
        "en_pause": sum(1 for p in liste if p["etat"] == "en_pause"),
        "termines_7j": int(termines_7j),
        "liste": [{"id": p["id"], "titre": p["titre"], "etat": p["etat"], "etat_derive": p["etat_derive"],
                   "faites": p["compteurs"]["faites"], "total": p["compteurs"]["total"],
                   "derniere_note": p["derniere_note"], "derniere_note_tronquee": p["derniere_note_tronquee"],
                   "questions_ouvertes": p["questions_ouvertes"], "depot": p["depot"],
                   "branche_prete": pretes.get(p["id"])} for p in ouverts],
    }


def _executant(conn) -> Dict[str, Any]:
    from . import execution  # import différé

    poste = presence.etat_poste(conn)
    machine = poste.get("poste") or {}
    vue = execution.vue_executant(conn)
    en_main = vue.get("carte_en_cours") if vue.get("connu") else None
    return {
        "etat": poste.get("etat"), "message": poste.get("message"), "nom": machine.get("nom"),
        "plateforme": vue.get("plateforme") if vue.get("connu") else None,
        "hote": vue.get("hote") if vue.get("connu") else None,
        "derniere_vue": poste.get("derniere_vue"), "hors_ligne_depuis": poste.get("hors_ligne_depuis"),
        "cartes_en_attente": poste.get("cartes_en_attente"), "pause_reclamations": poste.get("pause_reclamations"),
        "peut_executer": vue.get("peut_executer") if vue.get("connu") else None,
        "carte_en_cours": None if not en_main else {
            "titre": en_main.get("titre"), "projet": en_main.get("projet"), "projet_titre": en_main.get("projet_titre"),
            "statut": en_main.get("statut"), "voie": en_main.get("voie"), "connue": en_main.get("connue")},
        "voies_fermees": vue.get("voies_fermees") if vue.get("connu") else {},
    }


def _bloc(nom: str, calcul: Callable[[], Any], illisibles: Dict[str, str]) -> Any:
    try:
        return calcul()
    except Exception as exc:  # noqa: BLE001 — un bloc illisible vaut null avec sa raison, jamais une valeur inventée
        illisibles[nom] = T.BLOC_ILLISIBLE.format(type=type(exc).__name__)
        return None


def construire(conn) -> Dict[str, Any]:
    """Contenu de ``GET /v1/accueil`` (forme partagée : ``hermes/tests/outils/fixtures_accueil/accueil.json``)."""
    illisibles: Dict[str, str] = {}
    file: Optional[Dict[str, Any]] = _bloc("a_traiter", lambda: questions.file_questions(conn), illisibles)
    return {
        "genere_le": datetime.fromtimestamp(base.maintenant(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "a_traiter": _bloc("a_traiter", lambda: _a_traiter(file), illisibles) if file is not None else None,
        "chez_hermes": file["compteurs"]["chez_hermes"] if file is not None else None,
        "discussions": file["discussions"] if file is not None else questions.discussions_en_attente(),
        "projets": _bloc("projets", lambda: _projets(conn), illisibles),
        "executant": _bloc("executant", lambda: _executant(conn), illisibles),
        "quotas": _bloc("quotas", lambda: quotas.vue(conn), illisibles),
        "notifications": _bloc("notifications", lambda: notifications.etat_public(conn), illisibles),
        "pause_generale": _bloc("pause_generale", projets.pause_generale, illisibles),
        "illisibles": illisibles,
    }
