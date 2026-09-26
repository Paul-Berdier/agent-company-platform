"""Contrat du relevé du poste (« inventaire ») : modèles, efforts, paliers, quotas et dépôts autorisés
d'une voie (``poste-codex`` ou ``poste-claude``), étape P4 du plan d'autonomie (décision D21).

Une seule source pour les deux côtés :

- le **poste** (P5) le produit à partir de ce que Codex CLI (``model/list`` de l'app-server) et Claude
  Code déclarent, puis le publie sur ``/machine/v1/inventaire`` ;
- le **greffon** ``acp-poste`` le valide avant de l'enregistrer (table ``releves``) et ne route une étape
  que vers un modèle, un effort et un palier qui y figurent. Rien n'est inventé : sans relevé, le
  catalogue est « Inconnu » et une étape du poste est refusée.

En P4, aucun relevé réel n'existe : les tests déposent un relevé ``source: "releve_factice"`` aux
identifiants manifestement factices, par la même fonction que la route P5.

Les champs des modèles gardent les noms de Codex (``displayName``, ``isDefault``,
``supportedReasoningEfforts``…) pour qu'un relevé se lise sans traduction. Les refus sont en français,
y compris pour un champ inconnu ou manquant (:func:`valider_releve`).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from ._validation import ContratValide

VOIES = ("poste-codex", "poste-claude")
SOURCES = ("poste", "releve_factice")
MODELES_MAX = 200
DEPOTS_MAX = 100
EFFORTS_MAX = 16
PALIERS_MAX = 16

_ID_MODELE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
_EFFORT = re.compile(r"[a-z][a-z0-9_-]{0,19}")
_PALIER = re.compile(r"[a-z][a-z0-9_-]{0,31}")
ALIAS_DEPOT = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+ -]{0,63}")


def _texte(valeur: Any, *, champ: str, maximum: int, motif: Optional[re.Pattern] = None) -> str:
    if not isinstance(valeur, str):
        raise ValueError(f"« {champ} » doit être une chaîne de caractères")
    if "\x00" in valeur:
        raise ValueError(f"« {champ} » : le caractère NUL (\\x00) est interdit")
    if not valeur.strip():
        raise ValueError(f"« {champ} » ne peut pas être vide")
    if len(valeur) > maximum:
        raise ValueError(f"« {champ} » : au maximum {maximum} caractères")
    if motif is not None and motif.fullmatch(valeur) is None:
        raise ValueError(f"« {champ} » : format invalide (« {valeur[:40]} »)")
    return valeur


def _liste_de_textes(valeur: Any, *, champ: str, maximum: int, motif: re.Pattern) -> List[str]:
    if not isinstance(valeur, list):
        raise ValueError(f"« {champ} » doit être une liste")
    if len(valeur) > maximum:
        raise ValueError(f"« {champ} » : au plus {maximum} éléments")
    textes = [_texte(v, champ=champ, maximum=32, motif=motif) for v in valeur]
    if len(set(textes)) != len(textes):
        raise ValueError(f"« {champ} » contient un doublon")
    return textes


def _instant(valeur: Any, *, champ: str) -> datetime:
    if isinstance(valeur, str):
        try:
            valeur = datetime.fromisoformat(valeur)
        except ValueError:
            raise ValueError(f"« {champ} » : horodatage ISO 8601 illisible") from None
    if not isinstance(valeur, datetime):
        raise ValueError(f"« {champ} » doit être un horodatage ISO 8601")
    if valeur.tzinfo is None or valeur.utcoffset() is None:
        raise ValueError(f"« {champ} » doit porter son fuseau (UTC attendu)")
    try:
        return valeur.astimezone(UTC)
    except (OverflowError, ValueError):
        raise ValueError(f"« {champ} » : horodatage hors de la plage UTC lisible") from None


class _Contrat(ContratValide):
    """Frontière JSON stricte : tout écart est refusé avec un message français."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _champs_declares_seulement(cls, donnees: Any) -> Any:
        if isinstance(donnees, BaseModel):
            donnees = donnees.model_dump()
        if not isinstance(donnees, Mapping):
            raise ValueError("un objet JSON est attendu")
        inconnus = sorted(str(cle) for cle in donnees if cle not in cls.model_fields)
        if inconnus:
            raise ValueError("champ inconnu refusé : " + ", ".join(f"« {nom} »" for nom in inconnus))
        manquants = [nom for nom, info in cls.model_fields.items() if info.is_required() and nom not in donnees]
        if manquants:
            raise ValueError("champ obligatoire absent : " + ", ".join(f"« {nom} »" for nom in manquants))
        return donnees


