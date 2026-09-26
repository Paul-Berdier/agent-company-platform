"""Présence du poste Windows (cahier P4 § 12.4) et état du poste (outil ``poste_etat``, route ``/v1/poste``).

- :func:`enregistrer` : appelée par P5 (long-poll, battements) ; en P4, par le poste simulé des tests seulement.
- :func:`evaluer` : dans chaque passe de l'émetteur. Au-delà de ``seuil_hors_ligne_s`` sans vue, le poste passe
  ``hors_ligne`` et UNE notification part (clé ``hors_ligne:<machine>:<passage>``). Un retour en ligne ouvre un
  nouveau passage.
- Jamais vu : ``non_configure``, AUCUNE notification. ``stranded_in_ready`` n'émet aucun événement : la
  présence est la seule source (plan § 6).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from . import base, notifications, routage
from . import kanban_adapter as ka
from . import textes as T

SOURCES = ("longpoll", "battement", "simule")
_MACHINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def enregistrer(conn, machine_id: str, source: str) -> Dict[str, Any]:
    if not isinstance(machine_id, str) or not _MACHINE.match(machine_id):
        raise ValueError("identifiant de machine invalide")
    if source not in SOURCES:
        raise ValueError(f"source de présence inconnue : {source}")
    maintenant = base.maintenant()
    with base.transaction(conn):
        ligne = conn.execute("SELECT * FROM presence WHERE machine_id = ?", (machine_id,)).fetchone()
        if ligne is None:
            conn.execute("INSERT INTO presence (machine_id, derniere_vue, source, passage) VALUES (?, ?, ?, 1)",
                         (machine_id, maintenant, source))
        elif ligne["hors_ligne_depuis"] is not None:
            conn.execute("UPDATE presence SET derniere_vue = ?, source = ?, passage = passage + 1, "
                         "hors_ligne_depuis = NULL, hors_ligne_notifie = 0 WHERE machine_id = ?",
                         (maintenant, source, machine_id))
            base.journaliser(conn, f"poste:{machine_id}", "retour_en_ligne", cible=machine_id)
        else:
            conn.execute("UPDATE presence SET derniere_vue = ?, source = ? WHERE machine_id = ?",
                         (maintenant, source, machine_id))
    return base.ligne_en_dict(conn.execute("SELECT * FROM presence WHERE machine_id = ?", (machine_id,)).fetchone())


def cartes_en_attente(conn) -> int:
    """Cartes du poste prêtes et non réclamées, sur tous les tableaux de projet (lecture kanban)."""
    total = 0
    for p in conn.execute("SELECT tableau FROM projets WHERE etat IN ('actif', 'en_pause', 'creation')").fetchall():
        try:
            with ka.connexion(p["tableau"]) as kc:
                total += sum(1 for t in ka.list_tasks(kc, status="ready") if ka.est_voie_poste(t.assignee))
        except Exception:  # noqa: BLE001 — tableau illisible : non compté (le compte est un minimum)
            continue
    return total


def evaluer(conn) -> List[str]:
    """Passe les machines silencieuses en ``hors_ligne`` et enfile UNE notification par passage."""
    maintenant = base.maintenant()
    seuil = int(base.reglage(conn, "seuil_hors_ligne_s") or 180)
    notifiees: List[str] = []
    for ligne in conn.execute("SELECT * FROM presence").fetchall():
        if maintenant - int(ligne["derniere_vue"]) <= seuil or ligne["hors_ligne_notifie"]:
            continue
        depuis = int(ligne["derniere_vue"])
        texte = notifications.texte(T.NOTIF_HORS_LIGNE, heure=routage.date_lisible(depuis, "%H:%M"),
                                    n=cartes_en_attente(conn))
        with base.transaction(conn):
            conn.execute("UPDATE presence SET hors_ligne_depuis = ?, hors_ligne_notifie = 1 WHERE machine_id = ?",
                         (depuis, ligne["machine_id"]))
            notifications.enfiler_dans(conn, cle=f"hors_ligne:{ligne['machine_id']}:{ligne['passage']}",
                                       genre="hors_ligne", texte_notif=texte)
            base.journaliser(conn, "acp-poste:emetteur", "hors_ligne", cible=ligne["machine_id"])
        notifiees.append(ligne["machine_id"])
    return notifiees


def etat_poste(conn) -> Dict[str, Any]:
    """``non_configure`` (jamais vu), ``en_ligne`` ou ``hors_ligne`` ; jamais une valeur inventée."""
    lignes = conn.execute("SELECT * FROM presence ORDER BY derniere_vue DESC").fetchall()
    resultat: Dict[str, Any] = {"pause_reclamations": bool(base.reglage(conn, "pause_reclamations"))}
    try:
        resultat["cartes_en_attente"] = cartes_en_attente(conn)
    except Exception:  # noqa: BLE001
        resultat["cartes_en_attente"] = None
    if not lignes:
        resultat.update(etat="non_configure", derniere_vue=None, hors_ligne_depuis=None, machine=None,
                        message=T.POSTE_JAMAIS_VU)
        return resultat
    ligne = lignes[0]
    seuil = int(base.reglage(conn, "seuil_hors_ligne_s") or 180)
    en_ligne = base.maintenant() - int(ligne["derniere_vue"]) <= seuil
    resultat.update(etat="en_ligne" if en_ligne else "hors_ligne", machine=ligne["machine_id"],
                    derniere_vue=ligne["derniere_vue"], derniere_vue_lisible=routage.date_lisible(ligne["derniere_vue"]),
                    hors_ligne_depuis=None if en_ligne else int(ligne["hors_ligne_depuis"] or ligne["derniere_vue"]),
                    source=ligne["source"])
    return resultat
