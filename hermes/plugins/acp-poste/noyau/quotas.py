"""Vue des quotas par voie (étape P5, cahier P5 § 12.5) : ``GET /v1/quotas``.

Chaque compteur est celui du DERNIER relevé de la voie (``compteurs``, contrat ``SubscriptionQuotaReport``), servi
sous la forme ``SubscriptionQuotaView`` du contrat (part restante déduite de la seule part utilisée relevée). Rien
n'est estimé : sans relevé, ``inconnu`` ; au-delà de ``releve_perime_s`` (2 h), ``perime`` ; un relevé en échec
garde son ``detail`` français. Hermes : « même enveloppe que Codex » seulement si ``poste.toml`` le déclare.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from . import base, contrat_partage, routage  # noqa: F401 — contrat_partage met le contrat sur sys.path
from . import kanban_adapter as ka
from . import textes as T

from acp_poste_contrat.quotas import SubscriptionQuotaView  # noqa: E402

SOURCES = {"poste-codex": "codex_app_server", "poste-claude": "ligne_etat_sessions_proprietaire"}


def _vues(releve, *, machine_id: str, nom: str, recu_le: int, perime: bool) -> List[Dict[str, Any]]:
    recu = datetime.fromtimestamp(int(recu_le), tz=timezone.utc)
    vues = []
    for compteur in releve.compteurs:
        vue = SubscriptionQuotaView.from_report(compteur, worker_id=machine_id, worker_name=nom, received_at=recu,
                                                stale=perime)
        vues.append(vue.model_dump(mode="json"))
    return vues


def vue(conn) -> Dict[str, Any]:
    maintenant = base.maintenant()
    perime_s = int(base.reglage(conn, "releve_perime_s") or 7200)
    seuil = int(base.reglage(conn, "seuil_quota_pct") or 90)
    resultat: Dict[str, Any] = {}
    enveloppe = None
    for voie in ka.VOIES_POSTE:
        dernier = routage.dernier_releve(conn, voie)
        bloc: Dict[str, Any] = {"etat": "inconnu", "releve_le": None, "compteurs": [], "seuil_pct": seuil,
                                "source": SOURCES[voie]}
        if voie == "poste-claude":
            bloc["source_libelle"] = T.QUOTAS_SOURCE_CLAUDE
        if dernier is not None:
            releve_id, releve, releve_le = dernier
            ligne = conn.execute("SELECT machine_id, recu_le FROM releves WHERE id = ?", (releve_id,)).fetchone()
            contexte = routage.contexte_poste(conn, releve_id) or {}
            poste = contexte.get("poste") or {}
            if enveloppe is None and isinstance(poste.get("hermes_meme_enveloppe_que_codex"), bool):
                enveloppe = poste["hermes_meme_enveloppe_que_codex"]
            perime = maintenant - releve_le > perime_s
            bloc.update(etat="perime" if perime else "releve", releve_le=releve_le,
                        releve_le_lisible=routage.date_lisible(releve_le), releve_id=releve_id,
                        etat_releve=releve.etat, detail=releve.detail, source_releve=releve.source,
                        resume=releve.quotas.model_dump(mode="json") if releve.quotas else None,
                        compteurs=_vues(releve, machine_id=(ligne["machine_id"] if ligne else None) or "releve-factice",
                                        nom=poste.get("nom") or T.INCONNU, recu_le=int(ligne["recu_le"]) if ligne
                                        else releve_le, perime=perime))
        resultat[voie] = bloc
    resultat["hermes"] = ({"etat": "meme_enveloppe_que_codex", "libelle": T.QUOTAS_HERMES_MEME_ENVELOPPE}
                          if enveloppe else {"etat": "inconnu", "libelle": T.INCONNU})
    return resultat
