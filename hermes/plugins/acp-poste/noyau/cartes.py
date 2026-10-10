"""Création des cartes d'un projet à partir des DEMANDES enregistrées (cahier P4 § 4).

Écritures à deux bases, sans transaction commune ; l'ordre est toujours le même :

1. **réservation** dans la base du greffon (lignes ``demandes`` avec leur clé, ``carte`` NULL) ;
2. **création kanban** sous UNE transaction externe (``write_txn``) du tableau du projet, chaque carte
   avec ``idempotency_key = cle`` : le répartiteur ne voit jamais un tour à moitié créé
   (kanban_db.py:1341-1343) ;
3. **rattachement** (``demandes.carte``).

Une coupure entre deux étapes se rattrape : au rejeu (même clé, même carte : kanban_db.py:1318-1325)
et par la réparation de l'émetteur (:func:`reparer`). Une carte est reconnue comme émise par le
greffon à sa CLÉ, même avant le rattachement.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import base
from . import kanban_adapter as ka
from . import textes as T

DUREE_HERMES_TRAVAIL = 3600
DUREE_HERMES_SYNTHESE = 1800
DUREE_PLANIFICATION = 1800


def assigne(voie: str) -> str:
    """Assigné kanban d'une voie : le profil ``default`` pour Hermes, la voie elle-même pour le poste."""
    return ka.PROFIL_HERMES if voie == "hermes" else voie


def reserver(conn, lignes: Sequence[Dict[str, Any]]) -> None:
    """Insère les demandes (à appeler DANS une transaction de la base du greffon)."""
    maintenant = base.maintenant()
    for d in lignes:
        conn.execute(
            "INSERT INTO demandes (cle, projet_id, tableau, carte, role, classe, voie, tour, ref, titre, modele, effort, "
            "palier, modele_carte, effort_carte, source_routage, releve_id, depot_alias, consigne, carte_relue, "
            "correction_n, mention, parents, competences, priorite, duree_max, triage, corps, cree_le) "
            "VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (d["cle"], d["projet_id"], d["tableau"], d["role"], d["classe"], d["voie"], d["tour"], d.get("ref"),
             d.get("titre", "")[:200], d.get("modele"), d.get("effort"), d.get("palier"), d.get("modele_carte"),
             d.get("effort_carte"), d["source_routage"], d.get("releve_id"), d.get("depot_alias"), d["consigne"],
             d.get("carte_relue"), int(d.get("correction_n") or 0), d.get("mention"),
             json.dumps(list(d.get("parents") or [])),
             json.dumps(list(d["competences"])) if d.get("competences") is not None else None,
             int(d.get("priorite") or 0), d.get("duree_max"), 1 if d.get("triage") else 0, d.get("corps") or "",
             maintenant))