class ModeleReleve(_Contrat):
    """Un modèle tel que la CLI de la voie le déclare (champs de Codex ``model/list``)."""

    id: str
    displayName: Optional[str] = None  # noqa: N815 — nom de Codex
    isDefault: bool = False  # noqa: N815
    supportedReasoningEfforts: List[str] = []  # noqa: N815
    defaultReasoningEffort: Optional[str] = None  # noqa: N815
    serviceTiers: List[str] = []  # noqa: N815
    defaultServiceTier: Optional[str] = None  # noqa: N815

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, valeur: Any) -> str:
        return _texte(valeur, champ="id", maximum=128, motif=_ID_MODELE)

    @field_validator("displayName", mode="before")
    @classmethod
    def _nom(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="displayName", maximum=200)

    @field_validator("isDefault", mode="before")
    @classmethod
    def _defaut(cls, valeur: Any) -> bool:
        if type(valeur) is not bool:
            raise ValueError("« isDefault » doit être un booléen (true ou false)")
        return valeur

    @field_validator("supportedReasoningEfforts", mode="before")
    @classmethod
    def _efforts(cls, valeur: Any) -> List[str]:
        return _liste_de_textes(valeur, champ="supportedReasoningEfforts", maximum=EFFORTS_MAX, motif=_EFFORT)

    @field_validator("serviceTiers", mode="before")
    @classmethod
    def _paliers(cls, valeur: Any) -> List[str]:
        return _liste_de_textes(valeur, champ="serviceTiers", maximum=PALIERS_MAX, motif=_PALIER)

    @field_validator("defaultReasoningEffort", mode="before")
    @classmethod
    def _effort_defaut(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="defaultReasoningEffort", maximum=20, motif=_EFFORT)

    @field_validator("defaultServiceTier", mode="before")
    @classmethod
    def _palier_defaut(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="defaultServiceTier", maximum=32, motif=_PALIER)

    @model_validator(mode="after")
    def _coherence(self) -> "ModeleReleve":
        if self.defaultReasoningEffort and self.defaultReasoningEffort not in self.supportedReasoningEfforts:
            raise ValueError(f"modèle « {self.id} » : l'effort par défaut « {self.defaultReasoningEffort} » ne "
                             "figure pas parmi ses efforts pris en charge")
        if self.defaultServiceTier and self.defaultServiceTier not in self.serviceTiers:
            raise ValueError(f"modèle « {self.id} » : le palier par défaut « {self.defaultServiceTier} » ne "
                             "figure pas parmi ses paliers")
        return self


class Quotas(_Contrat):
    """Part utilisée de l'abonnement de la voie et prochaine remise à zéro, telles que relevées
    (``None`` : inconnu, jamais estimé)."""

    pourcentage_utilise: Optional[float] = None
    remise_a_zero: Optional[datetime] = None

    @field_validator("pourcentage_utilise", mode="before")
    @classmethod
    def _pourcentage(cls, valeur: Any) -> Optional[float]:
        if valeur is None:
            return None
        if type(valeur) not in (int, float) or not math.isfinite(valeur) or not 0 <= valeur <= 100:
            raise ValueError("« pourcentage_utilise » doit être un nombre fini compris entre 0 et 100")
        return float(valeur)

    @field_validator("remise_a_zero", mode="before")
    @classmethod
    def _remise(cls, valeur: Any) -> Optional[datetime]:
        return None if valeur is None else _instant(valeur, champ="remise_a_zero")


