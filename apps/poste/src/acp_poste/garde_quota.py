"""Gardes de l'exécutant avant toute réclamation (cahier P6 § 6.1, points 4 et 5 ; décisions D84 et D85).

**Quotas** (garde à 90 %, jamais un contournement) :

- voie Codex retirée si la fenêtre la plus chargée du dernier relevé ``account/rateLimits/read`` atteint 90 % ;
- voie Claude retirée si le dernier ``rate_limit_event`` vaut ``rejected``, ou si ``utilization`` atteint 0,9, tant
  que l'heure de remise (``resetsAt``) n'est pas passée ;
- sans relevé (aucune exécution Claude observée) : la voie reste ouverte, et la page Quotas dit « garde inopérante
  tant qu'aucune exécution n'a été observée » (le relevé publié est en échec ``unavailable`` avec cette phrase).

**Budget du jour** (D84, D85) : au plus ``cartes_par_jour`` cartes et ``heures_agent_par_jour`` heures d'agent par
jour UTC ; compteurs persistants (``/donnees/acp/etat/compteurs.json``), remis à zéro au changement de jour.

Le dernier ``rate_limit_event`` est rangé dans ``/donnees/acp/etat/quotas-claude.json`` et publié dans l'inventaire
(source ``claude_code_rate_limit_event``, une fenêtre à la fois : clé = type de la fenêtre s'il est donné, sinon
``sans_type``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from acp_poste_contrat.quotas import SubscriptionQuotaReport

from .coffre import ecrire_atomiquement
from .evenements import LimiteClaude

SEUIL = 0.9
CLAUDE_INCONNU = ("Aucune exécution Claude observée sur l'exécutant : quotas inconnus, garde inopérante tant "
                  "qu'aucune exécution n'a été observée.")


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _instant(texte: Any) -> datetime | None:
    if not isinstance(texte, str):
        return None
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


# ------------------------------------------------------------------ Codex


def charge_codex(compteurs: Iterable[dict[str, Any]] | None) -> float | None:
    """Pourcentage le plus élevé des fenêtres d'un relevé Codex réussi, ou ``None`` si inconnu."""
    plus_haut = None
    for compteur in compteurs or ():
        if not isinstance(compteur, dict) or compteur.get("status") != "ok":
            continue
        for fenetre in compteur.get("windows") or ():
            valeur = fenetre.get("used_percent") if isinstance(fenetre, dict) else None
            if type(valeur) in (int, float):
                plus_haut = valeur if plus_haut is None else max(plus_haut, valeur)
        if compteur.get("limit_reached") is True:
            plus_haut = max(plus_haut or 0, 100)
    return plus_haut


def codex_ouverte(compteurs: Iterable[dict[str, Any]] | None) -> tuple[bool, str | None]:
    charge = charge_codex(compteurs)
    if charge is not None and charge >= SEUIL * 100:
        return False, f"Garde de quota : fenêtre Codex à {charge:g} % (seuil 90 %) : voie Codex retirée."
    return True, None


# ------------------------------------------------------------------ Claude


@dataclass
class QuotasClaude:
    """Dernier ``rate_limit_event`` observé, persistant."""

    fichier: Path

    def lire(self) -> dict[str, Any] | None:
        try:
            donnees = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return donnees if isinstance(donnees, dict) and donnees.get("statut") else None

    def noter(self, limite: LimiteClaude | None) -> None:
        if limite is None:
            return
        ecrire_atomiquement(self.fichier, json.dumps(limite.json(), ensure_ascii=False).encode("utf-8"))

    def ouverte(self, maintenant: datetime | None = None) -> tuple[bool, str | None, datetime | None]:
        """(ouverte, raison, remise) d'après le dernier événement ; une remise passée rouvre la voie."""
        instant = maintenant or datetime.now(UTC)
        donnees = self.lire()
        if donnees is None:
            return True, None, None
        remise = _instant(donnees.get("remise"))
        if remise is not None and remise <= instant:
            return True, None, None
        utilisation = donnees.get("utilisation")
        if donnees.get("statut") == "rejected":
            return False, "Garde de quota : limite Claude atteinte (rate_limit_event « rejected ») : voie Claude " \
                          "retirée jusqu'à la remise.", remise
        if type(utilisation) in (int, float) and utilisation >= SEUIL:
            return False, (f"Garde de quota : fenêtre Claude à {utilisation * 100:g} % (seuil 90 %) : voie Claude "
                           "retirée jusqu'à la remise."), remise
        return True, None, None

    def releve(self) -> SubscriptionQuotaReport:
        """Relevé publié (contrat des quotas, source ``claude_code_rate_limit_event``)."""
        donnees = self.lire()
        if donnees is None:
            return SubscriptionQuotaReport.model_validate({
                "provider": "claude_code", "status": "unavailable", "source": "claude_code_rate_limit_event",
                "plan": None, "windows": [], "credits": None, "limit_reached": None, "reached_type": None,
                "observed_at": _iso(datetime.now(UTC)), "detail": CLAUDE_INCONNU})
        utilisation = donnees.get("utilisation")
        pourcentage = None
        if type(utilisation) in (int, float):
            pourcentage = round(min(100.0, max(0.0, float(utilisation) * 100)), 1)
        return SubscriptionQuotaReport.model_validate({
            "provider": "claude_code", "status": "ok", "source": "claude_code_rate_limit_event", "plan": None,
            "limit_id": "default",
            "windows": [{"key": donnees.get("fenetre") or "sans_type", "used_percent": pourcentage,
                         "window_minutes": None, "resets_at": donnees.get("remise")}],
            "credits": None, "limit_reached": donnees.get("statut") == "rejected", "reached_type": None,
            "observed_at": donnees.get("observe_le") or _iso(datetime.now(UTC)), "detail": None})


# ------------------------------------------------------------------ budget du jour


@dataclass
class Budget:
    fichier: Path
    cartes_par_jour: int
    heures_par_jour: int

    def _lire(self, jour: str) -> dict[str, Any]:
        try:
            donnees = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            donnees = {}
        if not isinstance(donnees, dict) or donnees.get("jour") != jour:
            return {"jour": jour, "cartes": 0, "secondes_agent": 0}
        return {"jour": jour, "cartes": int(donnees.get("cartes") or 0),
                "secondes_agent": int(donnees.get("secondes_agent") or 0)}

    def etat(self, maintenant: datetime | None = None) -> dict[str, Any]:
        return self._lire((maintenant or datetime.now(UTC)).strftime("%Y-%m-%d"))

    def ouvert(self, maintenant: datetime | None = None) -> tuple[bool, str | None]:
        etat = self.etat(maintenant)
        if etat["cartes"] >= self.cartes_par_jour:
            return False, f"Plafond du jour atteint : {etat['cartes']} cartes (au plus {self.cartes_par_jour}, D85)."
        if etat["secondes_agent"] >= self.heures_par_jour * 3600:
            return False, (f"Plafond du jour atteint : {self.heures_par_jour} h d'agent (D85) : reprise demain, "
                           "heure UTC.")
        return True, None

    def compter(self, *, carte: bool = False, secondes: float = 0.0, maintenant: datetime | None = None) -> None:
        etat = self.etat(maintenant)
        etat["cartes"] += 1 if carte else 0
        etat["secondes_agent"] += max(0, int(secondes))
        ecrire_atomiquement(self.fichier, json.dumps(etat).encode("utf-8"))
