"""Lecture des flux des agents (cahier P6 § 6.3) : JSONL de ``codex exec --json`` et ``stream-json`` de
``claude -p``, puis la sortie structurée commune.

Rien de ces flux n'est journalisé ni transmis brut : l'exécutant n'en retient que la session (reprise du fil), le
modèle servi, les jetons, les limites de débit, l'erreur éventuelle et la sortie structurée, validée.

- **Codex 0.156.1** (``exec/src/exec_events.rs``) : ``thread.started`` (``thread_id`` = session), ``turn.completed``
  (``usage``), ``turn.failed`` et ``error`` (message), ``item.completed`` de type ``agent_message``. Le flux ne publie
  **ni le modèle servi ni le palier** : ils restent « inconnus » (``None``), jamais supposés.
- **Claude Code** : ``system``/``init`` (``model``, ``session_id``, ``tools``), ``rate_limit_event``
  (``rate_limit_info`` : ``status``, ``resetsAt``, ``utilization``, et le type de fenêtre s'il est donné :
  ``rateLimitType`` ou ``rate_limit_type``, nom exact SUPPOSÉ, cahier C3), ``result`` (``structured_output``,
  ``usage``, ``is_error``, ``session_id``).

Sortie structurée (schéma imposé aux deux CLI) :
``{"issue": "termine|question|echec", "resume", "question", "verdict", "corrections"}``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterable

from acp_poste_contrat.machine import RESUME_MAX

LIGNES_MAX = 50_000
LIGNE_MAX = 1024 * 1024
TEXTE_MAX = 4000
ISSUES = ("termine", "question", "echec")
OUTILS_CLAUDE_INTERDITS = ("Bash", "BashOutput", "KillShell", "WebFetch", "WebSearch", "Task", "NotebookEdit")
_LIMITE = re.compile(r"(?i)usage limit|rate limit|quota|too many requests|429")
# Caractères de contrôle retirés des textes de l'agent (tabulation, saut de ligne et retour chariot gardés) : le NUL est
# refusé par le contrat, et il faisait échouer le commit (« embedded null byte ») ; les autres n'ont aucun sens dans un
# résumé ni dans un message de commit (relecture de P6).
_CONTROLES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

SCHEMA_SORTIE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["issue", "resume", "question", "verdict", "corrections"],
    "properties": {
        "issue": {"type": "string", "enum": list(ISSUES)},
        "resume": {"type": "string", "maxLength": RESUME_MAX},
        "question": {"type": ["string", "null"], "maxLength": TEXTE_MAX},
        "verdict": {"type": ["string", "null"], "enum": ["accepte", "corrections", None]},
        "corrections": {"type": ["string", "null"], "maxLength": RESUME_MAX},
    },
}


class SortieInvalide(ValueError):
    """Sortie structurée absente ou hors schéma (message français, sans le contenu)."""


@dataclass
class SortieAgent:
    issue: str
    resume: str
    question: str | None = None
    verdict: str | None = None
    corrections: str | None = None


def _texte(valeur: Any, maximum: int) -> str | None:
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise SortieInvalide("Sortie structurée de l'agent : champ texte attendu.")
    valeur = _CONTROLES.sub("", valeur).strip()
    if len(valeur) > maximum:
        valeur = valeur[: maximum - 12].rstrip() + " [tronqué]"
    return valeur or None


def valider_sortie(document: Any, *, relecture: bool) -> SortieAgent:
    """Sortie de l'agent, contrôlée : issue connue, résumé non vide, question exigée pour l'issue ``question``,
    verdict réservé aux relectures, consigne de correction exigée avec le verdict ``corrections``."""
    if isinstance(document, str):
        try:
            document = json.loads(document)
        except ValueError:
            raise SortieInvalide("Sortie structurée de l'agent illisible (JSON attendu).") from None
    if not isinstance(document, dict):
        raise SortieInvalide("Sortie structurée de l'agent absente.")
    issue = document.get("issue")
    if issue not in ISSUES:
        raise SortieInvalide("Sortie structurée de l'agent : issue inconnue.")
    resume = _texte(document.get("resume"), RESUME_MAX)
    if not resume:
        raise SortieInvalide("Sortie structurée de l'agent : résumé vide.")
    question = _texte(document.get("question"), TEXTE_MAX)
    if issue == "question" and not question:
        raise SortieInvalide("Sortie structurée de l'agent : question annoncée mais absente.")
    verdict = document.get("verdict")
    if verdict not in (None, "accepte", "corrections"):
        raise SortieInvalide("Sortie structurée de l'agent : verdict inconnu.")
    corrections = _texte(document.get("corrections"), RESUME_MAX)
    if relecture and issue == "termine":
        if verdict is None:
            raise SortieInvalide("Sortie structurée d'une relecture : verdict absent.")
        if (verdict == "corrections") != bool(corrections):
            raise SortieInvalide("Sortie structurée d'une relecture : la consigne de correction accompagne le "
                                 "verdict « corrections », et lui seul.")
    else:
        verdict, corrections = None, None
    return SortieAgent(issue=issue, resume=resume, question=question if issue == "question" else None,
                       verdict=verdict, corrections=corrections)


def _lignes_json(lignes: Iterable[bytes | str]) -> Iterable[dict[str, Any]]:
    for rang, ligne in enumerate(lignes):
        if rang >= LIGNES_MAX:
            break
        if isinstance(ligne, bytes):
            if len(ligne) > LIGNE_MAX:
                continue
            ligne = ligne.decode("utf-8", "replace")
        ligne = ligne.strip()
        if not ligne.startswith("{"):
            continue
        try:
            objet = json.loads(ligne)
        except (ValueError, RecursionError):
            continue
        if isinstance(objet, dict):
            yield objet


def _entier(valeur: Any) -> int | None:
    return valeur if type(valeur) is int and valeur >= 0 else None


@dataclass
class FluxCodex:
    session: str | None = None
    jetons: dict[str, int | None] = field(default_factory=lambda: {"entree": None, "sortie": None, "cache": None})
    erreur: str | None = None
    limite_atteinte: bool = False
    dernier_message: str | None = None
    tours_termines: int = 0
    commandes: int = 0


def lire_flux_codex(lignes: Iterable[bytes | str]) -> FluxCodex:
    flux = FluxCodex()
    totaux = {"entree": 0, "sortie": 0, "cache": 0}
    vus = False
    for evenement in _lignes_json(lignes):
        genre = evenement.get("type")
        if genre == "thread.started" and isinstance(evenement.get("thread_id"), str):
            flux.session = evenement["thread_id"][:128]
        elif genre == "turn.completed":
            flux.tours_termines += 1
            usage = evenement.get("usage") if isinstance(evenement.get("usage"), dict) else {}
            for cle, source in (("entree", "input_tokens"), ("sortie", "output_tokens"),
                                ("cache", "cached_input_tokens")):
                valeur = _entier(usage.get(source))
                if valeur is not None:
                    totaux[cle] += valeur
                    vus = True
        elif genre in ("turn.failed", "error"):
            message = (evenement.get("error") or {}).get("message") if genre == "turn.failed" else \
                evenement.get("message")
            if isinstance(message, str):
                flux.erreur = message[:300]
                flux.limite_atteinte = flux.limite_atteinte or bool(_LIMITE.search(message))
        elif genre == "item.completed" and isinstance(evenement.get("item"), dict):
            item = evenement["item"]
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                flux.dernier_message = item["text"][: 64 * 1024]
            elif item.get("type") == "command_execution":
                flux.commandes += 1
    if vus:
        flux.jetons = dict(totaux)
    return flux


@dataclass
class LimiteClaude:
    statut: str
    remise: datetime | None
    utilisation: float | None
    fenetre: str | None
    observe_le: datetime

    def json(self) -> dict[str, Any]:
        return {"statut": self.statut, "remise": self.remise.strftime("%Y-%m-%dT%H:%M:%SZ") if self.remise else None,
                "utilisation": self.utilisation, "fenetre": self.fenetre,
                "observe_le": self.observe_le.strftime("%Y-%m-%dT%H:%M:%SZ")}


@dataclass
class FluxClaude:
    session: str | None = None
    modele_servi: str | None = None
    outils: list[str] = field(default_factory=list)
    jetons: dict[str, int | None] = field(default_factory=lambda: {"entree": None, "sortie": None, "cache": None})
    limite: LimiteClaude | None = None
    resultat: dict[str, Any] | None = None
    erreur: str | None = None
    limite_atteinte: bool = False

    @property
    def outils_interdits(self) -> list[str]:
        return [o for o in self.outils if o in OUTILS_CLAUDE_INTERDITS or o.startswith("mcp__")]


_FENETRE = re.compile(r"[a-z0-9][a-z0-9_]{0,31}")


def _limite(info: dict[str, Any], maintenant: datetime) -> LimiteClaude | None:
    statut = info.get("status")
    if statut not in ("allowed", "allowed_warning", "rejected"):
        return None
    remise = info.get("resetsAt")
    instant = None
    if type(remise) in (int, float) and 0 < remise < 10**11:
        instant = datetime.fromtimestamp(float(remise), tz=UTC)
    utilisation = info.get("utilization")
    utilisation = float(utilisation) if type(utilisation) in (int, float) and 0 <= utilisation <= 1.5 else None
    fenetre = info.get("rateLimitType", info.get("rate_limit_type"))
    fenetre = fenetre if isinstance(fenetre, str) and _FENETRE.fullmatch(fenetre) else None
    return LimiteClaude(statut=statut, remise=instant, utilisation=utilisation, fenetre=fenetre, observe_le=maintenant)


def lire_flux_claude(lignes: Iterable[bytes | str], *, maintenant: datetime | None = None) -> FluxClaude:
    flux = FluxClaude()
    instant = maintenant or datetime.now(UTC)
    for evenement in _lignes_json(lignes):
        genre = evenement.get("type")
        if genre == "system" and evenement.get("subtype") == "init":
            if isinstance(evenement.get("model"), str):
                flux.modele_servi = evenement["model"][:128]
            if isinstance(evenement.get("session_id"), str):
                flux.session = evenement["session_id"][:128]
            outils = evenement.get("tools")
            if isinstance(outils, list):
                flux.outils = [o for o in outils if isinstance(o, str)][:200]
        elif genre == "rate_limit_event" and isinstance(evenement.get("rate_limit_info"), dict):
            limite = _limite(evenement["rate_limit_info"], instant)
            if limite is not None:
                flux.limite = limite
                flux.limite_atteinte = flux.limite_atteinte or limite.statut == "rejected"
        elif genre == "result":
            flux.resultat = evenement
            if isinstance(evenement.get("session_id"), str):
                flux.session = evenement["session_id"][:128]
            usage = evenement.get("usage") if isinstance(evenement.get("usage"), dict) else {}
            cache = [_entier(usage.get(c)) for c in ("cache_read_input_tokens", "cache_creation_input_tokens")]
            flux.jetons = {"entree": _entier(usage.get("input_tokens")), "sortie": _entier(usage.get("output_tokens")),
                           "cache": sum(c for c in cache if c is not None) if any(c is not None for c in cache)
                           else None}
            if evenement.get("is_error") or evenement.get("subtype") != "success":
                erreurs = evenement.get("errors")
                texte = erreurs[0] if isinstance(erreurs, list) and erreurs and isinstance(erreurs[0], str) else \
                    str(evenement.get("subtype") or "erreur")
                flux.erreur = texte[:300]
                if evenement.get("api_error_status") == 429 or _LIMITE.search(texte):
                    flux.limite_atteinte = True
    return flux


def sortie_claude(flux: FluxClaude) -> Any:
    """Sortie structurée d'un résultat Claude (``structured_output``), sinon le texte du résultat (à valider)."""
    if flux.resultat is None:
        return None
    structure = flux.resultat.get("structured_output")
    if structure is not None:
        return structure
    return flux.resultat.get("result")