class Depot(_Contrat):
    """Un dépôt autorisé par le poste, connu du greffon par son seul alias (jamais un chemin)."""

    alias: str

    @field_validator("alias", mode="before")
    @classmethod
    def _alias(cls, valeur: Any) -> str:
        return _texte(valeur, champ="alias", maximum=32, motif=ALIAS_DEPOT)


class Releve(_Contrat):
    """Relevé complet d'une voie du poste."""

    voie: str
    source: str
    version_cli: Optional[str] = None
    releve_le: datetime
    modeles: List[ModeleReleve]
    quotas: Optional[Quotas] = None
    depots: List[Depot] = []

    @field_validator("voie", mode="before")
    @classmethod
    def _voie(cls, valeur: Any) -> str:
        if valeur not in VOIES:
            raise ValueError(f"« voie » : valeurs admises : {', '.join(VOIES)}")
        return valeur

    @field_validator("source", mode="before")
    @classmethod
    def _source(cls, valeur: Any) -> str:
        if valeur not in SOURCES:
            raise ValueError(f"« source » : valeurs admises : {', '.join(SOURCES)}")
        return valeur

    @field_validator("version_cli", mode="before")
    @classmethod
    def _version(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="version_cli", maximum=64, motif=_VERSION)

    @field_validator("releve_le", mode="before")
    @classmethod
    def _releve_le(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="releve_le")

    @field_validator("modeles", mode="before")
    @classmethod
    def _modeles(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list) or not valeur:
            raise ValueError("« modeles » doit être une liste non vide")
        if len(valeur) > MODELES_MAX:
            raise ValueError(f"« modeles » : au plus {MODELES_MAX} modèles")
        return valeur

    @field_validator("depots", mode="before")
    @classmethod
    def _depots(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list):
            raise ValueError("« depots » doit être une liste")
        if len(valeur) > DEPOTS_MAX:
            raise ValueError(f"« depots » : au plus {DEPOTS_MAX} dépôts")
        return valeur

    @model_validator(mode="after")
    def _uniques(self) -> "Releve":
        ids = [m.id for m in self.modeles]
        if len(set(ids)) != len(ids):
            raise ValueError("« modeles » : identifiant de modèle en double")
        if sum(1 for m in self.modeles if m.isDefault) > 1:
            raise ValueError("« modeles » : un seul modèle peut être le modèle par défaut")
        alias = [d.alias for d in self.depots]
        if len(set(alias)) != len(alias):
            raise ValueError("« depots » : alias en double")
        return self

    def modele(self, identifiant: str) -> Optional[ModeleReleve]:
        return next((m for m in self.modeles if m.id == identifiant), None)

    def modele_par_defaut(self) -> Optional[ModeleReleve]:
        return next((m for m in self.modeles if m.isDefault), None)


def _message(erreur: Mapping[str, Any]) -> str:
    texte = str(erreur.get("msg") or "valeur refusée")
    for prefixe in ("Value error, ", "Assertion failed, "):
        if texte.startswith(prefixe):
            texte = texte[len(prefixe):]
    lieu = ".".join(str(p) for p in erreur.get("loc") or () if p != "__root__")
    if erreur.get("type") == "missing":
        texte = "champ obligatoire absent"
    elif erreur.get("type") in ("list_type", "dict_type", "model_type"):
        texte = "type invalide"
    return f"{lieu} : {texte}" if lieu else texte


def valider_releve(donnees: Any) -> Releve:
    """Relevé validé, ou ``ValueError`` au message français (« Relevé refusé : … »)."""
    try:
        return Releve.model_validate(donnees)
    except ValidationError as exc:
        details = "; ".join(_message(e) for e in exc.errors()[:5])
        raise ValueError(f"Relevé refusé : {details}.") from None
