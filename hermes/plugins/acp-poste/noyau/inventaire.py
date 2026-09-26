"""Réception de l'inventaire du poste (étape P5, cahier P5 § 4.3, § 11) : ``POST /machine/v1/inventaire``.

Tout ou rien, SOUS la transaction ``IMMEDIATE`` de la route : garde « aucun identifiant » (le même balayage que le
poste avant l'envoi), validation par le contrat partagé (``InventairePoste``), une ligne ``releves`` par voie
(``source = "poste"``, ``machine_id``) dont le résumé ``quotas`` est calculé ICI depuis ``compteurs``
(``resume_quotas``), une ligne ``inventaires`` (le reste de l'inventaire), purges bornées qui épargnent les relevés
cités ou acceptés, acquittement des ordres ``releve`` livrés. Cadence : un inventaire par
``inventaire_intervalle_min_s`` au plus, sauf ordre ``releve`` en attente (sinon 429 et ``Retry-After``).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import base, contrat_partage, ordres, routage  # noqa: F401 — contrat_partage met le contrat sur sys.path
from . import textes as T
from .textes import RefusACP

from acp_poste_contrat.inventaire import (  # noqa: E402
    InventairePoste,
    identifiant_trouve,
    resume_quotas,
    valider_inventaire,
)

INVENTAIRES_GARDES = 200
ALERTES_MAX = 16
LIBELLES_CLI = {"codex": "Codex", "claude": "Claude Code"}


class TropFrequent(RefusACP):
    """429 : l'inventaire précédent est trop récent ; ``retry_after`` en secondes."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("trop_frequent", T.TROP_FREQUENT.format(n=retry_after))
        self.retry_after = retry_after


def iso(epoch: int) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def delai_avant_prochain(conn, machine_id: str) -> int:
    """Secondes à attendre avant d'accepter un nouvel inventaire de ce poste (0 : admis tout de suite)."""
    if ordres.releve_en_attente(conn, machine_id):
        return 0
    ligne = conn.execute("SELECT MAX(recu_le) FROM inventaires WHERE machine_id = ?", (machine_id,)).fetchone()
    if ligne is None or ligne[0] is None:
        return 0
    intervalle = int(base.reglage(conn, "inventaire_intervalle_min_s") or 60)
    return max(0, int(ligne[0]) + intervalle - base.maintenant())


def refus_contrat(detail: str) -> RefusACP:
    for prefixe in ("Inventaire refusé : ", "Relevé refusé : "):
        if detail.startswith(prefixe):
            detail = detail[len(prefixe):]
    detail = detail.strip()
    if not detail.endswith("."):
        detail += "."
    return RefusACP("requete_refusee", T.REQUETE_REFUSEE.format(detail=detail[:400]))


def valider_corps(corps: Any) -> InventairePoste:
    """Garde « aucun identifiant » puis contrat ; lève le refus 422 en français."""
    trouve = identifiant_trouve(corps)
    if trouve:
        raise refus_contrat(trouve)
    try:
        return valider_inventaire(corps)
    except ValueError as exc:
        raise refus_contrat(str(exc)) from None


def alertes_de(inventaire: InventairePoste) -> List[str]:
    """Ce que la page Poste doit dire de cet inventaire (liste de secours, échecs, versions, bac à sable)."""
    alertes: List[str] = []
    for releve in inventaire.releves:
        if releve.origine_liste == "identique_au_catalogue_embarque":
            alertes.append(T.ALERTE_LISTE_SECOURS_PROBABLE.format(v=releve.version_cli or T.INCONNU))
        elif releve.origine_liste == "catalogue_embarque":
            alertes.append(T.ALERTE_LISTE_SECOURS.format(v=releve.version_cli or T.INCONNU))
        if releve.etat not in (None, "ok"):
            alertes.append(T.ALERTE_VOIE_EN_ECHEC.format(voie=releve.voie, etat=releve.etat,
                                                          detail=releve.detail or T.INCONNU))
    for cle, version in sorted(inventaire.versions.items()):
        if not version.conforme:
            alertes.append(T.ALERTE_VERSION_CLI.format(cli=LIBELLES_CLI.get(cle, cle), lue=version.lue or T.INCONNU,
                                                       testee=version.testee))
    if not inventaire.bac_a_sable_codex.ecriture_admise:
        alertes.append(T.ALERTE_BAC_A_SABLE.format(raison=inventaire.bac_a_sable_codex.raison or T.INCONNU))
    return [a[:300] for a in alertes[:ALERTES_MAX]]


def recevoir_dans(conn, machine_id: str, corps: Any, *, inventaire: Optional[InventairePoste] = None) -> Dict[str, Any]:
    """Enregistre l'inventaire (voir l'en-tête) ; rend la réponse ``ReponseInventaire``."""
    inventaire = inventaire or valider_corps(corps)
    maintenant = base.maintenant()
    releves: Dict[str, int] = {}
    for releve in inventaire.releves:
        donnees = releve.model_dump(mode="json")
        resume = resume_quotas(releve.compteurs)
        donnees["quotas"] = resume.model_dump(mode="json") if resume is not None else None
        releves[releve.voie] = routage.enregistrer_releve_dans(conn, donnees, machine_id=machine_id, recu_le=maintenant)
        routage.purger_releves_dans(conn, releve.voie)
    alertes = alertes_de(inventaire)
    reste = inventaire.model_dump(mode="json")
    reste.pop("releves")
    reste["releves"] = releves
    reste["alertes"] = alertes
    contenu = json.dumps(reste, ensure_ascii=False, sort_keys=True)
    conn.execute("INSERT INTO inventaires (machine_id, recu_le, releve_le, empreinte, contenu) VALUES (?, ?, ?, ?, ?)",
                 (machine_id, maintenant, int(inventaire.releve_le.timestamp()),
                  hashlib.sha256(contenu.encode("utf-8")).hexdigest(), contenu))
    conn.execute("DELETE FROM inventaires WHERE id NOT IN (SELECT id FROM inventaires ORDER BY id DESC LIMIT ?)",
                 (INVENTAIRES_GARDES,))
    servis = ordres.acquitter_releves_livres_dans(conn, machine_id)
    base.journaliser(conn, f"poste:{machine_id}", "inventaire", cible=machine_id,
                     detail={"releves": releves, "ordres_servis": servis, "alertes": len(alertes)})
    return {"recu_le": iso(maintenant), "releves": releves, "alertes": alertes}


def dernier(conn, machine_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Dernier inventaire reçu (d'un poste donné, sinon de tout poste), relevés non compris ; None si aucun."""
    if machine_id:
        ligne = conn.execute("SELECT * FROM inventaires WHERE machine_id = ? ORDER BY id DESC LIMIT 1",
                             (machine_id,)).fetchone()
    else:
        ligne = conn.execute("SELECT * FROM inventaires ORDER BY id DESC LIMIT 1").fetchone()
    if ligne is None:
        return None
    try:
        contenu = json.loads(ligne["contenu"])
    except ValueError:
        contenu = None
    return {"id": int(ligne["id"]), "machine_id": ligne["machine_id"], "recu_le": int(ligne["recu_le"]),
            "releve_le": int(ligne["releve_le"]), "contenu": contenu,
            "alertes": list((contenu or {}).get("alertes") or [])}
