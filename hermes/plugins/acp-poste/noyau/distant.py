"""Politique d'exécution distante d'ACP 2.

L'identité et l'inventaire du serveur restent ceux du protocole existant.
Ce contrôle n'est pas une attestation matérielle d'hébergement : il refuse
l'ancien poste Windows et un inventaire absent, sans supprimer leurs données.
Les gardes d'isolation, de compte, de quota et de dépôt s'appliquent ensuite.
"""

from __future__ import annotations

import json
from typing import Any, Optional

INVENTAIRE_ABSENT = (
    "Le serveur d'exécution n'a pas encore publié son inventaire. "
    "Vérifiez sa disponibilité dans Paramètres."
)
EXECUTION_LOCALE_REFUSEE = (
    "ACP exécute les missions uniquement sur un serveur distant Linux. "
    "Ce PC ne peut pas recevoir de travail ; configurez le serveur dans Paramètres."
)
SERVEUR_ABSENT = (
    "Aucun serveur d'exécution actif. La connexion à ACP reste disponible ; "
    "configurez le serveur dans Paramètres."
)


def raison_inventaire(inventaire: Any) -> Optional[str]:
    """Raison du refus distant, indépendamment des droits d'exécution du moteur."""
    if not isinstance(inventaire, dict) or not isinstance(inventaire.get("poste"), dict):
        return INVENTAIRE_ABSENT
    poste = inventaire["poste"]
    if poste.get("plateforme") != "linux" or poste.get("hote") != "railway":
        return EXECUTION_LOCALE_REFUSEE
    return None


def raison_refus(conn, machine_id: str) -> Optional[str]:
    """Relit l'identité active et son DERNIER inventaire, jamais un ancien verdict."""
    machine = conn.execute("SELECT etat FROM machines WHERE id = ?", (machine_id,)).fetchone()
    if machine is None or machine["etat"] != "actif":
        return SERVEUR_ABSENT
    ligne = conn.execute(
        "SELECT contenu FROM inventaires WHERE machine_id = ? ORDER BY id DESC LIMIT 1",
        (machine_id,),
    ).fetchone()
    try:
        inventaire = json.loads(ligne["contenu"]) if ligne is not None else None
    except (ValueError, TypeError):
        inventaire = None
    return raison_inventaire(inventaire)
