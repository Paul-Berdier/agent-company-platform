"""Projection bornée des résultats d'un run du poste, jamais des colonnes cumulées de la carte.

Lecture de ``Run``/``get_run``/``latest_run`` vérifiée sur Hermes f97608f, kanban_db.py:696 et 4116.
La fin efface tasks.current_run_id mais conserve task_runs.claim_lock. Les métadonnées du dernier
run ne sont jamais reprises pour remplir celles d'une nouvelle exécution. Aucun flux brut exposé.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

from . import contrat_partage  # noqa: F401 — met le contrat partagé sur sys.path

from acp_poste_contrat.machine import MetadonneesExecution  # noqa: E402

_MACHINE = re.compile(r"acp-poste:(m[0-9a-f]{11})")
_VOIES = ("poste-codex", "poste-claude", "poste-integration")
_STATUTS = {"running", "scheduled", "blocked", "review", "done", "failed", "abandoned", "reclaimed", "cancelled", "timeout"}
_ISSUES = {"completed", "scheduled", "review", "review_requested", "blocked", "reclaimed", "cancelled", "failed", "timeout",
           "crashed", "abandoned", "interrupted"}


def vide(etat: str = "indisponible") -> dict[str, Any]:
    return {"schema_version": 1, "etat": etat, "provenance": None, "portee": None, "run_id": None,
            "machine_id": None, "statut": None, "issue": None, "debut": None, "fin": None,
            "metadonnees": None, "motif_metadonnees": "absentes"}


def _entier(valeur: Any) -> int | None:
    return valeur if type(valeur) is int and 0 <= valeur <= 2**62 else None


def _masquer(valeur: Any, masque: Callable[[str], str]) -> Any:
    if isinstance(valeur, str):
        return masque(valeur)
    if isinstance(valeur, dict):
        return {k: _masquer(v, masque) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_masquer(v, masque) for v in valeur]
    return valeur


def construire(demande: dict[str, Any], tache: Any, runs: Iterable[Any],
               masque: Callable[[str], str]) -> dict[str, Any]:
    """Une observation du run courant, sinon du dernier run. Une incohérence ferme la projection.

    Les métadonnées sont rapportées par l'exécutant ; leur validation structurelle ne constitue
    pas une nouvelle exécution des tests. La machine vient du verrou historique du run lui-même.
    Les valeurs facultatives absentes restent absentes, y compris session_locale et les jetons.
    """
    if demande.get("voie") not in _VOIES:
        return vide("non_pris_en_charge")
    if (tache is None or getattr(tache, "id", None) != demande.get("carte")
            or getattr(tache, "created_by", None) != "acp-poste"
            or getattr(tache, "idempotency_key", None) != demande.get("cle")):
        return vide()
    liste = list(runs)
    if any(getattr(r, "task_id", None) != tache.id or not _entier(getattr(r, "id", None))
           or _entier(getattr(r, "started_at", None)) is None for r in liste):
        return vide()
    courant = getattr(tache, "current_run_id", None)
    if courant is not None:
        correspondants = [r for r in liste if r.id == courant]
        if len(correspondants) != 1 or getattr(correspondants[0], "ended_at", None) is not None:
            return vide()
        run = correspondants[0]
        if (getattr(tache, "status", None) != "running"
                or getattr(tache, "claim_lock", None) != getattr(run, "claim_lock", None)):
            return vide()
        portee = "courante"
    else:
        if not liste:
            return vide("aucune")
        run = max(liste, key=lambda r: (r.started_at, r.id))
        if (_entier(getattr(run, "ended_at", None)) is None
                or run.ended_at < run.started_at):
            return vide()
        portee = "derniere"
    verrou = getattr(run, "claim_lock", None)
    machine = _MACHINE.fullmatch(verrou) if isinstance(verrou, str) else None
    if machine is None or getattr(run, "profile", None) != demande.get("voie"):
        return vide()
    resultat = dict(vide(), etat="observe", provenance="hermes.task_runs", portee=portee,
                    run_id=run.id, machine_id=machine.group(1), debut=run.started_at,
                    fin=_entier(getattr(run, "ended_at", None)),
                    statut=run.status if getattr(run, "status", None) in _STATUTS else None,
                    issue=run.outcome if getattr(run, "outcome", None) in _ISSUES else None)
    meta = getattr(run, "metadata", None)
    if not meta:
        return resultat
    if not isinstance(meta, dict):
        return dict(resultat, motif_metadonnees="invalides")
    # Hermes peut enrichir metadata avec ses propres artefacts ; ne jamais les réémettre ici.
    propres = {k: v for k, v in meta.items() if k in MetadonneesExecution.model_fields}
    try:
        valide = MetadonneesExecution.model_validate(propres)
        # Un résultat d'une autre carte n'est jamais présenté comme celui-ci.
        if ((demande.get("role") == "integration" and not valide.branche.startswith("hermes/projet-"))
                or (demande.get("role") != "integration" and valide.branche != "hermes/" + tache.id)):
            return dict(resultat, motif_metadonnees="invalides")
        valeurs = valide.model_dump(mode="json", exclude_unset=True)
        valeurs = _masquer(valeurs, masque)
    except Exception:  # contrat ou masquage indisponible : aucune donnée brute ne sort
        return dict(resultat, motif_metadonnees="invalides")
    return dict(resultat, metadonnees=valeurs, motif_metadonnees=None)
