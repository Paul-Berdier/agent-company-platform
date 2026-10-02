"""Attentes de quota (étape P6, cahier P6 § 5.6) : une carte que l'exécutant a planifiée sur ``bloquer(quota)``
(``schedule_task``) est débloquée (``unblock_task``) au premier passage du répartiteur qui suit l'heure de remise à
zéro annoncée (``reprise_le`` ; sans heure annoncée, maintenant + 1 h).

Appelée par l'émetteur sur ``on_kanban_dispatch_tick``, dans la passerelle (P4 § 12.4) : 60 s au plus après l'heure
dite (``dispatch_interval_seconds``). Rien n'est débloqué si la carte n'est plus planifiée POUR LE QUOTA (raison
exacte) : une pause de projet ou une question ne se lève jamais ici. Un projet en pause garde l'attente jusqu'à sa
reprise."""

from __future__ import annotations

from typing import List

from . import base, projets
from . import kanban_adapter as ka

PREFIXE_RAISON = "Quota de l'abonnement (ACP)"


def _derniere_raison(kc, carte: str):
    raison = None
    for evenement in ka.list_events(kc, carte):
        if evenement.kind == "scheduled":
            charge = evenement.payload if isinstance(evenement.payload, dict) else {}
            raison = charge.get("reason")
    return raison


def debloquer(conn) -> List[str]:
    """Débloque les attentes échues ; rend ``["<tableau>/<carte>", …]``."""
    debloquees: List[str] = []
    for ligne in [base.ligne_en_dict(l) for l in conn.execute(
            "SELECT * FROM attentes WHERE reprise_le <= ? ORDER BY reprise_le", (base.maintenant(),)).fetchall()]:
        fiche = projets.projet(conn, ligne["tableau"])
        if fiche is not None and fiche["etat"] == "en_pause":
            continue  # gardée : la reprise du projet la retrouvera échue
        fait = False
        if fiche is not None and fiche["etat"] == "actif":
            with ka.connexion(ligne["tableau"]) as kc:
                tache = ka.get_task(kc, ligne["carte"])
                raison = _derniere_raison(kc, ligne["carte"]) if tache is not None else None
                if tache is not None and tache.status == "scheduled" and str(raison or "").startswith(PREFIXE_RAISON):
                    fait = bool(ka.unblock_task(kc, ligne["carte"]))
        with base.transaction(conn):
            conn.execute("DELETE FROM attentes WHERE tableau = ? AND carte = ?", (ligne["tableau"], ligne["carte"]))
            if fait:
                base.journaliser(conn, "acp-poste:emetteur", "attente_quota_levee",
                                 projet_id=fiche["id"] if fiche else None, cible=ligne["carte"])
        if fait:
            debloquees.append(f"{ligne['tableau']}/{ligne['carte']}")
    return debloquees