def demandes_non_rattachees(conn, projet_id: str, cles: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    lignes = conn.execute("SELECT * FROM demandes WHERE projet_id = ? AND carte IS NULL ORDER BY cree_le, rowid",
                          (projet_id,)).fetchall()
    voulues = set(cles) if cles is not None else None
    return [base.ligne_en_dict(l) for l in lignes if voulues is None or l["cle"] in voulues]


def creer(conn, projet: Dict[str, Any], demandes: Sequence[Dict[str, Any]], *, kc=None,
          creer_tableau: bool = False) -> Dict[str, str]:
    """Crée (ou retrouve par leur clé) les cartes des ``demandes`` sous UNE transaction kanban, puis les
    rattache. Rend ``{cle: identifiant de carte}``. Si une création lève, la transaction kanban est
    annulée : aucune carte n'existe, et l'exception remonte."""
    if not demandes:
        return {}
    tableau = projet["tableau"]
    if creer_tableau:
        ka.create_board(tableau, name=projet["titre"][:80], description=T.DESCRIPTION_TABLEAU)
    connues = {l["cle"]: l["carte"] for l in conn.execute(
        "SELECT cle, carte FROM demandes WHERE projet_id = ? AND carte IS NOT NULL", (projet["id"],))}
    ids: Dict[str, str] = {}

    def _creer_toutes(kconn) -> None:
        with ka.write_txn(kconn):
            for d in demandes:
                parents = []
                for cle_parent in json.loads(d.get("parents") or "[]"):
                    identifiant = ids.get(cle_parent) or connues.get(cle_parent)
                    if not identifiant:
                        raise RuntimeError(f"parent {cle_parent} sans carte")
                    parents.append(identifiant)
                competences = json.loads(d["competences"]) if d.get("competences") else None
                ids[d["cle"]] = ka.create_task(
                    kconn, title=d["titre"] or T.LIBELLES_ROLE.get(d["role"], d["role"]), body=d["corps"],
                    assignee=assigne(d["voie"]), created_by=ka.CREATEUR, priority=int(d["priorite"] or 0),
                    parents=parents, triage=bool(d["triage"]), idempotency_key=d["cle"],
                    max_runtime_seconds=d.get("duree_max"), skills=competences,
                    model_override=d.get("modele_carte"), reasoning_effort=d.get("effort_carte"), board=tableau)

    if kc is not None:
        _creer_toutes(kc)
    else:
        with ka.connexion(tableau) as kconn:
            _creer_toutes(kconn)
    with base.transaction(conn):
        for cle, carte in ids.items():
            conn.execute("UPDATE demandes SET carte = ? WHERE cle = ? AND carte IS NULL", (carte, cle))
    return ids


def planifier_pour_la_pause(conn, projet: Dict[str, Any], cartes: Iterable[str], *, kc=None, acteur: str = "acp-poste") -> List[str]:
    """Pose en ``scheduled`` (raison exacte « Pause du projet (ACP) ») les cartes ``todo``/``ready``
    données ; jamais une carte ``running`` (complete_task refuserait ensuite ``scheduled`` :
    kanban_db.py:2785-2789). Journalise chaque carte planifiée, rend leur liste."""
    planifiees: List[str] = []

    def _faire(kconn) -> None:
        for carte in cartes:
            tache = ka.get_task(kconn, carte)
            if tache is None or tache.status not in ("todo", "ready"):
                continue
            if ka.schedule_task(kconn, carte, reason=T.RAISON_PAUSE_PROJET):
                planifiees.append(carte)

    if kc is not None:
        _faire(kc)
    else:
        with ka.connexion(projet["tableau"]) as kconn:
            _faire(kconn)
    if planifiees:
        with base.transaction(conn):
            for carte in planifiees:
                base.journaliser(conn, acteur, "pause_carte", projet_id=projet["id"], cible=carte)
    return planifiees


def cartes_du_projet(conn, projet_id: str) -> List[Dict[str, Any]]:
    return [base.ligne_en_dict(l) for l in conn.execute(
        "SELECT * FROM demandes WHERE projet_id = ? ORDER BY tour, cree_le, rowid", (projet_id,))]


def reparer(conn, *, delai_s: int = 60) -> List[str]:
    """Réparation des créations interrompues (passe de l'émetteur) : projets restés en ``creation`` et
    demandes non rattachées depuis plus de ``delai_s``. Rejoue la création (idempotente par la clé)
    puis rend les projets réparés."""
    limite = base.maintenant() - delai_s
    repares: List[str] = []
    projets = conn.execute(
        "SELECT DISTINCT p.* FROM projets p JOIN demandes d ON d.projet_id = p.id "
        "WHERE d.carte IS NULL AND d.cree_le <= ? AND p.etat IN ('creation', 'actif', 'en_pause')", (limite,)).fetchall()
    for ligne in projets:
        projet = base.ligne_en_dict(ligne)
        demandes = [d for d in demandes_non_rattachees(conn, projet["id"]) if d["cree_le"] <= limite]
        creer(conn, projet, demandes, creer_tableau=True)
        with ka.connexion(projet["tableau"]) as kc:
            dernier = ka.dernier_evenement(kc)
        with base.transaction(conn):
            if projet["etat"] == "creation":
                conn.execute("UPDATE projets SET etat = 'actif', maj_le = ? WHERE id = ? AND etat = 'creation'",
                             (base.maintenant(), projet["id"]))
                conn.execute("INSERT OR IGNORE INTO curseurs (tableau, evenement, maj_le) VALUES (?, ?, ?)",
                             (projet["tableau"], dernier, base.maintenant()))
            base.journaliser(conn, "acp-poste:emetteur", "reparation", projet_id=projet["id"],
                             detail={"demandes": len(demandes)})
        if projet["etat"] == "en_pause":
            planifier_pour_la_pause(conn, projet, [d["carte"] for d in cartes_du_projet(conn, projet["id"]) if d["carte"]])
        repares.append(projet["id"])
    # Projets en « creation » sans aucune demande en attente (coupure après le rattachement).
    for ligne in conn.execute("SELECT * FROM projets WHERE etat = 'creation' AND maj_le <= ?", (limite,)).fetchall():
        projet = base.ligne_en_dict(ligne)
        if demandes_non_rattachees(conn, projet["id"]):
            continue
        with ka.connexion(projet["tableau"]) as kc:
            dernier = ka.dernier_evenement(kc)
        with base.transaction(conn):
            conn.execute("UPDATE projets SET etat = 'actif', maj_le = ? WHERE id = ? AND etat = 'creation'",
                         (base.maintenant(), projet["id"]))
            conn.execute("INSERT OR IGNORE INTO curseurs (tableau, evenement, maj_le) VALUES (?, ?, ?)",
                         (projet["tableau"], dernier, base.maintenant()))
        repares.append(projet["id"])
    return repares
