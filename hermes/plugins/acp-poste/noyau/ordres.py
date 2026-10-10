"""Ordres au poste (étape P5, cahier P5 § 4.6) : ``releve`` (« Relever maintenant »), ``pause`` et ``reprise``
(pause générale de P4, affichage seulement en P5).

Livraison AU MOINS UNE FOIS : un ordre reste dû jusqu'à son acquittement (``ordres_acquittes`` d'une
réclamation, ou réception de l'inventaire pour un ``releve`` livré) ; les genres sont idempotents. Un ordre non
acquitté au-delà de ``ordre_expiration_s`` (1 h) est abandonné et journalisé (passe de l'émetteur).

Les fonctions ``…_dans`` s'exécutent SOUS une transaction ouverte par l'appelant (route machine) ; les autres
ouvrent la leur.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from . import base

GENRES = ("releve", "pause", "reprise")


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def creer_dans(conn, machine_id: str, genre: str, auteur: str) -> int:
    if genre not in GENRES:
        raise ValueError(f"genre d'ordre inconnu : {genre}")
    curseur = conn.execute("INSERT INTO ordres (machine_id, genre, cree_le, cree_par) VALUES (?, ?, ?, ?)",
                           (machine_id, genre, base.maintenant(), auteur))
    base.journaliser(conn, auteur, "ordre", cible=machine_id, detail={"genre": genre, "ordre": curseur.lastrowid})
    return int(curseur.lastrowid)


def creer(conn, machine_id: str, genre: str, auteur: str) -> int:
    with base.transaction(conn):
        return creer_dans(conn, machine_id, genre, auteur)


def dus(conn, machine_id: str) -> List[Dict[str, Any]]:
    """Ordres ni acquittés ni abandonnés, du plus ancien au plus récent (forme du contrat ``Ordre``)."""
    lignes = conn.execute("SELECT id, genre, cree_le FROM ordres WHERE machine_id = ? AND acquitte_le IS NULL AND "
                          "abandonne_le IS NULL ORDER BY id LIMIT 32", (machine_id,)).fetchall()
    return [{"id": int(l["id"]), "genre": l["genre"], "cree_le": _iso(l["cree_le"])} for l in lignes]


def livrer_dans(conn, ids: Iterable[int]) -> None:
    maintenant = base.maintenant()
    for identifiant in ids:
        conn.execute("UPDATE ordres SET livre_le = ? WHERE id = ? AND livre_le IS NULL", (maintenant, int(identifiant)))


def acquitter_dans(conn, machine_id: str, ids: Iterable[int]) -> int:
    """Acquitte les ordres DE CETTE machine (un identifiant d'une autre machine est ignoré)."""
    maintenant = base.maintenant()
    total = 0
    for identifiant in ids:
        total += conn.execute("UPDATE ordres SET acquitte_le = ? WHERE id = ? AND machine_id = ? AND acquitte_le IS "
                              "NULL", (maintenant, int(identifiant), machine_id)).rowcount
    return total


def acquitter_releves_livres_dans(conn, machine_id: str) -> int:
    """Réception d'un inventaire : les ordres ``releve`` déjà livrés sont servis."""
    return conn.execute("UPDATE ordres SET acquitte_le = ? WHERE machine_id = ? AND genre = 'releve' AND livre_le "
                        "IS NOT NULL AND acquitte_le IS NULL AND abandonne_le IS NULL",
                        (base.maintenant(), machine_id)).rowcount


def releve_en_attente(conn, machine_id: str) -> bool:
    return conn.execute("SELECT 1 FROM ordres WHERE machine_id = ? AND genre = 'releve' AND acquitte_le IS NULL AND "
                        "abandonne_le IS NULL LIMIT 1", (machine_id,)).fetchone() is not None


def expirer(conn) -> List[int]:
    """Passe de l'émetteur : ordres non acquittés depuis plus de ``ordre_expiration_s`` → abandonnés."""
    limite = base.maintenant() - int(base.reglage(conn, "ordre_expiration_s") or 3600)
    ids = [int(l[0]) for l in conn.execute("SELECT id FROM ordres WHERE acquitte_le IS NULL AND abandonne_le IS NULL "
                                           "AND cree_le < ?", (limite,)).fetchall()]
    if ids:
        with base.transaction(conn):
            for identifiant in ids:
                conn.execute("UPDATE ordres SET abandonne_le = ? WHERE id = ? AND acquitte_le IS NULL",
                             (base.maintenant(), identifiant))
            base.journaliser(conn, "acp-poste:emetteur", "ordres_abandonnes", detail={"ordres": ids})
    return ids


def en_attente(conn, machine_id: str) -> List[Dict[str, Any]]:
    """Ordres dus, pour la page Poste (livré ou non)."""
    lignes = conn.execute("SELECT id, genre, cree_le, livre_le FROM ordres WHERE machine_id = ? AND acquitte_le IS "
                          "NULL AND abandonne_le IS NULL ORDER BY id", (machine_id,)).fetchall()
    return [{"id": int(l["id"]), "genre": l["genre"], "cree_le": int(l["cree_le"]),
             "livre": l["livre_le"] is not None} for l in lignes]
