"""Cartes ``poste-*`` NON émises par le greffon (cahier P4 § 12.3, décision D37).

Seul le greffon crée les cartes du poste : une carte ``poste-*`` créée à la main (tableau de bord, CLI
``hermes kanban create``) ou par un agent ne doit jamais être servie au poste. À chaque passe de
l'émetteur, sur TOUS les tableaux, une carte est refusée si elle réunit :

- un assigné ``poste-*`` ;
- le statut ``ready`` (``block_task`` n'agit que depuis ``running``/``ready`` : kanban_db.py:3208-3299 ; une
  carte ``todo`` n'est pas réclamable et sera refusée dès qu'elle passera ``ready``) ;
- une clé d'idempotence absente de ``demandes``, un créateur autre que ``acp-poste``, ou une demande
  rattachée à une AUTRE carte ou un autre tableau.

Effet : ``block_task(kind="capability", raison exacte)``, journalisé, notification ``bloquee``. À la
seconde occurrence (le propriétaire débloque), Hermes la passe en triage (kanban_db.py:3302-3328) : voulu.
**Bloquée et non archivée** : ``archived`` satisferait ses enfants (kanban_db.py:2192-2199).

:func:`demande_de_la_carte` est la même condition, exposée pour la réclamation du poste (P6).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import base, notifications
from . import kanban_adapter as ka
from . import textes as T


def demande_de_la_carte(conn, tableau: str, tache: Any) -> Optional[Dict[str, Any]]:
    """Demande qui a émis ``tache`` sur ``tableau``, ou None si la carte n'est pas du greffon."""
    cle = getattr(tache, "idempotency_key", None)
    if not cle or not str(cle).startswith(ka.PREFIXE_CLE) or getattr(tache, "created_by", None) != ka.CREATEUR:
        return None
    demande = base.ligne_en_dict(conn.execute("SELECT * FROM demandes WHERE cle = ?", (cle,)).fetchone())
    if demande is None or demande["tableau"] != tableau:
        return None
    if demande["carte"] is not None and demande["carte"] != tache.id:
        return None
    if demande["voie"] != tache.assignee:
        return None
    return demande


def balayer(conn) -> List[Tuple[str, str]]:
    """Bloque les cartes ``poste-*`` étrangères prêtes ; rend ``[(tableau, carte), …]``."""
    projets_par_tableau = {l["tableau"]: base.ligne_en_dict(l) for l in conn.execute("SELECT * FROM projets")}
    bloquees: List[Tuple[str, str]] = []
    for meta in ka.list_boards(include_archived=False):
        tableau = meta.get("slug")
        if not tableau:
            continue
        try:
            with ka.connexion(tableau) as kc:
                for tache in ka.list_tasks(kc, status="ready"):
                    if not ka.est_voie_poste(tache.assignee) or demande_de_la_carte(conn, tableau, tache) is not None:
                        continue
                    if ka.block_task(kc, tache.id, kind="capability", reason=T.RAISON_ETRANGERE):
                        bloquees.append((tableau, tache.id))
        except Exception:  # noqa: BLE001 — un tableau illisible ne bloque pas la passe
            continue
    for tableau, carte in bloquees:
        fiche = projets_par_tableau.get(tableau)
        with base.transaction(conn):
            base.journaliser(conn, "acp-poste:emetteur", "carte_etrangere_bloquee",
                             projet_id=fiche["id"] if fiche else None, cible=f"{tableau}/{carte}")
            if fiche is None:
                # Hors tableau de projet, aucun curseur d'événements : la notification part d'ici.
                notifications.enfiler_dans(conn, cle=f"bloquee:{tableau}:{carte}", genre="bloquee",
                                           texte_notif=notifications.texte(T.NOTIF_BLOQUEE_HORS_PROJET, tableau=tableau,
                                                                           carte=carte))
    return bloquees
